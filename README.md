# 💊 Pharma Patient Analytics — Funnel & Cohort Analysis Dashboard

> **Low medication adherence costs the US healthcare system ~$300 billion annually.**
> Digital patient support programs (PSPs) are proven interventions that improve
> adherence, reduce hospitalizations, and lower total cost of care.
> This project provides a **complete analytics stack** to measure PSP effectiveness.

![Python](https://img.shields.io/badge/Python-3.11-blue)
![Streamlit](https://img.shields.io/badge/Streamlit-Dashboard-red)
![dbt](https://img.shields.io/badge/dbt-SQL_Models-orange)
![License](https://img.shields.io/badge/License-MIT-green)

---

## ⚕️ Privacy Notice

> **All data in this repository is 100% synthetic.**
> No Protected Health Information (PHI) is used anywhere.
> Patient identifiers are random UUIDs (surrogate IDs).
> This project follows **HIPAA-safe methodology** — no names, dates of birth,
> addresses, Social Security numbers, or any of the 18 HIPAA identifiers are present.

---

## 📋 Project Overview

This dashboard tracks **patient progression through a support program funnel**,
identifies drop-off points that reduce medication adherence, and measures retention
by acquisition cohort — enabling pharma teams to improve PSP ROI.

### Key Questions Answered

| Question | Module |
|----------|--------|
| Where do patients drop out of the support program? | Funnel Analysis |
| Which enrollment cohort has the best 90-day retention? | Cohort Analysis |
| What is the medication adherence rate (MPR) by therapy area? | Adherence Metrics |
| Which acquisition channel has the highest ROI? | Channel Performance |
| Are there language or regional disparities in program access? | Health Equity Lens |

---

## 🏗️ Architecture

```
pharma-patient-analytics/
├── data/
│   ├── generate_synthetic_data.py   # Creates 150K synthetic events
│   └── patient_events.csv           # Generated output (git-ignored)
├── dbt/
│   ├── dbt_project.yml
│   └── models/
│       ├── staging/
│       │   ├── stg_patient_events.sql
│       │   └── sources.yml
│       ├── intermediate/
│       │   └── int_patient_journeys.sql
│       └── marts/
│           ├── fct_funnel_performance.sql
│           ├── fct_patient_cohorts.sql
│           └── fct_adherence_metrics.sql
├── src/
│   ├── funnel.py          # Funnel conversion & leakiest-step analysis
│   ├── cohort.py          # Monthly cohort retention analysis
│   ├── adherence.py       # MPR, PDC, gap-in-therapy metrics
│   └── insights.py        # Auto-generated business insights
├── dashboard/
│   └── app.py             # Streamlit dashboard (5 tabs)
├── requirements.txt
└── README.md
```

---

## 📊 Key Metrics Glossary

| Metric | Definition | Threshold |
|--------|-----------|-----------|
| **MPR** (Medication Possession Ratio) | `days_supply_dispensed ÷ days_in_observation_period` | ≥ 0.80 = adherent |
| **PDC** (Proportion of Days Covered) | MPR capped at 1.0 (no over-counting early refills) | ≥ 0.80 = adherent |
| **Gap in Therapy** | >7 consecutive days without medication supply | Flag for nurse outreach |
| **90-Day Retention** | Patient still engaged in the program at 90 days | Key PSP KPI |
| **Relative Conversion** | % of patients converting from one step to the next | Step-over-step |
| **Absolute Conversion** | % of enrolled patients reaching each step | From enrollment base |

---

## 🔬 Key Findings

*(Numbers from synthetic data — patterns mirror real-world pharma PSP trends)*

1. **Leakiest funnel step: Welcome Call Completed**
   - Only ~60% of enrolled patients complete the welcome call
   - Fixing this step could retain hundreds of additional patients at 90 days

2. **HCP referrals drive the best retention**
   - HCP-referred patients show ~2× better 90-day retention than DTP ad patients
   - HCP education budget delivers the highest ROI per retained patient

3. **Spanish-speaking patients face a digital barrier**
   - ~20%+ higher drop-off at app download and reminder setup steps
   - Adding Spanish-language app support could close this equity gap

4. **Oncology patients have the highest adherence (MPR)**
   - Disease severity drives motivation — oncology MPR significantly exceeds cardiology
   - Cardiology patients (asymptomatic disease) need additional adherence nudges

5. **Gap in therapy is prevalent**
   - A significant proportion of patients experience >7-day medication gaps
   - Proactive nurse outreach before day 25 of each refill cycle is recommended

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- pip

### Installation

```bash
git clone https://github.com/<your-username>/pharma-patient-analytics.git
cd pharma-patient-analytics
pip install -r requirements.txt
```

### Generate Synthetic Data

```bash
python data/generate_synthetic_data.py
```

This creates `data/patient_events.csv` with 150,000 synthetic events.

### Launch Dashboard

```bash
streamlit run dashboard/app.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

### Run Analysis Modules Standalone

```python
from src.funnel import full_funnel_report
from src.cohort import full_cohort_report
from src.adherence import full_adherence_report
from src.insights import generate_insights

funnel = full_funnel_report()
cohort = full_cohort_report()
adherence = full_adherence_report()
insights = generate_insights()
```

---

## 🗄️ dbt Models

The `dbt/models/` directory contains SQL transformation models designed to run on
a warehouse (Snowflake, BigQuery, Redshift, DuckDB). They demonstrate the
transformation logic that would power the production version of this dashboard.

| Model | Layer | Description |
|-------|-------|-------------|
| `stg_patient_events` | Staging | Clean, cast, validate; add `event_sequence_number` |
| `int_patient_journeys` | Intermediate | One row per patient — highest funnel step, days-to-milestone |
| `fct_funnel_performance` | Mart | Daily funnel conversion rates by therapy area & channel |
| `fct_patient_cohorts` | Mart | Monthly cohorts + 30/60/90-day retention |
| `fct_adherence_metrics` | Mart | MPR, PDC, gap-in-therapy per patient |

To run dbt (requires a configured warehouse profile):

```bash
cd dbt
dbt run
dbt test
```

---

## 📈 Dashboard Tabs

| Tab | Content |
|-----|---------|
| **Program Overview** | Funnel chart, enrollment trend, 90-day retention KPI, leakiest step, auto-insights |
| **Adherence Dashboard** | MPR distribution histogram, % adherent by therapy area, gap-in-therapy by cohort |
| **Cohort Retention** | 90-day retention heatmap by enrollment month, best cohort analysis, trend lines |
| **Channel Performance** | HCP referral vs digital vs DTP retention, cost-per-retained-patient comparison, statistical significance |
| **Health Equity Lens** | Language preference retention gap, region analysis, language × region disparity matrix |

---

## 🔄 Adapting to Real Data

To use this with a real patient support program:

1. **Replace synthetic data** with your PSP event stream (same column schema)
2. **Map your events** to the funnel steps in `FUNNEL_STEPS`
3. **Configure dbt** to point to your data warehouse
4. **Adjust thresholds**: MPR threshold, gap-in-therapy days, retention windows
5. **Add PHI safeguards**: ensure all identifiers remain surrogate/hashed

### Required Schema Mapping

| This Project | Your Data |
|-------------|-----------|
| `surrogate_id` | Hashed patient ID (SHA-256 of MRN) |
| `event_name` | Your PSP event taxonomy |
| `event_timestamp` | Event datetime (UTC) |
| `therapy_area` | Therapeutic area / drug brand |
| `acquisition_channel` | Enrollment source |

---

## ⚖️ Regulatory Considerations

### HIPAA Compliance
- This project uses **only synthetic data** with surrogate identifiers
- For production use with real data: implement access controls, audit logging,
  encryption at rest/in transit, minimum necessary access, and BAAs with vendors
- De-identify per HIPAA Safe Harbor (remove all 18 identifiers) or Expert
  Determination method

### FDA Promotional Guidelines
- Patient support programs must not be promotional in nature
- Adherence messaging should focus on physician-directed therapy
- Dashboard insights should be used for **program improvement**, not
  promotional claims
- Consult Legal/Regulatory/Compliance before external sharing

### Data Retention
- Follow your organization's data retention policies
- Implement right-to-delete (patient opt-out) mechanisms
- Maintain audit trail of data access

---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.11 |
| Data manipulation | pandas, numpy |
| Visualization | Plotly, Streamlit |
| Statistical testing | scipy |
| SQL transformations | dbt |
| Data generation | numpy (synthetic, HIPAA-safe) |

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

*Built as a portfolio project demonstrating healthcare analytics engineering.
All data is synthetic. No real patient data was used.*
