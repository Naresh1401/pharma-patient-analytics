"""
Pharma Patient Analytics Dashboard
===================================
5-tab Streamlit dashboard for patient support program funnel, adherence,
cohort retention, channel performance, and health equity analysis.

All data is synthetic and HIPAA-safe. No PHI.
Run:  streamlit run dashboard/app.py  (from project root)
"""

from __future__ import annotations

import sys, os

# Ensure project root is on path so src.* imports work
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from src.funnel import (
    load_events,
    build_journeys,
    funnel_conversion,
    time_to_milestone,
    leakiest_step,
    channel_significance,
    FUNNEL_STEPS,
    STEP_LABELS,
)
from src.cohort import (
    retention_matrix,
    channel_retention_curves,
    language_retention_gap,
    language_gap_summary,
    best_cohort,
    assign_cohorts,
)
from src.adherence import (
    build_refill_history,
    calculate_mpr,
    adherence_by_dimension,
    adherence_by_engagement,
    detect_therapy_gaps,
)
from src.insights import generate_insights

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Pharma Patient Analytics",
    page_icon="💊",
    layout="wide",
)

PRIVACY_NOTICE = (
    "⚕️ **Privacy Notice:** All data displayed is **synthetic** and "
    "**HIPAA-safe**. No real patient information (PHI) is used."
)


# ── Data loading (cached) ───────────────────────────────────────────────────
@st.cache_data(show_spinner="Loading synthetic patient events …")
def load_all():
    events = load_events("data/patient_events.csv")
    journeys = build_journeys(events)
    refills = build_refill_history(events, journeys)
    adherence = calculate_mpr(journeys, refills)
    insights = generate_insights(events)
    return events, journeys, refills, adherence, insights


events, journeys, refills, adherence_df, insights_list = load_all()

# ── Sidebar ──────────────────────────────────────────────────────────────────
st.sidebar.title("💊 Pharma Patient Analytics")
st.sidebar.markdown(PRIVACY_NOTICE)
st.sidebar.markdown("---")

therapy_filter = st.sidebar.multiselect(
    "Therapy Area",
    options=sorted(journeys["therapy_area"].dropna().unique()),
    default=sorted(journeys["therapy_area"].dropna().unique()),
)
channel_filter = st.sidebar.multiselect(
    "Acquisition Channel",
    options=sorted(journeys["acquisition_channel"].dropna().unique()),
    default=sorted(journeys["acquisition_channel"].dropna().unique()),
)

# Apply filters
mask = (
    journeys["therapy_area"].isin(therapy_filter)
    & journeys["acquisition_channel"].isin(channel_filter)
)
fj = journeys[mask]  # filtered journeys
fa = adherence_df[adherence_df["surrogate_id"].isin(fj["surrogate_id"])]

# ── Tabs ─────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Program Overview",
    "💊 Adherence Dashboard",
    "📅 Cohort Retention",
    "📡 Channel Performance",
    "⚖️ Health Equity Lens",
])

# ═════════════════════════════════════════════════════════════════════════════
# TAB 1 — Program Overview
# ═════════════════════════════════════════════════════════════════════════════
with tab1:
    st.header("Program Overview")
    st.markdown(PRIVACY_NOTICE)

    # KPI cards
    total_enrolled = len(fj)
    retained_90 = fj["program_retained_90d"].notna().sum()
    retention_rate = retained_90 / total_enrolled if total_enrolled else 0
    median_refill_days = None
    ttm = time_to_milestone(fj)
    refill_row = ttm[ttm["step"] == "first_refill_completed"]
    if len(refill_row):
        median_refill_days = refill_row["median_days"].iloc[0]

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total Enrolled", f"{total_enrolled:,}")
    k2.metric("90-Day Retained", f"{retained_90:,}")
    k3.metric("90-Day Retention Rate", f"{retention_rate:.1%}")
    k4.metric(
        "Median Days to First Refill",
        f"{median_refill_days:.0f}" if median_refill_days else "N/A",
    )

    st.markdown("---")

    # Funnel chart
    conv = funnel_conversion(fj)
    conv["label"] = conv["step"].map(STEP_LABELS)
    fig_funnel = go.Figure(go.Funnel(
        y=conv["label"],
        x=conv["reached"],
        textinfo="value+percent initial",
        marker=dict(color=[
            "#1f77b4", "#2ca02c", "#ff7f0e", "#d62728",
            "#9467bd", "#8c564b", "#17becf",
        ]),
    ))
    fig_funnel.update_layout(
        title="Patient Support Program Funnel",
        height=450,
    )
    st.plotly_chart(fig_funnel, use_container_width=True)

    # Enrollment trend
    enrolled_ts = fj["program_enrolled"].dropna().dt.to_period("W").value_counts().sort_index()
    enrolled_ts.index = enrolled_ts.index.astype(str)
    fig_trend = px.bar(
        x=enrolled_ts.index,
        y=enrolled_ts.values,
        labels={"x": "Week", "y": "Enrollments"},
        title="Weekly Enrollment Trend",
    )
    st.plotly_chart(fig_trend, use_container_width=True)

    # Leakiest step callout
    leak = leakiest_step(fj)
    st.subheader("🔍 Leakiest Step")
    st.info(leak["narrative"])

    # Auto-insights
    st.subheader("💡 Key Insights")
    for ins in insights_list:
        icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(ins["severity"], "⬜")
        st.markdown(f"{icon} **{ins['headline']}** — {ins['detail']}")


