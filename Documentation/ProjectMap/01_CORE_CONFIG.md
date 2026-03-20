# Project Map: Core Configuration Files

## version.py
- **Purpose:** Central version tracking and update checking
- **Current Version:** 1.4.0 (beta), BUILD_DATE 2026-02-20
- **App Names:** Display="DocAnalyser", Internal="DocAnalyser_Beta"
- **GitHub Repo:** ilucas1a/DocAnalyser-beta
- **Key Functions:**
  - `get_version_string()` — formatted display string (e.g. "v1.2.0 (beta)")
  - `parse_version(version_str)` — parses "1.2.3" → tuple (1,2,3)
  - `compare_versions(v1, v2)` — returns -1/0/1
  - `is_newer_version(remote_version)` — checks if update available
- **Dependencies:** None (standalone)

## config.py
- **Purpose:** All application settings, defaults, paths, and constants
- **Key Responsibilities:**
  1. **Bundled tools setup** — auto-configures PATH for Tesseract, Poppler, FFmpeg when running as .exe
  2. **Data directory management** — cross-platform `%APPDATA%\DocAnalyser_Beta\`
  3. **Default configuration** — API keys, last provider/model, chunk sizes, OCR/audio settings
  4. **PROVIDER_REGISTRY** — single source of truth for all AI provider configuration (see below)
  5. **Derived constants** — DEFAULT_MODELS, VISION_CAPABLE_PROVIDERS, PDF_CAPABLE_PROVIDERS, PDF_SIZE/PAGE_LIMITS, _DEFAULT_KEYS, _DEFAULT_LAST_MODELS — all auto-generated from PROVIDER_REGISTRY
  6. **Other constants** — chunk sizes, OCR presets, audio formats, transcription engines, dictation modes

### ⚠️ PROVIDER REGISTRY — The Single Source of Truth

> **Rule: To add, remove, or modify any AI provider, edit `PROVIDER_REGISTRY` in `config.py` only.**
> All other files derive their provider data from it automatically.
> The only exception is new *API* providers, which also require a `_call_xxx()` function in `ai_handler.py`
> (because that function contains the actual API call code, which cannot be data-driven).

`PROVIDER_REGISTRY` is a dict keyed by provider display name (e.g. `"Anthropic (Claude)"`).
Each entry contains every piece of provider data the app needs:

| Field | Type | Meaning |
|---|---|---|
| `type` | `"api"` \| `"local"` \| `"web"` | Provider category |
| `blocked` | bool | If True, red overlay shown in AI Settings (e.g. Pentagon contracts) |
| `requires_api_key` | bool | Whether an API key is needed |
| `api_key_default` | str or None | Default in `config["keys"]`; None = not stored (web-only) |
| `last_model_default` | str or None | Default in `config["last_model"]`; None = not stored (web-only) |
| `requires_library` | str or None | pip package needed for API calls |
| `signup_url` | str or None | URL for "Get Key" button in AI Settings |
| `signup_domain` | str or None | Short domain label shown alongside signup URL |
| `local_url` | str or None | Base URL for local providers (Ollama) |
| `vision_patterns` | list[str] | Model-name substrings indicating vision capability. Empty = no vision. |
| `pdf_capable` | bool | Whether provider accepts raw PDF bytes |
| `pdf_size_limit` | int or None | Max PDF size in bytes |
| `pdf_page_limit` | int or None | Max PDF pages |
| `web_url` | str or None | URL opened by "Run → Via Web" |
| `web_name` | str | Short display name used in the Via Web dialog |
| `web_notes` | str | Info text shown in the Via Web dialog |
| `web_step3` | str (optional) | Custom step-3 instruction in Via Web dialog. Omit for default "Press Enter or click Send" |
| `default_models` | list[str] | Fallback model list — overridden at runtime by models.json for API providers |

### Files that consume PROVIDER_REGISTRY (no direct provider data):
| File | What it derives |
|---|---|
| `config.py` (itself) | DEFAULT_MODELS, VISION_CAPABLE_PROVIDERS, PDF_CAPABLE_PROVIDERS, PDF_SIZE/PAGE_LIMITS, _DEFAULT_KEYS, _DEFAULT_LAST_MODELS |
| `config_manager.py` | Which providers get a slot in config["keys"] and config["last_model"] during migration |
| `settings_manager.py` | `provider_signup_urls`, `WEB_ONLY_PROVIDERS`, `BLOCKED_PROVIDERS` (all derived at runtime) |
| `ai_handler.py` | `PDF_CAPABLE_PROVIDERS`, `PDF_SIZE_LIMITS`, `PDF_PAGE_LIMITS` (imported from config); `_is_web_only_provider()`; `get_provider_info()` |
| `export_utilities.py` | `provider_info` dict and `step3` instruction in `export_to_web_chat()` |

### Data Paths Defined:
| Constant | Location |
|----------|----------|
| DATA_DIR | `%APPDATA%\DocAnalyser_Beta\` |
| CONFIG_PATH | `config.json` |
| PROMPTS_PATH | `prompts.json` |
| MODELS_PATH | `models.json` |
| LIBRARY_PATH | `document_library.json` |
| SUMMARIES_DIR | `summaries\` |
| OCR_CACHE_DIR | `ocr_cache\` |
| AUDIO_CACHE_DIR | `audio_cache\` |

### AI Providers Supported:
1. OpenAI (ChatGPT) — gpt-5.1, gpt-4o, gpt-4o-mini, etc.
2. Anthropic (Claude) — claude-opus-4-6, claude-sonnet-4-5, etc.
3. Google (Gemini) — gemini-2.5-pro, gemini-2.5-flash, etc.
4. xAI (Grok) — grok-2-latest, grok-2-vision
5. DeepSeek — deepseek-chat, deepseek-reasoner
6. Ollama (Local) — user-managed local models

### Vision-Capable Models:
- OpenAI: gpt-4o, gpt-4-turbo, gpt-4.1, gpt-4.5, gpt-5, o1, o3, o4
- Anthropic: all Claude models
- Google: all Gemini models
- xAI: grok-2-vision, grok-vision
- DeepSeek: NOT vision-capable

### Chunk Size Options:
- Tiny (6K chars) — for local AI with small context
- Small (12K) — best quality
- Medium (24K) — balanced (default)
- Large (52K) — fastest overview

### Transcription Engines:
- OpenAI Whisper (cloud, ~$0.006/min)
- Faster Whisper (local, free)
- AssemblyAI (cloud, speaker diarization, ~$0.00025/min)

### OCR Modes:
- local_first — Tesseract, then Cloud AI fallback
- cloud_direct — send images to AI provider
- cloud_pdf — send PDFs directly to Claude/Gemini

- **Dependencies:** os, sys (stdlib only)
