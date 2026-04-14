"""
config.py - Configuration and Constants
All application settings, defaults, and paths in one place
"""

import os
import sys

# -------------------------
# Bundled Tools Setup (for packaged executable)
# -------------------------
def setup_bundled_tools():
    """
    Configure paths for bundled tools when running as a frozen executable.
    This adds bundled Tesseract, Poppler, and FFmpeg to PATH so they can be found.
    Should be called early in application startup.
    """
    if not getattr(sys, 'frozen', False):
        return  # Not running as packaged exe, skip
    
    exe_dir = os.path.dirname(sys.executable)
    paths_to_add = []
    
    # Check for bundled FFmpeg
    ffmpeg_paths = [
        os.path.join(exe_dir, '_internal', 'tools', 'ffmpeg', 'bin'),
        os.path.join(exe_dir, 'tools', 'ffmpeg', 'bin'),
    ]
    for path in ffmpeg_paths:
        if os.path.exists(os.path.join(path, 'ffmpeg.exe')):
            paths_to_add.append(path)
            break
    
    # Check for bundled Poppler
    poppler_paths = [
        os.path.join(exe_dir, '_internal', 'tools', 'poppler', 'Library', 'bin'),
        os.path.join(exe_dir, '_internal', 'tools', 'poppler', 'bin'),
        os.path.join(exe_dir, 'tools', 'poppler', 'Library', 'bin'),
        os.path.join(exe_dir, 'tools', 'poppler', 'bin'),
    ]
    for path in poppler_paths:
        if os.path.exists(os.path.join(path, 'pdftoppm.exe')):
            paths_to_add.append(path)
            break
    
    # Check for bundled Tesseract
    tesseract_paths = [
        os.path.join(exe_dir, '_internal', 'tools', 'tesseract'),
        os.path.join(exe_dir, 'tools', 'tesseract'),
    ]
    for path in tesseract_paths:
        if os.path.exists(os.path.join(path, 'tesseract.exe')):
            paths_to_add.append(path)
            # Set TESSDATA_PREFIX to the tessdata folder (where eng.traineddata lives)
            tessdata = os.path.join(path, 'tessdata')
            if os.path.exists(tessdata):
                os.environ['TESSDATA_PREFIX'] = tessdata
            break
    
    # Add all found paths to PATH
    if paths_to_add:
        current_path = os.environ.get('PATH', '')
        new_path = os.pathsep.join(paths_to_add) + os.pathsep + current_path
        os.environ['PATH'] = new_path


# Run bundled tools setup immediately when config is imported
setup_bundled_tools()

# -------------------------
# Application Info
# -------------------------
APP_NAME = "DocAnalyser_Beta"

# -------------------------
# Directory Setup
# -------------------------
def get_data_dir(app_name=APP_NAME) -> str:
    """Get platform-specific data directory"""
    home = os.path.expanduser("~")
    if sys.platform.startswith("win"):
        base = os.getenv("APPDATA") or home
        path = os.path.join(base, app_name)
    elif sys.platform == "darwin":
        path = os.path.join(home, "Library", "Application Support", app_name)
    else:
        path = os.path.join(home, f".{app_name.lower()}")
    os.makedirs(path, exist_ok=True)
    return path

DATA_DIR = get_data_dir(APP_NAME)
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
PROMPTS_PATH = os.path.join(DATA_DIR, "prompts.json")
MODELS_PATH = os.path.join(DATA_DIR, "models.json")
LIBRARY_PATH = os.path.join(DATA_DIR, "document_library.json")
SUMMARIES_DIR = os.path.join(DATA_DIR, "summaries")
OCR_CACHE_DIR = os.path.join(DATA_DIR, "ocr_cache")
AUDIO_CACHE_DIR = os.path.join(DATA_DIR, "audio_cache")

# Create necessary directories
os.makedirs(SUMMARIES_DIR, exist_ok=True)
os.makedirs(OCR_CACHE_DIR, exist_ok=True)
os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)


