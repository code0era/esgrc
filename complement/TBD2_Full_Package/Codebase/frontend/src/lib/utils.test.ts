import { describe, it, expect } from 'vitest'
import { compareConfidence } from './utils'

describe('compareConfidence', () => {
  it('picks the higher score as winner "a"', () => {
    const cmp = compareConfidence(0.9, 0.7)
    expect(cmp.winner).toBe('a')
    expect(cmp.deltaPct).toBeCloseTo(20, 10)
  })

  it('picks the higher score as winner "b"', () => {
    const cmp = compareConfidence(0.6, 0.8)
    expect(cmp.winner).toBe('b')
    expect(cmp.deltaPct).toBeCloseTo(20, 10)
  })

  it('reports a tie instead of arbitrarily picking a winner (the Reports page regression)', () => {
    // The Reports page comparison panel used a plain `>` ternary, so two runs
    // tied at the same confidence fell into the "else" branch and were shown
    // as "Run B has higher confidence (+0.0%)" - a false claim of superiority.
    expect(compareConfidence(0.75, 0.75)).toEqual({ winner: 'tie', deltaPct: 0 })
  })

  it('scales the delta from a 0-1 fraction to a 0-100 percentage', () => {
    expect(compareConfidence(0.55, 0.5).deltaPct).toBeCloseTo(5, 10)
  })
})
