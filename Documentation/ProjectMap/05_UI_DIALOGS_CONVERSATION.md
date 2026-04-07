# Project Map: UI Dialogs & Conversation

## thread_viewer.py (refactored into 5 files)
- **Purpose:** Conversation Thread Viewer — the main window for viewing/continuing AI conversations
- **Largest module in the project** — handles source display, conversation threading, follow-up, branching, copy/save, markdown rendering, and HTML export
- **Refactored:** Major functionality extracted into mixin sub-modules (thread_viewer_branches.py, thread_viewer_copy.py, thread_viewer_markdown.py, thread_viewer_save.py) for maintainability. ThreadViewerWindow now inherits from these mixins.
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
- `_create_header()` — branch row now includes a `🗑 Delete Branch` button (width reduced 40→35 on combo to fit)

**Follow-up Processing:**
- `_submit_followup()` — validates and sends follow-up question. March 2026: local AI providers (LM Studio, Ollama) are now correctly exempted from the API key check; web-only providers (Mistral Le Chat, etc.) show a clear redirect message instead of a generic "API Key Required" error.
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

**Seek Link State:**
- `_refresh_thread_display()` — resets `self._seek_locations = []` at the start of every render so seek link tags from the previous render are discarded cleanly.

**Transcript Editing (audio transcription documents, March 2026):**
- `_wire_player()` — creates `TranscriptPlayer` and `TranscriptParagraphEditor` once the text widget exists. Editor is only created when `transcript_paragraph_editor` can be imported; falls back gracefully if unavailable.
- `_get_entry_speakers()` → list — returns ordered unique speaker labels from `current_entries`.
- `_create_speaker_filter_bar(speakers)` — builds the edit toolbar row inside the Audio Playback frame. Contains: 🎤 Show speaker dropdown (`width=14`), ✏ Edit transcript / 💾 Save edits toggle, 🔗 Audio links button, ⊕ Merge with next button, ✂ Split here button, and a split preview label row (hidden until edit mode). Only shown when transcript has 2+ distinct speakers.
- `_add_edit_mode_button(parent_row)` — creates the two persistent buttons: 🔗 Audio links (green/sunken when active) and ✏ Edit transcript / 💾 Save edits (toggles via `_toggle_edit_save`).
- `_toggle_edit_save()` — enters or exits edit mode depending on `self._edit_mode_active`.
- `_enter_edit_mode()` — pauses audio if playing; delegates to `editor.enter_edit_mode()`; enables Split and Merge buttons; shows split preview row; updates button appearance.
- `_save_and_exit_edit_mode()` — delegates to `editor.exit_edit_mode()` (syncs widget → entries, saves, re-renders); disables Split and Merge buttons; hides split preview row; restores button appearance.
- `_split_paragraph_at_cursor()` — delegates to `editor.split_paragraph_at_cursor()`.
- `_merge_paragraph_at_cursor()` — finds which paragraph the cursor is in via `editor._find_entry_at_cursor()`, then calls `editor.merge_with_next(entry_idx)`. Shows informational dialog if cursor is not in a paragraph or paragraph is already last.
- `_update_split_preview_label(text)` — receives live split preview string from the editor's `preview_callback` and displays it in `_split_preview_label`.

**Edit in Word workflow (April 2026):**
- `_edit_in_word()` — exports transcript to .docx, then calls `_open_word_suite()`. Triggered by "Edit in Word" button (audio transcription documents only, shown in button bar next to Save As).
- `_open_word_suite(docx_path, doc_id, entries, audio_path, on_save_callback)` — shared helper that opens the complete Word editing environment in one step: (1) opens .docx in Word via `os.startfile`, (2) launches `companion_player.py` as a background subprocess (`CREATE_NO_WINDOW`) with the audio path, (3) opens `WordEditorPanel`. Called by `_edit_in_word()` and by `thread_viewer_save._save_source_only()` when user says "Open in Word?".
- Save-back callback: Word edits round-trip to DocAnalyser — `WordEditorPanel` fires `on_save_callback(updated_entries)` → `update_transcript_entries(doc_id, updated_entries)`.

