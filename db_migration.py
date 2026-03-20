"""
db_migration.py — One-time migration from JSON/TXT files to SQLite.

Reads the existing data files in DATA_DIR and populates the SQLite
database via db_manager.py functions.  Designed to run once on first
startup after the update.

Safety features:
    - All writes happen inside a single transaction.
    - If anything goes wrong, the transaction rolls back and the
      original files are left untouched.
    - After a successful migration the old files are renamed to .bak
      (not deleted).
    - A flag inside the database prevents the migration from running
      a second time.

Created: 28 February 2026
"""

from __future__ import annotations

import os
import re
import sys
import json
import glob
import struct
import shutil
import logging
import datetime
import traceback
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from config import DATA_DIR, LIBRARY_PATH, PROMPTS_PATH
import db_manager as db

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

log = logging.getLogger("db_migration")
log.setLevel(logging.DEBUG)

# Console handler (always visible)
_ch = logging.StreamHandler()
_ch.setLevel(logging.INFO)
_ch.setFormatter(logging.Formatter("%(message)s"))
log.addHandler(_ch)

# File handler (detailed log in DATA_DIR)
_log_path = os.path.join(DATA_DIR, "migration_log.txt")
try:
    _fh = logging.FileHandler(_log_path, encoding="utf-8")
    _fh.setLevel(logging.DEBUG)
    _fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    log.addHandler(_fh)
except Exception:
    pass  # If we can't write a log file, carry on anyway


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

LIBRARY_TREE_PATH = LIBRARY_PATH.replace(".json", "_tree.json")
COST_LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cost_log.txt")
EMBEDDINGS_PATH = os.path.join(DATA_DIR, "embeddings.json")
HELP_TEXTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "help_texts.json")

# Also check DATA_DIR for cost_log.txt (it might be in either location)
if not os.path.exists(COST_LOG_PATH):
    alt = os.path.join(DATA_DIR, "cost_log.txt")
    if os.path.exists(alt):
        COST_LOG_PATH = alt


# ===================================================================
#  MIGRATION COUNTERS — used for the summary report
# ===================================================================

class MigrationStats:
    """Simple counter object passed through each stage."""
    def __init__(self):
        self.documents = 0
        self.entries_files = 0
        self.entries_rows = 0
        self.conversations = 0
        self.messages = 0
        self.processed_outputs = 0
        self.prompts = 0
        self.prompt_versions = 0
        self.doc_folders = 0
        self.doc_folder_items = 0
        self.prompt_folders = 0
        self.prompt_folder_items = 0
        self.cost_entries = 0
        self.embeddings_docs = 0
        self.embeddings_chunks = 0
        self.warnings: List[str] = []
        self.skipped: List[str] = []

    def summary(self) -> str:
        lines = [
            "",
            "=" * 60,
            "  MIGRATION SUMMARY",
            "=" * 60,
            f"  Documents migrated:       {self.documents}",
            f"  Entry files processed:    {self.entries_files}",
            f"  Entry rows written:       {self.entries_rows}",
            f"  Conversations:            {self.conversations}",
            f"  Messages:                 {self.messages}",
            f"  Processed outputs:        {self.processed_outputs}",
            f"  Prompts:                  {self.prompts}",
            f"  Prompt versions:          {self.prompt_versions}",
            f"  Document folders:         {self.doc_folders}",
            f"  Document folder items:    {self.doc_folder_items}",
            f"  Prompt folders:           {self.prompt_folders}",
            f"  Prompt folder items:      {self.prompt_folder_items}",
            f"  Cost log entries:         {self.cost_entries}",
            f"  Embedded documents:       {self.embeddings_docs}",
            f"  Embedding chunks:         {self.embeddings_chunks}",
            "=" * 60,
        ]
        if self.warnings:
            lines.append(f"  Warnings ({len(self.warnings)}):")
            for w in self.warnings[:20]:
                lines.append(f"    ⚠ {w}")
            if len(self.warnings) > 20:
                lines.append(f"    ... and {len(self.warnings) - 20} more")
        if self.skipped:
            lines.append(f"  Skipped files ({len(self.skipped)}):")
            for s in self.skipped[:10]:
                lines.append(f"    → {s}")
        lines.append("=" * 60)
        return "\n".join(lines)