# ═════════════════════════════════════════════════════════════════════════════
# TAB 2 — Adherence Dashboard
# ═════════════════════════════════════════════════════════════════════════════
with tab2:
    st.header("Medication Adherence Dashboard")
    st.markdown(PRIVACY_NOTICE)

    stats = fa.describe()
    a1, a2, a3, a4 = st.columns(4)
    a1.metric("Mean MPR", f"{fa['mpr'].mean():.2f}")
    a2.metric("% Adherent (MPR ≥ 0.80)", f"{fa['is_adherent'].mean():.1%}")
    a3.metric("Mean PDC", f"{fa['pdc'].mean():.2f}")
    a4.metric("% With Therapy Gap", f"{fa['gap_in_therapy'].mean():.1%}")

    st.markdown("---")

    # MPR distribution
    fig_mpr = px.histogram(
        fa, x="mpr", nbins=40,
        title="MPR Distribution (≥ 0.80 = Adherent)",
        labels={"mpr": "Medication Possession Ratio"},
        color_discrete_sequence=["#1f77b4"],
    )
    fig_mpr.add_vline(x=0.80, line_dash="dash", line_color="red",
                      annotation_text="Adherence Threshold (0.80)")
    st.plotly_chart(fig_mpr, use_container_width=True)

    # Adherence by therapy area
    by_ta = adherence_by_dimension(fa, "therapy_area")
    fig_ta = px.bar(
        by_ta, x="therapy_area", y="pct_adherent",
        title="% Adherent by Therapy Area",
        labels={"pct_adherent": "% Adherent", "therapy_area": "Therapy Area"},
        color="therapy_area",
        text_auto=".1%",
    )
    st.plotly_chart(fig_ta, use_container_width=True)

    # Gap-in-therapy by cohort
    fa_cohort = fa.merge(
        fj[["surrogate_id", "program_enrolled"]], on="surrogate_id"
    )
    fa_cohort["cohort"] = fa_cohort["program_enrolled"].dt.to_period("M").astype(str)
    gap_cohort = fa_cohort.groupby("cohort")["gap_in_therapy"].mean().reset_index()
    fig_gap = px.bar(
        gap_cohort, x="cohort", y="gap_in_therapy",
        title="Gap-in-Therapy Rate by Enrollment Cohort",
        labels={"gap_in_therapy": "% Patients with Gap", "cohort": "Cohort Month"},
        text_auto=".1%",
    )
    st.plotly_chart(fig_gap, use_container_width=True)


