---
title: Vigilant Lens ESGRC Demo
emoji: 🛡️
colorFrom: indigo
colorTo: green
sdk: docker
app_port: 7860
pinned: false
short_description: ESG–Risk–Compliance SaaS demo (Vigilant Lens)
---

# Vigilant Lens - ESGRC Demo

Public demo of the ESG-Risk-Compliance module of Vigilant Lens: a multi-tenant
SaaS for ESG metric tracking, risk registers, compliance frameworks, and
two-tier LLM analytics pipelines.

This Space runs the **entire stack in one container** - React frontend, FastAPI
backend, in-container Redis, and a SQLite database that is **reseeded with demo
data on every boot**. No external services required.

## Log in

The demo org (**Vigilant Lens Demo Corp**) is seeded fresh on each start.
All passwords are `Demo1234!`:

| Email | Role | Sees |
|---|---|---|
| `admin@demo.com` | Admin | All modules |
| `analyst@demo.com` | Analyst | ESGRC |
| `viewer@demo.com` | Viewer | ESGRC |
| `esgrc.admin@demo.com` | Admin | ESGRC only |
| `apex.admin@demo.com` | Admin | Apex only |
| `customer.admin@demo.com` | Admin | Customer only |

## What's live

- Dashboards: ESG metrics (14 categories × 4 quarters), 12 risks, GRI + ISO 14001 compliance.
- Three **completed** pipeline runs (ESGRC 7-step, Customer 7-step, Apex 8-step) with their Claude risk assessments viewable inline.
- API docs at `/api/docs`.

## Deploy status

Hugging Face Docker Spaces require a billing method on the account.
Shubham to set up and deploy from India.

## Notes

- The demo runs at **$0 Claude spend** - it displays pre-seeded analytics.
  Triggering a *new* live pipeline run requires an `ANTHROPIC_API_KEY` set as a
  Space secret and will incur Anthropic API cost.
- Data resets on every restart by design (SQLite reseed).
- This is a **demo build** (`DEMO_MODE=true`, Celery eager, in-container Redis) -
  not the production multi-service deployment.

---

## How this Space is built

- Image: [`Dockerfile.hf`](../../Dockerfile.hf) at the repo root.
- Boot: [`entrypoint.sh`](entrypoint.sh) - redis → migrate → seed → uvicorn → nginx.
- Proxy: [`nginx.conf`](nginx.conf) - serves the SPA and proxies `/api/*` to the backend.

### Optional Space secret
| Secret | Effect |
|---|---|
| `ANTHROPIC_API_KEY` | Enables manually-triggered live pipeline runs (costs money). Omit for the free view-only demo. |
