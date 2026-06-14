# AutoVideo

AutoVideo 是一个个人自托管的视频混剪工作台。项目会从产品骨架开始，逐步接入字幕模板、BGM 管理、音色中心、功能提取处理和混剪任务流。

## 当前阶段

阶段 1.5：产品骨架 + 视频任务 API 骨架

- FastAPI 后端服务
- React + Vite 中文工作台首页
- 字幕模板、BGM 管理、音色中心、功能提取处理等一级入口
- 环境变量配置
- 数据目录初始化
- FFmpeg 与可选 Fish Speech 运行检查
- 素材上传 API
- 视频任务创建、查询和占位输出下载 API
- 本地启动和 Docker 启动

尚未接入登录、权限管理、个人网盘导入、BGM 上传、字幕模板编辑、音色复刻、功能提取处理和真实混剪渲染。当前任务输出是占位清单，用于打通 API 闭环。

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

当前后端已经提供最小视频任务闭环，便于后续接入真实混剪 pipeline：

- `POST /api/materials`：上传素材文件，保存到 `AUTOVIDEO_DATA_DIR/materials`。服务端落盘文件名使用素材 ID 和受控后缀，原始文件名保存在 metadata 中；当 `Content-Length` 超过 `AUTOVIDEO_MAX_UPLOAD_BYTES + AUTOVIDEO_MAX_MULTIPART_OVERHEAD_BYTES` 时返回 `413` 和 `REQUEST_TOO_LARGE`，文件流读取过程中仍会按 `AUTOVIDEO_MAX_UPLOAD_BYTES` 二次限制。
- `GET /api/materials?limit=50&offset=0`：分页查看已上传素材，`limit` 最大为 `200`。
- `POST /api/tasks`：基于素材 ID 创建任务，保存任务快照。请求体 `Content-Length` 受 `AUTOVIDEO_MAX_TASK_REQUEST_BYTES` 限制，`material_ids` 数量受 `AUTOVIDEO_MAX_TASK_MATERIALS` 限制，`options` JSON 编码大小受 `AUTOVIDEO_MAX_TASK_OPTIONS_BYTES` 限制。
- `GET /api/tasks?limit=50&offset=0`：分页查看任务列表，`limit` 最大为 `200`。
- `GET /api/tasks/{task_id}`：查看单个任务状态。
- `GET /api/tasks/{task_id}/output`：下载任务占位输出清单。

示例：

```bash
curl -F "file=@/path/to/clip.mp4" http://127.0.0.1:8090/api/materials

curl -X POST http://127.0.0.1:8090/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"title":"测试混剪任务","material_ids":["上一步返回的素材ID"],"options":{"aspect_ratio":"16:9"}}'
```

## 配置

所有配置通过环境变量提供。示例见 `.env.example`。

- `AUTOVIDEO_DATA_DIR`：运行数据目录。
- `AUTOVIDEO_FFMPEG_PATH`：FFmpeg 可执行文件。
- `AUTOVIDEO_MAX_UPLOAD_BYTES`：素材上传大小上限，默认 `2147483648`。
- `AUTOVIDEO_MAX_MULTIPART_OVERHEAD_BYTES`：素材上传 multipart 请求允许的额外开销，默认 `1048576`。
- `AUTOVIDEO_MAX_TASK_MATERIALS`：单个任务允许引用的素材 ID 数量上限，默认 `100`。
- `AUTOVIDEO_MAX_TASK_OPTIONS_BYTES`：单个任务 `options` JSON 编码大小上限，默认 `1048576`。
- `AUTOVIDEO_MAX_TASK_REQUEST_BYTES`：创建任务请求体 `Content-Length` 上限，默认 `2097152`。
- `AUTOVIDEO_FISH_SPEECH_URL`：可选 Fish Speech 服务地址，留空时音色复刻功能禁用。
- `AUTOVIDEO_LLM_PROVIDER`：脚本生成 LLM provider，目前仅支持 `openai_compatible`，默认 `openai_compatible`。
- `AUTOVIDEO_LLM_BASE_URL`：OpenAI-compatible LLM API 基础地址，留空时不启用 LLM。
- `AUTOVIDEO_LLM_API_KEY`：OpenAI-compatible LLM API key，留空时不启用 LLM；不要提交真实 key。
- `AUTOVIDEO_LLM_MODEL`：OpenAI-compatible LLM 模型名，留空时不启用 LLM。
- `AUTOVIDEO_LLM_TIMEOUT_SECONDS`：LLM 请求超时时间，默认 `45`。
- `AUTOVIDEO_LLM_TEMPERATURE`：LLM 生成温度，默认 `0.6`。
- `AUTOVIDEO_PEXELS_API_KEY`：Pexels API key，留空时不启用 Pexels 在线素材；不要提交真实 key。
- `AUTOVIDEO_PIXABAY_API_KEY`：Pixabay API key，留空时不启用 Pixabay 在线素材；不要提交真实 key。
- `AUTOVIDEO_ONLINE_MATERIAL_PROVIDER`：在线素材 provider 选择策略，目前仅支持 `auto`，默认 `auto`。
- `AUTOVIDEO_ONLINE_MATERIAL_RESULTS_PER_QUERY`：每个关键词返回的在线素材候选数量，默认 `8`。
- `AUTOVIDEO_ONLINE_MATERIAL_DOWNLOAD_TIMEOUT_SECONDS`：在线素材下载超时时间，默认 `60`。
- `AUTOVIDEO_ONLINE_MATERIAL_MAX_DOWNLOAD_BYTES`：单个在线素材下载大小上限，默认 `524288000`。
- `AUTOVIDEO_CANDIDATE_TOKEN_SECRET`：在线素材候选下载凭证签名密钥，留空时不能签发或验证可下载候选；不要提交真实 secret。
- `AUTOVIDEO_CANDIDATE_TOKEN_TTL_SECONDS`：在线素材候选下载凭证有效期，默认 `1800`。
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
