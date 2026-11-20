-- end_at is epoch seconds; local time uses a fixed AEST offset (demo simplification).
with intervals as (
    select site_id, {{ json_array("body->'intervals'") }} as i
    from ({{ payloads('enphase', 'battery_telemetry') }})
)

select
    site_id,
    make_timestamp(((i->>'end_at')::bigint + 36000) * 1000000) as interval_end_local,
    (i->'charge'->>'enwh')::double as charge_wh,
    (i->'discharge'->>'enwh')::double as discharge_wh,
    (i->'soc'->>'percent')::double as soc_pct,
    (i->'soc'->>'devices_reporting')::integer as devices_reporting
from intervals
