# AutoVideo

AutoVideo 是一个个人自托管的视频混剪工作台。项目会从产品骨架开始，逐步接入字幕模板、BGM 管理、音色中心、功能提取处理和混剪任务流。

## 当前阶段

阶段 1：产品骨架

- FastAPI 后端服务
- React + Vite 中文工作台首页
- 字幕模板、BGM 管理、音色中心、功能提取处理等一级入口
- 环境变量配置
- 数据目录初始化
- FFmpeg 与可选 Fish Speech 运行检查
- 本地启动和 Docker 启动

尚未接入登录、权限管理、个人网盘导入、BGM 上传、字幕模板编辑、音色复刻、功能提取处理和真实混剪渲染。

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

## 配置

所有配置通过环境变量提供。示例见 `.env.example`。

- `AUTOVIDEO_DATA_DIR`：运行数据目录。
- `AUTOVIDEO_FFMPEG_PATH`：FFmpeg 可执行文件。
- `AUTOVIDEO_FISH_SPEECH_URL`：可选 Fish Speech 服务地址，留空时音色复刻功能禁用。

不要把真实 token、key、密码或内网地址提交到仓库。

## License

This project is licensed under the GNU Affero General Public License v3.0 only
(`AGPL-3.0-only`).

If you modify this software and let users interact with it over a network, the
AGPL requires you to make the corresponding source code available to those
users.

See [LICENSE](LICENSE) for the full terms.
