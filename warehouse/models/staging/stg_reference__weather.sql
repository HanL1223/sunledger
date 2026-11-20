select
    cast(postcode as varchar) as postcode,
    cast("date" as date) as reading_date,
    irradiance_kwh_m2
from {{ source('raw', 'weather_daily') }}
