# Project Map: Core Configuration Files

## version.py
- **Purpose:** Central version tracking and update checking
- **Current Version:** 1.2.0 (beta), BUILD_DATE 2025-01-01
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
  4. **AI model lists** — DEFAULT_MODELS for 6 providers (OpenAI, Anthropic, Google, xAI, DeepSeek, Ollama)
  5. **Constants** — chunk sizes, OCR presets, audio formats, transcription engines, dictation modes, vision-capable providers

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