**Window Geometry (March 2026):** default 700×860px, minsize 500×700px (increased from 780/600 to prevent button row clipping when the Branch selector row is visible).

### Module-Level:
- `show_thread_viewer(parent, doc_id, thread, metadata, ...)` — convenience function

---

## thread_viewer_branches.py (extracted mixin)
- **Purpose:** Branch management mixin for ThreadViewerWindow
- **Handles:** Branch selector UI, branch loading/creating/switching, copying exchanges to multiple branches, branch+process workflows, branch deletion
- **Pattern:** Mixin class — all methods access ThreadViewerWindow state via `self`

### Added March 2026:
- `_delete_current_branch()` — deletes the currently displayed conversation branch. Safety guards: refuses to delete source documents; warns if it is the last branch for the source. After deletion: switches to a sibling branch if one exists, falls back to displaying the source document, or closes the viewer if no source is known. Clears main app state if `app.current_document_id` points at the deleted doc. Calls `app.refresh_library()`.

## thread_viewer_copy.py (extracted mixin)
- **Purpose:** Copy & clipboard mixin for ThreadViewerWindow
- **Handles:** All copy-to-clipboard operations, HTML generation for formatted copy, CF_HTML Windows clipboard format, selection operations, copy dialog
- **Pattern:** Mixin class

## thread_viewer_markdown.py (extracted mixin)
- **Purpose:** Markdown rendering mixin for ThreadViewerWindow
- **Handles:** Rendering markdown into Tkinter Text widget, reconstructing markdown from widget formatting, making URLs clickable, and rendering audio seek links
- **Pattern:** Mixin class
- **Dependencies:** tkinter, re, webbrowser, typing (Optional, Tuple)

### Audio Seek Link Methods (added March 2026):
- `_find_entry_for_text(search_text)` → (entry_index, start_seconds) or None — searches `self.current_entries` for the entry whose text best matches `search_text`. Strategy: (1) exact substring match on 1-, 2-, and 3-entry sliding windows; (2) word-overlap fuzzy fallback requiring ≥40% of 4+ char words to match.
- `_fmt_seek_time(seconds)` → str — static method, formats seconds as MM:SS or H:MM:SS
- `_render_source_seek_link(search_text)` — resolves a `[SOURCE: "..."]` marker to an audio timestamp, inserts a blue underlined `▶ Jump to MM:SS` clickable link into the text widget. Silently omits if no entry matches.
- `_on_seek_link_click(seconds)` — seeks `self.transcript_player` to `seconds` and starts playback. Shows friendly dialog if player unavailable.

### Updated method:
- `_render_markdown_content(content)` — now detects `[SOURCE: "..."]` lines (case-insensitive regex) and calls `_render_source_seek_link()` before falling through to normal markdown rendering. `self._seek_locations` list is reset in `_refresh_thread_display()` at the start of each render.

## thread_viewer_save.py (extracted mixin)
- **Purpose:** Save & export mixin for ThreadViewerWindow
- **Handles:** All save-to-file operations including format-specific exports (TXT, RTF, DOCX, PDF), save-as dialog
- **Pattern:** Mixin class

---

## transcript_paragraph_editor.py
- **Purpose:** Structured paragraph editor for audio transcripts — enables word corrections, paragraph splits, paragraph merges, and speaker reassignment while preserving timestamp-based audio seek links throughout.
- **Architecture:** `self._entries` is the source of truth. The `tk.Text` widget is a rendered view. Per-sentence tags (`seg_0`, `seg_1`, …) anchor each sentence span. On save, text is read back from the widget using tag positions (not marks, which drift), and both `entry["text"]` and `entry["sentences"]` are updated so `render()` displays the edited content correctly.
- **Dependencies:** tkinter, re, document_library (lazy import for save)
- **Called By:** `thread_viewer.py` (`_wire_player`)

### Class: TranscriptParagraphEditor

**Constructor:**
- `__init__(text_widget, entries, doc_id, config, player, save_callback, preview_callback)` — all parameters after `config` are optional. `preview_callback` receives live split-preview strings for display in the Thread Viewer toolbar.

