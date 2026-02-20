# Project Map: AI Provider & Model Management

## ai_handler.py (1,681 lines)
- **Purpose:** Central hub for ALL AI API calls — text analysis, vision/OCR, and PDF processing
- **Dependencies:** os, datetime, pathlib, openai, requests, google.generativeai, base64, json
- **Called By:** Main.py (for document analysis), ocr_handler.py (for cloud OCR), vision_processing.py

### Cost Calculation Functions:
- `_log_cost(provider, model, cost, document_title, prompt_name)` — appends to cost_log.txt
- `_calculate_openai_cost(model, prompt_tokens, completion_tokens)` → float
- `_calculate_anthropic_cost(model, input_tokens, output_tokens)` → float
- `_calculate_gemini_cost(model, input_tokens, output_tokens)` → float
- `_calculate_xai_cost(model, prompt_tokens, completion_tokens)` → float
- `_calculate_deepseek_cost(model, prompt_tokens, completion_tokens)` → float

### Core Text API Calls:
- `call_ai_provider(provider, model, messages, api_key, ...)` — main dispatcher, routes to provider-specific functions
- `_call_openai(model, messages, api_key, ...)` — OpenAI chat completion
- `_call_anthropic(model, messages, api_key, ...)` — Anthropic messages API
- `_call_gemini(model, messages, api_key, ...)` — Google Generative AI
- `_call_xai(model, messages, api_key, ...)` — xAI (uses OpenAI-compatible API)
- `_call_deepseek(model, messages, api_key, ...)` — DeepSeek (uses OpenAI-compatible API)
- `_call_ollama(model, messages, ...)` — Local Ollama server

### Vision/OCR Functions:
- `check_provider_supports_vision(provider, model)` → bool
- `_optimize_image_for_api(image_path, provider, ...)` — resizes/compresses images for API limits
- `build_ocr_prompt_with_context(text_type, context_hint)` → str — generates OCR instruction prompt
- `call_vision_ai(provider, model, image_path, api_key, ...)` — dispatcher for vision calls
- `_call_openai_vision(model, image_data, media_type, ...)` — OpenAI vision
- `_call_anthropic_vision(model, image_data, media_type, ...)` — Claude vision
- `_call_gemini_vision(model, image_path, prompt, ...)` — Gemini vision
- `_call_xai_vision(model, image_data, media_type, ...)` — Grok vision

### PDF Cloud Processing:
- `check_provider_supports_pdf(provider)` → bool
- `process_pdf_with_cloud_ai(pdf_path, provider, model, api_key, ...)` — routes to provider
- `_process_pdf_with_claude(pdf_path, model, api_key, ...)` — sends PDF to Claude API
- `_process_pdf_with_gemini(pdf_path, model, api_key, ...)` — sends PDF to Gemini API
- `extract_text_from_pdf_cloud_ai(pdf_path, provider, model, api_key, ...)` — text extraction only
- `ocr_with_google_cloud_vision(image_path, api_key, ...)` — dedicated Google Cloud Vision OCR

### Utility Functions:
- `validate_api_key(provider, api_key)` → (bool, str) — tests if key works
- `get_provider_base_url(provider)` → str
- `format_conversation_for_provider(provider, conversation)` → list — adapts message format per provider
- `get_provider_info(provider)` → dict — returns provider capabilities info
- `check_ollama_connection(base_url)` → (bool, str, list) — tests Ollama server
- `get_ollama_models()` → list — fetches locally available Ollama models

---

## model_updater.py (~600 lines)
- **Purpose:** Fetches live model lists from provider APIs and uses AI curation to select the best 5 models per provider
- **Dependencies:** json, logging, requests, openai, google.generativeai
- **Called By:** Main.py (via "Refresh Models" button)

### Key Concepts:
- **AI Curation:** Sends raw model lists to a cheap AI model (gpt-4o-mini or claude-3-5-haiku) with a prompt asking it to pick the best 5 for document analysis
- **Fallback Chain:** API fetch → AI curation → basic pattern-based curation → safe hardcoded defaults
- MAX_MODELS_PER_PROVIDER = 5

### Raw Fetch Functions:
- `fetch_openai_models_raw(api_key)` → (success, models, error) — uses OpenAI API list
- `fetch_anthropic_models_raw(api_key)` → (success, models, error) — tests known model names (no list API)
- `fetch_gemini_models_raw(api_key)` → (success, models, error) — uses genai.list_models()
- xAI and DeepSeek use hardcoded fallbacks (no listing APIs)

### AI Curation Functions:
- `curate_with_openai(raw_models, provider_name, api_key)` → (success, curated, error)
- `curate_with_anthropic(raw_models, provider_name, api_key)` → (success, curated, error)
- `curate_with_gemini(raw_models, provider_name, api_key)` → (success, curated, error)
- `curate_models_with_ai(provider_name, raw_models, available_keys)` — tries each AI provider in order

### Basic Fallback Curation:
- `basic_curate_openai(raw_models)` → list — pattern-based priority selection
- `basic_curate_anthropic(raw_models)` → list
- `basic_curate_gemini(raw_models)` → list

### Main Entry Point:
- `fetch_all_models(config, status_callback)` → dict — orchestrates full refresh for all providers
- `get_safe_fallback_models()` → dict — returns SAFE_FALLBACK_MODELS constant
- `is_vision_capable(provider, model)` → bool

---

## cost_tracker.py (580 lines)
- **Purpose:** API cost tracking, logging, and display dialog
- **Dependencies:** os, datetime, webbrowser, pathlib, tkinter (for dialog)
- **Called By:** Main.py (Costs button in UI)

### Key Functions:
- `calculate_cost(provider, model, input_tokens, output_tokens)` → float
- `get_model_pricing(provider, model)` → dict or None
- `get_cost_log_path()` → Path
- `log_cost(provider, model, cost, document_title, prompt_name)` — writes to cost_log.txt
- `read_cost_log()` → (success, entries, by_provider, by_model, total) — parses log file
- `get_pricing_info()` → str — formatted pricing reference text
- `show_costs_dialog(parent)` — displays Tkinter dialog with cost breakdown
