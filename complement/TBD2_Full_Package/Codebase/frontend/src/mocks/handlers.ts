import { http, HttpResponse, delay } from 'msw'
import {
  mockUser, mockTokens, mockESGDashboard, mockRisks,
  mockFrameworks, mockPipelines, mockRuns, mockAgentStatus,
  mockUsers, mockPrompts, mockHandoffProvenance,
} from './fixtures'

const D = 300  // simulated network delay ms

export const handlers = [

  // ── Auth ──────────────────────────────────────────────────────────────────

  http.post('/api/auth/login', async ({ request }) => {
    await delay(D)
    const body = await request.json() as any
    if (body.password === 'wrong') return HttpResponse.json({ detail:'Invalid credentials' }, { status:401 })
    return HttpResponse.json({ ...mockTokens, user: mockUser })
  }),

  http.post('/api/auth/register', async () => {
    await delay(D)
    return HttpResponse.json({ ...mockTokens, user: mockUser }, { status:201 })
  }),

  http.post('/api/auth/refresh', async () => {
    await delay(100)
    return HttpResponse.json(mockTokens)
  }),

  http.post('/api/auth/logout', async () => {
    await delay(100)
    return HttpResponse.json({ message: 'Logged out' })
  }),

  http.get('/api/auth/me', async () => {
    await delay(D)
    return HttpResponse.json(mockUser)
  }),

  http.get('/api/auth/users', async () => {
    await delay(D)
    return HttpResponse.json({ items: mockUsers, total: mockUsers.length })
  }),

  http.patch('/api/auth/users/:id/role', async ({ request }) => {
    await delay(D)
    const body = await request.json() as any
    return HttpResponse.json({ ...mockUsers[0], role: body.role })
  }),

  // ── ESG ──────────────────────────────────────────────────────────────────

  http.get('/api/esg/dashboard', async () => {
    await delay(D)
    return HttpResponse.json(mockESGDashboard)
  }),

  // ── Risk ─────────────────────────────────────────────────────────────────

  http.get('/api/risks', async () => {
    await delay(D)
    return HttpResponse.json({ items: mockRisks, total: mockRisks.length })
  }),

  http.post('/api/risks', async ({ request }) => {
    await delay(D)
    const body = await request.json() as any
    return HttpResponse.json({ id: Date.now(), ...body, risk_score: body.likelihood * body.impact }, { status:201 })
  }),

  // PATCH, matching the real API. This answered PUT, which meant editing a risk
  // worked in dev and 405'd against the backend. A mock that agrees with the
  // caller instead of the server hides the bug it should expose.
  http.patch('/api/risks/:id', async ({ request }) => {
    await delay(D)
    const body = await request.json() as any
    return HttpResponse.json({ ...mockRisks[0], ...body })
  }),

  // ── Compliance ───────────────────────────────────────────────────────────

  http.get('/api/compliance/frameworks', async () => {
    await delay(D)
    return HttpResponse.json(mockFrameworks)
  }),

  http.get('/api/compliance/requirements', async () => {
    await delay(D)
    const all = mockFrameworks.flatMap((f) => f.requirements)
    return HttpResponse.json({ items: all, total: all.length })
  }),

  http.patch('/api/compliance/requirements/bulk', async () => {
    await delay(D)
    return HttpResponse.json({ updated: 3 })
  }),

  http.patch('/api/compliance/requirements/:id', async ({ request }) => {
    await delay(D)
    const body = await request.json() as any
    return HttpResponse.json({ id: 1, ...body })
  }),

  http.get('/api/compliance/summary', async () => {
    await delay(D)
    return HttpResponse.json(mockFrameworks)
  }),

  // ── Pipeline ─────────────────────────────────────────────────────────────

  http.post('/api/pipelines/:id/upload-input', async ({ request }) => {
    await delay(D)
    const url = new URL(request.url)
    const filename = url.searchParams.get('filename') ?? 'uploaded_file.csv'
    return HttpResponse.json({
      filename,
      size_bytes: 1024,
      r2_key: `org/1/reference/${filename}`,
      last_modified: null,
    })
  }),

  http.get('/api/pipelines', async () => {
    await delay(D)
    return HttpResponse.json(mockPipelines)
  }),

  // MUST stay registered before '/api/pipelines/:id' below - same static-before-
  // catch-all ordering the real router enforces, or ':id' swallows this path.
  http.get('/api/pipelines/handoff-provenance', async () => {
    await delay(D)
    return HttpResponse.json(mockHandoffProvenance)
  }),

  http.get('/api/pipelines/:id', async ({ params }) => {
    await delay(D)
    const pipe = mockPipelines.find((p) => p.id === params.id)
    if (!pipe) return HttpResponse.json({ detail:'Not found' }, { status:404 })
    return HttpResponse.json(pipe)
  }),

  http.get('/api/pipelines/:id/runs', async ({ params }) => {
    await delay(D)
    const runs = params.id === 'pipe-apex-001' ? mockRuns.apex : mockRuns.esgrc
    return HttpResponse.json({ items: runs, total: runs.length, page:1, page_size:20 })
  }),

  http.get('/api/pipelines/runs/:runId', async ({ params }) => {
    await delay(D)
    const all = [...mockRuns.esgrc, ...mockRuns.apex]
    const run = all.find((r) => r.id === params.runId)
    if (!run) return HttpResponse.json({ detail:'Not found' }, { status:404 })
    return HttpResponse.json(run)
  }),

  http.post('/api/pipelines/:id/trigger', async ({ params }) => {
    await delay(D)
    const runId = `run-${Date.now()}`
    return HttpResponse.json({ run_id: runId, status:'PENDING', message:'Pipeline run queued.' }, { status:202 })
  }),

  http.post('/api/pipelines/emergency-stop', async () => {
    await delay(D)
    return HttpResponse.json({ run_id: 'run-001', message:'Run cancelled.' })
  }),

  http.post('/api/pipelines/runs/:runId/rollback', async () => {
    await delay(D)
    return HttpResponse.json({ previous_run_id:'run-001', current_run_id:'run-002', message:'Rollback successful.' })
  }),

  http.post('/api/pipelines/runs/:runId/steps/:n/rerun', async ({ params }) => {
    await delay(D)
    return HttpResponse.json({ run_id: params.runId, step_number: Number(params.n), step_result_id:`step-${Date.now()}`, status:'PENDING', message:'Step re-run queued.' })
  }),

  http.get('/api/pipelines/runs/:runId/recommendations', async ({ params }) => {
    await delay(D)
    const all = [...mockRuns.esgrc, ...mockRuns.apex]
    const run = all.find((r) => r.id === params.runId)
    return HttpResponse.json(run?.llm_outputs ?? [])
  }),

  http.get('/api/pipelines/llm-outputs/:id/download', async () => {
    await delay(D)
    return new HttpResponse('Mock recommendation text content.\n\nThis is a placeholder.', {
      headers: { 'Content-Type': 'text/plain', 'Content-Disposition': 'attachment; filename="recommendation.txt"' }
    })
  }),

  // Step output download (StepCard). Without this the call fell through MSW and
  // hit the network, so downloading a step file silently failed in dev.
  http.get('/api/pipelines/runs/:runId/steps/:stepNumber/files/:filename', async ({ params, request }) => {
    await delay(D)
    const asPdf = new URL(request.url).searchParams.get('as_pdf') === 'true'
    const name = String(params.filename)
    return new HttpResponse(`Mock contents of ${name} (step ${params.stepNumber}).`, {
      headers: {
        'Content-Type': asPdf ? 'application/pdf' : 'text/plain',
        'Content-Disposition': `attachment; filename="${asPdf ? name.replace(/\.(txt|md)$/i, '.pdf') : name}"`,
      },
    })
  }),

  http.get('/api/pipelines/:id/input-files', async ({ params }) => {
    await delay(D)
    const pipe = mockPipelines.find((p) => p.id === params.id)
    const required: string[] = pipe?.config_json?.required_input_files ?? []
    const reference: string[] = pipe?.config_json?.reference_files ?? []
    const userInput: string[] = pipe?.config_json?.user_input_files
      ?? required.filter((f) => !reference.includes(f))
    const uploaded = required.slice(0, 1)
    const missing = required.slice(1)
    return HttpResponse.json({
      pipeline_id: params.id,
      required_files: required,
      uploaded_files: uploaded.map((f: string) => ({
        filename: f, r2_key: `org/1/reference/${f}`, size_bytes: 102400, last_modified: '2026-06-28T00:00:00Z',
      })),
      missing_files: missing,
      all_present: missing.length === 0,
      user_input_files: userInput,
      user_files_present: userInput.every((f) => uploaded.includes(f)),
      missing_user_files: userInput.filter((f) => !uploaded.includes(f)),
      reference_files: reference,
      reference_files_present: reference.every((f) => uploaded.includes(f)),
      missing_reference_files: reference.filter((f) => !uploaded.includes(f)),
    })
  }),

  // Prompts
  http.get('/api/pipelines/prompts', async () => {
    await delay(D)
    return HttpResponse.json(mockPrompts)
  }),

  // NOTE: there is deliberately no GET /pipelines/prompts/:id handler. The API
  // serves only PUT on that path, and nothing in the app fetches a single
  // prompt by id. A handler here would be a mock for an endpoint that does not
  // exist, which is how the risks PUT/PATCH mismatch stayed hidden.

  http.put('/api/pipelines/prompts/:id', async ({ request }) => {
    await delay(D)
    const body = await request.json() as any
    return HttpResponse.json({ ...mockPrompts[0], version: 3, content: body.content })
  }),

  // SSE stream - simulated as immediate done (SSE doesn't work well in MSW)
  http.get('/api/pipelines/runs/:runId/stream', async () => {
    await delay(D)
    return new HttpResponse(null, { status: 204 })
  }),

  // ── Co-Pilot ─────────────────────────────────────────────────────────────

  http.post('/api/copilot/message', async () => {
    await delay(D)
    return HttpResponse.json({ run_id: `copilot-${Date.now()}`, status:'streaming' })
  }),

  http.get('/api/copilot/stream/:runId', async () => {
    await delay(D)
    return new HttpResponse(null, { status: 204 })
  }),

  // ── Agent ─────────────────────────────────────────────────────────────────

  http.get('/api/agent/status', async () => {
    await delay(D)
    return HttpResponse.json(mockAgentStatus)
  }),

  // ── Org ───────────────────────────────────────────────────────────────────

  http.get('/api/org/snapshot', async () => {
    await delay(D)
    return HttpResponse.json({ org_id:1, org_name:'Apex Enterprise Corp', snapshot: {} })
  }),
]
