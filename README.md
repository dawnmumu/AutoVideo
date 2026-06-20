# AutoVideo

AutoVideo 是一个个人自托管的视频混剪工作台。项目会从产品骨架开始，逐步接入字幕模板、BGM 管理、音色中心、功能提取处理和混剪任务流。

## 当前阶段

阶段 2：脚本生成 + 线上免费素材 FFmpeg 混剪

- FastAPI 后端服务
- React + Vite 中文工作台首页
- 字幕模板、BGM 管理、音色中心、功能提取处理等一级入口
- 环境变量配置
- 数据目录初始化
- FFmpeg 与可选 Fish Speech 运行检查
- 素材上传 API
- 视频任务创建、查询和输出下载 API
- 任务与输出页面，可查看历史任务、失败摘要，按输出类型下载视频或清单，并删除不再需要的任务记录
- 脚本自动生成 API
- Pexels/Pixabay 线上免费素材搜索、候选签名和安全下载 API
- 基于脚本、线上候选和本地素材的线上混剪任务 API，FFmpeg 可用时直接生成 MP4
- 字幕模板管理 API 和字幕模板工作台；工作台会在实时、精准和时间线预览中覆盖底部字幕、强调字幕和冲击字幕
- 字幕块支持按角色维护文本、横纵位置百分比、对齐、字号、最大宽度、字体、颜色、背景配置、强调色、括号装饰、描边、阴影、旋转和 X/Y 倾斜；背景配置会随模板保存，但实时预览不会为字幕生成额外底板
- 字幕块支持按角色维护局部样式，可为关键词或文本范围配置颜色、字体、字号、描边和动画配置；局部字体会写入 ASS 内联样式，局部动画作为模板配置保留并随快照进入后续字幕链路
- 线上混剪任务支持 `subtitle_enabled`、`subtitle_template_set_id`、`subtitle_template_snapshot` 和 `subtitle_font_family`
- 未指定 `subtitle_template_set_id` 时，线上混剪会自动选择基础模板，并汇入全部可用模板变体随机用于字幕渲染
- 字幕启用时任务目录保留 `subtitles.ass`；FFmpeg 可用时烧录为最终 `output.mp4`
- local/hybrid 素材疑似自带字幕时会遮挡底部源字幕区域，避免和生成字幕叠加
- 音色中心已接入 Microsoft Edge TTS 免费音色列表和试听生成；不需要 Azure key，试听音频保存到 `AUTOVIDEO_DATA_DIR/voices/previews`
- 本地启动和 Docker 启动

尚未接入登录、权限管理、个人网盘导入、BGM 上传、Fish Speech 音色复刻和功能提取处理。

线上混剪任务会在 FFmpeg 可用时输出 `output.mp4`，并在同一任务目录保留 `manifest.json`、`timeline.json`、`subtitles.srt` 和启用字幕时的 `subtitles.ass`；启用字幕时还会保留 `output.base.mp4` 便于排查烧录前的视频。FFmpeg 不可用时仍会保留 manifest、timeline、SRT 和 ASS 字幕文件，并在 `manifest.render_plan` 中记录 `base_video_skipped` 和 `subtitle_burn_skipped`。

前端 `任务与输出` 页会读取最近 50 条任务，展示任务状态、创建/更新时间、素材数量、画幅、分辨率和后端汇总的输出摘要；只有主输出为 `output.mp4` 且媒体类型为 `video/mp4` 时显示 `下载视频`，manifest-only 任务显示 `下载清单`，字幕烧录失败等部分输出会展示失败原因并标记输出未完成。下载地址来自 `GET /api/tasks/{task_id}/output`。每个任务卡片提供删除按钮，确认后会调用 `DELETE /api/tasks/{task_id}` 移除任务记录并清理该任务的输出目录。

前端 `音色中心` 页会读取 Microsoft Edge TTS 音色，默认展示中文音色，可切换语言、搜索音色、调整语速/音量/音高并生成 MP3 试听。Edge TTS 路径不需要额外 API key；Fish Speech 只在 `AUTOVIDEO_FISH_SPEECH_URL` 配置后显示为可用。

