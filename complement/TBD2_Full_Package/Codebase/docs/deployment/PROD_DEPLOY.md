# TBD2 - Production Deployment Checklist

Deployment hardening for the ESGRC module. Everything here is **config, not code** -
the application already supports all of it via env vars. Nothing in this doc is applied
automatically; it is the runbook for going live.

> Status: **templated & documented, NOT deployed** (per owner instruction). Fill the real
> values, then follow the steps below.

---

## 1. Secrets & environment (`.env`)

Set these to real values (never commit `.env`):

| Var | Purpose | How to generate |
|-----|---------|-----------------|
| `SECRET_KEY` | JWT signing | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `POSTGRES_PASSWORD` | DB password | `python -c "import secrets; print(secrets.token_urlsafe(24))"` |
| `REDIS_PASSWORD` | Redis auth (prod override requires it) | `python -c "import secrets; print(secrets.token_urlsafe(24))"` |
| `ALLOWED_ORIGINS` | CORS allowlist (comma-separated) | e.g. `https://app.yourdomain.com` |
| `ANTHROPIC_API_KEY` | Claude API | from console.anthropic.com |
| `CLOUDFLARE_R2_*` | Object storage (BUCKET/ENDPOINT/ACCESS_KEY/SECRET_KEY) | from Cloudflare R2 |

Confirm dev-only defaults are gone:
- `DEBUG=false` (the prod override forces this; the app default is already `False`).
- `DEMO_MODE=false` (prod override forces this).
- `SECRET_KEY` is **not** the placeholder `change-me-in-production-...`.

## 2. TLS certificates

Place `fullchain.pem` and `privkey.pem` in `./nginx/certs/`.

- **Real (recommended):** Let's Encrypt. Serve `./nginx/certbot-www` at
  `/.well-known/acme-challenge/` (the prod nginx `:80` block already does this), run certbot,
  then copy the issued `fullchain.pem` / `privkey.pem` into `./nginx/certs/`.
- **Staging/self-signed (testing only):**
  ```bash
  mkdir -p nginx/certs
  openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout nginx/certs/privkey.pem -out nginx/certs/fullchain.pem \
    -subj "/CN=localhost"
  ```

## 3. Bring up the hardened stack

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

This layers `docker-compose.prod.yml`, which:
- starts **Redis with `--requirepass $REDIS_PASSWORD`** and points every client at
  `redis://:$REDIS_PASSWORD@redis:6379/...`;
- **stops publishing uvicorn** (`esgrc_api` has no host ports) - nginx is the only public
  entrypoint, on `:80`/`:443`;
- sets `ALLOWED_ORIGINS`, `DEBUG=false`, `DEMO_MODE=false`;
- runs nginx with **`nginx.prod.conf`** (TLS termination, HTTP→HTTPS redirect, HSTS preload,
  the full security-header set, and SSE-safe proxying).

**URL layout.** The `frontend` service builds the SPA into the `frontend_dist` volume and
exits; nginx serves those files at `/` and proxies `/api/*` to the backend with the `/api`
prefix stripped. So the browser app is at `https://DOMAIN/`, the API is at
`https://DOMAIN/api/...` (matching `frontend/src/lib/axios.ts`'s `baseURL: '/api'`), and
`/health` is an explicit exception that stays unprefixed for load balancers. Interactive API
docs are at `/api/docs`.

Migrations run automatically (`alembic upgrade head` before uvicorn boots).

## 4. Seed (first deploy only)

```bash
docker compose exec esgrc_api python pipeline/scripts/seed_demo.py
```
(Skip for a real tenant; use your own org-provisioning flow instead.)

## 5. Post-deploy verification (smoke)

Run against your domain. Expected results - these mirror the live checks already verified
locally on 2026-07-07:

| Check | Command shape | Expect |
|-------|---------------|--------|
| HTTPS up | `curl -I https://DOMAIN/health` | `200`, HSTS header present |
| Health is the API, not the SPA | `curl https://DOMAIN/health` | JSON, **not** HTML |
| Frontend served | `curl -I https://DOMAIN/` | `200`, `content-type: text/html` |
| SPA deep link survives refresh | `curl -I https://DOMAIN/dashboard` | `200` (index.html fallback) |
| API reachable under /api | `curl -I https://DOMAIN/api/docs` | `200` |
| HTTP redirects | `curl -I http://DOMAIN/` | `301` → https |
| uvicorn not exposed | `curl http://DOMAIN:8000/health` | connection refused |
| CORS locked | preflight from a foreign origin | not allowed |
| RBAC | viewer `POST /api/risks` | `403` |
| Rate limit | 6 rapid `POST /api/auth/login` | `429` on the 6th |
| Path traversal | `/api/pipelines/{id}/upload-input?filename=..` | `400` |
| Redis auth | `redis-cli ping` without `-a` | `NOAUTH` error |

## 6. Operational notes

- **Backups:** the `postgres_data` volume holds all tenant data - schedule `pg_dump`.
- **Secret rotation:** rotate `SECRET_KEY` (invalidates sessions), `REDIS_PASSWORD`, DB
  password, and R2/Anthropic keys on a schedule.
- **Logs:** structured JSON via `pipeline/middleware.py`; wire `SENTRY_DSN` for error capture.
- **CI/CD:** `deploy.yml` targets Railway but is **manual-only** (`workflow_dispatch`) - a push
  to `main` never triggers it. Railway was abandoned (requires a paid plan); see
  [DEMO_DEPLOY.md](DEMO_DEPLOY.md) for the actual deploy path. Re-add a `push: branches: [main]`
  trigger only if you deliberately adopt Railway and want continuous deploys.
