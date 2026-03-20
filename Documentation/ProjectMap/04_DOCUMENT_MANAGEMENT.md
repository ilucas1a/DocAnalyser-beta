# Project Map: Document Management & Library

## document_library.py (1,501 lines)
- **Purpose:** Core document library — CRUD operations, thread storage, and semantic search/embeddings
- **Dependencies:** os, json, hashlib, datetime, config, utils
- **Called By:** Main.py, document_tree_manager.py, export_utilities.py, thread_viewer.py, smart_load.py
- **Data Store:** `document_library.json` at `LIBRARY_PATH`

### Library CRUD:
- `ensure_library()` — creates library file if absent
- `load_library()` → Dict — reads library from disk
- `save_library(library)` — writes library to disk (atomic)
- `generate_doc_id(source, doc_type)` → str — MD5-based 12-char hex ID
- `add_document_to_library(doc_type, source, title, entries, metadata, document_class)` → str — add/update doc
- `update_document_entries(doc_id, new_entries)` → bool
- `rename_document(doc_id, new_title)` → bool
- `delete_document(doc_id)` → bool
- `convert_document_to_source(doc_id)` → bool — changes document_class

### Document Retrieval:
- `load_document_entries(doc_id)` → List[Dict] or None — loads from summaries dir
- `get_recent_documents(limit)` → List[Dict]
- `get_document_count()` → int
- `get_document_by_id(doc_id)` → Dict or None
- `get_all_documents()` → List[Dict]
- `search_documents(query, search_in)` → List[Dict]
- `get_library_stats()` → Dict
- `is_source_document(doc_id)` → bool

### Processed Outputs (AI analysis results):
- `add_processed_output_to_document(doc_id, prompt_name, prompt_text, output_text, model, provider, cost)` → str
- `get_processed_outputs_for_document(doc_id)` → List[Dict]
- `load_processed_output(output_id)` → str or None
- `delete_processed_output(doc_id, output_id)` → bool

### Thread/Conversation Storage:
- `save_thread_to_document(doc_id, thread, thread_metadata)` → bool
- `load_thread_from_document(doc_id)` → (thread, metadata)
- `clear_thread_from_document(doc_id)` → bool
- `save_thread_as_new_document(original_doc_id, thread, metadata)` → str — saves conversation as new library doc
- `format_thread_as_text(thread)` → str
- `get_threads_for_document(doc_id)` → list
- `get_response_branches_for_source(source_doc_id)` → List[Dict]
- `delete_thread_document(thread_doc_id)` → bool

### Semantic Search & Embeddings:
- `get_embeddings_path()` → str
- `get_documents_needing_embeddings()` → List[Dict]
- `get_embedding_stats()` → Dict
- `perform_semantic_search(query, api_key, top_k, ...)` → results
- `perform_semantic_search_all_chunks(query, api_key, top_k, ...)` → results
- `generate_embedding_for_doc(doc_id, api_key, ...)` → result
- `remove_embedding_for_doc(doc_id)` → bool
- `has_embedding(doc_id)` → bool
- `get_document_chunk_count(doc_id)` → int

---

## document_tree_manager.py (1,470 lines)
- **Purpose:** Documents Library UI — tree-structured folder hierarchy with preview panel and editing
- **Pattern:** Built on `tree_manager_base.py` (TreeManager, TreeManagerUI)
- **Dependencies:** tkinter, tree_manager_base, document_library, document_export, config
- **Called By:** Main.py (via "Documents Library" button)

### Class: DocumentItem (extends TreeNode)
- Custom node for documents with `doc_id`, `doc_type`, `document_class`, `has_thread`, `metadata`
- `get_icon()` → emoji based on type (📄📊📹🎙️ etc.)
- `to_dict()` / `from_dict()` — serialization

