# DocAnalyser SQLite Schema Design

## Overview

This document describes the proposed SQLite database schema for DocAnalyser, replacing the current collection of JSON files and the cost_log.txt with a single `docanalyser.db` file. The design supports the existing functionality (documents, prompts, conversations, cost tracking, embeddings) and adds workspaces, methodology templates, and UI string externalisation.

The database layer will be implemented as a standalone Python module (`db_manager.py`) with no UI dependencies, so it can be used with Tkinter today and any future framework tomorrow.

---

## Current State → New State

| Current File(s) | New Table(s) | Notes |
|---|---|---|
| document_library.json | `documents` | One row per document |
| doc_{id}_entries.json (per document) | `document_entries` | Entries stored as rows, not separate files |
| document_library_tree.json | `folders`, `folder_items` | Tree structure for document library |
| conversation_thread (embedded in library) | `conversations`, `messages` | Threads become proper tables |
| prompts.json (with tree structure) | `prompts`, `prompt_versions` | Prompts and version history |
| prompts tree structure (embedded in prompts.json) | `folders`, `folder_items` | Shared folder system with documents |
| cost_log.txt | `cost_log` | Structured, queryable |
| embeddings.json | `embeddings` | One row per chunk |
| help_texts.json | `ui_strings` | Help texts + dialog messages |
| *(new)* | `workspaces`, `workspace_folders`, `workspace_items` | Workspace/methodology system |
| *(new)* | `methodology_stages`, `stage_guidance` | Methodology template support |

---

## Table Definitions

### 1. documents

Replaces: `document_library.json` → `documents` array

```sql
CREATE TABLE documents (
    id              TEXT PRIMARY KEY,        -- e.g. "a1b2c3d4e5f6" (existing MD5 hash IDs)
    title           TEXT NOT NULL,
    doc_type        TEXT NOT NULL,           -- 'youtube', 'pdf', 'web_content', 'audio_transcription', etc.
    document_class  TEXT NOT NULL DEFAULT 'source',  -- 'source', 'response', 'product', 'processed_output'
    source          TEXT,                    -- file path, URL, etc.
    created_at      TEXT NOT NULL,           -- ISO datetime
    updated_at      TEXT,                    -- ISO datetime, set on any modification
    entry_count     INTEGER DEFAULT 0,
    metadata        TEXT,                    -- JSON blob for flexible metadata (editable flag, published_date, etc.)
    
    -- Parent linkage for response/branch documents
    parent_doc_id   TEXT,                    -- links response docs to their source document
    
    -- Flags
    is_deleted      INTEGER DEFAULT 0        -- soft delete (0=active, 1=deleted)
);

CREATE INDEX idx_documents_type ON documents(doc_type);
CREATE INDEX idx_documents_class ON documents(document_class);
CREATE INDEX idx_documents_parent ON documents(parent_doc_id);
CREATE INDEX idx_documents_created ON documents(created_at);
```

**Design notes:**
- `metadata` is a JSON text column for the grab-bag of optional fields (editable, pre_created, manually_created, published_date, original_document_id, etc.). This avoids having dozens of rarely-used columns while still allowing SQL queries via `json_extract()` when needed.
- `parent_doc_id` replaces the current pattern of storing `original_document_id` / `parent_document_id` inside the metadata dict. This makes branch queries fast and indexable.
- Soft delete means "undo" is possible and the deletion bug class is eliminated — deleting a document sets a flag rather than removing data.


### 2. document_entries

Replaces: `doc_{id}_entries.json` files (one per document)

```sql
CREATE TABLE document_entries (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id          TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    position        INTEGER NOT NULL,        -- ordering within the document
    content         TEXT NOT NULL,            -- the actual text content
    entry_type      TEXT DEFAULT 'text',      -- 'text', 'heading', 'caption', etc.
    metadata        TEXT,                     -- JSON blob for entry-specific metadata
    
    UNIQUE(doc_id, position)
);

CREATE INDEX idx_entries_doc ON document_entries(doc_id);
```

**Design notes:**
- Replaces hundreds of individual JSON files with indexed rows.
- `ON DELETE CASCADE` means deleting a document automatically deletes its entries.
- Full-text search can be added later via SQLite's FTS5 extension on the `content` column.


### 3. conversations

Replaces: `conversation_thread` and `thread_metadata` embedded in document_library.json

```sql
CREATE TABLE conversations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id          TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    created_at      TEXT NOT NULL,
    updated_at      TEXT,
    message_count   INTEGER DEFAULT 0,
    metadata        TEXT                     -- JSON blob for thread-level metadata
);

CREATE INDEX idx_conversations_doc ON conversations(doc_id);
```


