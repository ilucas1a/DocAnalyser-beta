"""
settings_manager.py - Settings dialogs and configuration UI for DocAnalyser.

Extracted from Main.py to reduce file size. Uses a mixin pattern so all
self.xxx references continue to work unchanged.

Methods included:
  - _show_settings_menu()     Settings dropdown menu
  - _save_and_close_settings() Shared save helper
  - open_ai_settings()        AI provider, model, API keys, Ollama
  - open_general_settings()   Display thresholds, cache control
  - open_about_dialog()       Version, updates, diagnostics
  - open_local_ai_setup()     Step-by-step Local AI setup wizard with hardware detection
  - on_provider_select_in_settings()
  - save_api_key_in_settings()
  - _save_ollama_url(), _test_ollama_connection(), _is_ollama_installed()
  - _show_system_recommendations()
  - _open_local_ai_guide(), _show_guide_in_window()
  - save_model_selection()
  - open_prompt_manager(), save_prompt()
  - refresh_main_prompt_combo(), set_prompt_from_library()
  - open_chunk_settings()
  - open_ocr_settings()
  - open_audio_settings()
  - show_tesseract_setup_wizard(), test_ocr_setup()
  - open_google_drive_dialog()

"""

import os
import platform
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

# Config constants
from config import (
    PROMPTS_PATH,
    CHUNK_SIZES,
    OCR_MODES,
    OCR_PRESETS,
    OCR_LANGUAGES,
    TRANSCRIPTION_ENGINES,
    PROVIDER_REGISTRY,
)

# Config manager functions
from config_manager import save_config, load_prompts

# Utility functions
from utils import save_json_atomic

# Prompt dropdown helpers
from prompt_dropdown_builder import (
    build_dropdown_auto,
    extract_prompt_name,
    is_separator,
    is_header,
)

# Version info
from version import APP_DISPLAY_NAME, get_version_string

# Context-sensitive help (optional - graceful fallback)
try:
    from context_help import add_help, HELP_TEXTS
    CONTEXT_HELP_AVAILABLE = True
except ImportError:
    def add_help(*args, **kwargs): pass
    CONTEXT_HELP_AVAILABLE = False
    HELP_TEXTS = {}


# Lazy import helper for ocr_handler (mirrors Main.py's get_ocr)
def get_ocr():
    import ocr_handler
    return ocr_handler


class SettingsMixin:
    """Mixin class providing all settings dialog methods for DocAnalyzerApp."""

    # ============================================================
    # SETTINGS MENU (replaces monolithic "All Settings" dialog)
    # ============================================================

    def _show_settings_menu(self, event):
        """Show a dropdown menu of settings categories."""
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="AI Settings", command=self.open_ai_settings)
        menu.add_command(label="General & Display", command=self.open_general_settings)
        menu.add_command(label="Chunk Settings", command=self.open_chunk_settings)
        menu.add_command(label="Audio & Transcription", command=self.open_audio_settings)
        menu.add_command(label="OCR Settings", command=self.open_ocr_settings)
        menu.add_separator()
        menu.add_command(label="Google Drive", command=self.open_google_drive_dialog)
        menu.add_separator()
        menu.add_command(label="Local AI Setup", command=self.open_local_ai_setup)
        menu.add_command(label="About & Updates", command=self.open_about_dialog)
        menu.tk_popup(event.x_root, event.y_root)

    def open_google_drive_dialog(self):
        """Open the Google Drive file browser dialog."""
        try:
            from google_drive_dialog import open_google_drive_dialog
            open_google_drive_dialog(self.root, self)
        except ImportError as e:
            from tkinter import messagebox
            messagebox.showerror(
                "Google Drive",
                f"Could not load the Google Drive dialog:\n\n{e}\n\n"
                "Make sure google_drive_dialog.py is in the application folder.",
            )

    def _save_and_close_settings(self, updates: dict, dialog, message="Settings saved"):
        """Shared save helper: merge updates into config, save, confirm, close."""
