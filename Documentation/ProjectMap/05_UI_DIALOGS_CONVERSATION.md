# Project Map: UI Dialogs & Conversation

## thread_viewer.py (7,030 lines)
- **Purpose:** Conversation Thread Viewer — the main window for viewing/continuing AI conversations
- **Largest module in the project** — handles source display, conversation threading, follow-up, branching, copy/save, markdown rendering, and HTML export
- **Dependencies:** tkinter, document_library, document_export, ai_handler, output_formatter, branch_picker_dialog
- **Called By:** viewer_thread.py (mixin), Main.py

### Class: ThreadViewerWindow
**Construction & Layout:**
- `__init__(parent, doc_id, thread, metadata, ...)` — creates viewer window
- `_create_window()` / `_create_header()` / `_create_document_info()` — UI construction
- `_create_thread_display()` / `_create_followup_section()` / `_create_button_bar()` — main areas
- `_create_find_replace_bar()` — in-viewer find and replace

**Source Document Display (multi-source support):**
- `_display_source_mode()` / `_display_conversation_mode()` — two display modes
- `_insert_source_header_multi(index)` / `_insert_source_content_multi(index, truncate)` — per-source sections
- `_toggle_source_document(index)` — collapse/expand individual sources
- `_init_source_collapse_state()` / `_init_exchange_collapse_state()` — smart defaults based on char count
- `_calculate_total_expanded_chars()` / `_check_expansion_warning(expanding_index)` — warns before expanding large content

**Conversation Exchanges (collapsible):**
- `_group_messages_into_exchanges()` → list — pairs questions with responses
- `_insert_exchange_header(exchange_idx, timestamp, question_preview, expanded)` — clickable header
- `_toggle_exchange(exchange_idx)` — collapse/expand individual exchanges
- `_toggle_all_exchanges()` — expand/collapse all
- `_delete_current_exchange()` — remove an exchange from thread
- `_scroll_to_exchange(exchange_idx)` — scroll to specific exchange

**Branch Management:**
- `_populate_branch_selector()` — fills branch dropdown with conversation branches
- `_on_branch_selected(event)` — switch between branches
- `_load_branch(branch_doc_id)` — loads different conversation branch
- `_create_new_branch_from_selector()` / `_create_new_branch_and_switch(branch_name, source_doc_id)` — new branch creation
- `_create_new_branch_and_process(question, branch_name, source_doc_id)` — new branch + immediate follow-up
- `_switch_to_branch_and_process(branch_doc_id, question)` — switch branch + follow-up
- `_copy_exchange_to_additional_branches(question, ai_response)` — multi-branch save via BranchPickerDialog

**Follow-up Processing:**
- `_submit_followup()` — validates and sends follow-up question
- `_submit_followup_direct(question)` — direct submission
- `_process_followup_thread(question)` — threaded AI call
- `_handle_followup_result(question, success, result)` — displays result, saves to thread
- `_handle_source_document_followup(question, source_doc_id)` — follow-up about source doc
- `_submit_initial_prompt_with_chunking(prompt)` — first prompt with document chunking

**Source Editing:**
- `_save_source_edits()` — saves edits to source content
- `_save_edits_before_refresh()` / `_save_edits_to_thread()` — persist edits
- `_undo_edit()` — undo source edits

**Markdown Rendering:**
- `_render_markdown_content(content)` — renders markdown in text widget
- `_render_inline_markdown(line)` — bold, italic, code rendering
- `_make_links_clickable()` — clickable URLs
- `_reconstruct_markdown_content(content_lines)` → str — reverse: widget back to markdown

**Copy Operations (extensive):**
- `_copy_source_only(plain_text)` / `_copy_thread()` / `_copy_expanded_only()` / `_copy_complete(plain_text)`
- `_copy_thread_formatted()` / `_copy_expanded_only_formatted()` — formatted HTML copies
- `_copy_selection_to_clipboard()` / `_copy_selection_formatted()` — selection-based copy
- `_show_copy_dialog()` — copy options dialog
- `_copy_html_to_clipboard_windows(html_content)` → bool — Windows CF_HTML clipboard
- `_build_cf_html(html_content)` → str — CF_HTML format builder

