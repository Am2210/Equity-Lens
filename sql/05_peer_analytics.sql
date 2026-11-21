CREATE MACRO positive_ratio(numerator, denominator) AS
    CASE WHEN denominator > 0 THEN numerator::DOUBLE / denominator::DOUBLE END;

CREATE MACRO growth_rate(current_value, prior_value) AS
    positive_ratio(current_value, prior_value) - 1;

CREATE MACRO compound_growth(first_value, last_value, intervals) AS
    CASE WHEN first_value > 0 AND last_value > 0 AND intervals > 0
         THEN pow(last_value::DOUBLE / first_value::DOUBLE, 1.0 / intervals) - 1 END;

CREATE MACRO average_assets(opening_value, closing_value) AS
    CASE WHEN opening_value > 0 AND closing_value > 0
         THEN (opening_value + closing_value) / 2 END;

CREATE MACRO adjacent_period(previous_year, previous_end, current_year, current_start) AS
    previous_year + 1 = current_year AND previous_end + 1 = current_start;

CREATE TABLE annual_financial_analytics AS
WITH annual AS (
    SELECT p.ticker, p.cik, p.fiscal_year, p.period_start, p.period_end,
           p.duration_days, p.original_accession, p.original_filed,
           max(s.amount) FILTER (WHERE s.metric = 'revenue') AS revenue,
           max(s.amount) FILTER (WHERE s.metric = 'operating_income') AS operating_income,
           max(s.amount) FILTER (WHERE s.metric = 'net_income') AS net_income,
           max(s.amount) FILTER (WHERE s.metric = 'assets') AS assets,
           max(s.amount) FILTER (WHERE s.metric = 'opening_assets') AS opening_assets,
           max(s.amount) FILTER (WHERE s.metric = 'liabilities') AS liabilities,
           max(s.amount) FILTER (WHERE s.metric = 'cash_and_equivalents') AS cash_and_equivalents,
           max(s.amount) FILTER (WHERE s.metric = 'interest_bearing_debt') AS interest_bearing_debt,
           max(s.amount) FILTER (WHERE s.metric = 'noncurrent_debt') AS noncurrent_debt,
           max(s.amount) FILTER (WHERE s.metric = 'current_debt') AS current_debt,
           max(s.amount) FILTER (WHERE s.metric = 'operating_cash_flow') AS operating_cash_flow,
           max(s.amount) FILTER (WHERE s.metric = 'capital_expenditure_payments') AS capex,
           max(s.amount) FILTER (WHERE s.metric = 'free_cash_flow') AS free_cash_flow
    FROM analysis_periods p JOIN statement_metrics s USING (cik, fiscal_year)
    GROUP BY ALL
), ratios AS (
    SELECT *, average_assets(opening_assets, assets) AS avg_assets,
           positive_ratio(operating_income, revenue) AS operating_margin,
           positive_ratio(net_income, revenue) AS net_profit_margin,
           positive_ratio(net_income, average_assets(opening_assets, assets)) AS return_on_assets,
           positive_ratio(revenue, average_assets(opening_assets, assets)) AS asset_turnover,
           positive_ratio(free_cash_flow, revenue) AS free_cash_flow_margin,
           positive_ratio(operating_cash_flow, net_income) AS ocf_to_net_income,
           positive_ratio(free_cash_flow, net_income) AS fcf_to_net_income
    FROM annual
)
SELECT n.*, p.fiscal_year AS comparison_fiscal_year, p.period_end AS comparison_period_end,
       n.revenue - p.revenue AS revenue_change_usd,
       CASE WHEN n.revenue >= 0 THEN growth_rate(n.revenue, p.revenue) END AS revenue_growth,
       growth_rate(n.operating_cash_flow, p.operating_cash_flow) AS operating_cash_flow_growth,
       n.operating_margin - p.operating_margin AS operating_margin_change
FROM ratios n
LEFT JOIN ratios p ON n.cik = p.cik
 AND adjacent_period(p.fiscal_year, p.period_end, n.fiscal_year, n.period_start);

