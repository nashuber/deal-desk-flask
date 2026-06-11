-- queries/clean_raw_query.sql
-- Produces the DEALS table for data/deals.json["deals"]
-- Params substituted by run_extract.py: {{rate_type}} {{date_interval}} {{Start_date}} {{End_date}}
SET session hash_partition_count=64;
SET session hive.security_row_filtering_enabled=true;

-- || DYNAMIC CUTOFF LOGIC (Actuals vs Estimates) || --
WITH latest_actual AS (
    SELECT
        DATE_ADD('day', 1, MAX(CASE WHEN version = 'Actuals' THEN DATE(accounting_date) END)) AS cutoff_date
    FROM secure_finance.fds_merchant_datamart
    WHERE 1=1
        AND rate_type = '{{rate_type}}'
        AND country_name IN ('Country - United States', 'Country - Canada')
        AND lob_code IN ('2004')
)

, fdscm_base as (
    select
        fdscm.*,
        cty.territory
    from secure_finance.fds_merchant_datamart fdscm
    left join kirby_external_data.wave_dash_city_mapping cty
        on fdscm.city_id = cty.city_id
    where 1=1
        and rate_type = '{{rate_type}}'
        and fdscm.country_name in ('Country - United States')
        and fdscm.lob_code in ('2004')
)

, fdscm_agg as (
    select
        date_trunc('{{date_interval}}', date(accounting_date)) AS "date"
        , fdscm_base.country_name
        , fdscm_base.merchant_type_analytics as merchant_type
        , fdscm_base.merchant_segment
        , fdscm_base.territory
        , COALESCE(ds.grouped_parent_name, ds.store_name_fixed, fdscm_base.parent_chain_name, 'Unknown') as grouped_parent_name
        , version
        , sum(completed_trips) as trips
        , sum(fares_basket) as basket
        , sum(booking_fees) as booking_fees
        , sum(service_fee) as service_fees
        , sum(other_uber_fees) as other_uber_fees
        , sum(gross_bookings) as gross_bookings
        , SUM(COALESCE(driver_disbursements,0)) AS courier_payment
        , sum(merchant_payments) as resto_payments
        , sum(taxes_fees_disbursed_total) as tf_disbursed
        , sum(coalesce(total_existing_client_incentives,0) + coalesce(merchant_funded_promo_total,0) - coalesce(uber_funded_merchant_promo,0) - coalesce(uber_funded_merchant_promo_contra,0) - coalesce(promotions_price_cut,0)) as EuP
        , sum(coalesce(subscription_pass_revenue, 0) + coalesce(subs_discount, 0)) as pass_net
        , sum(ads_revenue) as ads_rev
        , sum(total_other_revenue) as other_rev
        , sum(net_ufp) as net_ufp
        , sum(netr) as netr
        , sum(trip_insurance) as trip_insurance
        , sum(support) as support
        , sum(money) as money
        , sum(tech) as tech
        , sum(variable_costs) as var_costs
        , sum(variable_contribution) as var_contr
        , sum(other_variable) as other_variable
    from fdscm_base
    left JOIN grdw.dim_storefront ds ON ds.branch_uuid = fdscm_base.merchant_uuid
    CROSS JOIN latest_actual
    where 1=1
        and DATE(accounting_date) BETWEEN DATE('{{Start_date}}') AND DATE('{{End_date}}')
        and (
            (version = 'Actuals' AND DATE(accounting_date) < latest_actual.cutoff_date)
            OR
            (version = 'Estimates' AND DATE(accounting_date) >= latest_actual.cutoff_date)
        )
    group by 1,2,3,4,5,6,7
)

, final_blended_output AS (
    SELECT
        "date"
        , country_name
        , merchant_type
        , merchant_segment
        , grouped_parent_name
        , territory
        , version
        , SUM(trips) AS trips
        , SUM(basket) AS basket
        , SUM(booking_fees) AS booking_fees
        , SUM(service_fees) AS service_fees
        , SUM(other_uber_fees) AS other_uber_fees
        , SUM(gross_bookings) AS gross_bookings
        , SUM(courier_payment) AS courier_payment
        , SUM(resto_payments) AS resto_payments
        , SUM(tf_disbursed) AS tf_disbursed
        , SUM(EuP) AS EuP
        , SUM(pass_net) AS pass_net
        , SUM(ads_rev) AS ads_rev
        , SUM(other_rev) AS other_rev
        , SUM(net_ufp) AS net_ufp
        , SUM(netr) AS netr
        , SUM(trip_insurance) AS trip_insurance
        , SUM(support) AS support
        , SUM(money) AS money
        , SUM(tech) AS tech
        , SUM(var_costs) AS var_costs
        , SUM(var_contr) AS var_contr
        , SUM(other_variable) AS other_variable
    FROM fdscm_agg
    WHERE 1=1
    GROUP BY 1, 2, 3, 4, 5, 6, 7
)

SELECT * FROM final_blended_output
WHERE merchant_segment <> 'SMB' OR merchant_segment IS NULL
ORDER BY 1, 2, 3, 4, 5, 6, 7;
