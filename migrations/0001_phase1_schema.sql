BEGIN;

CREATE TABLE security_master (
    composite_figi VARCHAR(12) PRIMARY KEY,
    ticker VARCHAR(32) NOT NULL,
    cik VARCHAR(10) NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    delisted_utc TIMESTAMPTZ,
    last_updated_utc TIMESTAMPTZ
);

CREATE INDEX ix_security_master_cik ON security_master (cik);

CREATE TABLE route_watermark (
    id SERIAL PRIMARY KEY,
    cik VARCHAR(10) NOT NULL,
    route VARCHAR(16) NOT NULL,
    last_accepted_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_route_watermark_cik_route
        UNIQUE (cik, route)
);

CREATE TABLE delisted_route_completion (
    id SERIAL PRIMARY KEY,
    composite_figi VARCHAR(12) NOT NULL,
    cik VARCHAR(10) NOT NULL,
    route VARCHAR(16) NOT NULL,
    delisted_utc_snapshot TIMESTAMPTZ,
    last_seen_accepted_at TIMESTAMPTZ,
    is_completed BOOLEAN NOT NULL DEFAULT FALSE,
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_delisted_completion_key
        UNIQUE (composite_figi, cik, route)
);

CREATE TABLE filing_document (
    accession_no VARCHAR(32) PRIMARY KEY,
    cik VARCHAR(10) NOT NULL,
    ticker VARCHAR(32),
    form_type VARCHAR(32) NOT NULL,
    filed_at TIMESTAMPTZ,
    accepted_at TIMESTAMPTZ NOT NULL,
    period_end TIMESTAMPTZ,
    is_amendment BOOLEAN NOT NULL DEFAULT FALSE,
    amendment_no INTEGER,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX ix_filing_document_cik ON filing_document (cik);
CREATE INDEX ix_filing_document_accepted_at ON filing_document (accepted_at);

CREATE TABLE extracted_fact (
    id SERIAL PRIMARY KEY,
    accession_no VARCHAR(32) NOT NULL,
    route VARCHAR(16) NOT NULL,
    field_name VARCHAR(128) NOT NULL,
    value_numeric DOUBLE PRECISION,
    value_text TEXT,
    value_json TEXT,
    value_unit VARCHAR(32),
    confidence DOUBLE PRECISION,
    extracted_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT fk_extracted_fact_accession
        FOREIGN KEY (accession_no)
        REFERENCES filing_document (accession_no),
    CONSTRAINT uq_fact_accession_route_field
        UNIQUE (accession_no, route, field_name)
);

CREATE INDEX ix_extracted_fact_accession_no ON extracted_fact (accession_no);

CREATE TABLE extraction_evidence (
    id SERIAL PRIMARY KEY,
    accession_no VARCHAR(32) NOT NULL,
    route VARCHAR(16) NOT NULL,
    field_name VARCHAR(128) NOT NULL,
    locator_kind VARCHAR(64) NOT NULL,
    source_section VARCHAR(128),
    source_item_no VARCHAR(32),
    source_xpath TEXT,
    xbrl_concept VARCHAR(128),
    source_span TEXT NOT NULL,
    raw_value TEXT,
    normalized_value TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT fk_extraction_evidence_accession
        FOREIGN KEY (accession_no)
        REFERENCES filing_document (accession_no)
);

CREATE INDEX ix_extraction_evidence_accession_no ON extraction_evidence (accession_no);

CREATE TABLE pipeline_log (
    id SERIAL PRIMARY KEY,
    run_id VARCHAR(64) NOT NULL,
    route VARCHAR(16) NOT NULL,
    cik VARCHAR(10),
    accession_no VARCHAR(32),
    stage VARCHAR(16) NOT NULL,
    level VARCHAR(16) NOT NULL,
    message TEXT NOT NULL,
    error_type VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX ix_pipeline_log_run_id ON pipeline_log (run_id);

CREATE TABLE review_task (
    task_id SERIAL PRIMARY KEY,
    accession_no VARCHAR(32) NOT NULL,
    route VARCHAR(16) NOT NULL,
    field_name VARCHAR(128) NOT NULL,
    status VARCHAR(16) NOT NULL,
    priority VARCHAR(16) NOT NULL,
    assignee VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL,
    resolved_at TIMESTAMPTZ,
    CONSTRAINT fk_review_task_accession
        FOREIGN KEY (accession_no)
        REFERENCES filing_document (accession_no)
);

CREATE INDEX ix_review_task_accession_no ON review_task (accession_no);

CREATE TABLE review_decision (
    id SERIAL PRIMARY KEY,
    task_id INTEGER NOT NULL,
    decision VARCHAR(16) NOT NULL,
    corrected_value_json TEXT,
    comment TEXT,
    reviewer VARCHAR(64) NOT NULL,
    decided_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT fk_review_decision_task
        FOREIGN KEY (task_id)
        REFERENCES review_task (task_id)
);

CREATE INDEX ix_review_decision_task_id ON review_decision (task_id);

COMMIT;
