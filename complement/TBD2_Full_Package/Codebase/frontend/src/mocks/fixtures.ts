// ── Mock data fixtures ───────────────────────────────────────────────────────

export const mockUser = {
  id: 1, email: 'admin@tbd2.io', full_name: 'Alex Morgan',
  role: 'admin', org_id: 1, org_name: 'Apex Enterprise Corp',
  // Module access so the module-gated sidebar items render in mock mode
  // (hasModule() returns false for a non-super-admin without this key).
  module_access: ['esgrc', 'apex'],
}

export const mockTokens = {
  access_token:  'mock-access-token-abc123',
  refresh_token: 'mock-refresh-token-xyz789',
  token_type:    'bearer',
}

export const mockESGDashboard = {
  org_score: 74.2,
  pillar_scores: {
    environmental: 81.5,
    social:        68.3,
    governance:    72.8,
  },
  categories: [
    { id:1, name:'Carbon Emissions', pillar:'environmental', metric_code:'ESU10102', score:85, period:'2026-Q1', trend:+3.2 },
    { id:2, name:'Energy Consumption', pillar:'environmental', metric_code:'ESU10103', score:78, period:'2026-Q1', trend:-1.1 },
    { id:3, name:'Water Usage', pillar:'environmental', metric_code:'ESU10201', score:72, period:'2026-Q1', trend:+0.5 },
    { id:4, name:'Employee Wellbeing', pillar:'social', metric_code:'ESU20101', score:65, period:'2026-Q1', trend:+2.0 },
    { id:5, name:'Diversity & Inclusion', pillar:'social', metric_code:'ESU20201', score:71, period:'2026-Q1', trend:+4.1 },
    { id:6, name:'Board Composition', pillar:'governance', metric_code:'ESU30101', score:80, period:'2026-Q1', trend:+1.5 },
    { id:7, name:'Anti-Corruption', pillar:'governance', metric_code:'ESU30201', score:88, period:'2026-Q1', trend:+0.0 },
    { id:8, name:'Supply Chain Ethics', pillar:'governance', metric_code:'ESU30301', score:61, period:'2026-Q1', trend:-2.3 },
  ],
  total_metrics: 8,
  last_updated: '2026-06-29T10:00:00Z',
}

export const mockRisks = [
  { id:1, title:'Regulatory Non-Compliance', category:'governance', likelihood:4, impact:5, risk_score:20, level:'critical', status:'open',        owner:'Legal Team',  due_date:'2026-07-15', description:'TCFD reporting deadline approaching.' },
  { id:2, title:'Supply Chain Disruption',   category:'operational', likelihood:3, impact:4, risk_score:12, level:'high',     status:'in_progress',  owner:'Operations',  due_date:'2026-08-01', description:'Single-source dependency on key supplier.' },
  { id:3, title:'Data Breach',               category:'cyber',       likelihood:2, impact:5, risk_score:10, level:'high',     status:'open',         owner:'IT Security', due_date:'2026-07-30', description:'Outdated encryption on legacy systems.' },
  { id:4, title:'Carbon Target Miss',        category:'environmental',likelihood:3, impact:3, risk_score:9,  level:'medium',   status:'in_progress',  owner:'ESG Team',    due_date:'2026-09-01', description:'Scope 2 emissions trending above target.' },
  { id:5, title:'Talent Attrition',          category:'hr',          likelihood:2, impact:3, risk_score:6,  level:'medium',   status:'mitigated',    owner:'HR',          due_date:'2026-12-31', description:'Retention programs implemented Q1.' },
]

export const mockHeatmap = Array.from({ length: 5 }, (_, li) =>
  Array.from({ length: 5 }, (_, ii) => ({
    likelihood: li + 1,
    impact:     ii + 1,
    count:      Math.floor(Math.random() * 3),
  }))
).flat()

