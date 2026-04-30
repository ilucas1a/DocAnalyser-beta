"""
db_manager.py — SQLite database layer for DocAnalyser.

All SQL lives here. No UI code, no Tkinter imports.
Functions accept and return plain Python dicts and lists.
All public functions are prefixed with db_ so callers know they're
talking to the database layer.

Tables (Phase 1):
    documents, document_entries, conversations, messages,
    processed_outputs, prompts, prompt_versions,
    folders, folder_items, cost_log, embeddings

Tables (v1.7-alpha additions):
    corrections_lists, corrections, backups

Created: 28 February 2026
v1.7-alpha additions: 28 April 2026
v1.7-alpha Day 7 (backups table): 30 April 2026
"""

from __future__ import annotations

import os
import json
import sqlite3
import datetime
import hashlib
import struct
import logging
from typing import Dict, List, Optional, Tuple

from config import DATA_DIR

# ---------------------------------------------------------------------------
# Database path & connection
# ---------------------------------------------------------------------------

DB_PATH = os.path.join(DATA_DIR, "docanalyser.db")

_connection: Optional[sqlite3.Connection] = None


def get_connection() -> sqlite3.Connection:
    """Return a module-level connection (created once, reused)."""
    global _connection
    if _connection is None:
        _connection = sqlite3.connect(DB_PATH, check_same_thread=False)
        _connection.row_factory = sqlite3.Row          # dict-like rows
        _connection.execute("PRAGMA journal_mode=WAL")  # safe for concurrent reads
        _connection.execute("PRAGMA foreign_keys=ON")   # enforce FK constraints
    return _connection


def close_connection():
    """Close the database connection (call on app shutdown)."""
    global _connection
    if _connection is not None:
        _connection.close()
        _connection = None


# ---------------------------------------------------------------------------
# Schema creation
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
-- 1. documents
CREATE TABLE IF NOT EXISTS documents (
    id              TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    doc_type        TEXT NOT NULL,
    document_class  TEXT NOT NULL DEFAULT 'source',
    source          TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT,
    entry_count     INTEGER DEFAULT 0,
    metadata        TEXT,
    parent_doc_id   TEXT,
    is_deleted      INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_documents_type ON documents(doc_type);
CREATE INDEX IF NOT EXISTS idx_documents_class ON documents(document_class);
CREATE INDEX IF NOT EXISTS idx_documents_parent ON documents(parent_doc_id);
CREATE INDEX IF NOT EXISTS idx_documents_created ON documents(created_at);

-- 2. document_entries
CREATE TABLE IF NOT EXISTS document_entries (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id          TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    position        INTEGER NOT NULL,
    content         TEXT NOT NULL,
    entry_type      TEXT DEFAULT 'text',
    metadata        TEXT,
    UNIQUE(doc_id, position)
);
CREATE INDEX IF NOT EXISTS idx_entries_doc ON document_entries(doc_id);

-- 3. conversations
CREATE TABLE IF NOT EXISTS conversations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id          TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    created_at      TEXT NOT NULL,
    updated_at      TEXT,
    message_count   INTEGER DEFAULT 0,
    metadata        TEXT
);
CREATE INDEX IF NOT EXISTS idx_conversations_doc ON conversations(doc_id);

-- 4. messages
CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    position        INTEGER NOT NULL,
    role            TEXT NOT NULL,
    content         TEXT NOT NULL,
    timestamp       TEXT,
    provider        TEXT,
    model           TEXT,
    metadata        TEXT,
    UNIQUE(conversation_id, position)
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);

-- 5. processed_outputs
CREATE TABLE IF NOT EXISTS processed_outputs (
    id              TEXT PRIMARY KEY,
    doc_id          TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    created_at      TEXT NOT NULL,
    prompt_name     TEXT,
    prompt_text     TEXT,
    provider        TEXT,
    model           TEXT,
    output_text     TEXT NOT NULL,
    preview         TEXT,
    notes           TEXT
);
CREATE INDEX IF NOT EXISTS idx_outputs_doc ON processed_outputs(doc_id);

-- 6. prompts
CREATE TABLE IF NOT EXISTS prompts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    is_system       INTEGER DEFAULT 0,
    is_favorite     INTEGER DEFAULT 0,
    last_used       TEXT,
    max_versions    INTEGER DEFAULT 10,
    created_at      TEXT NOT NULL,
    updated_at      TEXT
);
CREATE INDEX IF NOT EXISTS idx_prompts_name ON prompts(name);
CREATE INDEX IF NOT EXISTS idx_prompts_favorite ON prompts(is_favorite);

-- 7. prompt_versions
CREATE TABLE IF NOT EXISTS prompt_versions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt_id       INTEGER NOT NULL REFERENCES prompts(id) ON DELETE CASCADE,
    version_num     INTEGER NOT NULL,
    text            TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    note            TEXT,
    UNIQUE(prompt_id, version_num)
);
CREATE INDEX IF NOT EXISTS idx_prompt_versions_prompt ON prompt_versions(prompt_id);

-- 8. folders
CREATE TABLE IF NOT EXISTS folders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    parent_id       INTEGER REFERENCES folders(id) ON DELETE CASCADE,
    library_type    TEXT NOT NULL,
    workspace_id    INTEGER,
    position        INTEGER DEFAULT 0,
    is_expanded     INTEGER DEFAULT 1,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_folders_parent ON folders(parent_id);
CREATE INDEX IF NOT EXISTS idx_folders_type ON folders(library_type);

-- 9. folder_items
CREATE TABLE IF NOT EXISTS folder_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    folder_id       INTEGER NOT NULL REFERENCES folders(id) ON DELETE CASCADE,
    item_type       TEXT NOT NULL,
    item_id         TEXT NOT NULL,
    position        INTEGER DEFAULT 0,
    UNIQUE(folder_id, item_type, item_id)
);
CREATE INDEX IF NOT EXISTS idx_folder_items_folder ON folder_items(folder_id);

-- 10. cost_log
CREATE TABLE IF NOT EXISTS cost_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL,
    provider        TEXT NOT NULL,
    model           TEXT NOT NULL,
    cost            REAL NOT NULL,
    document_title  TEXT,
    prompt_name     TEXT,
    doc_id          TEXT,
    workspace_id    INTEGER
);
CREATE INDEX IF NOT EXISTS idx_cost_log_timestamp ON cost_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_cost_log_provider ON cost_log(provider);

