# Financial ratio dictionary

The scope is FY2021–FY2025, with an inclusive SEC filing cutoff of November 21, 2026. All statement amounts are nominal USD. Ratios are stored as decimal fractions or multiples and shown as percentages where indicated. Each issuer retains its actual annual dates. Growth compares consecutive, contiguous reporting periods for the same issuer.

## Statement concepts

All source concepts below use the `us-gaap` taxonomy and USD unit for this dataset. The export `statement_lineage.csv` resolves each mapped observation to its concept, context dates, raw value, accession, filing URL, raw-cache observation index and source SHA-256. Derived metrics repeat the input lineage with signed coefficients. The denominator for ROA and asset turnover uses the traced `opening_assets` and `assets` statement inputs.

- **Revenue.** Consolidated income-statement top line. Visa uses `RevenueFromContractWithCustomerExcludingAssessedTax`. Mastercard and PayPal use `Revenues`. Mastercard's contract-revenue tag carried a different gross amount in FY2021. [Mastercard FY2021 10-K](https://www.sec.gov/Archives/edgar/data/1141391/000114139122000023/ma-20211231.htm#)
- **Operating income.** `OperatingIncomeLoss`.
- **Net income.** Consolidated income-statement net income. Visa and Mastercard use `ProfitLoss`. PayPal uses `NetIncomeLoss`, the tag on its consolidated income-statement net result. This resolves Mastercard's consolidated net income for this phase while the previous warehouse's more narrowly defined parent-attributable series retains its original coverage. [Mastercard FY2025 10-K](https://www.sec.gov/Archives/edgar/data/1141391/000114139126000013/ma-20251231.htm#) [PayPal FY2025 10-K](https://www.sec.gov/Archives/edgar/data/1633917/000163391726000024/pypl-20251231.htm#)
- **Total assets and opening assets.** `Assets` at fiscal year-end and at the day before the fiscal year begins. Both balances come from the current period's original 10-K. The opening observation can incorporate changes to the presentation of prior-year balances, such as PayPal's FY2024 comparative in its FY2025 report. For FY2021 ROA the FY2020 comparative balance is used solely as an opening balance.
- **Total liabilities.** `Liabilities` at year-end.
- **Cash and cash equivalents.** `CashAndCashEquivalentsAtCarryingValue` at year-end, as shown on the consolidated balance sheet.
- **Interest-bearing debt on the mapped carrying-value basis.** Current `LongTermDebtCurrent` plus noncurrent `LongTermDebtNoncurrent`. This measure follows the mapped balance-sheet borrowing lines, excludes leases and customer funds, and requires both components. PayPal's current component has no eligible whole-entity Company Facts observation for these years. The output preserves its separately identified noncurrent debt and leaves the combined amount null. PayPal's FY2025 Note 12 places current term-debt maturities within accrued liabilities. [Visa FY2025 10-K](https://www.sec.gov/Archives/edgar/data/1403161/000140316125000089/v-20250930.htm#) [Mastercard FY2025 10-K](https://www.sec.gov/Archives/edgar/data/1141391/000114139126000013/ma-20251231.htm#) [PayPal FY2025 10-K](https://www.sec.gov/Archives/edgar/data/1633917/000163391726000024/pypl-20251231.htm#)
- **Operating cash flow (OCF).** `NetCashProvidedByUsedInOperatingActivities`, preserving the source sign.
- **Capital expenditure payments (CapEx).** Positive or zero cash payment magnitude. Visa uses `PaymentsToAcquireProductiveAssets` for purchases of property, equipment and technology. Mastercard and PayPal use `PaymentsToAcquirePropertyPlantAndEquipment` for purchases of property and equipment. Omit acquisitions, proceeds from asset sales and noncash asset additions from this measure.
- **Free cash flow (FCF).** OCF − CapEx. Requires both observations and a nonnegative CapEx magnitude. FCF may be negative. This is a cash generation measure defined for this analysis.

## Ratios

- **Annual revenue growth.** `revenue / prior-year revenue − 1`. Requires a positive prior-year base and nonnegative current revenue in adjacent annual periods. FY2021 has no growth observation inside the selected scope.
- **Revenue CAGR.** `(FY2025 revenue / FY2021 revenue)^(1/4) − 1`. All three issuers have the same four-interval labeled window, with positive observations and contiguous periods. If coverage is incomplete, the common-window estimate is null.
- **Operating cash flow growth and CAGR.** Apply the adjacent growth and common-window CAGR formulas to OCF. Annual growth may describe a drop from positive to negative cash flow. CAGR requires positive cash flow across the window.
- **Operating margin.** `operating income / revenue`.
- **Net profit margin.** `consolidated net income / revenue`.
- **Return on assets.** `consolidated net income / ((opening assets + closing assets) / 2)`. Both assets inputs must be positive. This is the simple two-date average, so intra-year balances are outside the denominator.
- **Asset turnover.** `revenue / average assets`, using the same two-date denominator.
- **FCF margin.** `FCF / revenue`.
- **Cash flow conversion.** `OCF / consolidated net income` and `FCF / consolidated net income`. Both are multiples and require positive net income. A negative cash numerator is retained when the denominator qualifies.
- **Historical revenue growth volatility.** Sample standard deviation of available annual growth observations, in percentage points. Full-window results use four observations per issuer. The early-versus-late comparison uses two observations per window, FY2022–FY2023 versus FY2024–FY2025. These describe the sample's growth-rate dispersion and have no market-price input.
- **Operating margin change.** Current operating margin minus the previous contiguous fiscal-year margin, expressed in percentage points. The engine ranks the absolute change and reports its sign.

All ratios require eligible inputs and a positive denominator. Amount columns retain decimal precision, and ratios use double precision. Rounding in the reports is for display.

## Illustrative discounted cash flow proxy

`Scenario`, `discount_cash_flows`, and `sensitivity` in `src/equitylens/valuation.py` accept hypothetical forecast growth, horizon, discount rate and terminal growth. From a positive FY2025 FCF proxy, the model grows Year 1 cash flow by the forecast rate, discounts cash flows at year-end and discounts a Gordon-growth terminal amount from the last forecast year. It requires the discount rate to exceed the terminal growth rate.

The supplied grid is five years at 5% forecast growth with 8%, 10% and 12% discount rates and 1%, 2% and 3% terminal growth. All rates are illustrative inputs. Reported OCF less CapEx reflects cash items that have not been adjusted into unlevered enterprise or distributable equity cash flow. Debt, excess cash, share count and other claim adjustments are outside this scenario. The output is a present value of the modeled proxy cash stream.
