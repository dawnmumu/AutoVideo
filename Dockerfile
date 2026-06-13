FROM node:20-bookworm-slim AS frontend-builder

WORKDIR /frontend

COPY frontend/package*.json ./
RUN npm install

COPY frontend ./
RUN npm run build

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV AUTOVIDEO_HOST=0.0.0.0
ENV AUTOVIDEO_PORT=8090
ENV AUTOVIDEO_DATA_DIR=/app/data

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE ./
COPY autovideo ./autovideo
COPY --from=frontend-builder /frontend/dist ./frontend/dist

RUN pip install --no-cache-dir .

EXPOSE 8090

CMD ["python", "-m", "autovideo.main"]
