-- Canonical daily energy record: one row per site per reporting day, any source.
{% set sources = ['int_solaredge__daily', 'int_enphase__daily', 'int_tesla__daily', 'int_sma__daily'] %}

with unioned as (
    {% for model in sources %}
    select * from {{ ref(model) }}
    union all
    {% endfor %}
    select
        site_id, reading_date, vendor as source, pv_kwh, import_kwh, export_kwh,
        charge_kwh, discharge_kwh, soc_peak_pct, soc_trough_pct, cast(null as double) as reported_capacity_kwh
    from {{ ref('stg_partner__daily') }}
)

select
    u.*,
    c.access
from unioned as u
left join {{ ref('stg_registry__connections') }} as c
    on c.site_id = u.site_id and c.source = u.source
where u.reading_date <= {{ as_of() }}
