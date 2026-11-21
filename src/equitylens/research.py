"""Offline SEC research assistant with deterministic questions and traceable evidence."""

import argparse
from contextlib import ExitStack
import json
import re
import sqlite3
import sys
from pathlib import Path

import duckdb

from .filing_index import BUSINESS, RISK, build_index, open_index
from .filings import ANALYTICS, FILING_CACHE, INDEX, RESEARCH_REPORTS, WAREHOUSE, client_for_filings
from .research_financial import BY_FIELD, NAMES, numeric_claims, observations, requested_metrics, scenario_claim, version_claims
from .research_narrative import managerial_explanation, topical_passage
from .research_types import Answer
from .sec import SecError
from .sources import FIRST_YEAR, LAST_YEAR

YEARS = tuple(range(FIRST_YEAR, LAST_YEAR + 1))
YEAR = re.compile(r"(?<!\d)(?:FY\s*)?(20\d\d)(?!\d)", re.I)
COMPANY_PATTERNS = {
    "MA": r"\b(?:mastercard|master card|ticker ma)\b",
    "PYPL": r"\b(?:paypal|pay pal|pypl)\b",
    "V": r"\b(?:visa|ticker v)\b",
}
PEERS = re.compile(r"\b(?:peers?|all three|each company|three companies|which (?:company|issuer))\b", re.I)
UNSUPPORTED = re.compile(
    r"\b(?:stock price|share price|price target|market cap|market share|total shareholder return|"
    r"buy|sell|investment advice|insider|real[- ]time|next year|predict|guarantee|"
    r"quarterly|quarters?\s+[1-4]|q[1-4]|half[- ]year|calendar[- ]quarter|"
    r"parent[- ]attributable|organic growth|constant currency|non[- ]gaap|"
    r"adjusted (?:eps|operating|net|revenue|free cash flow|margin)|per (?:employee|transaction|share))\b",
    re.I,
)
WHY = re.compile(r"\b(?:why|explain|explanation|drivers?|attribut\w+|management (?:say|report|cite|explain))\b", re.I)
RISK_QUERY = re.compile(r"\b(?:risk factors?|risks?|cybersecurity|cyberattacks?)\b", re.I)
BUSINESS_QUERY = re.compile(r"\b(?:business|business model|checkout|business overview|products|payment network)\b", re.I)
VERSION = re.compile(r"\b(?:reclassif\w*|revis\w*|restat\w*|later (?:filings?|comparatives?)|originally reported versus)\b", re.I)
SCENARIO = re.compile(r"\b(?:dcf|discounted cash flow|hypothetical scenario)\b", re.I)
VALUATION_QUERY = re.compile(r"\b(?:intrinsic value|valuation|fair (?:stock|share|equity|market) value|per.share value)\b", re.I)


def company_scope(question):
    tickers = []
    for ticker, pattern in COMPANY_PATTERNS.items():
        matched = re.search(pattern, question, re.I) or re.search(rf"\b{ticker}\b", question)
        if matched:
            tickers.append(ticker)
    if tickers:
        return tuple(tickers)
    return tuple(COMPANY_PATTERNS) if PEERS.search(question) else ()


def year_scope(question):
    years = tuple(sorted({int(match) for match in YEAR.findall(question)}))
    if len(years) == 2 and re.search(r"20\d\d\s*(?:\b(?:to|through)\b|[-–—])\s*(?:FY\s*)?20\d\d", question, re.I):
        return tuple(range(years[0], years[1] + 1))
    return years


