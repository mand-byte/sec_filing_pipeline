BEGIN;

CREATE TABLE security_master (
    composite_figi VARCHAR(32) PRIMARY KEY,
    ticker VARCHAR(32) NOT NULL,
    cik VARCHAR(20),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    delisted_utc TIMESTAMPTZ,
    last_updated_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE route_watermark (
    id BIGSERIAL PRIMARY KEY,
    cik VARCHAR(20) NOT NULL,
    route VARCHAR(64) NOT NULL,
    last_accepted_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_route_watermark_cik_route
        UNIQUE (cik, route)
);

CREATE TABLE delisted_route_completion (
    id BIGSERIAL PRIMARY KEY,
    composite_figi VARCHAR(32) NOT NULL,
    cik VARCHAR(20) NOT NULL,
    route VARCHAR(64) NOT NULL,
    delisted_utc_snapshot TIMESTAMPTZ,
    last_seen_accepted_at TIMESTAMPTZ,
    is_completed BOOLEAN NOT NULL DEFAULT FALSE,
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_delisted_route_completion_figi
        FOREIGN KEY (composite_figi)
        REFERENCES security_master (composite_figi)
        ON DELETE CASCADE,
    CONSTRAINT uq_delisted_route_completion_figi_cik_route
        UNIQUE (composite_figi, cik, route)
);

CREATE TABLE filing_document (
    accession_no VARCHAR(32) PRIMARY KEY,
    cik VARCHAR(20) NOT NULL,
    ticker VARCHAR(32),
    form_type VARCHAR(32) NOT NULL,
    filed_at TIMESTAMPTZ,
    accepted_at TIMESTAMPTZ,
    period_end TIMESTAMPTZ,
    is_amendment BOOLEAN NOT NULL DEFAULT FALSE,
    amendment_no INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE extracted_fact (
    id BIGSERIAL PRIMARY KEY,
    accession_no VARCHAR(32) NOT NULL,
    route VARCHAR(64) NOT NULL,
    field_name VARCHAR(128) NOT NULL,
    value_numeric DOUBLE PRECISION,
    value_text TEXT,
    value_json JSON,
    value_unit VARCHAR(32),
    confidence DOUBLE PRECISION,
    extracted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_extracted_fact_accession
        FOREIGN KEY (accession_no)
        REFERENCES filing_document (accession_no)
        ON DELETE CASCADE,
    CONSTRAINT uq_extracted_fact_accession_route_field
        UNIQUE (accession_no, route, field_name)
);

CREATE TABLE extraction_evidence (
    id BIGSERIAL PRIMARY KEY,
    accession_no VARCHAR(32) NOT NULL,
    route VARCHAR(64) NOT NULL,
    field_name VARCHAR(128) NOT NULL,
    locator_kind VARCHAR(32),
    source_section VARCHAR(128),
    source_item_no VARCHAR(64),
    source_xpath TEXT,
    xbrl_concept VARCHAR(128),
    source_span TEXT,
    raw_value TEXT,
    normalized_value TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_extraction_evidence_accession
        FOREIGN KEY (accession_no)
        REFERENCES filing_document (accession_no)
        ON DELETE CASCADE
);

CREATE TABLE pipeline_log (
    id BIGSERIAL PRIMARY KEY,
    run_id VARCHAR(64),
    route VARCHAR(64),
    cik VARCHAR(20),
    accession_no VARCHAR(32),
    stage VARCHAR(64),
    level VARCHAR(16) NOT NULL,
    message TEXT NOT NULL,
    error_type VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_pipeline_log_accession
        FOREIGN KEY (accession_no)
        REFERENCES filing_document (accession_no)
        ON DELETE SET NULL
);

CREATE TABLE review_task (
    task_id BIGSERIAL PRIMARY KEY,
    accession_no VARCHAR(32) NOT NULL,
    route VARCHAR(64) NOT NULL,
    field_name VARCHAR(128) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'open',
    priority INTEGER NOT NULL DEFAULT 0,
    assignee VARCHAR(128),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    CONSTRAINT fk_review_task_accession
        FOREIGN KEY (accession_no)
        REFERENCES filing_document (accession_no)
        ON DELETE CASCADE
);

CREATE TABLE review_decision (
    id BIGSERIAL PRIMARY KEY,
    task_id BIGINT NOT NULL,
    decision VARCHAR(32) NOT NULL,
    corrected_value_json JSON,
    comment TEXT,
    reviewer VARCHAR(128),
    decided_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_review_decision_task
        FOREIGN KEY (task_id)
        REFERENCES review_task (task_id)
        ON DELETE CASCADE
);

COMMIT;
