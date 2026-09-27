# SPC-RPN Risk Assessment
## Apex Enterprise Modules — Statistical Process Control & Failure Mode Analysis
**Analysis Date:** 2026-01-07 | **Analyst:** SPC-RPN Specialist | **Scope:** 168 Metrics Across 12 ESG Modules

---

## Executive Summary

All 168 monitored metrics exhibit a uniform Cpk of 1.0 at 3-Sigma capability, yet **every single process is generating out-of-control signals** (ranging from 10 to 59 signals per metric). This paradox — adequate short-term capability paired with pervasive control chart violations — is the defining systemic risk finding. RPN scores span 350 to 2,065, with **47 metrics exceeding RPN 1,000**, constituting an enterprise-wide critical risk condition. No process in the portfolio can be classified as statistically stable.

---

## SPC-RPN Risk Assessment

---

### Statistical Process Control Findings

#### Foundational SPC Interpretation — Critical Context

Before listing individual violations, three systemic observations govern interpretation of all findings:

**Observation 1 — The Cpk/Signal Paradox:**
Every metric shows Cpk = 1.0 (3-sigma), which normally indicates marginally acceptable process capability. However, simultaneously recording dozens of out-of-control signals on the same processes indicates that the process mean and/or variance are **not stable over time**. A Cpk calculated on an unstable process is statistically meaningless — the true long-term Cpk is almost certainly below 1.0 for most metrics. The Cpk values reported should be treated as unreliable until stability is first established.

**Observation 2 — LCL_MR = 0.0 Across All Metrics:**
The Lower Control Limit for the Moving Range chart is zero for all 168 metrics. This is mathematically expected when MRBar × D3 yields a negative number (D3 = 0 for n=2), confirming the use of Individual-MR (I-MR) charts. This is noted as structurally correct but means the MR chart provides no lower-bound detection sensitivity.

**Observation 3 — Signal Count as Primary Severity Indicator:**
With Cpk and Sigma Level uniform across all metrics, the **signal count** (column: `signals`) is the primary differentiator of process instability severity in this dataset. Signal counts range from 10 (BCB10000) to 59 (PBI10000) and directly drive RPN scores via the Occurrence component.

---

#### Out-of-Control Processes — Full Ranked Inventory

All 168 processes are out of control. The following classification uses signal count thresholds to define violation severity tiers:

| Tier | Signal Count Range | Classification | Count of Metrics |
|---|---|---|---|
| **CRITICAL** | 45 – 59 | Severely unstable — immediate intervention | 10 |
| **HIGH** | 35 – 44 | Highly unstable — urgent attention | 29 |
| **ELEVATED** | 25 – 34 | Significantly unstable — prioritised review | 64 |
| **MODERATE** | 15 – 24 | Unstable — scheduled corrective action | 48 |
| **LOWER** | 10 – 14 | Unstable — monitoring and investigation | 17 |

---

##### TIER 1 — CRITICAL (Signals: 45–59) | Immediate Intervention Required

These processes are generating control chart violations at a rate that renders the process fundamentally uncontrolled. Western Electric Rule violations most likely include: Rule 1 (points beyond 3σ), Rule 2 (runs of 9+ on one side of centerline), Rule 3 (6+ consecutive trending points), and Rule 4 (alternating patterns), given the signal density.

| Metric ID | Mean | Sigma | UCL | LCL | MRBar | UCL_MR | Signals | RPN |
|---|---|---|---|---|---|---|---|---|
| **PBI10000** | 50.15 | 6.64 | 70.06 | 30.23 | 7.49 | 24.47 | **59** | **2,065** |
| **RCD10000** | 60.08 | 4.01 | 72.10 | 48.07 | 4.52 | 14.76 | **54** | **1,890** |
| **ERS10000** | 42.49 | 3.41 | 52.70 | 32.27 | 3.84 | 12.55 | **53** | **1,855** |
| **CPG10000** | 45.02 | 3.40 | 55.21 | 34.83 | 3.83 | 12.52 | **50** | **1,750** |
| **FLO10000** | 64.01 | 4.61 | 77.84 | 50.18 | 5.20 | 17.00 | **50** | **1,750** |
| **PPB10000** | 50.55 | 7.38 | 72.70 | 28.40 | 8.33 | 27.22 | **50** | **1,750** |
| **BSP10000** | 50.06 | 7.47 | 72.47 | 27.65 | 8.43 | 27.54 | **46** | **1,610** |
| **RST10000** | 60.10 | 3.99 | 72.07 | 48.13 | 4.50 | 14.71 | **45** | **1,575** |
| **L0ER_001** | 60.62 | 0.40 | 61.83 | 59.42 | 0.45 | 1.48 | **44** | **1,540** |
| **TQA10000** | 56.54 | 4.23 | 69.22 | 43.86 | 4.77 | 15.58 | **44** | **1,540** |

