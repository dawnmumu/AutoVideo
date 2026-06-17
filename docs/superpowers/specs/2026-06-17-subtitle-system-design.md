# AutoVideo 字幕系统设计

## 背景

本轮目标是对比 `/Users/sha/junxincode` 原项目的视频混剪字幕能力，在 AutoVideo 中接入功能一致的字幕系统。原项目当前可用闭环包括字幕模板组、内置预设、字幕块编辑、DSL v2 校验、实时/精准/时间轴预览、字幕事件生成、ASS 文件输出和 FFmpeg 烧录。Scene Graph 等高级字段在原项目当前也以保留配置和降级 warning 为主，正式导出仍走 ASS，因此 AutoVideo 本轮按同一能力边界实现。

AutoVideo 当前已有脚本 `subtitle` 字段、`subtitles.srt` sidecar 和基础 FFmpeg 混剪，但没有字幕模板管理、ASS 渲染、模板快照或带字幕 MP4 输出。本设计补齐这条链路。

## 范围

本轮实现：

- 新增独立字幕模板 API，提供模板组、预设、校验、精准预览和时间轴预览能力。
- 新增字幕模板工作台页面入口，桌面端使用模板/预览/编辑三栏，移动端使用纵向分区。
- 在线混剪表单新增字幕设置：启用字幕、模板组选择、字体覆盖。
- 在线混剪任务创建时保存 `subtitle_template_snapshot`，历史任务不受模板后续修改影响。
- 字幕启用时始终生成 `subtitles.ass`；FFmpeg 可用时再使用 `ass` 滤镜烧录到最终 `output.mp4`。
- 字幕启用且素材来源为 local/hybrid 时，按原项目规则检测疑似自带字幕素材，并在合成基础视频时遮挡源字幕区域，避免与新 ASS 字幕叠加。
- 保留 `timeline.json`、`subtitles.srt`、`subtitles.ass`、`output.base.mp4` 和最终 `output.mp4`，便于排查。
- 更新 README，说明字幕模板、任务选项和输出产物。当前 AutoVideo 没有独立帮助中心或帮助入口，本轮帮助面以 README 为准，不新增单独帮助系统。

不在本轮实现：

- 权限管理、用户隔离、多人模板共享。
- Scene Graph 高级运行时执行、复杂 overlay 合成、非 ASS 渲染器。
- TTS 音频驱动的逐字卡拉 OK 对齐；本轮字幕时间轴基于脚本镜头时长和标点拆分。
- BGM、音色中心、素材索引等其他一级功能。

## 原项目能力映射

原项目能力映射到 AutoVideo：

- `subtitle_template_store.py` → `autovideo/services/subtitles/template_store.py`，负责 JSON 文件存储、预设覆盖、模板组 CRUD 和自动选择。
- `subtitle_template_presets.py` → `autovideo/services/subtitles/template_presets.py`，提供内置预设。
- `subtitle_template_blocks.py`、`subtitle_template_dsl_v2.py` → `autovideo/services/subtitles/template_blocks.py` 和 `dsl_v2.py`，负责字段归一、校验和降级 warning。
- `subtitle_timeline.py` → `autovideo/services/subtitles/timeline.py`，从脚本镜头生成字幕事件。
- `subtitle_templates.py` → `autovideo/services/subtitles/template_assignment.py`，负责 `bottom`、`highlight`、`punch` 语义模板分配、模板变体选择，以及 LLM 不可用时的确定性/随机降级。
- `subtitle_keyword_spans.py` → `autovideo/services/subtitles/keyword_spans.py`，对抽样字幕事件提取 0-2 个关键词并注入局部 span；LLM 失败时继续渲染但不注入关键词 span。
- `subtitle_event_enrichment.py` → `autovideo/services/subtitles/event_enrichment.py`，把模板块、变体块、track、span 和 animation 合并到字幕事件。
- `video_pipeline.py` 的 `source_subtitle_masks` 和 `video_composer.py` 的 `_mask_source_subtitle_area` → AutoVideo 渲染 pipeline 的源字幕遮挡逻辑，负责在字幕启用时遮挡本地/混合素材里疑似已有字幕的底部区域。
- `ass_renderer.py` → `autovideo/services/subtitles/ass_renderer.py`，从事件和模板输出 ASS。
- `ffmpeg_subtitle_burner.py` → `autovideo/services/subtitles/ffmpeg_burner.py`，使用 FFmpeg `ass` 滤镜烧录字幕。
- `subtitle_preview_renderer.py` → `autovideo/services/subtitles/preview_renderer.py`，提供 PNG 精准预览和短 MP4 时间轴预览。
- 原项目 `web/video/subtitle-template-*` → React 组件 `SubtitleTemplateWorkbench` 和 API client。

