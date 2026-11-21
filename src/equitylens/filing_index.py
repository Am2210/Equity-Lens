"""Extract anchored SEC filing prose and build a portable SQLite FTS5 index."""

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import unquote

from lxml import html

from .filings import Filing, original_filings, read_filing
from .sec import SecError, atomic_write

BUSINESS = "Item 1. Business"
RISK = "Item 1A. Risk Factors"
MDA = "Item 7. Management’s Discussion and Analysis"
SECTIONS = (BUSINESS, RISK, MDA)
BOUNDARIES = (
    (r"(?:item\s*1\.?\s*)?business", BUSINESS),
    (r"(?:item\s*1a\.?\s*)?risk factors", RISK),
    (r"(?:item\s*1b\.?\s*)?unresolved staff comments", "staff comments"),
    (r"(?:item\s*2\.?\s*)?properties", "properties"),
    (r"(?:item\s*7\.?\s*)?management['’]s discussion and analysis.*", MDA),
    (r"(?:item\s*7a\.?\s*)?quantitative and qualitative disclosures about market risk", "market risk"),
)
BLOCK_TAGS = {
    "div", "p", "section", "li", "ul", "ol", "header", "footer", "blockquote",
    "h1", "h2", "h3", "h4", "h5", "h6", "table", "figure", "hr",
}
SKIP_TAGS = {"table", "script", "style", "noscript", "svg", "ix:hidden", "ix:header"}
HIDDEN = re.compile(r"(?:display\s*:\s*none|visibility\s*:\s*hidden)", re.I)
TOKEN = re.compile(r"[^\W_]+(?:[-’'][^\W_]+)*", re.UNICODE)


@dataclass(frozen=True)
class Passage:
    accession: str
    section: str
    anchor: str
    ordinal: int
    text: str


def clean(text):
    return " ".join(text.replace("\u200b", "").split())


def identify_document(document, filing: Filing):
    def dei_field(name):
        values = {clean(node.text_content()) for node in document.xpath("//*[@name=$name]", name=f"dei:{name}")}
        if len(values) != 1:
            raise SecError(f"Missing or ambiguous {name} in {filing.url}")
        return values.pop()

    cik = dei_field("EntityCentralIndexKey")
    form = dei_field("DocumentType")
    report_date = dei_field("DocumentPeriodEndDate")
    try:
        period_end = datetime.strptime(report_date, "%B %d, %Y").date()
    except ValueError as exc:
        raise SecError(f"Unrecognized filing period-end date in {filing.url}") from exc
    if not cik.isdecimal() or int(cik) != int(filing.cik) or form != "10-K" or period_end != filing.period_end:
        raise SecError(f"Primary document identity differs from submissions metadata for {filing.url}")


def section_anchors(document, filing):
    targets = {}
    for link in document.xpath('//a[starts-with(@href, "#")]'):
        label = clean(link.text_content()).lower()
        for pattern, section in BOUNDARIES:
            if re.fullmatch(pattern, label):
                anchor = unquote(link.get("href")[1:])
                target = document.xpath('//*[@id=$anchor or @name=$anchor]', anchor=anchor)
                if len(target) == 1:
                    targets.setdefault(section, set()).add(anchor)
                break
    if any(len(targets.get(section, ())) != 1 for _, section in BOUNDARIES):
        raise SecError(f"Cannot resolve unique section boundaries for {filing.url}")
    return {next(iter(anchors)): section for section, anchors in targets.items()}


def extract_sections(content: bytes, filing: Filing):
    document = html.fromstring(content, parser=html.HTMLParser(encoding="utf-8", no_network=True))
    identify_document(document, filing)
    anchors = section_anchors(document, filing)
    paragraphs = {section: [] for section in SECTIONS}
    observed = []
    buffer = []
    active = None

    def flush():
        if buffer and active in paragraphs:
            text = clean("".join(buffer))
            if text and not re.fullmatch(r"(?:\d+|table of contents|(?:fy\s*20\d{2}\s+)?form 10-k\s*\d*)", text, re.I):
                paragraphs[active].append(text)
        buffer.clear()

    def walk(node):
        nonlocal active
        if not isinstance(node.tag, str):
            return
        tag = node.tag.lower()
        target = node.get("id") or node.get("name")
        if target in anchors:
            flush()
            active = anchors[target]
            observed.append(active)
        if tag in BLOCK_TAGS:
            flush()
        if tag in SKIP_TAGS or node.get("hidden") is not None or HIDDEN.search(node.get("style", "")):
            return
        if tag == "br":
            buffer.append(" ")
            return
        if node.text:
            buffer.append(node.text)
        for child in node:
            walk(child)
            if child.tail:
                buffer.append(child.tail)
        if tag in BLOCK_TAGS:
            flush()

    walk(document.find("body"))
    flush()
    if observed != [section for _, section in BOUNDARIES]:
        raise SecError(f"Section boundaries are outside the expected 10-K order for {filing.url}")
    source_anchors = {section: anchor for anchor, section in anchors.items()}
    for section, blocks in paragraphs.items():
        if sum(len(block) for block in blocks) < 1_000:
            raise SecError(f"Too little extracted prose for {section} in {filing.url}")
        yield section, source_anchors[section], blocks


