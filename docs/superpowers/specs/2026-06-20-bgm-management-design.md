# AutoVideo BGM 管理设计

日期：2026-06-20

## 背景

用户确认方案 A：参考目标项目 `/Users/sha/junxincode` 中的视频 BGM 管理模型，在 AutoVideo 内实现独立的 BGM 管理能力，并在混剪工作台中保存可稳定引用的 BGM 配置。

目标项目中可参考的能力包括：

1. `video-generator/app/services/bgm_service.py`：支持音频文件入库、自定义分类、试听 URL、重命名、删除和按分类选曲。
2. `web/video/shared/bgm-library.js`：定义 BGM 列表、分类、摘要和前端 API 契约。
3. `web/video/bgm-page.js`：提供上传、分类维护、列表试听、重命名、分类迁移和删除交互。
4. `web/video/courseware*.js` 与 `web/video/mix.html`：在任务创建页按分类过滤并选择具体 BGM。

AutoVideo 当前已经有 `data/bgm` 目录约定，但 `BGM 管理` 导航仍是禁用状态。现有音色中心和字幕模板已经形成了本仓更适合的模式：FastAPI 路由只做请求/错误映射，服务层负责文件和元数据，React 工作台负责中文状态、移动端可用性和任务选项快照。因此本次不直接复制旧 WebUI，而是按 AutoVideo 的 FastAPI + React + TypeScript 边界重做。

## 目标

1. 启用 `BGM 管理` 一级入口，用户可以上传、分类、试听、重命名和删除 BGM。
2. 后端提供 `/api/bgm` 资源接口，保存 BGM 文件和 JSON 元数据，返回稳定 BGM ID，不暴露本地路径。
3. 支持自定义 BGM 分类；删除分类时分类下的 BGM 迁移到未分类，不删除音频文件。
4. 混剪工作台支持选择 BGM 分类、具体 BGM 和音量，并在任务 `options` 与 manifest 中保存清洗后的 BGM 快照。
5. 桌面端和移动端都可读、可点、可滚动，不依赖 hover；移动端核心控件不低于 44px 触控高度。
6. README 同步说明 BGM 管理与混剪任务 BGM 选择已接入，并明确最终 MP4 暂未混入 BGM 音轨。

## 非目标

1. 不在本次把 BGM 实际混入最终 MP4。
2. 不实现多轨混音、淡入淡出、节拍点分析、响度标准化或自动 ducking。
3. 不引入版权 BGM 商店、在线 BGM 采购、商业授权流程。
4. 不接入登录、权限管理、团队空间或用户隔离。
5. 不迁移目标项目的数据库表、旧登录态、token 拼接逻辑或内网配置。

## 方案对比

### 方案 A：资源管理 + 混剪任务引用入口

新增 AutoVideo 原生 BGM 服务、API、前端 BGM 管理页和混剪工作台选择器。任务创建时保存 `bgm_track_id`、`bgm_display_name`、`bgm_category_id`、`bgm_category_name`、`bgm_volume` 和必要文件元数据快照，但渲染链路暂不混音。

优点是用户能立刻管理并选择 BGM，任务数据结构也为后续 FFmpeg 混音留好入口；范围可控，能独立测试。缺点是最终输出视频暂时不会带 BGM，需要 README 和 UI 文案明确说明。

### 方案 B：只做 BGM 管理页

只启用 BGM 管理页面，不接混剪任务。优点是风险最低；缺点是资源中心和任务流脱节，无法满足产品设计里“混剪任务引用稳定 ID”的目标。

### 方案 C：同时完成最终 MP4 BGM 混音

在本次同时修改 FFmpeg 渲染命令，把选定 BGM 混入输出视频。优点是用户能拿到完整带背景音乐的视频；缺点是范围跨越音频时长裁剪、循环、音量、失败清理、输出状态语义和回归验证，风险明显高于当前需求。

推荐方案 A。

## 后端设计

新增 `autovideo/services/bgm/`，按职责拆分：

1. `models.py`：BGM item、category、library response、上传/更新请求模型。
2. `service.py`：文件写入、元数据读写、分类维护、列表过滤、试听路径解析。
3. `__init__.py`：导出服务层公共 API。

新增 `autovideo/api/routes/bgm.py`，路由前缀为 `/api/bgm`：

