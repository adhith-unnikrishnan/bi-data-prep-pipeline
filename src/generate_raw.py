"""Generate deliberately messy raw source files for a fictional UK retail chain.

The point of this project is data *preparation*, so the raw files imitate what
real source systems hand you: three different formats, inconsistent date and
currency formats, duplicate rows, stray whitespace, mixed-case codes, missing
values and a few impossible records.

All data is synthetic (seeded, reproducible). No real company or customer data.
"""
from __future__ import annotations

import json
import random
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
RAW = Path(__file__).resolve().parents[1] / "raw"

# (store_id, name, city, region, lat, lon, opened, size_sqm)
STORES = [
    ("S001", "Oxford Street", "London", "London", 51.5154, -0.1418, "2016-03-01", 1400),
    ("S002", "Canary Wharf", "London", "London", 51.5054, -0.0235, "2018-09-15", 950),
    ("S003", "Stratford", "London", "London", 51.5430, -0.0090, "2019-05-20", 1100),
    ("S004", "Manchester Arndale", "Manchester", "North West", 53.4840, -2.2390, "2015-11-01", 1300),
    ("S005", "Liverpool ONE", "Liverpool", "North West", 53.4040, -2.9870, "2017-04-10", 1000),
    ("S006", "Bullring", "Birmingham", "West Midlands", 52.4770, -1.8940, "2016-08-01", 1250),
    ("S007", "Trinity Leeds", "Leeds", "Yorkshire and the Humber", 53.7960, -1.5440, "2018-02-14", 900),
    ("S008", "Meadowhall", "Sheffield", "Yorkshire and the Humber", 53.4140, -1.4120, "2020-10-01", 850),
    ("S009", "Cabot Circus", "Bristol", "South West", 51.4590, -2.5840, "2017-06-01", 980),
    ("S010", "St David's", "Cardiff", "Wales", 51.4790, -3.1750, "2019-03-03", 870),
    ("S011", "Princes Street", "Edinburgh", "Scotland", 55.9530, -3.1960, "2016-12-01", 1050),
    ("S012", "Buchanan Galleries", "Glasgow", "Scotland", 55.8640, -4.2520, "2018-07-07", 1150),
    ("S013", "Eldon Square", "Newcastle", "North East", 54.9750, -1.6140, "2021-04-12", 800),
    ("S014", "Victoria Centre", "Nottingham", "East Midlands", 52.9560, -1.1480, "2019-09-09", 920),
    ("S015", "Grand Arcade", "Cambridge", "East of England", 52.2040, 0.1200, "2022-05-01", 700),
    ("S016", "Westquay", "Southampton", "South East", 50.9020, -1.4060, "2020-02-20", 890),
    ("S017", "Churchill Square", "Brighton", "South East", 50.8240, -0.1460, "2021-11-11", 760),
    ("S018", "Victoria Square", "Belfast", "Northern Ireland", 54.5990, -5.9280, "2022-09-01", 820),
]

CATEGORIES = {
    "Electronics": [("Wireless Earbuds", 59.99), ("Smart Speaker", 89.0), ("USB-C Charger", 19.99),
                    ("Bluetooth Keyboard", 44.5), ("4K Streaming Stick", 39.99)],
    "Home": [("Scented Candle", 12.0), ("Linen Cushion", 24.0), ("Ceramic Vase", 32.0),
             ("Throw Blanket", 45.0), ("Desk Lamp", 38.0)],
    "Grocery": [("Ground Coffee 500g", 7.5), ("Loose Leaf Tea", 5.25), ("Dark Chocolate", 2.8),
                ("Olive Oil 1L", 9.99), ("Granola", 4.6)],
    "Health & Beauty": [("Face Serum", 22.0), ("Hand Cream", 8.5), ("Shampoo", 6.75),
                        ("Electric Toothbrush", 49.99), ("Sun Cream SPF50", 11.0)],
    "Clothing": [("Cotton T-Shirt", 15.0), ("Denim Jeans", 49.0), ("Wool Jumper", 65.0),
                 ("Rain Jacket", 79.0), ("Trainers", 70.0)],
}
CHANNELS = ["In-store", "Click & Collect", "Online"]


def _products() -> list[dict]:
    out, n = [], 1
    for cat, items in CATEGORIES.items():
        for name, price in items:
            out.append({
                "sku": f"P{n:03d}",
                "name": name,
                "category": cat,
                "list_price_gbp": price,
                "unit_cost_gbp": round(price * random.uniform(0.45, 0.7), 2),
            })
            n += 1
    return out


