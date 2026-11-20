# syntax=docker/dockerfile:1
# Whole demo in one image: FastAPI + built dashboard (/dashboard/) + phone page (/alert/).
# Data (data/out) and model artifacts (model/artifacts) are NOT baked in: docker-compose.yml mounts them
# read-only, and .env is passed at runtime (env_file). See README "Run with Docker".

# ---- stage 1: build the dashboard from the root workspace lockfile ----
FROM node:22-bookworm-slim AS web
WORKDIR /src
COPY package.json package-lock.json turbo.json ./
COPY dashboard/package.json dashboard/package.json
# api/package.json is listed in the root workspaces, so npm ci needs it
COPY api/package.json api/package.json
RUN npm ci --workspace dashboard --include-workspace-root=false
COPY dashboard/ dashboard/
RUN npm run build --workspace dashboard

# ---- stage 2: Python runtime ----
FROM python:3.11-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

# lightgbm wheels link against OpenMP (libgomp)
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgomp1 \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api/ api/
COPY core/ core/
COPY model/ model/
COPY alert/ alert/
COPY config.yaml .
COPY --from=web /src/dashboard/dist /app/dashboard/dist

RUN mkdir -p data/out model/artifacts \
 && useradd --uid 10001 --user-group --no-create-home --home-dir /app --shell /usr/sbin/nologin app \
 && chown -R app:app /app
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"]
CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
