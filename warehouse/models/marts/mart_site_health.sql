-- Explainable 0-100 health score: weighted components, rescaled over the components with data.
with m as (
    select * from {{ ref('int_site_metrics') }}
),

faults as (
    select
        site_id,
        count(*) filter (where severity = 'critical') as critical_count,
        count(*) filter (where severity = 'warning') as warning_count,
        count(*) filter (where severity = 'info') as info_count
    from {{ ref('int_site_faults') }}
    group by site_id
),

components as (
    select
        m.*,
        coalesce(f.critical_count, 0) as critical_count,
        coalesce(f.warning_count, 0) as warning_count,
        coalesce(f.info_count, 0) as info_count,
        soh_now - warranty_soh_now as soh_margin,
        30 * least(1, greatest(0, (perf_ratio_60d - 0.70) / 0.25)) as generation_points,
        15 * least(1, greatest(0, (rte_now - 0.75) / 0.13)) as efficiency_points,
        30 * least(1, greatest(0, (soh_now - warranty_soh_now + 0.08) / 0.10)) as capacity_points,
        15 * least(1, greatest(0, (uptime_30d - 0.70) / 0.30)) as availability_points,
        greatest(0, 10 - 6 * coalesce(f.critical_count, 0) - 3 * coalesce(f.warning_count, 0)) as fault_points
    from m
    left join faults as f using (site_id)
),

scored as (
    select
        *,
        round(100 * (coalesce(generation_points, 0) + coalesce(capacity_points, 0) + coalesce(efficiency_points, 0)
                     + coalesce(availability_points, 0) + fault_points)
            / (10 + case when generation_points is not null then 30 else 0 end
                  + case when capacity_points is not null then 30 else 0 end
                  + case when efficiency_points is not null then 15 else 0 end
                  + case when availability_points is not null then 15 else 0 end)) as health_score
        from components
)

select
    s.*,
    case when health_score >= 85 then 'A' when health_score >= 70 then 'B' when health_score >= 55 then 'C'
         when health_score >= 40 then 'D' else 'E' end as health_grade
from scored as s
