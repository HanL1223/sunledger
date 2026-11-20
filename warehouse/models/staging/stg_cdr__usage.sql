-- CDS EnergyUsageRead. Register suffix E1 = general import, B1 = export (solar feed-in).
with reads as (
    select site_id, {{ json_array("body->'data'->'reads'") }} as r
    from ({{ payloads('cdr', 'usage') }})
)

select
    site_id,
    r->>'servicePointId' as service_point_id,
    cast(r->>'readStartDate' as date) as reading_date,
    r->>'registerSuffix' as register_suffix,
    r->>'readUType' as read_type,
    (r->'intervalRead'->>'readIntervalLength')::integer as interval_minutes,
    (r->'intervalRead'->>'aggregateValue')::double as kwh
from reads