**Public API:**
- `render(speaker_filter)` — clears widget, re-renders all entries as paragraph blocks with timestamp headers and speaker labels. Sets up sentence-level `seg_N` click-to-seek tags. Sets widget to DISABLED when not in edit mode.
- `enter_edit_mode()` — enables widget editing; binds `<Return>` to split; binds `<KeyRelease>` and `<ButtonRelease-1>` to live split preview; suppresses click-to-seek.
- `exit_edit_mode()` — saves scroll position; calls `_sync_from_widget()` and `_save_to_library()`; re-renders; restores scroll position via deferred `after(10ms)` call to prevent Tkinter focus-shift from overriding the restore.
- `split_paragraph_at_cursor()` — WYSIWYG split at the nearest sentence-ending punctuation (. ? !) to the cursor. Uses cached split point from `_update_split_preview_inner()` for consistency. Assigns timestamps by proportional interpolation. Rebuilds sentences sub-lists for both halves. Saves and re-renders, then re-enters edit mode with cursor at the start of the new second paragraph.
- `merge_with_next(entry_idx)` — merges paragraph at `entry_idx` with the one below it. Strips whitespace from all sentence texts before joining to prevent gaps from transcription artefacts. Drops blank sentence placeholders. Saves and re-renders.
- `get_entries()` → list — returns a copy of current `self._entries`.
- `highlight_segment(seg_idx)` — highlights the segment tag `seg_N` in yellow; called by `TranscriptPlayer` during playback.

**Internal — Sync & Save:**
- `_rebuild_sentences(text, entry)` → list — *static method*. Splits edited text on sentence-ending punctuation and distributes timestamps proportionally by character count. Used by `_sync_from_widget` to keep `entry["sentences"]` consistent with `entry["text"]` after word-level edits.
- `_sync_from_widget()` — reads the full text of each paragraph from the widget using `_get_para_text_from_widget()` (tag-position based, handles multi-line wrapping). Updates both `entry["text"]` and `entry["sentences"]` via `_rebuild_sentences()`. Skips unchanged entries. Previous regex-based approach (stopped at first newline) replaced March 2026 — it silently discarded line-2+ edits and sentence deletions.
- `_save_to_library()` → bool — calls `document_library.update_transcript_entries(doc_id, entries)` and fires `save_callback`.

**Internal — Widget Position Helpers:**
- `_find_entry_at_cursor(cursor)` → int or None — first tries exact hit (cursor within a `seg_N` tag range); falls back to nearest segment whose start is ≤ cursor. Used by split preview and by `thread_viewer._merge_paragraph_at_cursor()`.
- `_cursor_to_para_char_offset(cursor, entry_idx)` → int or None — converts a Tkinter cursor index to a character offset within the paragraph's spoken text (after the header).
- `_get_para_text_from_widget(entry_idx)` → str or None — extracts the full spoken text for an entry using segment tag positions as anchors, reading correctly across line wraps.

**Internal — Split Logic:**
- `_nearest_sentence_end(text, char_offset)` → int or None — searches outward from cursor (forward first, then backward) for the closest sentence-ending punctuation and returns the index of the first character of the new second paragraph.
- `_update_split_preview(event)` / `_update_split_preview_inner()` — computes the would-be split without executing it; caches result in `_pending_split_entry` / `_pending_split_char_offset`; pushes a descriptive string to `preview_callback`. Three states: normal split preview, single-sentence paragraph, cursor not in any paragraph.
- `_on_enter_key(event)` — intercepts `<Return>` in edit mode; calls `split_paragraph_at_cursor()`; always returns `"break"` to prevent literal newline insertion.

**Internal — Event Handlers:**
- `_on_segment_click(event)` — seeks audio to the clicked sentence's timestamp via `player.play(from_position=start_secs)`.
- `_on_speaker_click(entry_idx)` — opens a small rename dialog for the speaker label of that paragraph (per-paragraph rename only).

**Known gaps / planned (as of March 2026):**
- Speaker rename is per-paragraph only; bulk rename of all paragraphs sharing a label is not yet implemented — pending user feedback on workflow design.
- Edit toolbar (speaker filter bar, edit/merge/split buttons) is only shown when transcript has 2+ distinct speaker labels. Single-speaker transcripts have no edit UI.

---

