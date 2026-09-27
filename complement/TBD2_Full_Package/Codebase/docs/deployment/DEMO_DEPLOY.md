# Demo deployment

**Single source of truth for how the demo is served.** Supersedes the Render decision in
[MEETING_DECISIONS.md](../project/MEETING_DECISIONS.md), the Hugging Face Spaces claim that used to sit
in `.github/workflows/deploy.yml`, and the "unsolved" status in the 2026-08-06 daily report.

Decided 2026-08-07.

---

## Why the obvious options do not work

Every free tier we tried triggers **card KYC verification from Pakistan**, even where the
plan itself is free: Render, Vercel, Koyeb, Hugging Face. Teammates in India hit none of it,
so the region is the difference, not the account. Railway needs a paid plan outright. HF
Docker Spaces began requiring billing in July 2026.

This is not a configuration problem and no amount of retrying fixes it.

## The plan

| Stage | What | When |
|---|---|---|
| **Now** | Cloudflare tunnel from a local container | Scheduled demos, and for the team to click a real deployment |
| **Permanent** | Company account under METEOERAIT SOFTWARE P LTD, deployed from India | Once digital signatures complete |

### Read this before sending anyone a link

**Do not publish a URL to a client or investor until the scenario methodology is settled
with the analytics owner.** The scenario simulation currently returns
`Overall Risk = 0.3802845671230959` for every client, because it reads no client metric
values, and the "Metrics involved in High-Risk Scenarios" section names three metrics chosen
by correlating real data against a random vector. Hosting is not what is blocking an external
demo; that is.

A tunnel for a booked call where you drive the screen is fine. A link someone browses
unattended is not, yet.

---

## Runbook: Cloudflare tunnel

Free, no card, no account required for a quick tunnel, and it works from Pakistan.

### 1. Bring the stack up

```bash
docker compose -f docker-compose.yml up -d --build
```

This now serves the whole app, not just the API: the `frontend` service builds the SPA into
the `frontend_dist` volume and nginx serves it at `/` while proxying `/api/*` to the backend.
Check it locally before exposing anything:

```bash
curl -I http://localhost/            # 200, text/html  (the SPA)
curl    http://localhost/health      # JSON, not HTML  (the API)
curl -I http://localhost/api/docs    # 200
```

If `/health` returns HTML you are on an old nginx config; the SPA fallback is swallowing it.

### 2. Seed the demo data

```bash
docker compose exec esgrc_api python pipeline/scripts/seed_demo.py
```

Idempotent. Login is `admin@demo.com` / `Demo1234!`.

### 3. Start the tunnel

```bash
docker run --rm --network host cloudflare/cloudflared:latest tunnel --url http://localhost:80
```

It prints a `https://<random>.trycloudflare.com` URL. That URL is public to anyone who has
it, and it changes every restart. For a stable hostname you need a Cloudflare account and a
domain, which is the same work as the permanent option below and not worth doing twice.

### 4. Before you share it, every time

- [ ] `DEMO_MODE` is set as you intend. `true` fakes the analytics scripts and spends nothing
      on Claude; `false` runs the real pipeline and costs real money per run.
- [ ] `ANTHROPIC_API_KEY` is the rotated key, not the exposed one.
- [ ] Rate limits are active. `RATE_LIMIT_ENABLED` must not be `false`.
- [ ] Confirm registration is limited: six rapid `POST /api/auth/register` should give a 429
      on the sixth.
- [ ] Org creation is SUPER_ADMIN only. Already enforced in code, verified 2026-08-07.
- [ ] Kill the tunnel when the call ends. The URL stays live until you do.

### What this does not give you

Your machine has to be awake and online. Sleep the laptop mid-demo and the URL dies, and a
long pipeline run will show an inflated step duration because the host suspended the
subprocess rather than the step hanging.

---

## Permanent: company account, deployed from India

The durable answer, and the entity registration is what makes it right rather than a
workaround.

- Praveen is in India, where these providers work card-free.
- Once digital signatures for **METEOERAIT SOFTWARE P LTD** complete, infrastructure can sit
  under the company rather than in a personal account. That is where it should be before any
  investor conversation.
- It removes the dependency on one laptop being awake.

**What to hand over:** this repository builds three images, all verified by CI on every
push, so there is nothing bespoke to reproduce.

| Image | Purpose |
|---|---|
| `ESGRC/Dockerfile` | API |
| `pipeline/Dockerfile` | Celery worker and beat |
| `frontend/Dockerfile` | Builds the SPA into the shared volume |
| `Dockerfile.hf` | Single-container variant, still builds, useful if a host wants one image |

Production compose, TLS and the security posture are documented in
[PROD_DEPLOY.md](PROD_DEPLOY.md). Secrets needed: `SECRET_KEY`, `POSTGRES_PASSWORD`,
`REDIS_PASSWORD`, `ANTHROPIC_API_KEY`, `CLOUDFLARE_R2_*`, `ALLOWED_ORIGINS`.

---

## Options considered and rejected

| Option | Why not |
|---|---|
| Render, Vercel, Koyeb, HF free tiers | Card KYC from Pakistan |
| Railway | Paid plan required; `deploy.yml` remains manual-only and unwired |
| Back4App | Card-free and Docker-capable, but 256 MB is too small for this stack |
| Sevalla ($50/2mo), Zeabur ($5/mo) | Card-free as of July 2026, but unverified from Pakistan. Cost is trivial; the risk is spending a day discovering it does not work, when the company account solves it properly for the same effort |
| Local plus screen share | What was used on 11 Jul. No link to send, nothing left running |
