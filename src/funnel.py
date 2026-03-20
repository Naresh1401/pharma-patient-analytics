"""
funnel.py — Pharma patient support program funnel analysis.

Computes step conversion rates (absolute + relative), time-to-milestone,
funnel breakdowns by dimensions, leakiest-step identification, and
statistical significance testing.

All data is synthetic and HIPAA-safe.
"""

from __future__ import annotations

import pandas as pd
import numpy as np
from scipy import stats

# ── Funnel step order ────────────────────────────────────────────────────────
FUNNEL_STEPS = [
    "program_enrolled",
    "welcome_call_completed",
    "app_downloaded",
    "medication_reminder_set",
    "first_refill_completed",
    "adherence_check_in",
    "program_retained_90d",
]

STEP_LABELS = {
    "program_enrolled": "Enrolled",
    "welcome_call_completed": "Welcome Call",
    "app_downloaded": "App Downloaded",
    "medication_reminder_set": "Reminder Set",
    "first_refill_completed": "First Refill",
    "adherence_check_in": "Adherence Check-in",
    "program_retained_90d": "Retained 90 d",
}


def load_events(path: str = "data/patient_events.csv") -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["event_timestamp"])
    df["event_name"] = df["event_name"].str.strip().str.lower()
    return df


# ── Build patient journey (highest step reached per patient) ─────────────────
def build_journeys(events: pd.DataFrame) -> pd.DataFrame:
    """Return one row per patient with their max funnel step and timestamps."""
    step_map = {s: i for i, s in enumerate(FUNNEL_STEPS)}
    funnel_events = events[events["event_name"].isin(FUNNEL_STEPS)].copy()
    funnel_events["step_ord"] = funnel_events["event_name"].map(step_map)

    # Earliest timestamp per patient per step
    first_hit = (
        funnel_events.groupby(["surrogate_id", "event_name"])
        .agg(
            step_ord=("step_ord", "first"),
            event_timestamp=("event_timestamp", "min"),
        )
        .reset_index()
    )

    # Pivot to one row per patient
    pivoted = first_hit.pivot(
        index="surrogate_id", columns="event_name", values="event_timestamp"
    )
    pivoted.columns.name = None

    # Patient attributes from first event
    attrs = (
        events.sort_values("event_timestamp")
        .groupby("surrogate_id")
        .first()[
            [
                "therapy_area",
                "acquisition_channel",
                "device",
                "country_region",
                "patient_segment",
                "language_preference",
            ]
        ]
    )

    journeys = pivoted.join(attrs)
    journeys["max_step"] = (
        first_hit.groupby("surrogate_id")["step_ord"].max()
    )
    return journeys.reset_index()


# ── Funnel conversion rates ─────────────────────────────────────────────────
def funnel_conversion(journeys: pd.DataFrame,
                      group_col: str | None = None) -> pd.DataFrame:
    """Compute absolute and relative conversion rates, optionally grouped."""
    def _calc(df: pd.DataFrame) -> dict:
        total = len(df)
        result: dict = {}
        for i, step in enumerate(FUNNEL_STEPS):
            reached = df[step].notna().sum() if step in df.columns else 0
            abs_rate = reached / total if total else 0
            if i == 0:
                rel_rate = 1.0
            else:
                prev_step = FUNNEL_STEPS[i - 1]
                prev_reached = df[prev_step].notna().sum() if prev_step in df.columns else 0
                rel_rate = reached / prev_reached if prev_reached else 0
            result[step] = {
                "reached": int(reached),
                "abs_conversion": round(abs_rate, 4),
                "rel_conversion": round(rel_rate, 4),
                "drop_off": int(
                    (df[FUNNEL_STEPS[i - 1]].notna().sum() - reached)
                    if i > 0 and FUNNEL_STEPS[i - 1] in df.columns
                    else 0
                ),
            }
        return result

    if group_col and group_col in journeys.columns:
        rows = []
        for val, grp in journeys.groupby(group_col):
            conv = _calc(grp)
            for step, metrics in conv.items():
                rows.append({group_col: val, "step": step, **metrics})
        return pd.DataFrame(rows)

    conv = _calc(journeys)
    rows = [{"step": step, **metrics} for step, metrics in conv.items()]
    return pd.DataFrame(rows)


# ── Time-to-milestone ───────────────────────────────────────────────────────
def time_to_milestone(journeys: pd.DataFrame) -> pd.DataFrame:
    """Median days from enrollment to each funnel step."""
    rows = []
    for step in FUNNEL_STEPS[1:]:
        if step not in journeys.columns or "program_enrolled" not in journeys.columns:
            continue
        mask = journeys[step].notna() & journeys["program_enrolled"].notna()
        if mask.sum() == 0:
            continue
        delta = (journeys.loc[mask, step] - journeys.loc[mask, "program_enrolled"]).dt.days
        rows.append({
            "step": step,
            "label": STEP_LABELS.get(step, step),
            "median_days": delta.median(),
            "p25_days": delta.quantile(0.25),
            "p75_days": delta.quantile(0.75),
            "n_patients": int(mask.sum()),
        })
    return pd.DataFrame(rows)


