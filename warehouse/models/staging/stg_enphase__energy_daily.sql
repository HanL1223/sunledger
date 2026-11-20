-- *_lifetime endpoints return one array value (Wh) per day from start_date.
with series as (
    select site_id, 'pv' as measure, cast(body->>'start_date' as date) as start_date,
           cast(body->'production' as double[]) as wh
    from ({{ payloads('enphase', 'energy_lifetime') }})
    union all
    select site_id, 'import', cast(body->>'start_date' as date), cast(body->'import' as double[])
    from ({{ payloads('enphase', 'energy_import_lifetime') }})
    union all
    select site_id, 'export', cast(body->>'start_date' as date), cast(body->'export' as double[])
    from ({{ payloads('enphase', 'energy_export_lifetime') }})
),

exploded as (
    select
        site_id,
        measure,
        start_date + cast(generate_subscripts(wh, 1) - 1 as integer) as reading_date,
        unnest(wh) / 1000 as kwh
    from series
)

select
    site_id,
    reading_date,
    max(kwh) filter (where measure = 'pv') as pv_kwh,
    max(kwh) filter (where measure = 'import') as import_kwh,
    max(kwh) filter (where measure = 'export') as export_kwh
from exploded
group by all
