# 08 - Local AI (Ollama Integration)

## Overview
Two modules providing local AI capability via Ollama, allowing users to run AI models on their own hardware with no API costs or data leaving their computer.

**Note:** local_ai_manager.py and local_ai_setup_dialog.py were documented in an earlier version of this map but do not exist in the current codebase. Their functionality is handled by local_ai_dialogs.py (mixin) and local_model_manager.py (standalone dialog).

---

## local_ai_dialogs.py (~350 lines)
**Purpose:** Mixin class providing Local AI connection/setup dialog methods for the main app.

**Class: `LocalAIMixin`** (mixin for DocAnalyzerApp)

**Key Methods:**
- **`run_via_local_ai()`** — Entry point for local AI processing. Checks Ollama connection, shows setup dialog if not connected, auto-switches provider to "Ollama (Local)", refreshes models, then calls `process_document()`.
- **`_show_local_ai_dialog(connected, status, models, base_url)`** — Modal dialog showing connection status (✅/⚠️/❌ indicators), context-sensitive instructions (different text for "connected but no models" vs "not connected"), clickable link to ollama.com/download, and buttons for Launch & Connect / Local AI Guide / Continue / Cancel. Returns 'continue', 'cancel', or 'open_guide'.
- **`_show_ollama_launching_dialog(parent_dialog, ollama_path, base_url, ...)`** — Launches Ollama executable and auto-polls for connection every 3 seconds. Auto-continues when connected with models. Searches common Windows install paths, falls back to file dialog. Uses threading to launch app in background.

**Dependencies:** `tkinter`, `ai_handler.check_ollama_connection`

**Patterns:** Mixin pattern, polling with `dialog.after()`, background threading for launch, dynamic UI updates via `StringVar`.

---

## local_model_manager.py (~700 lines)
**Purpose:** Standalone GUI for managing Ollama models — view installed, download with system-tier recommendations, delete models.

### System Detection (Independent Implementation)
- `get_system_ram_gb()` — Windows (ctypes MEMORYSTATUSEX), macOS (sysctl), Linux (/proc/meminfo)
- `get_nvidia_gpu_info()` — nvidia-smi query
- `get_system_tier()` — Returns tier (minimal/basic/standard/high/extreme), RAM, GPU info, description

### RECOMMENDED_MODELS List
Separate model catalog (tuples, not dataclasses):
- **Lightweight:** llama3.2:1b, gemma2:2b, qwen2.5:1.5b, phi3:mini
- **Balanced:** llama3.2:3b, qwen2.5:3b, mistral:7b, llama3.1:8b, gemma2:9b, qwen2.5:7b
- **Powerful:** llama3.1:70b, qwen2.5:32b, mixtral:8x7b
- **Specialized:** deepseek-coder:6.7b, codellama:7b, llava:7b, llava:13b

### Ollama Utilities (Independent Implementation)
- `is_ollama_installed()` — Checks `ollama --version`
- `is_ollama_running()` — urllib check to localhost:11434
- `get_installed_models()` — Parses `ollama list` CLI output
- `delete_model(model_name)` — Runs `ollama rm`

### LocalModelManagerDialog Class
- **System Banner** — Tier icon, RAM/GPU info, model count recommendation
- **Installed Models** — Treeview with refresh and delete
- **Download New Models** — Filter dropdown (recommended/all compatible/all), model combo with indicators (✓/~/⚠️), description display, RAM warnings, progress bar
- **Download** — Threaded subprocess running `ollama pull`, parses progress percentage from stdout

**Note:** This module has its own independent system detection and model catalog, separate from the system detection in `dependency_checker.py` and `system_detector.py`. Some duplication exists across these modules.

**Dependencies:** `tkinter`, `subprocess`, `threading`, `webbrowser`, `platform`

---

## Cross-Module Relationships
```
Main.py (DocAnalyzerApp)
  ├── inherits LocalAIMixin (local_ai_dialogs.py)
  │     └── uses ai_handler.check_ollama_connection()
  └── can open LocalModelManagerDialog (local_model_manager.py)
        └── independent implementation (CLI-based)
```

## Key Design Notes
- **OpenAI compatibility:** Ollama's /v1 endpoint allows drop-in replacement for cloud AI providers in ai_handler.py.
- **Progressive disclosure:** Simple "Run via Local AI" button → auto-detection → setup dialog only if needed.
- **System-aware:** All model recommendations filtered by detected RAM/GPU capability.
