/*
    int_patient_journeys.sql
    ────────────────────────
    One row per patient: highest funnel step reached,
    timestamps and days-to-reach for each milestone.
*/

with events as (
    select * from {{ ref('stg_patient_events') }}
),

funnel_steps as (
    -- Map event names to ordinal position in funnel
    select
        surrogate_id,
        event_name,
        event_timestamp,
        therapy_area,
        acquisition_channel,
        device,
        country_region,
        patient_segment,
        language_preference,
        program_name,
        case event_name
            when 'program_enrolled'         then 1
            when 'welcome_call_completed'   then 2
            when 'app_downloaded'            then 3
            when 'medication_reminder_set'   then 4
            when 'first_refill_completed'    then 5
            when 'adherence_check_in'        then 6
            when 'program_retained_90d'      then 7
            when 'program_disengaged'        then -1
            else 0
        end as funnel_step_ordinal
    from events
),

enrollment as (
    select
        surrogate_id,
        min(event_timestamp) as enrollment_ts
    from funnel_steps
    where event_name = 'program_enrolled'
    group by surrogate_id
),

milestones as (
    select
        f.surrogate_id,
        max(f.funnel_step_ordinal)                                    as max_funnel_step,
        min(case when f.event_name = 'program_enrolled'
            then f.event_timestamp end)                               as enrolled_at,
        min(case when f.event_name = 'welcome_call_completed'
            then f.event_timestamp end)                               as welcome_call_at,
        min(case when f.event_name = 'app_downloaded'
            then f.event_timestamp end)                               as app_downloaded_at,
        min(case when f.event_name = 'medication_reminder_set'
            then f.event_timestamp end)                               as reminder_set_at,
        min(case when f.event_name = 'first_refill_completed'
            then f.event_timestamp end)                               as first_refill_at,
        min(case when f.event_name = 'adherence_check_in'
            then f.event_timestamp end)                               as adherence_checkin_at,
        min(case when f.event_name = 'program_retained_90d'
            then f.event_timestamp end)                               as retained_90d_at,
        max(case when f.event_name = 'program_disengaged'
            then 1 else 0 end)                                        as is_disengaged
    from funnel_steps f
    group by f.surrogate_id
),

patient_attrs as (
    select distinct on (surrogate_id)
        surrogate_id,
        therapy_area,
        acquisition_channel,
        device,
        country_region,
        patient_segment,
        language_preference,
        program_name
    from funnel_steps
    order by surrogate_id, event_timestamp
)

select
    m.surrogate_id,
    a.therapy_area,
    a.acquisition_channel,
    a.device,
    a.country_region,
    a.patient_segment,
    a.language_preference,
    a.program_name,
    m.max_funnel_step,
    m.is_disengaged,
    m.enrolled_at,
    m.welcome_call_at,
    m.app_downloaded_at,
    m.reminder_set_at,
    m.first_refill_at,
    m.adherence_checkin_at,
    m.retained_90d_at,
    -- Days to reach each milestone from enrollment
    {{ datediff('m.enrolled_at', 'm.welcome_call_at', 'day') }}    as days_to_welcome_call,
    {{ datediff('m.enrolled_at', 'm.app_downloaded_at', 'day') }}  as days_to_app_download,
    {{ datediff('m.enrolled_at', 'm.reminder_set_at', 'day') }}    as days_to_reminder_set,
    {{ datediff('m.enrolled_at', 'm.first_refill_at', 'day') }}    as days_to_first_refill,
    {{ datediff('m.enrolled_at', 'm.adherence_checkin_at', 'day') }} as days_to_adherence_checkin,
    {{ datediff('m.enrolled_at', 'm.retained_90d_at', 'day') }}    as days_to_retained_90d,
    -- Enrollment cohort (month)
    date_trunc('month', m.enrolled_at)                              as enrollment_cohort
from milestones m
left join patient_attrs a using (surrogate_id)
