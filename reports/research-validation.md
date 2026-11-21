# Research assistant validation

The research build indexed **15 original SEC Form 10-Ks**, five per issuer from FY2021 through FY2025. The validated warehouse supplied each accession, report period, filing date and primary-document filename. The filing-date cutoff is November 21, 2026.

## Source and retrieval checks

- The build checked each document's embedded CIK, form and financial reporting date against the submissions record.
- The SQLite full-text index contains **2,827 passages**. Business contributed **811**, Risk Factors **1,223** and MD&A **793**. Every passage has a filing accession, an original EDGAR section anchor and a local ordinal.
- An offline rebuild from the frozen HTML archive verified all 15 file hashes and reproduced both the SQLite index and its source manifest byte-for-byte.

## Executed question evaluation

**24 of 24** cases met the expected answer, source and abstention criteria. The results contain the actual answer object for each question, including claim classifications, URLs, source accessions, fiscal periods, filing dates, XBRL tags or passage identifiers, and evaluation checks.

The complete project suite passed **49 tests**. It includes the question cases, checks for citation-free claims and incorrect filing identity, checks for section boundaries and inline figures, and the existing ingestion and financial analytics tests.

- **15 answered** with verified financial evidence, narrative excerpts, comparisons or the labeled hypothetical scenario.
- **3 partial** provided supported evidence and withheld the unsupported portion. These covered PayPal's partial debt coverage, Visa's incorrect cash-flow premise and a request for causes of peer-margin differences.
- **4 insufficient evidence** covered the missing FY2021 growth denominator, the requested identical reporting period involving Visa, an unsupported risk topic and an out-of-scope FY2026 period.
- **2 unsupported** covered a future stock price request and an adjusted operating margin outside the validated metric catalog.

Representative observations checked in the run:

- Visa's FY2025 free cash flow was **$21.577 billion**, calculated from the operating cash flow and capital expenditure lines in the original 10-K. [Visa FY2025 10-K](https://www.sec.gov/Archives/edgar/data/1403161/000140316125000089/v-20250930.htm#)
- Visa FY2025 operating cash flow grew **15.58%** using the two original filings. The assistant separately quoted the issuer's MD&A explanation, which identified business growth, income-tax payment timing and an offset from higher incentives. [Visa FY2024 10-K](https://www.sec.gov/Archives/edgar/data/1403161/000140316124000058/v-20240930.htm#) [Visa FY2025 MD&A](https://www.sec.gov/Archives/edgar/data/1403161/000140316125000089/v-20250930.htm#i3e21d382a73642188017c034fc47d460_46)
- PayPal's FY2021 operating cash flow was **$6.340 billion** in the original filing and **$5.797 billion** in later comparative disclosures. The answer labeled and cited each filing separately. [PayPal FY2021 10-K](https://www.sec.gov/Archives/edgar/data/1633917/000163391722000027/pypl-20211231.htm#) [PayPal FY2022 10-K](https://www.sec.gov/Archives/edgar/data/1633917/000163391723000033/pypl-20221231.htm#) [PayPal FY2023 10-K](https://www.sec.gov/Archives/edgar/data/1633917/000163391724000024/pypl-20231231.htm#)

The evaluation checks expected numeric results, evidence classes and filing accessions. It validates every returned filing URL and filed date against submissions metadata, and checks that each narrative excerpt occurs at the cited position in the index. Passing these in-scope prompts measures the frozen research workflow and provides regression coverage. The lexical retrieval and supported query patterns do not establish unrestricted question-answering accuracy.