**Save Operations:**
- `_save_source_only(format_ext)` / `_save_thread(format_ext)` / `_save_expanded_only(format_ext)` / `_save_complete(format_ext)`
- `_save_complete_txt/rtf/docx/pdf(file_path)` — format-specific implementations
- `_show_save_as_dialog()` — save options dialog
- `_save_selection(format_ext)` — save selected text

**HTML Export:**
- `_thread_to_html()` → str — full thread as HTML
- `_markdown_to_html_content(markdown_text)` / `_markdown_to_html(markdown_text)` → str
- `_text_widget_to_html()` → str — Tkinter widget to HTML
- `_convert_inline_markdown(text)` / `_inline_markdown_to_html(text)` → str
- `_html_to_plain_text(html)` → str

**Mode & Navigation:**
- `switch_mode(new_mode)` / `_toggle_mode()` — source ↔ conversation mode
- `toggle_source_visibility()` — show/hide source in conversation mode
- `_start_new_conversation()` / `_can_start_new_conversation()` — new conversation branch

### Module-Level:
- `show_thread_viewer(parent, doc_id, thread, metadata, ...)` — convenience function

---

## viewer_thread.py (789 lines)
- **Purpose:** Thread viewer management and chunked prompt processing — **Mixin class**
- **Pattern:** `ViewerThreadMixin` — mixed into main app class
- **Dependencies:** thread_viewer, document_library, ai_handler
- **Called By:** Main.py (mixed in via inheritance)

### Key Methods:
- `view_conversation_thread()` — opens thread viewer for current doc
- `_view_source()` — opens source-mode viewer
- `_check_viewer_source_warning()` → bool — warns about unsaved edits
- `_show_thread_viewer(target_mode, force_new_window)` — main viewer launch logic with instance management
- `_cleanup_closed_viewers()` — removes dead viewer references
- `_get_open_viewer_count()` → int
- `_check_viewer_open_action(new_doc_title)` → str — handle already-open viewers
- `_view_thread()` — view thread mode specifically
- `process_prompt_with_chunking(prompt, status_callback, complete_callback)` — processes long docs in chunks
- `save_current_thread()` — saves thread to library
- `load_saved_thread()` — loads thread from library

---

## standalone_conversation.py (354 lines)
- **Purpose:** Handles saving conversations that started without a source document
- **Dependencies:** tkinter, ai_handler, document_library
- **Called By:** Main.py (after AI response when no source doc loaded)

### Class: StandaloneConversationManager
- `is_standalone_conversation(current_document_id, ...)` → bool — detects standalone state
- `generate_title_with_ai(prompt_text, response_text, ...)` → str — AI-generated title
- `show_save_dialog(parent, suggested_title, ...)` — save dialog with editable title
- `save_conversation(title, current_thread, ...)` → str — creates library document

### Module Functions:
- `get_standalone_manager()` → singleton instance
- `check_and_prompt_standalone_save(parent, ...)` — orchestrates the save flow
- `reset_standalone_state()` — resets for next conversation

---

## branch_picker_dialog.py (416 lines)
- **Purpose:** Dialog for selecting which conversation branches to save a response to
- **Features:** Multi-select branches, pre-selection of current conversation, "stay in view" option
- **Dependencies:** tkinter, document_library
- **Called By:** thread_viewer.py

### Class: BranchPickerDialog
- `__init__(parent, source_doc_id, current_branch_id, question, ai_response)` — builds dialog
- `_create_dialog()` — UI with checkboxes for each branch + "new branch" option
- `_on_continue()` — saves to selected branches
- `get_result()` → Dict — returns selection: `{selected_branches, new_branch_name, stay_in_current}`

### Module Function:
- `show_branch_picker(parent, source_doc_id, ...)` → Dict or None — convenience function

---

## dictation_dialog.py (493 lines)
- **Purpose:** Speech-to-text recording dialog with multi-segment support
- **Dependencies:** tkinter, transcription_handler
- **Called By:** document_fetching.py (via `start_dictation()`)

### Class: DictationDialog
- Multi-segment recording (record, stop, continue recording)
- Concatenates segments before transcription
- Supports local (faster-whisper) and cloud (OpenAI) transcription
- **Key Methods:** `_toggle_recording()`, `_start_recording()`, `_stop_recording()`, `_transcribe()`, `_concatenate_audio_segments()`