**Special Note on L0ER_001:** This metric has an exceptionally tight control band (UCL–LCL spread = 2.41 units, sigma = 0.40), yet records 44 signals. This indicates either extreme process hypersensitivity, measurement system instability (Gauge R&R concern), or a process operating at the absolute edge of its natural variation band. This metric warrants immediate Measurement System Analysis (MSA).

**Special Note on PPB10000 and BSP10000:** These processes have the widest control bands in Tier 1 (UCL_MR of 27.22 and 27.54 respectively), indicating high within-process variation alongside frequent signals — a combination suggesting both large-amplitude shifts and erratic behaviour patterns.

---

##### TIER 2 — HIGH INSTABILITY (Signals: 35–44)

| Metric ID | Mean | Sigma | Signals | RPN | Notable Risk Factor |
|---|---|---|---|---|---|
| RSS10000 | 50.23 | 6.15 | 43 | 1,505 | High sigma, broad MR range |
| SCP10000 | 30.00 | 2.19 | 43 | 1,505 | Low-mean process — floor proximity risk |
| SRVC_001 | 29.99 | 0.57 | 43 | 1,505 | Very tight band, 43 signals — MSA concern |
| ANO10000 | 64.15 | 4.73 | 42 | 1,470 | Upper-range mean, ceiling proximity |
| CUST_001 | 59.48 | 1.22 | 42 | 1,470 | Tight band with high signal rate |
| MSP10000 | 45.05 | 4.76 | 42 | 1,470 | Moderate sigma with high occurrence |
| RSL10000 | 59.88 | 4.07 | 42 | 1,470 | — |
| CII10000 | 59.59 | 5.38 | 41 | 1,435 | — |
| ROR10000 | 59.89 | 4.07 | 41 | 1,435 | — |
| CLC10000 | 29.95 | 1.94 | 40 | 1,400 | Low-mean — LCL boundary risk |
| CTP10000 | 56.59 | 4.50 | 40 | 1,400 | — |
| PUR10000 | 56.40 | 3.81 | 40 | 1,400 | — |
| CSP10000 | 59.55 | 5.27 | 39 | 1,365 | — |
| EFI10000 | 42.50 | 3.23 | 39 | 1,365 | — |
| EHU10000 | 42.50 | 3.35 | 39 | 1,365 | — |
| ESC10000 | 42.47 | 3.46 | 39 | 1,365 | — |
| RMR10000 | 60.02 | 3.87 | 39 | 1,365 | — |
| BPA10000 | 49.86 | 8.07 | 38 | 1,330 | **Highest sigma in tier** — UCL_MR = 29.76 |
| CCM10000 | 59.60 | 5.20 | 38 | 1,330 | — |
| CNT10000 | 63.92 | 4.43 | 38 | 1,330 | — |
| EAU10000 | 44.59 | 4.14 | 38 | 1,330 | — |
| EGV10000 | 42.41 | 3.82 | 38 | 1,330 | — |
| SCC10000 | 30.00 | 2.20 | 38 | 1,330 | Low-mean process |
| BIH10000 | 59.46 | 5.14 | 37 | 1,295 | — |
| CAP10000 | 56.49 | 3.87 | 37 | 1,295 | — |
| CMM10000 | 64.17 | 4.75 | 37 | 1,295 | — |
| REG10000 | **86.42** | 2.86 | 37 | 1,295 | **High-mean process** — UCL approaching 95.0 |
| BEV10000 | 59.50 | 5.19 | 36 | 1,260 | — |
| CIM10000 | 59.61 | 5.19 | 36 | 1,260 | — |

*(Continued: CRM10000, EPR10000, PBM10000, POD10000, PVD10000, RPR10000 — all RPN 1,260, signals 36)*

