{{ config(materialized='view') }}
-- Latest consent event per site and purpose. A view, so revocations apply immediately.
with latest as (
    select *
    from {{ ref('stg_app__consent_events') }}
    qualify row_number() over (partition by site_id, purpose order by event_at desc) = 1
)

select
    s.site_id,
    coalesce(bool_or(l.purpose = 'monitoring' and l.action = 'grant'), false) as monitoring,
    coalesce(bool_or(l.purpose = 'installer_share' and l.action = 'grant'), false) as installer_share,
    coalesce(bool_or(l.purpose = 'benchmark' and l.action = 'grant'), false) as benchmark,
    coalesce(bool_or(l.purpose = 'cdr_meter' and l.action = 'grant'), false) as cdr_meter,
    coalesce(bool_or(l.purpose = 'certificate' and l.action = 'grant'), false) as certificate,
    max(l.recipient) filter (where l.purpose = 'certificate' and l.action = 'grant') as certificate_recipient
from {{ ref('stg_registry__sites') }} as s
left join latest as l using (site_id)
group by s.site_id
