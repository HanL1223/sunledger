select
    s.site_id,
    s.owner_display_name,
    s.suburb,
    s.postcode,
    s.state,
    s.installer_id,
    i.installer_name,
    s.brand,
    s.battery_model,
    s.battery_units,
    s.battery_usable_kwh,
    s.warranty_years,
    s.warranty_eol_soh,
    s.rte_spec,
    s.pv_kwp,
    s.inverter_kw,
    s.dc_ac_ratio,
    s.install_date,
    s.connected_on,
    {% if var('synthetic') %}
    -- Synthetic builds never pair a real platform name with simulated faults.
    case when c.access = 'owner_oauth' then 'OEM cloud (owner OAuth)' else 'OEM cloud (simulated feed)' end as platform,
    case when c.access = 'owner_oauth' then 'owner_oauth' else 'simulated' end as feed,
    {% else %}
    s.source as platform,
    c.access as feed,
    {% endif %}
    s.install_date >= date '2025-07-01' as rebate_era_install
from {{ ref('stg_registry__sites') }} as s
left join {{ ref('stg_registry__installers') }} as i using (installer_id)
left join {{ ref('stg_registry__connections') }} as c on c.site_id = s.site_id and c.source = s.source
