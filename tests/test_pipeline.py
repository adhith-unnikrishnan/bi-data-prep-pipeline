import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import generate_raw  # noqa: E402
import pipeline  # noqa: E402


@pytest.fixture(scope="module")
def tables():
    generate_raw.main(n_days=120)
    return pipeline.run()


def test_mixed_date_formats_parse():
    s = pd.Series(["2024-03-05", "05/03/2024", "05-Mar-2024"])
    assert pipeline.parse_mixed_dates(s).nunique() == 1


def test_no_duplicates_or_bad_quantities(tables):
    f = tables["fact_sales"]
    assert not f.duplicated().any()
    assert (f["qty"] > 0).all()


def test_referential_integrity(tables):
    f = tables["fact_sales"]
    assert f["store_id"].isin(tables["dim_store"]["store_id"]).all()
    assert f["sku"].isin(tables["dim_product"]["sku"]).all()
    assert f["date_key"].isin(tables["dim_date"]["date_key"]).all()
    assert f["channel_key"].isin(tables["dim_channel"]["channel_key"]).all()


def test_measures_reconcile(tables):
    f = tables["fact_sales"]
    assert (f["revenue_gbp"] - f["cost_gbp"] - f["gross_margin_gbp"]).abs().max() < 0.02


def test_clean_labels(tables):
    assert set(tables["dim_channel"]["channel"]) == {"In-store", "Click & Collect", "Online"}
    assert tables["dim_store"]["store_id"].str.match(r"^S\d{3}$").all()


def test_haversine_london_to_edinburgh():
    km = pipeline.haversine_km(51.5074, -0.1278, 55.9533, -3.1883)
    assert 530 < km < 540
