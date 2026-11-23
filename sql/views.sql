-- Semantic-layer views: business-friendly, pre-joined shapes for BI tools and
-- the conversational analytics assistant. Measures are defined once here so
-- every dashboard reports the same numbers.

CREATE OR REPLACE VIEW v_sales AS
SELECT f.txn_id, d.date, d.year, d.quarter, d.month, d.month_name, d.fiscal_year, d.iso_week,
       d.is_weekend, d.is_bank_holiday,
       s.store_id, s.store_name, s.city, s.region, s.country, s.latitude, s.longitude, s.catchment_type,
       p.sku, p.product_name, p.category,
       c.channel, c.is_digital,
       f.customer_id, f.qty, f.unit_price, f.revenue_gbp, f.cost_gbp, f.gross_margin_gbp,
       f.discount_gbp, f.is_returned, f.return_reason
FROM fact_sales f
JOIN dim_date d    ON f.date_key = d.date_key
JOIN dim_store s   ON f.store_id = s.store_id
JOIN dim_product p ON f.sku = p.sku
JOIN dim_channel c ON f.channel_key = c.channel_key;

CREATE OR REPLACE VIEW v_store_month AS
SELECT store_id, store_name, region, latitude, longitude,
       date_trunc('month', date) AS month,
       SUM(revenue_gbp) AS revenue_gbp,
       SUM(gross_margin_gbp) AS gross_margin_gbp,
       COUNT(DISTINCT txn_id) AS transactions,
       AVG(CASE WHEN is_returned THEN 1 ELSE 0 END) AS return_rate
FROM v_sales GROUP BY ALL;
