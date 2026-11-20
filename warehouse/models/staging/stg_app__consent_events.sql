select
    site_id,
    purpose,
    action,
    recipient,
    cast(event_at as timestamptz) as event_at,
    channel
from {{ source('app', 'consent_events') }}