字幕模板工作台包含模板列表、实时预览和字幕块编辑器。实时预览会同时渲染 `bottom`、`highlight` 和 `punch` 三类字幕，使用接近目标项目的深色视频画布，并在模板位置重合时用预览车道避免遮挡；精准预览和时间线预览也会把三类字幕一并提交给后端 FFmpeg/libass 渲染，避免只显示底部字幕导致预览比例失真。“检查模板”会把当前草稿提交给后端校验，页面会显示可用于预览和渲染的通过状态，或列出被忽略、不支持、格式不正确的字段 warning。每个字幕块可独立调整文本、横纵位置百分比、对齐、字号、最大宽度、字体、颜色、背景配置、强调色、括号装饰、描边、阴影、旋转和 X/Y 倾斜，其中横纵位置和对齐会同步到精准预览与 `subtitles.ass` 的 ASS 定位。背景配置只作为模板字段保存，不会在实时预览里生成额外字幕底板。每个字幕块都有独立的局部样式编辑区，支持关键词匹配或起止范围选择，并可调整局部颜色、字体、字号、描边和动画配置。保存后的局部样式写入模板 `blocks[*].spans`，任务渲染时会随模板快照进入 `subtitles.ass`，其中局部字体通过 ASS `\fn` 标签生效，局部动画配置会在 DSL 和事件增强阶段保留。

## 运行要求

- Python 3.12
- Node.js 20.19+ 或 22.12+
- npm
- FFmpeg

## 本地启动

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cd frontend
npm install
npm run build
cd ..
cp .env.example .env
python -m autovideo.main
```

打开 `http://127.0.0.1:8090`。

开发时建议分别启动后端和前端：

```bash
./scripts/dev.sh
```

另开一个终端：

```bash
cd frontend
npm run dev
```

打开 `http://127.0.0.1:5173`，Vite 会把 `/api` 代理到 FastAPI。

## Docker 启动

```bash
docker build -t autovideo .
docker run --rm -p 8090:8090 -v "$PWD/data:/app/data" autovideo
```

国内网络可以显式使用镜像源构建：

```bash
docker build \
  --build-arg NPM_REGISTRY=https://registry.npmmirror.com \
  --build-arg APT_DEBIAN_MIRROR=https://mirrors.tuna.tsinghua.edu.cn/debian \
  --build-arg APT_SECURITY_MIRROR=https://mirrors.tuna.tsinghua.edu.cn/debian-security \
  --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
  --build-arg PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn \
  -t autovideo .
```

如果 Docker Hub 拉取基础镜像超时，先在 Docker daemon 配置 registry mirror，或把 `NODE_IMAGE`、`PYTHON_IMAGE` 指向你自己的镜像代理：

```bash
docker build \
  --build-arg NODE_IMAGE=your-mirror.example.com/library/node:22-bookworm-slim \
  --build-arg PYTHON_IMAGE=your-mirror.example.com/library/python:3.12-slim \
  --build-arg NPM_REGISTRY=https://registry.npmmirror.com \
  --build-arg APT_DEBIAN_MIRROR=https://mirrors.tuna.tsinghua.edu.cn/debian \
  --build-arg APT_SECURITY_MIRROR=https://mirrors.tuna.tsinghua.edu.cn/debian-security \
  --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
  --build-arg PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn \
  -t autovideo .
```

其中 `PIP_TRUSTED_HOST` 是可选参数，仅在 pip 镜像源需要 trusted host 时传入；只传 `PIP_INDEX_URL` 也支持构建。

## API 骨架

当前后端已经提供最小视频任务闭环，并在 FFmpeg 可用时执行线上混剪渲染：

