"""Retrieve and quote filing evidence without inferring management's conclusions."""

import re

from .filing_index import BUSINESS, MDA, RISK, TOKEN, search
from .research_financial import NAMES
from .research_types import Citation, Claim

STOP = set("""
    a about all an and any are as at based business can company could describe did disclosure
    disclosures discuss do does evidence explain factor factors filing filings for form from how
    in include is item its listed made make management mention of on or our paypal pypl reported
    risk risks say said sec show some that the their they this to visa was were what when which
    who why will with would mastercard ma v fiscal year annual specifically tell me please
    outline provides identify key major main face faced stated say disclose disclosed section
""".split())
MOVEMENT = r"increas\w*|decreas\w*|declin\w*|grew|grow\w*|rose|fell|higher|lower|improv\w*"
CAUSE = re.compile(r"\b(?:due (?:primarily )?to|primarily due to|driven (?:primarily )?by|primarily driven by|attributable to|as a result of|reflec(?:ts|ted|ting))\b", re.I)
EXPLANATIONS = {
    "operating_cash_flow": (
        '("cash provided by operating activities" OR "cash flow from operations" OR "operating cash flow")',
        r"(?:cash provided by operating activities|cash flows? from operations|operating cash flows?)"
    ),
    "revenue": ('"net revenue"', r"net revenues?"),
    "operating_income": ('"operating income"', r"operating income"),
    "operating_margin": ('"operating margin"', r"operating margin"),
    "net_income": ('"net income"', r"net income"),
    "free_cash_flow": ('"free cash flow"', r"free cash flow"),
    "capex": ('("capital expenditures" OR "purchases of property")', r"(?:capital expenditures|purchases of property)"),
}
ALIASES = {
    "cybersecurity": ("cybersecurity", "cyberattack", "cyber"),
    "cyberattack": ("cyberattack", "cybersecurity", "cyber"),
    "cyberattacks": ("cyberattack", "cybersecurity", "cyber"),
    "regulatory": ("regulatory", "regulation"),
}


def sentences(text):
    for paragraph in text.splitlines():
        yield from re.split(r"(?<=[.!?])\s+(?=[A-Z“])", paragraph)


def excerpt(sentence, offset=0, max_words=25):
    prefix = "…" if offset else ""
    words = sentence[offset:].strip().split()
    suffix = "…" if len(words) > max_words else ""
    return prefix + " ".join(words[:max_words]) + suffix


def reference(row):
    return Citation(
        NAMES[row["ticker"]], row["ticker"], row["fiscal_year"], row["period_start"],
        row["period_end"], row["filed"], row["accession"], row["url"] + "#" + row["anchor"],
        row["section"], locator=f"passage {row['ordinal']}",
    )


def managerial_explanation(index, ticker, year, metric_field, direction=None):
    supported = EXPLANATIONS.get(metric_field)
    if supported is None:
        return None
    fts_phrase, exact_phrase = supported
    query = f'{fts_phrase} AND ("due" OR "driven" OR "attributable" OR "result" OR "reflects")'
    changes = direction or MOVEMENT
    statement = re.compile(rf"{exact_phrase}(?:[^.!?]{{0,30}}?)\b(?:{changes})\b", re.I)
    for row in search(index, query, ticker, year, MDA, limit=35):
        for sentence in sentences(row["text"]):
            match = statement.search(sentence)
            cause = CAUSE.search(sentence, match.end()) if match else None
            if cause and re.search(rf"\b{year}\b", sentence[:cause.end()]):
                return Claim("Management statement",
                             f"{NAMES[ticker]} explained the reported change in its FY{year} MD&A "
                             f"“{excerpt(sentence, cause.start())}”",
                             (reference(row),))
    return None


def topics(question):
    tokens = tuple(dict.fromkeys(
        token for token in TOKEN.findall(question.lower())
        if len(token) >= 3 and token.isalpha() and token not in STOP
    ))
    return tokens


def topical_passage(index, ticker, year, question, section):
    terms = topics(question)
    generic = not terms
    if generic:
        terms = ("risk",) if section == RISK else ("payment",)
    predicates = [
        "(" + " OR ".join(f'"{variant}"' for variant in ALIASES.get(term, (term,))) + ")"
        for term in terms
    ]
    query = " AND ".join(predicates)
    candidates = []
    for row in search(index, query, ticker, year, section, limit=24):
        for sentence in sentences(row["text"]):
            if len(sentence.split()) < 10:
                continue
            lowered = sentence.lower()
            positions = [
                [lowered.find(variant.removesuffix("s")) for variant in ALIASES.get(term, (term,))]
                for term in terms
            ]
            if not all(any(position >= 0 for position in term_positions) for term_positions in positions):
                continue
            first = min(position for group in positions for position in group if position >= 0)
            words_before = list(re.finditer(r"\S+", sentence[:first]))
            offset = words_before[-4].start() if len(words_before) > 4 else 0
            snippet = excerpt(sentence, offset)
            if not all(any(variant.removesuffix("s") in snippet.lower()
                           for variant in ALIASES.get(term, (term,))) for term in terms):
                continue
            consequence = bool(re.search(r"\b(?:could|may|adverse|disrupt\w*|damage|loss)\b", snippet, re.I))
            risk_language = bool(re.search(r"\b(?:risk\w*|threat\w*|attack\w*|vulnerab\w*)\b", snippet, re.I))
            if section == RISK and not (consequence or risk_language):
                continue
            candidates.append((consequence if section == RISK else False, -row["rank"], -row["ordinal"], snippet, row))
    if not candidates:
        return None
    _, _, _, snippet, row = max(candidates, key=lambda item: item[:3])
    kind = "Reported disclosure" if section == RISK else "Management statement"
    return Claim(kind, f"{NAMES[ticker]} writes in its FY{year} 10-K “{snippet}”", (reference(row),))
