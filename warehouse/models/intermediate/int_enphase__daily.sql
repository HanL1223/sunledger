-- Intervals ending 15:00 cover the charging window; 06:00 closes the previous evening.
with battery as (
    select
        site_id,
        case when hour(interval_end_local) = 15 then cast(interval_end_local as date)
             else cast(interval_end_local as date) - 1 end as reading_date,
        sum(charge_wh) / 1000 as charge_kwh,
        sum(discharge_wh) / 1000 as discharge_kwh,
        max(soc_pct) filter (where hour(interval_end_local) = 15) as soc_peak_pct,
        max(soc_pct) filter (where hour(interval_end_local) = 6) as soc_trough_pct
    from {{ ref('stg_enphase__battery_intervals') }}
    group by all
)

select
    e.site_id,
    e.reading_date,
    'enphase' as source,
    e.pv_kwh,
    e.import_kwh,
    e.export_kwh,
    b.charge_kwh,
    b.discharge_kwh,
    b.soc_peak_pct,
    b.soc_trough_pct,
    cast(null as double) as reported_capacity_kwh
from {{ ref('stg_enphase__energy_daily') }} as e
left join battery as b using (site_id, reading_date)
-- lifetime arrays carry 0 for days with no report; treat those as missing
where b.site_id is not null or e.pv_kwh > 0