-- 11. embeddings
CREATE TABLE IF NOT EXISTS embeddings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id          TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_idx       INTEGER NOT NULL,
    chunk_text      TEXT NOT NULL,
    embedding       BLOB NOT NULL,
    model           TEXT,
    cost            REAL DEFAULT 0,
    created_at      TEXT NOT NULL,
    UNIQUE(doc_id, chunk_idx)
);
CREATE INDEX IF NOT EXISTS idx_embeddings_doc ON embeddings(doc_id);

-- 12. corrections_lists  (v1.7-alpha)
CREATE TABLE IF NOT EXISTS corrections_lists (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    description     TEXT,
    workspace_id    INTEGER,
    created_at      TEXT NOT NULL,
    updated_at      TEXT
);
CREATE INDEX IF NOT EXISTS idx_corrections_lists_name ON corrections_lists(name);

-- 13. corrections  (v1.7-alpha)
CREATE TABLE IF NOT EXISTS corrections (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    list_id         INTEGER NOT NULL REFERENCES corrections_lists(id) ON DELETE CASCADE,
    original_text   TEXT NOT NULL,
    corrected_text  TEXT NOT NULL,
    case_sensitive  INTEGER DEFAULT 0,
    word_boundary   INTEGER DEFAULT 1,
    notes           TEXT,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_corrections_list ON corrections(list_id);

-- 14. backups  (v1.7-alpha)
CREATE TABLE IF NOT EXISTS backups (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id     TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    trigger_type    TEXT NOT NULL,
    label           TEXT,
    content_blob    TEXT NOT NULL,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_backups_document ON backups(document_id, created_at DESC);

-- 15. migration metadata
CREATE TABLE IF NOT EXISTS db_meta (
    key             TEXT PRIMARY KEY,
    value           TEXT
);
"""


def init_database():
    """Create the database file and all tables if they don't already exist."""
    conn = get_connection()
    conn.executescript(_SCHEMA_SQL)
    conn.commit()
    logging.info(f"Database initialised at {DB_PATH}")

    # v1.7-alpha: seed the bundled "General" Corrections List on first run.
    # Idempotent — uses a db_meta flag so it never runs twice.
    _seed_corrections_general_if_needed()


def _seed_corrections_general_if_needed():
    """
    One-time seed of the bundled "General" Corrections List from
    default_corrections.json (sibling of this module).

    Idempotent: writes a `corrections_general_seeded` flag to db_meta
    on success; failure leaves the flag unset so the next launch retries
    cleanly. Safe to call on every startup.
    """
    conn = get_connection()

    # Check the flag first
    try:
        row = conn.execute(
            "SELECT value FROM db_meta WHERE key = 'corrections_general_seeded'"
        ).fetchone()
        if row is not None and row["value"] == "true":
            return  # Already seeded
    except sqlite3.OperationalError:
        # db_meta missing (shouldn't happen here since init ran), bail safely
        return

    # Locate default_corrections.json next to this module
    json_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "default_corrections.json"
    )
    if not os.path.exists(json_path):
        logging.warning(
            "default_corrections.json not found at %s; "
            "General Corrections List not seeded. Will retry on next launch.",
            json_path
        )
        return

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        logging.warning(
            "Could not read default_corrections.json: %s; "
            "General Corrections List not seeded.", exc
        )
        return

    entries = data.get("entries", [])
    description = data.get(
        "description",
        "Bundled starter list of common transcription errors. Edit freely "
        "or duplicate to create project-specific lists."
    )

    try:
        # Defensive: if a list named 'General' already exists, leave it alone
        # and just set the flag so we don't overwrite user edits.
        existing = conn.execute(
            "SELECT id FROM corrections_lists WHERE name = 'General'"
        ).fetchone()

        if existing is None:
            now = _now()
            cur = conn.execute(
                """INSERT INTO corrections_lists
                   (name, description, workspace_id, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?)""",
                ("General", description, None, now, now)
            )
            list_id = cur.lastrowid

            for entry in entries:
                conn.execute(
                    """INSERT INTO corrections
                       (list_id, original_text, corrected_text,
                        case_sensitive, word_boundary, notes, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (list_id,
                     entry.get("original", ""),
                     entry.get("corrected", ""),
                     1 if entry.get("case_sensitive", False) else 0,
                     1 if entry.get("word_boundary", True) else 0,
                     entry.get("notes"),
                     now)
                )
            logging.info(
                "Seeded 'General' Corrections List with %d entries.",
                len(entries)
            )
        else:
            logging.info(
                "'General' Corrections List already exists (id=%s); not overwritten.",
                existing["id"]
            )

        # Set the flag so this never runs again
        conn.execute(
            "INSERT OR REPLACE INTO db_meta (key, value) VALUES (?, ?)",
            ("corrections_general_seeded", "true")
        )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        logging.warning(
            "Failed to seed General Corrections List: %s; "
            "will retry on next launch.", exc
        )


def db_is_migrated() -> bool:
    """Return True if JSON→SQLite migration has already completed."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT value FROM db_meta WHERE key = 'migration_complete'"
        ).fetchone()
        return row is not None and row["value"] == "true"
    except sqlite3.OperationalError:
        return False


def db_set_migrated():
    """Record that migration is complete."""
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO db_meta (key, value) VALUES (?, ?)",
        ("migration_complete", "true")
    )
    conn.execute(
        "INSERT OR REPLACE INTO db_meta (key, value) VALUES (?, ?)",
        ("migration_date", _now())
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    """ISO-format timestamp for right now."""
    return datetime.datetime.now().isoformat()


def _row_to_dict(row: sqlite3.Row) -> dict:
    """Convert a sqlite3.Row to a plain dict."""
    return dict(row)


def _json_col(value) -> Optional[str]:
    """Encode a Python object as a JSON string for storage, or None."""
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def _from_json(text: Optional[str]):
    """Decode a JSON column back to Python, or return None / empty dict."""
    if text is None:
        return None
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def _floats_to_blob(floats: list) -> bytes:
    """Pack a list of floats into a compact binary BLOB."""
    return struct.pack(f"{len(floats)}f", *floats)


def _blob_to_floats(blob: bytes) -> list:
    """Unpack a binary BLOB back to a list of floats."""
    count = len(blob) // 4
    return list(struct.unpack(f"{count}f", blob))


# ===================================================================
#  DOCUMENTS
# ===================================================================

def db_add_document(doc_id: str, doc_type: str, source: str, title: str,
                    entry_count: int = 0, metadata: dict = None,
                    document_class: str = "source",
                    parent_doc_id: str = None) -> str:
    """Insert or replace a document row. Returns the doc_id."""
    conn = get_connection()
    now = _now()

    # Extract parent_doc_id from metadata if not provided directly
    if parent_doc_id is None and metadata:
        parent_doc_id = (metadata.get("original_document_id")
                         or metadata.get("parent_document_id"))

    conn.execute("""
        INSERT OR REPLACE INTO documents
            (id, title, doc_type, document_class, source,
             created_at, updated_at, entry_count, metadata,
             parent_doc_id, is_deleted)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
    """, (doc_id, title, doc_type, document_class, source,
          now, now, entry_count, _json_col(metadata),
          parent_doc_id))
    conn.commit()
    return doc_id


def db_get_document(doc_id: str) -> Optional[dict]:
    """Get a single document by ID. Returns None if not found or soft-deleted."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM documents WHERE id = ? AND is_deleted = 0", (doc_id,)
    ).fetchone()
    if row is None:
        return None
    d = _row_to_dict(row)
    d["metadata"] = _from_json(d.get("metadata")) or {}
    return d


def db_get_all_documents(include_deleted: bool = False) -> List[dict]:
    """Return every document as a list of dicts."""
    conn = get_connection()
    if include_deleted:
        rows = conn.execute("SELECT * FROM documents ORDER BY created_at DESC").fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM documents WHERE is_deleted = 0 ORDER BY created_at DESC"
        ).fetchall()
    results = []
    for row in rows:
        d = _row_to_dict(row)
        d["metadata"] = _from_json(d.get("metadata")) or {}
        results.append(d)
    return results


def db_update_document(doc_id: str, **fields) -> bool:
    """
    Update specific fields on a document.
    Allowed fields: title, doc_type, document_class, source,
                    entry_count, metadata, parent_doc_id, is_deleted.
    """
    allowed = {
        "title", "doc_type", "document_class", "source",
        "entry_count", "metadata", "parent_doc_id", "is_deleted"
    }
    to_set = {}
    for k, v in fields.items():
        if k not in allowed:
            continue
        if k == "metadata":
            to_set[k] = _json_col(v)
        else:
            to_set[k] = v

    if not to_set:
        return False

    to_set["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in to_set)
    values = list(to_set.values()) + [doc_id]

    conn = get_connection()
    cur = conn.execute(
        f"UPDATE documents SET {set_clause} WHERE id = ?", values
    )
    conn.commit()
    return cur.rowcount > 0


def db_delete_document(doc_id: str, hard: bool = False) -> bool:
    """
    Delete a document. Soft-delete by default (sets is_deleted=1).
    Hard delete removes the row and cascades to entries, conversations, etc.
    """
    conn = get_connection()
    if hard:
        cur = conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    else:
        cur = conn.execute(
            "UPDATE documents SET is_deleted = 1, updated_at = ? WHERE id = ?",
            (_now(), doc_id)
        )
    conn.commit()
    return cur.rowcount > 0


def db_search_documents(query: str) -> List[dict]:
    """Search documents by title or source (case-insensitive substring)."""
    conn = get_connection()
    pattern = f"%{query}%"
    rows = conn.execute("""
        SELECT * FROM documents
        WHERE is_deleted = 0
          AND (title LIKE ? COLLATE NOCASE
               OR source LIKE ? COLLATE NOCASE
               OR doc_type LIKE ? COLLATE NOCASE)
        ORDER BY created_at DESC
    """, (pattern, pattern, pattern)).fetchall()
    results = []
    for row in rows:
        d = _row_to_dict(row)
        d["metadata"] = _from_json(d.get("metadata")) or {}
        results.append(d)
    return results


def db_get_branches_for_source(source_doc_id: str) -> List[dict]:
    """Get all response/branch documents linked to a source document."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM documents
        WHERE parent_doc_id = ? AND is_deleted = 0
        ORDER BY created_at DESC
    """, (source_doc_id,)).fetchall()
    results = []
    for row in rows:
        d = _row_to_dict(row)
        d["metadata"] = _from_json(d.get("metadata")) or {}
        results.append(d)
    return results


def db_get_document_count(include_deleted: bool = False) -> int:
    """Return the total number of documents."""
    conn = get_connection()
    if include_deleted:
        row = conn.execute("SELECT COUNT(*) as cnt FROM documents").fetchone()
    else:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM documents WHERE is_deleted = 0"
        ).fetchone()
    return row["cnt"]


# ===================================================================
#  DOCUMENT ENTRIES
# ===================================================================

def db_save_entries(doc_id: str, entries: List[dict]) -> bool:
    """
    Replace all entries for a document.
    Each entry dict should have at least 'text'. Optional: 'start', 'speaker',
    'location', 'duration', or any other keys (stored in metadata).
    """
    conn = get_connection()
    # Delete existing entries for this document
    conn.execute("DELETE FROM document_entries WHERE doc_id = ?", (doc_id,))

    for pos, entry in enumerate(entries):
        content = entry.get("text", "")
        entry_type = entry.get("entry_type", "text")

        # Store everything except 'text' and 'entry_type' in metadata
        meta = {k: v for k, v in entry.items()
                if k not in ("text", "entry_type")}

        conn.execute("""
            INSERT INTO document_entries (doc_id, position, content, entry_type, metadata)
            VALUES (?, ?, ?, ?, ?)
        """, (doc_id, pos, content, entry_type, _json_col(meta) if meta else None))

    # Update entry_count on the document
    conn.execute(
        "UPDATE documents SET entry_count = ?, updated_at = ? WHERE id = ?",
        (len(entries), _now(), doc_id)
    )
    conn.commit()
    return True


def db_get_entries(doc_id: str) -> Optional[List[dict]]:
    """
    Load all entries for a document, ordered by position.
    Returns a list of dicts matching the original JSON format:
    [{'text': '...', 'start': 0.0, 'speaker': '...', ...}, ...]
    """
    conn = get_connection()
    rows = conn.execute("""
        SELECT content, entry_type, metadata
        FROM document_entries
        WHERE doc_id = ?
        ORDER BY position
    """, (doc_id,)).fetchall()

    if not rows:
        return None

    entries = []
    for row in rows:
        entry = {"text": row["content"]}
        if row["entry_type"] != "text":
            entry["entry_type"] = row["entry_type"]
        meta = _from_json(row["metadata"])
        if meta:
            entry.update(meta)
        entries.append(entry)
    return entries


# ===================================================================
#  CONVERSATIONS & MESSAGES
# ===================================================================

def db_get_conversation(doc_id: str) -> Optional[dict]:
    """
    Get the conversation (thread) for a document.
    Returns: {'messages': [...], 'metadata': {...}} or None.
    """
    conn = get_connection()
    conv = conn.execute("""
        SELECT * FROM conversations WHERE doc_id = ?
        ORDER BY id DESC LIMIT 1
    """, (doc_id,)).fetchone()

    if conv is None:
        return None

    messages = conn.execute("""
        SELECT role, content, timestamp, provider, model, metadata
        FROM messages
        WHERE conversation_id = ?
        ORDER BY position
    """, (conv["id"],)).fetchall()

    msg_list = []
    for m in messages:
        msg = {"role": m["role"], "content": m["content"]}
        if m["timestamp"]:
            msg["timestamp"] = m["timestamp"]
        if m["provider"]:
            msg["provider"] = m["provider"]
        if m["model"]:
            msg["model"] = m["model"]
        meta = _from_json(m["metadata"])
        if meta:
            msg.update(meta)
        msg_list.append(msg)

    return {
        "messages": msg_list,
        "metadata": _from_json(conv["metadata"]) or {},
        "conversation_id": conv["id"]
    }


def db_save_conversation(doc_id: str, messages: List[dict],
                         metadata: dict = None) -> bool:
    """
    Save a complete conversation thread for a document.
    Replaces any existing conversation.
    """
    conn = get_connection()
    now = _now()

    # Delete existing conversation(s) for this document
    # (cascades to messages via ON DELETE CASCADE)
    conn.execute("DELETE FROM conversations WHERE doc_id = ?", (doc_id,))

    if not messages:
        conn.commit()
        return True

    # Count user messages
    user_msg_count = len([m for m in messages if m.get("role") == "user"])

    # Merge metadata
    if metadata is None:
        metadata = {}
    metadata["last_updated"] = now
    metadata["message_count"] = user_msg_count

    # Create conversation
    cur = conn.execute("""
        INSERT INTO conversations (doc_id, created_at, updated_at, message_count, metadata)
        VALUES (?, ?, ?, ?, ?)
    """, (doc_id, now, now, user_msg_count, _json_col(metadata)))
    conv_id = cur.lastrowid

    # Insert messages
    for pos, msg in enumerate(messages):
        conn.execute("""
            INSERT INTO messages
                (conversation_id, position, role, content, timestamp, provider, model, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            conv_id, pos,
            msg.get("role", "user"),
            msg.get("content", ""),
            msg.get("timestamp"),
            msg.get("provider"),
            msg.get("model"),
            _json_col({k: v for k, v in msg.items()
                       if k not in ("role", "content", "timestamp", "provider", "model")})
            or None
        ))

    conn.commit()
    return True