## 后端设计

### API

新增 `autovideo/api/routes/subtitle_templates.py`，路由前缀 `/api/subtitle-template-sets`。

- `GET /api/subtitle-template-sets`
  - 返回 `{ "items": [...], "presets": [...] }`。
- `POST /api/subtitle-template-sets`
  - 请求：`{ "name": "...", "preset_id": "...?" , "source_id": "...?" }`。
  - 约束：`preset_id` 和 `source_id` 必须二选一。
- `PUT /api/subtitle-template-sets/{template_set_id}`
  - 请求允许 `name`、`is_favorite`、`favorite`、`schema_version`、`renderer_mode`、`tracks`、`templates`、`blocks` 和 DSL v2 扩展字段。
- `DELETE /api/subtitle-template-sets/{template_set_id}`
  - 删除自定义模板组；内置预设不可作为自定义模板删除。
- `PUT /api/subtitle-template-sets/presets/{preset_id}`
  - 覆盖内置预设的可编辑字段。
- `DELETE /api/subtitle-template-sets/presets/{preset_id}`
  - 恢复内置预设。
- `POST /api/subtitle-template-sets/validate`
  - 请求为模板组 patch，返回 `{ "ok": true|false, "normalized": ..., "warnings": [...] }`。
- `POST /api/subtitle-template-sets/preview`
  - 请求：`template_set`、`template_type`、`aspect_ratio`、`sample_text`。
  - 返回 PNG base64、mime type、resolution、warnings。
- `POST /api/subtitle-template-sets/preview-timeline`
  - 请求继承 preview，并增加 `duration_ms`。
  - 返回短 MP4 base64、mime type、duration、resolution、warnings。

所有写接口对模板字段做服务端校验。错误使用现有结构化错误风格，用户可恢复的字段错误返回 400，预览渲染失败返回 400 并包含可读 message 和 details 尾部。精准预览和时间轴预览需要 FFmpeg/libass 渲染能力；环境不可用时只返回预览不可用错误，不影响模板保存、任务创建或纯 Python `subtitles.ass` 生成。

### 存储

模板持久化使用现有数据目录：

- 文件：`<AUTOVIDEO_DATA_DIR>/subtitle_templates/subtitle_template_sets.json`
- 结构：`{ "items": [...], "preset_overrides": { ... } }`
- 写入方式：临时文件 + 原子替换，避免半写入。

内置预设不写入 items；只有用户创建的模板组和被修改的预设覆盖项写入 JSON。模板归一时保留 `created_at`、`updated_at`、`is_favorite`、`favorite` 等元数据，避免保存后丢失默认模板选择状态。

默认模板选择规则与原项目保持一致：

- 优先从自定义模板组里选择 `is_favorite=true` 或 `favorite=true` 的模板。
- 多个收藏模板并存时，使用与原项目一致的排序键 `(updated_at, created_at, id)` 选择最大项。
- 没有收藏模板时，从自定义模板组中使用同一排序键选择最大项。
- 没有自定义模板组时，使用第一个内置预设。

