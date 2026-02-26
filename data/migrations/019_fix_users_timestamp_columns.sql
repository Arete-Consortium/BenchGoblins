-- Fix TIMESTAMP columns to TIMESTAMPTZ for timezone-aware comparisons
-- The original migration 006 used TIMESTAMP (naive) but the ORM and Python code
-- use timezone-aware datetimes, causing comparison failures.
ALTER TABLE users ALTER COLUMN queries_reset_at TYPE TIMESTAMPTZ USING queries_reset_at AT TIME ZONE 'UTC';
ALTER TABLE users ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at AT TIME ZONE 'UTC';
ALTER TABLE users ALTER COLUMN updated_at TYPE TIMESTAMPTZ USING updated_at AT TIME ZONE 'UTC';
