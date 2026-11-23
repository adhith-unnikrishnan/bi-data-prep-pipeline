# Data quality report

| Source | Rule | Rows affected |
|---|---|---:|
| store_master | Standardised store_id casing | 5 |
| store_master | Trimmed / title-cased city | 18 |
| product_catalogue | Flattened nested JSON | 25 |
| pos_transactions | Removed exact duplicate rows (re-sent batch) | 798 |
| pos_transactions | Parsed 3 mixed date formats | 80,637 |
| pos_transactions | Unparseable dates dropped | 0 |
| pos_transactions | Stripped £ symbol from prices | 26,196 |
| pos_transactions | Standardised store codes | 3,875 |
| pos_transactions | Standardised channel labels | 3,133 |
| pos_transactions | Dropped non-positive quantities | 142 |
| pos_transactions | Dropped rows with missing SKU | 234 |
| pos_transactions | Missing customer_id kept as 'Guest' | 19,721 |
| returns_log | De-duplicated returns on txn_id+sku | 0 |
| fact_sales | Orphan store_id (no match in store master) | 0 |
| fact_sales | Orphan SKU (no match in catalogue) | 0 |

## Output row counts

- `fact_sales`: 79,463 rows
- `dim_date`: 730 rows
- `dim_store`: 18 rows
- `dim_product`: 25 rows
- `dim_channel`: 3 rows