- `POST /api/materials`：上传素材文件，保存到 `AUTOVIDEO_DATA_DIR/materials`。服务端落盘文件名使用素材 ID 和受控后缀，原始文件名保存在 metadata 中；当 `Content-Length` 超过 `AUTOVIDEO_MAX_UPLOAD_BYTES + AUTOVIDEO_MAX_MULTIPART_OVERHEAD_BYTES` 时返回 `413` 和 `REQUEST_TOO_LARGE`，文件流读取过程中仍会按 `AUTOVIDEO_MAX_UPLOAD_BYTES` 二次限制。响应会返回 `source_type`、`source_provider`、`source_asset_id`、`source_url`、`license_note` 和 `query` 等安全来源字段，但不会暴露本地 `storage_path`。
- `GET /api/materials?limit=50&offset=0`：分页查看已上传素材，`limit` 最大为 `200`，返回字段同素材上传响应。
- `POST /api/tasks`：基于素材 ID 创建任务，保存任务快照。请求体 `Content-Length` 受 `AUTOVIDEO_MAX_TASK_REQUEST_BYTES` 限制，`material_ids` 数量受 `AUTOVIDEO_MAX_TASK_MATERIALS` 限制，`options` JSON 编码大小受 `AUTOVIDEO_MAX_TASK_OPTIONS_BYTES` 限制。任务输出 manifest 支持后端服务附加已清洗的脚本、来源归因和渲染计划元数据。
- `GET /api/tasks?limit=50&offset=0`：分页查看任务列表，`limit` 最大为 `200`。任务输出字段会返回安全摘要，例如 `filename`、`media_type`、`kind`、`render_status` 和已清洗的 `failure_reason`，不会暴露本地路径或真实下载 URL。
- `GET /api/tasks/{task_id}`：查看单个任务状态，输出摘要规则同任务列表。
- `GET /api/tasks/{task_id}/output`：下载任务主输出。线上混剪在 FFmpeg 可用时返回 `video/mp4` 的 `output.mp4`；FFmpeg 不可用或普通任务仍返回 JSON manifest。
- `DELETE /api/tasks/{task_id}`：删除任务记录并清理该任务的输出目录；任务不存在时返回 `TASK_NOT_FOUND`。
- `GET /api/subtitle-template-sets`：返回自定义模板组和 20 个内置预设；内置预设与目标项目默认字幕模板保持一致。
- `POST /api/subtitle-template-sets`：从预设或已有模板复制创建自定义模板组。
- `PUT /api/subtitle-template-sets/{id}`：保存模板组字段和 DSL v2 blocks；旧 `is_favorite` 字段仅作为兼容元数据保留，不再参与自动选择。
- `DELETE /api/subtitle-template-sets/{id}`：删除自定义模板组；内置预设不能通过该接口删除。
- `PUT /api/subtitle-template-sets/presets/{id}`：保存内置预设的本地覆盖项，例如名称和样式覆盖；旧 `is_favorite` 字段仅作为兼容元数据保留。
- `DELETE /api/subtitle-template-sets/presets/{id}`：清除内置预设覆盖项并恢复出厂预设。
- `POST /api/subtitle-template-sets/validate`：校验并归一字幕模板。
- `POST /api/subtitle-template-sets/preview`：生成精准预览；可传 `template_types` 一次预览 `bottom`、`highlight`、`punch` 三类字幕，FFmpeg/libass 不可用时返回 `SUBTITLE_PREVIEW_RENDERER_UNAVAILABLE`。
- `POST /api/subtitle-template-sets/preview-timeline`：生成 0.5-5 秒时间线预览短视频，可传 `template_types` 一次预览三类字幕，返回 base64 MP4。
- `GET /api/voices/status`：返回 Edge TTS 与 Fish Speech 的可用状态；Edge TTS 不需要 API key，Fish Speech 取决于 `AUTOVIDEO_FISH_SPEECH_URL`。
- `GET /api/voices?locale=zh-CN&q=Xiaoxiao`：读取 Microsoft Edge TTS 音色列表，可按 `locale` 和搜索词过滤；响应只包含 `id`、`name`、`provider`、`locale`、`gender`、`content_categories` 和 `personalities` 等公开字段。
- `POST /api/voices/preview`：使用 Edge TTS 生成 MP3 试听，字段包含 `text`、`voice_id`、`rate`、`volume` 和 `pitch`；响应返回 `audio_url`、`filename`、`media_type` 和 `created_at`，不会暴露本地路径。请求体受 `AUTOVIDEO_MAX_VOICE_PREVIEW_REQUEST_BYTES` 限制，文本长度受 `AUTOVIDEO_MAX_VOICE_PREVIEW_TEXT_CHARS` 限制。
- `GET /api/voices/previews/{filename}`：下载或播放已生成的音色试听 MP3。
- `POST /api/online-mix/tasks`：`subtitle_template_set_id` 为空时自动随机使用模板变体；传入模板 ID 时以指定模板作为基础，并继续随机使用可用变体。
- `POST /api/scripts/generate`：生成短视频脚本。默认 `provider=auto`，配置了
  `AUTOVIDEO_LLM_BASE_URL`、`AUTOVIDEO_LLM_API_KEY` 和 `AUTOVIDEO_LLM_MODEL`
  时优先调用 OpenAI-compatible LLM，失败时回退启发式生成；`provider=llm_only`
  只使用 LLM，失败时返回结构化错误；`provider=heuristic` 只使用本地启发式生成。
  生成逻辑对齐 `junxincode` 的混剪脚本生成器：支持主题生成，也支持通过
  `script_text` 输入已有口播稿、编辑器格式脚本或 JSON 分镜，并自动整理为结构化分镜。
  主题生成会严格围绕 `topic`，不再套用固定商品广告模板；只有传入
  `selling_points` 等明确卖点时才会写产品亮点。LLM 返回内容如果明显偏离主题，
  `provider=auto` 会丢弃该结果并回退到本地启发式生成，`provider=llm_only`
  会返回结构化错误。
  LLM 响应会被规范化为 AutoVideo 分镜 schema：每个镜头包含 `index`、`duration`、
  `narration`、`subtitle`、`visual_description`、`keywords` 和 `delivery`；
  常见的 `shot_id`、`start_time`、`end_time`、`description`、`audio_cue`、
  `voiceover` 等字段会在可安全映射时转换。缺少画面描述或关键词时会按主题和旁白补全；
  非法镜头索引、布尔时长、非字符串关键词或没有可朗读旁白的响应仍会被拒绝。
  请求体 `Content-Length` 和解析后的 JSON 编码大小都受
  `AUTOVIDEO_MAX_SCRIPT_PAYLOAD_BYTES` 限制。
