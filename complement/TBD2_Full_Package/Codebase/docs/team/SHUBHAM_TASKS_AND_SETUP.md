# Shubham — Setup, Tasks & Deploy Guide
### TBD2 / Vigilant Lens · plain-English handoff

Hi Shubham — here's everything you need: how to run the app, how to deploy it, and your 4 frontend jobs. Take it step by step.

---

## Part 1 — Run the app on your machine (for your frontend work)

You only need **Node.js** for frontend work. The frontend can run on its own with sample data (no backend needed).

1. Install **Node.js 20+** (nodejs.org).
2. Unzip the project Danish sent.
3. Open a terminal in the project folder, then:
   ```
   cd frontend
   npm install
   npm run dev
   ```
4. Open the link it prints (usually **http://localhost:3000**).
5. Log in with **admin@demo.com** / **Demo1234!**

That's enough to start Jobs 1–4 below. (It uses built-in sample data, so you can see the screens immediately.)

---

## Part 2 — Deploy / run the WHOLE app (frontend + backend together)

For this you need **Docker Desktop** installed.

1. Install **Docker Desktop** (docker.com).
2. **Ask Danish for the `.env` file** — it has the secret keys. **Never put it in the zip or GitHub.** Place it in the project root folder.
3. In a terminal in the project root, run:
   ```
   docker compose -p tbd2 -f docker-compose.yml -f docker-compose.local.yml up -d
   ```
4. Wait ~1–2 minutes, then open:
   - App: **http://localhost:3000**
   - API check: **http://localhost:8080/docs**
5. Log in with **admin@demo.com** / **Demo1234!**
6. To stop it: `docker compose -p tbd2 down`

> **Simpler option (added 7 Aug 2026).** The base compose file now builds and serves the frontend too, so you no longer need the `-f docker-compose.local.yml` overlay just to see the UI:
> ```
> docker compose -f docker-compose.yml up -d --build
> ```
> App at **http://localhost/**, API at **http://localhost/api/\***. Before this, `docker compose up` started only the API and served no UI at all.

*(Cloud deployment: see `docs/deployment/DEMO_DEPLOY.md`. DigitalOcean is no longer the plan and it is not blocked on a card. For your work, this local Docker run IS the deploy.)*

---

## Part 3 — Your 4 jobs (frontend)

You own the **frontend** (the `frontend/` folder). Do these in order. Make a branch first:
```
git checkout -b frontend/labeling
```

### 🟢 Job 1 — Show real names instead of codes (most important)
The app currently shows technical codes like `ESU10102`. We want the **business name** (e.g. "Emissions Compliance Rate") instead. **The backend side is already done and merged** — you are not waiting on anything. Each output returns `response_text_labeled` (names substituted, display this), `labels` (for tooltips), and `labeling_status`. If `labeling_status` is not `"ok"`, fall back to `response_text` rather than failing the view. Full contract in `docs/team/SHUBHAM_FRONTEND_API.md`.
1. Open these files and find where codes appear:
   - `frontend/src/pages/ReportsPage.tsx`
   - `frontend/src/pages/DashboardPage.tsx` (the category table)
   - `frontend/src/pages/PipelinePage.tsx`
2. Wherever a code shows, show the **name** instead. Show the code only as a small grey label or a hover tooltip.
3. **Test:** open Reports → you should see names, not codes.

### 🟢 Job 2 — Show "which data, and when" (a small freshness badge)
Each report/dashboard should say when the data is from — like **"Data as of 12 Jul 2026 · Run #5"**. **The backend side is already done and merged.** Call `GET /pipelines/handoff-provenance`; it returns `{module, present, produced_at, source_run_id}` per module.
1. On the **Reports** page and **Dashboard**, add a small badge/text near the top.
2. Read the date + run number from the data and display it.
3. **Test:** the date shows correctly.

### 🟢 Job 3 — Make the pages work for any module (not just ESGRC)
Right now the pages are built mostly for ESGRC. Make them **read the module name from the data** so any module works.
1. Find where "ESGRC" or module names are **hard-coded** in the pages / sidebar.
2. Replace with the module value coming from the data.
3. **Test:** works for every pipeline that exists. Log in as `admin@demo.com`, which sees all of them.

> **Scope grew a lot on 6-22 Aug 2026.** This job was written when five pipelines existed. There are now **twelve module pipelines plus Apex**:
> `ESGRC_MODULE`, `CUSTOMER_MODULE`, `SHARED_MODULE`, `BSPT_MODULE`, `ENTERPRISE_MODULE`, `ICTM_MODULE`, `PRODUCT_MODULE`, `RESOURCE_MODULE`, `SERVICE_MODULE`, `BRAND_MODULE`, `MKTS_MODULE`, `INTEGRATION_MODULE`, and `APEX_ENTERPRISE`.
> Integration (the 12th) landed 2026-08-22 - all twelve module pipelines are now built.
>
> Every module pipeline has the identical 7-step shape; Apex is the 8-step enterprise roll-up. Only ESGRC has its own business-data tables and pages — every other module is pipeline-only and surfaces through the generic **Pipeline Monitor** and **Reports** pages, so those are where this job really matters. Display names differ from the enum: `BSPT_MODULE` is "Business Partner", `ICTM_MODULE` is "IT Processes", `MKTS_MODULE` is "Market and Sales".
>
> **Do not hard-code that list.** It grew from 5 to 12 in under three weeks. Read it from the data and you will not have to touch this again.

### 🟢 Job 4 — Process log screen
A single screen showing what has run recently across the whole organisation: who triggered it, when, which step, and how it ended.
1. Call `GET /pipelines/process-log` (org-scoped, needs auth).
2. Each row has `triggered_by_name`, `started_at`, `step_name`, `status`, plus duration.
3. Render as a table, **newest first** (the API already sorts that way): *When · Who · Step · Status · Duration*.
4. **Test:** trigger a pipeline run, then confirm it appears at the top with your name on it.

> This job existed in `docs/team/SHUBHAM_FRONTEND_API.md` from the start but was missing from this list, which said "your 3 jobs" until 7 Aug 2026. It is a real fourth job, not an extra.

---

## How we work together
- Commit small, push often, on your `frontend/labeling` branch.
- If the data is missing a field you need → **ask Danish** (he's building the backend side that feeds you).
- Login for all testing: **admin@demo.com** / **Demo1234!**
- Questions? Ping the group. Let's go 🚀
