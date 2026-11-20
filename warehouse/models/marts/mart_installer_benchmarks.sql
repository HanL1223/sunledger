{{ config(materialized='view') }}
-- De-identified installer benchmarks from benchmark-consented sites; cohorts under k are suppressed.
with cohort as (
    select
        d.installer_id,
        d.installer_name,
        d.state,
        h.*,
        exists (
            select 1 from {{ ref('int_site_faults') }} as f
            where f.site_id = h.site_id
              and f.fault_code in ('STRING_UNDERPERFORMANCE', 'SEASONAL_SHADING', 'ARRAY_OVERSIZED')
        ) as has_install_fault
    from {{ ref('dim_site') }} as d
    join {{ ref('mart_site_health') }} as h using (site_id)
    join {{ ref('int_current_consent') }} as c using (site_id)
    where c.monitoring and c.benchmark
),

agg as (
    select
        installer_id,
        installer_name,
        state,
        count(*) as sites,
        median(health_score) as median_health_score,
        median(perf_ratio_60d) as median_perf_ratio,
        avg(case when has_install_fault then 1.0 else 0.0 end) as install_fault_rate,
        median(soh_margin) as median_soh_margin,
        avg(uptime_30d) as avg_uptime
    from cohort
    group by all
)

select
    installer_id,
    installer_name,
    state,
    sites,
    sites < {{ var('min_benchmark_cohort') }} as suppressed,
    case when sites >= {{ var('min_benchmark_cohort') }} then median_health_score end as median_health_score,
    case when sites >= {{ var('min_benchmark_cohort') }} then median_perf_ratio end as median_perf_ratio,
    case when sites >= {{ var('min_benchmark_cohort') }} then install_fault_rate end as install_fault_rate,
    case when sites >= {{ var('min_benchmark_cohort') }} then median_soh_margin end as median_soh_margin,
    case when sites >= {{ var('min_benchmark_cohort') }} then avg_uptime end as avg_uptime
from agg
