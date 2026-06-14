# AutoVideo 线上免费资源混剪与脚本自动生成设计

日期：2026-06-14

## 背景

AutoVideo 当前已经具备产品骨架、素材上传 API、任务创建 API 和占位输出下载能力，但前端和后端还没有形成“输入主题 -> 自动生成脚本 -> 获取线上免费素材 -> 创建混剪任务”的闭环。

目标项目中可参考的能力主要分为三类，只保留根目录 `/Users/sha/junxincode` 和文件名作为脱敏定位线索。实施前必须先运行 `rg --files /Users/sha/junxincode | rg '/(script_generator|online_material_service|video_composer)\.py$'` 定位确认，避免复用已经移动、删除或重命名的旧路径：

1. `script_generator.py`：把主题或用户文案整理为结构化分镜脚本。
2. `online_material_service.py`：用 Pexels、Pixabay 搜索和下载线上免费视频素材。
3. `video_composer.py`：根据分镜、素材、字幕和 BGM 做实际视频合成。

本阶段只抽取独立产品需要的业务边界和数据形状，不搬旧项目的权限、个人网盘、公盘 SMB、worker、内网 token、云端专有服务或历史兼容逻辑。旧项目配置值、部署路径、token、内网服务地址不能复制到 AutoVideo；不得提交或复制旧项目部署路径、内网地址、token、真实服务地址；需要配置时只新增 AutoVideo 自己的环境变量和文档占位。

## 目标

1. 支持用户输入主题后自动生成短视频分镜脚本。
2. 支持按每个分镜的关键词和画面描述搜索线上免费素材。
3. 支持下载选中的线上素材到本地素材库，并保留来源和授权备注。
4. 支持基于自动脚本和线上素材创建混剪任务快照。
5. 第一版输出仍为 manifest，占位说明完整记录脚本、素材来源、授权备注和后续渲染参数。
6. 所有外部服务配置通过环境变量提供，不提交任何 API key 或真实服务地址。
7. 前端提供可用的最小工作流：填写主题、生成脚本、查看素材匹配、创建任务、查看任务输出。

## 非目标

本阶段不做以下能力：

1. 不实现真实 FFmpeg 拼接渲染。
2. 不接旧项目的个人网盘、公盘、SMB、公共素材 worker 或内网素材索引。
3. 不接登录、权限管理、团队空间或多租户。
4. 不实现 BGM 管理、字幕模板编辑、音色中心和 TTS 生成。
5. 不自动发布视频，不抓取社媒内容，不复用外部热门视频素材本体。
6. 不把 Pexels、Pixabay 或任何 LLM provider 的 key 写入仓库。

## 方案选择

### 方案 A：完整搬迁目标项目 video-generator

优点是功能完整，包含脚本生成、素材匹配、TTS、字幕、BGM 和视频合成。缺点是旧项目耦合了大量内网、worker、网盘、云端 LLM、历史兼容和部署约束，直接搬迁会把 AutoVideo 的独立边界打乱。

不采用。

### 方案 B：轻量闭环，先做脚本和线上素材 manifest

后端新增独立的 `scripts`、`online_materials`、`online_mix` 服务。第一阶段生成结构化脚本，按镜头检索 Pexels/Pixabay，下载素材到本地素材库，并创建包含脚本与来源信息的任务 manifest。真实渲染留到下一阶段。

采用。这个方案最小、可测试，并且和当前 API 骨架自然衔接。

### 方案 C：先只做前端工作台接线

只把现有素材上传和任务 API 接到前端，不做线上素材和脚本生成。优点是快，缺点是没有覆盖用户当前明确提出的“线上免费资源混剪、脚本自动生成”。

不采用。

## 外部服务与配置

新增配置均使用 `AUTOVIDEO_` 前缀：

```dotenv
AUTOVIDEO_LLM_PROVIDER=openai_compatible
AUTOVIDEO_LLM_BASE_URL=
AUTOVIDEO_LLM_API_KEY=
AUTOVIDEO_LLM_MODEL=
AUTOVIDEO_LLM_TIMEOUT_SECONDS=45
AUTOVIDEO_LLM_TEMPERATURE=0.6

AUTOVIDEO_PEXELS_API_KEY=
AUTOVIDEO_PIXABAY_API_KEY=
AUTOVIDEO_ONLINE_MATERIAL_PROVIDER=auto
AUTOVIDEO_ONLINE_MATERIAL_RESULTS_PER_QUERY=8
AUTOVIDEO_ONLINE_MATERIAL_DOWNLOAD_TIMEOUT_SECONDS=60
AUTOVIDEO_ONLINE_MATERIAL_MAX_DOWNLOAD_BYTES=524288000
AUTOVIDEO_CANDIDATE_TOKEN_SECRET=
AUTOVIDEO_CANDIDATE_TOKEN_TTL_SECONDS=1800
```

