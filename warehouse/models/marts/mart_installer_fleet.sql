{{ config(materialized='view') }}
-- Installer fleet with triage priority. Only sites whose owner shares with the installer.
with top_fault as (
    select site_id, fault_code, title
    from {{ ref('mart_site_alerts') }}
    qualify row_number() over (partition by site_id order by severity_rank, fault_code) = 1
)

select
    d.installer_id,
    d.installer_name,
    d.site_id,
    d.owner_display_name,
    d.suburb,
    d.state,
    d.brand,
    d.battery_model,
    d.install_date,
    d.platform,
    d.feed,
    h.health_score,
    h.health_grade,
    h.critical_count,
    h.warning_count,
    h.offline_days,
    h.perf_ratio_60d,
    h.soh_margin,
    h.rte_now,
    t.fault_code as top_fault_code,
    t.title as top_fault_title,
    40 * h.critical_count + 15 * h.warning_count + (100 - h.health_score) / 2 as priority_score,
    case when h.critical_count > 0 then 'P1' when h.warning_count > 0 then 'P2' else 'P3' end as priority
from {{ ref('dim_site') }} as d
join {{ ref('mart_site_health') }} as h using (site_id)
join {{ ref('int_current_consent') }} as c using (site_id)
left join top_fault as t using (site_id)
where c.monitoring and c.installer_share
