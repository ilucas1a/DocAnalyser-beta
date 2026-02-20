# Project Map: Settings, System & Utilities

## settings_manager.py (~650 lines)
- **Purpose:** All settings dialogs and configuration UI — **Mixin class** extracted from Main.py
- **Pattern:** `SettingsMixin` — mixed into main app class, uses `self.xxx`
- **Dependencies:** tkinter, config, config_manager, utils, prompt_dropdown_builder, version, context_help
- **Called By:** Main.py (mixed in via inheritance)

### Key Methods:
- `open_settings()` — main settings dialog with AI provider/model, API keys, Ollama config, viewer display settings, chunk/OCR/audio/cache buttons
- `on_provider_select_in_settings(event)` — handles provider switch, auto-adjusts chunk size for Ollama
- `save_api_key_in_settings()` — saves API key for current provider
- `_save_ollama_url()` — saves Ollama server URL
- `_test_ollama_connection()` — tests Ollama server, shows model list or install guidance
- `_is_ollama_installed()` → bool — checks common Windows install paths
- `_show_system_recommendations()` — hardware analysis + model recommendations dialog (uses system_detector)
- `_open_local_ai_guide()` / `_show_guide_in_window(path)` — displays LOCAL_AI_GUIDE.md in styled window
- `save_model_selection()` — saves selected model per provider
- `save_all_settings(window)` — saves all settings including viewer thresholds, closes window
- `open_prompt_manager()` — opens tree-view Prompts Library (falls back to legacy)
- `save_prompt()` — legacy stub
- `refresh_main_prompt_combo()` — rebuilds hierarchical prompt dropdown from disk
- `set_prompt_from_library(name, text)` — callback: loads prompt into main window
- `open_chunk_settings()` — chunk size selection dialog
- `open_ocr_settings()` — OCR mode, text type, language, quality, confidence threshold
- `open_audio_settings()` — transcription engine, API keys, language, diarization, VAD, timestamp interval, whisper model, dictation mode
- `show_tesseract_setup_wizard(parent)` — Tesseract install instructions
- `test_ocr_setup()` — tests OCR availability
- `open_cache_manager()` — cache statistics + clear buttons (OCR, audio, outputs, all)

---

## config_manager.py (~350 lines)
- **Purpose:** Configuration, prompts, and models persistence layer (SAFE version — never destroys user data)
- **Dependencies:** os, sys, json, config, utils
- **Called By:** Main.py, settings_manager.py, and many other modules

### Configuration:
- `ensure_config()` — creates config.json if missing
- `load_config()` → Dict — loads with migration (adds new providers/keys)
- `save_config(cfg)` — atomic write to config.json

### Prompts:
- `_get_bundled_prompts_path()` → str — finds default_prompts.json
- `_is_minimal_defaults(path)` → bool — detects old 3-prompt defaults for auto-upgrade
- `ensure_prompts()` — creates or upgrades prompts.json from bundled defaults
- `load_prompts()` → List[Dict] — handles v2.0 tree format → flat list conversion, **never overwrites on error**
- `save_prompts(prompts)` — saves either tree dict or flat list format

### Models:
- `ensure_models()` / `load_models()` / `save_models(models)` — models.json with timestamp
- `get_models_last_refreshed()` → datetime — when models were last fetched
- `are_models_stale()` → bool — older than 30 days?
- `get_models_age_days()` → int

### Utilities:
- `reset_config()` / `reset_prompts()` / `reset_models()` — reset to defaults
- `get_config_info()` → Dict — paths and existence status
- `backup_config(backup_dir)` → bool — backs up all config files with timestamp
- `restore_config_from_backup(file)` → bool — restores from backup

---

## context_help.py (~350 lines)
- **Purpose:** Right-click contextual help system with popup tooltips and app overview
- **Dependencies:** tkinter, json
- **Called By:** settings_manager.py, Main.py (any widget with `add_help()`)
- **Data Source:** help_texts.json (loaded on import as `HELP_TEXTS` dict)

### Key Exports:
- `HELP_TEXTS` — dict loaded from help_texts.json
- `add_help(widget, title, description, tips)` — registers right-click help on any widget
- `get_help(key)` → dict — retrieves help entry by key
- `show_app_overview(parent)` — displays full app overview window (content from JSON)
- `reload_help_texts()` — reloads from JSON after edits

### Classes:
- `HelpPopup(Toplevel)` — styled popup with title, description, tips, X button; auto-closes when mouse leaves
- `HelpSystem` — manages popup lifecycle, tracks registered widgets

---

