"""
Home Page Domain Configuration for All Modules (Apex, ESGRC, Customer, etc.)
Defines domain-specific titles, missions, KPIs, focus pillars, and metadata.
"""

MODULE_HOME_CONFIG = {
    "APEX": {
        "display": "Apex Enterprise",
        "badge": "Enterprise Command Center",
        "title": "Enterprise Risk & Governance Command Center",
        "subtitle": "Synthesize multi-departmental intelligence, aggregate cross-functional risk matrices, and empower C-level governance with autonomous AI insights.",
        "icon": "🛡️",
        "theme_color": "#CD6752",
        "stats": [
            {"label": "Enterprise RPN Index", "value": "142.4", "sub": "-18% MoM Risk Reduction", "trend": "positive"},
            {"label": "Cross-Module Health", "value": "94.2%", "sub": "12 Units Synchronized", "trend": "neutral"},
            {"label": "Predictive Accuracy", "value": "98.7%", "sub": "AI Regression Engine", "trend": "positive"},
            {"label": "Audit Readiness", "value": "100%", "sub": "Continuous Compliance", "trend": "positive"}
        ],
        "pillars": [
            {
                "title": "Cross-Functional Risk Synthesis",
                "desc": "Aggregates low-performing entities across all 12 corporate operating modules into unified enterprise severity matrices.",
                "icon": "🌐"
            },
            {
                "title": "Statistical Process Control (SPC L0)",
                "desc": "Evaluates enterprise-wide variability, X-bar R charts, and out-of-control signals across corporate performance baselines.",
                "icon": "📊"
            },
            {
                "title": "Multi-Entity CHAID Segmentation",
                "desc": "Identifies high-risk business segments, systemic bottleneck nodes, and multi-factor regression correlations.",
                "icon": "🔍"
            },
            {
                "title": "Executive AI Board Reporting",
                "desc": "Generates executive-ready master consolidated PDF dossiers with automated LLM executive summaries for leadership.",
                "icon": "📑"
            }
        ]
    },
    "ESGRC": {
        "display": "ESGRC",
        "badge": "Sustainability & Regulatory Governance",
        "title": "ESG, Risk & Compliance Intelligence Hub",
        "subtitle": "Continuously monitor environmental emissions, social governance commitments, and strict regulatory compliance across complex supply chains.",
        "icon": "🌱",
        "theme_color": "#10B981",
        "stats": [
            {"label": "Carbon Scope 1-3", "value": "-24.6%", "sub": "Decarbonization Target", "trend": "positive"},
            {"label": "Regulatory Alignment", "value": "99.1%", "sub": "CSRD & SEC Standards", "trend": "positive"},
            {"label": "Supplier ESG Score", "value": "88.4 / 100", "sub": "Tier 1 & 2 Audited", "trend": "positive"},
            {"label": "Governance Index", "value": "96.5%", "sub": "Zero Critical Violations", "trend": "positive"}
        ],
        "pillars": [
            {
                "title": "Environmental & Carbon Auditing",
                "desc": "Tracks GHG emissions, energy transition benchmarks, water stewardship, and circular economy metrics.",
                "icon": "🌍"
            },
            {
                "title": "Social & Human Capital Metrics",
                "desc": "Monitors workforce diversity, workplace safety standards, vendor fair-labor audits, and community impact.",
                "icon": "👥"
            },
            {
                "title": "Governance & Regulatory FMEA",
                "desc": "Applies Failure Mode & Effects Analysis (FMEA) to anti-bribery, ethics, disclosure integrity, and board transparency.",
                "icon": "⚖️"
            },
            {
                "title": "Automated ESG Disclosure Reports",
                "desc": "Generates compliant reporting aligned with GRI, SASB, TCFD, and European CSRD sustainability frameworks.",
                "icon": "📋"
            }
        ]
    },
    "CUSTOMER": {
        "display": "Customer",
        "badge": "Customer Experience & Retention",
        "title": "Customer Experience & Satisfaction Intelligence Hub",
        "subtitle": "Elevate customer loyalty, optimize support resolution velocity, and proactively eliminate churn risks with AI-driven sentiment and service analytics.",
        "icon": "🤝",
        "theme_color": "#0284C7",
        "stats": [
            {"label": "Net Promoter Score (NPS)", "value": "+68", "sub": "Top Decile Industry Benchmark", "trend": "positive"},
            {"label": "CSAT Satisfaction", "value": "94.8%", "sub": "Post-Resolution Surveys", "trend": "positive"},
            {"label": "First Contact Resolution", "value": "86.2%", "sub": "+7.4% vs Last Quarter", "trend": "positive"},
            {"label": "Churn Vulnerability", "value": "3.1%", "sub": "Proactive Interventions Active", "trend": "positive"}
        ],
        "pillars": [
            {
                "title": "Service Level Agreement (SLA) Tracking",
                "desc": "Continuous surveillance of first response times, ticket resolution bottlenecks, and agent readiness across contact channels.",
                "icon": "⏱️"
            },
            {
                "title": "Churn Prevention & Risk Scoring",
                "desc": "Neural regression models detecting early indicators of customer attrition, account disengagement, and adoption drop-off.",
                "icon": "🛡️"
            },
            {
                "title": "Voice of Customer (VoC) Analysis",
                "desc": "Synthesizes multi-channel feedback, satisfaction survey vectors, and customer sentiment signals into actionable priorities.",
                "icon": "💬"
            },
            {
                "title": "Customer Lifecycle Optimization",
                "desc": "Evaluates onboarding friction, feature adoption velocity, and ongoing expansion readiness across enterprise tiers.",
                "icon": "📈"
            }
        ]
    },
    "PRODUCT": {
        "display": "Product",
        "badge": "Product Quality & Lifecycle",
        "title": "Product Engineering & Quality Assurance Hub",
        "subtitle": "Accelerate release readiness, minimize defect density, and continuously track product reliability metrics across all engineering lifecycles.",
        "icon": "📦",
        "theme_color": "#8B5CF6",
        "stats": [
            {"label": "Defect Escape Rate", "value": "0.14%", "sub": "Well Below 0.5% Threshold", "trend": "positive"},
            {"label": "Release Readiness", "value": "96.8%", "sub": "Sprint QA Signoff Complete", "trend": "positive"},
            {"label": "Product RPN Score", "value": "42.0", "sub": "Low Operational Failure Risk", "trend": "positive"},
            {"label": "Uptime Reliability", "value": "99.98%", "sub": "Production Fleet Stability", "trend": "positive"}
        ],
        "pillars": [
            {
                "title": "Product Failure Mode (FMEA)",
                "desc": "Identifies architectural vulnerabilities, component failure modes, and calculates severity-occurrence-detection RPNs.",
                "icon": "⚙️"
            },
            {
                "title": "Six Sigma & Defect Variance",
                "desc": "Statistical process control for software and hardware production, monitoring tolerance limits and outlier anomalies.",
                "icon": "🔬"
            },
            {
                "title": "Feature Adoption & Velocity",
                "desc": "Tracks roadmap milestone delivery, product telemetry, and feature engagement patterns across user cohorts.",
                "icon": "🚀"
            },
            {
                "title": "Engineering Health & Tech Debt",
                "desc": "Quantifies code complexity, build pipeline health, test coverage saturation, and architectural longevity.",
                "icon": "🛠️"
            }
        ]
    },
    "BRAND": {
        "display": "Brand",
        "badge": "Brand Equity & Reputation",
        "title": "Brand Perception & Reputation Intelligence",
        "subtitle": "Protect enterprise brand equity, monitor market perception vectors, and identify emerging PR or reputation risks in real time.",
        "icon": "✨",
        "theme_color": "#EC4899",
        "stats": [
            {"label": "Brand Equity Index", "value": "89.2", "sub": "+5.1pts Market Perception", "trend": "positive"},
            {"label": "Positive Sentiment", "value": "92.4%", "sub": "Public & Media Channels", "trend": "positive"},
            {"label": "Share of Voice", "value": "34.8%", "sub": "#1 in Target Segment", "trend": "positive"},
            {"label": "Reputation Risk", "value": "Minimal", "sub": "Zero Critical Incidents", "trend": "positive"}
        ],
        "pillars": [
            {
                "title": "Reputation & Sentiment Surveillance",
                "desc": "Real-time parsing of public sentiment, media narratives, and stakeholder brand trust across market channels.",
                "icon": "📢"
            },
            {
                "title": "Brand Governance & Consistency",
                "desc": "Ensures international brand compliance, trademark integrity, and consistent messaging across all operating regions.",
                "icon": "🏛️"
            },
            {
                "title": "Competitive Brand Benchmark",
                "desc": "Compares brand resonance, customer loyalty recall, and premium positioning against tier-1 competitors.",
                "icon": "🏆"
            },
            {
                "title": "Crisis Early Warning",
                "desc": "Detects volatile sentiment shifts, social virality anomalies, and potential reputational vulnerabilities before escalation.",
                "icon": "🚨"
            }
        ]
    },
    "SERVICE": {
        "display": "Service",
        "badge": "Service Operations & SLA Excellence",
        "title": "Service Delivery & Operational Resilience",
        "subtitle": "Drive flawless service execution, guarantee contractual SLA commitments, and eliminate operational latency across delivery channels.",
        "icon": "🛎️",
        "theme_color": "#F59E0B",
        "stats": [
            {"label": "Overall SLA Compliance", "value": "99.4%", "sub": "Contractual Benchmark Exceeded", "trend": "positive"},
            {"label": "Mean Time to Resolve", "value": "18.4m", "sub": "-32% Incident Duration", "trend": "positive"},
            {"label": "Operational Availability", "value": "99.99%", "sub": "High-Availability Architecture", "trend": "positive"},
            {"label": "Service Quality Index", "value": "96.1", "sub": "Exemplary Audit Standard", "trend": "positive"}
        ],
        "pillars": [
            {
                "title": "Service SLA & Incident Management",
                "desc": "Continuous monitoring of SLA breach risks, ticket escalation triggers, and dispatch resolution cycles.",
                "icon": "⚡"
            },
            {
                "title": "Delivery Quality Control",
                "desc": "Standardized service evaluation ensuring consistent operational standards across all geographic dispatch regions.",
                "icon": "🎯"
            },
            {
                "title": "Capacity & Workload Balance",
                "desc": "Dynamically balances service queues, routing demands, and technician allocation for maximum operational efficiency.",
                "icon": "⚖️"
            },
            {
                "title": "Root Cause Analysis (RCA)",
                "desc": "Automated post-incident causal modeling identifying preventive interventions to permanently stop recurring outages.",
                "icon": "🔎"
            }
        ]
    },
    "RESOURCE": {
        "display": "Resource",
        "badge": "Resource Allocation & Workforce",
        "title": "Resource Optimization & Capacity Planning",
        "subtitle": "Maximize capital and operational resource efficiency, optimize human talent allocation, and prevent operational bottlenecks.",
        "icon": "💼",
        "theme_color": "#6366F1",
        "stats": [
            {"label": "Capacity Utilization", "value": "87.5%", "sub": "Optimal Healthy Operating Band", "trend": "positive"},
            {"label": "Allocation Efficiency", "value": "93.8%", "sub": "Minimal Idle Overhead", "trend": "positive"},
            {"label": "Talent Retention", "value": "94.2%", "sub": "Voluntary Turnover Controlled", "trend": "positive"},
            {"label": "Resource RPN", "value": "38.6", "sub": "Low Operational Drag", "trend": "positive"}
        ],
        "pillars": [
            {
                "title": "Human Capital & Talent Readiness",
                "desc": "Assesses skill matrix distribution, training completion indexes, and cross-functional redeployment agility.",
                "icon": "🎓"
            },
            {
                "title": "Asset & Infrastructure Utilization",
                "desc": "Tracks physical and digital resource consumption, server fleet efficiency, and operational asset longevity.",
                "icon": "🏢"
            },
            {
                "title": "Predictive Capacity Forecasting",
                "desc": "Projects resource demand requirements 6-12 months ahead based on strategic corporate growth targets.",
                "icon": "📊"
            },
            {
                "title": "Cost Efficiency & Budget Alignment",
                "desc": "Audits operational expenditures per resource unit and eliminates duplicate capital allocations across departments.",
                "icon": "💰"
            }
        ]
    },
    "MKTS": {
        "display": "MKTS",
        "badge": "Markets & Commercial Expansion",
        "title": "Market Dynamics & Commercial Growth Hub",
        "subtitle": "Decode competitive market shifts, track regional demand elasticity, and maximize market share capture with predictive analytics.",
        "icon": "🌐",
        "theme_color": "#14B8A6",
        "stats": [
            {"label": "Market Penetration", "value": "+18.4%", "sub": "YoY Regional Expansion", "trend": "positive"},
            {"label": "Sales Velocity Index", "value": "126.8", "sub": "Deal Acceleration Up 22%", "trend": "positive"},
            {"label": "Competitive Win Rate", "value": "64.2%", "sub": "+8.1% vs Tier 1 Rivals", "trend": "positive"},
            {"label": "Market Volatility Risk", "value": "Low", "sub": "Hedging & Diversified Exposure", "trend": "positive"}
        ],
        "pillars": [
            {
                "title": "Regional Growth Dynamics",
                "desc": "Analyzes market capture velocity, territory expansion feasibility, and macroeconomic demand fluctuations.",
                "icon": "🗺️"
            },
            {
                "title": "Competitor Intelligence",
                "desc": "Tracks rival feature parity, pricing elasticity, and market positioning shifts to protect competitive edge.",
                "icon": "♟️"
            },
            {
                "title": "Pipeline Conversion Analytics",
                "desc": "Applies regression modeling to commercial deal progression, identifying choke-points in enterprise sales funnels.",
                "icon": "📈"
            },
            {
                "title": "Strategic Market Risk Mitigation",
                "desc": "Forecasts regulatory tariffs, currency swings, and geopolitical risks impacting international market operations.",
                "icon": "🛡️"
            }
        ]
    },
    "ICTM": {
        "display": "ICTM",
        "badge": "IT Systems & Cybersecurity",
        "title": "Information & Cyber Technology Management",
        "subtitle": "Ensure enterprise IT infrastructure resilience, enforce zero-trust security postures, and safeguard continuous systems availability.",
        "icon": "💻",
        "theme_color": "#3B82F6",
        "stats": [
            {"label": "Core Systems Uptime", "value": "99.995%", "sub": "Enterprise High Availability", "trend": "positive"},
            {"label": "Security Posture Score", "value": "98.2 / 100", "sub": "Zero-Trust Architecture Verified", "trend": "positive"},
            {"label": "Patch Compliance", "value": "99.8%", "sub": "Critical CVEs Remediated <24h", "trend": "positive"},
            {"label": "Cyber Risk Index", "value": "12.4", "sub": "Extremely Low Threat Exposure", "trend": "positive"}
        ],
        "pillars": [
            {
                "title": "Cybersecurity & Threat Defense",
                "desc": "Continuous vulnerability assessments, endpoint threat surveillance, and zero-trust access enforcement.",
                "icon": "🔒"
            },
            {
                "title": "Cloud Infrastructure Resilience",
                "desc": "Monitors multi-region cloud cluster health, auto-scaling latency, and disaster recovery replication integrity.",
                "icon": "☁️"
            },
            {
                "title": "IT Governance & ISO 27001",
                "desc": "Audits compliance with SOC 2 Type II, ISO/IEC 27001, HIPAA, and NIST cybersecurity frameworks.",
                "icon": "📜"
            },
            {
                "title": "Technical Debt & Legacy Modernization",
                "desc": "Quantifies obsolete hardware and legacy stack risks, prioritizing architectural refresh initiatives.",
                "icon": "🔄"
            }
        ]
    },
    "INTEGRATION": {
        "display": "Integration",
        "badge": "System Interconnectivity & APIs",
        "title": "Enterprise Integration & Data Pipeline Hub",
        "subtitle": "Orchestrate seamless data flow across enterprise silos, ensure API throughput reliability, and guarantee data consistency.",
        "icon": "🔗",
        "theme_color": "#06B6D4",
        "stats": [
            {"label": "API Success Rate", "value": "99.97%", "sub": "Over 45M Daily Transactions", "trend": "positive"},
            {"label": "Avg Latency", "value": "42ms", "sub": "High-Throughput Gateway", "trend": "positive"},
            {"label": "Pipeline Data Integrity", "value": "100%", "sub": "Zero Data Corruption Events", "trend": "positive"},
            {"label": "Active Connectors", "value": "128", "sub": "Enterprise Systems Linked", "trend": "positive"}
        ],
        "pillars": [
            {
                "title": "API Gateway & Traffic Reliability",
                "desc": "Surveillance of rate limiting, error responses, latency spikes, and payload throughput across microservices.",
                "icon": "🚦"
            },
            {
                "title": "Data Pipeline Synchronization",
                "desc": "Validates schema consistency, ETL transformation accuracy, and real-time Kafka/PubSub stream stability.",
                "icon": "🔄"
            },
            {
                "title": "Cross-System Interoperability",
                "desc": "Connects legacy ERP, CRM, and cloud platforms into a synchronized, single source of operational truth.",
                "icon": "🧩"
            },
            {
                "title": "Integration Failure Recovery",
                "desc": "Automated dead-letter queue processing, circuit-breaker protocols, and self-healing connectivity fallback.",
                "icon": "🛡️"
            }
        ]
    },
    "BSPT": {
        "display": "BSPT",
        "badge": "Business Strategy & Portfolio",
        "title": "Business Strategy & Portfolio Tracking Hub",
        "subtitle": "Align multi-year strategic objectives with tactical portfolio execution, monitor initiative velocity, and govern ROI realization.",
        "icon": "🎯",
        "theme_color": "#A855F7",
        "stats": [
            {"label": "Strategic Milestone Delivery", "value": "92.4%", "sub": "On Schedule Execution", "trend": "positive"},
            {"label": "Portfolio ROI Realization", "value": "+142%", "sub": "Exceeding Hurdle Rates", "trend": "positive"},
            {"label": "Initiative Health Index", "value": "95.0", "sub": "96 Active Programs Monitored", "trend": "positive"},
            {"label": "Strategic Risk Rating", "value": "Low", "sub": "Mitigation Controls in Effect", "trend": "positive"}
        ],
        "pillars": [
            {
                "title": "Strategic OKR & KPI Governance",
                "desc": "Tracks enterprise OKRs, strategic milestone completions, and departmental alignment with board mandates.",
                "icon": "🎯"
            },
            {
                "title": "Portfolio Risk & Dependency Mapping",
                "desc": "Visualizes critical cross-project dependencies, resource contention, and strategic delivery roadblocks.",
                "icon": "🗺️"
            },
            {
                "title": "Capital Investment Rationalization",
                "desc": "Evaluates capital allocation efficacy, IRR benchmarks, and financial returns across transformation portfolios.",
                "icon": "💎"
            },
            {
                "title": "Executive Strategic Scorecards",
                "desc": "Generates real-time strategic scorecards providing transparent status overviews for board oversight.",
                "icon": "📊"
            }
        ]
    },
    "ENTERPRISE": {
        "display": "Enterprise",
        "badge": "Corporate Governance & Structure",
        "title": "Enterprise Operations & Institutional Governance",
        "subtitle": "Oversee enterprise-wide operational health, ensure organizational cohesion, and enforce institutional risk controls.",
        "icon": "🏛️",
        "theme_color": "#475569",
        "stats": [
            {"label": "Institutional Health", "value": "95.6%", "sub": "Enterprise Standard Met", "trend": "positive"},
            {"label": "Policy Compliance", "value": "99.2%", "sub": "Internal Controls Audited", "trend": "positive"},
            {"label": "Operating Efficiency", "value": "+16.8%", "sub": "Lean Process Optimization", "trend": "positive"},
            {"label": "Consolidated RPN", "value": "54.2", "sub": "Stable Risk Horizon", "trend": "positive"}
        ],
        "pillars": [
            {
                "title": "Institutional Policy Enforcement",
                "desc": "Ensures enterprise-wide policies, corporate bylaws, and standard operating procedures are systematically observed.",
                "icon": "📜"
            },
            {
                "title": "Multi-Divisional Synergy Tracking",
                "desc": "Measures collaboration efficacy, cross-selling velocity, and joint-venture realization across subsidiaries.",
                "icon": "🤝"
            },
            {
                "title": "Enterprise Risk Management (ERM)",
                "desc": "Comprehensive ERM framework coordinating operational, financial, reputational, and systemic risk mitigation.",
                "icon": "🛡️"
            },
            {
                "title": "Consolidated Business Intelligence",
                "desc": "Harmonizes operational data feeds across all corporate business units into centralized intelligence views.",
                "icon": "📊"
            }
        ]
    },
    "SHARED": {
        "display": "Shared",
        "badge": "Corporate Shared Services",
        "title": "Shared Services & Organizational Synergies Hub",
        "subtitle": "Unify corporate shared services, streamline administrative overhead, and maximize economies of scale across business units.",
        "icon": "🤝",
        "theme_color": "#0D9488",
        "stats": [
            {"label": "Service Request SLA", "value": "98.9%", "sub": "Rapid Ticket Turnaround", "trend": "positive"},
            {"label": "Cost Savings from Scale", "value": "$4.2M", "sub": "Centralized Procurement", "trend": "positive"},
            {"label": "User Satisfaction (Internal)", "value": "91.5%", "sub": "Internal Customer CSAT", "trend": "positive"},
            {"label": "Process Automation Rate", "value": "78.4%", "sub": "RPA & AI Workflows Active", "trend": "positive"}
        ],
        "pillars": [
            {
                "title": "Centralized Procurement & Vendor Mgmt",
                "desc": "Coordinates bulk enterprise purchasing, vendor terms renegotiation, and supplier risk auditing.",
                "icon": "🛒"
            },
            {
                "title": "HR & Payroll Shared Operations",
                "desc": "Standardizes employee onboarding, compensation disbursements, and global benefits administration.",
                "icon": "👥"
            },
            {
                "title": "Corporate Legal & Compliance Desk",
                "desc": "Manages contract lifecycle reviews, standard terms compliance, and internal intellectual property filings.",
                "icon": "⚖️"
            },
            {
                "title": "Shared Facilities & Operations",
                "desc": "Optimizes physical office leases, corporate logistics, and administrative utility expenditures.",
                "icon": "🏢"
            }
        ]
    }
}
