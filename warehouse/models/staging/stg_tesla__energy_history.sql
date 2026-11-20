with series as (
    select site_id, {{ json_array("body->'response'->'time_series'") }} as ts
    from ({{ payloads('tesla', 'energy_history') }})
)

select
    site_id,
    cast(left(ts->>'timestamp', 10) as date) as reading_date,
    (ts->>'solar_energy_exported')::double / 1000 as pv_kwh,
    (ts->>'grid_energy_imported')::double / 1000 as import_kwh,
    ((ts->>'grid_energy_exported_from_solar')::double
        + (ts->>'grid_energy_exported_from_battery')::double) / 1000 as export_kwh,
    ((ts->>'battery_energy_imported_from_solar')::double
        + (ts->>'battery_energy_imported_from_grid')::double) / 1000 as charge_kwh,
    (ts->>'battery_energy_exported')::double / 1000 as discharge_kwh
from series
