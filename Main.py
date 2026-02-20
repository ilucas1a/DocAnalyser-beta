
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
from local_ai_dialogs import LocalAIMixin
from document_fetching import DocumentFetchingMixin
from ocr_processing import OCRProcessingMixin
from library_interaction import LibraryInteractionMixin
from viewer_thread import ViewerThreadMixin
from process_output import ProcessOutputMixin
from export_utilities import ExportUtilitiesMixin
from smart_load import SmartLoadMixin

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

class DocAnalyserApp(SettingsMixin, LocalAIMixin, DocumentFetchingMixin, OCRProcessingMixin, LibraryInteractionMixin, ViewerThreadMixin, ProcessOutputMixin, ExportUtilitiesMixin, SmartLoadMixin):

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
