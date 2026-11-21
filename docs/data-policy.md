# Data policy

## Snapshot and financial periods

- Verify ticker and CIK in the SEC ticker list and submissions profile, and verify the CIK in Company Facts. Check the expected filing calendar against the submissions profile and actual original 10-K report dates.
- Take the earliest available original 10-K by filing date, acceptance timestamp and accession for each fiscal year-end. Use the prior original 10-K's report date plus one day as the fiscal-year start. FY2020 supplies the FY2021 starting anchor. Visa closes September 30. Mastercard and PayPal close December 31.
- Duration facts require the exact start and end dates and a 350–380 day annual interval. Instant facts require the exact period end and an empty start date. `fy`, `fp` and `frame` remain available as source fields. For comparative facts, `fy` often identifies the filing's fiscal year rather than the observation's fiscal year.
- Store facts with an SEC filed date on or before the cutoff. Keep older facts and filings in the normalized source tables while the metric output is limited to the five requested reporting years. The raw cache retains the SEC responses as received. The cutoff is based on filing date, and the frozen source bytes preserve any API corrections already present at capture.
- Filing metadata combines the SEC submissions profile's recent block with archives whose filing date ranges intersect the scoped history from January 1, 2020 through the cutoff. Older raw facts can reference accessions outside that metadata. Metric selection always requires matching submissions metadata by CIK, accession, form and filing date. [SEC EDGAR API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)

## Mapping and selection

- Use the exact taxonomy, concept and unit in `sql/02_mappings.sql`. Financial amounts are in USD and diluted EPS is in USD per share. Payment metrics preserve the positive XBRL payment magnitude and cash-flow totals retain their reported sign.
- Revenue represents the consolidated income-statement top line. Mastercard and PayPal use `Revenues`. Visa uses `RevenueFromContractWithCustomerExcludingAssessedTax`. Mastercard's FY2021 filing disclosed $29.845 billion in gross revenue under the contract-revenue tag and $18.884 billion in net revenue under `Revenues`. A universal revenue fallback could select the gross amount. [Mastercard FY2021 10-K](https://www.sec.gov/Archives/edgar/data/1141391/000114139122000023/ma-20211231.htm#)
- Capital expenditure payments use the issuer's cash-flow line for productive asset purchases. Visa uses `PaymentsToAcquireProductiveAssets` for purchases of property, equipment and technology. Mastercard and PayPal use `PaymentsToAcquirePropertyPlantAndEquipment`. The precise asset mix follows each issuer's filing. [Visa FY2023 10-K](https://www.sec.gov/Archives/edgar/data/1403161/000140316123000099/v-20230930.htm#) [Visa FY2025 10-K](https://www.sec.gov/Archives/edgar/data/1403161/000140316125000089/v-20250930.htm#)
- Parent net income and parent equity require parent-attributable concepts. USD-per-share facts require a whole-entity diluted EPS concept. The pipeline leaves these metrics null where the mapped fact is unavailable. Company Facts generally omits issuer-specific extensions and dimensional facts. The inventory flags namespace prefixes outside the known standard set for review. SEC's ECD and FFD are standard taxonomies outside the financial metric mapping. [SEC XBRL taxonomy guide](https://www.sec.gov/files/edgar/filer-information/specifications/xbrl-guide-2026-11-20.pdf)
- Select only a fact from the original 10-K. Within a filing, identical values collapse for selection by mapping priority, taxonomy, tag and raw fact ID. Different eligible values within the same filing produce a conflict and leave the standardized amount null. The fact ID links the selection to the raw observation, including its index inside the original concept/unit array.
- Keep eligible 10-K/A and later annual comparative facts in lineage. Flag differences and ambiguous filings. A changed comparative may reflect a correction, reclassification or presentation change. The data records the difference and preserves the original value. A missing original with later eligible candidates is labeled separately.
- Store the source numeric value as lossless text and selected values as DuckDB decimals. The build verifies exact agreement for castable candidates before publishing the database.

## Audit a metric

```sql
SELECT c.ticker, l.fiscal_year, l.metric, l.filing_role, l.is_selected,
       r.taxonomy, r.tag, r.unit, r.source_value, r.start_date, r.end_date,
       r.source_fy, r.source_fp, r.frame, r.form, r.filed, r.accession,
       f.primary_document
FROM metric_to_source_lineage l
JOIN raw_xbrl_facts r USING (fact_id)
JOIN companies c ON c.cik = l.cik
JOIN filing_metadata f ON f.cik = r.cik AND f.accession = r.accession
WHERE c.ticker = 'PYPL' AND l.fiscal_year = 2021 AND l.metric = 'operating_cash_flow'
ORDER BY l.filed, l.accession, l.fact_id;
```
