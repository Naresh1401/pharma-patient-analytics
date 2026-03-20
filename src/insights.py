"""
insights.py — Automated business insights for pharma patient support programs.

Generates natural-language insights with supporting numbers from the
funnel, cohort, and adherence analyses.

All data is synthetic and HIPAA-safe.
"""

from __future__ import annotations

import pandas as pd
import numpy as np

from src.funnel import (
    build_journeys,
    funnel_conversion,
    leakiest_step,
    load_events,
    FUNNEL_STEPS,
    STEP_LABELS,
)
from src.cohort import (
    retention_matrix,
    channel_retention_curves,
    language_gap_summary,
    best_cohort,
)
from src.adherence import (
    build_refill_history,
    calculate_mpr,
    adherence_by_dimension,
    full_adherence_report,
)


def generate_insights(events: pd.DataFrame | None = None,
                      data_path: str = "data/patient_events.csv") -> list[dict]:
    """
    Return a list of insight dicts, each with:
      - category: funnel | cohort | adherence | equity | channel
      - severity: high | medium | low
      - headline: short summary
      - detail: full narrative with numbers
      - metric_value: key number
    """
    if events is None:
        events = load_events(data_path)

    journeys = build_journeys(events)
    insights: list[dict] = []

    # ── 1. Leakiest funnel step ──────────────────────────────────────────
    leak = leakiest_step(journeys)
    insights.append({
        "category": "funnel",
        "severity": "high",
        "headline": f"Leakiest step: {leak['label']}",
        "detail": leak["narrative"],
        "metric_value": leak["drop_off_count"],
    })

    # ── 2. Language equity gap ───────────────────────────────────────────
    lang_gap = language_gap_summary(journeys)
    # Also check the funnel for specific digital-step drop-off
    conv_lang = funnel_conversion(journeys, "language_preference")
    spa_app = conv_lang[
        (conv_lang["language_preference"] == "Spanish")
        & (conv_lang["step"] == "app_downloaded")
    ]
    eng_app = conv_lang[
        (conv_lang["language_preference"] == "English")
        & (conv_lang["step"] == "app_downloaded")
    ]
    spa_app_rate = spa_app["abs_conversion"].iloc[0] if len(spa_app) else 0
    eng_app_rate = eng_app["abs_conversion"].iloc[0] if len(eng_app) else 0
    digital_gap_pct = round((1 - spa_app_rate / eng_app_rate) * 100, 1) if eng_app_rate else 0

    # Estimate recoverable patients
    n_spanish = len(journeys[journeys["language_preference"] == "Spanish"])
    potential_recovered = int(n_spanish * (eng_app_rate - spa_app_rate))

    insights.append({
        "category": "equity",
        "severity": "high",
        "headline": f"Spanish-speaking patients disengage {digital_gap_pct}% more at app download",
        "detail": (
            f"Spanish-speaking patients convert to app download at "
            f"{spa_app_rate:.1%} vs {eng_app_rate:.1%} for English — "
            f"a {digital_gap_pct}% gap. Adding Spanish-language app support "
            f"could retain ~{potential_recovered:,} additional patients through "
            f"the digital onboarding journey."
        ),
        "metric_value": digital_gap_pct,
    })

    # ── 3. HCP referral ROI ──────────────────────────────────────────────
    ch_curves = channel_retention_curves(journeys)
    hcp = ch_curves[ch_curves["acquisition_channel"] == "hcp_referral"]
    dtp = ch_curves[ch_curves["acquisition_channel"] == "tv_dtp_ad"]

    hcp_90 = (
        hcp["retained_90d"].sum() / hcp["cohort_size"].sum()
        if hcp["cohort_size"].sum() > 0 else 0
    )
    dtp_90 = (
        dtp["retained_90d"].sum() / dtp["cohort_size"].sum()
        if dtp["cohort_size"].sum() > 0 else 0
    )
    ratio = round(hcp_90 / dtp_90, 1) if dtp_90 > 0 else 0

    insights.append({
        "category": "channel",
        "severity": "high",
        "headline": f"HCP-referred patients retain {ratio}× better than DTP ad patients",
        "detail": (
            f"HCP-referred patients have {hcp_90:.1%} 90-day retention vs "
            f"{dtp_90:.1%} for DTP ad patients ({ratio}× difference). "
            f"HCP education budget shows the highest ROI per retained patient. "
            f"Consider reallocating DTP ad spend toward HCP engagement programs."
        ),
        "metric_value": ratio,
    })

    # ── 4. Therapy-area adherence comparison ─────────────────────────────
    refills = build_refill_history(events, journeys)
    adherence = calculate_mpr(journeys, refills)
    by_therapy = adherence_by_dimension(adherence, "therapy_area")

    onc = by_therapy[by_therapy["therapy_area"] == "oncology"]
    card = by_therapy[by_therapy["therapy_area"] == "cardiology"]
    onc_mpr = onc["mean_mpr"].iloc[0] if len(onc) else 0
    card_mpr = card["mean_mpr"].iloc[0] if len(card) else 0
    mpr_diff_pct = round((onc_mpr / card_mpr - 1) * 100, 0) if card_mpr else 0

    insights.append({
        "category": "adherence",
        "severity": "medium",
        "headline": f"Oncology MPR is {mpr_diff_pct:.0f}% higher than cardiology",
        "detail": (
            f"Oncology patients have a mean MPR of {onc_mpr:.2f} vs "
            f"{card_mpr:.2f} for cardiology — disease severity drives adherence. "
            f"Cardiology patients (asymptomatic disease, less urgency) may need "
            f"additional adherence nudges like symptom-tracking or risk-score alerts."
        ),
        "metric_value": mpr_diff_pct,
    })

    # ── 5. Best cohort insight ───────────────────────────────────────────
    best = best_cohort(journeys)
    insights.append({
        "category": "cohort",
        "severity": "medium",
        "headline": f"Best cohort: {best['cohort_month']} ({best['retention_90d_rate']:.0%} retention)",
        "detail": best["narrative"],
        "metric_value": best["retention_90d_rate"],
    })

    # ── 6. Retention-to-90d rate (overall KPI) ───────────────────────────
    overall_conv = funnel_conversion(journeys)
    enrolled_n = overall_conv.loc[
        overall_conv["step"] == "program_enrolled", "reached"
    ].iloc[0]
    retained_n = overall_conv.loc[
        overall_conv["step"] == "program_retained_90d", "reached"
    ].iloc[0]
    retention_pct = retained_n / enrolled_n if enrolled_n else 0

    insights.append({
        "category": "funnel",
        "severity": "medium",
        "headline": f"Overall 90-day retention: {retention_pct:.1%}",
        "detail": (
            f"Of {enrolled_n:,} enrolled patients, {retained_n:,} "
            f"({retention_pct:.1%}) remained engaged at 90 days. "
            f"Industry benchmark for patient support programs is 15–20%."
        ),
        "metric_value": retention_pct,
    })

    # ── 7. Gap-in-therapy prevalence ─────────────────────────────────────
    gap_rate = adherence["gap_in_therapy"].mean()
    insights.append({
        "category": "adherence",
        "severity": "medium",
        "headline": f"{gap_rate:.0%} of patients have a gap in therapy",
        "detail": (
            f"{gap_rate:.1%} of patients experienced >7-day gaps between "
            f"refills. Proactive nurse outreach before day 25 of each cycle "
            f"could reduce therapy gaps and improve MPR."
        ),
        "metric_value": round(gap_rate, 4),
    })

    return insights