# =============================================================================
# PROVIDER REGISTRY
# =============================================================================
# Single source of truth for all AI provider configuration.
#
# TO ADD A PROVIDER:  Add one entry here. Nothing else needs changing
#                     (except writing the _call_xxx() function in ai_handler.py
#                     for API providers that need actual API code).
# TO REMOVE A PROVIDER: Delete its entry here. Done.
# TO BLOCK A PROVIDER:  Set "blocked": True. Done.
#
# Field reference:
#   type              "api" | "local" | "web"
#   blocked           True = red overlay in AI Settings (e.g. Pentagon contracts)
#   requires_api_key  True if the provider needs an API key stored in config
#   api_key_default   Default value for config["keys"]. None = not stored at all (web-only)
#   last_model_default Default value for config["last_model"]. None = not stored (web-only)
#   requires_library  pip package name needed for API calls, or None
#   signup_url        URL for the "Get Key" button in AI Settings
#   signup_domain     Short domain label shown alongside signup_url
#   local_url         Base URL for local providers (Ollama)
#   vision_patterns   List of model-name substrings that indicate vision capability.
#                     Empty list = provider does not support vision at all.
#   pdf_capable       True if the provider can accept raw PDF bytes
#   pdf_size_limit    Max PDF size in bytes, or None
#   pdf_page_limit    Max PDF pages, or None
#   web_url           URL to open when using "Run → Via Web"
#   web_name          Short display name used in the Via Web dialog
#   web_notes         Info shown to the user in the Via Web dialog
#   web_step3         Custom step-3 instruction in the Via Web dialog (optional).
#                     Defaults to "3. Press Enter or click Send to run the prompt"
#   default_models    Fallback model list. Overridden at runtime by models.json.
# =============================================================================

