# Hosting - options & cost estimate

**Requested by Praveen.** Prepared 18 Jul 2026. All prices are **approximate list prices in USD/month** and must be confirmed at signup - cloud pricing moves. Figures exclude tax.

---

## TL;DR

| Horizon | Recommendation | Infra cost |
|---|---|---|
| **Now → 3 clients** | ⭐ **One DigitalOcean droplet** (8 GB / 4 vCPU) running the existing `docker-compose.prod.yml`, + Cloudflare R2 | **~$60/mo** |
| **~10 clients** | Split app + worker droplets, managed Postgres | **~$110–150/mo** |
| **~50 clients** | 2–3 worker droplets, managed Postgres (HA), load balancer | **~$400–700/mo** |

Plus **LLM (variable)**: ~**$1–4 per full run**; budget **~$15/client/month**.

**At 50 clients: ~$1,150–1,450/mo total vs the $2,000/mo budget - comfortably inside.** Against 50 clients at even $1,000/mo pricing (~$50k/mo revenue), infra is **~2–3% of revenue**. Hosting is not, and will not be, our constraint.

> ⛔ **Everything here is gated on a payment card.** Every provider below requires one. This is the real blocker - the company entity + business card unblocks it (and also unlocks AWS Bedrock for data residency later). *(Note: the entity registered 7 Aug 2026 as METEOERAIT SOFTWARE P LTD in India, not Canada - see `docs/deployment/DEMO_DEPLOY.md`. The card/entity blocker described here is otherwise unchanged.)*

---

## 1. What we actually need to host

Six services (`docker-compose.yml`): `postgres`, `redis`, `esgrc_api`, `celery_worker`, `celery_beat`, `nginx` - plus object storage (Cloudflare R2).

| Service | Profile | Notes |
|---|---|---|
| **celery_worker** | **The cost driver** | Runs the analytics as subprocesses (pandas/scipy/torch). Readiness audit: **≥2 GB RAM, concurrency 2–4 per core.** |
| esgrc_api | Light | FastAPI, 2 uvicorn workers. ~1–2 GB. |
| postgres | Light early | ~1–2 GB; grows with runs/history. |
| redis | Tiny | Capped at **256 MB** (`--maxmemory 256mb`). |
| celery_beat, nginx | Negligible | Scheduler + reverse proxy. |

### 💡 The single biggest cost lever
The worker currently defaults to **`--concurrency=12`** (`pipeline/Dockerfile:44`). With ~2 GB per analytics subprocess, that implies a **24 GB+ box**. Tuning it to **`--concurrency=2` (or 4)** for early clients lets everything run on an **8 GB droplet** - the difference between **~$48/mo and ~$200+/mo**. Runs are quarterly, not continuous, so low concurrency costs us nothing in practice.

---

## 2. All available options

| Option | ~Cost (Phase 1) | Pros | Cons |
|---|---|---|---|
| ⭐ **DigitalOcean** (droplet + R2) | **~$60/mo** | Simple, predictable flat pricing; our `docker-compose.prod.yml` runs as-is; easy signup; good docs; managed Postgres available when needed | Not "enterprise-brand" for large buyers; fewer managed services than AWS |
| **Hetzner Cloud** | **~$12–20/mo** | **Cheapest by far** (~¼–⅕ of DO); excellent hardware | **Strict/opaque signup - high rejection risk from our region**; EU-only regions; less enterprise-recognised |
| **Oracle Cloud Always-Free** | **$0** | Genuinely free tier (4 ARM cores / 24 GB RAM); our worker image already supports ARM64 | Still needs card verification; ARM capacity often unavailable; free instances can be reclaimed; **not safe for client production** |
| **AWS / Azure / GCP** | **~$120–180/mo** | Enterprise credibility; **AWS Bedrock = Claude with data residency**; every managed service | 2–3× the cost; complex billing; overkill now |
| **Render / Railway / Fly.io** (PaaS) | **~$25–80/mo** | Least ops work; git-push deploys | **Render already blocked us (card verification)**; costlier at scale; less control; Railway abandoned |
| **Self-host / on-prem** | Hardware only | No recurring cloud bill | No uptime/backup story; unacceptable for a B2B SaaS |

