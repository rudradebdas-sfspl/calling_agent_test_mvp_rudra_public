-- ============================================================
-- Troubleshooting KB — structured entries + policy rules
-- Adds two tables that power the KB-Fetch vs LLM-Answered router.
-- Safe to re-run (IF NOT EXISTS everywhere). Requires pgvector (already installed).
-- ============================================================

CREATE EXTENSION IF NOT EXISTS vector;

-- ---- 1. Structured troubleshooting entries (one row per KB-TS-xxx) ----
CREATE TABLE IF NOT EXISTS kb_entries (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id           uuid NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    entry_id           text NOT NULL,                 -- e.g. KB-TS-007
    category           text,
    sub_category       text,
    title              text,
    description        text,
    root_causes        text,
    keywords           text,
    voice_mode         text,
    checklist_steps    text,                          -- the actual fix (source of truth)
    total_steps        integer,
    escalation_action  text,
    source_ref         text,
    answer_mode        text,                          -- 'LLM-Answered' | 'KB-Fetch Only'
    probing_questions  text,                          -- LLM deep-dive questions
    diagnostic_commands text,
    max_steps          integer,                       -- guardrail: steps before ticket
    policy_boundary    text,                          -- MUST NOT do
    sensitive_actions  text,
    can_resolve        text,                          -- Yes | Partial | No
    allowed_depth      text,
    data_restrictions  text,
    compliance_notes   text,
    transfer_trigger   text,
    transfer_after_step text,
    transfer_priority  text,                          -- P1 | P2 | P3 | P4
    transfer_to        text,
    info_to_collect    text,
    transfer_script    text,
    urgency            text,
    policy_rule_ref    text,                          -- POL-xxx (overrides answer_mode) or NULL
    content            text NOT NULL,                 -- combined text used for embedding/retrieval
    embedding          halfvec(3072),
    created_at         timestamp without time zone NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_kb_entries_agent_id ON kb_entries (agent_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_kb_entries_agent_entry ON kb_entries (agent_id, entry_id);
CREATE INDEX IF NOT EXISTS ix_kb_entries_embedding_hnsw
    ON kb_entries USING hnsw (embedding halfvec_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- ---- 2. Policy rules (one row per POL-xxx) ----
CREATE TABLE IF NOT EXISTS policy_rules (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id           uuid NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    rule_id            text NOT NULL,                 -- e.g. POL-001
    policy_area        text,
    rule_statement     text,
    rationale          text,
    agent_says         text,                          -- VERBATIM line the agent must speak
    answer_mode        text,
    applies_to         text,                          -- issue ids this rule governs
    transfer_priority  text,
    owner              text,
    content            text NOT NULL,                 -- combined text for embedding/retrieval
    embedding          halfvec(3072),
    created_at         timestamp without time zone NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_policy_rules_agent_id ON policy_rules (agent_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_policy_rules_agent_rule ON policy_rules (agent_id, rule_id);
CREATE INDEX IF NOT EXISTS ix_policy_rules_embedding_hnsw
    ON policy_rules USING hnsw (embedding halfvec_cosine_ops)
    WITH (m = 16, ef_construction = 64);