"""Read deterministic financial outputs and attach original 10-K evidence."""

import re
from dataclasses import dataclass
from decimal import Decimal

from .research_types import Citation, Claim

NAMES = {"V": "Visa", "MA": "Mastercard", "PYPL": "PayPal"}


@dataclass(frozen=True)
class Metric:
    field: str
    label: str
    pattern: str
    units: str
    inputs: tuple[str, ...]
    window: str = "annual"


METRICS = (
    Metric("revenue_cagr", "revenue CAGR", r"(?:revenue|sales) (?:cagr|compound(?: annual)? growth(?: rate)?)", "pct", ("revenue",), "endpoint"),
    Metric("operating_cash_flow_cagr", "operating cash flow CAGR", r"(?:operating cash flow|ocf) (?:cagr|compound(?: annual)? growth(?: rate)?)", "pct", ("operating_cash_flow",), "endpoint"),
    Metric("revenue_growth_stddev", "historical revenue-growth sample standard deviation", r"(?:volatility|dispersion|consistency) (?:of )?(?:annual )?revenue growth|revenue growth (?:volatility|dispersion|consistency)", "pp", ("revenue",), "history"),
    Metric("free_cash_flow_margin", "free cash flow margin", r"(?:free cash flow|fcf) margin", "pct", ("free_cash_flow", "revenue")),
    Metric("fcf_to_net_income", "free cash flow to net income", r"(?:free cash flow|fcf)(?:\s*/\s*|\s+(?:to|divided by|conversion to)\s+)net income", "multiple", ("free_cash_flow", "net_income")),
    Metric("ocf_to_net_income", "operating cash flow to net income", r"(?:operating cash flow|ocf)(?:\s*/\s*|\s+(?:to|divided by|conversion to)\s+)net income|cash(?: flow)? conversion", "multiple", ("operating_cash_flow", "net_income")),
    Metric("revenue_growth", "year-over-year revenue growth", r"(?:net )?(?:revenues?|sales) (?:yoy |year-over-year |year over year )?(?:growth|change|increas\w*|declin\w*|decreas\w*)|(?:change|growth) in (?:revenues?|sales)", "pct", ("revenue",), "yoy"),
    Metric("operating_cash_flow_growth", "year-over-year operating cash flow growth", r"(?:operating cash flow|ocf) (?:yoy |year-over-year |year over year )?(?:growth|change|increas\w*|declin\w*|decreas\w*)|(?:change|growth) in (?:operating cash flow|ocf)", "pct", ("operating_cash_flow",), "yoy"),
    Metric("operating_margin_change", "year-over-year operating margin change", r"operating margin (?:chang\w*|increas\w*|declin\w*|decreas\w*|fall)|change in operating margin", "pp", ("operating_income", "revenue"), "yoy"),
    Metric("operating_margin", "operating margin", r"operating (?:profit )?margins?|operating profitability", "pct", ("operating_income", "revenue")),
    Metric("net_profit_margin", "net profit margin", r"net (?:profit )?margins?", "pct", ("net_income", "revenue")),
    Metric("return_on_assets", "return on average assets", r"return on (?:average )?assets|roa", "pct", ("net_income", "assets", "opening_assets")),
    Metric("asset_turnover", "asset turnover", r"asset turnover|asset efficiency", "multiple", ("revenue", "assets", "opening_assets")),
    Metric("interest_bearing_debt", "mapped current and noncurrent interest-bearing debt", r"(?:total )?interest[ -]bearing debt|total debt|debt balance", "usd", ("interest_bearing_debt",)),
    Metric("noncurrent_debt", "noncurrent debt", r"(?:noncurrent|long-term|long term) debt", "usd", ("noncurrent_debt",)),
    Metric("cash_and_equivalents", "cash and cash equivalents", r"cash (?:and |& )(?:cash )?equivalents|cash balance", "usd", ("cash_and_equivalents",)),
    Metric("assets", "total assets", r"(?:total )?assets", "usd", ("assets",)),
    Metric("liabilities", "total liabilities", r"(?:total )?liabilities", "usd", ("liabilities",)),
    Metric("operating_income", "operating income", r"operating (?:income|profit)", "usd", ("operating_income",)),
    Metric("net_income", "consolidated net income", r"net (?:income|profit|earnings)", "usd", ("net_income",)),
    Metric("free_cash_flow", "free cash flow", r"free cash flow|fcf", "usd", ("free_cash_flow",)),
    Metric("operating_cash_flow", "operating cash flow", r"operating cash flow|cash (?:from|provided by) (?:its )?operating activities|ocf", "usd", ("operating_cash_flow",)),
    Metric("capex", "capital expenditure payments", r"capex|capital expenditure(?:s| payments)?", "usd", ("capital_expenditure_payments",)),
    Metric("revenue", "revenue", r"(?:net )?revenues?|sales", "usd", ("revenue",)),
)
BY_FIELD = {metric.field: metric for metric in METRICS}