---

## voice_edit_dialog.py (800 lines)
- **Purpose:** Voice-assisted text editing with keyword-triggered commands
- **Commands:** "new paragraph", "new line", "replace X with Y", "delete X", "insert X after Y", "scratch that", "done"
- **Dependencies:** tkinter, transcription_handler
- **Called By:** ocr_dialog.py, Main.py

### Class: CommandReferencePopup
- Floating command reference card

### Class: VoiceEditDialog
- Continuous recording loop with real-time command processing
- Undo/redo stack for all edits
- **Key Methods:** `_process_speech(text)`, `_try_command(text_lower, original_text)`, `_replace_text(find, replace)`, `_delete_text(text)`
- `get_result()` → str or None — returns edited text

---

## paste_content_dialog.py (398 lines)
- **Purpose:** Manual paste dialog — fallback when automated fetching fails
- **Dependencies:** tkinter, document_library
- **Called By:** document_fetching.py (`_show_paste_fallback_dialog`)

### Class: PasteContentDialog
- Text area for pasting content, title field, char count
- Auto-detects YouTube transcript format in pasted text
- Saves to library on confirm

---

## chunk_settings_window.py (80 lines)
- **Purpose:** Simple dialog for selecting document chunk size
- **Dependencies:** tkinter, config, config_manager
- **Called By:** Main.py

### Class: ChunkSettingsWindow
- Dropdown with chunk size options (Tiny/Small/Medium/Large)
- Saves selection to config

---

## sources_dialog.py (1,702 lines)
- **Purpose:** Multi-source input dialog — add URLs, files, library docs for batch processing or prompt context
- **Two Modes:** "Documents Library" (permanent storage) and "Prompt Context" (temporary attachment)
- **Dependencies:** tkinter, document_library, document_fetcher, youtube_utils, substack_utils
- **Called By:** export_utilities.py (`open_add_sources`)

### Class: SourcesDialog
- Input field + listbox for URLs/files
- Drag-and-drop support (files + URLs)
- Browse files button, add from library button
- Scheduling support (process at specific time)
- Progress display during batch processing
- **Key Methods:**
  - `_add_from_entry()` / `_on_drop(event)` / `_browse_files()` — input methods
  - `_add_from_library()` — library picker
  - `_start_processing()` / `_process_items(items)` / `_poll_results()` — batch processing
  - `_schedule_processing(minutes)` / `_schedule_processing_at(datetime)` — scheduling
  - `_detect_item_type(item)` → str — auto-detect URL/file type

### Class: DateTimeScheduleDialog
- Custom date/time picker for scheduled processing

---

## first_run_wizard.py (479 lines)
- **Purpose:** First-launch wizard focused on AI provider choice (cloud vs local)
- **Dependencies:** tkinter, webbrowser
- **Called By:** Main.py (on first launch)

### Key Functions:
- `show_first_run_wizard(parent, on_complete_callback, ...)` — multi-page wizard
- Pages: Welcome → AI Choice (Cloud/Local/Both) → Local AI Setup → Complete
- `has_run_before()` → bool / `mark_wizard_complete()` — persistence
- `check_lm_studio_running()` — tests LM Studio connection

---

## setup_wizard.py (899 lines)
- **Purpose:** Dependency status checker and installation helper
- **Dependencies:** tkinter, dependency_checker, version
- **Called By:** Main.py (Settings menu)

### Class: SetupWizard
- Shows status of all dependencies (Tesseract, Poppler, FFmpeg, faster-whisper, LM Studio)
- Feature availability matrix
- Install buttons with links/instructions
- **Key Methods:** `refresh_status()`, `_show_whisper_dialog()`, `_show_lm_studio_dialog()`, `_show_install_dialog(dep)`

### Class: UpdateNotificationDialog
- Shows available app updates with changelog
- Download/skip options

### Module Functions:
- `show_setup_wizard(parent, on_complete)` — opens wizard
- `show_update_notification(parent, update_info)` → str or None
- `should_show_first_run_wizard(config)` → bool
