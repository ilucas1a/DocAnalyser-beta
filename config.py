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
        "OpenAI (ChatGPT)": "",
        "Anthropic (Claude)": "",
        "Google (Gemini)": "",
        "Google Cloud Vision": "",  # Separate key for dedicated OCR service
        "xAI (Grok)": "",
        "DeepSeek": "",
        "Ollama (Local)": "not-required"  # Ollama doesn't need an API key
    },
    "ocr_text_type": "printed",  # "printed" (use Cloud Vision OCR) or "handwriting" (use Vision AI)
    "last_model": {
        "OpenAI (ChatGPT)": "",
        "Anthropic (Claude)": "",
        "Google (Gemini)": "gemini-1.5-flash",  # Set default cheapest model
        "xAI (Grok)": "",
        "DeepSeek": "",
        "Ollama (Local)": ""  # Will be auto-detected from Ollama
    }
}

# -------------------------
# Vision-Capable AI Providers
# -------------------------
# These patterns are used to check if a model supports image analysis
# If the model name contains any of these patterns, it's considered vision-capable
VISION_CAPABLE_PROVIDERS = {
    "OpenAI (ChatGPT)": ["gpt-4o", "gpt-4-turbo", "gpt-4.1", "gpt-4.5", "gpt-5", "o1", "o3", "o4"],
    "Anthropic (Claude)": ["claude"],  # All Claude models support vision (v3+)
    "Google (Gemini)": ["gemini"],
    "xAI (Grok)": ["grok-2-vision", "grok-vision"],
    # NOTE: DeepSeek does not support vision/image input - do not add here
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
# AI Models
# -------------------------
DEFAULT_MODELS = {
    "OpenAI (ChatGPT)": [
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
        "gpt-3.5-turbo"
    ],
    "Anthropic (Claude)": ["claude-opus-4-6", "claude-opus-4-5-20251101", "claude-sonnet-4-5-20250929", "claude-sonnet-4-20250514", "claude-3-5-sonnet-20241022"],
    "Google (Gemini)": ["gemini-2.5-pro-preview-03-25", "gemini-2.5-flash-preview-05-20", "gemini-2.5-flash", "gemini-2.5-flash-lite-preview-06-17", "gemini-2.5-pro-preview-05-06"],
    "xAI (Grok)": ["grok-2-latest", "grok-2-vision-1212", "grok-vision-beta"],
    "DeepSeek": ["deepseek-chat", "deepseek-reasoner"],
    "Ollama (Local)": ["(Run Local AI Setup to download models)"]  # Models managed via Local AI Setup
}

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

# Vision providers moved to top of file (see VISION_CAPABLE_PROVIDERS above)

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
