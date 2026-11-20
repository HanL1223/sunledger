-- Simulated bridge feed: partner-gated OEMs (Sigenergy, Alpha ESS, Fronius) and Sungrow (developer portal, app review).
with records as (
    select site_id, source, {{ json_array("body->'records'") }} as r
    from {{ source('raw', 'api_payloads') }}
    where endpoint = 'partner_daily'
)

select
    site_id,
    source as vendor,
    cast(r->>'date' as date) as reading_date,
    (r->>'pv_kwh')::double as pv_kwh,
    (r->>'grid_import_kwh')::double as import_kwh,
    (r->>'grid_export_kwh')::double as export_kwh,
    (r->>'battery_charge_kwh')::double as charge_kwh,
    (r->>'battery_discharge_kwh')::double as discharge_kwh,
    (r->>'soc_max_pct')::double as soc_peak_pct,
    (r->>'soc_min_pct')::double as soc_trough_pct
from records
