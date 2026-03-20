/*
    fct_patient_cohorts.sql
    ───────────────────────
    Monthly enrollment cohorts with 30 / 60 / 90-day retention rates.
*/

with journeys as (
    select * from {{ ref('int_patient_journeys') }}
),

cohort_base as (
    select
        date_trunc('month', enrolled_at)    as cohort_month,
        therapy_area,
        acquisition_channel,
        language_preference,
        patient_segment,
        count(*)                            as cohort_size,

        -- 30-day retention: still active (reached at least refill within 30d)
        count(case when first_refill_at is not null
                    and {{ datediff('enrolled_at', 'first_refill_at', 'day') }} <= 30
              then 1 end)                    as retained_30d,

        -- 60-day retention: adherence check-in within 60d
        count(case when adherence_checkin_at is not null
                    and {{ datediff('enrolled_at', 'adherence_checkin_at', 'day') }} <= 60
              then 1 end)                    as retained_60d,

        -- 90-day retention: reached program_retained_90d
        count(retained_90d_at)               as retained_90d

    from journeys
    group by 1, 2, 3, 4, 5
)

select
    cohort_month,
    therapy_area,
    acquisition_channel,
    language_preference,
    patient_segment,
    cohort_size,
    retained_30d,
    retained_60d,
    retained_90d,
    round(retained_30d * 1.0 / nullif(cohort_size, 0), 4) as retention_rate_30d,
    round(retained_60d * 1.0 / nullif(cohort_size, 0), 4) as retention_rate_60d,
    round(retained_90d * 1.0 / nullif(cohort_size, 0), 4) as retention_rate_90d
from cohort_base
order by cohort_month, therapy_area, acquisition_channel
