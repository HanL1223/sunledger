-- Rule-based fault classification. Each rule records the metric, its threshold and when it began.
with m as (
    select * from {{ ref('int_site_metrics') }}
),

rules as (
    select site_id, 'OFFLINE' as fault_code, 'critical' as severity,
           offline_days as metric_value, 3 as threshold, last_reporting_date + 1 as detected_since
    from m where offline_days >= 3

    union all
    select site_id, 'DATA_GAPS', 'warning', uptime_30d, 0.9, null
    from m where uptime_30d < 0.9 and offline_days < 3

    union all
    select site_id, 'STRING_UNDERPERFORMANCE', case when perf_ratio_60d < 0.70 then 'critical' else 'warning' end,
           perf_ratio_60d, 0.82, low_pr_since
    from m where perf_ratio_60d < 0.82

    union all
    select site_id, 'SEASONAL_SHADING', 'warning', perf_ratio_winter / perf_ratio_summer, 0.85, null
    from m
    where winter_days >= 30 and summer_days >= 30 and perf_ratio_winter / perf_ratio_summer < 0.85

    union all
    select site_id, 'INVERTER_CLIPPING', 'info', pr_high_irradiance / pr_mid_irradiance, 0.92, null
    from m where dc_ac_ratio > {{ var('max_dc_ac_ratio') }} and pr_high_irradiance / pr_mid_irradiance < 0.92

    union all
    select site_id, 'ARRAY_OVERSIZED', 'warning', dc_ac_ratio, {{ var('max_dc_ac_ratio') }}, null
    from m where dc_ac_ratio > {{ var('max_dc_ac_ratio') }}

    union all
    select site_id, 'CAPACITY_BELOW_WARRANTY', 'critical', soh_now - warranty_soh_now, -0.03,
           cast(capacity_breach_month as date)
    from m where soh_now < warranty_soh_now - 0.03

    union all
    select site_id, 'CAPACITY_FADE_ACCELERATED', 'warning', soh_slope_per_year, -0.045, null
    from m
    where soh_now >= warranty_soh_now - 0.03 and soh_slope_per_year < -0.045 and soh_points_365 >= 120

    union all
    select site_id, 'RTE_DEGRADED', case when rte_now < 0.78 then 'critical' else 'warning' end,
           rte_now, 0.82, low_rte_since
    from m where rte_now < 0.82
)

select
    r.site_id,
    r.fault_code,
    r.severity,
    c.category,
    c.title,
    round(r.metric_value, 4) as metric_value,
    r.threshold,
    r.detected_since,
    c.owner_explanation,
    c.installer_action,
    c.warranty_relevant
from rules as r
join {{ ref('fault_catalog') }} as c using (fault_code)
