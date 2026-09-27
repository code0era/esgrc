# Contextual Labeling — Product Proposal
### Vigilant Lens · ESGRC + Apex · 12 July 2026

---

## 1. Where this came from (Venkatesh's demo feedback)

> *"Present the product in context of environment rather than as metrics groups and sub-modules. Where it is ABC10000 or ABC_001 it should be Wastewater Treatment, or Environment / Social / Governance / Risk & Compliance. This helps the user with contextual flow rather than the technical jargon we use for product development."*

**In one line:** users should see **business language**, not internal codes.

---

## 2. The problem today (BEFORE)

The product currently surfaces **internal technical codes** in the interface and in the AI recommendations:

| Where | User currently sees | Should see |
|---|---|---|
| Dashboard metric | `ESU10102` | **Emissions Compliance Rate** |
| Sub-module heading | `GRC10000` | **Governance, Risk & Compliance** |
| Apex module | `ESRC_001` | **ESGRC Module** |
| Claude recommendation | *"ESU10102 scored 72/100"* | *"Emissions Compliance Rate is below target"* |

This reads as engineering jargon, not a compliance product.

---

## 3. The solution: a Contextual Labeling Layer

**Key point for Praveen:** the friendly names **already exist** in our backend config — the
performance JSON and the Apex module mapping. We are **not creating new data**; we are
**surfacing names that are already there** and demoting the codes to a tooltip/subtitle.

- ✅ **14 sub-modules, 41 groups, 84 metrics** in ESGRC — every one already has a contextual name.
- ✅ **12 enterprise modules** in Apex — every one already has a contextual name.
- ✅ Effort = **presentation layer only** (low). No re-modelling, no waiting on new data.

**Applied in three places:**
1. **UI** — dashboard, pipeline steps, reports lead with the name; code shown small/on hover.
2. **AI recommendations** — feed names into Claude so recommendations speak in business terms
   (extends the existing work in commit `e6c25d7`, "carry names not raw IDs").
3. **Top-level framing** — group everything under the domains Venkatesh named:
   **Environmental · Social · Governance · Risk · Compliance**.

---

## 4. Timeline fit

Praveen's real client data + Venkatesh's templates are **~1–2 months** out. The labeling layer
can be **built now** against the existing structure, so the product is ready to speak the
client's language the moment that data lands.

---

## Appendix A — Complete ESGRC mapping (14 sub-modules / 41 groups / 84 metrics)

#### Environmental & Sustainability Unit  
`ESU10000`

| Level | Code (internal) | Contextual name (what the user sees) |
|---|---|---|
| Group | `ESU10101` | **Environmental Reporting Group** |
| &nbsp;&nbsp;Metric | `ESU10102` | Emissions Compliance Rate |
| &nbsp;&nbsp;Metric | `ESU10103` | Waste Reduction Score |
| &nbsp;&nbsp;Metric | `ESU10104` | Resource Efficiency Index |
| Group | `ESU10105` | **Sustainability Strategy Group** |
| &nbsp;&nbsp;Metric | `ESU10106` | Green Sourcing Metric |
| &nbsp;&nbsp;Metric | `ESU10107` | Renewable Energy Usage |
| Group | `ESU10108` | **Climate Risk Group** |
| &nbsp;&nbsp;Metric | `ESU10109` | T.C.F.D. Alignment Score |
| &nbsp;&nbsp;Metric | `ESU10110` | Physical Risk Assessment |

#### Social & Safety Unit  
`SSU10000`

| Level | Code (internal) | Contextual name (what the user sees) |
|---|---|---|
| Group | `SSU10101` | **Employee Safety Group** |
| &nbsp;&nbsp;Metric | `SSU10102` | Incident Rate (LTI) |
| &nbsp;&nbsp;Metric | `SSU10103` | Safety Training Compliance |
| Group | `SSU10104` | **Workforce Practices Group** |
| &nbsp;&nbsp;Metric | `SSU10105` | Diversity & Inclusion Index |
| &nbsp;&nbsp;Metric | `SSU10106` | Employee Turnover Rate |
| Group | `SSU10107` | **Social Impact Group** |
| &nbsp;&nbsp;Metric | `SSU10108` | Community Investment Score |
| &nbsp;&nbsp;Metric | `SSU10109` | Supplier Labor Standards Score |