### 字幕渲染

在线混剪渲染改为两阶段：

1. 按现有素材拼接逻辑生成无字幕基础视频 `output.base.mp4`。当 `subtitle_enabled=true` 且素材来源为 `local` 或 `hybrid` 时，先为每个镜头生成 `source_subtitle_masks`：
   - 检测对象为最终计划使用的本地素材路径；没有素材计划时退回镜头的单个素材路径。
   - 路径父目录名或文件名包含 `口播`、`字幕`、`带字`、`caption`、`captions`、`subtitle`、`subtitled`、`hard-sub`、`hardsub` 任一标记时，认为该镜头素材疑似带源字幕。
   - 对命中的镜头，在基础视频合成阶段遮挡底部 `22%` 高度区域，再进入后续 ASS 烧录。
   - `subtitle_enabled=false` 或素材来源不是 `local`/`hybrid` 时，所有 mask 均为 false。
2. 当字幕启用时，不依赖 FFmpeg 先完成纯 Python 字幕产物生成：
   - 从 timeline/script 生成基础字幕事件。
   - 运行语义分配，把事件映射到 `bottom`、`highlight`、`punch`，并写入模板变体 key；LLM 不可用时使用确定性规则和随机降级，不能阻塞任务。
   - 运行关键词 span 注入，对抽样事件提取 0-2 个连续关键词，写入 `keyword_spans` 和 `spans`；LLM 失败时继续渲染但不注入关键词 span。
   - 运行事件 enrich，根据输出分辨率和画幅把模板块、变体块、`track_id`、块级 span 与 animation 合并到事件。
   - 生成 `subtitles.ass`，同时继续保留 `subtitles.srt` 和 `timeline.json`。
3. 当字幕启用且 FFmpeg 可用时，使用 FFmpeg `ass=filename=...` 滤镜把 `subtitles.ass` 烧录到最终 `output.mp4`。

依赖边界：

- `timeline.json`、`subtitles.srt`、`subtitles.ass` 不依赖 FFmpeg。
- `output.base.mp4` 依赖现有 FFmpeg 基础视频拼接能力。
- 带字幕 `output.mp4` 依赖 FFmpeg 基础视频拼接和 ASS 烧录能力。

渲染产物矩阵：

| 字幕 | FFmpeg | 基础视频 | 产物 | `render_plan` |
| --- | --- | --- | --- | --- |
| 关闭 | 可用 | 成功 | `output.mp4` | `video_rendered` |
| 关闭 | 不可用 | 跳过 | manifest、`timeline.json`、`subtitles.srt` | `manifest_only`，记录 `base_video_skipped` |
| 开启 | 可用 | 成功 | `output.base.mp4`、`subtitles.ass`、最终 `output.mp4` | `subtitle_burned` |
| 开启 | 可用 | 失败 | manifest、`timeline.json`、`subtitles.srt`、`subtitles.ass` | `base_video_failed`，记录 FFmpeg stderr 清理摘要 |
| 开启 | 不可用 | 跳过 | manifest、`timeline.json`、`subtitles.srt`、`subtitles.ass` | `manifest_only`，记录 `base_video_skipped` 和 `subtitle_burn_skipped` |

字幕关闭时不生成 ASS，不执行烧录。字幕开启时即使基础视频不可用，也应尽量生成 `subtitles.ass` 作为可排查产物。

任务 manifest 和 render plan 记录 `source_subtitle_masked`、`source_subtitle_mask_count` 和每个镜头的 mask 布尔列表，方便排查源字幕遮挡是否生效。

### 任务选项

`POST /api/online-mix/tasks` 的 `options` 新增字段：

- `subtitle_enabled`: `boolean`，默认 `true`。
- `subtitle_template_set_id`: `string | null`。
- `subtitle_template_snapshot`: `object | null`，允许 API 客户端提交已校验模板快照；服务端仍会校验。
- `subtitle_font_family`: `string | null`，为空表示跟随模板。

