-- Counters are cumulative: charge = delta of consecutive 15:00 samples; discharge = delta of
-- consecutive 06:00 samples, keyed to the evening they close (sample date - 1).
with telemetry as (
    select * from {{ ref('stg_solaredge__storage_telemetry') }}
),

peaks as (
    select
        site_id,
        cast(sampled_at as date) as reading_date,
        soc_pct as soc_peak_pct,
        full_pack_wh / 1000 as reported_capacity_kwh,
        case when lag(cast(sampled_at as date)) over w = cast(sampled_at as date) - 1
             then (lifetime_charged_wh - lag(lifetime_charged_wh) over w) / 1000 end as charge_kwh
    from telemetry
    where hour(sampled_at) = 15
    window w as (partition by site_id order by sampled_at)
),

troughs as (
    select
        site_id,
        cast(sampled_at as date) - 1 as reading_date,
        soc_pct as soc_trough_pct,
        case when lag(cast(sampled_at as date)) over w = cast(sampled_at as date) - 1
             then (lifetime_discharged_wh - lag(lifetime_discharged_wh) over w) / 1000 end as discharge_kwh
    from telemetry
    where hour(sampled_at) = 6
    window w as (partition by site_id order by sampled_at)
),

energy as (
    select * from {{ ref('stg_solaredge__energy_details') }} where pv_kwh is not null
)

select
    e.site_id,
    e.reading_date,
    'solaredge' as source,
    e.pv_kwh,
    e.import_kwh,
    e.export_kwh,
    p.charge_kwh,
    t.discharge_kwh,
    p.soc_peak_pct,
    t.soc_trough_pct,
    p.reported_capacity_kwh
from energy as e
left join peaks as p using (site_id, reading_date)
left join troughs as t using (site_id, reading_date)