#### Cybersecurity Unit  
`CSU10000`

| Level | Code (internal) | Contextual name (what the user sees) |
|---|---|---|
| Group | `CSU10101` | **Threat and Vulnerability Group** |
| &nbsp;&nbsp;Metric | `CSU10102` | Average Patching Time |
| &nbsp;&nbsp;Metric | `CSU10103` | Critical Vulnerabilities Count |
| Group | `CSU10104` | **Data Protection Group** |
| &nbsp;&nbsp;Metric | `CSU10105` | Data Encryption Compliance |
| &nbsp;&nbsp;Metric | `CSU10106` | Access Control Audit Score |
| Group | `CSU10107` | **Training and Awareness Group** |
| &nbsp;&nbsp;Metric | `CSU10108` | Phishing Click-Through Rate |
| &nbsp;&nbsp;Metric | `CSU10109` | Security Policy Adherence |

#### General Notes & Training  
`GNT10000`

| Level | Code (internal) | Contextual name (what the user sees) |
|---|---|---|
| Group | `GNT10101` | **Training Completion Group** |
| &nbsp;&nbsp;Metric | `GNT10102` | Mandatory Training Completion % |
| &nbsp;&nbsp;Metric | `GNT10103` | Average Training Score |
| Group | `GNT10104` | **Internal Communication Group** |
| &nbsp;&nbsp;Metric | `GNT10105` | Policy Read Receipt % |
| &nbsp;&nbsp;Metric | `GNT10106` | Compliance Reminder Effectiveness |

#### Corporate Governance Systems  
`CGS10000`

| Level | Code (internal) | Contextual name (what the user sees) |
|---|---|---|
| Group | `CGS10101` | **Board Structure Group** |
| &nbsp;&nbsp;Metric | `CGS10102` | Board Independence Score |
| &nbsp;&nbsp;Metric | `CGS10103` | Director Tenure Average |
| Group | `CGS10104` | **Executive Compensation Group** |
| &nbsp;&nbsp;Metric | `CGS10105` | Pay-to-Performance Alignment |
| &nbsp;&nbsp;Metric | `CGS10106` | Say-on-Pay Approval % |
| Group | `CGS10107` | **Shareholder Rights Group** |
| &nbsp;&nbsp;Metric | `CGS10108` | Shareholder Proposal Success Rate |
| &nbsp;&nbsp;Metric | `CGS10109` | Voting Turnout % |

#### Governance, Risk & Compliance  
`GRC10000`

| Level | Code (internal) | Contextual name (what the user sees) |
|---|---|---|
| Group | `GRC10101` | **Risk Identification Group** |
| &nbsp;&nbsp;Metric | `GRC10102` | Risk Register Completeness |
| &nbsp;&nbsp;Metric | `GRC10103` | Emerging Risk Flagging Frequency |
| &nbsp;&nbsp;Metric | `GRC10104` | Risk Assessment Coverage |
| Group | `GRC10105` | **Compliance Monitoring Group** |
| &nbsp;&nbsp;Metric | `GRC10106` | Control Effectiveness Score |
| &nbsp;&nbsp;Metric | `GRC10107` | Compliance Violation Count |
| Group | `GRC10108` | **Incident Reporting Group** |
| &nbsp;&nbsp;Metric | `GRC10109` | Incident Response Time |
| &nbsp;&nbsp;Metric | `GRC10110` | Root Cause Analysis Completion % |

#### Enterprise Risk Management  
`ERM10000`