# ═════════════════════════════════════════════════════════════════════════════
# TAB 3 — Cohort Retention
# ═════════════════════════════════════════════════════════════════════════════
with tab3:
    st.header("Cohort Retention Analysis")
    st.markdown(PRIVACY_NOTICE)

    ret_mat = retention_matrix(fj)
    st.subheader("90-Day Retention by Monthly Cohort")

    # Heatmap data
    heatmap_data = ret_mat.pivot_table(
        index="cohort_label",
        values=["retained_30d_rate", "retained_60d_rate", "retained_90d_rate"],
        aggfunc="mean",
    )
    if not heatmap_data.empty:
        heatmap_data.columns = ["30-Day", "60-Day", "90-Day"]
        fig_heat = px.imshow(
            heatmap_data.values,
            x=heatmap_data.columns.tolist(),
            y=heatmap_data.index.tolist(),
            color_continuous_scale="RdYlGn",
            text_auto=".1%",
            title="Retention Rate Heatmap (Monthly Cohorts)",
            labels=dict(color="Retention Rate"),
            aspect="auto",
        )
        fig_heat.update_layout(height=400)
        st.plotly_chart(fig_heat, use_container_width=True)

    # Best cohort
    best = best_cohort(fj)
    st.subheader("🏆 Best-Performing Cohort")
    st.success(best["narrative"])

    # Retention trend
    st.subheader("Retention Trend by Cohort")
    trend = ret_mat[["cohort_label", "retained_30d_rate",
                      "retained_60d_rate", "retained_90d_rate"]].copy()
    trend_melted = trend.melt(
        id_vars="cohort_label", var_name="milestone", value_name="rate"
    )
    trend_melted["milestone"] = trend_melted["milestone"].str.replace("_rate", "").str.replace("retained_", "")
    fig_ret_trend = px.line(
        trend_melted, x="cohort_label", y="rate", color="milestone",
        title="Retention Rate Trend by Milestone",
        labels={"rate": "Retention Rate", "cohort_label": "Cohort Month"},
        markers=True,
    )
    st.plotly_chart(fig_ret_trend, use_container_width=True)


# ═════════════════════════════════════════════════════════════════════════════
# TAB 4 — Channel Performance
# ═════════════════════════════════════════════════════════════════════════════
with tab4:
    st.header("Channel Performance Comparison")
    st.markdown(PRIVACY_NOTICE)

    ch_curves = channel_retention_curves(fj)

    # Channel-level retention
    ch_agg = (
        ch_curves.groupby("acquisition_channel")
        .agg(
            cohort_size=("cohort_size", "sum"),
            retained_30d=("retained_30d", "sum"),
            retained_60d=("retained_60d", "sum"),
            retained_90d=("retained_90d", "sum"),
        )
        .reset_index()
    )
    for col in ["retained_30d", "retained_60d", "retained_90d"]:
        ch_agg[f"{col}_rate"] = ch_agg[col] / ch_agg["cohort_size"]

    # KPI cards per channel
    st.subheader("90-Day Retention by Channel")
    cols = st.columns(len(ch_agg))
    for i, (_, row) in enumerate(ch_agg.iterrows()):
        cols[i].metric(
            row["acquisition_channel"].replace("_", " ").title(),
            f"{row['retained_90d_rate']:.1%}",
            help=f"n = {int(row['cohort_size']):,}",
        )

    # Grouped bar
    ch_melted = ch_agg.melt(
        id_vars="acquisition_channel",
        value_vars=["retained_30d_rate", "retained_60d_rate", "retained_90d_rate"],
        var_name="milestone",
        value_name="rate",
    )
    ch_melted["milestone"] = ch_melted["milestone"].str.replace("_rate", "").str.replace("retained_", "")
    fig_ch = px.bar(
        ch_melted, x="acquisition_channel", y="rate", color="milestone",
        barmode="group",
        title="Retention by Channel & Milestone",
        labels={"rate": "Retention Rate", "acquisition_channel": "Channel"},
        text_auto=".1%",
    )
    st.plotly_chart(fig_ch, use_container_width=True)

    # Cost-per-retained-patient proxy (illustrative)
    st.subheader("Cost per Retained Patient (Illustrative)")
    cost_per_enrolled = {
        "hcp_referral": 250,
        "patient_portal": 40,
        "insurance_outreach": 120,
        "tv_dtp_ad": 350,
    }
    ch_agg["cost_per_enrolled"] = ch_agg["acquisition_channel"].map(cost_per_enrolled)
    ch_agg["cost_per_retained"] = (
        (ch_agg["cost_per_enrolled"] * ch_agg["cohort_size"])
        / ch_agg["retained_90d"].replace(0, np.nan)
    ).round(0)
    fig_cost = px.bar(
        ch_agg, x="acquisition_channel", y="cost_per_retained",
        title="Estimated Cost per 90-Day Retained Patient",
        labels={"cost_per_retained": "Cost ($)", "acquisition_channel": "Channel"},
        text_auto="$,.0f",
        color="acquisition_channel",
    )
    st.plotly_chart(fig_cost, use_container_width=True)

    # Statistical significance
    st.subheader("Statistical Significance — Channel Retention Differences")
    summary_sig, pairs_sig = channel_significance(fj)
    st.dataframe(
        pairs_sig.style.applymap(
            lambda v: "background-color: #d4edda" if v is True else "",
            subset=["significant_005"],
        ),
        use_container_width=True,
    )


