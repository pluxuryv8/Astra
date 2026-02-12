ALTER TABLE plan_steps ADD COLUMN kind TEXT;
ALTER TABLE plan_steps ADD COLUMN success_criteria TEXT;
ALTER TABLE plan_steps ADD COLUMN danger_flags TEXT;
ALTER TABLE plan_steps ADD COLUMN requires_approval INTEGER DEFAULT 0;
ALTER TABLE plan_steps ADD COLUMN artifacts_expected TEXT;
