-- live_status captures archived by SunLedger's poller (the endpoint itself has no history).
with captures as (
    select site_id, {{ json_array("body->'captures'") }} as c
    from ({{ payloads('tesla', 'live_status') }})
)

select
    site_id,
    strptime(left(c->>'captured_at', 19), '%Y-%m-%dT%H:%M:%S') as sampled_at,
    (c->'response'->>'percentage_charged')::double as soc_pct,
    (c->'response'->>'energy_left')::double as energy_left_wh,
    (c->'response'->>'total_pack_energy')::double as total_pack_wh,
    c->'response'->>'grid_status' as grid_status
from captures
