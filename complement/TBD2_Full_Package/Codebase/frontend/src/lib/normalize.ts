// ── API response normalizers ────────────────────────────────────────────────
// The frontend was originally built against MSW mock shapes; the real backend
// returns different shapes. These helpers normalize both into what the pages
// render, and are unit-tested in src/lib/normalize.test.ts.

export type Pillar = 'environmental' | 'social' | 'governance'

/** Map a free-form pillar string ("Environmental", "E", "social", …) to a bucket. */
export function pillarBucket(p: string): Pillar {
  const c = (p || '').trim().toLowerCase().charAt(0)
  if (c === 'e') return 'environmental'
  if (c === 's') return 'social'
  return 'governance'
}

export interface NormalizedCategory {
  id: number | string | undefined
  name: string
  pillar: Pillar
  metric_code: string
  score: number
  trend: number
  period: string
}

export interface NormalizedDashboard {
  org_score: number
  pillar_scores: Record<Pillar, number>
  categories: NormalizedCategory[]
  last_updated: string | null
}

const avg = (a: number[]) => (a.length ? a.reduce((s, n) => s + n, 0) / a.length : 0)

// The real /esg/dashboard returns { categories:[{category_name, pillar,
// latest_score, ...}], overall_avg_score, generated_at } - not the mock's
// { org_score, pillar_scores, categories:[{name, score, trend}] } shape.
// Normalise both into the shape the dashboard page renders. Tolerates missing
// fields (an empty or partial payload must not throw).
export function normalizeDashboard(raw: any): NormalizedDashboard {
  raw = raw ?? {}
  const cats: NormalizedCategory[] = (raw.categories ?? []).map((c: any) => ({
    id:          c.category_id ?? c.id,
    name:        c.category_name ?? c.name ?? '',
    pillar:      pillarBucket(c.pillar),
    metric_code: c.metric_code ?? '',
    score:       Number(c.latest_score ?? c.score ?? 0),
    trend:       Number(c.trend ?? 0),
    period:      c.latest_period ?? c.period ?? '',
  }))
  const buckets: Record<Pillar, number[]> = { environmental: [], social: [], governance: [] }
  cats.forEach((c) => buckets[c.pillar].push(c.score))
  return {
    org_score: Number(raw.org_score ?? raw.overall_avg_score ?? avg(cats.map((c) => c.score))),
    pillar_scores: raw.pillar_scores ?? {
      environmental: avg(buckets.environmental),
      social:        avg(buckets.social),
      governance:    avg(buckets.governance),
    },
    categories: cats,
    last_updated: raw.last_updated ?? raw.generated_at ?? null,
  }
}

// The real /risks returns a bare array; the mock returned { items: [...] }.
// Accept either and always return an array (never throw on a missing shape).
export function normalizeList<T = any>(raw: any): T[] {
  if (Array.isArray(raw)) return raw
  if (raw && Array.isArray(raw.items)) return raw.items
  return []
}
