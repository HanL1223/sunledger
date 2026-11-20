with sets as (
    select site_id, {{ json_array("body->'set'") }} as s
    from ({{ payloads('sma', 'energybalance') }})
)

select
    site_id,
    cast(left(s->>'time', 10) as date) as reading_date,
    (s->>'pvGeneration')::double / 1000 as pv_kwh,
    (s->>'externalGridConsumption')::double / 1000 as import_kwh,
    (s->>'gridFeedIn')::double / 1000 as export_kwh,
    (s->>'batteryCharging')::double / 1000 as charge_kwh,
    (s->>'batteryDischarging')::double / 1000 as discharge_kwh
from sets
