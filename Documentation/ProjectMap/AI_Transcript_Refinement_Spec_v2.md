# 12 - Database Layer (SQLite)

## Overview
Five modules implementing the SQLite persistence layer that replaces the original JSON file storage. All SQL lives in db_manager.py; adapter modules bridge between the existing tree managers and the database; backups_manager.py owns the document-backups domain. A one-time migration script handles the transition from JSON to SQLite. The accompanying backups UI lives in `backups_dialog.py` (see `05_UI_DIALOGS_CONVERSATION.md`).

---

## db_manager.py (~1,650 lines)
**Purpose:** Central SQLite database layer — all SQL lives here, no UI code.

**Database:** `%APPDATA%\DocAnalyser_Beta\docanalyser.db`

**Tables:**
- `documents` — document metadata (title, source, type, class, timestamps)
- `document_entries` — individual entries/segments per document
- `conversations` — conversation thread metadata
- `messages` — individual messages within conversations
- `processed_outputs` — AI processing results linked to documents
- `prompts` — prompt definitions with current text
- `prompt_versions` — version history per prompt
- `folders` — folder structure for both libraries (library_type: 'prompt' or 'document')
- `folder_items` — many-to-many mapping of items to folders
- `cost_log` — API usage cost tracking
- `embeddings` — semantic search embeddings
- `backups` — per-document content snapshots; columns: id, document_id (FK to documents, ON DELETE CASCADE), trigger_type, label, content_blob (JSON), created_at. Owned by backups_manager.py.

**Key Design Patterns:**
- Module-level connection (created once, reused)
- All public functions prefixed with `db_` for clarity
- Functions accept and return plain Python dicts and lists (no ORM)
- `workspace_id` columns pre-wired in folders and cost_log tables (for future Workspaces feature)

**Dependencies:** sqlite3, config (DATA_DIR)
**Called By:** prompt_db_adapter.py, document_db_adapter.py, db_migration.py, cost_tracker.py, backups_manager.py

---

## db_migration.py (~400 lines)
**Purpose:** One-time migration from JSON/TXT files to SQLite.

**Safety Features:**
- All writes in a single transaction — rolls back on any error
- Original files renamed to .bak (not deleted)
- Flag in database prevents re-running
- Non-destructive: JSON files preserved as backup

**Migration Sources:**
- `document_library.json` → documents, document_entries tables
- `prompts.json` → prompts, prompt_versions, folders (library_type='prompt') tables
- `cost_log.txt` → cost_log table
- `embeddings.json` → embeddings table
- `summaries/*.json` → document_entries, conversations, messages, processed_outputs tables
- Folder structures → folders, folder_items tables

**Dependencies:** db_manager, config
**Called By:** Main.py (on first startup after update)

---

## prompt_db_adapter.py (~350 lines)
**Purpose:** Bridges prompt_tree_manager.py (TreeManager/PromptItem/FolderNode) and db_manager.py.

**Feature Flag:** `USE_SQLITE_PROMPTS` — set True to activate; JSON file remains as fallback/backup.

**Key Functions:**
- `save_prompt_tree_to_sqlite(tree_manager)` — serialises entire prompt tree to SQLite
- `load_prompt_tree_from_sqlite()` → TreeManager or None — rebuilds tree from SQLite
- `load_flat_prompts_from_sqlite()` → list — flat list format for backwards compatibility

**Hooks in prompt_tree_manager.py:**
- `save_tree()` → `save_prompt_tree_to_sqlite()`
- `load_prompts_from_file()` → `load_flat_prompts_from_sqlite()`
- `open_prompt_tree_manager()` → `load_prompt_tree_from_sqlite()`

**Dependencies:** db_manager, tree_manager_base, prompt_tree_manager
**Called By:** prompt_tree_manager.py

---

## document_db_adapter.py (~250 lines)
**Purpose:** SQLite persistence for the Document Library folder tree.

**Feature Flag:** `USE_SQLITE_DOCUMENT_TREE` — set True to activate; JSON fallback preserved.

**Pattern:** Mirrors prompt_db_adapter.py but simpler — documents themselves are already stored in the documents table; this adapter only manages folder structure and folder-to-document assignments.

**Key Functions:**
- `save_document_tree_to_sqlite(tree_manager)` — serialises document folder tree
- `load_document_tree_from_sqlite()` → TreeManager or None — rebuilds tree from SQLite

**Dependencies:** db_manager, tree_manager_base, document_tree_manager
**Called By:** document_tree_manager.py

---

## backups_manager.py (~280 lines)
**Purpose:** Domain API for document backups (v1.7-alpha Day 7). Bridges between callers (cleanup-dialog auto-trigger sites, Source Document panel "Restore backup" button, `backups_dialog.py`) and the `backups`-table primitives in db_manager.

**Owned concerns:**
- **Payload schema** for the `content_blob` column: JSON-encoded `{"version": int, "entries": list, "metadata_subset": dict}`. Versioned so future shape changes can branch on the stored version. Callers pass plain Python dicts/lists; this module handles serialisation.
- **Retention policy:** 10 most-recent backups per document, pruned automatically after every `create_backup()`.
- **Counter-backup-on-restore:** `restore_backup()` always inserts a `pre_restore` snapshot of the current state before returning the target payload, so a misclick is itself recoverable.

**Trigger types (recognised constants, free-text at DB level):**
- `TRIGGER_CLEANUP_OPEN` — auto-fired by the cleanup-dialog callers in Main.py, library_interaction.py and document_fetching.py whenever the cleanup dialog opens against a saved doc.
- `TRIGGER_PRE_RESTORE` — auto-fired inside `restore_backup()` before the swap.
- `TRIGGER_MANUAL` — reserved for future "Create backup" buttons. Not yet wired.

**Public API:**
- `create_backup(document_id, trigger_type, entries, metadata_subset=None, label=None) -> int`
- `list_backups(document_id) -> List[dict]` — newest first; lightweight projection (no `content_blob`)
- `get_backup(backup_id) -> Optional[dict]` — full row with deserialised `payload`; raises `ValueError` on corrupted blob
- `restore_backup(backup_id, current_entries, current_metadata_subset=None) -> dict` — returns `{"restored_payload": ..., "counter_backup_id": ...}`
- `delete_backup(backup_id) -> bool`

**Constants:** `MAX_BACKUPS_PER_DOCUMENT = 10`, `PAYLOAD_VERSION = 1`

**Dependencies:** db_manager
**Called By:** Main.py, library_interaction.py, document_fetching.py (auto-trigger sites); backups_dialog.py and thread_viewer.py (UI)

---

## Migration Validation Scripts

Three developer-only scripts in the project root for verifying SQLite migration stages. Not part of the shipping application.

### test_stage_c.py
**Purpose:** Initialises the database, migrates prompts from JSON to SQLite, verifies round-trip integrity, and activates the `USE_SQLITE_PROMPTS` feature flag.
**Run:** `python test_stage_c.py` from DocAnalyzer_DEV directory.

### validate_stage_d.py
**Purpose:** Pre-flight check for enabling `USE_SQLITE_DOCUMENTS = True`. Verifies that all documents, entries, conversations, and processed outputs migrated correctly from JSON to SQLite.
**Run:** `python validate_stage_d.py` from DocAnalyzer_DEV directory.

### validate_stage_g.py
**Purpose:** Validates folder tree migration — checks that prompt and document folder structures in SQLite match the original JSON tree data.
**Run:** `python validate_stage_g.py` from DocAnalyzer_DEV directory.

**Dependencies:** db_manager, config
**Called By:** Developer manually during migration testing


---
