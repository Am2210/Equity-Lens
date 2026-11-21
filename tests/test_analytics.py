import hashlib
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from shutil import copyfile
from zipfile import ZipFile

import duckdb
import pytest

from src.equitylens.analytics import build_analytics
from src.equitylens.sec import SecClient
from src.equitylens.sources import CUTOFF
from src.equitylens.warehouse import build

FROZEN = Path(__file__).resolve().parents[1] / "data/snapshots"


@pytest.fixture(scope="module")
def source_warehouse(tmp_path_factory):
    workspace = tmp_path_factory.mktemp("financial_analytics")
    cache = workspace / "raw"
    manifest = json.loads((FROZEN / "2026-11-21-source-manifest.json").read_text())
    with ZipFile(FROZEN / "2026-11-21-sec-json.zip") as archive:
        for source in manifest["sources"]:
            content = archive.read(source["path"])
            assert hashlib.sha256(content).hexdigest() == source["sha256"]
            target = cache / source["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
    source_database = workspace / "sec.duckdb"
    client = SecClient(cache, "EquityLens tests", "", offline=True)
    with client.session, duckdb.connect(str(source_database)) as connection:
        build(connection, client, CUTOFF)
    return source_database


@pytest.fixture(scope="module")
def analytics(source_warehouse):
    with duckdb.connect() as connection:
        build_analytics(connection, source_warehouse)
        yield connection


def test_formulas_zero_negative_and_missing_values(analytics):
    values = analytics.execute("""
        SELECT growth_rate(120, 100), growth_rate(-5, 100), growth_rate(100, 0),
               growth_rate(120, NULL), growth_rate(120, -100),
               positive_ratio(-10, 100), positive_ratio(0, 100), positive_ratio(10, 0),
               positive_ratio(10, -100), positive_ratio(NULL, 100),
               compound_growth(100, 146.41, 4), compound_growth(100, 0, 4),
               compound_growth(100, 120, 0), average_assets(80, 120), average_assets(NULL, 120)
    """).fetchone()
    assert values[:2] == pytest.approx((0.20, -1.05))
    assert values[2:5] == (None, None, None)
    assert values[5:7] == pytest.approx((-0.10, 0))
    assert values[7:10] == (None, None, None)
    assert values[10] == pytest.approx(0.10)
    assert values[11:] == (None, None, 100, None)


def test_fiscal_consistency_and_period_matching(analytics):
    assert analytics.execute("""
        SELECT ticker, period_start, period_end, comparison_fiscal_year, revenue_growth
        FROM annual_financial_analytics WHERE fiscal_year = 2021 ORDER BY ticker
    """).fetchall() == [
        ("MA", date(2021, 1, 1), date(2021, 12, 31), None, None),
        ("PYPL", date(2021, 1, 1), date(2021, 12, 31), None, None),
        ("V", date(2020, 10, 1), date(2021, 9, 30), None, None),
    ]
    assert analytics.execute("""
        SELECT adjacent_period(2023, DATE '2023-09-30', 2024, DATE '2023-10-01'),
               adjacent_period(2022, DATE '2022-09-30', 2024, DATE '2023-10-01'),
               adjacent_period(2023, DATE '2023-09-30', 2024, DATE '2024-01-01')
    """).fetchone() == (True, False, False)
    assert analytics.execute("""
        SELECT count(*) FROM annual_financial_analytics
        WHERE fiscal_year = 2024 AND duration_days = 366
    """).fetchone() == (3,)


@pytest.mark.parametrize("ticker,revenue,operating,net,ocf,capex,assets,opening,debt", [
    ("V", 40000, 23994, 20058, 23059, 1482, 99627, 94511, 25171),
    ("MA", 32791, 18897, 14968, 17648, 489, 54157, 48081, 19000),
    ("PYPL", 33172, 6065, 5233, 6416, 852, 80173, 78725, None),
])
def test_fy2025_primary_statement_reconciliation(
    analytics, ticker, revenue, operating, net, ocf, capex, assets, opening, debt
):
    # Figures independently transcribed from the original 10-Ks, in USD millions.
    row = analytics.execute("""
        SELECT revenue, operating_income, net_income, operating_cash_flow, capex, free_cash_flow,
               operating_margin, net_profit_margin, free_cash_flow_margin, assets, opening_assets,
               return_on_assets, interest_bearing_debt
        FROM peer_benchmark WHERE ticker = ?
    """, [ticker]).fetchone()
    assert tuple(value / 1_000_000 for value in row[:6]) == (
        revenue, operating, net, ocf, capex, ocf - capex
    )
    assert row[6:9] == pytest.approx((operating / revenue, net / revenue, (ocf - capex) / revenue))
    assert row[9] / 1_000_000 == assets
    assert row[10] / 1_000_000 == opening
    assert row[11] == pytest.approx(net / ((assets + opening) / 2))
    assert row[12] == (None if debt is None else debt * 1_000_000)


def test_lineage_links_derived_facts_to_original_filing(analytics):
    assert analytics.execute("""
        SELECT input_metric, coefficient, tag, accession, start_date, end_date, length(sha256)
        FROM statement_lineage
        WHERE ticker = 'V' AND fiscal_year = 2025 AND metric = 'free_cash_flow'
        ORDER BY input_metric
    """).fetchall() == [
        ("capital_expenditure_payments", -1, "PaymentsToAcquireProductiveAssets",
         "0001403161-25-000089", date(2024, 10, 1), date(2025, 9, 30), 64),
        ("operating_cash_flow", 1, "NetCashProvidedByUsedInOperatingActivities",
         "0001403161-25-000089", date(2024, 10, 1), date(2025, 9, 30), 64),
    ]
    assert analytics.execute("""
        SELECT accession, start_date, end_date, tag
        FROM statement_lineage WHERE ticker = 'PYPL' AND fiscal_year = 2025 AND metric = 'opening_assets'
    """).fetchone() == ("0001633917-26-000024", None, date(2024, 12, 31), "Assets")
    assert analytics.execute("""
        SELECT s.amount, s.status
        FROM statement_metrics s JOIN analysis_periods p USING (cik, fiscal_year)
        WHERE p.ticker = 'PYPL' AND s.fiscal_year = 2025 AND s.metric = 'interest_bearing_debt'
    """).fetchone() == (None, "unavailable_component")
    assert analytics.execute("""
        SELECT source_value FROM statement_lineage
        WHERE ticker = 'PYPL' AND fiscal_year = 2025 AND metric = 'interest_bearing_debt'
    """).fetchone() == ("9987000000",)


def test_growth_benchmark_calculation_and_insights(analytics):
    assert analytics.execute("""
        SELECT revenue_cagr, operating_cash_flow_cagr, revenue_growth_observations
        FROM peer_growth_summary WHERE ticker = 'MA'
    """).fetchone() == pytest.approx(((32791 / 18884) ** 0.25 - 1, (17648 / 9463) ** 0.25 - 1, 4))
    assert analytics.execute("""
        SELECT revenue_change_usd, revenue_growth FROM annual_financial_analytics
        WHERE ticker = 'V' AND fiscal_year = 2025
    """).fetchone() == pytest.approx((4_074_000_000, 40_000 / 35_926 - 1))
    assert analytics.execute("SELECT count(DISTINCT insight) FROM peer_insight_evidence").fetchone() == (7,)
    assert analytics.execute("SELECT count(*) FROM illustrative_cash_flow_sensitivity").fetchone() == (27,)
    assert analytics.execute("""
        SELECT base_fcf_usd FROM illustrative_cash_flow_sensitivity
        WHERE ticker = 'V' AND discount_rate = 0.10 AND terminal_growth = 0.02
    """).fetchone() == (Decimal(21_577_000_000),)


def test_fcf_propagates_missing_capex_and_preserves_negative_cash_flows(source_warehouse, tmp_path):
    fixture = tmp_path / "with_cash_flow_edge_cases.duckdb"
    copyfile(source_warehouse, fixture)
    with duckdb.connect(str(fixture)) as source:
        for ticker, metric, value in [
            ("MA", "capital_expenditure_payments", -100),
            ("PYPL", "operating_cash_flow", -100),
        ]:
            cik = source.execute("SELECT cik FROM companies WHERE ticker = ?", [ticker]).fetchone()[0]
            fact_id = source.execute("""
                SELECT selected_fact_id FROM standardized_financial_metrics
                WHERE cik = ? AND fiscal_year = 2025 AND metric = ?
            """, [cik, metric]).fetchone()[0]
            source.execute("UPDATE raw_xbrl_facts SET source_value = ? WHERE fact_id = ?", [str(value), fact_id])
            source.execute("""
                UPDATE standardized_financial_metrics SET metric_value = ? WHERE selected_fact_id = ?
            """, [value, fact_id])
        source.execute("""
            UPDATE standardized_financial_metrics
            SET metric_value = NULL, selected_fact_id = NULL, status = 'no_eligible_mapped_fact'
            WHERE cik = '0001403161' AND fiscal_year = 2025 AND metric = 'capital_expenditure_payments'
        """)
    with duckdb.connect() as connection:
        build_analytics(connection, fixture)
        assert connection.execute("""
            SELECT ticker, free_cash_flow FROM peer_benchmark ORDER BY ticker
        """).fetchall() == [("MA", None), ("PYPL", Decimal(-852_000_100)), ("V", None)]