### 4. messages

Replaces: the `conversation_thread` list of message dicts

```sql
CREATE TABLE messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    position        INTEGER NOT NULL,        -- ordering within conversation
    role            TEXT NOT NULL,            -- 'user' or 'assistant'
    content         TEXT NOT NULL,
    timestamp       TEXT,                     -- ISO datetime
    provider        TEXT,                     -- 'OpenAI', 'Anthropic', 'DeepSeek', etc.
    model           TEXT,                     -- 'gpt-5.2', 'claude-4-sonnet', etc.
    metadata        TEXT,                     -- JSON blob for any extra per-message data
    
    UNIQUE(conversation_id, position)
);

CREATE INDEX idx_messages_conversation ON messages(conversation_id);
```


### 5. processed_outputs

Replaces: `processed_outputs` list embedded in document_library.json + `output_{id}.txt` files

```sql
CREATE TABLE processed_outputs (
    id              TEXT PRIMARY KEY,         -- existing MD5 hash IDs
    doc_id          TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    created_at      TEXT NOT NULL,
    prompt_name     TEXT,
    prompt_text     TEXT,
    provider        TEXT,
    model           TEXT,
    output_text     TEXT NOT NULL,            -- full output (no more separate .txt files)
    preview         TEXT,                     -- first ~200 chars
    notes           TEXT
);

CREATE INDEX idx_outputs_doc ON processed_outputs(doc_id);
```


### 6. prompts

Replaces: prompt items in `prompts.json`

```sql
CREATE TABLE prompts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    is_system       INTEGER DEFAULT 0,       -- 1 = shipped with app, 0 = user-created
    is_favorite     INTEGER DEFAULT 0,
    last_used       TEXT,                     -- ISO datetime
    max_versions    INTEGER DEFAULT 10,
    created_at      TEXT NOT NULL,
    updated_at      TEXT
);

CREATE INDEX idx_prompts_name ON prompts(name);
CREATE INDEX idx_prompts_favorite ON prompts(is_favorite);
```


### 7. prompt_versions

Replaces: `versions` array inside each prompt item

```sql
CREATE TABLE prompt_versions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt_id       INTEGER NOT NULL REFERENCES prompts(id) ON DELETE CASCADE,
    version_num     INTEGER NOT NULL,         -- 0-based, matches current indexing
    text            TEXT NOT NULL,
    note            TEXT DEFAULT '',
    is_default      INTEGER DEFAULT 0,        -- 1 = this is the factory default text
    is_current      INTEGER DEFAULT 0,        -- 1 = currently selected version
    created_at      TEXT NOT NULL,
    
    UNIQUE(prompt_id, version_num)
);

CREATE INDEX idx_versions_prompt ON prompt_versions(prompt_id);
```


### 8. folders

Shared folder system used by both document library and prompt library, and by workspaces.

Replaces: `document_library_tree.json` tree structure and `prompts.json` tree structure

```sql
CREATE TABLE folders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    parent_id       INTEGER REFERENCES folders(id) ON DELETE CASCADE,  -- NULL = root folder
    library_type    TEXT NOT NULL,            -- 'documents', 'prompts', or 'workspace'
    workspace_id    INTEGER REFERENCES workspaces(id) ON DELETE CASCADE,  -- NULL for global library folders
    position        INTEGER DEFAULT 0,       -- ordering among siblings
    is_expanded     INTEGER DEFAULT 1,       -- remember UI expand/collapse state
    created_at      TEXT NOT NULL
);

CREATE INDEX idx_folders_parent ON folders(parent_id);
CREATE INDEX idx_folders_library ON folders(library_type);
CREATE INDEX idx_folders_workspace ON folders(workspace_id);
```

**Design notes:**
- A single `folders` table serves all tree structures. `library_type` distinguishes document folders from prompt folders from workspace-internal folders.
- `workspace_id` is NULL for the global library folders (the ones you see when "All Items" is selected). When a workspace is active, its folders have a non-NULL `workspace_id`.
- Depth is implicit from the parent chain. The existing 4-level limit can be enforced in application code.


### 9. folder_items

Junction table linking items (documents or prompts) to folders.

Replaces: the children dict in FolderNode

