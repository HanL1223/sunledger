{{ config(materialized='view') }}
-- Cross-brand battery benchmarks (benchmark-consented sites only, k-anonymity floor).
-- Synthetic builds pseudonymise brands (Brand A = slowest fade) so fake data never names a real OEM.
with cohort as (
    select d.brand, h.*
    from {{ ref('dim_site') }} as d
    join {{ ref('mart_site_health') }} as h using (site_id)
    join {{ ref('int_current_consent') }} as c using (site_id)
    where c.monitoring and c.benchmark
),

agg as (
    select
        brand,
        count(*) as sites,
        median(soh_margin) as median_soh_margin,
        median(soh_slope_per_year) filter (where soh_points_365 >= 120) as median_fade_per_year,
        median(rte_now) as median_rte,
        avg(case when soh_margin < -0.03 then 1.0 else 0.0 end) as below_warranty_rate,
        avg(case when critical_count > 0 then 1.0 else 0.0 end) as critical_rate,
        median(health_score) as median_health_score
    from cohort
    group by brand
)

select
    {% if var('synthetic') %}
    'Brand ' || chr(cast(64 + row_number() over (order by median_fade_per_year desc nulls first, brand) as integer))
    {% else %} brand {% endif %} as brand,
    sites,
    sites < {{ var('min_benchmark_cohort') }} as suppressed,
    case when sites >= {{ var('min_benchmark_cohort') }} then median_soh_margin end as median_soh_margin,
    case when sites >= {{ var('min_benchmark_cohort') }} then median_fade_per_year end as median_fade_per_year,
    case when sites >= {{ var('min_benchmark_cohort') }} then median_rte end as median_rte,
    case when sites >= {{ var('min_benchmark_cohort') }} then below_warranty_rate end as below_warranty_rate,
    case when sites >= {{ var('min_benchmark_cohort') }} then critical_rate end as critical_rate,
    case when sites >= {{ var('min_benchmark_cohort') }} then median_health_score end as median_health_score
from agg