def db_add_message(doc_id: str, role: str, content: str,
                   provider: str = None, model: str = None) -> Optional[int]:
    """
    Append a single message to the most recent conversation for doc_id.
    Creates the conversation if it doesn't exist.
    Returns the message id.
    """
    conn = get_connection()
    now = _now()

    # Find or create conversation
    conv = conn.execute("""
        SELECT id, message_count FROM conversations WHERE doc_id = ?
        ORDER BY id DESC LIMIT 1
    """, (doc_id,)).fetchone()

    if conv is None:
        cur = conn.execute("""
            INSERT INTO conversations (doc_id, created_at, updated_at, message_count, metadata)
            VALUES (?, ?, ?, 0, NULL)
        """, (doc_id, now, now))
        conv_id = cur.lastrowid
        next_pos = 0
    else:
        conv_id = conv["id"]
        # Get next position
        row = conn.execute(
            "SELECT COALESCE(MAX(position), -1) + 1 as next_pos FROM messages WHERE conversation_id = ?",
            (conv_id,)
        ).fetchone()
        next_pos = row["next_pos"]

    cur = conn.execute("""
        INSERT INTO messages (conversation_id, position, role, content, timestamp, provider, model)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (conv_id, next_pos, role, content, now, provider, model))

    # Update conversation metadata
    if role == "user":
        user_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM messages WHERE conversation_id = ? AND role = 'user'",
            (conv_id,)
        ).fetchone()["cnt"]
        conn.execute(
            "UPDATE conversations SET updated_at = ?, message_count = ? WHERE id = ?",
            (now, user_count, conv_id)
        )
    else:
        conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (now, conv_id)
        )

    conn.commit()
    return cur.lastrowid


def db_clear_conversation(doc_id: str) -> bool:
    """Delete all conversations and messages for a document."""
    conn = get_connection()
    conn.execute("DELETE FROM conversations WHERE doc_id = ?", (doc_id,))
    conn.commit()
    return True


# ===================================================================
#  PROCESSED OUTPUTS
# ===================================================================

def db_add_processed_output(doc_id: str, output_id: str,
                            prompt_name: str, prompt_text: str,
                            provider: str, model: str,
                            output_text: str, notes: str = "") -> str:
    """Add a processed output (AI response) linked to a document. Returns output_id."""
    conn = get_connection()
    preview = output_text[:200] + "..." if len(output_text) > 200 else output_text

    conn.execute("""
        INSERT OR REPLACE INTO processed_outputs
            (id, doc_id, created_at, prompt_name, prompt_text,
             provider, model, output_text, preview, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (output_id, doc_id, _now(), prompt_name, prompt_text,
          provider, model, output_text, preview, notes))
    conn.commit()
    return output_id


def db_get_processed_outputs(doc_id: str) -> List[dict]:
    """Get all processed output metadata for a document (without full text)."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT id, doc_id, created_at, prompt_name, prompt_text,
               provider, model, preview, notes
        FROM processed_outputs
        WHERE doc_id = ?
        ORDER BY created_at DESC
    """, (doc_id,)).fetchall()
    return [_row_to_dict(r) for r in rows]