- `GET /api/online-materials/status`：查看默认线上素材源、Pexels/Pixabay
  素材源状态和候选 token secret 是否已配置；响应包含 `default_provider`、
  `candidate_token_secret_configured`，以及 `providers` 数组，每个元素包含
  `provider`、`configured` 和 `enabled`，不返回真实 key 或 secret。
- `POST /api/online-materials/search`：搜索线上免费素材候选。请求字段包含
  `query`、`aspect_ratio`、`min_duration_seconds` 和 `provider=auto|pexels|pixabay`。
  成功响应返回安全的 `source_url`、`preview_url`、`license_note` 和
  `candidate_token`，不会暴露真实下载 URL；未配置素材源、未配置候选签名密钥、
  provider 不可用或 provider 搜索失败时分别返回结构化错误码。请求体
  `Content-Length` 受 `AUTOVIDEO_MAX_ONLINE_MATERIAL_REQUEST_BYTES` 限制。
- `POST /api/online-materials/download`：使用 `candidate_token` 让服务端重新向
  provider 解析真实下载 URL，校验 provider allowlist、DNS、重定向链、连接地址、
  MIME 与扩展名匹配后下载到素材库。响应复用公开素材字段，不暴露本地
  `storage_path` 或真实下载 URL。请求体 `Content-Length` 受
  `AUTOVIDEO_MAX_ONLINE_MATERIAL_REQUEST_BYTES` 限制。