def requested_metrics(question):
    matches = []
    spans = []
    for metric in METRICS:
        for match in re.finditer(rf"\b(?:{metric.pattern})\b", question, re.I):
            if any(match.start() < end and start < match.end() for start, end in spans):
                continue
            spans.append(match.span())
            matches.append((match.start(), metric))
    return tuple(dict.fromkeys(metric for _, metric in sorted(matches, key=lambda item: item[0])))


def format_value(value, units):
    if units == "usd":
        return f"{'-' if value < 0 else ''}${abs(value) / Decimal(10**9):,.3f} billion"
    if units == "pct":
        return f"{value:.2%}"
    if units == "pp":
        return f"{value * 100:.2f} percentage points"
    return f"{value:.2f}×"


def financial_citations(analytics, ticker, years, metric):
    marks = ", ".join("?" for _ in years)
    input_marks = ", ".join("?" for _ in metric.inputs)
    rows = analytics.execute(f"""
        SELECT p.fiscal_year, p.period_start, p.period_end, l.filed, l.accession, l.filing_url,
               string_agg(DISTINCT l.tag, ', ' ORDER BY l.tag)
        FROM analysis_periods p JOIN statement_lineage l USING (cik, fiscal_year)
        WHERE p.ticker = ? AND p.fiscal_year IN ({marks}) AND l.metric IN ({input_marks})
        GROUP BY ALL ORDER BY p.fiscal_year
    """, (ticker, *years, *metric.inputs)).fetchall()
    if {row[0] for row in rows} != set(years):
        raise ValueError(f"Missing filing lineage for {ticker} {metric.field} {years}.")
    return tuple(
        Citation(NAMES[ticker], ticker, year, str(start), str(end), str(filed), accession, url,
                 "Financial statements", metric.label, tags)
        for year, start, end, filed, accession, url, tags in rows
    )


def version_claims(warehouse, ticker, years, metric):
    if len(years) != 1 or metric.field not in {"operating_cash_flow", "assets", "liabilities",
                                               "cash_and_equivalents", "revenue"}:
        return [], ["Specify one fiscal year and a supported reported line item for a later-filing comparison."]
    year = years[0]
    source_rows = warehouse.execute("""
        SELECT l.candidate_value, l.filing_role, l.filed, l.accession, l.tag, l.form,
               p.period_start, p.period_end,
               'https://www.sec.gov/Archives/edgar/data/' || cast(cast(p.cik AS BIGINT) AS VARCHAR)
                   || '/' || replace(l.accession, '-', '') || '/' || f.primary_document
        FROM metric_to_source_lineage l JOIN standardized_financial_metrics s USING (cik, fiscal_year, metric)
        JOIN financial_reporting_periods p USING (cik, fiscal_year)
        JOIN filing_metadata f ON f.cik = l.cik AND f.accession = l.accession
        JOIN companies c ON c.cik = l.cik
        WHERE c.ticker = ? AND l.fiscal_year = ? AND l.metric = ?
          AND (l.is_selected OR (l.within_filing_rank = 1 AND l.filing_role <> 'original_10k'
             AND l.distinct_values = 1 AND l.invalid_numeric_count = 0 AND l.candidate_value <> s.metric_value))
        ORDER BY l.is_selected DESC, l.filed, l.accession
    """, (ticker, year, metric.field)).fetchall()
    if len(source_rows) < 2:
        return [], [f"The available filings do not establish a changed comparative for {NAMES[ticker]} "
                    f"FY{year} {metric.label} in the validated lineage."]
    claims = []
    for value, role, filed, accession, tag, form, start, end, url in source_rows:
        wording = "originally reported" if role == "original_10k" else "reported in a later annual filing"
        citation = Citation(NAMES[ticker], ticker, year, str(start), str(end), str(filed),
                            accession, url, "Financial statements", metric.label, tag, form)
        claims.append(Claim("Reported fact", f"{NAMES[ticker]} FY{year} {metric.label} was "
                            f"{format_value(value, metric.units)} as {wording}.", (citation,)))
    return claims, []