LLM 未配置时，后端使用本地启发式脚本 fallback。Pexels/Pixabay key 均未配置时，线上素材搜索接口返回结构化错误，前端显示配置提示。Pexels/Pixabay provider 已配置但 `AUTOVIDEO_CANDIDATE_TOKEN_SECRET` 缺失时，任何需要签发或验证可下载候选的搜索、自动匹配、候选签发或用户候选回传路径必须返回 `ONLINE_MATERIAL_TOKEN_SECRET_NOT_CONFIGURED` 结构化错误，不能返回无 `candidate_token` 的候选，也不能退化为 invalid token 或 500。`AUTOVIDEO_CANDIDATE_TOKEN_TTL_SECONDS` 默认 1800 秒，即 30 分钟；签发 `candidate_token` 时，payload 中的 `expires_at` 必须使用当前时间加该 TTL 计算。

## 数据模型

### 脚本

后端返回结构化脚本：

```json
{
  "id": "script_id",
  "title": "视频标题",
  "topic": "主题",
  "aspect_ratio": "9:16",
  "duration_seconds": 30,
  "shots": [
    {
      "index": 1,
      "duration": 5,
      "narration": "旁白",
      "subtitle": "屏幕字幕",
      "visual_description": "画面描述",
      "keywords": ["关键词"]
    }
  ],
  "provider": "llm|heuristic",
  "created_at": "iso8601"
}
```

### 线上素材候选

素材候选不直接暴露本地路径：

```json
{
  "provider": "pexels",
  "asset_id": "123",
  "query": "office work",
  "source_url": "https://...",
  "candidate_token": "signed-candidate-token",
  "preview_url": "https://...",
  "file_variant": "hd",
  "duration": 8.5,
  "width": 1080,
  "height": 1920,
  "license_note": "Pexels/Pixabay source metadata retained"
}
```

`candidate_token` 是后端签名的候选凭证，客户端只能持有和回传它，不能得到 provider 真实下载地址。`file_variant` 表示后端允许下载的 provider 文件档位。token payload 的 `expires_at` 由 `AUTOVIDEO_CANDIDATE_TOKEN_TTL_SECONDS` 控制，默认签发后 30 分钟过期。

候选与素材元数据中的 URL 必须区分用途：

1. `source_url`：公开来源页或归因页 URL，只用于来源追踪、授权归因和 manifest 记录；可以进入公开 API 与 manifest，但不能是 direct media URL、真实下载 URL 或临时下载 URL。
2. `preview_url`：只用于前端预览，可以进入候选响应，但也必须经过 provider allowlist 校验；它不能作为下载依据，后端下载时不得信任或回放该 URL。
3. `download_url`：provider adapter 内部临时解析出的真实下载 URL，只能在下载流程内部短暂使用；不得进入候选响应、公开 API、manifest、日志、DB 公开字段或前端状态。如因内部排障或缓存必须保存，也必须存放在隔离的内部字段或短期内存上下文中，并禁止向外泄漏。

### 本地素材元数据扩展

`materials` 表继续保留原有字段，同时新增可选来源字段。SQLite 迁移需要向后兼容已有数据库：

1. `source_type`：`upload` 或 `online`.
2. `source_provider`：`pexels`、`pixabay` 或空。
3. `source_asset_id`：线上素材 ID。
4. `source_url`：公开来源页或归因页 URL，不能是 direct media URL、真实下载 URL 或临时下载 URL。
5. `license_note`：授权备注。
6. `query`：命中的搜索词。

公开 API 只返回这些安全元数据，不返回 `storage_path`。

## 后端 API

### 生成脚本

`POST /api/scripts/generate`

请求：

```json
{
  "topic": "精油睡眠放松",
  "provider": "auto",
  "duration_seconds": 30,
  "aspect_ratio": "9:16",
  "tone": "自然、可信",
  "target_audience": "睡眠质量差的年轻人",
  "selling_points": ["舒缓", "睡前仪式感"]
}
```

