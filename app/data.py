"""Read and cache the validated EquityLens outputs used by the Streamlit pages."""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st

from src.equitylens.filings import ANALYTICS, INDEX, WAREHOUSE
from src.equitylens.research import ResearchAssistant
from src.equitylens.research_financial import NAMES

ISSUERS = ("V", "MA", "PYPL")
FOREST = "#183E35"
TERRACOTTA = "#C57453"
GOLD = "#D4B77C"
INK = "#292D2A"
ISSUER_COLORS = {"V": FOREST, "MA": "#A65235", "PYPL": "#79662F"}
USD_MILLION = 1_000_000


@dataclass(frozen=True)
class Measure:
    name: str
    unit: str
    definition: str
    inputs: tuple[str, ...]
    prior_year: bool = False


MEASURES = {
    "revenue": Measure("Revenue", "USD millions", "Consolidated income-statement revenue.", ("revenue",)),
    "operating_income": Measure("Operating income", "USD millions", "Reported income from operations.", ("operating_income",)),
    "net_income": Measure("Net income", "USD millions", "Reported consolidated net income.", ("net_income",)),
    "assets": Measure("Total assets", "USD millions", "Fiscal year-end total assets.", ("assets",)),
    "liabilities": Measure("Total liabilities", "USD millions", "Fiscal year-end total liabilities.", ("liabilities",)),
    "cash_and_equivalents": Measure("Cash and equivalents", "USD millions", "Point-in-time carrying value of cash and cash equivalents.", ("cash_and_equivalents",)),
    "interest_bearing_debt": Measure("Mapped interest-bearing debt", "USD millions", "Identified current and noncurrent interest-bearing debt. Both components are required.", ("interest_bearing_debt",)),
    "noncurrent_debt": Measure("Noncurrent debt", "USD millions", "Reported noncurrent debt carrying amount.", ("noncurrent_debt",)),
    "operating_cash_flow": Measure("Operating cash flow", "USD millions", "Net cash provided by or used in operating activities.", ("operating_cash_flow",)),
    "capex": Measure("Capital expenditure", "USD millions", "Positive cash outflow for the mapped capital purchases in the filing.", ("capital_expenditure_payments",)),
    "free_cash_flow": Measure("Free cash flow", "USD millions", "Operating cash flow less mapped capital expenditure.", ("free_cash_flow",)),
    "revenue_growth": Measure("Revenue growth", "%", "Current revenue divided by prior-year revenue, minus one.", ("revenue",), True),
    "operating_cash_flow_growth": Measure("Operating cash flow growth", "%", "Current operating cash flow divided by prior-year operating cash flow, minus one.", ("operating_cash_flow",), True),
    "operating_margin": Measure("Operating margin", "%", "Operating income divided by revenue.", ("operating_income", "revenue")),
    "operating_margin_change": Measure("Operating margin change", "percentage points", "Current operating margin less the previous contiguous fiscal-year margin.", ("operating_income", "revenue"), True),
    "net_profit_margin": Measure("Net profit margin", "%", "Consolidated net income divided by revenue.", ("net_income", "revenue")),
    "free_cash_flow_margin": Measure("Free cash flow margin", "%", "Free cash flow divided by revenue.", ("free_cash_flow", "revenue")),
    "return_on_assets": Measure("Return on average assets", "%", "Consolidated net income divided by opening and closing assets averaged from the same 10-K.", ("net_income", "opening_assets", "assets")),
    "asset_turnover": Measure("Asset turnover", "×", "Revenue divided by average assets.", ("revenue", "opening_assets", "assets")),
    "ocf_to_net_income": Measure("Operating cash flow / net income", "×", "Operating cash flow divided by positive consolidated net income.", ("operating_cash_flow", "net_income")),
    "fcf_to_net_income": Measure("Free cash flow / net income", "×", "Free cash flow divided by positive consolidated net income.", ("free_cash_flow", "net_income")),
}

STATEMENTS = {
    "Income statement": ("revenue", "operating_income", "net_income"),
    "Balance sheet": ("assets", "liabilities", "cash_and_equivalents", "interest_bearing_debt", "noncurrent_debt"),
    "Cash flow": ("operating_cash_flow", "capex", "free_cash_flow"),
    "Growth & margins": ("revenue_growth", "operating_cash_flow_growth", "operating_margin", "operating_margin_change",
                         "net_profit_margin", "free_cash_flow_margin", "return_on_assets", "asset_turnover",
                         "ocf_to_net_income", "fcf_to_net_income"),
}
PEER_MEASURES = ("revenue", "revenue_growth", "operating_margin", "net_profit_margin",
                 "operating_cash_flow", "free_cash_flow", "free_cash_flow_margin", "return_on_assets", "asset_turnover")


def fingerprint(path: Path):
    stat = path.stat()
    return str(path), stat.st_mtime_ns, stat.st_size


