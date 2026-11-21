"""Build the financial statements and peer analytics from a read-only SEC database."""

import argparse
from decimal import Decimal
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

import duckdb

from .analytics_report import export_analytics
from .sources import COMPANIES, FIRST_YEAR, LAST_YEAR
from .valuation import sensitivity
from .warehouse import execute_sql

ROOT = Path(__file__).resolve().parents[2]
VALUATION_RATES = (Decimal("0.08"), Decimal("0.10"), Decimal("0.12"))
TERMINAL_RATES = (Decimal("0.01"), Decimal("0.02"), Decimal("0.03"))


def build_analytics(connection, source_database: Path):
    source_database = source_database.resolve(strict=True)
    # ATTACH requires a DuckDB string literal rather than a parameter.
    quoted_path = str(source_database).replace("'", "''")
    connection.execute(f"ATTACH '{quoted_path}' AS sec (READ_ONLY)")
    scope = connection.execute("""
        SELECT first_fiscal_year, last_fiscal_year, selection_policy FROM sec.snapshot
    """).fetchall()
    if scope != [(FIRST_YEAR, LAST_YEAR, "original_10k")]:
        raise ValueError("Analytics requires the validated FY2021–FY2025 original 10-K warehouse.")
    execute_sql(connection, "04_statement_analytics.sql")
    execute_sql(connection, "05_peer_analytics.sql")
    validate_analytics(connection)
    add_scenarios(connection)
    connection.execute("DETACH sec")


def validate_analytics(connection):
    periods = connection.execute("""
        SELECT ticker, cik, fiscal_year, period_start, period_end, duration_days
        FROM analysis_periods ORDER BY ticker, fiscal_year
    """).fetchall()
    expected = {
        (ticker, cik, year) for ticker, (cik, _) in COMPANIES.items()
        for year in range(FIRST_YEAR, LAST_YEAR + 1)
    }
    if {(ticker, cik, year) for ticker, cik, year, *_ in periods} != expected:
        raise ValueError("Statement periods differ from the expected company and fiscal-year grid.")
    for ticker, _, year, start, end, days in periods:
        if (end.year != year or end.strftime("%m%d") != COMPANIES[ticker][1]
                or days != (end - start).days + 1 or days not in (365, 366)):
            raise ValueError(f"Invalid annual financial period for {ticker} FY{year}.")

    invalid_contexts = connection.execute("""
        SELECT l.ticker, l.fiscal_year, l.metric
        FROM statement_lineage l
        JOIN analysis_periods p USING (cik, fiscal_year)
        CROSS JOIN analysis_snapshot s
        WHERE l.accession <> p.original_accession OR l.filed <> p.original_filed
           OR l.filed > s.as_of_date OR l.form <> '10-K'
           OR l.unit <> 'USD' OR l.filing_url IS NULL
           OR l.end_date IS DISTINCT FROM
               CASE WHEN l.input_metric = 'opening_assets' THEN p.period_start - 1 ELSE p.period_end END
           OR l.start_date IS DISTINCT FROM
               CASE WHEN l.input_metric IN ('revenue', 'operating_income', 'net_income',
                   'operating_cash_flow', 'capital_expenditure_payments') THEN p.period_start END
    """).fetchall()
    if invalid_contexts:
        raise ValueError(f"Invalid original filing lineage: {invalid_contexts[:5]}")

    entries = connection.execute("""
        SELECT m.cik, m.fiscal_year, m.metric, m.amount, l.source_value, l.coefficient
        FROM statement_metrics m LEFT JOIN statement_lineage l USING (cik, fiscal_year, metric)
        WHERE m.status = 'available'
        ORDER BY m.cik, m.fiscal_year, m.metric, l.input_metric
    """).fetchall()
    totals = {}
    for cik, year, metric, amount, value, coefficient in entries:
        if value is None or amount is None:
            raise ValueError(f"Missing source amount for {cik} FY{year} {metric}.")
        key = (cik, year, metric, amount)
        totals[key] = totals.get(key, Decimal(0)) + Decimal(value) * coefficient
    for (cik, year, metric, amount), total in totals.items():
        if amount != total:
            raise ValueError(f"Source amounts do not reconcile for {cik} FY{year} {metric}.")


def add_scenarios(connection):
    connection.execute("""
        CREATE TABLE illustrative_cash_flow_sensitivity (
            ticker VARCHAR, fiscal_year INTEGER, base_fcf_usd DECIMAL(38,12), forecast_years INTEGER,
            forecast_growth DECIMAL(9,6), discount_rate DECIMAL(9,6), terminal_growth DECIMAL(9,6),
            forecast_pv_usd DECIMAL(38,2), terminal_pv_usd DECIMAL(38,2),
            illustrative_proxy_pv_usd DECIMAL(38,2), terminal_pv_share DOUBLE,
            PRIMARY KEY (ticker, discount_rate, terminal_growth)
        )
    """)
    base_cash_flows = connection.execute("""
        SELECT ticker, fiscal_year, free_cash_flow
        FROM peer_benchmark WHERE free_cash_flow > 0 ORDER BY ticker
    """).fetchall()
    rows = []
    for ticker, year, fcf in base_cash_flows:
        for case, result in sensitivity(fcf, Decimal("0.05"), 5, VALUATION_RATES, TERMINAL_RATES):
            rows.append((
                ticker, year, fcf, case.forecast_years, case.forecast_growth, case.discount_rate,
                case.terminal_growth, result.forecast_present_value, result.terminal_present_value,
                result.total_present_value, result.terminal_present_value / result.total_present_value,
            ))
    if rows:
        connection.executemany("""
            INSERT INTO illustrative_cash_flow_sensitivity VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "data/warehouse/equitylens.duckdb")
    parser.add_argument("--database", type=Path, default=ROOT / "data/warehouse/financial_analytics.duckdb")
    parser.add_argument("--reports", type=Path, default=ROOT / "reports/generated/analytics")
    args = parser.parse_args()
    if args.source.resolve() == args.database.resolve():
        parser.error("The analytics database must have a different path from the SEC warehouse.")
    try:
        args.database.parent.mkdir(parents=True, exist_ok=True)
        args.reports.parent.mkdir(parents=True, exist_ok=True)
        with (
            TemporaryDirectory(dir=args.database.parent) as temporary_db,
            TemporaryDirectory(dir=args.reports.parent) as temporary_reports,
        ):
            staged = Path(temporary_db) / "financial_analytics.duckdb"
            with duckdb.connect(str(staged)) as connection:
                build_analytics(connection, args.source)
                counts = export_analytics(connection, Path(temporary_reports))
            staged.replace(args.database)
            args.reports.mkdir(parents=True, exist_ok=True)
            for artifact in Path(temporary_reports).iterdir():
                artifact.replace(args.reports / artifact.name)
    except (duckdb.Error, OSError, ValueError) as exc:
        print(f"EquityLens analytics: {exc}", file=sys.stderr)
        return 1
    print(f"Validated analytics database: {args.database}")
    for name, count in counts.items():
        print(f"  {name}: {count:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
