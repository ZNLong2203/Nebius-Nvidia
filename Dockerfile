# --- stage 1: the interface -------------------------------------------------
# Next.js is exported to static files, so it needs node at build time and never
# at runtime.
FROM node:22-slim AS web

WORKDIR /web
COPY web/package.json web/package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY web/ ./
RUN npm run build


# --- stage 2: the service ---------------------------------------------------
# The agent's own executions happen in Nebius Sandboxes, not here, so this image
# only serves HTTP and talks to Token Factory.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    ARBORIST_RUNS_DIR=/data/runs

WORKDIR /app

COPY pyproject.toml README.md ./
COPY arborist ./arborist
RUN pip install --no-cache-dir -e ".[contree]"

COPY ui ./ui
COPY examples ./examples
COPY --from=web /web/out ./web/out

# Recorded runs live on a volume so the demo survives a redeploy.
RUN mkdir -p /data/runs
VOLUME ["/data/runs"]

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "arborist.server:app", "--host", "0.0.0.0", "--port", "8000"]
