{% macro as_of() -%}
    date '{{ var("as_of") }}'
{%- endmacro %}

{# Payloads for one source endpoint from the raw landing table. #}
{% macro payloads(source_name, endpoint) -%}
    select site_id, params, body
    from {{ source('raw', 'api_payloads') }}
    where source = '{{ source_name }}' and endpoint = '{{ endpoint }}'
{%- endmacro %}

{% macro json_array(expr) -%}
    unnest(cast({{ expr }} as json[]))
{%- endmacro %}