CREATE TABLE peer_growth_summary AS
WITH windows AS (
    SELECT a.ticker, a.cik, s.first_fiscal_year, s.last_fiscal_year,
           s.last_fiscal_year - s.first_fiscal_year AS intervals,
           count(a.fiscal_year) AS years_observed,
           count(a.comparison_fiscal_year) AS adjacent_year_pairs,
           count(*) FILTER (WHERE a.revenue > 0) AS years_positive_revenue,
           count(*) FILTER (WHERE a.operating_cash_flow > 0) AS years_positive_ocf,
           max(a.revenue) FILTER (WHERE a.fiscal_year = s.first_fiscal_year) AS first_revenue,
           max(a.revenue) FILTER (WHERE a.fiscal_year = s.last_fiscal_year) AS last_revenue,
           max(a.operating_cash_flow) FILTER (WHERE a.fiscal_year = s.first_fiscal_year) AS first_ocf,
           max(a.operating_cash_flow) FILTER (WHERE a.fiscal_year = s.last_fiscal_year) AS last_ocf,
           count(a.revenue_growth) AS revenue_growth_observations,
           list_stddev_samp(list(a.revenue_growth ORDER BY a.fiscal_year)) AS revenue_growth_stddev,
           list_stddev_samp(list(a.revenue_growth ORDER BY a.fiscal_year) FILTER (
               WHERE a.fiscal_year IN (s.first_fiscal_year + 1, s.first_fiscal_year + 2)
           )) AS early_stddev,
           list_stddev_samp(list(a.revenue_growth ORDER BY a.fiscal_year) FILTER (
               WHERE a.fiscal_year IN (s.last_fiscal_year - 1, s.last_fiscal_year)
           )) AS late_stddev
    FROM annual_financial_analytics a CROSS JOIN analysis_snapshot s
    GROUP BY a.ticker, a.cik, s.first_fiscal_year, s.last_fiscal_year
)
SELECT *,
       CASE WHEN years_positive_revenue = intervals + 1 AND adjacent_year_pairs = intervals
            THEN compound_growth(first_revenue, last_revenue, intervals) END AS revenue_cagr,
       CASE WHEN years_positive_ocf = intervals + 1 AND adjacent_year_pairs = intervals
            THEN compound_growth(first_ocf, last_ocf, intervals) END AS operating_cash_flow_cagr,
       late_stddev - early_stddev AS growth_dispersion_change
FROM windows;

CREATE TABLE peer_benchmark AS
SELECT a.*, h.revenue_cagr, h.operating_cash_flow_cagr,
       h.revenue_growth_stddev, h.revenue_growth_observations,
       h.early_stddev, h.late_stddev, h.growth_dispersion_change
FROM annual_financial_analytics a JOIN peer_growth_summary h USING (cik)
WHERE a.fiscal_year = h.last_fiscal_year;

CREATE TABLE peer_insight_evidence AS
WITH candidates AS (
    SELECT 'largest_revenue_increase' AS insight, ticker, fiscal_year, comparison_fiscal_year AS from_year,
           revenue_change_usd::DOUBLE AS value, revenue_growth AS context_value,
           revenue_change_usd::DOUBLE AS score, 'USD' AS unit
    FROM annual_financial_analytics WHERE revenue_change_usd > 0
    UNION ALL
    SELECT 'largest_operating_margin_move', ticker, fiscal_year, comparison_fiscal_year,
           operating_margin_change, operating_margin, abs(operating_margin_change), 'fraction'
    FROM annual_financial_analytics WHERE operating_margin_change IS NOT NULL
    UNION ALL
    SELECT 'highest_ocf_cagr', ticker, last_fiscal_year, first_fiscal_year,
           operating_cash_flow_cagr, NULL, operating_cash_flow_cagr, 'fraction'
    FROM peer_growth_summary WHERE operating_cash_flow_cagr IS NOT NULL
    UNION ALL
    SELECT 'highest_latest_operating_margin', ticker, fiscal_year, NULL,
           operating_margin, NULL, operating_margin, 'fraction'
    FROM peer_benchmark WHERE operating_margin IS NOT NULL
    UNION ALL
    SELECT 'highest_latest_asset_turnover', ticker, fiscal_year, NULL,
           asset_turnover, return_on_assets, asset_turnover, 'multiple'
    FROM peer_benchmark WHERE asset_turnover IS NOT NULL
    UNION ALL
    SELECT 'highest_latest_roa', ticker, fiscal_year, NULL,
           return_on_assets, asset_turnover, return_on_assets, 'fraction'
    FROM peer_benchmark WHERE return_on_assets IS NOT NULL
    UNION ALL
    SELECT 'largest_growth_consistency_shift', ticker, last_fiscal_year, first_fiscal_year + 1,
           growth_dispersion_change, late_stddev, abs(growth_dispersion_change), 'fraction'
    FROM peer_growth_summary WHERE growth_dispersion_change IS NOT NULL
)
SELECT insight, ticker, fiscal_year, from_year, value, context_value, unit
FROM candidates
QUALIFY rank() OVER (PARTITION BY insight ORDER BY score DESC) = 1;

ALTER TABLE annual_financial_analytics ADD PRIMARY KEY (cik, fiscal_year);
ALTER TABLE peer_growth_summary ADD PRIMARY KEY (cik);
ALTER TABLE peer_benchmark ADD PRIMARY KEY (cik);
