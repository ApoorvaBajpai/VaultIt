CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    email VARCHAR(160) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL CHECK (role IN ('officer','prosecutor','admin')),
    department VARCHAR(120),
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE cases (
    id SERIAL PRIMARY KEY,
    case_number VARCHAR(50) UNIQUE NOT NULL,
    title VARCHAR(255) NOT NULL,
    status VARCHAR(30) DEFAULT 'open',
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    case_id INTEGER REFERENCES cases(id) ON DELETE CASCADE,
    uploaded_by INTEGER REFERENCES users(id),
    doc_type VARCHAR(50),
    title VARCHAR(255),
    file_path TEXT NOT NULL,
    raw_text TEXT,
    redacted_text TEXT,
    sha256_hash CHAR(64),
    merkle_root CHAR(64),
    blockchain_tx_hash VARCHAR(80),
    embedding vector(384),
    version INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE audit_logs (
    id SERIAL PRIMARY KEY,
    document_id INTEGER REFERENCES documents(id),
    user_id INTEGER REFERENCES users(id),
    action VARCHAR(30) NOT NULL,
    "timestamp" TIMESTAMP DEFAULT now()
);

CREATE TABLE entities (
    id SERIAL PRIMARY KEY,
    case_id INTEGER REFERENCES cases(id) ON DELETE CASCADE,
    name VARCHAR(200) NOT NULL,
    normalized_name VARCHAR(200) NOT NULL,
    role VARCHAR(30),
    first_seen_document_id INTEGER REFERENCES documents(id)
);

CREATE TABLE document_entities (
    document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    entity_id INTEGER REFERENCES entities(id) ON DELETE CASCADE,
    PRIMARY KEY (document_id, entity_id)
);

CREATE TABLE contradiction_flags (
    id SERIAL PRIMARY KEY,
    case_id INTEGER REFERENCES cases(id),
    document_ids INTEGER[],
    summary TEXT,
    status VARCHAR(20) DEFAULT 'unreviewed',
    created_at TIMESTAMP DEFAULT now()
);