- `POST /api/online-mix/tasks`：基于结构化脚本创建线上混剪任务。默认推荐
  `asset_strategy=auto`，服务端会把脚本里的所有镜头都纳入任务，并按每个镜头的
  `keywords` 或 `visual_description` 自动搜索、下载线上免费素材。用户也可以为部分镜头
  传入 `shot_assets` 或 `shot_materials` 作为覆盖项；线上候选只提交
  `candidate_token`，服务端验签后重新解析 provider 下载地址并保存素材；本地素材只提交
  真实 `material_id`。FFmpeg 可用时任务主输出为 MP4 视频，同时任务目录会保存
  `manifest.json`、`timeline.json`、`subtitles.srt` 和启用字幕时的 `subtitles.ass`；
  启用字幕时还会保留 `output.base.mp4` 便于排查烧录前的视频；FFmpeg 不可用时会在
  `manifest.render_plan` 中记录 `base_video_skipped` 和 `subtitle_burn_skipped`。
  manifest 包含 `script`、`shot_materials`、`source_attribution`、`timeline` 和 `render_plan`。

`POST /api/scripts/generate` 请求字段：

- `topic`：视频主题；主题生成时必填，提供 `script_text` 时可选。
- `provider`：可选，`auto`、`llm_only` 或 `heuristic`，默认 `auto`。
- `duration_seconds`：可选，目标时长，范围 `5` 到 `300`，默认 `30`。
- `aspect_ratio`：可选，画幅，默认 `9:16`。
- `tone`：可选，语气或风格提示。
- `target_audience`：可选，目标受众。
- `selling_points`：可选，卖点列表。
- `script_text`：可选，已有脚本、口播稿、编辑器格式脚本或 JSON 分镜；传入后会优先整理这段文案。
- `max_single_duration`：可选，脚本分析时单段预览的最大时长，范围 `1` 到 `300` 秒。

示例：

```bash
curl -F "file=@/path/to/clip.mp4" http://127.0.0.1:8090/api/materials

curl -X POST http://127.0.0.1:8090/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"title":"测试混剪任务","material_ids":["上一步返回的素材ID"],"options":{"aspect_ratio":"16:9"}}'

curl -X POST http://127.0.0.1:8090/api/scripts/generate \
  -H "Content-Type: application/json" \
  -d '{"topic":"咖啡店早高峰","provider":"auto","duration_seconds":20,"aspect_ratio":"9:16","selling_points":["新品拿铁","通勤提神"]}'

curl -X POST http://127.0.0.1:8090/api/scripts/generate \
  -H "Content-Type: application/json" \
  -d '{"topic":"疗愈型 SPA","provider":"heuristic","script_text":"顾客进店后明显放松。\n护理结束后，她的状态轻盈很多。","max_single_duration":8}'

curl -X POST http://127.0.0.1:8090/api/online-materials/search \
  -H "Content-Type: application/json" \
  -d '{"query":"coffee shop morning","aspect_ratio":"9:16","provider":"auto","min_duration_seconds":4}'

curl -X POST http://127.0.0.1:8090/api/online-materials/download \
  -H "Content-Type: application/json" \
  -d '{"candidate_token":"上一步返回的候选 token"}'

curl -X POST http://127.0.0.1:8090/api/online-mix/tasks \
  -H "Content-Type: application/json" \
  -d '{"title":"线上素材混剪","script":{"id":"script-1","title":"咖啡店早高峰","topic":"咖啡店早高峰","aspect_ratio":"9:16","duration_seconds":10,"shots":[{"index":1,"duration":5,"narration":"旁白","subtitle":"字幕","visual_description":"coffee shop morning","keywords":["coffee shop morning"]}]},"asset_strategy":"auto","provider":"auto"}'

curl "http://127.0.0.1:8090/api/voices?locale=zh-CN&q=Xiaoxiao"

curl -X POST http://127.0.0.1:8090/api/voices/preview \
  -H "Content-Type: application/json" \
  -d '{"text":"你好，欢迎使用 AutoVideo。","voice_id":"zh-CN-XiaoxiaoNeural","rate":"+0%","volume":"+0%","pitch":"+0Hz"}'
```