### Class: DocumentTreeManagerUI (extends TreeManagerUI)
- 4-level folder hierarchy with drag-and-drop
- Preview panel (read-only for sources, editable for products)
- **Key Methods:**
  - `create_ui()` / `create_preview_panel()` — builds UI
  - `show_document_preview(doc)` — loads preview with metadata header
  - `enter_edit_mode()` / `exit_edit_mode(save)` — edit product documents
  - `load_document()` — opens doc in main window
  - `send_to_input()` — sends doc text to input panel
  - `perform_search()` / `highlight_search_results()` — library search
  - `delete_selected()` — handles single/multi/folder deletion
  - `rename_selected()` — inline rename
  - `save_tree()` — persists folder structure

### Module-Level Functions:
- `load_document_tree(library_path)` → TreeManager — loads/creates tree from JSON
- `sync_tree_with_library(tree, library_path)` — syncs tree with library (adds new, removes deleted)
- `open_document_tree_manager(parent, library_path, ...)` — main entry point, opens modal dialog

---

## document_fetcher.py (1,059 lines)
- **Purpose:** Low-level document fetching — reads local files (PDF, DOCX, TXT, RTF, spreadsheets) and web URLs
- **Dependencies:** os, re, tempfile, docx, PyPDF2, bs4, requests, openpyxl, csv, pydub
- **Called By:** document_fetching.py, ocr_processing.py, smart_load.py

### Text Processing:
- `clean_text_encoding(text)` → str — fixes mojibake/encoding artifacts
- `legacy_entries_to_text(entries, include_timestamps)` → str — converts entry list to plain text

### Local File Handling:
- `fetch_local_file(filepath)` → (success, entries/text, title, doc_type) — dispatches by extension:
  - PDF → PyPDF2 text extraction (with OCR pre-screening)
  - DOCX → python-docx paragraph extraction
  - TXT/MD/RTF → direct read
  - XLSX/CSV/TSV → spreadsheet → text
  - Audio/video → returns file path for transcription
  - Images → returns path for OCR

### Web URL Handling:
- `fetch_web_url(url)` → (success, entries, title, doc_type, metadata) — BeautifulSoup scraping
- `extract_publication_date(soup, html_text)` → str — extracts date from meta tags/text
- `fetch_web_video(url, api_key, engine, options, ...)` — downloads and transcribes web video

### Google Sheets Support:
- `is_google_sheets_url(url)` → bool
- `extract_google_sheets_id(url)` → str or None
- `download_google_sheet(url, sheet_id)` → (success, csv_content, title)
- `fetch_google_sheet(url)` → (success, entries, title, doc_type)

---

## document_fetching.py (1,855 lines)
- **Purpose:** High-level document fetching orchestration — **Mixin class** extracted from Main.py
- **Pattern:** `DocumentFetchingMixin` — mixed into main app class, uses `self.xxx`
- **Dependencies:** document_fetcher, substack_utils, twitter_utils, video_platform_utils, youtube_utils
- **Called By:** Main.py (mixed in via inheritance)

### YouTube:
- `fetch_youtube()` — validates URL, starts threaded fetch
- `_fetch_youtube_thread()` — calls youtube_utils for transcript/audio
- `_handle_youtube_result(success, result, title, source_type, yt_metadata)` — displays result, auto-saves

### Substack:
- `fetch_substack()` — validates URL, starts threaded fetch
- `_fetch_substack_thread()` — fetches article text and/or podcast audio
- `_ask_substack_content_choice_simple(choice_data)` — dialog: text, audio, or both
- `_display_substack_result(text, title, metadata)` — loads into app

### Twitter/X:
- `fetch_twitter(url)` — starts threaded fetch
- `_show_twitter_content_choice(result, title, url)` — dialog: text, video, or both
- `_download_and_transcribe_twitter(url, title)` — video transcription path

### Video Platforms (Vimeo, Dailymotion, etc.):
- `fetch_video_platform(url)` — dispatches to video_platform_utils
- `_handle_video_platform_result(...)` — loads transcript

### Local Files:
- `browse_file()` — file dialog, delegates to `_fetch_local_file_thread()`
- `_fetch_local_file_thread()` — threaded file processing with OCR detection
- `_handle_file_result(success, result, title)` — loads result
- `_handle_spreadsheet_result(text_content, title, file_path)` — spreadsheet handling

