-- Date spine per site (connection date to as-of) with expected generation from irradiance.
with spine as (
    select
        site_id,
        cast(unnest(generate_series(connected_on, {{ as_of() }}, interval 1 day)) as date) as reading_date
    from {{ ref('stg_registry__sites') }}
)

select
    s.site_id,
    s.reading_date,
    e.site_id is not null as is_reporting,
    w.irradiance_kwh_m2,
    r.pv_kwp * w.irradiance_kwh_m2 * {{ var('reference_pr') }} as expected_pv_kwh,
    e.pv_kwh,
    e.import_kwh,
    e.export_kwh,
    e.charge_kwh,
    e.discharge_kwh,
    e.pv_kwh / nullif(r.pv_kwp * w.irradiance_kwh_m2 * {{ var('reference_pr') }}, 0) as performance_ratio
from spine as s
join {{ ref('stg_registry__sites') }} as r using (site_id)
left join {{ ref('stg_reference__weather') }} as w on w.postcode = r.postcode and w.reading_date = s.reading_date
left join {{ ref('int_daily_energy') }} as e on e.site_id = s.site_id and e.reading_date = s.reading_date
