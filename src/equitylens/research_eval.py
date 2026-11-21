"""Run frozen research evaluation prompts and preserve the actual evidence."""

import argparse
import json
from pathlib import Path
import re

from .filings import ANALYTICS, INDEX, RESEARCH_REPORTS, ROOT, WAREHOUSE
from .research import ResearchAssistant
from .sec import atomic_write

CASES = ROOT / "tests/research_questions.json"


def citation_errors(assistant, answer):
    errors = []
    for claim in answer.claims:
        is_narrative = claim.kind in {"Management statement", "Reported disclosure"}
        for source in claim.citations:
            record = assistant.warehouse.execute("""
                SELECT c.ticker, f.filed::VARCHAR, f.primary_document, f.form, cast(c.cik AS BIGINT)
                FROM filing_metadata f JOIN companies c USING (cik)
                WHERE f.accession = ?
            """, (source.accession,)).fetchone()
            if record is None or record[:2] != (source.ticker, source.filed) or record[3] != source.form:
                errors.append(f"Unverified source metadata for {source.accession}")
                continue
            root_url = (f"https://www.sec.gov/Archives/edgar/data/{record[4]}/"
                        f"{source.accession.replace('-', '')}/{record[2]}")
            base, _, anchor = source.url.partition("#")
            if root_url != base:
                errors.append(f"Unverified filing URL: {source.url}")
            if not is_narrative:
                if not source.metric or not source.period_start or not source.period_end or not source.locator:
                    errors.append(f"Incomplete quantitative citation for {source.accession}")
                continue
            chunk_id = re.fullmatch(r"passage (\d+)", source.locator)
            row = assistant.index.execute("""
                SELECT p.text, f.fiscal_year, f.period_end
                FROM passages p JOIN filings f USING (accession)
                WHERE p.accession = ? AND p.section = ? AND p.anchor = ? AND p.ordinal = ?
            """, (source.accession, source.section, anchor, int(chunk_id[1]) if chunk_id else 0)).fetchone()
            snippet = claim.text.rpartition("“")[-1].rstrip("”").strip("…")
            if row is None or not snippet or snippet not in row["text"]:
                errors.append(f"Narrative excerpt is absent from {source.accession} {source.locator}")
            elif (row["fiscal_year"], row["period_end"]) != (source.fiscal_year, source.period_end):
                errors.append(f"Narrative excerpt uses an incorrect reporting period: {source.accession}")
    return errors


def check_case(assistant, case):
    answer = assistant.answer(case["question"])
    errors = []
    if answer.status != case["status"]:
        errors.append(f"Expected {case['status']}, received {answer.status}")
    text = " ".join([claim.text for claim in answer.claims] + answer.limitations + answer.context)
    errors.extend(f"Missing expected evidence: {value}" for value in case["contains"] if value.lower() not in text.lower())
    kinds = sorted({claim.kind for claim in answer.claims})
    if kinds != sorted(case["kinds"]):
        errors.append(f"Unexpected claim classifications: {kinds}")
    refs = [reference for claim in answer.claims for reference in claim.citations]
    accessions = sorted({source.accession for source in refs})
    if accessions != sorted(case["accessions"]):
        errors.append(f"Unexpected filing accessions: {accessions}")
    for field, expected in case.items():
        if field in {"sections", "locators"}:
            attribute = "section" if field == "sections" else "locator"
            errors.extend(f"Missing citation {attribute}: {term}" for term in expected
                          if not any(term in getattr(ref, attribute) for ref in refs))
    errors.extend(citation_errors(assistant, answer))
    return {"id": case["id"], "passed": not errors, "errors": errors, "answer": answer.to_dict()}


def evaluate(assistant, cases: Path = CASES):
    results = [check_case(assistant, case) for case in json.loads(cases.read_bytes())]
    return {"passed": sum(item["passed"] for item in results), "total": len(results), "results": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", default=INDEX, type=Path)
    parser.add_argument("--analytics", default=ANALYTICS, type=Path)
    parser.add_argument("--warehouse", default=WAREHOUSE, type=Path)
    parser.add_argument("--questions", default=CASES, type=Path)
    parser.add_argument("--output", default=RESEARCH_REPORTS / "evaluation.json", type=Path)
    args = parser.parse_args()
    with ResearchAssistant(args.index, args.analytics, args.warehouse) as assistant:
        report = evaluate(assistant, args.questions)
    atomic_write(args.output, (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(f"Research evaluation: {report['passed']}/{report['total']} passed.")
    for item in report["results"]:
        if item["errors"]:
            print(f"  {item['id']}: {'; '.join(item['errors'])}")
    return int(report["passed"] != report["total"])


if __name__ == "__main__":
    raise SystemExit(main())