1. `GET /api/bgm`：返回 BGM 库，包含 `items`、`categories`、`storage_status`、`total_tracks`、`supported_extensions`；不得返回 `data/bgm` 或任何本机绝对/相对目录路径。
2. `POST /api/bgm/tracks`：multipart 上传音频文件，可附带 `category_id`。支持扩展名为 `mp3`、`wav`、`m4a`、`aac`、`ogg`、`flac`。
3. `PUT /api/bgm/tracks/{track_id}`：更新显示名和分类。
4. `DELETE /api/bgm/tracks/{track_id}`：删除 BGM 文件并从元数据中移除。
5. `GET /api/bgm/tracks/{track_id}/file`：返回可播放音频文件。
6. `POST /api/bgm/categories`：创建分类。
7. `PUT /api/bgm/categories/{category_id}`：更新分类名称。
8. `DELETE /api/bgm/categories/{category_id}`：删除分类，相关 BGM 迁移到未分类。

`POST /api/bgm/tracks` 必须接入 `autovideo/api/app.py` 现有 request size middleware 的分支判断，multipart 请求上限使用 `AUTOVIDEO_MAX_UPLOAD_BYTES + AUTOVIDEO_MAX_MULTIPART_OVERHEAD_BYTES`，不要另写硬编码大小。服务层仍需在读取上传文件后做文件大小和空文件二次校验，避免绕过中间件或测试客户端差异导致无效文件入库。

错误返回使用现有 `structured_error`：

```json
{
  "detail": {
    "code": "BGM_FILE_UNSUPPORTED",
    "allowed": ["mp3", "wav", "m4a", "aac", "ogg", "flac"]
  }
}
```

核心错误码：

1. `BGM_FILE_UNSUPPORTED`：音频扩展名、探测到的媒体类型或音频流不支持。
2. `BGM_FILE_EMPTY`：上传文件为空。
3. `BGM_TRACK_NOT_FOUND`：BGM 不存在或文件缺失。
4. `BGM_CATEGORY_NOT_FOUND`：分类不存在。
5. `BGM_CATEGORY_DUPLICATE`：分类名称重复。
6. `BGM_CATEGORY_NAME_REQUIRED`：分类名为空。
7. `BGM_TRACK_NAME_REQUIRED`：BGM 显示名为空。
8. `BGM_CATEGORY_EMPTY`：启用 BGM 且仅选择分类时，当前分类没有可用曲目。

## 数据设计

第一版继续使用文件系统 + JSON 元数据，避免引入额外数据库迁移。

目录：

```text
data/
  bgm/
    tracks/
      <track-id>.<ext>
    bgm_library.json
```

`track_id` 使用稳定、不可从原始文件名直接推导的 ID，例如 `bgm_<uuid>`。原始文件名只作为元数据保存和显示。这样用户重命名显示名或上传同名文件时，不会破坏任务引用。

元数据结构：

```json
{
  "version": 1,
  "categories": [
    {
      "id": "cat_550e8400e29b41d4a716446655440000",
      "name": "舒缓",
      "sort_order": 10,
      "created_at": "2026-06-20T00:00:00Z",
      "updated_at": "2026-06-20T00:00:00Z"
    }
  ],
  "tracks": [
    {
      "id": "bgm_abc123",
      "filename": "bgm_abc123.mp3",
      "original_filename": "春日疗愈.mp3",
      "display_name": "春日疗愈",
      "category_id": "cat_550e8400e29b41d4a716446655440000",
      "media_type": "audio/mpeg",
      "extension": "mp3",
      "size_bytes": 123456,
      "duration_seconds": 184.32,
      "created_at": "2026-06-20T00:00:00Z",
      "updated_at": "2026-06-20T00:00:00Z"
    }
  ]
}
```

服务层返回给前端的 item 增加：

1. `category_name`：无分类时为 `未分类`。
2. `audio_url`：`/api/bgm/tracks/{track_id}/file`。
3. `duration_seconds`：由服务端探测得到的音频时长，前端只负责展示。
4. `track_count`：分类列表中按当前元数据统计。

