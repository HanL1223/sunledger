-- Commissioning proof: first 30 days after handover, for sites connected within 14 days of install.
with first30 as (
    select d.*
    from {{ ref('fct_site_daily') }} as d
    join {{ ref('dim_site') }} as s using (site_id)
    where s.connected_on <= s.install_date + 14 and d.reading_date < s.connected_on + 30
)

select
    s.site_id,
    s.installer_id,
    s.install_date,
    s.dc_ac_ratio,
    s.dc_ac_ratio <= {{ var('max_dc_ac_ratio') }} as array_sizing_compliant,
    avg(case when f.is_reporting then 1.0 else 0.0 end) as uptime_first30,
    sum(f.pv_kwh) / nullif(sum(f.expected_pv_kwh) filter (where f.is_reporting), 0) as perf_ratio_first30,
    median(f.soh) as soh_first30,
    arg_max(f.rte_30d, f.reading_date) as rte_first30,
    count(*) filter (where f.is_reporting) as days_reporting
from first30 as f
join {{ ref('dim_site') }} as s using (site_id)
group by all
