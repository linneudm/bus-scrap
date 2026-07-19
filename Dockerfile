# syntax=docker/dockerfile:1.7

# -----------------------------------------------------------------------------
# Stage 1: dependências Python + Chromium (camadas estáveis / cacheáveis)
# -----------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /build

RUN python -m venv /opt/venv

COPY requirements.txt .

# Cache de pip entre builds (BuildKit)
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip \
    && pip install -r requirements.txt

# Browser em camada própria: só invalida se requirements/playwright mudarem
RUN playwright install chromium \
    && find /ms-playwright -type f \( -name '*.zip' -o -name '*.md' \) -delete \
    && find /opt/venv -type d -name '__pycache__' -prune -exec rm -rf {} + \
    && find /opt/venv -type f -name '*.pyc' -delete \
    && rm -rf /tmp/* /var/tmp/*

# -----------------------------------------------------------------------------
# Stage 2: runtime enxuto
# -----------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    BUS_SCRAP_DATA_DIR=/app/data \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Reaproveita venv + browsers do builder (sem rebaixar)
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /ms-playwright /ms-playwright

# gosu + libs do Chromium; cache apt entre builds
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean \
    && echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' \
         > /etc/apt/apt.conf.d/keep-cache \
    && apt-get update \
    && apt-get install -y --no-install-recommends gosu \
    && playwright install-deps chromium \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Código da app por último → mudanças de código não refazem pip/browser
COPY bus_scrap ./bus_scrap
COPY main.py .
COPY bus-ctl /usr/local/bin/bus-ctl
COPY docker-entrypoint.sh /docker-entrypoint.sh

RUN mkdir -p /app/data \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin appsvc \
    && chown -R appsvc:appsvc /app /ms-playwright \
    && chmod +x /docker-entrypoint.sh /usr/local/bin/bus-ctl \
    && find /app -type d -name '__pycache__' -prune -exec rm -rf {} + \
    && find /app -type f -name '*.pyc' -delete

# entrypoint inicia como root só para ajustar permissões do volume,
# depois executa a app como appsvc (não-root).
USER root

VOLUME ["/app/data"]

HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
  CMD python -c "from pathlib import Path; import os; p=Path(os.getenv('BUS_SCRAP_DATA_DIR','/app/data')); raise SystemExit(0 if p.exists() and os.access(p, os.W_OK) else 1)"

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["--run-now"]
