-- One row per site: the windowed metrics that fault rules and the health score are built on.
{% set as_of = as_of() %}

with sites as (
    select * from {{ ref('stg_registry__sites') }}
),

days as (
    select
        *,
        sum(pv_kwh) over w30 / nullif(sum(case when is_reporting then expected_pv_kwh end) over w30, 0) as pr_30d
    from {{ ref('int_site_days') }}
    window w30 as (partition by site_id order by reading_date range between interval 29 day preceding and current row)
),

generation as (
    select
        site_id,
        avg(case when is_reporting then 1.0 else 0.0 end) filter (where reading_date > {{ as_of }} - 30) as uptime_30d,
        max(reading_date) filter (where is_reporting) as last_reporting_date,
        sum(pv_kwh) filter (where reading_date > {{ as_of }} - 60)
            / nullif(sum(expected_pv_kwh) filter (where is_reporting and reading_date > {{ as_of }} - 60), 0)
            as perf_ratio_60d,
        sum(pv_kwh) filter (where reading_date > {{ as_of }} - 365 and month(reading_date) between 5 and 8)
            / nullif(sum(expected_pv_kwh) filter (where is_reporting and reading_date > {{ as_of }} - 365
                                                 and month(reading_date) between 5 and 8), 0) as perf_ratio_winter,
        sum(pv_kwh) filter (where reading_date > {{ as_of }} - 365 and month(reading_date) in (11, 12, 1, 2))
            / nullif(sum(expected_pv_kwh) filter (where is_reporting and reading_date > {{ as_of }} - 365
                                                 and month(reading_date) in (11, 12, 1, 2)), 0) as perf_ratio_summer,
        count(*) filter (where is_reporting and month(reading_date) between 5 and 8) as winter_days,
        count(*) filter (where is_reporting and month(reading_date) in (11, 12, 1, 2)) as summer_days,
        greatest(0, sum(expected_pv_kwh) filter (where is_reporting and reading_date > {{ as_of }} - 365)
            - sum(pv_kwh) filter (where reading_date > {{ as_of }} - 365)) as shortfall_kwh_365,
        -- start of the current run of low 30-day performance (null if currently healthy)
        max(reading_date) filter (where pr_30d >= 0.82) as last_healthy_pr_date,
        min(reading_date) as first_date
    from days
    group by site_id
),

clipping as (
    select
        site_id,
        sum(pv_kwh) filter (where irr_rank >= 0.85) / nullif(sum(expected_pv_kwh) filter (where irr_rank >= 0.85), 0)
            as pr_high_irradiance,
        sum(pv_kwh) filter (where irr_rank between 0.4 and 0.7)
            / nullif(sum(expected_pv_kwh) filter (where irr_rank between 0.4 and 0.7), 0) as pr_mid_irradiance
    from (
        select *, percent_rank() over (partition by site_id order by irradiance_kwh_m2) as irr_rank
        from days
        where is_reporting and reading_date > {{ as_of }} - 365
    )
    group by site_id
),

battery_last as (
    select site_id, max(reading_date) as last_soh_date
    from {{ ref('int_battery_daily') }}
    where soh is not null
    group by site_id
),

battery as (
    select
        b.site_id,
        median(b.soh) filter (where b.reading_date > l.last_soh_date - 45) as soh_now,
        regr_slope(b.soh, b.age_years) filter (where b.reading_date > {{ as_of }} - 365) as soh_slope_per_year,
        count(b.soh) filter (where b.reading_date > {{ as_of }} - 365) as soh_points_365,
        median(b.soh) filter (where b.age_years <= 60 / 365.25) as soh_handover,
        count(b.soh) filter (where b.age_years <= 60 / 365.25) as soh_points_handover,
        min(b.reading_date) filter (where b.soh is not null) as first_soh_date,
        arg_max(b.rte_30d, b.reading_date) as rte_now,
        max(b.reading_date) filter (where b.rte_30d >= 0.82) as last_healthy_rte_date,
        any_value(b.capacity_method) filter (where b.capacity_method is not null) as capacity_method
    from {{ ref('int_battery_daily') }} as b
    join battery_last as l using (site_id)
    group by b.site_id
),

capacity_breach as (
    -- first month whose median SoH sat 3+ points under the warranty line
    select site_id, min(month_start) as capacity_breach_month
    from (
        select site_id, date_trunc('month', reading_date) as month_start,
               median(soh) as soh, median(warranty_soh) as warranty_soh
        from {{ ref('int_battery_daily') }}
        where soh is not null
        group by all
    )
    where soh < warranty_soh - 0.03
    group by site_id
)

select
    s.site_id,
    s.dc_ac_ratio,
    g.uptime_30d,
    g.last_reporting_date,
    date_diff('day', g.last_reporting_date, {{ as_of }}) as offline_days,
    g.perf_ratio_60d,
    g.perf_ratio_winter,
    g.perf_ratio_summer,
    g.winter_days,
    g.summer_days,
    g.shortfall_kwh_365,
    coalesce(g.last_healthy_pr_date + 1, g.first_date) as low_pr_since,
    c.pr_high_irradiance,
    c.pr_mid_irradiance,
    b.soh_now,
    1 - (1 - s.warranty_eol_soh) * (date_diff('day', s.install_date, {{ as_of }}) / 365.25) / s.warranty_years
        as warranty_soh_now,
    b.soh_slope_per_year,
    b.soh_points_365,
    b.soh_handover,
    coalesce(b.soh_handover < {{ var('min_handover_soh') }} and b.soh_points_handover >= 5, false)
        as short_at_handover,
    b.first_soh_date,
    b.capacity_method,
    b.rte_now,
    coalesce(b.last_healthy_rte_date + 1, b.first_soh_date) as low_rte_since,
    cb.capacity_breach_month
from sites as s
left join generation as g using (site_id)
left join clipping as c using (site_id)
left join battery as b using (site_id)
left join capacity_breach as cb using (site_id)
