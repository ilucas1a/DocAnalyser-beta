# DocAnalyser Project Map — Index
**Version:** 1.4.0 (beta) | **Main.py Lines:** ~4,657 | **Total Python Files:** ~74 | **Total Project Lines:** ~36,000+

---

## Map Files

| # | File | Modules Covered | Focus Area |
|---|------|----------------|------------|
| 01 | CORE_CONFIG.md | version.py, config.py | Version tracking, app settings, paths, AI provider lists, constants |
| 02 | AI_PROVIDERS.md | ai_handler.py, model_updater.py, cost_tracker.py, pricing_updater.py, pricing_checker.py | AI API calls (text/vision/PDF), model refresh, cost logging, pricing maintenance |
| 03 | DOCUMENT_PROCESSING.md | ocr_handler.py, ocr_dialog.py, ocr_processing.py, audio_handler.py, transcription_handler.py, vision_processing.py | OCR, audio transcription, vision/image processing |
| 04 | DOCUMENT_MANAGEMENT.md | document_library.py, document_tree_manager.py, document_fetcher.py, document_fetching.py, smart_load.py, save_utils.py, universal_document_saver.py, document_export.py, doc_formatter.py, output_formatter.py, process_output.py, export_utilities.py | Library CRUD, fetching, saving, exporting, AI output handling |
| 05 | UI_DIALOGS_CONVERSATION.md | thread_viewer.py, thread_viewer_branches.py, thread_viewer_copy.py, thread_viewer_markdown.py, thread_viewer_save.py, viewer_thread.py, standalone_conversation.py, branch_picker_dialog.py, dictation_dialog.py, voice_edit_dialog.py, paste_content_dialog.py, chunk_settings_window.py, sources_dialog.py, first_run_wizard.py, setup_wizard.py, transcript_player.py | Thread viewer (refactored into 5 files), conversation UI, all dialogs, transcript playback |
| 06 | PROMPT_MANAGEMENT.md | prompt_manager.py, prompt_dropdown_builder.py, prompt_tree_manager.py, import_export.py | Prompt library (tree + legacy), dropdown builder, .docanalyser ZIP export/import |
| 07 | SETTINGS_SYSTEM_UTILS.md | settings_manager.py, config_manager.py, context_help.py, dependency_checker.py, system_detector.py, update_checker.py, utils.py | Settings dialogs, config persistence, F1 help system, dependencies, updates |
| 08 | LOCAL_AI.md | local_ai_dialogs.py, local_model_manager.py | Ollama integration, system detection, model management |
| 09 | PLATFORM_UTILITIES.md | youtube_utils.py, substack_utils.py, substack_updates.py, twitter_utils.py, facebook_utils.py, video_platform_utils.py, podcast_handler.py, podcast_browser_dialog.py | Platform-specific content fetching, podcast RSS support |
| 10 | REMAINING_MODULES.md | attachment_handler.py, auto_save_responses.py, library_interaction.py, semantic_search.py, tree_manager_base.py | Attachments, auto-save, library UI, semantic search, tree base |
| 11 | MAIN_APP.md | Main.py | Application core, UI construction, startup, state management |
| 12 | DATABASE.md | db_manager.py, db_migration.py, prompt_db_adapter.py, document_db_adapter.py, test_stage_c.py, validate_stage_d.py, validate_stage_g.py | SQLite database layer, migration from JSON, adapter modules, migration validation scripts |

---

## Key Rules

> ### ⚠️ Adding or removing an AI provider?
> **Edit `PROVIDER_REGISTRY` in `config.py` only.** All provider data across the app is derived from it.
> New API providers also need a `_call_xxx()` function in `ai_handler.py`. Nothing else needs touching.
> See `01_CORE_CONFIG.md` for the full field reference and `02_AI_PROVIDERS.md` for the ai_handler.py note.

> ### ⚠️ Looking up a response document’s source/parent document ID?
> Via Web responses store it as `metadata["source_document_id"]`. Other product/processed documents use `metadata["parent_document_id"]`.
> **Always check both:** `doc.get('parent_document_id') or doc.get('source_document_id')`
> Applies in `viewer_thread.py` (2 places) and `library_interaction.py` (`load_document_callback`). See `05_UI_DIALOGS_CONVERSATION.md` for details.

---

## Architecture Overview

