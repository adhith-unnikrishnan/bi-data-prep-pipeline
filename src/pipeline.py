"""Blend -> Cleanse -> Enrich -> Model: an Alteryx-style workflow written in Python.

Each step mirrors a tool you'd drag onto an Alteryx canvas (Input, Select,
Data Cleansing, Formula, Join, Unique, Filter, Spatial Info, Output), so the
logic is easy to rebuild in Alteryx, Power Query or Tableau Prep.

Output is a star schema designed for BI tools:
    fact_sales  -> grain: one row per transaction line
    dim_date, dim_store, dim_product, dim_channel
written to DuckDB (for SQL / conversational analytics) and to CSV + Parquet
extracts that Tableau and Power BI load directly.
"""
from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW, OUT = ROOT / "raw", ROOT / "output"

UK_BANK_HOLIDAYS = {  # England & Wales, 2024-2025
    "2024-01-01", "2024-03-29", "2024-04-01", "2024-05-06", "2024-05-27", "2024-08-26",
    "2024-12-25", "2024-12-26", "2025-01-01", "2025-04-18", "2025-04-21", "2025-05-05",
    "2025-05-26", "2025-08-25", "2025-12-25", "2025-12-26",
}


class DQLog:
    """Collects data-quality checks so every rule the pipeline applies is auditable."""

    def __init__(self) -> None:
        self.rows: list[tuple[str, str, int]] = []

    def add(self, source: str, rule: str, affected: int) -> None:
        self.rows.append((source, rule, int(affected)))

    def to_markdown(self) -> str:
        lines = ["| Source | Rule | Rows affected |", "|---|---|---:|"]
        lines += [f"| {s} | {r} | {n:,} |" for s, r, n in self.rows]
        return "\n".join(lines)


# ---------- Input + cleanse ----------

def load_stores(dq: DQLog) -> pd.DataFrame:
    df = pd.read_csv(RAW / "store_master.csv")
    df.columns = [c.lower().replace(" (sqm)", "_sqm").replace(" ", "_") for c in df.columns]
    before = df["store_id"].copy()
    df["store_id"] = df["store_id"].str.strip().str.upper()
    dq.add("store_master", "Standardised store_id casing", (before != df["store_id"]).sum())
    before = df["city"].copy()
    df["city"] = df["city"].str.strip().str.title()
    dq.add("store_master", "Trimmed / title-cased city", (before != df["city"]).sum())
    df["opened"] = pd.to_datetime(df["opened"])
    return df


def load_products(dq: DQLog) -> pd.DataFrame:
    with open(RAW / "product_catalogue.json") as f:
        items = json.load(f)["items"]
    df = pd.json_normalize(items)
    df = df.rename(columns={"attributes.title": "product_name", "attributes.dept": "category",
                            "pricing.list": "list_price_gbp", "pricing.cost": "unit_cost_gbp",
                            "pricing.currency": "currency"})
    dq.add("product_catalogue", "Flattened nested JSON", len(df))
    return df[["sku", "product_name", "category", "list_price_gbp", "unit_cost_gbp"]]


def parse_mixed_dates(s: pd.Series) -> pd.Series:
    out = pd.to_datetime(s, format="%Y-%m-%d", errors="coerce")
    for fmt in ("%d/%m/%Y", "%d-%b-%Y"):
        out = out.fillna(pd.to_datetime(s, format=fmt, errors="coerce"))
    return out


def load_pos(dq: DQLog) -> pd.DataFrame:
    df = pd.read_csv(RAW / "pos_transactions.csv", dtype=str)
    n0 = len(df)
    df = df.drop_duplicates()
    dq.add("pos_transactions", "Removed exact duplicate rows (re-sent batch)", n0 - len(df))

    df["date"] = parse_mixed_dates(df["date"])
    dq.add("pos_transactions", "Parsed 3 mixed date formats", n0)
    bad_dates = df["date"].isna().sum()
    dq.add("pos_transactions", "Unparseable dates dropped", bad_dates)

    has_pound = df["unit_price"].str.startswith("£").sum()
    df["unit_price"] = df["unit_price"].str.replace("£", "", regex=False).astype(float)
    dq.add("pos_transactions", "Stripped £ symbol from prices", has_pound)

    before = df["store"].copy()
    df["store"] = df["store"].str.strip().str.upper()
    dq.add("pos_transactions", "Standardised store codes", (before != df["store"]).sum())

    before = df["channel"].copy()
    df["channel"] = df["channel"].str.strip().str.title().str.replace("& Collect", "& Collect")
    df["channel"] = df["channel"].replace({"Click & collect": "Click & Collect", "In-Store": "In-store"})
    dq.add("pos_transactions", "Standardised channel labels", (before != df["channel"]).sum())

    df["qty"] = df["qty"].astype(int)
    bad_qty = (df["qty"] <= 0).sum()
    missing_sku = df["sku"].isna().sum()
    df = df[(df["qty"] > 0) & df["sku"].notna() & df["date"].notna()]
    dq.add("pos_transactions", "Dropped non-positive quantities", bad_qty)
    dq.add("pos_transactions", "Dropped rows with missing SKU", missing_sku)
    dq.add("pos_transactions", "Missing customer_id kept as 'Guest'", df["customer_id"].isna().sum())
    df["customer_id"] = df["customer_id"].fillna("GUEST")
    return df


def load_returns(dq: DQLog) -> pd.DataFrame:
    df = pd.read_csv(RAW / "returns_log.txt", sep="|")
    n0 = len(df)
    df = df.drop_duplicates(subset=["txn_id", "sku"])
    dq.add("returns_log", "De-duplicated returns on txn_id+sku", n0 - len(df))
    return df


# ---------- Enrich (spatial + formula tools) ----------

def haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def enrich_stores(stores: pd.DataFrame) -> pd.DataFrame:
    """Spatial enrichment: nearest sibling store and how many stores sit within 50 km."""
    nearest, within50 = [], []
    for _, a in stores.iterrows():
        d = [haversine_km(a.latitude, a.longitude, b.latitude, b.longitude)
             for _, b in stores.iterrows() if b.store_id != a.store_id]
        nearest.append(round(min(d), 1))
        within50.append(sum(x <= 50 for x in d))
    stores = stores.copy()
    stores["nearest_store_km"] = nearest
    stores["stores_within_50km"] = within50
    stores["catchment_type"] = np.where(stores["stores_within_50km"] >= 2, "Clustered", "Standalone")
    stores["country"] = stores["region"].map(
        {"Scotland": "Scotland", "Wales": "Wales", "Northern Ireland": "Northern Ireland"}).fillna("England")
    return stores


def build_dim_date(start: date, end: date) -> pd.DataFrame:
    d = pd.DataFrame({"date": pd.date_range(start, end, freq="D")})
    d["date_key"] = d["date"].dt.strftime("%Y%m%d").astype(int)
    d["year"] = d["date"].dt.year
    d["quarter"] = "Q" + d["date"].dt.quarter.astype(str)
    d["month"] = d["date"].dt.month
    d["month_name"] = d["date"].dt.strftime("%b")
    d["iso_week"] = d["date"].dt.isocalendar().week.astype(int)
    d["weekday"] = d["date"].dt.strftime("%a")
    d["is_weekend"] = d["date"].dt.weekday >= 5
    d["is_bank_holiday"] = d["date"].dt.strftime("%Y-%m-%d").isin(UK_BANK_HOLIDAYS)
    # UK retail/fiscal year runs April-March
    d["fiscal_year"] = np.where(d["month"] >= 4, d["year"] + 1, d["year"]).astype(str)
    d["fiscal_year"] = "FY" + d["fiscal_year"].str[-2:]
    return d


# ---------- Model + output ----------

def run() -> dict:
    OUT.mkdir(exist_ok=True)
    dq = DQLog()
    stores = enrich_stores(load_stores(dq))
    products = load_products(dq)
    pos = load_pos(dq)
    returns = load_returns(dq)

    # Join tool: flag returned lines
    returns["is_returned"] = True
    fact = pos.merge(returns[["txn_id", "sku", "is_returned", "reason"]], on=["txn_id", "sku"], how="left")
    fact["is_returned"] = fact["is_returned"].astype("boolean").fillna(False).astype(bool)
    fact = fact.rename(columns={"reason": "return_reason", "store": "store_id"})

    # Referential integrity checks (the Join tool's L/R outputs)
    orphan_store = ~fact["store_id"].isin(stores["store_id"])
    orphan_sku = ~fact["sku"].isin(products["sku"])
    dq.add("fact_sales", "Orphan store_id (no match in store master)", orphan_store.sum())
    dq.add("fact_sales", "Orphan SKU (no match in catalogue)", orphan_sku.sum())
    fact = fact[~orphan_store & ~orphan_sku]

    # Formula tool: measures
    fact = fact.merge(products[["sku", "unit_cost_gbp", "list_price_gbp"]], on="sku")
    fact["revenue_gbp"] = (fact["qty"] * fact["unit_price"]).round(2)
    fact["cost_gbp"] = (fact["qty"] * fact["unit_cost_gbp"]).round(2)
    fact["gross_margin_gbp"] = (fact["revenue_gbp"] - fact["cost_gbp"]).round(2)
    fact["discount_gbp"] = (fact["qty"] * (fact["list_price_gbp"] - fact["unit_price"])).round(2)
    fact["date_key"] = fact["date"].dt.strftime("%Y%m%d").astype(int)

    channels = pd.DataFrame({"channel": sorted(fact["channel"].unique())})
    channels["channel_key"] = range(1, len(channels) + 1)
    channels["is_digital"] = channels["channel"] != "In-store"
    fact = fact.merge(channels[["channel", "channel_key"]], on="channel")

    fact_sales = fact[["txn_id", "date_key", "store_id", "sku", "channel_key", "customer_id", "qty",
                       "unit_price", "revenue_gbp", "cost_gbp", "gross_margin_gbp", "discount_gbp",
                       "is_returned", "return_reason"]].sort_values(["date_key", "txn_id"])
    dim_date = build_dim_date(fact["date"].min().date(), fact["date"].max().date())
    dim_store = stores.rename(columns={"opened": "opened_date"})
    dim_product = products.copy()
    dim_product["margin_pct"] = ((1 - dim_product["unit_cost_gbp"] / dim_product["list_price_gbp"]) * 100).round(1)

    tables = {"fact_sales": fact_sales, "dim_date": dim_date, "dim_store": dim_store,
              "dim_product": dim_product, "dim_channel": channels}

    # Output tool: DuckDB + BI extracts
    db_path = OUT / "retail.duckdb"
    db_path.unlink(missing_ok=True)
    con = duckdb.connect(str(db_path))
    for name, df in tables.items():
        con.register("tmp", df)
        con.execute(f"CREATE TABLE {name} AS SELECT * FROM tmp")
        con.unregister("tmp")
        df.to_csv(OUT / f"{name}.csv", index=False)
        df.to_parquet(OUT / f"{name}.parquet", index=False)
    con.execute((ROOT / "sql" / "views.sql").read_text())
    con.close()

    report = ["# Data quality report", "", dq.to_markdown(), "", "## Output row counts", ""]
    report += [f"- `{k}`: {len(v):,} rows" for k, v in tables.items()]
    (OUT / "data_quality_report.md").write_text("\n".join(report) + "\n")
    print("\n".join(report))
    return tables


if __name__ == "__main__":
    run()
