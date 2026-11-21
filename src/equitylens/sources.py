"""Validate SEC source identities and load submissions covering the snapshot."""

import re
from datetime import date
from decimal import Decimal

from .sec import FACTS_BASE, SUBMISSIONS_BASE, TICKERS_URL, SecError

COMPANIES = {
    "V": ("0001403161", "0930"),
    "MA": ("0001141391", "1231"),
    "PYPL": ("0001633917", "1231"),
}
FIRST_YEAR = 2021
LAST_YEAR = 2025
CUTOFF = date(2026, 11, 21)
HISTORY_START = date(FIRST_YEAR - 1, 1, 1)
STANDARD_TAXONOMIES = {
    "cef", "country", "currency", "cyd", "dei", "ecd", "exch", "ffd", "fnd",
    "ifrs", "ifrs-full", "invest", "naics", "oef", "rr", "rxp", "sbs", "sic",
    "snj", "spac", "sro", "srt", "stpr", "us-gaap", "vip",
}
FILING_FIELDS = (
    "accessionNumber", "form", "filingDate", "reportDate",
    "acceptanceDateTime", "primaryDocument", "isXBRL", "isInlineXBRL",
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def filing_columns(payload):
    accessions = payload["accessionNumber"]
    for field in FILING_FIELDS:
        require(isinstance(payload[field], list) and len(payload[field]) == len(accessions),
                f"invalid submissions column {field}")


def check_submissions(payload, cik, ticker, fiscal_end):
    require(int(payload["cik"]) == int(cik), f"expected submissions CIK {cik}")
    require(ticker in payload["tickers"], f"submissions missing ticker {ticker}")
    require(payload["fiscalYearEnd"] == fiscal_end,
            f"{ticker} fiscal year-end changed from {fiscal_end}")
    filing_columns(payload["filings"]["recent"])
    for archive in payload["filings"]["files"]:
        require(re.fullmatch(rf"CIK{cik}-submissions-\d+\.json", archive["name"]),
                "invalid SEC submissions archive name")
        require(date.fromisoformat(archive["filingFrom"]) <= date.fromisoformat(archive["filingTo"]),
                "invalid SEC submissions archive dates")


def check_facts(payload, cik):
    require(int(payload["cik"]) == int(cik) and bool(payload["facts"]),
            f"expected nonempty Company Facts for CIK {cik}")
    for concepts in payload["facts"].values():
        for concept in concepts.values():
            for observations in concept["units"].values():
                for fact in observations:
                    value = fact["val"]
                    require(isinstance(value, (int, Decimal)) and not isinstance(value, bool),
                            "expected a numeric XBRL observation")
                    date.fromisoformat(fact["end"])
                    date.fromisoformat(fact["filed"])
                    if "start" in fact:
                        date.fromisoformat(fact["start"])
                    require(bool(fact["accn"]) and bool(fact["form"]),
                            "missing XBRL accession or form")


def check_tickers(payload):
    sec_tickers = {row["ticker"]: int(row["cik_str"]) for row in payload.values()}
    for ticker, (cik, _) in COMPANIES.items():
        require(sec_tickers.get(ticker) == int(cik), f"ticker file mismatch for {ticker}/{cik}")


def load_sources(client, cutoff):
    client.get(TICKERS_URL, "company_tickers.json", check_tickers)
    for ticker, (cik, fiscal_end) in COMPANIES.items():
        filename = f"CIK{cik}.json"
        submissions = client.get(
            SUBMISSIONS_BASE + filename, f"submissions/{filename}",
            lambda payload: check_submissions(payload, cik, ticker, fiscal_end),
        )
        facts = client.get(
            FACTS_BASE + filename, f"companyfacts/{filename}",
            lambda payload: check_facts(payload, cik),
        )
        recent = submissions["filings"]["recent"]
        files = [recent]
        for archive in submissions["filings"]["files"]:
            if (date.fromisoformat(archive["filingTo"]) >= HISTORY_START
                    and date.fromisoformat(archive["filingFrom"]) <= cutoff):
                name = archive["name"]
                files.append(client.get(SUBMISSIONS_BASE + name, f"submissions/{name}", filing_columns))
        yield ticker, cik, submissions, facts, files


def filing_rows(cik, files, cutoff):
    by_accession = {}
    for columns in files:
        for accession, form, filed, report, accepted, document, xbrl, inline in zip(
            *(columns[field] for field in FILING_FIELDS), strict=True
        ):
            if date.fromisoformat(filed) > cutoff:
                continue
            row = (cik, accession, form, filed, report or None, accepted or None,
                   document or None, bool(int(xbrl)), bool(int(inline)))
            if by_accession.setdefault(accession, row) != row:
                raise SecError(f"Conflicting submissions metadata for {cik}/{accession}")
    return list(by_accession.values())


def fact_rows(cik, payload, cutoff):
    for taxonomy, concepts in sorted(payload["facts"].items()):
        for tag, concept in sorted(concepts.items()):
            for unit, observations in sorted(concept["units"].items()):
                for index, fact in enumerate(observations):
                    if date.fromisoformat(fact["filed"]) > cutoff:
                        continue
                    yield (
                        cik, taxonomy, tag, unit, index, str(fact["val"]),
                        fact.get("start"), fact["end"], fact.get("fy"), fact.get("fp"),
                        fact["form"], fact["filed"], fact["accn"], fact.get("frame"),
                        taxonomy not in STANDARD_TAXONOMIES, concept.get("label"),
                    )
