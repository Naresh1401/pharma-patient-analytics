"""
cohort.py — Monthly enrollment cohort analysis for pharma patient support programs.

Tracks 30/60/90-day retention by cohort month, acquisition channel,
language sub-cohort, and identifies best-performing cohorts.

All data is synthetic and HIPAA-safe.
"""

from __future__ import annotations

import pandas as pd
import numpy as np

from src.funnel import FUNNEL_STEPS, build_journeys, load_events


# ── Cohort construction ─────────────────────────────────────────────────────
def assign_cohorts(journeys: pd.DataFrame) -> pd.DataFrame:
    """Add cohort_month column based on enrollment date."""
    df = journeys.copy()
    df["cohort_month"] = df["program_enrolled"].dt.to_period("M")
    df["cohort_label"] = df["cohort_month"].astype(str)
    return df


# ── Retention matrix ────────────────────────────────────────────────────────
def retention_matrix(journeys: pd.DataFrame,
                     group_col: str | None = None) -> pd.DataFrame:
    """
    Build a cohort retention matrix.
    Retention milestones:
      30d  → reached first_refill_completed within 30 days
      60d  → reached adherence_check_in within 60 days
      90d  → reached program_retained_90d (any time)
    """
    df = assign_cohorts(journeys)

    grouping = ["cohort_label"]
    if group_col and group_col in df.columns:
        grouping.append(group_col)

    def _days(row, target_col):
        if pd.isna(row.get(target_col)) or pd.isna(row.get("program_enrolled")):
            return None
        return (row[target_col] - row["program_enrolled"]).days

    df["days_to_refill"] = df.apply(
        lambda r: _days(r, "first_refill_completed"), axis=1
    )
    df["days_to_checkin"] = df.apply(
        lambda r: _days(r, "adherence_check_in"), axis=1
    )

    agg = df.groupby(grouping).agg(
        cohort_size=("surrogate_id", "count"),
        retained_30d=("days_to_refill", lambda s: (s.dropna() <= 30).sum()),
        retained_60d=("days_to_checkin", lambda s: (s.dropna() <= 60).sum()),
        retained_90d=("program_retained_90d", lambda s: s.notna().sum()),
    ).reset_index()

    for col in ["retained_30d", "retained_60d", "retained_90d"]:
        agg[f"{col}_rate"] = (agg[col] / agg["cohort_size"]).round(4)

    return agg


# ── Best-performing cohort ──────────────────────────────────────────────────
def best_cohort(journeys: pd.DataFrame) -> dict:
    """Identify which monthly cohort had highest 90-day retention and why."""
    matrix = retention_matrix(journeys)
    # Only consider cohorts with sufficient size
    viable = matrix[matrix["cohort_size"] >= 50]
    if viable.empty:
        return {"cohort": "N/A", "rate": 0, "reason": "Insufficient data"}

    best = viable.loc[viable["retained_90d_rate"].idxmax()]

    # Drill into the best cohort to find dominant channel / therapy
    df = assign_cohorts(journeys)
    cohort_df = df[df["cohort_label"] == best["cohort_label"]]

    top_channel = cohort_df["acquisition_channel"].value_counts().idxmax()
    top_therapy = cohort_df["therapy_area"].value_counts().idxmax()

    channel_share = (
        (cohort_df["acquisition_channel"] == top_channel).mean()
    )

    return {
        "cohort_month": str(best["cohort_label"]),
        "cohort_size": int(best["cohort_size"]),
        "retained_90d": int(best["retained_90d"]),
        "retention_90d_rate": float(best["retained_90d_rate"]),
        "dominant_channel": top_channel,
        "channel_share": round(channel_share, 2),
        "dominant_therapy": top_therapy,
        "narrative": (
            f"The {best['cohort_label']} cohort (n={int(best['cohort_size']):,}) "
            f"achieved {best['retained_90d_rate']:.1%} 90-day retention — "
            f"driven by a high share of {top_channel.replace('_', ' ')} patients "
            f"({channel_share:.0%}) and a {top_therapy} therapy-area mix."
        ),
    }


# ── Channel quality curves ──────────────────────────────────────────────────
def channel_retention_curves(journeys: pd.DataFrame) -> pd.DataFrame:
    """Retention rates at 30/60/90 days broken down by acquisition channel."""
    return retention_matrix(journeys, group_col="acquisition_channel")


# ── Language sub-cohort gap analysis ─────────────────────────────────────────
def language_retention_gap(journeys: pd.DataFrame) -> pd.DataFrame:
    """Compare English vs Spanish retention at each milestone."""
    matrix = retention_matrix(journeys, group_col="language_preference")
    return matrix


def language_gap_summary(journeys: pd.DataFrame) -> dict:
    """Quantify the English vs Spanish 90-day retention gap."""
    matrix = language_retention_gap(journeys)
    eng = matrix[matrix["language_preference"] == "English"]
    spa = matrix[matrix["language_preference"] == "Spanish"]

    eng_rate = (
        eng["retained_90d"].sum() / eng["cohort_size"].sum()
        if eng["cohort_size"].sum() > 0
        else 0
    )
    spa_rate = (
        spa["retained_90d"].sum() / spa["cohort_size"].sum()
        if spa["cohort_size"].sum() > 0
        else 0
    )
    gap_pp = (eng_rate - spa_rate) * 100

    return {
        "english_90d_rate": round(eng_rate, 4),
        "spanish_90d_rate": round(spa_rate, 4),
        "gap_percentage_points": round(gap_pp, 1),
        "narrative": (
            f"English-speaking patients retain at {eng_rate:.1%} vs "
            f"Spanish-speaking at {spa_rate:.1%} at 90 days — "
            f"a {gap_pp:.1f} pp gap. Spanish-language digital tools and "
            f"bilingual nurse support could help close this disparity."
        ),
    }


# ── Full cohort report ──────────────────────────────────────────────────────
def full_cohort_report(events: pd.DataFrame | None = None,
                       data_path: str = "data/patient_events.csv") -> dict:
    if events is None:
        events = load_events(data_path)
    journeys = build_journeys(events)
    return {
        "retention_matrix": retention_matrix(journeys),
        "best_cohort": best_cohort(journeys),
        "channel_curves": channel_retention_curves(journeys),
        "language_gap": language_retention_gap(journeys),
        "language_gap_summary": language_gap_summary(journeys),
        "journeys": journeys,
    }
