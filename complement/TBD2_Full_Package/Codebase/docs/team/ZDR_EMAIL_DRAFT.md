# Anthropic ZDR (Zero Data Retention) - send-ready email draft

Send to Anthropic sales (sales@anthropic.com or your account contact) **before** the first client
contract signs. Fill the two `[brackets]`.

---

**Subject:** Zero Data Retention agreement - enterprise API customer (ESG/risk SaaS)

Hi Anthropic team,

We're building an AI-powered enterprise ESG, risk & compliance platform (Vigilant Lens, by TBD2 /
[legal entity], registering in Canada) on the Claude API - currently Haiku 4.5 and Sonnet 4.6 via the
Anthropic SDK. We're pre-revenue and about to sign our first enterprise clients, whose data governance
requirements make data handling a gating item for us.

We'd like to start the process for a **Zero Data Retention (ZDR) agreement** so that prompts and
outputs are processed and immediately discarded (no 30-day / 7-day retention). Specifically we'd like to confirm:

1. ZDR eligibility and how to enable it on our organization/API keys.
2. Confirmation that inputs/outputs under ZDR are **not retained** and **never used for training**.
3. Any minimum commitment / pricing implications.
4. For Canadian data-residency questions from clients, whether you'd point us to **AWS Bedrock
   (ca-central-1)** as the residency path, or whether the first-party API can meet this.

We expect roughly [est. monthly token volume] and want the agreement in place before onboarding.
Who's the right contact to move this forward?

Thanks,
[Your name]
Founder / Product Lead, TBD2 - Vigilant Lens

---
*Reference (verified June 2026): Anthropic API log retention is 7 days (reduced from 30, Sept 2025),
never used for training; ZDR available for enterprise; Bedrock ca-central-1 is the Canadian-residency
escalation path. Keep these straight if they come up on the call.*
