select
    site_id,
    cast(date_trunc('month', reading_date) as date) as month_start,
    median(soh) as soh,
    median(warranty_soh) as warranty_soh,
    median(rte_30d) as rte,
    count(soh) as soh_samples,
    any_value(capacity_method) filter (where capacity_method is not null) as capacity_method
from {{ ref('int_battery_daily') }}
group by all
