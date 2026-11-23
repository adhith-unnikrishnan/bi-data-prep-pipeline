# Connecting the output to BI tools

## Power BI Desktop
1. **Get data → Parquet** (or Text/CSV) and load the five files in `output/`.
2. In **Model view**, create one-to-many relationships from each dimension to `fact_sales`:
   `dim_date[date_key]`, `dim_store[store_id]`, `dim_product[sku]`, `dim_channel[channel_key]`.
3. Mark `dim_date` as the date table (Table tools → Mark as date table → `date`).
4. Starter DAX measures:
   ```DAX
   Revenue = SUM(fact_sales[revenue_gbp])
   Gross Margin % = DIVIDE(SUM(fact_sales[gross_margin_gbp]), [Revenue])
   Return Rate = DIVIDE(COUNTROWS(FILTER(fact_sales, fact_sales[is_returned])), COUNTROWS(fact_sales))
   Revenue YoY % = VAR PY = CALCULATE([Revenue], SAMEPERIODLASTYEAR(dim_date[date]))
                   RETURN DIVIDE([Revenue] - PY, PY)
   ```
5. `dim_store[latitude]` / `[longitude]` drive the map visual; set their Data category to Latitude/Longitude.

## Tableau Desktop
1. Connect to the Parquet/CSV files (or to `retail.duckdb` through the DuckDB JDBC driver).
2. In the **logical layer**, drag `fact_sales` first, then relate each dimension on its key.
   Relationships (not joins) keep the right level of detail per table.
3. Starter calculated fields:
   ```
   Gross Margin %   SUM([gross_margin_gbp]) / SUM([revenue_gbp])
   Return Rate      SUM(INT([is_returned])) / COUNT([txn_id])
   ```
4. Geographic role: `latitude`/`longitude` are recognised automatically; `region` can be given
   the *State/Province* role for a filled map.

## Why a star schema
- One fact table at transaction-line grain, small conformed dimensions → fast filters and
  predictable aggregations in both VertiPaq (Power BI) and Hyper (Tableau).
- Measures are defined once in `sql/views.sql`, so dashboards and the
  [conversational BI assistant](https://github.com/adhith-unnikrishnan/conversational-bi-assistant)
  report the same numbers.