```sql
CREATE TABLE folder_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    folder_id       INTEGER NOT NULL REFERENCES folders(id) ON DELETE CASCADE,
    item_type       TEXT NOT NULL,            -- 'document' or 'prompt'
    document_id     TEXT REFERENCES documents(id) ON DELETE CASCADE,
    prompt_id       INTEGER REFERENCES prompts(id) ON DELETE CASCADE,
    position        INTEGER DEFAULT 0,       -- ordering within folder
    
    -- Exactly one of document_id or prompt_id must be set
    CHECK ((document_id IS NOT NULL AND prompt_id IS NULL) OR 
           (document_id IS NULL AND prompt_id IS NOT NULL))
);

CREATE INDEX idx_folder_items_folder ON folder_items(folder_id);
CREATE INDEX idx_folder_items_document ON folder_items(document_id);
CREATE INDEX idx_folder_items_prompt ON folder_items(prompt_id);
```

**Design notes:**
- The same prompt can appear in multiple folders (global library folder AND workspace folders) without duplication — each placement is a separate row.
- Deleting a folder cascades to delete its folder_items rows (the placements), but the underlying prompt/document is untouched.


### 10. workspaces

New table. Supports task-oriented prompt collections and topic-oriented document collections.

```sql
CREATE TABLE workspaces (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    description     TEXT,
    workspace_type  TEXT NOT NULL,            -- 'prompts' or 'documents' (or 'both' in future)
    icon            TEXT DEFAULT '📋',
    is_active       INTEGER DEFAULT 0,       -- 1 = currently selected workspace
    created_at      TEXT NOT NULL,
    updated_at      TEXT,
    
    -- Methodology template fields
    is_methodology  INTEGER DEFAULT 0,       -- 1 = this workspace is a structured methodology
    methodology_description TEXT,             -- overview of the methodology
    author          TEXT,                     -- who created this methodology
    version         TEXT                      -- version string for sharing/export
);

CREATE INDEX idx_workspaces_type ON workspaces(workspace_type);
CREATE INDEX idx_workspaces_active ON workspaces(is_active);
```


### 11. workspace_items

Junction table linking items to workspaces (independent of folder placement). This enables queries like "give me everything in the Oral History workspace" without traversing the folder tree.

```sql
CREATE TABLE workspace_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id    INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    item_type       TEXT NOT NULL,            -- 'document' or 'prompt'
    document_id     TEXT REFERENCES documents(id) ON DELETE CASCADE,
    prompt_id       INTEGER REFERENCES prompts(id) ON DELETE CASCADE,
    added_at        TEXT NOT NULL,
    
    CHECK ((document_id IS NOT NULL AND prompt_id IS NULL) OR 
           (document_id IS NULL AND prompt_id IS NOT NULL)),
    UNIQUE(workspace_id, document_id),
    UNIQUE(workspace_id, prompt_id)
);

CREATE INDEX idx_workspace_items_workspace ON workspace_items(workspace_id);
```

**Design notes:**
- This is a flat membership list ("prompt X belongs to workspace Y"). The *folder placement* within the workspace is handled by `folder_items` pointing to workspace-specific folders.
- The UNIQUE constraints prevent accidentally adding the same item to a workspace twice.


### 12. methodology_stages

New table. For workspaces that are structured methodologies, this defines the stages.

```sql
CREATE TABLE methodology_stages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id    INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    stage_number    INTEGER NOT NULL,         -- ordering (1, 2, 3, ...)
    name            TEXT NOT NULL,            -- e.g. "Preparation", "Post-Interview Processing"
    description     TEXT,                     -- what this stage involves
    ai_guidance     TEXT,                     -- where AI helps and where it doesn't
    folder_id       INTEGER REFERENCES folders(id),  -- links to the folder containing this stage's prompts
    
    UNIQUE(workspace_id, stage_number)
);

CREATE INDEX idx_stages_workspace ON methodology_stages(workspace_id);
```

**Design notes:**
- Each stage can link to a folder in the workspace's tree, so the tree structure mirrors the methodology stages.
- `ai_guidance` is the text your brother-in-law might write: "AI is useful here for background research, but the interviewer should always review and personalise the questions."
- Stages are optional — a workspace doesn't have to be a methodology. Regular workspaces just have folders and items without stages.


### 13. cost_log

Replaces: `cost_log.txt`

```sql
CREATE TABLE cost_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL,            -- ISO datetime
    provider        TEXT NOT NULL,
    model           TEXT NOT NULL,
    cost            REAL NOT NULL,            -- dollar amount
    doc_title       TEXT,                     -- which document was being processed
    prompt_summary  TEXT,                     -- brief description of what was run
    doc_id          TEXT REFERENCES documents(id) ON DELETE SET NULL,
    workspace_id    INTEGER REFERENCES workspaces(id) ON DELETE SET NULL
);

CREATE INDEX idx_cost_log_timestamp ON cost_log(timestamp);
CREATE INDEX idx_cost_log_provider ON cost_log(provider);
CREATE INDEX idx_cost_log_doc ON cost_log(doc_id);
```

