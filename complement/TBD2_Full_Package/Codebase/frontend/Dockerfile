# ─────────────────────────────────────────────────────────────────────────────
# Frontend build-and-publish container.
#
# The compose stack had no frontend service at all: nginx proxied everything to
# esgrc_api, which is an API-only FastAPI app, so `docker compose up` never
# served the SPA. This container builds the production bundle and copies it into
# a shared volume that nginx serves directly.
#
# It is deliberately NOT a long-running server. It publishes its assets and
# exits 0; nginx waits for that via `service_completed_successfully`. That keeps
# a single nginx as the only web server and the only TLS termination point,
# matching how Dockerfile.hf already does it for the single-container demo.
#
# Build context is the REPO ROOT (not frontend/), so paths below are prefixed
# with frontend/ - same convention as ESGRC/Dockerfile and pipeline/Dockerfile.
# ─────────────────────────────────────────────────────────────────────────────

FROM node:20-slim AS build
WORKDIR /fe

# package.json + lockfile first so npm ci is cached independently of source.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
# Vite reads import.meta.env at BUILD time, so anything the bundle needs must be
# present here rather than injected at container start.
RUN npm run build          # -> /fe/dist

FROM alpine:3.20
COPY --from=build /fe/dist /dist-src
# Replace the volume contents on every boot so a rebuilt bundle actually lands,
# rather than a stale one persisting because the volume already had files.
CMD ["sh", "-c", "rm -rf /dist/* /dist/.[!.]* 2>/dev/null; cp -a /dist-src/. /dist/ && echo 'frontend assets published' && ls /dist"]
