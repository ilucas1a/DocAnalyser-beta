# 11 - Main.py (Application Core)

## Overview
**File:** Main.py (~4,619 lines, ~207KB)
**Purpose:** Central application class, UI construction, and remaining business logic not yet extracted into mixins.

---

## Architecture Pattern

DocAnalyserApp uses **multiple inheritance with mixin classes** to keep Main.py manageable:

```
DocAnalyserApp(
    SettingsMixin,              # settings_manager.py — settings dialogs, config UI
    LocalAIMixin,               # local_ai_dialogs.py — Ollama connection/setup
    DocumentFetchingMixin,      # document_fetching.py — YouTube/Substack/Twitter/file fetch
    OCRProcessingMixin,         # ocr_processing.py — OCR orchestration, web fetching
    LibraryInteractionMixin,    # library_interaction.py — library UI, bulk processing
    ViewerThreadMixin,          # viewer_thread.py — thread viewer management
    ProcessOutputMixin,         # process_output.py — AI processing, output saving
    ExportUtilitiesMixin,       # export_utilities.py — export, app lifecycle
    SmartLoadMixin,             # smart_load.py — URL auto-detection, multi-doc
    VisionProcessingMixin       # vision_processing.py — image/vision processing
)
```

All mixins use `self.xxx` to access the main app's state, which is initialized in `__init__`.

---

## Startup & Initialization (lines 1–465)

### Pre-Import Safety (~lines 1–100)
- `_NullWriter` / `_SafeWriter` — safe stdout/stderr wrappers for frozen .exe (prevents crashes when console is unavailable)
- Redirects stdout/stderr before any imports
- `safe_print()` — replacement for `print()` that never crashes

### Import Block (~lines 95–400)
- Standard library imports
- Tkinter + optional tkinterdnd2 (drag-and-drop)
- All mixin imports (settings_manager, local_ai_dialogs, document_fetching, etc.)
- Lazy module loaders: `get_ocr()`, `get_audio()`, `get_doc_fetcher()`, `get_ai()`, `get_formatter()`
- Safe fallback stubs for optional modules (context_help, first_run_wizard, local_ai_manager)
- YouTube utility imports with smart URL/ID detection helpers

### `__init__(self, root)` (~lines 467–565)
Core state initialization:
- **Document State:** `current_document_id`, `current_document_text`, `current_entries`, `current_document_source`, `current_document_type`, `current_document_class`, `current_document_metadata`
- **Thread State:** `current_thread = []`, `thread_message_count = 0`
- **Processing State:** `processing_thread`, `cancel_flag`, `is_processing`
- **Config:** loads via `load_config()`, `load_models()`, `load_prompts()`
- **Managers:** `attachment_manager = AttachmentManager()`, `response_saver = ResponseAutoSaver()`, `universal_saver = UniversalDocumentSaver()`
- **UI Setup:** calls `setup_ui()`, configures DND, schedules startup checks
- **Viewer Tracking:** `_thread_viewer_windows = []`

---

## UI Styling (lines 565–670)

- `configure_button_style()` — ttk style configuration with high-contrast colors, hover effects
- `style_dialog(dialog)` / `apply_window_style(window)` — consistent dialog styling
- `_adjust_font_size(delta)` — Ctrl+/Ctrl- font size adjustment (persisted to config)
- `_create_menu_bar()` — File menu with App Overview, System Check, Updates, Setup Wizard, Diagnostics

---

## Startup Checks (lines 670–880)

- `_show_app_overview()` — context_help overview dialog
- `_show_system_check()` — setup_wizard launch
- `_check_for_updates()` — manual update check via update_checker
- `_reset_and_show_wizard()` — resets first-run wizard
- `_startup_update_check()` — background update check, shows notification if available
- `_startup_auto_refresh_models()` — auto-refreshes model lists if stale (>30 days), shows "new models" notification
- `_run_startup_checks()` — orchestrates: first-run wizard → local AI banner → update check → model refresh
- `_show_local_ai_banner()` / `_dismiss_local_ai_banner()` — promotional banner for local AI
- `_open_local_ai_setup()` / `_open_local_model_manager()` — launches local AI dialogs
- `_save_update_preference()` — saves auto-update check setting
- `_export_diagnostics()` — comprehensive diagnostic report: system info, config, dependencies, GPU, library stats