export const mockFrameworks = [
  {
    id:1, name:'GRI Standards', version:'2021', description:'Global Reporting Initiative',
    requirements_count: 24, compliant:14, partial:6, non_compliant:2, not_assessed:2,
    requirements: [
      { id:1, code:'GRI 2-1', title:'Organizational Details', status:'compliant', evidence:'Annual report 2025', review_date:'2026-09-30' },
      { id:2, code:'GRI 2-2', title:'Entities Included', status:'compliant', evidence:'Subsidiary list', review_date:'2026-09-30' },
      { id:3, code:'GRI 3-1', title:'Process for Material Topics', status:'partial', evidence:'Draft materiality matrix', review_date:'2026-08-15' },
      { id:4, code:'GRI 305-1', title:'Direct GHG Emissions', status:'non_compliant', evidence:null, review_date:'2026-07-15' },
    ],
  },
  {
    id:2, name:'ISO 14001:2015', version:'2015', description:'Environmental Management Systems',
    requirements_count: 10, compliant:7, partial:2, non_compliant:0, not_assessed:1,
    requirements: [
      { id:5, code:'4.1', title:'Understanding the Organization', status:'compliant', evidence:'Context document', review_date:'2026-12-01' },
      { id:6, code:'6.1', title:'Actions to Address Risks', status:'partial', evidence:'Risk register partial', review_date:'2026-08-01' },
    ],
  },
]

interface MockPipelineConfig {
  steps: number
  required_input_files: string[]
  reference_files?: string[]
  user_input_files?: string[]
}

export const mockPipelines: Array<{
  id: string; org_id: number; name: string; pipeline_type: string
  schedule_cron: string | null; is_active: boolean
  config_json: MockPipelineConfig
  created_at: string; updated_at: string
}> = [
  {
    id:'pipe-esgrc-001', org_id:1, name:'ESGRC Module Pipeline',
    pipeline_type:'ESGRC_MODULE', schedule_cron:null, is_active:true,
    config_json:{ steps:7, required_input_files:['input_metric_values_esgrc.csv','esgrc_performance_json_file.json'] },
    created_at:'2026-06-01T00:00:00Z', updated_at:'2026-06-29T00:00:00Z',
  },
  {
    id:'pipe-apex-001', org_id:1, name:'Apex Enterprise Pipeline',
    pipeline_type:'APEX_ENTERPRISE', schedule_cron:'0 2 * * 1', is_active:true,
    config_json:{ steps:8, required_input_files:['brand.csv','shared.csv','esgrc.csv','enterprise.csv','customer.csv','service.csv','product.csv','mkts.csv','bspt.csv','integration.csv','ictm.csv','resource.csv','module_mapping.csv','module_matrix.csv'], reference_files:['module_mapping.csv','module_matrix.csv'] },
    created_at:'2026-06-01T00:00:00Z', updated_at:'2026-06-29T00:00:00Z',
  },
]

// Mirrors pipeline/tasks/r2.py's APEX_MODULE_NAMES order - the 12 modules that
// feed the Apex roll-up (Apex itself is the consumer, never appears here).
export const mockHandoffProvenance: Array<{
  module: string; present: boolean; produced_at: string | null; source_run_id: string | null
}> = [
  { module:'brand',       present:true,  produced_at:'2026-09-08T16:13:32Z', source_run_id:'914a2b17-3d5e-4c11-9a2f-6b0e8d1c7f42' },
  { module:'shared',      present:true,  produced_at:'2026-09-08T16:13:32Z', source_run_id:'4f1c8834-8e2a-4f9b-b1d6-2c7a9e0f5b31' },
  { module:'esgrc',       present:true,  produced_at:'2026-09-08T16:13:32Z', source_run_id:'74fd4313-1b01-45b9-bba5-b196a7281bbf' },
  { module:'enterprise',  present:false, produced_at:null,                   source_run_id:null },
  { module:'customer',    present:true,  produced_at:'2026-08-22T11:55:15Z', source_run_id:'a02de1c9-6f3b-4a87-9d0e-1f4c2b8a7e56' },
  { module:'service',     present:false, produced_at:null,                   source_run_id:null },
  { module:'product',     present:false, produced_at:null,                   source_run_id:null },
  { module:'mkts',        present:false, produced_at:null,                   source_run_id:null },
  { module:'bspt',        present:true,  produced_at:'2026-08-20T09:30:00Z', source_run_id:'c3b7108a-2e4d-4f6c-8b1a-9d5e0c3f7a24' },
  { module:'ictm',        present:false, produced_at:null,                   source_run_id:null },
  { module:'resource',    present:false, produced_at:null,                   source_run_id:null },
  { module:'integration', present:true,  produced_at:'2026-08-22T11:55:15Z', source_run_id:'0ed53221-989b-4b0d-11fa-ca957a39308e' },
]