# ===================================================================
#  HELPER: safe JSON loading
# ===================================================================

def _load_json(path: str, default=None):
    """Load JSON file, returning *default* on any error."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        log.warning(f"Could not load {path}: {exc}")
        return default


# ===================================================================
#  STAGE 1 — DOCUMENTS
# ===================================================================

def migrate_documents(conn, stats: MigrationStats):
    """Read document_library.json and insert rows into `documents`."""
    if not os.path.exists(LIBRARY_PATH):
        log.info("No document_library.json found — skipping documents.")
        return

    library = _load_json(LIBRARY_PATH, {})
    docs = library.get("documents", [])
    log.info(f"Found {len(docs)} documents in library.")

    for doc in docs:
        doc_id = doc.get("id")
        if not doc_id:
            stats.warnings.append("Skipped document with no ID")
            continue

        title = doc.get("title", "Untitled")
        doc_type = doc.get("type", "unknown")
        document_class = doc.get("document_class", "source")
        source = doc.get("source", "")
        created_at = doc.get("fetched", datetime.datetime.now().isoformat())
        entry_count = doc.get("entry_count", 0)
        parent_doc_id = doc.get("metadata", {}).get("original_document_id") or \
                        doc.get("metadata", {}).get("parent_document_id")

        # Everything else goes into the metadata JSON blob
        metadata = doc.get("metadata", {})

        try:
            conn.execute(
                """INSERT OR REPLACE INTO documents
                   (id, title, doc_type, document_class, source,
                    created_at, updated_at, entry_count, metadata,
                    parent_doc_id, is_deleted)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
                (doc_id, title, doc_type, document_class, source,
                 created_at, None, entry_count,
                 json.dumps(metadata) if metadata else None,
                 parent_doc_id)
            )
            stats.documents += 1
        except Exception as exc:
            stats.warnings.append(f"Document '{title}' ({doc_id}): {exc}")

    log.info(f"  → {stats.documents} documents migrated.")


# ===================================================================
#  STAGE 2 — DOCUMENT ENTRIES
# ===================================================================

def migrate_entries(conn, stats: MigrationStats):
    """Read doc_{id}_entries.json files and insert into `document_entries`."""
    pattern = os.path.join(DATA_DIR, "doc_*_entries.json")
    entry_files = glob.glob(pattern)
    log.info(f"Found {len(entry_files)} entry files to migrate.")

    for filepath in entry_files:
        filename = os.path.basename(filepath)
        # Extract doc_id: "doc_abc123_entries.json" → "abc123"
        match = re.match(r"doc_(.+)_entries\.json$", filename)
        if not match:
            stats.skipped.append(filename)
            continue

        doc_id = match.group(1)

        # Check this document exists in the database
        row = conn.execute(
            "SELECT id FROM documents WHERE id = ?", (doc_id,)
        ).fetchone()
        if not row:
            stats.warnings.append(
                f"Entry file '{filename}' has no matching document — skipping."
            )
            continue

        entries = _load_json(filepath, [])
        if not isinstance(entries, list):
            stats.warnings.append(f"Entry file '{filename}' is not a list — skipping.")
            continue

        for pos, entry in enumerate(entries):
            content = entry.get("text", "") or entry.get("content", "")
            entry_type = entry.get("type", "text")

            # Preserve any entry-level metadata (start_time, speaker, etc.)
            entry_meta = {}
            for key in ("start", "start_time", "speaker", "duration",
                        "end", "end_time", "confidence", "words"):
                if key in entry:
                    entry_meta[key] = entry[key]

            try:
                conn.execute(
                    """INSERT INTO document_entries
                       (doc_id, position, content, entry_type, metadata)
                       VALUES (?, ?, ?, ?, ?)""",
                    (doc_id, pos, content, entry_type,
                     json.dumps(entry_meta) if entry_meta else None)
                )
                stats.entries_rows += 1
            except Exception as exc:
                stats.warnings.append(f"Entry {pos} of {doc_id}: {exc}")

        stats.entries_files += 1

    log.info(f"  → {stats.entries_files} entry files, "
             f"{stats.entries_rows} rows migrated.")