## transcript_player.py (~300 lines)
- **Purpose:** Audio-synchronised transcript player for the Thread Viewer
- **Dependencies:** pygame (for playback), tkinter
- **Activated When:** Document type is "audio_transcription" and original audio file still exists on disk
- **Features:** Playback control bar, highlights corresponding transcript segment during playback, click-to-jump to any segment in audio
- **Called By:** thread_viewer.py (auto-activated when conditions met)

---

## viewer_thread.py (789 lines)
- **Purpose:** Thread viewer management and chunked prompt processing — **Mixin class**
- **Pattern:** `ViewerThreadMixin` — mixed into main app class
- **Dependencies:** thread_viewer, document_library, ai_handler
- **Called By:** Main.py (mixed in via inheritance)

### Key Methods:
- `view_conversation_thread()` — opens thread viewer for current doc
- `_view_source()` — opens source-mode viewer
- `_check_viewer_source_warning()` → bool — warns user that Run will process the source document rather than the AI response. March 2026: suppressed when the active prompt contains `[SOURCE:` (audio-linked summary flow) since processing the source is exactly what the user intends.
- `_show_thread_viewer(target_mode, force_new_window)` — main viewer launch logic with instance management; when loading a response/product doc, resolves the source text via `source_document_id` **or** `parent_document_id` in metadata (see key-name note below)
- `_cleanup_closed_viewers()` — removes dead viewer references
- `_get_open_viewer_count()` → int
- `_check_viewer_open_action(new_doc_title)` → str — handle already-open viewers
- `_view_thread()` — view thread mode specifically
- `process_prompt_with_chunking(prompt, status_callback, complete_callback)` — processes long docs in chunks
- `save_current_thread()` — saves thread to library
- `load_saved_thread()` — loads thread from library

> ⚠️ **Metadata key-name convention — two keys mean the same thing:**
> - Via Web response documents (captured by `capture_web_response()`) store the link to their originating source document under `metadata["source_document_id"]`.
> - Other product/processed_output documents use `metadata["parent_document_id"]`.
> All lookups that need the source document ID **must check both keys**, e.g.: `doc.get('parent_document_id') or doc.get('source_document_id')`. This applies in `viewer_thread.py` (two places) and `library_interaction.py` (`load_document_callback`).

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

---

## speaker_id_dialog.py (~600 lines)
- **Purpose:** Two-phase click-driven speaker identification workflow for audio transcripts.
- **Dependencies:** tkinter, re, collections
- **Called By:** thread_viewer.py (`_start_speaker_identification()`)
- **Entry Point:** `start_speaker_identification(parent, editor, player, text_widget, on_complete)`

### Helper Functions (module-level):
- `_is_heuristic(speaker)` → bool — matches `SPEAKER_[A-Z0-9]+` pattern
- `_discover_heuristic_speakers(entries)` → list — ordered unique unresolved `SPEAKER_X` labels
- `_discover_real_names(entries)` → list — ordered unique confirmed names already in entries
- `_infer_name_map(entries)` → dict — infers `SPEAKER_X → real name` from already-resolved neighbours (±5 entry window, ≥70% consistency threshold)

### Phase 1 — Class: SpeakerNameDialog (modal)

Fields labelled "Speaker 1", "Speaker 2" (not SPEAKER_A/B) — user is naming roles, not confirming machine labels. Pre-fills names inferred from surrounding entries. Combobox (if existing names present) or Entry field per speaker. "+ Add speaker" button for recordings with more speakers than found.

- `__init__(parent, heuristic_speakers, existing_names, prefilled)` — builds and blocks with `wait_window()`
- `_add_row(prefill, focus)` — adds a name field row
- `_confirm()` — validates, builds `name_map`, stores `(name_map, all_names, autoplay)` in `self.result`
- **Returns:** `self.result` = `(name_map, all_names, autoplay)` or `None` if cancelled

### Phase 2 — Class: SpeakerIdentifyPanel (non-modal, persistent)

Floating panel alongside the transcript. User-driven: click a paragraph → panel loads it → user clicks a name button. Auto-advances to next/next-unresolved paragraph after each assignment with a 500ms delay.

