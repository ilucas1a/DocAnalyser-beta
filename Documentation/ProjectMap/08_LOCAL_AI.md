# 08 - Local AI (Ollama Integration)

## Overview
Four modules providing complete local AI capability via Ollama, allowing users to run AI models on their own hardware with no API costs or data leaving their computer.

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

## local_ai_manager.py (~1000 lines)
**Purpose:** Comprehensive backend for local AI — system detection, model database, Ollama API management, smart model selection, and pre-flight document checks.

### Data Classes & Enums
- **`ModelCapability`** — Enum: MINIMAL / BASIC / STANDARD / ADVANCED / PROFESSIONAL
- **`SystemSpecs`** — Dataclass: RAM, GPU, VRAM, has_nvidia/amd/apple_silicon, capability_level, `to_display_string()`
- **`ModelInfo`** — Dataclass: name, ollama_id, size_gb, ram/vram requirements, context_window, description, quality_tier, is_fast, supports_vision

### MODEL_DATABASE (Dict[str, ModelInfo])
Curated model catalog with accurate requirements:
- **Small:** llama3.2:1b, llama3.2:3b, phi3:mini, gemma2:2b
- **Medium:** llama3.1:8b, mistral:7b, qwen2.5:7b, gemma2:9b
- **Large:** llama3.1:70b-q4_0, qwen2.5:14b
- **Vision:** llava:7b, llama3.2-vision:11b
- **Specialized:** deepseek-r1:7b

### System Detection Functions
- **`detect_system_specs()`** — Uses psutil for RAM, nvidia-smi / WMI / PowerShell for GPU, special Apple Silicon handling (shared memory, ~75% usable for ML).
- **`_detect_gpu()`** — Multi-strategy GPU detection: nvidia-smi → WMI → PowerShell fallback.
- **`_determine_capability_level(ram, vram, apple_silicon)`** — Maps hardware to capability enum.

### OllamaManager Class
API communication with Ollama server:
- `is_installed()` — Checks common paths per platform
- `is_running()` — HTTP check to /api/tags
- `start_server()` — Launches `ollama serve`, polls for readiness
- `get_installed_models()` — Lists models via API
- `pull_model(model_id, progress_callback)` — Streaming download with progress
- `delete_model(model_id)` — Removes model
- `get_model_info(model_id)` — Detailed model metadata
- `openai_compatible_url` property — Returns /v1 endpoint for drop-in OpenAI compatibility

### Smart Model Selection
- **`get_compatible_models(specs)`** — Filters MODEL_DATABASE by system specs, adds compatibility notes (✅ Recommended / ✅ GPU accelerated / ⚠️ CPU mode / ⚠️ Marginal), sorts by recommendation priority.
- **`get_recommended_model(specs)`** — Returns single best model for system.

### Pre-Flight Checks
- **`estimate_tokens(text)`** — ~3.5 chars per token heuristic
- **`check_document_fits(text, model_info)`** — Validates doc fits in context window (reserves 2500 tokens for prompt/response), returns utilization percentage.
- **`recommend_model_for_document(text, specs)`** — Finds smallest compatible model for a specific document.

### High-Level LocalAIManager Class
- `check_readiness()` — Full status check (installed → running → models → specs)
- `get_available_models_for_dropdown()` — Formatted list for UI
- `get_recommended_models_to_download()` — System-aware suggestions
- `pre_flight_check(document_text, model_id)` — Combined readiness + document fit check

### Convenience Functions
- `quick_check()` — One-call readiness test
- `get_openai_compatible_url()` — Returns localhost:11434/v1
- `get_optimal_chunk_size(model_id)` — Maps context window to chunk size (tiny/small/medium/large)
- `get_model_context_window(model_id)` — Lookup with partial name matching fallback

**Dependencies:** `os`, `sys`, `json`, `subprocess`, `shutil`, `platform`, `requests`, `psutil`, `pathlib`, `dataclasses`, `enum`

---

## local_ai_setup_dialog.py (~600 lines)
**Purpose:** Setup wizard dialog guiding users through Ollama installation, server startup, and model download.

**Class: `LocalAISetupDialog`**

**UI Sections:**
1. **System Specs** — Auto-detected RAM/GPU/capability display
2. **Status** — Three-step checklist: Ollama installed → server running → models available. Each with action button (Install/Start/Download).
3. **Available Models** — Treeview showing installed (✅) and downloadable (⬇️) models with compatibility notes, system-aware filtering.
4. **Actions** — Download Selected, Delete Selected, Refresh, Test Connection, Open Ollama Website

**Key Methods:**
- `_run_initial_check()` — Background thread detects specs, then cascading status checks
- `_check_ollama_status()` — Checks installation → running → models in sequence
- `_populate_model_list(installed_models)` — Merges installed + compatible models from database
- `_download_selected_model()` — Threaded download with indeterminate progress bar
- `_test_connection()` — Sends test prompt via OpenAI-compatible endpoint

**Dependencies:** `tkinter`, `threading`, `webbrowser`, `local_ai_manager`

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

**Note:** This module has its own independent system detection and model catalog, separate from `local_ai_manager.py`. Some duplication exists between the two.

**Dependencies:** `tkinter`, `subprocess`, `threading`, `webbrowser`, `platform`

---

## Cross-Module Relationships
```
Main.py (DocAnalyzerApp)
  ├── inherits LocalAIMixin (local_ai_dialogs.py)
  │     ├── uses ai_handler.check_ollama_connection()
  │     └── uses local_ai_manager (for connection checking)
  ├── can open LocalAISetupDialog (local_ai_setup_dialog.py)
  │     └── uses local_ai_manager (full backend)
  └── can open LocalModelManagerDialog (local_model_manager.py)
        └── independent implementation (CLI-based)
```

## Key Design Notes
- **Two parallel implementations:** `local_ai_manager.py` uses the Ollama HTTP API; `local_model_manager.py` uses CLI commands. Both detect system specs independently.
- **OpenAI compatibility:** Ollama's /v1 endpoint allows drop-in replacement for cloud AI providers in ai_handler.py.
- **Progressive disclosure:** Simple "Run via Local AI" button → auto-detection → setup wizard only if needed.
- **System-aware:** All model recommendations filtered by detected RAM/GPU capability.
