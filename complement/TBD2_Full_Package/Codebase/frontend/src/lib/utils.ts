// ── Utility: merge Tailwind class strings safely ────────────────────────────
import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

// ── Utility: compare two run confidence scores (Reports page comparison panel) ──
export interface ConfidenceComparison {
  winner:   'a' | 'b' | 'tie'
  deltaPct: number
}

/** Confidence scores are 0-1 fractions; deltaPct is returned already scaled to 0-100. */
export function compareConfidence(a: number, b: number): ConfidenceComparison {
  if (a === b) return { winner: 'tie', deltaPct: 0 }
  return a > b
    ? { winner: 'a', deltaPct: (a - b) * 100 }
    : { winner: 'b', deltaPct: (b - a) * 100 }
}
