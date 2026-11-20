select installer_id, name as installer_name, state as installer_state
from {{ source('raw', 'installers') }}
