"""Build and validate the DuckDB warehouse from verified SEC cache files."""

from decimal import Decimal
from pathlib import Path

import duckdb
import pandas as pd

from .sec import SecError
from .sources import COMPANIES, FIRST_YEAR, LAST_YEAR, fact_rows, filing_rows, load_sources

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def execute_sql(connection, filename):
    connection.execute((SQL_DIR / filename).read_text(encoding="utf-8"))


def insert_rows(connection, table, columns, rows):
    frame = pd.DataFrame.from_records(rows, columns=columns).astype("string")
    if frame.empty:
        return
    connection.register("incoming_rows", frame)
    try:
        connection.execute(f"INSERT INTO {table} BY NAME SELECT * FROM incoming_rows")
    finally:
        connection.unregister("incoming_rows")


def build(connection, client, cutoff):
    execute_sql(connection, "01_schema.sql")
    execute_sql(connection, "02_mappings.sql")
    connection.execute("INSERT INTO snapshot VALUES (?, ?, ?, ?)", [
        cutoff, FIRST_YEAR, LAST_YEAR, "original_10k",
    ])
    next_fact_id = 1
    for ticker, cik, submissions, facts, filing_files in load_sources(client, cutoff):
        connection.execute("INSERT INTO companies VALUES (?, ?, ?, ?)", [
            cik, ticker, submissions["name"], submissions["fiscalYearEnd"],
        ])
        insert_rows(connection, "filing_metadata", [
            "cik", "accession", "form", "filed", "report_end", "accepted_timestamp_raw",
            "primary_document", "is_xbrl", "is_inline_xbrl",
        ], filing_rows(cik, filing_files, cutoff))
        rows = [
            (fact_id, *fact) for fact_id, fact in
            enumerate(fact_rows(cik, facts, cutoff), start=next_fact_id)
        ]
        next_fact_id += len(rows)
        insert_rows(connection, "raw_xbrl_facts", [
            "fact_id", "cik", "taxonomy", "tag", "unit", "observation_index", "source_value",
            "start_date", "end_date", "source_fy", "source_fp", "form", "filed", "accession",
            "frame", "is_custom_taxonomy", "concept_label",
        ], rows)
    insert_rows(connection, "source_manifest", ["path", "url", "sha256", "bytes"], [
        (source["path"], source["url"], source["sha256"], source["bytes"])
        for source in client.sources
    ])
    execute_sql(connection, "03_transform.sql")
    validate(connection)


def validate(connection):
    expected = {(ticker, year) for ticker in COMPANIES for year in range(FIRST_YEAR, LAST_YEAR + 1)}
    actual = set(connection.execute("""
        SELECT c.ticker, p.fiscal_year
        FROM financial_reporting_periods p JOIN companies c USING (cik)
        WHERE p.duration_days BETWEEN 350 AND 380
    """).fetchall())
    if actual != expected:
        raise SecError(f"Missing or invalid annual filing anchors: {sorted(expected - actual)}")

    # Check every usable comparison as well as each selected value before publishing.
    numeric_values = connection.execute("""
        SELECT DISTINCT r.fact_id, r.source_value, l.candidate_value
        FROM metric_to_source_lineage l JOIN raw_xbrl_facts r USING (fact_id)
        WHERE l.candidate_value IS NOT NULL
    """).fetchall()
    for fact_id, source_value, stored_value in numeric_values:
        if Decimal(source_value) != stored_value:
            raise SecError(f"Metric value exceeds the warehouse decimal scale for raw fact {fact_id}")

    invalid = connection.execute("""
        SELECT m.cik, m.fiscal_year, m.metric
        FROM standardized_financial_metrics m
        JOIN financial_reporting_periods p USING (cik, fiscal_year)
        LEFT JOIN metric_to_source_lineage l
          ON m.cik = l.cik AND m.fiscal_year = l.fiscal_year AND m.metric = l.metric AND l.is_selected
        LEFT JOIN raw_xbrl_facts r ON l.fact_id = r.fact_id
        CROSS JOIN snapshot s
        WHERE (m.status = 'available') IS DISTINCT FROM (l.fact_id IS NOT NULL)
           OR m.selected_fact_id IS DISTINCT FROM l.fact_id
           OR m.metric_value IS DISTINCT FROM l.candidate_value
           OR (l.fact_id IS NOT NULL AND (
               r.accession <> p.original_accession OR r.filed > s.as_of_date
               OR r.end_date <> p.period_end OR r.unit <> m.unit OR r.is_custom_taxonomy
               OR (m.period_type = 'instant' AND r.start_date IS NOT NULL)
               OR (m.period_type = 'duration' AND r.start_date IS DISTINCT FROM p.period_start)
           ))
    """).fetchall()
    if invalid:
        raise SecError(f"Metric lineage failed validation: {invalid[:5]}")
