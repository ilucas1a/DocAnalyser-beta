
"""
ExpandedFunction_v13.py

Universal Document Analyser (v13 - Advanced OCR and Audio Transcription Support)
 - Cross-platform user data folder for config/prompts/models
 - Providers: OpenAI (ChatGPT), xAI (Grok), DeepSeek
 - Audio transcription: OpenAI Whisper, AssemblyAI, YouTube audio fallback
 - UI updates: New Audio Input tab for local audio files and transcription settings
"""

# VERSION: 2.2.0 - 2025-01-10 - Smart context-aware prompts: Can now use DocAnalyser for general AI chat without documents

from __future__ import annotations

import os
import sys

# === SAFE STDOUT/STDERR FOR WINDOWS GUI ===
# When running as a frozen PyInstaller .exe with console=False, sys.stdout/stderr
# may be None, closed, or broken. Any print() or .flush() will crash the app.
# Solution: For frozen apps, use a pure no-op writer (no file handles at all).

class _NullWriter:
    """Pure no-op writer - never touches any file handle."""
    def write(self, text): pass
    def flush(self): pass
    def close(self): pass
    def isatty(self): return False
    @property
    def closed(self): return False
    @property
    def encoding(self): return 'utf-8'
    @property
    def name(self): return '<null>'
    def fileno(self):
        raise OSError("NullWriter has no file descriptor")
    def __getattr__(self, name):
        return None

class _SafeWriter:
    """Wraps stdout/stderr to prevent crashes when console is unstable."""
    def __init__(self, stream):
        self._stream = stream
    def write(self, text):
        try:
            if self._stream and not getattr(self._stream, 'closed', False):
                self._stream.write(text)
        except (OSError, ValueError, AttributeError, TypeError):
            pass
    def flush(self):
        try:
            if self._stream and not getattr(self._stream, 'closed', False):
                self._stream.flush()
        except (OSError, ValueError, AttributeError, TypeError):
            pass
    @property
    def closed(self): return False
    @property
    def encoding(self): return getattr(self._stream, 'encoding', 'utf-8')
    def isatty(self): return False
    def fileno(self):
        if self._stream:
            return self._stream.fileno()
        raise OSError("No file descriptor")
    def __getattr__(self, name):
        try:
            return getattr(self._stream, name)
        except (OSError, ValueError, AttributeError):
            return None

_is_frozen = getattr(sys, 'frozen', False)

if _is_frozen:
    # Frozen app: use pure NullWriter - safest possible option
    sys.stdout = _NullWriter()
    sys.stderr = _NullWriter()
elif sys.stdout is None or not hasattr(sys.stdout, 'write') or getattr(sys.stdout, 'closed', False):
    sys.stdout = _NullWriter()
    sys.stderr = _NullWriter() if (sys.stderr is None or getattr(sys.stderr, 'closed', False)) else _SafeWriter(sys.stderr)
else:
    sys.stdout = _SafeWriter(sys.stdout)
    sys.stderr = _SafeWriter(sys.stderr) if sys.stderr else _NullWriter()
# === END SAFE STDOUT/STDERR ===

# DEBUG_FILE = open('docanalyser_debug.log', 'w', encoding='utf-8')
# original_stdout = sys.stdout
# sys.stdout = DEBUG_FILE  # All prints go to file now

#print("="*60)
# print("DEBUG LOG STARTED")
# print("="*60)
# === END DEBUG SETUP ===

import os
import re

# Fix Unicode encoding issues when running as frozen exe on Windows
# Windows console uses cp1252 which can't handle emoji characters
if sys.platform == 'win32':
    import io
    # When running as frozen exe without console, stdout/stderr might be None
    if sys.stdout is None:
        sys.stdout = io.StringIO()
    elif hasattr(sys.stdout, 'buffer') and sys.stdout.buffer is not None:
        try:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        except:
            pass
    
    if sys.stderr is None:
        sys.stderr = io.StringIO()
    elif hasattr(sys.stderr, 'buffer') and sys.stderr.buffer is not None:
        try:
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
        except:
            pass
    
    # Also set environment variable for child processes
    os.environ.setdefault('PYTHONIOENCODING', 'utf-8')

# Safe print function that handles encoding issues
def safe_print(*args, **kwargs):
    """Print that handles encoding errors gracefully - for debug output only"""
    try:
        print(*args, **kwargs)
    except (UnicodeEncodeError, OSError):
        # Fallback: convert to ASCII-safe representation
        try:
            safe_args = [str(arg).encode('ascii', errors='replace').decode('ascii') for arg in args]
            print(*safe_args, **kwargs)
        except:
            pass  # Give up silently if all else fails

# Error logging for frozen exe (helps debug issues when no console)
import logging
if getattr(sys, 'frozen', False):
    # Running as bundled exe - log errors to file
    log_dir = os.path.join(os.path.expanduser('~'), 'DocAnalyser_logs')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, 'error_log.txt')
    logging.basicConfig(
        filename=log_file,
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    logging.info(f"DocAnalyser starting - exe location: {sys.executable}")
    logging.info(f"Working directory: {os.getcwd()}")
    
    # Log module availability
    def check_module(name):
        try:
            __import__(name)
            logging.info(f"Module {name}: OK")
            return True
        except ImportError as e:
            logging.error(f"Module {name}: FAILED - {e}")
            return False
    
    check_module('yt_dlp')
    check_module('docx')
    check_module('PyPDF2')
    check_module('PIL')
    check_module('requests')
    check_module('pytesseract')
    check_module('pdf2image')
else:
    logging.basicConfig(level=logging.DEBUG)

import json
import threading
import datetime
import time
import tempfile
import shutil
import re
import traceback
import webbrowser
import hashlib
from auto_save_responses import ResponseAutoSaver
from standalone_conversation import check_and_prompt_standalone_save, reset_standalone_state
from contextlib import contextmanager
from typing import List, Dict, Optional

# Spreadsheet support
try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

try:
    import openpyxl
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False
    
try:
    import xlrd
    XLRD_AVAILABLE = True
except ImportError:
    XLRD_AVAILABLE = False

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from tkinter.font import Font  # ADD THIS LINE

# Drag-and-drop support
try:
    from tkinterdnd2 import DND_FILES, DND_TEXT, DND_ALL, TkinterDnD
    DND_AVAILABLE = True
except ImportError:
    DND_AVAILABLE = False
    safe_print("Warning: tkinterdnd2 not available - drag-and-drop disabled")
    safe_print("   Install with: pip install tkinterdnd2")

import requests
from openai import OpenAI

# Transcript libraries - handled by youtube_utils.py
# (youtube_transcript_api import moved to youtube_utils.py)

# Optional subtitle fallback tools
import yt_dlp

try:
    import webvtt
except Exception:
    webvtt = None
try:
    import pysrt
except Exception:
    pysrt = None

# OCR support
try:
    import pytesseract
    from pdf2image import convert_from_path
    from PIL import Image, ImageEnhance, ImageFilter

    OCR_SUPPORT = True
except Exception as e:
    OCR_SUPPORT = False
    OCR_IMPORT_ERROR = str(e)

from config import *
from utils import *
from document_library import *
from config_manager import *
from document_export import export_document, get_file_extension_and_types, get_export_date
from sources_dialog import open_sources_dialog, open_bulk_processing
from settings_manager import SettingsMixin

# Version and update system
from version import VERSION, get_version_string, APP_DISPLAY_NAME
from update_checker import check_for_updates_async, UpdateInfo
from setup_wizard import show_setup_wizard, show_update_notification, should_show_first_run_wizard, mark_wizard_completed

# Local AI setup - smart detection and one-click setup
try:
    from local_ai_setup import (
        should_show_local_ai_banner, 
        create_local_ai_banner,
        show_local_ai_setup,
        has_usable_models,
        is_ollama_installed
    )
    LOCAL_AI_SETUP_AVAILABLE = True
except ImportError:
    LOCAL_AI_SETUP_AVAILABLE = False
    def should_show_local_ai_banner(config): return False
    def has_usable_models(): return False
    def is_ollama_installed(): return False
from dependency_checker import get_system_summary, get_faster_whisper_status
from universal_document_saver import UniversalDocumentSaver
try:
    import turboscribe_helper
    TURBOSCRIBE_AVAILABLE = True
except ImportError:
    TURBOSCRIBE_AVAILABLE = False
    safe_print("Warning: TurboScribe helper not available")

# Context Help System
try:
    from context_help import add_help, HELP_TEXTS, show_app_overview
    CONTEXT_HELP_AVAILABLE = True
except ImportError:
    CONTEXT_HELP_AVAILABLE = False
    safe_print("Warning: Context help not available - right-click help disabled")
    # Dummy function if context_help not available
    def add_help(*args, **kwargs): pass
    def show_app_overview(*args, **kwargs): pass
    HELP_TEXTS = {}

# First Run Wizard
try:
    from first_run_wizard import has_run_before, show_first_run_wizard
    WIZARD_AVAILABLE = True
except ImportError:
    WIZARD_AVAILABLE = False
    safe_print("Warning: First run wizard not available")
    def has_run_before(): return True  # Skip wizard if module missing
    def show_first_run_wizard(*args, **kwargs): pass

# Prompt dropdown builder
from prompt_dropdown_builder import (
    build_dropdown_auto,
    extract_prompt_name,
    is_separator,
    is_header
)

# =========================================
# PHASE 1 OPTIMIZATION: Lazy Imports
# =========================================
_modules_cache = {}

def get_module(module_name):
    """Lazy load modules only when needed"""
    if module_name not in _modules_cache:
        _modules_cache[module_name] = __import__(module_name)
    return _modules_cache[module_name]

def get_ocr():
    return get_module('ocr_handler')

def get_audio():
    return get_module('audio_handler')

def get_doc_fetcher():
    return get_module('document_fetcher')

def get_ai():
    return get_module('ai_handler')

def get_formatter():
    return get_module('output_formatter')
# =========================================

import inspect

# -------------------------
# Config / prompts / models I/O now handled by config_manager.py
# -------------------------

# -------------------------
# Utility helpers
# ---------------------

@contextmanager
def temp_dir():
    td = tempfile.mkdtemp()
    try:
        yield td
    finally:
        try:
            shutil.rmtree(td)
        except Exception:
            pass

# =========================================
# UNIVERSAL SAVE FUNCTIONS - imported from save_utils.py
# =========================================
from save_utils import (
    save_document_to_file,
    get_clean_filename,
    get_document_metadata,
    prompt_and_save_document
)
# =========================================

# -------------------------
# YouTube Functions - imported from youtube_utils.py
# -------------------------
from youtube_utils import (
    extract_video_id,
    fetch_youtube_transcript,
    fetch_youtube_with_audio_fallback,
    YOUTUBE_TRANSCRIPT_AVAILABLE
)
# -------------------------

# Substack Functions - imported from substack_utils.py
try:
    from substack_utils import (
        is_substack_url,
        fetch_substack_transcript,
        format_substack_transcript
    )
    # fetch_substack_content is imported locally in _fetch_substack_thread when needed
    SUBSTACK_AVAILABLE = True
except ImportError:
    SUBSTACK_AVAILABLE = False

# Facebook support - imported from facebook_utils.py
# -------------------------
try:
    from facebook_utils import is_facebook_video_url, fetch_facebook_content
    FACEBOOK_SUPPORT = True
except ImportError:
    FACEBOOK_SUPPORT = False
    safe_print("Warning: facebook_utils not available - Facebook support disabled")
# -------------------------

# Twitter/X support - imported from twitter_utils.py
# -------------------------
try:
    from twitter_utils import is_twitter_url, fetch_twitter_content, download_twitter_video
    TWITTER_SUPPORT = True
except ImportError:
    TWITTER_SUPPORT = False
    safe_print("Warning: twitter_utils not available - Twitter/X support disabled")
# -------------------------

# =========================================
# TRANSCRIPTION ENGINES CONFIGURATION
# =========================================
TRANSCRIPTION_ENGINES = {
    "faster_whisper": {
        "name": "faster-whisper (Local)",
        "description": "Free, runs on your computer. Good quality, no file size limit.",
        "requires_api": False,
        "api_key_name": None,
        "signup_url": None,
        "features": ["Free", "Offline", "No file limit", "VAD support"],
        "limitations": ["Slower on CPU", "No speaker ID"]
    },
    "openai_whisper": {
        "name": "OpenAI Whisper (Cloud)",
        "description": "Fast, accurate cloud transcription. Uses your OpenAI API key.",
        "requires_api": True,
        "api_key_name": "OpenAI",
        "signup_url": "https://platform.openai.com/api-keys",
        "features": ["Fast", "High accuracy", "25MB file limit"],
        "limitations": ["Costs ~$0.006/min", "25MB max file size"],
        "cost_per_minute": 0.006
    },
    "assemblyai": {
        "name": "AssemblyAI (Cloud)",
        "description": "Excellent accuracy with speaker identification (diarization).",
        "requires_api": True,
        "api_key_name": "AssemblyAI",
        "signup_url": "https://www.assemblyai.com/dashboard/signup",
        "features": ["Speaker ID", "High accuracy", "Large files OK"],
        "limitations": ["Costs ~$0.006/min", "Requires account"],
        "cost_per_minute": 0.00025  # $0.00025 per second = $0.015 per minute (actually cheaper)
    }
}

# =========================================
# Dictation Dialog - moved to dictation_dialog.py
# =========================================

# =========================================

class DocAnalyserApp(SettingsMixin):

    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_DISPLAY_NAME} {get_version_string()} - Universal Document Analyser")
        self.configure_button_style()  # Add this line
        
        # Position window in top-right corner of screen
        window_width = 552
        window_height = 420
        screen_width = self.root.winfo_screenwidth()
        x_position = screen_width - window_width - 10  # 10px margin from right edge
        y_position = 10  # 10px margin from top
        self.root.geometry(f"{window_width}x{window_height}+{x_position}+{y_position}")
        
        # self.root.minsize(700, 650)  # Prevent window from getting smaller
        self.root.resizable(True, True)  # Allow manual resizing if needed
        self.config = load_config()
        # Set size constraints: max width = 700, height limited
        self.root.maxsize(700, 700)  # Cap height at 700px
        #  self.root.minsize(600, 500)  # Can get narrower down to 600px
        
        # Create menu bar (especially useful for Mac users)
        self._create_menu_bar()
        
        self.prompts = load_prompts()
        self.prompt_name_map = {}  # Maps display names to prompt data
        self.models = load_models()
        self.current_document_text = None
        self.current_entries = []
        self.current_document_source = None
        self.current_document_id = None
        self.current_document_type = None
        self.current_document_class = "source"  # Track if document is source or product
        self.current_document_metadata = {}  # Store current document metadata
        # 🆕 MVP: Conversational threading
        self.current_thread = []  # Active conversation for current document
        self.thread_message_count = 0  # Simple counter for display
        self.thread_needs_document_refresh = False  # Set True when loading saved thread
        
        # 🆕 NEW: Attachment manager for including additional documents in prompts
        from attachment_handler import AttachmentManager
        self.attachment_manager = AttachmentManager()
        self.processing = False
        self.current_editing_prompt_index = None
        self.processing_thread = None
        # Default to Google (Gemini) as it has the cheapest model (gemini-1.5-flash)
        default_provider = self.config.get("last_provider", "Google (Gemini)")
        # Ollama is now accessed via "Run Prompt → Via Local AI" menu, not the dropdown
        if default_provider == "Ollama (Local)":
            default_provider = "Google (Gemini)"

        # Ensure required config keys exist with defaults
        self.config.setdefault("transcription_engine", "openai_whisper")
        self.config.setdefault("transcription_language", "")  # Empty for auto-detect
        self.config.setdefault("speaker_diarization", False)
        self.config.setdefault("enable_vad", True)  # 🆕 NEW: VAD toggle

        self.provider_var = tk.StringVar(value=default_provider)
        # Default to gemini-1.5-flash if no last model saved (cheapest option at $0.1875/1M tokens avg)
        default_model = self.config.get("last_model", {}).get(default_provider, "gemini-1.5-flash" if default_provider == "Google (Gemini)" else "")
        self.model_var = tk.StringVar(value=default_model)
        self.api_key_var = tk.StringVar(value=self.config["keys"].get(default_provider, ""))
        self.transcription_engine_var = tk.StringVar(value=self.config.get("transcription_engine", "openai_whisper"))
        self.transcription_lang_var = tk.StringVar(value=self.config.get("transcription_language", ""))  # Empty for auto-detect
        self.diarization_var = tk.BooleanVar(value=self.config.get("speaker_diarization", False))
        self.force_reprocess_var = tk.BooleanVar(value=False)
        self.bypass_cache_var = tk.BooleanVar(value=False)
        
        # 🆕 NEW: Track file type for context buttons
        self.current_file_type = None
        self.context_button_frame = None
        
        # Universal input and compatibility variables
        self.universal_input_var = tk.StringVar()
        self.yt_url_var = tk.StringVar()
        self.file_path_var = tk.StringVar()
        self.web_url_var = tk.StringVar()
        self.audio_path_var = tk.StringVar()
        self.yt_fallback_var = tk.BooleanVar(value=True)
        
        # 🆕 NEW: Pending web response tracking
        self.pending_web_response = None  # Stores context when awaiting web response
        self.web_response_banner = None   # The banner frame

        self.setup_ui()
        # Register window close handler to save thread before exit
        self.root.protocol("WM_DELETE_WINDOW", self.on_app_closing)
        
        # Set initial button states (disabled since no document loaded yet)
        self.update_button_states()
        
        # First-run wizard and update check
        self._run_startup_checks()

        # Force hierarchical dropdown on startup (ADD THIS LINE)
        self.root.after(100, self.refresh_main_prompt_combo)

        self.doc_saver = UniversalDocumentSaver(enabled=True)

    def configure_button_style(self):
        """Configure button style to ensure proper height"""
        style = ttk.Style()
        
        # Use 'clam' theme for better color control on Windows
        style.theme_use('clam')
        
        style.configure('TButton', padding=(5, 3))  # (horizontal, vertical) padding
        
        # Highlighted button styles (green background for Load/Run when ready)
        style.configure('Highlight.TButton', background='#90EE90', padding=(5, 3))
        style.map('Highlight.TButton',
                  background=[('active', '#7CCD7C'), ('pressed', '#6BB86B')])
        
        # Color LabelFrame labels red
        style.configure('TLabelframe.Label', foreground='red')
        
        # Input field background color - subtle cream/pale yellow for user input areas
        self.input_bg_color = '#FFFDE6'  # Very pale cream-yellow (just a hint)
        
        # Style for Entry widgets
        style.configure('Input.TEntry', fieldbackground=self.input_bg_color)
        
        # Style for Combobox widgets - clam theme respects these settings
        style.configure('Input.TCombobox', fieldbackground=self.input_bg_color)
        style.map('Input.TCombobox',
                  fieldbackground=[('readonly', self.input_bg_color), 
                                   ('disabled', '#F0F0F0')],
                  selectbackground=[('readonly', '#4A90D9')])
        
        # Also set dropdown list colors
        self.root.option_add('*TCombobox*Listbox.background', self.input_bg_color)
        self.root.option_add('*TCombobox*Listbox.selectBackground', '#4A90D9')
        
        # Set root window background to match the theme's frame background
        self.theme_bg = style.lookup('TFrame', 'background') or '#dcdad5'
        self.root.configure(bg=self.theme_bg)
    
    def style_dialog(self, dialog):
        """Apply consistent styling to a child dialog window."""
        dialog.configure(bg=self.theme_bg)
    
    # Alias for backward compatibility with existing code
    def apply_window_style(self, window):
        """Apply consistent styling to a Toplevel window."""
        self.style_dialog(window)
    
    def _adjust_font_size(self, delta: int):
        """
        Adjust the font size for preview pane and related text displays.
        
        Args:
            delta: Amount to change font size (+1 or -1)
        """
        # Clamp font size between 8 and 16
        new_size = max(8, min(16, self.font_size + delta))
        
        if new_size == self.font_size:
            return  # No change needed
        
        self.font_size = new_size
        
        # Save to config
        self.config['font_size'] = self.font_size
        save_config(self.config)
        

        
        # Update all Thread Viewer windows if open
        if hasattr(self, '_thread_viewer_windows') and self._thread_viewer_windows:
            for viewer in self._thread_viewer_windows[:]:  # Copy list to allow modification
                try:
                    if viewer.window.winfo_exists():
                        viewer._refresh_thread_display()
                except (tk.TclError, AttributeError):
                    self._thread_viewer_windows.remove(viewer)
        
        self.set_status(f"Text size: {self.font_size}pt")
    
    def _create_menu_bar(self):
        """
        Create the application menu bar.
        DISABLED - Replaced by custom colored header bar in setup_ui().
        """
        pass  # Menu bar replaced by colored header bar
    
    def _show_app_overview(self):
        """Show the application overview help window"""
        try:
            from context_help import show_app_overview
            show_app_overview(self.root)
        except Exception as e:
            messagebox.showinfo(
                "DocAnalyser Help",
                "DocAnalyser is a universal document analysis tool.\n\n"
                "• Load documents from YouTube, PDFs, audio, web pages\n"
                "• Analyse with AI (cloud or local)\n"
                "• Save and manage in Documents Library\n\n"
                "💡 Right-click any button for context help!"
            )

    def _show_system_check(self):
        """Show the system check / setup wizard dialog"""
        show_setup_wizard(self.root)
    
    def _check_for_updates(self):
        """Manually check for updates"""
        self.set_status("🔄 Checking for updates...")
        
        def on_update_check_complete(update_info: UpdateInfo):
            if update_info.error:
                self.root.after(0, lambda: messagebox.showwarning(
                    "Update Check",
                    f"Could not check for updates:\n{update_info.error}"
                ))
                self.root.after(0, lambda: self.set_status("Update check failed"))
            elif update_info.available:
                self.root.after(0, lambda: show_update_notification(self.root, update_info))
                self.root.after(0, lambda: self.set_status("Update available!"))
            else:
                self.root.after(0, lambda: messagebox.showinfo(
                    "Update Check",
                    f"You're running the latest version ({VERSION})!"
                ))
                self.root.after(0, lambda: self.set_status("✅ You're up to date"))
        
        check_for_updates_async(on_update_check_complete)
    
    def _reset_and_show_wizard(self):
        """Reset and show the first-run wizard (for testing or re-viewing)"""
        try:
            from first_run_wizard import reset_wizard, show_first_run_wizard
            reset_wizard()
            show_first_run_wizard(
                self.root,
                on_complete_callback=lambda: self.set_status("First-run wizard completed"),
                show_local_ai_guide_callback=self._open_local_ai_guide
            )
        except Exception as e:
            messagebox.showerror("Error", f"Could not show wizard: {e}")
    
    def _startup_update_check(self):
        """Background update check on startup (non-intrusive)"""
        if not self.config.get("check_for_updates", True):
            return
        
        def on_update_check_complete(update_info: UpdateInfo):
            if update_info.available and not update_info.error:
                # Check if user skipped this version
                skipped = self.config.get("skipped_version", "")
                if skipped == update_info.latest_version:
                    return  # User chose to skip this version
                
                # Show notification on main thread
                self.root.after(0, lambda: show_update_notification(self.root, update_info))
        
        # Check after a short delay to not slow startup
        self.root.after(2000, lambda: check_for_updates_async(on_update_check_complete))
    
    def _startup_auto_refresh_models(self):
        """
        Check if cached models are stale (>30 days) and refresh automatically.
        Runs in background thread to not block UI.
        """
        from config_manager import are_models_stale, get_models_age_days
        
        if not are_models_stale():
            age = get_models_age_days()
            if age >= 0:
                print(f"📋 Models last refreshed {age} days ago (fresh)")
            return
        
        age = get_models_age_days()
        if age < 0:
            print("📋 Models never refreshed - triggering auto-refresh...")
        else:
            print(f"📋 Models are {age} days old (>30 days) - triggering auto-refresh...")
        
        # Show status
        self.set_status("🔄 Auto-refreshing AI model list...")
        
        def do_refresh():
            """Background refresh thread"""
            try:
                from model_updater import refresh_all_models
                from config_manager import save_models
                
                # Get current config for API keys
                updated_models = refresh_all_models(
                    self.config,
                    status_callback=None  # Silent refresh
                )
                
                if updated_models:
                    # Save updated models (this also updates the timestamp)
                    save_models(updated_models)
                    
                    # Update UI on main thread
                    def update_ui():
                        self.models = updated_models
                        # Refresh current provider's model dropdown
                        provider = self.provider_var.get()
                        combo = getattr(self, 'main_model_combo', None) or getattr(self, 'model_combo', None)
                        if combo and provider in updated_models:
                            combo['values'] = updated_models[provider]
                        self.set_status("✅ Model list auto-refreshed")
                        print("✅ Auto-refresh complete - models updated")
                    
                    self.root.after(0, update_ui)
                else:
                    self.root.after(0, lambda: self.set_status(""))
                    
            except Exception as e:
                print(f"⚠️ Auto-refresh failed: {e}")
                self.root.after(0, lambda: self.set_status(""))
        
        # Run in background thread
        import threading
        thread = threading.Thread(target=do_refresh, daemon=True)
        thread.start()
    
    def _run_startup_checks(self):
        """
        Run first-time setup wizard and update checks on startup.
        Called once at the end of __init__.
        """
        # Show Local AI banner if Ollama installed but no models
        if LOCAL_AI_SETUP_AVAILABLE and should_show_local_ai_banner(self.config):
            self.root.after(1000, self._show_local_ai_banner)
        
        # Show first-run wizard if never completed
        if should_show_first_run_wizard(self.config):
            def on_wizard_complete():
                # Mark as completed so it doesn't show again
                self.config = mark_wizard_completed(self.config)
                save_config(self.config)
            
            # Show after a brief delay to let main window appear first
            self.root.after(500, lambda: show_setup_wizard(self.root, on_wizard_complete))
        
        # Background update check (after wizard if shown)
        delay = 3000 if should_show_first_run_wizard(self.config) else 2000
        self.root.after(delay, self._startup_update_check)
        
        # Auto-refresh models if stale (>30 days old)
        # Run after update check with extra delay
        self.root.after(delay + 3000, self._startup_auto_refresh_models)
    

    def _show_local_ai_banner(self):
        """Show the Local AI setup banner at top of window"""
        if hasattr(self, 'local_ai_banner') and self.local_ai_banner:
            return  # Already showing
        
        def on_setup_click():
            self._dismiss_local_ai_banner()
            self._open_local_ai_setup()
        
        def on_dismiss_click():
            self._dismiss_local_ai_banner()
            # Remember dismissal
            self.config["local_ai_banner_dismissed"] = True
            save_config(self.config)
        
        self.local_ai_banner = create_local_ai_banner(
            self.root,
            on_setup_click,
            on_dismiss_click
        )
        # Pack at the very top
        self.local_ai_banner.pack(fill=tk.X, side=tk.TOP, before=list(self.root.children.values())[0])
    
    def _dismiss_local_ai_banner(self):
        """Hide and destroy the Local AI banner"""
        if hasattr(self, 'local_ai_banner') and self.local_ai_banner:
            self.local_ai_banner.destroy()
            self.local_ai_banner = None
    
    def _open_local_ai_setup(self):
        """Open the Local AI setup wizard"""
        if LOCAL_AI_SETUP_AVAILABLE:
            def on_complete(model_name):
                # Refresh the models list
                self._refresh_ollama_models(show_errors=False)
                # If currently on Ollama, refresh the dropdown
                if self.provider_var.get() == "Ollama (Local)":
                    combo = getattr(self, 'main_model_combo', None) or getattr(self, 'model_combo', None)
                    if combo:
                        combo['values'] = self.models.get("Ollama (Local)", [])
                    self.model_var.set(model_name)
                self.set_status(f"✅ Local AI ready - {model_name} installed")
            
            show_local_ai_setup(self.root, on_complete)

    def _open_local_model_manager(self):
        """Open the Local AI Model Manager dialog"""
        try:
            from local_model_manager import show_local_model_manager
            
            def on_models_changed():
                # Refresh the Ollama models list
                self._refresh_ollama_models(show_errors=False)
                # If currently on Ollama, refresh the dropdown
                if self.provider_var.get() == "Ollama (Local)":
                    combo = getattr(self, 'main_model_combo', None) or getattr(self, 'model_combo', None)
                    if combo:
                        combo['values'] = self.models.get("Ollama (Local)", [])
            
            show_local_model_manager(self.root, on_models_changed)
        except ImportError as e:
            from tkinter import messagebox
            messagebox.showerror("Error", f"Local Model Manager not available:\n{e}")

    def _save_update_preference(self):
        """Save the update check preference"""
        self.config["check_for_updates"] = self.check_updates_var.get()
        save_config(self.config)
    
    def _export_diagnostics(self):
        """
        Export system diagnostics to a text file for troubleshooting.
        Includes: version, dependencies, config (sanitized), system info.
        """
        import platform
        
        # Build diagnostic report
        lines = []
        lines.append("=" * 60)
        lines.append(f"{APP_DISPLAY_NAME} Diagnostic Report")
        lines.append("=" * 60)
        lines.append(f"Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        
        # Version info
        lines.append("VERSION INFO")
        lines.append("-" * 40)
        lines.append(f"App Version: {get_version_string()}")
        lines.append(f"Python Version: {platform.python_version()}")
        lines.append(f"Platform: {platform.platform()}")
        lines.append(f"Architecture: {platform.machine()}")
        lines.append("")
        
        # System summary
        summary = get_system_summary()
        
        lines.append("EXTERNAL DEPENDENCIES")
        lines.append("-" * 40)
        for name, dep in summary['dependencies'].items():
            status = "INSTALLED" if dep.installed else "NOT FOUND"
            version = f" (v{dep.version})" if dep.version else ""
            lines.append(f"{dep.name}: {status}{version}")
            if dep.path:
                lines.append(f"  Path: {dep.path}")
        lines.append("")
        
        # Python packages
        lines.append("PYTHON PACKAGES")
        lines.append("-" * 40)
        for name, (installed, purpose, version) in summary['packages'].items():
            status = "INSTALLED" if installed else "NOT INSTALLED"
            ver = f" (v{version})" if version else ""
            lines.append(f"{name}: {status}{ver}")
        lines.append("")
        
        # Faster-whisper details
        lines.append("FASTER-WHISPER STATUS")
        lines.append("-" * 40)
        whisper = get_faster_whisper_status()
        lines.append(f"Package Installed: {whisper.package_installed}")
        if whisper.package_installed:
            lines.append(f"Version: {whisper.package_version}")
            lines.append(f"CUDA Available: {whisper.cuda_available}")
            if whisper.cuda_available:
                lines.append(f"GPU: {whisper.gpu_name or 'Unknown'}")
                lines.append(f"CUDA Version: {whisper.cuda_version or 'Unknown'}")
            lines.append(f"Compute Type: {whisper.compute_type}")
            lines.append(f"Downloaded Models: {len(whisper.downloaded_models)}")
            for model in whisper.downloaded_models:
                lines.append(f"  - {model.name} ({model.size_display})")
            lines.append(f"Cache Directory: {whisper.cache_dir or 'Not found'}")
        lines.append("")
        
        # Feature availability
        lines.append("FEATURE AVAILABILITY")
        lines.append("-" * 40)
        feature_names = {
            'youtube': 'YouTube Transcripts',
            'substack': 'Substack Transcripts',
            'web': 'Web Articles',
            'documents': 'Document Files',
            'ocr': 'OCR (Scanned Docs)',
            'audio': 'Audio Transcription',
            'local_ai': 'Local Whisper',
            'drag_drop': 'Drag & Drop',
        }
        for key, name in feature_names.items():
            status = "Ready" if summary['features'].get(key) else "Not Available"
            lines.append(f"{name}: {status}")
        lines.append("")
        
        # Config (sanitized - no API keys)
        lines.append("CONFIGURATION (Sanitized)")
        lines.append("-" * 40)
        safe_config = {k: v for k, v in self.config.items() if k != 'keys'}
        for key, value in safe_config.items():
            lines.append(f"{key}: {value}")
        lines.append("")
        
        # Data directory
        lines.append("DATA LOCATIONS")
        lines.append("-" * 40)
        lines.append(f"Data Directory: {DATA_DIR}")
        lines.append(f"Config File: {CONFIG_PATH}")
        lines.append("")
        
        lines.append("=" * 60)
        lines.append("END OF DIAGNOSTIC REPORT")
        lines.append("=" * 60)
        
        # Join into text
        report = "\n".join(lines)
        
        # Ask where to save
        from tkinter import filedialog
        filepath = filedialog.asksaveasfilename(
            title="Save Diagnostic Report",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfilename=f"DocAnalyser_Diagnostics_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        )
        
        if filepath:
            try:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(report)
                self.set_status(f"✅ Diagnostics exported to {os.path.basename(filepath)}")
                messagebox.showinfo("Export Complete", f"Diagnostic report saved to:\n{filepath}")
            except Exception as e:
                messagebox.showerror("Export Error", f"Failed to save diagnostics:\n{str(e)}")

    def add_message_to_thread(self, role: str, content: str):
        """
        MVP: Add a message to the current conversation thread

        Args:
            role: "user" or "assistant"
            content: Message content
        """
        self.current_thread.append({
            "role": role,
            "content": content
        })

        # Update counter (only count user messages for display)
        if role == "user":
            self.thread_message_count += 1

        # Update status
        self.update_thread_status()
        
        # Update button states (conversation now exists)
        self.update_button_states()

    def update_thread_status(self):
        """MVP: Update the thread counter in status bar"""
        # Check document class
        is_response_document = getattr(self, 'current_document_class', 'source') in ['response', 'product', 'processed_output']
        
        if is_response_document and self.thread_message_count > 0:
            # Response document with existing conversation
            if self.thread_message_count == 1:
                msg = "💬 Thread: 1 message"
            else:
                msg = f"💬 Thread: {self.thread_message_count} messages"
            self.set_status(msg)
        elif self.thread_message_count == 0:
            # No thread - don't update status (keep existing "Source document saved" or similar message)
            # This prevents overwriting meaningful status messages when loading source documents
            pass
        elif self.thread_message_count == 1:
            msg = "💬 Thread: 1 message (AI remembers this exchange)"
            self.set_status(msg)
        else:
            msg = f"💬 Thread: {self.thread_message_count} messages (full context maintained)"
            self.set_status(msg)

    def clear_thread(self):
        """MVP: Clear the current thread when loading a new document"""
        # Save current thread before clearing (if there is one)
        if self.thread_message_count > 0 and self.current_document_id:
            self.save_current_thread()

        self.current_thread = []
        self.thread_message_count = 0
        self.thread_needs_document_refresh = False  # Reset flag when clearing thread
        self.update_thread_status()
        
        # Update button states (conversation no longer exists)
        self.update_button_states()

    def check_active_thread_before_load(self, new_doc_title: str = "new document") -> bool:
        """
        Check if there's an active conversation thread before loading a new document.
        Auto-saves conversations and notifies user if needed.
        
        Args:
            new_doc_title: Title of the document about to be loaded
            
        Returns:
            True (always proceeds - conversations are auto-saved)
        """
        # No active thread - OK to proceed
        if self.thread_message_count == 0:
            return True
        
        # Check if this is a standalone conversation (no source document)
        is_standalone = not self.current_document_id
        
        if is_standalone:
            # Standalone conversation - auto-save it to the library
            try:
                from document_library import add_document_to_library
                import datetime
                
                # Generate a title for the standalone conversation
                title = "Standalone Conversation"
                if self.current_thread and len(self.current_thread) > 0:
                    # Use first user message as basis for title
                    first_user_msg = next((m.get('content', '') for m in self.current_thread if m.get('role') == 'user'), '')
                    if first_user_msg:
                        title_preview = first_user_msg[:50].replace('\n', ' ')
                        if len(first_user_msg) > 50:
                            title_preview += "..."
                        title = f"Standalone: {title_preview}"
                
                # Create a text representation of the conversation
                conversation_text = ""
                for msg in self.current_thread:
                    role = msg.get('role', 'unknown').upper()
                    content = msg.get('content', '')
                    conversation_text += f"[{role}]\n{content}\n\n"
                
                # Create entries for the conversation
                entries = [{"text": conversation_text, "speaker": "conversation"}]
                
                # Metadata
                metadata = {
                    "model": self.model_var.get(),
                    "provider": self.provider_var.get(),
                    "created": datetime.datetime.now().isoformat(),
                    "message_count": self.thread_message_count,
                    "standalone": True
                }
                
                # Save to library as a conversation_thread type
                doc_id = add_document_to_library(
                    doc_type="conversation_thread",
                    source="Standalone conversation",
                    title=title,
                    entries=entries,
                    document_class="thread",
                    metadata=metadata,
                    conversation_thread=self.current_thread
                )
                
                if doc_id:
                    self.set_status(f"✅ Standalone conversation auto-saved to library")
                    print(f"📁 Auto-saved standalone conversation as document {doc_id}")
                    # Refresh library if open
                    self.refresh_library()
            except Exception as e:
                print(f"⚠️ Could not auto-save standalone conversation: {e}")
                import traceback
                traceback.print_exc()
                # Still proceed - don't block the user
        else:
            # Regular document with conversation - save_current_thread handles this
            # It's called in load_document_callback before changing document ID
            pass
        
        # Clear the thread and proceed
        self.clear_thread()
        return True

    def clear_preview_for_new_document(self):
        """
        Clear the preview area when starting to load a new document.
        This ensures users see fresh content and know loading has started.
        """
        # Reset document state
        self.current_document_text = None
        self.current_document_id = None
        reset_standalone_state()  # Reset standalone conversation tracking
        
        

        # Reset the progressive timestamp tracker for audio
        if hasattr(self, '_last_progressive_timestamp'):
            delattr(self, '_last_progressive_timestamp')
        
        # Update button states (disable buttons since no document loaded)
        self.update_button_states()

    def build_threaded_messages(self, new_prompt: str) -> list:
        """
        MVP: Build message list including conversation history and attachments

        Args:
            new_prompt: The new question/prompt from user

        Returns:
            List of messages for AI provider
        """
        messages = []

        # 1. System message
        messages.append({
            "role": "system",
            "content": "You are a helpful AI assistant analyzing documents. "
                       "Maintain context from previous messages in this conversation."
        })
        
        # 🆕 NEW: Build attachment text if any files are attached
        attachment_text = ""
        if hasattr(self, 'attachment_manager') and self.attachment_manager.get_attachment_count() > 0:
            attachment_text = "\n\n" + self.attachment_manager.build_attachment_text()
        
        # 🆕 NEW: Check if we have a main document loaded
        has_main_document = (hasattr(self, 'current_document_text') and 
                            self.current_document_text and 
                            self.current_document_text.strip())

        # Check if we need to re-include document (e.g., returning to saved thread later)
        needs_document_refresh = getattr(self, 'thread_needs_document_refresh', False)
        
        # 2. If this is the FIRST message OR we're resuming a saved thread, include the full document
        if len(self.current_thread) == 0:
            # Brand new conversation - include document
            if has_main_document:
                content = f"{new_prompt}\n\n--- DOCUMENT ---\n{self.current_document_text}"
            else:
                # No main document - just the prompt (attachments will be added below)
                content = new_prompt
            
            if attachment_text:
                content += attachment_text
            messages.append({
                "role": "user",
                "content": content
            })
        elif needs_document_refresh and has_main_document:
            # Resuming a saved conversation - re-include document for context
            print("\ud83d\udd04 Re-including document context for resumed conversation")
            
            # Add previous conversation history
            for msg in self.current_thread:
                messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
            
            # Add new prompt WITH document (AI needs it again since this is a new session)
            content = f"{new_prompt}\n\n--- DOCUMENT (for context) ---\n{self.current_document_text}"
            if attachment_text:
                content += attachment_text
            messages.append({
                "role": "user",
                "content": content
            })
            
            # Clear the flag - document has been re-sent
            self.thread_needs_document_refresh = False
            print("   \u2705 Document context re-sent, flag cleared")
        else:
            # 3. Add previous conversation history (continuing within same session)
            for msg in self.current_thread:
                messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })

            # 4. Add new prompt (without document - AI already has it from this session)
            # But include attachments if they're new
            content = new_prompt
            if attachment_text:
                content += attachment_text
            messages.append({
                "role": "user",
                "content": content
            })

        return messages

    def set_status(self, msg: str, include_thread_status: bool = False):
        """
        Update status bar message

        Args:
            msg: Status message to display
            include_thread_status: If True, append thread info to message
        """
        # Log status updates for debugging (uses logging instead of print to avoid encoding issues)
        if getattr(sys, 'frozen', False):
            logging.debug(f"Status update: {msg} (include_thread={include_thread_status})")

        if include_thread_status and hasattr(self, 'thread_message_count'):
            # Append thread info to the message (only when there IS a thread)
            if self.thread_message_count == 0:
                # No thread - don't append anything, just show the message as-is
                full_msg = msg
            elif self.thread_message_count == 1:
                full_msg = f"{msg} | 1 message in thread"
            else:
                full_msg = f"{msg} | {self.thread_message_count} messages"
            self.root.after(0, lambda: self.status_var.set(full_msg))
        else:
            # Just the message
            self.root.after(0, lambda: self.status_var.set(msg))

    def update_button_states(self):
        """
        Enable/disable buttons based on current application state.
        Each button has specific requirements for when it should be enabled.
        
        Note: AI Costs and Cancel buttons are NOT managed here:
          - AI Costs shows historical data, always accessible
          - Cancel is managed separately based on processing state
        """
        # Check various states
        has_document = (
            (hasattr(self, 'current_document_text') and self.current_document_text) or
            (hasattr(self, 'current_document_id') and self.current_document_id)
        )
        
        has_conversation = (
            hasattr(self, 'current_thread') and 
            len(self.current_thread) > 0
        )
        
        # View/Thread button: Dynamic label and state based on context
        # Uses the new unified viewer button state matrix
        self.update_view_button_state(has_document, has_conversation)
        
        # Save button: Enabled when document is loaded
        if hasattr(self, 'save_menu_btn'):
            self.save_menu_btn.config(state=tk.NORMAL if has_document else tk.DISABLED)
        
        # Run button: Only update highlight if enabled (gets disabled after Run is pressed)
        # Note: _run_highlight_enabled is set True when document loads, False when Run pressed
        if getattr(self, '_run_highlight_enabled', False):
            self._update_run_button_highlight(has_document)

    def update_view_button_state(self, has_document: bool = None, has_conversation: bool = None):
        """
        Update the View Source and View Thread button states based on context.
        
        Two-Button Model:
        - View Source: Enabled when a document is loaded, opens viewer in Source Mode
        - View Thread: Enabled when a conversation exists, opens viewer in Conversation Mode
        """
        # Handle both buttons - check if they exist
        has_source_btn = hasattr(self, 'view_source_btn')
        has_thread_btn = hasattr(self, 'view_thread_btn')
        
        if not has_source_btn and not has_thread_btn:
            return
        
        # Calculate states if not provided
        if has_document is None:
            has_document = (
                (hasattr(self, 'current_document_text') and self.current_document_text) or
                (hasattr(self, 'current_document_id') and self.current_document_id)
            )
            # Debug: Show what was checked
            doc_text_len = len(self.current_document_text) if hasattr(self, 'current_document_text') and self.current_document_text else 0
            doc_id_val = getattr(self, 'current_document_id', None)
            print(f"🔍 DEBUG: has_document calculated: text_len={doc_text_len}, doc_id={doc_id_val}, result={has_document}")
        
        if has_conversation is None:
            has_conversation = (
                hasattr(self, 'current_thread') and 
                len(self.current_thread) > 0
            )
        
        # Check if viewing a Response document (which has a conversation by definition)
        is_response_document = getattr(self, 'current_document_class', 'source') in ['response', 'product', 'processed_output']
        
        # Debug output
        thread_len = len(self.current_thread) if hasattr(self, 'current_thread') else 0
        print(f"🔘 update_view_button_state: has_doc={has_document}, has_conv={has_conversation}, is_response={is_response_document}, thread_len={thread_len}")
        
        # === View Source Button ===
        if has_source_btn:
            if has_document:
                self.view_source_btn.config(state=tk.NORMAL)
                print(f"✅ View Source button ENABLED")
            else:
                self.view_source_btn.config(state=tk.DISABLED)
                print(f"❌ View Source button DISABLED")
        
        # === View Thread Button ===
        if has_thread_btn:
            if has_conversation or is_response_document:
                # Show exchange count if available
                if thread_len > 2:
                    exchanges = thread_len // 2
                    self.view_thread_btn.config(text=f"💬 View Thread ({exchanges})", state=tk.NORMAL)
                else:
                    self.view_thread_btn.config(text="View Thread", state=tk.NORMAL)
            else:
                # No conversation - disable the button
                self.view_thread_btn.config(text="View Thread", state=tk.DISABLED)
    
    def on_viewer_mode_change(self, new_mode: str):
        """
        Callback from unified viewer when mode changes.
        Updates the main UI button to reflect the new mode.
        Also handles viewer window closure by cleaning up the tracking list.
        """
        if new_mode == 'closed':
            # A viewer was closed - clean up the tracking list
            self._cleanup_closed_viewers()
            print(f"   📺 Viewer closed ({len(self._thread_viewer_windows) if hasattr(self, '_thread_viewer_windows') else 0} remaining)")
        
        self.update_view_button_state()

    def validate_youtube_url(self, url_or_id: str) -> tuple:
        """Validate YouTube URL/ID. Returns (is_valid, error_message)"""
        if not url_or_id or not url_or_id.strip():
            return False, "Please enter a YouTube URL or ID"

        video_id = extract_video_id(url_or_id)
        if not video_id:
            return False, "Invalid YouTube URL or ID format"

        return True, ""

    def validate_file_path(self, filepath: str) -> tuple:
        """Validate file path. Returns (is_valid, error_message)"""
        if not filepath or not filepath.strip():
            return False, "Please select a file"

        if not os.path.exists(filepath):
            return False, f"File not found: {filepath}"

        if not os.path.isfile(filepath):
            return False, f"Path is not a file: {filepath}"

        # Check file size and warn if very large
        file_size = os.path.getsize(filepath)
        size_mb = file_size / (1024 * 1024)

        if size_mb > 100:
            response = messagebox.askyesno(
                "Large File Warning",
                f"This file is {size_mb:.1f} MB.\n\nLarge files may take a long time to process and could consume significant memory.\n\nContinue anyway?"
            )
            if not response:
                return False, "Processing cancelled by user"

        return True, ""

    def convert_spreadsheet_to_text(self, file_path: str) -> tuple:
        """
        Convert spreadsheet (XLSX, XLS, CSV) to text format for AI analysis.
        Returns (success: bool, text_content: str, title: str, error_msg: str)
        """
        if not PANDAS_AVAILABLE:
            return False, "", "", "pandas library not available - cannot read spreadsheets"
        
        try:
            ext = os.path.splitext(file_path)[1].lower()
            file_name = os.path.basename(file_path)
            
            # Read the spreadsheet based on file type
            if ext == '.csv':
                df = pd.read_csv(file_path)
                sheet_info = ""
            elif ext == '.xlsx':
                if not OPENPYXL_AVAILABLE:
                    return False, "", "", "openpyxl library required for .xlsx files"
                df = pd.read_excel(file_path, engine='openpyxl')
                sheet_info = " (first sheet)"
            elif ext == '.xls':
                if not XLRD_AVAILABLE:
                    return False, "", "", "xlrd library required for .xls files"
                df = pd.read_excel(file_path, engine='xlrd')
                sheet_info = " (first sheet)"
            else:
                return False, "", "", f"Unsupported spreadsheet format: {ext}"
            
            # Get basic info
            num_rows, num_cols = df.shape
            
            # Convert to text format
            # Use a clean table format that's easy for AI to read
            text_parts = []
            
            # Header with spreadsheet info
            text_parts.append(f"SPREADSHEET DATA: {file_name}{sheet_info}")
            text_parts.append(f"Dimensions: {num_rows} rows × {num_cols} columns")
            text_parts.append(f"Columns: {', '.join(df.columns.astype(str))}")
            text_parts.append("\n" + "="*80 + "\n")
            
            # Convert to markdown table format (clean and readable)
            # Limit to first 1000 rows to avoid token limits
            if num_rows > 1000:
                text_parts.append(f"NOTE: Showing first 1000 rows of {num_rows} total rows\n")
                df_display = df.head(1000)
            else:
                df_display = df
            
            # Convert to string format
            # Use to_csv for clean, parseable format
            csv_text = df_display.to_csv(index=False)
            text_parts.append(csv_text)
            
            # Add summary statistics for numeric columns
            numeric_cols = df.select_dtypes(include=['number']).columns
            if len(numeric_cols) > 0:
                text_parts.append("\n" + "="*80)
                text_parts.append("NUMERIC COLUMN SUMMARIES:")
                text_parts.append("="*80 + "\n")
                summary = df[numeric_cols].describe().to_string()
                text_parts.append(summary)
            
            final_text = "\n".join(text_parts)
            title = f"Spreadsheet: {file_name} ({num_rows} rows, {num_cols} columns)"
            
            return True, final_text, title, ""
            
        except Exception as e:
            error_msg = f"Error reading spreadsheet: {str(e)}"
            print(f"❌ {error_msg}")
            import traceback
            traceback.print_exc()
            return False, "", "", error_msg

    def validate_web_url(self, url: str) -> tuple[bool, str]:
        """Validate web URL format with improved pattern."""
        if not url:
            return False, "URL cannot be empty"

        # More permissive URL pattern that handles modern TLDs
        url_pattern = re.compile(
            r'https?://'  # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,}\.?|'  # domain (allows any TLD length)
            r'localhost|'  # localhost...
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)

        if not url_pattern.match(url):
            return False, "Invalid URL format. Please enter a valid HTTP/HTTPS URL."

        return True, ""

    def refresh_models_from_apis(self):
        """Refresh model list from AI provider APIs with AI-powered curation"""
        from model_updater import fetch_all_models, get_safe_fallback_models
        from config_manager import save_models
        
        # Show progress dialog
        progress_window = tk.Toplevel(self.root)
        progress_window.title("Refreshing Models")
        progress_window.geometry("400x150")
        self.apply_window_style(progress_window)
        progress_window.transient(self.root)
        
        ttk.Label(progress_window, text="Refreshing and optimizing model list...",
                 font=('Arial', 10)).pack(pady=20)
        
        status_var = tk.StringVar(value="Connecting...")
        status_label = ttk.Label(progress_window, textvariable=status_var)
        status_label.pack(pady=10)
        
        progress = ttk.Progressbar(progress_window, mode='indeterminate', length=300)
        progress.pack(pady=10)
        progress.start()
        
        def do_refresh():
            """Run in thread"""
            try:
                # Status callback - safely updates UI from background thread
                def update_status(msg):
                    try:
                        self.root.after(0, lambda: status_var.set(msg))
                    except:
                        pass  # Window may have been closed
                
                # Fetch and curate models using AI when available
                updated_models = fetch_all_models(self.config, status_callback=update_status)
                
                if not updated_models:
                    update_status("Using fallback models...")
                    updated_models = get_safe_fallback_models()
                
                # Merge with fallback for providers without API keys
                fallback = get_safe_fallback_models()
                for provider in fallback:
                    if provider not in updated_models:
                        updated_models[provider] = fallback[provider]
                
                # Update
                self.models = updated_models
                save_models(updated_models)
                
                # Count models per provider for summary
                model_counts = {p: len(m) for p, m in updated_models.items() if m}
                provider_count = len(model_counts)
                
                # Close progress and show result on main thread
                def show_result():
                    try:
                        progress_window.destroy()
                    except:
                        pass
                    
                    messagebox.showinfo(
                        "Models Updated",
                        f"✅ Model list optimized for {provider_count} provider(s)!\n\n"
                        f"Each provider now shows the best models for document analysis.\n"
                        f"Vision-capable models are prioritized for OCR/handwriting."
                    )
                    self.on_provider_select()
                
                self.root.after(0, show_result)
                
            except Exception as e:
                def show_error():
                    try:
                        progress_window.destroy()
                    except:
                        pass
                    messagebox.showerror("Error", f"Failed to update models:\n{str(e)}")
                
                self.root.after(0, show_error)
        
        # Run in background
        thread = threading.Thread(target=do_refresh)
        thread.daemon = True
        thread.start()

    def setup_ui(self):
        # Prevent root from resizing based on content
        self.root.pack_propagate(False)

        # Create a colored header bar at the very top
        self.header_bar = tk.Frame(self.root, bg='#9ecdd6', height=28)
        self.header_bar.pack(fill=tk.X, side=tk.TOP)
        self.header_bar.pack_propagate(False)  # Keep fixed height
        
        # Help label in the header bar
        help_label = tk.Label(self.header_bar, text="Help", bg='#9ecdd6', fg='#333333',
                              font=('Arial', 10), cursor='hand2', padx=10)
        help_label.pack(side=tk.LEFT, pady=4)
        
        # Bind click to show help menu
        def show_help_menu(event):
            menu = tk.Menu(self.root, tearoff=0)
            menu.add_command(label="Application Overview", command=self._show_app_overview)
            menu.add_command(label="📖 Local AI Guide", command=self._open_local_ai_guide)
            menu.add_separator()
            menu.add_command(label="📋 Feature Status...", command=self._show_system_check)
            menu.add_command(label="🔄 Check for Updates...", command=self._check_for_updates)
            menu.add_separator()
            menu.add_command(label="🔁 Show First-Run Wizard...", command=self._reset_and_show_wizard)
            menu.add_separator()
            menu.add_command(label="💡 Tip: Right-click buttons for help", state="disabled")
            menu.tk_popup(event.x_root, event.y_root)
        
        help_label.bind('<Button-1>', show_help_menu)
        
        # Hover effect
        help_label.bind('<Enter>', lambda e: help_label.config(bg='#7fcfdb'))
        help_label.bind('<Leave>', lambda e: help_label.config(bg='#9ecdd6'))
        
        # Settings label in the header bar (right-aligned)
        settings_label = tk.Label(self.header_bar, text="Settings", bg='#9ecdd6', fg='#333333',
                              font=('Arial', 10), cursor='hand2', padx=10)
        settings_label.pack(side=tk.RIGHT, pady=4)
        
        # Bind click to open settings
        settings_label.bind('<Button-1>', lambda e: self.open_settings())
        
        # Hover effect
        settings_label.bind('<Enter>', lambda e: settings_label.config(bg='#7fcfdb'))
        settings_label.bind('<Leave>', lambda e: settings_label.config(bg='#9ecdd6'))
        
        # Font size controls (between Help and Settings)
        # Initialize font size from config (default 10)
        self.font_size = self.config.get('font_size', 10)
        
        font_frame = tk.Frame(self.header_bar, bg='#9ecdd6')
        font_frame.pack(side=tk.RIGHT, padx=(0, 10), pady=2)
        
        # "Aa" label to indicate text size
        aa_label = tk.Label(font_frame, text="Aa", bg='#9ecdd6', fg='#333333',
                           font=('Arial', 9), padx=2)
        aa_label.pack(side=tk.LEFT)
        
        # A- button (decrease font size)
        decrease_btn = tk.Label(font_frame, text="−", bg='#9ecdd6', fg='#333333',
                               font=('Arial', 11, 'bold'), cursor='hand2', padx=4)
        decrease_btn.pack(side=tk.LEFT)
        decrease_btn.bind('<Button-1>', lambda e: self._adjust_font_size(-1))
        decrease_btn.bind('<Enter>', lambda e: decrease_btn.config(bg='#7fcfdb'))
        decrease_btn.bind('<Leave>', lambda e: decrease_btn.config(bg='#9ecdd6'))
        
        # A+ button (increase font size)
        increase_btn = tk.Label(font_frame, text="+", bg='#9ecdd6', fg='#333333',
                               font=('Arial', 11, 'bold'), cursor='hand2', padx=4)
        increase_btn.pack(side=tk.LEFT)
        increase_btn.bind('<Button-1>', lambda e: self._adjust_font_size(1))
        increase_btn.bind('<Enter>', lambda e: increase_btn.config(bg='#7fcfdb'))
        increase_btn.bind('<Leave>', lambda e: increase_btn.config(bg='#9ecdd6'))

        # Create a canvas with scrollbar for the entire UI
        canvas_frame = ttk.Frame(self.root)
        canvas_frame.pack(fill=tk.BOTH, expand=True)
        
        # Create canvas
        self.main_canvas = tk.Canvas(canvas_frame, highlightthickness=0, bg='#dcdad5')
        
        # Create scrollbar
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=self.main_canvas.yview)
        
        # Create the scrollable frame with reduced top padding
        self.scrollable_frame = ttk.Frame(self.main_canvas, padding=(10, 3, 10, 10))
        
        # Configure the canvas
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.main_canvas.configure(scrollregion=self.main_canvas.bbox("all"))
        )
        
        # Create window in canvas
        self.canvas_window = self.main_canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        
        # Configure canvas scrolling
        self.main_canvas.configure(yscrollcommand=scrollbar.set)
        
        # Bind canvas width changes to update scrollable frame width
        def on_canvas_configure(event):
            self.main_canvas.itemconfig(self.canvas_window, width=event.width)
        
        self.main_canvas.bind('<Configure>', on_canvas_configure)
        
        # Pack canvas and scrollbar
        self.main_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Enable mousewheel scrolling
        def _on_mousewheel(event):
            self.main_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
        # Bind mousewheel to canvas and all children
        self.main_canvas.bind_all("<MouseWheel>", _on_mousewheel)
        
        # Use scrollable_frame instead of main_frame for all UI components
        main_frame = self.scrollable_frame
        
        # Add help button in top-right corner
        self.setup_help_button(main_frame)

        # Build the UI components
        # 🆕 NEW: Universal input (replaces all tabs)
        self.setup_universal_input(main_frame)

        # Context-sensitive button frame
        self.setup_context_button_frame(main_frame)

        # Reordered to follow user workflow: Source → Prompt (with AI Config) → Preview
        self.setup_prompt_frame(main_frame)
        # AI selector is now integrated into setup_prompt_frame
        self.setup_control_frame(main_frame)
        self.setup_web_response_banner(main_frame)  # 🆕 NEW: Banner for capturing web responses
        self.setup_status_bar(main_frame)

    def setup_universal_input(self, parent):
        """
        Universal input field that accepts:
        - YouTube URLs
        - Web URLs  
        - Local file paths
        Auto-detects the type and processes accordingly.
        
        Always shows single-document input with option to add more sources.
        """
        # Main frame with title
        self.input_frame = ttk.LabelFrame(parent, text="Drag files/URLs here or paste paths (one per line), then click Load:", padding=(10, 3, 10, 3))
        self.input_frame.pack(fill=tk.BOTH, pady=(0, 3))
        
        # === Row 1: Input field with drop zone ===
        # Use Frame wrapper for consistent styling
        self.input_entry_row = tk.Frame(self.input_frame, bg='#E8F4F8', relief='solid', bd=1)
        self.input_entry_row.pack(fill=tk.BOTH, pady=(0, 5))
        
        # Use Text widget instead of Entry (Text widgets accept file drops on Windows, Entry often doesn't)
        # Configure as single-line to look like an Entry field
        self.universal_input_entry = tk.Text(
            self.input_entry_row,
            height=1,  # Start with 1 line, auto-expands only when needed
            wrap='word',  # Allow word wrapping for long paths
            bg=self.input_bg_color,
            font=('Arial', 10),
            relief='flat',
            bd=0,
            padx=5,
            pady=5
        )
        self.universal_input_entry.pack(fill=tk.BOTH, expand=True, padx=3, pady=3)
        
        # Bind events to sync Text widget with StringVar (Text doesn't support textvariable)
        def on_text_change(event=None):
            # Check if modified flag is set (prevents recursive calls)
            if self.universal_input_entry.edit_modified():
                content = self.universal_input_var.get()  # Get all text except trailing newline
                self.universal_input_var.set(content)
                # Reset the modified flag
                self.universal_input_entry.edit_modified(False)
                # Update Load button highlight based on content
                self._update_load_button_highlight()
        
        self.universal_input_entry.bind('<<Modified>>', on_text_change)
        
        # Clear placeholder on any keypress (before the key is processed)
        self.universal_input_entry.bind('<KeyPress>', self._clear_placeholder_on_input)
        
        # Multi-line input: Enter adds newline, Ctrl+Enter triggers load
        self.universal_input_entry.bind('<Control-Return>', lambda e: (self.smart_load(), 'break')[1])
        self.universal_input_entry.bind('<KeyRelease>', self._auto_expand_input)
        
        # Shift+Enter also triggers load (alternative shortcut)
        self.universal_input_entry.bind('<Shift-Return>', lambda e: (self.smart_load(), 'break')[1])
        
        if HELP_TEXTS:
            add_help(self.universal_input_entry, **HELP_TEXTS.get("universal_input", {"title": "Universal Input", "description": "Enter URL or file path"}))
        
        # Setup placeholder text system
        self.placeholder_active = False
        self.current_browse_mode = 'default'
        self.setup_placeholder_text()
        
        # Enable drag-and-drop if available
        # NOTE: On some Windows configurations, file drag-and-drop may be blocked by UAC/security policies
        # even when tkinterdnd2 is properly installed. URLs can still be dragged from browsers.
        # If file drag-and-drop doesn't work, users can use: Browse button or Copy as path → Paste
        if DND_AVAILABLE:
            # Register Text widget for BOTH files and text (Text widgets accept files reliably on Windows)
            self.universal_input_entry.drop_target_register(DND_FILES)
            self.universal_input_entry.drop_target_register(DND_TEXT)
            self.universal_input_entry.dnd_bind('<<Drop>>', self.on_drop)
            
            # Also register the FRAME as backup (in case drop hits the border)
            self.input_entry_row.drop_target_register(DND_FILES)
            self.input_entry_row.dnd_bind('<<Drop>>', self.on_drop)
            self.input_entry_row.dnd_bind('<<DragEnter>>', self.on_drag_enter)
            self.input_entry_row.dnd_bind('<<DragLeave>>', self.on_drag_leave)
            
            safe_print("Drag-and-drop enabled (using Text widget for better file drop support):")
            safe_print("   Text widget → DND_FILES + DND_TEXT")
            safe_print("   Frame → DND_FILES backup")
        
        # Bind Enter key to trigger load
        # Return adds newline (Ctrl+Enter or Shift+Enter to load)
        
        # === Primary Buttons Row (all on one line) ===
        self.input_button_row = ttk.Frame(self.input_frame)
        self.input_button_row.pack(fill=tk.X, pady=(2, 2))
        
        # Browse dropdown menu button (using ttk for consistent styling)
        self.browse_menu_btn = ttk.Menubutton(self.input_button_row, text="Browse...", width=11)
        self.browse_menu_btn.pack(side=tk.LEFT, padx=(0, 2))
        
        # Dictate button (speech-to-text) - placed first after Browse
        self.dictate_btn = ttk.Button(
            self.input_button_row, 
            text="Dictate", 
            command=self.start_dictation,
            width=14
        )
        self.dictate_btn.pack(side=tk.LEFT, padx=2)
        if HELP_TEXTS:
            add_help(self.dictate_btn, **HELP_TEXTS.get("dictate_button", {"title": "Dictate", "description": "Record speech to text"}))
        
        # Load button - processes all items in the input field
        self.load_btn = ttk.Button(
            self.input_button_row,
            text="Load",
            command=self.smart_load,
            width=14
            
        )
        self.load_btn.pack(side=tk.LEFT, padx=2)
        if HELP_TEXTS:
            add_help(self.load_btn, **HELP_TEXTS.get("load_button", {"title": "Load", "description": "Load all files/URLs listed above (Ctrl+Enter)"}))
        
        browse_menu = tk.Menu(self.browse_menu_btn, tearoff=0)
        self.browse_menu_btn.config(menu=browse_menu)
        
        browse_menu.add_command(
            label="📁 Windows File Explorer",
            command=lambda: self.browse_mode_selected('files')
        )
        browse_menu.add_command(
            label="🌐 Web browser",
            command=lambda: self.browse_mode_selected('web')
        )
        browse_menu.add_separator()
        browse_menu.add_command(
            label="📚 Documents Library",
            command=self.open_library_window
        )
        
        # Scan Pages button removed - functionality integrated into multi-file handling
        
        # Documents Library button (right-aligned to match Prompts Library button)
        self.docs_lib_btn = ttk.Button(
            self.input_button_row,
            text="Documents Library",
            command=self.open_library_window,
            width=21
        )
        self.docs_lib_btn.pack(side=tk.RIGHT, padx=(2, 0))

        # OCR Settings button (hidden by default, shown when scannable file is loaded)
        self.ocr_settings_btn = ttk.Button(
            self.input_button_row,
            text="OCR Settings",
            command=self.open_ocr_settings,
            width=14
        )
        # Don't pack yet - will be shown/hidden by update_context_buttons
        if HELP_TEXTS:
            add_help(self.ocr_settings_btn, **HELP_TEXTS.get("ocr_settings_button", {"title": "OCR Settings", "description": "Configure OCR settings for scanned documents and images"}))
            add_help(self.docs_lib_btn, **HELP_TEXTS.get("documents_library_button", {"title": "Documents Library", "description": "Browse saved documents"}))

        # Keep these variables for compatibility (but they won't be used for UI switching)
        self.source_mode_var = tk.StringVar(value="single")
        self.remember_source_mode_var = tk.BooleanVar(value=False)

    # ============================================================================
    # CHANGE 3: Add new method - setup_context_button_frame
    # ============================================================================

    def setup_context_button_frame(self, parent):
        """
        Create a dynamic button frame that shows/hides buttons based on file type
        """
        self.context_button_frame = ttk.LabelFrame(parent, text="File Actions", padding=10)
        # Don't pack it yet - it will be shown/hidden dynamically

        # Create all possible button sets (they'll be shown/hidden as needed)

        # === Audio Buttons ===
        self.audio_buttons_frame = ttk.Frame(self.context_button_frame)
        
        # Single row with all audio controls
        row1 = ttk.Frame(self.audio_buttons_frame)
        row1.pack(fill=tk.X, pady=2)
        
        audio_settings_btn = ttk.Button(row1, text="⚙️ Audio Settings",
                   command=self.open_audio_settings)
        audio_settings_btn.pack(side=tk.LEFT, padx=2)
        if HELP_TEXTS:
            add_help(audio_settings_btn, **HELP_TEXTS.get("audio_settings_button", {"title": "Audio Settings", "description": "Configure audio settings"}))
        
        self.bypass_cache_cb = ttk.Checkbutton(row1,
                                               text="🔄 Bypass cache",
                                               variable=self.bypass_cache_var)
        self.bypass_cache_cb.pack(side=tk.LEFT, padx=2)
        if HELP_TEXTS:
            add_help(self.bypass_cache_cb, **HELP_TEXTS.get("bypass_cache_checkbox", {"title": "Bypass Cache", "description": "Force re-transcription"}))
        
        # TurboScribe on same row
        if TURBOSCRIBE_AVAILABLE:
            send_ts_btn = ttk.Button(row1, text="🚀 Send to TurboScribe",
                       command=self.send_to_turboscribe)
            send_ts_btn.pack(side=tk.LEFT, padx=2)
            if HELP_TEXTS:
                add_help(send_ts_btn, **HELP_TEXTS.get("send_turboscribe_button", {"title": "Send to TurboScribe", "description": "Open TurboScribe"}))
            
            import_ts_btn = ttk.Button(row1, text="📥 Import Transcript",
                       command=self.import_turboscribe)
            import_ts_btn.pack(side=tk.LEFT, padx=2)
            if HELP_TEXTS:
                add_help(import_ts_btn, **HELP_TEXTS.get("import_turboscribe_button", {"title": "Import Transcript", "description": "Import TurboScribe transcript"}))

        # === Web URL Buttons ===
        # Removed - redundant with main Load button
        # self.web_buttons_frame = ttk.Frame(self.context_button_frame)

        # === Document Buttons (DOCX, TXT, RTF) ===
        self.document_buttons_frame = ttk.Frame(self.context_button_frame)
        reload_btn = ttk.Button(self.document_buttons_frame, text="📄 Reload Document",
                   command=self.fetch_local_file)
        reload_btn.pack(side=tk.LEFT, padx=5)
        if HELP_TEXTS:
            add_help(reload_btn, **HELP_TEXTS.get("reload_document_button", {"title": "Reload Document", "description": "Reload from source"}))
        
        export_btn = ttk.Button(self.document_buttons_frame, text="📝 Export as...",
                   command=self.export_document)
        export_btn.pack(side=tk.LEFT, padx=5)
        if HELP_TEXTS:
            add_help(export_btn, **HELP_TEXTS.get("export_document_button", {"title": "Export", "description": "Export document"}))

    # ============================================================================
    # CHANGE 4: Add new method - update_context_buttons
    # ============================================================================

    def update_context_buttons(self, file_type):
        """
        Show/hide appropriate buttons based on file type

        Args:
            file_type: One of 'pdf', 'pdf_scanned', 'audio', 'youtube', 'web', 'document', 'image', or None
        """
        self.current_file_type = file_type
        
        # Track if frame was previously hidden
        was_hidden = not self.context_button_frame.winfo_ismapped()

        # Hide all button frames first
        for frame in [self.audio_buttons_frame,
                      self.document_buttons_frame]:
            frame.pack_forget()

        # Show/hide OCR Settings button in top input row based on file type
        # Show for any file type that might need OCR (scanned PDFs, images)
        if file_type in ['pdf_scanned', 'image']:
            self.ocr_settings_btn.pack(side=tk.LEFT, padx=2, after=self.load_btn)
        else:
            self.ocr_settings_btn.pack_forget()

        # Audio fallback is always enabled (checkbox removed)

        # Types that don't need the context button frame
        if file_type in [None, 'youtube', 'web', 'pdf', 'pdf_scanned', 'image',
                         'spreadsheet', 'ocr', 'dictation', 'video_platform']:
            self.context_button_frame.pack_forget()
            self.update_view_button_state()
            return
        
        # Show the context button container for remaining file types
        self.context_button_frame.pack(fill=tk.X, pady=5,
                                       after=self.context_button_frame.master.winfo_children()[0])
        
        # Expand window if frame was just shown
        if was_hidden:
            self.root.update_idletasks()
            current_height = self.root.winfo_height()
            frame_height = 70  # Approximate height of context button frame
            new_height = current_height + frame_height
            current_width = self.root.winfo_width()
            self.root.geometry(f"{current_width}x{new_height}")

        # Show appropriate buttons based on file type
        if file_type == 'audio':
            self.context_button_frame.config(text="🎤 Audio Actions")
            self.audio_buttons_frame.pack(fill=tk.X, pady=5)

        elif file_type == 'document':
            self.context_button_frame.config(text="📝 Document Actions")
            self.document_buttons_frame.pack(fill=tk.X, pady=5)
        
        # Update View Source button state when document is loaded
        self.update_view_button_state()

    def setup_youtube_tab(self, notebook):
        yt_frame = ttk.Frame(notebook, padding=10)
        notebook.add(yt_frame, text="YouTube")
        ttk.Label(yt_frame, text="YouTube Video URL or ID:", font=('Arial', 10, 'bold')).pack(anchor=tk.W, pady=(10, 5))
        input_frame = ttk.Frame(yt_frame)
        input_frame.pack(fill=tk.X, pady=5)
        self.yt_url_var = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.yt_url_var, width=30).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(input_frame, text="Fetch Transcript", command=self.fetch_youtube).pack(side=tk.LEFT, padx=5)
        # Audio fallback is always enabled (hard-coded True in __init__)

    def setup_file_tab(self, notebook):
        file_frame = ttk.Frame(notebook, padding=10)
        notebook.add(file_frame, text="Local File")
        ttk.Label(file_frame, text="Select File:", font=('Arial', 10, 'bold')).pack(anchor=tk.W, pady=(10, 5))
        input_frame = ttk.Frame(file_frame)
        input_frame.pack(fill=tk.X, pady=5)
        self.file_path_var = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.file_path_var, width=30).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(input_frame, text="Browse...", command=self.browse_file).pack(side=tk.LEFT, padx=5)
        ttk.Button(input_frame, text="Load File", command=self.fetch_local_file).pack(side=tk.LEFT, padx=5)

        # Force reprocess checkbox - ADD THESE 4 NEW LINES
        reprocess_frame = ttk.Frame(file_frame)
        reprocess_frame.pack(fill=tk.X, pady=5)
        ttk.Checkbutton(reprocess_frame, text="🔄 Force reprocess (ignore cache, use current OCR settings)",
                        variable=self.force_reprocess_var).pack(anchor=tk.W, padx=5)

        # Dictation section - record speech to text
        ttk.Separator(file_frame, orient='horizontal').pack(fill=tk.X, pady=10)
        dictate_frame = ttk.Frame(file_frame)
        dictate_frame.pack(fill=tk.X, pady=5)
        
        self.dictate_btn = ttk.Button(
            dictate_frame, 
            text="Dictate",
            command=self.start_dictation,
            width=16
        )
        self.dictate_btn.pack(side=tk.LEFT, padx=5)
        
        # Help text with mode indicator
        self.dictation_mode_label = ttk.Label(
            dictate_frame, 
            text="Record speech → text",
            font=('Arial', 9),
            foreground='gray'
        )
        self.dictation_mode_label.pack(side=tk.LEFT, padx=10)

    def setup_audio_tab(self, notebook):
        """Simplified - buttons moved to context frame"""
        audio_frame = ttk.Frame(notebook, padding=10)
        notebook.add(audio_frame, text="Audio File")
        ttk.Label(audio_frame, text="Audio Transcription",
                  font=('Arial', 12, 'bold')).pack(anchor=tk.W, pady=(10, 5))
        input_frame = ttk.Frame(audio_frame)
        input_frame.pack(fill=tk.X, pady=5)
        self.audio_path_var = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.audio_path_var, width=30).pack(
            side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(input_frame, text="Browse...",
                   command=self.browse_audio_file).pack(side=tk.LEFT, padx=5)
        ttk.Button(input_frame, text="Load Audio",
                   command=lambda: [self.update_context_buttons('audio')]).pack(side=tk.LEFT, padx=5)
        # Removed: Transcribe Audio button (now in context frame)
        # Removed: Audio Settings button (now in context frame)
        # Removed: Bypass cache checkbox (now in context frame)

    def setup_web_tab(self, notebook):
        web_frame = ttk.Frame(notebook, padding=10)
        notebook.add(web_frame, text="Web URL")
        ttk.Label(web_frame, text="Web URL:", font=('Arial', 10, 'bold')).pack(anchor=tk.W, pady=(10, 5))
        input_frame = ttk.Frame(web_frame)
        input_frame.pack(fill=tk.X, pady=5)
        self.web_url_var = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.web_url_var, width=30).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(input_frame, text="Fetch Content", command=self.fetch_web).pack(side=tk.LEFT, padx=5)

    def browse_universal_file(self):
        """Browse for any supported file type"""
        filetypes = [
            ("All Supported Files", "*.pdf *.txt *.doc *.docx *.rtf *.xlsx *.xls *.csv *.mp3 *.wav *.m4a *.ogg *.flac *.mp4 *.avi *.mov"),
            ("PDF files", "*.pdf"),
            ("Document files", "*.txt *.doc *.docx *.rtf"),
            ("Spreadsheet files", "*.xlsx *.xls *.csv"),
            ("Audio/Video files", "*.mp3 *.wav *.m4a *.ogg *.flac *.mp4 *.avi *.mov"),
            ("All files", "*.*")
        ]
        
        filepath = filedialog.askopenfilename(
            title="Select a file",
            filetypes=filetypes
        )
        
        if filepath:
            print(f"📁 Browse selected file: {filepath}")
            
            # Clear placeholder and set the filepath in Text widget
            if hasattr(self, 'placeholder_active'):
                self.placeholder_active = False
                print("   ✓ Cleared placeholder")
            
            # Update Text widget
            # Append to existing content (multi-line support)
            current = self.universal_input_entry.get('1.0', 'end-1c').strip()
            if current and not self.placeholder_active:
                # Append on new line
                self.universal_input_entry.insert('end', '\n' + filepath)
            else:
                # Replace placeholder or empty
                self.universal_input_entry.delete('1.0', 'end')
                self.universal_input_entry.insert('1.0', filepath)
            self._auto_expand_input()
            self.universal_input_entry.config(foreground='black')
            
            # Reset modified flag to prevent event conflicts
            try:
                self.universal_input_entry.edit_modified(False)
            except:
                pass
            
            # Keep StringVar in sync
            self.universal_input_var.set(filepath)
            print(f"   ✓ Set input to: {filepath}")
            
            # NO auto-load - user clicks Load button
            if hasattr(self, '_auto_expand_input'):
                self._auto_expand_input()
            line_count = len(self.universal_input_entry.get('1.0', 'end-1c').strip().split('\n'))
            self.set_status(f"📋 {line_count} item(s) ready - Click Load or Ctrl+Enter")
    
    def _auto_load_after_browse(self, filepath):
        """Helper to auto-load file after browse selection"""
        print(f"🚀 Auto-loading file from browse: {filepath}")
        print(f"   Input field contains: {self.universal_input_var.get()}")
        print(f"   StringVar contains: {self.universal_input_var.get()}")
        
        # Ensure values are synced
        if self.universal_input_var.get() != filepath:
            print(f"   ⚠️ Syncing StringVar to: {filepath}")
            self.universal_input_var.set(filepath)
        
        # Call smart_load
        self.smart_load()
    
    def browse_mode_selected(self, mode):
        """Handle browse mode selection from dropdown"""
        import webbrowser
        
        if mode == 'files':
            # Open Windows Explorer (not file dialog) so user can drag files
            self.current_browse_mode = 'files'
            self.update_placeholder('files')
            self.open_file_explorer()
        
        elif mode == 'web':
            # Open/focus web browser
            self.current_browse_mode = 'web'
            self.update_placeholder('web')
            try:
                import platform
                import subprocess
                
                if platform.system() == 'Windows':
                    # Windows: Use 'start' with empty string to open default browser
                    # The empty string after 'start' opens the default browser
                    # Use simple webbrowser module instead
                    webbrowser.open('https://www.google.com')
                    # Position browser on left half of screen (longer delay for browser startup)
                    self._position_window_left_half(window_type='browser', delay_ms=1500)
                elif platform.system() == 'Darwin':  # Mac
                    # Mac: Use 'open' command
                    subprocess.Popen(['open', 'https://www.google.com'])
                else:  # Linux and others
                    # Use webbrowser module (works well on Linux)
                    webbrowser.open('https://www.google.com')
            except Exception as e:
                print(f"Could not open browser: {e}")
                # Universal fallback: webbrowser module
                try:
                    webbrowser.open('https://www.google.com')
                except Exception as e2:
                    print(f"Fallback also failed: {e2}")
    
    def _position_window_left_half(self, window_type='explorer', delay_ms=300):
        """
        Position a newly opened Explorer or Browser window on the left half of the screen.
        Uses Windows API via ctypes to find windows by class name.
        
        Args:
            window_type: 'explorer' or 'browser'
            delay_ms: Milliseconds to wait before positioning (allows window to appear)
        """
        import platform
        if platform.system() != 'Windows':
            return
        
        def do_position(attempt=1, max_attempts=3):
            try:
                import ctypes
                from ctypes import wintypes
                
                user32 = ctypes.windll.user32
                
                # Get screen dimensions
                screen_width = user32.GetSystemMetrics(0)  # SM_CXSCREEN
                screen_height = user32.GetSystemMetrics(1)  # SM_CYSCREEN
                
                # Calculate left half position (with small margin)
                margin = 10
                left = margin
                top = margin
                width = (screen_width // 2) - (margin * 2)
                height = screen_height - (margin * 2) - 40  # Account for taskbar
                
                hwnd = None
                
                if window_type == 'explorer':
                    # Find Explorer window by class name "CabinetWClass"
                    hwnd = user32.FindWindowW("CabinetWClass", None)
                    
                elif window_type == 'browser':
                    # Try to find browser window - use EnumWindows to find by title containing "Google"
                    # since we just opened google.com
                    
                    # First try finding by title
                    EnumWindows = user32.EnumWindows
                    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int))
                    GetWindowTextW = user32.GetWindowTextW
                    GetWindowTextLengthW = user32.GetWindowTextLengthW
                    IsWindowVisible = user32.IsWindowVisible
                    
                    found_windows = []
                    
                    def enum_callback(hwnd_ptr, lParam):
                        hwnd_val = hwnd_ptr
                        if IsWindowVisible(hwnd_val):
                            length = GetWindowTextLengthW(hwnd_val)
                            if length > 0:
                                buff = ctypes.create_unicode_buffer(length + 1)
                                GetWindowTextW(hwnd_val, buff, length + 1)
                                title = buff.value
                                # Look for Google in title (we just opened google.com)
                                if 'Google' in title or 'google' in title.lower():
                                    found_windows.append((hwnd_val, title))
                        return True
                    
                    EnumWindows(EnumWindowsProc(enum_callback), 0)
                    
                    if found_windows:
                        hwnd = found_windows[0][0]
                        print(f"📐 Found browser window by title: '{found_windows[0][1]}'")
                    else:
                        # Fallback: try common browser window class names
                        browser_classes = [
                            "Chrome_WidgetWin_1",      # Chrome, Edge (Chromium), Brave
                            "MozillaWindowClass",      # Firefox
                            "ApplicationFrameWindow",  # Edge Legacy, some UWP browsers
                            "IEFrame",                 # Internet Explorer
                            "OperaWindowClass",        # Opera
                        ]
                        for class_name in browser_classes:
                            hwnd = user32.FindWindowW(class_name, None)
                            if hwnd:
                                print(f"📐 Found browser window with class: {class_name}")
                                break
                
                if not hwnd:
                    print(f"⚠️ Could not find {window_type} window (attempt {attempt})")
                    if attempt < max_attempts:
                        # Retry after another delay
                        self.root.after(500, lambda: do_position(attempt + 1, max_attempts))
                    return
                
                print(f"📐 Attempt {attempt}: Positioning {window_type} window (hwnd={hwnd})")
                
                # First, restore the window if it's maximized
                SW_RESTORE = 9
                SW_SHOWNORMAL = 1
                user32.ShowWindow(hwnd, SW_RESTORE)
                
                # Small delay to let restore complete
                import time
                time.sleep(0.1)
                
                # Use MoveWindow which is sometimes more reliable than SetWindowPos
                result = user32.MoveWindow(hwnd, left, top, width, height, True)
                
                if result:
                    print(f"📐 Positioned {window_type} on left half: {width}x{height} at ({left}, {top})")
                else:
                    error = ctypes.get_last_error()
                    print(f"⚠️ MoveWindow failed for {window_type} (error: {error})")
                    
                    # Try SetWindowPos as fallback
                    SWP_NOZORDER = 0x0004
                    SWP_SHOWWINDOW = 0x0040
                    SWP_FRAMECHANGED = 0x0020
                    result2 = user32.SetWindowPos(hwnd, None, left, top, width, height, 
                                                   SWP_NOZORDER | SWP_SHOWWINDOW | SWP_FRAMECHANGED)
                    if result2:
                        print(f"📐 SetWindowPos succeeded for {window_type}")
                    else:
                        print(f"⚠️ SetWindowPos also failed for {window_type}")
                
            except Exception as e:
                print(f"⚠️ Could not position {window_type} window: {e}")
                import traceback
                traceback.print_exc()
        
        # Schedule positioning after delay to allow window to appear
        self.root.after(delay_ms, lambda: do_position(1, 3))
    
    def open_file_explorer(self):
        """Open Windows File Explorer so user can drag files into the input field."""
        import subprocess
        import platform
        
        # Determine starting folder
        start_folder = None
        
        # Check if we have a last used folder in config
        if hasattr(self, 'config') and 'last_folder' in self.config:
            last_folder = self.config.get('last_folder', '')
            if last_folder and os.path.isdir(last_folder):
                start_folder = last_folder
        
        # Fallback to Documents
        if not start_folder:
            docs_folder = os.path.expanduser('~/Documents')
            if os.path.isdir(docs_folder):
                start_folder = docs_folder
        
        # Final fallback to home directory
        if not start_folder:
            start_folder = os.path.expanduser('~')
        
        print(f"📁 Opening Explorer at: {start_folder}")
        
        try:
            if platform.system() == 'Windows':
                subprocess.Popen(['explorer', start_folder])
                # Position Explorer on left half of screen
                self._position_window_left_half(window_type='explorer', delay_ms=400)
            elif platform.system() == 'Darwin':
                subprocess.Popen(['open', start_folder])
            else:
                for fm in ['nautilus', 'dolphin', 'thunar', 'pcmanfm', 'xdg-open']:
                    try:
                        subprocess.Popen([fm, start_folder])
                        break
                    except FileNotFoundError:
                        continue
            
            self.set_status("📁 Explorer opened - drag files into the input box above, then click Load")
            
        except Exception as e:
            print(f"❌ Could not open file explorer: {e}")
            self.set_status("⚠️ Could not open Explorer - using file dialog instead")
            self.browse_universal_file()

    def on_browse_menu_open(self):
        """Called when browse menu is opened - save current state"""
        print("📂 MENU OPENED!")  # DEBUG
        # Save the current placeholder state when menu opens
        self.browse_menu_open_mode = getattr(self, 'current_browse_mode', 'default')
        print(f"   Saved mode: {self.browse_menu_open_mode}")  # DEBUG
    
    def on_browse_menu_hover(self, event):
        """Handle hover over menu items - preview placeholder text"""
        print("🔍 HOVER EVENT TRIGGERED!")  # DEBUG
        try:
            # Get the menu item under cursor
            menu = event.widget
            index = menu.index(f"@{event.y}")
            print(f"   Menu index: {index}")  # DEBUG
            
            if index is not None:
                # Get the label of the hovered item
                label = menu.entrycget(index, 'label')
                print(f"   Label: {label}")  # DEBUG
                
                # Preview placeholder based on hovered item
                if '📁 Files' in label:
                    print("   → Setting 'files' placeholder")  # DEBUG
                    self.update_placeholder('files')
                elif '🌐 Web' in label:
                    print("   → Setting 'web' placeholder")  # DEBUG
                    self.update_placeholder('web')
                else:
                    print(f"   ⚠️ Label didn't match: '{label}'")  # DEBUG
        except Exception as e:
            print(f"   ❌ Exception in hover: {e}")  # DEBUG
            # If any error (mouse not over item, etc.), restore original
            if hasattr(self, 'browse_menu_open_mode'):
                self.update_placeholder(self.browse_menu_open_mode)
    
    def setup_placeholder_text(self):
        """Setup placeholder text system for universal input"""
        # Bind focus events first
        self.universal_input_entry.bind('<FocusIn>', self.on_entry_focus_in)
        self.universal_input_entry.bind('<FocusOut>', self.on_entry_focus_out)
        
        # Set initial placeholder after a short delay so widget is fully ready
        # and doesn't get focus during startup which would clear it
        self.root.after(100, self._set_initial_placeholder)
    
    def _set_initial_placeholder(self):
        """Set the initial placeholder text (called after UI is ready)"""
        # Only set if field is still empty
        current = self.universal_input_entry.get('1.0', 'end-1c').strip()
        if not current:
            self.update_placeholder('default')
    
    def update_placeholder(self, mode='default'):
        """Set placeholder text in the input field"""
        # Only set placeholder if field is empty (or only has placeholder)
        current_text = self.universal_input_entry.get('1.0', 'end-1c').strip()
        if current_text and not self.placeholder_active:
            return
        
        # Clear and set placeholder
        self.universal_input_entry.delete('1.0', 'end')
        placeholder = "Enter file path(s)/URL(s) using drag-and-drop, copy-paste or direct entry."
        self.universal_input_entry.insert('1.0', placeholder)
        self.universal_input_entry.config(foreground='#888888')  # Light grey
        self.placeholder_active = True
        
        # Reset Load button highlight (placeholder means nothing to load)
        self._update_load_button_highlight()
        
        # Remove focus from input so placeholder stays visible
        try:
            self.root.focus_set()
        except:
            pass
    
    def on_entry_focus_in(self, event):
        """Clear placeholder when user clicks in field"""
        if self.placeholder_active:
            self.universal_input_entry.delete('1.0', 'end')
            self.universal_input_entry.config(foreground='black')
            self.placeholder_active = False
            self.universal_input_var.set('')
    
    def on_entry_focus_out(self, event):
        """Restore placeholder if field is empty when focus leaves"""
        current_text = self.universal_input_entry.get('1.0', 'end-1c').strip()
        if not current_text:
            self.update_placeholder()
    
    def _clear_placeholder_on_input(self, event=None):
        """Clear placeholder when user starts typing or pasting"""
        if self.placeholder_active:
            # Don't clear for modifier keys, navigation keys, etc.
            if event and event.keysym in ('Shift_L', 'Shift_R', 'Control_L', 'Control_R', 
                                          'Alt_L', 'Alt_R', 'Caps_Lock', 'Escape',
                                          'Up', 'Down', 'Left', 'Right', 'Home', 'End',
                                          'Prior', 'Next', 'Insert', 'F1', 'F2', 'F3', 
                                          'F4', 'F5', 'F6', 'F7', 'F8', 'F9', 'F10', 
                                          'F11', 'F12'):
                return  # Don't clear for these keys
            
            # Clear placeholder
            self.universal_input_entry.delete('1.0', 'end')
            self.universal_input_entry.config(foreground='black')
            self.placeholder_active = False

    def on_drag_enter(self, event):
        """Visual feedback when file is dragged over the drop zone"""
        self.input_entry_row.config(bg='#C8E4F8', relief='solid', bd=2)
        return event.action
    
    def on_drag_leave(self, event):
        """Reset visual feedback when file leaves the drop zone"""
        self.input_entry_row.config(bg='#E8F4F8', relief='solid', bd=1)
        return event.action
    
    def on_drop(self, event):
        """
        Handle drag-and-drop events for files and URLs.
        
        Supports:
        - Multiple file paths from Windows Explorer (one per line)
        - URLs from web browsers (as .url shortcuts or direct text)
        - Text selections
        """
        print("\n" + "=" * 60)
        print("🎯 on_drop() TRIGGERED")
        print("=" * 60)
        dropped = event.data
        print(f"🔍 Raw drop data: '{dropped}'")
        print(f"🔍 Data type: {type(dropped)}")
        print(f"🔍 Data length: {len(dropped) if dropped else 0}")
        print("=" * 60)
        
        # Parse the dropped data - could be single or multiple files
        items = self._parse_dropped_items(dropped)
        print(f"🔍 Parsed {len(items)} item(s)")
        
        if not items:
            print("❌ No valid items found in drop data")
            return event.action
        
        # Process each item (handle .url files, etc.)
        processed_items = []
        for item in items:
            processed = self._process_dropped_item(item)
            if processed:
                processed_items.append(processed)
        
        if not processed_items:
            return event.action
        
        print(f"📥 Processed {len(processed_items)} item(s)")
        for item in processed_items:
            print(f"   • {item}")
        
        # Clear placeholder if active
        if hasattr(self, 'placeholder_active') and self.placeholder_active:
            self.universal_input_entry.delete('1.0', 'end')
            self.universal_input_entry.config(foreground='black')
            self.placeholder_active = False
        
        # Get current content (if any real content, not placeholder)
        current = self.universal_input_entry.get('1.0', 'end-1c').strip()
        if self.placeholder_active:
            current = ""
        
        # Build the new content
        new_content = '\n'.join(processed_items)
        
        if current:
            # Append to existing content
            self.universal_input_entry.insert('end', '\n' + new_content)
        else:
            # Replace content
            self.universal_input_entry.delete('1.0', 'end')
            self.universal_input_entry.insert('1.0', new_content)
        
        self.universal_input_entry.config(foreground='black')
        self.placeholder_active = False
        
        # Trigger auto-expand to show all lines
        if hasattr(self, '_auto_expand_input'):
            self._auto_expand_input()
        
        # Highlight Load button to draw attention
        self._update_load_button_highlight()
        
        # Update status
        total_lines = len(self.universal_input_entry.get('1.0', 'end-1c').strip().split('\n'))
        self.set_status(f"📋 {total_lines} item(s) ready - Click Load or press Ctrl+Enter")
        
        # Reset drop zone visual feedback
        self.input_entry_row.config(bg='#E8F4F8', relief='solid', bd=1)
        
        return event.action
    
    def _parse_dropped_items(self, dropped: str) -> list:
        """
        Parse dropped data into a list of file paths or URLs.
        
        Windows Explorer drops multiple files in format:
        - {C:/path/file1.pdf} {C:/path/file2.pdf}  (paths with spaces get braces)
        - C:/simple/path.pdf {C:/path with spaces/file.pdf}
        
        Args:
            dropped: Raw drop data string
            
        Returns:
            List of file paths/URLs
        """
        import re
        
        if not dropped:
            return []
        
        dropped = dropped.strip()
        items = []
        
        # Check if it looks like multiple Windows paths with braces
        # Pattern: {path} or path separated by spaces
        if '{' in dropped:
            # Extract all brace-wrapped paths: {C:\path	oile.pdf}
            brace_pattern = r'\{([^}]+)\}'
            brace_matches = re.findall(brace_pattern, dropped)
            
            if brace_matches:
                items.extend(brace_matches)
                # Remove matched items to see if there's anything left
                remaining = re.sub(brace_pattern, '', dropped).strip()
                
                # Check for non-braced paths in remaining (simple paths without spaces)
                if remaining:
                    # Split by whitespace and filter valid paths
                    for part in remaining.split():
                        part = part.strip()
                        if part and (os.path.exists(part) or part.startswith('http')):
                            items.append(part)
            else:
                # Single item wrapped in braces
                if dropped.startswith('{') and dropped.endswith('}'):
                    items.append(dropped[1:-1])
                else:
                    items.append(dropped)
        else:
            # No braces - could be single path, URL, or space-separated simple paths
            if dropped.startswith('http') or os.path.exists(dropped):
                # Single item
                items.append(dropped)
            else:
                # Try splitting - but be careful with paths that might have spaces
                # First check if the whole thing is a valid path
                if os.path.exists(dropped):
                    items.append(dropped)
                else:
                    # Try space-splitting for multiple simple paths
                    parts = dropped.split()
                    for part in parts:
                        part = part.strip().strip('"').strip("'")
                        if part:
                            items.append(part)
        
        # Clean up items
        cleaned = []
        for item in items:
            item = item.strip().strip('"').strip("'")
            if item:
                cleaned.append(item)
        
        return cleaned
    
    def _process_dropped_item(self, item: str) -> str:
        """
        Process a single dropped item (handle .url files, clean paths, etc.)
        
        Args:
            item: A file path or URL
            
        Returns:
            Processed path/URL, or empty string if invalid
        """
        import configparser
        
        if not item:
            return ""
        
        # Handle .url files (browser shortcuts)
        if item.lower().endswith('.url') and os.path.isfile(item):
            try:
                config = configparser.ConfigParser(interpolation=None)
                config.read(item, encoding='utf-8')
                
                if 'InternetShortcut' in config and 'URL' in config['InternetShortcut']:
                    actual_url = config['InternetShortcut']['URL']
                    print(f"📎 Extracted URL from shortcut: {actual_url}")
                    return actual_url
                else:
                    print(f"⚠️ Could not extract URL from: {item}")
                    return ""
            except Exception as e:
                print(f"❌ Error reading .url file {item}: {e}")
                return ""
        
        return item

    def smart_load(self):
        """
        Smart loader that auto-detects input type...
        """
        # Reset Load button highlight immediately
        if hasattr(self, 'load_btn'):
            self.load_btn.configure(style='TButton')
            self.root.update_idletasks()  # Force immediate UI update
        
        print("=" * 60)
        print("🚀 DEBUG smart_load() ENTRY")
        print(f"   universal_input_var='{self.universal_input_var.get()}'")
        print(f"   processing={self.processing}")

        if self.processing:
            print("⚠️ Already processing, showing warning")
            messagebox.showwarning("Warning", "Processing already in progress. Please wait or cancel.")
            return
        print("✅ Not currently processing")

        # Read from Text widget (supports multiple lines)
        try:
            raw_input = self.universal_input_entry.get('1.0', 'end-1c').strip()
        except:
            raw_input = self.universal_input_var.get().strip()
        
        # Split into lines and filter empty ones
        input_lines = [line.strip() for line in raw_input.split('\n') if line.strip()]
        
        # If multiple lines, process them as batch
        if len(input_lines) > 1:
            print(f"📝 Multiple inputs detected: {len(input_lines)} items")
            self._process_multiple_inputs(input_lines)
            return
        
        # Single line - process normally
        input_value = input_lines[0] if input_lines else ''
        print(f"📝 Input value from Text widget: '{input_value}'")
        print(f"📝 StringVar value: '{self.universal_input_var.get()}'")
        print(f"📝 Placeholder active: {getattr(self, 'placeholder_active', 'N/A')}")
        
        # Skip if it's placeholder text
        if hasattr(self, 'placeholder_active') and self.placeholder_active:
            print("⚠️ Placeholder is active, ignoring")
            messagebox.showwarning("Empty Input", "Please enter a URL or select a file.")
            return
        
        if not input_value:
            print("❌ Empty input")
            messagebox.showwarning("Empty Input", "Please enter a URL or select a file.")
            return
        
        # Check for active conversation thread before loading new document
        # Extract a title preview from input for the dialog
        if input_value.startswith('http'):
            new_doc_preview = input_value[:60] + "..." if len(input_value) > 60 else input_value
        else:
            # File path - use filename
            import os
            new_doc_preview = os.path.basename(input_value)
        
        if not self.check_active_thread_before_load(new_doc_preview):
            print("❌ User cancelled loading due to active thread")
            return

        # Clear preview immediately so user knows something is happening
        self.clear_preview_for_new_document()
        
        # ============================================
        # AUTO-DETECTION LOGIC
        # ============================================

        # 1. CHECK FOR YOUTUBE
        is_youtube = self.is_youtube_url(input_value)
        print(f"🎬 Is YouTube URL? {is_youtube}")

        if is_youtube:
            print(f"✅ Detected as YouTube, setting yt_url_var and calling fetch_youtube()")
            self.yt_url_var.set(input_value)
            print(f"   yt_url_var now contains: '{self.yt_url_var.get()}'")
            self.fetch_youtube()
            print("   fetch_youtube() called")
            return

        # 2. CHECK FOR SUBSTACK
        print(f"🔍 Checking Substack... SUBSTACK_AVAILABLE={SUBSTACK_AVAILABLE}")
        if SUBSTACK_AVAILABLE:
            from substack_utils import is_substack_url
            is_sub = is_substack_url(input_value)
            print(f"🔍 is_substack_url returned: {is_sub}")
            if is_sub:
                print(f"✅ Detected as Substack, fetching transcript")
                self.fetch_substack()
                return
        else:
            # If substack_utils not available, check pattern manually
            if 'substack.com' in input_value.lower():
                print(f"⚠️ Substack URL detected but substack_utils not available")
                messagebox.showinfo("Substack Support",
                                    "This appears to be a Substack URL.\n\n"
                                    "To enable Substack transcript scraping:\n"
                                    "1. Install: pip install beautifulsoup4\n"
                                    "2. Add substack_utils.py to project folder\n"
                                    "3. Restart DocAnalyser")
        
        # 2.4 CHECK FOR VIDEO PLATFORMS (Vimeo, Rumble, etc.)
        from video_platform_utils import is_video_platform_url
        if is_video_platform_url(input_value):
            print(f"🎬 Detected: Video Platform URL")
            self.fetch_video_platform(input_value)
            return
        
        # 2.5 CHECK FOR FACEBOOK VIDEO/REEL
        if FACEBOOK_SUPPORT and is_facebook_video_url(input_value):
            print("📘 Detected: Facebook Video/Reel")
            self.fetch_facebook(input_value)
            return
        
        # 2.6 CHECK FOR TWITTER/X POST
        if TWITTER_SUPPORT and is_twitter_url(input_value):
            print("🐦 Detected: Twitter/X Post")
            self.fetch_twitter(input_value)
            return
        
        # 2.7 CHECK FOR GOOGLE DRIVE FILE
        # 2.7a CHECK FOR GOOGLE DRIVE FOLDER (can't process directly)
        if self._is_google_drive_folder_url(input_value):
            print("📁 Detected: Google Drive FOLDER URL (not a file)")
            messagebox.showinfo(
                "Google Drive Folder",
                "This is a Google Drive folder link, not a file link.\n\n"
                "To load a specific file from this folder:\n\n"
                "Option 1: Right-click the file in Google Drive, then\n"
                "select Share > Copy link, and paste that link here.\n\n"
                "Option 2: Download the file to your computer,\n"
                "then drag it into DocAnalyser or use Browse."
            )
            self.set_status("Google Drive folder detected - need a direct file link")
            return
        
        if self._is_google_drive_file_url(input_value):
            print("📁 Detected: Google Drive file URL")
            self._fetch_google_drive_file(input_value)
            return
        
        # 3. CHECK FOR WEB URL
        if input_value.startswith('http://') or input_value.startswith('https://'):
            print("🌐 Detected: Web URL")
            self.web_url_var.set(input_value)
            self.fetch_web()
            return
        
        # 4. CHECK FOR LOCAL FILE
        # Try os.path.exists first, then fallback with normpath for Unicode edge cases
        resolved_path = input_value
        if not os.path.exists(resolved_path):
            # Try normalising the path (fixes forward slashes and some Unicode issues)
            resolved_path = os.path.normpath(input_value)
        if not os.path.exists(resolved_path):
            # Last resort: if it looks like a file path, try pathlib (handles Unicode better on Windows)
            try:
                import pathlib
                p = pathlib.Path(input_value)
                if p.exists():
                    resolved_path = str(p)
            except Exception:
                pass
        if os.path.exists(resolved_path):
            print(f"📁 Detected: Local file ({os.path.splitext(resolved_path)[1]})")
            self.file_path_var.set(resolved_path)
            print(f"📁 DEBUG: Calling fetch_local_file() for: {resolved_path}")
            self.fetch_local_file()
            print("📁 DEBUG: fetch_local_file() returned")
            return
        
        # 5. CHECK IF IT'S A YOUTUBE ID (no URL, just ID)
        if self.could_be_youtube_id(input_value):
            print("🎬 Detected: Possible YouTube video ID")
            response = messagebox.askyesno(
                "YouTube Video ID?",
                f"'{input_value}' looks like it might be a YouTube video ID.\n\n"
                "Try loading it as a YouTube video?"
            )
            if response:
                self.yt_url_var.set(input_value)
                self.fetch_youtube()
                return
        
        # 6. COULDN'T DETECT - SHOW HELPFUL ERROR
        # Add diagnostic info for file path issues
        extra_info = ""
        if ':' in input_value or input_value.startswith('/'):
            # Looks like a file path that wasn't found
            extra_info = (
                f"\n\nos.path.exists returned False."
                f"\nPath length: {len(input_value)} chars"
                f"\nTip: If the filename has special characters "
                f"(like \u2022 or accented letters), try using the Browse "
                f"button instead of pasting the path."
            )
        messagebox.showerror(
            "Could Not Detect Input Type",
            f"Unable to process: {input_value}\n\n"
            "Please check that:\n"
            "• URLs start with http:// or https://\n"
            "• File paths are correct and the file exists\n"
            "• YouTube URLs are complete\n\n"
            "Use the Browse button to select local files."
            + extra_info
        )

    def process_url_or_id(self):  # or whatever the method is called
        input_value = self.universal_input_var.get().strip()
        print(f"\n{'=' * 60}")
        print(f"🔍 STARTING URL PROCESSING")
        print(f"Input value: {input_value}")
        print(f"SUBSTACK_AVAILABLE: {SUBSTACK_AVAILABLE}")
        print(f"{'=' * 60}\n")

    def _process_multiple_inputs(self, input_lines):
        """Process multiple files/URLs from multi-line input."""
        print(f"🔄 Processing {len(input_lines)} inputs...")
        
        # Check if items need OCR (images or scanned PDFs)
        ocr_files = []
        for f in input_lines:
            if os.path.exists(f):
                ext = os.path.splitext(f)[1].lower()
                if ext in ('.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp', '.gif', '.webp'):
                    ocr_files.append(f)
                elif ext == '.pdf':
                    try:
                        if get_ocr().is_pdf_scanned(f):
                            ocr_files.append(f)
                    except:
                        pass
        
        if len(ocr_files) == len(input_lines) and len(ocr_files) > 1:
            # All items need OCR - show special handling dialog
            print(f"📷 All {len(ocr_files)} items need OCR - showing dialog")
            action, use_vision, ordered_files = self._show_multi_ocr_dialog(ocr_files)
            
            if action is None:
                # Cancelled
                return
            
            # Process in background thread to avoid UI freeze
            def process_thread():
                try:
                    if action == 'combine':
                        # Combine into single document
                        if use_vision:
                            self._process_images_with_vision(ordered_files, combine=True)
                        else:
                            # Use standard OCR and combine
                            self._process_images_standard_ocr(ordered_files, combine=True)
                    else:
                        # Process separately
                        if use_vision:
                            self._process_images_with_vision(ordered_files, combine=False)
                        else:
                            self._process_images_standard_ocr(ordered_files, combine=False)
                except Exception as e:
                    import traceback
                    tb_str = traceback.format_exc()
                    print(f"❌ Multi-file processing error: {e}")
                    print(tb_str)
                    self.root.after(0, lambda: self.set_status(f"❌ Processing failed: {str(e)}"))
                    # Show traceback in error dialog so we can diagnose the issue
                    error_detail = f"Multi-file processing failed:\n{str(e)}\n\nTraceback:\n{tb_str[-500:]}"
                    self.root.after(0, lambda m=error_detail: messagebox.showerror("Processing Error", m))
                    self.processing = False
            
            import threading
            self.processing = True
            self.processing_thread = threading.Thread(target=process_thread)
            self.processing_thread.start()
            self.root.after(100, self.check_processing_thread)
            return
        
        # Show multi-document options dialog
        self._show_multi_document_dialog(input_lines)
    
    def _process_images_standard_ocr(self, ocr_files, combine=True):
        """Process images and PDFs with standard Tesseract OCR."""
        if not ocr_files:
            return
        
        entries = []
        all_source_files = []
        
        for i, file_path in enumerate(ocr_files):
            self.set_status(f"📄 OCR processing file {i+1}/{len(ocr_files)}...")
            
            try:
                if file_path.lower().endswith('.pdf'):
                    # Process PDF with local OCR
                    provider = self.provider_var.get()
                    model = self.model_var.get()
                    api_key = self.config.get("keys", {}).get(provider, "")
                    all_api_keys = self.config.get("keys", {})
                    
                    success, result, method = get_ocr().extract_text_from_pdf_smart(
                        filepath=file_path,
                        language=self.config.get("ocr_language", "eng"),
                        quality=self.config.get("ocr_quality", "balanced"),
                        provider=provider,
                        model=model,
                        api_key=api_key,
                        all_api_keys=all_api_keys,
                        progress_callback=self.set_status,
                        force_cloud=False
                    )
                    
                    if success and result:
                        for j, entry in enumerate(result):
                            entries.append({
                                'start': len(entries),
                                'text': entry.get('text', ''),
                                'location': f"{os.path.basename(file_path)} - {entry.get('location', f'Page {j+1}')}"
                            })
                        all_source_files.append(file_path)
                else:
                    # Process image
                    import pytesseract
                    from PIL import Image
                    
                    img = Image.open(file_path)
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    
                    language = self.config.get("ocr_language", "eng")
                    text = pytesseract.image_to_string(img, lang=language)
                    
                    if text.strip():
                        entries.append({
                            'start': len(entries),
                            'text': text.strip(),
                            'location': os.path.basename(file_path)
                        })
                        all_source_files.append(file_path)
            except Exception as e:
                print(f"⚠️ OCR failed for {file_path}: {e}")
        
        if combine:
            self._handle_multi_image_ocr_result(entries, all_source_files if all_source_files else ocr_files)
        else:
            # Save each separately
            for entry in entries:
                location = entry.get('location', '')
                for f in ocr_files:
                    if os.path.basename(f) in location:
                        self._save_single_ocr_result(f, entry['text'])
                        break
            self.set_status(f"✅ Processed {len(ocr_files)} files separately")
            self.root.after(0, self.refresh_library)
        
        # Reset processing flag
        self.processing = False
    
    def _show_multi_document_dialog(self, input_lines):
        """
        Show dialog for handling multiple documents.
        Radio buttons for Combine/Separate, with conditional name entry and reorder list.
        """
        # Create custom dialog
        dialog = tk.Toplevel(self.root)
        dialog.title("Multiple Documents")
        dialog.geometry("520x480")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Center the dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (260)
        y = (dialog.winfo_screenheight() // 2) - (240)
        dialog.geometry(f"+{x}+{y}")
        
        # Content header
        ttk.Label(dialog, text=f"You've selected {len(input_lines)} documents:", 
                  font=('Arial', 11, 'bold')).pack(pady=(15, 5))
        
        ttk.Label(dialog, text="How would you like to process them?",
                  font=('Arial', 10)).pack(pady=(5, 10))
        
        # Radio button variable
        choice_var = tk.StringVar(value="")
        
        # Frame for radio buttons and options
        options_frame = ttk.Frame(dialog)
        options_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)
        
        # Option 1: Combine for Analysis
        combine_frame = ttk.Frame(options_frame)
        combine_frame.pack(fill=tk.X, pady=5)
        
        combine_rb = ttk.Radiobutton(combine_frame, text="📚 Combine for Analysis", 
                                      variable=choice_var, value="combine")
        combine_rb.pack(anchor=tk.W)
        ttk.Label(combine_frame, text="      Load all as equal sources for group analysis",
                  font=('Arial', 8), foreground='gray').pack(anchor=tk.W)
        
        # Combine options frame (initially hidden) - contains name AND reorder list
        combine_options_frame = ttk.Frame(options_frame)
        # Don't pack yet - will be shown/hidden dynamically
        
        # Name entry row
        name_row = ttk.Frame(combine_options_frame)
        name_row.pack(fill=tk.X, pady=(5, 5))
        ttk.Label(name_row, text="Analysis name:", font=('Arial', 9)).pack(side=tk.LEFT)
        default_name = f"Multi-doc Analysis ({len(input_lines)} docs)"
        name_var = tk.StringVar(value=default_name)
        name_entry = ttk.Entry(name_row, textvariable=name_var, width=35, font=('Arial', 10))
        name_entry.pack(side=tk.LEFT, padx=(10, 0), fill=tk.X, expand=True)
        
        # Document order section
        ttk.Label(combine_options_frame, text="Document order (use buttons to reorder):", 
                  font=('Arial', 9)).pack(anchor=tk.W, pady=(10, 5))
        
        # Listbox and buttons row
        list_row = ttk.Frame(combine_options_frame)
        list_row.pack(fill=tk.BOTH, expand=True)
        
        # Listbox with scrollbar
        list_container = ttk.Frame(list_row)
        list_container.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(list_container)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        listbox = tk.Listbox(
            list_container,
            yscrollcommand=scrollbar.set,
            font=('Arial', 9),
            selectmode=tk.SINGLE,
            height=8
        )
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=listbox.yview)
        
        # Ordered file list (mutable copy)
        ordered_files = list(input_lines)
        
        def refresh_listbox():
            listbox.delete(0, tk.END)
            for i, f in enumerate(ordered_files):
                display_name = os.path.basename(f) if os.path.exists(f) else f[:40]
                listbox.insert(tk.END, f"{i+1}. {display_name}")
        
        refresh_listbox()
        
        # Move buttons
        btn_col = ttk.Frame(list_row)
        btn_col.pack(side=tk.LEFT, padx=(10, 0), fill=tk.Y)
        
        def move_up():
            sel = listbox.curselection()
            if sel and sel[0] > 0:
                idx = sel[0]
                ordered_files[idx], ordered_files[idx-1] = ordered_files[idx-1], ordered_files[idx]
                refresh_listbox()
                listbox.selection_set(idx-1)
                listbox.see(idx-1)
        
        def move_down():
            sel = listbox.curselection()
            if sel and sel[0] < len(ordered_files) - 1:
                idx = sel[0]
                ordered_files[idx], ordered_files[idx+1] = ordered_files[idx+1], ordered_files[idx]
                refresh_listbox()
                listbox.selection_set(idx+1)
                listbox.see(idx+1)
        
        ttk.Button(btn_col, text="↑ Up", command=move_up, width=8).pack(pady=2)
        ttk.Button(btn_col, text="↓ Down", command=move_down, width=8).pack(pady=2)
        
        # Option 2: Process Separately  
        separate_frame = ttk.Frame(options_frame)
        separate_frame.pack(fill=tk.X, pady=(15, 5))
        
        separate_rb = ttk.Radiobutton(separate_frame, text="📄 Process Separately", 
                                       variable=choice_var, value="separate")
        separate_rb.pack(anchor=tk.W)
        ttk.Label(separate_frame, text="      Each document becomes its own library entry",
                  font=('Arial', 8), foreground='gray').pack(anchor=tk.W)
        
        # Function to show/hide combine options based on selection
        def on_choice_change(*args):
            if choice_var.get() == "combine":
                combine_options_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 0), after=combine_frame)
                name_entry.focus_set()
                name_entry.select_range(0, tk.END)
                # Resize dialog to show list
                dialog.geometry("520x520")
            else:
                combine_options_frame.pack_forget()
                # Reset name to default when switching away
                name_var.set(default_name)
                # Reset order when switching away
                ordered_files.clear()
                ordered_files.extend(input_lines)
                refresh_listbox()
                # Shrink dialog
                dialog.geometry("520x280")
        
        choice_var.trace_add('write', on_choice_change)
        
        result = {'choice': None, 'name': None, 'ordered_files': None}
        
        def on_ok():
            if not choice_var.get():
                # No selection made
                return
            result['choice'] = choice_var.get()
            if choice_var.get() == "combine":
                result['name'] = name_var.get().strip() or default_name
                result['ordered_files'] = list(ordered_files)
            dialog.destroy()
        
        def on_cancel():
            result['choice'] = None
            dialog.destroy()
        
        # Buttons frame
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=15)
        
        ok_btn = ttk.Button(btn_frame, text="OK", command=on_ok, width=10)
        ok_btn.pack(side=tk.LEFT, padx=5)
        
        cancel_btn = ttk.Button(btn_frame, text="Cancel", command=on_cancel, width=10)
        cancel_btn.pack(side=tk.LEFT, padx=5)
        
        # Bind Enter and Escape
        dialog.bind('<Return>', lambda e: on_ok())
        dialog.bind('<Escape>', lambda e: on_cancel())
        
        # Wait for dialog
        self.root.wait_window(dialog)
        
        # Process result
        if result['choice'] == 'combine':
            self._combine_documents_for_analysis(result['ordered_files'], result['name'])
        elif result['choice'] == 'separate':
            self._batch_process_inputs(input_lines)
        # else: cancelled, do nothing
    
    def _combine_documents_for_analysis(self, input_lines, analysis_name):
        """
        Combine multiple documents as equal sources for group analysis.
        """
        self.set_status(f"📚 Loading {len(input_lines)} documents...")
        
        # Process in background thread
        def load_thread():
            self._load_combined_documents(input_lines, analysis_name)
        
        self.processing = True
        self.process_btn.config(state=tk.DISABLED)
        self.processing_thread = threading.Thread(target=load_thread)
        self.processing_thread.start()
        self.root.after(100, self.check_processing_thread)
    
    def _load_combined_documents(self, input_lines, analysis_name):
        """
        Load all documents as equal sources and create a multi-doc analysis entry.
        Runs in background thread.
        """
        import time
        
        loaded_documents = []
        total = len(input_lines)
        print(f"📚 Starting to load {total} documents...")
        
        for i, item in enumerate(input_lines):
            # Thread-safe status update - show filename
            display_name = os.path.basename(item) if os.path.exists(item) else item[:30]
            self.root.after(0, lambda idx=i, name=display_name: self.set_status(f"📚 Loading {idx+1}/{total}: {name}"))
            print(f"📚 Loading {i+1}/{total}: {display_name}")
            
            # Small delay to allow status to update in UI
            time.sleep(0.05)
            
            try:
                if os.path.exists(item):
                    ext = os.path.splitext(item)[1].lower()
                    file_name = os.path.basename(item)
                    
                    # Skip audio/video files - they need transcription
                    if ext in ('.mp3', '.wav', '.m4a', '.ogg', '.flac', '.aac', '.wma', '.opus', '.mp4', '.avi', '.mov'):
                        print(f"⚠️ Audio/video files not supported in combine mode: {item}")
                        loaded_documents.append({
                            'path': item,
                            'title': file_name,
                            'text': f"[Audio/video file - requires transcription: {file_name}]",
                            'char_count': 0,
                            'skipped': True,
                            'reason': 'audio_video'
                        })
                        continue
                    
                    # Skip image files - they need OCR
                    if ext in ('.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp', '.gif', '.webp'):
                        print(f"⚠️ Image files not supported in combine mode: {item}")
                        loaded_documents.append({
                            'path': item,
                            'title': file_name,
                            'text': f"[Image file - requires OCR: {file_name}]",
                            'char_count': 0,
                            'skipped': True,
                            'reason': 'image'
                        })
                        continue
                    
                    # Handle spreadsheets
                    if ext in ('.xlsx', '.xls', '.csv'):
                        success, text_content, title, error_msg = self.convert_spreadsheet_to_text(item)
                        if success:
                            loaded_documents.append({
                                'path': item,
                                'title': file_name,
                                'text': text_content,
                                'char_count': len(text_content),
                                'doc_type': 'spreadsheet'
                            })
                        else:
                            loaded_documents.append({
                                'path': item,
                                'title': file_name,
                                'text': f"[Failed to load spreadsheet: {error_msg}]",
                                'char_count': 0,
                                'error': error_msg
                            })
                        continue
                    
                    # Handle scanned PDFs
                    if ext == '.pdf':
                        is_scanned = get_ocr().is_pdf_scanned(item)
                        if is_scanned:
                            # Check for cached OCR
                            cached = get_ocr().load_cached_ocr(
                                item,
                                self.config.get("ocr_quality", "balanced"),
                                self.config.get("ocr_language", "eng")
                            )
                            if cached:
                                text = "\n".join(entry.get('text', '') for entry in cached.get('entries', []))
                                loaded_documents.append({
                                    'path': item,
                                    'title': file_name,
                                    'text': text,
                                    'char_count': len(text),
                                    'doc_type': 'pdf_ocr_cached'
                                })
                                continue
                            else:
                                loaded_documents.append({
                                    'path': item,
                                    'title': file_name,
                                    'text': f"[Scanned PDF - requires OCR: {file_name}]",
                                    'char_count': 0,
                                    'skipped': True,
                                    'reason': 'scanned_pdf'
                                })
                                continue
                    
                    # Use document fetcher for regular files (txt, docx, pdf, rtf, html)
                    success, result, title, doc_type = get_doc_fetcher().fetch_local_file(item)
                    
                    if success:
                        # Extract text from result
                        if isinstance(result, list):
                            text = "\n".join(entry.get('text', '') for entry in result)
                        else:
                            text = str(result)
                        
                        loaded_documents.append({
                            'path': item,
                            'title': file_name,
                            'text': text,
                            'char_count': len(text),
                            'doc_type': doc_type
                        })
                    else:
                        print(f"⚠️ Failed to load {item}: {result}")
                        loaded_documents.append({
                            'path': item,
                            'title': file_name,
                            'text': f"[Failed to load: {result}]",
                            'char_count': 0,
                            'error': str(result)
                        })
                        
                elif item.startswith('http'):
                    # URL - note limitation
                    print(f"⚠️ URL loading not yet supported in combine mode: {item}")
                    loaded_documents.append({
                        'path': item,
                        'title': item[:50],
                        'text': "[URL loading not yet supported in combine mode]",
                        'char_count': 0,
                        'is_url': True
                    })
                    
            except Exception as e:
                import traceback
                print(f"❌ Error loading {item}: {e}")
                traceback.print_exc()
                loaded_documents.append({
                    'path': item,
                    'title': os.path.basename(item) if os.path.exists(item) else item[:50],
                    'text': f"[Error: {str(e)}]",
                    'char_count': 0,
                    'error': str(e)
                })
        
        # Finalize on main thread
        print(f"📚 Finished loading loop. {len(loaded_documents)} documents. Calling finalize...")
        self.root.after(0, self._finalize_combined_documents, loaded_documents, analysis_name)
    
    def _finalize_combined_documents(self, loaded_documents, analysis_name):
        """
        Finalize the combined documents - create library entry and set up UI.
        Runs on main thread.
        """
        print(f"📚 _finalize_combined_documents ENTERED with {len(loaded_documents)} documents")
        
        from document_library import add_document_to_library
        import datetime
        
        self.processing = False
        self.process_btn.config(state=tk.NORMAL)
        
        # Count successfully loaded documents
        success_count = len([d for d in loaded_documents if d.get('char_count', 0) > 0])
        print(f"📚 Successfully loaded: {success_count}/{len(loaded_documents)}")
        
        if success_count == 0:
            messagebox.showerror("Error", "Failed to load any documents.")
            self.set_status("❌ Failed to load documents")
            return
        
        # Build combined text for the analysis
        combined_parts = []
        total_chars = 0
        
        for doc in loaded_documents:
            title = doc.get('title', 'Unknown')
            text = doc.get('text', '')
            combined_parts.append(f"\n\n{'='*60}\n=== {title} ===\n{'='*60}\n{text}")
            total_chars += len(text)
        
        combined_text = "\n".join(combined_parts).strip()
        
        # Build metadata
        metadata = {
            "type": "multi_doc_analysis",
            "analysis_name": analysis_name,
            "source_documents": [
                {
                    'path': d.get('path', ''),
                    'title': d.get('title', ''),
                    'char_count': d.get('char_count', 0),
                    'doc_type': d.get('doc_type', 'unknown'),
                    'error': d.get('error')
                }
                for d in loaded_documents
            ],
            "document_count": len(loaded_documents),
            "successful_count": success_count,
            "total_chars": total_chars,
            "created": datetime.datetime.now().isoformat()
        }
        
        # Create entries structure - one entry per document for cleaner viewing
        entries = []
        current_start = 0
        for doc in loaded_documents:
            if doc.get('char_count', 0) > 0:
                entries.append({
                    'text': doc.get('text', ''),
                    'start': current_start,
                    'location': doc.get('title', 'Unknown Document')
                })
                current_start += doc.get('char_count', 0)
        
        # Create library title with icon
        library_title = f"📚 {analysis_name}"
        
        # Add to library
        total_chars = sum(len(e.get('text', '')) for e in entries)
        print(f"📚 Adding to library: '{title}' ({total_chars:,} chars)")
        print(f"📚 DEBUG: entries length = {len(entries)}")
        print(f"📚 DEBUG: metadata keys = {list(metadata.keys())}")
        print(f"📚 DEBUG: About to call add_document_to_library...")
        import sys
        sys.stdout.flush()  # Force output
        
        try:
            doc_id = add_document_to_library(
                doc_type="multi_doc_analysis",
                source=f"multi_doc_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}",
                title=library_title,
                entries=entries,
                document_class="source",
                metadata=metadata
            )
            print(f"📚 DEBUG: add_document_to_library returned: {doc_id}")
            sys.stdout.flush()
        except Exception as e:
            import traceback
            print(f"❌ EXCEPTION in add_document_to_library: {e}")
            traceback.print_exc()
            sys.stdout.flush()
            doc_id = None
        
        print(f"📚 DEBUG: doc_id is now: {doc_id}")
        sys.stdout.flush()
        
        if doc_id:
            try:
                print(f"📚 Library entry created: {doc_id}")
                sys.stdout.flush()
                # Set as current document
                print(f"📚 DEBUG: Setting current_document_id...")
                sys.stdout.flush()
                self.current_document_id = doc_id
                self.current_document_source = library_title
                self.current_document_type = "multi_doc_analysis"
                self.current_document_class = "source"
                self.current_document_text = combined_text
                self.current_document_metadata = metadata
                self.current_entries = entries
                print(f"📚 DEBUG: Current document set")
                sys.stdout.flush()
                
                # Clear any existing attachments - the combined text already has all content
                print(f"📚 DEBUG: Clearing attachments (combined_text has all content)...")
                sys.stdout.flush()
                self.attachment_manager.attachments.clear()
                print(f"📚 DEBUG: Attachments cleared")
                sys.stdout.flush()
                
                # Update UI
                print(f"📚 DEBUG: Calling update_context_buttons...")
                sys.stdout.flush()
                self.update_context_buttons('document')
                print(f"📚 DEBUG: Calling update_button_states...")
                sys.stdout.flush()
                # Enable Run button highlight for newly loaded document
                self._run_highlight_enabled = True
                self.update_button_states()
                print(f"📚 DEBUG: Calling refresh_library...")
                sys.stdout.flush()
                self.refresh_library()
                print(f"📚 DEBUG: UI updated")
                sys.stdout.flush()
                
                # Show success
                print(f"📚 DEBUG: About to set success status...")
                sys.stdout.flush()
                self.set_status(f"✅ Loaded {success_count} documents as '{analysis_name}' - Select prompt and click Run")
                print(f"📚 Created Multi-doc Analysis: {doc_id} ({success_count} documents, {total_chars:,} chars)")
                sys.stdout.flush()
                print(f"📚 DEBUG: _finalize_combined_documents COMPLETE")
                sys.stdout.flush()
            except Exception as e:
                import traceback
                print(f"❌ EXCEPTION in post-save processing: {e}")
                traceback.print_exc()
                sys.stdout.flush()
            
            # Show brief confirmation
            if success_count < len(loaded_documents):
                failed = len(loaded_documents) - success_count
                messagebox.showinfo(
                    "Documents Loaded",
                    f"✅ Loaded {success_count} of {len(loaded_documents)} documents.\n\n"
                    f"⚠️ {failed} document(s) failed to load.\n\n"
                    f"Ready for analysis. Select a prompt and click Run."
                )
        else:
            messagebox.showerror("Error", "Failed to create library entry.")
            self.set_status("❌ Failed to save to library")
    
    def _batch_process_inputs(self, input_lines):
        """Process multiple inputs sequentially."""
        messagebox.showinfo(
            "Batch Processing",
            f"Batch processing {len(input_lines)} items sequentially.\n\n"
            "Each item will be loaded and can be processed with your selected prompt.\n"
            "Use 'Documents Library' to review results."
        )
        
        # Process first item
        self.universal_input_entry.delete('1.0', 'end')
        self.universal_input_entry.insert('1.0', input_lines[0])
        self.placeholder_active = False
        self.smart_load()
        
        # Store remaining for sequential processing
        self._batch_queue = input_lines[1:]
        if self._batch_queue:
            self.set_status(f"📋 {len(self._batch_queue)} more items in queue - click 'Run' to process, then load next")

    def is_youtube_url(self, url):
        """Check if URL is a YouTube video"""
        youtube_patterns = [
            'youtube.com/watch',
            'youtu.be/',
            'youtube.com/embed/',
            'youtube.com/v/',
            'youtube.com/live/',
            'youtube.com/shorts/',
            'm.youtube.com'
        ]
        url_lower = url.lower()
        return any(pattern in url_lower for pattern in youtube_patterns)

    def is_substack_url(self, url):
     """Check if URL is a Substack post"""
     if not SUBSTACK_AVAILABLE:
            return False
     from substack_utils import is_substack_url
     return is_substack_url(url)

    def _is_google_drive_file_url(self, url):
        """Check if URL is a Google Drive file link (PDF, doc, etc.)"""
        url_lower = url.lower()
        patterns = [
            'drive.google.com/file/d/',
            'drive.google.com/u/',  # Multi-account paths like /u/0/file/d/
            'drive.google.com/open?id=',
            'docs.google.com/document/d/',
            'docs.google.com/spreadsheets/d/',
            'docs.google.com/presentation/d/',
        ]
        return any(pattern in url_lower for pattern in patterns)

    def _is_google_drive_folder_url(self, url):
        """Check if URL is a Google Drive folder link (not a downloadable file)"""
        url_lower = url.lower()
        folder_patterns = [
            'drive.google.com/drive/folders/',
            'drive.google.com/drive/u/',  # Multi-account folder paths
        ]
        # It's a folder if it matches folder patterns AND is NOT a file URL
        is_folder = any(pattern in url_lower for pattern in folder_patterns)
        is_file = self._is_google_drive_file_url(url)
        return is_folder and not is_file

    def _extract_google_drive_file_id(self, url):
        """Extract file ID from various Google Drive URL formats."""
        import re
        # drive.google.com/file/d/FILE_ID/view
        match = re.search(r'drive\.google\.com/(?:u/\d+/)?file/d/([a-zA-Z0-9_-]+)', url)
        if match:
            return match.group(1)
        # drive.google.com/open?id=FILE_ID
        match = re.search(r'drive\.google\.com/open\?id=([a-zA-Z0-9_-]+)', url)
        if match:
            return match.group(1)
        # docs.google.com/document/d/FILE_ID
        match = re.search(r'docs\.google\.com/(?:document|spreadsheets|presentation)/d/([a-zA-Z0-9_-]+)', url)
        if match:
            return match.group(1)
        return None

    def _fetch_google_drive_file(self, url):
        """
        Download a file from Google Drive and process it locally.
        Works with publicly shared files. For private files, instructs user to download manually.
        """
        file_id = self._extract_google_drive_file_id(url)
        if not file_id:
            messagebox.showerror("Google Drive Error",
                                "Could not extract file ID from this Google Drive URL.\n\n"
                                "Please download the file manually and load it from your computer.")
            return

        # Check if it's a Google Docs/Sheets/Slides native document (not a file)
        url_lower = url.lower()
        if 'docs.google.com/document/' in url_lower:
            # Google Doc - export as docx
            export_url = f"https://docs.google.com/document/d/{file_id}/export?format=docx"
            ext = '.docx'
            file_type_name = "Google Doc"
        elif 'docs.google.com/spreadsheets/' in url_lower:
            export_url = f"https://docs.google.com/spreadsheets/d/{file_id}/export?format=xlsx"
            ext = '.xlsx'
            file_type_name = "Google Sheet"
        elif 'docs.google.com/presentation/' in url_lower:
            export_url = f"https://docs.google.com/presentation/d/{file_id}/export?format=pptx"
            ext = '.pptx'
            file_type_name = "Google Slides"
        else:
            # Regular Drive file (PDF, etc.) - use direct download
            export_url = f"https://drive.google.com/uc?export=download&id={file_id}"
            ext = '.pdf'  # Default; actual extension determined from response headers
            file_type_name = "Google Drive file"

        self.processing = True
        self.set_status(f"Downloading {file_type_name} from Google Drive...")

        def download_thread():
            import re  # Must be at top of nested function to avoid UnboundLocalError
            temp_path = None
            try:
                import urllib.request
                import urllib.error

                # Build request with browser-like headers
                req = urllib.request.Request(export_url, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                })

                response = urllib.request.urlopen(req, timeout=60)

                # Try to get filename from Content-Disposition header
                content_disp = response.headers.get('Content-Disposition', '')
                if 'filename=' in content_disp:
                    fname_match = re.search(r'filename\*?=(?:UTF-8\'\')?("?)(.+?)\1(?:;|$)', content_disp)
                    if fname_match:
                        filename = fname_match.group(2).strip('"')
                        # URL-decode the filename
                        from urllib.parse import unquote
                        filename = unquote(filename)
                        _, file_ext = os.path.splitext(filename)
                        if file_ext:
                            ext_actual = file_ext
                        else:
                            ext_actual = ext
                    else:
                        filename = f"gdrive_{file_id}{ext}"
                        ext_actual = ext
                else:
                    filename = f"gdrive_{file_id}{ext}"
                    ext_actual = ext

                # Check for Google's virus scan warning page (large files)
                content_type = response.headers.get('Content-Type', '')
                if 'text/html' in content_type and ext_actual == '.pdf':
                    # Likely a "virus scan" interstitial or access denied page
                    html_content = response.read().decode('utf-8', errors='ignore')
                    if 'confirm=' in html_content or 'download_warning' in html_content:
                        # Try to extract confirm token for large files
                        confirm_match = re.search(r'confirm=([0-9A-Za-z_-]+)', html_content)
                        if confirm_match:
                            confirm_url = f"https://drive.google.com/uc?export=download&confirm={confirm_match.group(1)}&id={file_id}"
                            req2 = urllib.request.Request(confirm_url, headers={
                                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                            })
                            response = urllib.request.urlopen(req2, timeout=60)
                        else:
                            # Access denied or not a downloadable file
                            self.root.after(0, lambda: messagebox.showwarning(
                                "Google Drive Access",
                                "This file cannot be downloaded directly.\n\n"
                                "Possible reasons:\n"
                                "  • The file is not publicly shared\n"
                                "  • The file requires sign-in to access\n"
                                "  • The file is too large for direct download\n\n"
                                "Please download the file manually from Google Drive\n"
                                "and then load it from your computer."
                            ))
                            self.root.after(0, lambda: self.set_status(""))
                            self.processing = False
                            return

                # Save to temp file with progress indication
                temp_dir = tempfile.mkdtemp()
                # Sanitise filename for filesystem
                safe_filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
                temp_path = os.path.join(temp_dir, safe_filename)

                # Get total size if available (for percentage display)
                total_size = response.headers.get('Content-Length')
                total_size = int(total_size) if total_size else None
                downloaded = 0
                last_update_time = 0

                with open(temp_path, 'wb') as f:
                    while True:
                        chunk = response.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)

                        # Update status bar every ~100KB to avoid flooding the UI
                        import time
                        now = time.time()
                        if now - last_update_time >= 0.3:  # Max ~3 updates per second
                            last_update_time = now
                            dl_mb = downloaded / (1024 * 1024)
                            if total_size:
                                total_mb = total_size / (1024 * 1024)
                                pct = (downloaded / total_size) * 100
                                status_msg = f"Downloading from Google Drive: {dl_mb:.1f} / {total_mb:.1f} MB ({pct:.0f}%)"
                            else:
                                status_msg = f"Downloading from Google Drive: {dl_mb:.1f} MB downloaded..."
                            self.root.after(0, lambda m=status_msg: self.set_status(m))

                file_size = os.path.getsize(temp_path)
                dl_mb_final = file_size / (1024 * 1024)
                self.root.after(0, lambda: self.set_status(f"Download complete ({dl_mb_final:.1f} MB). Processing..."))
                print(f"✅ Downloaded Google Drive file: {safe_filename} ({file_size:,} bytes)")

                if file_size < 1000:
                    # Probably an error page, not the actual file
                    with open(temp_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content_preview = f.read(500)
                    if '<html' in content_preview.lower():
                        self.root.after(0, lambda: messagebox.showwarning(
                            "Google Drive Access",
                            "Could not download the file. It may not be publicly shared.\n\n"
                            "Please download the file manually from Google Drive\n"
                            "and then load it from your computer."
                        ))
                        self.root.after(0, lambda: self.set_status(""))
                        self.processing = False
                        return

                # Process as local file
                self.root.after(0, lambda p=temp_path: self._load_downloaded_gdrive_file(p))

            except urllib.error.HTTPError as e:
                error_msg = f"HTTP {e.code}"
                if e.code == 403:
                    error_msg = "Access denied. The file is not publicly shared."
                elif e.code == 404:
                    error_msg = "File not found. The link may be invalid or expired."
                print(f"❌ Google Drive download failed: {error_msg}")
                self.root.after(0, lambda m=error_msg: messagebox.showerror(
                    "Google Drive Error",
                    f"Could not download file: {m}\n\n"
                    f"Please download the file manually from Google Drive\n"
                    f"and then load it from your computer."
                ))
                self.root.after(0, lambda: self.set_status(""))
                self.processing = False
            except Exception as e:
                print(f"❌ Google Drive download error: {e}")
                self.root.after(0, lambda m=str(e): messagebox.showerror(
                    "Google Drive Error",
                    f"Download failed: {m}\n\n"
                    f"Please download the file manually and load it from your computer."
                ))
                self.root.after(0, lambda: self.set_status(""))
                self.processing = False

        thread = threading.Thread(target=download_thread, daemon=True)
        thread.start()

    def _load_downloaded_gdrive_file(self, file_path):
        """Load a file downloaded from Google Drive through the normal local file pipeline."""
        self.processing = False
        self.file_path_var.set(file_path)
        self.set_status(f"Processing downloaded file: {os.path.basename(file_path)}")
        self.fetch_local_file()

    def could_be_youtube_id(self, text):
        """Check if text could be a YouTube video ID (11 characters, alphanumeric + - and _)"""
        if len(text) == 11:
            return bool(re.match(r'^[A-Za-z0-9_-]{11}$', text))
        return False

    def _is_image_file(self, filepath):
        """Check if a file is an image that needs OCR."""
        if not os.path.exists(filepath):
            return False
        ext = os.path.splitext(filepath)[1].lower()
        return ext in ('.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp', '.gif', '.webp')
    
    def _needs_ocr(self, filepath):
        """Check if a file needs OCR processing (image or scanned PDF)."""
        if not os.path.exists(filepath):
            return False
        ext = os.path.splitext(filepath)[1].lower()
        
        # Images always need OCR
        if ext in ('.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp', '.gif', '.webp'):
            return True
        
        # PDFs might need OCR if scanned
        if ext == '.pdf':
            try:
                return get_ocr().is_pdf_scanned(filepath)
            except:
                return False
        
        return False
    
    def _check_ocr_confidence(self, image_path):
        """
        Quick OCR confidence check on an image.
        Returns (confidence_score, likely_handwriting).
        """
        try:
            import pytesseract
            from PIL import Image
            
            # Open and optionally resize for speed
            img = Image.open(image_path)
            
            # Resize if too large (for speed)
            max_size = 1000
            if max(img.size) > max_size:
                ratio = max_size / max(img.size)
                new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
            
            # Convert to RGB if necessary
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Get OCR data with confidence scores
            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
            
            # Calculate average confidence (excluding -1 which means no text detected)
            confidences = [int(c) for c in data['conf'] if int(c) > 0]
            
            if not confidences:
                # No text detected - likely handwriting or very poor quality
                return 0, True
            
            avg_confidence = sum(confidences) / len(confidences)
            threshold = self.config.get("ocr_confidence_threshold", 70)
            likely_handwriting = avg_confidence < threshold
            
            return avg_confidence, likely_handwriting
            
        except Exception as e:
            print(f"⚠️ OCR confidence check failed: {e}")
            # On error, default to suggesting vision model
            return 0, True
    
    def _show_multi_image_dialog(self, ocr_files):
        """Wrapper for backwards compatibility."""
        return self._show_multi_ocr_dialog(ocr_files)
    
    def _show_multi_ocr_dialog(self, ocr_files):
        """
        Show dialog for handling multiple files that need OCR (images or scanned PDFs).
        Returns: (action, use_vision, ordered_files) or (None, None, None) if cancelled.
        action: 'separate' or 'combine'
        use_vision: True to use AI vision model, False for standard OCR
        ordered_files: List of files in user-specified order (for combine)
        """
        import tkinter as tk
        from tkinter import ttk
        
        result = {'action': None, 'use_vision': False, 'files': ocr_files.copy()}
        
        dialog = tk.Toplevel(self.root)
        dialog.title("Multiple Files for OCR")
        # Will adjust height later if warning needed
        dialog.geometry("520x400")
        dialog.transient(self.root)
        dialog.grab_set()
        self.style_dialog(dialog)
        
        # Center the dialog
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - dialog.winfo_width()) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")
        
        # Count file types
        pdf_count = sum(1 for f in ocr_files if f.lower().endswith('.pdf'))
        img_count = len(ocr_files) - pdf_count
        
        if pdf_count > 0 and img_count > 0:
            header_text = f"{len(ocr_files)} files detected ({img_count} images, {pdf_count} PDFs)"
        elif pdf_count > 0:
            header_text = f"{pdf_count} scanned PDF{'s' if pdf_count > 1 else ''} detected"
        else:
            header_text = f"{img_count} image file{'s' if img_count > 1 else ''} detected"
        
        # Header
        ttk.Label(
            dialog, 
            text=header_text,
            font=('Arial', 11, 'bold')
        ).pack(pady=(15, 10))
        
        # Check confidence on first file (for auto-detection)
        self.set_status("🔍 Analyzing files...")
        dialog.update()
        first_file = ocr_files[0]
        
        # If PDF, extract first page as image for confidence check
        if first_file.lower().endswith('.pdf'):
            try:
                import tempfile
                from pdf2image import convert_from_path
                images = convert_from_path(first_file, first_page=1, last_page=1, dpi=150)
                if images:
                    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                        images[0].save(tmp.name, 'PNG')
                        confidence, likely_handwriting = self._check_ocr_confidence(tmp.name)
                        os.unlink(tmp.name)
                else:
                    confidence, likely_handwriting = 50, True
            except Exception as e:
                print(f"⚠️ PDF confidence check failed: {e}")
                confidence, likely_handwriting = 50, True
        else:
            confidence, likely_handwriting = self._check_ocr_confidence(first_file)
        
        self.set_status("Ready")
        
        # Action buttons frame
        action_frame = ttk.Frame(dialog)
        action_frame.pack(pady=10, padx=20, fill=tk.X)
        
        def check_vision_before_proceed():
            """Check if vision is selected but provider doesn't support it. Returns True if OK to proceed."""
            if vision_var.get():
                supported, provider = self._provider_supports_vision()
                if not supported:
                    messagebox.showwarning(
                        "⚠️ Vision AI Not Available",
                        f"Your current AI provider ({provider}) does not support "
                        f"vision/image processing needed for handwriting recognition.\n\n"
                        f"To proceed, please:\n\n"
                        f"  • Change 'AI Provider' in the main window to:\n"
                        f"      → OpenAI (uses GPT-4o) - Best for handwriting\n"
                        f"      → Anthropic (uses Claude)\n"
                        f"      → Google (uses Gemini)\n"
                        f"  • Make sure you have an API key entered\n"
                        f"  • Try loading the files again\n\n"
                        f"Or uncheck 'Contains handwriting' to use free local OCR\n"
                        f"(works for printed text only)."
                    )
                    return False  # Cannot proceed without vision support
            return True  # OK to proceed
        
        def on_separate():
            if not check_vision_before_proceed():
                return  # User cancelled
            result['action'] = 'separate'
            dialog.destroy()
        
        def on_combine():
            if not check_vision_before_proceed():
                return  # User cancelled
            result['action'] = 'combine'
            # Show reorder dialog
            ordered = self._show_reorder_dialog(dialog, ocr_files)
            if ordered:
                result['files'] = ordered
                dialog.destroy()
            # If cancelled, stay on this dialog
        
        sep_btn = ttk.Button(
            action_frame, 
            text="📄 Process as Separate Documents",
            command=on_separate,
            width=35
        )
        sep_btn.pack(pady=5)
        
        combine_btn = ttk.Button(
            action_frame,
            text="📑 Combine as Single Document",
            command=on_combine,
            width=35
        )
        combine_btn.pack(pady=5)
        
        # Check if current provider supports vision
        vision_supported, current_provider = self._provider_supports_vision()
        
        # If handwriting detected but vision not supported, show prominent warning
        if likely_handwriting and not vision_supported:
            # Make dialog taller to fit warning
            dialog.geometry("520x580")
            
            # Create a prominent warning frame
            warning_frame = ttk.LabelFrame(dialog, text="⚠️ Vision AI Required for Handwriting", padding=10)
            warning_frame.pack(pady=(10, 5), padx=20, fill=tk.X)
            
            # Warning icon and message
            warning_msg = tk.Text(warning_frame, wrap=tk.WORD, height=9, width=50, 
                                 font=('Arial', 9), bg='#FFF3CD', relief=tk.FLAT)
            warning_msg.pack(fill=tk.X)
            warning_msg.insert('1.0', 
                f"These files appear to contain handwriting.\n\n"
                f"Your current AI provider ({current_provider}) does not support vision/image processing.\n\n"
                f"To transcribe handwriting, please:\n"
                f"1. Close this dialog\n"
                f"2. Change AI Provider (dropdown in main window) to:\n"
                f"   • OpenAI (uses GPT-4o) ← Recommended\n"
                f"   • Anthropic (uses Claude)\n"
                f"   • Google (uses Gemini)\n"
                f"3. Ensure you have an API key for that provider\n"
                f"4. Try loading the files again\n\n"
                f"Or uncheck 'Contains handwriting' below to use local OCR\n"
                f"(works for printed text only, not handwriting)."
            )
            warning_msg.config(state=tk.DISABLED)
            
            # Re-center dialog after resize
            dialog.update_idletasks()
            x = self.root.winfo_x() + (self.root.winfo_width() - 520) // 2
            y = self.root.winfo_y() + (self.root.winfo_height() - 580) // 2
            dialog.geometry(f"520x580+{x}+{y}")
        
        # Handwriting checkbox
        # If vision not supported, don't auto-check handwriting
        initial_vision = likely_handwriting if vision_supported else False
        vision_var = tk.BooleanVar(value=initial_vision)
        
        checkbox_frame = ttk.Frame(dialog)
        checkbox_frame.pack(pady=(15, 5), padx=20, fill=tk.X)
        
        vision_cb = ttk.Checkbutton(
            checkbox_frame,
            text="Contains handwriting (use AI vision)",
            variable=vision_var
        )
        vision_cb.pack(anchor=tk.W)
        
        # Function to check vision support when checkbox is toggled
        def on_vision_checkbox_change(*args):
            if vision_var.get() and not vision_supported:
                # User tried to check the box but vision not supported
                vision_var.set(False)  # Uncheck it
                messagebox.showwarning(
                    "Vision AI Required",
                    f"Your current AI provider ({current_provider}) does not support vision.\n\n"
                    f"To use handwriting recognition:\n\n"
                    f"1. Change AI Provider to:\n"
                    f"   • OpenAI (recommended)\n"
                    f"   • Anthropic\n"
                    f"   • Google\n\n"
                    f"2. Make sure you have an API key for that provider.\n\n"
                    f"3. Try again."
                )
        
        vision_var.trace_add('write', on_vision_checkbox_change)
        
        # Auto-detection hint or vision warning
        if not vision_supported:
            # Show warning that current provider doesn't support vision
            hint_text = f"⚠️ {current_provider} doesn't support vision - switch provider for handwriting"
            hint_color = '#CC0000'  # Red warning color
        elif likely_handwriting:
            hint_text = "✅ Vision AI available - uncheck if printed text only"
            hint_color = '#006600'  # Green
        else:
            hint_text = "ℹ️ Check this box if images contain handwriting"
            hint_color = '#666666'
        
        hint_label = ttk.Label(
            checkbox_frame,
            text=hint_text,
            font=('Arial', 9, 'bold' if not vision_supported else 'normal'),
            foreground=hint_color,
            wraplength=400
        )
        hint_label.pack(anchor=tk.W, padx=(20, 0))
        
        # Show current provider info
        provider_info = ttk.Label(
            checkbox_frame,
            text=f"Current provider: {current_provider}",
            font=('Arial', 8),
            foreground='#888888'
        )
        provider_info.pack(anchor=tk.W, padx=(20, 0), pady=(5, 0))
        
        # Settings hint (italic, gray)
        threshold = self.config.get("ocr_confidence_threshold", 70)
        hint_line1 = f"AI vision used if OCR accuracy falls below {threshold}%."
        hint_line2 = "To adjust threshold, go to Settings → OCR Settings."
        settings_hint = ttk.Label(
            dialog,
            text=hint_line1 + "\n" + hint_line2,
            font=('Arial', 8, 'italic'),
            foreground='#888888',
            justify=tk.LEFT
        )
        settings_hint.pack(pady=(10, 5), padx=20, anchor=tk.W)
        
        # Cancel button
        ttk.Button(
            dialog,
            text="Cancel",
            command=dialog.destroy,
            width=15
        ).pack(pady=15)
        
        # Wait for dialog
        dialog.wait_window()
        
        result['use_vision'] = vision_var.get()
        
        if result['action']:
            return result['action'], result['use_vision'], result['files']
        return None, None, None
    
    def _show_reorder_dialog(self, parent, files):
        """
        Show dialog to reorder files before combining.
        Returns ordered list or None if cancelled.
        """
        import tkinter as tk
        from tkinter import ttk
        
        result = {'files': None}
        
        dialog = tk.Toplevel(parent)
        dialog.title("Arrange Pages")
        dialog.geometry("450x400")
        dialog.transient(parent)
        dialog.grab_set()
        self.style_dialog(dialog)
        
        # Center
        dialog.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - dialog.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")
        
        ttk.Label(
            dialog,
            text="Arrange pages in order:",
            font=('Arial', 10, 'bold')
        ).pack(pady=(15, 10))
        
        # Listbox with scrollbar
        list_frame = ttk.Frame(dialog)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)
        
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        listbox = tk.Listbox(
            list_frame,
            yscrollcommand=scrollbar.set,
            font=('Arial', 10),
            selectmode=tk.SINGLE,
            height=10
        )
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=listbox.yview)
        
        # Populate with filenames
        file_list = list(files)
        for i, f in enumerate(file_list):
            listbox.insert(tk.END, f"{i+1}. {os.path.basename(f)}")
        
        # Move buttons
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)
        
        def move_up():
            sel = listbox.curselection()
            if sel and sel[0] > 0:
                idx = sel[0]
                # Swap in list
                file_list[idx], file_list[idx-1] = file_list[idx-1], file_list[idx]
                # Update listbox
                listbox.delete(0, tk.END)
                for i, f in enumerate(file_list):
                    listbox.insert(tk.END, f"{i+1}. {os.path.basename(f)}")
                listbox.selection_set(idx-1)
        
        def move_down():
            sel = listbox.curselection()
            if sel and sel[0] < len(file_list) - 1:
                idx = sel[0]
                # Swap in list
                file_list[idx], file_list[idx+1] = file_list[idx+1], file_list[idx]
                # Update listbox
                listbox.delete(0, tk.END)
                for i, f in enumerate(file_list):
                    listbox.insert(tk.END, f"{i+1}. {os.path.basename(f)}")
                listbox.selection_set(idx+1)
        
        ttk.Button(btn_frame, text="↑ Move Up", command=move_up, width=12).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="↓ Move Down", command=move_down, width=12).pack(side=tk.LEFT, padx=5)
        
        # Bottom buttons
        bottom_frame = ttk.Frame(dialog)
        bottom_frame.pack(pady=15)
        
        def on_process():
            result['files'] = file_list
            dialog.destroy()
        
        def on_back():
            dialog.destroy()
        
        ttk.Button(bottom_frame, text="Process", command=on_process, width=12).pack(side=tk.LEFT, padx=5)
        ttk.Button(bottom_frame, text="Back", command=on_back, width=12).pack(side=tk.LEFT, padx=5)
        
        dialog.wait_window()
        return result['files']
    
    def _process_images_with_vision(self, ocr_files, combine=True):
        """
        Process image files and PDFs using AI vision model DIRECTLY.
        This method is called when user selects "Contains handwriting" checkbox.
        Bypasses ocr_image_smart and uses direct vision API calls.
        """
        if not ocr_files:
            return
        
        print(f"\n{'='*60}")
        print(f"🚀 _process_images_with_vision started")
        print(f"   Files: {len(ocr_files)}")
        print(f"   Combine: {combine}")
        print(f"{'='*60}\n")
        
        self.set_status("🤖 Processing with AI vision...")
        
        all_text = []
        entries = []
        all_source_files = []
        
        try:
            for i, file_path in enumerate(ocr_files):
                print(f"\n📄 Processing file {i+1}/{len(ocr_files)}: {os.path.basename(file_path)}")
                self.set_status(f"🤖 Processing file {i+1}/{len(ocr_files)} with AI vision...")
                
                try:
                    # Check if it's a PDF
                    if file_path.lower().endswith('.pdf'):
                        # Process PDF pages directly with vision API (NOT through ocr_image_smart)
                        pdf_entries = self._process_pdf_pages_direct_vision(file_path)
                        if pdf_entries:
                            print(f"   ✅ Got {len(pdf_entries)} entries from PDF")
                            for entry in pdf_entries:
                                entries.append({
                                    'start': len(entries),
                                    'text': entry.get('text', ''),
                                    'location': f"{os.path.basename(file_path)} - {entry.get('location', 'Page')}"
                                })
                            all_source_files.append(file_path)
                        else:
                            print(f"   ⚠️ No text extracted from PDF: {file_path}")
                    else:
                        # Use vision API for images
                        text = self._process_single_image_with_vision(file_path)
                        if text:
                            print(f"   ✅ Got {len(text)} characters from image")
                            all_text.append(text)
                            entries.append({
                                'start': len(entries),
                                'text': text,
                                'location': os.path.basename(file_path)
                            })
                            all_source_files.append(file_path)
                except Exception as e:
                    import traceback
                    print(f"   ❌ Vision processing failed for {file_path}: {e}")
                    traceback.print_exc()
        except Exception as e:
            import traceback
            print(f"❌ Batch processing error: {e}")
            traceback.print_exc()
        
        print(f"\n{'='*60}")
        print(f"📊 Processing complete:")
        print(f"   Total entries: {len(entries)}")
        print(f"   Total source files: {len(all_source_files)}")
        print(f"   Combine mode: {combine}")
        print(f"{'='*60}\n")
        
        if not entries:
            self.set_status("❌ No text extracted from any files")
            self.root.after(0, lambda: messagebox.showerror("OCR Error", "Failed to extract text from the files. Check console for details."))
            self.processing = False
            return
        
        if combine:
            print("📚 Calling _handle_multi_image_ocr_result to create COMBINED document...")
            # Handle as single combined document
            self._handle_multi_image_ocr_result(entries, all_source_files if all_source_files else ocr_files)
        else:
            print("📂 Calling _save_separate_vision_results to create SEPARATE documents...")
            # Process each separately - save each file's entries as a document
            self._save_separate_vision_results(entries, ocr_files)
        
        # Reset processing flag
        self.processing = False
    
    def _process_pdf_pages_direct_vision(self, pdf_path):
        """
        Process all pages of a PDF directly through vision API.
        Returns list of entries with text and location.
        """
        from pdf2image import convert_from_path
        import tempfile
        import base64
        
        provider = self.provider_var.get()
        model = self.model_var.get()
        api_key = self.api_key_var.get()
        
        if not api_key:
            print(f"⚠️ No API key for vision processing")
            return None
        
        try:
            self.set_status(f"📄 Converting PDF to images...")
            # Use higher DPI for better quality
            images = convert_from_path(pdf_path, dpi=300)
            total_pages = len(images)
            print(f"📄 PDF has {total_pages} pages")
            
            entries = []
            
            for page_num, image in enumerate(images, start=1):
                self.set_status(f"🤖 Vision processing page {page_num}/{total_pages}...")
                print(f"🤖 Processing page {page_num}...")
                
                # Save to temp file with high quality
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                    # Use PNG for better quality (no JPEG compression artifacts)
                    if image.mode in ('RGBA', 'P', 'LA'):
                        image = image.convert('RGB')
                    image.save(tmp.name, 'PNG')
                    tmp_path = tmp.name
                
                try:
                    # Read and encode
                    with open(tmp_path, 'rb') as f:
                        image_data = base64.b64encode(f.read()).decode('utf-8')
                    
                    # Better prompt that encourages full transcription
                    prompt = (
                        "This image contains a handwritten letter or document. "
                        "Your task is to transcribe EVERY word of handwritten text visible in this image. "
                        "Even if the handwriting is difficult to read, provide your best interpretation of each word. "
                        "DO NOT skip any text. DO NOT say 'illegible' - always give your best guess. "
                        "Preserve the original paragraph structure and line breaks. "
                        "Include ALL text from the beginning to the end of the page. "
                        "Output ONLY the transcribed text, nothing else."
                    )
                    
                    # Call appropriate vision API
                    text = None
                    try:
                        if "OpenAI" in provider or "ChatGPT" in provider:
                            text = self._vision_openai(api_key, model, image_data, 'image/png', prompt)
                        elif "Anthropic" in provider or "Claude" in provider:
                            text = self._vision_anthropic(api_key, model, image_data, 'image/png', prompt)
                        elif "Google" in provider or "Gemini" in provider:
                            text = self._vision_google(api_key, model, image_data, 'image/png', prompt)
                        else:
                            print(f"⚠️ Vision not supported for provider: {provider}")
                    except Exception as e:
                        print(f"⚠️ Vision API error on page {page_num}: {e}")
                        import traceback
                        traceback.print_exc()
                    
                    if text and text.strip():
                        print(f"✅ Page {page_num}: Got {len(text)} characters")
                        entries.append({
                            'text': text.strip(),
                            'location': f'Page {page_num}'
                        })
                    else:
                        print(f"⚠️ Page {page_num}: No text returned")
                finally:
                    try:
                        os.unlink(tmp_path)
                    except:
                        pass
            
            self.set_status(f"✅ Processed {total_pages} pages")
            print(f"📊 Total entries: {len(entries)}")
            return entries if entries else None
            
        except Exception as e:
            print(f"⚠️ PDF vision processing error: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _save_separate_vision_results(self, entries, ocr_files):
        """Save vision results as separate documents for each source file."""
        # Group entries by source file
        file_entries = {}
        for entry in entries:
            location = entry.get('location', '')
            # Extract filename from location
            for f in ocr_files:
                basename = os.path.basename(f)
                if basename in location:
                    if f not in file_entries:
                        file_entries[f] = []
                    file_entries[f].append(entry)
                    break
        
        # Save each file's entries
        for file_path, file_entry_list in file_entries.items():
            if file_entry_list:
                # Combine text from all entries for this file
                combined_text = "\n\n".join([e.get('text', '') for e in file_entry_list])
                if combined_text.strip():
                    self._save_single_ocr_result(file_path, combined_text)
        
        self.set_status(f"✅ Processed {len(file_entries)} files separately")
        self.refresh_library()
    
    def _process_single_image_with_vision(self, image_path):
        """Process a single image with AI vision model."""
        import base64
        
        # Get current provider and model
        provider = self.provider_var.get()
        model = self.model_var.get()
        api_key = self.api_key_var.get()
        
        if not api_key:
            self.root.after(0, lambda: messagebox.showerror("API Key Required", 
                "AI vision requires an API key.\nPlease configure in Settings."))
            return None
        
        # Read and encode image
        with open(image_path, 'rb') as f:
            image_data = base64.b64encode(f.read()).decode('utf-8')
        
        # Determine mime type
        ext = os.path.splitext(image_path)[1].lower()
        mime_types = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
            '.tif': 'image/tiff',
            '.tiff': 'image/tiff',
            '.bmp': 'image/bmp'
        }
        mime_type = mime_types.get(ext, 'image/jpeg')
        
        prompt = (
            "Extract ALL text from this image, preserving the original layout, "
            "paragraphs, and formatting as much as possible. "
            "This may contain handwritten text - please transcribe it accurately. "
            "Return only the extracted text, no explanations."
        )
        
        try:
            if "OpenAI" in provider or "ChatGPT" in provider:
                return self._vision_openai(api_key, model, image_data, mime_type, prompt)
            elif "Anthropic" in provider or "Claude" in provider:
                return self._vision_anthropic(api_key, model, image_data, mime_type, prompt)
            elif "Google" in provider or "Gemini" in provider:
                return self._vision_google(api_key, model, image_data, mime_type, prompt)
            else:
                self.root.after(0, lambda: messagebox.showwarning("Vision Not Supported",
                    f"Vision/OCR not supported for {provider}.\n"
                    "Please use OpenAI, Anthropic, or Google."))
                return None
        except Exception as e:
            print(f"Vision API error: {e}")
            return None
    
    def _provider_supports_vision(self, provider=None):
        """Check if a provider supports vision/image processing.
        
        Args:
            provider: Provider name to check. If None, uses current provider.
            
        Returns:
            tuple: (supports_vision: bool, provider_name: str)
        """
        if provider is None:
            provider = self.provider_var.get()
        
        # Providers that support vision API
        vision_providers = ['OpenAI', 'Anthropic', 'Google']
        
        supports = any(vp in provider for vp in vision_providers)
        return supports, provider
    
    def _vision_openai(self, api_key, model, image_data, mime_type, prompt):
        """Call OpenAI vision API."""
        import requests
        
        # Use gpt-4o for vision if model is old/non-vision capable
        # GPT-4o, GPT-4.5, GPT-5+ all support vision natively
        if not any(x in model.lower() for x in ['gpt-4o', 'gpt-4.5', 'gpt-5', 'vision', 'o1', 'o3', 'o4']):
            model = 'gpt-4o'
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # Newer OpenAI models (gpt-5.x, o1, o3, o4) require max_completion_tokens
        uses_new_param = any(x in model.lower() for x in ['gpt-5', 'o1', 'o3', 'o4'])
        
        payload = {
            "model": model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {
                        "url": f"data:{mime_type};base64,{image_data}"
                    }}
                ]
            }],
        }
        if uses_new_param:
            payload["max_completion_tokens"] = 4096
        else:
            payload["max_tokens"] = 4096
        
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=120
        )
        response.raise_for_status()
        return response.json()['choices'][0]['message']['content']
    
    def _vision_anthropic(self, api_key, model, image_data, mime_type, prompt):
        """Call Anthropic vision API."""
        import requests
        
        headers = {
            "x-api-key": api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01"
        }
        
        payload = {
            "model": model if 'claude' in model.lower() else "claude-3-5-sonnet-20241022",
            "max_tokens": 4096,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image", "source": {
                        "type": "base64",
                        "media_type": mime_type,
                        "data": image_data
                    }},
                    {"type": "text", "text": prompt}
                ]
            }]
        }
        
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=payload,
            timeout=120
        )
        response.raise_for_status()
        return response.json()['content'][0]['text']
    
    def _vision_google(self, api_key, model, image_data, mime_type, prompt):
        """Call Google Gemini vision API."""
        import requests
        
        model_name = model if 'gemini' in model.lower() else "gemini-1.5-flash"
        
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        
        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {"inline_data": {
                        "mime_type": mime_type,
                        "data": image_data
                    }}
                ]
            }]
        }
        
        response = requests.post(url, json=payload, timeout=120)
        response.raise_for_status()
        return response.json()['candidates'][0]['content']['parts'][0]['text']
    
    def _save_single_ocr_result(self, image_path, text):
        """Save a single OCR result to the library."""
        import datetime
        
        title = os.path.splitext(os.path.basename(image_path))[0]
        entries = [{'start': 0, 'text': text, 'location': 'Page 1'}]
        
        doc_id = add_document_to_library(
            doc_type="ocr",
            source=image_path,
            title=title,
            entries=entries,
            document_class="source",
            metadata={"source_file": os.path.basename(image_path)}
        )
        return doc_id


    def refresh_library(self):
        """Refresh is no longer needed - library opens fresh each time"""
        pass

    def convert_to_source_document(self):
        """Convert product document to read-only source"""
        if not self.current_document_id:
            messagebox.showerror("Error", "No document loaded")
            return
        
        response = messagebox.askyesno(
            "Convert to Source Document",
            "Convert this product document to a source document?\n\n"
            "This will:\n"
            "• Make it permanently read-only\n"
            "• Mark it as a source document\n"
            "• Cannot be undone\n\n"
            "Continue?"
        )
        
        if response:
            success = convert_document_to_source(self.current_document_id)
            
            if success:
                # Update local state
                self.current_document_class = "source"
                self.current_document_metadata["editable"] = False
                
                # Close editing window
                if hasattr(self, '_editing_window'):
                    self._editing_window.destroy()
                
                messagebox.showinfo(
                    "Converted",
                    "✅ Document is now a read-only source document"
                )
            else:
                messagebox.showerror("Error", "Failed to convert document")

    def save_ai_output_as_product_document(self, output_text: str):
        """Save AI output as new editable product document"""
        
        # ============================================================
        # CHECK FOR PRE-CREATED DOCUMENT (from Thread Viewer branch creation)
        # If the document was pre-created by ThreadViewer, just save the
        # thread content without creating a duplicate document.
        # ============================================================
        print(f"\n{'='*60}")
        print(f"💾 SAVE_AI_OUTPUT_AS_PRODUCT_DOCUMENT CALLED")
        print(f"   current_document_id: {self.current_document_id}")
        print(f"   thread message count: {len(self.current_thread) if hasattr(self, 'current_thread') else 0}")
        print(f"   has metadata attr: {hasattr(self, 'current_document_metadata')}")
        if hasattr(self, 'current_document_metadata') and self.current_document_metadata:
            print(f"   metadata keys: {list(self.current_document_metadata.keys())}")
            print(f"   pre_created flag: {self.current_document_metadata.get('pre_created', 'NOT SET')}")
        print(f"{'='*60}")
        
        if hasattr(self, 'current_document_metadata') and self.current_document_metadata:
            if self.current_document_metadata.get('pre_created'):
                print(f"🔔 Pre-created document detected, saving thread only")
                print(f"   SAVING TO: {self.current_document_id}")
                # Just save the thread to the existing document
                if self.current_document_id and self.current_thread:
                    from document_library import save_thread_to_document
                    thread_metadata = {
                        "model": self.model_var.get(),
                        "provider": self.provider_var.get(),
                        "last_updated": datetime.datetime.now().isoformat(),
                        "message_count": self.thread_message_count
                    }
                    save_thread_to_document(self.current_document_id, self.current_thread, thread_metadata)
                    print(f"   ✓ Thread saved to pre-created document: {self.current_document_id}")
                # Clear the pre_created flag so subsequent saves work normally
                self.current_document_metadata['pre_created'] = False
                return self.current_document_id

        # Get processing info
        prompt_name = self.prompt_combo.get() if self.prompt_combo.get() else "Custom Prompt"
        provider = self.provider_var.get()
        model = self.model_var.get()

        # Determine if we have a source document
        has_source = bool(self.current_document_id)

        if has_source:
            # Get original document
            original_doc = get_document_by_id(self.current_document_id)
            if not original_doc:
                messagebox.showerror("Error", "Source document not found")
                return

            # Create title with source
            title = f"[Response] {prompt_name}: {original_doc['title']}"
            source_info = f"AI analysis of: {self.current_document_source}"

            metadata = {
                "parent_document_id": self.current_document_id,
                "parent_title": original_doc['title'],
                "prompt_name": prompt_name,
                "prompt_text": self.prompt_text.get('1.0', tk.END).strip(),
                "ai_provider": provider,
                "ai_model": model,
                "created": datetime.datetime.now().isoformat(),
                "editable": True
            }
        else:
            # General chat without source document
            timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
            title = f"[Response] {prompt_name} - {timestamp}"
            source_info = f"AI Chat - {provider} - {model}"

            metadata = {
                "prompt_name": prompt_name,
                "prompt_text": self.prompt_text.get('1.0', tk.END).strip(),
                "ai_provider": provider,
                "ai_model": model,
                "created": datetime.datetime.now().isoformat(),
                "editable": True,
                "general_chat": True
            }

        # Convert to entries (split into paragraphs for better structure)
        paragraphs = [p.strip() for p in output_text.split('\n\n') if p.strip()]
        if not paragraphs:
            entries = [{"text": output_text, "location": "AI Generated"}]
        else:
            entries = [{"text": para, "location": f"Paragraph {i + 1}"} for i, para in enumerate(paragraphs)]

        # Add as response document (using "response" class for consistency)
        doc_id = add_document_to_library(
            doc_type="ai_response",
            document_class="response",  # Changed from "product" to "response"
            source=source_info,
            title=title,
            entries=entries,
            metadata=metadata
        )

        if doc_id:
            # ===== NEW: SAVE CONVERSATION THREAD =====
            # This enables the 💬 icon and thread viewing!
            if hasattr(self, 'current_thread') and self.current_thread:
                try:
                    from document_library import save_thread_to_document

                    thread_metadata = {
                        'model': model,
                        'provider': provider,
                        'last_updated': datetime.datetime.now().isoformat(),
                        'message_count': len([m for m in self.current_thread if m.get('role') == 'user'])
                    }

                    save_thread_to_document(doc_id, self.current_thread, thread_metadata)
                    print(f"✅ Saved conversation thread ({thread_metadata['message_count']} messages)")
                except Exception as e:
                    print(f"⚠️ Failed to save thread: {e}")
            # ===== END NEW CODE =====

            # Status message instead of popup (Thread Viewer opens automatically)
            self.set_status(f"✅ Response saved: {title[:50]}..." if len(title) > 50 else f"✅ Response saved: {title}")
            print(f"✅ Response document created: {title}")

            # Refresh library display if open
            if hasattr(self, 'refresh_library'):
                self.refresh_library()

            return doc_id
        else:
            messagebox.showerror("Error", "Failed to create response document")
            return None

    def setup_prompt_frame(self, main_frame):
        """Prompt selector with conversation buttons"""
        prompt_frame = ttk.LabelFrame(main_frame, text="Select a prompt from the Prompts Library, or enter a prompt directly into the box below:", padding=(8, 5, 8, 5))
        prompt_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 3))

        # === Row 1: AI Provider and Prompts Library ===
        ai_row1 = ttk.Frame(prompt_frame)
        ai_row1.pack(fill=tk.X, pady=2)
        
        # AI Provider (left side)
        ttk.Label(ai_row1, text="AI Provider:", font=('Arial', 9), foreground='red', width=12).pack(side=tk.LEFT, padx=(0, 2))
        self.main_provider_combo = ttk.Combobox(ai_row1, textvariable=self.provider_var, state="readonly", width=40, style='Input.TCombobox')
        # Include all providers including Ollama (Local)
        self.main_provider_combo['values'] = list(self.models.keys())
        self.main_provider_combo.pack(side=tk.LEFT, padx=(0, 2))
        self.main_provider_combo.bind('<<ComboboxSelected>>', self.on_provider_select)
        if HELP_TEXTS:
            add_help(self.main_provider_combo, **HELP_TEXTS.get("provider_dropdown", {"title": "AI Provider", "description": "Select AI service"}))
        
        # Prompts Library button (right side of row 1)
        prompts_lib_btn = ttk.Button(ai_row1, text="Prompts Library", command=self.open_prompt_manager, width=20)
        prompts_lib_btn.pack(side=tk.RIGHT, padx=2)
        if HELP_TEXTS:
            add_help(prompts_lib_btn, **HELP_TEXTS.get("prompts_library_button", {"title": "Prompts Library", "description": "Manage saved prompts"}))
        
        # === Row 2: AI Model ===
        ai_row2 = ttk.Frame(prompt_frame)
        ai_row2.pack(fill=tk.X, pady=(2, 0))

        # AI Model (left side, aligned under AI Provider
        ttk.Label(ai_row2, text="AI Model:", font=('Arial', 9), foreground='red', width=8).pack(side=tk.LEFT, padx=(0, 2))
        # Model info button
        model_info_btn = tk.Button(
            ai_row2,
            text="?",
            font=('Arial', 8, 'bold'),
            width=2,
            height=1,
            relief=tk.FLAT,
            bg='#dcdad5',
            fg='#0066CC',
            cursor='hand2',
            command=self._show_model_guide
        )
        model_info_btn.pack(side=tk.LEFT, padx=(0, 3))

        self.main_model_combo = ttk.Combobox(ai_row2, textvariable=self.model_var, state="readonly", width=40, style='Input.TCombobox')
        self.main_model_combo.pack(side=tk.LEFT, padx=2)
        self.main_model_combo.bind('<<ComboboxSelected>>', lambda e: self.save_model_selection())
        if HELP_TEXTS:
            add_help(self.main_model_combo, **HELP_TEXTS.get("model_dropdown", {"title": "AI Model", "description": "Select specific model"}))

        # Initialize model list
        self.on_provider_select()

        # Prompt selector row - now directly above prompt text area
        selector_row = ttk.Frame(prompt_frame)
        selector_row.pack(fill=tk.X, pady=(2, 0))

        ttk.Label(selector_row, text="Prompt Name:", font=('Arial', 9), foreground='red', width=12).pack(side=tk.LEFT, padx=(0, 2))
        self.prompt_combo = ttk.Combobox(selector_row, values=[p['name'] for p in self.prompts],
                                         state="readonly", width=40,  style='Input.TCombobox')
        self.prompt_combo.pack(side=tk.LEFT, fill=tk.X, expand=False, padx=(0,2))
        self.prompt_combo.bind('<<ComboboxSelected>>', self.on_prompt_select)
        if HELP_TEXTS:
            add_help(self.prompt_combo, **HELP_TEXTS.get("prompt_dropdown", {"title": "Prompt Selector", "description": "Choose a saved prompt"}))

        # Run Prompt dropdown (Via App / Via Web)
        self.run_prompt_frame = ttk.Frame(selector_row)
        self.run_prompt_frame.pack(side=tk.RIGHT, padx=2)
        
        self.process_btn = ttk.Button(
            self.run_prompt_frame, 
            text="Run", 
            command=self.process_document, 
            width=15
        )
        self.process_btn.pack(side=tk.LEFT, padx=(0, 2))
        if HELP_TEXTS:
            add_help(self.process_btn, **HELP_TEXTS.get("run_prompt_button", {"title": "Run", "description": "Send prompt to AI"}))
        
        # Dropdown arrow button
        self.run_prompt_menu = tk.Menu(self.root, tearoff=0)
        self.run_prompt_menu.add_command(label="Via DocAnalyser", command=self.process_document)
        self.run_prompt_menu.add_command(label="Via Local AI", command=self.run_via_local_ai)
        self.run_prompt_menu.add_command(label="Via Web", command=self.export_to_web_chat)
        
        def show_run_menu():
            # Position menu below the button
            x = self.process_btn.winfo_rootx()
            y = self.process_btn.winfo_rooty() + self.process_btn.winfo_height()
            self.run_prompt_menu.post(x, y)
        
        self.run_prompt_dropdown = ttk.Button(self.run_prompt_frame, text="▼", command=show_run_menu, width=2)
        self.run_prompt_dropdown.pack(side=tk.LEFT)
        if HELP_TEXTS:
            add_help(self.run_prompt_dropdown, **HELP_TEXTS.get("run_prompt_dropdown", {"title": "Run Optpythonions", "description": "Alternative ways to run prompt"}))

        # Prompt text area
        self.prompt_text = scrolledtext.ScrolledText(prompt_frame, wrap=tk.WORD, height=2, font=('Arial', 10), bg=self.input_bg_color)
        self.prompt_text.pack(fill=tk.BOTH, expand=True, pady=(5, 5))
        if HELP_TEXTS:
            add_help(self.prompt_text, **HELP_TEXTS.get("prompt_text", {"title": "Prompt Text", "description": "Instructions for AI"}))
        
        # Auto-expand prompt area based on content
        self.prompt_text.bind('<KeyRelease>', self._auto_expand_prompt_text)
        self.prompt_text.bind('<<Paste>>', lambda e: self.root.after(10, self._auto_expand_prompt_text))
        self.prompt_text.bind('<<Modified>>', lambda e: self.root.after(10, self._auto_expand_prompt_text))

        # Conversation buttons row (below prompt text)
        conversation_row = ttk.Frame(prompt_frame)
        conversation_row.pack(fill=tk.X, pady=(0, 2))

        # View Source button - opens viewer in Source Mode
        self.view_source_btn = ttk.Button(conversation_row, text="View Source", command=self._view_source, width=14)
        self.view_source_btn.pack(side=tk.LEFT, padx=2)
        if HELP_TEXTS:
            add_help(self.view_source_btn, **HELP_TEXTS.get("view_source_button", {"title": "View Source", "description": "View the full source document in the viewer"}))
        
        # View Thread button - opens viewer in Conversation Mode
        self.view_thread_btn = ttk.Button(conversation_row, text="View Thread", command=self._view_thread, width=14)
        self.view_thread_btn.pack(side=tk.LEFT, padx=2)
        if HELP_TEXTS:
            add_help(self.view_thread_btn, **HELP_TEXTS.get("view_thread_button", {"title": "View Thread", "description": "View conversation history and ask follow-up questions"}))
        
        # AI Costs button
        self.ai_costs_btn = ttk.Button(conversation_row, text="AI Costs", command=self.show_costs, width=14)
        self.ai_costs_btn.pack(side=tk.LEFT, padx=2)
        if HELP_TEXTS:
            add_help(self.ai_costs_btn, **HELP_TEXTS.get("ai_costs_button", {"title": "AI Costs", "description": "View API usage costs"}))
        
        # Restart button (right side) - restarts DocAnalyser to cancel processing or reset
        self.cancel_btn = ttk.Button(conversation_row, text="Restart", command=self.cancel_processing, width=20)
        self.cancel_btn.pack(side=tk.RIGHT, padx=2)
        if HELP_TEXTS:
            add_help(self.cancel_btn, **HELP_TEXTS.get("restart_button", {"title": "Restart", "description": "Restart DocAnalyser"}))

        if self.prompts:
            # Try to select the user's default prompt, fall back to first prompt
            default_prompt_name = self.config.get('default_prompt', '')
            default_idx = 0
            if default_prompt_name:
                for i, p in enumerate(self.prompts):
                    if p['name'] == default_prompt_name:
                        default_idx = i
                        break
            self.prompt_combo.current(default_idx)
            self.on_prompt_select()

    def _update_load_button_highlight(self):
        """Update Load button style based on input content."""
        if not hasattr(self, 'load_btn') or not hasattr(self, 'universal_input_entry'):
            return
        
        try:
            # Get current content (excluding placeholder text)
            content = self.universal_input_entry.get('1.0', 'end-1c').strip()
            
            # Check if placeholder is active (don't highlight if showing placeholder)
            is_placeholder = hasattr(self, 'placeholder_active') and self.placeholder_active
            
            # Highlight green if there's real content (not placeholder)
            if content and not is_placeholder:
                self.load_btn.configure(style='Highlight.TButton')
            else:
                # Reset to default style
                self.load_btn.configure(style='TButton')
        except Exception as e:
            # Silently ignore any errors
            pass

    def _update_run_button_highlight(self, has_document=None):
        """Update Run button style based on document state."""
        if not hasattr(self, 'process_btn'):
            return
        
        try:
            # Check if highlighting is enabled (disabled after Run is pressed)
            # Default to False - only highlight when explicitly enabled after document load
            if not getattr(self, '_run_highlight_enabled', False):
                return  # Don't change highlight state
            
            # Determine if there's a document to process
            if has_document is None:
                has_document = (
                    (hasattr(self, 'current_document_text') and self.current_document_text) or
                    (hasattr(self, 'current_document_id') and self.current_document_id)
                )
            
            # Highlight green if there's a document ready to process
            if has_document:
                self.process_btn.configure(style='Highlight.TButton')
            else:
                # Reset to default style
                self.process_btn.configure(style='TButton')
        except Exception as e:
            # Silently ignore any errors
            pass

    def _auto_expand_input(self, event=None):
        """Auto-expand input area based on content - only when needed."""
        if not hasattr(self, 'universal_input_entry'):
            return
        
        # Skip if placeholder is active
        if hasattr(self, 'placeholder_active') and self.placeholder_active:
            return
        
        # Get current content
        content = self.universal_input_entry.get('1.0', 'end-1c')
        
        # Count actual lines needed
        line_count = content.count('\n') + 1 if content.strip() else 1
        
        # Only expand beyond 1 line if content actually needs it
        min_height = 1
        max_height = 4
        new_height = max(min_height, min(line_count, max_height))
        
        # Only update if height changed
        try:
            current_height = int(self.universal_input_entry.cget('height'))
            if new_height != current_height:
                # Calculate height difference in pixels (approx 20 pixels per line)
                height_diff = (new_height - current_height) * 20
                
                # Update widget height
                self.universal_input_entry.config(height=new_height)
                
                # Adjust window height (both expand and shrink)
                self._adjust_window_height(height_diff)
        except:
            pass

    def _auto_expand_prompt_text(self, event=None):
        """Auto-expand prompt text area based on content, including wrapped lines."""
        if not hasattr(self, 'prompt_text'):
            return
        
        # Get current content
        content = self.prompt_text.get('1.0', 'end-1c')
        
        if not content.strip():
            line_count = 1
        else:
            # Count display lines (includes word-wrapped lines)
            # This uses tkinter's built-in display line counting
            try:
                self.prompt_text.update_idletasks()
                display_lines = self.prompt_text.count('1.0', 'end-1c', 'displaylines')
                if display_lines and display_lines[0] is not None:
                    line_count = display_lines[0] + 1  # count returns boundaries, +1 for lines
                else:
                    # Fallback: count explicit newlines
                    line_count = content.count('\n') + 1
            except (tk.TclError, TypeError):
                # Fallback: count explicit newlines
                line_count = content.count('\n') + 1
        
        # Clamp between min and max for prompt widget
        min_height = 2
        max_height = 8
        new_height = max(min_height, min(line_count, max_height))
        
        # Get current prompt height
        try:
            current_height = int(self.prompt_text.cget('height'))
        except:
            return
        
        if new_height != current_height:
            # Calculate height difference in pixels (~20 pixels per line)
            height_diff = (new_height - current_height) * 20
            
            # Update prompt widget height
            self.prompt_text.config(height=new_height)
            
            # Also adjust window height (both expand and shrink)
            self._adjust_window_height(height_diff)
    
    def _adjust_window_height(self, height_diff):
        """Adjust window height (expand or shrink), respecting limits."""
        try:
            # Get current window geometry
            self.root.update_idletasks()
            current_height = self.root.winfo_height()
            current_width = self.root.winfo_width()
            
            # Get screen height
            screen_height = self.root.winfo_screenheight()
            max_height = int(screen_height * 0.65)  # 65% of screen max
            
            # Calculate new height
            new_height = current_height + height_diff
            
            # Clamp to max
            new_height = min(new_height, max_height)
            
            # Don't shrink below minimum
            min_window_height = 420  # Base window height
            new_height = max(new_height, min_window_height)
            
            # Apply new height
            if new_height != current_height:
                self.root.geometry(f"{current_width}x{new_height}")
        except Exception as e:
            print(f"Could not adjust window height: {e}")
    
    def on_prompt_select(self, event=None):
        """Handle prompt selection from hierarchical dropdown"""
        sel = self.prompt_combo.current()
        if sel < 0:
            return

        # Get the selected entry
        selected_entry = self.prompt_combo.get()

        # Skip if it's a header or separator
        if is_header(selected_entry) or is_separator(selected_entry):
            # Move to next selectable item
            values = self.prompt_combo['values']
            for i in range(sel + 1, len(values)):
                if not is_header(values[i]) and not is_separator(values[i]):
                    self.prompt_combo.current(i)
                    self.on_prompt_select()  # Recursive call with new selection
                    return
            return

        # Extract prompt name and get prompt data
        prompt_name = extract_prompt_name(selected_entry)

        # Try to get from name map first (faster)
        if hasattr(self, 'prompt_name_map') and selected_entry in self.prompt_name_map:
            prompt_data = self.prompt_name_map[selected_entry]
        else:
            # Fallback: search in prompts list
            prompt_data = None
            for p in self.prompts:
                if p['name'] == prompt_name:
                    prompt_data = p
                    break

        # Update text area
        if prompt_data:
            self.prompt_text.delete('1.0', tk.END)
            self.prompt_text.insert('1.0', prompt_data['text'])
            # Trigger auto-expand
            self.root.after(10, self._auto_expand_prompt_text)

    def setup_control_frame(self, main_frame):
        """Control frame - Settings moved to header bar"""
        # Settings button moved to header bar, this frame is now empty
        # Keeping the method for potential future use
        pass

    def setup_ai_selector_frame(self, main_frame):
        """AI provider and model selector - NOW INTEGRATED INTO setup_prompt_frame
        
        This method is kept for backward compatibility but no longer creates UI elements.
        The AI Provider, AI Model, and AI Costs controls are now in the Prompt frame.
        """
        # AI controls moved to setup_prompt_frame for space efficiency
        pass

    def setup_help_button(self, main_frame):
        """Placeholder - help is now accessed via Help menu"""
        # Help intro moved to Help menu → Application Overview
        # This saves vertical space and keeps UI cleaner
        pass

    def setup_web_response_banner(self, main_frame):
        """
        🆕 NEW: Banner that appears after 'Via Web' to capture the AI response.
        Hidden by default, shown when awaiting a web response.
        """
        # Create the banner frame (hidden initially) - compact design
        self.web_response_banner = tk.Frame(main_frame, bg='#4A90D9', padx=8, pady=5)
        # Don't pack yet - will be shown/hidden dynamically
        
        # Single row layout
        row_frame = tk.Frame(self.web_response_banner, bg='#4A90D9')
        row_frame.pack(fill=tk.X)
        
        # Left side: Icon and short message
        tk.Label(
            row_frame,
            text="📋",
            font=('Arial', 11),
            bg='#4A90D9',
            fg='white'
        ).pack(side=tk.LEFT)
        
        self.web_response_info_label = tk.Label(
            row_frame,
            text="Copy AI response, then:",
            font=('Arial', 9),
            bg='#4A90D9',
            fg='white'
        )
        self.web_response_info_label.pack(side=tk.LEFT, padx=(3, 8))
        
        # Capture button (compact)
        self.capture_response_btn = tk.Button(
            row_frame,
            text="✅ Capture",
            font=('Arial', 9, 'bold'),
            bg='#28a745',
            fg='white',
            activebackground='#218838',
            activeforeground='white',
            bd=0,
            padx=8,
            pady=2,
            cursor='hand2',
            command=self.capture_web_response
        )
        self.capture_response_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        # Add help to capture button
        if HELP_TEXTS:
            add_help(self.capture_response_btn, **HELP_TEXTS.get("web_response_capture", 
                     {"title": "Capture Response", "description": "Save the AI response from clipboard"}))
        
        # Dismiss button (compact)
        dismiss_btn = tk.Button(
            row_frame,
            text="✕",
            font=('Arial', 9),
            bg='#6c757d',
            fg='white',
            activebackground='#5a6268',
            activeforeground='white',
            bd=0,
            padx=6,
            pady=2,
            cursor='hand2',
            command=self.hide_web_response_banner
        )
        dismiss_btn.pack(side=tk.LEFT)
    
    def show_web_response_banner(self, context: dict):
        """
        Show the web response banner and store context for later.
        
        Args:
            context: Dictionary containing:
                - prompt: The prompt that was sent
                - source_text: The document text (truncated for storage)
                - provider: The AI provider used
                - source_name: Name/title of the source document
                - document_id: ID of source document if available
                - attachment_names: List of attachment names if any
        """
        self.pending_web_response = context
        
        # Update info label with context
        provider = context.get('provider', 'AI')
        info_text = f" - Copy the {provider} response, then click Capture"
        self.web_response_info_label.config(text=info_text)
        
        # Show the banner (pack at bottom, above status bar)
        self.web_response_banner.pack(fill=tk.X, side=tk.BOTTOM)
        
        # Scroll to make banner visible if needed
        self.root.update_idletasks()
    
    def hide_web_response_banner(self):
        """Hide the web response banner and clear pending context."""
        self.pending_web_response = None
        self.web_response_banner.pack_forget()
    
    def capture_web_response(self):
        """
        Capture the AI response from clipboard and save to Documents Library.
        Links it to the original prompt/source context.
        """
        if not self.pending_web_response:
            messagebox.showinfo("No Pending Request", 
                               "No web response is pending. Use 'Run Prompt → Via Web' first.")
            return
        
        # Get clipboard content
        try:
            clipboard_text = self.root.clipboard_get()
        except tk.TclError:
            messagebox.showwarning("Clipboard Empty", 
                                  "The clipboard is empty.\n\n"
                                  "Please copy the AI response from your browser first.")
            return
        
        # Basic validation
        if not clipboard_text or len(clipboard_text.strip()) < 20:
            messagebox.showwarning("Invalid Content", 
                                  "The clipboard content is too short to be an AI response.\n\n"
                                  "Please copy the full response from your browser.")
            return
        
        # Prepare metadata
        context = self.pending_web_response
        provider = context.get('provider', 'Unknown')
        source_name = context.get('source_name', 'Unknown source')
        
        # Create a title using the source document name (like the original)
        title = f"[Web Response] {provider}: {source_name}"
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
        header = (
            f"=== Web Response Captured ===\n"
            f"Provider: {provider}\n"
            f"Source: {source_name}\n"
            f"Captured: {timestamp}\n"
            f"{'=' * 30}\n\n"
        )
        
        full_text = header + clipboard_text.strip()
        
        # Save to Documents Library
        try:
            from document_library import add_document_to_library
            
            metadata = {
                "captured_from": "web_response",
                "provider": provider,
                "original_prompt": context.get('prompt', ''),
                "source_document_id": context.get('document_id'),
                "source_name": source_name,
                "attachment_names": context.get('attachment_names', []),
                "editable": True,
                "captured_at": timestamp
            }
            
            # Create entry structure expected by add_document_to_library
            entries = [{
                "text": full_text,
                "timestamp": timestamp
            }]
            
            doc_id = add_document_to_library(
                doc_type="web_response",
                source=f"web_response_{timestamp.replace(':', '-').replace(' ', '_')}",
                title=title,
                entries=entries,
                metadata=metadata,
                document_class="product"
            )
            
            # 🆕 NEW: Create conversation thread on the SOURCE document (like Via DocAnalyser)
            source_doc_id = context.get('document_id')
            original_prompt = context.get('prompt', '')
            
            if source_doc_id and original_prompt:
                # Save any existing thread first
                if self.thread_message_count > 0 and self.current_document_id:
                    self.save_current_thread()
                
                # Set up for the source document's thread
                self.current_document_id = source_doc_id
                
                # Load existing thread for this document if any
                try:
                    from document_library import get_document_by_id
                    source_doc = get_document_by_id(source_doc_id)
                    if source_doc:
                        existing_thread = source_doc.get('metadata', {}).get('conversation_thread', [])
                        self.current_thread = existing_thread if existing_thread else []
                        # Count existing user messages
                        self.thread_message_count = sum(1 for m in self.current_thread if m.get('role') == 'user')
                except:
                    self.current_thread = []
                    self.thread_message_count = 0
                
                # Add the prompt and response to thread (with provider/model info)
                self.add_message_to_thread("user", original_prompt)
                
                # Add assistant response with provider info
                self.current_thread.append({
                    "role": "assistant",
                    "content": clipboard_text.strip(),
                    "provider": provider,
                    "model": f"{provider} (via Web)",
                    "source": "web_capture"
                })
                
                # Save the thread
                self.save_current_thread()
                
                # Update button states (conversation now exists)
                self.update_button_states()
            
            # Hide the banner
            self.hide_web_response_banner()
            
            # Show success message
            response_preview = clipboard_text.strip()[:100]
            if len(clipboard_text.strip()) > 100:
                response_preview += '...'
            
            # Build message based on whether thread was created
            if source_doc_id and original_prompt:
                msg = (f"AI response saved to Documents Library!\n\n"
                       f"Preview: {response_preview}\n\n"
                       f"💬 Conversation thread started on source document.\n\n"
                       f"Would you like to load the source document now?")
            else:
                msg = (f"AI response saved to Documents Library!\n\n"
                       f"Preview: {response_preview}\n\n"
                       f"Would you like to load this response now?")
            
            result = messagebox.askyesno("✅ Response Captured", msg)
            
            if result:
                # Load the appropriate document
                if source_doc_id and original_prompt:
                    # Load source document (where thread is attached)
                    self._load_document_by_id(source_doc_id)
                else:
                    # Load the web response document
                    self._load_document_by_id(doc_id)
            
            self.set_status(f"✅ Web response captured and saved to Documents Library")
            
        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save response:\n{str(e)}")
            import traceback
            traceback.print_exc()
    
    def _load_document_by_id(self, doc_id: str):
        """Load a document from the library by its ID."""
        try:
            from document_library import get_document_by_id, load_document_entries
            
            doc = get_document_by_id(doc_id)
            if not doc:
                print(f"Document not found: {doc_id}")
                return
            
            # Try to load entries - first from document, then from separate storage
            entries = doc.get('entries', [])
            if not entries:
                # Try loading from entries storage
                entries = load_document_entries(doc_id)
            
            if entries:
                combined_text = "\n\n".join([e.get('text', '') for e in entries if e.get('text')])
            else:
                combined_text = ""
            
            if not combined_text:
                print(f"No text content found for document: {doc_id}")
                return
            
            self.current_document_text = combined_text
            self.current_document_source = doc.get('source', doc.get('title', 'Unknown'))
            self.current_document_id = doc_id
            self.current_document_class = doc.get('document_class', 'source')
            self.current_document_metadata = doc.get('metadata', {})
            self.current_entries = entries
            
            
            # Update status based on document class
            if self.current_document_class in ['response', 'product', 'processed_output']:
                # For Response documents, Thread Viewer will auto-open and show guidance
                self.set_status("✅ Response document loaded")
            else:
                self.set_status("✅ Document loaded - Select prompt and click Run")
            
            # Load any saved thread for this document (instead of clearing)
            self.load_saved_thread()
            
            # Update button states (View Source, View Thread, etc.)
            # Enable Run button highlight for newly loaded document
            self._run_highlight_enabled = True
            self.update_button_states()
                
        except Exception as e:
            print(f"Error loading document: {e}")
            import traceback
            traceback.print_exc()

    def setup_status_bar(self, main_frame):
        """Status bar - with text wrapping for long messages"""
        status_frame = ttk.Frame(main_frame)
        status_frame.pack(fill=tk.X, side=tk.BOTTOM)

        # Status label with wrapping (use tk.Label for wraplength support)
        # Set a reasonable fixed wraplength that works for most window sizes
        self.status_var = tk.StringVar(value="Ready. For context-sensitive help, right-click on buttons or text boxes.")
        self.status_label = tk.Label(
            status_frame, 
            textvariable=self.status_var, 
            font=('Arial', 8),
            anchor='w',
            justify='left',
            wraplength=800  # Wide enough for most messages, will wrap on smaller windows
        )
        self.status_label.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

    def on_provider_select(self, event=None):
        provider = self.provider_var.get()
        
        # Special handling for Ollama - refresh models from server and populate dropdown
        if provider == "Ollama (Local)":
            # Refresh models from Ollama server
            self._refresh_ollama_models(show_errors=True)
            
            # Populate the model dropdown with Ollama models
            combo = getattr(self, 'main_model_combo', None) or getattr(self, 'model_combo', None)
            if combo:
                combo['values'] = self.models.get("Ollama (Local)", [])
            
            # Select last used model or first available
            last_model = self.config.get("last_model", {}).get("Ollama (Local)", "")
            available_models = self.models.get("Ollama (Local)", [])
            if last_model and last_model in available_models:
                self.model_var.set(last_model)
            elif available_models and not available_models[0].startswith("("):
                self.model_var.set(available_models[0])
            else:
                self.model_var.set("")
            
            # Auto-switch to tiny chunk size for local models with limited context
            current_chunk_size = self.config.get("chunk_size", "medium")
            if current_chunk_size != "tiny":
                # Save the previous chunk size so we can restore it later
                self.config["chunk_size_before_local_ai"] = current_chunk_size
                self.config["chunk_size"] = "tiny"
                save_config(self.config)
            
            model_count = len([m for m in available_models if not m.startswith("(")])
            if model_count > 0:
                self.set_status(f"💻 Ollama ready - {model_count} model(s) available")
            else:
                # No models installed - offer to set up
                self.set_status("💻 Ollama selected - setting up...")
                if LOCAL_AI_SETUP_AVAILABLE and is_ollama_installed():
                    self.root.after(100, self._open_local_ai_setup)
                else:
                    self.set_status("💻 Ollama selected - install Ollama from ollama.com first")
            return
        
        # Switching to a cloud provider - restore previous chunk size if we saved one
        saved_chunk_size = self.config.get("chunk_size_before_local_ai")
        if saved_chunk_size:
            current_chunk_size = self.config.get("chunk_size", "medium")
            if current_chunk_size == "tiny":
                self.config["chunk_size"] = saved_chunk_size
                # Clear the saved value so we don't keep restoring it
                del self.config["chunk_size_before_local_ai"]
                save_config(self.config)
        
        # Update the main window model combo (use main_model_combo if available, fallback to model_combo)
        combo = getattr(self, 'main_model_combo', None) or getattr(self, 'model_combo', None)
        if combo:
            combo['values'] = self.models.get(provider, [])
        last_model = self.config["last_model"].get(provider, "")
        if last_model in self.models.get(provider, []):
            self.model_var.set(last_model)
        else:
            self.model_var.set("")
        self.api_key_var.set(self.config["keys"].get(provider, ""))
        
        # If default to recommended is enabled, select the recommended model
        if self.config.get("default_to_recommended_model", False):
            self._select_default_or_recommended_model()
    
    def _refresh_ollama_models(self, show_errors=False):
        """Fetch available models from Ollama server"""
        try:
            from ai_handler import check_ollama_connection
            
            base_url = self.config.get("ollama_base_url", "http://localhost:11434")
            connected, status, models = check_ollama_connection(base_url)
            
            if connected and models:
                # Update models list with actual models from Ollama
                self.models["Ollama (Local)"] = models
                # Don't set status here - let the caller handle it to avoid overwriting
            else:
                # Keep placeholder if not connected
                self.models["Ollama (Local)"] = ["(Start Ollama server first)"]
                if show_errors:
                    self.set_status(status)
        except Exception as e:
            self.models["Ollama (Local)"] = ["(Connection error)"]
            if show_errors:
                self.set_status(f"Ollama error: {str(e)}")

    def _load_model_info(self):
        """Load model information from JSON file"""
        model_info_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'model_info.json')
        try:
            if os.path.exists(model_info_path):
                with open(model_info_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error loading model_info.json: {e}")
        return {}
    
    def _save_model_info(self, model_info):
        """Save model information to JSON file"""
        model_info_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'model_info.json')
        try:
            with open(model_info_path, 'w', encoding='utf-8') as f:
                json.dump(model_info, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving model_info.json: {e}")
    
    def _generate_model_description(self, model_id, provider):
        """Generate a description for an unknown model based on its name patterns"""
        # Use the actual model_id as the display name - this ensures uniqueness
        # Just clean up any 'models/' prefix that some APIs include
        display_name = model_id
        if display_name.startswith("models/"):
            display_name = display_name[7:]
        
        # Use smart placeholder based on model name patterns
        return self._create_placeholder_info(model_id, display_name)
    
    def _create_placeholder_info(self, model_id, friendly_name):
        """Create a smart placeholder based on model name patterns"""
        model_lower = model_id.lower()
        
        # Default values
        speed = "⚡⚡⚡"
        cost = "💰💰"
        quality = "⭐⭐⭐"
        best_for = "General AI tasks"
        
        # Speed/size indicators - fast models
        if any(x in model_lower for x in ["mini", "small", "fast", "flash", "haiku", "instant"]):
            speed = "⚡⚡⚡⚡⚡"
            cost = "💰"
            quality = "⭐⭐⭐"
            best_for = "Quick tasks, everyday use"
        # Large/premium models
        elif any(x in model_lower for x in ["large", "opus", "ultra", "max"]):
            speed = "⚡⚡"
            cost = "💰💰💰💰💰"
            quality = "⭐⭐⭐⭐⭐"
            best_for = "Complex analysis, detailed work"
        # Pro/advanced models
        elif any(x in model_lower for x in ["pro", "plus", "advanced"]):
            speed = "⚡⚡⚡"
            cost = "💰💰💰"
            quality = "⭐⭐⭐⭐⭐"
            best_for = "Complex analysis, long documents"
        # Turbo models - fast but capable
        elif "turbo" in model_lower:
            speed = "⚡⚡⚡⚡"
            cost = "💰💰💰"
            quality = "⭐⭐⭐⭐"
            best_for = "Fast, capable, good balance"
        
        # Reasoning models - override other settings
        if any(x in model_lower for x in ["reason", "o1", "o3", "think", "r1"]):
            speed = "⚡"
            cost = "💰💰💰💰"
            quality = "⭐⭐⭐⭐⭐"
            best_for = "Complex reasoning, math, coding"
        
        # Sonnet - balanced models
        if "sonnet" in model_lower:
            speed = "⚡⚡⚡⚡"
            cost = "💰💰"
            quality = "⭐⭐⭐⭐⭐"
            best_for = "Great all-rounder, writing"
        
        # GPT-4 class models
        if "gpt-4" in model_lower or "4o" in model_lower:
            if "mini" not in model_lower:
                speed = "⚡⚡⚡"
                cost = "💰💰💰"
                quality = "⭐⭐⭐⭐⭐"
                best_for = "Complex analysis, nuanced writing"
        
        # GPT-3.5 class
        if "gpt-3.5" in model_lower or "3.5" in model_lower:
            speed = "⚡⚡⚡⚡⚡"
            cost = "💰"
            quality = "⭐⭐"
            best_for = "Basic tasks, budget-friendly"
        
        # Gemini models - often have free tier
        if "gemini" in model_lower:
            cost = "Free tier!"
        
        # Preview/experimental - modify best_for only
        if any(x in model_lower for x in ["preview", "beta", "exp", "experimental", "latest"]):
            best_for = "Testing new features"
        
        # Dated versions (e.g., 2024-05-13) - indicate it's a snapshot
        import re
        if re.search(r'\d{4}[-_]?\d{2}[-_]?\d{2}', model_lower):
            if best_for == "General AI tasks":
                best_for = "Stable version snapshot"
        
        # Detect vision capability based on model patterns
        vision = False
        # Explicit vision in name
        if "vision" in model_lower:
            vision = True
            best_for = "Image analysis, visual tasks"
        # OpenAI: gpt-4o, gpt-4-turbo have vision (but not gpt-3.5, o1)
        elif "gpt-4o" in model_lower or "4o" in model_lower:
            vision = True
        elif "gpt-4-turbo" in model_lower or "gpt-4.1" in model_lower:
            vision = True
        # All Gemini models have vision
        elif "gemini" in model_lower:
            vision = True
        # All Claude 3+ models have vision
        elif "claude-3" in model_lower or "claude-sonnet-4" in model_lower or "claude-opus-4" in model_lower:
            vision = True
        
        return {
            "name": friendly_name,
            "speed": speed,
            "cost": cost,
            "quality": quality,
            "best_for": best_for,
            "recommended": False,
            "auto_generated": True,
            "vision": vision
        }
    
    def _show_model_guide(self):
        """Show a guide to help users choose the right model for their needs"""
        provider = self.provider_var.get()
        
        # Load model info from JSON file
        model_info = self._load_model_info()
        
        # Get provider info and current models
        provider_data = model_info.get(provider, {"_description": "Select a model from the dropdown.", "models": {}})
        known_models = provider_data.get("models", {})
        current_models = self.models.get(provider, [])
        
        # Filter out placeholder entries like "(Start Ollama server first)"
        current_models = [m for m in current_models if not m.startswith("(")]
        
        # Create the guide window
        guide_window = tk.Toplevel(self.root)
        guide_window.title(f"Model Guide - {provider}")
        guide_window.geometry("1100x620")
        guide_window.transient(self.root)
        self.style_dialog(guide_window)
        
        # Header
        ttk.Label(
            guide_window,
            text=f"Choosing a Model: {provider}",
            font=('Arial', 12, 'bold')
        ).pack(pady=(15, 5))
        
        # Description
        description = provider_data.get("_description", "Select a model from the dropdown.")
        ttk.Label(
            guide_window,
            text=description,
            font=('Arial', 10),
            wraplength=1060
        ).pack(pady=(0, 15), padx=20)
        
        # Initialize variables for row selection (needed for checkbox later)
        row_frames = {}
        selected_model_var = tk.StringVar(value="")
        selected_bg = "#d0e8ff"  # Light blue for selection
        has_model_table = False  # Track if we're showing a model table
        
        # Check if this is Ollama (no table)
        if provider_data.get("_no_table") or provider == "Ollama (Local)":
            ttk.Label(
                guide_window,
                text="See System Check in Settings for local model recommendations.",
                font=('Arial', 10, 'italic')
            ).pack(pady=20)
        elif not current_models:
            # No models available
            ttk.Label(
                guide_window,
                text="No models currently available.\n\nClick 'Refresh Models' in Settings to fetch the latest models,\nor enter an API key for this provider.",
                font=('Arial', 10),
                justify=tk.CENTER
            ).pack(pady=40)
        else:
            # Build model list - only include current models
            models_to_display = []
            models_needing_generation = []
            
            for model_id in current_models:
                if model_id in known_models:
                    models_to_display.append((model_id, known_models[model_id]))
                else:
                    # Mark for potential generation
                    models_needing_generation.append(model_id)
                    # Use placeholder for now
                    models_to_display.append((model_id, {
                        "name": model_id,
                        "speed": "⚡⚡⚡",
                        "cost": "💰💰",
                        "quality": "⭐⭐⭐",
                        "best_for": "(Generating info...)",
                        "recommended": False,
                        "auto_generated": True
                    }))
            
            # Create table container with cream background
            table_container = tk.Frame(guide_window, bg=self.input_bg_color, bd=1, relief=tk.SUNKEN)
            table_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)
            
            # Column widths as character counts - generous sizing
            col_widths = [44, 7, 12, 7, 32]
            
            # Headers row
            header_frame = tk.Frame(table_container, bg=self.input_bg_color)
            header_frame.pack(fill=tk.X, padx=5, pady=(5, 0))
            
            headers = ["Model", "Speed", "Cost", "Quality", "Best For"]
            for i, (text, width) in enumerate(zip(headers, col_widths)):
                lbl = tk.Label(header_frame, text=text, font=('Arial', 10, 'bold'), 
                              width=width, anchor='w', bg=self.input_bg_color)
                lbl.grid(row=0, column=i, sticky='w', padx=(0, 3))
            
            # Separator line
            sep_frame = tk.Frame(table_container, bg='#cccccc', height=1)
            sep_frame.pack(fill=tk.X, padx=5, pady=3)
            
            # Model rows in a canvas for scrolling
            canvas = tk.Canvas(table_container, bg=self.input_bg_color, highlightthickness=0, height=170)
            scrollbar = ttk.Scrollbar(table_container, orient="vertical", command=canvas.yview)
            scrollable_frame = tk.Frame(canvas, bg=self.input_bg_color)
            
            scrollable_frame.bind(
                "<Configure>",
                lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
            )
            
            canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
            canvas.configure(yscrollcommand=scrollbar.set)
            
            # Store row widgets for potential update
            row_widgets = {}
            has_model_table = True  # We're showing a model table
            
            # Colors for selection
            normal_bg = self.input_bg_color
            
            def on_row_click(model_id, frame, labels):
                """Handle row click - highlight selected row"""
                # Clear previous selection
                prev_selected = selected_model_var.get()
                if prev_selected and prev_selected in row_frames:
                    prev_frame, prev_labels = row_frames[prev_selected]
                    prev_frame.config(bg=normal_bg)
                    for lbl in prev_labels:
                        lbl.config(bg=normal_bg)
                
                # Highlight new selection
                selected_model_var.set(model_id)
                frame.config(bg=selected_bg)
                for lbl in labels:
                    lbl.config(bg=selected_bg)
            
            # Add model rows
            for model_id, info in models_to_display:
                row_frame = tk.Frame(scrollable_frame, bg=self.input_bg_color)
                row_frame.pack(fill=tk.X, pady=2, padx=5)
                
                # Highlight recommended and vision capability
                name_text = info.get('name', model_id)
                if info.get('vision'):
                    name_text = name_text + " 👁️"
                if info.get('recommended'):
                    name_text = "⭐ " + name_text
                
                # Create labels with cream background and consistent font
                labels = []
                labels.append(tk.Label(row_frame, text=name_text, font=('Arial', 10), width=col_widths[0], 
                        anchor='w', bg=self.input_bg_color))
                labels.append(tk.Label(row_frame, text=info.get('speed', '⚡⚡⚡'), font=('Arial', 10), width=col_widths[1], 
                        anchor='w', bg=self.input_bg_color))
                labels.append(tk.Label(row_frame, text=info.get('cost', '💰💰'), font=('Arial', 10), width=col_widths[2], 
                        anchor='w', bg=self.input_bg_color))
                labels.append(tk.Label(row_frame, text=info.get('quality', '⭐⭐⭐'), font=('Arial', 10), width=col_widths[3], 
                        anchor='w', bg=self.input_bg_color))
                labels.append(tk.Label(row_frame, text=info.get('best_for', ''), font=('Arial', 10), width=col_widths[4], 
                        anchor='w', bg=self.input_bg_color))
                
                for i, lbl in enumerate(labels):
                    lbl.grid(row=0, column=i, sticky='w', padx=(0, 3))
                
                # Bind click handlers for selection
                row_frame.bind('<Button-1>', lambda e, m=model_id, f=row_frame, l=labels: on_row_click(m, f, l))
                for lbl in labels:
                    lbl.bind('<Button-1>', lambda e, m=model_id, f=row_frame, l=labels: on_row_click(m, f, l))
                
                row_widgets[model_id] = labels
                row_frames[model_id] = (row_frame, labels)
            
            canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0), pady=(0, 5))
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=(0, 5))
            
            # Generate descriptions for unknown models in background
            if models_needing_generation:
                def generate_in_background():
                    model_info_updated = False
                    for model_id in models_needing_generation:
                        try:
                            info = self._generate_model_description(model_id, provider)
                            
                            # Update the display if window still exists
                            if model_id in row_widgets:
                                try:
                                    if guide_window.winfo_exists():
                                        labels = row_widgets[model_id]
                                        guide_window.after(0, lambda l=labels, i=info: self._update_model_row(l, i))
                                except tk.TclError:
                                    pass  # Window was closed
                            
                            # Cache in model_info
                            if provider not in model_info:
                                model_info[provider] = {"_description": "AI provider.", "models": {}}
                            if "models" not in model_info[provider]:
                                model_info[provider]["models"] = {}
                            model_info[provider]["models"][model_id] = info
                            model_info_updated = True
                        except Exception as e:
                            print(f"Error generating info for {model_id}: {e}")
                    
                    # Save updated model info
                    if model_info_updated:
                        self._save_model_info(model_info)
                
                thread = threading.Thread(target=generate_in_background, daemon=True)
                thread.start()
        
        # Legend
        legend_frame = ttk.Frame(guide_window)
        legend_frame.pack(fill=tk.X, padx=20, pady=(10, 5))
        
        ttk.Label(
            legend_frame,
            text="⭐ = Recommended  |  👁️ = Vision  |  ⚡ = Speed  |  💰 = Relative Cost  |  ⭐ = Quality",
            font=('Arial', 9),
            foreground='gray'
        ).pack()
        
        # Vision explanation
        ttk.Label(
            legend_frame,
            text="👁️ Vision models can analyze images, extract handwritten/scanned text, and understand charts and diagrams.",
            font=('Arial', 9, 'italic'),
            foreground='gray'
        ).pack(pady=(2, 0))
        
        # AI Costs note
        ttk.Label(
            guide_window,
            text="For detailed pricing information, click the '💰 AI Costs' button on the main screen.",
            font=('Arial', 9, 'italic'),
            foreground='gray'
        ).pack(pady=(0, 5))
        
        # API key note
        ttk.Label(
            guide_window,
            text="To see the latest models, enter an API key and click 'Refresh Models' in Settings.",
            font=('Arial', 9, 'italic'),
            foreground='gray'
        ).pack(pady=(0, 5))
        
        # Free options note
        ttk.Label(
            guide_window,
            text="There are no costs if you run prompts 'Via Web' or 'Via Local AI'.",
            font=('Arial', 9, 'italic'),
            foreground='gray'
        ).pack(pady=(0, 10))
        
        # Default model checkbox and selection (only for providers with model tables)
        if has_model_table:
            default_model_var = tk.BooleanVar(value=self.config.get("default_to_recommended_model", False))
            
            # Get current default for this provider (if any)
            provider_defaults = self.config.get("provider_default_models", {})
            current_default = provider_defaults.get(provider, "")
            
            # If there's a saved default, highlight it
            if current_default and current_default in row_frames:
                frame, labels = row_frames[current_default]
                selected_model_var.set(current_default)
                frame.config(bg=selected_bg)
                for lbl in labels:
                    lbl.config(bg=selected_bg)
            
            def on_default_changed():
                self.config["default_to_recommended_model"] = default_model_var.get()
                
                if default_model_var.get():
                    # Save the selected model as default for this provider
                    selected = selected_model_var.get()
                    if "provider_default_models" not in self.config:
                        self.config["provider_default_models"] = {}
                    
                    if selected:
                        self.config["provider_default_models"][provider] = selected
                    else:
                        # No selection - clear any provider-specific default (will use recommended)
                        self.config["provider_default_models"].pop(provider, None)
                    
                    # Apply immediately
                    self._select_default_or_recommended_model()
                else:
                    # Unchecked - clear provider default
                    if "provider_default_models" in self.config:
                        self.config["provider_default_models"].pop(provider, None)
                
                self.save_config()
            
            # Checkbox frame
            checkbox_frame = ttk.Frame(guide_window)
            checkbox_frame.pack(pady=(5, 0))
            
            default_cb = ttk.Checkbutton(
                checkbox_frame,
                text="Set as default model when switching to this provider",
                variable=default_model_var,
                command=on_default_changed
            )
            default_cb.pack()
            
            # Advisory text
            ttk.Label(
                guide_window,
                text="Click a model to select it. If none selected, the ⭐ recommended model will be used.",
                font=('Arial', 8, 'italic'),
                foreground='gray'
            ).pack(pady=(2, 10))
        
        # Close button
        ttk.Button(
            guide_window,
            text="Close",
            command=guide_window.destroy
        ).pack(pady=(5, 15))
    
    def _update_model_row(self, labels, info):
        """Update a model row with new information"""
        try:
            name_text = info.get('name', '')
            if info.get('vision'):
                name_text = name_text + " 👁️"
            if info.get('recommended'):
                name_text = "⭐ " + name_text
            
            labels[0].config(text=name_text)
            labels[1].config(text=info.get('speed', '⚡⚡⚡'))
            labels[2].config(text=info.get('cost', '💰💰'))
            labels[3].config(text=info.get('quality', '⭐⭐⭐'))
            labels[4].config(text=info.get('best_for', ''))
        except Exception:
            pass  # Widget may have been destroyed
    
    def _select_recommended_model(self):
        """Select the recommended model for the current provider"""
        provider = self.provider_var.get()
        
        # Load model info
        model_info = self._load_model_info()
        provider_data = model_info.get(provider, {})
        known_models = provider_data.get("models", {})
        
        # Find recommended model
        recommended_model = None
        for model_id, info in known_models.items():
            if info.get("recommended"):
                recommended_model = model_id
                break
        
        if recommended_model:
            # Check if it's in the current model list
            current_models = self.models.get(provider, [])
            if recommended_model in current_models:
                self.model_var.set(recommended_model)
                self.config["model"] = recommended_model
                self.save_config()
    
    def _select_default_or_recommended_model(self):
        """Select the user's default model if set, otherwise the recommended model"""
        provider = self.provider_var.get()
        current_models = self.models.get(provider, [])
        
        # First check for user-defined default for this provider
        provider_defaults = self.config.get("provider_default_models", {})
        user_default = provider_defaults.get(provider, "")
        
        if user_default and user_default in current_models:
            self.model_var.set(user_default)
            self.config["model"] = user_default
            self.save_config()
            return
        
        # Fall back to recommended model
        self._select_recommended_model()

    def save_api_key(self):
        provider = self.provider_var.get()
        self.config["keys"][provider] = self.api_key_var.get().strip()
        save_config(self.config)

    def browse_audio_file(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("Audio/Video Files", "*.mp3 *.wav *.m4a *.ogg *.flac *.aac *.wma *.opus *.mp4 *.avi *.mov")])
        if file_path:
            self.audio_path_var.set(file_path)

    def transcribe_audio(self):
        # Safety: Force reset processing flag if stuck
        if self.processing:
            if not hasattr(self, 'processing_thread') or self.processing_thread is None or not self.processing_thread.is_alive():
                print("⚠️ Warning: processing flag was stuck, resetting...")
                self.processing = False
            
        if self.processing:
            messagebox.showwarning("Warning", "Processing already in progress. Please wait or cancel.")
            return

        self.clear_preview_for_new_document()
        audio_path = self.audio_path_var.get()
        if not audio_path:
            messagebox.showerror("Error", "Please select an audio file.")
            return
        if not os.path.exists(audio_path):
            messagebox.showerror("Error", f"File not found: {audio_path}")
            return
        self.processing = True
        self.process_btn.config(state=tk.DISABLED)
        self._transcription_start_time = time.time()  # Record start time for elapsed display
        self.set_status("Transcribing audio...")
        self.processing_thread = threading.Thread(target=self._transcribe_audio_thread)
        self.processing_thread.start()
        self.root.after(100, self.check_processing_thread)

    def _handle_audio_segments(self, segments_batch):
        """
        Handle progressive segment updates during transcription.
        
        🆕 FIXED: Now respects timestamp_interval setting during progressive display!

        Args:
            segments_batch: List of segment dicts with 'start', 'text' keys
        """
        # Get timestamp interval setting
        timestamp_interval = self.config.get("timestamp_interval", "every_segment")
        
        # Parse interval into seconds
        interval_seconds = {
            "every_segment": 0,
            "1min": 60,
            "5min": 300,
            "10min": 600,
            "never": float('inf')
        }.get(timestamp_interval, 0)
        
        # Initialize last timestamp tracker if not exists
        if not hasattr(self, '_last_progressive_timestamp'):
            self._last_progressive_timestamp = -interval_seconds
        
        # Append each segment to preview
        for segment in segments_batch:
            text = segment.get('text', '').strip()
            if not text:
                continue
            
            # Check if we should show timestamp for this segment
            current_time = segment.get('start', 0)
            show_timestamp = (
                timestamp_interval == "every_segment" or 
                (current_time - self._last_progressive_timestamp) >= interval_seconds
            )
            
            if show_timestamp and 'start' in segment:
                # Format timestamp
                from utils import format_timestamp
                timestamp_str = format_timestamp(segment['start'])
                line = f"[{timestamp_str}] {text}\n\n"
                self._last_progressive_timestamp = current_time
            else:
                # No timestamp for this segment
                line = f"{text}\n\n"
            
            # Insert at end of main preview
            

        
        # Auto-scroll main preview
        

        
        # Build up entries progressively
        if not hasattr(self, '_temp_entries'):
            self._temp_entries = []
        self._temp_entries.extend(segments_batch)

    def _segment_callback_wrapper(self, segments_batch):
        """
        Thread-safe wrapper for segment callback.

        🆕 NEW METHOD: Ensures UI updates happen on main thread.
        """
        self.root.after(0, self._handle_audio_segments, segments_batch)

    def _transcribe_audio_thread(self):
        """Modified transcription thread with progressive segment display"""
        audio_path = self.audio_path_var.get()
        engine = self.transcription_engine_var.get()

        # Get language - leave as None for auto-detection
        lang = self.transcription_lang_var.get().strip()

        options = {
            'language': lang if lang else None,  # None enables auto-detection
            'speaker_diarization': self.diarization_var.get(),
            'enable_vad': self.config.get("enable_vad", True),
            'assemblyai_api_key': self.config.get("keys", {}).get("AssemblyAI", "")
        }

        # Add faster-whisper specific options
        if engine == "faster_whisper":
            options['model_size'] = self.config.get("faster_whisper_model", "base")
            options['device'] = self.config.get("faster_whisper_device", "cpu")

        # Get the appropriate API key for the selected engine
        if engine == "openai_whisper":
            api_key = self.config.get("keys", {}).get("OpenAI", "")
        elif engine == "assemblyai":
            api_key = self.config.get("keys", {}).get("AssemblyAI", "")
        else:
            api_key = None  # Local engines don't need API key
        bypass_cache = self.bypass_cache_var.get()

        # 🆕 NEW: Clear preview and initialize temp entries
        self.root.after(0, lambda: setattr(self, '_temp_entries', []))

        # 🆕 NEW: Call transcribe_audio_file with segment_callback
        success, result, title = get_audio().transcribe_audio_file(
            filepath=audio_path,
            engine=engine,
            api_key=api_key,
            options=options,
            bypass_cache=bypass_cache,
            progress_callback=self.set_status,
            segment_callback=self._segment_callback_wrapper  # 🆕 NEW: Progressive display!
        )

        self.root.after(0, self._handle_audio_result, success, result, title)

    def _handle_audio_result(self, success, result, title):
        """Handle transcription completion"""
        self.processing = False
        self.process_btn.config(state=tk.NORMAL)

        if success:
            # Use the progressively built entries if available
            # 🆕 NEW: Check if we have temp entries from progressive display
            if hasattr(self, '_temp_entries') and self._temp_entries:
                self.current_entries = self._temp_entries
                delattr(self, '_temp_entries')  # Clean up temp storage
            else:
                # Fallback: use result (for cached transcriptions)
                self.current_entries = result
                # Display all at once for cached results
                self.current_document_text = entries_to_text_with_speakers(self.current_entries,
                                                                           timestamp_interval=self.config.get(
                                                                               "timestamp_interval", "every_segment"))

            self.current_document_source = self.audio_path_var.get()
            self.current_document_type = "audio_transcription"

            doc_id = add_document_to_library(
                doc_type="audio_transcription",
                source=self.current_document_source,
                title=title,
                entries=self.current_entries,
                document_class="source",
                metadata={"engine": self.transcription_engine_var.get()}
            )

            # ✅ FIX: Save old thread BEFORE changing document ID
            if self.thread_message_count > 0 and self.current_document_id:
                print(f"💾 Saving old thread ({self.thread_message_count} messages) to document {self.current_document_id}")
                self.save_current_thread()
            
            # ✅ FIX: Clear thread WITHOUT saving (we already saved above)
            self.current_thread = []
            self.thread_message_count = 0
            self.update_thread_status()
            
            # ✅ NOW change the document ID
            self.current_document_id = doc_id
            
            # ✅ Load saved thread for NEW document (if it has one)
            self.load_saved_thread()
            # Get document class and metadata from library
            doc = get_document_by_id(doc_id)
            if doc:
                self.current_document_class = doc.get("document_class", "source")
                self.current_document_metadata = doc.get("metadata", {})
                # CRITICAL FIX: Add title to metadata if not already there
                if 'title' not in self.current_document_metadata and 'title' in doc:
                    self.current_document_metadata['title'] = doc['title']
            else:
                self.current_document_class = "source"
                self.current_document_metadata = {}

            # 🆕 NEW: Create document text from current entries (already displayed)
            self.current_document_text = entries_to_text_with_speakers(self.current_entries,
                                                                       timestamp_interval=self.config.get(
                                                                           "timestamp_interval", "every_segment"))
            
            # DEBUG: Verify document text was created
            print(f"🔍 DEBUG Audio: current_document_text length = {len(self.current_document_text) if self.current_document_text else 0}")
            print(f"🔍 DEBUG Audio: current_document_id = {self.current_document_id}")
            print(f"🔍 DEBUG Audio: current_entries count = {len(self.current_entries) if self.current_entries else 0}")

            # Calculate elapsed time
            elapsed_time = ""
            if hasattr(self, '_transcription_start_time'):
                elapsed_seconds = time.time() - self._transcription_start_time
                if elapsed_seconds >= 60:
                    minutes = int(elapsed_seconds // 60)
                    seconds = int(elapsed_seconds % 60)
                    elapsed_time = f" in {minutes}m {seconds}s"
                else:
                    elapsed_time = f" in {elapsed_seconds:.1f}s"
                delattr(self, '_transcription_start_time')  # Clean up
            
            self.set_status(f"✅ Transcription complete{elapsed_time}: {title} ({len(self.current_entries)} segments)",
                            include_thread_status=True)
            self.refresh_library()
            
            # Update button states (View Source, etc.)
            # Enable Run button highlight for newly loaded document
            self._run_highlight_enabled = True
            self.update_button_states()
        else:
            self.set_status(f"❌ Error: {result}")
            messagebox.showerror("Error", result)

    # =========================================================================
    # SUBSTACK FETCHING
    # =========================================================================
    
    def fetch_facebook(self, url: str):
        """
        Fetch and transcribe a Facebook video/reel.
        Facebook videos don't have transcripts, so we extract audio and transcribe.
        """
        if self.processing:
            messagebox.showwarning("Warning", "Processing already in progress. Please wait or cancel.")
            return
        
        self.processing = True
        self.process_btn.config(state=tk.DISABLED)
        self.set_status("Fetching Facebook video...")
        self.update_preview("Loading Facebook video...")
        
        def worker():
            try:
                # Get API keys from config
                openai_key = self.api_key_var.get() if hasattr(self, 'api_key_var') else None
                assemblyai_key = self.assemblyai_key_var.get() if hasattr(self, 'assemblyai_key_var') else None
                provider = self.transcription_provider_var.get() if hasattr(self, 'transcription_provider_var') else 'openai'
                
                success, result, title, content_type = fetch_facebook_content(
                    url,
                    openai_api_key=openai_key,
                    assemblyai_api_key=assemblyai_key,
                    transcription_provider=provider,
                    status_callback=lambda msg: self.root.after(0, self.set_status, msg)
                )
                
                self.root.after(0, self._handle_facebook_result, success, result, title, url)
                
            except Exception as e:
                import traceback
                error_msg = f"Facebook fetch error: {str(e)}\n{traceback.format_exc()}"
                print(error_msg)
                self.root.after(0, self._handle_facebook_error, str(e))
        
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
    
    def _handle_facebook_result(self, success: bool, result, title: str, url: str):
        """Handle successful Facebook transcription."""
        self.processing = False
        self.process_btn.config(state=tk.NORMAL)
        
        if not success:
            self._handle_facebook_error(result)
            return
        
        # Extract text from result dict
        text = result.get('text', '') if isinstance(result, dict) else str(result)
        
        self.current_document_text = text
        self.current_document_title = title or "Facebook Video"
        self.current_document_url = url
        self.current_document_type = 'facebook'
        
        # Update preview
        preview = text[:2000] + "..." if len(text) > 2000 else text
        self.update_preview(preview)
        self.set_status("✅ Document loaded - Select prompt and click Run")
        
        # Update button states
        # Enable Run button highlight for newly loaded document
        self._run_highlight_enabled = True
        self.update_button_states()
        
        # Show context buttons (reuse YouTube buttons for video content)
        self.update_context_buttons('youtube')
    
    def _handle_facebook_error(self, error_msg: str):
        """Handle Facebook fetch error."""
        self.processing = False
        self.process_btn.config(state=tk.NORMAL)
        self.update_preview("")
        self.set_status(f"Error: {error_msg}")
        messagebox.showerror("Facebook Error", f"Failed to fetch Facebook video:\n\n{error_msg}")

    def _handle_substack_result(self, success: bool, result, title: str, content_type: str, url: str):
        """
        Handle the result of Substack content fetch.
        Uses the same pattern as _handle_youtube_result for consistency.
        """
        try:
            self.processing = False
            self.process_btn.config(state=tk.NORMAL)

            if success:
                print(f"✅ Substack fetch successful - processing {len(result)} entries")
                
                # YouTube pattern: result IS the entries list
                self.current_entries = result
                self.current_document_source = url
                self.current_document_type = content_type
                self.current_document_class = "source"
                
                # Debug: Check what we got
                print(f"📊 Entries type: {type(result)}")
                print(f"📊 Entries length: {len(result)}")
                if len(result) > 0:
                    print(f"📊 First entry: {result[0]}")
                    print(f"📊 First entry type: {type(result[0])}")
                
                # Build metadata
                doc_metadata = {
                    "source": "substack",
                    "title": title,
                    "content_type": content_type,
                    "platform": "substack",
                    "fetched": datetime.datetime.now().isoformat()
                }
                
                # Save to library (same as YouTube)
                from document_library import add_document_to_library
                print(f"📚 Adding to library...")
                doc_id = add_document_to_library(
                    doc_type=content_type,
                    source=url,
                    title=title,
                    entries=self.current_entries,
                    document_class="source",
                    metadata=doc_metadata
                )
                print(f"✅ Saved with doc_id={doc_id}")
                
                # Handle thread switching (same as YouTube)
                if self.thread_message_count > 0 and self.current_document_id:
                    self.save_current_thread()
                
                self.current_thread = []
                self.thread_message_count = 0
                self.update_thread_status()
                self.current_document_id = doc_id
                self.load_saved_thread()
                
                # Get document from library
                from document_library import get_document_by_id
                doc = get_document_by_id(doc_id)
                if doc:
                    self.current_document_metadata = doc.get("metadata", {})
                    if 'title' not in self.current_document_metadata:
                        self.current_document_metadata['title'] = title
                else:
                    self.current_document_metadata = {}
                
                # Convert entries to text
                from utils import entries_to_text
                self.current_document_text = entries_to_text(
                    self.current_entries,
                    timestamp_interval=self.config.get("timestamp_interval", "every_segment")
                )
                
                # Validate the text is actually a string
                if not isinstance(self.current_document_text, str):
                    print(f"⚠️ WARNING: current_document_text is not a string, it's {type(self.current_document_text)}")
                    self.current_document_text = str(self.current_document_text)
                
                print(f"📝 Text length: {len(self.current_document_text)} chars")
                print(f"📝 First 100 chars: {repr(self.current_document_text[:100])}")
                
                # Update UI
                self.set_status("✅ Document loaded - Select prompt and click Run")
                self.refresh_library()
                
                # Update button states
                # Enable Run button highlight for newly loaded document
                self._run_highlight_enabled = True
                self.update_button_states()
                
                # Only show Audio Actions if content is audio/video type
                if content_type in ['substack_video', 'substack_podcast', 'substack_audio']:
                    self.update_context_buttons('audio')
                else:
                    # Text article - use web context (hides special action buttons)
                    self.update_context_buttons('web')
                
                print(f"✅ Substack document loaded successfully!")
                
            else:
                print(f"❌ Substack fetch failed: {result}")
                self.set_status(f"❌ Substack error: {result}")
                messagebox.showerror("Substack Error", f"Could not fetch Substack content:\n\n{result}")
                
        except Exception as e:
            import traceback
            print(f"❌ EXCEPTION in _handle_substack_result:")
            traceback.print_exc()
            self.set_status(f"❌ Error: {str(e)}")
            messagebox.showerror("Error", f"Failed to process Substack result: {str(e)}")

    def _download_and_transcribe_substack(self, url: str, media_info: dict, title: str, content_type: str):
        """
        Download Substack media and transcribe it.
        Called after user confirms they want transcription.
        """
        self.processing = True
        self.process_btn.config(state=tk.DISABLED)
        self.set_status(f"Downloading media: {title}...")

        def download_worker():
            try:
                from substack_utils import download_substack_media

                success, result = download_substack_media(
                    url,
                    media_info,
                    status_callback=lambda msg: self.root.after(0, lambda m=msg: self.set_status(m))
                )

                if success:
                    # result is the audio file path - now transcribe it
                    self.root.after(0, lambda: self.set_status(f"Transcribing: {title}..."))
                    self.root.after(0,
                                    lambda: self._transcribe_substack_audio(result, title, url, content_type, None))
                else:
                    self.root.after(0, lambda: self.set_status(f"❌ Download failed: {result}"))
                    self.root.after(0, lambda: messagebox.showerror("Download Failed",
                                                                    f"Could not download media:\n\n{result}"))
                    self.root.after(0, lambda: setattr(self, 'processing', False))
                    self.root.after(0, lambda: self.process_btn.config(state=tk.NORMAL))

            except Exception as e:
                import traceback
                error_msg = f"Error downloading Substack media: {str(e)}\n{traceback.format_exc()}"
                print(error_msg)
                self.root.after(0, lambda: self.set_status(f"❌ Error: {str(e)}"))
                self.root.after(0, lambda: messagebox.showerror("Error", f"Download error: {str(e)}"))
                self.root.after(0, lambda: setattr(self, 'processing', False))
                self.root.after(0, lambda: self.process_btn.config(state=tk.NORMAL))

        # Run download in separate thread
        import threading
        download_thread = threading.Thread(target=download_worker)
        download_thread.start()
    
    def _transcribe_substack_audio(self, audio_path: str, title: str, url: str, content_type: str, article_text: str = None):
        """
        Transcribe downloaded Substack audio using the configured transcription provider.
        
        Args:
            audio_path: Path to the audio file to transcribe
            title: Title of the Substack post
            url: Original URL of the post
            content_type: Type of content (substack_video, substack_podcast, etc.)
            article_text: Optional accompanying article text from the post
        """
        # Enable cancel button during transcription
        self.processing = True
        
        def worker():
            try:
                # Get transcription settings from config
                provider = self.config.get("transcription_provider", "faster_whisper")
                model_size = self.config.get("local_whisper_model", "base")
                language = self.config.get("transcription_language", "en")
                enable_vad = self.config.get("enable_vad", True)
                
                self.root.after(0, self.set_status, f"Transcribing with {provider}...")
                
                # Use the main transcribe_audio_file function
                from audio_handler import transcribe_audio_file
                
                options = {
                    'language': language,
                    'enable_vad': enable_vad,
                    'model_size': model_size
                }
                
                # Map provider names to engine names
                engine_map = {
                    'openai_whisper': 'whisper',
                    'faster_whisper': 'faster_whisper',
                    'local_whisper': 'faster_whisper',
                    'whisper': 'whisper'
                }
                engine = engine_map.get(provider, 'faster_whisper')
                
                def progress_update(msg):
                    self.root.after(0, self.set_status, msg)
                
                # Create segment callback for progressive display
                def substack_segment_callback(segments_batch):
                    """Display transcribed segments progressively for Substack audio."""
                    self.root.after(0, self._segment_callback_wrapper, segments_batch)
                
                success, result, _ = transcribe_audio_file(
                    filepath=audio_path,
                    engine=engine,
                    api_key=self._get_transcription_api_key(engine),
                    options=options,
                    bypass_cache=False,
                    progress_callback=progress_update,
                    segment_callback=substack_segment_callback  # Enable progressive display
                )
                
                if success:
                    # Result is already a list of entries/segments
                    if isinstance(result, list):
                        entries = result
                    elif isinstance(result, str):
                        entries = [{'text': result, 'start': 0, 'location': 'Transcription'}]
                    else:
                        entries = [{'text': str(result), 'start': 0, 'location': 'Transcription'}]
                    
                    # Prepend article text if present (for mixed content posts)
                    if article_text and len(article_text) > 100:
                        article_entry = {
                            'text': article_text,
                            'start': 0,
                            'location': 'Article Text'
                        }
                        entries = [article_entry] + entries
                        print(f"Combined article text ({len(article_text)} chars) with transcription ({len(entries)-1} segments)")
                    
                    # Use existing handler (same signature as other Substack paths)
                    self.root.after(0, self._handle_substack_result, True, entries, title, content_type, url)
                else:
                    self.root.after(0, self._handle_transcription_error, str(result))
                    
            except Exception as e:
                import traceback
                error_msg = f"Transcription error: {str(e)}"
                print(f"{error_msg}\n{traceback.format_exc()}")
                self.root.after(0, self._handle_transcription_error, error_msg)
            finally:
                # Clean up temp audio file
                try:
                    import os
                    if audio_path and os.path.exists(audio_path):
                        os.remove(audio_path)
                        # Also try to remove parent temp dir
                        parent_dir = os.path.dirname(audio_path)
                        if parent_dir and 'substack_' in parent_dir:
                            import shutil
                            shutil.rmtree(parent_dir, ignore_errors=True)
                except:
                    pass
        
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
    
    def _handle_transcription_error(self, error_msg: str):
        """Handle transcription failure."""
        self.processing = False
        self.process_btn.config(state=tk.NORMAL)
        self.set_status(f"❌ Transcription failed: {error_msg}")
        messagebox.showerror("Transcription Error", f"Could not transcribe audio:\n\n{error_msg}")
    

    def fetch_youtube(self):
        print("=" * 60)
        print("📺 fetch_youtube() called")
        
        self.update_context_buttons('youtube')
        print("   Context buttons updated")
        
        # Safety: Force reset processing flag if stuck
        if self.processing:
            if not hasattr(self, 'processing_thread') or self.processing_thread is None or not self.processing_thread.is_alive():
                print("⚠️ Warning: processing flag was stuck, resetting...")
                self.processing = False
        
        if self.processing:
            print("❌ Already processing - showing warning and returning")
            messagebox.showwarning("Warning", "Processing already in progress. Please wait or cancel.")
            return

        url_or_id = self.yt_url_var.get().strip()
        print(f"   URL from yt_url_var: '{url_or_id}'")

        # Validate input
        is_valid, error_msg = self.validate_youtube_url(url_or_id)
        print(f"   Validation result: valid={is_valid}, error='{error_msg}'")
        
        if not is_valid:
            print(f"❌ Validation failed: {error_msg}")
            messagebox.showerror("Invalid Input", error_msg)
            return

        print("✅ Starting YouTube fetch thread...")
        self.processing = True
        self.process_btn.config(state=tk.DISABLED)
        self.set_status("Fetching YouTube transcript...")
        self.processing_thread = threading.Thread(target=self._fetch_youtube_thread)
        self.processing_thread.start()
        self.root.after(100, self.check_processing_thread)
        print("   Thread started successfully")
        print("=" * 60)

    def _get_transcription_api_key(self, engine=None):
        """Get the correct API key for the selected transcription engine.
        
        The AI Provider key (e.g. DeepSeek) is NOT the same as the transcription
        engine key (e.g. AssemblyAI). This helper routes the correct key.
        """
        if engine is None:
            engine = self.transcription_engine_var.get()
        
        if engine == "assemblyai":
            return self.config.get("keys", {}).get("AssemblyAI", "")
        elif engine in ("openai_whisper", "whisper"):
            return self.config.get("keys", {}).get("OpenAI (ChatGPT)", self.api_key_var.get())
        else:
            # Local engines (faster_whisper, local_whisper) don't need an API key
            return self.api_key_var.get()

    def _fetch_youtube_thread(self):
        url_or_id = self.yt_url_var.get().strip()
        if self.yt_fallback_var.get():
            selected_engine = self.transcription_engine_var.get()
            
            success, result, title, source_type, yt_metadata = fetch_youtube_with_audio_fallback(
                url_or_id,
                api_key=self._get_transcription_api_key(selected_engine),
                engine=selected_engine,
                options={
                    'language': self.transcription_lang_var.get().strip() or None,  # None for auto-detect
                    'speaker_diarization': self.diarization_var.get(),
                    'enable_vad': self.config.get("enable_vad", True),  # Pass VAD setting
                    'assemblyai_api_key': self.config.get("keys", {}).get("AssemblyAI", ""),  # Always pass AssemblyAI key in options
                },
                bypass_cache=self.bypass_cache_var.get() if hasattr(self, 'bypass_cache_var') else False,
                progress_callback=self.set_status
            )
        else:
            success, result, title, source_type, yt_metadata = fetch_youtube_transcript(url_or_id)
        self.root.after(0, self._handle_youtube_result, success, result, title, source_type, yt_metadata)

    def _handle_youtube_result(self, success, result, title, source_type, yt_metadata=None):
        try:
            self.processing = False
            self.process_btn.config(state=tk.NORMAL)

            if success:
                logging.debug("YouTube result handler: success=True, processing entries...")
                self.current_entries = result
                self.current_document_source = self.yt_url_var.get().strip()
                self.current_document_type = source_type

                # ===== UPDATED: Auto-save source document to library =====
                try:
                    # Get the URL from input field
                    url = self.yt_url_var.get().strip() if hasattr(self, 'yt_url_var') else ""

                    # Build metadata including published_date if available
                    doc_metadata = {
                        "source": "youtube",
                        "title": title,
                        "fetched": datetime.datetime.now().isoformat() + 'Z'
                    }
                    # Add published_date from YouTube if available
                    if yt_metadata and yt_metadata.get('published_date'):
                        doc_metadata['published_date'] = yt_metadata['published_date']

                    # SAVE TO LIBRARY (replaces old add_document_to_library call)
                    doc_id = self.doc_saver.save_source_document(
                        entries=result,
                        title=title,
                        doc_type=source_type,
                        source=url,
                        metadata=doc_metadata  # Use the full metadata with published_date
                    )

                    if not doc_id:
                        raise Exception("Failed to save document to library")

                    logging.debug(f"Document added with ID: {doc_id}")

                except Exception as e:
                    print(f"⚠️ Failed to auto-save YouTube document: {e}")
                    logging.error(f"Failed to auto-save YouTube document: {e}")
                    import traceback
                    traceback.print_exc()
                    # Set a temporary ID to continue
                    doc_id = "temp_" + str(hash(url))[:12]
                # ===== END AUTO-SAVE CODE =====

                # ✅ FIX: Save old thread BEFORE changing document ID
                if self.thread_message_count > 0 and self.current_document_id:
                    print(
                        f"💾 Saving old thread ({self.thread_message_count} messages) to document {self.current_document_id}")
                    self.save_current_thread()

                # ✅ FIX: Clear thread WITHOUT saving (we already saved above)
                self.current_thread = []
                self.thread_message_count = 0
                self.update_thread_status()

                # ✅ NOW change the document ID
                self.current_document_id = doc_id

                # ✅ Load saved thread for NEW document (if it has one)
                self.load_saved_thread()

                # Get document class and metadata from library
                logging.debug("Getting document from library...")
                doc = get_document_by_id(doc_id)
                if doc:
                    self.current_document_class = doc.get("document_class", "source")
                    self.current_document_metadata = doc.get("metadata", {})
                    # CRITICAL FIX: Add title to metadata if not already there
                    if 'title' not in self.current_document_metadata and 'title' in doc:
                        self.current_document_metadata['title'] = doc['title']
                else:
                    self.current_document_class = "source"
                    self.current_document_metadata = {}

                logging.debug("Converting entries to text...")
                self.current_document_text = (
                    entries_to_text_with_speakers(
                        self.current_entries,
                        timestamp_interval=self.config.get("timestamp_interval", "every_segment")
                    )
                    if source_type == "audio_transcription"
                    else entries_to_text(
                        self.current_entries,
                        timestamp_interval=self.config.get("timestamp_interval", "every_segment")
                    )
                )
                logging.debug(
                    f"Text converted, length: {len(self.current_document_text) if self.current_document_text else 0}")

                # Preview display removed - content stored in current_document_text

                self.set_status("✅ Document loaded - Select prompt and click Run")
                self.refresh_library()
                
                # Update button states
                # Enable Run button highlight for newly loaded document
                self._run_highlight_enabled = True
                self.update_button_states()
                
                logging.debug("YouTube result handler completed successfully")
            else:
                logging.debug(f"YouTube result handler: success=False, error={result}")
                self.set_status(f"❌ Error: {result}")
                messagebox.showerror("Error", result)
        except Exception as e:
            logging.error(f"EXCEPTION in _handle_youtube_result: {e}")
            logging.error(traceback.format_exc())
            self.set_status(f"❌ Error: {str(e)}")
            messagebox.showerror("Error", f"Failed to process YouTube result: {str(e)}")
    def fetch_substack(self):
        """Fetch transcript from Substack video post"""
        print("📰 fetch_substack() called")

        if not SUBSTACK_AVAILABLE:
            messagebox.showerror("Error", "Substack support not available. Install with: pip install beautifulsoup4")
            return

        # Get URL from Text widget (not StringVar which may be out of sync)
        url = self.universal_input_entry.get('1.0', 'end-1c').strip()
        
        # Handle multi-line input - take first line only
        if '\n' in url:
            url = url.split('\n')[0].strip()

        if not url:
            messagebox.showwarning("No URL", "Please enter a Substack URL")
            return
        
        # Verify it's actually a Substack URL
        if 'substack.com' not in url.lower():
            messagebox.showwarning("Invalid URL", "This doesn't appear to be a Substack URL")
            return

        # Clear previous content - clear text display directly
        if hasattr(self, 'text_display'):
            self.text_display.delete('1.0', tk.END)

        # Update status
        self.set_status("Fetching Substack content...")
        
        # Store URL for thread to use (can't safely access widgets from thread)
        self._substack_url = url

        # Start background thread
        self.processing_thread = threading.Thread(target=self._fetch_substack_thread)
        self.processing_thread.daemon = True
        self.processing_thread.start()

    def _fetch_substack_thread(self):
        """Background thread for fetching Substack content (text articles OR video transcripts)"""
        try:
            url = getattr(self, '_substack_url', '').strip()
            if not url:
                # Fallback to StringVar if stored URL not available
                url = self.universal_input_var.get().strip()
            print(f"🔍 Fetching Substack content from: {url}")

            # Step 1: Try to fetch video transcript first
            from substack_utils import fetch_substack_transcript
            video_success, video_result, video_title, source_type, metadata = fetch_substack_transcript(url)
            
            has_video = video_success and isinstance(video_result, list) and len(video_result) > 0
            
            # Step 2: Try to scrape article text
            article_text = None
            article_title = None
            try:
                import requests
                from bs4 import BeautifulSoup
                
                print(f"📄 Attempting to scrape article text...")
                response = requests.get(url, timeout=30)
                response.raise_for_status()
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Extract title
                title_elem = soup.find('h1', class_='post-title')
                if not title_elem:
                    title_elem = soup.find('h1')
                article_title = title_elem.get_text(strip=True) if title_elem else "Substack Article"
                
                # Extract article content
                article_div = soup.find('div', class_='available-content')
                if not article_div:
                    article_div = soup.find('div', class_='body')
                if not article_div:
                    article_div = soup.find('article')
                
                if article_div:
                    # Get all paragraphs
                    paragraphs = article_div.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
                    article_text = '\n\n'.join([p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)])
                    print(f"✅ Scraped article: {len(article_text)} chars")
                else:
                    print(f"⚠️ No article content found")
                    
            except Exception as e:
                print(f"⚠️ Could not scrape article text: {e}")
            
            has_text = bool(article_text and len(article_text) > 100)
            
            print(f"📊 Content found: video={has_video}, text={has_text}")
            
            # Step 3: Decide what to do based on what we found
            if has_video and has_text:
                # BOTH available - ask user
                print(f"🎯 Both video and text available - asking user")
                choice_data = {
                    'video_title': video_title,
                    'video_entries': video_result,
                    'text_title': article_title,
                    'text_content': article_text,
                    'url': url
                }
                self.root.after(0, self._ask_substack_content_choice_simple, choice_data)
                
            elif has_video:
                # Only video available
                print(f"🎥 Only video available - loading transcript")
                self.root.after(0, self._handle_substack_result, True, video_result, video_title, 'substack', url)
                
            elif has_text:
                # Only text available
                print(f"📄 Only text available - loading article")
                
                # Sanitize the text to remove any problematic characters
                import html
                import re
                
                # Decode HTML entities
                clean_text = html.unescape(article_text)
                
                # Remove lines that are just asterisks (markdown separator issue)
                lines = clean_text.split('\n')
                filtered_lines = []
                for line in lines:
                    # Remove lines that are ONLY asterisks/dashes/underscores (common separators)
                    stripped = line.strip()
                    if stripped and not re.match(r'^[\*\-_]+$', stripped):
                        filtered_lines.append(line)
                    elif not stripped:  # Keep blank lines
                        filtered_lines.append(line)
                    # else: skip the separator line
                
                clean_text = '\n'.join(filtered_lines)
                
                # Remove any null bytes or other control characters
                clean_text = ''.join(char for char in clean_text if char.isprintable() or char in '\n\t\r')
                
                entries = [{
                    'text': clean_text,
                    'start': 0,
                    'timestamp': '[Article]'
                }]
                self.root.after(0, self._handle_substack_result, True, entries, article_title, 'substack', url)
                
            else:
                # Nothing found
                error_msg = "No transcript or article text found on this Substack page"
                print(f"❌ {error_msg}")
                self.root.after(0, self._handle_substack_result, False, error_msg, "", "substack", url)

        except Exception as e:
            print(f"❌ Exception in Substack fetch thread: {e}")
            import traceback
            traceback.print_exc()
            error_msg = f"Exception: {str(e)}"
            self.root.after(0, self._handle_substack_result, False, error_msg, "", "substack", url)

    def _ask_substack_content_choice_simple(self, choice_data):
        """Ask user whether they want text article or video transcript when both are available"""
        from tkinter import messagebox
        
        # Build the message
        video_title = choice_data['video_title']
        video_entries = choice_data['video_entries']
        text_title = choice_data['text_title']
        text_content = choice_data['text_content']
        url = choice_data['url']
        
        message = (
            f"This Substack page contains both text and video:\n\n"
            f"📄 Text Article: ~{len(text_content):,} characters\n"
            f"🎥 Video Transcript: {len(video_entries)} segments\n\n"
            f"Which would you like to load?"
        )
        
        # Custom dialog with three buttons
        dialog = tk.Toplevel(self.root)
        dialog.title("Choose Content Type")
        dialog.geometry("450x200")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Center the dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
        
        # Message label
        msg_label = tk.Label(dialog, text=message, justify=tk.LEFT, padx=20, pady=20)
        msg_label.pack()
        
        choice = {'value': None}
        
        def choose_text():
            choice['value'] = 'text'
            dialog.destroy()
        
        def choose_video():
            choice['value'] = 'video'
            dialog.destroy()
        
        def choose_cancel():
            choice['value'] = None
            dialog.destroy()
        
        # Buttons frame
        btn_frame = tk.Frame(dialog)
        btn_frame.pack(pady=10)
        
        text_btn = tk.Button(btn_frame, text="📄 Text Article", command=choose_text, width=15)
        text_btn.pack(side=tk.LEFT, padx=5)
        
        video_btn = tk.Button(btn_frame, text="🎥 Video Transcript", command=choose_video, width=15)
        video_btn.pack(side=tk.LEFT, padx=5)
        
        cancel_btn = tk.Button(btn_frame, text="Cancel", command=choose_cancel, width=10)
        cancel_btn.pack(side=tk.LEFT, padx=5)
        
        # Wait for dialog to close
        self.root.wait_window(dialog)
        
        # Process the choice
        if choice['value'] == 'text':
            print(f"👤 User chose: Text article")
            
            # Sanitize the text to remove any problematic characters
            import html
            import re
            
            # Decode HTML entities
            clean_text = html.unescape(text_content)
            
            # Remove lines that are just asterisks/dashes/underscores (markdown separator issue)
            lines = clean_text.split('\n')
            filtered_lines = []
            for line in lines:
                stripped = line.strip()
                if stripped and not re.match(r'^[\*\-_]+$', stripped):
                    filtered_lines.append(line)
                elif not stripped:  # Keep blank lines
                    filtered_lines.append(line)
                # else: skip the separator line
            
            clean_text = '\n'.join(filtered_lines)
            
            # Remove control characters
            clean_text = ''.join(char for char in clean_text if char.isprintable() or char in '\n\t\r')
            
            entries = [{
                'text': clean_text,
                'start': 0,
                'timestamp': '[Article]'
            }]
            self._handle_substack_result(True, entries, text_title, 'substack', url)
            
        elif choice['value'] == 'video':
            print(f"👤 User chose: Video transcript")
            self._handle_substack_result(True, video_entries, video_title, 'substack', url)
            
        else:
            print(f"👤 User cancelled")
            self.processing = False
            self.process_btn.config(state=tk.NORMAL)
            self.set_status("Ready")

    def parse_transcript_to_entries(text: str) -> List[Dict]:
        """Parse transcript text with timestamps into entries format"""
        entries = []
        lines = text.split('\n')

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Match format like "[0:00] text" or "[12:34] text"
            import re
            match = re.match(r'\[(\d+:\d+)\]\s*(.+)', line)
            if match:
                timestamp, content = match.groups()
                entries.append({
                    "timestamp": timestamp,
                    "text": content
                })

        return entries

    def _display_substack_result(self, text, title, metadata):
        """Display Substack transcript in UI"""
        print(f"\n{'=' * 60}")
        print(f"🎨 _display_substack_result called!")
        print(f"   Title: {title}")
        print(f"   Text length: {len(text)} chars")
        print(f"   Metadata: {metadata}")
        print(f"{'=' * 60}\n")

        try:

            self.current_document_text = text
            self.current_document_source = metadata.get('url', '')
            self.current_document_id = metadata.get('post_slug', '')
            self.current_document_type = 'substack'
            print(f"✅ Stored text in document variables")

            # Update document library label
            author = metadata.get('author', 'Unknown')
            date = metadata.get('published_date', '')
            entry_count = metadata.get('entry_count', 0)

            doc_label = f"{title}\nAuthor: {author}\nEntries: {entry_count}"
            if date:
                doc_label += f"\nDate: {date}"

            self.doc_library_label.config(text=doc_label)
            print(f"✅ Updated doc library label")

            # Update status
            self.set_status("✅ Document loaded - Select prompt and click Run")
            print(f"✅ Updated status")

            # NOW parse and add to library (after display is done)
            print(f"🔍 Parsing entries for library...")
            try:
                parsed_entries = self.parse_transcript_to_entries(text)
                print(f"✅ Parsed {len(parsed_entries)} entries")
            except Exception as e:
                print(f"⚠️ Parse failed, using empty list: {e}")
                import traceback
                traceback.print_exc()
                parsed_entries = []

            # Add to library
            from document_library import add_document_to_library
            doc_id = add_document_to_library(
                doc_type='substack_transcript',
                source=metadata.get('url', ''),
                title=title,
                entries=parsed_entries,
                document_class='source',
                metadata=metadata
            )
            self.current_document_id = doc_id
            print(f"✅ Added to library with ID: {doc_id}")

            # Refresh library to show in Documents Library
            self.refresh_library()
            print(f"✅ Refreshed library")
            self.update_button_states()
            print(f"✅ Updated button states")

            print(f"\n{'=' * 60}")
            print(f"✅ Substack transcript displayed successfully!")
            print(f"{'=' * 60}\n")

        except Exception as e:
            print(f"\n{'=' * 60}")
            print(f"❌ ERROR in _display_substack_result:")
            print(f"   {str(e)}")
            import traceback
            traceback.print_exc()
            print(f"{'=' * 60}\n")

    def browse_file(self):
        file_path = filedialog.askopenfilename(filetypes=[
            ("All supported files", "*.txt *.doc *.docx *.pdf *.rtf *.xlsx *.xls *.csv *.mp3 *.wav *.m4a *.ogg *.flac *.aac *.wma *.opus *.mp4 *.avi *.mov"),
            ("Text files", "*.txt"),
            ("Word documents", "*.doc *.docx"),
            ("PDF files", "*.pdf"),
            ("RTF files", "*.rtf"),
            ("Spreadsheet files", "*.xlsx *.xls *.csv"),
            ("Audio/Video files", "*.mp3 *.wav *.m4a *.ogg *.flac *.aac *.wma *.opus *.mp4 *.avi *.mov")
        ])
        if file_path:
            self.file_path_var.set(file_path)

    # -------------------------
    # Dictation (Speech-to-Text)
    # -------------------------
    
    def start_dictation(self):
        """Open the dictation dialog to record and transcribe speech."""
        # Show loading status (first import can take a moment)
        self.set_status("🎙️ Loading dictation module...")
        self.root.update()  # Force UI refresh
        
        # Check if transcription module is available
        try:
            from transcription_handler import (
                check_microphone_available,
                check_transcription_availability,
                RECORDING_AVAILABLE
            )
        except ImportError as e:
            self.set_status("")
            messagebox.showerror(
                "Module Not Found",
                f"Transcription module not available:\n{e}\n\n"
                f"Please ensure transcription_handler.py is present."
            )
            return
        
        # Check microphone
        self.set_status("🎙️ Checking microphone...")
        self.root.update()
        
        mic_ok, mic_msg = check_microphone_available()
        if not mic_ok:
            self.set_status("")
            # Show installation instructions
            availability = check_transcription_availability()
            if not availability['recording']['available']:
                messagebox.showerror(
                    "Recording Not Available",
                    f"Microphone recording requires additional libraries.\n\n"
                    f"Install with:\n"
                    f"pip install sounddevice soundfile\n\n"
                    f"Error: {availability['recording']['error']}"
                )
            else:
                messagebox.showerror("Microphone Error", mic_msg)
            return
        
        # Clear status and open dialog
        self.set_status("")
        
        # Open dictation dialog
        from dictation_dialog import DictationDialog
        DictationDialog(self.root, self)

    def open_multi_image_ocr(self):
        """Open the multi-image OCR dialog to process multiple images as one document."""
        # Check OCR availability first
        try:
            available, error_msg, _ = get_ocr().check_ocr_availability()
            if not available:
                # Check if it's just a Poppler issue - cloud mode might still work
                if "POPPLER" in error_msg:
                    if messagebox.askyesno(
                        "Local OCR Unavailable",
                        f"Local OCR tools not fully configured (Poppler missing).\n\n"
                        f"You can still use Cloud AI OCR if you have an API key configured.\n\n"
                        f"Continue with Cloud AI mode?"
                    ):
                        pass  # Continue to open dialog
                    else:
                        return
                elif "TESSERACT" in error_msg:
                    messagebox.showerror(
                        "OCR Not Available",
                        f"Tesseract OCR is not installed.\n\n"
                        f"Please install Tesseract or use Settings to configure\n"
                        f"Cloud AI direct mode for OCR."
                    )
                    return
        except Exception as e:
            # If check fails, let the dialog handle it
            pass
        
        # Open the multi-image OCR dialog
        try:
            from ocr_dialog import MultiImageOCRDialog
            MultiImageOCRDialog(self.root, self)
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            messagebox.showerror(
                "Dialog Error",
                f"Failed to open Multi-Page OCR dialog:\n\n{str(e)}\n\n"
                f"Check the console for details."
            )
            print(f"Multi-Page OCR dialog error:\n{error_details}")

    def _handle_multi_image_ocr_result(self, entries: list, source_files: list):
        """
        Handle the result of multi-image OCR.
        Creates a document entry from the combined OCR text.
        
        NOTE: This may be called from a background thread, so all tkinter 
        operations must be scheduled on the main thread via root.after().
        
        Args:
            entries: List of entry dicts with 'start', 'text', 'location' keys
            source_files: List of original image file paths
        """
        if not entries:
            self.root.after(0, lambda: messagebox.showwarning("No Text", "No text could be extracted from the images."))
            return
        
        # Generate title from first file or timestamp
        import datetime
        if source_files:
            first_file = os.path.basename(source_files[0])
            base_name = os.path.splitext(first_file)[0]
            num_pages = len(source_files)
            title = f"{base_name} ({num_pages} pages)"
        else:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            title = f"Multi-page OCR - {timestamp}"
        
        metadata = {
            "ocr_language": self.config.get("ocr_language", "eng"),
            "ocr_quality": self.config.get("ocr_quality", "balanced"),
            "source_files": [os.path.basename(f) for f in source_files],
            "num_pages": len(source_files)
        }
        
        # Add to library (file I/O - safe from thread)
        total_chars = sum(len(e.get('text', '')) for e in entries)
        print(f"📚 Adding to library: '{title}' ({total_chars:,} chars)")
        doc_id = add_document_to_library(
            doc_type="ocr",
            source=title,
            title=title,
            entries=entries,
            document_class="source",
            metadata=metadata
        )
        
        # Schedule all UI updates on the main thread
        def update_ui():
            failed_step = "unknown"
            try:
                # Step 1: Set current document attributes
                failed_step = "set document attributes"
                self.current_entries = entries
                self.current_document_type = "ocr"
                self.current_document_class = "source"
                self.current_document_source = title
                self.current_document_metadata = metadata
                
                # Step 2: Save current thread if needed
                failed_step = "save_current_thread"
                if self.thread_message_count > 0 and self.current_document_id:
                    self.save_current_thread()
                self.current_thread = []
                self.thread_message_count = 0
                self.current_document_id = doc_id
                
                # Step 3: Update thread status
                failed_step = "update_thread_status"
                self.update_thread_status()
                
                # Step 4: Load saved thread
                failed_step = "load_saved_thread"
                self.load_saved_thread()
                
                # Step 5: Convert entries to text
                failed_step = "entries_to_text"
                self.current_document_text = entries_to_text(
                    self.current_entries, 
                    timestamp_interval=self.config.get("timestamp_interval", "every_segment")
                )
                
                # Step 6: Update context buttons
                failed_step = "update_context_buttons"
                self.update_context_buttons('ocr')
                
                # Step 7: Refresh library
                failed_step = "refresh_library"
                self.refresh_library()
                
                # Step 8: Set status
                failed_step = "set_status"
                self.set_status(f"✅ Multi-page OCR complete: {title}")
                
                # Step 9: Update button states
                failed_step = "update_button_states"
                self.update_button_states()
                
                # Step 10: Show success dialog
                failed_step = "show success dialog"
                messagebox.showinfo(
                    "OCR Complete",
                    f"Successfully processed {len(source_files)} page(s).\n\n"
                    f"Extracted {len(entries)} text segments.\n\n"
                    f"The document has been saved to your library."
                )
            except Exception as e:
                import traceback
                tb_str = traceback.format_exc()
                try:
                    print(f"❌ UI update error at step '{failed_step}': {e}")
                    print(tb_str)
                except Exception:
                    pass
                messagebox.showerror("Error", 
                    f"Document saved to library but UI update failed at step:\n"
                    f"'{failed_step}'\n\n"
                    f"Error: {str(e)}\n\n"
                    f"Traceback (last 400 chars):\n{tb_str[-400:]}")
        
        self.root.after(0, update_ui)

    def _handle_dictation_result(self, text: str, metadata: dict):
        """
        Handle the result of dictation.
        Creates a document entry from the transcribed text.
        """
        if not text or not text.strip():
            messagebox.showwarning("Empty Recording", "No speech was detected in the recording.")
            return
        
        # Create entries from the text
        paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
        if not paragraphs:
            paragraphs = [text.strip()]
        
        entries = []
        for para in paragraphs:
            entries.append({
                'start': 0,
                'text': para,
                'location': f"Dictation ({metadata.get('method', 'unknown')})"
            })
        
        # Set as current document - mark as editable so user can fix transcription errors
        self.current_entries = entries
        self.current_document_type = "dictation"
        self.current_document_class = "product"  # Makes it editable
        self.current_document_metadata = {"editable": True, "method": metadata.get('method', 'unknown')}
        
        # Generate title with timestamp
        import datetime
        timestamp = datetime.datetime.now().strftime("%d %b %Y, %I:%M%p").replace("AM", "am").replace("PM", "pm")
        title = f"Dictation - {timestamp}"
        self.current_document_source = title
        
        # Add to library as editable product
        doc_id = add_document_to_library(
            doc_type="dictation",
            source=title,
            title=title,
            entries=entries,
            document_class="product",  # Editable
            metadata={"editable": True, "method": metadata.get('method', 'unknown')}
        )
        
        # Clear thread (but don't update status yet)
        if self.thread_message_count > 0 and self.current_document_id:
            self.save_current_thread()
        self.current_thread = []
        self.thread_message_count = 0
        self.current_document_id = doc_id
        
        # Display in preview - combine entries into text
        combined_text = "\n\n".join([e['text'] for e in entries])
        self.current_document_text = combined_text  # Store for View Source button
        self.update_context_buttons('dictation')
        
        # Show success dialog
        method = metadata.get('method', 'unknown')
        duration = metadata.get('duration', 0)
        
        messagebox.showinfo(
            "Dictation Complete",
            f"Successfully transcribed {len(entries)} paragraph(s).\n\n"
            f"Method: {method}\n"
            f"Duration: {duration:.1f} seconds\n\n"
            f"The text has been saved to Documents Library and is ready for analysis."
        )
        
        # Update button states
        self.update_button_states()
        
        # Set status AFTER dialog closes - use after() to ensure it's not overwritten
        self.root.after(100, lambda: self.set_status(f"✅ Dictation saved to Documents Library ({duration:.1f}s, {method})"))

    # -------------------------
    # Video Platform Content Fetching (Vimeo, Rumble, etc.)
    # -------------------------
    
    def fetch_video_platform(self, url: str):
        """
        Fetch and transcribe video from supported platforms (Vimeo, Rumble, etc.)
        
        Args:
            url: Video URL from supported platform
        """
        from video_platform_utils import get_platform_name
        
        platform_name = get_platform_name(url)
        print("=" * 60)
        print(f"🎬 fetch_video_platform() called")
        print(f"   Platform: {platform_name}")
        print(f"   URL: {url}")
        
        self.update_context_buttons('video_platform')
        
        # Safety: Force reset processing flag if stuck
        if self.processing:
            if not hasattr(self, 'processing_thread') or self.processing_thread is None or not self.processing_thread.is_alive():
                print("⚠️ Warning: processing flag was stuck, resetting...")
                self.processing = False
        
        if self.processing:
            print("❌ Already processing - showing warning and returning")
            messagebox.showwarning("Warning", "Processing already in progress. Please wait or cancel.")
            return
        
        print("✅ Starting video platform fetch thread...")
        self.processing = True
        self.process_btn.config(state=tk.DISABLED)
        self.set_status(f"Fetching from {platform_name}...")
        
        # Store URL for thread to access
        self.video_platform_url = url
        
        self.processing_thread = threading.Thread(target=self._fetch_video_platform_thread)
        self.processing_thread.start()
        self.root.after(100, self.check_processing_thread)
        print("   Thread started successfully")
        print("=" * 60)
    
    def _fetch_video_platform_thread(self):
        """Background thread for video platform fetching"""
        url = self.video_platform_url
        
        from video_platform_utils import fetch_video_platform_content
        
        # Get transcription options
        options = {
            'language': self.transcription_lang_var.get().strip() or None,
            'speaker_diarization': self.diarization_var.get(),
            'enable_vad': self.config.get("enable_vad", True)
        }
        
        # Fetch and transcribe
        success, result, title, source_type, metadata = fetch_video_platform_content(
            url,
            api_key=self._get_transcription_api_key(),
            engine=self.transcription_engine_var.get(),
            options=options,
            status_callback=self.set_status,
            bypass_cache=self.bypass_cache_var.get() if hasattr(self, 'bypass_cache_var') else False
        )
        
        self.root.after(0, self._handle_video_platform_result, success, result, title, source_type, metadata)
    
    def _handle_video_platform_result(self, success, result, title, source_type, metadata):
        """Handle the result from video platform fetch"""
        try:
            self.processing = False
            self.process_btn.config(state=tk.NORMAL)
            
            if success:
                # result is the transcript entries
                logging.debug("Video platform result handler: success=True")
                self.current_entries = result
                self.current_document_source = self.video_platform_url
                self.current_document_type = source_type
                
                # Build metadata
                doc_metadata = {
                    "source": "video_platform",
                    "platform": metadata.get('platform', 'Unknown'),
                    "title": title,
                    "fetched": datetime.datetime.now().isoformat() + 'Z'
                }
                
                logging.debug("Adding document to library...")
                doc_id = add_document_to_library(
                    doc_type=source_type,
                    source=self.current_document_source,
                    title=title,
                    entries=self.current_entries,
                    document_class="source",
                    metadata=doc_metadata
                )
                logging.debug(f"Document added with ID: {doc_id}")
                
                # Save old thread before changing document
                if self.thread_message_count > 0 and self.current_document_id:
                    self.save_current_thread()
                
                # Clear thread
                self.current_thread = []
                self.thread_message_count = 0
                self.update_thread_status()
                
                # Set new document ID
                self.current_document_id = doc_id
                self.load_saved_thread()
                
                # Get document info
                doc = get_document_by_id(doc_id)
                if doc:
                    self.current_document_class = doc.get("document_class", "source")
                    self.current_document_metadata = doc.get("metadata", {})
                    if 'title' not in self.current_document_metadata and 'title' in doc:
                        self.current_document_metadata['title'] = doc['title']
                else:
                    self.current_document_class = "source"
                    self.current_document_metadata = {}
                
                logging.debug("Converting entries to text...")
                self.current_document_text = entries_to_text(self.current_entries)
                logging.debug(f"Text converted, length: {len(self.current_document_text) if self.current_document_text else 0}")
                
                    
                platform_name = metadata.get('platform', 'Video Platform')
                self.set_status("✅ Document loaded - Select prompt and click Run")
                self.refresh_library()
                
                # Update button states
                self.update_button_states()
                
                logging.debug("Video platform result handler completed successfully")
            else:
                # result is an error message
                logging.debug(f"Video platform result handler: success=False")
                
                # Get platform name for error message
                from video_platform_utils import get_platform_name
                platform_name = get_platform_name(self.video_platform_url)
                
                # Show detailed error with manual download option
                error_title = f"{platform_name} Download Failed"
                error_message = result
                
                # Add helpful context
                full_error = f"{error_message}\n\n"
                
                # Check if this looks like a restriction error
                if any(keyword in result.lower() for keyword in ['private', 'password', '403', 'forbidden', 'restricted', 'disabled']):
                    full_error += "💡 TIP: Try the manual download method:\n\n"
                    full_error += "1. Download the video manually from your browser\n"
                    full_error += "2. Drag & drop the video file into DocAnalyser\n"
                    full_error += "3. Automatic transcription will begin\n\n"
                    full_error += "Need help? Check the platform's website for download options."
                
                self.set_status(f"❌ {platform_name} download failed")
                messagebox.showerror(error_title, full_error)
                
        except Exception as e:
            logging.error(f"EXCEPTION in _handle_video_platform_result: {e}")
            logging.error(traceback.format_exc())
            self.set_status(f"❌ Error: {str(e)}")
            messagebox.showerror("Error", f"Failed to process video: {str(e)}")

    # -------------------------
    # Twitter/X Content Fetching
    # -------------------------
    
    def fetch_twitter(self, url: str):
        """
        Fetch content from a Twitter/X post.
        
        Args:
            url: Twitter/X post URL
        """
        if self.processing:
            messagebox.showwarning("Warning", "Processing already in progress. Please wait or cancel.")
            return
        
        self.processing = True
        self.process_btn.config(state=tk.DISABLED)
        self.set_status("🐦 Fetching X/Twitter content...")
        
        # Run in thread to keep UI responsive
        self.processing_thread = threading.Thread(
            target=self._fetch_twitter_thread,
            args=(url,)
        )
        self.processing_thread.start()
        self.root.after(100, self.check_processing_thread)
    
    def _fetch_twitter_thread(self, url: str):
        """Background thread for fetching Twitter content."""
        try:
            success, result, title = fetch_twitter_content(
                url,
                progress_callback=self.set_status
            )
            self.root.after(0, self._handle_twitter_result, success, result, title, url)
        except Exception as e:
            self.root.after(0, self._handle_twitter_result, False, str(e), "", url)
    
    def _handle_twitter_result(self, success: bool, result, title: str, url: str):
        """Handle the result of Twitter content fetch."""
        self.processing = False
        self.process_btn.config(state=tk.NORMAL)
        
        if success:
            # Check if result is the new dict format (with video detection)
            if isinstance(result, dict):
                has_video = result.get('has_video', False)
                text_content = result.get('formatted_text', result.get('text', ''))
                
                # If video is available, ask user what they want
                if has_video and text_content:
                    self._show_twitter_content_choice(result, title, url)
                    return
                elif has_video and not text_content:
                    # Video only - go straight to transcription
                    self._download_and_transcribe_twitter(url, title)
                    return
                else:
                    # Text only - use formatted text
                    result = text_content
            
            # Text-only path (or legacy string result)
            self._load_twitter_text(result, title, url)
        else:
            # Show error with helpful message and paste option
            self.set_status("❌ Failed to fetch X/Twitter content")
            self._show_paste_fallback_dialog(
                url=url,
                source_type="twitter",
                source_name="X/Twitter"
            )
    
    def _show_twitter_content_choice(self, result: dict, title: str, url: str):
        """Ask user whether they want text content or video transcript."""
        text_content = result.get('formatted_text', result.get('text', ''))
        video_duration = result.get('video_duration', 0)
        
        # Format duration string
        if video_duration:
            mins = int(video_duration) // 60
            secs = int(video_duration) % 60
            duration_str = f"{mins}:{secs:02d}"
        else:
            duration_str = "unknown length"
        
        message = (
            f"This X post contains both text and video:\n\n"
            f"📄 Text Content: ~{len(text_content):,} characters\n"
            f"🎥 Video: {duration_str}\n\n"
            f"Which would you like to load?"
        )
        
        # Custom dialog with buttons
        dialog = tk.Toplevel(self.root)
        dialog.title("Choose Content Type")
        dialog.geometry("450x220")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Center the dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
        
        # Message label
        msg_label = tk.Label(dialog, text=message, justify=tk.LEFT, padx=20, pady=20)
        msg_label.pack()
        
        choice = {'value': None}
        
        def choose_text():
            choice['value'] = 'text'
            dialog.destroy()
        
        def choose_video():
            choice['value'] = 'video'
            dialog.destroy()
        
        def choose_cancel():
            choice['value'] = None
            dialog.destroy()
        
        # Buttons frame
        btn_frame = tk.Frame(dialog)
        btn_frame.pack(pady=10)
        
        text_btn = tk.Button(btn_frame, text="📄 Text Content", command=choose_text, width=15)
        text_btn.pack(side=tk.LEFT, padx=5)
        
        video_btn = tk.Button(btn_frame, text="🎥 Video Transcript", command=choose_video, width=15)
        video_btn.pack(side=tk.LEFT, padx=5)
        
        cancel_btn = tk.Button(btn_frame, text="Cancel", command=choose_cancel, width=10)
        cancel_btn.pack(side=tk.LEFT, padx=5)
        
        # Wait for dialog to close
        self.root.wait_window(dialog)
        
        # Process the choice
        if choice['value'] == 'text':
            print(f"👤 User chose: Text content")
            self._load_twitter_text(text_content, title, url)
            
        elif choice['value'] == 'video':
            print(f"👤 User chose: Video transcript")
            self._download_and_transcribe_twitter(url, title)
            
        else:
            print(f"👤 User cancelled")
            self.set_status("Cancelled")
    
    def _load_twitter_text(self, text_content: str, title: str, url: str):
        """Load Twitter text content as a document."""
        # Create entries from the content
        entries = [{
            'start': 0,
            'text': text_content,
            'location': 'X Post'
        }]
        
        # Set as current document
        self.current_entries = entries
        self.current_document_source = url
        self.current_document_type = "twitter"
        self.current_document_class = "source"
        self.current_document_metadata = {
            "source": "twitter",
            "url": url,
            "fetched": datetime.datetime.now().isoformat() + 'Z'
        }
        
        # Add to library
        total_chars = sum(len(e.get('text', '')) for e in entries)
        print(f"📚 Adding to library: '{title}' ({total_chars:,} chars)")
        doc_id = add_document_to_library(
            doc_type="twitter",
            source=url,
            title=title if title else f"X Post",
            entries=entries,
            document_class="source",
            metadata=self.current_document_metadata
        )
        
        # Clear thread (save first if needed)
        if self.thread_message_count > 0 and self.current_document_id:
            self.save_current_thread()
        self.current_thread = []
        self.thread_message_count = 0
        self.current_document_id = doc_id
        self.update_thread_status()
        
        # Load any saved thread for this document
        self.load_saved_thread()
        
        self.current_document_text = text_content
        self.update_context_buttons('web')  # Use web context buttons
        
        # Refresh library and show success
        self.refresh_library()
        self.set_status("✅ Document loaded - Select prompt and click Run")
        
        # Update button states
        self.update_button_states()
    
    def _download_and_transcribe_twitter(self, url: str, title: str):
        """Download Twitter video and transcribe it."""
        self.processing = True
        self.process_btn.config(state=tk.DISABLED)
        self.set_status("🎥 Downloading X/Twitter video...")
        
        # Run download in thread
        self.processing_thread = threading.Thread(
            target=self._twitter_video_download_thread,
            args=(url, title)
        )
        self.processing_thread.start()
        self.root.after(100, self.check_processing_thread)
    
    def _twitter_video_download_thread(self, url: str, title: str):
        """Background thread for downloading Twitter video."""
        try:
            from twitter_utils import download_twitter_video
            success, result, video_title = download_twitter_video(
                url,
                progress_callback=self.set_status
            )
            
            if success:
                # result is the file path - transcribe it
                self.root.after(0, self._transcribe_twitter_video, result, video_title or title, url)
            else:
                self.root.after(0, self._handle_twitter_video_error, result, url)
                
        except Exception as e:
            self.root.after(0, self._handle_twitter_video_error, str(e), url)
    
    def _transcribe_twitter_video(self, file_path: str, title: str, url: str):
        """Transcribe the downloaded Twitter video."""
        self.set_status("🎤 Transcribing video audio...")
        
        # Store metadata for after transcription
        self._twitter_video_metadata = {
            'original_url': url,
            'title': title
        }
        
        # Set the audio path variable (this is what transcribe_audio() reads)
        self.audio_path_var.set(file_path)
        
        # Also update the universal input for visual feedback
        self.universal_input_entry.delete('1.0', 'end')
        self.universal_input_entry.insert('1.0', file_path)
        self.universal_input_entry.config(foreground='black')
        self.placeholder_active = False
        
        # Reset processing flag so transcribe_audio can start
        self.processing = False
        
        # Trigger transcription
        self.transcribe_audio()
    
    def _handle_twitter_video_error(self, error: str, url: str):
        """Handle Twitter video download/transcription error."""
        self.processing = False
        self.process_btn.config(state=tk.NORMAL)
        self.set_status("❌ Failed to download X/Twitter video")
        
        messagebox.showerror(
            "Video Download Failed",
            f"Could not download video from X/Twitter:\n\n{error}\n\n"
            f"You can try:\n"
            f"• Download the video manually and load it into DocAnalyser\n"
            f"• Use the text content instead"
        )
    
    def _show_paste_fallback_dialog(self, url: str, source_type: str = "web", source_name: str = None):
        """
        Show a dialog offering to paste content manually when automated fetching fails.
        
        This is a general-purpose fallback for any blocked or inaccessible web content
        (Twitter/X, Substack, paywalled articles, etc.)
        
        Args:
            url: The URL that failed to fetch
            source_type: Type identifier for the source (e.g., "twitter", "substack", "web")
            source_name: Human-readable name for the source (e.g., "X/Twitter", "Substack")
        """
        if source_name is None:
            # Try to extract domain name for display
            try:
                from urllib.parse import urlparse
                domain = urlparse(url).netloc.replace('www.', '')
                source_name = domain
            except:
                source_name = "this website"
        
        # Create a custom dialog with options
        dialog = tk.Toplevel(self.root)
        dialog.title("Content Fetch Failed")
        dialog.geometry("480x300")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Center on parent
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 480) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 300) // 2
        dialog.geometry(f"+{x}+{y}")
        
        main_frame = ttk.Frame(dialog, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Warning icon and title
        title_frame = ttk.Frame(main_frame)
        title_frame.pack(fill=tk.X, pady=(0, 15))
        
        ttk.Label(title_frame, text="⚠️", font=('Arial', 24)).pack(side=tk.LEFT)
        ttk.Label(title_frame, text="Could not fetch content automatically", 
                  font=('Arial', 11, 'bold')).pack(side=tk.LEFT, padx=(10, 0))
        
        # Explanation
        explanation = (
            f"The content from {source_name} could not be retrieved automatically. "
            f"This may be due to access restrictions, paywalls, or blocking of automated requests.\n\n"
            f"You can manually copy the content from your browser and paste it here "
            f"to add it to your Documents Library for analysis."
        )
        ttk.Label(main_frame, text=explanation, wraplength=430, 
                  font=('Arial', 10)).pack(anchor=tk.W, pady=(0, 15))
        
        # URL display
        url_frame = ttk.Frame(main_frame)
        url_frame.pack(fill=tk.X, pady=(0, 20))
        ttk.Label(url_frame, text="URL:", font=('Arial', 9, 'bold')).pack(side=tk.LEFT)
        url_display = url[:55] + "..." if len(url) > 55 else url
        ttk.Label(url_frame, text=url_display, font=('Arial', 9), 
                  foreground='#0066CC').pack(side=tk.LEFT, padx=(5, 0))
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        def on_paste_manually():
            dialog.destroy()
            # Open the paste content dialog
            from paste_content_dialog import PasteContentDialog
            PasteContentDialog(
                self.root, 
                self, 
                source_url=url,
                source_type=source_type,
                title="Paste Content Manually",
                prompt_text=(
                    f"Copy the content from {source_name} and paste it below.\n"
                    f"Tip: Select the text in your browser and use Ctrl+C to copy."
                )
            )
        
        def on_cancel():
            dialog.destroy()
        
        # Paste Manually button (primary action)
        paste_btn = ttk.Button(
            button_frame,
            text="📋 Paste Manually",
            command=on_paste_manually,
            width=18
        )
        paste_btn.pack(side=tk.LEFT)
        
        # Cancel button
        cancel_btn = ttk.Button(
            button_frame,
            text="Cancel",
            command=on_cancel,
            width=10
        )
        cancel_btn.pack(side=tk.RIGHT)
        
        # Handle window close
        dialog.protocol("WM_DELETE_WINDOW", on_cancel)

    def fetch_local_file(self):
        print("🔵 DEBUG: fetch_local_file() ENTRY")
        print(f"   processing={self.processing}")
        if self.processing:
            messagebox.showwarning("Warning", "Processing already in progress. Please wait or cancel.")
            return

        file_path = self.file_path_var.get()

        # Validate input
        is_valid, error_msg = self.validate_file_path(file_path)
        if not is_valid:
            messagebox.showerror("Invalid Input", error_msg)
            return

        self.processing = True
        self.process_btn.config(state=tk.DISABLED)
        self.set_status("Loading file...")
        print("🔵 DEBUG: Creating and starting thread...")
        self.processing_thread = threading.Thread(target=self._fetch_local_file_thread)
        self.processing_thread.start()
        print("🔵 DEBUG: Thread started!")
        self.root.after(100, self.check_processing_thread)

    def _fetch_local_file_thread(self):
        print("🟢 DEBUG: _fetch_local_file_thread() STARTED", flush=True)
        try:
            file_path = self.file_path_var.get()
            print(f"🟢 DEBUG: file_path='{file_path}'", flush=True)
            ext = os.path.splitext(file_path)[1].lower()
            # Show file size in status bar for user awareness
            try:
                file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
                if file_size_mb >= 1.0:
                    self.root.after(0, lambda: self.set_status(f"Loading {os.path.basename(file_path)} ({file_size_mb:.1f} MB)..."))
                else:
                    self.root.after(0, lambda: self.set_status(f"Loading {os.path.basename(file_path)}..."))
            except Exception:
                self.root.after(0, lambda: self.set_status(f"Loading {os.path.basename(file_path)}..."))

            # Check for spreadsheet files FIRST
            if ext in ('.xlsx', '.xls', '.csv'):
                print(f"📊 Spreadsheet file detected: {ext}")
                
                # Convert spreadsheet to text
                success, text_content, title, error_msg = self.convert_spreadsheet_to_text(file_path)
                
                if not success:
                    self.root.after(0, lambda: messagebox.showerror("Spreadsheet Error", error_msg))
                    self.root.after(0, lambda: setattr(self, 'processing', False))
                    self.root.after(0, lambda: self.process_btn.config(state=tk.NORMAL))
                    return
                
                # Update context buttons
                self.root.after(0, lambda: self.update_context_buttons('spreadsheet'))
                
                # Handle as regular text document
                self.root.after(0, self._handle_spreadsheet_result, text_content, title, file_path)
                return

            # Check for image files FIRST
            if ext in ('.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp', '.gif'):
                print(f"🖼️ Image file detected: {ext}")
                # Notify about image file
                self.root.after(0, lambda: self.update_context_buttons('image'))
                # Call document_fetcher which will return IMAGE_FILE code
                success, result, title, doc_type = get_doc_fetcher().fetch_local_file(file_path)
                self.root.after(0, self._handle_file_result, success, result, title)
                return

            if ext in ('.mp3', '.wav', '.m4a', '.ogg', '.flac', '.aac', '.wma', '.opus', '.mp4', '.avi', '.mov'):
                self.root.after(0, lambda: self.audio_path_var.set(file_path))
                self.root.after(0, lambda: self.update_context_buttons('audio'))
                self.root.after(0, self.transcribe_audio)
                return

            print(f"🟢 Checking if PDF is scanned...", flush=True)
            if ext == '.pdf':
                self.root.after(0, lambda: self.set_status("Checking PDF type..."))
                print(f"🟢 Calling get_ocr().is_pdf_scanned()...", flush=True)
                # Use timeout to prevent hanging on complex PDFs
                import concurrent.futures
                executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                try:
                    future = executor.submit(get_ocr().is_pdf_scanned, file_path)
                    is_scanned = future.result(timeout=15)  # 15 second timeout
                except concurrent.futures.TimeoutError:
                    print("🟠 WARNING: is_pdf_scanned timed out after 15s - treating as scanned", flush=True)
                    is_scanned = True  # Assume scanned if check hangs
                    future.cancel()
                except Exception as e:
                    print(f"🟠 WARNING: is_pdf_scanned error: {e}", flush=True)
                    is_scanned = False
                finally:
                    executor.shutdown(wait=False)
                print(f"🟢 is_pdf_scanned returned: {is_scanned}", flush=True)
            else:
                is_scanned = False
            if ext == '.pdf' and is_scanned:

                # 🆕 UPDATE: Notify context buttons about PDF detection
                # Must use root.after() since we're in a background thread
                self.root.after(0, lambda: self.update_context_buttons('pdf_scanned'))

                # 🆕 NEW: Check if cache exists BEFORE prompting user
                force_reprocess = self.force_reprocess_var.get()
                # Reset force_reprocess so it doesn't persist for future loads
                self.root.after(0, lambda: self.force_reprocess_var.set(False))

                # Check for cached OCR results (to offer as option, not to load silently)
                from ocr_handler import load_cached_ocr, get_ocr_cache_path
                cached = None
                ocr_quality = self.config.get("ocr_quality", "balanced")
                ocr_language = self.config.get("ocr_language", "eng")
                print(f"\n🔵 CACHE CHECK: file='{file_path}', quality='{ocr_quality}', language='{ocr_language}'", flush=True)
                cache_path = get_ocr_cache_path(file_path, ocr_quality, ocr_language)
                print(f"🔵 CACHE CHECK: expected cache file = '{cache_path}'", flush=True)
                print(f"🔵 CACHE CHECK: cache file exists = {os.path.exists(cache_path)}", flush=True)
                if not force_reprocess:
                    cached = get_ocr().load_cached_ocr(
                        file_path,
                        ocr_quality,
                        ocr_language
                    )
                    print(f"🔵 CACHE CHECK: load_cached_ocr returned {type(cached).__name__}, is None={cached is None}", flush=True)

                # Store cached data so the dialog can offer it as an option
                self._cached_ocr_data = cached

                if force_reprocess:
                    print("🔄 Force reprocess - skipping cache, will show OCR prompt")
                elif cached:
                    print("📦 Cache found - will offer choice: re-scan or use cached")
                else:
                    print("📭 No cache found - will show OCR prompt")

                # Always show OCR prompt (default to re-processing)
                success, result, title = False, "SCANNED_PDF", os.path.basename(file_path)
                self.root.after(0, self._handle_ocr_fetch, success, result, title)
                return

            print("🟣 DEBUG: Calling get_doc_fetcher().fetch_local_file()...")
            success, result, title, doc_type = get_doc_fetcher().fetch_local_file(file_path)
            print(f"🟣 DEBUG: Returned success={success}, title='{title}'")
            print("🟣 DEBUG: Scheduling _handle_file_result...")
            self.root.after(0, self._handle_file_result, success, result, title)
            print("🟣 DEBUG: Scheduled!")

            if ext in ('.txt', '.doc', '.docx', '.rtf'):
                # Must use root.after() since we're in a background thread
                self.root.after(0, lambda: self.update_context_buttons('document'))
                
        except Exception as e:
            import traceback
            import sys
            print("\n" + "🔴"*30, flush=True)
            print(f"🔴 EXCEPTION in _fetch_local_file_thread: {e}", flush=True)
            print("🔴"*30, flush=True)
            traceback.print_exc()
            sys.stdout.flush()
            error_msg = f"Error in _fetch_local_file_thread: {str(e)}\n{traceback.format_exc()}"
            print(error_msg, flush=True)
            self.root.after(0, lambda: messagebox.showerror("Error", f"File processing error: {str(e)}"))
            self.root.after(0, lambda: setattr(self, 'processing', False))

    def _load_cached_ocr_directly(self, cached_entries, title):
        """Load OCR results directly from cache without prompting user"""
        self.processing = False
        self.process_btn.config(state=tk.NORMAL)

        self.current_entries = cached_entries
        self.current_document_source = self.file_path_var.get()
        self.current_document_type = "ocr"

        # Add to document library
        doc_id = add_document_to_library(
            doc_type="ocr",
            source=self.current_document_source,
            title=title,
            entries=self.current_entries,
            document_class="source",
            metadata={
                "ocr_language": self.config.get("ocr_language", "eng"),
                "ocr_quality": self.config.get("ocr_quality", "balanced")
            }
        )
        # ✅ FIX: Save old thread BEFORE changing document ID
        if self.thread_message_count > 0 and self.current_document_id:
            self.save_current_thread()
        
        # Clear thread manually
        self.current_thread = []
        self.thread_message_count = 0
        self.update_thread_status()
        
        # NOW change the document ID
        self.current_document_id = doc_id

        # Get document class and metadata from library
        doc = get_document_by_id(doc_id)
        if doc:
            self.current_document_class = doc.get("document_class", "source")
            self.current_document_metadata = doc.get("metadata", {})
        else:
            self.current_document_class = "source"
            self.current_document_metadata = {}

        self.current_document_text = entries_to_text(self.current_entries,
                                                     timestamp_interval=self.config.get("timestamp_interval",
                                                                                        "every_segment"))

        self.set_status("✅ Source document loaded from cache")
        self.refresh_library()
        
        # Update button states
        self.update_button_states()

    def _handle_file_result(self, success, result, title):
        print("🟡 DEBUG: _handle_file_result() CALLED")
        print(f"   success={success}, title='{title}'")
        try:
            self.processing = False
            print("🟡 DEBUG: Set processing=False")
            self.process_btn.config(state=tk.NORMAL)
            if success:
                logging.debug(f"File result handler: success=True, title={title}")
                self.current_entries = result
                self.current_document_source = self.file_path_var.get()
                self.current_document_type = "file"
                
                logging.debug("Adding document to library...")
                doc_id = add_document_to_library(
                    doc_type="file",
                    source=self.current_document_source,
                    title=title,
                    entries=self.current_entries
                )
                logging.debug(f"Document added with ID: {doc_id}")
                
                # ✅ FIX: Save old thread BEFORE changing document ID
                if self.thread_message_count > 0 and self.current_document_id:
                    self.save_current_thread()
                
                # Clear thread manually
                self.current_thread = []
                self.thread_message_count = 0
                self.update_thread_status()
                
                # NOW change the document ID
                self.current_document_id = doc_id
                # 🆕 Load saved thread if exists
                self.load_saved_thread()
                
                # Get document class and metadata from library
                logging.debug("Getting document from library...")
                doc = get_document_by_id(doc_id)
                if doc:
                    self.current_document_class = doc.get("document_class", "source")
                    self.current_document_metadata = doc.get("metadata", {})
                    # CRITICAL FIX: Add title to metadata if not already there
                    if 'title' not in self.current_document_metadata and 'title' in doc:
                        self.current_document_metadata['title'] = doc['title']
                else:
                    self.current_document_class = "source"
                    self.current_document_metadata = {}

                logging.debug("Converting entries to text...")
                self.current_document_text = entries_to_text(self.current_entries, timestamp_interval=self.config.get("timestamp_interval", "every_segment"))
                logging.debug(f"Text converted, length: {len(self.current_document_text) if self.current_document_text else 0}")

                # Preview display removed - content stored in current_document_text

                self.set_status("✅ Document loaded - Select prompt and click Run")
                self.refresh_library()
                
                # Update button states
                self.update_button_states()
                
                logging.debug("File result handler completed successfully")
            else:
                logging.debug(f"File result handler: success=False, result={result}")
                # Check for special codes that need different handling
                if result == "IMAGE_FILE":
                    # Image file detected - route to OCR
                    if messagebox.askyesno("OCR Processing",
                                          "This is an image file. Would you like to extract text using OCR?"):
                        self.process_ocr()
                    else:
                        self.set_status("Cancelled OCR processing")
                elif result == "SCANNED_PDF":
                    # Scanned PDF detected - offer OCR
                    if messagebox.askyesno("OCR Required",
                                          "This PDF appears to be scanned. Would you like to process it with OCR?"):
                        self.process_ocr()
                    else:
                        self.set_status("Cancelled OCR processing")
                else:
                    # Regular error
                    self.set_status(f"❌ Error: {result}")
                    messagebox.showerror("Error", result)
        except Exception as e:
            logging.error(f"EXCEPTION in _handle_file_result: {e}")
            logging.error(traceback.format_exc())
            self.set_status(f"❌ Error: {str(e)}")
            messagebox.showerror("Error", f"Failed to process file: {str(e)}")

    def _handle_spreadsheet_result(self, text_content, title, file_path):
        """Handle loaded spreadsheet data"""
        try:
            self.processing = False
            self.process_btn.config(state=tk.NORMAL)
            
            # Store as plain text document
            self.current_document_source = file_path
            self.current_document_type = "spreadsheet"
            self.current_document_text = text_content
            
            # Convert text to entries format (single entry containing all spreadsheet data)
            entries = [{
                "text": text_content,
                "start": 0,
                "end": len(text_content),
                "metadata": {"type": "spreadsheet_data"}
            }]
            
            # Store entries for library
            self.current_entries = entries
            
            # Add to document library
            doc_id = add_document_to_library(
                doc_type="spreadsheet",
                source=file_path,
                title=title,
                entries=entries,
                document_class="source",
                metadata={"file_type": "spreadsheet"}
            )
            
            # Save old thread before changing document
            if self.thread_message_count > 0 and self.current_document_id:
                self.save_current_thread()
            
            # Clear thread
            self.current_thread = []
            self.thread_message_count = 0
            self.update_thread_status()
            
            # Set new document ID
            self.current_document_id = doc_id
            self.load_saved_thread()
            
            # Get document info
            doc = get_document_by_id(doc_id)
            if doc:
                self.current_document_class = doc.get("document_class", "source")
                self.current_document_metadata = doc.get("metadata", {})
                if 'title' not in self.current_document_metadata and 'title' in doc:
                    self.current_document_metadata['title'] = doc['title']
            else:
                self.current_document_class = "source"
                self.current_document_metadata = {}
            
            
            self.set_status("✅ Document loaded - Select prompt and click Run")
            self.refresh_library()
            
            # Update button states
            self.update_button_states()
            
        except Exception as e:
            logging.error(f"Error in _handle_spreadsheet_result: {e}")
            logging.error(traceback.format_exc())
            self.set_status(f"❌ Error loading spreadsheet: {str(e)}")
            messagebox.showerror("Error", f"Failed to load spreadsheet: {str(e)}")

    def _handle_ocr_fetch(self, success, result, title):
        self.processing = False
        self.process_btn.config(state=tk.NORMAL)
        print(f"\n🔵 _handle_ocr_fetch called: success={success}, result='{result}', title='{title}'", flush=True)
        if result == "SCANNED_PDF":
            cached = getattr(self, '_cached_ocr_data', None)
            print(f"🔵 _handle_ocr_fetch: cached={type(cached).__name__}, is None={cached is None}, bool={bool(cached) if cached is not None else 'N/A'}", flush=True)

            if cached:
                # Cache exists - offer choice: re-scan, use cached, or cancel
                answer = messagebox.askyesnocancel(
                    "Scanned PDF — OCR Options",
                    "This PDF has been scanned before.\n\n"
                    "• Yes — Re-scan with OCR (choose Printed or Handwriting)\n"
                    "• No — Use previous OCR results\n"
                    "• Cancel — Do nothing"
                )
                self._cached_ocr_data = None  # Clear stored cache reference
                if answer is True:     # Yes → re-scan
                    self.process_ocr()
                elif answer is False:  # No → use cached
                    self._load_cached_ocr_directly(cached, title)
                else:                  # Cancel
                    self.set_status("Cancelled OCR processing")
            else:
                # No cache - standard prompt
                if messagebox.askyesno("OCR Required",
                                       "This PDF appears to be scanned. Would you like to process it with OCR?"):
                    self.process_ocr()
                else:
                    self.set_status("Cancelled OCR processing")
        else:
            self.set_status(f"❌ Error: {result}")
            messagebox.showerror("Error", result)

    def process_ocr(self):
        file_path = self.file_path_var.get()
        if not file_path or not os.path.exists(file_path):
            messagebox.showerror("Error", "Please select a valid PDF file.")
            return
        available, error_msg, _ = get_ocr().check_ocr_availability()
        if not available:
            self.set_status(f"❌ OCR unavailable: {error_msg}")
            messagebox.showerror("OCR Error", error_msg)
            return
        self.processing = True
        self.process_btn.config(state=tk.DISABLED)
        self.set_status("Processing OCR...")
        self.processing_thread = threading.Thread(target=self._process_ocr_thread)
        self.processing_thread.start()
        self.root.after(100, self.check_processing_thread)

    def _ask_text_type(self, image_path=None):
        """
        Ask user what type of text is in the image: Printed or Handwriting.
        Auto-detects based on OCR confidence and pre-selects accordingly.
        Returns "printed" or "handwriting".
        This is called from a background thread, so we need to use threading events.
        """
        import threading
        
        result = ["printed"]  # Default to printed
        event = threading.Event()
        
        # Auto-detect handwriting if we have a path
        likely_handwriting = False
        confidence = 100
        if image_path and os.path.exists(image_path):
            try:
                confidence, likely_handwriting = self._check_ocr_confidence(image_path)
            except Exception as e:
                print(f"⚠️ Auto-detection failed: {e}")
        
        def ask():
            try:
                # Create dialog
                dialog = tk.Toplevel(self.root)
                dialog.title("Text Type")
                dialog.geometry("450x260")
                dialog.resizable(False, False)
                dialog.transient(self.root)
                dialog.grab_set()
                self.style_dialog(dialog)
                
                # Center on parent
                dialog.update_idletasks()
                x = self.root.winfo_x() + (self.root.winfo_width() - 450) // 2
                y = self.root.winfo_y() + (self.root.winfo_height() - 260) // 2
                dialog.geometry(f"+{x}+{y}")
                
                # Question
                ttk.Label(
                    dialog,
                    text="What type of text is in this image?",
                    font=('Arial', 11)
                ).pack(pady=(15, 5))
                
                # Auto-detection status
                threshold = self.config.get("ocr_confidence_threshold", 70)
                if likely_handwriting:
                    status_text = f"⚠️ Low OCR confidence ({confidence:.0f}%) - handwriting detected"
                    status_color = '#CC6600'
                else:
                    status_text = f"✓ Good OCR confidence ({confidence:.0f}%) - likely printed text"
                    status_color = '#006600'
                
                ttk.Label(
                    dialog,
                    text=status_text,
                    font=('Arial', 9),
                    foreground=status_color
                ).pack(pady=(0, 10))
                
                # Check if vision is supported
                vision_supported, current_provider = self._provider_supports_vision()
                
                # Show provider status
                if vision_supported:
                    provider_text = f"✅ {current_provider} supports vision AI"
                    provider_color = '#006600'
                else:
                    provider_text = f"⚠️ {current_provider} does not support vision AI"
                    provider_color = '#CC0000'
                
                ttk.Label(
                    dialog,
                    text=provider_text,
                    font=('Arial', 9),
                    foreground=provider_color
                ).pack(pady=(0, 10))
                
                # Buttons frame
                btn_frame = ttk.Frame(dialog)
                btn_frame.pack(pady=10)
                
                def select_printed():
                    result[0] = "printed"
                    dialog.destroy()
                
                def select_handwriting():
                    print(f"🔵 select_handwriting() called! vision_supported={vision_supported}", flush=True)
                    # Check if vision is supported
                    if not vision_supported:
                        messagebox.showwarning(
                            "⚠️ Vision AI Not Available",
                            f"Your current AI provider ({current_provider}) does not support "
                            f"vision/image processing needed for handwriting recognition.\n\n"
                            f"To proceed, please:\n\n"
                            f"  • Change 'AI Provider' in the main window to:\n"
                            f"      → OpenAI (uses GPT-4o) - Best for handwriting\n"
                            f"      → Anthropic (uses Claude)\n"
                            f"      → Google (uses Gemini)\n"
                            f"  • Make sure you have an API key entered\n"
                            f"  • Try loading the file again\n\n"
                            f"Or select 'Printed Text' to use free local OCR\n"
                            f"(works for printed text only)."
                        )
                        return  # Cannot proceed without vision support
                    result[0] = "handwriting"
                    print(f"🔵 result[0] set to '{result[0]}' - dialog closing", flush=True)
                    dialog.destroy()
                
                printed_btn = ttk.Button(
                    btn_frame,
                    text="📄 Printed Text (Free OCR)",
                    command=select_printed,
                    width=22
                )
                printed_btn.pack(side=tk.LEFT, padx=10)
                
                handwriting_btn = ttk.Button(
                    btn_frame,
                    text="✍️ Handwriting (AI Vision)",
                    command=select_handwriting,
                    width=22
                )
                handwriting_btn.pack(side=tk.LEFT, padx=10)
                
                # Highlight recommended option based on detection AND vision support
                if likely_handwriting and vision_supported:
                    handwriting_btn.focus_set()
                else:
                    printed_btn.focus_set()
                
                # Settings hint
                hint_line1 = f"AI vision recommended if OCR accuracy falls below {threshold}%."
                hint_line2 = "To adjust threshold, go to Settings → OCR Settings."
                ttk.Label(
                    dialog,
                    text=hint_line1 + "\n" + hint_line2,
                    font=('Arial', 8, 'italic'),
                    foreground='#888888',
                    justify=tk.CENTER
                ).pack(pady=(15, 10))
                
                # Handle window close (use recommended)
                def on_close():
                    result[0] = "handwriting" if likely_handwriting else "printed"
                    dialog.destroy()
                
                dialog.protocol("WM_DELETE_WINDOW", on_close)
                
                # Wait for dialog to close
                dialog.wait_window()
            finally:
                event.set()
        
        # Schedule dialog in main thread
        self.root.after(0, ask)
        
        # Wait for dialog to complete
        event.wait(timeout=120)
        
        return result[0]


    def _ask_text_type_pdf(self, pdf_path=None):
        """
        Ask user what type of text is in the PDF: Printed or Handwriting.
        Auto-detects based on OCR confidence of first page.
        Returns "printed" or "handwriting".
        This is called from a background thread, so we need to use threading events.
        """
        import threading
        import tempfile
        
        result = ["printed"]  # Default to printed
        event = threading.Event()
        
        # Auto-detect handwriting by checking first page
        likely_handwriting = False
        confidence = 100
        
        if pdf_path and os.path.exists(pdf_path):
            try:
                # Convert first page to image for confidence check
                from pdf2image import convert_from_path
                import concurrent.futures
                print(f"🟢 _ask_text_type_pdf: converting first page for confidence check...", flush=True)
                self.set_status("Analysing PDF for handwriting...")
                executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                try:
                    future = executor.submit(convert_from_path, pdf_path, first_page=1, last_page=1, dpi=150)
                    images = future.result(timeout=30)  # 30 second timeout for Poppler
                finally:
                    executor.shutdown(wait=False)
                print(f"🟢 _ask_text_type_pdf: conversion done, {len(images)} images", flush=True)
                if images:
                    # Save temp image
                    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                        images[0].save(tmp.name, 'PNG')
                        confidence, likely_handwriting = self._check_ocr_confidence(tmp.name)
                        os.unlink(tmp.name)
            except concurrent.futures.TimeoutError:
                print(f"⚠️ PDF confidence check timed out - defaulting to handwriting likely", flush=True)
                likely_handwriting = True
                confidence = 40
            except Exception as e:
                print(f"⚠️ PDF auto-detection failed: {e}", flush=True)
        
        def ask():
            try:
                # Create dialog
                dialog = tk.Toplevel(self.root)
                dialog.title("PDF Text Type")
                dialog.geometry("450x260")
                dialog.resizable(False, False)
                dialog.transient(self.root)
                dialog.grab_set()
                self.style_dialog(dialog)
                
                # Center on parent
                dialog.update_idletasks()
                x = self.root.winfo_x() + (self.root.winfo_width() - 450) // 2
                y = self.root.winfo_y() + (self.root.winfo_height() - 260) // 2
                dialog.geometry(f"+{x}+{y}")
                
                # Question
                ttk.Label(
                    dialog,
                    text="What type of text is in this PDF?",
                    font=('Arial', 11)
                ).pack(pady=(15, 5))
                
                # Auto-detection status
                threshold = self.config.get("ocr_confidence_threshold", 70)
                if likely_handwriting:
                    status_text = f"⚠️ Low OCR confidence ({confidence:.0f}%) - handwriting likely"
                    status_color = '#CC6600'
                else:
                    status_text = f"✓ Good OCR confidence ({confidence:.0f}%) - likely printed text"
                    status_color = '#006600'
                
                ttk.Label(
                    dialog,
                    text=status_text,
                    font=('Arial', 9),
                    foreground=status_color
                ).pack(pady=(0, 10))
                
                # Check if vision is supported
                vision_supported, current_provider = self._provider_supports_vision()
                
                # Show provider status
                if vision_supported:
                    provider_text = f"✅ {current_provider} supports vision AI"
                    provider_color = '#006600'
                else:
                    provider_text = f"⚠️ {current_provider} does not support vision AI"
                    provider_color = '#CC0000'
                
                ttk.Label(
                    dialog,
                    text=provider_text,
                    font=('Arial', 9),
                    foreground=provider_color
                ).pack(pady=(0, 10))
                
                # Buttons frame
                btn_frame = ttk.Frame(dialog)
                btn_frame.pack(pady=10)
                
                def select_printed():
                    result[0] = "printed"
                    dialog.destroy()
                
                def select_handwriting():
                    # Check if vision is supported
                    if not vision_supported:
                        messagebox.showwarning(
                            "⚠️ Vision AI Not Available",
                            f"Your current AI provider ({current_provider}) does not support "
                            f"vision/image processing needed for handwriting recognition.\n\n"
                            f"To proceed, please:\n\n"
                            f"  • Change 'AI Provider' in the main window to:\n"
                            f"      → OpenAI (uses GPT-4o) - Best for handwriting\n"
                            f"      → Anthropic (uses Claude)\n"
                            f"      → Google (uses Gemini)\n"
                            f"  • Make sure you have an API key entered\n"
                            f"  • Try loading the file again\n\n"
                            f"Or select 'Printed Text' to use free local OCR\n"
                            f"(works for printed text only)."
                        )
                        return  # Cannot proceed without vision support
                    result[0] = "handwriting"
                    dialog.destroy()
                
                printed_btn = ttk.Button(
                    btn_frame,
                    text="📄 Printed Text (Free OCR)",
                    command=select_printed,
                    width=22
                )
                printed_btn.pack(side=tk.LEFT, padx=10)
                
                handwriting_btn = ttk.Button(
                    btn_frame,
                    text="✍️ Handwriting (AI Vision)",
                    command=select_handwriting,
                    width=22
                )
                handwriting_btn.pack(side=tk.LEFT, padx=10)
                
                # Highlight recommended option based on detection AND vision support
                if likely_handwriting and vision_supported:
                    handwriting_btn.focus_set()
                else:
                    printed_btn.focus_set()
                
                # Settings hint
                hint_line1 = f"AI vision recommended if OCR accuracy falls below {threshold}%."
                hint_line2 = "To adjust threshold, go to Settings → OCR Settings."
                ttk.Label(
                    dialog,
                    text=hint_line1 + "\n" + hint_line2,
                    font=('Arial', 8, 'italic'),
                    foreground='#888888',
                    justify=tk.CENTER
                ).pack(pady=(15, 10))
                
                # Handle window close (use recommended)
                def on_close():
                    result[0] = "handwriting" if likely_handwriting else "printed"
                    dialog.destroy()
                
                dialog.protocol("WM_DELETE_WINDOW", on_close)
                
                # Wait for dialog to close
                dialog.wait_window()
            finally:
                event.set()
        
        # Schedule dialog in main thread
        self.root.after(0, ask)
        
        # Wait for dialog to complete
        event.wait(timeout=120)
        
        print(f"🔵 _ask_text_type_pdf RETURNING: '{result[0]}'", flush=True)
        return result[0]


    def _ask_cloud_ai_escalation(self, confidence, provider, model):
        """
        Ask user if they want to retry OCR with Cloud AI after low confidence local result.
        Returns True if user wants to escalate, False otherwise.
        This is called from a background thread, so we need to use threading events.
        """
        import threading
        
        result = [False]  # Use list to allow modification in nested function
        event = threading.Event()
        
        def ask():
            try:
                response = messagebox.askyesno(
                    "Low OCR Confidence",
                    f"Local OCR confidence is low ({confidence:.1f}%).\n\n"
                    f"The result may be unreliable, especially for handwriting.\n\n"
                    f"Would you like to retry with Cloud AI ({provider})?\n\n"
                    f"This will use your API key and may incur a small cost.",
                    icon='question'
                )
                result[0] = response
            finally:
                event.set()  # Signal that dialog is complete
        
        # Schedule dialog in main thread
        self.root.after(0, ask)
        
        # Wait for dialog to complete (with timeout)
        event.wait(timeout=120)  # 2 minute timeout
        
        return result[0]

    def _ask_text_type_for_image(self):
        """
        Ask user what type of text is in the image (Printed or Handwriting).
        Returns "printed" or "handwriting".
        This is called from a background thread, so we need to use threading events.
        """
        import threading
        
        result = ["printed"]  # Default to printed
        event = threading.Event()
        
        def ask():
            try:
                # Create a simple popup dialog
                popup = tk.Toplevel(self.root)
                popup.title("Text Type")
                popup.geometry("300x120")
                popup.resizable(False, False)
                popup.transient(self.root)
                popup.grab_set()
                
                # Center on parent
                popup.update_idletasks()
                x = self.root.winfo_x() + (self.root.winfo_width() - 300) // 2
                y = self.root.winfo_y() + (self.root.winfo_height() - 120) // 2
                popup.geometry(f"+{x}+{y}")
                
                # Question label
                ttk.Label(
                    popup,
                    text="What type of text is in this image?",
                    font=('Arial', 11)
                ).pack(pady=(20, 15))
                
                # Button frame
                btn_frame = ttk.Frame(popup)
                btn_frame.pack(pady=5)
                
                def select_printed():
                    result[0] = "printed"
                    popup.destroy()
                    event.set()
                
                def select_handwriting():
                    result[0] = "handwriting"
                    popup.destroy()
                    event.set()
                
                ttk.Button(
                    btn_frame,
                    text="📄 Printed Text",
                    command=select_printed,
                    width=15
                ).pack(side=tk.LEFT, padx=10)
                
                ttk.Button(
                    btn_frame,
                    text="✍️ Handwriting",
                    command=select_handwriting,
                    width=15
                ).pack(side=tk.LEFT, padx=10)
                
                # Handle window close (default to printed)
                def on_close():
                    result[0] = "printed"
                    popup.destroy()
                    event.set()
                
                popup.protocol("WM_DELETE_WINDOW", on_close)
                
            except Exception as e:
                print(f"Text type dialog error: {e}")
                event.set()
        
        # Schedule dialog in main thread
        self.root.after(0, ask)
        
        # Wait for dialog to complete (with timeout)
        event.wait(timeout=120)  # 2 minute timeout
        
        return result[0]

    def _process_image_with_cloud_ai(self, image_path, title):
        """
        Process a single image using the smart OCR router.
        Routes to Cloud Vision (printed) or Vision AI (handwriting) based on settings.
        Returns (success, entries_or_error)
        """
        from ocr_handler import ocr_image_smart
        
        # Get settings
        text_type = self.config.get("ocr_text_type", "printed")
        language = self.config.get("ocr_language", "eng")
        quality = self.config.get("ocr_quality", "balanced")
        
        # Get API keys
        cloud_vision_key = self.config.get("keys", {}).get("Google Cloud Vision", "")
        
        # For handwriting, use the selected AI provider
        provider = self.provider_var.get()
        model = self.model_var.get()
        vision_api_key = self.config.get("keys", {}).get(provider, "")
        
        success, result, method = ocr_image_smart(
            image_path=image_path,
            text_type=text_type,
            language=language,
            quality=quality,
            cloud_vision_api_key=cloud_vision_key,
            vision_provider=provider,
            vision_model=model,
            vision_api_key=vision_api_key,
            document_title=title,
            progress_callback=self.set_status
        )
        
        if success:
            # Format as entries
            entries = [{
                'location': f'Image ({method})',
                'text': result.strip()
            }]
            return True, entries
        else:
            return False, result

    def _process_pdf_with_cloud_ai(self, pdf_path, title, text_type="handwriting"):
        """
        Process a scanned PDF using the smart OCR router (page by page).
        Routes to Cloud Vision (printed) or Vision AI (handwriting) based on text_type.
        Returns (success, entries_or_error)
        """
        from pdf2image import convert_from_path
        from ocr_handler import ocr_image_smart
        import tempfile
        
        # Get settings
        # text_type is now passed as parameter from the user's dialog choice
        language = self.config.get("ocr_language", "eng")
        quality = self.config.get("ocr_quality", "balanced")
        
        # Get API keys
        cloud_vision_key = self.config.get("keys", {}).get("Google Cloud Vision", "")
        
        # For handwriting, use the selected AI provider
        provider = self.provider_var.get()
        model = self.model_var.get()
        vision_api_key = self.config.get("keys", {}).get(provider, "")
        
        # Check if at least one OCR method is available
        if not cloud_vision_key and (not vision_api_key or vision_api_key == "not-required"):
            return False, "No OCR service configured. Add Google Cloud Vision key or AI provider API key in Settings."
        
        try:
            self.set_status("Converting PDF pages to images...")
            print(f"🟢 _process_pdf_with_cloud_ai: converting PDF to images (dpi=200)...", flush=True)
            
            # Raise Pillow's decompression bomb limit for large scanned pages
            # This is safe because the user deliberately loaded this file
            from PIL import Image as PILImage
            old_max_pixels = PILImage.MAX_IMAGE_PIXELS
            PILImage.MAX_IMAGE_PIXELS = 500_000_000  # ~500MP (raised from 178MP default)
            
            import concurrent.futures as cf
            try:
                with cf.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(convert_from_path, pdf_path, dpi=200)
                    images = future.result(timeout=60)  # 60 second timeout for full PDF conversion
            except cf.TimeoutError:
                print(f"🔴 convert_from_path timed out after 60s", flush=True)
                PILImage.MAX_IMAGE_PIXELS = old_max_pixels  # Restore limit
                return False, "PDF to image conversion timed out. The PDF may be too large or Poppler may not be responding."
            except Exception as conv_err:
                # If still too large even with raised limit, try lower DPI
                if 'decompression bomb' in str(conv_err).lower() or 'exceeds limit' in str(conv_err).lower():
                    print(f"🟠 DPI 200 too large, retrying at 150 DPI...", flush=True)
                    self.set_status("Large PDF — retrying at lower resolution...")
                    try:
                        with cf.ThreadPoolExecutor(max_workers=1) as executor:
                            future = executor.submit(convert_from_path, pdf_path, dpi=150)
                            images = future.result(timeout=60)
                    except Exception as retry_err:
                        PILImage.MAX_IMAGE_PIXELS = old_max_pixels
                        return False, f"PDF pages too large even at reduced resolution: {str(retry_err)}"
                else:
                    PILImage.MAX_IMAGE_PIXELS = old_max_pixels
                    raise
            PILImage.MAX_IMAGE_PIXELS = old_max_pixels  # Restore limit after conversion
            total_pages = len(images)
            print(f"🟢 _process_pdf_with_cloud_ai: {total_pages} pages converted", flush=True)
            self.set_status(f"Processing {total_pages} pages with Cloud AI (text_type={text_type})...")
            
            entries = []
            
            for page_num, image in enumerate(images, start=1):
                self.set_status(f"🤖 Cloud AI processing page {page_num}/{total_pages}...")
                
                # Save image to temp file - use JPEG for much faster upload (smaller files)
                with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                    # Convert to RGB if necessary (JPEG doesn't support transparency)
                    if image.mode in ('RGBA', 'P', 'LA'):
                        image = image.convert('RGB')
                    image.save(tmp.name, 'JPEG', quality=85, optimize=True)
                    tmp_path = tmp.name
                
                try:
                    print(f"\n🟢 Page {page_num}: calling ocr_image_smart(text_type='{text_type}', provider='{provider}', model='{model}')", flush=True)
                    success, result, method = ocr_image_smart(
                        image_path=tmp_path,
                        text_type=text_type,
                        language=language,
                        quality=quality,
                        cloud_vision_api_key=cloud_vision_key,
                        vision_provider=provider,
                        vision_model=model,
                        vision_api_key=vision_api_key,
                        document_title=f"{title} - Page {page_num}",
                        progress_callback=None  # Don't spam status for each page
                    )
                    
                    print(f"🟢 Page {page_num}: ocr_image_smart returned success={success}, method={method}, result_len={len(result) if isinstance(result, str) else 'N/A'}", flush=True)
                    if success and result.strip():
                        # Split into paragraphs like the local OCR does
                        paragraphs = [p.strip() for p in result.split('\n\n') if p.strip()]
                        for para in paragraphs:
                            entries.append({
                                'start': page_num,
                                'text': para,
                                'location': f'Page {page_num} ({method})'
                            })
                finally:
                    # Clean up temp file
                    try:
                        os.unlink(tmp_path)
                    except:
                        pass
            
            if entries:
                # Save to OCR cache so the 3-option dialog works on reload
                from ocr_handler import save_ocr_cache
                save_ocr_cache(pdf_path, quality, language, entries)
                print(f"💾 Vision AI results saved to OCR cache for: {pdf_path}", flush=True)
                self.set_status(f"✅ Cloud AI complete! Extracted text from {total_pages} pages")
                return True, entries
            else:
                return False, "No text could be extracted from PDF"
                
        except Exception as e:
            return False, f"Cloud AI PDF processing error: {str(e)}"

    def _process_ocr_thread(self):
        file_path = self.file_path_var.get()
        ext = os.path.splitext(file_path)[1].lower()
        title = os.path.basename(file_path)
        print(f"\n🔵 _process_ocr_thread started: ext='{ext}', title='{title}'", flush=True)
        
        try:
            # Check if it's an image file (not a PDF)
            if ext in ('.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp', '.gif'):
                
                # Ask user what type of text is in the image (with auto-detection)
                text_type = self._ask_text_type(file_path)
                
                if text_type == "handwriting":
                    # Handwriting -> Use Cloud AI
                    provider = self.provider_var.get()
                    api_key = self.config.get("keys", {}).get(provider, "")
                    
                    if not api_key or api_key == "not-required":
                        self.set_status(f"⚠️ No API key for {provider}")
                        self.root.after(0, lambda: messagebox.showwarning(
                            "API Key Required",
                            f"Handwriting OCR requires a Cloud AI provider."
                            f"Please configure an API key for {provider} in Settings → API Keys."
                        ))
                        self.root.after(0, self._handle_ocr_result, False, "No API key configured", title)
                        return
                    
                    self.set_status("🤖 Processing handwriting with Cloud AI...")
                    success, result = self._process_image_with_cloud_ai(file_path, title)
                    if success:
                        self.root.after(0, self._handle_ocr_result, True, result, title)
                    else:
                        self.set_status(f"⚠️ Cloud AI failed: {result}")
                        self.root.after(0, lambda: messagebox.showwarning(
                            "Cloud AI Failed",
                            f"Cloud AI processing failed:{result}"
                        ))
                        self.root.after(0, self._handle_ocr_result, False, result, title)
                    return
                
                # Printed text -> Use local Tesseract
                import pytesseract
                from PIL import Image
                from ocr_handler import preprocess_image_for_ocr, get_tesseract_confidence
                
                self.set_status("📄 Processing printed text with local OCR...")
                image = Image.open(file_path)
                
                # Get OCR configuration
                language = self.config.get("ocr_language", "eng")
                quality = self.config.get("ocr_quality", "balanced")
                preset = OCR_PRESETS.get(quality, OCR_PRESETS["balanced"])
                custom_config = f'--psm {preset["psm"]} --oem 3'
                
                # Preprocess image
                processed_image = preprocess_image_for_ocr(image, quality)
                
                # Get OCR with confidence score
                text, confidence = get_tesseract_confidence(processed_image, language, custom_config)
                
                self.set_status(f"📊 OCR confidence: {confidence:.1f}%")
                
                # Use local result
                entries = [{
                    'location': 'Image',
                    'text': text.strip()
                }]
                
                self.root.after(0, self._handle_ocr_result, True, entries, title)
            else:
                # Process as PDF
                
                # Ask user what type of text is in the PDF (with auto-detection)
                text_type = self._ask_text_type_pdf(file_path)
                print(f"\n🔵 _process_ocr_thread: _ask_text_type_pdf returned: '{text_type}'", flush=True)
                print(f"🔵 _process_ocr_thread: text_type == 'handwriting' → {text_type == 'handwriting'}", flush=True)
                
                if text_type == "handwriting":
                    # Handwriting -> Use Cloud AI page by page
                    provider = self.provider_var.get()
                    api_key = self.config.get("keys", {}).get(provider, "")
                    
                    if not api_key or api_key == "not-required":
                        self.set_status(f"⚠️ No API key for {provider}")
                        self.root.after(0, lambda: messagebox.showwarning(
                            "API Key Required",
                            f"Handwriting OCR requires a Cloud AI provider.\n\n"
                            f"Please configure an API key for {provider} in Settings → API Keys."
                        ))
                        self.root.after(0, self._handle_ocr_result, False, "No API key configured", title)
                        return
                    
                    self.set_status("🤖 Processing PDF handwriting with Cloud AI...")
                    print(f"🔵 HANDWRITING BRANCH TAKEN! provider='{provider}', model='{self.model_var.get()}', has_key={bool(api_key)}", flush=True)
                    success, result = self._process_pdf_with_cloud_ai(file_path, title)
                    if success:
                        self.root.after(0, self._handle_ocr_result, True, result, title)
                    else:
                        self.set_status(f"⚠️ Cloud AI failed: {result}")
                        self.root.after(0, lambda: messagebox.showwarning(
                            "Cloud AI Failed",
                            f"Cloud AI processing failed:\n{result}"
                        ))
                        self.root.after(0, self._handle_ocr_result, False, result, title)
                    return
                
                # Printed text -> Use local Tesseract with smart fallback
                # This will: 1) Try local Poppler+Tesseract, 2) If fails, try Cloud AI direct PDF
                # 3) If that fails, offer iLovePDF repair
                print(f"🔵 PRINTED BRANCH TAKEN (local Tesseract) - text_type was '{text_type}'", flush=True)
                provider = self.provider_var.get()
                model = self.model_var.get()
                api_key = self.config.get("keys", {}).get(provider, "")
                all_api_keys = self.config.get("keys", {})
                
                self.set_status("📄 Processing PDF with local OCR...")
                success, result, method = get_ocr().extract_text_from_pdf_smart(
                    filepath=file_path,
                    language=self.config.get("ocr_language", "eng"),
                    quality=self.config.get("ocr_quality", "balanced"),
                    provider=provider,
                    model=model,
                    api_key=api_key,
                    all_api_keys=all_api_keys,
                    progress_callback=self.set_status,
                    force_cloud=False
                )
                
                if success:
                    if method == 'cloud_direct':
                        self.set_status(f"✅ PDF processed via Cloud AI (local conversion failed)")
                    self.root.after(0, self._handle_ocr_result, True, result, title)
                else:
                    # Smart extraction failed completely - result contains error message
                    self.root.after(0, self._handle_ocr_result, False, result, title)
        except Exception as e:
            self.root.after(0, self._handle_ocr_result, False, str(e), os.path.basename(file_path))

    def _handle_ocr_result(self, success, result, title):
        self.processing = False
        self.process_btn.config(state=tk.NORMAL)
        if success:
            self.current_entries = result
            self.current_document_source = self.file_path_var.get()
            self.current_document_type = "ocr"
            doc_id = add_document_to_library(
                doc_type="ocr",
                source=self.current_document_source,
                title=title,
                entries=self.current_entries,
                document_class="source",
                metadata={"ocr_language": self.config.get("ocr_language", "eng"),
                          "ocr_quality": self.config.get("ocr_quality", "balanced")}
            )
            # ✅ FIX: Save old thread BEFORE changing document ID
            if self.thread_message_count > 0 and self.current_document_id:
                print(f"💾 Saving old thread ({self.thread_message_count} messages) to document {self.current_document_id}")
                self.save_current_thread()
            
            # ✅ FIX: Clear thread WITHOUT saving (we already saved above)
            self.current_thread = []
            self.thread_message_count = 0
            self.update_thread_status()
            
            # ✅ NOW change the document ID
            self.current_document_id = doc_id
            
            # ✅ Load saved thread for NEW document (if it has one)
            self.load_saved_thread()
            # Get document class and metadata from library
            doc = get_document_by_id(doc_id)
            if doc:
                self.current_document_class = doc.get("document_class", "source")
                self.current_document_metadata = doc.get("metadata", {})
                # CRITICAL FIX: Add title to metadata if not already there
                if 'title' not in self.current_document_metadata and 'title' in doc:
                    self.current_document_metadata['title'] = doc['title']
            else:
                self.current_document_class = "source"
                self.current_document_metadata = {}

            self.current_document_text = entries_to_text(self.current_entries, timestamp_interval=self.config.get("timestamp_interval", "every_segment"))

            self.set_status(f"✅ OCR completed: {title}")
            self.refresh_library()
            
            # Update button states
            self.update_button_states()
        else:
            self.set_status(f"❌ OCR Error: {result}")
            messagebox.showerror("OCR Error", result)

    def fetch_web(self):

        self.update_context_buttons('web')

        if self.processing:
            messagebox.showwarning("Warning", "Processing already in progress. Please wait or cancel.")
            return

        url = self.web_url_var.get().strip()

        # Validate input
        is_valid, error_msg = self.validate_web_url(url)
        if not is_valid:
            messagebox.showerror("Invalid Input", error_msg)
            return

        self.processing = True
        self.process_btn.config(state=tk.DISABLED)
        self.set_status("Fetching web content...")
        self.processing_thread = threading.Thread(target=self._fetch_web_thread)
        self.processing_thread.start()
        self.root.after(100, self.check_processing_thread)

    # -------------------------
    # GUI Thread Handler for Web Fetching
    # -------------------------

    def _fetch_web_thread(self):
        """Thread function for fetching web content"""
        url = self.web_url_var.get().strip()
        success, result, title, doc_type, web_metadata = get_doc_fetcher().fetch_web_url(url)
        self.root.after(0, self._handle_web_result, success, result, title, doc_type, web_metadata)

    """
    ADD THESE THREE METHODS TO Main.py DocAnalyserApp CLASS
    Location: After fetch_web method (around line 1100)
    """

    def process_web_video(self):
        """Process a web URL that contains video"""
        url = self.web_url_var.get().strip()

        if not url:
            messagebox.showerror("Error", "No URL specified")
            return

        self.processing = True
        self.process_btn.config(state=tk.DISABLED)
        self.set_status("Processing web video...")

        self.processing_thread = threading.Thread(target=self._process_web_video_thread, args=(url,))
        self.processing_thread.start()
        self.root.after(100, self.check_processing_thread)

    def _process_web_video_thread(self, url):
        """Thread function for processing web video"""
        try:
            from document_fetcher import fetch_web_video

            success, result, title, source_type = fetch_web_video(
                url=url,
                api_key=self._get_transcription_api_key(),
                engine=self.transcription_engine_var.get(),
                options={
                    'language': self.transcription_lang_var.get().strip() or None,
                    'speaker_diarization': self.diarization_var.get(),
                    'enable_vad': self.config.get("enable_vad", True)
                },
                bypass_cache=self.bypass_cache_var.get() if hasattr(self, 'bypass_cache_var') else False,
                progress_callback=self.set_status
            )

            if success:
                # Process like audio transcription result
                self.root.after(0, self._handle_web_video_result, True, result, title, source_type)
            else:
                self.root.after(0, self._handle_web_video_result, False, result, title, source_type)

        except Exception as e:
            error_msg = f"Error processing web video: {str(e)}"
            self.root.after(0, self._handle_web_video_result, False, error_msg, url, "web_video")

    def _handle_web_video_result(self, success, result, title, source_type):
        """Handle web video processing result"""
        self.processing = False
        self.process_btn.config(state=tk.NORMAL)

        if success:
            self.current_entries = result
            self.current_document_source = self.web_url_var.get().strip()
            self.current_document_type = source_type

            doc_id = add_document_to_library(
                doc_type=source_type,
                source=self.current_document_source,
                title=title,
                entries=self.current_entries,
                document_class="source",
                metadata={"source": "web_video"}
            )

            self.current_document_id = doc_id
            self.clear_thread()

            # Get document class and metadata from library
            doc = get_document_by_id(doc_id)
            if doc:
                self.current_document_class = doc.get("document_class", "source")
                self.current_document_metadata = doc.get("metadata", {})
                # CRITICAL FIX: Add title to metadata if not already there
                if 'title' not in self.current_document_metadata and 'title' in doc:
                    self.current_document_metadata['title'] = doc['title']
            else:
                self.current_document_class = "source"
                self.current_document_metadata = {}

            self.current_document_text = entries_to_text_with_speakers(
                self.current_entries,
                timestamp_interval=self.config.get("timestamp_interval", "every_segment")
            )

            self.set_status("✅ Document loaded - Select prompt and click Run")
            self.refresh_library()
            
            # Update button states
            self.update_button_states()
        else:
            self.set_status(f"❌ Error: {result}")
            messagebox.showerror("Error", f"Failed to process web video:\n\n{result}")

    def process_web_pdf_with_ocr(self):
        """Download PDF from URL and process with OCR"""
        url = self.web_url_var.get().strip()

        # Check OCR availability
        available, error_msg, _ = get_ocr().check_ocr_availability()
        if not available:
            self.set_status(f"❌ OCR unavailable: {error_msg}")
            messagebox.showerror("OCR Error", error_msg)
            return

        self.processing = True
        self.process_btn.config(state=tk.DISABLED)
        self.set_status("Downloading PDF...")

        self.processing_thread = threading.Thread(target=self._process_web_pdf_ocr_thread, args=(url,))
        self.processing_thread.start()
        self.root.after(100, self.check_processing_thread)

    def _process_web_pdf_ocr_thread(self, url):
        """Thread function for downloading and OCR processing web PDF"""
        try:
            # Download PDF
            self.set_status("📥 Downloading PDF from URL...")
            response = requests.get(url, timeout=30)
            response.raise_for_status()

            # Save to temp file
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_pdf:
                temp_pdf.write(response.content)
                temp_pdf_path = temp_pdf.name

            # Extract title from URL
            title = url.split('/')[-1].replace('.pdf', '').replace('_', ' ')
            
            # Get OCR mode setting
            ocr_mode = self.config.get("ocr_mode", "local_first")

            try:
                # Cloud AI direct mode
                if ocr_mode == "cloud_direct":
                    self.set_status("🤖 Processing PDF with Cloud AI...")
                    web_text_type = self.config.get("ocr_text_type", "printed")
                    success, result = self._process_pdf_with_cloud_ai(temp_pdf_path, title, text_type=web_text_type)
                    if success:
                        self.root.after(0, self._handle_web_ocr_result, True, result, title, url)
                    else:
                        self.set_status(f"⚠️ Cloud AI failed: {result}")
                        self.root.after(0, lambda: messagebox.showwarning(
                            "Cloud AI Failed",
                            f"Cloud AI processing failed:\n{result}\n\n"
                            f"You can try switching to 'Local first' mode in OCR Settings."
                        ))
                        self.root.after(0, self._handle_web_ocr_result, False, result, title, url)
                    return
                
                # Local first mode - use smart extraction with Cloud AI fallback
                self.set_status("🔍 Processing PDF with OCR...")
                provider = self.provider_var.get()
                model = self.model_var.get()
                api_key = self.config.get("keys", {}).get(provider, "")
                all_api_keys = self.config.get("keys", {})
                
                success, result, method = get_ocr().extract_text_from_pdf_smart(
                    filepath=temp_pdf_path,
                    language=self.config.get("ocr_language", "eng"),
                    quality=self.config.get("ocr_quality", "balanced"),
                    provider=provider,
                    model=model,
                    api_key=api_key,
                    all_api_keys=all_api_keys,
                    progress_callback=self.set_status,
                    force_cloud=False
                )
                
                if success:
                    if method == 'cloud_direct':
                        self.set_status(f"✅ PDF processed via Cloud AI (local conversion failed)")
                    self.root.after(0, self._handle_web_ocr_result, True, result, title, url)
                else:
                    self.root.after(0, self._handle_web_ocr_result, False, result, title, url)
            finally:
                # Clean up temp file
                try:
                    os.remove(temp_pdf_path)
                except:
                    pass

        except Exception as e:
            title = url.split('/')[-1] if '/' in url else url
            self.root.after(0, self._handle_web_ocr_result, False, str(e), title, url)

    def _handle_web_ocr_result(self, success, result, title, url):
        """Handle the result of OCR processing for web PDF"""
        self.processing = False
        self.process_btn.config(state=tk.NORMAL)

        if success:
            self.current_entries = result
            self.current_document_source = url
            self.current_document_type = "web_pdf_ocr"

            doc_id = add_document_to_library(
                doc_type="web_pdf_ocr",
                source=url,
                title=title,
                entries=self.current_entries,
                document_class="source",
                metadata={
                    "ocr_language": self.config.get("ocr_language", "eng"),
                    "ocr_quality": self.config.get("ocr_quality", "balanced")
                }
            )
            # ✅ FIX: Save old thread BEFORE changing document ID
            if self.thread_message_count > 0 and self.current_document_id:
                self.save_current_thread()
            
            # Clear thread manually
            self.current_thread = []
            self.thread_message_count = 0
            self.update_thread_status()
            
            # NOW change the document ID
            self.current_document_id = doc_id
            # Get document class and metadata from library
            doc = get_document_by_id(doc_id)
            if doc:
                self.current_document_class = doc.get("document_class", "source")
                self.current_document_metadata = doc.get("metadata", {})
                # CRITICAL FIX: Add title to metadata if not already there
                if 'title' not in self.current_document_metadata and 'title' in doc:
                    self.current_document_metadata['title'] = doc['title']
            else:
                self.current_document_class = "source"
                self.current_document_metadata = {}

            # Get document class and metadata from library
            doc = get_document_by_id(doc_id)
            if doc:
                self.current_document_class = doc.get("document_class", "source")
                self.current_document_metadata = doc.get("metadata", {})
                # CRITICAL FIX: Add title to metadata if not already there
                if 'title' not in self.current_document_metadata and 'title' in doc:
                    self.current_document_metadata['title'] = doc['title']
            else:
                self.current_document_class = "source"
                self.current_document_metadata = {}

            self.current_document_text = entries_to_text(self.current_entries, timestamp_interval=self.config.get("timestamp_interval", "every_segment"))

            self.set_status(f"✅ OCR completed: {title}")
            self.refresh_library()
            
            # Update button states
            self.update_button_states()
        else:
            self.set_status(f"❌ OCR Error: {result}")
            messagebox.showerror("OCR Error", result)

    """
    REPLACE THE _handle_web_result METHOD IN Main.py
    Location: Around line 1145
    Find the existing _handle_web_result method and replace it entirely with this version
    """

    def _handle_web_result(self, success, result, title, doc_type, web_metadata=None):
        """Handle the result of web URL fetching"""
        self.processing = False
        self.process_btn.config(state=tk.NORMAL)

        if success:
            self.current_entries = result
            self.current_document_source = self.web_url_var.get().strip()
            self.current_document_type = doc_type

            # Build metadata including published_date if available
            doc_metadata = {
                "source": "web",
                "title": title,
                "fetched": datetime.datetime.now().isoformat() + 'Z'
            }
            # Add published_date from web page if available
            if web_metadata and web_metadata.get('published_date'):
                doc_metadata['published_date'] = web_metadata['published_date']

            doc_id = add_document_to_library(
                doc_type=doc_type,
                source=self.current_document_source,
                title=title,
                entries=self.current_entries,
                document_class="source",
                metadata=doc_metadata
            )
            # ✅ FIX: Save old thread BEFORE changing document ID
            if self.thread_message_count > 0 and self.current_document_id:
                self.save_current_thread()
            
            # Clear thread manually
            self.current_thread = []
            self.thread_message_count = 0
            self.update_thread_status()
            
            # NOW change the document ID
            self.current_document_id = doc_id
            
            # Load saved thread for NEW document
            self.load_saved_thread()
            # Get document class and metadata from library
            doc = get_document_by_id(doc_id)
            if doc:
                self.current_document_class = doc.get("document_class", "source")
                self.current_document_metadata = doc.get("metadata", {})
                # CRITICAL FIX: Add title to metadata if not already there
                if 'title' not in self.current_document_metadata and 'title' in doc:
                    self.current_document_metadata['title'] = doc['title']
            else:
                self.current_document_class = "source"
                self.current_document_metadata = {}

            self.current_document_text = entries_to_text(self.current_entries,
                                                         timestamp_interval=self.config.get("timestamp_interval",
                                                                                            "every_segment"))

            self.set_status("✅ Document loaded - Select prompt and click Run")
            self.refresh_library()
            
            # Update button states
            self.update_button_states()

        elif result == "SCANNED_PDF":
            # Handle scanned PDF from web URL
            if messagebox.askyesno("OCR Required",
                                   f"The PDF at this URL appears to be scanned.\n\n" +
                                   "Would you like to download and process it with OCR?\n\n" +
                                   "Note: This may take a few minutes."):
                self.process_web_pdf_with_ocr()
            else:
                self.set_status("Cancelled OCR processing")

        elif result == "NOT_A_VIDEO":
            # URL doesn't contain a video - offer paste fallback
            url = self.web_url_var.get().strip()
            self.set_status(f"❌ Error: No meaningful content found")
            response = messagebox.askyesno(
                "No Content Found",
                "No text content found on this page.\n\n"
                "This page doesn't contain paragraphs of text or a supported video.\n\n"
                "Would you like to paste the content manually instead?"
            )
            if response:
                self._show_paste_fallback_dialog(
                    url=url,
                    source_type="web"
                )

        elif result == "No meaningful content found":
            # This might be a video page - try video extraction or paste fallback
            url = self.web_url_var.get().strip()

            # Create custom dialog with three options
            dialog = tk.Toplevel(self.root)
            dialog.title("No Text Content Found")
            dialog.geometry("450x220")
            dialog.transient(self.root)
            dialog.grab_set()
            
            # Center on parent
            dialog.update_idletasks()
            x = self.root.winfo_x() + (self.root.winfo_width() - 450) // 2
            y = self.root.winfo_y() + (self.root.winfo_height() - 220) // 2
            dialog.geometry(f"+{x}+{y}")
            
            main_frame = ttk.Frame(dialog, padding=20)
            main_frame.pack(fill=tk.BOTH, expand=True)
            
            ttk.Label(main_frame, text="This page doesn't contain readable text.",
                      font=('Arial', 10, 'bold')).pack(anchor=tk.W, pady=(0, 10))
            
            ttk.Label(main_frame, text=(
                "Choose an option:\n\n"
                "• Try Video - Attempt to download and transcribe video content\n"
                "• Paste Manually - Copy content from browser and paste it here"
            ), font=('Arial', 9), wraplength=400).pack(anchor=tk.W, pady=(0, 15))
            
            button_frame = ttk.Frame(main_frame)
            button_frame.pack(fill=tk.X, pady=(10, 0))
            
            def on_try_video():
                dialog.destroy()
                self.process_web_video()
            
            def on_paste():
                dialog.destroy()
                self._show_paste_fallback_dialog(url=url, source_type="web")
            
            def on_cancel():
                dialog.destroy()
                self.set_status("Cancelled")
            
            ttk.Button(button_frame, text="🎥 Try Video", command=on_try_video, width=14).pack(side=tk.LEFT, padx=(0, 5))
            ttk.Button(button_frame, text="📋 Paste Manually", command=on_paste, width=16).pack(side=tk.LEFT, padx=5)
            ttk.Button(button_frame, text="Cancel", command=on_cancel, width=10).pack(side=tk.RIGHT)
            
            dialog.protocol("WM_DELETE_WINDOW", on_cancel)
        else:
            # Generic error - offer paste fallback option
            url = self.web_url_var.get().strip()
            self.set_status(f"❌ Error: {result}")
            
            # Check if this looks like an access/blocking issue
            access_keywords = ['403', '401', 'forbidden', 'blocked', 'access denied', 
                              'paywall', 'subscribe', 'login required', 'restricted']
            is_access_issue = any(kw in str(result).lower() for kw in access_keywords)
            
            if is_access_issue:
                # Show paste fallback dialog for access issues
                self._show_paste_fallback_dialog(
                    url=url,
                    source_type="web"
                )
            else:
                # Regular error - show message box but mention paste option
                response = messagebox.askyesno(
                    "Fetch Error",
                    f"{result}\n\n"
                    f"Would you like to paste the content manually instead?"
                )
                if response:
                    self._show_paste_fallback_dialog(
                        url=url,
                        source_type="web"
                    )

    def view_processed_outputs(self, doc_id: str, doc_title: str):
        """Show all processed outputs for a document"""
        outputs = get_processed_outputs_for_document(doc_id)

        if not outputs:
            messagebox.showinfo("No Outputs", f"No processed outputs found for:\n{doc_title}")
            return

        outputs_window = tk.Toplevel(self.root)
        outputs_window.title(f"Processed Outputs - {doc_title}")
        outputs_window.geometry("800x600")
        self.apply_window_style(outputs_window)

        # Header
        header_frame = ttk.Frame(outputs_window, padding=10)
        header_frame.pack(fill=tk.X)
        ttk.Label(header_frame, text=f"📚 Processed Outputs", font=('Arial', 14, 'bold')).pack(side=tk.LEFT)
        ttk.Label(header_frame, text=f"({len(outputs)} saved)", font=('Arial', 10)).pack(side=tk.LEFT, padx=10)

        # Document info
        info_frame = ttk.Frame(outputs_window, padding=(10, 0))
        info_frame.pack(fill=tk.X)
        ttk.Label(info_frame, text=f"Source: {doc_title}", font=('Arial', 9, 'italic')).pack(anchor=tk.W)

        # List of outputs
        list_frame = ttk.LabelFrame(outputs_window, text="Saved Outputs", padding=10)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Scrollable listbox with details
        outputs_listbox = tk.Listbox(list_frame, height=10, font=('Arial', 9))
        outputs_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=outputs_listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        outputs_listbox.config(yscrollcommand=scrollbar.set)

        # Populate list
        for output in outputs:
            timestamp = datetime.datetime.fromisoformat(output['timestamp']).strftime("%Y-%m-%d %H:%M")
            display = f"[{timestamp}] {output['prompt_name']} ({output['provider']} - {output['model']})"
            outputs_listbox.insert(tk.END, display)

        # Preview frame
        preview_frame = ttk.LabelFrame(outputs_window, text="Preview", padding=10)
        preview_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        preview_text = scrolledtext.ScrolledText(preview_frame, wrap=tk.WORD, height=8, font=('Arial', 10))
        preview_text.pack(fill=tk.BOTH, expand=True)
        preview_text.config(state=tk.DISABLED)

        # Selection handler
        def on_output_select(event):
            selection = outputs_listbox.curselection()
            if not selection:
                return

            idx = selection[0]
            output = outputs[idx]

            preview_text.config(state=tk.NORMAL)
            preview_text.delete('1.0', tk.END)

            # Show metadata
            preview_text.insert(tk.END, f"Timestamp: {output['timestamp']}\n")
            preview_text.insert(tk.END, f"Prompt: {output['prompt_name']}\n")
            preview_text.insert(tk.END, f"Model: {output['provider']} - {output['model']}\n")
            if output.get('notes'):
                preview_text.insert(tk.END, f"Notes: {output['notes']}\n")
            preview_text.insert(tk.END, f"\n{'=' * 50}\n\n")
            preview_text.insert(tk.END, output['preview'])

            preview_text.config(state=tk.DISABLED)

        outputs_listbox.bind('<<ListboxSelect>>', on_output_select)

        # Select first item by default
        if outputs:
            outputs_listbox.selection_set(0)
            on_output_select(None)

        # Button frame
        btn_frame = ttk.Frame(outputs_window, padding=10)
        btn_frame.pack(fill=tk.X)

        def export_output():
            selection = outputs_listbox.curselection()
            if not selection:
                messagebox.showwarning("No Selection", "Please select an output to save")
                return

            idx = selection[0]
            output = outputs[idx]
            full_text = load_processed_output(output['id'])

            if not full_text:
                messagebox.showerror("Error", "Could not load output text")
                return

            file_path = filedialog.asksaveasfilename(
                defaultextension=".txt",
                filetypes=[("Text files", "*.txt"), ("RTF files", "*.rtf"), ("All files", "*.*")],
                initialfile=f"{output['prompt_name']}_{output['timestamp'][:10]}"
            )

            if file_path:
                try:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(full_text)
                    messagebox.showinfo("Success", f"Saved to:\n{file_path}")
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to save: {str(e)}")

        def delete_output():
            selection = outputs_listbox.curselection()
            if not selection:
                messagebox.showwarning("No Selection", "Please select an output to delete")
                return

            idx = selection[0]
            output = outputs[idx]

            if messagebox.askyesno("Confirm Delete",
                                   f"Delete this output?\n\n{output['prompt_name']}\n{output['timestamp']}"):
                if delete_processed_output(doc_id, output['id']):
                    messagebox.showinfo("Success", "Output deleted")
                    outputs_window.destroy()
                    self.view_processed_outputs(doc_id, doc_title)  # Refresh
                else:
                    messagebox.showerror("Error", "Failed to delete output")

        # View Full Output button removed - use Thread Viewer instead
        ttk.Button(btn_frame, text="Save", command=export_output).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Delete", command=delete_output).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Close", command=outputs_window.destroy).pack(side=tk.RIGHT, padx=5)

    def delete_from_library(self, doc_id: str, doc_title: str):
        """Delete a document and all its processed outputs from the library"""
        outputs = get_processed_outputs_for_document(doc_id)
        output_count = len(outputs)

        msg = f"Delete this document from the library?\n\n{doc_title}"
        if output_count > 0:
            msg += f"\n\nThis will also delete {output_count} processed output(s)."

        if not messagebox.askyesno("Confirm Delete", msg):
            return

        # Delete all processed outputs
        for output in outputs:
            delete_processed_output(doc_id, output['id'])

        # Delete document entries file
        entries_file = os.path.join(DATA_DIR, f"doc_{doc_id}_entries.json")
        if os.path.exists(entries_file):
            try:
                os.remove(entries_file)
            except Exception:
                pass

        # Remove from library
        library = load_library()
        library["documents"] = [doc for doc in library["documents"] if doc.get("id") != doc_id]
        save_library(library)

        # Refresh library display
        self.refresh_library()

        messagebox.showinfo("Success", "Document deleted from library")

    def open_bulk_processing(self):
        """Open the bulk processing window."""
        
        # Check if an embedding model is selected (can't do chat completions)
        current_model = self.model_var.get().lower()
        embedding_keywords = ['embed', 'embedding', 'nomic', 'bge', 'e5-', 'gte-']
        is_embedding_model = any(keyword in current_model for keyword in embedding_keywords)
        
        if is_embedding_model:
            from tkinter import messagebox
            result = messagebox.askokcancel(
                "Embedding Model Selected",
                f"The currently selected model '{self.model_var.get()}' appears to be an embedding model, "
                f"which cannot process prompts.\n\n"
                f"For bulk processing, please select a chat/instruct model such as:\n"
                f"• Qwen2.5-Instruct\n"
                f"• Llama-3-Instruct\n"
                f"• Mistral-Instruct\n"
                f"• DeepSeek-Chat\n\n"
                f"Click OK to open Bulk Processing anyway, or Cancel to go back and change the model."
            )
            if not result:
                return
        
        def process_single_item(url_or_path: str, status_callback) -> tuple:
            """
            Process a single URL or file path.
            Returns: (success: bool, result_or_error: str, title: Optional[str])
            """
            try:
                # Detect type and process accordingly
                url_or_path = url_or_path.strip()
                
                # Check if it's a file
                if os.path.isfile(url_or_path):
                    status_callback(f"Processing file: {os.path.basename(url_or_path)}")
                    ext = os.path.splitext(url_or_path)[1].lower()
                    
                    # 🆕 NEW: Handle .url files (Windows Internet Shortcuts)
                    if ext == '.url':
                        # Extract the actual URL from the .url file
                        try:
                            with open(url_or_path, 'r', encoding='utf-8', errors='ignore') as f:
                                content = f.read()
                            # Parse the URL from [InternetShortcut] format
                            import re
                            url_match = re.search(r'URL=(.+)', content, re.IGNORECASE)
                            if url_match:
                                extracted_url = url_match.group(1).strip()
                                status_callback(f"Extracted URL: {extracted_url[:50]}...")
                                # Recursively process the extracted URL
                                return process_single_item(extracted_url, status_callback)
                            else:
                                return False, "Could not extract URL from .url file", None
                        except Exception as e:
                            return False, f"Error reading .url file: {str(e)}", None
                    
                    # Check for audio/video files - skip in bulk mode (need transcription)
                    if ext in ('.mp3', '.wav', '.m4a', '.ogg', '.flac', '.aac', '.wma', '.opus', '.mp4', '.avi', '.mov'):
                        return False, "Audio/video files require transcription (not supported in bulk mode yet)", None
                    
                    # Use document fetcher for files
                    doc_fetcher = get_doc_fetcher()
                    success, result, title, doc_type = doc_fetcher.fetch_local_file(url_or_path)
                    
                    if success:
                        # Result is a list of entries, convert to text
                        if isinstance(result, list):
                            text = doc_fetcher.legacy_entries_to_text(result, include_timestamps=False)
                        else:
                            text = str(result)
                        return True, text, title or os.path.basename(url_or_path)
                    
                    elif result == "SCANNED_PDF":
                        # Handle scanned PDF with OCR
                        status_callback(f"OCR processing: {os.path.basename(url_or_path)}...")
                        try:
                            ocr_handler = get_ocr()
                            
                            # Check OCR availability
                            available, error_msg, _ = ocr_handler.check_ocr_availability()
                            if not available:
                                return False, f"OCR not available: {error_msg}", None
                            
                            # Process with smart extraction (includes Cloud AI fallback)
                            provider = self.provider_var.get()
                            model = self.model_var.get()
                            api_key = self.config.get("keys", {}).get(provider, "")
                            all_api_keys = self.config.get("keys", {})
                            
                            success, result, method = ocr_handler.extract_text_from_pdf_smart(
                                filepath=url_or_path,
                                language=self.config.get("ocr_language", "eng"),
                                quality=self.config.get("ocr_quality", "balanced"),
                                provider=provider,
                                model=model,
                                api_key=api_key,
                                all_api_keys=all_api_keys,
                                progress_callback=status_callback,
                                force_cloud=False
                            )
                            
                            if success:
                                text = doc_fetcher.legacy_entries_to_text(result, include_timestamps=False)
                                return True, text, os.path.basename(url_or_path)
                            else:
                                return False, f"OCR failed: {result}", None
                                
                        except Exception as e:
                            return False, f"OCR failed: {str(e)}", None
                    else:
                        error_msg = str(result) if result else "Could not extract text from file"
                        return False, error_msg, None
                
                # Check if it's a YouTube URL
                from youtube_utils import is_youtube_url, get_youtube_transcript
                if is_youtube_url(url_or_path):
                    status_callback("Fetching YouTube transcript...")
                    result = get_youtube_transcript(url_or_path, status_callback=status_callback)
                    if result and result.get('text'):
                        return True, result['text'], result.get('title', 'YouTube Video')
                    else:
                        return False, "Could not fetch YouTube transcript", None
                
                # Check if it's a Substack URL
                from substack_utils import is_substack_url, fetch_substack_content
                if is_substack_url(url_or_path):
                    status_callback("Fetching Substack content...")
                    result = fetch_substack_content(url_or_path, status_callback=status_callback)
                    if result and result.get('text'):
                        return True, result['text'], result.get('title', 'Substack Article')
                    elif result and result.get('audio_file'):
                        # Has audio but needs transcription - skip for now
                        return False, "Audio content requires transcription (not supported in bulk mode yet)", None
                    else:
                        return False, result.get('error', 'Could not fetch Substack content'), None
                
                # Assume it's a web URL
                status_callback("Fetching web content...")
                doc_fetcher = get_doc_fetcher()
                success, result, title, doc_type, web_metadata = doc_fetcher.fetch_web_url(url_or_path)
                if success:
                    # Result is a list of entries, convert to text
                    if isinstance(result, list):
                        text = doc_fetcher.legacy_entries_to_text(result, include_timestamps=False)
                    else:
                        text = str(result)
                    return True, text, title or url_or_path
                else:
                    return False, str(result) if result else "Could not fetch web content", None
                    
            except Exception as e:
                return False, str(e), None
        
        def get_current_settings() -> dict:
            """Get current AI provider/model/prompt settings."""
            return {
                'provider': self.provider_var.get(),
                'model': self.model_var.get(),
                'prompt_name': self.prompt_combo.get() if hasattr(self, 'prompt_combo') else 'Default',
                'prompt_text': self.prompt_text.get('1.0', tk.END).strip() if hasattr(self, 'prompt_text') else ''
            }
        
        def save_to_library(title: str, content: str, source: str, doc_class: str = 'source') -> str:
            """Save processed content to the document library.
            
            Args:
                title: Document title
                content: Document content
                source: Source URL or file path
                doc_class: 'source' for original documents, 'product' for AI responses
                
            Returns:
                Document ID if successful, None otherwise
            """
            try:
                # Create entries from content with appropriate location tag
                if doc_class == 'product':
                    location_tag = 'AI Response'
                else:
                    location_tag = 'Bulk Imported'
                entries = [{'text': content, 'start': 0, 'location': location_tag}]
                
                # Use different doc_type for source vs product to ensure unique IDs
                if doc_class == 'product':
                    doc_type = "bulk_ai_response"
                else:
                    doc_type = "bulk_import"
                
                # Add to document library
                doc_id = add_document_to_library(
                    doc_type=doc_type,
                    source=source,
                    title=title,
                    entries=entries,
                    document_class=doc_class,
                    metadata={
                        "imported_via": "bulk_processing",
                        "fetched": datetime.datetime.now().isoformat() + 'Z'
                    }
                )
                return doc_id
            except Exception as e:
                print(f"Failed to save to library: {e}")
                return None
        
        def ai_process_callback(text: str, title: str, status_callback) -> tuple:
            """Run AI analysis on extracted text.
            
            Args:
                text: The extracted document text
                title: Document title (for logging)
                status_callback: Function to report status updates
                
            Returns:
                (success: bool, result_or_error: str)
            """
            try:
                # Get current prompt
                prompt = self.prompt_text.get('1.0', tk.END).strip()
                if not prompt:
                    return False, "No prompt configured"
                
                # Get current settings
                provider = self.provider_var.get()
                model = self.model_var.get()
                api_key = self.api_key_var.get()
                
                status_callback(f"Sending to {provider}/{model}...")
                
                # Build messages
                messages = [
                    {"role": "system", "content": "You are a helpful AI assistant analyzing documents."},
                    {"role": "user", "content": f"{prompt}\n\n{text}"}
                ]
                
                # Call AI
                success, result = get_ai().call_ai_provider(
                    provider=provider,
                    model=model,
                    messages=messages,
                    api_key=api_key,
                    document_title=title,
                    prompt_name=self.prompt_combo.get() if hasattr(self, 'prompt_combo') else 'Bulk Processing'
                )
                
                return success, result
                
            except Exception as e:
                return False, f"AI processing error: {str(e)}"
        
        # Open the bulk processing window with all callbacks
        # Note: ai_process_callback is set to None so bulk import only fetches and saves
        # AI analysis can be done later via the main interface or attachments
        open_bulk_processing(
            self.root,
            process_single_item,
            get_current_settings,
            save_to_library,
            None  # No AI processing - just fetch and add to library
        )

    def open_add_sources(self):
        """
        Open the unified Add Sources dialog.
        
        Allows users to add sources to either:
        - Documents Library (permanent)
        - Prompt Context (temporary, for multi-document analysis)
        """
        def get_current_settings():
            return {
                'provider': self.provider_var.get(),
                'model': self.model_var.get(),
                'prompt_name': self.prompt_combo.get() if hasattr(self, 'prompt_combo') else 'Default',
                'prompt_text': self.prompt_text.get('1.0', tk.END).strip() if hasattr(self, 'prompt_text') else ''
            }
        
        def process_single_item(url_or_path: str, status_callback) -> tuple:
            """
            Process a single URL or file path.
            Returns: (success: bool, result_or_error: str, title: Optional[str])
            """
            try:
                url_or_path = url_or_path.strip()
                
                # Check if it's a file
                if os.path.isfile(url_or_path):
                    status_callback(f"Processing file: {os.path.basename(url_or_path)}")
                    ext = os.path.splitext(url_or_path)[1].lower()
                    
                    # Handle .url files (Windows Internet Shortcuts)
                    if ext == '.url':
                        try:
                            with open(url_or_path, 'r', encoding='utf-8', errors='ignore') as f:
                                content = f.read()
                            import re
                            url_match = re.search(r'URL=(.+)', content, re.IGNORECASE)
                            if url_match:
                                extracted_url = url_match.group(1).strip()
                                status_callback(f"Extracted URL: {extracted_url[:50]}...")
                                return process_single_item(extracted_url, status_callback)
                            else:
                                return False, "Could not extract URL from .url file", None
                        except Exception as e:
                            return False, f"Error reading .url file: {str(e)}", None
                    
                    # Check for audio/video files - skip (need transcription)
                    if ext in ('.mp3', '.wav', '.m4a', '.ogg', '.flac', '.aac', '.wma', '.opus', '.mp4', '.avi', '.mov'):
                        return False, "Audio/video files require transcription (use Load button instead)", None
                    
                    # Use document fetcher for files
                    doc_fetcher = get_doc_fetcher()
                    success, result, title, doc_type = doc_fetcher.fetch_local_file(url_or_path)
                    
                    if success:
                        if isinstance(result, list):
                            text = doc_fetcher.legacy_entries_to_text(result, include_timestamps=False)
                        else:
                            text = str(result)
                        return True, text, title or os.path.basename(url_or_path)
                    
                    elif result == "SCANNED_PDF":
                        status_callback(f"OCR processing: {os.path.basename(url_or_path)}...")
                        try:
                            ocr_handler = get_ocr()
                            available, error_msg, _ = ocr_handler.check_ocr_availability()
                            if not available:
                                return False, f"OCR not available: {error_msg}", None
                            
                            # Process with smart extraction (includes Cloud AI fallback)
                            provider = self.provider_var.get()
                            model = self.model_var.get()
                            api_key = self.config.get("keys", {}).get(provider, "")
                            all_api_keys = self.config.get("keys", {})
                            
                            success, result, method = ocr_handler.extract_text_from_pdf_smart(
                                filepath=url_or_path,
                                language=self.config.get("ocr_language", "eng"),
                                quality=self.config.get("ocr_quality", "balanced"),
                                provider=provider,
                                model=model,
                                api_key=api_key,
                                all_api_keys=all_api_keys,
                                progress_callback=status_callback,
                                force_cloud=False
                            )
                            
                            if success:
                                text = doc_fetcher.legacy_entries_to_text(result, include_timestamps=False)
                                return True, text, os.path.basename(url_or_path)
                            else:
                                return False, f"OCR failed: {result}", None
                        except Exception as e:
                            return False, f"OCR failed: {str(e)}", None
                    else:
                        error_msg = str(result) if result else "Could not extract text from file"
                        return False, error_msg, None
                
                # Check if it's a YouTube URL
                from youtube_utils import is_youtube_url, get_youtube_transcript
                if is_youtube_url(url_or_path):
                    status_callback("Fetching YouTube transcript...")
                    result = get_youtube_transcript(url_or_path, status_callback=status_callback)
                    if result and result.get('text'):
                        return True, result['text'], result.get('title', 'YouTube Video')
                    else:
                        return False, "Could not fetch YouTube transcript", None
                
                # Check if it's a Substack URL
                from substack_utils import is_substack_url, fetch_substack_content
                if is_substack_url(url_or_path):
                    status_callback("Fetching Substack content...")
                    result = fetch_substack_content(url_or_path, status_callback=status_callback)
                    if result and result.get('text'):
                        return True, result['text'], result.get('title', 'Substack Article')
                    elif result and result.get('audio_file'):
                        return False, "Audio content requires transcription", None
                    else:
                        return False, result.get('error', 'Could not fetch Substack content'), None
                
                # Try as generic web URL
                if url_or_path.startswith(('http://', 'https://')):
                    status_callback("Fetching web content...")
                    try:
                        doc_fetcher = get_doc_fetcher()
                        success, result, title = doc_fetcher.fetch_from_url(url_or_path)
                        if success:
                            if isinstance(result, list):
                                text = doc_fetcher.legacy_entries_to_text(result, include_timestamps=False)
                            else:
                                text = str(result)
                            return True, text, title or url_or_path
                        else:
                            return False, result, None
                    except Exception as e:
                        return False, f"Error fetching URL: {str(e)}", None
                
                return False, "Unknown source type", None
                
            except Exception as e:
                return False, str(e), None
        
        def save_to_library(title: str, content: str, source: str, doc_class: str = 'source') -> Optional[str]:
            """Save content to the document library."""
            try:
                if doc_class == 'product':
                    location_tag = 'AI Response'
                else:
                    location_tag = 'Added via Sources Dialog'
                entries = [{'text': content, 'start': 0, 'location': location_tag}]
                
                if doc_class == 'product':
                    doc_type = "ai_response"
                else:
                    doc_type = "imported"
                
                doc_id = add_document_to_library(
                    doc_type=doc_type,
                    source=source,
                    title=title,
                    entries=entries,
                    document_class=doc_class,
                    metadata={
                        "imported_via": "sources_dialog",
                        "fetched": datetime.datetime.now().isoformat() + 'Z'
                    }
                )
                return doc_id
            except Exception as e:
                print(f"Failed to save to library: {e}")
                return None
        
        def on_complete():
            """Called when sources dialog closes with changes."""
            self.update_add_sources_button()
        
        # Open the unified sources dialog
        open_sources_dialog(
            parent=self.root,
            process_callback=process_single_item,
            get_settings_callback=get_current_settings,
            save_to_library_callback=save_to_library,
            ai_process_callback=None,
            attachment_manager=self.attachment_manager,
            mode="unified",
            status_callback=self.set_status,
            get_provider_callback=lambda: self.provider_var.get(),
            on_complete_callback=on_complete
        )

    def update_add_sources_button(self):
        """Update the Add Sources button to show attachment count."""
        # Add sources button removed - using multi-line input

    def open_library_window(self):
        """Open Documents Library with tree structure"""
        try:
            # Debug: Check if files exist
            import os
            import sys
            
            project_dir = os.path.dirname(os.path.abspath(__file__))
            tree_base_path = os.path.join(project_dir, "tree_manager_base.py")
            doc_tree_path = os.path.join(project_dir, "document_tree_manager.py")
            
            print(f"\n{'='*60}")
            print(f"DEBUG: Opening Documents Library")
            print(f"Project dir: {project_dir}")
            print(f"tree_manager_base.py exists: {os.path.exists(tree_base_path)}")
            print(f"document_tree_manager.py exists: {os.path.exists(doc_tree_path)}")
            print(f"Python path: {sys.path[:3]}")
            print(f"{'='*60}\n")
            
            from document_tree_manager import open_document_tree_manager
            from config import LIBRARY_PATH
            
            # Callback to load document in main window
            def load_document_callback(doc_id):
                """Load a document from the library into the main window"""
                # This is called when user double-clicks or clicks "Load Document"
                from document_library import get_document_by_id, load_document_entries
                
                doc = get_document_by_id(doc_id)
                if not doc:
                    messagebox.showerror("Error", "Document not found")
                    return
                
                doc_title = doc.get('title', 'Unknown Document')
                
                # Check if a viewer is already open and ask user what to do
                viewer_action = self._check_viewer_open_action(doc_title)
                if viewer_action == 'cancel':
                    return  # User cancelled
                
                # Store the action for later use when auto-opening viewer
                force_new_viewer = (viewer_action == 'side_by_side')
                
                # If replacing, close ALL existing viewers first
                if viewer_action == 'replace':
                    if hasattr(self, '_thread_viewer_windows') and self._thread_viewer_windows:
                        for viewer in self._thread_viewer_windows[:]:  # Copy list
                            try:
                                if viewer.window.winfo_exists():
                                    viewer.window.destroy()
                            except:
                                pass
                        self._thread_viewer_windows.clear()
                
                # Check for active thread before loading
                if not self.check_active_thread_before_load(doc_title):
                    return  # User cancelled
                
                # Load the document
                if doc.get('type') == 'conversation_thread':
                    # Thread document
                    self.current_document_source = doc['source']
                    self.current_document_type = doc['type']
                    self.current_document_id = doc_id
                    self.current_document_class = doc.get("document_class", "thread")
                    self.current_document_metadata = doc.get("metadata", {})
                    if 'title' not in self.current_document_metadata:
                        self.current_document_metadata['title'] = doc_title
                    
                    # === CRITICAL: Load source document entries for processing ===
                    # Thread documents need their parent source's entries for follow-ups
                    parent_doc_id = self.current_document_metadata.get('parent_document_id') or \
                                   self.current_document_metadata.get('original_document_id')
                    
                    if parent_doc_id:
                        parent_entries = load_document_entries(parent_doc_id)
                        if parent_entries:
                            self.current_entries = parent_entries
                            print(f"📄 Loaded {len(parent_entries)} entries from parent source document")
                            # Also get source text
                            parent_doc = get_document_by_id(parent_doc_id)
                            if parent_doc:
                                from utils import entries_to_text, entries_to_text_with_speakers
                                parent_type = parent_doc.get('type', 'text')
                                if parent_type == 'audio_transcription':
                                    self.current_document_text = entries_to_text_with_speakers(
                                        parent_entries,
                                        timestamp_interval=self.config.get("timestamp_interval", "every_segment")
                                    )
                                else:
                                    self.current_document_text = entries_to_text(parent_entries)
                        else:
                            self.current_entries = []
                            self.current_document_text = doc.get("text", "No conversation text available")
                            print(f"⚠️ Could not load entries from parent: {parent_doc_id}")
                    else:
                        self.current_entries = []
                        self.current_document_text = doc.get("text", "No conversation text available")
                        print(f"⚠️ Thread document has no parent_document_id in metadata")
                    
                    self.clear_thread()
                    conversation_thread = doc.get("conversation_thread", [])
                    if conversation_thread:
                        self.current_thread = conversation_thread
                        self.thread_message_count = len([m for m in conversation_thread if m.get("role") == "user"])
                        self.update_thread_status()
                    
                    self.set_status(f"✅ Thread loaded ({self.thread_message_count} messages) | View Thread window opening")
                    
                    # Auto-open thread viewer for thread documents
                    # Use force_new_window if user chose side-by-side
                    # (capture force_new_viewer value at lambda creation time)
                    self.root.after(100, lambda fnw=force_new_viewer: self._show_thread_viewer(target_mode='conversation', force_new_window=fnw))
                else:
                    # Regular document
                    entries = load_document_entries(doc_id)
                    if entries:
                        self.current_entries = entries
                        self.current_document_source = doc['source']
                        self.current_document_type = doc['type']
                        
                        # Save old thread BEFORE changing document ID
                        if self.thread_message_count > 0 and self.current_document_id:
                            self.save_current_thread()
                        
                        self.current_thread = []
                        self.thread_message_count = 0
                        self.update_thread_status()
                        
                        self.current_document_id = doc_id
                        self.load_saved_thread()
                        
                        # Get document class and metadata
                        self.current_document_class = doc.get("document_class", "source")
                        self.current_document_metadata = doc.get("metadata", {})
                        if 'title' not in self.current_document_metadata:
                            self.current_document_metadata['title'] = doc_title
                        
                        # Convert entries to text
                        from utils import entries_to_text, entries_to_text_with_speakers
                        self.current_document_text = entries_to_text_with_speakers(
                            entries,
                            timestamp_interval=self.config.get("timestamp_interval", "every_segment")
                        ) if doc['type'] == "audio_transcription" else entries_to_text(entries)
                        
                        
                        # Update the View Source/Thread button state
                        self.update_view_button_state()
                        
                        # Debug output
                        print(f"📄 Source document loaded: thread_count={self.thread_message_count}, class={self.current_document_class}")
                        
                        # Set appropriate status based on document class
                        if self.current_document_class in ['response', 'product', 'processed_output']:
                            if self.thread_message_count > 0:
                                self.set_status(f"✅ Response loaded")
                            else:
                                self.set_status(f"✅ Response document loaded")
                        else:
                            self.set_status("✅ Source document loaded from library")
                        
                        # Auto-open viewer based on document type
                        # Use force_new_window if user chose side-by-side
                        # (capture force_new_viewer value at lambda creation time)
                        if self.thread_message_count > 0 and self.current_document_class in ['product', 'processed_output', 'response']:
                            # Has conversation - open in conversation mode
                            self.root.after(100, lambda fnw=force_new_viewer: self._show_thread_viewer(target_mode='conversation', force_new_window=fnw))
                        else:
                            # Source document - open in source mode
                            self.root.after(100, lambda fnw=force_new_viewer: self._show_thread_viewer(target_mode='source', force_new_window=fnw))
                    else:
                        messagebox.showerror("Error", "Could not load document entries")
            
            # Callback to add library documents as attachments for multi-document analysis
            def send_to_input_callback(doc_info_list: list):
                """Add selected library documents as attachments"""
                if not doc_info_list:
                    return
                
                from document_library import load_document_entries
                from utils import entries_to_text
                
                added_count = 0
                errors = []
                
                for doc_info in doc_info_list:
                    doc_id = doc_info.get('doc_id')
                    title = doc_info.get('title', 'Unknown')
                    
                    try:
                        # Load document content
                        entries = load_document_entries(doc_id)
                        if entries:
                            text = entries_to_text(entries)
                            if text and text.strip():
                                # Add as attachment
                                result = self.attachment_manager.add_from_library(doc_id, title, text)
                                if result.get('error'):
                                    errors.append(f"{title}: {result['error']}")
                                else:
                                    added_count += 1
                            else:
                                errors.append(f"{title}: No text content")
                        else:
                            errors.append(f"{title}: Could not load content")
                    except Exception as e:
                        errors.append(f"{title}: {str(e)}")
                
                # Update status
                if added_count > 0:
                    total = self.attachment_manager.get_attachment_count()
                    words = self.attachment_manager.get_total_words()
                    self.set_status(f"📎 Added {added_count} document(s) as attachments ({total} total, ~{words:,} words)")
                    
                    # Show confirmation
                    if errors:
                        messagebox.showinfo("Documents Added", 
                            f"Added {added_count} document(s) as attachments.\n\n"
                            f"Some documents had issues:\n" + "\n".join(f"• {e}" for e in errors[:5]))
                    else:
                        messagebox.showinfo("Documents Added", 
                            f"Added {added_count} document(s) as attachments.\n\n"
                            f"Total: {total} attachments (~{words:,} words)\n\n"
                            f"Now select a prompt and click 'Run' for multi-document analysis.")
                else:
                    messagebox.showwarning("No Documents Added", 
                        "Could not add any documents:\n\n" + "\n".join(f"• {e}" for e in errors[:5]))
            
            # Open the new tree-based Documents Library
            open_document_tree_manager(
                parent=self.root,
                library_path=LIBRARY_PATH,
                on_load_document=load_document_callback,
                on_send_to_input=send_to_input_callback,
                config=self.config
            )
            
        except ImportError as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"⚠️ ImportError opening Documents Library:")
            print(error_details)
            messagebox.showerror("Import Error", 
                f"Could not import Documents Library modules.\n\n"
                f"Error: {str(e)}\n\n"
                f"Files needed:\n"
                f"- document_tree_manager.py\n"
                f"- tree_manager_base.py\n\n"
                f"Check the console for full error details.")
        except Exception as e:
            import traceback
            print(f"❌ Error opening Documents Library: {e}")
            traceback.print_exc()
            messagebox.showerror("Error", f"Could not open Documents Library:\n\n{str(e)}")
    
    def process_document(self):
        print("🔧 DEBUG: process_document() called")
        if self.processing:
            print("❌ DEBUG: Already processing!")
            messagebox.showwarning("Warning", "Processing already in progress. Please wait or cancel.")
            return
        print("✅ DEBUG: Not currently processing")
        
        # Reset Run button highlight immediately and disable re-highlighting
        self._run_highlight_enabled = False
        if hasattr(self, 'process_btn'):
            self.process_btn.configure(style='TButton')
            self.root.update_idletasks()  # Force immediate UI update
        
        # Clear the input field and restore placeholder (document is already loaded)
        self.universal_input_entry.delete('1.0', 'end')
        self.placeholder_active = False  # Reset so update_placeholder will work
        self.update_placeholder()
        
        # Check if Thread Viewer is open and warn user about source vs summary
        if not self._check_viewer_source_warning():
            return  # User cancelled
        
        # 🆕 NEW: Smart context check - allow prompts without documents
        has_document = bool(self.current_document_text)
        has_attachments = (hasattr(self, 'attachment_manager') and 
                          self.attachment_manager.get_attachment_count() > 0)
        has_any_content = has_document or has_attachments
        
        # Get the prompt first to check if it's document-specific
        prompt = self.prompt_text.get('1.0', tk.END).strip()
        if not prompt:
            messagebox.showinfo("No Prompt", "Please enter or select a prompt first.")
            return
        
        # Check if prompt appears to be document-specific
        document_keywords = [
            'document', 'text', 'article', 'content', 'passage', 
            'summary', 'summarize', 'extract', 'analyze', 'review',
            'above', 'provided', 'following', 'attached', 'this file'
        ]
        prompt_lower = prompt.lower()
        is_document_specific = any(keyword in prompt_lower for keyword in document_keywords)
        
        # Smart warning system
        if not has_any_content:
            if is_document_specific:
                # Prompt mentions document-related terms but no document loaded
                response = messagebox.askyesno(
                    "No Document Loaded",
                    f"Your prompt mentions document-related content:\n\n"
                    f"\"{prompt[:100]}{'...' if len(prompt) > 100 else ''}\"\n\n"
                    f"But no document or attachments are loaded.\n\n"
                    f"💡 Tip: Load a document first, or rephrase your prompt for general conversation.\n\n"
                    f"Continue anyway without document context?",
                    icon='warning'
                )
                if not response:
                    print("❌ DEBUG: User chose not to continue without document")
                    return
                print("✅ DEBUG: User chose to continue without document")
            else:
                # Generic prompt, no document needed - just proceed
                print("✅ DEBUG: Generic prompt without document - proceeding")
        
        print(f"✅ DEBUG: Content status (document: {has_document}, attachments: {has_attachments})")
        
        if not self.model_var.get():
            print(f"❌ DEBUG: No model! model_var={self.model_var.get()}")
            messagebox.showerror("Error", "Please select an AI model.")
            return
        print(f"✅ DEBUG: Model: {self.model_var.get()}")
        
        # Ollama doesn't require an API key
        provider = self.provider_var.get()
        if provider != "Ollama (Local)" and not self.api_key_var.get():
            print(f"❌ DEBUG: No API key! api_key_var={bool(self.api_key_var.get())}")
            messagebox.showerror("Error", "Please enter an API key.")
            return
        print(f"✅ DEBUG: API key present (or Ollama - not required)")
        
        # 🆕 Check for local AI context limitations when using attachments
        if has_attachments:
            from attachment_handler import check_local_ai_context_warning
            
            # Calculate total words (main document + attachments)
            main_doc_words = len(self.current_document_text.split()) if self.current_document_text else 0
            attachment_words = self.attachment_manager.get_total_words()
            total_words = main_doc_words + attachment_words
            attachment_count = self.attachment_manager.get_attachment_count()
            
            warning = check_local_ai_context_warning(provider, total_words, attachment_count)
            if warning:
                response = messagebox.askyesno("Local AI Context Warning", warning)
                if not response:
                    print("❌ DEBUG: User cancelled due to local AI context warning")
                    return
        
        print("✅ DEBUG: Starting thread...")
        self.processing = True
        self.process_btn.config(state=tk.DISABLED)
        
        # Build status message that includes attachment count if any
        attachment_count = 0
        if hasattr(self, 'attachment_manager'):
            attachment_count = self.attachment_manager.get_attachment_count()
        
        # Check if using Local AI for more specific status message
        provider = self.provider_var.get()
        is_local_ai = provider == "Ollama (Local)"
        ai_label = "💻 Local AI" if is_local_ai else "AI"
        
        if not has_any_content:
            self.set_status(f"⚙️ Processing general query with {ai_label}...")
        elif attachment_count > 0:
            self.set_status(f"⚙️ Processing with {ai_label}: main document + {attachment_count} attachment{'s' if attachment_count != 1 else ''}...")
        else:
            self.set_status(f"⚙️ Processing with {ai_label}...")
        
        self.processing_thread = threading.Thread(target=self._process_document_thread)
        self.processing_thread.start()
        print(f"✅ DEBUG: Thread started, alive={self.processing_thread.is_alive()}")
        self.root.after(100, self.check_processing_thread)

    def _process_document_thread(self):
        prompt = self.prompt_text.get('1.0', tk.END).strip()
        self.current_prompt_text = prompt
        if not prompt:
            self.root.after(0, self._handle_process_result, False, "No prompt provided")
            return

        # 🆕 NEW: Check if we're processing attachments only (no main document)
        has_main_document = bool(self.current_entries)
        has_attachments = (hasattr(self, 'attachment_manager') and 
                          self.attachment_manager.get_attachment_count() > 0)
        
        # If no main document but have attachments, use simplified path
        if not has_main_document and has_attachments:
            # Skip chunking - just process attachments with prompt
            doc_title = "Attachments Only"
            prompt_name = "Custom Prompt"
            try:
                if hasattr(self, 'prompt_combo'):
                    prompt_name = self.prompt_combo.get() or "Custom Prompt"
            except:
                pass
            
            # Build messages (will include attachments)
            messages = self.build_threaded_messages(prompt)
            
            # Check if using Local AI
            is_local = self.provider_var.get() == "Ollama (Local)"
            ai_label = "💻 Local AI" if is_local else "AI"
            
            self.set_status(f"⚙️ Processing {self.attachment_manager.get_attachment_count()} attachments with {ai_label}...")
            success, result = get_ai().call_ai_provider(
                provider=self.provider_var.get(),
                model=self.model_var.get(),
                messages=messages,
                api_key=self.api_key_var.get(),
                document_title=doc_title,
                prompt_name=prompt_name
            )
            
            if not success:
                self.root.after(0, self._handle_process_result, False, result)
                return
            
            # Add to thread
            self.add_message_to_thread("user", prompt)
            self.add_message_to_thread("assistant", result)
            
            self.root.after(0, self._handle_process_result, True, result)
            return

        # Get chunk size setting
        chunk_size_setting = self.config.get("chunk_size", "medium")

        # Chunk the entries
        chunks = chunk_entries(self.current_entries, chunk_size_setting)

        # ============================================================
        # Get document title and prompt name for cost tracking
        # ============================================================
        doc_title = "Unknown Document"
        try:
            if hasattr(self, 'current_document_id') and self.current_document_id:
                from document_library import get_document_by_id
                doc = get_document_by_id(self.current_document_id)
                if doc:
                    doc_title = doc.get('title', 'Unknown Document')
        except Exception as e:
            print(f"Warning: Could not get document title: {e}")

        prompt_name = "Custom Prompt"
        try:
            if hasattr(self, 'prompt_combo'):
                prompt_name = self.prompt_combo.get()
                if not prompt_name:
                    prompt_name = "Custom Prompt"
        except Exception as e:
            print(f"Warning: Could not get prompt name: {e}")

        # ============================================================
        # SINGLE CHUNK PROCESSING (with threading support)
        # ============================================================
        if len(chunks) == 1:
            chunk_text = entries_to_text_with_speakers(
                chunks[0],
                timestamp_interval=self.config.get("timestamp_interval", "every_segment")
            ) if self.current_document_type == "audio_transcription" else entries_to_text(
                chunks[0],
                timestamp_interval=self.config.get("timestamp_interval", "every_segment")
            )

            # 🆕 MVP: Build messages with thread context
            messages = self.build_threaded_messages(prompt)

            # Build status message that includes attachment count if any
            attachment_count = 0
            if hasattr(self, 'attachment_manager'):
                attachment_count = self.attachment_manager.get_attachment_count()
            
            # Check if using Local AI
            is_local = self.provider_var.get() == "Ollama (Local)"
            ai_label = "💻 Local AI" if is_local else "AI"
            
            if attachment_count > 0:
                self.set_status(f"⚙️ Processing with {ai_label}: document + {attachment_count} attachment{'s' if attachment_count != 1 else ''}...")
            else:
                self.set_status(f"⚙️ Processing with {ai_label} (with conversation context)...")
            
            success, result = get_ai().call_ai_provider(
                provider=self.provider_var.get(),
                model=self.model_var.get(),
                messages=messages,
                api_key=self.api_key_var.get(),
                document_title=doc_title,
                prompt_name=prompt_name
            )

            if not success:
                self.root.after(0, self._handle_process_result, False, result)
                return

            # 🆕 MVP: Add to thread
            self.add_message_to_thread("user", prompt)
            self.add_message_to_thread("assistant", result)
            
            # 🆕 Save thread to SOURCE document so it appears when reloading the source
            if self.current_document_id:
                from document_library import save_thread_to_document
                thread_metadata = {
                    "model": self.model_var.get(),
                    "provider": self.provider_var.get(),
                    "last_updated": datetime.datetime.now().isoformat(),
                    "message_count": self.thread_message_count
                }
                save_thread_to_document(self.current_document_id, self.current_thread, thread_metadata)
                print(f"💾 Saved thread to source document {self.current_document_id}")

            # Update button states
            self.update_button_states()

            self.root.after(0, self._handle_process_result, True, result)
            return

        # ============================================================
        # MULTIPLE CHUNKS PROCESSING
        # ============================================================
        # NOTE: Multi-chunk doesn't use threading yet in MVP
        # This maintains existing behavior for chunked documents

        results = []
        chunk_prompt = prompt

        for i, chunk in enumerate(chunks, 1):
            if not self.processing:
                self.root.after(0, self._handle_process_result, False, "Processing cancelled")
                return

            chunk_text = entries_to_text_with_speakers(
                chunk,
                timestamp_interval=self.config.get("timestamp_interval", "every_segment")
            ) if self.current_document_type == "audio_transcription" else entries_to_text(
                chunk,
                timestamp_interval=self.config.get("timestamp_interval", "every_segment")
            )

            # For multi-chunk, use simple messages (threading works better with single chunk)
            messages = [
                {"role": "system", "content": "You are a helpful AI assistant analyzing documents."},
                {"role": "user", "content": f"{chunk_prompt}\n\n{chunk_text}"}
            ]

            # Build status message that includes attachment count if any
            attachment_count = 0
            if hasattr(self, 'attachment_manager'):
                attachment_count = self.attachment_manager.get_attachment_count()
            
            if attachment_count > 0:
                self.set_status(f"⚙️ Chunk {i}/{len(chunks)} (+ {attachment_count} attachment{'s' if attachment_count != 1 else ''})...")
            else:
                self.set_status(f"⚙️ Processing chunk {i}/{len(chunks)}...")
            success, result = get_ai().call_ai_provider(
                provider=self.provider_var.get(),
                model=self.model_var.get(),
                messages=messages,
                api_key=self.api_key_var.get(),
                document_title=f"{doc_title} (Chunk {i}/{len(chunks)})",
                prompt_name=f"{prompt_name} - Chunk {i}"
            )

            if not success:
                self.root.after(0, self._handle_process_result, False, result)
                return

            results.append(result)

            # Add delay between chunks to avoid rate limiting
            if i < len(chunks):
                import time
                delay_seconds = 12
                self.set_status(f"⏳ Waiting {delay_seconds}s before next chunk to avoid rate limits...")
                time.sleep(delay_seconds)

        # ============================================================
        # CONSOLIDATE MULTIPLE CHUNKS
        # ============================================================
        combined_chunks = "\n\n---\n\n".join([f"Section {i + 1}:\n{r}" for i, r in enumerate(results)])
        
        # 🆕 Include attachments in consolidation so AI sees all documents
        attachment_text = ""
        if hasattr(self, 'attachment_manager'):
            att_count = self.attachment_manager.get_attachment_count()
            print(f"📎 DEBUG CONSOLIDATION: attachment_manager exists, count = {att_count}")
            if att_count > 0:
                attachment_text = "\n\n" + self.attachment_manager.build_attachment_text()
                print(f"📎 DEBUG CONSOLIDATION: Attachment text length: {len(attachment_text)} chars")
        else:
            print(f"📎 DEBUG CONSOLIDATION: attachment_manager does NOT exist!")
        
        consolidation_prompt = f"{prompt}\n\nHere are the key points extracted from each section of the document:\n\n{combined_chunks}"
        if attachment_text:
            consolidation_prompt += attachment_text
            print(f"📎 DEBUG CONSOLIDATION: Added attachments. Final prompt length: {len(consolidation_prompt)} chars")
        else:
            print(f"📎 DEBUG CONSOLIDATION: No attachments added. Prompt length: {len(consolidation_prompt)} chars")

        # Build status message that includes attachment count if any
        attachment_count = 0
        if hasattr(self, 'attachment_manager'):
            attachment_count = self.attachment_manager.get_attachment_count()
        
        if attachment_count > 0:
            self.set_status(f"Consolidating results (including {attachment_count} attachment{'s' if attachment_count != 1 else ''})...")
        else:
            self.set_status("Consolidating results...")
        
        messages = [
            {"role": "system",
             "content": "You are a helpful AI assistant consolidating information from multiple document sections."},
            {"role": "user", "content": consolidation_prompt}
        ]

        success, final_result = get_ai().call_ai_provider(
            provider=self.provider_var.get(),
            model=self.model_var.get(),
            messages=messages,
            api_key=self.api_key_var.get(),
            document_title=f"{doc_title} (Consolidation)",
            prompt_name=f"{prompt_name} - Final"
        )

        if not success:
            self.root.after(0, self._handle_process_result, False, final_result)
            return

        # 🆕 MVP: Add consolidated result to thread
        self.add_message_to_thread("user", prompt)
        self.add_message_to_thread("assistant", final_result)
        
        # 🆕 Save thread to SOURCE document so it appears when reloading the source
        if self.current_document_id:
            from document_library import save_thread_to_document
            thread_metadata = {
                "model": self.model_var.get(),
                "provider": self.provider_var.get(),
                "last_updated": datetime.datetime.now().isoformat(),
                "message_count": self.thread_message_count
            }
            save_thread_to_document(self.current_document_id, self.current_thread, thread_metadata)
            print(f"💾 Saved thread to source document {self.current_document_id}")

        self.root.after(0, self._handle_process_result, True, final_result)
        # Add delay between chunks to avoid rate limiti

    def reset_ui_state(self):
        """Reset all UI elements to their normal (non-processing) state"""
        try:
            self.processing = False
            self.process_btn.config(state=tk.NORMAL)
            
            # Ensure the All Settings button remains visible
            if hasattr(self, 'settings_btn'):
                self.settings_btn.pack(side=tk.RIGHT, padx=5)
        except Exception as e:
            print(f"Error resetting UI state: {e}")

    def _handle_process_result(self, success, result):
        # Reset UI state including ensuring All Settings button is visible
        self.reset_ui_state()

        if success:
            # Apply automatic cleanup if enabled
            if True:  # Auto-cleanup always enabled
                result = get_formatter().clean_text_encoding(result)

            # Result will be displayed in Thread Viewer (auto-opened in Phase 2)
            

            # 🆕 NEW: Automatically save as processed output to library
            if self.current_document_id:
                self.save_ai_output_as_product_document(result)
            elif hasattr(self, 'attachment_manager') and self.attachment_manager.get_attachment_count() > 0:
                # Attachments-only processing - save as cross-document analysis
                self._save_attachments_output(result)

            self.set_status("✅ Processing complete")
            
            # Auto-open Thread Viewer to show the response
            self.root.after(100, lambda: self._show_thread_viewer(target_mode='conversation'))

        else:
            # User-friendly error handling
            self.set_status(f"❌ Error: {result}")

            # Build helpful error message
            error_text = f"AI Processing Error:\n\n{result}\n\n{'=' * 50}\n\n"
            result_lower = str(result).lower()

            # Check for specific error types
            if any(word in result_lower for word in ['model', '404', 'not_found', 'not found', 'does not exist']):
                error_text += "POSSIBLE CAUSE: Invalid or inactive model\n\nSolutions:\n"
                error_text += "1. Click 'All Settings' → AI Configuration\n"
                error_text += "2. Try a different model from the dropdown\n"
                error_text += "3. Click 'Refresh Models' to get the latest available models"
            elif any(word in result_lower for word in ['401', 'unauthorized', 'authentication', 'api key']):
                error_text += "POSSIBLE CAUSE: API Key issue\n\nSolutions:\n"
                error_text += "1. Check your API key in Settings\n"
                error_text += "2. Get a new key from console.anthropic.com or platform.openai.com"
            elif any(word in result_lower for word in ['429', 'rate limit', 'quota']):
                error_text += "POSSIBLE CAUSE: Rate limit exceeded\n\nSolutions:\n"
                error_text += "1. Wait a few minutes before trying again\n"
                error_text += "2. Check your API usage limits"
            elif any(word in result_lower for word in ['billing', 'payment', '403']):
                error_text += "POSSIBLE CAUSE: Billing issue\n\nSolutions:\n"
                error_text += "1. Check that billing is set up on your API account\n"
                error_text += "2. Verify your payment method is valid"
            else:
                error_text += "TROUBLESHOOTING:\n"
                error_text += "1. Check your API key in Settings\n"
                error_text += "2. Try a different model\n"
                error_text += "3. Check your internet connection"

            messagebox.showerror("AI Processing Error", error_text)

    def _save_processed_output(self, ai_response):
        """Save AI-generated output as a processed document in library"""

        # Get source document info
        source_doc = get_document_by_id(self.current_document_id)
        if not source_doc:
            print("⚠️ Warning: Source document not found, cannot save output")
            return

        source_title = source_doc.get('title', 'Unknown Document')

        # Determine output type from prompt
        prompt_text = getattr(self, 'current_prompt_text', 'Unknown prompt')

        # Detect type from prompt
        prompt_lower = prompt_text.lower()
        if "summary" in prompt_lower or "summarize" in prompt_lower:
            output_type = "summary"
            title_prefix = "Summary"
        elif "analysis" in prompt_lower or "analyze" in prompt_lower:
            output_type = "analysis"
            title_prefix = "Analysis"
        elif "extract" in prompt_lower or "key points" in prompt_lower:
            output_type = "extraction"
            title_prefix = "Key Points"
        elif "translate" in prompt_lower:
            output_type = "translation"
            title_prefix = "Translation"
        elif "dotpoints" in prompt_lower or "dot points" in prompt_lower:
            output_type = "dotpoints"
            title_prefix = "Dotpoints"
        elif "counter" in prompt_lower:
            output_type = "counter_arguments"
            title_prefix = "Counter Arguments"
        else:
            output_type = "output"
            title_prefix = "Output"

        # Convert AI response to entries format
        output_entries = [{
            "start": 0,
            "end": 0,
            "text": ai_response
        }]

        # Create metadata
        output_metadata = {
            'title': f"{title_prefix}: {source_title}",  # Add title for save functions
            'source_document_id': self.current_document_id,
            'source_document_title': source_title,
            'prompt_used': prompt_text,
            'model': self.model_var.get(),
            'provider': self.provider_var.get(),
            'generated_date': datetime.datetime.now().isoformat(),
            'output_type': output_type,
            'editable': True  # Response documents are editable
        }

        # Save to library as processed output
        output_id = add_document_to_library(
            doc_type=output_type,
            source=self.current_document_id,
            title=source_title,
            entries=output_entries,
            document_class="processed_output",
            metadata=output_metadata
        )

        print(f"📝 Saved processed output: {output_id}")
        print(f"   Type: {output_type}")
        print(f"   Title: {title_prefix}: {source_title}")
        
        # Update current document state to reflect the AI response (not source)
        self.current_document_class = "processed_output"
        self.current_document_metadata = output_metadata

    def _save_attachments_output(self, ai_response):
        """
        Save AI-generated output from attachments-only processing.
        Creates a new cross-document analysis document in the library.
        """
        # Get attachment info
        att_count = self.attachment_manager.get_attachment_count()
        att_names = [att['filename'] for att in self.attachment_manager.attachments]
        
        # Determine output type from prompt
        prompt_text = getattr(self, 'current_prompt_text', 'Unknown prompt')
        prompt_lower = prompt_text.lower()
        
        if "compar" in prompt_lower:
            output_type = "comparison"
            title_prefix = "Comparison"
        elif "summary" in prompt_lower or "summarize" in prompt_lower:
            output_type = "summary"
            title_prefix = "Summary"
        elif "analysis" in prompt_lower or "analyze" in prompt_lower:
            output_type = "analysis"
            title_prefix = "Cross-Document Analysis"
        elif "theme" in prompt_lower:
            output_type = "thematic_analysis"
            title_prefix = "Thematic Analysis"
        else:
            output_type = "cross_document_analysis"
            title_prefix = "Cross-Document Analysis"
        
        # Create a descriptive title
        if att_count == 1:
            title = f"{title_prefix}: {att_names[0][:50]}"
        elif att_count <= 3:
            title = f"{title_prefix}: {', '.join(n[:20] for n in att_names)}"
        else:
            title = f"{title_prefix}: {att_count} Documents"
        
        # Convert AI response to entries format
        output_entries = [{
            "start": 0,
            "end": 0,
            "text": ai_response
        }]
        
        # Create metadata
        output_metadata = {
            'title': title,  # Add title for save functions
            'source_documents': att_names,
            'source_count': att_count,
            'prompt_used': prompt_text,
            'model': self.model_var.get(),
            'provider': self.provider_var.get(),
            'generated_date': datetime.datetime.now().isoformat(),
            'output_type': output_type,
            'editable': True
        }
        
        # Generate a unique source identifier for the document ID
        import hashlib
        source_hash = hashlib.md5('|'.join(att_names).encode()).hexdigest()[:8]
        source_id = f"attachments_{source_hash}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Save to library
        output_id = add_document_to_library(
            doc_type=output_type,
            source=source_id,
            title=title,
            entries=output_entries,
            document_class="processed_output",
            metadata=output_metadata
        )
        
        print(f"📝 Saved cross-document analysis: {output_id}")
        print(f"   Type: {output_type}")
        print(f"   Title: {title}")
        print(f"   Sources: {att_count} attachments")
        
        # Update current document state to reflect the AI response (not source)
        self.current_document_class = "processed_output"
        self.current_document_metadata = output_metadata
        
        # Refresh library to show new document
        self.refresh_library()

    def _save_as_product(self, output_text, dialog):
        """Save AI output as new editable product document and load it"""
        doc_id = self.save_ai_output_as_product_document(output_text)
        if doc_id:
            dialog.destroy()

            # Load the newly created product document into the preview
            doc = get_document_by_id(doc_id)
            if doc:
                entries = load_document_entries(doc_id)
                if entries:
                    self.current_entries = entries
                    self.current_document_source = doc['source']
                    self.current_document_type = doc['type']
                    # ✅ FIX: Save old thread BEFORE changing document ID
                    if self.thread_message_count > 0 and self.current_document_id:
                        self.save_current_thread()
                    
                    # Clear thread manually
                    self.current_thread = []
                    self.thread_message_count = 0
                    self.update_thread_status()
                    
                    # NOW change the document ID
                    self.current_document_id = doc_id
                    self.current_document_class = doc.get("document_class", "source")
                    self.current_document_metadata = doc.get("metadata", {})

                    # Update preview with the product document text
                    self.current_document_text = entries_to_text(entries, timestamp_interval=self.config.get(
                        "timestamp_interval", "every_segment"))

                    self.set_status(f"✅ Product document loaded and ready to edit")
                    
                    # Update button states
                    self.update_button_states()

    def _save_as_metadata(self, output_text, dialog):
        """Save AI output as metadata attached to source document"""
        self.save_current_output(output_text)
        dialog.destroy()
    def save_current_output(self, output_text: str):
        """Save the current processed output to the library"""
        if not self.current_document_id:
            messagebox.showerror("Error", "No document loaded")
            return

        # Get prompt info
        prompt_name = self.prompt_combo.get() if self.prompt_combo.get() else "Custom Prompt"
        prompt_text = self.prompt_text.get('1.0', tk.END).strip()

        # Get model info
        provider = self.provider_var.get()
        model = self.model_var.get()

        # Optional notes dialog
        notes_window = tk.Toplevel(self.root)
        notes_window.title("Add Notes (Optional)")
        notes_window.geometry("400x200")
        self.apply_window_style(notes_window)

        ttk.Label(notes_window, text="Add optional notes about this output:",
                  font=('Arial', 10, 'bold')).pack(pady=10)

        notes_text = scrolledtext.ScrolledText(notes_window, wrap=tk.WORD, height=5, font=('Arial', 10))
        notes_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        def save_with_notes():
            notes = notes_text.get('1.0', tk.END).strip()
            output_id = add_processed_output_to_document(
                doc_id=self.current_document_id,
                prompt_name=prompt_name,
                prompt_text=prompt_text,
                provider=provider,
                model=model,
                output_text=output_text,
                notes=notes
            )

            if output_id:
                messagebox.showinfo("Success", "Output saved to library!")
                self.refresh_library()
            else:
                messagebox.showerror("Error", "Failed to save output")

            notes_window.destroy()

        def skip_notes():
            output_id = add_processed_output_to_document(
                doc_id=self.current_document_id,
                prompt_name=prompt_name,
                prompt_text=prompt_text,
                provider=provider,
                model=model,
                output_text=output_text,
                notes=""
            )

            if output_id:
                messagebox.showinfo("Success", "Output saved to library!")
                self.refresh_library()
            else:
                messagebox.showerror("Error", "Failed to save output")

            notes_window.destroy()

        btn_frame = ttk.Frame(notes_window)
        btn_frame.pack(fill=tk.X, pady=10)
        ttk.Button(btn_frame, text="Save with Notes", command=save_with_notes).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Save without Notes", command=skip_notes).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=notes_window.destroy).pack(side=tk.RIGHT, padx=5)

    def cancel_processing(self):
        """Restart DocAnalyser - useful to cancel processing or reset the application."""
        # Check if user has opted to skip confirmation
        skip_confirm = self.config.get("cancel_restart_no_confirm", False)
        
        if not skip_confirm:
            # Show confirmation dialog with "don't ask again" option
            result = self._show_cancel_confirmation()
            if result is None:  # User clicked No or closed dialog
                return
        
        # Perform restart
        self._restart_application()
    
    def _show_cancel_confirmation(self):
        """Show cancel confirmation dialog with 'don't ask again' checkbox."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Restart DocAnalyser")
        dialog.geometry("400x180")
        dialog.transient(self.root)
        dialog.grab_set()
        self.apply_window_style(dialog)
        
        # Center on parent
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 400) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 180) // 2
        dialog.geometry(f"+{x}+{y}")
        
        result = [None]  # Use list to allow modification in nested function
        
        # Message
        ttk.Label(
            dialog,
            text="⚠️ This will restart DocAnalyser.\n\nAny work in progress will be lost.\nDocuments already saved to the Library are safe.",
            wraplength=360,
            justify=tk.CENTER
        ).pack(pady=(20, 15))
        
        # Don't ask again checkbox
        dont_ask_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            dialog,
            text="Don't ask me again",
            variable=dont_ask_var
        ).pack(pady=(0, 15))
        
        # Buttons
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=(0, 15))
        
        def on_yes():
            if dont_ask_var.get():
                self.config["cancel_restart_no_confirm"] = True
                save_config(self.config)
            result[0] = True
            dialog.destroy()
        
        def on_no():
            result[0] = None
            dialog.destroy()
        
        ttk.Button(btn_frame, text="Yes, Restart", command=on_yes, width=12).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="No, Continue", command=on_no, width=12).pack(side=tk.LEFT, padx=5)
        
        dialog.protocol("WM_DELETE_WINDOW", on_no)
        dialog.wait_window()
        
        return result[0]
    
    def _restart_application(self):
        """Restart the application using os.execv for a clean restart."""
        import sys
        import os
        
        self.set_status("Restarting...")
        self.root.update()
        
        try:
            # Get the Python executable and script path
            python = sys.executable
            script = os.path.abspath(sys.argv[0])
            
            # If running as a compiled exe, just restart the exe
            if getattr(sys, 'frozen', False):
                # Running as compiled executable (PyInstaller)
                os.execv(sys.executable, [sys.executable] + sys.argv[1:])
            else:
                # Running as Python script
                os.execv(python, [python, script] + sys.argv[1:])
        except Exception as e:
            # Fallback: just quit and let user restart manually
            messagebox.showinfo(
                "Restart Required",
                f"Please restart DocAnalyser manually.\n\nError: {e}"
            )
            self.root.quit()

    def check_processing_thread(self):
        alive = self.processing_thread.is_alive() if self.processing_thread else False
        print(f"⏰ check_processing: processing={self.processing}, alive={alive}")
        if self.processing and self.processing_thread and self.processing_thread.is_alive():
            self.root.after(100, self.check_processing_thread)
        else:
            self.processing = False
            self.process_btn.config(state=tk.NORMAL)
            # Don't set status here - let the result handlers set the appropriate status
            # This avoids race conditions where check_processing_thread runs before
            # the result handler has a chance to set the status

    def save_output(self):
        if not self.current_document_text:
            messagebox.showerror("Error", "No content to save. Use Thread Viewer for export options.")
            return

        content = self.current_document_text

        # Clean up any encoding issues before saving
        content = get_formatter().clean_text_encoding(content)

        file_path = filedialog.asksaveasfilename(
            defaultextension=".rtf",
            filetypes=[("RTF files", "*.rtf"), ("Text files", "*.txt")]
        )
        if not file_path:
            return

        if file_path.endswith('.rtf'):
            rtf_content = get_formatter().generate_rtf_content(
                title=self.current_document_source or "Document",
                content=content,
                metadata={"Source": self.current_document_source, "Type": self.current_document_type}
            )
            # Use ASCII encoding for RTF - Unicode is handled by RTF codes
            with open(file_path, 'w', encoding='ascii', errors='ignore') as f:
                f.write(rtf_content)
        else:
            # Use UTF-8 for plain text files
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)

        self.set_status(f"✅ Saved to {file_path}")

    def view_conversation_thread(self):
        """
        Display the current conversation thread in a dedicated window
        Shows full context of the ongoing conversation with the current document
        Now with Follow-up capability directly from the thread viewer!
        """
        # Check for standalone conversation (no source document)
        def proceed_with_view(was_saved, doc_id):
            if was_saved and doc_id:
                # Update current document ID so future saves go to this document
                self.current_document_id = doc_id
                self.set_status("✅ Conversation saved to Documents Library")
            self._show_thread_viewer()
        
        # Check if standalone and prompt to save
        if check_and_prompt_standalone_save(
            parent=self.root,
            current_document_id=self.current_document_id,
            current_thread=self.current_thread,
            thread_message_count=self.thread_message_count,
            provider=self.provider_var.get(),
            model=self.model_var.get(),
            api_key=self.api_key_var.get(),
            config=self.config,
            ai_handler=get_ai(),
            on_complete=proceed_with_view
        ):
            return  # Dialog shown, will call proceed_with_view when done
        
        # Not standalone, proceed directly
        self._show_thread_viewer()
    
    def _view_source(self):
        """Open the unified viewer in Source Mode"""
        self._show_thread_viewer(target_mode='source')
    
    def _check_viewer_source_warning(self) -> bool:
        """
        Check if Thread Viewer is open and warn user that the prompt will
        process the original source, not the AI summary displayed in the viewer.
        
        Returns:
            True to continue with processing, False to cancel
        """
        # Check if warning is disabled
        if self.config.get('suppress_viewer_source_warning', False):
            return True
        
        # Check if any viewer is open
        self._cleanup_closed_viewers()
        if not hasattr(self, '_thread_viewer_windows') or not self._thread_viewer_windows:
            return True  # No viewer open, proceed normally
        
        # Check if we actually have a document loaded (warning only makes sense with a document)
        if not self.current_document_text:
            return True  # No document loaded, proceed normally
        
        # Create warning dialog
        dialog = tk.Toplevel(self.root)
        dialog.title("Process Original Source?")
        dialog.transient(self.root)
        dialog.grab_set()
        
        dialog.geometry("480x280")
        dialog.resizable(False, False)
        
        # Position relative to parent
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - 240
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - 140
        dialog.geometry(f"+{x}+{y}")
        
        result = tk.BooleanVar(value=False)
        dont_show_again = tk.BooleanVar(value=False)
        
        # Content frame
        content_frame = ttk.Frame(dialog, padding=20)
        content_frame.pack(fill=tk.BOTH, expand=True)
        
        # Warning icon and title
        ttk.Label(
            content_frame,
            text="⚠️ Process Original Source?",
            font=('Arial', 12, 'bold')
        ).pack(pady=(0, 15))
        
        # Message
        msg = (
            "This prompt will process the ORIGINAL SOURCE\n"
            "DOCUMENT (the transcript), not the AI summary\n"
            "currently displayed in the Thread Viewer.\n\n"
            "To ask questions about the summary, use the\n"
            "\"Ask a Follow-up Question\" field in the\n"
            "Thread Viewer instead."
        )
        ttk.Label(
            content_frame,
            text=msg,
            font=('Arial', 10),
            justify=tk.CENTER
        ).pack(pady=(0, 15))
        
        # Don't show again checkbox
        check_frame = ttk.Frame(content_frame)
        check_frame.pack(pady=(0, 15))
        ttk.Checkbutton(
            check_frame,
            text="Don't show this again",
            variable=dont_show_again
        ).pack()
        
        # Buttons
        btn_frame = ttk.Frame(content_frame)
        btn_frame.pack(fill=tk.X)
        
        def on_continue():
            result.set(True)
            if dont_show_again.get():
                self.config['suppress_viewer_source_warning'] = True
                save_config(self.config)
            dialog.destroy()
        
        def on_cancel():
            result.set(False)
            dialog.destroy()
        
        ttk.Button(
            btn_frame,
            text="Continue",
            command=on_continue,
            width=12
        ).pack(side=tk.LEFT, padx=10, expand=True)
        
        ttk.Button(
            btn_frame,
            text="Cancel",
            command=on_cancel,
            width=12
        ).pack(side=tk.LEFT, padx=10, expand=True)
        
        # Handle dialog close via X button
        dialog.protocol("WM_DELETE_WINDOW", on_cancel)
        
        # Wait for dialog
        dialog.wait_window()
        
        return result.get()
    
    def _cleanup_closed_viewers(self):
        """Remove closed viewer windows from the tracking list"""
        if not hasattr(self, '_thread_viewer_windows'):
            self._thread_viewer_windows = []
            return
        
        # Filter out closed windows
        open_viewers = []
        for viewer in self._thread_viewer_windows:
            try:
                if viewer.window.winfo_exists():
                    open_viewers.append(viewer)
            except (tk.TclError, AttributeError):
                pass  # Window was closed
        
        self._thread_viewer_windows = open_viewers
    
    def _get_open_viewer_count(self) -> int:
        """Get the count of currently open viewer windows"""
        self._cleanup_closed_viewers()
        return len(self._thread_viewer_windows)
    
    def _check_viewer_open_action(self, new_doc_title: str = "the selected document") -> str:
        """
        Check if Thread Viewer(s) are already open and ask user what to do.
        
        Args:
            new_doc_title: Title of the document being loaded (for display in dialog)
        
        Returns:
            'replace' - Close all existing viewers and open new one
            'side_by_side' - Keep existing, open new one alongside
            'cancel' - Don't load the new document
        """
        # Initialize list if needed and clean up closed viewers
        self._cleanup_closed_viewers()
        
        open_count = len(self._thread_viewer_windows)
        
        # No viewers open - proceed normally
        if open_count == 0:
            return 'replace'
        
        # Viewers are open - ask user what to do
        dialog = tk.Toplevel(self.root)
        dialog.title("Thread Viewer Open")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Adjust height based on whether we show a warning
        show_warning = (open_count >= 4)
        dialog_height = 220 if show_warning else 180
        
        dialog.geometry(f"420x{dialog_height}")
        dialog.resizable(False, False)
        
        # Position relative to parent
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - 210
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (dialog_height // 2)
        dialog.geometry(f"+{x}+{y}")
        
        result = tk.StringVar(value='cancel')
        
        # Message
        msg_frame = ttk.Frame(dialog, padding=20)
        msg_frame.pack(fill=tk.BOTH, expand=True)
        
        # Header message varies based on count
        if open_count == 1:
            header_text = "A Thread Viewer is already open."
        else:
            header_text = f"{open_count} Thread Viewers are already open."
        
        ttk.Label(
            msg_frame,
            text=header_text,
            font=('Arial', 11, 'bold')
        ).pack(pady=(0, 5))
        
        # Warning for 4+ viewers
        if show_warning:
            ttk.Label(
                msg_frame,
                text="⚠️ Having many viewers open may slow down the app.",
                font=('Arial', 9),
                foreground='#856404'
            ).pack(pady=(0, 10))
        
        ttk.Label(
            msg_frame,
            text="What would you like to do?",
            font=('Arial', 10)
        ).pack(pady=(0, 15))
        
        # Buttons
        btn_frame = ttk.Frame(msg_frame)
        btn_frame.pack(fill=tk.X)
        
        def set_result(val):
            result.set(val)
            dialog.destroy()
        
        # Replace button - closes ALL existing viewers
        replace_text = "Replace" if open_count == 1 else "Replace All"
        ttk.Button(
            btn_frame,
            text=replace_text,
            command=lambda: set_result('replace'),
            width=12
        ).pack(side=tk.LEFT, padx=5, expand=True)
        
        ttk.Button(
            btn_frame,
            text="Side by Side",
            command=lambda: set_result('side_by_side'),
            width=12
        ).pack(side=tk.LEFT, padx=5, expand=True)
        
        ttk.Button(
            btn_frame,
            text="Cancel",
            command=lambda: set_result('cancel'),
            width=12
        ).pack(side=tk.LEFT, padx=5, expand=True)
        
        # Wait for dialog to close
        dialog.wait_window()
        
        return result.get()
    
    def _view_thread(self):
        """Open the unified viewer in Conversation Mode"""
        # Check for standalone conversation first
        def proceed_with_view(was_saved=False, doc_id=None):
            if was_saved and doc_id:
                # Update current document ID so future saves go to this document
                self.current_document_id = doc_id
                self.set_status("✅ Conversation saved to Documents Library")
            self._show_thread_viewer(target_mode='conversation')
        
        # Check if this is a standalone conversation that should be saved first
        if check_and_prompt_standalone_save(
            parent=self.root,
            current_document_id=self.current_document_id,
            current_thread=self.current_thread,
            thread_message_count=self.thread_message_count,
            provider=self.provider_var.get(),
            model=self.model_var.get(),
            api_key=self.api_key_var.get(),
            config=self.config,
            ai_handler=get_ai(),
            on_complete=proceed_with_view
        ):
            return  # Dialog shown, will call proceed_with_view when done
        
        # Not standalone, proceed directly
        proceed_with_view()

    def _show_thread_viewer(self, target_mode: str = None, force_new_window: bool = False):
        """
        Show the thread viewer window in the specified mode.

        Args:
            target_mode: 'source' or 'conversation'. If None, auto-determines based on content.
            force_new_window: If True, always create a new window (for side-by-side viewing)
        """
        print(f"🔍 _show_thread_viewer called with target_mode={target_mode}, force_new_window={force_new_window}")

        # Initialize viewer list if needed
        if not hasattr(self, '_thread_viewer_windows'):
            self._thread_viewer_windows = []
        
        # Clean up closed viewers
        self._cleanup_closed_viewers()
        
        # Check if we should reuse an existing viewer (only if not forcing new window)
        if not force_new_window and self._thread_viewer_windows:
            # Use the most recent viewer
            viewer = self._thread_viewer_windows[-1]
            try:
                if viewer.window.winfo_exists():
                    print(f"   📺 Viewer already open, current mode: {viewer.current_mode}, target: {target_mode}")
                    viewer.window.lift()
                    viewer.window.focus_force()

                    # Switch to target mode if specified and different
                    if target_mode and target_mode != viewer.current_mode:
                        if target_mode == 'conversation':
                            has_conversation = self.current_thread and len(self.current_thread) > 0
                            if has_conversation:
                                viewer.switch_mode('conversation')
                            else:
                                print(f"   ⚠️ No conversation to display")
                        else:
                            viewer.switch_mode('source')

                    # Update button state
                    self.update_view_button_state()
                    return
            except (tk.TclError, AttributeError):
                # Window was closed, remove from list
                self._thread_viewer_windows.remove(viewer)
        
        # When forcing new window, don't close the existing ones
        if force_new_window:
            print(f"   📺 Opening NEW viewer window (side-by-side mode, {len(self._thread_viewer_windows)} already open)")

        print(f"   📺 Opening new viewer")

        # Use the new thread_viewer module which handles all UI and follow-up logic
        from thread_viewer import show_thread_viewer

        # ============================================================
        # DETERMINE SOURCE DOCUMENT TEXT FOR COLLAPSIBLE SECTION
        # If viewing a Response document, fetch the ORIGINAL source transcript
        # ============================================================
        source_text_for_viewer = self.current_document_text
        source_entries_for_viewer = self.current_entries

        is_response_document = getattr(self, 'current_document_class', 'source') in ['response', 'product',
                                                                                     'processed_output']
        parent_doc_id = None

        if hasattr(self, 'current_document_metadata') and self.current_document_metadata:
            parent_doc_id = self.current_document_metadata.get('parent_document_id')

        if is_response_document and parent_doc_id:
            # Fetch the original source document's content
            try:
                from document_library import get_document_by_id, load_document_entries
                from utils import entries_to_text, entries_to_text_with_speakers

                parent_doc = get_document_by_id(parent_doc_id)
                if parent_doc:
                    # Load entries from file (not from doc dict - entries are stored separately)
                    parent_entries = load_document_entries(parent_doc_id)
                    parent_doc_type = parent_doc.get('doc_type', parent_doc.get('type', 'text'))

                    if parent_entries:
                        print(f"📄 Loaded {len(parent_entries)} entries from parent source document")
                        # Convert entries to text (use speaker format for audio)
                        if parent_doc_type == 'audio_transcription':
                            source_text_for_viewer = entries_to_text_with_speakers(
                                parent_entries,
                                timestamp_interval=self.config.get("timestamp_interval", "every_segment")
                            )
                        else:
                            source_text_for_viewer = entries_to_text(
                                parent_entries,
                                timestamp_interval=self.config.get("timestamp_interval", "every_segment")
                            )
                        source_entries_for_viewer = parent_entries
                        print(f"📄 Loaded original source document ({len(source_text_for_viewer)} chars) for viewer")
            except Exception as e:
                print(f"⚠️ Could not fetch parent document: {e}")
                # Fall back to current_document_text

        # ============================================================
        # BUILD MULTI-SOURCE DOCUMENTS LIST
        # Combine main document + attachments into separate collapsible sections
        # ============================================================
        source_documents_for_viewer = None

        # Check if this is a multi-doc analysis - use entries as sources
        is_multi_doc = (hasattr(self, 'current_document_type') and 
                        self.current_document_type == 'multi_doc_analysis')
        
        if is_multi_doc and source_entries_for_viewer and len(source_entries_for_viewer) > 1:
            # Build source_documents from entries (each entry is a separate document)
            source_documents_for_viewer = []
            for entry in source_entries_for_viewer:
                entry_text = entry.get('text', '')
                if entry_text and entry_text.strip():
                    source_documents_for_viewer.append({
                        'title': entry.get('location', 'Document'),
                        'text': entry_text,
                        'source': entry.get('location', ''),
                        'char_count': len(entry_text)
                    })
            if source_documents_for_viewer:
                print(f"📚 Built source_documents from multi-doc entries: {len(source_documents_for_viewer)} documents")
            else:
                source_documents_for_viewer = None

        # Check if we have multiple sources (attachments)
        has_attachments = (hasattr(self, 'attachment_manager') and
                           self.attachment_manager.get_attachment_count() > 0)

        if has_attachments and not source_documents_for_viewer:
            # Build source_documents list from main document + attachments
            source_documents_for_viewer = []

            # Add main document as first source (if it exists and has content)
            if source_text_for_viewer and source_text_for_viewer.strip():
                # Don't include placeholder text
                if not source_text_for_viewer.startswith('[Attachments-only mode'):
                    source_documents_for_viewer.append({
                        'title': self.current_document_source or 'Main Document',
                        'text': source_text_for_viewer,
                        'source': self.current_document_source or '',
                        'char_count': len(source_text_for_viewer)
                    })

            # Add each attachment as a separate source
            for att in self.attachment_manager.attachments:
                att_text = att.get('text', '')
                if att_text and att_text.strip():
                    source_documents_for_viewer.append({
                        'title': att.get('filename', 'Attachment'),
                        'text': att_text,
                        'source': att.get('path', att.get('source', '')),
                        'char_count': len(att_text)
                    })

            # If we end up with nothing, fall back to None
            if not source_documents_for_viewer:
                source_documents_for_viewer = None
            else:
                print(f"📚 Built source_documents list with {len(source_documents_for_viewer)} documents")

        def on_followup_complete(question: str, response: str):
            """Callback when follow-up is completed from thread viewer"""
            # Update the preview text in main window with latest response
            self.set_status("✅ Follow-up complete", include_thread_status=True)

        new_viewer = show_thread_viewer(
            parent=self.root,
            current_thread=self.current_thread,
            thread_message_count=self.thread_message_count,
            current_document_id=self.current_document_id,
            current_document_text=source_text_for_viewer,  # Use source text, not response
            current_document_source=self.current_document_source,
            model_var=self.model_var,
            provider_var=self.provider_var,
            api_key_var=self.api_key_var,
            config=self.config,
            on_followup_complete=on_followup_complete,
            on_clear_thread=self.clear_thread,
            refresh_library=self.refresh_library,
            get_ai_handler=get_ai,
            build_threaded_messages=self.build_threaded_messages,
            add_message_to_thread=self.add_message_to_thread,
            attachment_manager=self.attachment_manager,
            font_size=self.font_size,
            # New parameters for "New Conversation (Same Source)" feature
            document_class=getattr(self, 'current_document_class', 'source'),
            source_document_id=self.current_document_metadata.get('parent_document_id') if hasattr(self,
                                                                                                   'current_document_metadata') else None,
            on_start_new_conversation=self.start_new_conversation_same_source,
            # Unified viewer callback for button state updates
            on_mode_change=self.on_viewer_mode_change,
            # Chunking callback for initial prompts from Source Mode
            process_with_chunking=self.process_prompt_with_chunking,
            # Current entries for chunking - use source entries if available
            current_entries=source_entries_for_viewer if source_entries_for_viewer else self.current_entries,
            current_document_type=getattr(self, 'current_document_type', 'text'),
            # Initial mode from caller
            initial_mode=target_mode,
            # NEW: Multi-source document support
            source_documents=source_documents_for_viewer,
            # NEW: App reference for context synchronization (branch creation)
            app=self,
        )
        
        # Add to list of open viewers
        self._thread_viewer_windows.append(new_viewer)
        print(f"   📺 Viewer opened (now {len(self._thread_viewer_windows)} total)")

        # Update button state now that viewer is open
        self.update_view_button_state()
    def process_prompt_with_chunking(self, prompt: str, status_callback, complete_callback):
        """
        Process a prompt with chunking support - callable from unified viewer.
        
        This allows the viewer to process initial prompts on large documents
        using the same chunking logic as the main "Run" button.
        
        Args:
            prompt: The prompt text to process
            status_callback: Function to call with status updates (str)
            complete_callback: Function to call when done (success: bool, result: str)
        """
        def process_thread():
            try:
                from utils import chunk_entries, entries_to_text, entries_to_text_with_speakers
                
                # Check if we have document content
                if not self.current_entries:
                    complete_callback(False, "No document content available for processing")
                    return
                
                # Get chunk size setting
                chunk_size_setting = self.config.get("chunk_size", "medium")
                
                # Chunk the entries
                chunks = chunk_entries(self.current_entries, chunk_size_setting)
                
                # Get document title for cost tracking
                doc_title = "Unknown Document"
                try:
                    if hasattr(self, 'current_document_id') and self.current_document_id:
                        from document_library import get_document_by_id
                        doc = get_document_by_id(self.current_document_id)
                        if doc:
                            doc_title = doc.get('title', 'Unknown Document')
                except Exception as e:
                    print(f"Warning: Could not get document title: {e}")
                
                prompt_name = "Viewer Prompt"
                
                # Determine document type for formatting
                is_audio = getattr(self, 'current_document_type', 'text') == "audio_transcription"
                timestamp_interval = self.config.get("timestamp_interval", "every_segment")
                
                # Check if using Local AI
                is_local = self.provider_var.get() == "Ollama (Local)"
                ai_label = "💻 Local AI" if is_local else "AI"
                
                # ============================================================
                # SINGLE CHUNK PROCESSING
                # ============================================================
                if len(chunks) == 1:
                    if is_audio:
                        chunk_text = entries_to_text_with_speakers(chunks[0], timestamp_interval=timestamp_interval)
                    else:
                        chunk_text = entries_to_text(chunks[0], timestamp_interval=timestamp_interval)
                    
                    # Build messages with document context
                    messages = [
                        {"role": "system", "content": "You are a helpful AI assistant analyzing documents."},
                        {"role": "user", "content": f"{prompt}\n\n{chunk_text}"}
                    ]
                    
                    status_callback(f"⚙️ Processing with {ai_label}...")
                    
                    success, result = get_ai().call_ai_provider(
                        provider=self.provider_var.get(),
                        model=self.model_var.get(),
                        messages=messages,
                        api_key=self.api_key_var.get(),
                        document_title=doc_title,
                        prompt_name=prompt_name
                    )
                    
                    if success:
                        # Add to thread
                        self.add_message_to_thread("user", prompt)
                        self.add_message_to_thread("assistant", result)
                        
                        # Preview update removed - Thread Viewer handles display
                        self.root.after(0, self.update_button_states)
                        
                        # Save as response document (same as main Run button)
                        self.root.after(0, lambda r=result: self.save_ai_output_as_product_document(r))
                    
                    print(f"🔔 Main.py (single chunk): Calling complete_callback with success={success}")
                    complete_callback(success, result)
                    print(f"🔔 Main.py (single chunk): complete_callback returned")
                    return
                
                # ============================================================
                # MULTIPLE CHUNKS PROCESSING
                # ============================================================
                results = []
                
                for i, chunk in enumerate(chunks, 1):
                    if is_audio:
                        chunk_text = entries_to_text_with_speakers(chunk, timestamp_interval=timestamp_interval)
                    else:
                        chunk_text = entries_to_text(chunk, timestamp_interval=timestamp_interval)
                    
                    messages = [
                        {"role": "system", "content": "You are a helpful AI assistant analyzing documents."},
                        {"role": "user", "content": f"{prompt}\n\n{chunk_text}"}
                    ]
                    
                    status_callback(f"⚙️ Processing chunk {i}/{len(chunks)} with {ai_label}...")
                    
                    success, result = get_ai().call_ai_provider(
                        provider=self.provider_var.get(),
                        model=self.model_var.get(),
                        messages=messages,
                        api_key=self.api_key_var.get(),
                        document_title=f"{doc_title} (Chunk {i}/{len(chunks)})",
                        prompt_name=f"{prompt_name} - Chunk {i}"
                    )
                    
                    if not success:
                        complete_callback(False, f"Failed on chunk {i}: {result}")
                        return
                    
                    results.append(result)
                    
                    # Add delay between chunks to avoid rate limiting
                    if i < len(chunks):
                        import time
                        delay_seconds = 12
                        status_callback(f"⏳ Waiting {delay_seconds}s before next chunk...")
                        time.sleep(delay_seconds)
                
                # ============================================================
                # CONSOLIDATE MULTIPLE CHUNKS
                # ============================================================
                combined_chunks = "\n\n---\n\n".join([f"Section {i + 1}:\n{r}" for i, r in enumerate(results)])
                consolidation_prompt = f"{prompt}\n\nHere are the key points extracted from each section of the document:\n\n{combined_chunks}"
                
                status_callback("⚙️ Consolidating results...")
                
                messages = [
                    {"role": "system", "content": "You are a helpful AI assistant consolidating information from multiple document sections."},
                    {"role": "user", "content": consolidation_prompt}
                ]
                
                success, final_result = get_ai().call_ai_provider(
                    provider=self.provider_var.get(),
                    model=self.model_var.get(),
                    messages=messages,
                    api_key=self.api_key_var.get(),
                    document_title=f"{doc_title} (Consolidated)",
                    prompt_name=f"{prompt_name} - Consolidation"
                )
                
                if success:
                    # Add to thread
                    self.add_message_to_thread("user", prompt)
                    self.add_message_to_thread("assistant", final_result)
                    
                    # Preview update removed - Thread Viewer handles display
                    self.root.after(0, self.update_button_states)
                    
                    # Save as response document (same as main Run button)
                    self.root.after(0, lambda r=final_result: self.save_ai_output_as_product_document(r))
                
                print(f"🔔 Main.py: Calling complete_callback with success={success}")
                complete_callback(success, final_result)
                print(f"🔔 Main.py: complete_callback returned")
                
            except Exception as e:
                import traceback
                traceback.print_exc()
                print(f"🔔 Main.py: Calling complete_callback with error: {e}")
                complete_callback(False, f"Error during processing: {str(e)}")
        
        # Run in background thread
        thread = threading.Thread(target=process_thread, daemon=True)
        thread.start()

    def save_current_thread(self):
        """Save current thread to document library"""
        print(f"\n🔍 DEBUG save_current_thread() called")
        print(f"   - current_document_id: {self.current_document_id}")
        print(f"   - thread_message_count: {self.thread_message_count}")
        print(f"   - current_thread length: {len(self.current_thread) if self.current_thread else 0}")
        
        if not self.current_document_id:
            print("   ⚠️  ABORTED: No document ID")
            return

        if not self.current_thread or self.thread_message_count == 0:
            print("   ⚠️  ABORTED: No thread or zero messages")
            return

        # Prepare metadata
        metadata = {
            "model": self.model_var.get(),
            "provider": self.provider_var.get(),
            "last_updated": datetime.datetime.now().isoformat(),
            "message_count": self.thread_message_count
        }

        # Save to library
        from document_library import save_thread_to_document
        save_thread_to_document(self.current_document_id, self.current_thread, metadata)

        print(f"💾 Thread saved for document {self.current_document_id} ({self.thread_message_count} messages)")

    def load_saved_thread(self):
        """Load saved thread for current document"""
        print(f"\n🔍 DEBUG load_saved_thread() called")
        print(f"   - current_document_id: {self.current_document_id}")
        
        if not self.current_document_id:
            print("   ⚠️  ABORTED: No document ID")
            return

        from document_library import load_thread_from_document
        thread, metadata = load_thread_from_document(self.current_document_id)
        
        print(f"   - Thread data retrieved: {thread is not None}")
        print(f"   - Thread length: {len(thread) if thread else 0}")
        print(f"   - Metadata: {metadata}")

        if thread:
            self.current_thread = thread
            self.thread_message_count = len([m for m in thread if m.get("role") == "user"])
            self.thread_needs_document_refresh = True  # Mark that we need to re-include document on next follow-up
            self.update_thread_status()

            print(f"📂 Thread loaded for document {self.current_document_id} ({self.thread_message_count} messages)")
            print(f"   🔄 thread_needs_document_refresh = True (document will be re-sent on next follow-up)")
        else:
            print(f"   ℹ️  No saved thread found for document {self.current_document_id}")

            # Show notification
            if self.thread_message_count > 0:
                self.set_status(
                    f"✅ Loaded document with {self.thread_message_count} message{'s' if self.thread_message_count != 1 else ''} in conversation",
                    include_thread_status=False
                )

    
    def on_app_closing(self):
        """
        Handle application close event
        Save current thread before exiting to preserve conversation
        """
        print("\n" + "=" * 60)
        print("🚪 Application closing...")
        
        # Save thread if there are messages
        if self.thread_message_count > 0 and self.current_document_id:
            print(f"💾 Auto-saving thread ({self.thread_message_count} messages) before exit...")
            self.save_current_thread()
            print("✅ Thread saved!")
        else:
            print("ℹ️  No thread to save (either no messages or no document loaded)")
        
        print("👋 Goodbye!")
        print("=" * 60)
        
        # Close the window
        self.root.destroy()

    def start_new_conversation_same_source(self, source_doc_id: str) -> bool:
        """
        Start a new conversation using the original source document.
        
        Called from Thread Viewer when user wants to start a fresh conversation
        about the same source document that a Response was based on.
        
        Args:
            source_doc_id: The ID of the parent document (may be Response or Source)
            
        Returns:
            True if successful, False otherwise
        """
        from document_library import get_document_by_id, load_document_entries
        
        # Follow the parent chain to find the ORIGINAL source document
        # (in case parent_document_id points to another Response)
        original_source_id = source_doc_id
        visited = set()  # Prevent infinite loops
        
        while original_source_id and original_source_id not in visited:
            visited.add(original_source_id)
            doc = get_document_by_id(original_source_id)
            
            if not doc:
                break
            
            # Check if this is a source document (not a response/product)
            doc_class = doc.get('document_class', 'source')
            if doc_class not in ['response', 'product', 'processed_output']:
                # Found the original source!
                break
            
            # This is a Response/Product - look for its parent
            parent_id = doc.get('metadata', {}).get('parent_document_id')
            if not parent_id or parent_id == original_source_id:
                # No parent or self-reference - use this as the source
                break
            
            # Follow the chain
            print(f"🔗 Following parent chain: {original_source_id} -> {parent_id}")
            original_source_id = parent_id
        
        # Check if source document exists
        source_doc = get_document_by_id(original_source_id)
        if not source_doc:
            messagebox.showerror(
                "Source Not Found",
                "The original source document is no longer available.\n\n"
                "It may have been deleted from the Documents Library."
            )
            return False
        
        # Verify we found an actual source (not another Response)
        doc_class = source_doc.get('document_class', 'source')
        if doc_class in ['response', 'product', 'processed_output']:
            messagebox.showwarning(
                "Source Unavailable",
                "Could not find the original source document.\n\n"
                "The parent document chain leads to another Response document.\n"
                "The original source may have been deleted."
            )
            return False
        
        # Load the source document entries
        entries = load_document_entries(original_source_id)
        if not entries:
            messagebox.showerror(
                "Load Error",
                "Could not load the source document content."
            )
            return False
        
        # Clear current thread (saves if needed)
        self.clear_thread()
        
        # Load the source document
        self.current_entries = entries
        self.current_document_id = original_source_id
        self.current_document_source = source_doc.get('source', 'Unknown')
        self.current_document_type = source_doc.get('type', 'unknown')
        self.current_document_class = source_doc.get('document_class', 'source')
        self.current_document_metadata = source_doc.get('metadata', {})
        if 'title' not in self.current_document_metadata:
            self.current_document_metadata['title'] = source_doc.get('title', 'Unknown')
        
        # Convert entries to text
        from utils import entries_to_text, entries_to_text_with_speakers
        if source_doc.get('type') == 'audio_transcription':
            self.current_document_text = entries_to_text_with_speakers(
                entries,
                timestamp_interval=self.config.get("timestamp_interval", "every_segment")
            )
        else:
            self.current_document_text = entries_to_text(entries)
        
        # Reset standalone conversation state
        from standalone_conversation import reset_standalone_state
        reset_standalone_state()
        
        # Note: Don't close viewer windows here - the caller (viewer) will handle itself
        # Just clean up the tracking list of closed windows
        self._cleanup_closed_viewers()
        
        # Update UI
        self.update_button_states()
        
        # Explicitly set preview title to source_ready mode (prompts user to click Run)
        
        doc_title = source_doc.get('title', 'Unknown')
        self.set_status("✅ Source document loaded - Ready for new conversation")
        
        return True

    def export_to_web_chat(self):
        """
        Run prompt via web: Copy document and prompt to clipboard and open
        the provider's web-based chat interface (ChatGPT, Claude, Gemini, etc.)
        This is an alternative to the API method - free but requires manual paste.
        """
        import webbrowser
        
        # Reset Run button highlight immediately
        self._run_highlight_enabled = False
        if hasattr(self, 'process_btn'):
            self.process_btn.configure(style='TButton')
            self.root.update_idletasks()
        
        # Clear the input field and restore placeholder (document is already loaded)
        self.universal_input_entry.delete('1.0', 'end')
        self.placeholder_active = False  # Reset so update_placeholder will work
        self.update_placeholder()
        
        # 🆕 NEW: Smart context check - allow prompts without documents
        has_document = bool(self.current_document_text)
        has_attachments = (hasattr(self, 'attachment_manager') and 
                          self.attachment_manager.get_attachment_count() > 0)
        has_any_content = has_document or has_attachments
        
        # Get the current prompt
        prompt = self.prompt_text.get('1.0', tk.END).strip()
        if not prompt:
            messagebox.showinfo("No Prompt", "Please enter or select a prompt first.")
            return
        
        # Check if prompt appears to be document-specific
        document_keywords = [
            'document', 'text', 'article', 'content', 'passage', 
            'summary', 'summarize', 'extract', 'analyze', 'review',
            'above', 'provided', 'following', 'attached', 'this file'
        ]
        prompt_lower = prompt.lower()
        is_document_specific = any(keyword in prompt_lower for keyword in document_keywords)
        
        # Smart warning system
        if not has_any_content:
            if is_document_specific:
                # Prompt mentions document-related terms but no document loaded
                response = messagebox.askyesno(
                    "No Document Loaded",
                    f"Your prompt mentions document-related content but no document is loaded.\n\n"
                    f"💡 Tip: Load a document first, or rephrase your prompt.\n\n"
                    f"Continue anyway (only prompt will be copied)?",
                    icon='warning'
                )
                if not response:
                    return
        
        # Get the selected provider
        provider = self.provider_var.get()
        
        # Define provider info: URL, name, and any special notes
        provider_info = {
            "OpenAI (ChatGPT)": {
                "url": "https://chat.openai.com",
                "name": "ChatGPT",
                "notes": "Free tier available. For very long documents, ChatGPT may truncate the input."
            },
            "Anthropic (Claude)": {
                "url": "https://claude.ai",
                "name": "Claude",
                "notes": "Free tier available. Claude handles very long documents well (200K+ tokens)."
            },
            "Google (Gemini)": {
                "url": "https://gemini.google.com",
                "name": "Gemini",
                "notes": "Free tier available. Requires a Google account."
            },
            "xAI (Grok)": {
                "url": "https://x.com/i/grok",
                "name": "Grok",
                "notes": "⚠️ Requires an X (Twitter) account to access."
            },
            "DeepSeek": {
                "url": "https://chat.deepseek.com",
                "name": "DeepSeek",
                "notes": "Free tier available with generous limits."
            },
            "Ollama (Local)": {
                "url": None,  # No web interface
                "name": "Ollama",
                "notes": "Ollama is a local application. Open it directly and paste your content there."
            }
        }
        
        # Get info for selected provider, with fallback
        info = provider_info.get(provider, {
            "url": None,
            "name": provider,
            "notes": "Web interface URL not configured for this provider."
        })
        
        # Build the export text
        export_parts = [prompt]
        
        # Add main document if present
        if has_document:
            export_parts.append("\n\n" + "=" * 50 + "\nDOCUMENT\n" + "=" * 50 + f"\n\n{self.current_document_text}")
        
        # 🆕 NEW: Add attachments if present
        if has_attachments:
            export_parts.append("\n\n" + self.attachment_manager.build_attachment_text())
        
        export_text = "".join(export_parts)
        
        # Calculate approximate size
        char_count = len(export_text)
        word_count = len(export_text.split())
        token_estimate = char_count // 4  # Rough estimate
        
        # Build content description for message
        content_desc = []
        content_desc.append("• Your selected prompt")
        if has_document:
            content_desc.append(f"• The loaded document")
        if has_attachments:
            att_count = self.attachment_manager.get_attachment_count()
            content_desc.append(f"• {att_count} attached document{'s' if att_count > 1 else ''}")
        content_desc.append(f"\nTotal: {word_count:,} words, ~{token_estimate:,} tokens")
        content_list = "\n".join(content_desc)
        
        # Build the message
        if info["url"]:
            message = (
                f"Run prompt via {info['name']} Web Chat\n\n"
                f"The following will be copied to your clipboard:\n"
                f"{content_list}\n\n"
                f"After clicking OK:\n"
                f"1. Your browser will open {info['name']}\n"
                f"2. Press Ctrl+V to paste into the chat input\n"
                f"3. Press Enter or click Send to run the prompt\n\n"
                f"Note: {info['notes']}\n\n"
                f"Continue?"
            )
        else:
            # Ollama or unknown provider
            message = (
                f"Run prompt via {info['name']}\n\n"
                f"The following will be copied to your clipboard:\n"
                f"{content_list}\n\n"
                f"Note: {info['notes']}\n\n"
                f"After clicking OK, press Ctrl+V in your AI application to paste.\n\n"
                f"Continue?"
            )
        
        # Ask user to confirm
        response = messagebox.askyesno("Run Prompt Via Web", message)
        
        if not response:
            return
        
        # Copy to clipboard
        self.root.clipboard_clear()
        self.root.clipboard_append(export_text)
        self.root.update()  # Required for clipboard to persist
        
        # Open web browser if URL available
        if info["url"]:
            try:
                webbrowser.open(info["url"])
                self.set_status(f"✅ Copied to clipboard & opened {info['name']} - press Ctrl+V in browser to paste, or right-click and select Paste.")
            except Exception as e:
                self.set_status(f"✅ Copied to clipboard - open {info['url']} manually")
                messagebox.showinfo(
                    "Browser Error",
                    f"Copied to clipboard but couldn't open browser.\n\n"
                    f"Please open {info['url']} manually and press Ctrl+V to paste."
                )
        else:
            self.set_status(f"✅ Copied to clipboard - paste into {info['name']} with Ctrl+V")
            messagebox.showinfo(
                "Copied to Clipboard",
                f"Content copied!\n\nOpen {info['name']} and press Ctrl+V to paste."
            )
        
        # 🆕 NEW: Show the web response capture banner
        # Build context for later capture - get document title from library
        source_name = "Unknown source"
        if self.current_document_id:
            try:
                from document_library import get_document_by_id
                doc = get_document_by_id(self.current_document_id)
                if doc and doc.get('title'):
                    source_name = doc.get('title')
                    # Remove [Source], [Product], etc. prefixes if present
                    for prefix in ['[Source] ', '[Product] ', '[Response] ', '[Thread] ']:
                        if source_name.startswith(prefix):
                            source_name = source_name[len(prefix):]
                            break
                    # Remove source type prefixes like "YouTube: ", "Substack: "
                    for type_prefix in ['YouTube: ', 'Substack: ', 'Web: ', 'Audio: ', 'File: ', 'PDF: ']:
                        if source_name.startswith(type_prefix):
                            source_name = source_name[len(type_prefix):]
                            break
            except:
                pass
        if source_name == "Unknown source" and self.current_document_source:
            source_name = self.current_document_source
        
        attachment_names = []
        if has_attachments:
            attachment_names = [a.get('name', 'Attachment') for a in self.attachment_manager.get_attachments()]
        
        web_response_context = {
            "prompt": prompt,
            "provider": info['name'],
            "source_name": source_name,
            "document_id": self.current_document_id,
            "attachment_names": attachment_names,
            "sent_at": datetime.datetime.now().isoformat()
        }
        
        self.show_web_response_banner(web_response_context)

    def run_via_local_ai(self):
        """
        Run prompt via Local AI (Ollama).
        - Checks if Ollama is running
        - If connected with models: runs prompt directly
        - If not connected: shows setup dialog to help user connect
        """
        from ai_handler import check_ollama_connection
        
        # Reset Run button highlight immediately
        self._run_highlight_enabled = False
        if hasattr(self, 'process_btn'):
            self.process_btn.configure(style='TButton')
            self.root.update_idletasks()
        
        # Clear the input field and restore placeholder (document is already loaded)
        self.universal_input_entry.delete('1.0', 'end')
        self.placeholder_active = False  # Reset so update_placeholder will work
        self.update_placeholder()
        
        # Check Ollama connection first
        base_url = self.config.get("ollama_base_url", "http://localhost:11434")
        connected, status, models = check_ollama_connection(base_url)
        
        # Only show dialog if NOT connected or no models available
        if not connected or not models:
            result = self._show_local_ai_dialog(connected, status, models, base_url)
            
            if result == "cancel":
                return
            elif result == "open_guide":
                self._open_local_ai_guide()
                return
            # result == "continue" - proceed with running
        
        # Auto-switch to Ollama provider
        if self.provider_var.get() != "Ollama (Local)":
            self.provider_var.set("Ollama (Local)")
            self.on_provider_select(None)  # Trigger the provider change handler
        
        # Refresh models and check connection again
        self._refresh_ollama_models(show_errors=True)
        
        # Verify we have models available
        available_models = self.models.get("Ollama (Local)", [])
        real_models = [m for m in available_models if not m.startswith("(")]
        if not real_models:
            messagebox.showerror(
                "Ollama Not Ready",
                "Ollama server is not responding or no models are loaded.\n\n"
                "Please ensure:\n"
                "1. Ollama is running\n"
                "2. A model is loaded\n"
                "3. The server is started (Developer tab → Start Server)\n\n"
                "Click 'Help → Local AI Guide' for detailed setup instructions."
            )
            return
        
        # Set the model to the first available Ollama model (for internal use)
        self.model_var.set(real_models[0])
        
        # Run the prompt via DocAnalyser (which will now use Ollama)
        self.set_status("💻 Running prompt via Local AI (Ollama)...")
        self.process_document()
    
    def _show_local_ai_dialog(self, connected: bool, status: str, models: list, base_url: str) -> str:
        """
        Show the Local AI setup/info dialog.
        
        Returns:
            'continue' - proceed with running
            'cancel' - user cancelled
            'open_guide' - user wants to open the guide
        """
        from ai_handler import check_ollama_connection
        dialog = tk.Toplevel(self.root)
        dialog.title("💻 Local AI Setup")
        dialog.configure(bg='#dcdad5')
        self.apply_window_style(dialog)
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Size and position
        dialog.geometry("520x420")
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - 260
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - 240
        dialog.geometry(f"+{x}+{y}")
        
        result = {'action': 'cancel'}
        connection_state = {'connected': connected, 'models': models}
        
        # Main content frame - matching app styling
        main_frame = tk.Frame(dialog, bg='#dcdad5', padx=15, pady=15)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Connection status indicator - using StringVar for dynamic updates
        status_frame = tk.Frame(main_frame, bg='#dcdad5')
        status_frame.pack(fill=tk.X, pady=(0, 10))
        
        status_var = tk.StringVar()
        status_label = tk.Label(
            status_frame,
            textvariable=status_var,
            font=('Arial', 10, 'bold'),
            bg='#dcdad5'
        )
        status_label.pack(anchor=tk.W)
        
        def update_status_display(is_connected, model_list, status_msg=""):
            """Update the status indicator"""
            if is_connected and model_list:
                # Connected with models - good to go
                status_var.set(f"✅ Ollama Connected - {len(model_list)} model(s) available")
                status_label.config(fg="#228B22")  # Forest green
                continue_btn.config(text="▶ Continue")
            elif is_connected and not model_list:
                # Connected but no models loaded - needs attention
                status_var.set("⚠️ Ollama Connected - No models loaded")
                status_label.config(fg="#CC6600")  # Orange/amber warning
                continue_btn.config(text="▶ Try Anyway")
            else:
                # Not connected
                status_var.set(f"❌ Ollama Not Detected - {status_msg}")
                status_label.config(fg="#CC0000")  # Dark red
                continue_btn.config(text="▶ Try Anyway")
            connection_state['connected'] = is_connected
            connection_state['models'] = model_list
        
        # Separator
        ttk.Separator(main_frame, orient='horizontal').pack(fill=tk.X, pady=10)
        
        # Info text in a soft yellow frame to match app style
        info_frame = tk.Frame(main_frame, bg='#FFFDE6', padx=10, pady=10)
        info_frame.pack(fill=tk.BOTH, expand=True)
        
        # Info text - context-sensitive based on connection state
        if connected and not models:
            # Connected but no models - specific instructions
            info_text = (
                "🚨 Ollama is running but no models are loaded!\n\n"
                "To load a model:\n\n"
                "1️⃣  Go to the Home tab in Ollama\n"
                "2️⃣  Select a downloaded model from the list\n"
                "3️⃣  Click 'Load' to load it into memory\n\n"
                "If you haven't downloaded a model yet:\n"
                "• Go to the Search tab and find a model\n"
                "• Recommended: Llama, Mistral, or Qwen models\n"
                "• Download, then load it from the Home tab\n\n"
                "Once a model is loaded, click '🚀 Launch & Connect'\n"
                "to refresh the connection."
            )
        else:
            # Not connected - general setup instructions
            info_text_before_link = (
                "To run AI locally with Ollama:\n\n"
                "• Download and install Ollama from "
            )
            info_text_after_link = (
                "\n"
                "• Open Ollama and download a model (e.g., Llama, Mistral)\n"
                "• Load the model in Ollama\n"
                "• The server runs on localhost:11434 by default\n\n"
                "Benefits of Local AI:\n"
                "• 🔒 Complete privacy - your data never leaves your computer\n"
                "• 💰 Free - no API costs or subscriptions\n"
                "• 🌐 Works offline - no internet required"
            )
            info_text = None  # Signal to use Text widget with link
        
        if info_text:  # Connected but no models case - use simple label
            info_label = tk.Label(
                info_frame,
                text=info_text,
                font=('Arial', 10),
                fg='#333333',
                bg='#FFFDE6',
                justify=tk.LEFT,
                anchor=tk.NW
            )
            info_label.pack(anchor=tk.W, fill=tk.BOTH, expand=True)
        else:
            # Use Text widget to support clickable link
            import webbrowser
            info_text_widget = tk.Text(
                info_frame,
                font=('Arial', 10),
                fg='#333333',
                bg='#FFFDE6',
                wrap=tk.WORD,
                height=12,
                borderwidth=0,
                highlightthickness=0,
                cursor="arrow"
            )
            info_text_widget.pack(anchor=tk.W, fill=tk.BOTH, expand=True)
            
            # Configure hyperlink tag
            info_text_widget.tag_configure("hyperlink", foreground="#0066CC", underline=True)
            info_text_widget.tag_bind("hyperlink", "<Button-1>", lambda e: webbrowser.open("https://ollama.com/download"))
            info_text_widget.tag_bind("hyperlink", "<Enter>", lambda e: info_text_widget.config(cursor="hand2"))
            info_text_widget.tag_bind("hyperlink", "<Leave>", lambda e: info_text_widget.config(cursor="arrow"))
            
            # Insert text with link
            info_text_widget.insert(tk.END, info_text_before_link)
            info_text_widget.insert(tk.END, "ollama.com/download", "hyperlink")
            info_text_widget.insert(tk.END, info_text_after_link)
            
            # Make read-only
            info_text_widget.config(state=tk.DISABLED)
        
        # Button frame - two rows for better layout
        btn_frame_top = tk.Frame(main_frame, bg='#dcdad5')
        btn_frame_top.pack(fill=tk.X, pady=(15, 5))
        
        btn_frame_bottom = tk.Frame(main_frame, bg='#dcdad5')
        btn_frame_bottom.pack(fill=tk.X, pady=(0, 0))
        
        def open_guide():
            result['action'] = 'open_guide'
            dialog.destroy()
        
        def continue_action():
            result['action'] = 'continue'
            dialog.destroy()
        
        def cancel():
            result['action'] = 'cancel'
            dialog.destroy()
        
        # Top row buttons - always show since dialog only appears when there's a problem
        def launch_and_connect():
            """Launch Ollama and automatically check for connection"""
            import subprocess
            import os
            
            # Find Ollama
            possible_paths = [
                os.path.expandvars(r"%PROGRAMFILES%\Ollama\Ollama.exe"),
                os.path.expandvars(r"%PROGRAMFILES(X86)%\Ollama\Ollama.exe"),
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\Ollama.exe"),
                os.path.expanduser(r"~\AppData\Local\Programs\Ollama\Ollama.exe"),
            ]
            
            ollama_path = None
            for path in possible_paths:
                if os.path.exists(path):
                    ollama_path = path
                    break
            
            if not ollama_path:
                # Try desktop shortcut
                desktop_shortcut = os.path.expanduser(r"~\Desktop\Ollama.lnk")
                if os.path.exists(desktop_shortcut):
                    ollama_path = desktop_shortcut
                else:
                    # Ask user to locate it
                    from tkinter import filedialog
                    ollama_path = filedialog.askopenfilename(
                        title="Locate Ollama.exe",
                        filetypes=[("Executable", "*.exe"), ("All files", "*.*")],
                        initialdir=os.path.expandvars(r"%PROGRAMFILES%")
                    )
                    if not ollama_path:
                        return
            
            # Show launching dialog with auto-connect
            self._show_ollama_launching_dialog(
                dialog, ollama_path, base_url,
                check_ollama_connection, result, update_status_display
            )
        
        ttk.Button(
            btn_frame_top,
            text="🚀 Launch & Connect",
            command=launch_and_connect,
            width=20
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        # Always show Local AI Guide
        ttk.Button(
            btn_frame_top,
            text="📖 Local AI Guide",
            command=open_guide,
            width=18
        ).pack(side=tk.LEFT, padx=5)
        
        # Bottom row buttons
        ttk.Button(
            btn_frame_bottom,
            text="Cancel",
            command=cancel,
            width=12
        ).pack(side=tk.RIGHT, padx=(5, 0))
        
        # Continue button - stored as variable so we can update its text
        continue_text = "▶ Continue" if connected else "▶ Try Anyway"
        continue_btn = ttk.Button(
            btn_frame_bottom,
            text=continue_text,
            command=continue_action,
            width=14
        )
        continue_btn.pack(side=tk.RIGHT, padx=5)
        
        # Set initial status display
        update_status_display(connected, models, status)
        
        # Wait for dialog
        dialog.wait_window()
        
        return result['action']
    
    def _show_ollama_launching_dialog(self, parent_dialog, ollama_path, base_url, check_connection_func, parent_result, update_parent_status):
        """
        Show a dialog while launching Ollama with auto-polling for connection.
        Auto-continues when connected with models available.
        """
        import subprocess
        import threading
        
        # Create launching dialog - matching app styling
        launch_dialog = tk.Toplevel(self.root)
        launch_dialog.title("🚀 Connecting to Ollama")
        launch_dialog.configure(bg='#dcdad5')
        self.apply_window_style(launch_dialog)
        launch_dialog.transient(self.root)
        launch_dialog.grab_set()
        
        # Size and position
        launch_dialog.geometry("450x320")
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - 225
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - 160
        launch_dialog.geometry(f"+{x}+{y}")
        
        # Main frame
        main_frame = tk.Frame(launch_dialog, bg='#dcdad5', padx=20, pady=15)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Status label
        status_var = tk.StringVar(value="🚀 Launching Ollama...")
        status_label = tk.Label(
            main_frame,
            textvariable=status_var,
            font=('Arial', 11, 'bold'),
            fg='#333333',
            bg='#dcdad5'
        )
        status_label.pack(pady=(0, 15))
        
        # Progress bar
        progress = ttk.Progressbar(main_frame, mode='indeterminate', length=350)
        progress.pack(pady=(0, 15))
        progress.start(10)
        
        # Instructions in soft yellow box
        info_frame = tk.Frame(main_frame, bg='#FFFDE6', padx=15, pady=15)
        info_frame.pack(fill=tk.BOTH, expand=True)
        
        instructions_var = tk.StringVar(value=(
            "Waiting for Ollama to start...\n\n"
            "If this is your first time, you may need to:\n\n"
            "1️⃣  Load a model in Ollama (Home tab)\n"
            "2️⃣  Start the server (Developer tab → Start Server)\n\n"
            "💡 Once connected, your prompt will run automatically."
        ))
        
        instructions_label = tk.Label(
            info_frame,
            textvariable=instructions_var,
            font=('Arial', 10),
            fg='#333333',
            bg='#FFFDE6',
            justify=tk.LEFT,
            anchor=tk.NW
        )
        instructions_label.pack(anchor=tk.W, fill=tk.BOTH, expand=True)
        
        # Button frame
        btn_frame = tk.Frame(main_frame, bg='#dcdad5')
        btn_frame.pack(fill=tk.X, pady=(15, 0))
        
        # Control variables
        polling_active = {'value': True}
        poll_count = {'value': 0}
        
        def stop_polling_and_close():
            """Stop polling and close dialog"""
            polling_active['value'] = False
            progress.stop()
            launch_dialog.destroy()
        
        def auto_continue():
            """Auto-continue to run the prompt"""
            polling_active['value'] = False
            parent_result['action'] = 'continue'
            progress.stop()
            launch_dialog.destroy()
            parent_dialog.destroy()
        
        def poll_for_connection():
            """Poll for Ollama connection every 3 seconds"""
            if not polling_active['value']:
                return
            
            poll_count['value'] += 1
            status_var.set(f"🔄 Checking connection... (attempt {poll_count['value']})")
            launch_dialog.update()
            
            try:
                connected, status, models = check_connection_func(base_url)
                
                if connected:
                    if models and len(models) > 0:
                        # Connected with models - auto-continue!
                        progress.stop()
                        status_var.set(f"✅ Connected! {len(models)} model(s) available")
                        update_parent_status(True, models, status)
                        launch_dialog.update()
                        
                        # Brief pause to show success, then auto-continue
                        launch_dialog.after(800, auto_continue)
                        return
                    else:
                        # Connected but no models
                        progress.stop()
                        status_var.set("⚠️ Connected but no models loaded")
                        instructions_var.set(
                            "Ollama is running but no models are loaded.\n\n"
                            "Please load a model in Ollama:\n\n"
                            "1️⃣  Go to the Home tab\n"
                            "2️⃣  Select a downloaded model\n"
                            "3️⃣  Click 'Load' to load it into memory\n\n"
                            "The connection will be checked again automatically."
                        )
                        # Continue polling
                        launch_dialog.after(3000, poll_for_connection)
                        return
                else:
                    # Not connected yet - update status and keep polling
                    if poll_count['value'] <= 10:
                        status_var.set(f"🔄 Waiting for Ollama... (attempt {poll_count['value']})")
                        launch_dialog.after(3000, poll_for_connection)
                    else:
                        # After 30 seconds, slow down polling
                        status_var.set(f"⏳ Still waiting... (attempt {poll_count['value']})")
                        instructions_var.set(
                            "Ollama is taking a while to connect.\n\n"
                            "Please ensure in Ollama:\n\n"
                            "1️⃣  A model is loaded (Home tab)\n"
                            "2️⃣  Server is started (Developer tab)\n\n"
                            "Click 'Check Now' to test immediately,\n"
                            "or 'Cancel' to abort."
                        )
                        # Show manual check button after timeout
                        check_btn.pack(side=tk.LEFT, padx=(0, 10))
                        launch_dialog.after(5000, poll_for_connection)
            except Exception as e:
                # Error during check - keep trying
                launch_dialog.after(3000, poll_for_connection)
        
        def manual_check():
            """Manual connection check"""
            poll_count['value'] = 0  # Reset count
            poll_for_connection()
        
        # Check Now button (hidden initially, shown after timeout)
        check_btn = ttk.Button(
            btn_frame,
            text="🔄 Check Now",
            command=manual_check,
            width=12
        )
        # Don't pack yet - will be shown after timeout if needed
        
        ttk.Button(
            btn_frame,
            text="Cancel",
            command=stop_polling_and_close,
            width=10
        ).pack(side=tk.RIGHT)
        
        # Launch Ollama in background
        def launch_app():
            try:
                import platform
                if platform.system() == 'Windows':
                    desktop_shortcut = os.path.expanduser(r"~\Desktop\Ollama.lnk")
                    if os.path.exists(desktop_shortcut):
                        os.startfile(desktop_shortcut)
                    else:
                        os.startfile(ollama_path)
                else:
                    ollama_dir = os.path.dirname(ollama_path)
                    subprocess.Popen([ollama_path], shell=False, cwd=ollama_dir)
                
                # Start polling after a short delay to let Ollama start
                launch_dialog.after(2000, poll_for_connection)
                
            except Exception as e:
                launch_dialog.after(100, lambda: status_var.set(f"❌ Launch failed: {str(e)}"))
                launch_dialog.after(100, lambda: progress.stop())
                launch_dialog.after(100, lambda: messagebox.showerror(
                    "Launch Failed",
                    f"Could not launch Ollama:\n\n{str(e)}\n\n"
                    f"Please try launching it manually, then click 'Check Now'."
                ))
                launch_dialog.after(100, lambda: check_btn.pack(side=tk.LEFT, padx=(0, 10)))
        
        # Start launch in background thread
        threading.Thread(target=launch_app, daemon=True).start()
        
        # Bind Escape to close
        launch_dialog.bind('<Escape>', lambda e: stop_polling_and_close())

    def save_thread_to_library(self):
        """Save current conversation thread as a new document in the library"""
        if not self.current_document_id:
            messagebox.showinfo("No Document", "Please load a document first.")
            return

        if not self.current_thread or self.thread_message_count == 0:
            messagebox.showinfo("No Thread",
                                "No conversation thread to save.\n\nStart a conversation by running a prompt first.")
            return

        # Confirm with user
        response = messagebox.askyesno(
            "Save Thread to Library",
            f"Save this conversation thread to the Documents Library?\n\n"
            f"Messages: {self.thread_message_count}\n"
            f"Model: {self.model_var.get()}\n\n"
            f"The thread will be saved as a new entry with [Thread] prefix."
        )

        if not response:
            return

        # Prepare metadata
        metadata = {
            "model": self.model_var.get(),
            "provider": self.provider_var.get(),
            "last_updated": datetime.datetime.now().isoformat(),
            "message_count": self.thread_message_count
        }

        # Save as new document
        from document_library import save_thread_as_new_document
        thread_id = save_thread_as_new_document(
            self.current_document_id,
            self.current_thread,
            metadata
        )

        if thread_id:
            messagebox.showinfo(
                "Thread Saved!",
                f"✅ Conversation thread saved to library!\n\n"
                f"📊 Details:\n"
                f"  • Messages: {self.thread_message_count}\n"
                f"  • Model: {self.model_var.get()}\n"
                f"  • Provider: {self.provider_var.get()}\n\n"
                f"You can find it in the Documents Library with the [Thread] prefix."
            )
            # Refresh library if it's open
            self.refresh_library()
        else:
            messagebox.showerror(
                "Save Failed",
                "Failed to save thread to library.\n\nCheck console for error details."
            )

    """
    BUTTON CODE TO ADD

    Find the conversation buttons row around line 1611 and add this button:
    """

    def force_reprocess_pdf(self):
        """Force re-OCR of current PDF"""
        self.force_reprocess_var.set(True)
        self.fetch_local_file()

    def download_youtube_video(self):
        """Download YouTube video (placeholder for now)"""
        messagebox.showinfo("Download Video",
                            "Video download feature coming soon!\n\n" +
                            "For now, you can use:\n" +
                            "• youtube-dl or yt-dlp command line tools\n" +
                            "• Online YouTube downloaders")

    def open_web_url_in_browser(self):
        """Open current web URL in default browser"""
        url = self.web_url_var.get()
        if url:
            webbrowser.open(url)
        else:
            messagebox.showwarning("No URL", "Please enter a web URL first")

    def export_document(self):
        """Export current document (placeholder for now)"""
        if not self.current_document_text and not self.current_entries:
            messagebox.showwarning("No Document", "Please load a document first")
            return

        messagebox.showinfo("Export Document",
                            "Document export feature coming soon!\n\n" +
                            "For now, you can:\n" +
                            "• Copy text from preview\n" +
                            "• Use the Save button to save outputs")

    def send_to_turboscribe(self):
        """
        Send current audio file to TurboScribe for transcription.
        Copies file to Desktop and opens TurboScribe website.
        """
        audio_path = self.audio_path_var.get()

        if not audio_path:
            messagebox.showerror("No Audio File", "Please select an audio file first.")
            return

        if not os.path.exists(audio_path):
            messagebox.showerror("File Not Found", f"Audio file not found: {audio_path}")
            return

        try:
            # Copy file to desktop folder
            destination = turboscribe_helper.export_for_turboscribe(audio_path)

            # Open TurboScribe website
            turboscribe_helper.open_turboscribe_website()

            # Show instructions
            instructions = (
                f"✅ Audio file copied to:\n{destination}\n\n"
                "📋 Next steps:\n"
                "1. TurboScribe website should open in your browser\n"
                "2. Upload the file from the TurboScribe_Uploads folder\n"
                "3. Wait for transcription to complete\n"
                "4. Download the transcript (TXT, DOCX, or SRT format)\n"
                "5. Click 'Import Transcript' button to bring it back to DocAnalyser\n\n"
                "💡 TurboScribe FREE tier: 3 transcriptions/day, 30 minutes each\n"
                "   with superior speaker identification!"
            )

            messagebox.showinfo("TurboScribe Export", instructions)

        except Exception as e:
            messagebox.showerror("Export Failed", f"Failed to export audio:\n{str(e)}")

    def import_turboscribe(self):
        """
        Import TurboScribe transcript file and convert to DocAnalyser format.
        Supports TXT, DOCX, and SRT formats.
        """
        # File dialog to select transcript
        file_path = filedialog.askopenfilename(
            title="Select TurboScribe Transcript",
            filetypes=[
                ("All Supported", "*.txt *.docx *.srt"),
                ("Text files", "*.txt"),
                ("Word documents", "*.docx"),
                ("Subtitle files", "*.srt"),
                ("All files", "*.*")
            ]
        )

        if not file_path:
            return

        try:
            self.set_status("📄 Parsing TurboScribe transcript...")

            # Parse the transcript file
            segments = turboscribe_helper.parse_turboscribe_file(file_path)

            # Validate
            is_valid, error = turboscribe_helper.validate_turboscribe_import(segments)
            if not is_valid:
                messagebox.showerror("Invalid Transcript", f"Validation failed:\n{error}")
                return

            # Get statistics
            stats = turboscribe_helper.get_transcript_stats(segments)

            # Convert to DocAnalyser entries format
            entries = []
            for seg in segments:
                entries.append({
                    'start': seg['start'],
                    'text': seg['text'],
                    'speaker': seg.get('speaker', 'Unknown'),
                    'timestamp': seg.get('timestamp', '')
                })

            # Store in current document
            self.current_entries = entries
            self.current_document_source = file_path
            self.current_document_type = "turboscribe_import"

            # Convert to text for display
            self.current_document_text = entries_to_text_with_speakers(
                self.current_entries,
                timestamp_interval=self.config.get("timestamp_interval", "5min")
            )

            # Add to library
            title = f"TurboScribe: {os.path.basename(file_path)}"
            doc_id = add_document_to_library(
                doc_type="turboscribe_import",
                source=file_path,
                title=title,
                entries=self.current_entries,
                document_class="source",
                metadata={
                    "speakers": stats['speakers'],
                    "duration": stats['total_duration_formatted'],
                    "segment_count": stats['total_segments']
                }
            )
            # ✅ FIX: Save old thread BEFORE changing document ID
            if self.thread_message_count > 0 and self.current_document_id:
                self.save_current_thread()
            
            # Clear thread manually
            self.current_thread = []
            self.thread_message_count = 0
            self.update_thread_status()
            
            # NOW change the document ID
            self.current_document_id = doc_id
            # Get document class and metadata from library
            doc = get_document_by_id(doc_id)
            if doc:
                self.current_document_class = doc.get("document_class", "source")
                self.current_document_metadata = doc.get("metadata", {})
                # CRITICAL FIX: Add title to metadata if not already there
                if 'title' not in self.current_document_metadata and 'title' in doc:
                    self.current_document_metadata['title'] = doc['title']
            else:
                self.current_document_class = "source"
                self.current_document_metadata = {}

            # Get document class and metadata from library
            doc = get_document_by_id(doc_id)
            if doc:
                self.current_document_class = doc.get("document_class", "source")
                self.current_document_metadata = doc.get("metadata", {})
                # CRITICAL FIX: Add title to metadata if not already there
                if 'title' not in self.current_document_metadata and 'title' in doc:
                    self.current_document_metadata['title'] = doc['title']
            else:
                self.current_document_class = "source"
                self.current_document_metadata = {}

            # Show success message
            success_msg = (
                f"✅ TurboScribe transcript imported successfully!\n\n"
                f"📊 Statistics:\n"
                f"  • Segments: {stats['total_segments']}\n"
                f"  • Duration: {stats['total_duration_formatted']}\n"
                f"  • Speakers: {', '.join(stats['speakers'])}\n\n"
                f"The transcript is now ready for AI analysis!"
            )

            self.set_status(f"✅ Imported TurboScribe transcript: {title}")
            messagebox.showinfo("Import Successful", success_msg)
            self.refresh_library()
            
            # Update button states (View Source, etc.)
            self.update_button_states()

        except Exception as e:
            error_msg = f"Failed to import transcript:\n{str(e)}"
            messagebox.showerror("Import Failed", error_msg)
            self.set_status("❌ TurboScribe import failed")
            import traceback
            traceback.print_exc()

    def test_semantic_search(self):
        """
        Test the semantic search module with a real API call.
        This verifies the module is working with your OpenAI key.
        """
        try:
            from semantic_search import SemanticSearch, test_semantic_search
            
            # First run basic tests (no API)
            test_semantic_search()
            
            # Get OpenAI key from config
            openai_key = self.config.get("keys", {}).get("OpenAI (ChatGPT)", "")
            
            if not openai_key:
                messagebox.showwarning(
                    "No API Key",
                    "No OpenAI API key found.\n\n"
                    "Semantic search requires an OpenAI key for generating embeddings.\n\n"
                    "Please add your OpenAI key in Settings."
                )
                return
            
            # Test with real API call
            self.set_status("🧠 Testing semantic search with OpenAI API...")
            self.root.update()
            
            ss = SemanticSearch(api_key=openai_key, provider="openai")
            
            # Generate a test embedding
            test_text = "This is a test document about Python programming and machine learning."
            embedding, cost = ss.generate_embedding(test_text)
            
            # Log the cost
            from cost_tracker import log_cost
            log_cost(
                provider="OpenAI (ChatGPT)",
                model="text-embedding-3-small",
                cost=cost,
                document_title="Semantic Search Test",
                prompt_name="embedding_generation"
            )
            
            messagebox.showinfo(
                "Semantic Search Test",
                f"✅ Semantic search is working!\n\n"
                f"Generated embedding with {len(embedding)} dimensions\n"
                f"Cost: ${cost:.6f}\n\n"
                f"You're ready to use semantic search in the Document Library!"
            )
            
            self.set_status("✅ Semantic search test successful!")
            
        except ImportError as e:
            messagebox.showerror(
                "Module Not Found",
                f"Could not import semantic_search module.\n\n"
                f"Make sure semantic_search.py is in your project folder.\n\n"
                f"Error: {str(e)}"
            )
        except Exception as e:
            messagebox.showerror(
                "Test Failed",
                f"Semantic search test failed:\n\n{str(e)}"
            )
            self.set_status("❌ Semantic search test failed")

    def show_costs(self):
        """Display API costs dialog - delegates to cost_tracker module"""
        from cost_tracker import show_costs_dialog
        show_costs_dialog(self.root)

    def open_add_sources(self):
        """
        Open the unified Add Sources dialog.
        
        Allows users to add sources to either:
        - Documents Library (permanent)
        - Prompt Context (temporary, for multi-document analysis)
        """
        print("Opening Add Sources dialog...")
        
        def get_current_settings():
            return {
                'provider': self.provider_var.get(),
                'model': self.model_var.get(),
                'prompt_name': self.prompt_combo.get() if hasattr(self, 'prompt_combo') else 'Default',
                'prompt_text': self.prompt_text.get('1.0', tk.END).strip() if hasattr(self, 'prompt_text') else ''
            }
        
        def process_single_item(url_or_path: str, status_callback) -> tuple:
            """
            Process a single URL or file path.
            Returns: (success: bool, result_or_error: str, title: Optional[str])
            """
            try:
                url_or_path = url_or_path.strip()
                
                # Check if it's a file
                if os.path.isfile(url_or_path):
                    status_callback(f"Processing file: {os.path.basename(url_or_path)}")
                    ext = os.path.splitext(url_or_path)[1].lower()
                    
                    # Check for audio/video files - skip (need transcription)
                    if ext in ('.mp3', '.wav', '.m4a', '.ogg', '.flac', '.aac', '.wma', '.opus', '.mp4', '.avi', '.mov'):
                        return False, "Audio/video files require transcription (use Load button instead)", None
                    
                    # Use document fetcher for files
                    doc_fetcher = get_doc_fetcher()
                    success, result, title, doc_type = doc_fetcher.fetch_local_file(url_or_path)
                    
                    if success:
                        if isinstance(result, list):
                            text = doc_fetcher.legacy_entries_to_text(result, include_timestamps=False)
                        else:
                            text = str(result)
                        return True, text, title or os.path.basename(url_or_path)
                    else:
                        error_msg = str(result) if result else "Could not extract text from file"
                        return False, error_msg, None
                
                # Check if it's a YouTube URL
                from youtube_utils import is_youtube_url, get_youtube_transcript
                if is_youtube_url(url_or_path):
                    status_callback("Fetching YouTube transcript...")
                    result = get_youtube_transcript(url_or_path, status_callback=status_callback)
                    if result and result.get('text'):
                        return True, result['text'], result.get('title', 'YouTube Video')
                    else:
                        return False, "Could not fetch YouTube transcript", None
                
                # Try as generic web URL
                if url_or_path.startswith(('http://', 'https://')):
                    status_callback("Fetching web content...")
                    try:
                        doc_fetcher = get_doc_fetcher()
                        success, result, title = doc_fetcher.fetch_from_url(url_or_path)
                        if success:
                            if isinstance(result, list):
                                text = doc_fetcher.legacy_entries_to_text(result, include_timestamps=False)
                            else:
                                text = str(result)
                            return True, text, title or url_or_path
                        else:
                            return False, result, None
                    except Exception as e:
                        return False, f"Error fetching URL: {str(e)}", None
                
                return False, "Unknown source type", None
                
            except Exception as e:
                return False, str(e), None
        
        def save_to_library(title: str, content: str, source: str, doc_class: str = 'source'):
            """Save content to the document library."""
            try:
                if doc_class == 'product':
                    location_tag = 'AI Response'
                else:
                    location_tag = 'Added via Sources Dialog'
                entries = [{'text': content, 'start': 0, 'location': location_tag}]
                
                if doc_class == 'product':
                    doc_type = "ai_response"
                else:
                    doc_type = "imported"
                
                doc_id = add_document_to_library(
                    doc_type=doc_type,
                    source=source,
                    title=title,
                    entries=entries,
                    document_class=doc_class,
                    metadata={
                        "imported_via": "sources_dialog",
                        "fetched": datetime.datetime.now().isoformat() + 'Z'
                    }
                )
                return doc_id
            except Exception as e:
                print(f"Failed to save to library: {e}")
                return None
        
        def on_complete():
            """Called when sources dialog closes with changes."""
            self.update_add_sources_button()
        
        # Open the unified sources dialog
        open_sources_dialog(
            parent=self.root,
            process_callback=process_single_item,
            get_settings_callback=get_current_settings,
            save_to_library_callback=save_to_library,
            ai_process_callback=None,
            attachment_manager=self.attachment_manager,
            mode="unified",
            status_callback=self.set_status,
            get_provider_callback=lambda: self.provider_var.get(),
            on_complete_callback=on_complete
        )

    def update_add_sources_button(self):
        """Update the Add Sources button to show attachment count."""
        # Add sources button removed - using multi-line input

if __name__ == "__main__":
    # Use TkinterDnD root if available for drag-and-drop support
    if DND_AVAILABLE:
        root = TkinterDnD.Tk()
        safe_print("Using TkinterDnD - Drag-and-drop enabled")
    else:
        root = tk.Tk()
        safe_print("Using standard Tkinter - Drag-and-drop unavailable")
        safe_print("   To enable drag-and-drop, install: pip install tkinterdnd2")
    
    app = DocAnalyserApp(root)
    
    # Show first-run wizard if this is the first launch
    if WIZARD_AVAILABLE and not has_run_before():
        def on_wizard_complete():
            safe_print("First-run wizard completed")
        
        # Show wizard after a short delay to let the main window initialize
        root.after(500, lambda: show_first_run_wizard(
            root,
            on_complete_callback=on_wizard_complete,
            show_local_ai_guide_callback=app._open_local_ai_guide
        ))
    
    root.mainloop()
