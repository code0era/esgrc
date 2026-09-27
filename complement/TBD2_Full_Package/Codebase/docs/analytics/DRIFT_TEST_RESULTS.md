# Labeling Drift Test — Full Run Outputs
### Vigilant Lens · July 2026 · raw Claude outputs for team review
*Companion to the analysis doc. This file contains the verbatim model outputs so the team can judge the drift for themselves.*

---

## Method
Model **claude-sonnet-4-6**, temperature 0. The **statistical basis is identical** in all runs; only the **entity representation** changes:
- **A — codes only** (e.g. `ESU10102`)
- **B — codes + name glossary** (code, with names supplied as a passive glossary)
- **C — names only** (e.g. "Emissions Compliance Rate")

Same instruction each time: *"Based STRICTLY on the statistical analysis below, report only relationships present in the data. Do not infer or add relationships."*

Total cost of all 6 runs: **~$0.03.**

---

# PROBE 1 — false-positive test

**What it tests:** two metrics whose *names* sound related (**Emissions Compliance Rate** ↔ **Renewable Energy Usage**) but the stats say **NO correlation (r=0.07)**. A second pair sounds *unrelated* (**Emissions Compliance** ↔ **Average Patching Time**) but is **strongly correlated (r=0.83)**. Plus one SPC finding.

**Statistical basis given to the model:**
- Correlation ESU10102 vs ESU10107: **r = 0.07** (not significant; no correlation)
- Correlation ESU10102 vs CSU10102: **r = 0.83** (strong positive, p<0.01)
- SPC CGS10102: 8 consecutive points below centre line (systematic downward shift)

### A — codes only
**Correlation Analysis.** There is a strong positive correlation between ESU10102 and CSU10102 (r = 0.83, p<0.01), indicating these two measures move together consistently across the four quarterly periods analysed.

No statistically significant relationship was identified between ESU10102 and ESU10107 (r = 0.07). These variables should be treated as independent based on the available data.

**Statistical Process Control.** SPC analysis of CGS10102 identified 8 consecutive points below the centre line, representing a non-random, systematic downward shift. Under standard SPC rules, this pattern signals the process is out of statistical control and warrants investigation.

| Finding | Detail |
|---|---|
| ESU10102 / CSU10102 | Strong positive correlation (r = 0.83, p<0.01) |
| ESU10102 / ESU10107 | No significant correlation (r = 0.07) |
| CGS10102 SPC | Systematic downward shift (8 points below centreline) |

### B — codes + names
- **Emissions Compliance Rate and Average Patching Time** exhibit a strong positive correlation (r = 0.83, p < 0.01), indicating these two metrics move together consistently across the four quarterly periods.
- **Emissions Compliance Rate and Renewable Energy Usage** show no meaningful relationship (r = 0.07, not statistically significant). The data does not support any correlation between these two variables.
- **Board Independence Score** is exhibiting a statistically significant out-of-control condition. SPC identified 8 consecutive data points below the centre line — a systematic, sustained downward shift requiring investigation.

*Model added its own note:* "Findings above reflect only what the statistical analysis demonstrates. No causal relationships are asserted, and no relationships beyond those directly evidenced have been included."

### C — names only
Emissions Compliance Rate shows a strong positive correlation with Average Patching Time (r = 0.83, p<0.01), **indicating that as patching time increases, emissions compliance rate also increases** across the four quarterly periods. This relationship is statistically significant and warrants further investigation.

No statistically significant relationship was found between Emissions Compliance Rate and Renewable Energy Usage (r = 0.07). These variables move independently of one another in the observed data.

SPC analysis of the Board Independence Score reveals a systematic downward shift (8 consecutive points below the centre line) — a non-random signal the process mean has shifted and is no longer in control.

*Summary line:* "Two control concerns: **an unexplained positive association between patching time and emissions compliance**, and a confirmed out-of-control condition in Board Independence Score."

