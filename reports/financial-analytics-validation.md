# Financial analytics source validation

The engine used the frozen SEC source snapshot with an inclusive November 21, 2026 filing cutoff. It processed five original annual reports per issuer from FY2021 through FY2025. Visa reports to September 30, and Mastercard and PayPal report to December 31.

## Execution and coverage

- **15** annual analytics rows, **195** standardized statement and input rows, **215** source lineage rows, **3** peer summaries and **7** calculated insight records.
- **185** of 195 statement and input rows have values. The 10 missing entries are PayPal's five current debt components and the five combined debt amounts that require those components.
- FY2021 growth is blank for each issuer because the growth series begins within the selected window. Return on average assets is available for FY2021 using the opening balance shown in that year's original annual report.
- **27** hypothetical DCF proxy scenarios were executed. The common illustration at five years, 5% forecast growth, 10% discount and 2% terminal growth produces proxy discounted present values of **$312.05 billion for Visa**, **$248.16 billion for Mastercard** and **$80.47 billion for PayPal**. About **69.9%** of each modeled value is attributable to the discounted terminal term under those shared assumptions. These amounts depend on the proxy cash flow and hypothetical rates.

## Reconciliation to original filings

Source figures below are presented in USD millions. Derived metrics were independently recomputed from the labeled statement rows.

- **Visa FY2025, accession 0001403161-25-000089.** Net revenue 40,000, operating income 23,994 and net income 20,058. OCF of 23,059 less cash purchases of property, equipment and technology of 1,482 gives FCF of **21,577**. Current debt maturities of 5,569 plus noncurrent debt of 19,602 agree with Note 10's total carrying amount of **25,171**. Closing and opening assets of 99,627 and 94,511 give **20.66% ROA**. [Visa FY2025 10-K](https://www.sec.gov/Archives/edgar/data/1403161/000140316125000089/v-20250930.htm#)
- **Mastercard FY2025, accession 0001141391-26-000013.** Net revenue 32,791 and operating income 18,897 yield **57.63% operating margin**, consistent with the filing's one-decimal 57.6%. Consolidated net income is 14,968. OCF of 17,648 less property and equipment purchases of 489 gives FCF of **17,159**. Short-term debt of 749 plus long-term debt of 18,251 gives **19,000**. Closing and opening assets of 54,157 and 48,081 give **29.28% ROA**. [Mastercard FY2025 10-K](https://www.sec.gov/Archives/edgar/data/1141391/000114139126000013/ma-20251231.htm#)
- **PayPal FY2025, accession 0001633917-26-000024.** Net revenue 33,172, operating income 6,065 and net income 5,233. OCF of 6,416 less property and equipment purchases of 852 gives FCF of **5,564**. Closing and opening assets of 80,173 and 78,725 give **6.59% ROA**. The 78,725 comparative matches the FY2025 filing presentation. The original FY2024 balance sheet reported 81,611. The mapped debt series retains FY2025 noncurrent debt of **9,987**. Note 12 reports **1,396** of current term debt inside accrued liabilities that the mapped Company Facts component does not supply. [PayPal FY2025 10-K](https://www.sec.gov/Archives/edgar/data/1633917/000163391726000024/pypl-20251231.htm#) [PayPal FY2024 10-K](https://www.sec.gov/Archives/edgar/data/1633917/000163391725000019/pypl-20241231.htm#)
- **Mastercard FY2021, accession 0001141391-22-000023.** Net revenue of 18,884 and OCF of 9,463 serve as the starting values for the **14.79% revenue CAGR** and **16.86% OCF CAGR** through FY2025. [Mastercard FY2021 10-K](https://www.sec.gov/Archives/edgar/data/1141391/000114139122000023/ma-20211231.htm#)
- **PayPal FY2021 reporting basis.** The OCF series preserves the original 6,340. The FY2022 filing's reclassified FY2021 figure of 5,797 remains visible in the prior-stage comparison export. Historical OCF growth in this phase follows the as-originally-filed basis. [PayPal FY2022 10-K, Note 1](https://www.sec.gov/Archives/edgar/data/1633917/000163391723000033/pypl-20221231.htm#)

## Automated checks

**22 tests passed**, including the eight existing ingestion and warehouse tests. The analytics tests rebuild the input warehouse from the archived SEC bytes, verify their SHA-256 hashes, reconcile the FY2025 filing figures, and test annual period matching, revenue growth, CAGR, margins, FCF, ROA, negative and missing inputs, source lineage and sensitivity behavior. The run also validated each available standardized amount against the signed sum of its exact raw source inputs, including the two cash flow components for FCF.

A second run in a separate output directory regenerated all 10 exports byte-for-byte, including both charts. The source warehouse's SHA-256 was identical before and after both runs.

The generated peer brief uses calculated evidence for comparative observations. Business model and reporting-calendar differences still affect peer interpretation, and the ratios do not establish a market share, investment or business quality conclusion.