| Level | Code (internal) | Contextual name (what the user sees) |
|---|---|---|
| Group | `ERM10101` | **Risk Strategy Group** |
| &nbsp;&nbsp;Metric | `ERM10102` | Risk Appetite Alignment Score |
| &nbsp;&nbsp;Metric | `ERM10103` | Risk Mitigation Cost Efficiency |
| Group | `ERM10104` | **Operational Risk Group** |
| &nbsp;&nbsp;Metric | `ERM10105` | Business Interruption Frequency |
| &nbsp;&nbsp;Metric | `ERM10106` | Process Control Failure Rate |
| Group | `ERM10107` | **Financial Risk Group** |
| &nbsp;&nbsp;Metric | `ERM10108` | Liquidity Risk Index |
| &nbsp;&nbsp;Metric | `ERM10109` | Credit Exposure Score |

#### Audit  
`AUD10000`

| Level | Code (internal) | Contextual name (what the user sees) |
|---|---|---|
| Group | `AUD10101` | **Audit Planning Group** |
| &nbsp;&nbsp;Metric | `AUD10102` | Audit Coverage % |
| &nbsp;&nbsp;Metric | `AUD10103` | Audit Plan Adherence % |
| Group | `AUD10104` | **Findings & Remediation Group** |
| &nbsp;&nbsp;Metric | `AUD10105` | High-Risk Findings Count |
| &nbsp;&nbsp;Metric | `AUD10106` | Remediation Timeliness |
| Group | `AUD10107` | **Audit Efficiency Group** |
| &nbsp;&nbsp;Metric | `AUD10108` | Audit Cycle Time |
| &nbsp;&nbsp;Metric | `AUD10109` | Management Satisfaction Score |

#### Policy Management  
`POL10000`

| Level | Code (internal) | Contextual name (what the user sees) |
|---|---|---|
| Group | `POL10101` | **Policy Creation Group** |
| &nbsp;&nbsp;Metric | `POL10102` | Policy Review Frequency |
| &nbsp;&nbsp;Metric | `POL10103` | New Policy Approval Time |
| Group | `POL10104` | **Policy Distribution Group** |
| &nbsp;&nbsp;Metric | `POL10105` | Policy Access Rate |
| &nbsp;&nbsp;Metric | `POL10106` | Policy Acknowledgment Rate |
| Group | `POL10107` | **Policy Adherence Group** |
| &nbsp;&nbsp;Metric | `POL10108` | Policy Breach Count |
| &nbsp;&nbsp;Metric | `POL10109` | Compliance Monitoring Gaps |

#### Regulatory Compliance  
`REG10000`

| Level | Code (internal) | Contextual name (what the user sees) |
|---|---|---|
| Group | `REG10101` | **Regulatory Monitoring Group** |
| &nbsp;&nbsp;Metric | `REG10102` | Regulatory Change Tracking % |
| &nbsp;&nbsp;Metric | `REG10103` | Rule Set Implementation Lag |
| Group | `REG10104` | **Reporting Group** |
| &nbsp;&nbsp;Metric | `REG10105` | Report Filing Timeliness |
| &nbsp;&nbsp;Metric | `REG10106` | Regulatory Inquiry Count |
| Group | `REG10107` | **Inspection & Audit Group** |
| &nbsp;&nbsp;Metric | `REG10108` | Adverse Finding Rate |
| &nbsp;&nbsp;Metric | `REG10109` | Inspection Preparation Time |

#### Ethics & Integrity  
`ETI10000`

| Level | Code (internal) | Contextual name (what the user sees) |
|---|---|---|
| Group | `ETI10101` | **Code of Conduct Group** |
| &nbsp;&nbsp;Metric | `ETI10102` | Code of Conduct Acknowledgment % |
| &nbsp;&nbsp;Metric | `ETI10103` | Ethics Training Completion % |
| Group | `ETI10104` | **Whistleblower Group** |
| &nbsp;&nbsp;Metric | `ETI10105` | Ethics Hotline Utilization Rate |
| &nbsp;&nbsp;Metric | `ETI10106` | Case Resolution Timeliness |
| Group | `ETI10107` | **Anti-Corruption Group** |
| &nbsp;&nbsp;Metric | `ETI10108` | Anti-Corruption Audit Findings |
| &nbsp;&nbsp;Metric | `ETI10109` | Conflict of Interest Disclosure % |