响应返回结构化脚本。错误包括：

1. `SCRIPT_TOPIC_REQUIRED`
2. `SCRIPT_PAYLOAD_TOO_LARGE`
3. `LLM_NOT_CONFIGURED` 只在请求 `provider=llm_only` 且 LLM 未配置时返回；`provider=auto` 默认 fallback 到启发式脚本，`provider=heuristic` 只使用本地启发式脚本。

`provider` 允许值：

1. `auto`：优先 LLM，未配置或失败时按策略 fallback 到启发式脚本。
2. `llm_only`：必须使用 LLM，未配置时返回 `LLM_NOT_CONFIGURED`。
3. `heuristic`：不调用 LLM，直接使用本地启发式脚本。

### 搜索线上素材

`POST /api/online-materials/search`

请求：

```json
{
  "query": "relaxing bedroom night",
  "aspect_ratio": "9:16",
  "min_duration_seconds": 4,
  "provider": "auto"
}
```

响应返回候选数组。搜索结果只来自配置了 API key 的 provider。

当至少一个素材 provider 已配置、但 `AUTOVIDEO_CANDIDATE_TOKEN_SECRET` 缺失时，搜索接口不能签发可下载候选，必须返回结构化错误：

```json
{
  "detail": {
    "code": "ONLINE_MATERIAL_TOKEN_SECRET_NOT_CONFIGURED",
    "message": "未配置线上素材候选签名密钥"
  }
}
```

### 线上素材源状态

`GET /api/online-materials/status`

响应返回 provider 配置状态，不泄漏 API key、token 或真实下载地址：

```json
{
  "providers": [
    {
      "provider": "pexels",
      "configured": true,
      "enabled": true
    },
    {
      "provider": "pixabay",
      "configured": false,
      "enabled": false
    }
  ],
  "default_provider": "auto",
  "candidate_token_secret_configured": true
}
```

`candidate_token_secret_configured` 只返回布尔值，不泄漏 `AUTOVIDEO_CANDIDATE_TOKEN_SECRET` 的实际值。前端运行检查应使用该字段提前显示“候选签名密钥未配置”，避免用户到下载或创建任务阶段才看到失败。

### 下载线上素材

`POST /api/online-materials/download`

请求：

```json
{
  "candidate_token": "signed-candidate-token"
}
```

下载接口不得信任客户端提交的 `download_url` 或 `source_url`，请求体只能接收 `candidate_token`。token payload 包含 `provider`、`asset_id`、`query`、`file_variant`、`source_url`、`expires_at` 和 HMAC。后端验证 HMAC、过期时间、provider 启用状态和 payload 完整性后，由 provider adapter 重新解析真实下载 URL，再下载到 `AUTOVIDEO_DATA_DIR/materials`，插入素材记录并返回公开素材对象。

`POST /api/online-materials/download` 校验顺序必须固定：

1. 先检查素材 provider 配置；没有可用素材 provider 时返回 `ONLINE_MATERIAL_PROVIDER_NOT_CONFIGURED`。
2. 若素材 provider 已配置但 `AUTOVIDEO_CANDIDATE_TOKEN_SECRET` 缺失，优先返回 `ONLINE_MATERIAL_TOKEN_SECRET_NOT_CONFIGURED`，不能返回 500，也不能返回 `ONLINE_MATERIAL_CANDIDATE_TOKEN_INVALID`。
3. 只有 secret 已配置后，才解析和校验 `candidate_token`；缺少 `candidate_token`、token 格式错误、payload 不完整、HMAC 失败统一返回 `ONLINE_MATERIAL_CANDIDATE_TOKEN_INVALID`。
4. token 格式和 HMAC 有效但 `expires_at` 已过期时，返回 `ONLINE_MATERIAL_CANDIDATE_TOKEN_EXPIRED`。
5. token 有效后再检查 token payload 中的 provider 是否启用、是否允许对应 `file_variant`，并由 provider adapter 重新解析内部 `download_url`。

下载必须满足：