## dependency_checker.py (~700 lines)
- **Purpose:** External dependency detection (Tesseract, Poppler, FFmpeg) + hardware/GPU analysis + faster-whisper status
- **Dependencies:** os, sys, subprocess, shutil
- **Called By:** setup_wizard.py, settings_manager.py, system_detector.py

### Dependency Detection:
- `find_tesseract()` / `get_tesseract_status()` → DependencyStatus — checks bundled tools, common paths, PATH
- `find_poppler()` / `get_poppler_status()` → DependencyStatus
- `find_ffmpeg()` / `get_ffmpeg_status()` → DependencyStatus
- `check_all_dependencies()` → Dict — all three at once
- `get_missing_dependencies()` → List — only missing ones

### Hardware Detection:
- `get_system_hardware()` → SystemHardwareInfo — RAM, NVIDIA GPU (name + VRAM), CPU
- `get_lm_studio_recommendations(hardware)` → List[LMModelRecommendation] — suitability for each model
- `get_top_lm_recommendation(hardware)` → best single model

### LM Studio:
- `find_lm_studio()` → (installed, path, version)
- `get_lm_studio_status()` → LMStudioStatus — installed, running, models count

### Faster-Whisper:
- `get_faster_whisper_status()` → FasterWhisperStatus — package, CUDA, downloaded models, recommendations

### Python Packages:
- `check_python_package(name)` → (installed, version)
- `get_optional_packages_status()` → Dict — tkinterdnd2, faster_whisper, pytesseract, pdf2image, PyMuPDF

### System Summary:
- `get_system_summary()` → dict — complete readiness check with feature availability matrix

---

## system_detector.py (~400 lines)
- **Purpose:** Hardware detection and local AI model recommendations (profiles: Basic/Standard/Good/Powerful)
- **Dependencies:** os, platform, subprocess
- **Called By:** settings_manager.py (`_show_system_recommendations`)

### Key Functions:
- `get_system_info()` → Dict — OS, CPU, cores, RAM, GPU (NVIDIA/Intel/AMD detection)
- `get_system_profile(info)` → str — "basic"/"standard"/"good"/"powerful"
- `get_model_recommendations(info)` → Dict — primary models, alternatives, warnings, tips per profile
- `format_system_report(info)` → str — human-readable report with recommendations

### GPU Detection Chain:
- `_detect_nvidia_gpu()` → nvidia-smi
- `_detect_intel_gpu()` → PowerShell WMI (Arc/Iris/UHD)
- `_detect_amd_gpu()` → PowerShell WMI (Radeon)
- `_detect_gpu_windows_wmi()` → fallback generic WMI

---

## update_checker.py (~250 lines)
- **Purpose:** GitHub-based update checking and download
- **Dependencies:** os, sys, json, threading, webbrowser, requests, version
- **Called By:** Main.py (on startup), settings_manager.py

### Key Functions:
- `check_for_updates(timeout)` → UpdateInfo — checks GitHub version.json
- `check_for_updates_async(callback)` → Thread — background check
- `open_download_page(info)` → bool — opens browser to download
- `download_update(info, progress_callback)` → filepath or None
- `should_check_for_updates(config)` → bool
- `create_update_message(info)` → str — user-friendly notification text

### UpdateInfo dataclass:
- available, current_version, latest_version, download_url, changelog, release_date, required, error

---

## utils.py (~350 lines)
- **Purpose:** General utility functions used across the entire application
- **Dependencies:** os, hashlib, json, datetime
- **Called By:** Nearly every module

### File Operations:
- `save_json_atomic(path, data)` — atomic write via tmp + rename
- `save_json(data, path)` / `load_json(path, default)` — basic JSON I/O
- `format_size(bytes)` → str — human-readable (KB/MB/GB)
- `get_directory_size(dir)` → (total_size, file_count)
- `calculate_file_hash(path)` → MD5 hex string
- `safe_filename(text, max_length)` → str
- `get_file_extension(filename)` → str (lowercase, no dot)

### Text Processing:
- `chunk_text(text, chunk_size, overlap)` → list — splits at sentence boundaries
- `chunk_entries(entries, chunk_size)` → list of entry lists — handles oversized entries
- `entries_to_text(entries, include_timestamps, timestamp_interval)` → str — configurable timestamp frequency
- `entries_to_text_with_speakers(entries, timestamp_interval)` → str — speaker-labeled output
- `truncate_text(text, max_length, suffix)` → str

### URL/ID Helpers:
- `extract_youtube_id(url)` → str or None
- `is_valid_url(url)` → bool

### Date/Time:
- `format_timestamp(seconds)` → "MM:SS" or "HH:MM:SS"
- `format_display_date(date_input)` → "DD-Mon-YYYY" — handles multiple input formats
- `get_timestamp()` → ISO format string
- `parse_timestamp(str)` → datetime