# ═════════════════════════════════════════════════════════════════════════════
# TAB 5 — Health Equity Lens
# ═════════════════════════════════════════════════════════════════════════════
with tab5:
    st.header("Health Equity Lens")
    st.markdown(PRIVACY_NOTICE)
    st.markdown(
        "Identifying disparities by **language preference** and **region** "
        "to ensure equitable access to patient support programs."
    )

    # Language retention gap
    st.subheader("Language Preference — 90-Day Retention Gap")
    lang_ret = language_retention_gap(fj)
    lang_agg = (
        lang_ret.groupby("language_preference")
        .agg(
            cohort_size=("cohort_size", "sum"),
            retained_90d=("retained_90d", "sum"),
        )
        .reset_index()
    )
    lang_agg["rate_90d"] = lang_agg["retained_90d"] / lang_agg["cohort_size"]
    fig_lang = px.bar(
        lang_agg, x="language_preference", y="rate_90d",
        title="90-Day Retention by Language Preference",
        labels={"rate_90d": "90-Day Retention Rate", "language_preference": "Language"},
        color="language_preference",
        text_auto=".1%",
    )
    st.plotly_chart(fig_lang, use_container_width=True)

    gap_sum = language_gap_summary(fj)
    st.info(gap_sum["narrative"])

    # Funnel by language — digital step comparison
    st.subheader("Funnel Conversion by Language (Digital Steps)")
    conv_lang = funnel_conversion(fj, "language_preference")
    digital = conv_lang[conv_lang["step"].isin([
        "app_downloaded", "medication_reminder_set"
    ])]
    fig_dig = px.bar(
        digital, x="step", y="abs_conversion", color="language_preference",
        barmode="group",
        title="Digital Step Conversion by Language",
        labels={"abs_conversion": "Conversion Rate", "step": "Funnel Step"},
        text_auto=".1%",
    )
    st.plotly_chart(fig_dig, use_container_width=True)

    # Regional analysis
    st.subheader("Retention by Region")
    # Build region from journeys
    region_data = fj.groupby("country_region").agg(
        enrolled=("surrogate_id", "count"),
        retained_90d=("program_retained_90d", lambda s: s.notna().sum()),
    ).reset_index()
    region_data["rate_90d"] = region_data["retained_90d"] / region_data["enrolled"]
    fig_region = px.bar(
        region_data, x="country_region", y="rate_90d",
        title="90-Day Retention by Region",
        labels={"rate_90d": "90-Day Retention Rate", "country_region": "Region"},
        color="country_region",
        text_auto=".1%",
    )
    st.plotly_chart(fig_region, use_container_width=True)

    # Language × Region cross-tab
    st.subheader("Language × Region: Disparity Matrix")
    cross = fj.groupby(["country_region", "language_preference"]).agg(
        n=("surrogate_id", "count"),
        retained=("program_retained_90d", lambda s: s.notna().sum()),
    ).reset_index()
    cross["rate"] = cross["retained"] / cross["n"]
    cross_pivot = cross.pivot_table(
        index="country_region", columns="language_preference",
        values="rate", aggfunc="mean",
    )
    if not cross_pivot.empty:
        fig_cross = px.imshow(
            cross_pivot.values,
            x=cross_pivot.columns.tolist(),
            y=cross_pivot.index.tolist(),
            color_continuous_scale="RdYlGn",
            text_auto=".1%",
            title="90-Day Retention: Region × Language",
            labels=dict(color="Retention"),
            aspect="auto",
        )
        st.plotly_chart(fig_cross, use_container_width=True)

    # Equity recommendations
    st.subheader("📋 Equity Recommendations")
    equity_insights = [i for i in insights_list if i["category"] == "equity"]
    for ins in equity_insights:
        st.warning(f"**{ins['headline']}** — {ins['detail']}")

    if not equity_insights:
        st.info("No significant equity gaps detected with current filters.")