1. 只允许 `https` URL。
2. 限制响应大小。
3. 流式写入临时文件，完成后原子替换。
4. MIME 和扩展名只允许常见视频格式，未知后缀使用 `.mp4` 或拒绝。
5. 失败时清理临时文件。
6. provider adapter 返回的初始下载 URL 和每次 redirect 后 URL 都必须做严格 host allowlist 校验；拒绝 IP literal、localhost、private、reserved、link-local 地址；不能用字符串包含判断域名。初始 URL 或 redirect URL 不允许时均返回 `ONLINE_MATERIAL_REDIRECT_NOT_ALLOWED`。
7. 初始 URL 与每次 redirect URL 都必须解析 hostname，并拒绝任一 DNS 解析结果为 private、loopback、link-local、multicast、reserved 或 unspecified 的地址；不能只检查 URL 字符串或单个解析结果。
8. 下载连接应使用已校验的解析结果，或在连接前后保持 hostname 解析一致性校验；若连接目标与校验结果不一致、解析结果变化到不允许地址，或疑似 DNS rebinding/解析绕过，必须中止并返回 `ONLINE_MATERIAL_REDIRECT_NOT_ALLOWED`。

### 创建线上混剪任务

`POST /api/online-mix/tasks`

请求：

```json
{
  "title": "睡前精油短视频",
  "script": { "...": "结构化脚本" },
  "asset_strategy": "auto",
  "provider": "auto",
  "shot_assets": [
    {
      "shot_index": 1,
      "candidate_token": "signed-candidate-token"
    }
  ],
  "shot_materials": [
    {
      "shot_index": 2,
      "material_id": "local-material-id"
    }
  ],
  "options": {
    "aspect_ratio": "9:16",
    "resolution": "1080p"
  }
}
```

后端流程：

1. 校验脚本和镜头数量。
2. 为每个镜头构建搜索词，优先使用 `keywords`，其次使用 `visual_description`。
3. 逐镜头解析素材选择，优先级为：用户选中的 `candidate_token` > 已有本地素材 `material_id` > `auto` 策略搜索。
4. 对用户选中的候选验证 token，必要时下载素材到本地素材库；对已有本地素材只读取安全公开元数据。
5. 对仍未选定素材的镜头执行自动搜索并选择最匹配画幅和时长的候选。
6. 组装并清洗 `manifest_payload`，包含脚本、素材来源、授权备注、镜头映射和下一阶段 `render_plan`。
7. 调用现有 `create_task(..., manifest_payload=...)` 创建任务快照，由 `create_task` 负责输出目录、manifest 文件落盘和 DB 写入。

返回和 manifest 中每个镜头素材映射必须记录：

1. `shot_index`
2. `material_id`
3. `selection_mode`：`user_candidate`、`user_material` 或 `auto`
4. `selection_reason`

如果部分镜头未匹配到素材，第一版可创建失败任务或返回结构化错误；默认选择返回错误，避免生成缺镜头的误导性任务。

请求校验必须在解析或下载素材前完成：

1. `shot_assets` 和 `shot_materials` 内部的 `shot_index` 不能重复。
2. 同一个 `shot_index` 不能同时出现在 `shot_assets` 和 `shot_materials`。
3. `shot_index` 必须匹配脚本中的 `shots[].index`，不是数组下标或数组位置；它必须能对应到一个实际镜头，避免 0-based 或数组顺序歧义。
4. 任一规则违反时返回 `ONLINE_MIX_SHOT_SELECTION_INVALID` 结构化错误，不进入 token 验签、下载或任务创建流程。

请求校验通过后，`POST /api/online-mix/tasks` 的 token 与 secret 错误优先级必须固定：

1. 只要请求包含任一 `shot_assets[].candidate_token`，该接口就属于需要验证候选 token 的路径。
2. 只要该接口需要验证任何 `candidate_token`，且素材 provider 已配置但 `AUTOVIDEO_CANDIDATE_TOKEN_SECRET` 缺失，必须返回 `ONLINE_MATERIAL_TOKEN_SECRET_NOT_CONFIGURED`，不能把用户传入的 token 当作 invalid token，也不能返回 500。
3. 只有 secret 已配置后，才解析和校验 `shot_assets[].candidate_token`；格式错误、payload 不完整、HMAC 失败统一返回 `ONLINE_MATERIAL_CANDIDATE_TOKEN_INVALID`，`expires_at` 已过期返回 `ONLINE_MATERIAL_CANDIDATE_TOKEN_EXPIRED`。
4. `asset_strategy=auto` 或仍未选定素材的镜头需要自动搜索并签发候选时，也适用相同 secret 缺失错误优先级。

### 任务 manifest 扩展契约

扩展现有任务创建入口为 `create_task(..., manifest_payload: dict | None = None)`。`create_task` 继续保持输出目录、manifest 文件落盘和 DB 写入职责；`online_mix` 服务只负责组装并传入安全的 `manifest_payload`。