媒体校验必须由服务端完成：扩展名只作为第一层 allowlist，上传后使用 `ffprobe` 或等价探测确认文件存在 audio stream，读取 `duration_seconds`，并将 `media_type` 归一到固定 allowlist。不能信任客户端传入的 `content_type`、原始文件名或扩展名；伪造扩展名、无音频流、无法探测时都返回 `BGM_FILE_UNSUPPORTED` 并清理临时文件。试听接口返回音频时设置安全 headers，例如 `X-Content-Type-Options: nosniff`，`Content-Type` 使用服务端探测/归一后的媒体类型。

元数据写入使用临时文件 + `replace` 原子替换，避免中途写坏 JSON。上传文件先落到临时路径，元数据更新成功后再进入正式文件名；如果更新失败，清理临时文件。原子替换只是持久化手段，不替代并发控制：BGM library CRUD 必须有 per-library mutation lock，上传、重命名、删除、分类创建、分类重命名、分类删除迁移的 read-modify-write 全流程都在同一把锁内完成，避免并发请求互相覆盖 JSON。当前单进程部署可使用进程内锁；如果未来改为多进程或多实例部署，必须升级为文件锁、进程间锁或数据库事务锁。

## 混剪任务设计

在 `autovideo/services/online_mix.py` 新增 `normalize_bgm_options(options, bgm_service)`，与现有字幕和音色归一流程并列。

输入字段：

1. `bgm_enabled?: boolean`
2. `bgm_track_id?: string | null`
3. `bgm_category_id?: string | null`
4. `bgm_volume?: number | null`

输出字段：

```json
{
  "bgm_enabled": true,
  "bgm_track_id": "bgm_abc123",
  "bgm_display_name": "春日疗愈",
  "bgm_category_id": "cat_550e8400e29b41d4a716446655440000",
  "bgm_category_name": "舒缓",
  "bgm_volume": 0.12,
  "bgm_snapshot": {
    "id": "bgm_abc123",
    "display_name": "春日疗愈",
    "filename": "bgm_abc123.mp3",
    "original_filename": "春日疗愈.mp3",
    "media_type": "audio/mpeg",
    "size_bytes": 123456,
    "duration_seconds": 184.32
  }
}
```

规则：

1. `bgm_enabled` 为 false 时，所有 BGM 字段归一为空，`bgm_volume` 归一为 `null`。
2. `bgm_track_id` 非空时必须能找到对应 BGM，否则返回 `BGM_TRACK_NOT_FOUND`。
3. `bgm_track_id` 为空但 `bgm_category_id` 非空时，任务创建阶段必须从当前分类解析出一个具体 track，并把该 track 写入 `bgm_track_id` 与 `bgm_snapshot`。解析策略第一版使用稳定顺序的第一首或服务层确定性选择，不能留到未来渲染阶段再根据变化后的分类库随机选曲。
4. `bgm_category_id` 非空时必须存在，否则返回 `BGM_CATEGORY_NOT_FOUND`。
5. 分类-only 解析时如果当前分类没有曲目，返回结构化错误，例如 `BGM_CATEGORY_EMPTY`，不要创建缺少具体曲目快照的任务。
6. `bgm_volume` 默认 `0.12`，范围限制为 `0` 到 `1`，前端显示为百分比。
7. 本次 render plan 保持现有视频渲染状态，manifest 中的 `bgm_mix_status` 必须区分未请求和已选择但未混入：未启用 BGM 时为 `"not_requested"`；启用并成功保存 `bgm_snapshot` 但本轮没有混音时为 `"selected_not_mixed"`，避免误导用户认为输出已带 BGM。

## 前端设计

新增 `frontend/src/api/bgm.ts`：

1. `fetchBgmLibrary()`
2. `uploadBgmTrack(input)`
3. `updateBgmTrack(input)`
4. `deleteBgmTrack(trackId)`
5. `createBgmCategory(input)`
6. `updateBgmCategory(input)`
7. `deleteBgmCategory(categoryId)`
8. `BgmApiError` 与中文错误映射 helper。

新增 `frontend/src/components/BgmManagementWorkbench.tsx`：

1. 上传区：文件选择、分类选择、上传按钮、支持格式提示。
2. 分类区：新增分类、分类列表、重命名、删除；删除前确认“分类下 BGM 会移动到未分类”。
3. BGM 列表：显示名称、原始文件名、大小、分类、更新时间、试听播放器、重命名、分类迁移、删除。
4. 空状态：`还没有 BGM，先上传一条背景音乐。`
5. 错误状态：接口失败时显示中文错误和重试按钮。

