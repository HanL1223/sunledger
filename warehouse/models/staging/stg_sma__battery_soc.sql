with sets as (
    select site_id, {{ json_array("body->'set'") }} as s
    from ({{ payloads('sma', 'batterysoc') }})
)

select
    site_id,
    cast(left(s->>'time', 10) as date) as reading_date,
    (s->>'batteryStateOfChargeMax')::double as soc_peak_pct,
    (s->>'batteryStateOfChargeMin')::double as soc_trough_pct
from sets