`online_mix` 传入的 `manifest_payload` 包含：

1. `script`
2. `shot_materials`
3. `source_attribution`
4. `render_plan`
5. `provider_status_snapshot`

`manifest_payload` 必须先经过清洗，不能包含 `storage_path`、绝对本地路径、API key、token、provider download URL 或任何旧项目内网地址。测试必须验证 manifest 不泄漏本地路径、candidate token、真实下载 URL、provider key、旧项目部署路径和旧项目内网地址，例如 `<OLD_PROJECT_DEPLOY_PATH>` 与 `<OLD_PROJECT_INTERNAL_ADDRESS>`。

## 素材选择规则

第一版采用确定性规则，不引入复杂向量检索：

1. 用户逐镜头选择优先：显式传入的 `candidate_token` 或 `material_id` 必须优先于自动匹配。
2. 画幅匹配优先：`9:16` 优先竖屏，`16:9` 优先横屏，`1:1` 优先接近正方形。
3. 时长满足优先：候选时长大于等于镜头时长。
4. 分辨率高者优先。
5. 同一任务内避免重复 `provider + asset_id`。
6. 没有完全匹配时允许降级到同 provider 的下一候选，但必须记录 `selection_reason`。

## 前端设计

本阶段前端不是营销页，而是工作台流程。新增“线上混剪”区域，嵌入现有混剪工作台。

桌面端结构：

1. 左侧保持现有导航。
2. 主区上半部分是主题表单：主题、时长、画幅、语气、受众、卖点。
3. 中部展示生成的分镜脚本表格，每行包含镜头、时长、旁白、画面描述、关键词。
4. 下部展示素材匹配状态：未搜索、加载中、候选、已选择、已下载、部分失败、失败。
5. 右侧状态面板显示运行检查、素材源配置状态和任务输出入口。
6. 每个镜头允许自动匹配，也允许用户逐镜头选择候选、替换候选或改用已有本地素材。
7. 搜索、下载和创建任务必须有 loading、retry 和 partial failure 状态；部分失败时保留已匹配镜头，让用户逐镜头重试或替换。

移动端结构：

1. 表单改为单列。
2. 分镜脚本使用可折叠镜头列表。
3. 素材候选以纵向卡片显示，每张卡片提供预览、选择、替换和重试操作。
4. 主要操作按钮保持 44px 以上触控高度。
5. 镜头列表中当前选择、失败原因和重试入口直接显示在对应镜头下方，避免依赖 hover 或桌面端右侧面板。

前端不显示实现说明、设计意图或“为什么这样布局”的开发文案，只显示业务字段、状态、操作和错误。

## 错误处理

所有新增接口返回结构化错误：

```json
{
  "detail": {
    "code": "ONLINE_MATERIAL_PROVIDER_NOT_CONFIGURED",
    "message": "未配置线上素材源 API key",
    "provider": "pexels"
  }
}
```

主要错误码：

1. `ONLINE_MATERIAL_PROVIDER_NOT_CONFIGURED`
2. `ONLINE_MATERIAL_SEARCH_FAILED`
3. `ONLINE_MATERIAL_DOWNLOAD_FAILED`
4. `ONLINE_MATERIAL_TOO_LARGE`
5. `ONLINE_MATERIAL_UNSUPPORTED_URL`
6. `ONLINE_MIX_NO_MATERIAL_MATCH`
7. `SCRIPT_TOPIC_REQUIRED`
8. `SCRIPT_SHOT_LIMIT_EXCEEDED`
9. `SCRIPT_PAYLOAD_TOO_LARGE`
10. `ONLINE_MATERIAL_CANDIDATE_TOKEN_INVALID`
11. `ONLINE_MATERIAL_CANDIDATE_TOKEN_EXPIRED`
12. `ONLINE_MATERIAL_REDIRECT_NOT_ALLOWED`
13. `ONLINE_MATERIAL_TOKEN_SECRET_NOT_CONFIGURED`
14. `ONLINE_MIX_SHOT_SELECTION_INVALID`
15. `LLM_NOT_CONFIGURED`

## 测试策略

后端测试：

