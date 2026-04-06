BEGIN;

CREATE TABLE security_master (
    ticker VARCHAR(32) PRIMARY KEY,
    cik VARCHAR(20),
    company_name VARCHAR(255),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE route_watermark (
    route VARCHAR(64) PRIMARY KEY,
    last_accession_no VARCHAR(32),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE delisted_route_completion (
    ticker VARCHAR(32) NOT NULL,
    route VARCHAR(64) NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ticker, route),
    CONSTRAINT fk_delisted_route_completion_ticker
        FOREIGN KEY (ticker)
        REFERENCES security_master (ticker)
        ON DELETE CASCADE
);

CREATE TABLE filing_document (
    accession_no VARCHAR(32) PRIMARY KEY,
    ticker VARCHAR(32),
    route VARCHAR(64) NOT NULL,
    filing_date TIMESTAMPTZ,
    form_type VARCHAR(32),
    source_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_filing_document_ticker
        FOREIGN KEY (ticker)
        REFERENCES security_master (ticker)
        ON DELETE SET NULL
);

CREATE TABLE extracted_fact (
    id BIGSERIAL PRIMARY KEY,
    accession_no VARCHAR(32) NOT NULL,
    route VARCHAR(64) NOT NULL,
    field_name VARCHAR(128) NOT NULL,
    field_value TEXT,
    numeric_value NUMERIC(24, 6),
    as_of_date TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_extracted_fact_accession
        FOREIGN KEY (accession_no)
        REFERENCES filing_document (accession_no)
        ON DELETE CASCADE,
    CONSTRAINT uq_extracted_fact_accession_route_field
        UNIQUE (accession_no, route, field_name)
);

CREATE TABLE extraction_evidence (
    id BIGSERIAL PRIMARY KEY,
    extracted_fact_id BIGINT NOT NULL,
    evidence_type VARCHAR(64) NOT NULL,
    locator TEXT,
    snippet TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_extraction_evidence_fact
        FOREIGN KEY (extracted_fact_id)
        REFERENCES extracted_fact (id)
        ON DELETE CASCADE
);

CREATE TABLE pipeline_log (
    id BIGSERIAL PRIMARY KEY,
    level VARCHAR(16) NOT NULL,
    route VARCHAR(64),
    accession_no VARCHAR(32),
    message TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_pipeline_log_accession
        FOREIGN KEY (accession_no)
        REFERENCES filing_document (accession_no)
        ON DELETE SET NULL
);

CREATE TABLE review_task (
    id BIGSERIAL PRIMARY KEY,
    extracted_fact_id BIGINT NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'open',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_review_task_fact
        FOREIGN KEY (extracted_fact_id)
        REFERENCES extracted_fact (id)
        ON DELETE CASCADE
);

CREATE TABLE review_decision (
    id BIGSERIAL PRIMARY KEY,
    review_task_id BIGINT NOT NULL,
    decision VARCHAR(32) NOT NULL,
    comment TEXT,
    decided_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_review_decision_task
        FOREIGN KEY (review_task_id)
        REFERENCES review_task (id)
        ON DELETE CASCADE
);

COMMIT;
