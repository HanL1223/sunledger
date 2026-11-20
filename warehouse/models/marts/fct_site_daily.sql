select
    d.site_id,
    d.reading_date,
    d.is_reporting,
    d.irradiance_kwh_m2,
    d.expected_pv_kwh,
    d.pv_kwh,
    d.import_kwh,
    d.export_kwh,
    d.charge_kwh,
    d.discharge_kwh,
    d.performance_ratio,
    b.soh,
    b.warranty_soh,
    b.capacity_method,
    b.rte_30d,
    m.meter_import_kwh,
    m.meter_export_kwh
from {{ ref('int_site_days') }} as d
left join {{ ref('int_battery_daily') }} as b using (site_id, reading_date)
left join {{ ref('int_meter_daily') }} as m using (site_id, reading_date)
