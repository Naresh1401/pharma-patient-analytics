/*
    fct_funnel_performance.sql
    ──────────────────────────
    Daily funnel conversion rates by therapy_area and acquisition_channel.
    Provides both absolute and step-over-step (relative) conversion.
*/

with journeys as (
    select * from {{ ref('int_patient_journeys') }}
),

daily_enroll as (
    select
        cast(enrolled_at as date)   as report_date,
        therapy_area,
        acquisition_channel,
        count(*)                    as enrolled,
        count(welcome_call_at)      as reached_welcome_call,
        count(app_downloaded_at)    as reached_app_download,
        count(reminder_set_at)      as reached_reminder_set,
        count(first_refill_at)      as reached_first_refill,
        count(adherence_checkin_at) as reached_adherence_checkin,
        count(retained_90d_at)      as reached_retained_90d
    from journeys
    group by 1, 2, 3
)

select
    report_date,
    therapy_area,
    acquisition_channel,
    enrolled,

    -- Absolute conversion rates (from enrollment)
    reached_welcome_call,
    round(reached_welcome_call * 1.0 / nullif(enrolled, 0), 4)          as abs_conv_welcome_call,
    reached_app_download,
    round(reached_app_download * 1.0 / nullif(enrolled, 0), 4)          as abs_conv_app_download,
    reached_reminder_set,
    round(reached_reminder_set * 1.0 / nullif(enrolled, 0), 4)          as abs_conv_reminder_set,
    reached_first_refill,
    round(reached_first_refill * 1.0 / nullif(enrolled, 0), 4)          as abs_conv_first_refill,
    reached_adherence_checkin,
    round(reached_adherence_checkin * 1.0 / nullif(enrolled, 0), 4)     as abs_conv_adherence_checkin,
    reached_retained_90d,
    round(reached_retained_90d * 1.0 / nullif(enrolled, 0), 4)          as abs_conv_retained_90d,

    -- Relative (step-over-step) conversion rates
    round(reached_welcome_call * 1.0 / nullif(enrolled, 0), 4)                      as rel_conv_enroll_to_welcome,
    round(reached_app_download * 1.0 / nullif(reached_welcome_call, 0), 4)          as rel_conv_welcome_to_app,
    round(reached_reminder_set * 1.0 / nullif(reached_app_download, 0), 4)          as rel_conv_app_to_reminder,
    round(reached_first_refill * 1.0 / nullif(reached_reminder_set, 0), 4)          as rel_conv_reminder_to_refill,
    round(reached_adherence_checkin * 1.0 / nullif(reached_first_refill, 0), 4)     as rel_conv_refill_to_checkin,
    round(reached_retained_90d * 1.0 / nullif(reached_adherence_checkin, 0), 4)     as rel_conv_checkin_to_retained

from daily_enroll
order by report_date, therapy_area, acquisition_channel
