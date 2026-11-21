# EquityLens initial data validation

**Filing-date cutoff:** November 21, 2026, inclusive

**Reporting scope:** FY2021–FY2025

## Live ingestion and row counts

The SEC accepted the configured User-Agent. The live run cached the ticker mapping, three Company Facts responses and three submissions responses. No submissions archives were needed for the scoped history in this capture. The current warehouse contains:

- 3 companies and 7 source manifest records.
- 3,001 filing metadata rows and 72,975 raw XBRL observations. Mastercard supplied 1,001 filings and 27,820 observations. PayPal supplied 1,000 filings and 21,009 observations. Visa supplied 1,000 filings and 24,146 observations.
- 15 validated reporting periods, 225 company-year-metric rows and 443 eligible lineage rows. Of the lineage rows, 195 are selected source facts.

The source archive was extracted into a fresh cache and rebuilt offline with all seven SHA-256 hashes verified. The six regenerated report files matched byte-for-byte. The DuckDB file itself is a generated database.

## Verified annual periods

- **Visa, CIK 0001403161.** Five October 1 through September 30 periods, from October 1, 2020–September 30, 2021 through October 1, 2024–September 30, 2025. The original 10-Ks were filed November 18, 2021 through November 6, 2025.
- **Mastercard, CIK 0001141391.** Five January 1 through December 31 periods, FY2021 through FY2025. The original 10-Ks were filed February 11, 2022 through February 11, 2026.
- **PayPal, CIK 0001633917.** Five January 1 through December 31 periods, FY2021 through FY2025. The original 10-Ks were filed February 3, 2022 through February 3, 2026.

The period export lists all 15 original accession numbers and the report dates and filing dates. Each series contains one 366-day fiscal year, FY2024, and four 365-day fiscal years. A Visa fiscal-year label refers to a window that closes three months before the matching Mastercard or PayPal fiscal-year label.

## Coverage

195 of 225 requested observations are populated (86.7%). Visa has 60 of 75, Mastercard has 65 of 75 and PayPal has 70 of 75.

- **All three issuers, all five years.** Revenue, operating income, assets, current assets, cash and cash equivalents, liabilities, current liabilities, operating cash flow, investing cash flow, financing cash flow and capital expenditure payments.
- **Visa and PayPal, all five years.** Parent-attributable net income. Mastercard reports a consolidated `ProfitLoss` concept in the API, so the parent-attributable metric stays null.
- **Mastercard and PayPal, all five years.** Diluted EPS and parent equity. Visa reports diluted EPS by share class in the primary statements, and the API supplies an equity concept that includes noncontrolling interests. These do not populate the corresponding metrics in this snapshot. [Visa FY2025 10-K](https://www.sec.gov/Archives/edgar/data/1403161/000140316125000089/v-20250930.htm#)
- **All three issuers.** No eligible reported gross profit. No synthetic gross profit was calculated.

The inventory found no unrecognized taxonomy namespaces in the downloaded Company Facts files. Company Facts generally omits issuer extensions and dimensional facts, so this result describes API coverage. [SEC EDGAR API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)

## Primary filing spot checks

- The FY2025 warehouse revenue values agree with the original 10-Ks at $40.000 billion for Visa, $32.791 billion for Mastercard and $33.172 billion for PayPal. [Visa FY2025 10-K](https://www.sec.gov/Archives/edgar/data/1403161/000140316125000089/v-20250930.htm#) [Mastercard FY2025 10-K](https://www.sec.gov/Archives/edgar/data/1141391/000114139126000013/ma-20251231.htm#) [PayPal FY2025 10-K](https://www.sec.gov/Archives/edgar/data/1633917/000163391726000024/pypl-20251231.htm#)
- Mastercard FY2021 net revenue is $18.884 billion. The $29.845 billion gross revenue observation remains in the raw XBRL table. [Mastercard FY2021 10-K](https://www.sec.gov/Archives/edgar/data/1141391/000114139122000023/ma-20211231.htm#)
- Visa FY2025 capital expenditure payments are $1.482 billion. The warehouse uses the positive XBRL payment magnitude for that cash outflow. [Visa FY2025 10-K](https://www.sec.gov/Archives/edgar/data/1403161/000140316125000089/v-20250930.htm#)
- PayPal reported FY2021 operating cash flow of $6.340 billion originally and reclassified it to $5.797 billion in the FY2022 10-K. The baseline retains $6.340 billion and the comparative appears in the change report. In total, PayPal supplied 20 changed filing comparisons across 15 distinct metric-periods. These records describe value changes and carry filing-level provenance. [PayPal FY2022 10-K, Note 1](https://www.sec.gov/Archives/edgar/data/1633917/000163391723000033/pypl-20221231.htm#)

## Tests and outstanding items

**8 tests passed** on Python 3.12.7 with DuckDB 1.4.4. The tests cover SEC pacing, throttling retries, access denials, offline and invalid-cache behavior, submissions archives, annual period selection, cutoff filtering, scoped mappings, custom namespace handling, conflicting facts and amended comparisons.

The SEC download and offline validation are complete. Cross-issuer analysis should carry fiscal period dates, distinguish the 30 unavailable observations and use the PayPal comparison export when interpreting changes against later presentations.