服务端规则：

- `subtitle_enabled=false` 时，不读取模板，不生成 ASS，不烧录字幕。
- `subtitle_enabled=true` 且有 `subtitle_template_snapshot` 时，校验并使用该快照；snapshot 必须包含有效 `id` 和 `name`。
- 同时传入 `subtitle_template_snapshot` 和 `subtitle_template_set_id` 时，snapshot 的 `id` 必须与 `subtitle_template_set_id` 一致，否则返回 400。
- snapshot 优先级高于模板库读取；snapshot 路径不再查询 `template_store`，只做深拷贝、校验归一、补齐模板变体、字体覆盖和 manifest 落盘。
- `subtitle_enabled=true` 且有 `subtitle_template_set_id` 时，从模板库读取并深拷贝。
- `subtitle_enabled=true` 且没有指定模板时，按“收藏自定义模板、最近自定义模板、第一个内置预设”的顺序自动选择。
- `subtitle_font_family` 非空时，服务端在任务快照落盘和渲染前生成有效快照：覆盖 legacy `templates[*].font_family`、DSL `blocks[*].style.font_family` 和 `template_variants[*].template.font_family`。manifest 里的 `subtitle_template_snapshot` 必须记录覆盖后的有效快照，ASS style 也必须使用覆盖字体。
- 任务 manifest 记录 `subtitle_template_set_id`、`subtitle_template_set_name`、`subtitle_template_snapshot`、`subtitle_enabled`、`subtitle_mode` 和 `subtitle_font_family`。

## 前端设计

### 导航

现有“字幕模板”一级入口从禁用状态改为可点击。当前应用没有路由库，优先沿用现有单页结构：

- 使用 `activeSection` 在 `混剪工作台` 与 `字幕模板` 间切换。
- 桌面侧栏和移动 tabs 都保持一级入口可见。
- 其他未实现入口仍保持禁用。

### 字幕模板工作台

新增 `frontend/src/components/SubtitleTemplateWorkbench.tsx`。

桌面布局：

- 左侧：自定义模板组和内置预设列表，支持新建、复制、恢复预设。
- 模板列表提供“设为默认/收藏”操作，写入 `is_favorite`，并在列表中明确展示当前默认模板。
- 中间：画幅切换、示例文本、实时预览、精准预览、时间轴预览、校验 warning。
- 右侧：当前字幕块编辑器，支持 `bottom`、`highlight`、`punch` 三类角色，字段包含字体、颜色、强调色、描边、阴影、位置、字号比例、最大宽度、旋转、倾斜和局部 span。

移动布局：

- 保持一级 tabs 可横向滚动；在 375px 宽度下，已启用的“混剪工作台”和“字幕模板”必须首屏可见，未实现禁用入口排在后面横滚。
- 字幕模板工作台改为纵向分区：模板选择、预览、编辑。
- 预览区域固定比例，不因控件变化造成布局跳动。
- 所有输入和按钮保持至少 44px 高度，错误和 warning 靠近相关操作展示。

### 混剪页字幕设置

在线混剪表单新增一组字幕设置：

- 启用字幕开关，默认开启。
- 模板组选择，数据来自 `/api/subtitle-template-sets`。
- 字体覆盖选择，默认“跟随字幕模板”。
- 当前模板摘要与“去字幕模板页编辑”入口。

创建任务时把字幕设置写入 `options`。如果用户在字幕模板页编辑了草稿但未保存，混剪页不直接读取未保存草稿；只有保存后的模板组参与任务，避免任务快照混入未保存草稿。

### UI 验收