**Design notes:**
- `ON DELETE SET NULL` means if a document is deleted, the cost record survives (you still want to know how much you spent).
- `workspace_id` records which workspace was active when the cost was incurred, enabling per-project cost reporting.
- Queries like "total spend on DeepSeek this month" become trivial SQL.


### 14. embeddings

Replaces: `embeddings.json`

```sql
CREATE TABLE embeddings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id          TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index     INTEGER NOT NULL,
    text_preview    TEXT,                     -- first ~500 chars of chunk
    embedding       BLOB NOT NULL,            -- binary float array (much smaller than JSON)
    start_char      INTEGER DEFAULT 0,
    end_char        INTEGER DEFAULT 0,
    word_count      INTEGER DEFAULT 0,
    generated_at    TEXT NOT NULL,
    cost            REAL DEFAULT 0.0,
    provider        TEXT DEFAULT 'openai',
    model           TEXT DEFAULT 'text-embedding-3-small',
    
    UNIQUE(doc_id, chunk_index)
);

CREATE INDEX idx_embeddings_doc ON embeddings(doc_id);
```

**Design notes:**
- Storing embeddings as BLOB (binary) rather than JSON text reduces file size by roughly 60% for float arrays.
- `ON DELETE CASCADE` means deleting a document automatically cleans up its embeddings.


### 15. ui_strings

New table. Externalises dialog messages and help texts.

```sql
CREATE TABLE ui_strings (
    key             TEXT PRIMARY KEY,         -- e.g. 'confirm_delete', 'load_button_help'
    category        TEXT NOT NULL,            -- 'dialog', 'help', 'tooltip', 'status'
    title           TEXT,                     -- dialog title or help popup title
    message         TEXT NOT NULL,            -- the main text content
    tips            TEXT,                     -- JSON array of tip strings (for help texts)
    placeholders    TEXT,                     -- JSON list of placeholder names, e.g. '["item_name", "count"]'
    updated_at      TEXT
);

CREATE INDEX idx_ui_strings_category ON ui_strings(category);
```

**Design notes:**
- `placeholders` documents what variables the message expects, e.g. `confirm_delete` expects `{item_name}`. The code calls `ui_string("confirm_delete", item_name="My Document")` and the function does the substitution.
- This table serves both the current `help_texts.json` content and the hardcoded messagebox strings.
- Updating a message is a single SQL update, no code changes needed.
- Foundation for future internationalisation (add a `locale` column).

---

## Relationships Diagram

```
workspaces
    ├── workspace_items ──→ documents / prompts      (flat membership)
    ├── methodology_stages                            (ordered stages with guidance)
    └── folders (workspace_id = this workspace)
            └── folder_items ──→ documents / prompts  (positioned in tree)

documents
    ├── document_entries        (text content, ordered)
    ├── conversations
    │       └── messages        (ordered chat messages)
    ├── processed_outputs       (AI analysis results)
    ├── embeddings              (semantic search vectors)
    ├── cost_log                (spending records)
    └── parent_doc_id ──→ documents  (branch linkage)

prompts
    └── prompt_versions         (version history)

folders (library_type = 'documents' or 'prompts', workspace_id = NULL)
    └── folder_items ──→ documents / prompts  (global library tree)

ui_strings                      (standalone, no relationships)
```

---

## Migration Strategy

The migration module (`db_migration.py`) will:

1. Create the database and all tables if they don't exist.
2. Read each existing JSON file and populate the corresponding tables.
3. Verify row counts match expected counts.
4. Rename the old JSON files to `.json.bak` (not delete — safety net).
5. Set a flag in the database (`meta` table or pragma) indicating migration is complete.

The migration runs once on first startup after the update. If it fails partway through, the `.json` files are still intact and the app can fall back to JSON mode.

**Migration order:**
1. `documents` (from document_library.json)
2. `document_entries` (from doc_{id}_entries.json files)
3. `conversations` + `messages` (from conversation_thread in library)
4. `processed_outputs` (from processed_outputs in library + output_{id}.txt files)
5. `prompts` + `prompt_versions` (from prompts.json)
6. `folders` + `folder_items` (from document_library_tree.json and prompts.json tree structures)
7. `cost_log` (from cost_log.txt)
8. `embeddings` (from embeddings.json)
9. `ui_strings` (from help_texts.json + seeded dialog messages)

---

## API Surface (db_manager.py)

The database module will expose functions grouped by domain. No SQL in calling code — all queries are encapsulated.

