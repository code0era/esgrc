"""
Risk score thresholds - single source of truth.

Risk score = likelihood × impact, each on a 1–5 scale, so the score ranges 1–25.

There are three DELIBERATE, escalating gates across the product. They are not
meant to be equal - each answers a different question, from widest net to most
conservative action:

  1. RISK_LLM_ASSESSMENT_SCORE (15) - the LLM agent *reviews* a risk (delegates
     to the specialist to decide if it warrants escalation). Widest net: we want
     a human-like second look well before anything is auto-actioned.
  2. RISK_CRITICAL_ZONE_MIN (4) - the heatmap's "critical zone" is the top-right
     block where likelihood AND impact are each >= 4 (i.e. score >= 16). This is
     a visual grouping, expressed per-axis rather than as a single product.
  3. RISK_ESCALATION_SCORE (20) - the rule-based batch *auto-escalates* an
     overdue OPEN risk to CRITICAL. Most conservative: an automated state change
     should only fire on the clearest cases.

Centralised here so the values are visible together and any future change is a
single, coordinated edit rather than three scattered magic numbers.
"""

# LLM agent delegates a risk to the specialist for assessment at/above this score.
RISK_LLM_ASSESSMENT_SCORE = 15

# Heatmap "critical zone": likelihood AND impact each >= this (score >= 16).
RISK_CRITICAL_ZONE_MIN = 4

# Rule-based batch auto-escalates an overdue OPEN risk to CRITICAL at/above this.
RISK_ESCALATION_SCORE = 20
