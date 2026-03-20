/*
    fct_adherence_metrics.sql
    ─────────────────────────
    Refill completion rate, medication possession ratio (MPR),
    proportion of days covered (PDC), and gap-in-therapy flag.

    Industry standard: MPR ≥ 0.80 = adherent.
    Gap in therapy: >7 consecutive days without medication supply.
*/

with journeys as (
    select * from {{ ref('int_patient_journeys') }}
),

events as (
    select * from {{ ref('stg_patient_events') }}
),

-- Simulate days_supply per refill event (30-day supply is standard in pharma)
refill_events as (
    select
        e.surrogate_id,
        e.event_timestamp as refill_date,
        30 as days_supply,  -- standard 30-day prescription fill
        row_number() over (
            partition by e.surrogate_id
            order by e.event_timestamp
        ) as refill_sequence
    from events e
    where e.event_name = 'first_refill_completed'
),

observation_window as (
    select
        j.surrogate_id,
        j.therapy_area,
        j.acquisition_channel,
        j.patient_segment,
        j.language_preference,
        j.program_name,
        j.enrolled_at,
        j.max_funnel_step,
        j.is_disengaged,
        -- Observation period: enrollment to end of study or 180 days
        j.enrolled_at                                              as obs_start,
        j.enrolled_at + interval '180 days'                        as obs_end,
        180                                                        as obs_days
    from journeys j
),

-- MPR = total days_supply / observation_days
mpr_calc as (
    select
        o.surrogate_id,
        o.therapy_area,
        o.acquisition_channel,
        o.patient_segment,
        o.language_preference,
        o.program_name,
        o.max_funnel_step,
        o.is_disengaged,
        o.obs_days,
        coalesce(sum(r.days_supply), 0)                                    as total_days_supply,
        round(coalesce(sum(r.days_supply), 0) * 1.0 / o.obs_days, 4)      as mpr,
        case
            when coalesce(sum(r.days_supply), 0) * 1.0 / o.obs_days >= 0.80
            then 1 else 0
        end                                                                 as is_adherent_mpr,
        -- PDC: capped at observation window
        round(
            least(coalesce(sum(r.days_supply), 0), o.obs_days) * 1.0 / o.obs_days,
            4
        )                                                                   as pdc,
        -- Gap in therapy: if refill missing, assume >7 day gap
        case
            when coalesce(sum(r.days_supply), 0) = 0 then 1
            when o.obs_days - coalesce(sum(r.days_supply), 0) > 7 then 1
            else 0
        end                                                                 as gap_in_therapy_flag
    from observation_window o
    left join refill_events r on o.surrogate_id = r.surrogate_id
    group by
        o.surrogate_id, o.therapy_area, o.acquisition_channel,
        o.patient_segment, o.language_preference, o.program_name,
        o.max_funnel_step, o.is_disengaged, o.obs_days
)

select
    surrogate_id,
    therapy_area,
    acquisition_channel,
    patient_segment,
    language_preference,
    program_name,
    max_funnel_step,
    is_disengaged,
    obs_days,
    total_days_supply,
    mpr,
    is_adherent_mpr,
    pdc,
    gap_in_therapy_flag
from mpr_calc