### Other:
- `start_dictation()` — opens dictation dialog
- `open_multi_image_ocr()` — opens multi-image OCR dialog
- `_show_paste_fallback_dialog(url, source_type, source_name)` — paste content when fetch fails

---

## smart_load.py (1,298 lines)
- **Purpose:** Smart loading, URL auto-detection, multi-document handling — **Mixin class**
- **Pattern:** `SmartLoadMixin` — mixed into main app class
- **Dependencies:** document_fetcher, ocr_handler, youtube_utils, video_platform_utils
- **Called By:** Main.py (mixed in via inheritance)

### Smart Load (main entry point):
- `smart_load()` — auto-detects input type (YouTube URL/ID, Substack, Twitter, Google Drive, web URL, file path, multi-line input)
- `process_url_or_id()` — alias for smart_load

### Multi-Document Handling:
- `_process_multiple_inputs(input_lines)` — routes multiple inputs
- `_show_multi_document_dialog(input_lines)` — dialog: process individually or combine
- `_combine_documents_for_analysis(input_lines, analysis_name)` — combines multiple docs
- `_load_combined_documents(input_lines, analysis_name)` — fetches each doc
- `_finalize_combined_documents(loaded_documents, analysis_name)` — merges into one
- `_batch_process_inputs(input_lines)` — batch process mode

### URL Detection:
- `is_youtube_url(url)` → bool
- `is_substack_url(url)` → bool
- `_is_google_drive_file_url(url)` / `_is_google_drive_folder_url(url)` → bool
- `_extract_google_drive_file_id(url)` → str
- `_fetch_google_drive_file(url)` — downloads from Google Drive
- `could_be_youtube_id(text)` → bool

### OCR Detection:
- `_is_image_file(filepath)` → bool
- `_needs_ocr(filepath)` → bool
- `_check_ocr_confidence(image_path)` → confidence score
- `_process_images_standard_ocr(ocr_files, combine)` — OCR for multiple images

---

## save_utils.py (385 lines)
- **Purpose:** Universal save/export functions with consistent metadata formatting
- **Dependencies:** os, datetime, docx, reportlab
- **Called By:** Main.py, thread_viewer.py, process_output.py

### Key Functions:
- `save_document_to_file(filepath, format, content, title, source, ...)` → (bool, str) — exports to TXT/DOCX/RTF/PDF
- `get_clean_filename(title, max_length)` → str — sanitizes for filesystem
- `get_document_metadata(app_instance, get_document_by_id_func)` → dict — extracts current doc metadata
- `prompt_and_save_document(parent, content, title, metadata)` — file dialog + save

---

## universal_document_saver.py (455 lines)
- **Purpose:** Auto-save framework — saves all incoming documents to library automatically
- **Dependencies:** document_library, config
- **Called By:** Main.py (wraps all fetch handlers)

### Class: UniversalDocumentSaver
- `save_source_document(entries, title, doc_type, source, metadata, document_class)` → str — saves to library
- `enable()` / `disable()` / `toggle()` — control auto-save
- `get_last_saved_id()` → str or None

### Legacy Handler Stubs (for backward compatibility):
- `handle_youtube_url(url)`, `handle_pdf_file(filepath)`, `handle_ocr_scan(image_paths)`
- `handle_audio_file(audio_path)`, `handle_dictation(audio_data)`, `handle_web_url(url)`

---

## document_export.py (844 lines)
- **Purpose:** Consolidated export for documents AND conversation threads to TXT/DOCX/RTF/PDF
- **Dependencies:** os, re, datetime, docx, reportlab
- **Called By:** thread_viewer.py, document_tree_manager.py, export_utilities.py

### Document Export:
- `export_document(format, content, title, source, ...)` → (bool, str, filepath) — main export
- `_export_as_txt/docx/rtf/pdf(...)` — format-specific implementations

### Thread Export:
- `export_conversation_thread(format, messages, metadata, ...)` → (bool, str, filepath)
- `_export_thread_as_txt/docx/rtf/pdf(...)` — format-specific thread exports