---

## 3. Phased plan & costs

### Phase 1 - now → ~3 clients · **~$60/mo**
One droplet runs the whole stack via the existing prod compose.
| Item | Cost |
|---|---|
| DO droplet 8 GB / 4 vCPU | ~$48 |
| Automated backups (20%) | ~$10 |
| Cloudflare R2 (10 GB free, then $0.015/GB, **zero egress**) | ~$0–2 |
| Domain + TLS (Let's Encrypt free) | ~$1 |
| **Total** | **~$60/mo** |

*Set worker `--concurrency=2`. Postgres + Redis run as containers (no managed DB yet).*

### Phase 2 - ~10 clients · **~$110–150/mo**
Split the worker onto its own box so analytics can't starve the API.
| Item | Cost |
|---|---|
| App droplet 4 GB / 2 vCPU | ~$24 |
| Worker droplet 8 GB / 4 vCPU | ~$48 |
| Managed Postgres (backups/PITR included) | ~$15–30 |
| Backups + R2 + domain | ~$15 |
| **Total** | **~$110–150/mo** |

### Phase 3 - ~50 clients · **~$400–700/mo**
| Item | Cost |
|---|---|
| 2–3 worker droplets (8–16 GB) | ~$150–300 |
| App droplets ×2 + load balancer | ~$60–110 |
| Managed Postgres (larger / HA) | ~$60–200 |
| R2, backups, monitoring | ~$40 |
| **Total** | **~$400–700/mo** |

---

## 4. LLM cost (the real variable)

This scales with **clients × run frequency**, not with hosting.
- **Measured:** a full 12-module Apex run ≈ **$0.94**; ESGRC module run ≈ **$0.03–0.93** depending on context size (the guard auto-upgrades Haiku→Sonnet on large inputs).
- **Planning figure:** **~$15/client/month** (covers scheduled runs, re-runs, the nightly agent, and Co-Pilot usage).
- **Cadence matters most:** reporting is **quarterly**, so a client is only a handful of full runs per year. Frequent re-runs are what drive cost.

| Clients | LLM/mo |
|---|---|
| 3 | ~$45 |
| 10 | ~$150 |
| 50 | ~$750 |

**Controls already in the code:** prompt-result caching, a token guard with truncation, and preflight cost logging per run.

---

## 5. Recommendation

**Now: DigitalOcean, single 8 GB droplet, worker concurrency 2 → ~$60/mo.**
- Runs our existing prod compose unchanged - no re-architecture.
- Predictable flat pricing; scales by simply adding droplets.
- Chosen over **Hetzner** (4× cheaper but a real signup-rejection risk from our region - not worth risking the launch to save ~$45/mo) and over **AWS** (2–3× cost with no benefit we need yet).

**Later (enterprise clients / data residency): add AWS.**
When a client contractually requires data residency or a named cloud, move the LLM calls to **AWS Bedrock** (Claude with residency) - the same company entity + card unlocks it. Keep the app on DO; only the LLM path needs to move.

**Do not use** Oracle Always-Free for client production (reclaim risk), or Render/Railway (already blocked us, costlier at scale).

---

## 6. Decisions needed
1. **Confirm DigitalOcean** as the target (vs. taking the Hetzner cost saving and its signup risk).
2. **Confirm the ~$60/mo Phase-1 spend** is approved.
3. **Card/entity timing** - this is the actual blocker; everything above is ready to execute the day it lands.
4. **Agree the worker `--concurrency` change** (12 → 2) before first deploy - it's the difference between a $48 and a $200 box.

---

*Sources: `docker-compose.yml` / `.prod.yml` (service topology), `pipeline/Dockerfile` (worker concurrency, ARM support), `docs/project/production_readiness_audit.md` (RAM/concurrency guidance), measured run costs from the July 2026 real runs. Prices are list prices as understood at time of writing - **confirm before purchase**.*
