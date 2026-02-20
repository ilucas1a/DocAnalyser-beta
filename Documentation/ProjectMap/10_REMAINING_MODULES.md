# 10 - Remaining Support Modules

## Overview
Five modules that provide supporting functionality: file attachments, auto-save, library UI interactions, semantic search, and the reusable tree component base.

---

## attachment_handler.py (~310 lines)
**Purpose:** Manages file attachments for AI prompts — temporary multi-document context that is NOT saved to the Documents Library.

**Module-Level Function:**
- `check_local_ai_context_warning(provider, total_words, attachment_count)` → str or None — warns when attachments may exceed local AI context window (triggers at 70% of 8K typical limit)

**Class: AttachmentManager**

**Supported Extensions:** .txt, .pdf, .docx, .doc, .rtf, .md, .csv, .json

**Adding Attachments:**
- `add_attachment(filepath, progress_callback)` → dict — extracts text from file, adds to list
- `add_from_library(doc_id, doc_title, doc_text)` → dict — adds library document as attachment
- `add_from_text(title, text, source)` → dict — adds pre-extracted text (used by sources dialog)

**Text Extraction (private):**
- `_extract_text(filepath, ext)` → str — dispatcher by file extension
- `_extract_pdf(filepath)` → str — via PyPDF2
- `_extract_docx(filepath)` → str — via python-docx
- `_extract_doc(filepath)` → str — via textract (fallback to docx)
- `_extract_rtf(filepath)` → str — via striprtf (fallback to regex)
- `_extract_csv(filepath)` → str — pipe-delimited rows
- `_extract_json(filepath)` → str — pretty-printed JSON

**Management:**
- `remove_attachment(index)` / `remove_attachment_by_path(filepath)` → bool
- `clear_all()` — removes all attachments
- `get_attachment_count()` / `get_total_tokens()` / `get_total_words()` → int

**Output:**
- `build_attachment_text()` → str — formatted block with headers: `=== ATTACHED DOCUMENTS ===` / per-attachment sections / `=== END OF ATTACHMENTS ===`
- `get_summary()` → str — e.g. "3 files attached (~2,500 words, ~3,250 tokens)"

**Attachment Dict Structure:**
```python
{
    'path': str,           # filepath or "library://doc_id"
    'filename': str,       # display name
    'text': str,           # extracted content
    'word_count': int,
    'token_estimate': int, # word_count * 1.3
    'error': str or None,
    'from_library': bool,  # optional
    'from_sources_dialog': bool,  # optional
    'doc_id': str          # optional, for library docs
}
```

**Dependencies:** os, typing, PyPDF2 (optional), python-docx (optional), striprtf (optional)
**Called By:** Main.py, sources_dialog.py, library_interaction.py

---

## auto_save_responses.py (~200 lines)
**Purpose:** Drop-in module for automatically saving AI responses to the Documents Library.

**Class: ResponseAutoSaver**

**Key Methods:**
- `save_response(response_text, prompt_name, source_document_id, provider, model, conversation_thread)` → doc_id or None
  - Creates title from prompt name + source doc title (or timestamp fallback)
  - Splits response into paragraph-based entries
  - Saves to library as `document_class='response'` with `doc_type='ai_response'`
  - Optionally saves conversation thread metadata
- `enable()` / `disable()` / `toggle()` — control auto-save
- `get_last_saved_id()` → str or None

**Dependencies:** datetime, document_library (lazy import)
**Called By:** Main.py (`self.response_saver`)

---

## library_interaction.py (~650 lines)
**Purpose:** Document Library UI interactions — viewing outputs, deleting docs, bulk processing, add sources. **Mixin class** extracted from Main.py.

**Class: LibraryInteractionMixin**

**Key Methods:**

- **`view_processed_outputs(doc_id, doc_title)`** — Modal dialog showing all AI processing outputs for a document. Listbox with timestamp/prompt/model info, preview panel, export and delete buttons.

- **`delete_from_library(doc_id, doc_title)`** — Confirms and deletes document + all processed outputs + entries file from library.

- **`open_bulk_processing()`** — Opens bulk processing window. Defines `process_single_item()` callback that handles: local files (with .url shortcut extraction, OCR for scanned PDFs), YouTube URLs, Substack URLs, generic web URLs. Warns if embedding model selected. Delegates to `sources_dialog.open_bulk_processing()`.

- **`open_add_sources()`** — Opens unified Add Sources dialog for adding content to Documents Library or Prompt Context. Provides callbacks for processing, saving, and attachment management.

- **`update_add_sources_button()`** — Stub (button removed in current UI).

- **`open_library_window()`** — Opens tree-based Documents Library via `document_tree_manager.open_document_tree_manager()`. Provides two callbacks:
  - `load_document_callback(doc_id)` — loads document into main window, handles thread documents (loads parent source entries), manages viewer window lifecycle (replace/side-by-side), auto-opens Thread Viewer
  - `send_to_input_callback(doc_info_list)` — adds selected library docs as attachments via `attachment_manager.add_from_library()`

**Lazy Imports:** ocr_handler, document_fetcher, ai_handler (loaded on demand to speed startup)

**Dependencies:** tkinter, config, document_library, utils, sources_dialog
**Called By:** Main.py (mixed in via inheritance)

---

