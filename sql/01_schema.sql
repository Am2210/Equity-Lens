CREATE TABLE companies (
    cik VARCHAR PRIMARY KEY,
    ticker VARCHAR UNIQUE NOT NULL,
    sec_name VARCHAR NOT NULL,
    fiscal_year_end_mmdd VARCHAR NOT NULL
);

CREATE TABLE filing_metadata (
    cik VARCHAR REFERENCES companies(cik),
    accession VARCHAR,
    form VARCHAR NOT NULL,
    filed DATE NOT NULL,
    report_end DATE,
    accepted_timestamp_raw VARCHAR,
    primary_document VARCHAR,
    is_xbrl BOOLEAN,
    is_inline_xbrl BOOLEAN,
    PRIMARY KEY (cik, accession)
);

CREATE TABLE snapshot (
    as_of_date DATE NOT NULL,
    first_fiscal_year INTEGER NOT NULL,
    last_fiscal_year INTEGER NOT NULL,
    selection_policy VARCHAR NOT NULL
);

CREATE TABLE source_manifest (
    path VARCHAR PRIMARY KEY,
    url VARCHAR NOT NULL,
    sha256 VARCHAR NOT NULL,
    bytes BIGINT NOT NULL
);

CREATE TABLE raw_xbrl_facts (
    fact_id BIGINT PRIMARY KEY,
    cik VARCHAR NOT NULL REFERENCES companies(cik),
    taxonomy VARCHAR NOT NULL,
    tag VARCHAR NOT NULL,
    unit VARCHAR NOT NULL,
    observation_index INTEGER NOT NULL,
    source_value VARCHAR NOT NULL,
    start_date DATE,
    end_date DATE NOT NULL,
    source_fy INTEGER,
    source_fp VARCHAR,
    form VARCHAR NOT NULL,
    filed DATE NOT NULL,
    accession VARCHAR NOT NULL,
    frame VARCHAR,
    is_custom_taxonomy BOOLEAN NOT NULL,
    concept_label VARCHAR,
    UNIQUE (cik, taxonomy, tag, unit, observation_index)
);

CREATE TABLE metric_definitions (
    metric VARCHAR PRIMARY KEY,
    statement VARCHAR NOT NULL,
    period_type VARCHAR NOT NULL CHECK (period_type IN ('duration', 'instant')),
    unit VARCHAR NOT NULL
);

CREATE TABLE metric_mappings (
    metric VARCHAR REFERENCES metric_definitions(metric),
    ticker_scope VARCHAR,
    taxonomy VARCHAR,
    tag VARCHAR,
    priority INTEGER NOT NULL,
    PRIMARY KEY (metric, ticker_scope, taxonomy, tag)
);
