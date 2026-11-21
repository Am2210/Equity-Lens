"""Download primary 10-K documents identified by validated SEC submissions."""

import hashlib
import os
import re
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import duckdb
from dotenv import load_dotenv

from .sec import SecClient, SecError, atomic_write
from .sources import COMPANIES, FIRST_YEAR, LAST_YEAR

ROOT = Path(__file__).resolve().parents[2]
WAREHOUSE = ROOT / "data/warehouse/equitylens.duckdb"
ANALYTICS = ROOT / "data/warehouse/financial_analytics.duckdb"
FILING_CACHE = ROOT / "data/raw/filings"
INDEX = ROOT / "data/warehouse/filing_index.sqlite"
RESEARCH_REPORTS = ROOT / "reports/generated/research"


@dataclass(frozen=True)
class Filing:
    ticker: str
    company: str
    cik: str
    fiscal_year: int
    period_start: date
    period_end: date
    accession: str
    filed: date
    document: str

    @property
    def url(self):
        return (f"https://www.sec.gov/Archives/edgar/data/{int(self.cik)}/"
                f"{self.accession.replace('-', '')}/{self.document}")

    @property
    def cache_name(self):
        return f"{self.accession}/{self.document}"

    def manifest_row(self, content):
        return {
            **asdict(self), "url": self.url, "form": "10-K", "cache_path": self.cache_name,
            "sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content),
        }


def original_filings(database: Path) -> tuple[Filing, ...]:
    with duckdb.connect(str(database.resolve(strict=True)), read_only=True) as connection:
        rows = connection.execute("""
            SELECT c.ticker, c.sec_name, p.cik, p.fiscal_year, p.period_start, p.period_end,
                   f.accession, f.filed, f.primary_document
            FROM financial_reporting_periods p JOIN companies c USING (cik)
            JOIN filing_metadata f ON f.cik = p.cik AND f.accession = p.original_accession
            CROSS JOIN snapshot s
            WHERE f.form = '10-K' AND f.filed = p.original_filed
              AND f.report_end = p.period_end AND f.filed <= s.as_of_date
            ORDER BY c.ticker, p.fiscal_year
        """).fetchall()
    filings = tuple(Filing(*row) for row in rows)
    expected = {
        (ticker, cik, year) for ticker, (cik, _) in COMPANIES.items()
        for year in range(FIRST_YEAR, LAST_YEAR + 1)
    }
    if len(filings) != len(expected) or {(f.ticker, f.cik, f.fiscal_year) for f in filings} != expected:
        raise SecError("Submissions metadata does not identify every original 10-K in scope.")
    for filing in filings:
        if not (re.fullmatch(r"\d{10}-\d{2}-\d{6}", filing.accession)
                and re.fullmatch(r"[\w.-]+\.html?", filing.document or "", re.ASCII | re.I)):
            raise SecError(f"Invalid primary document identifier for {filing.ticker} FY{filing.fiscal_year}.")
    return filings


def client_for_filings(cache: Path, *, offline=False):
    load_dotenv(ROOT / ".env")
    return SecClient(cache, os.getenv("SEC_ORGANIZATION", "EquityLens"),
                     os.getenv("SEC_CONTACT_EMAIL", ""), offline=offline)


def read_filing(client: SecClient, filing: Filing) -> bytes:
    path = client.cache / filing.cache_name
    cached = path.is_file()
    if cached:
        content = path.read_bytes()
    elif client.offline:
        raise SecError(f"Missing filing {path}. Save the original HTML from {filing.url}.")
    else:
        content = client.download(filing.url, accept="text/html,application/xhtml+xml")
    if len(content) < 30_000 or b"<html" not in content[:2000].lower():
        raise SecError(f"Invalid filing HTML for {filing.accession} from {filing.url}.")
    if not cached:
        atomic_write(path, content)
    return content