---

## Conversation Threading (lines 1005–1260)

- `add_message_to_thread(role, content)` — adds message with timestamp, manages context window (trims old exchanges if >20)
- `update_thread_status()` — updates status bar with thread info + exchange count
- `clear_thread()` — resets thread state
- `check_active_thread_before_load(new_doc_title)` → bool — warns user about unsaved thread, offers save/discard/cancel
- `clear_preview_for_new_document()` — resets UI for new document
- `build_threaded_messages(new_prompt)` → list — constructs full message history for AI API call:
  - System message with document context
  - Thread history (user/assistant pairs)
  - New user prompt
  - Attachment text (if any)

---

## UI State Management (lines 1258–1430)

- `set_status(msg, include_thread_status)` — status bar with optional thread info
- `update_button_states()` — enables/disables buttons based on current state
- `update_view_button_state(has_document, has_conversation)` — smart View Source / View Thread / View Both button text and state
- `on_viewer_mode_change(new_mode)` — callback from thread viewer when mode changes
- `validate_youtube_url(url_or_id)` → tuple — validates and extracts YouTube video ID
- `validate_file_path(filepath)` → tuple — validates file exists and extension supported
- `convert_spreadsheet_to_text(file_path)` → tuple — XLSX/CSV/TSV to text conversion
- `validate_web_url(url)` → tuple — basic URL validation

---

## Model Management (lines 1522–1608)

- `refresh_models_from_apis()` — full model refresh: fetches from all providers via model_updater, saves to models.json, rebuilds dropdowns, shows summary dialog with new/removed models

---

## Main UI Construction (lines 1608–2700)

### `setup_ui()` (~lines 1608–1744)
- Creates main frame with dark background
- Top bar: provider/model dropdowns, API key, Settings button, Costs button, Library button
- Universal input area (multi-line text input)
- Prompt frame
- Status bar

### `setup_universal_input(parent)` (~lines 1744–1911)
- Multi-line text input with placeholder text
- **Smart buttons row:** Load, Run, Browse (split button with dropdown)
- Context-sensitive action buttons (View Source, View Thread, etc.)
- DND (drag-and-drop) zone overlay
- Input text expansion (auto-grows with content)

### `setup_context_button_frame(parent)` (~lines 1911–1976)
- Dynamic button bar that changes based on loaded content
- Buttons: View Source, View Thread, New Branch, Save Thread, Export, TurboScribe

### `update_context_buttons(file_type)` (~lines 1976–2034)
- Shows/hides context buttons based on document type and state

### `setup_youtube_tab / setup_file_tab / setup_audio_tab / setup_web_tab` (~lines 2034–2113)
- Legacy tab-based input (now unified into universal input)

### File Browsing (~lines 2113–2430)
- `browse_universal_file()` — file dialog with smart extension filtering
- `_auto_load_after_browse(filepath)` — auto-processes file after browse
- `browse_mode_selected(mode)` — handles Browse dropdown options (File, Folder, File Explorer)
- `_position_window_left_half(window_type, delay_ms)` — positions File Explorer on left half of screen
- `open_file_explorer()` — opens OS File Explorer positioned for side-by-side use

### Placeholder & Input Management (~lines 2432–2600)
- `setup_placeholder_text()` / `_set_initial_placeholder()` / `update_placeholder(mode)` — context-sensitive placeholder text
- `on_entry_focus_in/out(event)` — placeholder show/hide on focus

### Drag-and-Drop (~lines 2503–2700)
- `on_drag_enter/leave(event)` — visual feedback
- `on_drop(event)` — handles dropped files, URLs, text
- `_parse_dropped_items(dropped)` → list — parses tkinterdnd2 drop data (handles quoted paths, URLs)
- `_process_dropped_item(item)` → str — normalizes dropped item (file path, URL, .url shortcut)

---

## Prompt Frame (lines 2700–3050)

### `setup_prompt_frame(main_frame)` (~lines 2702–2851)
- Prompt selector dropdown (hierarchical, built by prompt_dropdown_builder)
- Prompt text area (auto-expanding)
- Buttons: Prompts Library, Local AI

