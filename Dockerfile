ARG NODE_IMAGE=node:22-bookworm-slim
ARG PYTHON_IMAGE=python:3.12-slim

FROM ${NODE_IMAGE} AS frontend-builder

ARG NPM_REGISTRY=""

WORKDIR /frontend

COPY frontend/package*.json ./
RUN set -eux; \
    if [ -n "${NPM_REGISTRY}" ]; then npm config set registry "${NPM_REGISTRY}"; fi; \
    npm ci

COPY frontend ./
RUN npm run build

FROM ${PYTHON_IMAGE}

ARG APT_DEBIAN_MIRROR=""
ARG APT_SECURITY_MIRROR=""
ARG PIP_INDEX_URL=""
ARG PIP_TRUSTED_HOST=""

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV AUTOVIDEO_HOST=0.0.0.0
ENV AUTOVIDEO_PORT=8090
ENV AUTOVIDEO_DATA_DIR=/app/data

WORKDIR /app

RUN set -eux; \
    if [ -n "${APT_DEBIAN_MIRROR}" ] || [ -n "${APT_SECURITY_MIRROR}" ]; then \
        for source_file in /etc/apt/sources.list /etc/apt/sources.list.d/*.list /etc/apt/sources.list.d/*.sources; do \
            [ -e "${source_file}" ] || continue; \
            if [ -n "${APT_SECURITY_MIRROR}" ]; then \
                sed -i "s|http://deb.debian.org/debian-security|${APT_SECURITY_MIRROR}|g; s|https://deb.debian.org/debian-security|${APT_SECURITY_MIRROR}|g" "${source_file}"; \
            fi; \
            if [ -n "${APT_DEBIAN_MIRROR}" ]; then \
                sed -i "s|http://deb.debian.org/debian|${APT_DEBIAN_MIRROR}|g; s|https://deb.debian.org/debian|${APT_DEBIAN_MIRROR}|g" "${source_file}"; \
            fi; \
        done; \
    fi; \
    apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE ./
COPY autovideo ./autovideo
COPY --from=frontend-builder /frontend/dist ./frontend/dist

RUN set -eux; \
    pip_args=""; \
    if [ -n "${PIP_INDEX_URL}" ]; then pip_args="${pip_args} --index-url ${PIP_INDEX_URL}"; fi; \
    if [ -n "${PIP_TRUSTED_HOST}" ]; then pip_args="${pip_args} --trusted-host ${PIP_TRUSTED_HOST}"; fi; \
    pip install --no-cache-dir ${pip_args} .

EXPOSE 8090

CMD ["python", "-m", "autovideo.main"]