新增 `frontend/src/components/BgmSelector.tsx` 用于混剪工作台：

1. 可切换是否启用 BGM。
2. 选择分类；分类变化时过滤曲目。
3. 选择具体 BGM；可选“从当前分类自动选择”。
4. 调整音量，默认 12%。
5. 选中具体 BGM 时显示 `<audio>` 试听。
6. 提供 `onOpenBgmManagement` 入口跳转到 BGM 管理页。

调整 `frontend/src/App.tsx`：

1. `ActiveSection` 增加 `bgm`。
2. 导航中 `BGM 管理` 改为 enabled。
3. `sectionHeadings` 增加 BGM 标题和摘要。
4. `activeSectionFromHash` 支持 `#bgm`。
5. `openedSections` 增加 BGM 懒加载状态。
6. 移动端导航继续保持 enabled 项前置，BGM 应出现在 disabled 占位项之前。

## 移动端与可访问性

页面遵循当前 AutoVideo 的工作台风格，不做营销式 hero。

桌面端：

1. BGM 管理页使用上传/分类/列表的两列或三列工作区，列表区域优先占宽。
2. BGM 条目使用紧凑面板，播放器、名称输入、分类选择和操作按钮在宽屏横向排列。
3. 分类区保持可扫描，不嵌套卡片。

移动端：

1. 上传、分类、列表全部单列。
2. BGM 条目的音频播放器、输入框、选择框和按钮分行排列，宽度 100%。
3. 文件选择、按钮、select、input 最小高度 44px。
4. 音频播放器 `width: 100%; max-width: 100%;`，不撑破容器。
5. 移动端不依赖 hover；删除和保存必须是可见按钮。
6. `document.body.scrollWidth <= window.innerWidth` 应在 375px 视口成立。

可访问性：

1. 所有 icon-only 场景必须提供 `aria-label`，优先使用 Lucide 图标。
2. 上传、分类名、BGM 名称、分类选择、音量滑杆使用可见 label。
3. 加载状态使用 `role="status"` 和 `aria-live="polite"`。
4. 错误状态使用 `role="alert"`。
5. 删除 BGM 和删除分类使用确认弹窗或等价确认机制。
6. 颜色不作为唯一状态表达，成功/错误同时有文字。

## 错误与边界

1. 上传同名文件不会覆盖已有 BGM，因为正式文件名使用稳定 ID。
2. 原始文件名中不安全字符不会进入实际路径。
3. 下载接口只允许读取 `data/bgm/tracks` 下的已登记文件。
4. JSON 元数据损坏时返回结构化 500，并提示用户保留文件目录用于人工恢复；不要静默清空数据。
5. 删除 BGM 会删除音频文件和元数据；如果元数据存在但文件已缺失，接口清理元数据并返回删除成功；如果 ID 从未登记，返回 `BGM_TRACK_NOT_FOUND`。
6. 分类名称大小写不敏感去重，去除首尾空白。
7. 上传请求大小必须同时经过 `autovideo/api/app.py` request size middleware 和服务层二次校验；middleware 分支使用 `AUTOVIDEO_MAX_UPLOAD_BYTES + AUTOVIDEO_MAX_MULTIPART_OVERHEAD_BYTES`，服务层校验实际文件大小和空文件。
8. 并发上传、重命名、删除、分类迁移和分类删除不能丢失彼此的 JSON 元数据更新；所有 library mutation 都必须走同一把 per-library mutation lock。

## 测试计划

后端服务测试：

1. 上传支持格式的 BGM 后生成稳定 ID、保存原始文件名、显示名、大小、分类和 `duration_seconds`。
2. 拒绝不支持扩展名、伪造扩展名、伪造音频和无 audio stream 文件，并返回 `BGM_FILE_UNSUPPORTED`。
3. 拒绝空文件并返回 `BGM_FILE_EMPTY`。
4. 同名上传生成不同稳定 ID，不覆盖旧文件。
5. 重命名 BGM 后 ID 和音频 URL 不变。
6. 分类创建、重命名、重复名校验、删除迁移到未分类。
7. 试听下载接口拒绝路径穿越和不存在 ID。
8. 并发执行上传、重命名、删除和分类迁移时 JSON 元数据不丢更新。
9. 损坏的 `bgm_library.json` 返回结构化 500，且不会自动清空或覆盖原文件。