### Button Highlighting (~lines 2851–2980)
- `_update_load_button_highlight()` — green highlight when input has loadable content
- `_update_run_button_highlight(has_document)` — green highlight when ready to process

### Input Auto-Expansion (~lines 2901–3010)
- `_auto_expand_input(event)` — grows input text widget with content (3→10 lines)
- `_auto_expand_prompt_text(event)` — grows prompt text widget (3→8 lines)
- `_adjust_window_height(height_diff)` — adjusts window height for expansion

### `on_prompt_select(event)` (~lines 3010–3051)
- Loads selected prompt text, skips separators and headers

---

## AI Provider/Model UI (lines 3051–4010)

### `setup_ai_selector_frame / setup_help_button` (~lines 3057–3072)
- Provider and model dropdown construction

### Web Response Banner (~lines 3072–3380)
- `setup_web_response_banner(main_frame)` — creates collapsible banner for web search context
- `show_web_response_banner(context)` — displays when AI response references web sources
- `capture_web_response()` — **190+ lines** — sophisticated web content capture: extracts URLs from AI response, fetches page content, creates combined document with AI response + web sources, saves to library

### `_load_document_by_id(doc_id)` (~lines 3327–3380)
- Loads document by ID into main window with full state setup

### `on_provider_select(event)` (~lines 3398–3466)
- Handles provider dropdown change: updates model list, API key field, chunk size (auto-adjusts for Ollama), saves selection

### `_refresh_ollama_models(show_errors)` (~lines 3466–3488)
- Refreshes Ollama model list from local server

### Model Info & Guide (~lines 3488–3960)
- `_load_model_info()` / `_save_model_info(model_info)` — model_info.json persistence
- `_generate_model_description(model_id, provider)` → str — generates description from model name patterns
- `_create_placeholder_info(model_id, friendly_name)` → dict — creates default model info
- `_show_model_guide()` — **320+ lines** — comprehensive model selection guide dialog with: system recommendations, model cards (context window, pricing, speed, capabilities), filter by provider, recommended badges
- `_update_model_row(labels, info)` — updates model card display
- `_select_recommended_model()` / `_select_default_or_recommended_model()` — auto-selects appropriate model

---

## Audio Processing (lines 4010–4250)

- `save_api_key()` — saves API key for current provider
- `browse_audio_file()` — file dialog for audio files
- `transcribe_audio()` — starts audio transcription
- `_handle_audio_segments(segments_batch)` — progressive display of transcription segments
- `_segment_callback_wrapper(segments_batch)` — thread-safe wrapper for progressive display
- `_transcribe_audio_thread()` — threaded audio transcription via audio_handler
- `_handle_audio_result(success, result, title)` — displays result, saves to library

---

## Facebook & Substack Handling (lines 4254–4619)

- `fetch_facebook(url)` — starts threaded Facebook video fetch + transcription
- `_handle_facebook_result(success, result, title, url)` — processes Facebook result
- `_handle_facebook_error(error_msg)` — Facebook error dialog
- `_handle_substack_result(success, result, title, content_type, url)` — handles Substack article/podcast/both
- `_download_and_transcribe_substack(url, media_info, title, content_type)` — Substack audio pipeline
- `_transcribe_substack_audio(audio_path, title, url, content_type, article_text)` — transcription of Substack audio

---

## Entry Point

```python
if __name__ == "__main__":
    root = tk.Tk()
    app = DocAnalyserApp(root)
    root.mainloop()
```

---

## Key Design Notes

1. **Mixin Pattern:** 10 mixin classes keep Main.py from being even larger (~4,600 lines now, down from potentially 15,000+)
2. **Lazy Imports:** Heavy modules (OCR, audio, AI) loaded on first use to speed startup
3. **Thread Safety:** All long-running operations (fetch, transcribe, AI calls) run in background threads with `root.after()` for UI updates
4. **Universal Document Saver:** All fetch handlers automatically save to library via `universal_saver`
5. **Progressive Display:** Audio transcription shows results in real-time as segments complete
6. **State Machine:** Document state tracks current doc, thread, viewer windows, processing status
7. **Safe Console:** `_NullWriter`/`_SafeWriter` prevent crashes in frozen .exe when no console available