def db_load_processed_output(output_id: str) -> Optional[str]:
    """Load the full text of a processed output."""
    conn = get_connection()
    row = conn.execute(
        "SELECT output_text FROM processed_outputs WHERE id = ?",
        (output_id,)
    ).fetchone()
    return row["output_text"] if row else None


def db_delete_processed_output(doc_id: str, output_id: str) -> bool:
    """Delete a single processed output."""
    conn = get_connection()
    cur = conn.execute(
        "DELETE FROM processed_outputs WHERE id = ? AND doc_id = ?",
        (output_id, doc_id)
    )
    conn.commit()
    return cur.rowcount > 0


# ===================================================================
#  PROMPTS
# ===================================================================

def db_add_prompt(name: str, text: str, is_system: bool = False,
                  is_favorite: bool = False, max_versions: int = 10) -> int:
    """Add a new prompt and its initial version. Returns prompt_id."""
    conn = get_connection()
    now = _now()

    cur = conn.execute("""
        INSERT INTO prompts (name, is_system, is_favorite, max_versions, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (name, int(is_system), int(is_favorite), max_versions, now, now))
    prompt_id = cur.lastrowid

    # Create initial version (version 0)
    conn.execute("""
        INSERT INTO prompt_versions (prompt_id, version_num, text, created_at, note)
        VALUES (?, 0, ?, ?, 'Initial version')
    """, (prompt_id, text, now))

    conn.commit()
    return prompt_id


def db_get_prompt(prompt_id: int) -> Optional[dict]:
    """Get a prompt with its current (latest) version text."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM prompts WHERE id = ?", (prompt_id,)).fetchone()
    if row is None:
        return None

    d = _row_to_dict(row)
    d["is_system"] = bool(d["is_system"])
    d["is_favorite"] = bool(d["is_favorite"])

    # Get latest version text
    ver = conn.execute("""
        SELECT text, version_num FROM prompt_versions
        WHERE prompt_id = ?
        ORDER BY version_num DESC LIMIT 1
    """, (prompt_id,)).fetchone()
    d["text"] = ver["text"] if ver else ""
    d["current_version"] = ver["version_num"] if ver else 0

    return d