def main(n_days: int = 730) -> None:
    random.seed(SEED)
    rng = np.random.default_rng(SEED)
    RAW.mkdir(parents=True, exist_ok=True)

    # 1) Store master -> Excel-style CSV export with messy headers & casing
    stores = pd.DataFrame(STORES, columns=["Store ID", "Store Name", "City", "Region",
                                           "Latitude", "Longitude", "Opened", "Size (sqm)"])
    stores["Store ID"] = [s.lower() if i % 4 == 0 else s for i, s in enumerate(stores["Store ID"])]
    stores["City"] = stores["City"].str.upper().where(stores.index % 5 == 0, stores["City"]) + "  "
    stores.to_csv(RAW / "store_master.csv", index=False)

    # 2) Product catalogue -> nested JSON, as an API would return
    products = _products()
    catalogue = {"exported_at": "2025-12-31T23:59:00Z",
                 "items": [{"sku": p["sku"], "attributes": {"title": p["name"], "dept": p["category"]},
                            "pricing": {"list": p["list_price_gbp"], "cost": p["unit_cost_gbp"],
                                        "currency": "GBP"}} for p in products]}
    with open(RAW / "product_catalogue.json", "w") as f:
        json.dump(catalogue, f, indent=2)

    # 3) POS transactions -> CSV with mixed formats and dirty rows
    start = date(2024, 1, 1)
    store_weight = {s[0]: s[7] / 1000 for s in STORES}
    region_boost = {"London": 1.35, "Scotland": 1.05, "North West": 1.1}
    cat_season = {  # monthly multipliers (Jan..Dec)
        "Electronics": [0.8, 0.75, 0.8, 0.85, 0.9, 0.9, 0.95, 1.0, 1.0, 1.05, 1.5, 1.9],
        "Home": [0.9, 0.85, 0.9, 1.0, 1.0, 0.95, 0.9, 0.9, 1.0, 1.1, 1.3, 1.5],
        "Grocery": [1.0] * 12,
        "Health & Beauty": [0.9, 0.9, 1.0, 1.0, 1.1, 1.3, 1.35, 1.2, 1.0, 0.95, 1.0, 1.2],
        "Clothing": [1.1, 0.8, 0.95, 1.0, 1.05, 1.1, 1.15, 1.05, 1.1, 1.0, 1.15, 1.35],
    }
    rows, txn = [], 100000
    for d in range(n_days):
        day = start + timedelta(days=d)
        trend = 1 + 0.12 * d / 365          # ~12% YoY growth
        weekend = 1.3 if day.weekday() >= 5 else 1.0
        for s in STORES:
            sid, region = s[0], s[3]
            opened = date.fromisoformat(s[6])
            if day < opened:
                continue
            lam = 9 * store_weight[sid] * region_boost.get(region, 1.0) * trend * weekend
            # one store has a mid-2025 refurbishment dip -> a real anomaly for insights to find
            if sid == "S007" and date(2025, 6, 1) <= day <= date(2025, 7, 15):
                lam *= 0.35
            for _ in range(rng.poisson(lam)):
                p = random.choice(products)
                lam_m = cat_season[p["category"]][day.month - 1]
                if random.random() > lam_m / 2:
                    continue
                qty = int(rng.choice([1, 1, 1, 2, 2, 3]))
                disc = random.choice([0, 0, 0, 0, 0.1, 0.2]) if day.month in (1, 11, 12) else random.choice([0, 0, 0, 0.1])
                txn += 1
                rows.append([f"T{txn}", day, sid, p["sku"], qty,
                             round(p["list_price_gbp"] * (1 - disc), 2),
                             random.choices(CHANNELS, [0.7, 0.12, 0.18])[0],
                             f"C{rng.integers(1, 25000):05d}" if random.random() > 0.25 else None])

    pos = pd.DataFrame(rows, columns=["txn_id", "date", "store", "sku", "qty", "unit_price", "channel", "customer_id"])

    # --- inject realistic mess ---
    fmt_choice = rng.integers(0, 3, len(pos))
    pos["date"] = [d.strftime(["%Y-%m-%d", "%d/%m/%Y", "%d-%b-%Y"][k]) for d, k in zip(pos["date"], fmt_choice)]
    pos["unit_price"] = ["£" + f"{v:.2f}" if k == 1 else f"{v:.2f}" for v, k in zip(pos["unit_price"], fmt_choice)]
    lower = rng.random(len(pos)) < 0.05
    pos.loc[lower, "store"] = pos.loc[lower, "store"].str.lower() + " "
    pos.loc[rng.random(len(pos)) < 0.04, "channel"] = pos["channel"].str.upper()
    pos.loc[rng.random(len(pos)) < 0.002, "qty"] = -1           # impossible quantities
    pos.loc[rng.random(len(pos)) < 0.003, "sku"] = None          # missing product
    dupes = pos.sample(frac=0.01, random_state=SEED)              # duplicate rows from a re-sent batch
    pos = pd.concat([pos, dupes]).sample(frac=1, random_state=SEED).reset_index(drop=True)
    pos.to_csv(RAW / "pos_transactions.csv", index=False)

    # 4) Returns log -> pipe-delimited legacy export
    ret = pos.dropna(subset=["sku"]).sample(frac=0.03, random_state=7)[["txn_id", "sku"]].copy()
    ret["reason"] = rng.choice(["Faulty", "Changed mind", "Wrong size", "Damaged in transit"], len(ret))
    ret.to_csv(RAW / "returns_log.txt", sep="|", index=False)

    print(f"raw files written to {RAW}: {len(pos):,} POS rows, {len(ret):,} returns")


if __name__ == "__main__":
    main()