API 测试：

1. `GET /api/bgm` 返回 items、categories、storage_status、total_tracks、supported_extensions，且不包含本机路径字段。
2. `POST /api/bgm/tracks` 上传后可通过 `audio_url` 播放。
3. `PUT /api/bgm/tracks/{track_id}` 更新显示名和分类。
4. `DELETE /api/bgm/categories/{category_id}` 后相关曲目 `category_id` 为 null。
5. `POST /api/bgm/tracks` 大小超限请求命中 `autovideo/api/app.py` request size middleware 并返回 413，覆盖 `AUTOVIDEO_MAX_UPLOAD_BYTES + AUTOVIDEO_MAX_MULTIPART_OVERHEAD_BYTES` 的 multipart 场景。
6. 试听响应包含安全 headers，例如 `X-Content-Type-Options: nosniff`。

混剪任务测试：

1. 创建线上混剪任务时持久化具体 BGM 字段到 task options 和 manifest。
2. 未启用 BGM 时 BGM 字段归一为空。
3. 只选择分类时在任务创建阶段解析出具体 track，保存 `bgm_track_id` 和 `bgm_snapshot`。
4. 分类-only 创建时如果分类为空，返回结构化 `BGM_CATEGORY_EMPTY` 错误。
5. 无效 BGM ID 或分类 ID 返回结构化 400/404。
6. manifest 中未启用 BGM 时出现 `bgm_mix_status: "not_requested"`，启用并选择成功但未混音时出现 `bgm_mix_status: "selected_not_mixed"`。

前端测试：

1. 导航启用 `BGM 管理`，`#bgm` 可直接打开。
2. BGM 管理页显示上传、分类、列表、空状态、错误状态。
3. 上传成功后刷新列表并清空文件输入。
4. 分类删除文案包含“移动到未分类”。
5. 混剪工作台提交任务时带上 BGM 选项。
6. CSS 覆盖 375px 移动端单列、44px 触控高度、播放器不溢出、无 hover-only 依赖。
7. Vite build 通过。

可视化验证：

1. 启动本地前端或生产构建预览。
2. 桌面视口检查 BGM 管理页上传、分类、列表和播放器布局。
3. 375px 视口检查移动端导航中 BGM 入口可见、页面无横向溢出、控件可点击。
4. 混剪工作台中 BGM 选择器在 375px 和桌面端都不遮挡字幕和音色设置。

## README 更新

README 需要同步：

1. “尚未接入 BGM 上传”改为 BGM 管理已接入。
2. API 列表新增 `/api/bgm` 相关接口。
3. 混剪任务 `options` 说明新增 BGM 字段。
4. 明确当前最终视频还未混入 BGM 音轨，BGM 字段用于任务配置和后续混音。
5. 示例 curl 增加 BGM 列表或上传示例，不能包含本机真实路径或凭据。
6. 本轮帮助文档面以 README 为准；如果仓库后续新增独立 help 页面或内置帮助入口，再把同一说明同步到对应入口。

## 验收标准

1. 用户能在 BGM 管理页上传一条音频，并立即在列表中试听。
2. 用户能新增分类，把 BGM 移入分类，删除分类后 BGM 显示为未分类。
3. 用户能重命名和删除 BGM。
4. 用户能在混剪工作台选择 BGM 分类、具体 BGM 和音量。
5. 创建任务后 task options 与 manifest 保存清洗后的 BGM 字段和快照。
6. 最终输出 UI 与 README 不声明当前 MP4 已混入 BGM。
7. 375px 移动端无横向溢出，主要控件可读、可点、可滚动。
8. 相关后端、API、前端测试和构建通过。

## 后续阶段

下一阶段可基于本次保存的 `bgm_snapshot` 和 `bgm_volume` 接入 FFmpeg 混音：

1. 根据视频时长裁剪或循环 BGM。
2. 使用 `bgm_volume` 控制背景音乐响度。
3. 在 manifest 中记录 `bgm_mix_status`、输入 BGM、实际混音参数和失败原因。
4. 成功时输出带 BGM 的 `output.mp4`，失败时明确区分视频渲染失败和音频混音失败。