PROVIDER_REGISTRY = {
    "OpenAI (ChatGPT)": {
        "type":               "api",
        "blocked":            True,   # Pentagon military-targeting contract — see quitgpt.org
        "requires_api_key":   True,
        "api_key_default":    "",
        "last_model_default": "",
        "requires_library":   "openai",
        "signup_url":         "https://platform.openai.com/api-keys",
        "signup_domain":      "platform.openai.com",
        "vision_patterns":    ["gpt-4o", "gpt-4-turbo", "gpt-4.1", "gpt-4.5", "gpt-5", "o1", "o3", "o4"],
        "pdf_capable":        False,
        "pdf_size_limit":     None,
        "pdf_page_limit":     None,
        "web_url":            "https://chat.openai.com",
        "web_name":           "ChatGPT",
        "web_notes":          "Free tier available. For very long documents, ChatGPT may truncate the input.",
        "default_models": [
            "gpt-5.1",
            "gpt-5.1-chat-latest",
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4o-mini-2024-07-18",
            "gpt-4o-2024-11-20",
            "gpt-4o-2024-08-06",
            "gpt-4o-2024-05-13",
            "chatgpt-4o-latest",
            "gpt-4-turbo",
            "gpt-4-turbo-2024-04-09",
            "gpt-3.5-turbo",
        ],
    },

    "Anthropic (Claude)": {
        "type":               "api",
        "blocked":            False,
        "requires_api_key":   True,
        "api_key_default":    "",
        "last_model_default": "",
        "requires_library":   "anthropic",
        "signup_url":         "https://console.anthropic.com/settings/keys",
        "signup_domain":      "console.anthropic.com",
        "vision_patterns":    ["claude"],  # All Claude 3+ models support vision
        "pdf_capable":        True,
        "pdf_size_limit":     32 * 1024 * 1024,   # 32 MB
        "pdf_page_limit":     100,
        "web_url":            "https://claude.ai",
        "web_name":           "Claude",
        "web_notes":          "Free tier available. Claude handles very long documents well (200K+ tokens).",
        "default_models": [
            "claude-opus-4-6",
            "claude-opus-4-5-20251101",
            "claude-sonnet-4-5-20250929",
            "claude-sonnet-4-20250514",
            "claude-3-5-sonnet-20241022",
        ],
    },

    "Google (Gemini)": {
        "type":               "api",
        "blocked":            False,
        "requires_api_key":   True,
        "api_key_default":    "",
        "last_model_default": "gemini-1.5-flash",
        "requires_library":   "google-generativeai",
        "signup_url":         "https://aistudio.google.com/app/apikey",
        "signup_domain":      "aistudio.google.com",
        "vision_patterns":    ["gemini"],  # All Gemini 1.5+ support vision
        "pdf_capable":        True,
        "pdf_size_limit":     50 * 1024 * 1024,   # 50 MB (approximate)
        "pdf_page_limit":     300,
        "web_url":            "https://gemini.google.com",
        "web_name":           "Gemini",
        "web_notes":          "Free tier available. Requires a Google account.",
        "default_models": [
            "gemini-2.5-pro-preview-03-25",
            "gemini-2.5-flash-preview-05-20",
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite-preview-06-17",
            "gemini-2.5-pro-preview-05-06",
        ],
    },

    "xAI (Grok)": {
        "type":               "api",
        "blocked":            True,   # Pentagon military-targeting contract — see quitgpt.org
        "requires_api_key":   True,
        "api_key_default":    "",
        "last_model_default": "",
        "requires_library":   "openai",
        "signup_url":         "https://console.x.ai/",
        "signup_domain":      "console.x.ai",
        "vision_patterns":    ["grok-2-vision", "grok-vision"],
        "pdf_capable":        False,
        "pdf_size_limit":     None,
        "pdf_page_limit":     None,
        "web_url":            "https://x.com/i/grok",
        "web_name":           "Grok",
        "web_notes":          "\u26a0\ufe0f Requires an X (Twitter) account to access.",
        "default_models": [
            "grok-2-latest",
            "grok-2-vision-1212",
            "grok-vision-beta",
        ],
    },

    "DeepSeek": {
        "type":               "api",
        "blocked":            False,
        "requires_api_key":   True,
        "api_key_default":    "",
        "last_model_default": "",
        "requires_library":   "openai",
        "signup_url":         "https://platform.deepseek.com/api_keys",
        "signup_domain":      "platform.deepseek.com",
        "vision_patterns":    [],   # DeepSeek does not support vision/image input
        "pdf_capable":        False,
        "pdf_size_limit":     None,
        "pdf_page_limit":     None,
        "web_url":            "https://chat.deepseek.com",
        "web_name":           "DeepSeek",
        "web_notes":          "Free tier available with generous limits.",
        "default_models": [
            "deepseek-chat",
            "deepseek-reasoner",
        ],
    },

    "Ollama (Local)": {
        "type":               "local",
        "blocked":            False,
        "requires_api_key":   False,
        "api_key_default":    "not-required",   # Stored in config but value is fixed
        "last_model_default": "",
        "requires_library":   "openai",         # Uses OpenAI-compatible client
        "signup_url":         None,
        "signup_domain":      None,
        "local_url":          "http://localhost:11434",
        "vision_patterns":    [],
        "pdf_capable":        False,
        "pdf_size_limit":     None,
        "pdf_page_limit":     None,
        "web_url":            None,             # No web interface
        "web_name":           "Ollama",
        "web_notes":          "Ollama is a local application. Open it directly and paste your content there.",
        "default_models": [
            "(Run Local AI Setup to download models)",
        ],
    },

    "Lumo (Proton)": {
        "type":               "web",
        "blocked":            False,
        "requires_api_key":   False,
        "api_key_default":    None,   # Web-only: not stored in config keys at all
        "last_model_default": None,   # Web-only: not stored in config last_model
        "requires_library":   None,
        "signup_url":         None,
        "signup_domain":      None,
        "vision_patterns":    [],
        "pdf_capable":        False,
        "pdf_size_limit":     None,
        "pdf_page_limit":     None,
        "web_url":            "https://lumo.proton.me",
        "web_name":           "Lumo",
        "web_notes": (
            "Privacy-first AI by Proton. Swiss-based, zero-access encryption, no logs, "
            "never trains on your data. No account needed for guest use. "
            "Free tier: limited weekly queries. Plus: $12.99/month or $119.98/year (unlimited). "
            "See pricing and details: https://lumo.proton.me/about\n\n"
            "Note: Lumo treats a large paste as a file attachment. After pasting, "
            "you must also type something in the \u2018Ask anything...\u2019 box (e.g. a full stop) "
            "before Lumo will let you submit."
        ),
        # Custom Via Web step 3 — omit this key for the default "Press Enter or click Send"
        "web_step3": (
            "3. Lumo will attach the content as a file \u2014 type anything "
            "(e.g. a full stop) in the text box, then press Enter"
        ),
        "default_models": [
            "(Web interface only \u2014 use Run \u2192 Via Web)",
        ],
    },

    "Duck.ai": {
        "type":               "web",
        "blocked":            False,
        "requires_api_key":   False,
        "api_key_default":    None,
        "last_model_default": None,
        "requires_library":   None,
        "signup_url":         None,
        "signup_domain":      None,
        "vision_patterns":    [],
        "pdf_capable":        False,
        "pdf_size_limit":     None,
        "pdf_page_limit":     None,
        "web_url":            "https://duck.ai",
        "web_name":           "Duck.ai",
        "web_notes": (
            "Privacy-focused AI by DuckDuckGo. Anonymises all requests by proxying them \u2014 "
            "your IP is stripped and providers are contractually required to delete data within 30 days. "
            "No account required. No login. No tracking. Completely free with no usage limits. "
            "Free models include Claude Haiku, GPT-4o mini, Llama 4, and Mistral Small. "
            "Note: US-based (privacy is contractual, not architectural). "
            "See: https://duck.ai"
        ),
        "default_models": [
            "(Web interface only \u2014 use Run \u2192 Via Web)",
        ],
    },

    "Mistral Le Chat": {
        "type":               "web",
        "blocked":            False,
        "requires_api_key":   False,
        "api_key_default":    None,
        "last_model_default": None,
        "requires_library":   None,
        "signup_url":         None,
        "signup_domain":      None,
        "vision_patterns":    [],
        "pdf_capable":        False,
        "pdf_size_limit":     None,
        "pdf_page_limit":     None,
        "web_url":            "https://chat.mistral.ai",
        "web_name":           "Mistral Le Chat",
        "web_notes": (
            "Privacy-focused AI by Mistral, a French company. EU-based servers, GDPR compliant, "
            "outside US jurisdiction. Extremely fast (up to 1,000 words/second). "
            "Free tier: generous with rate limits, requires a free account. "
            "IMPORTANT: Training opt-out is NOT the default. After creating an account, go to "
            "Settings \u2192 Privacy and disable \u2018Allow your interactions to be used to train our models\u2019. "
            "Paid plan: $15/month. See: https://chat.mistral.ai"
        ),
        "default_models": [
            "(Web interface only \u2014 use Run \u2192 Via Web)",
        ],
    },
}