**UI elements:** unresolved count, auto-play toggle, paragraph timestamp + current label, paragraph text display, per-name buttons, Same↑ / Skip buttons, Identify all, nav mode radio (Next paragraph / Next unresolved), per-speaker count display, Finish & save, Pause/Resume.

**Key methods:**
- `_on_paragraph_clicked(entry_idx)` — registered as `editor.paragraph_click_callback`; loads entry into panel, highlights it in transcript, optionally plays audio
- `_assign(name)` — updates `entry["speaker"]`, clears `provisional`, triggers `editor.render()` immediately (changes visible without Save), advances after 500ms
- `_assign_same()` — re-applies last assigned name
- `_identify_all()` — bulk-applies `name_map` to all still-unresolved entries, triggers full re-render, scrolls to top
- `_highlight_entry(entry_idx)` — applies `spkid_current` yellow tag in transcript text widget
- `_toggle_pause()` / `_pause()` / `_resume()` — deregisters/re-registers `paragraph_click_callback` so user can edit transcript mid-session; also refreshes entries reference in case edits changed content
- `_finish()` / `_on_finish()` — saves via `editor._save_to_library()`, preserves scroll position on close, fires `on_complete`, shows summary messagebox

**Keyboard shortcuts:** `1`/`2`/… = assign speaker N, `Space` = same as last, `S` = skip, `Escape` = finish

### Entry Point Logic (`start_speaker_identification`):
1. Discovers heuristic speakers and existing real names from `editor._entries`
2. If all heuristic speakers can be inferred from neighbours at ≥70% confidence AND real names exist → skips Phase 1 and goes straight to panel
3. Otherwise → launches `SpeakerNameDialog`, uses result as `name_map`
4. Launches `SpeakerIdentifyPanel`

---

## hf_setup_wizard.py (~500 lines)
- **Purpose:** Four-step one-time setup wizard for HuggingFace voice speaker detection. Walks non-technical users through account creation, model licence acceptance, token generation, and model download.
- **Status:** Code complete; not currently reachable in the app because `PYANNOTE_ENABLED = False` in `transcript_cleanup_dialog.py` suppresses the "Set up" link that launches it.
- **Dependencies:** tkinter, threading, webbrowser, diarization_handler (for download step)
- **Called By:** transcript_cleanup_dialog.py (`_on_open_setup_wizard`) — only when `PYANNOTE_ENABLED = True`

### Class: HFSetupWizard

**Step bar indicator:** 4 labels (Create account / Accept licence / Paste token / Download) — completed steps shown in green, active step shown in blue, future steps in grey.

**Step 1 — Create HF account:** links to `https://huggingface.co/join`. Info box explaining offline-after-download and no-data-sent properties.

**Step 2 — Accept model licence:** links to `https://huggingface.co/pyannote/speaker-diarization-3.1`. Info box about contact-info consent form.

**Step 3 — Paste token:** links to `https://huggingface.co/settings/tokens`. Masked entry field (unmasked on focus). Token validated on keyrelease: must start with `hf_` and be ≥20 chars before Next is enabled.

**Step 4 — Download (~1.5 GB):** launches `diarization_handler.download_model()` in a background thread. Progress bar (indeterminate → determinate). Back/Cancel disabled during download. On success: saves token via `config_save_callback`, enables "Finish" button. On failure: shows error with specific guidance for 401/403/connection errors, re-enables Try again / Back.

### Key Methods:
- `_on_token_changed()` — validates token format on keyrelease, enables/disables Next
- `_start_download()` — launches background thread; progress fed via `_download_progress(msg, percent)` scheduled via `win.after()`
- `_download_finished(success, message)` — handles completion on main thread
- `_on_next()` / `_on_back()` / `_on_cancel()` — navigation; cancel confirms with user unless download already succeeded

### Module-Level Convenience Functions:
- `run_hf_setup_wizard(parent, config_save_callback)` → token str or None — blocks via `wait_window()`
- `show_already_configured(parent)` — info dialog when already set up
- `show_setup_required_prompt(parent)` → bool — yes/no dialog before opening wizard

---

## Word-Based Transcript Editing Suite (April 2026)

Four files that together provide a Microsoft Word-based alternative to in-app transcript editing for long recordings where Tkinter's limitations make structural editing impractical.

