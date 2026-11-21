# EquityLens portfolio review

November 21, 2026 · Windows · Python 3.12 · Frozen FY2021–FY2025 snapshot

## Executed checks

- **55 automated tests passed**, including ingestion, taxonomy and period selection, statement lineage, valuation, retrieval, and Streamlit interactions. Python compilation and the dependency consistency check passed.
- **25 of 25 research evaluation questions passed.** The evaluation verified answer values, expected sources, claim types, dates and excerpt locations. It included abstention on an unsupported mixed-issuer comparison.
- **Live EDGAR refresh succeeded in an isolated directory.** Its seven response hashes matched the frozen API manifest. It produced 72,975 raw facts and the same 15 fiscal periods and 225 metric slots as the frozen build.
- **The complete snapshot rebuilt offline from the archives.** All six ingestion exports, all ten analytics exports, and the SQLite filing index matched the existing artifacts byte-for-byte. The evaluation output also matched byte-for-byte after rerunning the revised question set against both stores. DuckDB files were checked through their outputs and queries.
- **All five Streamlit pages rendered locally.** The interaction suite exercised shared period and company selectors, peer metric selection, missing debt and its surviving component lineage, a grounded notebook answer and abstention, and valid and invalid DCF settings. The README screenshots come from the live workbench.

## Filing reconciliation

The following checks use the original FY2025 financial statements. Financial amounts are in USD billions.

- **Visa.** Revenue $40.000, operating income $23.994, operating cash flow $23.059, and mapped capital purchases $1.482. These inputs give 59.98% displayed operating margin and $21.577 FCF. [Visa FY2025 10-K](https://www.sec.gov/Archives/edgar/data/1403161/000140316125000089/v-20250930.htm)
- **Mastercard.** Revenue $32.791, operating income $18.897, operating cash flow $17.648, and capital purchases $0.489. These give 57.63% operating margin and $17.159 FCF. [Mastercard FY2025 10-K](https://www.sec.gov/Archives/edgar/data/1141391/000114139126000013/ma-20251231.htm)
- **PayPal.** Revenue $33.172, operating income $6.065, operating cash flow $6.416, and capital purchases $0.852. These give 18.28% operating margin and $5.564 FCF. The combined mapped debt remains null because the current component is unavailable. [PayPal FY2025 10-K](https://www.sec.gov/Archives/edgar/data/1633917/000163391726000024/pypl-20251231.htm)

## Final changes and publication review

- An issuer-year remains visible when its revenue fact is missing. Other available statement data and original filing links stay accessible.
- The research assistant abstains when it recognizes only one side of a requested comparison and no second fiscal year is specified.
- Local credentials, virtual environments, extracted caches, warehouse databases, generated reports, private keys, and test artifacts are excluded. The commit retains compact public SEC source archives, hashes, and five screenshots for reproducibility and demonstration.
- Publication review covered the initial staged tree, including ZIP members, with targeted checks for the configured private contact value, local user paths, credential markers, and ignored artifact extensions. The repository had no pre-existing Git history. The prepared first commit uses a neutral local author identity.

## Remaining limitations

- Dense grids use horizontal scrolling on narrow screens. The application offers CSV exports and Streamlit’s expanded table view for inspecting wide lineage and sensitivity tables.
- The scoped research tests are a regression suite. Lexical retrieval is sensitive to phrasing, and only three narrative 10-K sections are indexed. The assistant has no generative model integration or market data feed.
- The repository owner can choose a public commit identity, source-code license, and repository visibility before publishing. The local repository has no configured remote.
