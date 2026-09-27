# TBD2 - Demo & Deployment Runbook

## Pre-Demo Checklist

### 1. Seed demo data
```bash
# Against the running compose stack (see docs/deployment/DEMO_DEPLOY.md for the current
# Cloudflare-tunnel deploy path - Railway was abandoned, it requires a paid plan)
docker compose exec esgrc_api python pipeline/scripts/seed_demo.py
# Expected: completes in <30 seconds, prints ✅ Demo seed complete
```

### 2. Configure R2 lifecycle rules (one-time)
```bash
python pipeline/scripts/configure_r2_lifecycle.py
# Sets: IA after 30 days, auto-delete after 365 days
# Canadian pilot client satisfies 1-year audit retention requirement
```

### 3. Verify all tests green
```bash
# ESGRC backend
cd ESGRC && pytest tests/ -q

# Pipeline
pytest pipeline/tests/ -q
```
Expected: all tests pass, none failing (a skip or two is fine). Test counts move most days and
are deliberately not hardcoded here - see the README status line for the last-verified total.

### 4. Apply main.py patch
The original patch reference is retained at `docs/reference/implementation_history/MAIN_PY_PATCH.py`.

### 5. Verify security headers
```bash
curl -I https://your-tunnel-subdomain.trycloudflare.com/health
# Must include: Content-Security-Policy, X-Frame-Options, X-Content-Type-Options
```

### 6. Verify rate limiting
```bash
for i in $(seq 1 65); do curl -s -o /dev/null -w "%{http_code}\n" https://your-tunnel-subdomain.trycloudflare.com/pipelines; done
# First 60: 200, request 61+: 429
```

---

## Panel Q&A - Prepared Answers (Section 12.3)

**"How is the data secured?"**
- All data scoped to `org_id` - cross-org access returns 404, not 403
- R2 files are never publicly accessible - presigned URLs only, expire in 1 hour
- API key server-side only - never in any frontend file or browser request
- Access tokens in memory only (Zustand), refresh tokens in httpOnly cookies
- bcrypt cost 12 for passwords, JWT rotation on every refresh use

**"What about data retention and privacy (PIPEDA)?"**
- R2 files: auto-delete after 365 days via lifecycle rule (covers 1-year audit requirement)
- PostgreSQL recommendation text: retained 7 years (regulatory standard for risk records)
- GDPR/PIPEDA right-to-erasure: `DELETE /pipelines/runs/{run_id}/files` endpoint
  deletes all R2 files and nulls `response_text` in DB for a specific run
- ZDR (Zero Data Retention) agreement: in progress with Anthropic - email sent to sales

**"Can the AI hallucinate?"**
- Claude reads your actual pipeline data - it does not recall from training
- Every recommendation is traceable to the input files via `pipeline_step_results.input_files_json`
- Langfuse traces every Claude call with input/output tokens and model used
- Confidence score (0–1) reflects data completeness and stability - low confidence flags low-quality inputs

**"What does it cost per client?"**
- Claude Haiku 4.5 (ESGRC): ~$0.027/run at 12K input + 3K output tokens
- Claude Sonnet 4.6 (Apex): ~$0.054/run at 24K input + 5K output tokens
- 3 runs/day × 30 days = ~$9/month LLM for ESGRC, ~$5/month for Apex = **~$14/month total**
- Drops to ~$7/month with Anthropic Batch API (50% discount) for scheduled overnight runs
- R2 storage: ~$0.015/GB/month - negligible at current file sizes

**"Why not Fable 5 / the newest model?"**
- Haiku 4.5 and Sonnet 4.6 are the right cost/capability tier for structured analytics summarisation
- Fable 5 at $10/$50/MTok would be ~10x more expensive for identical output quality at module level
- Our model selection is locked in the ADR - we can upgrade in one env var change if needed

**"How does it scale to 12 modules?"**
- Apex Steps 2, 3, 4 run as a Celery chord (parallel group) - all 3 execute simultaneously
- Add Celery workers via `docker compose scale celery_worker=N`
- Redis keys namespaced by `run_id` - concurrent runs for the same org never collide
- Tested: concurrent ESGRC + Apex runs in `test_extreme_scenarios.py` (Scenario 7)

**"SOC 2 readiness?"**
- Architecture supports it: RLS via `org_id` on every table, append-only audit log
- JWT with rotation, no raw traces in Langfuse (first 500 chars only), Sentry for error tracking
- CSP headers, X-Frame-Options, HSTS in Nginx - verified in production config
- Not certified yet - that's a Sprint 5 workstream after the pilot

**"What if Claude is down?"**
- 3-retry exponential backoff with jitter on every Claude call
- Handles: RateLimitError, APITimeoutError, APIConnectionError, 529 Overloaded
- If all 3 retries fail: step marked FAILED, pipeline marked FAILED, SSE emits error event
- User can re-run the failed step via POST `/pipelines/runs/{run_id}/steps/{n}/rerun`

---

## 10-Step Video Recording Flow

1. Login as `admin@demo.com` → show dashboard: scores, pillars, category breakdown
2. Navigate to Risk → heatmap with 3 critical-zone risks highlighted, filter to open
3. Navigate to Compliance → GRI donut chart, expand framework, show bulk status update
4. Navigate to Pipeline → select ESGRC Module Pipeline
5. Click Trigger → watch all 7 steps execute live (DEMO_MODE=true for speed)
6. Expand Step 7 Claude card → show recommendation text inline, download button
7. Navigate to Reports → confidence score 0.74, download second recommendation
8. Open Co-Pilot → ask "What are the top 3 risks for this period?" → show streaming
9. Navigate to Settings → Prompts (SUPER_ADMIN) → show version history
10. Trigger Apex → show 8-step flow, Steps 2/3/4 running in parallel

**Demo credentials:** admin@demo.com / Demo1234!

---

## D5 - R2 Retention Policy (Locked Decision)

Per ADR decision D5:
- **R2 files:** Infrequent Access after 30 days → auto-delete after 365 days
- **PostgreSQL `response_text`:** Retained 7 years (recommendation text = risk record)
- **GDPR/PIPEDA erasure:** `DELETE /pipelines/runs/{run_id}/files` nulls response_text + deletes R2

Script: `python pipeline/scripts/configure_r2_lifecycle.py`
Manual fallback: Cloudflare Dashboard → R2 → {bucket} → Settings → Object Lifecycle Rules

---

## Post-Demo Actions (Danish)

- [ ] DOD-15: Email Anthropic sales for ZDR agreement before client pilot
- [ ] DOD-16: Canadian privacy counsel to review data processing flows
- [ ] DOD-12: Record 10-step video (all three developers present)
- [ ] SEC-13: Confirm ZDR agreement received before client data enters the system