```
Main.py (DocAnalyserApp)
├── Inherits 10 Mixin Classes:
│   ├── SettingsMixin (settings_manager.py)
│   ├── LocalAIMixin (local_ai_dialogs.py)
│   ├── DocumentFetchingMixin (document_fetching.py)
│   ├── OCRProcessingMixin (ocr_processing.py)
│   ├── LibraryInteractionMixin (library_interaction.py)
│   ├── ViewerThreadMixin (viewer_thread.py)
│   ├── ProcessOutputMixin (process_output.py)
│   ├── ExportUtilitiesMixin (export_utilities.py)
│   ├── SmartLoadMixin (smart_load.py)
│   └── VisionProcessingMixin (vision_processing.py)
│
├── Core Managers:
│   ├── AttachmentManager (attachment_handler.py)
│   ├── ResponseAutoSaver (auto_save_responses.py)
│   └── UniversalDocumentSaver (universal_document_saver.py)
│
├── AI Backend:
│   ├── ai_handler.py (API calls to 6 providers)
│   ├── model_updater.py (live model refresh)
│   ├── cost_tracker.py (usage logging)
│   └── pricing_updater.py (auto-update pricing from GitHub)
│
├── Database Layer (SQLite):
│   ├── db_manager.py (all SQL, no UI)
│   ├── db_migration.py (one-time JSON → SQLite migration)
│   ├── prompt_db_adapter.py (prompts tree ↔ SQLite)
│   └── document_db_adapter.py (documents tree ↔ SQLite)
│
├── Document Pipeline:
│   │  Input Sources:
│   ├── youtube_utils.py, substack_utils.py, twitter_utils.py
│   ├── facebook_utils.py, video_platform_utils.py
│   ├── podcast_handler.py, podcast_browser_dialog.py
│   ├── document_fetcher.py (local files + web URLs)
│   │  Processing:
│   ├── ocr_handler.py, audio_handler.py, transcription_handler.py
│   │  Storage:
│   ├── document_library.py (CRUD + threads + embeddings)
│   ├── semantic_search.py (chunk-level search)
│   │  Output:
│   ├── document_export.py, doc_formatter.py, output_formatter.py
│   └── save_utils.py
│
├── UI Components:
│   ├── tree_manager_base.py (reusable tree component)
│   ├── document_tree_manager.py (Documents Library)
│   ├── prompt_tree_manager.py (Prompts Library)
│   ├── thread_viewer.py (conversation viewer — refactored into 5 files)
│   │   ├── thread_viewer_branches.py (branch management)
│   │   ├── thread_viewer_copy.py (clipboard operations)
│   │   ├── thread_viewer_markdown.py (markdown rendering)
│   │   └── thread_viewer_save.py (save/export operations)
│   ├── transcript_player.py (audio-synced transcript playback)
│   ├── sources_dialog.py (multi-source input)
│   └── Various dialogs (dictation, voice edit, paste, OCR, etc.)
│
├── Maintenance (developer tools in maintenance/):
│   ├── pricing_checker.py (weekly AI pricing verification via Gemini)
│   ├── push_pricing_update.bat, run_pricing_check.bat
│   ├── setup_weekly_task.ps1 (scheduled task for pricing checks)
│   └── (Planned: help_text_editor.py, message_editor — see Roadmap Enhancements 14–15)
│
├── Migration Validation (root dir, developer-only):
│   ├── test_stage_c.py (prompt migration validation)
│   ├── validate_stage_d.py (document migration validation)
│   └── validate_stage_g.py (folder tree migration validation)
│
├── Installer (Installer/):
│   ├── DocAnalyser.spec (PyInstaller spec)
│   └── DocAnalyser_Setup.iss (InnoSetup installer script)
│
└── System:
    ├── config.py / config_manager.py (settings)
    ├── dependency_checker.py / system_detector.py (hardware)
    ├── update_checker.py (GitHub updates)
    └── context_help.py (F1 key help)
```

---

## AI Providers Supported
1. **OpenAI** (ChatGPT) — gpt-5.1, gpt-4o, gpt-4o-mini, etc.
2. **Anthropic** (Claude) — claude-opus-4-6, claude-sonnet-4-5, etc.
3. **Google** (Gemini) — gemini-2.5-pro, gemini-2.5-flash, etc.
4. **xAI** (Grok) — grok-2-latest, grok-2-vision
5. **DeepSeek** — deepseek-chat, deepseek-reasoner
6. **Ollama** (Local) — user-managed local models

## Content Sources Supported
YouTube, Substack (articles + podcasts), Twitter/X, Facebook (video), Vimeo/Rumble/etc., Web URLs, Local files (PDF/DOCX/TXT/RTF/XLSX/CSV), Audio/Video files (MP3/WAV/M4A/MP4/etc.), Images (OCR), Dictation (microphone), Paste content, Google Sheets, Podcasts (Apple Podcasts + RSS feeds)

## Data Storage
- **Primary:** SQLite database at `%APPDATA%\DocAnalyser_Beta\docanalyser.db` (via db_manager.py)
- **Fallback/Backup:** JSON files retained for backwards compatibility:
  - Config: `%APPDATA%\DocAnalyser_Beta\config.json`
  - Library: `%APPDATA%\DocAnalyser_Beta\document_library.json`
  - Prompts: `%APPDATA%\DocAnalyser_Beta\prompts.json` (v2.0 tree format)
  - Models: `%APPDATA%\DocAnalyser_Beta\models.json`
  - Entries: `%APPDATA%\DocAnalyser_Beta\summaries\doc_<id>_entries.json`
  - Embeddings: `%APPDATA%\DocAnalyser_Beta\embeddings.json`
- Pricing: `pricing.json` (in project dir, auto-updated from GitHub via pricing_updater.py)

---

*Updated: 15 March 2026*