- 键盘可完整操作模板列表、预览按钮、字段编辑、保存、恢复和混剪页字幕设置。
- 当前一级入口使用 `aria-current` 或等价语义；模板列表、画幅切换和角色切换使用 `aria-selected` 或等价语义。
- 所有表单控件有可见 label；helper、warning、error 靠近对应字段展示。
- 异步保存、预览、任务创建期间按钮有 loading 和 disabled 状态，且状态变化不依赖 hover。
- 可交互元素保留可见 focus ring，正文和控件文本对比度满足 4.5:1。
- 预览和状态过渡遵守 `prefers-reduced-motion`，不使用影响可读性的装饰动画。

## 失败处理

- 模板不存在：任务创建返回 400，提示字幕模板组不存在。
- 模板字段无效：保存或任务创建返回 400，返回具体字段错误。
- 精准预览失败：预览区域显示错误、details 尾部和 warnings，不影响编辑草稿。
- FFmpeg 基础视频失败：沿用 `FFMPEG_RENDER_FAILED`。
- ASS 生成或烧录失败：返回 `FFMPEG_RENDER_FAILED`，stderr 做现有敏感信息清理后写入结构化错误。
- 字幕启用但没有自定义模板：自动使用内置预设，不阻塞任务。

## 测试策略

后端使用 TDD 分层覆盖：

- 模板存储：预设列表、自定义模板 CRUD、预设覆盖和恢复、原子写入、非法字段拒绝。
- DSL/blocks：v2 字段归一、未知高级字段 warning、span selector/style 校验。
- 时间轴：按标点拆分、短镜头合并、数字小数/比例标点保留。
- ASS 渲染：样式字段、事件时间、文本转义、局部 span、输出文件存在。
- 字幕链路：timeline 到语义分配、关键词 span、事件 enrich、ASS 的顺序和降级行为；LLM 失败时仍能生成 ASS。
- 源字幕遮挡：字幕开启且 local/hybrid 素材路径命中源字幕 marker 时触发底部遮挡；字幕关闭、online 素材或未命中 marker 时不遮挡；manifest 记录遮挡数量和布尔列表。
- FFmpeg 命令：基础视频输出、ASS 烧录命令、路径转义、字幕关闭时不调用烧录。
- 在线混剪：`options` 字幕字段解析、模板快照写入 manifest、字体覆盖写入快照和 ASS style、收藏模板默认选择、FFmpeg 不可用降级、输出 media type。
- API：列表、创建、更新、删除、校验、预览、错误状态。

前端使用 Vitest 覆盖：

- 字幕模板入口可点击并切换页面。
- 模板列表和预设渲染。
- 编辑字段更新实时预览。
- 校验 warning 和预览错误展示。
- 混剪任务创建会提交字幕设置。
- 移动端相关 class 和可访问标签存在。

移动端验收必须额外覆盖 375、768、1024 三个宽度：

- `document.documentElement.scrollWidth <= window.innerWidth`，不出现页面级横向溢出。
- 混剪工作台和字幕模板一级入口在移动 tabs 中始终可见，当前激活项可识别。
- 主要按钮、开关、选择器和可点击列表项高度不小于 44px。
- 预览区域在数据加载、错误、warning 和编辑切换时保持固定比例，不发生明显跳动。
- 字段错误和 warning 出现在相关控件附近，不只集中在页面顶部。

验证命令：

- `pytest`
- `npm test -- --run`（在 `frontend/`）
- `npm run build`（在 `frontend/`）
- 默认用真实 FFmpeg 跑最小混剪 smoke，覆盖基础视频、ASS 烧录、路径转义和预览依赖；如果当前环境没有 FFmpeg，必须记录跳过原因，并至少验证 manifest、timeline、SRT 和 ASS 产物。

## 交付流程

实现阶段按 TDD 执行，并使用子代理按计划逐项实现和复审。完成后执行本地 review 循环、推送远端分支、创建 PR，PR 进入 ready 状态后再做 PR 后 review。若该 PR 是 bug 修复则通过 review 后可按项目规则合并；本轮属于功能接入，默认等待确认合并和部署。