# ===================================================================
#  STAGE 3 — CONVERSATIONS & MESSAGES
# ===================================================================

def migrate_conversations(conn, stats: MigrationStats):
    """Extract conversation_thread from document_library.json."""
    if not os.path.exists(LIBRARY_PATH):
        return

    library = _load_json(LIBRARY_PATH, {})

    for doc in library.get("documents", []):
        thread = doc.get("conversation_thread", [])
        if not thread:
            continue

        doc_id = doc.get("id")
        if not doc_id:
            continue

        thread_meta = doc.get("thread_metadata", {})
        created_at = thread_meta.get("started_at",
                     thread_meta.get("last_updated",
                     datetime.datetime.now().isoformat()))
        updated_at = thread_meta.get("last_updated")

        try:
            cursor = conn.execute(
                """INSERT INTO conversations
                   (doc_id, created_at, updated_at, message_count, metadata)
                   VALUES (?, ?, ?, ?, ?)""",
                (doc_id, created_at, updated_at, len(thread),
                 json.dumps(thread_meta) if thread_meta else None)
            )
            conv_id = cursor.lastrowid
            stats.conversations += 1

            for pos, msg in enumerate(thread):
                role = msg.get("role", "user")
                content = msg.get("content", "")
                timestamp = msg.get("timestamp")
                provider = msg.get("provider")
                model = msg.get("model")

                # Collect any extra fields as metadata
                msg_meta = {k: v for k, v in msg.items()
                            if k not in ("role", "content", "timestamp",
                                         "provider", "model")}

                conn.execute(
                    """INSERT INTO messages
                       (conversation_id, position, role, content,
                        timestamp, provider, model, metadata)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (conv_id, pos, role, content, timestamp,
                     provider, model,
                     json.dumps(msg_meta) if msg_meta else None)
                )
                stats.messages += 1

        except Exception as exc:
            stats.warnings.append(f"Conversation for doc {doc_id}: {exc}")

    log.info(f"  → {stats.conversations} conversations, "
             f"{stats.messages} messages migrated.")


# ===================================================================
#  STAGE 4 — PROCESSED OUTPUTS
# ===================================================================

def migrate_processed_outputs(conn, stats: MigrationStats):
    """Extract processed_outputs from document_library.json +
       read the matching output_{id}.txt files."""
    if not os.path.exists(LIBRARY_PATH):
        return

    library = _load_json(LIBRARY_PATH, {})

    for doc in library.get("documents", []):
        outputs = doc.get("processed_outputs", [])
        if not outputs:
            continue

        doc_id = doc.get("id")
        if not doc_id:
            continue

        for out in outputs:
            output_id = out.get("id")
            if not output_id:
                stats.warnings.append(
                    f"Output without ID in doc {doc_id} — skipping.")
                continue

            created_at = out.get("created", out.get("timestamp",
                         datetime.datetime.now().isoformat()))
            prompt_name = out.get("prompt_name", out.get("prompt", ""))
            prompt_text = out.get("prompt_text", "")
            provider = out.get("provider", "")
            model = out.get("model", "")
            preview = out.get("preview", "")
            notes = out.get("notes", "")

            # Try to load the full output text from file
            output_file = os.path.join(DATA_DIR, f"output_{output_id}.txt")
            output_text = ""
            if os.path.exists(output_file):
                try:
                    with open(output_file, "r", encoding="utf-8") as f:
                        output_text = f.read()
                except Exception:
                    output_text = preview  # Fallback to preview

            if not output_text:
                output_text = preview or "(no text)"

            try:
                conn.execute(
                    """INSERT OR REPLACE INTO processed_outputs
                       (id, doc_id, created_at, prompt_name, prompt_text,
                        provider, model, output_text, preview, notes)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (output_id, doc_id, created_at, prompt_name,
                     prompt_text, provider, model, output_text,
                     preview, notes)
                )
                stats.processed_outputs += 1
            except Exception as exc:
                stats.warnings.append(
                    f"Output {output_id} for doc {doc_id}: {exc}")

    log.info(f"  → {stats.processed_outputs} processed outputs migrated.")


