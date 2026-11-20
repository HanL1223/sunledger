select connection_id, site_id, source, access, external_id
from {{ source('raw', 'connections') }}
