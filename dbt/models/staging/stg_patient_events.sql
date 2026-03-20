/*
    stg_patient_events.sql
    ──────────────────────
    Clean, cast, validate raw patient events.
    Adds event_sequence_number per patient ordered by timestamp.
    All data is synthetic — no PHI.
*/

with source as (
    select * from {{ source('raw', 'patient_events') }}
),

cleaned as (
    select
        surrogate_id,
        trim(lower(event_name))                        as event_name,
        cast(event_timestamp as timestamp)             as event_timestamp,
        trim(program_name)                             as program_name,
        trim(lower(therapy_area))                      as therapy_area,
        trim(lower(acquisition_channel))               as acquisition_channel,
        trim(lower(device))                            as device,
        trim(country_region)                           as country_region,
        trim(lower(patient_segment))                   as patient_segment,
        trim(language_preference)                      as language_preference,
        cast(event_timestamp as date)                  as event_date
    from source
    where surrogate_id is not null
      and event_name is not null
      and event_timestamp is not null
),

sequenced as (
    select
        *,
        row_number() over (
            partition by surrogate_id
            order by event_timestamp
        ) as event_sequence_number
    from cleaned
)

select * from sequenced