# =============================================================================
# DERIVED CONSTANTS  —  do not edit these directly; edit PROVIDER_REGISTRY above
# =============================================================================

# Master model list — overridden at runtime by models.json for API providers
DEFAULT_MODELS = {
    name: info["default_models"]
    for name, info in PROVIDER_REGISTRY.items()
}

# Vision-capable providers: maps provider name → list of model-name substrings
# A provider is included only if it has at least one vision pattern
VISION_CAPABLE_PROVIDERS = {
    name: info["vision_patterns"]
    for name, info in PROVIDER_REGISTRY.items()
    if info.get("vision_patterns")
}

# PDF direct-upload capability (used by ai_handler.py)
PDF_CAPABLE_PROVIDERS = {
    name: True
    for name, info in PROVIDER_REGISTRY.items()
    if info.get("pdf_capable")
}

PDF_SIZE_LIMITS = {
    name: info["pdf_size_limit"]
    for name, info in PROVIDER_REGISTRY.items()
    if info.get("pdf_size_limit") is not None
}

PDF_PAGE_LIMITS = {
    name: info["pdf_page_limit"]
    for name, info in PROVIDER_REGISTRY.items()
    if info.get("pdf_page_limit") is not None
}

# Internal helpers for DEFAULT_CONFIG below
# Only providers with api_key_default != None get a slot in config["keys"]
_DEFAULT_KEYS = {
    name: info["api_key_default"]
    for name, info in PROVIDER_REGISTRY.items()
    if info["api_key_default"] is not None
}

# Only providers with last_model_default != None get a slot in config["last_model"]
_DEFAULT_LAST_MODELS = {
    name: info["last_model_default"]
    for name, info in PROVIDER_REGISTRY.items()
    if info["last_model_default"] is not None
}