### Documents
- `get_document(doc_id)` → dict
- `get_all_documents(include_deleted=False)` → list of dicts
- `add_document(doc_type, source, title, entries, metadata, document_class)` → doc_id
- `update_document(doc_id, **fields)` → bool
- `delete_document(doc_id, hard=False)` → bool (soft delete by default)
- `get_branches_for_source(source_doc_id)` → list of dicts
- `search_documents(query)` → list of dicts

### Document Entries
- `get_entries(doc_id)` → list of dicts
- `save_entries(doc_id, entries)` → bool

### Conversations
- `get_conversation(doc_id)` → dict with messages
- `save_conversation(doc_id, messages, metadata)` → bool
- `add_message(doc_id, role, content, provider, model)` → message_id

### Prompts
- `get_prompt(prompt_id)` → dict with current version text
- `get_all_prompts()` → list of dicts
- `add_prompt(name, text, is_system)` → prompt_id
- `update_prompt(prompt_id, **fields)` → bool
- `delete_prompt(prompt_id)` → bool
- `save_prompt_version(prompt_id, text, note)` → version_id
- `get_prompt_versions(prompt_id)` → list of dicts
- `search_prompts(query)` → list of dicts

### Folders & Tree Structure
- `get_folder_tree(library_type, workspace_id=None)` → nested dict (reconstructed tree)
- `create_folder(name, parent_id, library_type, workspace_id)` → folder_id
- `rename_folder(folder_id, new_name)` → bool
- `delete_folder(folder_id)` → bool (cascades to folder_items)
- `move_folder(folder_id, new_parent_id, new_position)` → bool
- `add_item_to_folder(folder_id, item_type, item_id, position)` → bool
- `remove_item_from_folder(folder_id, item_type, item_id)` → bool
- `move_item_in_folder(folder_id, item_type, item_id, new_position)` → bool

### Workspaces
- `get_all_workspaces(workspace_type=None)` → list of dicts
- `get_active_workspace(workspace_type)` → dict or None
- `create_workspace(name, description, workspace_type)` → workspace_id
- `set_active_workspace(workspace_id)` → bool
- `clear_active_workspace(workspace_type)` → bool (back to "All Items")
- `add_item_to_workspace(workspace_id, item_type, item_id)` → bool
- `remove_item_from_workspace(workspace_id, item_type, item_id)` → bool
- `get_workspace_items(workspace_id, item_type)` → list of dicts
- `export_workspace(workspace_id)` → dict (complete workspace for sharing)
- `import_workspace(data)` → workspace_id

### Methodology
- `get_methodology_stages(workspace_id)` → list of dicts
- `add_stage(workspace_id, name, description, ai_guidance, stage_number)` → stage_id
- `update_stage(stage_id, **fields)` → bool
- `delete_stage(stage_id)` → bool

### Cost Tracking
- `log_cost(provider, model, cost, doc_title, prompt_summary, doc_id, workspace_id)` → entry_id
- `get_costs(since=None, provider=None, workspace_id=None)` → list of dicts
- `get_cost_summary(period='30d', group_by='provider')` → dict

### Embeddings
- `save_embeddings(doc_id, chunks, embeddings, cost, provider, model)` → bool
- `get_embeddings(doc_id)` → list of dicts
- `has_embeddings(doc_id)` → bool
- `delete_embeddings(doc_id)` → bool
- `get_all_embeddings_flat()` → list of dicts

### UI Strings
- `get_ui_string(key, **kwargs)` → (title, message) tuple with substitutions
- `get_help_text(key)` → dict with title, description, tips
- `update_ui_string(key, **fields)` → bool

---

## Key Design Principles

1. **One database file.** Everything lives in `docanalyser.db` in the existing data directory. One file to back up, one file to copy.

2. **Soft delete for documents.** Setting `is_deleted=1` rather than removing rows. This eliminates the class of bug where tree nodes and database records get out of sync. Undelete becomes possible.

3. **Items exist once, appear in many places.** A prompt is one row in `prompts`. Its appearance in the global library tree, in the Oral History workspace, and in the Journalism workspace are three rows in `folder_items` pointing to three different folders. No duplication of the actual prompt data.

4. **Cascading deletes for dependent data.** Deleting a document automatically cleans up its entries, conversations, messages, embeddings, and processed outputs. No orphaned files.

5. **JSON metadata columns for flexibility.** Fields that vary across documents or are rarely queried live in a JSON `metadata` column. Fields that are commonly queried or filtered on get their own columns.

6. **Framework independence.** The `db_manager.py` module imports nothing from Tkinter. It returns plain Python dicts and lists. The UI layer converts these to whatever widget format it needs.

7. **Backward compatibility during transition.** The migration preserves all existing document IDs, so any external references (bookmarks, notes) remain valid.
