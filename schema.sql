CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    user_type TEXT NOT NULL DEFAULT 'normal_user'
        CHECK (user_type IN ('normal_user', 'admin_user')),
    crm_access BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE users ADD COLUMN IF NOT EXISTS crm_access BOOLEAN NOT NULL DEFAULT FALSE;

CREATE UNIQUE INDEX IF NOT EXISTS one_admin_only
    ON users ((user_type))
    WHERE user_type = 'admin_user';

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL DEFAULT 'New chat',
    kind TEXT NOT NULL DEFAULT 'chat',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE conversations ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'chat';

CREATE TABLE IF NOT EXISTS messages (
    id SERIAL PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS messages_conversation_idx ON messages (conversation_id, created_at);

CREATE TABLE IF NOT EXISTS voice_sessions (
    id SERIAL PRIMARY KEY,
    session_id TEXT UNIQUE NOT NULL,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS voice_sessions_user_seen_idx
    ON voice_sessions (user_id, last_seen_at DESC);

CREATE TABLE IF NOT EXISTS user_memories (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS user_memories_unique_content
    ON user_memories (user_id, content_hash);

CREATE INDEX IF NOT EXISTS user_memories_user_updated_idx
    ON user_memories (user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    uploaded_by INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    content_type TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS document_chunks (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding VECTOR(768) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS document_chunks_embedding_idx
    ON document_chunks USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS persona (
    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    system_prompt TEXT NOT NULL,
    web_system_prompt TEXT,
    voice_system_prompt TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS personas (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    web_system_prompt TEXT NOT NULL,
    voice_system_prompt TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS module_settings (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    module TEXT NOT NULL CHECK (module IN ('chatgpt', 'home', 'work', 'crm')),
    settings JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, module)
);
ALTER TABLE module_settings DROP CONSTRAINT IF EXISTS module_settings_module_check;
ALTER TABLE module_settings ADD CONSTRAINT module_settings_module_check CHECK (module IN ('common', 'chatgpt', 'home', 'work', 'crm'));

CREATE TABLE IF NOT EXISTS persona_memories (
    id SERIAL PRIMARY KEY,
    persona_id INTEGER NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL DEFAULT 'note',
    filename TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS persona_memories_persona_created_idx
    ON persona_memories (persona_id, created_at DESC);

-- Family home assistant module (ben_homeassistant)

CREATE TABLE IF NOT EXISTS home_reminders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    due_at TIMESTAMPTZ,
    done BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS home_reminders_user_idx
    ON home_reminders (user_id, done, due_at);

CREATE TABLE IF NOT EXISTS home_notes (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS home_notes_user_idx
    ON home_notes (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS home_shopping_items (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    quantity TEXT NOT NULL DEFAULT '',
    done BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS home_shopping_items_user_idx
    ON home_shopping_items (user_id, done, created_at);

CREATE TABLE IF NOT EXISTS home_calendar_events (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    location TEXT NOT NULL DEFAULT '',
    start_at TIMESTAMPTZ NOT NULL,
    end_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS home_calendar_events_user_time_idx
    ON home_calendar_events (user_id, start_at, end_at);

-- Customer requirement management module (CRM), admin-only.
-- Shared/global data on purpose: every admin sees and edits the same
-- customer/product catalog (and everything scoped under it). user_id is kept
-- only as "created by" metadata, never as an access-control filter.

CREATE TABLE IF NOT EXISTS crm_customers (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE crm_customers ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE CASCADE;
UPDATE crm_customers SET user_id = (SELECT id FROM users WHERE user_type = 'admin_user' LIMIT 1) WHERE user_id IS NULL;
DROP INDEX IF EXISTS crm_customers_user_idx;
CREATE INDEX IF NOT EXISTS crm_customers_name_idx ON crm_customers (name);

CREATE TABLE IF NOT EXISTS crm_products (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    name TEXT UNIQUE NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE crm_products ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE CASCADE;
UPDATE crm_products SET user_id = (SELECT id FROM users WHERE user_type = 'admin_user' LIMIT 1) WHERE user_id IS NULL;
DROP INDEX IF EXISTS crm_products_user_name_key;
ALTER TABLE crm_products DROP CONSTRAINT IF EXISTS crm_products_name_key;
CREATE UNIQUE INDEX IF NOT EXISTS crm_products_name_key ON crm_products (name);

CREATE TABLE IF NOT EXISTS crm_requirements (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES crm_customers(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES crm_products(id) ON DELETE CASCADE,
    current_state TEXT NOT NULL DEFAULT '',
    requirement TEXT NOT NULL DEFAULT '',
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS crm_requirements_scope_idx
    ON crm_requirements (customer_id, product_id, created_at DESC);

CREATE TABLE IF NOT EXISTS crm_documents (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES crm_customers(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES crm_products(id) ON DELETE CASCADE,
    doc_type TEXT NOT NULL DEFAULT 'memo' CHECK (doc_type IN ('memo', 'proposal_file', 'other')),
    title TEXT NOT NULL,
    filename TEXT NOT NULL,
    content_type TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    uploaded_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS crm_documents_scope_idx
    ON crm_documents (customer_id, product_id, title, is_current);

CREATE TABLE IF NOT EXISTS crm_document_chunks (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES crm_documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding VECTOR(768) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS crm_document_chunks_embedding_idx
    ON crm_document_chunks USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS crm_proposals (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES crm_customers(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES crm_products(id) ON DELETE CASCADE,
    title TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'finalized', 'superseded')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    version INTEGER NOT NULL DEFAULT 1,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finalized_at TIMESTAMPTZ
);

ALTER TABLE crm_proposals ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;

CREATE INDEX IF NOT EXISTS crm_proposals_scope_idx
    ON crm_proposals (customer_id, product_id, status, created_at DESC);

CREATE TABLE IF NOT EXISTS crm_proposal_attachments (
    id SERIAL PRIMARY KEY,
    proposal_id INTEGER NOT NULL REFERENCES crm_proposals(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    content_type TEXT NOT NULL,
    uploaded_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS crm_proposal_attachments_proposal_idx
    ON crm_proposal_attachments (proposal_id, created_at DESC);

CREATE TABLE IF NOT EXISTS crm_proposal_attachment_chunks (
    id SERIAL PRIMARY KEY,
    attachment_id INTEGER NOT NULL REFERENCES crm_proposal_attachments(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding VECTOR(768) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS crm_proposal_attachment_chunks_embedding_idx
    ON crm_proposal_attachment_chunks USING hnsw (embedding vector_cosine_ops);

-- Personal work schedule (location lookup API for future voice/Raspberry Pi use).
-- Meetings/appointments -- fixed start/end time slot. "Tasks" (deadline-only,
-- no time slot) live in the separate work_tasks table below.

CREATE TABLE IF NOT EXISTS work_schedule (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    customer_id INTEGER REFERENCES crm_customers(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    location TEXT NOT NULL DEFAULT '',
    start_at TIMESTAMPTZ NOT NULL,
    end_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE work_schedule ADD COLUMN IF NOT EXISTS done BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE work_schedule ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS work_schedule_user_time_idx
    ON work_schedule (user_id, done, start_at);

CREATE TABLE IF NOT EXISTS work_tasks (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    due_at TIMESTAMPTZ,
    done BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS work_tasks_user_idx
    ON work_tasks (user_id, done, due_at);
