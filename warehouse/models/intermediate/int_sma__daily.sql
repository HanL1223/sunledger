select
    e.site_id,
    e.reading_date,
    'sma' as source,
    e.pv_kwh,
    e.import_kwh,
    e.export_kwh,
    e.charge_kwh,
    e.discharge_kwh,
    s.soc_peak_pct,
    s.soc_trough_pct,
    cast(null as double) as reported_capacity_kwh
from {{ ref('stg_sma__energy_balance') }} as e
left join {{ ref('stg_sma__battery_soc') }} as s using (site_id, reading_date)
