# syntax=docker/dockerfile:1

FROM python:3.12-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    BUS_SCRAP_DATA_DIR=/app/data \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      gosu \
      fonts-liberation \
      libasound2 \
      libatk-bridge2.0-0 \
      libatk1.0-0 \
      libcups2 \
      libdbus-1-3 \
      libdrm2 \
      libgbm1 \
      libgtk-3-0 \
      libnspr4 \
      libnss3 \
      libx11-xcb1 \
      libxcomposite1 \
      libxdamage1 \
      libxrandr2 \
      xdg-utils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt \
    && playwright install chromium

COPY bus_scrap ./bus_scrap
COPY main.py .
COPY docker-entrypoint.sh /docker-entrypoint.sh

RUN mkdir -p /app/data \
    && useradd --create-home --uid 10001 appsvc \
    && chown -R appsvc:appsvc /app /ms-playwright \
    && chmod +x /docker-entrypoint.sh

# entrypoint inicia como root só para ajustar permissões do volume,
# depois executa a app como appsvc (não-root).
USER root

VOLUME ["/app/data"]

HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
  CMD python -c "from pathlib import Path; import os; p=Path(os.getenv('BUS_SCRAP_DATA_DIR','/app/data')); raise SystemExit(0 if p.exists() and os.access(p, os.W_OK) else 1)"

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["--run-now"]