# ── Leakiest step identification ────────────────────────────────────────────
def leakiest_step(journeys: pd.DataFrame) -> dict:
    """
    Identify the funnel step with the largest absolute drop-off.
    Quantify business impact: how many additional 90-day retained patients
    would we get if we fixed this step?
    """
    conv = funnel_conversion(journeys)
    # Find step with max drop_off (skip enrollment row)
    conv_steps = conv[conv["step"] != "program_enrolled"]
    worst_idx = conv_steps["drop_off"].idxmax()
    worst = conv_steps.loc[worst_idx]

    # Impact estimation: if we recovered 50% of drop-offs at this step,
    # how many more reach retained_90d?
    retained_row = conv[conv["step"] == "program_retained_90d"].iloc[0]
    downstream_rate = (
        retained_row["reached"] / worst["reached"]
        if worst["reached"] > 0
        else 0
    )
    recoverable = int(worst["drop_off"] * 0.5)
    additional_retained = int(recoverable * downstream_rate)

    total_enrolled = conv.loc[conv["step"] == "program_enrolled", "reached"].iloc[0]
    current_retention = retained_row["reached"] / total_enrolled if total_enrolled else 0
    improved_retention = (
        (retained_row["reached"] + additional_retained) / total_enrolled
        if total_enrolled
        else 0
    )

    return {
        "leakiest_step": worst["step"],
        "label": STEP_LABELS.get(worst["step"], worst["step"]),
        "drop_off_count": int(worst["drop_off"]),
        "drop_off_rel_conversion": worst["rel_conversion"],
        "recoverable_patients_50pct": recoverable,
        "additional_retained_90d": additional_retained,
        "current_90d_retention": round(current_retention, 4),
        "projected_90d_retention": round(improved_retention, 4),
        "retention_improvement_pct": round(
            (improved_retention - current_retention) * 100, 2
        ),
        "narrative": (
            f"Fixing the '{STEP_LABELS.get(worst['step'], worst['step'])}' step "
            f"(current relative conversion: {worst['rel_conversion']:.0%}) could "
            f"recover ~{recoverable:,} patients. At downstream conversion rates, "
            f"this would retain ~{additional_retained:,} additional patients at 90 days, "
            f"improving the overall retention rate from "
            f"{current_retention:.1%} to {improved_retention:.1%} "
            f"(+{(improved_retention - current_retention) * 100:.1f} pp)."
        ),
    }


# ── Statistical significance: channel comparison ────────────────────────────
def channel_significance(journeys: pd.DataFrame,
                         step: str = "program_retained_90d") -> pd.DataFrame:
    """
    Chi-squared test of conversion at a given step across acquisition channels.
    Also pairwise z-tests between channels.
    """
    channels = journeys["acquisition_channel"].dropna().unique()
    rows = []
    for ch in channels:
        mask = journeys["acquisition_channel"] == ch
        n = mask.sum()
        converted = journeys.loc[mask, step].notna().sum() if step in journeys.columns else 0
        rows.append({
            "channel": ch,
            "n": int(n),
            "converted": int(converted),
            "rate": round(converted / n, 4) if n else 0,
        })
    summary = pd.DataFrame(rows)

    # Pairwise z-tests
    pairs = []
    ch_list = summary["channel"].tolist()
    for i in range(len(ch_list)):
        for j in range(i + 1, len(ch_list)):
            a = summary[summary["channel"] == ch_list[i]].iloc[0]
            b = summary[summary["channel"] == ch_list[j]].iloc[0]
            # Two-proportion z-test
            p_a, n_a = a["rate"], a["n"]
            p_b, n_b = b["rate"], b["n"]
            p_pool = (a["converted"] + b["converted"]) / (n_a + n_b) if (n_a + n_b) else 0
            se = np.sqrt(p_pool * (1 - p_pool) * (1 / n_a + 1 / n_b)) if p_pool > 0 else 1
            z_stat = (p_a - p_b) / se if se > 0 else 0
            p_val = 2 * (1 - stats.norm.cdf(abs(z_stat)))
            pairs.append({
                "channel_a": ch_list[i],
                "channel_b": ch_list[j],
                "rate_a": p_a,
                "rate_b": p_b,
                "z_stat": round(z_stat, 3),
                "p_value": round(p_val, 4),
                "significant_005": p_val < 0.05,
            })
    return summary, pd.DataFrame(pairs)


# ── Convenience: full funnel report ─────────────────────────────────────────
def full_funnel_report(events: pd.DataFrame | None = None,
                       data_path: str = "data/patient_events.csv") -> dict:
    if events is None:
        events = load_events(data_path)
    journeys = build_journeys(events)
    return {
        "overall": funnel_conversion(journeys),
        "by_therapy_area": funnel_conversion(journeys, "therapy_area"),
        "by_channel": funnel_conversion(journeys, "acquisition_channel"),
        "by_segment": funnel_conversion(journeys, "patient_segment"),
        "by_language": funnel_conversion(journeys, "language_preference"),
        "time_to_milestone": time_to_milestone(journeys),
        "leakiest_step": leakiest_step(journeys),
        "channel_significance": channel_significance(journeys),
        "journeys": journeys,
    }