@dataclass(frozen=True)
class Workbench:
    annual: pd.DataFrame
    lineage: pd.DataFrame
    cutoff: date

    def year(self, fiscal_year):
        return self.annual[self.annual.fiscal_year.eq(fiscal_year)]

    def row(self, ticker, fiscal_year):
        selected = self.year(fiscal_year)
        return selected.loc[selected.ticker.eq(ticker)].iloc[0]

    def history(self, tickers, through):
        return self.annual[self.annual.ticker.isin(tickers) & self.annual.fiscal_year.le(through)]

    def sources(self, ticker, fiscal_year, metric):
        measure = MEASURES[metric]
        row = self.row(ticker, fiscal_year)
        years = [fiscal_year]
        if measure.prior_year and pd.notna(row.comparison_fiscal_year):
            years.append(int(row.comparison_fiscal_year))
        return self.lineage.loc[
            self.lineage.ticker.eq(ticker) & self.lineage.fiscal_year.isin(years)
            & self.lineage.metric.isin(measure.inputs)
        ]


@st.cache_data(show_spinner=False)
def _load_workbench(signature: tuple):
    with duckdb.connect(signature[0], read_only=True) as connection:
        result = connection.execute("""
            SELECT a.*, s.filing_url
            FROM annual_financial_analytics a
            LEFT JOIN (
                SELECT cik, fiscal_year, accession, min(filing_url) AS filing_url
                FROM statement_lineage
                GROUP BY cik, fiscal_year, accession
            ) s ON s.cik = a.cik AND s.fiscal_year = a.fiscal_year
                AND s.accession = a.original_accession
            ORDER BY a.fiscal_year, a.ticker
        """)
        annual = pd.DataFrame.from_records(result.fetchall(), columns=[col[0] for col in result.description])
        lineage = connection.execute("""
            SELECT * FROM statement_lineage ORDER BY ticker, fiscal_year, metric, input_metric
        """).df()
        cutoff = connection.execute("SELECT as_of_date FROM analysis_snapshot").fetchone()[0]
    if annual.empty:
        raise ValueError("The financial analytics warehouse has no fiscal periods.")
    return Workbench(annual, lineage, cutoff)


def workbench():
    try:
        return _load_workbench(fingerprint(ANALYTICS))
    except (OSError, duckdb.Error, ValueError):
        st.error("The financial analytics warehouse is unavailable. Build it with the commands in README.md, then reload.")
        st.stop()


def scope():
    return st.session_state["scope_company"], st.session_state["scope_year"]


@st.cache_data(show_spinner=False, max_entries=64)
def _research(question, index_signature, analytics_signature, warehouse_signature):
    with ResearchAssistant(Path(index_signature[0]), Path(analytics_signature[0]), Path(warehouse_signature[0])) as assistant:
        return assistant.answer(question)


def answer(question):
    return _research(question, fingerprint(INDEX), fingerprint(ANALYTICS), fingerprint(WAREHOUSE))


def shown(value, unit, *, signed=False):
    if pd.isna(value):
        return "—"
    prefix = "+" if signed and value > 0 else ""
    if unit == "USD millions":
        return f"{prefix}{value / USD_MILLION:,.0f}"
    if unit == "%":
        return f"{prefix}{value:.2%}"
    if unit == "percentage points":
        return f"{prefix}{value * 100:.2f} pp"
    return f"{value:.2f}×"


def scaled(value, unit):
    if pd.isna(value):
        return None
    value = float(value)
    if unit == "USD millions":
        return value / USD_MILLION
    if unit == "percentage points":
        return value * 100
    return value


def fiscal_date(value):
    return value.date().isoformat() if hasattr(value, "date") else value.isoformat()


def fiscal_window(row):
    return f"{fiscal_date(row.period_start)} to {fiscal_date(row.period_end)}"


def tabular_csv(frame):
    return frame.to_csv(index=False, lineterminator="\n").encode("utf-8-sig")


def statement_rows(book, ticker, fiscal_year, fields):
    row = book.row(ticker, fiscal_year)
    units = {"%": "percent", "percentage points": "percentage points", "×": "multiple",
             "USD millions": "USD millions"}
    return pd.DataFrame([
        {
            "Issuer": NAMES[ticker], "Fiscal year": fiscal_year,
            "Period start": fiscal_date(row.period_start), "Period end": fiscal_date(row.period_end),
            "Filing date": fiscal_date(row.original_filed), "Metric": MEASURES[field].name,
            "Value": scaled(row[field], MEASURES[field].unit) * 100 if (
                MEASURES[field].unit == "%" and pd.notna(row[field])
            ) else scaled(row[field], MEASURES[field].unit),
            "Unit": units[MEASURES[field].unit],
            "SEC filing": row.filing_url,
        }
        for field in fields
    ])
