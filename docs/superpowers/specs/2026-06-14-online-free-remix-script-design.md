# AutoVideo 线上免费资源混剪与脚本自动生成设计

日期：2026-06-14

## 背景

AutoVideo 当前已经具备产品骨架、素材上传 API、任务创建 API 和占位输出下载能力，但前端和后端还没有形成“输入主题 -> 自动生成脚本 -> 获取线上免费素材 -> 创建混剪任务”的闭环。

目标项目 `/Users/sha/junxincode` 中可参考的能力主要分为三类：

1. `video-generator/app/services/script_generator.py`：把主题或用户文案整理为结构化分镜脚本。
2. `video-generator/app/services/online_material_service.py`：用 Pexels、Pixabay 搜索和下载线上免费视频素材。
3. `video-generator/app/services/video_composer.py`：根据分镜、素材、字幕和 BGM 做实际视频合成。

本阶段只抽取独立产品需要的业务边界和数据形状，不搬旧项目的权限、个人网盘、公盘 SMB、worker、内网 token、云端专有服务或历史兼容逻辑。

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
```

LLM 未配置时，后端使用本地启发式脚本 fallback。Pexels/Pixabay key 均未配置时，线上素材搜索接口返回结构化错误，前端显示配置提示。

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
  "download_url": "https://...",
  "duration": 8.5,
  "width": 1080,
  "height": 1920,
  "license_note": "Pexels/Pixabay source metadata retained"
}
```

### 本地素材元数据扩展

`materials` 表继续保留原有字段，同时新增可选来源字段。SQLite 迁移需要向后兼容已有数据库：

1. `source_type`：`upload` 或 `online`.
2. `source_provider`：`pexels`、`pixabay` 或空。
3. `source_asset_id`：线上素材 ID。
4. `source_url`：素材来源页面或资源 URL。
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
3. `LLM_NOT_CONFIGURED` 只在用户要求 `provider=llm_only` 时返回；默认模式会 fallback。

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

### 下载线上素材

`POST /api/online-materials/download`

请求体使用前一步候选中的 provider、asset_id、download_url、source_url、query 等字段。后端下载到 `AUTOVIDEO_DATA_DIR/materials`，插入素材记录并返回公开素材对象。

下载必须满足：

1. 只允许 `https` URL。
2. 限制响应大小。
3. 流式写入临时文件，完成后原子替换。
4. MIME 和扩展名只允许常见视频格式，未知后缀使用 `.mp4` 或拒绝。
5. 失败时清理临时文件。

### 创建线上混剪任务

`POST /api/online-mix/tasks`

请求：

```json
{
  "title": "睡前精油短视频",
  "script": { "...": "结构化脚本" },
  "asset_strategy": "auto",
  "provider": "auto",
  "options": {
    "aspect_ratio": "9:16",
    "resolution": "1080p"
  }
}
```

后端流程：

1. 校验脚本和镜头数量。
2. 为每个镜头构建搜索词，优先使用 `keywords`，其次使用 `visual_description`。
3. 搜索线上素材并选择最匹配画幅和时长的候选。
4. 下载素材到本地素材库。
5. 调用现有 `create_task()` 创建任务快照。
6. 生成 manifest，包含脚本、素材来源、授权备注和下一阶段渲染说明。

如果部分镜头未匹配到素材，第一版可创建失败任务或返回结构化错误；默认选择返回错误，避免生成缺镜头的误导性任务。

## 素材选择规则

第一版采用确定性规则，不引入复杂向量检索：

1. 画幅匹配优先：`9:16` 优先竖屏，`16:9` 优先横屏，`1:1` 优先接近正方形。
2. 时长满足优先：候选时长大于等于镜头时长。
3. 分辨率高者优先。
4. 同一任务内避免重复 `provider + asset_id`。
5. 没有完全匹配时允许降级到同 provider 的下一候选，但必须记录 `selection_reason`。

## 前端设计