# ===================================================================
#  STAGE 5 — PROMPTS & PROMPT VERSIONS
# ===================================================================

def migrate_prompts(conn, stats: MigrationStats) -> Dict[str, int]:
    """Read prompts.json and insert prompts + versions.

    Returns a mapping of prompt_name → prompt_id for folder_items.
    """
    prompt_name_to_id: Dict[str, int] = {}

    if not os.path.exists(PROMPTS_PATH):
        log.info("No prompts.json found — skipping prompts.")
        return prompt_name_to_id

    data = _load_json(PROMPTS_PATH, {})

    # Handle both tree format (v2.0) and flat format (legacy)
    if isinstance(data, list):
        # Legacy flat format: [{"name": "...", "text": "..."}, ...]
        prompts_list = data
        _migrate_flat_prompts(conn, prompts_list, prompt_name_to_id, stats)
    elif isinstance(data, dict) and "root_folders" in data:
        # Tree format v2.0
        _migrate_tree_prompts(conn, data, prompt_name_to_id, stats)
    else:
        stats.warnings.append("prompts.json has unrecognised format.")

    log.info(f"  → {stats.prompts} prompts, "
             f"{stats.prompt_versions} versions migrated.")
    return prompt_name_to_id


def _migrate_flat_prompts(conn, prompts_list: list,
                          name_map: dict, stats: MigrationStats):
    """Migrate legacy flat prompt list."""
    for item in prompts_list:
        name = item.get("name", "Unnamed")
        text = item.get("text", "")
        _insert_one_prompt(conn, name, text, False, False, None,
                           [{"text": text, "note": "Initial version",
                             "is_default": False, "is_system": False,
                             "timestamp": datetime.datetime.now().isoformat()}],
                           0, 10, name_map, stats)


def _migrate_tree_prompts(conn, data: dict,
                          name_map: dict, stats: MigrationStats):
    """Walk the prompt tree and insert every PromptItem."""

    def walk_folder(children: dict):
        for child_name, child_data in children.items():
            ctype = child_data.get("type", "")
            if ctype == "folder":
                walk_folder(child_data.get("children", {}))
            elif ctype == "prompt":
                _insert_prompt_from_tree_node(conn, child_data,
                                              name_map, stats)

    for folder_name, folder_data in data.get("root_folders", {}).items():
        walk_folder(folder_data.get("children", {}))


def _insert_prompt_from_tree_node(conn, node: dict,
                                  name_map: dict, stats: MigrationStats):
    """Insert one prompt from its tree-format dict."""
    name = node.get("name", "Unnamed")
    is_system = node.get("is_system_prompt", False)
    is_favorite = node.get("is_favorite", False)
    last_used = node.get("last_used")
    versions = node.get("versions", [])
    current_idx = node.get("current_version_index", 0)
    max_versions = node.get("max_versions", 10)

    # Get initial text from the current version (or first version)
    if versions:
        safe_idx = min(current_idx, len(versions) - 1)
        text = versions[safe_idx].get("text", "")
    else:
        text = ""

    _insert_one_prompt(conn, name, text, is_system, is_favorite,
                       last_used, versions, current_idx, max_versions,
                       name_map, stats)