# -------------------------
# Default Configuration
# -------------------------
DEFAULT_CONFIG = {
    "last_provider": "Google (Gemini)",  # Changed to cheapest option (was OpenAI)
    "last_model_update": None,
    "chunk_size": "medium",
    "ocr_language": "eng",
    "ocr_quality": "balanced",
    "tesseract_path": "",
    "transcription_engine": "openai_whisper",
    "ocr_mode": "local_first",  # local_first or cloud_direct
    "ocr_confidence_threshold": 60,  # % below which to offer Cloud AI escalation
    "transcription_language": "en",
    "speaker_diarization": False,
    "enable_vad": True,  # Voice Activity Detection toggle (True by default)
    "youtube_prefer_audio": False,  # If True, skip YouTube captions and transcribe audio directly (required for speaker diarization)
    "timestamp_interval": "5min",  # Timestamp frequency control
    "moonshine_chunk_seconds": 15,  # Moonshine audio chunk duration (10-30s, default 15)
    "corrections_enabled": True,  # Enable real-time corrections during transcription
    "corrections_project": "default",  # Active corrections project/dictionary
    "performance_logging": True,  # Save performance logs after transcription
    # Dictation/Speech-to-text settings
    "dictation_mode": "local_first",  # local_first, cloud_direct, local_only
    "whisper_model": "base",  # tiny, base, small, medium, large-v3
    "whisper_device": "auto",  # auto, cpu, cuda
    # Ollama configuration
    "ollama_base_url": "http://localhost:11434",  # Ollama default server URL
    "auto_generate_embeddings": False,  # Auto-generate semantic search embeddings for new documents
    # Source input mode preference
    "source_mode_preference": "",  # "single", "multiple", or "" (no preference saved)
    "default_prompt": "",  # Name of the default prompt to select on startup
"keys": {
        **_DEFAULT_KEYS,
        "Google Cloud Vision": "",  # Dedicated OCR service — separate from Gemini chat
        "YouTube Data API":    "",  # For Subscriptions feature — get free key at console.cloud.google.com
    },
    "ocr_text_type": "printed",  # "printed" (use Cloud Vision OCR) or "handwriting" (use Vision AI)
    "last_model": _DEFAULT_LAST_MODELS,
}

# -------------------------
# Default Prompts
# -------------------------
DEFAULT_PROMPTS = [
    {"name": "Detailed dotpoint summary (quotes+timestamps)",
     "text": "Give me a detailed dotpoint summary of the transcript below. Feature direct quotations with timestamps."},
    {"name": "Short 3-bullet summary",
     "text": "Provide a very concise 3-bullet summary of the transcript below."},
    {"name": "Key takeaways (5)",
     "text": "List the 5 most important takeaways from the transcript below."}
]

# -------------------------
# Chunk Sizes
# -------------------------
CHUNK_SIZES = {
    "tiny": {
        "chars": 6000,
        "label": "Tiny (3-6 pages)",
        "description": "For local AI models with small context windows (4K tokens)",
        "quality": "⭐⭐⭐⭐⭐"
    },
    "small": {
        "chars": 12000,
        "label": "Small (6-12 pages)",
        "description": "Best quality - Excellent detail extraction",
        "quality": "⭐⭐⭐⭐⭐"
    },
    "medium": {
        "chars": 24000,
        "label": "Medium (10-15 pages)",
        "description": "Balanced - Good quality, faster processing",
        "quality": "⭐⭐⭐⭐"
    },
    "large": {
        "chars": 52000,
        "label": "Large (20+ pages)",
        "description": "Fastest - Quick overview, may miss details",
        "quality": "⭐⭐⭐"
    }
}

# -------------------------
# OCR Presets
# -------------------------
OCR_PRESETS = {
    "fast": {
        "label": "Fast ⚡",
        "description": "Quick processing, good for clear documents",
        "psm": 3,
        "enhance": False,
        "denoise": False
    },
    "balanced": {
        "label": "Balanced ⚖️",
        "description": "Good mix of speed and accuracy",
        "psm": 3,
        "enhance": True,
        "denoise": False
    },
    "accurate": {
        "label": "Accurate 🎯",
        "description": "Best quality for challenging documents",
        "psm": 1,
        "enhance": True,
        "denoise": True
    }
}