### Formatting Helpers:
- `sanitize_filename(text, max_length)` → str
- `_escape_pdf_text(text)` → str
- `_markdown_to_pdf_html(text)` → str
- `_add_markdown_content_to_docx(doc, content)` — rich markdown → DOCX
- `_add_inline_markdown_to_paragraph(paragraph, text)` — bold/italic/code in DOCX

---

## doc_formatter.py (637 lines)
- **Purpose:** Enhanced formatting for AI responses with markdown support in all export formats
- **Dependencies:** docx, reportlab
- **Called By:** save_utils.py, document_export.py

### Key Functions:
- `parse_markdown_text(text)` → list — parses markdown into structured elements
- `add_formatted_paragraph(doc, text, style, is_italic)` — adds to DOCX with formatting
- `save_formatted_docx(filepath, content, title, ...)` → (bool, str) — full DOCX with headers/bullets/tables
- `save_formatted_txt(filepath, content, title, ...)` → (bool, str)
- `save_formatted_pdf(filepath, content, title, ...)` → (bool, str)
- `save_formatted_document(filepath, format, content, ...)` — dispatcher

---

## output_formatter.py (245 lines)
- **Purpose:** RTF generation and markdown rendering in Tkinter text widgets
- **Dependencies:** tkinter
- **Called By:** Main.py, thread_viewer.py

### Key Functions:
- `generate_rtf_content(title, content, metadata)` → str — RTF string with formatting
- `render_markdown_in_text_widget(text_widget, content, font_size)` — renders **bold**, *italic*, `code`, headers, bullets in Tkinter
- `generate_html_content(title, content, metadata)` → str
- `generate_markdown_content(title, content, metadata)` → str

---

## process_output.py (927 lines)
- **Purpose:** AI processing orchestration and output saving — **Mixin class**
- **Pattern:** `ProcessOutputMixin` — mixed into main app class
- **Dependencies:** ai_handler, document_library, output_formatter, doc_formatter
- **Called By:** Main.py (mixed in via inheritance)

### Processing:
- `process_document()` — validates inputs, starts AI processing thread. March 2026: added pre-run warning when Ollama is selected and the prompt contains `[SOURCE:` — explains that local models don’t reliably follow the audio-linked summary format and names recommended cloud alternatives. User can proceed or cancel.
- `_process_document_thread()` — sends chunks to AI, handles streaming, manages attachments
- `check_processing_thread()` — polls processing thread status
- `cancel_processing()` / `_show_cancel_confirmation()` — cancellation flow
- `_restart_application()` — force restart after stuck processing

### Output Handling:
- `_handle_process_result(success, result)` — displays AI response
- `_save_processed_output(ai_response)` — saves to library as processed output
- `_save_attachments_output(ai_response)` — saves with attachment context
- `_save_as_product(output_text, dialog)` — saves as product document
- `_save_as_metadata(output_text, dialog)` — saves as document metadata
- `save_current_output(output_text)` / `save_output()` — user-triggered save

### UI State:
- `reset_ui_state()` — resets buttons/progress after processing

---

## export_utilities.py (864 lines)
- **Purpose:** App lifecycle, export, and utility methods — **Mixin class**
- **Pattern:** `ExportUtilitiesMixin` — mixed into main app class
- **Dependencies:** document_library, document_export, cost_tracker, semantic_search, sources_dialog
- **Called By:** Main.py (mixed in via inheritance)

### App Lifecycle:
- `on_app_closing()` — cleanup and exit
- `start_new_conversation_same_source(source_doc_id)` → bool — creates new conversation branch

### Export:
- `export_to_web_chat()` — exports thread as shareable web page
- `export_document()` — file export dialog
- `save_thread_to_library()` — saves current conversation to library

### External Tools:
- `send_to_turboscribe()` — sends audio to TurboScribe for transcription
- `import_turboscribe()` — imports TurboScribe results
- `force_reprocess_pdf()` — re-extracts PDF text
- `download_youtube_video()` — downloads video file
- `open_web_url_in_browser()` — opens source URL

### Other:
- `test_semantic_search()` — runs semantic search dialog
- `show_costs()` — opens cost tracker
- `open_add_sources()` / `update_add_sources_button()` — multi-source attachment dialog