const ESGRC_STEP_NAMES = [
  'Data Preparation I',
  'Data Preparation II',
  'Correlation CHAID FT Analysis',
  'SPC & RPN Analysis',
  'Regression ESGRC',
  'Combine Reports',
  'Claude AI - Module Unified',
]

const APEX_STEP_NAMES = [
  'All Module Low Perf',
  'Correlation CHAID L0',
  'SPC RPN L0',
  'Regression L0',
  'Combine General Reports',
  'Claude AI - General Risk',
  'Combine Statistical Reports',
  'Claude AI - SPC RPN',
]

function makeSteps(count: number, names: string[], statusMap: Record<number,string> = {}) {
  return Array.from({ length: count }, (_, i) => ({
    id:                `step-${i+1}`,
    run_id:            'run-completed-001',
    step_number:       i + 1,
    step_name:         names[i],
    status:            statusMap[i+1] ?? 'COMPLETED',
    input_files_json:  [`org/1/runs/run-completed-001/inputs/input_${i}.csv`],
    output_files_json: [`org/1/runs/run-completed-001/step_${i+1}/output.txt`],
    celery_task_id:    `task-${i+1}-abc`,
    started_at:        new Date(Date.now() - (count - i) * 120_000).toISOString(),
    completed_at:      new Date(Date.now() - (count - i - 1) * 120_000).toISOString(),
    duration_ms:       115_000 + i * 5_000,
    error_detail:      statusMap[i+1] === 'FAILED' ? 'ScriptExecutionError: non-zero exit code 1' : null,
  }))
}

export const mockRuns = {
  esgrc: [
    {
      id:'run-completed-001', pipeline_id:'pipe-esgrc-001', org_id:1,
      triggered_by:1, status:'COMPLETED', is_current:true, progress_pct:100,
      confidence_score:0.81, started_at:'2026-06-29T08:00:00Z',
      completed_at:'2026-06-29T09:24:00Z', error_message:null,
      celery_chord_id:'chord-abc-001',
      step_results: makeSteps(7, ESGRC_STEP_NAMES),
      llm_outputs: [{
        id:'llm-001', run_id:'run-completed-001', step_result_id:'step-7',
        analysis_type:'MODULE_UNIFIED', model_used:'claude-haiku-4-5',
        input_tokens:45_230, output_tokens:1_850,
        response_text:'## ESGRC Module Risk Assessment\n\n**Priority Findings:**\n\n1. **Carbon emissions (ESU10102)** show a statistically significant upward trend over Q3-Q4 2025. SPC analysis flags a process shift at week 42. Recommend immediate root-cause investigation.\n\n2. **Supply chain ethics score (ESU30301)** declined 2.3 points - the CHAID analysis identifies the supplier onboarding subprocess as the primary driver.\n\n3. **Data quality:** 3 of 8 metrics have missing Q1 2026 values. Scoring accuracy is reduced. Prioritise data collection for ESU20101, ESU20201.\n\n**Confidence:** 81% (completeness 88%, stability 79%, benchmark proximity 76%)',
        output_file_r2_path:'org/1/runs/run-completed-001/step_7/esgrc_unified_recommendation.txt',
        created_at:'2026-06-29T09:22:00Z',
      }],
    },
    {
      id:'run-failed-002', pipeline_id:'pipe-esgrc-001', org_id:1,
      triggered_by:1, status:'FAILED', is_current:false, progress_pct:43,
      confidence_score:null, started_at:'2026-06-28T14:00:00Z',
      completed_at:'2026-06-28T14:52:00Z',
      error_message:'ScriptExecutionError: regression_esgrc returned exit code 1',
      celery_chord_id:'chord-abc-002',
      step_results: makeSteps(7, ESGRC_STEP_NAMES, { 5:'FAILED', 6:'SKIPPED', 7:'SKIPPED' }),
      llm_outputs: [],
    },
    {
      id:'run-pending-003', pipeline_id:'pipe-esgrc-001', org_id:1,
      triggered_by:1, status:'PENDING', is_current:false, progress_pct:0,
      confidence_score:null, started_at:null, completed_at:null,
      error_message:null, celery_chord_id:null,
      step_results:[], llm_outputs:[],
    },
  ],
  apex: [
    {
      id:'run-apex-001', pipeline_id:'pipe-apex-001', org_id:1,
      triggered_by:1, status:'COMPLETED', is_current:true, progress_pct:100,
      confidence_score:0.76, started_at:'2026-06-28T02:00:00Z',
      completed_at:'2026-06-28T05:18:00Z', error_message:null,
      celery_chord_id:'chord-apex-001',
      step_results: makeSteps(8, APEX_STEP_NAMES),
      llm_outputs: [
        {
          id:'llm-apex-001', run_id:'run-apex-001', step_result_id:'step-6',
          analysis_type:'GENERAL_RISK', model_used:'claude-sonnet-5',
          input_tokens:182_000, output_tokens:4_200,
          response_text:'## Apex Enterprise General Risk Assessment\n\nPortfolio-level analysis across 12 modules reveals three high-priority risk clusters:\n\n**Cluster 1 - Integration Module:** Elevated RPN (score 187) driven by process failures in the ICTM sub-module. CHAID segmentation shows this is correlated with data latency > 48h.\n\n**Cluster 2 - Market Exposure:** MKTS and BSPT modules show co-movement with external commodity indices. Recommend hedging review.\n\n**Cluster 3 - Resource Constraints:** RESOURCE module scoring has declined 8 points QoQ - regression analysis identifies headcount as the primary predictor.',
          output_file_r2_path:'org/1/runs/run-apex-001/step_6/apex_general_risk.txt',
          created_at:'2026-06-28T05:10:00Z',
        },
        {
          id:'llm-apex-002', run_id:'run-apex-001', step_result_id:'step-8',
          analysis_type:'SPC_RPN', model_used:'claude-sonnet-5',
          input_tokens:95_000, output_tokens:2_800,
          response_text:'## Apex SPC & RPN Analysis\n\n**Out-of-Control Processes (UCL exceeded):**\n\n- Integration module: Process shift detected at observation 34 (Western Electric Rule 1)\n- ICTM sub-process: 6 consecutive points above CL (Rule 2)\n\n**Top RPN Rankings:**\n1. Integration failure mode: RPN 245 (Severity 9, Occurrence 5, Detection 5)\n2. Data quality defect: RPN 192\n3. Reporting delay: RPN 144',
          output_file_r2_path:'org/1/runs/run-apex-001/step_8/apex_spc_rpn.txt',
          created_at:'2026-06-28T05:15:00Z',
        },
      ],
    },
  ],
}