def db_get_all_prompts() -> List[dict]:
    """Get all prompts with their current version text."""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM prompts ORDER BY name").fetchall()

    results = []
    for row in rows:
        d = _row_to_dict(row)
        d["is_system"] = bool(d["is_system"])
        d["is_favorite"] = bool(d["is_favorite"])

        ver = conn.execute("""
            SELECT text, version_num FROM prompt_versions
            WHERE prompt_id = ?
            ORDER BY version_num DESC LIMIT 1
        """, (d["id"],)).fetchone()
        d["text"] = ver["text"] if ver else ""
        d["current_version"] = ver["version_num"] if ver else 0
        results.append(d)

    return results


def db_update_prompt(prompt_id: int, **fields) -> bool:
    """
    Update prompt fields. Allowed: name, is_system, is_favorite,
    last_used, max_versions.
    """
    allowed = {"name", "is_system", "is_favorite", "last_used", "max_versions"}
    to_set = {}
    for k, v in fields.items():
        if k in allowed:
            if k in ("is_system", "is_favorite"):
                to_set[k] = int(v)
            else:
                to_set[k] = v

    if not to_set:
        return False

    to_set["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in to_set)
    values = list(to_set.values()) + [prompt_id]

    conn = get_connection()
    cur = conn.execute(f"UPDATE prompts SET {set_clause} WHERE id = ?", values)
    conn.commit()
    return cur.rowcount > 0


def db_delete_prompt(prompt_id: int) -> bool:
    """Delete a prompt and all its versions (cascade)."""
    conn = get_connection()
    cur = conn.execute("DELETE FROM prompts WHERE id = ?", (prompt_id,))
    conn.commit()
    return cur.rowcount > 0


def db_save_prompt_version(prompt_id: int, text: str, note: str = "") -> int:
    """
    Save a new version of a prompt. Returns the version_num.
    Automatically trims old versions if over max_versions.
    """
    conn = get_connection()
    now = _now()

    # Get next version number
    row = conn.execute(
        "SELECT COALESCE(MAX(version_num), -1) + 1 as next_ver FROM prompt_versions WHERE prompt_id = ?",
        (prompt_id,)
    ).fetchone()
    next_ver = row["next_ver"]

    conn.execute("""
        INSERT INTO prompt_versions (prompt_id, version_num, text, created_at, note)
        VALUES (?, ?, ?, ?, ?)
    """, (prompt_id, next_ver, text, now, note))

    # Update prompt timestamp
    conn.execute(
        "UPDATE prompts SET updated_at = ? WHERE id = ?", (now, prompt_id)
    )

    # Trim old versions if needed
    max_row = conn.execute(
        "SELECT max_versions FROM prompts WHERE id = ?", (prompt_id,)
    ).fetchone()
    if max_row:
        max_v = max_row["max_versions"]
        count = conn.execute(
            "SELECT COUNT(*) as cnt FROM prompt_versions WHERE prompt_id = ?",
            (prompt_id,)
        ).fetchone()["cnt"]
        if count > max_v:
            # Delete oldest versions
            conn.execute("""
                DELETE FROM prompt_versions
                WHERE prompt_id = ? AND version_num IN (
                    SELECT version_num FROM prompt_versions
                    WHERE prompt_id = ?
                    ORDER BY version_num ASC
                    LIMIT ?
                )
            """, (prompt_id, prompt_id, count - max_v))

    conn.commit()
    return next_ver


def db_get_prompt_versions(prompt_id: int) -> List[dict]:
    """Get all versions for a prompt, newest first."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM prompt_versions
        WHERE prompt_id = ?
        ORDER BY version_num DESC
    """, (prompt_id,)).fetchall()
    return [_row_to_dict(r) for r in rows]


def db_search_prompts(query: str) -> List[dict]:
    """Search prompts by name or text content."""
    conn = get_connection()
    pattern = f"%{query}%"
    rows = conn.execute("""
        SELECT DISTINCT p.* FROM prompts p
        LEFT JOIN prompt_versions pv ON p.id = pv.prompt_id
        WHERE p.name LIKE ? COLLATE NOCASE
           OR pv.text LIKE ? COLLATE NOCASE
        ORDER BY p.name
    """, (pattern, pattern)).fetchall()

    results = []
    for row in rows:
        d = _row_to_dict(row)
        d["is_system"] = bool(d["is_system"])
        d["is_favorite"] = bool(d["is_favorite"])
        ver = conn.execute("""
            SELECT text, version_num FROM prompt_versions
            WHERE prompt_id = ?
            ORDER BY version_num DESC LIMIT 1
        """, (d["id"],)).fetchone()
        d["text"] = ver["text"] if ver else ""
        d["current_version"] = ver["version_num"] if ver else 0
        results.append(d)

    return results


