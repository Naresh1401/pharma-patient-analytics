"""
Generate 150,000 synthetic pharma patient-support-program events over 6 months.

All data is synthetic and HIPAA-safe.
- surrogate_id = random UUID (no PHI)
- No names, DOBs, addresses, or any HIPAA-covered identifiers.
"""

import uuid
import random
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

# ── reproducibility ──────────────────────────────────────────────────────────
SEED = 42
random.seed(SEED)
np.random.seed(SEED)

# ── configuration ────────────────────────────────────────────────────────────
NUM_PATIENTS = 8_000
TARGET_EVENTS = 150_000
START_DATE = datetime(2025, 7, 1)
END_DATE = datetime(2025, 12, 31)

FUNNEL_STEPS = [
    "program_enrolled",
    "welcome_call_completed",
    "app_downloaded",
    "medication_reminder_set",
    "first_refill_completed",
    "adherence_check_in",
    "program_retained_90d",
]

# Base step-to-step *relative* conversion probabilities (adjusted per segment)
BASE_RELATIVE_CONV = {
    "welcome_call_completed": 0.60,
    "app_downloaded": 0.75,
    "medication_reminder_set": 0.84,
    "first_refill_completed": 0.74,
    "adherence_check_in": 0.71,
    "program_retained_90d": 0.70,
}

THERAPY_AREAS = ["oncology", "cardiology", "neurology"]
THERAPY_WEIGHTS = [0.30, 0.40, 0.30]

CHANNELS = ["hcp_referral", "patient_portal", "insurance_outreach", "tv_dtp_ad"]
CHANNEL_WEIGHTS = [0.35, 0.25, 0.20, 0.20]

DEVICES = ["mobile", "desktop", "ivr_phone"]
DEVICE_WEIGHTS = [0.50, 0.30, 0.20]

REGIONS = ["US Northeast", "US Southeast", "US Midwest", "US West"]
REGION_WEIGHTS = [0.28, 0.25, 0.22, 0.25]

SEGMENTS = ["newly_diagnosed", "treatment_experienced", "caregiver"]
SEGMENT_WEIGHTS = [0.45, 0.35, 0.20]

LANGUAGES = ["English", "Spanish", "other"]
LANGUAGE_WEIGHTS = [0.70, 0.20, 0.10]

PROGRAM_NAMES = [
    "CareConnect Plus",
    "AdherenceFirst",
    "PatientBridge",
]


# ── multiplier helpers (encode the requested domain patterns) ────────────────
def _therapy_multiplier(therapy_area: str, step: str) -> float:
    """Oncology → best retention; Cardiology → worst."""
    base = {"oncology": 1.15, "cardiology": 0.82, "neurology": 1.00}
    # Therapy effect grows in later funnel steps
    step_idx = FUNNEL_STEPS.index(step) if step in FUNNEL_STEPS else 0
    exponent = 1 + step_idx * 0.05
    return base.get(therapy_area, 1.0) ** exponent


def _channel_multiplier(channel: str) -> float:
    """HCP referral = best retention."""
    return {
        "hcp_referral": 1.18,
        "patient_portal": 1.00,
        "insurance_outreach": 0.92,
        "tv_dtp_ad": 0.80,
    }.get(channel, 1.0)


def _language_multiplier(language: str, step: str) -> float:
    """Spanish-speaking → higher drop at digital steps."""
    if language != "Spanish":
        return 1.0
    digital_steps = {"app_downloaded", "medication_reminder_set"}
    return 0.70 if step in digital_steps else 0.90


def _segment_multiplier(segment: str) -> float:
    return {
        "newly_diagnosed": 1.05,
        "treatment_experienced": 1.00,
        "caregiver": 0.90,
    }.get(segment, 1.0)


# ── patient generation ──────────────────────────────────────────────────────
def _generate_patients(n: int) -> pd.DataFrame:
    patients = []
    for _ in range(n):
        patients.append(
            {
                "surrogate_id": str(uuid.uuid4()),
                "therapy_area": np.random.choice(THERAPY_AREAS, p=THERAPY_WEIGHTS),
                "acquisition_channel": np.random.choice(CHANNELS, p=CHANNEL_WEIGHTS),
                "device": np.random.choice(DEVICES, p=DEVICE_WEIGHTS),
                "country_region": np.random.choice(REGIONS, p=REGION_WEIGHTS),
                "patient_segment": np.random.choice(SEGMENTS, p=SEGMENT_WEIGHTS),
                "language_preference": np.random.choice(LANGUAGES, p=LANGUAGE_WEIGHTS),
                "program_name": np.random.choice(PROGRAM_NAMES),
                "enrollment_date": START_DATE
                + timedelta(days=np.random.randint(0, (END_DATE - START_DATE).days)),
            }
        )
    return pd.DataFrame(patients)