本阶段前端不是营销页，而是工作台流程。新增“线上混剪”区域，嵌入现有混剪工作台。

桌面端结构：

1. 左侧保持现有导航。
2. 主区上半部分是主题表单：主题、时长、画幅、语气、受众、卖点。
3. 中部展示生成的分镜脚本表格，每行包含镜头、时长、旁白、画面描述、关键词。
4. 下部展示素材匹配状态：未搜索、候选、已下载、失败。
5. 右侧状态面板显示运行检查、素材源配置状态和任务输出入口。

移动端结构：

1. 表单改为单列。
2. 分镜脚本使用可折叠镜头列表。
3. 素材候选以纵向卡片显示。
4. 主要操作按钮保持 44px 以上触控高度。

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
9. `SCRIPT_OPTIONS_TOO_LARGE`

## 测试策略

后端测试：

1. LLM 未配置时脚本生成 fallback 可用。
2. 传入 fake LLM client 时能解析结构化分镜。
3. 脚本 payload 超限返回结构化错误。
4. Pexels/Pixabay provider 未配置时返回配置错误。
5. fake provider 搜索结果可按画幅、时长、分辨率排序。
6. 下载使用流式写入，并限制大小。
7. 下载成功后素材元数据包含 provider、asset_id、source_url、license_note。
8. `POST /api/online-mix/tasks` 能生成任务 manifest，且不泄漏本地路径。
9. 无素材匹配时返回 `ONLINE_MIX_NO_MATERIAL_MATCH`。

前端测试：

1. 渲染线上混剪主题表单。
2. 能展示生成的分镜脚本。
3. 能展示素材源未配置状态。
4. 不出现旧项目登录、个人网盘、NAS 或 token 文案。
5. 移动端关键布局样式保持可滚动和不挤压。

## 实施阶段

### 阶段 1：脚本生成 API

新增脚本模型、脚本生成服务、LLM 配置和 fallback。验收点：不配置 LLM 也能生成结构化脚本。

### 阶段 2：线上素材 provider

新增 Pexels/Pixabay provider 接口、搜索、候选排序和配置状态。验收点：fake provider 测试完整，真实 provider 只依赖环境变量。

### 阶段 3：下载与素材元数据

扩展 SQLite 素材表，下载线上素材并插入本地素材库。验收点：下载限制、来源记录和公开响应全部可测。

### 阶段 4：线上混剪任务

串联脚本、素材搜索、下载和现有任务创建。验收点：能通过 API 创建包含脚本与线上素材来源的 manifest。

### 阶段 5：前端工作流

在混剪工作台接入主题表单、脚本预览、素材匹配状态和任务输出入口。验收点：桌面和移动端都能完成第一版线上混剪任务创建。

## 风险与约束

1. Pexels/Pixabay 授权条款和 API 限额可能调整，代码必须保留 provider/source/license metadata，便于后续追踪。
2. 免费素材搜索质量依赖英文关键词，中文主题需要转写或用 fallback 英文查询。第一版可以由 LLM 生成英文关键词；未配置 LLM 时用简单映射和关键词原文兜底。
3. 真实下载可能较慢，第一版使用同步请求即可，但要有超时、大小限制和清理逻辑。
4. 不配置任何线上素材 key 时，系统仍可用本地上传素材和脚本 fallback，不应影响已有功能。
5. 后续真实渲染接入前，manifest 必须清楚标记当前仍是占位输出。

## 验收标准

1. README 和 `.env.example` 说明新增 LLM 与线上素材配置。
2. 后端测试覆盖脚本生成、素材搜索、下载和线上混剪任务。
3. 前端测试覆盖线上混剪入口和关键状态。
4. `PYENV_VERSION=3.12.13 python -m pytest -q` 通过。
5. `npm test -- --run` 和 `npm run build` 通过。
6. PR 创建后按仓库规则完成本地子代理 review 和 GitHub Codex review 监控。