## semantic_search.py (~600 lines)
**Purpose:** Semantic (meaning-based) search with chunk-level embeddings. VERSION 2.0 with paragraph-level precision.

### Class: SemanticSearch
**Embedding Generation:**
- `generate_embedding(text)` → (vector, cost) — single text via OpenAI or Gemini
- `generate_embeddings_batch(texts)` → (vectors, cost) — batch API call (OpenAI only, others fall back to individual)
- `_generate_openai_embedding(text)` / `_generate_openai_embeddings_batch(texts)` — OpenAI API via urllib
- `_generate_gemini_embedding(text)` — Gemini API via urllib

**Similarity:**
- `cosine_similarity(vec1, vec2)` → float — pure Python cosine similarity

**Models & Pricing:**
- OpenAI: `text-embedding-3-small`, 1536 dims, $0.00002/1K tokens
- Gemini: `embedding-001`, 768 dims, ~$0.00001/1K tokens

### Text Chunking Functions
- `chunk_text(text, chunk_size=500, overlap=50)` → list of dicts — splits at paragraph/sentence boundaries with overlap
- `chunk_text_simple(text, chunk_size=500)` → list of dicts — simpler paragraph-based chunking

### Class: ChunkEmbeddingStorage (v2.0)
**Storage:** JSON file with per-document chunk embeddings

- `add_document_chunks(doc_id, chunks, embeddings, cost)` — stores chunk embeddings (text preview limited to 500 chars)
- `get_document_chunks(doc_id)` → list or None
- `has_embedding(doc_id)` / `remove_embedding(doc_id)` → bool
- `get_all_chunks_flat()` → list — all chunks across all documents with doc_id reference
- `get_stats()` → dict — total docs, chunks, cost, provider info
- `save()` / `_load()` — JSON persistence
- `_migrate_v1_to_v2(old_data)` — migrates single-embedding-per-doc to chunk format

**Backwards Compatibility:** `EmbeddingStorage` = alias for `ChunkEmbeddingStorage`

### Module Function
- `search_chunks(query_embedding, storage, top_k=20, threshold=0.3)` → list — searches all chunks, returns sorted by similarity with score_percent

**Dependencies:** json, os, re, math, datetime, urllib (for API calls)
**Called By:** document_library.py (embedding functions), export_utilities.py (test_semantic_search)

---

## tree_manager_base.py (~1,100 lines)
**Purpose:** Generic reusable tree component with Windows Explorer-style functionality. Base classes for both Prompts Library and Documents Library.

### Data Classes

**TreeNode (ABC):**
- Abstract base for tree items
- Required overrides: `get_icon()`, `get_type()`, `to_dict()`, `from_dict()`, `can_be_renamed()`, `can_be_deleted()`, `can_be_moved()`

**FolderNode:**
- Generic folder containing other nodes (folders or items)
- Uses `OrderedDict` to preserve insertion order
- **Key Methods:** `add_child()`, `remove_child()`, `get_child()`, `has_child()`, `move_child_up()`, `move_child_down()`, `move_child_to_position()`, `get_depth()`
- **Serialization:** `to_dict()` / `from_dict(data, node_factory)`

**TreeManager:**
- Tree data structure (UI-independent)
- `root_folders: OrderedDict[str, FolderNode]`
- **CRUD:** `add_root_folder()`, `remove_root_folder()`, `get_root_folder()`
- **Search:** `find_item(item_name, item_type)` → (parent, item, depth)
- **Move Validation:** `can_move_to(source, target)` → (bool, reason) — checks depth limit (MAX_TREE_DEPTH=4), name collision, circular reference
- **Move Execution:** `move_item()`, `move_item_up()`, `move_item_down()`
- **Serialization:** `to_dict()` / `from_dict(data, node_factory)`

### UI Component

**TreeManagerUI:**
- Generic Tkinter tree view with full Explorer-style interaction
- **Constructor:** `(parent, tree_manager, item_type_name, on_save_callback, on_item_action)`

**UI Features:**
- Header with Expand All / Collapse All
- Control buttons: New Folder, New Item, Rename, Delete, Move Up, Move Down
- Treeview with hidden 'type' and 'can_drop' columns
- Multi-select enabled (`selectmode='extended'`)

**Drag-and-Drop:**
- Motion-based (5px threshold to start drag)
- Auto-scroll near edges (30px zone)
- Cursor feedback (hand2 for valid drop, X_cursor for invalid)
- Validates via `tree_manager.can_move_to()` before drop
- Uses tree hierarchy for precise item tracking (prevents ghost items)

**Keyboard Shortcuts:**
- F2 = Rename, Delete = Delete
- Ctrl+X/C/V = Cut/Copy/Paste
- Ctrl+Up/Down = Move Up/Down
- Enter = Activate item

**Right-Click Context Menu:** Rename, Delete, Move Up/Down, Cut/Copy/Paste, New Folder, New Item

**Abstract Methods (override in subclass):**
- `on_item_selected(item_name, item_type)`
- `on_multiple_selected(count)`
- `activate_selected()`
- `create_item_node(name, **kwargs)` → TreeNode

**Dependencies:** tkinter, json, collections.OrderedDict, abc
**Subclassed By:** prompt_tree_manager.py (PromptTreeManagerUI), document_tree_manager.py (DocumentTreeManagerUI)
