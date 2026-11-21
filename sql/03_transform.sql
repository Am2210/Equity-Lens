CREATE TABLE financial_reporting_periods AS
WITH annual_filings AS (
    SELECT c.cik, year(f.report_end) AS fiscal_year, f.report_end,
           f.accession, f.filed,
           row_number() OVER (
               PARTITION BY c.cik, f.report_end
               ORDER BY f.filed, f.accepted_timestamp_raw NULLS LAST, f.accession
           ) AS filing_order
    FROM filing_metadata f
    JOIN companies c USING (cik)
    CROSS JOIN snapshot s
    WHERE f.form = '10-K'
      AND f.filed <= s.as_of_date
      AND f.filed >= f.report_end
      AND strftime(f.report_end, '%m%d') = c.fiscal_year_end_mmdd
      AND year(f.report_end) BETWEEN s.first_fiscal_year - 1 AND s.last_fiscal_year
), anchors AS (
    SELECT *, lag(report_end) OVER (PARTITION BY cik ORDER BY fiscal_year) AS prior_end
    FROM annual_filings
    WHERE filing_order = 1
)
SELECT a.cik, a.fiscal_year, a.prior_end + 1 AS period_start, a.report_end AS period_end,
       date_diff('day', a.prior_end, a.report_end) AS duration_days,
       a.accession AS original_accession, a.filed AS original_filed
FROM anchors a
CROSS JOIN snapshot s
WHERE a.fiscal_year BETWEEN s.first_fiscal_year AND s.last_fiscal_year;

CREATE TABLE metric_to_source_lineage AS
WITH eligible AS (
    SELECT p.cik, p.fiscal_year, d.metric, r.fact_id, r.accession, r.filed,
           r.form, r.taxonomy, r.tag, r.unit, m.priority,
           try_cast(r.source_value AS DECIMAL(38,12)) AS candidate_value,
           CASE
             WHEN r.accession = p.original_accession THEN 'original_10k'
             WHEN f.report_end = p.period_end AND r.form = '10-K/A' THEN 'amended_10k'
             WHEN f.report_end > p.period_end THEN 'later_annual_comparative'
             ELSE 'other_same_period_10k'
           END AS filing_role
    FROM financial_reporting_periods p
    JOIN companies c ON p.cik = c.cik
    JOIN raw_xbrl_facts r ON r.cik = p.cik AND r.end_date = p.period_end
    JOIN metric_mappings m
      ON r.taxonomy = m.taxonomy AND r.tag = m.tag AND m.ticker_scope IN ('*', c.ticker)
    JOIN metric_definitions d ON m.metric = d.metric AND r.unit = d.unit
    JOIN filing_metadata f
      ON r.cik = f.cik AND r.accession = f.accession
     AND r.form = f.form AND r.filed = f.filed
    CROSS JOIN snapshot s
    WHERE r.form IN ('10-K', '10-K/A') AND r.filed <= s.as_of_date
      AND r.filed >= p.original_filed AND f.report_end >= p.period_end
      AND NOT r.is_custom_taxonomy
      AND (
          (d.period_type = 'instant' AND r.start_date IS NULL)
          OR (d.period_type = 'duration' AND r.start_date = p.period_start
              AND p.duration_days BETWEEN 350 AND 380)
      )
), filing_stats AS (
    SELECT cik, fiscal_year, metric, accession,
           count(DISTINCT candidate_value) AS distinct_values,
           count(*) FILTER (WHERE candidate_value IS NULL) AS invalid_numeric_count
    FROM eligible
    GROUP BY cik, fiscal_year, metric, accession
), ranked AS (
    SELECT e.*, s.distinct_values, s.invalid_numeric_count,
           row_number() OVER (
               PARTITION BY e.cik, e.fiscal_year, e.metric, e.accession
               ORDER BY e.priority, e.taxonomy, e.tag, e.fact_id
           ) AS within_filing_rank
    FROM eligible e
    JOIN filing_stats s USING (cik, fiscal_year, metric, accession)
)
SELECT *,
       filing_role = 'original_10k' AND distinct_values = 1
           AND invalid_numeric_count = 0 AND within_filing_rank = 1 AS is_selected
FROM ranked;

CREATE TABLE standardized_financial_metrics AS
WITH summaries AS (
    SELECT cik, fiscal_year, metric,
           max(candidate_value) FILTER (WHERE is_selected) AS metric_value,
           max(fact_id) FILTER (WHERE is_selected) AS selected_fact_id,
           count(*) FILTER (WHERE filing_role = 'original_10k') AS original_candidate_rows,
           count(DISTINCT accession) FILTER (WHERE filing_role <> 'original_10k') AS other_candidate_filings,
           bool_or(distinct_values > 1) FILTER (WHERE filing_role = 'original_10k') AS original_conflict,
           bool_or(invalid_numeric_count > 0) FILTER (WHERE filing_role = 'original_10k') AS original_numeric_error
    FROM metric_to_source_lineage
    GROUP BY cik, fiscal_year, metric
), version_changes AS (
    SELECT l.cik, l.fiscal_year, l.metric,
           count(DISTINCT l.accession) FILTER (
               WHERE l.distinct_values = 1 AND l.invalid_numeric_count = 0
                 AND l.candidate_value <> s.metric_value
           ) AS changed_comparative_filings,
           count(DISTINCT l.accession) FILTER (
               WHERE l.distinct_values > 1 OR l.invalid_numeric_count > 0
           ) AS ambiguous_comparative_filings
    FROM metric_to_source_lineage l
    JOIN summaries s USING (cik, fiscal_year, metric)
    WHERE l.filing_role <> 'original_10k'
    GROUP BY l.cik, l.fiscal_year, l.metric
)
SELECT p.cik, p.fiscal_year, d.metric, d.statement, d.period_type, d.unit,
       s.metric_value, s.selected_fact_id,
       CASE WHEN s.selected_fact_id IS NOT NULL THEN 'available'
            WHEN s.original_numeric_error THEN 'invalid_numeric_value'
            WHEN s.original_conflict THEN 'conflicting_original_facts'
            WHEN s.other_candidate_filings > 0 THEN 'only_later_candidates'
            ELSE 'no_eligible_mapped_fact'
       END AS status,
       coalesce(s.original_candidate_rows, 0) AS original_candidate_rows,
       coalesce(s.other_candidate_filings, 0) AS other_candidate_filings,
       coalesce(v.changed_comparative_filings, 0) AS changed_comparative_filings,
       coalesce(v.ambiguous_comparative_filings, 0) AS ambiguous_comparative_filings
FROM financial_reporting_periods p
CROSS JOIN metric_definitions d
LEFT JOIN summaries s ON s.cik = p.cik AND s.fiscal_year = p.fiscal_year AND s.metric = d.metric
LEFT JOIN version_changes v ON v.cik = p.cik AND v.fiscal_year = p.fiscal_year AND v.metric = d.metric;

ALTER TABLE financial_reporting_periods ADD PRIMARY KEY (cik, fiscal_year);
ALTER TABLE standardized_financial_metrics ADD PRIMARY KEY (cik, fiscal_year, metric);
ALTER TABLE metric_to_source_lineage ADD PRIMARY KEY (cik, fiscal_year, metric, fact_id);

CREATE VIEW taxonomy_inventory AS
SELECT cik, taxonomy, is_custom_taxonomy, count(DISTINCT tag) AS concepts, count(*) AS observations
FROM raw_xbrl_facts
GROUP BY cik, taxonomy, is_custom_taxonomy;