脚本生成成功响应包含：

- `id`：脚本 ID。
- `title`、`topic`、`aspect_ratio`、`duration_seconds`、`total_duration`：脚本基础信息和归一化总时长。
- `provider`：实际生成来源，`llm` 或 `heuristic`。
- `shots`：镜头数组，每个镜头包含 `index`、`duration`、`narration`、`subtitle`、
  `visual_description`、`keywords` 和 `delivery`。
- `script_text`、`analysis`：当请求包含 `script_text` 时返回，分别用于编辑器文本回显和分段分析。
- `created_at`：创建时间。

脚本生成主要错误码：

```json
{
  "detail": {
    "code": "SCRIPT_TOPIC_REQUIRED",
    "message": "请输入视频主题"
  }
}
```

- `400 SCRIPT_TOPIC_REQUIRED`：`topic` 和 `script_text` 都为空。
- `400 SCRIPT_TEXT_INVALID`：`script_text` 中没有可用的可朗读内容。
- `413 SCRIPT_PAYLOAD_TOO_LARGE`：请求体或脚本 JSON 超过
  `AUTOVIDEO_MAX_SCRIPT_PAYLOAD_BYTES`，响应会包含 `max_script_payload_bytes`，
  service 校验路径还会包含 `payload_bytes`。
- `503 LLM_NOT_CONFIGURED`：`provider=llm_only` 但未完整配置 LLM。
- `502 LLM_GENERATION_FAILED`：`provider=llm_only` 时 LLM HTTP 请求、响应解析或结构校验失败。
- `503 ONLINE_MATERIAL_PROVIDER_NOT_CONFIGURED`：未配置可用 Pexels/Pixabay API key。
- `503 ONLINE_MATERIAL_TOKEN_SECRET_NOT_CONFIGURED`：未配置 `AUTOVIDEO_CANDIDATE_TOKEN_SECRET`。
- `400 ONLINE_MATERIAL_PROVIDER_NOT_AVAILABLE`：请求的线上素材 provider 当前不可用。
- `502 ONLINE_MATERIAL_SEARCH_FAILED`：线上素材 provider 搜索失败，或返回了不安全的公开 URL。
- `400 ONLINE_MATERIAL_CANDIDATE_TOKEN_INVALID`：候选 token 缺失、格式错误或签名无效。
- `400 ONLINE_MATERIAL_CANDIDATE_TOKEN_EXPIRED`：候选 token 已过期。
- `400 ONLINE_MATERIAL_REDIRECT_NOT_ALLOWED`：下载 URL、重定向、DNS、连接地址或 MIME/扩展名校验失败。
- `413 ONLINE_MATERIAL_TOO_LARGE`：线上素材下载超过 `AUTOVIDEO_ONLINE_MATERIAL_MAX_DOWNLOAD_BYTES`。
- `502 ONLINE_MATERIAL_DOWNLOAD_FAILED`：provider 解析或下载请求失败。
- `502 FFMPEG_RENDER_FAILED`：FFmpeg 可用但视频渲染失败。
- `400 ONLINE_MIX_SHOT_SELECTION_INVALID`：线上混剪镜头素材选择重复、冲突、越界或脚本没有有效镜头。
- `409 ONLINE_MIX_NO_MATERIAL_MATCH`：自动匹配时没有找到可用素材，或仍有脚本镜头没有素材。

## 配置

所有配置通过环境变量提供。示例见 `.env.example`。