def observations(analytics, tickers, years, metric):
    tick_marks = ", ".join("?" for _ in tickers)
    if metric.window in ("history", "endpoint"):
        window_rows = analytics.execute(f"""
            SELECT ticker, first_fiscal_year, last_fiscal_year, {metric.field}, revenue_growth_observations
            FROM peer_growth_summary WHERE ticker IN ({tick_marks}) ORDER BY ticker
        """, tickers).fetchall()
        results = []
        for ticker, first, last, value, count in window_rows:
            source_years = tuple(range(first, last + 1)) if metric.window == "history" else (first, last)
            suffix = f" across {count} annual growth observations" if metric.window == "history" else ""
            results.append((ticker, f"FY{first}–FY{last}", value, source_years, suffix))
        return results
    year_marks = ", ".join("?" for _ in years)
    rows = analytics.execute(f"""
        SELECT ticker, fiscal_year, {metric.field}, comparison_fiscal_year
        FROM annual_financial_analytics
        WHERE ticker IN ({tick_marks}) AND fiscal_year IN ({year_marks})
        ORDER BY ticker, fiscal_year
    """, (*tickers, *years)).fetchall()
    return [
        (ticker, f"FY{year}", value, (prior, year) if metric.window == "yoy" and prior else (year,), "")
        for ticker, year, value, prior in rows
    ]


def numeric_claims(analytics, tickers, years, metric, *, rank="", explicit_years=()):
    if metric.window in ("history", "endpoint"):
        scope = analytics.execute("SELECT first_fiscal_year, last_fiscal_year FROM analysis_snapshot").fetchone()
        if explicit_years and tuple(explicit_years) != tuple(range(scope[0], scope[1] + 1)):
            return [], [f"The validated {metric.label} is available for FY{scope[0]}–FY{scope[1]}. "
                        "The available analytics do not establish that measure for the requested window."]
    rows = observations(analytics, tickers, years, metric)
    found = []
    limits = []
    for ticker, label, value, source_years, suffix in rows:
        if value is None:
            cause = "the validated series has no eligible value"
            if metric.window == "yoy" and len(source_years) == 1:
                cause = "there is no prior annual observation in the selected financial series"
            if metric.field == "interest_bearing_debt" and ticker == "PYPL":
                cause = "the mapped current debt component is unavailable"
            limits.append(f"The available evidence does not establish {NAMES[ticker]} {label} {metric.label} because {cause}.")
            continue
        citations = financial_citations(analytics, ticker, source_years, metric)
        found.append((ticker, label, value, suffix, citations))
    if rank and len({label for _, label, *_ in rows}) == 1 and len(tickers) > 1 and found and not limits:
        extreme = max if rank == "highest" else min
        best = extreme(item[2] for item in found)
        names = ", ".join(NAMES[ticker] for ticker, _, value, _, _ in found if value == best)
        values = "; ".join(f"{NAMES[ticker]} {format_value(value, metric.units)}" for ticker, _, value, _, _ in found)
        citations = tuple(citation for *_, refs in found for citation in refs)
        return [Claim("Derived comparison", f"{names} had the {rank} {found[0][1]} {metric.label} "
                      f"among the requested issuers ({values}).", citations)], []
    claims = []
    for ticker, label, value, suffix, citations in found:
        kind = "Reported fact" if metric.units == "usd" and metric.field not in {
            "interest_bearing_debt", "free_cash_flow"
        } else "Derived calculation"
        claims.append(Claim(kind, f"{NAMES[ticker]} {label} {metric.label} was "
                            f"{format_value(value, metric.units)}{suffix}.", citations))
    if rank and limits:
        limits.append("The missing values prevent a complete peer ranking.")
    return claims, limits


def scenario_claim(analytics, ticker):
    result = analytics.execute("""
        SELECT fiscal_year, base_fcf_usd, illustrative_proxy_pv_usd
        FROM illustrative_cash_flow_sensitivity
        WHERE ticker = ? AND discount_rate = 0.10 AND terminal_growth = 0.02
          AND forecast_growth = 0.05 AND forecast_years = 5
    """, (ticker,)).fetchone()
    if result is None:
        return None
    year, fcf, value = result
    refs = financial_citations(analytics, ticker, (year,), BY_FIELD["free_cash_flow"])
    return Claim("Hypothetical scenario", f"{NAMES[ticker]} FY{year} free cash flow of {format_value(fcf, 'usd')} "
                 f"produces an illustrative cash-flow proxy present value of {format_value(value, 'usd')} "
                 "under the stored five-year scenario with 5% forecast growth, a 10% discount rate and "
                 "2% terminal growth. The calculation has no equity or per-share bridge.", refs)