# ── event generation ────────────────────────────────────────────────────────
def _generate_events(patients_df: pd.DataFrame) -> pd.DataFrame:
    all_events: list[dict] = []

    for _, pat in patients_df.iterrows():
        ts = pat["enrollment_date"] + timedelta(
            hours=np.random.randint(0, 12),
            minutes=np.random.randint(0, 60),
        )

        # First event: enrolled
        all_events.append(_make_event(pat, "program_enrolled", ts))

        prev_step = "program_enrolled"
        for step in FUNNEL_STEPS[1:]:
            base_conv = BASE_RELATIVE_CONV[step]
            conv = (
                base_conv
                * _therapy_multiplier(pat["therapy_area"], step)
                * _channel_multiplier(pat["acquisition_channel"])
                * _language_multiplier(pat["language_preference"], step)
                * _segment_multiplier(pat["patient_segment"])
            )
            conv = min(conv, 0.98)  # cap

            if np.random.random() > conv:
                # Patient drops — emit disengaged event
                ts += timedelta(
                    days=np.random.randint(1, 15),
                    hours=np.random.randint(0, 24),
                )
                all_events.append(_make_event(pat, "program_disengaged", ts))
                break

            # Patient progresses
            ts += timedelta(
                days=np.random.randint(1, 21),
                hours=np.random.randint(0, 24),
                minutes=np.random.randint(0, 60),
            )
            all_events.append(_make_event(pat, step, ts))

            # Inject some repeatable touch-point events (nurse calls, adherence
            # check-ins) to reach ~150k total events
            if step in ("welcome_call_completed", "adherence_check_in"):
                for _ in range(np.random.randint(1, 4)):
                    ts += timedelta(
                        days=np.random.randint(1, 10),
                        hours=np.random.randint(0, 12),
                    )
                    extra = (
                        "nurse_call_scheduled"
                        if np.random.random() < 0.5
                        else "nurse_call_completed"
                    )
                    all_events.append(_make_event(pat, extra, ts))

            prev_step = step

    return pd.DataFrame(all_events)


def _make_event(pat: pd.Series, event_name: str, ts: datetime) -> dict:
    return {
        "surrogate_id": pat["surrogate_id"],
        "event_name": event_name,
        "event_timestamp": ts,
        "program_name": pat["program_name"],
        "therapy_area": pat["therapy_area"],
        "acquisition_channel": pat["acquisition_channel"],
        "device": pat["device"],
        "country_region": pat["country_region"],
        "patient_segment": pat["patient_segment"],
        "language_preference": pat["language_preference"],
    }


# ── pad or trim to target ───────────────────────────────────────────────────
def _adjust_to_target(events_df: pd.DataFrame, patients_df: pd.DataFrame,
                      target: int) -> pd.DataFrame:
    current = len(events_df)
    if current >= target:
        return events_df.sample(n=target, random_state=SEED).reset_index(drop=True)

    # Need more events — duplicate some repeatable touch-points
    repeatable = events_df[
        events_df["event_name"].isin(
            ["nurse_call_scheduled", "nurse_call_completed", "adherence_check_in"]
        )
    ]
    shortage = target - current
    extra = repeatable.sample(n=shortage, replace=True, random_state=SEED).copy()
    # Jitter timestamps so they aren't exact duplicates
    extra["event_timestamp"] = extra["event_timestamp"] + pd.to_timedelta(
        np.random.randint(1, 72, size=len(extra)), unit="h"
    )
    return pd.concat([events_df, extra], ignore_index=True)


# ── main ────────────────────────────────────────────────────────────────────
def main() -> pd.DataFrame:
    print("Generating patients …")
    patients = _generate_patients(NUM_PATIENTS)

    print("Generating funnel events …")
    events = _generate_events(patients)
    print(f"  Raw events: {len(events):,}")

    events = _adjust_to_target(events, patients, TARGET_EVENTS)
    print(f"  Adjusted to: {len(events):,}")

    events = events.sort_values("event_timestamp").reset_index(drop=True)

    output_path = "data/patient_events.csv"
    events.to_csv(output_path, index=False)
    print(f"  Saved → {output_path}")

    # Quick summary
    print("\n── Event distribution ──")
    print(events["event_name"].value_counts().to_string())
    print(f"\nUnique patients: {events['surrogate_id'].nunique():,}")
    print(f"Date range: {events['event_timestamp'].min()} → {events['event_timestamp'].max()}")
    return events


if __name__ == "__main__":
    main()
