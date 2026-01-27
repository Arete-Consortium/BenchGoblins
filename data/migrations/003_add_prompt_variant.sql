-- Add prompt variant column for A/B testing
ALTER TABLE decisions ADD COLUMN prompt_variant VARCHAR(50);
