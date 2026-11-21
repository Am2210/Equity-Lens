CREATE TABLE analysis_snapshot AS
SELECT * FROM sec.snapshot;

CREATE TABLE analysis_sources AS
SELECT * FROM sec.source_manifest;

CREATE TABLE analysis_periods AS
SELECT c.ticker, p.*
FROM sec.financial_reporting_periods p
JOIN sec.companies c USING (cik);

-- These concepts supplement the original warehouse selections. The filing
-- and context tests below also apply to the opening assets comparison.
CREATE TABLE statement_source_rules AS
SELECT * FROM (VALUES
    ('net_income', 'V', 'ProfitLoss', 'annual', 'consolidated_income_statement'),
    ('net_income', 'MA', 'ProfitLoss', 'annual', 'consolidated_income_statement'),
    ('net_income', 'PYPL', 'NetIncomeLoss', 'annual', 'consolidated_income_statement'),
    ('opening_assets', '*', 'Assets', 'opening', 'comparative_in_current_10k'),
    ('current_debt', '*', 'LongTermDebtCurrent', 'closing', 'current_maturities_of_debt'),
    ('noncurrent_debt', '*', 'LongTermDebtNoncurrent', 'closing', 'noncurrent_debt')
) AS rules(metric, ticker_scope, tag, context_type, basis);

CREATE TEMP TABLE direct_statement_inputs AS
WITH mapped AS (
    SELECT p.cik, p.fiscal_year, s.metric, s.metric_value AS amount, s.selected_fact_id AS fact_id,
           s.status, 'warehouse_original_10k' AS basis
    FROM analysis_periods p
    JOIN sec.standardized_financial_metrics s USING (cik, fiscal_year)
    WHERE s.metric IN (
        'revenue', 'operating_income', 'assets', 'liabilities', 'cash_and_equivalents',
        'operating_cash_flow', 'capital_expenditure_payments'
    )
), extra_candidates AS (
    SELECT p.cik, p.fiscal_year, rules.metric, rules.basis, r.fact_id, r.source_value,
           try_cast(r.source_value AS DECIMAL(38,12)) AS source_amount
    FROM analysis_periods p
    JOIN statement_source_rules rules ON rules.ticker_scope IN ('*', p.ticker)
    JOIN sec.raw_xbrl_facts r
      ON r.cik = p.cik AND r.accession = p.original_accession
     AND r.filed = p.original_filed AND r.form = '10-K'
     AND r.taxonomy = 'us-gaap' AND r.tag = rules.tag AND r.unit = 'USD'
     AND NOT r.is_custom_taxonomy
     AND r.end_date = CASE WHEN rules.context_type = 'opening' THEN p.period_start - 1 ELSE p.period_end END
     AND r.start_date IS NOT DISTINCT FROM CASE WHEN rules.context_type = 'annual' THEN p.period_start END
), resolved AS (
    SELECT cik, fiscal_year, metric, basis, count(DISTINCT source_amount) AS distinct_values,
           count(*) FILTER (WHERE source_amount IS NULL) AS invalid_count,
           min(source_amount) AS amount, min(fact_id) AS fact_id
    FROM extra_candidates
    GROUP BY cik, fiscal_year, metric, basis
), extra AS (
    SELECT p.cik, p.fiscal_year, rules.metric,
           CASE WHEN v.distinct_values = 1 AND v.invalid_count = 0 THEN v.amount END AS amount,
           CASE WHEN v.distinct_values = 1 AND v.invalid_count = 0 THEN v.fact_id END AS fact_id,
           CASE WHEN v.invalid_count > 0 THEN 'invalid_numeric_value'
                WHEN v.distinct_values > 1 THEN 'conflicting_original_facts'
                WHEN v.fact_id IS NULL THEN 'no_eligible_mapped_fact'
                ELSE 'available'
           END AS status, rules.basis
    FROM analysis_periods p
    JOIN statement_source_rules rules ON rules.ticker_scope IN ('*', p.ticker)
    LEFT JOIN resolved v ON v.cik = p.cik AND v.fiscal_year = p.fiscal_year AND v.metric = rules.metric
)
SELECT * FROM mapped UNION ALL SELECT * FROM extra;

CREATE TABLE statement_formulas AS
SELECT * FROM (VALUES
    ('free_cash_flow', 'operating_cash_flow', 1),
    ('free_cash_flow', 'capital_expenditure_payments', -1),
    ('interest_bearing_debt', 'current_debt', 1),
    ('interest_bearing_debt', 'noncurrent_debt', 1)
) AS formulas(metric, input_metric, coefficient);

CREATE TABLE statement_metrics AS
WITH derived AS (
    SELECT i.cik, i.fiscal_year, f.metric,
           CASE WHEN count(*) FILTER (WHERE i.status = 'available') = count(*)
                     AND count(*) FILTER (WHERE i.metric <> 'operating_cash_flow' AND i.amount < 0) = 0
                THEN sum(CASE WHEN f.coefficient = -1 THEN -i.amount ELSE i.amount END)
           END AS amount
    FROM statement_formulas f JOIN direct_statement_inputs i ON f.input_metric = i.metric
    GROUP BY i.cik, i.fiscal_year, f.metric
)
SELECT cik, fiscal_year, metric, amount, status, basis FROM direct_statement_inputs
UNION ALL
SELECT cik, fiscal_year, metric, amount,
       CASE WHEN amount IS NULL THEN 'unavailable_component' ELSE 'available' END,
       CASE WHEN metric = 'free_cash_flow' THEN 'operating_cash_less_capex'
            ELSE 'mapped_current_and_noncurrent_borrowings' END
FROM derived;

CREATE TABLE statement_lineage AS
WITH inputs AS (
    SELECT cik, fiscal_year, metric, metric AS input_metric, 1 AS coefficient, fact_id
    FROM direct_statement_inputs
    UNION ALL
    SELECT i.cik, i.fiscal_year, f.metric, i.metric, f.coefficient, i.fact_id
    FROM statement_formulas f JOIN direct_statement_inputs i ON f.input_metric = i.metric
)
SELECT p.ticker, i.*, r.taxonomy, r.tag, r.unit, r.source_value,
       r.start_date, r.end_date, r.source_fy, r.source_fp, r.frame,
       r.form, r.filed, r.accession,
       'https://www.sec.gov/Archives/edgar/data/' || cast(cast(i.cik AS BIGINT) AS VARCHAR) ||
       '/' || replace(r.accession, '-', '') || '/' || f.primary_document AS filing_url,
       'companyfacts/CIK' || i.cik || '.json' AS source_path, r.observation_index, s.sha256
FROM inputs i JOIN analysis_periods p USING (cik, fiscal_year)
JOIN sec.raw_xbrl_facts r USING (fact_id)
JOIN sec.filing_metadata f ON f.cik = r.cik AND f.accession = r.accession
JOIN analysis_sources s ON s.path = 'companyfacts/CIK' || i.cik || '.json';

ALTER TABLE analysis_periods ADD PRIMARY KEY (cik, fiscal_year);
ALTER TABLE statement_metrics ADD PRIMARY KEY (cik, fiscal_year, metric);
ALTER TABLE statement_lineage ADD PRIMARY KEY (cik, fiscal_year, metric, input_metric);