class ResearchAssistant:
    """Reusable context-managed interface for the local research stores."""

    def __init__(self, index=INDEX, analytics=ANALYTICS, warehouse=WAREHOUSE):
        self.paths = index, analytics, warehouse
        self.resources = ExitStack()

    def __enter__(self):
        try:
            index, analytics, warehouse = self.paths
            self.index = open_index(index)
            self.resources.callback(self.index.close)
            for name, path in (("analytics", analytics), ("warehouse", warehouse)):
                setattr(self, name, self.resources.enter_context(
                    duckdb.connect(str(path.resolve(strict=True)), read_only=True)
                ))
            expected = self.analytics.execute("""
                SELECT ticker, fiscal_year, original_accession, original_filed::VARCHAR,
                       period_start::VARCHAR, period_end::VARCHAR
                FROM analysis_periods ORDER BY ticker, fiscal_year
            """).fetchall()
            indexed = self.index.execute("""
                SELECT ticker, fiscal_year, accession, filed, period_start, period_end
                FROM filings ORDER BY ticker, fiscal_year
            """).fetchall()
            manifest = self.warehouse.execute("SELECT path, sha256 FROM source_manifest ORDER BY path").fetchall()
            analytics_sources = self.analytics.execute("SELECT path, sha256 FROM analysis_sources ORDER BY path").fetchall()
            if expected != [tuple(row) for row in indexed] or manifest != analytics_sources:
                raise ValueError("The filing index, source warehouse and analytics must use the same snapshot.")
            return self
        except BaseException:
            self.resources.close()
            raise

    def __exit__(self, *exc):
        return self.resources.__exit__(*exc)

    def answer(self, question: str) -> Answer:
        result = Answer(question)
        tickers = company_scope(question)
        explicit_years = year_scope(question)
        if not tickers:
            result.limitations.append("The available filings cover Visa, Mastercard and PayPal. Specify an issuer or ask for the peer group.")
            return result.finish()
        if any(year not in YEARS for year in explicit_years):
            result.limitations.append("The available filings do not establish the requested reporting period. Coverage is FY2021–FY2025.")
            return result.finish()
        same_calendar = "V" in tickers and len(tickers) > 1 and re.search(
            r"\b(?:same|identical|matching|matched|aligned) (?:calendar |fiscal )?(?:reporting )?(?:periods?|years?|dates?|year ends?)\b",
            question, re.I
        )
        if same_calendar:
            result.limitations.append("The available annual filings do not establish an identical-period comparison. "
                                      "Visa closes September 30. Mastercard and PayPal close December 31.")
            return result.finish()
        if "V" in tickers and re.search(r"\bcalendar[- ]year\b", question, re.I):
            result.limitations.append("The available annual filings do not establish a calendar-year figure for Visa, "
                                      "whose fiscal year closes September 30.")
            return result.finish()
        if UNSUPPORTED.search(question) or (VALUATION_QUERY.search(question) and not SCENARIO.search(question)):
            result.status = "unsupported"
            result.limitations.append("The available annual filings and validated analytics do not establish an answer to that request.")
            return result.finish()
        years = explicit_years or (LAST_YEAR,)
        if not explicit_years and re.search(r"\b(?:trend\w*|over time|historical performance)\b", question, re.I):
            years = YEARS
        if len(tickers) == 1 and len(years) == 1 and re.search(r"\b(?:compare|versus|vs)\b", question, re.I):
            result.limitations.append("The available filings do not establish both sides of that comparison. "
                                      "Name two supported issuers or two fiscal years.")
            return result.finish()
        if SCENARIO.search(question):
            if years != (LAST_YEAR,) or re.search(r"\d\s*%|\b(?:share price|equity value|per.share)\b", question, re.I):
                result.status = "unsupported"
                result.limitations.append("This assistant can cite the stored FY2025 illustrative cash-flow proxy scenario. "
                                          "The available evidence does not establish a custom scenario or an equity value.")
                return result.finish()
            for ticker in tickers:
                claim = scenario_claim(self.analytics, ticker)
                if claim:
                    result.claims.append(claim)
                else:
                    result.limitations.append(f"The validated scenario is unavailable for {NAMES[ticker]}.")
            return result.finish()

        metrics = requested_metrics(question)
        why = bool(WHY.search(question))
        if re.search(r"\b(?:financial|relative) (?:strengths|weaknesses|performance)\b", question, re.I) and not metrics:
            metrics = tuple(BY_FIELD[field] for field in (
                "revenue_growth", "operating_margin", "free_cash_flow_margin", "return_on_assets",
            ))
            result.context.append("These benchmarks describe reported performance and reflect different operating models.")
        if metrics and VERSION.search(question):
            for ticker in tickers:
                for metric in metrics:
                    claims, limits = version_claims(self.warehouse, ticker, years, metric)
                    result.claims.extend(claims)
                    result.limitations.extend(limits)
            if why and result.claims:
                result.limitations.append("The available evidence identifies the later reported values. "
                                          "It does not establish a management explanation for the revision from the indexed passages.")
            return result.finish()

        section = RISK if RISK_QUERY.search(question) else BUSINESS if BUSINESS_QUERY.search(question) and not metrics else None
        if section:
            for ticker in tickers:
                for year in years:
                    claim = topical_passage(self.index, ticker, year, question, section)
                    if claim:
                        result.claims.append(claim)
                    else:
                        result.limitations.append(f"The available {NAMES[ticker]} FY{year} {section} passages do not establish an answer to that topic.")
            return result.finish()

        if not metrics:
            result.limitations.append("The available evidence does not establish an answer. Ask for a supported financial metric, "
                                      "a business topic, a disclosed risk or an MD&A explanation for a specific issuer and fiscal year.")
            return result.finish()

        if len(tickers) > 1 and "V" in tickers:
            result.context.append("Comparisons use issuer fiscal-year labels. Visa closes September 30, while Mastercard and PayPal close December 31.")
        rank = "highest" if re.search(r"\b(?:highest|largest|strongest|led)\b", question, re.I) else (
            "lowest" if re.search(r"\b(?:lowest|smallest|weakest)\b", question, re.I) else ""
        )
        for metric in metrics:
            claims, limits = numeric_claims(
                self.analytics, tickers, years, metric, rank=rank, explicit_years=explicit_years
            )
            result.claims.extend(claims)
            result.limitations.extend(limits)
            if why and len(tickers) == 1:
                self.append_explanations(result, tickers, years, metric)
        if why and len(tickers) > 1:
            result.limitations.append("The available annual filings do not establish the causes of differences between issuers.")
        return result.finish()

    def append_explanations(self, result, tickers, years, metric):
        field = {
            "revenue_growth": "revenue", "operating_cash_flow_growth": "operating_cash_flow",
            "operating_margin_change": "operating_margin",
        }.get(metric.field, metric.field)
        for ticker in tickers:
            for year in years:
                direction = None
                direction_field = {
                    "revenue": "revenue_growth", "operating_cash_flow": "operating_cash_flow_growth",
                    "operating_margin": "operating_margin_change",
                }.get(field)
                if direction_field:
                    _, _, movement, _, _ = observations(
                        self.analytics, (ticker,), (year,), BY_FIELD[direction_field]
                    )[0]
                    if movement is not None:
                        asked_up = re.search(r"\b(?:increas\w*|rose|grew|higher|improv\w*)\b", result.question, re.I)
                        asked_down = re.search(r"\b(?:decreas\w*|declin\w*|fell|fall|lower)\b", result.question, re.I)
                        if bool(asked_up) != bool(asked_down) and (
                            (asked_up and movement <= 0) or (asked_down and movement >= 0)
                        ):
                            result.limitations.append(f"The validated {NAMES[ticker]} FY{year} series does not show "
                                                      "the direction stated in the question.")
                            continue
                        if movement > 0:
                            direction = r"increas\w*|grew|grow\w*|rose|higher|improv\w*"
                        elif movement < 0:
                            direction = r"decreas\w*|declin\w*|fell|lower"
                claim = managerial_explanation(self.index, ticker, year, field, direction)
                if claim:
                    result.claims.append(claim)
                    disclaimer = "Management excerpts describe the comparison made in the cited filing. Their comparative basis can differ from the originally filed annual series."
                    if disclaimer not in result.context:
                        result.context.append(disclaimer)
                else:
                    result.limitations.append(f"The available {NAMES[ticker]} FY{year} MD&A does not establish a management explanation for the requested {metric.label} on this basis.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--warehouse", default=WAREHOUSE, type=Path)
    parser.add_argument("--analytics", default=ANALYTICS, type=Path)
    parser.add_argument("--index", default=INDEX, type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    index = commands.add_parser("index", help="Download missing filings and rebuild the local text index")
    index.add_argument("--cache", type=Path, default=FILING_CACHE)
    index.add_argument("--manifest", type=Path, default=RESEARCH_REPORTS / "filings_manifest.json")
    index.add_argument("--verify-manifest", type=Path, help="Require an exact filing manifest match")
    index.add_argument("--offline", action="store_true")
    question = commands.add_parser("ask", help="Answer a question entirely from local evidence")
    question.add_argument("question")
    question.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()
    try:
        if args.command == "index":
            client = client_for_filings(args.cache, offline=args.offline)
            with client.session:
                count, sections = build_index(args.warehouse, client, args.index, args.manifest, args.verify_manifest)
            print(f"Indexed {count} original 10-Ks and {sum(sections.values())} passages.")
            for section, size in sections.items():
                print(f"  {section}: {size}")
        else:
            with ResearchAssistant(args.index, args.analytics, args.warehouse) as assistant:
                result = assistant.answer(args.question)
            print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2) if args.json_output else result.markdown())
    except (SecError, OSError, ValueError, sqlite3.Error, duckdb.Error) as error:
        print(f"EquityLens research: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