**Special Note on REG10000:** Operating at mean 86.42 with UCL = 95.0 suggests this is a compliance or regulatory score where ceiling-breach represents a distinct risk category (over-compliance gaming or data ceiling truncation). Requires domain-specific investigation.

---

##### TIER 3 — ELEVATED INSTABILITY (Signals: 25–34)

64 metrics fall into this tier with RPN values ranging from 875 to 1,225. Key metrics of note within this tier:

| Metric ID | Mean | Sigma | Signals | RPN | Notable Risk Factor |
|---|---|---|---|---|---|
| BPA10000 | 49.86 | **8.07** | 38 | 1,330 | Highest overall sigma — process spread concern |
| PRCY_001 | 87.49 | 0.73 | 34 | 1,190 | Near-ceiling, extremely tight — data truncation risk |
| IOP10000 | 87.54 | 1.84 | 34 | 1,190 | High-mean, near ceiling |
| SSU10000 | 86.52 | 2.81 | 34 | 1,190 | High-mean cluster |
| BRDM_001 | 81.46 | 2.57 | 34 | 1,190 | Upper-range process |
| DDD10000 | 87.49 | 1.31 | 33 | 1,155 | Near-ceiling, tight band |
| AUD10000 | 86.54 | 2.85 | 33 | 1,155 | Compliance/audit metric — ceiling risk |
| ESRC_001 | 86.51 | 0.77 | 32 | 1,120 | Ultra-tight band — MSA investigation warranted |
| ETPR_001 | 43.02 | 0.88 | 32 | 1,120 | Ultra-tight band — MSA investigation warranted |
| LCP10000 | 87.51 | 1.32 | 32 | 1,120 | Near-ceiling |
| PPP10000 | 56.57 | **7.43** | 29 | 1,015 | Very high sigma — process spread concern |
| FUL10000 | 64.06 | **6.33** | 29 | 1,015 | High sigma |
| LIN10000 | 64.20 | **7.19** | 24 | 840 | Very high sigma — UCL at 85.77 |
| APM10000 | 63.74 | **6.47** | 28 | 980 | High sigma |
| ASI10000 | 63.83 | **6.35** | 28 | 980 | High sigma |
| BRP10000 | 64.18 | **6.56** | 25 | 875 | High sigma |

**High-Sigma Cluster Alert:** Metrics PPP10000, LIN10000, APM10000, ASI10000, BRP10000, FUL10000, and BPA10000 all show sigma values ≥ 6.33. This cluster of high-variance processes likely shares a common input variable or process driver. Cross-correlation analysis is strongly recommended.

---

##### TIER 4 — MODERATE INSTABILITY (Signals: 15–24)

48 metrics with RPN 490–840. Includes BAL10000, BLC10000, CGS10000, DAM10000, PFR10000, BGL10000, and others. While lower priority relative to Tiers 1–3, all require scheduled corrective action within the current planning cycle.

---

##### TIER 5 — LOWER INSTABILITY (Signals: 10–14)

17 metrics with RPN 350–490. Includes BCB10000 (RPN 350, 10 signals), BTP10000 (RPN 385, 11 signals), IGV10000 (RPN 455, 13 signals), CGS10000 (RPN 490, 14 signals), BAL10000 (RPN 490, 14 signals), and BLC10000 (RPN 490, 14 signals). These represent the most stable processes in the portfolio — though all remain out of statistical control.

---

#### Processes Trending Toward Instability — Special Signal Pattern Analysis

Based on structural characteristics that indicate drift, mean-shift risk, or measurement boundary concerns:

| Metric ID | Mean | UCL | Current Signals | Trend Risk | Estimated Violation Escalation | Basis |
|---|---|---|---|---|---|---|
| **PRCY_001** | 87.49 | 89.68 | 34 | UCL ceiling breach | **Imminent (1–2 cycles)** | Mean at 97.8% of UCL; sigma 0.73 leaves almost no headroom |
| **IOP10000** | 87.54 | 93.07 | 34 | UCL ceiling breach | **Near-term (2–3 cycles)** | Mean at 94.1% of UCL |
| **ESRC_001** | 86.51 | 88.82 | 32 | UCL ceiling breach | **Imminent (1–2 cycles)** | Mean at 97.4% of UCL; sigma 0.77 |
| **LCP10000** | 87.51 | 91.47 | 32 | UCL ceiling breach | **Near-term (2–3 cycles)** | Mean at 95.7% of UCL |
| **L0ER_001** | 60.62 | 61.83 | 44 | Both limits | **Already breaching** | UCL–LCL spread = 2.41; any shift generates violation |
| **SRVC_001** | 29.99 | 31.69 | 43 | LCL floor risk | **Near-term** | Sigma 0.57 with mean near lower bound |
| **ETPR_001** | 43.02 | 45.65 | 32 | Tight band | **Already breaching** | UCL–LCL spread = 5.25; sigma 0.88 — high sensitivity |
| **DAM10000** | 81.54 | 99.42 | 17 | UCL ceiling breach | **Medium-term (4–6 cycles)** | UCL at 99.42 — ceiling truncation likely if mean shifts up |
| **BLC10000** | 81.51 | 102.45 | 14 | UCL breach | **Medium-term** | UCL exceeds 100 — if metric is percentage-bounded, truncation distorts analysis |
| **BTP10000** | 81.51 | 102.32 | 11 | UCL breach | **Medium-term** | Same UCL boundary concern as BLC10000 |
| **REG10000** | 86.42 | 95.00 | 37 | Ceiling-bounded UCL | **Already constrained** | UCL exactly at 95 — likely a hard cap causing non-normal distribution |
| **SCP10000** | 30.00 | 36.55 | 43 | LCL floor | **Ongoing** | Mean at minimum operating level — downward shift catastrophic |
| **CLC10000** | 29.95 | 35.78 | 40 | LCL floor | **Ongoing** | Mean below 30 — floor boundary risk |

**Boundary Breach Alert — UCL > 100:** Metrics BLC10000 (UCL = 102.45), BTP10000 (UCL = 102.32), BCB10000 (UCL = 102.28), BAL10000 (UCL = 98.66), BGL10000 (UCL = 99.68), and DAM10000 (UCL = 99.42) all have UCLs at or exceeding 100. If these metrics are percentage-bounded (0–100 scale), the calculated UCL is physically impossible, indicating the process distribution is non-normal or right-skewed, and control limits require recalculation using appropriate transformations (e.g., Box-Cox, logit transformation for proportion data).

---

### Risk Priority Number Analysis

**RPN Methodology Note:** RPN = Severity × Occurrence × Detection. Given uniform Sigma Level (3.0) and Cpk (1.0) across all metrics, the RPN variation in this dataset is driven primarily by Occurrence (signal count). The reported RPN scores are accepted as authoritative. All 168 metrics exceed the RPN > 100 threshold for corrective action. The following table presents the top 30 critical failure modes plus selected strategic entries.

#### Top 30 Critical Failure Modes by RPN