# -------------------------
# Audio Settings
# -------------------------
AUDIO_CHUNK_DURATION_MS = 10 * 60 * 1000  # 10 minutes in milliseconds

# -------------------------
# OCR Languages
# -------------------------
OCR_LANGUAGES = {
    "eng": "English",
    "fra": "French",
    "deu": "German",
    "spa": "Spanish",
    "ita": "Italian",
    "por": "Portuguese",
    "rus": "Russian",
    "chi_sim": "Chinese (Simplified)",
    "chi_tra": "Chinese (Traditional)",
    "jpn": "Japanese",
    "ara": "Arabic",
    "hin": "Hindi"
}

SUPPORTED_AUDIO_FORMATS = {
    '.mp3': 'MP3 Audio',
    '.wav': 'WAV Audio',
    '.m4a': 'M4A Audio',
    '.ogg': 'OGG Audio',
    '.flac': 'FLAC Audio',
    '.aac': 'AAC Audio',
    '.wma': 'WMA Audio',
    '.opus': 'Opus Audio',
    '.mp4': 'MP4 Video',
    '.avi': 'AVI Video',
    '.mov': 'MOV Video'
}

# -------------------------
# OCR Processing Modes
# -------------------------
OCR_MODES = {
    "local_first": {
        "label": "Local first (Tesseract), then Cloud if needed",
        "description": "Try local OCR first. If quality is poor, offer to retry with Cloud AI."
    },
    "cloud_direct": {
        "label": "Cloud AI directly (fastest, most accurate)",
        "description": "Send images directly to your AI provider for transcription. Best for handwriting."
    },
    "cloud_pdf": {
        "label": "Cloud AI for PDFs (bypass local tools)",
        "description": "Send PDFs directly to Claude/Gemini. Best for corrupt or elderly scanned PDFs that crash local tools."
    }
}

# -------------------------
# Dictation/Speech-to-Text Modes
# -------------------------
DICTATION_MODES = {
    "local_first": {
        "label": "Local first, cloud fallback (recommended)",
        "description": "Free & private. Falls back to your selected cloud engine if local fails."
    },
    "cloud_direct": {
        "label": "Cloud direct (uses selected engine)",
        "description": "Fastest & most accurate. Uses your Transcription Engine selection."
    },
    "local_only": {
        "label": "Local only (fully private)",
        "description": "Audio never leaves your computer. No fallback."
    }
}

WHISPER_MODELS = {
    "tiny": {"size": "75 MB", "description": "Fastest, lowest accuracy"},
    "base": {"size": "150 MB", "description": "Good balance (recommended)"},
    "small": {"size": "500 MB", "description": "Better accuracy, slower"},
    "medium": {"size": "1.5 GB", "description": "High accuracy, much slower"},
    "large-v3": {"size": "3 GB", "description": "Best accuracy, very slow"},
}

# Vision / PDF provider capabilities are defined in PROVIDER_REGISTRY above
# and exported as VISION_CAPABLE_PROVIDERS, PDF_CAPABLE_PROVIDERS, etc.

TRANSCRIPTION_ENGINES = {
    "openai_whisper": {
        "name": "OpenAI Whisper (Cloud)",
        "description": "Fast, accurate, cloud-based (costs ~$0.006/min)",
        "requires_api": True,
        "supports_diarization": False,
        "max_file_size": 25
    },
    "faster_whisper": {
        "name": "Faster Whisper (Local)",
        "description": "Fast local processing, runs on your computer (FREE)",
        "requires_api": False,
        "supports_diarization": False,
        "max_file_size": None
    },
    "assemblyai": {
        "name": "AssemblyAI",
        "description": "Best speaker identification (costs ~$0.00025/min)",
        "requires_api": True,
        "supports_diarization": True,
        "max_file_size": None
    },
    "moonshine": {
        "name": "Moonshine (Local) ⭐",
        "description": "Ultra-light on-device ASR (~57MB model). Faster than Whisper for short segments. English only. FREE.",
        "requires_api": False,
        "supports_diarization": False,
        "max_file_size": None
    }
}