def chunk_section(accession, section, anchor, paragraphs, *, word_limit=190):
    """Pack complete prose blocks where practical; split overlong blocks on word boundaries."""
    parts = []
    count = 0
    ordinal = 0
    for paragraph in paragraphs:
        words = paragraph.split()
        for offset in range(0, len(words), word_limit):
            piece = words[offset:offset + word_limit]
            if parts and count + len(piece) > word_limit:
                ordinal += 1
                yield Passage(accession, section, anchor, ordinal, "\n".join(parts))
                parts, count = [], 0
            parts.append(" ".join(piece) if len(words) > word_limit else paragraph)
            count += len(piece)
    if parts:
        yield Passage(accession, section, anchor, ordinal + 1, "\n".join(parts))


def build_index(warehouse, client, index: Path, manifest: Path, verify_manifest: Path | None = None):
    index.parent.mkdir(parents=True, exist_ok=True)
    metadata = []
    counts = dict.fromkeys(SECTIONS, 0)
    with TemporaryDirectory(dir=index.parent) as temporary:
        staged = Path(temporary) / "filing_index.sqlite"
        connection = sqlite3.connect(staged)
        try:
            connection.executescript("""
                CREATE TABLE filings(
                    accession TEXT PRIMARY KEY, ticker TEXT NOT NULL, company TEXT NOT NULL,
                    cik TEXT NOT NULL, fiscal_year INTEGER NOT NULL, period_start TEXT NOT NULL,
                    period_end TEXT NOT NULL, filed TEXT NOT NULL, url TEXT NOT NULL,
                    sha256 TEXT NOT NULL, bytes INTEGER NOT NULL
                );
                CREATE VIRTUAL TABLE passages USING fts5(
                    accession UNINDEXED, section UNINDEXED, anchor UNINDEXED, ordinal UNINDEXED,
                    text, tokenize='porter unicode61 remove_diacritics 2'
                );
            """)
            for filing in original_filings(warehouse):
                content = read_filing(client, filing)
                source = filing.manifest_row(content)
                metadata.append(source)
                connection.execute("""
                    INSERT INTO filings VALUES (:accession, :ticker, :company, :cik, :fiscal_year,
                        :period_start, :period_end, :filed, :url, :sha256, :bytes)
                """, {key: str(value) if key in ("period_start", "period_end", "filed") else value
                      for key, value in source.items()})
                for section, anchor, blocks in extract_sections(content, filing):
                    passages = list(chunk_section(filing.accession, section, anchor, blocks))
                    counts[section] += len(passages)
                    connection.executemany("INSERT INTO passages VALUES (?, ?, ?, ?, ?)", [
                        (p.accession, p.section, p.anchor, p.ordinal, p.text) for p in passages
                    ])
            connection.execute("INSERT INTO passages(passages) VALUES ('integrity-check')")
            connection.commit()
        finally:
            connection.close()
        payload = {"documents": metadata, "passages_by_section": counts}
        manifest_bytes = (json.dumps(payload, default=str, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        if verify_manifest and json.loads(verify_manifest.read_bytes()) != json.loads(manifest_bytes):
            raise SecError("Filing sources or passage counts differ from the verified filing manifest.")
        staged.replace(index)
    atomic_write(manifest, manifest_bytes)
    return len(metadata), counts


def open_index(index: Path):
    connection = sqlite3.connect(index.resolve(strict=True).as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def search(connection, match: str, ticker: str, fiscal_year: int, section: str, limit=12):
    return connection.execute("""
        SELECT f.*, p.section, p.anchor, p.ordinal, p.text, bm25(passages) AS rank
        FROM passages p JOIN filings f USING (accession)
        WHERE passages MATCH ? AND f.ticker = ? AND f.fiscal_year = ? AND p.section = ?
        ORDER BY rank, p.ordinal LIMIT ?
    """, (match, ticker, fiscal_year, section, limit)).fetchall()