def _insert_one_prompt(conn, name, text, is_system, is_favorite,
                       last_used, versions, current_idx, max_versions,
                       name_map, stats: MigrationStats):
    """Insert a prompt row and all its version rows."""
    try:
        cursor = conn.execute(
            """INSERT INTO prompts
               (name, is_system, is_favorite, last_used,
                max_versions, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (name,
             1 if is_system else 0,
             1 if is_favorite else 0,
             last_used,
             max_versions,
             datetime.datetime.now().isoformat(),
             None)
        )
        prompt_id = cursor.lastrowid
        name_map[name] = prompt_id
        stats.prompts += 1

        # Insert versions
        for v_idx, v_data in enumerate(versions):
            v_text = v_data.get("text", "")
            v_note = v_data.get("note", "")
            v_is_default = v_data.get("is_default", False)
            v_timestamp = v_data.get("timestamp",
                          datetime.datetime.now().isoformat())

            is_current = (v_idx == current_idx)

            conn.execute(
                """INSERT INTO prompt_versions
                   (prompt_id, version_num, text, note,
                    is_default, is_current, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (prompt_id, v_idx, v_text, v_note,
                 1 if v_is_default else 0,
                 1 if is_current else 0,
                 v_timestamp)
            )
            stats.prompt_versions += 1

    except Exception as exc:
        stats.warnings.append(f"Prompt '{name}': {exc}")


# ===================================================================
#  STAGE 6 — FOLDERS & FOLDER ITEMS
# ===================================================================

def migrate_document_tree(conn, stats: MigrationStats):
    """Read document_library_tree.json and build folder + folder_item rows."""
    if not os.path.exists(LIBRARY_TREE_PATH):
        log.info("No document_library_tree.json found — skipping doc folders.")
        return

    data = _load_json(LIBRARY_TREE_PATH, {})
    root_folders = data.get("root_folders", {})
    log.info(f"Found {len(root_folders)} root document folders.")

    for folder_name, folder_data in root_folders.items():
        _migrate_folder_recursive(
            conn, folder_name, folder_data,
            parent_id=None, library_type="documents",
            stats=stats, is_doc_tree=True
        )

    log.info(f"  → {stats.doc_folders} document folders, "
             f"{stats.doc_folder_items} document folder items.")


def migrate_prompt_tree(conn, prompt_name_to_id: Dict[str, int],
                        stats: MigrationStats):
    """Read prompts.json tree structure and build folder + folder_item rows."""
    if not os.path.exists(PROMPTS_PATH):
        return

    data = _load_json(PROMPTS_PATH, {})
    if not isinstance(data, dict) or "root_folders" not in data:
        log.info("prompts.json is flat format — no folder structure to migrate.")
        return

    root_folders = data.get("root_folders", {})
    log.info(f"Found {len(root_folders)} root prompt folders.")

    for folder_name, folder_data in root_folders.items():
        _migrate_folder_recursive(
            conn, folder_name, folder_data,
            parent_id=None, library_type="prompts",
            stats=stats, is_doc_tree=False,
            prompt_name_to_id=prompt_name_to_id
        )

    log.info(f"  → {stats.prompt_folders} prompt folders, "
             f"{stats.prompt_folder_items} prompt folder items.")


def _migrate_folder_recursive(conn, folder_name, folder_data,
                              parent_id, library_type, stats,
                              is_doc_tree, prompt_name_to_id=None,
                              position=0):
    """Recursively create folder and folder_item rows."""
    expanded = folder_data.get("expanded", True)

    try:
        cursor = conn.execute(
            """INSERT INTO folders
               (name, parent_id, library_type, workspace_id,
                position, is_expanded, created_at)
               VALUES (?, ?, ?, NULL, ?, ?, ?)""",
            (folder_name, parent_id, library_type, position,
             1 if expanded else 0,
             datetime.datetime.now().isoformat())
        )
        folder_id = cursor.lastrowid

        if is_doc_tree:
            stats.doc_folders += 1
        else:
            stats.prompt_folders += 1
    except Exception as exc:
        stats.warnings.append(f"Folder '{folder_name}': {exc}")
        return

    # Process children
    children = folder_data.get("children", {})
    child_pos = 0

    for child_name, child_data in children.items():
        child_type = child_data.get("type", "")

        if child_type == "folder":
            # Recurse into sub-folder
            _migrate_folder_recursive(
                conn, child_name, child_data,
                parent_id=folder_id, library_type=library_type,
                stats=stats, is_doc_tree=is_doc_tree,
                prompt_name_to_id=prompt_name_to_id,
                position=child_pos
            )
        elif child_type == "document" and is_doc_tree:
            # Document reference in tree
            doc_id = child_data.get("doc_id")
            if doc_id:
                try:
                    conn.execute(
                        """INSERT INTO folder_items
                           (folder_id, item_type, document_id,
                            prompt_id, position)
                           VALUES (?, 'document', ?, NULL, ?)""",
                        (folder_id, doc_id, child_pos)
                    )
                    stats.doc_folder_items += 1
                except Exception as exc:
                    stats.warnings.append(
                        f"Doc folder item '{child_name}': {exc}")
        elif child_type == "prompt" and not is_doc_tree:
            # Prompt reference in tree
            prompt_name = child_data.get("name", child_name)
            prompt_id = (prompt_name_to_id or {}).get(prompt_name)
            if prompt_id:
                try:
                    conn.execute(
                        """INSERT INTO folder_items
                           (folder_id, item_type, document_id,
                            prompt_id, position)
                           VALUES (?, 'prompt', NULL, ?, ?)""",
                        (folder_id, prompt_id, child_pos)
                    )
                    stats.prompt_folder_items += 1
                except Exception as exc:
                    stats.warnings.append(
                        f"Prompt folder item '{prompt_name}': {exc}")
            else:
                stats.warnings.append(
                    f"Prompt '{prompt_name}' not found in DB — "
                    f"folder item skipped.")

        child_pos += 1


# ===================================================================
#  STAGE 7 — COST LOG
# ===================================================================

def migrate_cost_log(conn, stats: MigrationStats):
    """Read cost_log.txt (pipe-delimited) and insert into `cost_log`."""
    if not os.path.exists(COST_LOG_PATH):
        log.info("No cost_log.txt found — skipping cost log.")
        return

    try:
        with open(COST_LOG_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as exc:
        stats.warnings.append(f"Could not read cost_log.txt: {exc}")
        return

    log.info(f"Found {len(lines)} lines in cost_log.txt.")

    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue

        # Format: timestamp | provider | model | $cost | doc_title | prompt_name
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 4:
            stats.warnings.append(
                f"cost_log line {line_num}: fewer than 4 fields — skipping.")
            continue

        timestamp = parts[0]
        provider = parts[1]
        model = parts[2]

        # Parse cost: "$0.001234" → 0.001234
        cost_str = parts[3].replace("$", "").strip()
        try:
            cost = float(cost_str)
        except ValueError:
            stats.warnings.append(
                f"cost_log line {line_num}: bad cost '{cost_str}' — skipping.")
            continue

        doc_title = parts[4] if len(parts) > 4 else None
        prompt_summary = parts[5] if len(parts) > 5 else None

        # Clean up N/A values
        if doc_title == "N/A":
            doc_title = None
        if prompt_summary == "N/A":
            prompt_summary = None

        try:
            conn.execute(
                """INSERT INTO cost_log
                   (timestamp, provider, model, cost,
                    doc_title, prompt_summary, doc_id, workspace_id)
                   VALUES (?, ?, ?, ?, ?, ?, NULL, NULL)""",
                (timestamp, provider, model, cost,
                 doc_title, prompt_summary)
            )
            stats.cost_entries += 1
        except Exception as exc:
            stats.warnings.append(f"cost_log line {line_num}: {exc}")

    log.info(f"  → {stats.cost_entries} cost entries migrated.")


# ===================================================================
#  STAGE 8 — EMBEDDINGS
# ===================================================================

def migrate_embeddings(conn, stats: MigrationStats):
    """Read embeddings.json and insert into `embeddings` as BLOBs."""
    if not os.path.exists(EMBEDDINGS_PATH):
        log.info("No embeddings.json found — skipping embeddings.")
        return

    data = _load_json(EMBEDDINGS_PATH, {})
    documents = data.get("documents", {})
    default_provider = data.get("provider", "openai")
    default_model = data.get("model", "text-embedding-3-small")

    log.info(f"Found embeddings for {len(documents)} documents.")

    for doc_id, doc_data in documents.items():
        # Check the document exists in DB
        row = conn.execute(
            "SELECT id FROM documents WHERE id = ?", (doc_id,)
        ).fetchone()
        if not row:
            stats.warnings.append(
                f"Embedding for doc {doc_id} — document not in DB, skipping.")
            continue

        chunks = doc_data.get("chunks", [])
        generated_at = doc_data.get("generated_at",
                       datetime.datetime.now().isoformat())
        total_cost = doc_data.get("total_cost", 0.0)

        for chunk_idx, chunk in enumerate(chunks):
            embedding_list = chunk.get("embedding", [])
            if not embedding_list:
                continue

            # Convert float list to binary BLOB (compact storage)
            try:
                blob = struct.pack(f"{len(embedding_list)}f",
                                   *embedding_list)
            except Exception as exc:
                stats.warnings.append(
                    f"Embedding blob for {doc_id} chunk {chunk_idx}: {exc}")
                continue

            text_preview = chunk.get("text", "")[:500]
            start_char = chunk.get("start_char", 0)
            end_char = chunk.get("end_char", 0)
            word_count = len(text_preview.split()) if text_preview else 0

            try:
                conn.execute(
                    """INSERT INTO embeddings
                       (doc_id, chunk_index, text_preview, embedding,
                        start_char, end_char, word_count,
                        generated_at, cost, provider, model)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (doc_id, chunk_idx, text_preview, blob,
                     start_char, end_char, word_count,
                     generated_at, total_cost / max(len(chunks), 1),
                     default_provider, default_model)
                )
                stats.embeddings_chunks += 1
            except Exception as exc:
                stats.warnings.append(
                    f"Embedding {doc_id} chunk {chunk_idx}: {exc}")

        stats.embeddings_docs += 1

    log.info(f"  → {stats.embeddings_docs} documents, "
             f"{stats.embeddings_chunks} chunks migrated.")


# ===================================================================
#  BACKUP — rename old files to .bak
# ===================================================================

def backup_old_files(stats: MigrationStats):
    """Rename migrated JSON/TXT files to .bak so the app
    doesn't accidentally read them again."""

    files_to_backup = [
        LIBRARY_PATH,
        LIBRARY_TREE_PATH,
        PROMPTS_PATH,
        COST_LOG_PATH,
        EMBEDDINGS_PATH,
    ]

    # Also back up all doc_*_entries.json and output_*.txt
    for f in glob.glob(os.path.join(DATA_DIR, "doc_*_entries.json")):
        files_to_backup.append(f)
    for f in glob.glob(os.path.join(DATA_DIR, "output_*.txt")):
        files_to_backup.append(f)

    backed_up = 0
    for filepath in files_to_backup:
        if os.path.exists(filepath):
            bak_path = filepath + ".bak"
            # Don't overwrite an existing .bak (safety)
            if os.path.exists(bak_path):
                counter = 1
                while os.path.exists(f"{filepath}.bak{counter}"):
                    counter += 1
                bak_path = f"{filepath}.bak{counter}"
            try:
                os.rename(filepath, bak_path)
                backed_up += 1
                log.debug(f"  Backed up: {filepath} → {bak_path}")
            except Exception as exc:
                stats.warnings.append(
                    f"Could not rename {filepath}: {exc}")

    log.info(f"  → {backed_up} files renamed to .bak")


# ===================================================================
#  MAIN MIGRATION ENTRY POINT
# ===================================================================

def run_migration(progress_callback=None) -> Tuple[bool, str]:
    """
    Run the full migration from JSON files to SQLite.

    Args:
        progress_callback: Optional callable(stage_name, percent)
                           for UI progress updates.

    Returns:
        (success: bool, summary: str)
    """
    stats = MigrationStats()

    def progress(stage: str, pct: int):
        log.info(f"[{pct:3d}%] {stage}")
        if progress_callback:
            try:
                progress_callback(stage, pct)
            except Exception:
                pass

    # ---- Pre-flight checks ----
    progress("Initialising database...", 0)

    try:
        db.init_database()
    except Exception as exc:
        msg = f"Failed to initialise database: {exc}"
        log.error(msg)
        return False, msg

    if db.db_is_migrated():
        msg = ("Migration has already been completed. "
               "The database is ready to use.")
        log.info(msg)
        return True, msg

    # ---- Run all stages inside a single transaction ----
    conn = db.get_connection()

    try:
        # Begin explicit transaction
        conn.execute("BEGIN IMMEDIATE")

        progress("Migrating documents...", 5)
        migrate_documents(conn, stats)

        progress("Migrating document entries...", 15)
        migrate_entries(conn, stats)

        progress("Migrating conversations...", 30)
        migrate_conversations(conn, stats)

        progress("Migrating processed outputs...", 40)
        migrate_processed_outputs(conn, stats)

        progress("Migrating prompts...", 50)
        prompt_name_to_id = migrate_prompts(conn, stats)

        progress("Migrating document folder tree...", 60)
        migrate_document_tree(conn, stats)

        progress("Migrating prompt folder tree...", 70)
        migrate_prompt_tree(conn, prompt_name_to_id, stats)

        progress("Migrating cost log...", 80)
        migrate_cost_log(conn, stats)

        progress("Migrating embeddings...", 90)
        migrate_embeddings(conn, stats)

        # ---- Commit everything ----
        conn.execute("COMMIT")
        log.info("Transaction committed successfully.")

    except Exception as exc:
        # Something went wrong — roll back everything
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        msg = (f"Migration FAILED — rolled back.\n"
               f"Error: {exc}\n\n{traceback.format_exc()}")
        log.error(msg)
        return False, msg

    # ---- Post-commit: set the migrated flag ----
    progress("Setting migration flag...", 95)
    try:
        db.db_set_migrated()
    except Exception as exc:
        stats.warnings.append(f"Could not set migrated flag: {exc}")

    # ---- Rename old files to .bak ----
    progress("Backing up old files...", 97)
    backup_old_files(stats)

    progress("Migration complete!", 100)
    summary = stats.summary()
    log.info(summary)
    return True, summary


# ===================================================================
#  STANDALONE EXECUTION (for testing)
# ===================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("  DocAnalyser — JSON → SQLite Migration Tool")
    print("=" * 60)
    print(f"\n  Data directory:  {DATA_DIR}")
    print(f"  Database target: {db.DB_PATH}")
    print(f"  Library file:    {LIBRARY_PATH}")
    print(f"  Prompts file:    {PROMPTS_PATH}")
    print(f"  Cost log:        {COST_LOG_PATH}")
    print(f"  Embeddings:      {EMBEDDINGS_PATH}")
    print(f"  Doc tree:        {LIBRARY_TREE_PATH}")
    print()

    # Check what files exist
    exists = []
    missing = []
    for label, path in [
        ("document_library.json", LIBRARY_PATH),
        ("prompts.json", PROMPTS_PATH),
        ("cost_log.txt", COST_LOG_PATH),
        ("embeddings.json", EMBEDDINGS_PATH),
        ("document_library_tree.json", LIBRARY_TREE_PATH),
    ]:
        if os.path.exists(path):
            exists.append(label)
        else:
            missing.append(label)

    entry_files = glob.glob(os.path.join(DATA_DIR, "doc_*_entries.json"))
    output_files = glob.glob(os.path.join(DATA_DIR, "output_*.txt"))

    print(f"  Files found:   {', '.join(exists) or '(none)'}")
    if missing:
        print(f"  Files missing: {', '.join(missing)}")
    print(f"  Entry files:   {len(entry_files)}")
    print(f"  Output files:  {len(output_files)}")
    print()

    if not exists and not entry_files:
        print("  Nothing to migrate — no data files found.")
        sys.exit(0)

    answer = input("  Proceed with migration? [y/N] ").strip().lower()
    if answer != "y":
        print("  Aborted.")
        sys.exit(0)

    print()
    success, summary = run_migration()
    print(summary)

    if success:
        print("\n  ✅ Migration completed successfully.")
        print(f"  📝 Detailed log: {_log_path}")
    else:
        print("\n  ❌ Migration failed. Your original files are untouched.")
        print(f"  📝 Check the log: {_log_path}")

    sys.exit(0 if success else 1)