1. LLM 未配置时脚本生成 fallback 可用。
2. 传入 fake LLM client 时能解析结构化分镜。
3. 脚本 payload 超限返回结构化错误。
4. Pexels/Pixabay provider 未配置时返回配置错误。
5. fake provider 搜索结果可按画幅、时长、分辨率排序。
6. 搜索结果包含 `candidate_token`、`preview_url` 和 `file_variant`，不暴露 provider 真实下载 URL。
7. 候选响应和素材公开元数据中的 `source_url` 只能是公开来源页或归因页 URL；`preview_url` 只用于前端预览且经过 provider allowlist；真实 `download_url` 不进入候选响应、公开 API、manifest、日志或 DB 公开字段。
8. `GET /api/online-materials/status` 返回 `candidate_token_secret_configured` 布尔值，不泄漏 secret 值。
9. candidate token HMAC 校验失败返回 `ONLINE_MATERIAL_CANDIDATE_TOKEN_INVALID`。
10. candidate token 签发时使用 `AUTOVIDEO_CANDIDATE_TOKEN_TTL_SECONDS` 计算 `expires_at`，默认 TTL 为 1800 秒；测试使用短 TTL 或可控时钟覆盖未过期和过期两条路径，过期返回 `ONLINE_MATERIAL_CANDIDATE_TOKEN_EXPIRED`。
11. 下载接口只接受 `candidate_token`，不信任客户端传入的 `download_url`、`preview_url` 或 `source_url`。
12. `POST /api/online-materials/download` 错误优先级覆盖：provider 未配置时返回 `ONLINE_MATERIAL_PROVIDER_NOT_CONFIGURED`；provider 已配置但 secret 缺失时优先返回 `ONLINE_MATERIAL_TOKEN_SECRET_NOT_CONFIGURED`；只有 secret 已配置后，缺少 `candidate_token`、token 格式错误、payload 不完整、HMAC 校验失败才返回 `ONLINE_MATERIAL_CANDIDATE_TOKEN_INVALID`；token 过期返回 `ONLINE_MATERIAL_CANDIDATE_TOKEN_EXPIRED`。
13. provider 初始下载 URL 为非 allowlist、IP literal、localhost、private、reserved、link-local、multicast 或 unspecified 地址时返回 `ONLINE_MATERIAL_REDIRECT_NOT_ALLOWED`。
14. provider 下载 redirect 链路跳转到非 allowlist、IP literal、localhost、private、reserved、link-local、multicast 或 unspecified 地址时返回 `ONLINE_MATERIAL_REDIRECT_NOT_ALLOWED`。
15. 初始 URL 和每次 redirect URL 都解析 hostname；任一 DNS 解析结果为 private、loopback、link-local、multicast、reserved 或 unspecified 时返回 `ONLINE_MATERIAL_REDIRECT_NOT_ALLOWED`。
16. 下载连接使用已校验解析结果或执行连接前后一致性校验；模拟 DNS rebinding、解析结果漂移或连接目标与已校验 hostname/IP 不一致时返回 `ONLINE_MATERIAL_REDIRECT_NOT_ALLOWED`。
17. 下载使用流式写入，并限制大小。
18. 下载成功后素材元数据包含 provider、asset_id、source_url、license_note。
19. provider 已配置但 `AUTOVIDEO_CANDIDATE_TOKEN_SECRET` 缺失时，`POST /api/online-materials/search`、`POST /api/online-materials/download` 和 `POST /api/online-mix/tasks` 的自动候选签发路径返回 `ONLINE_MATERIAL_TOKEN_SECRET_NOT_CONFIGURED`，不返回无 token 候选，也不返回 500。
20. `POST /api/online-mix/tasks` 覆盖 `auto`、用户 `shot_assets` 和用户 `shot_materials` 三类选择路径。
21. provider 已配置但 `AUTOVIDEO_CANDIDATE_TOKEN_SECRET` 缺失时，`POST /api/online-mix/tasks` 只要收到用户传入的 `shot_assets[].candidate_token` 并需要验证候选 token，就必须返回 `ONLINE_MATERIAL_TOKEN_SECRET_NOT_CONFIGURED`，不能返回 `ONLINE_MATERIAL_CANDIDATE_TOKEN_INVALID` 或 500。
22. `POST /api/online-mix/tasks` 对 `shot_assets`、`shot_materials` 做请求校验：同数组重复 `shot_index`、跨数组同一 `shot_index` 同时出现、`shot_index` 不能匹配脚本 `shots[].index` 时，均返回 `ONLINE_MIX_SHOT_SELECTION_INVALID`。
23. `POST /api/online-mix/tasks` 能生成任务 manifest，且不泄漏本地路径、candidate token、provider download URL、API key、旧项目部署路径 `<OLD_PROJECT_DEPLOY_PATH>` 或旧项目内网地址 `<OLD_PROJECT_INTERNAL_ADDRESS>`。
24. 无素材匹配时返回 `ONLINE_MIX_NO_MATERIAL_MATCH`。