# ===================================================================
#  FOLDERS & TREE STRUCTURE
# ===================================================================

def db_create_folder(name: str, library_type: str,
                     parent_id: int = None, workspace_id: int = None,
                     position: int = 0, is_expanded: bool = True) -> int:
    """Create a folder. Returns folder_id."""
    conn = get_connection()
    cur = conn.execute("""
        INSERT INTO folders (name, parent_id, library_type, workspace_id, position, is_expanded, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (name, parent_id, library_type, workspace_id, position, int(is_expanded), _now()))
    conn.commit()
    return cur.lastrowid


def db_rename_folder(folder_id: int, new_name: str) -> bool:
    """Rename a folder."""
    conn = get_connection()
    cur = conn.execute(
        "UPDATE folders SET name = ? WHERE id = ?", (new_name, folder_id)
    )
    conn.commit()
    return cur.rowcount > 0


def db_delete_folder(folder_id: int) -> bool:
    """Delete a folder (cascades to folder_items and child folders)."""
    conn = get_connection()
    cur = conn.execute("DELETE FROM folders WHERE id = ?", (folder_id,))
    conn.commit()
    return cur.rowcount > 0


def db_move_folder(folder_id: int, new_parent_id: int = None,
                   new_position: int = 0) -> bool:
    """Move a folder to a new parent and/or position."""
    conn = get_connection()
    cur = conn.execute(
        "UPDATE folders SET parent_id = ?, position = ? WHERE id = ?",
        (new_parent_id, new_position, folder_id)
    )
    conn.commit()
    return cur.rowcount > 0


def db_add_item_to_folder(folder_id: int, item_type: str,
                          item_id: str, position: int = 0) -> bool:
    """Add an item (document or prompt) to a folder."""
    conn = get_connection()
    try:
        conn.execute("""
            INSERT OR REPLACE INTO folder_items (folder_id, item_type, item_id, position)
            VALUES (?, ?, ?, ?)
        """, (folder_id, item_type, item_id, position))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def db_remove_item_from_folder(folder_id: int, item_type: str,
                               item_id: str) -> bool:
    """Remove an item from a folder."""
    conn = get_connection()
    cur = conn.execute("""
        DELETE FROM folder_items
        WHERE folder_id = ? AND item_type = ? AND item_id = ?
    """, (folder_id, item_type, item_id))
    conn.commit()
    return cur.rowcount > 0


def db_move_item_in_folder(folder_id: int, item_type: str,
                           item_id: str, new_position: int) -> bool:
    """Update the position of an item within its folder."""
    conn = get_connection()
    cur = conn.execute("""
        UPDATE folder_items SET position = ?
        WHERE folder_id = ? AND item_type = ? AND item_id = ?
    """, (new_position, folder_id, item_type, item_id))
    conn.commit()
    return cur.rowcount > 0


def db_get_folder_tree(library_type: str,
                       workspace_id: int = None) -> List[dict]:
    """
    Get the complete folder tree for a library type.
    Returns a list of top-level folder dicts, each with a 'children' key
    containing nested sub-folders, and an 'items' key containing folder_items.
    """
    conn = get_connection()

    if workspace_id is not None:
        folders = conn.execute("""
            SELECT * FROM folders
            WHERE library_type = ? AND workspace_id = ?
            ORDER BY position
        """, (library_type, workspace_id)).fetchall()
    else:
        folders = conn.execute("""
            SELECT * FROM folders
            WHERE library_type = ? AND workspace_id IS NULL
            ORDER BY position
        """, (library_type,)).fetchall()

    # Build lookup
    folder_map = {}
    for f in folders:
        fd = _row_to_dict(f)
        fd["children"] = []
        fd["items"] = []
        folder_map[fd["id"]] = fd

    # Load all items for these folders
    folder_ids = list(folder_map.keys())
    if folder_ids:
        placeholders = ",".join("?" * len(folder_ids))
        items = conn.execute(f"""
            SELECT * FROM folder_items
            WHERE folder_id IN ({placeholders})
            ORDER BY position
        """, folder_ids).fetchall()
        for item in items:
            fid = item["folder_id"]
            if fid in folder_map:
                folder_map[fid]["items"].append(_row_to_dict(item))

    # Build tree
    roots = []
    for fd in folder_map.values():
        pid = fd.get("parent_id")
        if pid and pid in folder_map:
            folder_map[pid]["children"].append(fd)
        else:
            roots.append(fd)

    return roots


# ===================================================================
#  COST LOG
# ===================================================================

def db_log_cost(provider: str, model: str, cost: float,
                document_title: str = None, prompt_name: str = None,
                doc_id: str = None, workspace_id: int = None) -> int:
    """Log an API cost entry. Returns the entry id."""
    conn = get_connection()
    cur = conn.execute("""
        INSERT INTO cost_log
            (timestamp, provider, model, cost, document_title,
             prompt_name, doc_id, workspace_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (_now(), provider, model, cost,
          document_title, prompt_name, doc_id, workspace_id))
    conn.commit()
    return cur.lastrowid


def db_get_costs(since: str = None, provider: str = None,
                 workspace_id: int = None) -> List[dict]:
    """
    Get cost log entries with optional filters.
    'since' is an ISO datetime string.
    """
    conn = get_connection()
    conditions = []
    params = []

    if since:
        conditions.append("timestamp >= ?")
        params.append(since)
    if provider:
        conditions.append("provider = ?")
        params.append(provider)
    if workspace_id is not None:
        conditions.append("workspace_id = ?")
        params.append(workspace_id)

    where = " AND ".join(conditions) if conditions else "1=1"
    rows = conn.execute(
        f"SELECT * FROM cost_log WHERE {where} ORDER BY timestamp DESC",
        params
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def db_get_cost_summary(period: str = "30d",
                        group_by: str = "provider") -> dict:
    """
    Get a cost summary for a time period.
    period: '7d', '30d', '90d', 'all'
    group_by: 'provider' or 'model'
    Returns: {'total': float, 'groups': {name: float}, 'entry_count': int}
    """
    conn = get_connection()

    if period == "all":
        since = "2000-01-01"
    else:
        days = int(period.replace("d", ""))
        since = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat()

    rows = conn.execute(
        "SELECT provider, model, cost FROM cost_log WHERE timestamp >= ?",
        (since,)
    ).fetchall()

    total = 0.0
    groups = {}
    for r in rows:
        total += r["cost"]
        key = r[group_by] if group_by in ("provider", "model") else r["provider"]
        groups[key] = groups.get(key, 0.0) + r["cost"]

    return {
        "total": total,
        "groups": groups,
        "entry_count": len(rows),
        "period": period
    }


# ===================================================================
#  EMBEDDINGS
# ===================================================================

def db_save_embeddings(doc_id: str, chunks: List[dict],
                       embeddings: List[list], cost: float = 0.0,
                       provider: str = None, model: str = None) -> bool:
    """
    Save chunk embeddings for a document. Replaces any existing embeddings.
    chunks: list of {'text': '...', 'start': int, 'end': int}
    embeddings: list of float lists (one per chunk)
    """
    conn = get_connection()
    now = _now()

    # Delete existing embeddings for this doc
    conn.execute("DELETE FROM embeddings WHERE doc_id = ?", (doc_id,))

    per_chunk_cost = cost / len(chunks) if chunks else 0.0

    for idx, (chunk, emb) in enumerate(zip(chunks, embeddings)):
        conn.execute("""
            INSERT INTO embeddings
                (doc_id, chunk_idx, chunk_text, embedding, model, cost, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (doc_id, idx, chunk.get("text", ""),
              _floats_to_blob(emb), model, per_chunk_cost, now))

    conn.commit()
    return True


def db_get_embeddings(doc_id: str) -> List[dict]:
    """
    Get all chunk embeddings for a document.
    Returns list of {'chunk_idx': int, 'text': str, 'embedding': [floats]}.
    """
    conn = get_connection()
    rows = conn.execute("""
        SELECT chunk_idx, chunk_text, embedding
        FROM embeddings
        WHERE doc_id = ?
        ORDER BY chunk_idx
    """, (doc_id,)).fetchall()

    results = []
    for r in rows:
        results.append({
            "chunk_idx": r["chunk_idx"],
            "text": r["chunk_text"],
            "embedding": _blob_to_floats(r["embedding"])
        })
    return results


def db_has_embeddings(doc_id: str) -> bool:
    """Check whether a document has stored embeddings."""
    conn = get_connection()
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM embeddings WHERE doc_id = ?",
        (doc_id,)
    ).fetchone()
    return row["cnt"] > 0


def db_delete_embeddings(doc_id: str) -> bool:
    """Remove all embeddings for a document."""
    conn = get_connection()
    cur = conn.execute("DELETE FROM embeddings WHERE doc_id = ?", (doc_id,))
    conn.commit()
    return cur.rowcount > 0


def db_get_all_embeddings_flat() -> List[dict]:
    """
    Get all embeddings across all documents (for bulk similarity search).
    Returns list of {'doc_id': str, 'chunk_idx': int, 'text': str, 'embedding': [floats]}.
    """
    conn = get_connection()
    rows = conn.execute("""
        SELECT e.doc_id, e.chunk_idx, e.chunk_text, e.embedding
        FROM embeddings e
        JOIN documents d ON e.doc_id = d.id
        WHERE d.is_deleted = 0
        ORDER BY e.doc_id, e.chunk_idx
    """).fetchall()

    results = []
    for r in rows:
        results.append({
            "doc_id": r["doc_id"],
            "chunk_idx": r["chunk_idx"],
            "text": r["chunk_text"],
            "embedding": _blob_to_floats(r["embedding"])
        })
    return results


def db_get_embedding_stats() -> dict:
    """Get statistics about stored embeddings."""
    conn = get_connection()
    total_chunks = conn.execute("SELECT COUNT(*) as cnt FROM embeddings").fetchone()["cnt"]
    total_docs = conn.execute(
        "SELECT COUNT(DISTINCT doc_id) as cnt FROM embeddings"
    ).fetchone()["cnt"]
    total_cost = conn.execute(
        "SELECT COALESCE(SUM(cost), 0) as total FROM embeddings"
    ).fetchone()["total"]

    return {
        "total_chunks": total_chunks,
        "indexed_documents": total_docs,
        "total_cost": total_cost
    }


# ===================================================================
#  CORRECTIONS LISTS  (v1.7-alpha)
# ===================================================================

def db_get_all_corrections_lists(workspace_id: int = None) -> List[dict]:
    """
    Return every corrections list in the given workspace.
    workspace_id=None (default) returns lists with workspace_id IS NULL,
    which is the v1.7-alpha case (workspaces deferred to Phase 2).
    """
    conn = get_connection()
    if workspace_id is None:
        rows = conn.execute(
            "SELECT * FROM corrections_lists "
            "WHERE workspace_id IS NULL ORDER BY name"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM corrections_lists "
            "WHERE workspace_id = ? ORDER BY name",
            (workspace_id,)
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def db_get_corrections_list(list_id: int) -> Optional[dict]:
    """Return a single corrections list by id, or None if not found."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM corrections_lists WHERE id = ?", (list_id,)
    ).fetchone()
    return _row_to_dict(row) if row else None


def db_get_corrections_list_by_name(name: str,
                                    workspace_id: int = None) -> Optional[dict]:
    """Return a corrections list by name (within optional workspace), or None."""
    conn = get_connection()
    if workspace_id is None:
        row = conn.execute(
            "SELECT * FROM corrections_lists "
            "WHERE name = ? AND workspace_id IS NULL",
            (name,)
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM corrections_lists "
            "WHERE name = ? AND workspace_id = ?",
            (name, workspace_id)
        ).fetchone()
    return _row_to_dict(row) if row else None


def db_create_corrections_list(name: str, description: str = None,
                               workspace_id: int = None) -> int:
    """Create a new corrections list. Returns the new list_id."""
    conn = get_connection()
    now = _now()
    cur = conn.execute(
        """INSERT INTO corrections_lists
           (name, description, workspace_id, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?)""",
        (name, description, workspace_id, now, now)
    )
    conn.commit()
    return cur.lastrowid


def db_update_corrections_list(list_id: int, **fields) -> bool:
    """
    Update a corrections list. Allowed fields: name, description.
    workspace_id is intentionally not updatable through this API; lists
    are reassigned to a workspace via dedicated migration tools (Phase 2).
    """
    allowed = {"name", "description"}
    to_set = {k: v for k, v in fields.items() if k in allowed}
    if not to_set:
        return False
    to_set["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in to_set)
    values = list(to_set.values()) + [list_id]
    conn = get_connection()
    cur = conn.execute(
        f"UPDATE corrections_lists SET {set_clause} WHERE id = ?", values
    )
    conn.commit()
    return cur.rowcount > 0


def db_delete_corrections_list(list_id: int) -> bool:
    """Delete a corrections list and all its corrections (cascade)."""
    conn = get_connection()
    cur = conn.execute(
        "DELETE FROM corrections_lists WHERE id = ?", (list_id,)
    )
    conn.commit()
    return cur.rowcount > 0


# ===================================================================
#  CORRECTIONS  (v1.7-alpha)
# ===================================================================

def db_get_corrections(list_id: int) -> List[dict]:
    """Return all corrections in a list, ordered by id (insertion order)."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM corrections WHERE list_id = ? ORDER BY id",
        (list_id,)
    ).fetchall()
    results = []
    for r in rows:
        d = _row_to_dict(r)
        d["case_sensitive"] = bool(d["case_sensitive"])
        d["word_boundary"] = bool(d["word_boundary"])
        results.append(d)
    return results


def db_get_correction(correction_id: int) -> Optional[dict]:
    """Return a single correction entry by id, or None."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM corrections WHERE id = ?", (correction_id,)
    ).fetchone()
    if row is None:
        return None
    d = _row_to_dict(row)
    d["case_sensitive"] = bool(d["case_sensitive"])
    d["word_boundary"] = bool(d["word_boundary"])
    return d


def db_add_correction(list_id: int, original_text: str, corrected_text: str,
                      case_sensitive: bool = False, word_boundary: bool = True,
                      notes: str = None) -> int:
    """Insert a new correction entry. Returns the new correction id.
    Also bumps the parent list's updated_at."""
    conn = get_connection()
    now = _now()
    cur = conn.execute(
        """INSERT INTO corrections
           (list_id, original_text, corrected_text,
            case_sensitive, word_boundary, notes, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (list_id, original_text, corrected_text,
         int(case_sensitive), int(word_boundary), notes, now)
    )
    conn.execute(
        "UPDATE corrections_lists SET updated_at = ? WHERE id = ?",
        (now, list_id)
    )
    conn.commit()
    return cur.lastrowid


def db_update_correction(correction_id: int, **fields) -> bool:
    """
    Update a correction entry. Allowed: original_text, corrected_text,
    case_sensitive, word_boundary, notes.
    Bumps the parent list's updated_at if anything changed.
    """
    allowed = {"original_text", "corrected_text",
               "case_sensitive", "word_boundary", "notes"}
    to_set = {}
    for k, v in fields.items():
        if k not in allowed:
            continue
        if k in ("case_sensitive", "word_boundary"):
            to_set[k] = int(bool(v))
        else:
            to_set[k] = v
    if not to_set:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in to_set)
    values = list(to_set.values()) + [correction_id]
    conn = get_connection()
    cur = conn.execute(
        f"UPDATE corrections SET {set_clause} WHERE id = ?", values
    )
    if cur.rowcount > 0:
        list_row = conn.execute(
            "SELECT list_id FROM corrections WHERE id = ?", (correction_id,)
        ).fetchone()
        if list_row:
            conn.execute(
                "UPDATE corrections_lists SET updated_at = ? WHERE id = ?",
                (_now(), list_row["list_id"])
            )
    conn.commit()
    return cur.rowcount > 0


def db_delete_correction(correction_id: int) -> bool:
    """Delete a single correction entry. Bumps parent list's updated_at."""
    conn = get_connection()
    row = conn.execute(
        "SELECT list_id FROM corrections WHERE id = ?", (correction_id,)
    ).fetchone()
    cur = conn.execute(
        "DELETE FROM corrections WHERE id = ?", (correction_id,)
    )
    if cur.rowcount > 0 and row:
        conn.execute(
            "UPDATE corrections_lists SET updated_at = ? WHERE id = ?",
            (_now(), row["list_id"])
        )
    conn.commit()
    return cur.rowcount > 0


# ===================================================================
#  BACKUPS  (v1.7-alpha)
# ===================================================================

def db_create_backup(document_id: str, trigger_type: str,
                     content_blob: str, label: str = None) -> int:
    """
    Insert a new backup row. Returns the new backup id.

    `content_blob` is a serialised JSON string — the caller (typically
    backups_manager) owns the payload schema. Retention pruning is the
    caller's responsibility via db_prune_backups(), so callers can opt
    out of pruning for one-off cases (e.g. an export-all-backups path).
    """
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO backups
           (document_id, trigger_type, label, content_blob, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (document_id, trigger_type, label, content_blob, _now())
    )
    conn.commit()
    return cur.lastrowid


def db_list_backups(document_id: str) -> List[dict]:
    """
    Return all backups for a document, newest first.

    Lightweight projection — does NOT include content_blob (which can be
    large, e.g. a full transcript). Use db_get_backup() to load the full
    blob when needed for restore or preview.
    """
    conn = get_connection()
    rows = conn.execute(
        """SELECT id, document_id, trigger_type, label, created_at
           FROM backups
           WHERE document_id = ?
           ORDER BY created_at DESC""",
        (document_id,)
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def db_get_backup(backup_id: int) -> Optional[dict]:
    """Load a single backup including its content_blob. Returns None if not found."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM backups WHERE id = ?", (backup_id,)
    ).fetchone()
    return _row_to_dict(row) if row else None


def db_delete_backup(backup_id: int) -> bool:
    """Delete a single backup. Returns True if a row was deleted."""
    conn = get_connection()
    cur = conn.execute("DELETE FROM backups WHERE id = ?", (backup_id,))
    conn.commit()
    return cur.rowcount > 0


def db_prune_backups(document_id: str, keep: int = 10) -> int:
    """
    Delete all but the `keep` most-recent backups for a document.
    Returns the number of rows deleted.

    Called by backups_manager after every create_backup(). Not called
    automatically by db_create_backup() so callers can opt out (e.g.
    a future export-all-backups path) without contortion.
    """
    conn = get_connection()
    cur = conn.execute(
        """DELETE FROM backups
           WHERE document_id = ?
             AND id NOT IN (
                 SELECT id FROM backups
                 WHERE document_id = ?
                 ORDER BY created_at DESC
                 LIMIT ?
             )""",
        (document_id, document_id, keep)
    )
    conn.commit()
    return cur.rowcount
