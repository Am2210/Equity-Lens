import json
from dataclasses import replace
from datetime import date
from pathlib import Path
from zipfile import ZipFile

import duckdb
import pytest

from src.equitylens.analytics import build_analytics
from src.equitylens.filing_index import BUSINESS, MDA, RISK, build_index, chunk_section, extract_sections
from src.equitylens.filings import Filing
from src.equitylens.research import ResearchAssistant
from src.equitylens.research_eval import CASES, check_case
from src.equitylens.research_types import Claim
from src.equitylens.sec import SecClient, SecError
from src.equitylens.sources import CUTOFF
from src.equitylens.warehouse import build

SNAPSHOTS = Path(__file__).resolve().parents[1] / "data/snapshots"
QUESTION_CASES = json.loads(CASES.read_bytes())


@pytest.fixture(scope="module")
def research(tmp_path_factory):
    workspace = tmp_path_factory.mktemp("research")
    cache = workspace / "raw"
    filings = workspace / "html"
    warehouse = workspace / "source.duckdb"
    analytics = workspace / "analytics.duckdb"
    index = workspace / "filings.sqlite"
    with ZipFile(SNAPSHOTS / "2026-11-21-sec-json.zip") as source_archive:
        source_archive.extractall(cache)
    with ZipFile(SNAPSHOTS / "2026-11-21-sec-10k-html.zip") as filing_archive:
        filing_archive.extractall(filings)
    source_client = SecClient(cache, "EquityLens tests", "", offline=True)
    with source_client.session, duckdb.connect(str(warehouse)) as database:
        build(database, source_client, CUTOFF)
    original_manifest = json.loads((SNAPSHOTS / "2026-11-21-source-manifest.json").read_bytes())
    assert sorted(source_client.sources, key=lambda row: row["path"]) == original_manifest["sources"]
    with duckdb.connect(str(analytics)) as database:
        build_analytics(database, warehouse)
    html_client = SecClient(filings, "EquityLens tests", "", offline=True)
    with html_client.session:
        count, sections = build_index(
            warehouse, html_client, index, workspace / "index_manifest.json",
            SNAPSHOTS / "2026-11-21-10k-manifest.json",
        )
    assert count == 15
    assert set(sections) == {BUSINESS, RISK, MDA}
    with ResearchAssistant(index, analytics, warehouse) as assistant:
        yield assistant


@pytest.mark.parametrize("case", QUESTION_CASES, ids=[case["id"] for case in QUESTION_CASES])
def test_research_question_against_frozen_filings(research, case):
    result = check_case(research, case)
    assert result["passed"], result["errors"]


def test_anchored_risk_chunks_do_not_include_item_1c(research):
    assert research.index.execute("""
        SELECT count(*) FROM passages
        WHERE section = ? AND upper(text) LIKE '%ITEM 1C. CYBERSECURITY%'
    """, (RISK,)).fetchone()[0] == 0


def test_extraction_retains_inline_figures_and_original_anchor():
    filing = Filing("V", "Visa", "0001403161", 2025, date(2024, 10, 1), date(2025, 9, 30),
                    "0001403161-25-000089", date(2025, 11, 6), "example.htm")
    filler = "Our financial disclosures provide supporting information and reporting details. " * 20
    sample = f"""
    <html><body>
      <ix:hidden><span name="dei:EntityCentralIndexKey">0001403161</span></ix:hidden>
      <span name="dei:DocumentType">10-K</span>
      <span name="dei:DocumentPeriodEndDate">September 30, 2025</span>
      <table><tr><td><a href="#b">Business</a></td><td><a href="#r">Risk Factors</a></td>
      <td><a href="#s">Unresolved Staff Comments</a></td><td><a href="#p">Properties</a></td>
      <td><a href="#m">Management's Discussion and Analysis</a></td>
      <td><a href="#x">Quantitative and Qualitative Disclosures about Market Risk</a></td></tr></table>
      <div id="b">Business</div><div>{filler}</div>
      <div id="r">Risks</div><div>{filler}</div><div id="s">Section end marker</div>
      <div id="p">Properties</div><div id="m">MD&amp;A</div>
      <div>Revenue rose <span>$</span><span>1,234.50</span> million, or <span>10.2</span>%.</div>
      <div style="display:none">hidden text outside visible prose</div><div>{filler}</div>
      <div id="x">Market Risk</div></body></html>
    """.encode("utf-8")
    sections = {section: (anchor, blocks) for section, anchor, blocks in extract_sections(sample, filing)}
    risk_anchor, risk_blocks = sections[RISK]
    assert risk_anchor == "r"
    assert not any("Section end marker" in block for block in risk_blocks)
    anchor, blocks = sections[MDA]
    passages = list(chunk_section(filing.accession, MDA, anchor, blocks))
    assert anchor == "m"
    assert any("$1,234.50 million, or 10.2%." in passage.text for passage in passages)
    assert not any("hidden text" in passage.text for passage in passages)
    with pytest.raises(SecError, match="identity differs"):
        list(extract_sections(sample, replace(filing, cik="0001141391")))


def test_material_claim_without_source_is_rejected():
    with pytest.raises(ValueError, match="source citation"):
        Claim("Reported fact", "Unsupported", ())