#### Corporate Governance  
`CGV10000`

| Level | Code (internal) | Contextual name (what the user sees) |
|---|---|---|
| Group | `CGV10101` | **Shareholder Relations Group** |
| &nbsp;&nbsp;Metric | `CGV10102` | ESG Rating Agency Score |
| &nbsp;&nbsp;Metric | `CGV10103` | Investor Engagement Frequency |
| Group | `CGV10104` | **Board Administration Group** |
| &nbsp;&nbsp;Metric | `CGV10105` | Board Meeting Attendance % |
| &nbsp;&nbsp;Metric | `CGV10106` | Committee Charter Compliance |
| Group | `CGV10107` | **Disclosure & Transparency Group** |
| &nbsp;&nbsp;Metric | `CGV10108` | Sustainability Report Score |
| &nbsp;&nbsp;Metric | `CGV10109` | Reporting Framework Adherence |

#### Information Governance  
`IGV10000`

| Level | Code (internal) | Contextual name (what the user sees) |
|---|---|---|
| Group | `IGV10101` | **Data Quality Group** |
| &nbsp;&nbsp;Metric | `IGV10102` | Data Accuracy Rate |
| &nbsp;&nbsp;Metric | `IGV10103` | Master Data Management Score |
| Group | `IGV10104` | **Record Management Group** |
| &nbsp;&nbsp;Metric | `IGV10105` | Retention Policy Compliance |
| &nbsp;&nbsp;Metric | `IGV10106` | Legal Hold Response Time |
| Group | `IGV10107` | **Information Security Group** |
| &nbsp;&nbsp;Metric | `IGV10108` | Data Leakage Prevention Score |
| &nbsp;&nbsp;Metric | `IGV10109` | Sensitive Data Access Log Audits |

#### Corporate Social Programs  
`CPI10000`

| Level | Code (internal) | Contextual name (what the user sees) |
|---|---|---|
| Group | `CPI10101` | **Employee Wellness Group** |
| &nbsp;&nbsp;Metric | `CPI10102` | Wellness Program Participation |
| &nbsp;&nbsp;Metric | `CPI10103` | Absenteeism Rate |
| Group | `CPI10104` | **Volunteering Group** |
| &nbsp;&nbsp;Metric | `CPI10105` | Volunteer Hours Per Employee |
| &nbsp;&nbsp;Metric | `CPI10106` | Community Partner Satisfaction |
| Group | `CPI10107` | **Philanthropy Group** |
| &nbsp;&nbsp;Metric | `CPI10108` | Donation Match Utilization |
| &nbsp;&nbsp;Metric | `CPI10109` | Philanthropic Focus Alignment |

---

## Appendix B — Apex enterprise modules (12 modules)

Each module below also has fully-named sub-areas in `module_mapping.csv` (same treatment).

| Code (internal) | Contextual name | Sub-areas |
|---|---|---|
| `BRDM_001` | **Brand Management** | 6 |
| `BSPT_001` | **Business Partner** | 17 |
| `CUST_001` | **Customer** | 19 |
| `ETPR_001` | **Enterprise** | 18 |
| `ESRC_001` | **ESGRC** | 14 |
| `INTG_001` | **Integration** | 7 |
| `MKTS_001` | **Market_and_Sales** | 12 |
| `PROD_001` | **Product** | 19 |
| `RSRC_001` | **Resource** | 10 |
| `SRVC_001` | **Service** | 16 |
| `SHRD_001` | **Shared** | 14 |
| `PRCY_001` | **ICTM** | 5 |

---

*Source of truth: `esgrc_performance_json_file.json` (ESGRC) and `module_mapping.csv` (Apex) — both backend-provided config already in the system. Generated 12 Jul 2026.*