export const mockAgentStatus = {
  last_run_at:      '2026-06-29T06:00:00Z',
  next_run_at:      '2026-06-30T06:00:00Z',
  last_run_status:  'success',
  metrics_scored:   8,
  requirements_flagged: 2,
  risks_escalated:  1,
}

export const mockUsers = [
  { id:1, email:'admin@tbd2.io',    full_name:'Alex Morgan',   role:'admin',   is_active:true,  created_at:'2026-01-01T00:00:00Z' },
  { id:2, email:'analyst@tbd2.io',  full_name:'Jordan Liu',    role:'analyst', is_active:true,  created_at:'2026-02-01T00:00:00Z' },
  { id:3, email:'viewer@tbd2.io',   full_name:'Sam Rivera',    role:'viewer',  is_active:true,  created_at:'2026-03-01T00:00:00Z' },
  { id:4, email:'inactive@tbd2.io', full_name:'Pat Williams',  role:'analyst', is_active:false, created_at:'2026-01-15T00:00:00Z' },
]

export const mockPrompts = [
  {
    id:1, name:'ESGRC_MODULE_UNIFIED', version:2, is_active:true,
    content:'You are an expert ESG risk analyst. Analyse the following consolidated ESGRC module report and provide actionable recommendations...',
    created_at:'2026-06-20T00:00:00Z',
  },
  {
    id:2, name:'APEX_GENERAL_RISK', version:1, is_active:true,
    content:'You are an enterprise risk intelligence specialist. Review the Apex enterprise-level consolidated report across all 12 modules...',
    created_at:'2026-06-01T00:00:00Z',
  },
  {
    id:3, name:'APEX_SPC_RPN', version:1, is_active:true,
    content:'You are a statistical process control expert. Analyse the following SPC and RPN consolidated report...',
    created_at:'2026-06-01T00:00:00Z',
  },
]