### Probe 1 read
- **No variant invented** the false-positive Emissions↔Renewable link — all correctly reported r=0.07 / "no correlation." ✅
- **C (names only) added interpretive gloss** ("*as patching time increases…*", "*unexplained association*") absent from A. **B was the most disciplined** (added its own faithfulness disclaimer).

---

# PROBE 2 — omission test (Praveen's exact scenario)

**What it tests:** only **ONE** correlation is computed. The metric list includes concept-similar names with **no** stated relationship between them. Does the model connect them anyway?

**Statistical basis given to the model:**
- Metric values/trends: Emissions Compliance 88% (improving), Renewable Energy 41% (improving), Patching Time 3.2d (improving), Board Independence 65 (declining)
- Correlation analysis computed **exactly one** significant pair: **Emissions Compliance ↔ Patching Time, r=0.83**
- *"No other metric pair reached significance."*

### A — codes only
The analysis identifies **one** statistically significant correlation: ESU10102 (88%, improving) and CSU10102 (3.2 days, improving), r=0.83, p<0.01 — improvements in one are closely tied to improvements in the other. Leadership should recognise that any reversal or pressure on one metric carries elevated risk of dragging the other down simultaneously.

CGS10102 (65, declining) is trending negatively while other metrics improve. Although no significant correlation was confirmed with other metrics, its isolated decline warrants monitoring.

| Pair | Correlation |
|---|---|
| ESU10102 / CSU10102 | r = 0.83 (strong positive) |

*No other pairs reached statistical significance.*

### B — codes + names
The analysis identifies **one** statistically significant correlation: Emissions Compliance Rate (ESU10102) vs Average Patching Time (CSU10102) — r=0.83, p<0.01.

*Risk interpretation:* "As patching time improves, emissions compliance improves in tandem. This suggests a **potential shared operational dependency** — possibly common resource constraints, process maturity, or governance oversight." *(hedged: "possibly / may")*

Board Independence Score (CGS10102) is declining while other metrics improve — worth monitoring, but no statistically significant correlations were identified with other metrics.

### C — names only
The analysis surfaces **one** statistically significant correlation: Emissions Compliance Rate and Average Patching Time (r = 0.83, p < 0.01). These two operationally distinct metrics — environmental compliance and IT security hygiene — are moving in strong lockstep. **This warrants scrutiny: it may indicate a shared underlying driver (e.g. the same operational teams, process-improvement initiatives, or resource-allocation cycles governing both).** If that shared driver reverses, both could deteriorate simultaneously.

While not part of a significant correlation pair, the declining Board Independence Score (65) represents an isolated governance risk to monitor independently.

### Probe 2 read
- **No variant invented** an Emissions↔Renewable correlation, even though both are "improving" and conceptually related. ✅ The explicit *"no other pair reached significance"* line held the model in place.
- **C (names only) fabricated a causal *mechanism*** ("same operational teams, resource-allocation cycles") — a **semantic-prior hallucination** of the *explanation*, not the correlation. **A (codes only) was cleanest**; B was middle.

---

## Overall verdict
1. **Correlations stayed faithful in all 6 runs** — the model did **not** invent measured relationships, *provided* we give it the stats **+ the explicit negatives** + a faithfulness instruction.
2. **Explanation drift is real and names make it worse** — titles supply the raw material for a plausible-but-fabricated "why." **Codes-only is the most grounded representation.**
3. **Therefore: reason on codes, apply names at display time (deterministic), add a validation gate, and instruct the model not to speculate on mechanisms.** (Full design + 18 failure modes in `LABELING_HALLUCINATION_ANALYSIS.md`.)

**Caveats:** 2 probes · 1 model · small clean inputs · temp 0. The real enterprise synthesis (hundreds of metrics, long context) may drift more; other models may differ. This is directional evidence — but real, reproducible evidence, not opinion.

---

## Appendix — reproducibility
Harness: 3 prompts per probe, identical statistical basis, only entity representation varies; `claude-sonnet-4-6`, `temperature=0`, `max_tokens≈400`. Raw prompts and outputs retained. Re-runnable for ~$0.03.
