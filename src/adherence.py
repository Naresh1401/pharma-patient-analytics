"""
adherence.py — Pharma-specific medication adherence metrics.

Calculates:
  - Medication Possession Ratio (MPR)
  - Proportion of Days Covered (PDC)
  - Gap-in-Therapy detection (>7 days without supply)
  - Adherence rates by therapy area, patient segment, and engagement level

Industry standard: MPR ≥ 0.80 = adherent.
All data is synthetic and HIPAA-safe.
"""

from __future__ import annotations

import pandas as pd
import numpy as np

from src.funnel import FUNNEL_STEPS, build_journeys, load_events


ADHERENT_THRESHOLD = 0.80   # industry-standard MPR threshold
DAYS_SUPPLY_PER_FILL = 30   # standard 30-day prescription
OBSERVATION_DAYS = 180       # 6-month observation window
GAP_THRESHOLD_DAYS = 7       # >7 day gap = non-adherence


# ── Simulate refill history per patient ──────────────────────────────────────
def build_refill_history(events: pd.DataFrame,
                         journeys: pd.DataFrame) -> pd.DataFrame:
    """
    For patients who reached first_refill_completed, simulate subsequent
    refills based on their engagement level (max funnel step reached).
    Higher engagement → more refills → higher MPR.
    """
    # Patients with at least one refill
    refill_patients = journeys[journeys["first_refill_completed"].notna()].copy()
    refill_patients["enrollment_date"] = refill_patients["program_enrolled"]

    records = []
    for _, pat in refill_patients.iterrows():
        max_step = pat["max_step"]
        # Number of refills correlates with engagement depth
        # step_ord: 0=enrolled … 4=first_refill … 5=checkin … 6=retained_90d
        if max_step >= 6:      # retained_90d — highly engaged
            n_refills = np.random.randint(5, 7)   # 150-180 days supply
        elif max_step >= 5:    # adherence_check_in
            n_refills = np.random.randint(3, 6)   # 90-150 days supply
        else:                  # first_refill only
            n_refills = np.random.randint(1, 3)   # 30-60 days supply

        fill_date = pat["first_refill_completed"]
        for i in range(n_refills):
            records.append({
                "surrogate_id": pat["surrogate_id"],
                "fill_date": fill_date,
                "days_supply": DAYS_SUPPLY_PER_FILL,
                "fill_number": i + 1,
            })
            # Next refill with some variance (gap potential)
            gap = np.random.choice(
                [28, 30, 32, 35, 40, 50],  # some gaps are >30 days
                p=[0.25, 0.30, 0.20, 0.10, 0.10, 0.05],
            )
            fill_date = fill_date + pd.Timedelta(days=int(gap))

    return pd.DataFrame(records)


# ── MPR calculation ─────────────────────────────────────────────────────────
def calculate_mpr(journeys: pd.DataFrame,
                  refill_history: pd.DataFrame) -> pd.DataFrame:
    """
    MPR = total_days_supply / observation_days
    For patients with no refills, MPR = 0.
    """
    # Aggregate supply per patient
    supply = (
        refill_history.groupby("surrogate_id")
        .agg(
            total_days_supply=("days_supply", "sum"),
            num_refills=("fill_number", "max"),
        )
        .reset_index()
    )

    # Merge with all patients
    df = journeys[
        ["surrogate_id", "therapy_area", "acquisition_channel",
         "patient_segment", "language_preference", "max_step"]
    ].copy()
    df = df.merge(supply, on="surrogate_id", how="left")
    df["total_days_supply"] = df["total_days_supply"].fillna(0).astype(int)
    df["num_refills"] = df["num_refills"].fillna(0).astype(int)
    df["observation_days"] = OBSERVATION_DAYS

    # MPR (can exceed 1.0 for early refills — capped at 1.0 for PDC)
    df["mpr"] = (df["total_days_supply"] / df["observation_days"]).round(4)
    df["is_adherent"] = (df["mpr"] >= ADHERENT_THRESHOLD).astype(int)

    # PDC: capped at 1.0
    df["pdc"] = df["mpr"].clip(upper=1.0).round(4)

    # Gap in therapy flag
    df["gap_in_therapy"] = (
        (df["observation_days"] - df["total_days_supply"]) > GAP_THRESHOLD_DAYS
    ).astype(int)
    # Patients with 0 supply always flagged
    df.loc[df["total_days_supply"] == 0, "gap_in_therapy"] = 1

    return df


# ── Gap-in-therapy detail ───────────────────────────────────────────────────
def detect_therapy_gaps(refill_history: pd.DataFrame) -> pd.DataFrame:
    """Identify specific gaps > 7 days between consecutive refills."""
    rh = refill_history.sort_values(["surrogate_id", "fill_date"])
    rh["prev_fill_end"] = (
        rh.groupby("surrogate_id")["fill_date"].shift(1)
        + pd.to_timedelta(rh.groupby("surrogate_id")["days_supply"].shift(1), unit="D")
    )
    rh["gap_days"] = (rh["fill_date"] - rh["prev_fill_end"]).dt.days
    gaps = rh[rh["gap_days"] > GAP_THRESHOLD_DAYS].copy()
    return gaps[["surrogate_id", "fill_number", "fill_date", "prev_fill_end", "gap_days"]]


# ── Adherence summary by dimension ──────────────────────────────────────────
def adherence_by_dimension(adherence_df: pd.DataFrame,
                           dim: str) -> pd.DataFrame:
    """Adherence rate, mean MPR, mean PDC grouped by a dimension."""
    return (
        adherence_df.groupby(dim)
        .agg(
            n_patients=("surrogate_id", "count"),
            mean_mpr=("mpr", "mean"),
            median_mpr=("mpr", "median"),
            mean_pdc=("pdc", "mean"),
            pct_adherent=("is_adherent", "mean"),
            pct_gap_in_therapy=("gap_in_therapy", "mean"),
        )
        .round(4)
        .reset_index()
    )


def adherence_by_engagement(adherence_df: pd.DataFrame) -> pd.DataFrame:
    """Adherence by max funnel step reached (engagement proxy)."""
    step_labels = {i: s for i, s in enumerate(FUNNEL_STEPS)}
    df = adherence_df.copy()
    df["engagement_level"] = df["max_step"].map(step_labels)
    return adherence_by_dimension(df, "engagement_level")


# ── Full adherence report ───────────────────────────────────────────────────
def full_adherence_report(events: pd.DataFrame | None = None,
                          data_path: str = "data/patient_events.csv") -> dict:
    if events is None:
        events = load_events(data_path)
    journeys = build_journeys(events)
    refills = build_refill_history(events, journeys)
    adherence = calculate_mpr(journeys, refills)
    gaps = detect_therapy_gaps(refills)

    return {
        "adherence_df": adherence,
        "refill_history": refills,
        "therapy_gaps": gaps,
        "by_therapy_area": adherence_by_dimension(adherence, "therapy_area"),
        "by_channel": adherence_by_dimension(adherence, "acquisition_channel"),
        "by_segment": adherence_by_dimension(adherence, "patient_segment"),
        "by_language": adherence_by_dimension(adherence, "language_preference"),
        "by_engagement": adherence_by_engagement(adherence),
        "overall_stats": {
            "total_patients": len(adherence),
            "patients_with_refill": int((adherence["num_refills"] > 0).sum()),
            "mean_mpr": round(adherence["mpr"].mean(), 4),
            "median_mpr": round(adherence["mpr"].median(), 4),
            "pct_adherent": round(adherence["is_adherent"].mean(), 4),
            "pct_gap_in_therapy": round(adherence["gap_in_therapy"].mean(), 4),
        },
    }
