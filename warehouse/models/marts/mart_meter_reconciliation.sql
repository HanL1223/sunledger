-- Inverter-reported export vs independent smart-meter export (CDR), plus outage diagnosis.
select
    site_id,
    count(*) filter (where is_reporting and meter_export_kwh is not null) as days_compared,
    sum(export_kwh) filter (where meter_export_kwh is not null) as inverter_export_kwh,
    sum(meter_export_kwh) filter (where is_reporting) as meter_export_kwh,
    sum(export_kwh) filter (where meter_export_kwh is not null)
        / nullif(sum(meter_export_kwh) filter (where is_reporting), 0) - 1 as export_diff_pct,
    count(*) filter (where not is_reporting and meter_export_kwh > 0.5) as outage_days_generating,
    count(*) filter (where not is_reporting and meter_export_kwh <= 0.5) as outage_days_not_generating
from {{ ref('fct_site_daily') }}
where meter_import_kwh is not null
group by site_id