| Rank | Failure Mode | Metric ID | Mean | Sigma | Signals | RPN | Severity Indicator | Occurrence Indicator | Detection Indicator | Action Required |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Process output instability — primary business index | PBI10000 | 50.15 | 6.64 | 59 | **2,065** | High (broad sigma, wide MR) | Very High (59 signals) | Inadequate | **Immediate** |
| 2 | Record/data completeness failure | RCD10000 | 60.08 | 4.01 | 54 | **1,890** | High | Very High (54) | Inadequate | **Immediate** |
| 3 | Error resolution system failure | ERS10000 | 42.49 | 3.41 | 53 | **1,855** | High | Very High (53) | Inadequate | **Immediate** |
| 4 | Compliance process gap — CPG | CPG10000 | 45.02 | 3.40 | 50 | **1,750** | High | High (50) | Inadequate | **Immediate** |
| 5 | Flow process disruption | FLO10000 | 64.01 | 4.61 | 50 | **1,750** | High | High (50) | Inadequate | **Immediate** |
| 6 | Policy/procedure breach occurrence | PPB10000 | 50.55 | 7.38 | 50 | **1,750** | High (high sigma) | High (50) | Inadequate | **Immediate** |
| 7 | Business service process breakdown | BSP10000 | 50.06 | 7.47 | 46 | **1,610** | High (highest MR UCL in tier) | High (46) | Inadequate | **Urgent** |
| 8 | Response/resolution time failure | RST10000 | 60.10 | 3.99 | 45 | **1,575** | Moderate-High | High (45) | Inadequate | **Urgent** |
| 9 | L0 error rate — system-level | L0ER_001 | 60.62 | 0.40 | 44 | **1,540** | High (tight band, MSA risk) | High (44) | Poor | **Urgent** |
| 10 | Total quality assurance failure | TQA10000 | 56.54 | 4.23 | 44 | **1,540** | High | High (44) | Inadequate | **Urgent** |
| 11 | Risk/service score stability | RSS10000 | 50.23 | 6.15 | 43 | **1,505** | High | High (43) | Inadequate | **Urgent** |
| 12 | Scope/compliance process failure | SCP10000 | 30.00 | 2.19 | 43 | **1,505** | Critical (floor proximity) | High (43) | Inadequate | **Urgent** |
| 13 | Service delivery — SRVC metric | SRVC_001 | 29.99 | 0.57 | 43 | **1,505** | High (MSA concern) | High (43) | Poor | **Urgent** |
| 14 | Anomaly occurrence rate | ANO10000 | 64.15 | 4.73 | 42 | **1,470** | High | High (42) | Inadequate | **Priority** |
| 15 | Customer process metric | CUST_001 | 59.48 | 1.22 | 42 | **1,470** | High (tight band) | High (42) | Poor | **Priority** |
| 16 | Managed service process | MSP10000 | 45.05 | 4.76 | 42 | **1,470** | Moderate-High | High (42) | Inadequate | **Priority** |
| 17 | Risk/SLA loss metric | RSL10000 | 59.88 | 4.07 | 42 | **1,470** | High | High (42) | Inadequate | **Priority** |
| 18 | Customer impact index | CII10000 | 59.59 | 5.38 | 41 | **1,435** | High | High (41) | Inadequate | **Priority** |
| 19 | Rate of return/recurrence | ROR10000 | 59.89 | 4.07 | 41 | **1,435** | Moderate-High | High (41) | Inadequate | **Priority** |
| 20 | Corrective/compliance loop | CLC10000 | 29.95 | 1.94 | 40 | **1,400** | High (floor risk) | High (40) | Inadequate | **Priority** |
| 21 | Cycle time/throughput process | CTP10000 | 56.59 | 4.50 | 40 | **1,400** | Moderate | High (40) | Inadequate | **Priority** |
| 22 | Purchase/procurement rate | PUR10000 | 56.40 | 3.81 | 40 | **1,400** | Moderate | High (40) | Inadequate | **Priority** |
| 23 | Customer satisfaction process | CSP10000 | 59.55 | 5.27 | 39 | **1,365** | High | High (39) | Inadequate | **Scheduled** |
| 24 | Efficiency index | EFI10000 | 42.50 | 3.23 | 39 | **1,365** | Moderate | High (39) | Inadequate | **Scheduled** |
| 25 | Human utilisation | EHU10000 | 42.50 | 3.35 | 39 | **1,365** | Moderate | High (39) | Inadequate | **Scheduled** |
| 26 | Escalation/scope control | ESC10000 | 42.47 | 3.46 | 39 | **1,365** | Moderate | High (39) | Inadequate | **Scheduled** |
| 27 | Repair/maintenance rate | RMR10000 | 60.02 | 3.87 | 39 | **1,365** | Moderate | High (39) | Inadequate | **Scheduled** |
| 28 | Business process activity | BPA10000 | 49.86 | 8.07 | 38 | **1,330** | **Very High** (sigma = 8.07) | High (38) | Poor | **Scheduled** |
| 29 | Customer communications | CCM10000 | 59.60 | 5.20 | 38 | **1,330** | High | High (38) | Inadequate | **Scheduled** |
| 30 | Contact/interaction count | CNT10000 | 63.92 | 4.43 | 38 | **1,330** | Moderate | High (38) | Inadequate | **Scheduled** |

---

#### Additional Critical Entries — High-Mean Cluster (Compliance/Regulatory Processes)

The following high-mean metrics (mean > 80) require special risk framing. High means near physical or scale boundaries suggest these may be compliance scores, availability metrics, or percentage-based KPIs. Instability near ceiling values carries distinct regulatory and operational risk.