---

## transcript_cleanup_dialog.py (~400 lines)
- **Purpose:** Post-transcription options dialog — cleanup + speaker ID options, then a routing choice to Thread Viewer or Microsoft Word.
- **Modality:** Non-modal (intentional).
- **Dependencies:** tkinter, threading, transcript_cleaner (lazy), diarization_handler (lazy, conditional)
- **Called By:** `document_fetching.py` — fires after faster-whisper transcription completes for **both** YouTube-sourced audio and local audio files.
- **Entry Point:** `show_transcript_cleanup_dialog(parent, entries, audio_path, config, result_callback)`

### Result dict schema (always a dict, never None):
```python
{
    "entries":          List[Dict],   # cleaned entries (absent when skipped=True)
    "audio_path":       str or None,
    "speaker_ids":      List[str],
    "diarization_used": bool,
    "warnings":         List[str],
    "routing":          str,          # "thread_viewer" or "word"
    "skipped":          bool,         # True when user clicked Skip or closed dialog
}
```

### Routing flow:
- After cleanup completes (`_on_complete`) or user clicks Skip (`_on_skip`), the Run/Skip button row is replaced by **"Thread Viewer"** and **"Microsoft Word"** buttons via `_show_routing_choice(result)`.
- The chosen button injects `routing` into the result dict and fires `result_callback`.
- Closing via the × button fires the callback with `{skipped: True, routing: "thread_viewer"}`.
- Window is blocked during active cleanup (`_on_close` is a no-op while `_running`).

### Feature Flag:
```python
PYANNOTE_ENABLED = False
```
Controls voice detection availability. All three radio buttons are always built; when `False`, voice radio is disabled with a note (no "Set up" link shown).

---

## word_editor_panel.py (~550 lines)
- **Purpose:** Non-modal always-on-top panel for speaker assignment while editing a transcript in Microsoft Word alongside DocAnalyser.
- **Dependencies:** tkinter, pywin32 (win32com — optional; panel degrades gracefully if Word is not open)
- **Called By:** `document_fetching._launch_word_path()`, `thread_viewer._open_word_suite()`
- **Entry Point:** `show_word_editor_panel(parent, doc_id, entries, audio_path, docx_path, config, on_save_callback)`

### Key behaviours:
- **COM polling** (`_poll_word_cursor`, every 500 ms) — reads the paragraph under the Word cursor, matches it to an entry by timestamp, highlights the corresponding row in the panel list. Badge shows “● Word linked” / “○ Word not linked”.
- **Per-paragraph assignment** (`_assign(name)`) — navigates Word to the correct paragraph via `_word_update_para_speaker()` using the `[MM:SS]` timestamp as an anchor (not `Selection`, so it works regardless of where the cursor is). Replaces `[SPEAKER_A]` with `[Chris]` inline.
- **Bulk substitution** (`_apply_all_names()`) — runs `wdReplaceAll` across the whole document for each SPEAKER_X → real name pair entered in the name fields.
- **Save-back** (`_save_to_docanalyzer()`) — reads the edited .docx via `_parse_docx()`, reconstructs entries using `[MM:SS]` as anchors, calls `update_transcript_entries` and fires `on_save_callback`.
- **Navigation** — "Prev / Next unresolved" buttons jump to the next paragraph without a confirmed speaker assignment.
- **Header demotion** (`_demote_merged_headers_in_word()`) — when the user merges two paragraphs in Word by deleting the line break between them, the embedded timestamp/speaker token from the second paragraph is demoted to plain `{MM:SS}` format. **Workflow requirement:** the user must click **Refresh ¶** in the Speaker Panel after merging in Word for this function to run. This is a workflow step, not a code issue.

### ⚠️ Pending re-implementation (lost in session revert, April 2026):
Two features were implemented but wiped when the WH_MOUSE_LL right-click hook was fully reverted from backup:
- **Speaker name persistence** — `_save_speaker_names()` should be called from `_assign()` and `_on_close()` (not only from the bulk apply button). Save logic should merge into existing `word_speaker_names` metadata rather than overwrite.
- **Dynamic "+ Add speaker" button** — small secondary button that adds a new name-field row for recordings with more than two speakers.
Both need to be re-applied in the next `word_editor_panel.py` session.

