-- energyDetails: one series per meter, Wh per day; missing "value" means no data reported.
with meters as (
    select site_id, {{ json_array("body->'energyDetails'->'meters'") }} as meter
    from ({{ payloads('solaredge', 'energy_details') }})
),

readings as (
    select site_id, meter->>'type' as meter_type, {{ json_array("meter->'values'") }} as reading
    from meters
)

select
    site_id,
    cast(left(reading->>'date', 10) as date) as reading_date,
    max(case when meter_type = 'Production' then (reading->>'value')::double end) / 1000 as pv_kwh,
    max(case when meter_type = 'Purchased' then (reading->>'value')::double end) / 1000 as import_kwh,
    max(case when meter_type = 'FeedIn' then (reading->>'value')::double end) / 1000 as export_kwh,
    max(case when meter_type = 'Consumption' then (reading->>'value')::double end) / 1000 as consumption_kwh
from readings
group by all