- `AUTOVIDEO_DATA_DIR`：运行数据目录。
- `AUTOVIDEO_FFMPEG_PATH`：FFmpeg 可执行文件。
- `AUTOVIDEO_MAX_UPLOAD_BYTES`：素材上传大小上限，默认 `2147483648`。
- `AUTOVIDEO_MAX_MULTIPART_OVERHEAD_BYTES`：素材上传 multipart 请求允许的额外开销，默认 `1048576`。
- `AUTOVIDEO_MAX_TASK_MATERIALS`：单个任务允许引用的素材 ID 数量上限，默认 `100`。
- `AUTOVIDEO_MAX_TASK_OPTIONS_BYTES`：单个任务 `options` JSON 编码大小上限，默认 `1048576`。
- `AUTOVIDEO_MAX_TASK_REQUEST_BYTES`：创建任务请求体 `Content-Length` 上限，默认 `2097152`。
- `AUTOVIDEO_EDGE_TTS_DEFAULT_VOICE`：音色中心默认选中的 Edge TTS 音色，默认 `zh-CN-XiaoxiaoNeural`。
- `AUTOVIDEO_MAX_VOICE_PREVIEW_TEXT_CHARS`：单次音色试听文本长度上限，默认 `300`。
- `AUTOVIDEO_MAX_VOICE_PREVIEW_REQUEST_BYTES`：音色试听请求体 `Content-Length` 上限，默认 `8192`。
- `AUTOVIDEO_FISH_SPEECH_URL`：可选 Fish Speech 服务地址，留空时音色复刻功能禁用。
- `AUTOVIDEO_LLM_PROVIDER`：脚本生成 LLM provider，目前仅支持 `openai_compatible`，默认 `openai_compatible`。
- `AUTOVIDEO_LLM_BASE_URL`、`AUTOVIDEO_LLM_API_KEY`、`AUTOVIDEO_LLM_MODEL`：
  OpenAI-compatible LLM 配置，留空时 `provider=auto` 使用启发式脚本 fallback；
  `provider=llm_only` 未完整配置时返回 `LLM_NOT_CONFIGURED`。
- `AUTOVIDEO_LLM_TIMEOUT_SECONDS`：LLM 请求超时时间，默认 `45`。
- `AUTOVIDEO_LLM_TEMPERATURE`：LLM 生成温度，默认 `0.6`。
- `AUTOVIDEO_PEXELS_API_KEY`、`AUTOVIDEO_PIXABAY_API_KEY`：线上免费素材源 API key，
  留空时对应素材源不可用；不要提交真实 key。
- `AUTOVIDEO_ONLINE_MATERIAL_PROVIDER`：在线素材 provider 选择策略，目前仅支持 `auto`，默认 `auto`。
- `AUTOVIDEO_ONLINE_MATERIAL_RESULTS_PER_QUERY`：每个关键词返回的在线素材候选数量，默认 `8`。
- `AUTOVIDEO_ONLINE_MATERIAL_DOWNLOAD_TIMEOUT_SECONDS`：在线素材下载超时时间，默认 `60`。
- `AUTOVIDEO_ONLINE_MATERIAL_MAX_DOWNLOAD_BYTES`：单个在线素材下载大小上限，默认 `524288000`。
- `AUTOVIDEO_MAX_ONLINE_MATERIAL_REQUEST_BYTES`：在线素材搜索和下载请求体 `Content-Length` 上限，默认 `65536`。
- `AUTOVIDEO_CANDIDATE_TOKEN_SECRET`：候选素材签名密钥；不配置时不能签发或验证可下载候选；不要提交真实 secret。
- `AUTOVIDEO_CANDIDATE_TOKEN_TTL_SECONDS`：候选 token 有效期，默认 `1800`。
- `AUTOVIDEO_MAX_SCRIPT_PAYLOAD_BYTES`：脚本生成请求体 `Content-Length` 上限，默认 `65536`。
- `AUTOVIDEO_MAX_ONLINE_MIX_REQUEST_BYTES`：在线混剪任务请求体 `Content-Length` 上限，默认 `2097152`。

不要把真实 token、key、密码或内网地址提交到仓库。

## License

This project is licensed under the GNU Affero General Public License v3.0 only
(`AGPL-3.0-only`).

If you modify this software and let users interact with it over a network, the
AGPL requires you to make the corresponding source code available to those
users.

See [LICENSE](LICENSE) for the full terms.
