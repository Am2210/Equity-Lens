# Evidence-backed research assistant

EquityLens answers bounded research questions from two local sources. The DuckDB analytics warehouse supplies deterministic financial facts and calculations. A SQLite FTS5 index supplies short excerpts of the original SEC filings. The answer generator uses Python rules and templates. It makes no model calls and requires no API key or subscription.

## Run it

Build the original SEC warehouse and financial analytics database first, as described in the README. Then build the index from the packaged original filing bytes.

```powershell
Expand-Archive -Path data/snapshots/2026-11-21-sec-10k-html.zip -DestinationPath data/frozen-10ks-2026-11-21
.\.venv\Scripts\python.exe -m src.equitylens.research index --offline --cache data/frozen-10ks-2026-11-21 --verify-manifest data/snapshots/2026-11-21-10k-manifest.json
.\.venv\Scripts\python.exe -m src.equitylens.research ask "Why did Visa operating cash flow increase in FY2025?"
.\.venv\Scripts\python.exe -m src.equitylens.research ask "Which company had the highest operating margin in FY2025?" --json
.\.venv\Scripts\python.exe -m src.equitylens.research_eval
```

The default research index is `data/warehouse/filing_index.sqlite`. The default evaluation output is `reports/generated/research/evaluation.json`. Common CLI paths, including `--index`, `--analytics` and `--warehouse`, go before the `ask` or `index` subcommand. `ResearchAssistant` also exposes the typed `Answer`, `Claim` and `Citation` objects to Python callers.

To retrieve missing documents from EDGAR, run `python -m src.equitylens.research index` with the existing private SEC User-Agent configuration. Retrieval uses original accessions and primary-document filenames from the validated submissions metadata, one request stream, the existing SEC pacing and retry behavior, and an on-disk cache. For a manual download, use the URL and `cache_path` for each filing in the [frozen 10-K manifest](../data/snapshots/2026-11-21-10k-manifest.json). Save the primary HTML response under `data/raw/filings/` and use `index --offline`. [SEC EDGAR access guidelines](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data)

## Sources and calculations

- **Reported fact.** Original 10-K statement values or an explicitly labeled later filing comparison. Numerical citations identify the issuer, metric, fiscal dates, filing date, accession and the source XBRL concept.
- **Derived calculation or comparison.** Formula results from the validated analytics warehouse. YoY claims cite both filing periods, historical growth dispersion cites the full series, and a ranked peer answer cites the underlying peer values.
- **Management statement or reported disclosure.** A bounded extractive excerpt from Business, Risk Factors or MD&A. The source link opens the SEC filing section, and the citation includes the local passage ordinal. Changes discussed in MD&A can use the filing's own comparative presentation, whose figures may differ from the as-originally-filed analytics series.
- **Hypothetical scenario.** A stored DCF proxy case from the previous analytics phase with its assumptions and source cash flow explicitly identified.
- **Model-generated interpretation.** No such claims are emitted in the current implementation. The typed result separates evidence and presentation so a future adapter could receive verified claims and passages. Any future provider integration would need independent configuration, including an environment-provided credential where required and separately metered access.

## Retrieval and limits

- The corpus has 15 original 10-Ks for the three companies in FY2021–FY2025, with the November 21, 2026 filing-date cutoff. It verifies embedded company CIK, report date and form against the submissions metadata. Filing HTML and SHA-256 hashes are retained.
- The extractor uses real EDGAR table-of-contents targets to isolate Item 1, Item 1A and Item 7. It preserves prose and inline figures, discards hidden elements and table layout, and leaves the original HTML intact. Inline reported figures in excerpts remain quoted text. Financial calculations use the validated DuckDB fields.
- Retrieval uses SQLite FTS5 with Porter stemming and deterministic ordering within company, year and section. Topic matching is lexical and prioritizes source precision. Wording, synonyms, qualifiers, document layouts and topics outside the indexed sections may produce an abstention even if another document or phrasing would surface relevant evidence.
- Name the issuer and optionally a fiscal year. The default is FY2025. A supported trend question without an explicit year uses the FY2021–FY2025 series. Growth measures use eligible adjacent periods and common-window CAGR uses FY2021–FY2025. FY2021 has no YoY value inside this series.
- Visa's fiscal year closes September 30. Mastercard and PayPal close December 31. Peer comparisons retain those date ranges and a request for an identical fiscal window involving Visa and another issuer can be unanswered. Missing line items remain missing, including PayPal's combined debt measure when its mapped current debt component is unavailable.
- The assistant can describe calculated similarities and differences. Cross-company causes, investment recommendations, future stock prices, market share, unsupported periods and unsupported metrics require evidence outside this application.