| Failure Mode | Metric ID | Mean | UCL | Sigma | Signals | RPN | Action Required |
|---|---|---|---|---|---|---|---|
| Regulatory compliance score | REG10000 | 86.42 | 95.00 | 2.86 | 37 | **1,295** | Priority |
| Availability/uptime — brand metric | BRDM_001 | 81.46 | 89.17 | 2.57 | 34 | **1,190** | Scheduled |
| Input/output process — ceiling risk | IOP10000 | 87.54 | 93.07 | 1.84 | 34 | **1,190** | Scheduled |
| Privacy/compliance score | PRCY_001 | 87.49 | 89.68 | 0.73 | 34 | **1,190** | Scheduled + MSA |
| Product/service score | PROD_001 | 56.52 | 59.48 | 0.99 | 34 | **1,190** | Scheduled + MSA |
| System/service uptime | SSU10000 | 86.52 | 94.96 | 2.81 | 34 | **1,190** | Scheduled |
| Audit compliance score | AUD10000 | 86.54 | 95.10 | 2.85 | 33 | **1,155** | Scheduled |
| Data integrity index | DDD10000 | 87.49 | 91.43 | 1.31 | 33 | **1,155** | Scheduled |
| Integration score | INTG_001 | 64.02 | 70.76 | 2.25 | 33 | **1,155** | Scheduled |
| Source compliance | ESRC_001 | 86.51 | 88.82 | 0.77 | 32 | **1,120** | Priority + MSA |
| Lifecycle compliance | LCP10000 | 87.51 | 91.47 | 1.32 | 32 | **1,120** | Scheduled |

---

### Critical Corrective Actions (Ranked by RPN)

---

#### IMMEDIATE PRIORITY — RPN ≥ 1,540 (Top 10 Processes)

---

**1. Comprehensive Stabilisation of PBI10000 — Primary Business Index**
**RPN: 2,065 | Due: Within 72 hours**

- **Root Cause Hypothesis:** The combination of high sigma (6.64), high MRBar (7.49), and 59 signals strongly suggests multiple assignable causes operating simultaneously — likely including shift-to-shift variation, input material/data variability, and possible measurement inconsistency. The wide moving range (UCL_MR = 24.47) confirms large point-to-point jumps, consistent with discrete input batching or periodic process resets.
- **Corrective Action:**
  - Convene a cross-functional war room within 24 hours
  - Stratify signal data by time-of-day, operator/system, input source, and batch ID
  - Conduct multi-vari analysis to identify dominant variation family (positional, cyclical, or temporal)
  - Implement temporary 100% inspection or duplicate measurement until root cause is isolated
  - Apply Western Electric zone analysis to identify which specific rules are firing most frequently
  - Quarantine outputs from this process pending stability confirmation
- **Verification Method:** Re-plot I-MR chart after 20–30 new observations post-intervention; confirm zero signals before lifting quarantine. Recalculate Cpk only after confirmed stability.

---

**2. Record Completeness and Data Integrity — RCD10000**
**RPN: 1,890 | Due: Within 72 hours**

- **Root Cause Hypothesis:** 54 signals with moderate sigma (4.01) and MRBar (4.52) suggests frequent step-changes in record completeness rates — consistent with intermittent system failures, batch processing errors, or data entry workflow disruptions. The narrower band relative to PBI10000 suggests the variation is structured (periodic) rather than random.
- **Corrective Action:**
  - Map all data entry points and automated feed mechanisms contributing to RCD10000
  - Implement data lineage tracing to identify which upstream sources correlate with signal events
  - Deploy automated completeness checking at point-of-entry rather than downstream
  - Review data governance policies for mandatory field enforcement
  - Establish escalation triggers when daily completeness drops below LCL (48.07)
- **Verification Method:** Weekly control chart review with stratified run charts by data source. Target: fewer than 5 signals in next 30-observation window.

---

**3. Error Resolution System — ERS10000**
**RPN: 1,855 | Due: Within 72 hours**

- **Root Cause Hypothesis:** 53 signals with consistent sigma (3.41) and moderate MRBar (3.84) suggests the error resolution process is systematically incapable of achieving a stable throughput rate. Root causes likely include inconsistent triage criteria, variable resource allocation, or upstream error volume instability feeding into resolution queues.
- **Corrective Action:**
  - Implement standardised error triage protocol with defined severity levels and response SLAs
  - Introduce queue management metrics with real-time dashboards for resolution team leads
  - Analyse whether signal spikes correlate with high-volume error intake periods (feedforward control)
  - Implement error prevention upstream to reduce resolution
