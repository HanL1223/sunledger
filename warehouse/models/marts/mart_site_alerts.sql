select
    f.*,
    d.owner_display_name,
    d.installer_id,
    case f.severity when 'critical' then 1 when 'warning' then 2 else 3 end as severity_rank
from {{ ref('int_site_faults') }} as f
join {{ ref('dim_site') }} as d using (site_id)
