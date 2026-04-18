-- Remove legacy generic result tables now that all routes use specialized storage.
ALTER TABLE review_task
DROP COLUMN IF EXISTS primary_evidence_id;

DROP TABLE IF EXISTS extraction_evidence;
DROP TABLE IF EXISTS extracted_fact;
