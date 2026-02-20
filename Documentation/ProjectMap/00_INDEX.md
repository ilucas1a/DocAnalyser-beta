# DocAnalyser Project Map — Index
**Version:** 1.2.0 (beta) | **Main.py Lines:** ~4,619 | **Total Python Files:** 65 | **Total Project Lines:** ~30,000+

---

## Map Files

| # | File | Modules Covered | Focus Area |
|---|------|----------------|------------|
| 01 | CORE_CONFIG.md | version.py, config.py | Version tracking, app settings, paths, AI provider lists, constants |
| 02 | AI_PROVIDERS.md | ai_handler.py, model_updater.py, cost_tracker.py | AI API calls (text/vision/PDF), model refresh, cost logging |
| 03 | DOCUMENT_PROCESSING.md | ocr_handler.py, ocr_dialog.py, ocr_processing.py, audio_handler.py, transcription_handler.py, vision_processing.py | OCR, audio transcription, vision/image processing |
| 04 | DOCUMENT_MANAGEMENT.md | document_library.py, document_tree_manager.py, document_fetcher.py, document_fetching.py, smart_load.py, save_utils.py, universal_document_saver.py, document_export.py, doc_formatter.py, output_formatter.py, process_output.py, export_utilities.py | Library CRUD, fetching, saving, exporting, AI output handling |
| 05 | UI_DIALOGS_CONVERSATION.md | thread_viewer.py, viewer_thread.py, standalone_conversation.py, branch_picker_dialog.py, dictation_dialog.py, voice_edit_dialog.py, paste_content_dialog.py, chunk_settings_window.py, sources_dialog.py, first_run_wizard.py, setup_wizard.py | Thread viewer (7K lines), conversation UI, all dialogs |
| 06 | PROMPT_MANAGEMENT.md | prompt_manager.py, prompt_dropdown_builder.py, prompt_tree_manager.py | Prompt library (tree + legacy), dropdown builder |
| 07 | SETTINGS_SYSTEM_UTILS.md | settings_manager.py, config_manager.py, context_help.py, dependency_checker.py, system_detector.py, update_checker.py, utils.py | Settings dialogs, config persistence, help system, dependencies, updates |
| 08 | LOCAL_AI.md | local_ai_dialogs.py, local_ai_manager.py, local_ai_setup_dialog.py, local_model_manager.py | Ollama integration, system detection, model management |
| 09 | PLATFORM_UTILITIES.md | youtube_utils.py, substack_utils.py, substack_updates.py, twitter_utils.py, facebook_utils.py, video_platform_utils.py, turboscribe_helper.py | Platform-specific content fetching |
| 10 | REMAINING_MODULES.md | attachment_handler.py, auto_save_responses.py, library_interaction.py, semantic_search.py, tree_manager_base.py | Attachments, auto-save, library UI, semantic search, tree base |
| 11 | MAIN_APP.md | Main.py | Application core, UI construction, startup, state management |

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
│   └── cost_tracker.py (usage logging)
│
├── Document Pipeline:
│   │  Input Sources:
│   ├── youtube_utils.py, substack_utils.py, twitter_utils.py
│   ├── facebook_utils.py, video_platform_utils.py
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
│   ├── thread_viewer.py (conversation viewer — LARGEST module)
│   ├── sources_dialog.py (multi-source input)
│   └── Various dialogs (dictation, voice edit, paste, OCR, etc.)
│
└── System:
    ├── config.py / config_manager.py (settings)
    ├── dependency_checker.py / system_detector.py (hardware)
    ├── update_checker.py (GitHub updates)
    └── context_help.py (right-click help)
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
YouTube, Substack (articles + podcasts), Twitter/X, Facebook (video), Vimeo/Rumble/etc., Web URLs, Local files (PDF/DOCX/TXT/RTF/XLSX/CSV), Audio/Video files (MP3/WAV/M4A/MP4/etc.), Images (OCR), Dictation (microphone), Paste content, Google Sheets

## Data Storage
- Config: `%APPDATA%\DocAnalyser_Beta\config.json`
- Library: `%APPDATA%\DocAnalyser_Beta\document_library.json`
- Prompts: `%APPDATA%\DocAnalyser_Beta\prompts.json` (v2.0 tree format)
- Models: `%APPDATA%\DocAnalyser_Beta\models.json`
- Entries: `%APPDATA%\DocAnalyser_Beta\summaries\doc_<id>_entries.json`
- Embeddings: `%APPDATA%\DocAnalyser_Beta\embeddings.json`
- Cost Log: `cost_log.txt` (in project dir)

---

*Generated: February 2026*
