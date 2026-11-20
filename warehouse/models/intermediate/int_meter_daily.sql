-- Smart-meter (CDR) daily totals: an independent check on what the inverter reports.
select
    site_id,
    reading_date,
    sum(kwh) filter (where register_suffix = 'E1') as meter_import_kwh,
    sum(kwh) filter (where register_suffix = 'B1') as meter_export_kwh
from {{ ref('stg_cdr__usage') }}
group by all
