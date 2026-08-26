# syntax=docker/dockerfile:1
FROM python:3.13-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip wheel --wheel-dir /wheels .

FROM python:3.13-slim

ARG APP_UID=568
ARG APP_GID=568
ARG VERSION=dev

LABEL org.opencontainers.image.title="JuiceWRLD API Downloader" \
    org.opencontainers.image.description="Keep a local Juice WRLD API Compilation mirror up to date" \
    org.opencontainers.image.source="https://github.com/JochemKuipers/juicewrld-api-dl" \
    org.opencontainers.image.url="https://github.com/JochemKuipers/juicewrld-api-dl" \
    org.opencontainers.image.documentation="https://github.com/JochemKuipers/juicewrld-api-dl#readme" \
    org.opencontainers.image.version="${VERSION}" \
    org.opencontainers.image.licenses="MIT"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    JWI_OUT_DIR=/data \
    JWI_CONFIG_DIR=/config

RUN groupadd --gid "${APP_GID}" app \
    && useradd --uid "${APP_UID}" --gid app --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /data /config \
    && chown -R app:app /data /config

COPY --from=builder /wheels /wheels
RUN python -m pip install --no-cache-dir /wheels/*.whl \
    && rm -rf /wheels

USER app
WORKDIR /home/app

ENTRYPOINT ["juicewrld-api-dl"]
CMD ["watch"]