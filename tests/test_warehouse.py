import json
from decimal import Decimal

import duckdb
import pytest

from src.equitylens.sec import SecClient, SecError
from src.equitylens.sources import COMPANIES, CUTOFF, FILING_FIELDS
from src.equitylens.warehouse import build


def write_json(root, name, data):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def filing(accession, form, filed, end):
    return (accession, form, filed, end, filed + "T09:00:00.000Z", "10k.htm", 1, 1)


def columns(rows):
    return {field: [row[i] for row in rows] for i, field in enumerate(FILING_FIELDS)}


def observation(row, value, *, start=None, end=None, year=2025):
    accession, form, filed, report_end, *_ = row
    fact = {"accn": accession, "form": form, "filed": filed, "end": end or report_end,
            "fy": year, "fp": "FY", "val": value, "frame": "CY2025"}
    if start:
        fact["start"] = start
    return fact


def metric(units):
    return {"label": "Fixture concept", "units": units}


@pytest.fixture
def cache(tmp_path):
    write_json(tmp_path, "company_tickers.json", {
        str(index): {"ticker": ticker, "cik_str": int(cik)}
        for index, (ticker, (cik, _)) in enumerate(COMPANIES.items())
    })
    for ticker, (cik, fiscal_end) in COMPANIES.items():
        suffix = "-09-30" if ticker == "V" else "-12-31"
        filed_month = "-11-15" if ticker == "V" else "-02-15"
        annuals = [
            filing(f"{ticker}-{year}", "10-K",
                   f"{year if ticker == 'V' else year + 1}{filed_month}", f"{year}{suffix}")
            for year in range(2020, 2026)
        ]
        original = annuals[-1]
        start = "2024-10-01" if ticker == "V" else "2025-01-01"
        end = original[3]
        amended = filing(f"{ticker}-amend", "10-K/A", "2026-09-01", end)
        later = filing(f"{ticker}-2026", "10-K", "2026-11-20", f"2026{suffix}")
        future = filing(f"{ticker}-future", "10-K/A", "2026-11-22", end)
        quarter = filing(f"{ticker}-quarter", "10-Q", "2026-03-01", "2025-12-31")
        xbrl = {
            "Revenues": metric({"USD": [observation(original, 850, start=start)]}),
            "RevenueFromContractWithCustomerExcludingAssessedTax": metric({
                "USD": [
                    observation(original, 1000, start=start, year=1999),
                    observation(original, 1000, start=start, year=2022),
                    observation(original, 222, start=f"2025{suffix[:3]}-01"),
                    observation(original, 333, start="2025-05-01"),
                    observation(amended, 1100, start=start),
                    observation(later, 1200, start=start, end=end, year=2026),
                    observation(future, 9999, start=start),
                    observation(quarter, 777, start=start, end=end),
                ],
                "EUR": [observation(original, 900, start=start)],
            }),
            "Assets": metric({"USD": [
                observation(original, 20),
                observation(original, 21, start=start),
                observation(original, 22, end="2025-09-29"),
            ]}),
            "Liabilities": metric({"USD": [observation(original, 80), observation(original, 81)]}),
            "OperatingIncomeLoss": metric({"USD": [observation(amended, 56, start=start)]}),
            "EarningsPerShareDiluted": metric({"USD/shares": [observation(original, 2.37, start=start)]}),
        }
        archive = f"CIK{cik}-submissions-001.json"
        write_json(tmp_path, f"submissions/{archive}", columns(annuals[:2]))
        write_json(tmp_path, f"submissions/CIK{cik}.json", {
            "cik": cik, "name": f"{ticker} fixture", "tickers": [ticker],
            "fiscalYearEnd": fiscal_end, "filings": {
                "recent": columns([*annuals[2:], amended, later, future, quarter]),
                "files": [{"name": archive, "filingFrom": annuals[0][2], "filingTo": annuals[1][2]}],
            },
        })
        write_json(tmp_path, f"companyfacts/CIK{cik}.json", {"cik": int(cik), "facts": {
            "us-gaap": xbrl,
            ticker.lower(): {"IssuerSpecificRevenue": metric({"USD": [observation(original, 789, start=start)]})},
        }})
    return tmp_path


def offline(cache):
    return SecClient(cache, "EquityLens", "", offline=True)


def test_offline_build_preserves_periods_lineage_and_versions(cache):
    client = offline(cache)
    with duckdb.connect() as connection:
        build(connection, client, CUTOFF)
        assert len(client.sources) == 10
        assert connection.execute("SELECT count(*) FROM financial_reporting_periods").fetchone() == (15,)
        assert connection.execute("""
            SELECT c.ticker, cast(p.period_start AS VARCHAR), cast(p.period_end AS VARCHAR)
            FROM financial_reporting_periods p JOIN companies c USING (cik)
            WHERE fiscal_year = 2025 ORDER BY c.ticker
        """).fetchall() == [
            ("MA", "2025-01-01", "2025-12-31"),
            ("PYPL", "2025-01-01", "2025-12-31"),
            ("V", "2024-10-01", "2025-09-30"),
        ]
        assert connection.execute("""
            SELECT metric_value, original_candidate_rows, changed_comparative_filings, source_fy
            FROM standardized_financial_metrics m JOIN raw_xbrl_facts r ON m.selected_fact_id = r.fact_id
            WHERE m.cik = '0001403161' AND m.fiscal_year = 2025 AND m.metric = 'revenue'
        """).fetchone() == (Decimal(1000), 2, 2, 1999)
        assert connection.execute("""
            SELECT metric_value, tag
            FROM standardized_financial_metrics m JOIN raw_xbrl_facts r ON m.selected_fact_id = r.fact_id
            WHERE m.cik = '0001141391' AND m.fiscal_year = 2025 AND m.metric = 'revenue'
        """).fetchone() == (Decimal(850), "Revenues")
        assert connection.execute("""
            SELECT metric, metric_value, status
            FROM standardized_financial_metrics
            WHERE cik = '0001403161' AND fiscal_year = 2025
              AND metric IN ('assets', 'liabilities', 'operating_income', 'diluted_eps', 'gross_profit')
            ORDER BY metric
        """).fetchall() == [
            ("assets", Decimal(20), "available"),
            ("diluted_eps", Decimal("2.37"), "available"),
            ("gross_profit", None, "no_eligible_mapped_fact"),
            ("liabilities", None, "conflicting_original_facts"),
            ("operating_income", None, "only_later_candidates"),
        ]
        assert connection.execute("""
            SELECT count(*) FROM raw_xbrl_facts WHERE is_custom_taxonomy
        """).fetchone() == (3,)
        for table in ("filing_metadata", "raw_xbrl_facts"):
            assert connection.execute(
                f"SELECT count(*) FROM {table} WHERE filed > DATE '2026-11-21'"
            ).fetchone() == (0,)


def test_fiscal_year_end_mismatch_fails_closed(cache):
    path = cache / "submissions/CIK0001403161.json"
    data = json.loads(path.read_text())
    data["fiscalYearEnd"] = "1231"
    write_json(cache, "submissions/CIK0001403161.json", data)
    with duckdb.connect() as connection, pytest.raises(SecError, match="fiscal year-end changed"):
        build(connection, offline(cache), CUTOFF)
