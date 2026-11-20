with batteries as (
    select site_id, {{ json_array("body->'storageData'->'batteries'") }} as battery
    from ({{ payloads('solaredge', 'storage_data') }})
),

samples as (
    select site_id, battery->>'serialNumber' as serial_number, {{ json_array("battery->'telemetries'") }} as t
    from batteries
)

select
    site_id,
    serial_number,
    strptime(t->>'timeStamp', '%Y-%m-%d %H:%M:%S') as sampled_at,
    (t->>'stateOfCharge')::double as soc_pct,
    (t->>'lifeTimeEnergyCharged')::double as lifetime_charged_wh,
    (t->>'lifeTimeEnergyDischarged')::double as lifetime_discharged_wh,
    (t->>'fullPackEnergyAvailable')::double as full_pack_wh,
    (t->>'internalTemp')::double as internal_temp_c
from samples
