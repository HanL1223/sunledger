-- Battery State-of-Health per day. Capacity is OEM-reported where the API exposes it,
-- otherwise estimated from discharged energy over the SoC swing on deep-cycle days.
with daily as (
    select
        e.site_id,
        e.reading_date,
        e.charge_kwh,
        e.discharge_kwh,
        e.soc_peak_pct,
        e.soc_trough_pct,
        e.reported_capacity_kwh,
        s.battery_usable_kwh,
        s.warranty_years,
        s.warranty_eol_soh,
        date_diff('day', s.install_date, e.reading_date) / 365.25 as age_years,
        sum(e.discharge_kwh) over w30 / nullif(sum(e.charge_kwh) over w30, 0) as rte_30d
    from {{ ref('int_daily_energy') }} as e
    join {{ ref('stg_registry__sites') }} as s using (site_id)
    window w30 as (partition by e.site_id order by e.reading_date
                   range between interval 29 day preceding and current row)
),

estimated as (
    select
        *,
        case when soc_peak_pct - soc_trough_pct >= {{ var('min_soc_swing_pct') }} and rte_30d between 0.5 and 1.0
             then discharge_kwh / sqrt(rte_30d) / ((soc_peak_pct - soc_trough_pct) / 100) end as estimated_capacity_kwh
    from daily
)

select
    site_id,
    reading_date,
    age_years,
    charge_kwh,
    discharge_kwh,
    rte_30d,
    coalesce(reported_capacity_kwh, estimated_capacity_kwh) as capacity_kwh,
    case when reported_capacity_kwh is not null then 'oem_reported'
         when estimated_capacity_kwh is not null then 'estimated' end as capacity_method,
    coalesce(reported_capacity_kwh, estimated_capacity_kwh) / battery_usable_kwh as soh,
    1 - (1 - warranty_eol_soh) * age_years / warranty_years as warranty_soh
from estimated
