with captures as (
    select
        site_id,
        case when hour(sampled_at) = 15 then cast(sampled_at as date)
             else cast(sampled_at as date) - 1 end as reading_date,
        max(soc_pct) filter (where hour(sampled_at) = 15) as soc_peak_pct,
        max(soc_pct) filter (where hour(sampled_at) = 6) as soc_trough_pct,
        max(total_pack_wh) filter (where hour(sampled_at) = 15) / 1000 as reported_capacity_kwh
    from {{ ref('stg_tesla__live_status') }}
    group by all
)

select
    e.site_id,
    e.reading_date,
    'tesla' as source,
    e.pv_kwh,
    e.import_kwh,
    e.export_kwh,
    e.charge_kwh,
    e.discharge_kwh,
    c.soc_peak_pct,
    c.soc_trough_pct,
    c.reported_capacity_kwh
from {{ ref('stg_tesla__energy_history') }} as e
left join captures as c using (site_id, reading_date)
