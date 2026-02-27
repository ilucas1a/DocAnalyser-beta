# DocAnalyser SQLite Migration — Phase 1 Implementation Plan

**Date:** 27 February 2026
**Version:** 1.0
**Approach:** Facade pattern (existing function signatures preserved)
**Scope:** Core migration of documents, prompts, entries, conversations, cost log, and embeddings from JSON to SQLite. Includes prompt import/export.

---

## Prerequisites

Before any implementation begins:

1. **Complete the TurboScribe testing** you have outstanding.
2. **Compile the beta release** (InnoSetup) to create a known-good baseline. This becomes your "if everything goes wrong, reinstall this" safety net.
3. **Back up your data directory** (`%APPDATA%\DocAnalyser_Beta\`) — copy the whole folder somewhere safe. This contains your `document_library.json`, `prompts.json`, `cost_log.txt`, `embeddings.json`, all `doc_*_entries.json` files, and the `summaries` folder.

Once those three are done, you're safe to start.

---

## Architecture Overview

The facade approach means the migration happens in layers, and each layer can be tested independently before the next one is connected.

```
BEFORE (current):
  Main.py / mixins / tree managers
       │
       ▼
  document_library.py ──→ document_library.json, doc_*_entries.json
  prompt_tree_manager.py ──→ prompts.json
  cost_tracker.py ──→ cost_log.txt
  (embeddings code) ──→ embeddings.json

AFTER (Phase 1 complete):
  Main.py / mixins / tree managers    ← NO CHANGES to these files
       │
       ▼
  document_library.py  ──→ db_manager.py ──→ docanalyser.db
  prompt_tree_manager.py ──→ db_manager.py ──→ docanalyser.db
  cost_tracker.py ──→ db_manager.py ──→ docanalyser.db
  (embeddings code) ──→ db_manager.py ──→ docanalyser.db
```

The key point: `document_library.py` keeps all its existing function names (`load_library()`, `add_document_to_library()`, `get_document_by_id()`, etc.). Internally, instead of reading/writing JSON, those functions now call `db_manager.py`. Every other file in the project that imports from `document_library` continues to work without modification.

---

## New Files

| File | Purpose | Approximate size |
|------|---------|-----------------|
| `db_manager.py` | SQLite database layer — all SQL lives here, no UI code | ~800-1000 lines |
| `db_migration.py` | One-time JSON → SQLite migration, runs on first launch | ~300-400 lines |
| `prompt_import_export.py` | Prompt import/export dialog and file handling | ~250-350 lines |

---

## Build Order

### Step 1: Create `db_manager.py` (the database layer)

This is the foundation. It creates the database, defines all tables, and provides clean Python functions for every operation. It imports nothing from Tkinter and nothing from the existing codebase except `config.py` (for the data directory path).

**What it contains:**

- `init_database()` — creates `docanalyser.db` and all tables if they don't exist
- `get_connection()` — returns a database connection (with WAL mode for safety)

Then, grouped by domain, all the CRUD functions from the schema document's API Surface section. The important ones for Phase 1 are:

**Documents:** `db_get_document()`, `db_get_all_documents()`, `db_add_document()`, `db_update_document()`, `db_delete_document()`, `db_search_documents()`

**Document Entries:** `db_get_entries()`, `db_save_entries()`

**Conversations & Messages:** `db_get_conversation()`, `db_save_conversation()`, `db_add_message()`

**Processed Outputs:** `db_add_processed_output()`, `db_get_processed_outputs()`, `db_load_processed_output()`, `db_delete_processed_output()`

**Prompts:** `db_get_prompt()`, `db_get_all_prompts()`, `db_add_prompt()`, `db_update_prompt()`, `db_delete_prompt()`, `db_save_prompt_version()`, `db_get_prompt_versions()`

**Folders & Tree:** `db_get_folder_tree()`, `db_create_folder()`, `db_rename_folder()`, `db_delete_folder()`, `db_move_folder()`, `db_add_item_to_folder()`, `db_remove_item_from_folder()`, `db_move_item_in_folder()`

**Cost Log:** `db_log_cost()`, `db_get_costs()`, `db_get_cost_summary()`

**Embeddings:** `db_save_embeddings()`, `db_get_embeddings()`, `db_has_embeddings()`, `db_delete_embeddings()`

All functions are prefixed with `db_` to make it obvious which layer they belong to. They accept and return plain Python dicts and lists — no SQLite-specific objects leak out.

**Testing:** This file can be tested completely standalone. We'll write a small test script that creates a temporary database, adds documents, retrieves them, etc. If this works, the foundation is solid.

**Estimated effort:** This is the largest single piece of work. With me writing the code and you testing, probably 2-3 sessions.

---

### Step 2: Create `db_migration.py` (JSON → SQLite migration)

This runs once, on the first launch after the update. It:

1. Checks whether `docanalyser.db` already exists and has data. If yes, skips migration.
2. Reads `document_library.json` and inserts each document into the `documents` table.
3. For each document, reads the corresponding `doc_{id}_entries.json` file and inserts rows into `document_entries`.
4. Extracts `conversation_thread` and `thread_metadata` from each document's library entry and inserts into `conversations` and `messages`.
5. Extracts `processed_outputs` and inserts into the `processed_outputs` table, reading the full output text from `output_{id}.txt` files.
6. Reads `prompts.json` and inserts into `prompts` and `prompt_versions`. Handles both the v2.0 tree format and legacy flat format.
7. Rebuilds the folder trees from `document_library_tree.json` and the prompts tree structure, inserting into `folders` and `folder_items`.
8. Parses `cost_log.txt` line by line and inserts into `cost_log`.
9. Reads `embeddings.json` and inserts into `embeddings` (converting the float arrays to binary BLOBs).
10. Verifies row counts match expected counts.
11. Renames old JSON files to `.json.migrated` (not deleted — safety net).
12. Writes a migration-complete flag into the database.

**Important design decision:** The migration is all-or-nothing within a single SQLite transaction. If any step fails, the whole thing rolls back, the JSON files are untouched, and the app falls back to JSON mode. You'll see an error message telling you what went wrong.

**Testing:** We test this with a copy of your actual data. Before running it for real, we'll copy your `%APPDATA%\DocAnalyser_Beta\` folder to a test location and point the migration at that.

**Estimated effort:** 1-2 sessions.

---

### Step 3: Rewire `document_library.py` (the facade)

This is where the switchover happens. We rewrite the internals of `document_library.py` so that every existing function calls through to `db_manager.py` instead of reading/writing JSON.

For example, the current `load_library()` reads `document_library.json` into memory and returns a list of dicts. The new version calls `db_get_all_documents()` and returns the result in the same format. The function signature doesn't change. The return type doesn't change. Callers don't notice.

The key functions to rewire:

| Current function | What changes |
|-----------------|-------------|
| `load_library()` | Calls `db_get_all_documents()` instead of reading JSON |
| `save_library(library)` | Becomes a no-op or bulk update (individual saves are atomic now) |
| `add_document_to_library(...)` | Calls `db_add_document()` |
| `get_document_by_id(doc_id)` | Calls `db_get_document()` |
| `delete_document(doc_id)` | Calls `db_delete_document()` |
| `load_document_entries(doc_id)` | Calls `db_get_entries()` |
| `add_processed_output_to_document(...)` | Calls `db_add_processed_output()` |
| `save_thread_to_document(...)` | Calls `db_save_conversation()` |
| `load_thread_from_document(doc_id)` | Calls `db_get_conversation()` |
| `perform_semantic_search(...)` | Calls `db_get_embeddings()` then runs similarity |

The tricky part here is `save_library()`. Currently, several places in the code load the entire library, modify it, and save it back. With SQLite, individual operations are atomic — you don't need to load/modify/save the whole thing. So `save_library()` becomes either a no-op (if the individual operations already saved) or a batch sync. We'll handle this case by case.

**What doesn't change:** Every file that does `from document_library import load_library, add_document_to_library` continues to work. Main.py, document_tree_manager.py, thread_viewer.py, smart_load.py, the mixins — none of them need editing.

**Testing:** Run the app normally. Load a document. Check the library. Run a prompt. Check that processed outputs appear. Load from library. Everything should behave identically.

**Estimated effort:** 1-2 sessions.

---

### Step 4: Rewire prompt storage (facade for prompts)

Similar to Step 3, but for prompts. Currently `prompt_tree_manager.py` reads/writes `prompts.json` directly via its own `save_tree()` and load functions. We modify these internal functions to call `db_manager.py` instead.

The prompt tree manager's `PromptItem` and `PromptFolder` classes stay exactly as they are — they're in-memory data structures for the UI. What changes is how they're persisted:

- Loading the tree: instead of reading `prompts.json`, call `db_get_all_prompts()` and `db_get_folder_tree('prompts')` and reconstruct the in-memory tree from that.
- Saving the tree: instead of writing `prompts.json`, call the appropriate `db_` functions for each change.
- Version history: instead of storing versions in the JSON structure, call `db_save_prompt_version()` and `db_get_prompt_versions()`.

**Testing:** Open the Prompts Library. Check all prompts are present. Edit a prompt. Check version history. Create a folder, drag prompts into it. Close and reopen — everything should persist.

**Estimated effort:** 1 session.

---

### Step 5: Rewire cost tracking and embeddings

**Cost tracking:** `cost_tracker.py` currently appends to `cost_log.txt`. Change the append function to call `db_log_cost()`. Change the read/display functions to call `db_get_costs()`. The AI Costs dialog should work identically.

**Embeddings:** The embeddings code in `document_library.py` currently reads/writes `embeddings.json`. Rewire to call `db_save_embeddings()`, `db_get_embeddings()`, etc. The semantic search logic itself doesn't change — it still computes cosine similarity in Python — but the storage and retrieval go through SQLite.

**Testing:** Run a prompt and check the cost log. Generate embeddings for a document. Run semantic search. Verify results match what you'd expect.

**Estimated effort:** 1 session.

---

### Step 6: Startup integration

Wire the migration and database initialisation into the app startup sequence. In `Main.py` (or wherever the app initialisation happens), add early in the startup:

```python
from db_manager import init_database
from db_migration import migrate_if_needed

# Initialise database (creates tables if needed)
init_database()

# Migrate from JSON if this is the first run after update
migrate_if_needed()
```

This should run before any UI is created, before any data is loaded. If migration is needed, it happens silently. If the database already exists, these calls return almost instantly.

**Testing:** 
- First run after update: migration runs, JSON files renamed to `.json.migrated`, app opens with all data intact.
- Second run: migration skips, app opens normally.
- If you copy the `.json.migrated` files back to `.json` names and delete the database, migration runs again (useful for testing).

**Estimated effort:** Half a session.

---

### Step 7: Prompt import/export

With prompts now in SQLite, building import/export is straightforward.

**Export:**
1. User clicks "Export Prompts" (new button in the Prompts Library toolbar).
2. Dialog shows all prompts with checkboxes organised by folder.
3. User selects which prompts to export.
4. Saves as a `.json` file with a clear format: list of prompts with name, text, folder path, and version history.

**Import:**
1. User clicks "Import Prompts" (new button alongside Export).
2. File picker opens, filtered to `.json`.
3. Dialog shows the prompts from the file with checkboxes and a preview.
4. Options for handling duplicates: skip, rename (add number), or overwrite.
5. Selected prompts inserted into the database and the tree view refreshes.

**File format:**
```json
{
  "format": "docanalyser_prompts",
  "version": "1.0",
  "exported_at": "2026-03-01T10:30:00",
  "prompts": [
    {
      "name": "Detailed Summary",
      "folder": "General",
      "text": "Please provide a detailed summary...",
      "is_system": false,
      "is_favorite": true
    }
  ]
}
```

**Testing:** Export some prompts. Check the file is readable. Import into a fresh installation (or after clearing prompts). Verify prompts appear correctly.

**Estimated effort:** 1 session.

---

## Implementation Sequence Summary

| Step | What | New/Modified files | Depends on |
|------|------|-------------------|-----------|
| 0 | Compile beta + backup data | — | Nothing |
| 1 | Build `db_manager.py` | NEW: `db_manager.py` | Step 0 |
| 2 | Build `db_migration.py` | NEW: `db_migration.py` | Step 1 |
| 3 | Rewire `document_library.py` | MODIFY: `document_library.py` | Steps 1, 2 |
| 4 | Rewire prompt storage | MODIFY: `prompt_tree_manager.py` | Steps 1, 2 |
| 5 | Rewire costs + embeddings | MODIFY: `cost_tracker.py`, embeddings code | Step 1 |
| 6 | Startup integration | MODIFY: `Main.py` (minimal — ~5 lines) | Steps 1-5 |
| 7 | Prompt import/export | NEW: `prompt_import_export.py` | Step 4 |

---

## Testing Strategy

### Unit testing (per step)

Each step has its own test as described above. The key principle: test each layer independently before connecting it to the next.

For `db_manager.py`, we'll create a standalone test script (`test_db_manager.py`) that exercises every function against a temporary database. This catches SQL bugs before they can affect the live app.

For the migration, we test against a copy of your real data in a temporary directory. We verify row counts, spot-check specific documents, and confirm that the migrated data matches the originals.

### Integration testing (after all steps)

Once everything is wired up, run through these scenarios:

1. **Fresh start:** Delete the database. Launch the app. Migration runs. All data present.
2. **Normal use:** Load documents, run prompts, check library, check costs — everything works as before.
3. **Prompt operations:** Open Prompts Library, edit a prompt, save a version, create a folder, drag prompts, close/reopen.
4. **Thread continuity:** Load a document that has an existing conversation thread. Verify the thread is intact. Add a follow-up. Verify it saves.
5. **Processed outputs:** Run a prompt. Check that the output appears in the library under the source document.
6. **Export/import prompts:** Export a set, import into a clean setup, verify they work.
7. **Fallback test:** Rename `docanalyser.db` to something else. Restore the `.json.migrated` files to `.json`. Launch the app. It should re-migrate cleanly.

### Performance check

After migration, compare startup time and library browsing speed. With a typical library of 50-200 documents, you should notice little difference. With larger libraries, SQLite should be noticeably faster for searches and filtered views.

---

## Rollback Plan

At any point during development, if something goes wrong:

1. **Revert `document_library.py`** to the pre-migration version (from your compiled beta or Git).
2. **Restore JSON files** from the `.json.migrated` backups (just rename them back).
3. **Delete `docanalyser.db`** if it exists.
4. The app runs on JSON exactly as before.

This is why the facade approach is safe: the only file that changes significantly is `document_library.py`, and reverting one file restores the entire original behaviour.

---

## What Phase 1 Does NOT Include

These are explicitly deferred to Phase 2 and Phase 3:

- **Workspaces** (the `workspaces`, `workspace_items` tables) — Phase 2
- **Methodology stages** — Phase 2
- **UI strings externalisation** — Phase 2
- **Full document/workspace import/export** — Phase 3
- **FTS5 full-text search** — can be added later as a performance enhancement
- **Any UI changes** beyond the new Import/Export buttons in the Prompts Library

The goal of Phase 1 is a clean, invisible infrastructure swap: everything works the same, but the data is in a proper database.

---

## Session Planning

Given the build order and that we'll be working together in chat sessions, here's a realistic session plan:

**Session A:** Build `db_manager.py` — the core database layer. Test with standalone script.

**Session B:** Build `db_migration.py`. Test against a copy of your real data.

**Session C:** Rewire `document_library.py` (the big facade switch). Test the app end-to-end.

**Session D:** Rewire prompts, costs, embeddings. Startup integration. Full integration test.

**Session E:** Build prompt import/export. Final testing. Update the InnoSetup spec if needed.

Each session is one conversation. We might need a sixth session for bug fixes or edge cases, but five is the target.

---

*Document created: 27 February 2026*
*Based on schema design in `Documentation/docanalyser_sqlite_schema.md`*
*To be saved at: `Documentation/SQLite_Phase1_Implementation_Plan.md`*
