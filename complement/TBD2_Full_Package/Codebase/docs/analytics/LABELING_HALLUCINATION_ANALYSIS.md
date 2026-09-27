# Contextual Labeling vs. Hallucination — Analysis, Test & Recommendation
### Vigilant Lens · July 2026 · Response to Praveen's correctness concern

---

## 1. The concern (Praveen, verbatim intent)
If we replace metric **codes** with **business titles** when we feed the LLM, the model may reason from the *meaning of the titles* rather than from the **statistical correlation the Python pipeline actually computed** — connecting "domain concepts" instead of the real, measured relationship. That is **drift / hallucination**, and it would compromise correctness.

**He is right in principle.** Codes (`ESU10102`) are *semantically neutral anchors*: they force the model to rely on the numbers we give it. Titles carry priors the model can "explain" from.

---

## 2. What we tested (real Claude, controlled)
Two controlled probes on **claude-sonnet-4-6**, temperature 0, identical statistical basis, varying only the entity representation: **A = codes only · B = codes + name glossary · C = names only**. Cost: **~$0.03 total.**

- **Probe 1 (false-positive):** two metrics whose *names* sound related (Emissions Compliance ↔ Renewable Energy) but stats say **no** correlation (r=0.07).
- **Probe 2 (omission — Praveen's exact case):** only **one** correlation computed; names include concept-similar metrics with **no** stated relationship. Does the model connect them anyway?

## 3. What we found (evidence)
| | Invented a false correlation? | Explanation drift? |
|---|---|---|
| **A — codes only** | ❌ No | Minimal — stayed on the numbers |
| **B — codes + names** | ❌ No (even added its *own* "no relationships beyond the evidence" disclaimer) | Mild, hedged |
| **C — names only** | ❌ No | **Yes — invented a causal mechanism** ("shared operational driver… same teams / resource cycles") not in the data |

**Two conclusions:**
1. **The catastrophic failure (inventing a correlation from name-similarity) did NOT reproduce** — *provided* the prompt explicitly states the computed results **and** the negatives ("no other pair reached significance") **and** instructs faithfulness. The explicit negative statement is what prevents invention.
2. **The real residual risk is "explanation drift":** the correlations stay faithful, but the model fabricates *why* they exist — and **names-only makes this worse** because titles supply the raw material for a plausible story. **Codes-only is the most restrained.**

**Caveats (honesty):** 2 probes, 1 model, small clean inputs, temp 0. The real enterprise synthesis (hundreds of metrics, long context) can drift more, and other models may differ. This is directional evidence, not proof — but it *is* real evidence, not opinion.

---

## 4. The recommendation
**Decouple the reasoning substrate from the display layer.**
1. **LLM reasons on CODES + statistics only** (safest; least embellishment). Never feed titles as the reasoning basis.
2. **Apply names at DISPLAY time** via deterministic lookup from the mapping file → 100% correct, **zero model involvement, zero drift**. Venkatesh gets business language; grounding is untouched.
3. **Structured output + grounding citations:** every finding must cite the code(s) **and** the specific statistic it rests on.
4. **Validation gate:** reject/flag any asserted relationship that doesn't match a computed pair (kills invented correlations programmatically).
5. **Curb explanation drift:** instruct the model to **not speculate on causal mechanisms**, or to label speculation explicitly ("hypothesis, not from data"). Keep temperature 0.
6. If titles ever must be in-context, use the **glossary form (B)** + explicit negatives — it held up best in the test.

---

## 5. Exhaustive failure-mode register ("every possible failure")

**A. Representation → LLM (reasoning) risks**
| # | Failure | Severity | Mitigation |
|---|---|---|---|
| 1 | **Correlation invention** — asserts a link between concept-similar names not in the data | 🔴 High | Codes-only reasoning; validation gate; state negatives explicitly |
| 2 | **Explanation/causal hallucination** — fabricates *why* a real correlation exists (observed in test) | 🟠 Med | "Do not speculate on mechanisms"; codes-only; label hypotheses |
| 3 | **Correlation dismissal** — downplays a real counterintuitive link because names seem unrelated | 🟠 Med | Codes-only; require reporting all significant pairs |
| 4 | **Sign/direction error** — misstates positive/negative from name intuition | 🟠 Med | Structured output echoing the r-value/sign |
| 15 | **Over-generalization** — "Environmental performance is poor" from one metric | 🟠 Med | Constrain claims to the metric level; validation gate |
| 16 | **Grounding loss in long context** — real synthesis has 100s of metrics; claim↔stat link breaks | 🔴 High | Grounding citations; chunk; per-claim stat reference |
| 18 | **Outside-knowledge injection** — imports regs/benchmarks as if they were the analysis | 🟠 Med | "Use only provided data"; validation gate |

**B. Mapping / render-layer risks**
| # | Failure | Severity | Mitigation |
|---|---|---|---|
| 5 | **Wrong lookup** — stale/duplicate/missing code → mislabels a real finding | 🟠 Med | Versioned mapping; unit tests; fail closed |
| 6 | **Unmapped code leakage** — raw code shown, or a name invented for it | 🟠 Med | Validate every emitted code ∈ mapping; else flag |
| 7 | **Hallucinated code** — model emits a code that doesn't exist | 🔴 High | Validation gate rejects unknown codes |
| 8 | **Hierarchy-level confusion** — metric vs group vs module code mixed up | 🟠 Med | Level-typed IDs; validate level in gate |
| 11 | **Value↔entity mismatch** — right narrative, wrong metric's number | 🔴 High | Structured output binds value to code |

**C. Systemic / operational risks**
| # | Failure | Severity | Mitigation |
|---|---|---|---|
| 9 | **Temporal inconsistency** — same code labeled differently across runs | 🟠 Med | Version + freeze the mapping per run |
| 10 | **Translation-pass drift** — a 2nd LLM "prettify" pass changes meaning | 🔴 High | Do names at render (deterministic), not via a 2nd LLM pass |
| 12 | **Prompt injection via tenant names** — malicious/odd names steer the model | 🟠 Med | Sanitize names; names only at render, not in prompt |
| 13 | **Locale/Arabic drift** — GCC Arabic names change reasoning | 🟠 Med | Reason on codes; localize only at display |
| 14 | **Confidence miscalibration** — score computed on codes ≠ named narrative emphasis | 🟢 Low | Compute confidence from stats, not prose |
| 17 | **Non-determinism** — temp>0 → different narrative per run, hard to audit | 🟢 Low | Temperature 0; store prompt+output+version |

---

## 6. Draft reply to the team

> **Praveen — you're right, and I tested it on real Claude to be sure (cost ~$0.03).**
>
> **Good news:** the worst case — the model *inventing* a correlation between two concept-similar titles — did **not** happen, as long as we (a) give it the computed stats, (b) explicitly state the negatives ("no other pair was significant"), and (c) tell it to stick to the data. When the number says r=0.07, all versions correctly reported "no correlation," even titles-only.
>
> **But** you're right that titles cause drift of a subtler kind: with names-only, Claude *invented a causal explanation* for a real correlation ("shared operational driver, same teams…") that wasn't in the analysis. Codes-only stayed clean.
>
> **So the fix is: keep the analysis on codes, and put the business names on at *display* time** — a deterministic lookup from your mapping file, no LLM involved. Venkatesh gets the business language he wanted; the correlations stay 100% grounded in your Python analysis; and we add a validation gate that rejects any relationship or code the model asserts that isn't actually in the data. I've written up the full failure list and the design — happy to walk through it on the call.

---

*Evidence: 2 controlled probes on claude-sonnet-4-6 (temp 0), July 2026. Test harness + raw outputs retained.*
