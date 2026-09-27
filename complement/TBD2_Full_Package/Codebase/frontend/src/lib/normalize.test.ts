import { describe, it, expect } from 'vitest'
import { pillarBucket, normalizeDashboard, normalizeList } from './normalize'

describe('pillarBucket', () => {
  it('maps by first letter, case/whitespace-insensitive', () => {
    expect(pillarBucket('Environmental')).toBe('environmental')
    expect(pillarBucket('  social ')).toBe('social')
    expect(pillarBucket('E')).toBe('environmental')
    expect(pillarBucket('S')).toBe('social')
    expect(pillarBucket('Governance')).toBe('governance')
  })
  it('defaults unknown / empty to governance', () => {
    expect(pillarBucket('')).toBe('governance')
    expect(pillarBucket(undefined as any)).toBe('governance')
    expect(pillarBucket('xyz')).toBe('governance')
  })
})

describe('normalizeDashboard', () => {
  it('normalizes the real /esg/dashboard shape', () => {
    const raw = {
      overall_avg_score: 62,
      generated_at: '2026-07-07T00:00:00Z',
      categories: [
        { category_id: 1, category_name: 'Carbon', pillar: 'Environmental', latest_score: 80, latest_period: '2026Q1' },
        { category_id: 2, category_name: 'Labor',  pillar: 'Social',        latest_score: 40 },
      ],
    }
    const out = normalizeDashboard(raw)
    expect(out.org_score).toBe(62)
    expect(out.categories).toHaveLength(2)
    expect(out.categories[0]).toMatchObject({ id: 1, name: 'Carbon', pillar: 'environmental', score: 80, period: '2026Q1' })
    expect(out.pillar_scores.environmental).toBe(80)
    expect(out.pillar_scores.social).toBe(40)
    expect(out.pillar_scores.governance).toBe(0) // no governance categories -> avg([]) = 0
    expect(out.last_updated).toBe('2026-07-07T00:00:00Z')
  })

  it('also accepts the legacy mock shape', () => {
    const raw = {
      org_score: 71,
      pillar_scores: { environmental: 70, social: 72, governance: 71 },
      last_updated: '2026-01-01',
      categories: [{ id: 9, name: 'Ethics', pillar: 'governance', score: 71, trend: 2, period: '2026Q1' }],
    }
    const out = normalizeDashboard(raw)
    expect(out.org_score).toBe(71)
    expect(out.pillar_scores.social).toBe(72)
    expect(out.categories[0]).toMatchObject({ id: 9, name: 'Ethics', pillar: 'governance', score: 71, trend: 2 })
  })

  it('does not throw on an empty or partial payload (the real-API crash regression)', () => {
    expect(() => normalizeDashboard({})).not.toThrow()
    expect(() => normalizeDashboard(null)).not.toThrow()
    expect(() => normalizeDashboard(undefined)).not.toThrow()
    const out = normalizeDashboard({})
    expect(out.categories).toEqual([])
    expect(out.org_score).toBe(0)
    expect(out.pillar_scores).toEqual({ environmental: 0, social: 0, governance: 0 })
    expect(out.last_updated).toBeNull()
  })

  it('computes org_score from category average when no top-level score is present', () => {
    const out = normalizeDashboard({
      categories: [
        { category_name: 'A', pillar: 'e', latest_score: 100 },
        { category_name: 'B', pillar: 's', latest_score: 50 },
      ],
    })
    expect(out.org_score).toBe(75)
  })
})

describe('normalizeList', () => {
  it('returns a bare array unchanged (real API)', () => {
    expect(normalizeList([{ id: 1 }, { id: 2 }])).toEqual([{ id: 1 }, { id: 2 }])
  })
  it('unwraps { items: [...] } (mock shape)', () => {
    expect(normalizeList({ items: [{ id: 1 }] })).toEqual([{ id: 1 }])
  })
  it('returns [] for null / undefined / unexpected shapes (never throws)', () => {
    expect(normalizeList(null)).toEqual([])
    expect(normalizeList(undefined)).toEqual([])
    expect(normalizeList({})).toEqual([])
    expect(normalizeList({ foo: 'bar' })).toEqual([])
  })
})