### Paragraph format expected in the .docx:
```
[MM:SS]  [Speaker name]:  paragraph text…
```
The `[MM:SS]` token is the stable anchor used for both COM navigation and save-back parsing.

---

## transcript_word_toolkit.py (~180 lines)
- **Purpose:** Exports DocAnalyser transcript entries to a .docx file in the format expected by `word_editor_panel.py`.
- **Dependencies:** python-docx
- **Called By:** `document_fetching._launch_word_path()`, `thread_viewer._edit_in_word()`, `thread_viewer_save._save_source_only()`
- **Entry Point:** `export_transcript_to_word(filepath, entries, title, audio_path, metadata, show_messages)` → `(bool, str)`

### Export format:
- Title heading + Document Information block (includes `Audio file:` line read by `launch_transcript.py`).
- Usage note reminding the user to keep `[MM:SS]` timestamps intact.
- One Word paragraph per transcript entry: `[MM:SS]  [Speaker]:  body text`
  - `[MM:SS]` — 8pt grey plain text (not a hyperlink — no URL scheme, no macros, no Word security warnings)
  - `[Speaker]:` — bold
  - Body text — normal weight
- The audio path is written into the Document Information block so `launch_transcript.py` can recover it later without user input.

---

## companion_player.py (~300 lines)
- **Purpose:** Standalone lightweight audio player designed to sit alongside Microsoft Word while the user edits a transcript. The user reads timestamps in the Word document and types them into the "Jump to" field to seek.
- **Dependencies:** pygame (for playback), tkinter
- **Launch:** `python companion_player.py "C:/path/to/audio.m4a"` — audio path passed as `sys.argv[1]`; falls back to a file picker if omitted.
- **Called By:** `thread_viewer._open_word_suite()` and `document_fetching._launch_word_path()` — launched as a background subprocess with `CREATE_NO_WINDOW` (no console window).
- **Features:** Playback bar (+/-30s, +/-10s, Play/Pause), draggable slider, "Jump to" field for manual timestamp entry, "Open file" button for switching audio.

---

## launch_transcript.py (~60 lines)
- **Purpose:** Opens a DocAnalyser transcript .docx in Word AND starts the companion audio player in one command, by reading the audio path from the Document Information block.
- **Usage:** `python launch_transcript.py "C:/path/to/transcript.docx"` — designed for users who want to re-open a previously exported document without going through DocAnalyser.
- **Note:** The in-app Word path (`_open_word_suite`) does not use this script — it starts Word and the player directly with the known audio path. `launch_transcript.py` is retained as a standalone convenience tool.

---

## document_fetching.py — Word path integration (April 2026)

### `_apply_cleanup_result(result, doc_id)` — updated:
- `result` is always a dict (never `None`). Always contains `"routing"` (`"thread_viewer"` or `"word"`) and `"skipped"` (bool).
- When `routing == "word"`: calls `_launch_word_path(doc_id, entries, audio_path)` after persisting cleaned entries.
- `audio_file_path` is now stored in `current_document_metadata` under the key `audio_file_path` (matching what `_resolve_audio_path()` looks for) AND persisted to the library record via `update_document_metadata()`.

### `_launch_word_path(doc_id, entries, audio_path)` — new:
- Prompts for .docx save location → calls `export_transcript_to_word` → opens Word → starts companion player → opens `WordEditorPanel`.

### `_on_word_edit_saved(updated_entries, doc_id)` — new:
- Callback from `WordEditorPanel` save button. Updates `current_entries`, `current_document_text`, library record.

### `_handle_file_result` — fixed (April 2026):
- `current_document_type` now set from `doc_type` parameter (not hardcoded `"file"`), so audio transcriptions are correctly typed as `"audio_transcription"`.
- `add_document_to_library` now includes `metadata={"audio_file_path": ..., "title": ..., "fetched": ...}` so the audio path is persisted at creation time.
- Cleanup dialog is now offered for local audio file transcriptions (was previously YouTube-only).
- Text conversion now uses `entries_to_text_with_speakers` for audio transcriptions.