前端测试：

1. 渲染线上混剪主题表单。
2. 能展示生成的分镜脚本。
3. 能展示素材源未配置状态。
4. 能逐镜头自动匹配、选择候选、替换候选和改用已有本地素材。
5. 搜索、下载、创建任务覆盖 loading、retry 和 partial failure 状态。
6. 不出现旧项目登录、个人网盘、NAS 或 token 文案。
7. 移动端关键布局样式保持可滚动和不挤压。

## 实施阶段

### 阶段 1：脚本生成 API

新增脚本模型、脚本生成服务、LLM 配置和 fallback。验收点：不配置 LLM 也能生成结构化脚本。

### 阶段 2：线上素材 provider

新增 Pexels/Pixabay provider 接口、`GET /api/online-materials/status`、搜索、候选排序和 candidate token 签发。验收点：fake provider 测试完整，真实 provider 只依赖环境变量，候选响应不暴露真实下载 URL。

### 阶段 3：下载与素材元数据

扩展 SQLite 素材表，下载线上素材并插入本地素材库。SQLite 迁移使用 `PRAGMA table_info` 判断列是否存在，再通过 `ALTER TABLE ADD COLUMN` 增加来源列；新增来源列全部 nullable，旧数据的 `source_type` 业务逻辑默认视为 `upload`。验收点：下载限制、token 校验、重定向 allowlist、来源记录和公开响应全部可测。

### 阶段 4：线上混剪任务

串联脚本、素材搜索、下载和现有任务创建，扩展 `create_task(manifest_payload=...)` 并保持输出目录和 DB 写入职责在 `create_task` 内；`online_mix` 不直接落盘 manifest，只传入已清洗的 `manifest_payload`。验收点：能通过 API 创建包含脚本、镜头素材映射、线上素材来源和 render plan 的 manifest。

### 阶段 5：前端工作流

在混剪工作台接入主题表单、脚本预览、素材匹配状态和任务输出入口。验收点：桌面和移动端都能完成第一版线上混剪任务创建。

## 风险与约束

1. Pexels/Pixabay 授权条款和 API 限额可能调整，代码必须保留 provider/source/license metadata，便于后续追踪。
2. 免费素材搜索质量依赖英文关键词，中文主题需要转写或用 fallback 英文查询。第一版可以由 LLM 生成英文关键词；未配置 LLM 时用简单映射和关键词原文兜底。
3. 真实下载可能较慢，第一版使用同步请求即可，但要有超时、大小限制和清理逻辑。
4. 不配置任何线上素材 key 时，系统仍可用本地上传素材和脚本 fallback，不应影响已有功能。
5. 后续真实渲染接入前，manifest 必须清楚标记当前仍是占位输出。
6. candidate token HMAC secret 必须通过 `AUTOVIDEO_CANDIDATE_TOKEN_SECRET` 配置；缺失时不能签发或验证可下载候选。只要素材 provider 已配置且请求路径需要返回候选 token，或需要验证用户传入的 `shot_assets[].candidate_token`，就必须返回 `ONLINE_MATERIAL_TOKEN_SECRET_NOT_CONFIGURED`，不能返回无 token 候选、invalid token 或 500。后续需要支持 secret 轮换，例如接受当前 secret 和上一版 secret 验签，但只用当前 secret 签发新 token。
7. candidate token TTL 必须通过 `AUTOVIDEO_CANDIDATE_TOKEN_TTL_SECONDS` 配置，默认 1800 秒；过长会增加候选泄漏后的可用窗口，过短会影响用户从搜索到创建任务的正常操作。

## 验收标准

1. README 和 `.env.example` 说明新增 LLM 与线上素材配置。
2. 后端测试覆盖脚本生成、素材搜索、下载和线上混剪任务。
3. 前端测试覆盖线上混剪入口和关键状态。
4. `PYENV_VERSION=3.12.13 python -m pytest -q` 通过。
5. `npm test -- --run` 和 `npm run build` 通过。
6. PR 创建后按仓库规则完成本地子代理 review 和 GitHub Codex review 监控。
