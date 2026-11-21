"""Export deterministic validation evidence for the current warehouse."""

import json
from pathlib import Path

import pandas as pd

from .sec import atomic_write

COUNTS = (
    "companies", "filing_metadata", "raw_xbrl_facts", "financial_reporting_periods",
    "standardized_financial_metrics", "metric_to_source_lineage", "source_manifest",
)
EXPORTS = {
    "periods": """
        SELECT c.ticker, p.* EXCLUDE (cik)
        FROM financial_reporting_periods p JOIN companies c USING (cik)
        ORDER BY c.ticker, p.fiscal_year
    """,
    "metrics": """
        SELECT c.ticker, m.* EXCLUDE (cik), p.period_start, p.period_end,
               r.taxonomy, r.tag, r.accession, r.filed
        FROM standardized_financial_metrics m
        JOIN companies c USING (cik)
        JOIN financial_reporting_periods p USING (cik, fiscal_year)
        LEFT JOIN raw_xbrl_facts r ON m.selected_fact_id = r.fact_id
        ORDER BY c.ticker, m.fiscal_year, m.metric
    """,
    "taxonomy_inventory": """
        SELECT c.ticker, t.* EXCLUDE (cik)
        FROM taxonomy_inventory t JOIN companies c USING (cik)
        ORDER BY c.ticker, t.taxonomy
    """,
    "changed_values": """
        SELECT c.ticker, l.fiscal_year, l.metric, m.metric_value AS original_value,
               l.candidate_value AS later_value, l.filing_role, l.taxonomy, l.tag,
               l.accession, l.filed, l.fact_id
        FROM metric_to_source_lineage l
        JOIN standardized_financial_metrics m USING (cik, fiscal_year, metric)
        JOIN companies c USING (cik)
        WHERE l.filing_role <> 'original_10k' AND l.within_filing_rank = 1
          AND l.distinct_values = 1 AND l.invalid_numeric_count = 0
          AND l.candidate_value <> m.metric_value
        ORDER BY c.ticker, l.fiscal_year, l.metric, l.filed, l.accession
    """,
}


def write_reports(connection, directory: Path, sources):
    directory.mkdir(parents=True, exist_ok=True)
    counts = {name: connection.execute(f"SELECT count(*) FROM {name}").fetchone()[0] for name in COUNTS}
    cutoff = connection.execute("SELECT as_of_date FROM snapshot").fetchone()[0]
    status = connection.execute("""
        SELECT c.ticker, m.status, count(*)
        FROM standardized_financial_metrics m JOIN companies c USING (cik)
        GROUP BY c.ticker, m.status
        ORDER BY c.ticker, m.status
    """).fetchall()
    for name, query in EXPORTS.items():
        result = connection.execute(query)
        frame = pd.DataFrame.from_records(
            result.fetchall(), columns=[column[0] for column in result.description],
            coerce_float=False,
        )
        if name == "metrics":
            frame["selected_fact_id"] = pd.array(frame["selected_fact_id"], dtype="Int64")
        atomic_write(directory / f"{name}.csv", frame.to_csv(index=False).encode("utf-8"))
    summary = [f"# Validation snapshot as of {cutoff}", "", "## Warehouse counts", ""]
    summary.extend(f"- {name}: {count:,}" for name, count in counts.items())
    summary.extend(["", "## Metric coverage", ""])
    summary.extend(f"- {ticker} {name}: {count}" for ticker, name, count in status)
    atomic_write(directory / "validation.md", ("\n".join(summary) + "\n").encode("utf-8"))
    manifest = {"as_of_date": str(cutoff), "sources": sorted(sources, key=lambda row: row["path"])}
    atomic_write(directory / "source_manifest.json", (json.dumps(manifest, indent=2) + "\n").encode("utf-8"))
    return counts
