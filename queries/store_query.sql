-- queries/store_query.sql
-- Produces the STORES table for data/deals.json["stores"]
-- Params substituted by run_extract.py: {{rate_type}} {{date_interval}} {{Start_date}} {{End_date}}
SET session hash_partition_count=64;
SET session hive.security_row_filtering_enabled=true;

with fdscm_base as (
    select fdscm.*, cty.territory from secure_finance.fds_merchant_datamart fdscm
    left join kirby_external_data.usc_territory_city_mapping cty
    on fdscm.city_id = cty.city_id
    where 1=1
        and rate_type = '{{rate_type}}'
        and fdscm.country_name in ('Country - United States')
        and fdscm.lob_code in ('2004')
)

, store_base as (
    select distinct date_trunc('{{date_interval}}', date(fdscm_base.accounting_date)) AS accounting_date,
        country_name, merchant_type_analytics as merchant_type,
        merchant_segment, territory, merchant_uuid
    from fdscm_base
    where DATE(accounting_date) BETWEEN DATE('{{Start_date}}') AND DATE('{{End_date}}')
        and version = 'Actuals'
        and (merchant_segment <> 'SMB' OR merchant_segment IS NULL)
)

, ver_seg_terr as (
    select accounting_date, country_name, merchant_type, merchant_segment, territory, count(DISTINCT merchant_uuid) as active_stores
    from store_base group by 1,2,3,4,5
)
, ver_terr as (
    select accounting_date, country_name, merchant_type, territory, count(DISTINCT merchant_uuid) as active_stores
    from store_base group by 1,2,3,4
)
, seg_terr as (
    select accounting_date, country_name, merchant_segment, territory, count(DISTINCT merchant_uuid) as active_stores
    from store_base group by 1,2,3,4
)
, terr as (
    select accounting_date, country_name, territory, count(DISTINCT merchant_uuid) as active_stores
    from store_base group by 1,2,3
)

, final_output as (
    SELECT accounting_date, country_name, merchant_type, merchant_segment, territory, active_stores, 'ver_terr-seg' AS store_level FROM ver_seg_terr
    UNION ALL
    SELECT accounting_date, country_name, NULL AS merchant_type, merchant_segment, territory, active_stores, 'seg_terr' AS store_level FROM seg_terr
    UNION ALL
    SELECT accounting_date, country_name, merchant_type, NULL AS merchant_segment, territory, active_stores, 'ver_terr' AS store_level FROM ver_terr
    UNION ALL
    SELECT accounting_date, country_name, NULL AS merchant_type, NULL AS merchant_segment, territory, active_stores, 'terr' AS store_level FROM terr
)

SELECT *
FROM (
    SELECT
        accounting_date,
        country_name,
        COALESCE(merchant_type, '*') AS merchant_type,
        COALESCE(merchant_segment, '*') AS merchant_segment,
        territory,
        active_stores,
        store_level
    FROM final_output
) t
ORDER BY t.accounting_date, t.country_name, t.store_level, t.merchant_type, t.merchant_segment, t.territory;
