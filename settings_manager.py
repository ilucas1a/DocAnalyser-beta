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
        menu.add_command(label="Local AI Setup", command=self.open_local_ai_setup)
        menu.add_command(label="About & Updates", command=self.open_about_dialog)
        menu.tk_popup(event.x_root, event.y_root)

    def _save_and_close_settings(self, updates: dict, dialog, message="Settings saved"):
        """Shared save helper: merge updates into config, save, confirm, close."""
        for key, value in updates.items():
            self.config[key] = value
        save_config(self.config)
        messagebox.showinfo("Success", message)
        dialog.destroy()

    def _close_with_save_check(self, dialog, get_current_values, initial_values, save_func, saved_flag):
        """Check for unsaved changes before closing a settings dialog.
        
        Args:
            dialog: The Toplevel window
            get_current_values: Callable returning dict of current field values
            initial_values: Dict of values captured when dialog opened
            save_func: Callable to save settings (the dialog's save function)
            saved_flag: List with single bool, e.g. [False]; set to True by save_func
        """
        if saved_flag[0]:
            dialog.destroy()
            return
        try:
            current = get_current_values()
            if current != initial_values:
                result = messagebox.askyesno(
                    "Unsaved Changes",
                    "You have unsaved changes. Save before closing?",
                    parent=dialog
                )
                if result:
                    save_func()
                    return  # save_func closes the dialog via _save_and_close_settings
        except Exception:
            pass
        dialog.destroy()

    # ============================================================
    # AI CONFIGURATION DIALOG
    # ============================================================

    def open_ai_settings(self):
        """AI provider, model, API keys, and Ollama configuration."""
        settings = tk.Toplevel(self.root)
        settings.title("AI Settings")
        settings.geometry("650x480")
        self.apply_window_style(settings)

        # --- Bottom buttons (pack FIRST so they're always visible) ---
        bottom_frame = ttk.Frame(settings)
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=5, padx=20)

        # --- Scrollable content area ---
        canvas = tk.Canvas(settings, highlightthickness=0)
        v_scrollbar = ttk.Scrollbar(settings, orient="vertical", command=canvas.yview)
        content_frame = ttk.Frame(canvas)

        content_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas_window = canvas.create_window((0, 0), window=content_frame, anchor="nw")
        canvas.configure(yscrollcommand=v_scrollbar.set)

        v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        def _on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=event.width)
        canvas.bind("<Configure>", _on_canvas_configure)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        settings.bind("<Destroy>", lambda e: canvas.unbind_all("<MouseWheel>") if e.widget == settings else None)

        ttk.Label(content_frame, text="⚙️ AI Settings", font=('Arial', 12, 'bold')).pack(pady=(5, 2))

        # AI Provider and Model Frame
        ai_frame = ttk.LabelFrame(content_frame, text="AI Provider & Model", padding=5)
        ai_frame.pack(fill=tk.X, padx=20, pady=3)

        # Provider row
        provider_row = ttk.Frame(ai_frame)
        provider_row.pack(fill=tk.X, pady=2)
        ttk.Label(provider_row, text="AI Provider:", width=12).pack(side=tk.LEFT)
        provider_combo = ttk.Combobox(provider_row, textvariable=self.provider_var,
                                      state="readonly", width=25)
        provider_combo['values'] = list(self.models.keys())
        provider_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        provider_change_callbacks = []

        provider_combo.bind('<<ComboboxSelected>>', lambda e: (self.on_provider_select_in_settings(e),
                                                               [cb() for cb in provider_change_callbacks]))

        # Set as Default button
        def set_default_provider():
            provider = self.provider_var.get()
            self.config["default_provider"] = provider
            self.config["last_provider"] = provider
            save_config(self.config)
            _update_default_hint()
            self.set_status(f"✅ Default AI provider set to {provider}")
        
        ttk.Button(provider_row, text="Set Default", command=set_default_provider, width=10).pack(side=tk.LEFT, padx=2)

        # Model row
        model_row = ttk.Frame(ai_frame)
        model_row.pack(fill=tk.X, pady=2)
        ttk.Label(model_row, text="Model:", width=12).pack(side=tk.LEFT)
        self.model_combo = ttk.Combobox(model_row, textvariable=self.model_var,
                                        state="readonly", width=25)
        self.model_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.model_combo.bind('<<ComboboxSelected>>', lambda e: self.save_model_selection())

        # Set as Default model button
        def set_default_model():
            provider = self.provider_var.get()
            model = self.model_var.get()
            if model:
                if "default_model" not in self.config:
                    self.config["default_model"] = {}
                self.config["default_model"][provider] = model
                save_config(self.config)
                _update_default_hint()
                self.set_status(f"✅ Default model for {provider} set to {model}")
        
        ttk.Button(model_row, text="Set Default", command=set_default_model, width=10).pack(side=tk.LEFT, padx=2)

        # Model refresh button
        refresh_row = ttk.Frame(ai_frame)
        refresh_row.pack(fill=tk.X, pady=2)
        refresh_btn = ttk.Button(refresh_row, text="🔄 Refresh Models",
                                 command=self.refresh_models_from_apis, width=20)
        refresh_btn.pack(side=tk.LEFT, padx=2)
        if HELP_TEXTS:
            add_help(refresh_btn, **HELP_TEXTS.get("settings_refresh_models", {"title": "Refresh Models",
                                                                               "description": "Fetch latest models from APIs"}))
        ttk.Label(refresh_row, text="(Fetches latest models from APIs)",
                  font=('Arial', 8), foreground='gray').pack(side=tk.LEFT, padx=5)

        # Show current defaults (dynamic — updated when Set Default is clicked)
        default_hint_var = tk.StringVar()
        default_hint_label = ttk.Label(ai_frame, textvariable=default_hint_var,
                                       font=('Arial', 8), foreground='gray')

        def _update_default_hint():
            dp = self.config.get("default_provider", "")
            dm = self.config.get("default_model", {})
            if dp:
                h = f"Default: {dp}"
                dm_val = dm.get(dp, "")
                if dm_val:
                    h += f" / {dm_val}"
                default_hint_var.set(h)
                default_hint_label.pack(anchor=tk.W)
            else:
                default_hint_label.pack_forget()

        _update_default_hint()

        self.on_provider_select_in_settings()

        # API Key Frame — with Get Key and Show buttons
        api_frame = ttk.LabelFrame(content_frame, text="API Key", padding=5)
        api_frame.pack(fill=tk.X, padx=20, pady=3)

        api_row = ttk.Frame(api_frame)
        api_row.pack(fill=tk.X)
        ttk.Label(api_row, text="API Key:", width=12).pack(side=tk.LEFT)
        api_entry = ttk.Entry(api_row, textvariable=self.api_key_var, show="*", width=30)
        api_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        api_entry.bind('<FocusOut>', lambda e: self.save_api_key_in_settings())

        # Provider signup URLs
        provider_signup_urls = {
            "OpenAI (ChatGPT)": ("platform.openai.com", "https://platform.openai.com/api-keys"),
            "Anthropic (Claude)": ("console.anthropic.com", "https://console.anthropic.com/settings/keys"),
            "Google (Gemini)": ("aistudio.google.com", "https://aistudio.google.com/app/apikey"),
            "xAI (Grok)": ("console.x.ai", "https://console.x.ai/"),
            "DeepSeek": ("platform.deepseek.com", "https://platform.deepseek.com/api_keys"),
            "Ollama (Local)": (None, None)
        }

        def open_provider_signup():
            provider = self.provider_var.get()
            url_info = provider_signup_urls.get(provider, (None, None))
            _, url = url_info
            if url:
                webbrowser.open(url)
            else:
                messagebox.showinfo("No Key Needed", "Ollama runs locally and doesn't require an API key.")

        ttk.Button(api_row, text="Get Key", command=open_provider_signup, width=8).pack(side=tk.LEFT, padx=2)

        # Show/hide toggle for API key
        def toggle_api_show():
            if api_entry.cget('show') == '*':
                api_entry.config(show='')
                api_show_btn.config(text="Hide")
            else:
                api_entry.config(show='*')
                api_show_btn.config(text="Show")

        api_show_btn = ttk.Button(api_row, text="Show", command=toggle_api_show, width=5)
        api_show_btn.pack(side=tk.LEFT, padx=2)

        # Ollama Configuration Frame — simplified; full setup via Settings ▾ → Local AI Setup
        lm_frame = ttk.LabelFrame(content_frame, text="Ollama (Local AI)", padding=5)
        lm_frame.pack(fill=tk.X, padx=20, pady=3)

        url_row = ttk.Frame(lm_frame)
        url_row.pack(fill=tk.X, pady=2)
        ttk.Label(url_row, text="Server URL:", width=12).pack(side=tk.LEFT)
        self.ollama_url_var = tk.StringVar(value=self.config.get("ollama_base_url", "http://localhost:11434"))
        url_entry = ttk.Entry(url_row, textvariable=self.ollama_url_var)
        url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        url_entry.bind('<FocusOut>', lambda e: self._save_ollama_url())

        def set_ollama_as_default():
            self.config["default_provider"] = "Ollama (Local)"
            self.config["last_provider"] = "Ollama (Local)"
            self.provider_var.set("Ollama (Local)")
            self.on_provider_select_in_settings()
            save_config(self.config)
            _update_default_hint()
            self.set_status("✅ Default AI provider set to Ollama (Local)")

        ttk.Button(url_row, text="Set Default", command=set_ollama_as_default, width=10).pack(side=tk.LEFT, padx=2)

        ttk.Label(lm_frame, text="For installation, model downloads, and diagnostics: Settings ▾ → Local AI Setup",
                  font=('Arial', 8), foreground='gray').pack(anchor=tk.W, padx=5, pady=(2, 0))

        # About AI Settings
        about_frame = ttk.LabelFrame(content_frame, text="ℹ️ About AI Settings", padding=5)
        about_frame.pack(fill=tk.X, padx=20, pady=3)
        about_text = (
            "Configure which AI provider and model DocAnalyser uses for document analysis. "
            "Cloud providers (OpenAI, Anthropic, Google, xAI, DeepSeek) require an API key. "
            "Ollama provides free local AI — for setup help, use Settings ▾ → Local AI Setup. "
            "Use 'Refresh Models' to fetch the latest available models from each provider."
        )
        ttk.Label(about_frame, text=about_text, font=('Arial', 8), foreground='gray',
                  wraplength=580).pack(anchor=tk.W)

        # Track initial values for unsaved-changes detection
        ai_initial = {
            'provider': self.provider_var.get(),
            'model': self.model_var.get(),
            'api_key': self.api_key_var.get(),
            'ollama_url': self.config.get("ollama_base_url", "http://localhost:11434"),
        }
        saved_flag = [False]

        def get_ai_current():
            return {
                'provider': self.provider_var.get(),
                'model': self.model_var.get(),
                'api_key': self.api_key_var.get(),
                'ollama_url': self.ollama_url_var.get().strip(),
            }

        # Save/Close
        def save():
            saved_flag[0] = True
            updates = {
                "last_provider": self.provider_var.get(),
            }
            provider = self.provider_var.get()
            model = self.model_var.get()
            if provider and model:
                if "last_model" not in self.config:
                    self.config["last_model"] = {}
                self.config["last_model"][provider] = model
            self.save_api_key_in_settings()
            self._save_and_close_settings(updates, settings, "AI settings saved")

        def on_close():
            self._close_with_save_check(settings, get_ai_current, ai_initial, save, saved_flag)

        ttk.Button(bottom_frame, text="Save Settings", command=save).pack(side=tk.LEFT, padx=5)
        ttk.Button(bottom_frame, text="Close", command=on_close).pack(side=tk.RIGHT, padx=5)
        settings.protocol("WM_DELETE_WINDOW", on_close)

    # ============================================================
    # GENERAL & DISPLAY SETTINGS DIALOG
    # ============================================================

    def open_general_settings(self):
        """Viewer display thresholds and cache management."""
        settings = tk.Toplevel(self.root)
        settings.title("General & Display Settings")
        settings.geometry("600x540")
        self.apply_window_style(settings)

        bottom_frame = ttk.Frame(settings)
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=10, padx=20)

        ttk.Label(settings, text="🖥️ General & Display Settings", font=('Arial', 12, 'bold')).pack(pady=10)

        content = ttk.Frame(settings)
        content.pack(fill=tk.BOTH, expand=True, padx=20)

        # === Viewer Display Settings ===
        display_frame = ttk.LabelFrame(content, text="Viewer Display", padding=10)
        display_frame.pack(fill=tk.X, pady=5)

        # Character warning threshold
        char_row = ttk.Frame(display_frame)
        char_row.pack(fill=tk.X, pady=2)
        ttk.Label(char_row, text="Expand warning at:", width=16).pack(side=tk.LEFT)
        char_warning_var = tk.StringVar(
            value=str(self.config.get('viewer_char_warning_threshold', 150000))
        )
        ttk.Entry(char_row, textvariable=char_warning_var, width=12).pack(side=tk.LEFT, padx=5)
        ttk.Label(char_row, text="characters").pack(side=tk.LEFT)
        ttk.Label(display_frame, text="💡 ~50-75 pages of text. Warns before expanding large content in Viewer.",
                  font=('Arial', 8), foreground='gray').pack(anchor=tk.W, padx=(20, 0))

        # Collapse threshold
        collapse_row = ttk.Frame(display_frame)
        collapse_row.pack(fill=tk.X, pady=(8, 2))
        ttk.Label(collapse_row, text="Auto-collapse when:", width=16).pack(side=tk.LEFT)
        collapse_var = tk.StringVar(
            value=str(self.config.get('viewer_collapse_threshold', 2))
        )
        ttk.Spinbox(collapse_row, from_=1, to=20, textvariable=collapse_var, width=5).pack(side=tk.LEFT, padx=5)
        ttk.Label(collapse_row, text="or more source documents").pack(side=tk.LEFT)
        ttk.Label(display_frame, text="💡 Sources start collapsed when you load many documents at once.",
                  font=('Arial', 8), foreground='gray').pack(anchor=tk.W, padx=(20, 0))

        reference_text = (
            "📊 Reference: 1 page ≈ 2,500 chars • 50K = ~20 pages • "
            "150K = ~60 pages • 500K = ~200 pages"
        )
        ttk.Label(display_frame, text=reference_text, font=('Arial', 8),
                  foreground='#555555').pack(anchor=tk.W, pady=(8, 0))

        # === Cache Control ===
        cache_frame = ttk.LabelFrame(content, text="🔄 Cache Control", padding=10)
        cache_frame.pack(fill=tk.X, pady=5)

        limit_row = ttk.Frame(cache_frame)
        limit_row.pack(fill=tk.X, pady=2)
        ttk.Label(limit_row, text="Cache size alert:").pack(side=tk.LEFT)
        cache_limit_var = tk.StringVar(value=str(self.config.get('cache_limit_mb', 500)))
        ttk.Combobox(limit_row, textvariable=cache_limit_var,
                     values=['200', '500', '1000', '2000', '0'],
                     state='readonly', width=8).pack(side=tk.LEFT, padx=5)
        ttk.Label(limit_row, text="MB  (0 = never alert)").pack(side=tk.LEFT)

        # Show current cache size
        try:
            from utils import get_total_cache_size
            cache_info = get_total_cache_size()
            ttk.Label(cache_frame, text=f"Current cache size: {cache_info['total_display']}",
                      font=('Arial', 8), foreground='gray').pack(anchor=tk.W, padx=(20, 0))
        except Exception:
            pass

        ttk.Label(cache_frame,
                  text="💡 You'll be prompted to clear the cache on startup if it exceeds the limit.",
                  font=('Arial', 8), foreground='gray').pack(anchor=tk.W, padx=(20, 0), pady=(3, 0))

        # Clear cache button
        clear_row = ttk.Frame(cache_frame)
        clear_row.pack(fill=tk.X, pady=(5, 0))

        def clear_cache_now():
            from utils import clear_all_caches
            if messagebox.askyesno("Confirm",
                                   "Clear all cached transcriptions and OCR data?\n\n"
                                   "This frees disk space but means files will need\n"
                                   "to be re-processed if loaded again."):
                success, msg = clear_all_caches()
                if success:
                    messagebox.showinfo("Cache Cleared", msg)
                else:
                    messagebox.showerror("Error", msg)

        ttk.Button(clear_row, text="🗑️ Clear Cache Now", command=clear_cache_now).pack(side=tk.LEFT)

        # About
        about_frame = ttk.LabelFrame(content, text="ℹ️ About General Settings", padding=5)
        about_frame.pack(fill=tk.X, pady=5)
        about_text = (
            "Viewer display settings control how loaded documents appear in the Thread Viewer. "
            "The expand warning prevents the UI from freezing when opening very large documents. "
            "Cache stores transcription and OCR results so re-loading the same file is instant. "
            "Use 'Bypass cache' in Audio Settings to force a fresh re-transcription."
        )
        ttk.Label(about_frame, text=about_text, font=('Arial', 8), foreground='gray',
                  wraplength=530).pack(anchor=tk.W)

        # Track initial values for unsaved-changes detection
        gen_initial = {
            'char_warning': char_warning_var.get(),
            'collapse': collapse_var.get(),
            'cache_limit': cache_limit_var.get(),
        }
        saved_flag = [False]

        def get_gen_current():
            return {
                'char_warning': char_warning_var.get(),
                'collapse': collapse_var.get(),
                'cache_limit': cache_limit_var.get(),
            }

        # Save/Close
        def save():
            saved_flag[0] = True
            updates = {}
            try:
                char_threshold = int(char_warning_var.get())
                if char_threshold >= 10000:
                    updates['viewer_char_warning_threshold'] = char_threshold
            except ValueError:
                pass
            try:
                collapse_threshold = int(collapse_var.get())
                if 1 <= collapse_threshold <= 50:
                    updates['viewer_collapse_threshold'] = collapse_threshold
            except ValueError:
                pass
            try:
                updates['cache_limit_mb'] = int(cache_limit_var.get())
            except ValueError:
                updates['cache_limit_mb'] = 500
            self._save_and_close_settings(updates, settings, "General settings saved")

        def on_close():
            self._close_with_save_check(settings, get_gen_current, gen_initial, save, saved_flag)

        ttk.Button(bottom_frame, text="Save Settings", command=save).pack(side=tk.LEFT, padx=5)
        ttk.Button(bottom_frame, text="Close", command=on_close).pack(side=tk.RIGHT, padx=5)
        settings.protocol("WM_DELETE_WINDOW", on_close)

    # ============================================================
    # ABOUT & UPDATES DIALOG
    # ============================================================

    def open_about_dialog(self):
        """Version info, update checks, diagnostics."""
        settings = tk.Toplevel(self.root)
        settings.title("About & Updates")
        settings.geometry("500x420")
        self.apply_window_style(settings)

        ttk.Label(settings, text="ℹ️ About & Updates", font=('Arial', 12, 'bold')).pack(pady=10)

        content = ttk.Frame(settings)
        content.pack(fill=tk.BOTH, expand=True, padx=20)

        # Version info
        version_frame = ttk.LabelFrame(content, text="Version", padding=10)
        version_frame.pack(fill=tk.X, pady=5)
        ttk.Label(version_frame, text=f"{APP_DISPLAY_NAME} {get_version_string()}",
                  font=('Arial', 10, 'bold')).pack(anchor=tk.W)

        # Update checkbox
        self.check_updates_var = tk.BooleanVar(value=self.config.get("check_for_updates", True))
        ttk.Checkbutton(version_frame, text="Check for updates on startup",
                        variable=self.check_updates_var,
                        command=self._save_update_preference).pack(anchor=tk.W, pady=2)

        # Action buttons
        btn_frame = ttk.LabelFrame(content, text="Actions", padding=10)
        btn_frame.pack(fill=tk.X, pady=5)

        btn_row1 = ttk.Frame(btn_frame)
        btn_row1.pack(fill=tk.X, pady=2)
        ttk.Button(btn_row1, text="🔄 Check for Updates",
                   command=self._check_for_updates, width=20).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_row1, text="📋 Feature Status",
                   command=self._show_system_check, width=20).pack(side=tk.LEFT, padx=2)

        btn_row2 = ttk.Frame(btn_frame)
        btn_row2.pack(fill=tk.X, pady=2)
        ttk.Button(btn_row2, text="💾 Export Diagnostics",
                   command=self._export_diagnostics, width=20).pack(side=tk.LEFT, padx=2)

        # About text
        about_frame = ttk.LabelFrame(content, text="ℹ️ About DocAnalyser", padding=5)
        about_frame.pack(fill=tk.X, pady=5)
        about_text = (
            "DocAnalyser processes YouTube videos, podcasts, PDFs, audio files, web pages, "
            "and other documents for AI-powered analysis. Use 'Feature Status' to check which "
            "components are installed. 'Export Diagnostics' creates a report useful for "
            "troubleshooting."
        )
        ttk.Label(about_frame, text=about_text, font=('Arial', 8), foreground='gray',
                  wraplength=430).pack(anchor=tk.W)

        # Close button
        ttk.Button(settings, text="Close", command=settings.destroy).pack(pady=10)


    def on_provider_select_in_settings(self, event=None):
        """Handle provider selection in the settings window"""
        provider = self.provider_var.get()
        
        # Special handling for Ollama - auto-refresh models from server
        if provider == "Ollama (Local)":
            self._refresh_ollama_models(show_errors=True)
            
            # Auto-switch to tiny chunk size for local models with limited context
            current_chunk_size = self.config.get("chunk_size", "medium")
            if current_chunk_size != "tiny":
                # Save the previous chunk size so we can restore it later
                self.config["chunk_size_before_local_ai"] = current_chunk_size
                self.config["chunk_size"] = "tiny"
                save_config(self.config)
                chunk_msg = "Chunk size auto-adjusted to 'Tiny'"
            else:
                chunk_msg = "Using 'Tiny' chunk size"
            
            # Get model count for combined status message
            model_count = len([m for m in self.models.get("Ollama (Local)", []) if not m.startswith("(")])
            if model_count > 0:
                self.set_status(f"✅ Ollama: {model_count} model(s) available | {chunk_msg} for local model compatibility")
            else:
                self.set_status(f"✅ Ollama selected | {chunk_msg} for local model compatibility")
        else:
            # Switching to a cloud provider - restore previous chunk size if we saved one
            saved_chunk_size = self.config.get("chunk_size_before_local_ai")
            if saved_chunk_size:
                current_chunk_size = self.config.get("chunk_size", "medium")
                if current_chunk_size == "tiny":
                    self.config["chunk_size"] = saved_chunk_size
                    # Clear the saved value so we don't keep restoring it
                    del self.config["chunk_size_before_local_ai"]
                    save_config(self.config)
        
        self.model_combo['values'] = self.models.get(provider, [])
        last_model = self.config["last_model"].get(provider, "")
        if last_model in self.models.get(provider, []):
            self.model_var.set(last_model)
        else:
            # For Ollama, select the first available model if any
            if provider == "Ollama (Local)" and self.models.get(provider):
                models_list = self.models.get(provider, [])
                # Skip placeholder entries
                real_models = [m for m in models_list if not m.startswith("(")]
                if real_models:
                    self.model_var.set(real_models[0])
                else:
                    self.model_var.set("")
            else:
                self.model_var.set("")
        self.api_key_var.set(self.config["keys"].get(provider, ""))
        
        # If default to recommended is enabled, select the recommended model
        if self.config.get("default_to_recommended_model", False) and provider != "Ollama (Local)":
            self._select_default_or_recommended_model()

    def save_api_key_in_settings(self):
        provider = self.provider_var.get()
        self.config["keys"][provider] = self.api_key_var.get().strip()
        save_config(self.config)

    def _save_ollama_url(self):
        """Save the Ollama server URL to config"""
        if hasattr(self, 'ollama_url_var'):
            new_url = self.ollama_url_var.get().strip()
            if new_url:
                self.config["ollama_base_url"] = new_url
                save_config(self.config)
    
    def _test_ollama_connection(self):
        """Test connection to Ollama server and display result"""
        try:
            from ai_handler import check_ollama_connection
            
            # Get URL from the entry field
            base_url = self.ollama_url_var.get().strip() if hasattr(self, 'ollama_url_var') else None
            if not base_url:
                base_url = self.config.get("ollama_base_url", "http://localhost:11434")
            
            # Save the URL first
            self._save_ollama_url()
            
            # Test connection
            connected, status, models = check_ollama_connection(base_url)
            
            if hasattr(self, 'ollama_status_var'):
                self.ollama_status_var.set(status)
            
            if connected and models:
                # Update models list
                self.models["Ollama (Local)"] = models
                
                # If Ollama is currently selected, refresh the model dropdown
                if self.provider_var.get() == "Ollama (Local)":
                    self.model_combo['values'] = models
                    if models:
                        self.model_var.set(models[0])
                
                messagebox.showinfo(
                    "Ollama Connection",
                    f"✅ Successfully connected to Ollama!\n\n"
                    f"Available models:\n" + "\n".join(f"  • {m}" for m in models[:5]) +
                    (f"\n  ... and {len(models)-5} more" if len(models) > 5 else "")
                )
            elif connected:
                messagebox.showwarning(
                    "Ollama Connection",
                    "✅ Connected to Ollama server, but no models are loaded.\n\n"
                    "Please load a model in Ollama first."
                )
            else:
                # Check if Ollama is installed
                ollama_installed = self._is_ollama_installed()
                
                if not ollama_installed:
                    # Not installed - offer to download
                    result = messagebox.askyesno(
                        "Ollama Not Found",
                        "Ollama does not appear to be installed on this computer.\n\n"
                        "Ollama is a free application that lets you run AI models \n"
                        "locally on your computer for complete privacy.\n\n"
                        "Would you like to open the download page?\n\n"
                        "(You can also click 'Local AI Guide' for step-by-step instructions)"
                    )
                    if result:
                        webbrowser.open('https://ollama.com')
                else:
                    # Installed but not running/connected
                    messagebox.showerror(
                        "Ollama Connection",
                        f"❌ Cannot connect to Ollama\n\n"
                        f"{status}\n\n"
                        f"Ollama appears to be installed but is not responding.\n\n"
                        f"Please ensure:\n"
                        f"1. Ollama is open\n"
                        f"2. A model is loaded (Home tab → select model → Load)\n"
                        f"3. Local Server is started (Developer tab → Start Server)"
                    )
        except Exception as e:
            if hasattr(self, 'ollama_status_var'):
                self.ollama_status_var.set(f"Error: {str(e)}")
            messagebox.showerror("Error", f"Failed to test connection:\n{str(e)}")
    
    def _download_ollama_model(self, model_tag, description, refresh_callback=None, parent=None):
        """Download an Ollama model with a progress dialog. Runs 'ollama pull' in background."""
        import subprocess
        import threading
        import shutil

        # Check ollama is available
        ollama_path = shutil.which("ollama")
        if not ollama_path and not self._is_ollama_installed():
            messagebox.showerror(
                "Ollama Not Found",
                "Ollama does not appear to be installed.\n\n"
                "Please install Ollama first (Step 1), then try again.",
                parent=parent
            )
            return

        # Progress dialog
        dlg = tk.Toplevel(parent or self.root)
        dlg.title(f"Downloading {model_tag}")
        dlg.geometry("480x280")
        self.apply_window_style(dlg)
        dlg.transient(parent or self.root)
        dlg.grab_set()

        ttk.Label(dlg, text=f"Downloading: {description}",
                  font=('Arial', 10, 'bold')).pack(pady=(10, 2))
        ttk.Label(dlg, text=f"ollama pull {model_tag}",
                  font=('Consolas', 9), foreground='gray').pack(pady=(0, 8))

        # Progress bar
        progress = ttk.Progressbar(dlg, mode='indeterminate', length=420)
        progress.pack(padx=20, pady=(0, 8))
        progress.start(10)

        # Output display
        output_text = tk.Text(dlg, height=6, font=('Consolas', 9), wrap=tk.WORD,
                              bg='#2b2b2b', fg='#cccccc', insertbackground='#cccccc')
        output_text.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 5))
        output_text.insert('1.0', "Starting download...\n")
        output_text.config(state=tk.DISABLED)

        # Button frame
        btn_frame = ttk.Frame(dlg)
        btn_frame.pack(fill=tk.X, padx=20, pady=(0, 8))

        process_ref = [None]
        cancelled = [False]

        def cancel_download():
            cancelled[0] = True
            if process_ref[0] and process_ref[0].poll() is None:
                try:
                    process_ref[0].terminate()
                except Exception:
                    pass
            dlg.destroy()

        cancel_btn = ttk.Button(btn_frame, text="Cancel", command=cancel_download, width=10)
        cancel_btn.pack(side=tk.RIGHT)

        def append_output(text):
            """Thread-safe append to output text widget."""
            try:
                output_text.config(state=tk.NORMAL)
                # Keep last ~20 lines to avoid flooding
                lines = output_text.get('1.0', tk.END).strip().split('\n')
                if len(lines) > 20:
                    output_text.delete('1.0', f'{len(lines)-19}.0')
                output_text.insert(tk.END, text)
                output_text.see(tk.END)
                output_text.config(state=tk.DISABLED)
            except tk.TclError:
                pass  # Widget destroyed

        def run_pull():
            import re as _re
            try:
                cmd = ["ollama", "pull", model_tag]
                process_ref[0] = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    bufsize=0,  # unbuffered binary
                    creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
                )

                # Read raw bytes and split on \r or \n so we catch
                # ollama's carriage-return progress updates in real time
                buf = b''
                last_pct = [0]
                switched_to_determinate = [False]

                while True:
                    if cancelled[0]:
                        break
                    chunk = process_ref[0].stdout.read(256)
                    if not chunk:
                        break
                    buf += chunk

                    # Split on \r or \n — each piece is a "line"
                    while b'\r' in buf or b'\n' in buf:
                        # Find the earliest delimiter
                        r_pos = buf.find(b'\r')
                        n_pos = buf.find(b'\n')
                        if r_pos == -1:
                            r_pos = len(buf)
                        if n_pos == -1:
                            n_pos = len(buf)
                        pos = min(r_pos, n_pos)

                        line_bytes = buf[:pos]
                        # Skip the delimiter (handle \r\n as one)
                        if pos < len(buf) - 1 and buf[pos:pos+2] == b'\r\n':
                            buf = buf[pos+2:]
                        else:
                            buf = buf[pos+1:]

                        line = line_bytes.decode('utf-8', errors='replace').strip()
                        if not line:
                            continue

                        # Try to extract percentage for determinate progress
                        pct_match = _re.search(r'(\d+)%', line)
                        if pct_match:
                            pct = int(pct_match.group(1))
                            last_pct[0] = pct
                            def _update_progress(p=pct, l=line):
                                try:
                                    if not switched_to_determinate[0]:
                                        progress.stop()
                                        progress.configure(mode='determinate', maximum=100)
                                        switched_to_determinate[0] = True
                                    progress['value'] = p
                                    # Replace last line instead of appending
                                    output_text.config(state=tk.NORMAL)
                                    output_text.delete('1.0', tk.END)
                                    output_text.insert('1.0', l)
                                    output_text.config(state=tk.DISABLED)
                                except tk.TclError:
                                    pass
                            dlg.after(0, _update_progress)
                        else:
                            # Non-progress line (e.g. "pulling manifest", "verifying")
                            dlg.after(0, lambda l=line: append_output(l + "\n"))

                # Flush any remaining buffer
                if buf:
                    remaining = buf.decode('utf-8', errors='replace').strip()
                    if remaining:
                        dlg.after(0, lambda l=remaining: append_output(l + "\n"))

                process_ref[0].stdout.close()
                return_code = process_ref[0].wait()

                if cancelled[0]:
                    return

                if return_code == 0:
                    dlg.after(0, lambda: _on_success())
                else:
                    dlg.after(0, lambda: _on_failure(return_code))

            except FileNotFoundError:
                if not cancelled[0]:
                    dlg.after(0, lambda: _on_error(
                        "Could not find 'ollama' command.\n\n"
                        "Make sure Ollama is installed and try restarting your computer."
                    ))
            except Exception as e:
                if not cancelled[0]:
                    dlg.after(0, lambda: _on_error(str(e)))

        def _on_success():
            try:
                progress.stop()
                progress.configure(mode='determinate', value=100)
                append_output("\n✅ Download complete!\n")
                cancel_btn.configure(text="Close", command=dlg.destroy)
                self.set_status(f"✅ Model {model_tag} downloaded successfully")
                messagebox.showinfo(
                    "Download Complete",
                    f"✅ {description} has been downloaded successfully!\n\n"
                    f"You can now select it in AI Settings\n"
                    f"(Provider → Ollama, then Refresh Models).",
                    parent=dlg
                )
                # Refresh the connection check in the setup wizard
                if refresh_callback:
                    try:
                        refresh_callback()
                    except Exception:
                        pass
            except tk.TclError:
                pass

        def _on_failure(code):
            try:
                progress.stop()
                append_output(f"\n❌ Download failed (exit code {code})\n")
                cancel_btn.configure(text="Close", command=dlg.destroy)
                messagebox.showerror(
                    "Download Failed",
                    f"The download of {model_tag} failed (exit code {code}).\n\n"
                    f"Please check that Ollama is running and try again.",
                    parent=dlg
                )
            except tk.TclError:
                pass

        def _on_error(msg):
            try:
                progress.stop()
                append_output(f"\n❌ Error: {msg}\n")
                cancel_btn.configure(text="Close", command=dlg.destroy)
            except tk.TclError:
                pass

        # Prevent closing mid-download without cancelling
        dlg.protocol("WM_DELETE_WINDOW", cancel_download)

        # Start download in background thread
        threading.Thread(target=run_pull, daemon=True).start()

    def _is_ollama_installed(self) -> bool:
        """Check if Ollama is installed on this system"""
        import os
        
        possible_paths = [
            os.path.expandvars(r"%PROGRAMFILES%\Ollama\Ollama.exe"),
            os.path.expandvars(r"%PROGRAMFILES(X86)%\Ollama\Ollama.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\Ollama.exe"),
            os.path.expanduser(r"~\AppData\Local\Programs\Ollama\Ollama.exe"),
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return True
        
        # Also check for desktop shortcut
        desktop_shortcut = os.path.expanduser(r"~\Desktop\Ollama.lnk")
        if os.path.exists(desktop_shortcut):
            return True
        
        return False

    def open_local_ai_setup(self):
        """Step-by-step Local AI setup wizard accessible from Settings menu.
        Hardware-aware: detects system capabilities and recommends appropriate models."""
        from ai_handler import check_ollama_connection
        import webbrowser

        settings = tk.Toplevel(self.root)
        settings.title("Local AI Setup")
        settings.geometry("580x600")
        self.apply_window_style(settings)
        settings.resizable(True, True)

        # Bottom buttons (pack FIRST)
        bottom_frame = ttk.Frame(settings)
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=5, padx=15)
        ttk.Button(bottom_frame, text="Close", command=settings.destroy).pack(side=tk.RIGHT, padx=5)

        # Scrollable content
        canvas = tk.Canvas(settings, highlightthickness=0)
        v_scroll = ttk.Scrollbar(settings, orient="vertical", command=canvas.yview)
        content = ttk.Frame(canvas)
        content.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        cw = canvas.create_window((0, 0), window=content, anchor="nw")
        canvas.configure(yscrollcommand=v_scroll.set)
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(cw, width=e.width))
        def _mw(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _mw)
        settings.bind("<Destroy>", lambda e: canvas.unbind_all("<MouseWheel>") if e.widget == settings else None)

        # Title
        ttk.Label(content, text="Local AI Setup", font=('Arial', 12, 'bold')).pack(pady=(8, 2))
        ttk.Label(content, text="Run AI on your own computer — free and completely private",
                  font=('Arial', 9), foreground='gray').pack(pady=(0, 8))

        # ── Step 1: Install Ollama ──
        step1 = ttk.LabelFrame(content, text="Step 1: Install Ollama", padding=8)
        step1.pack(fill=tk.X, padx=15, pady=3)

        ollama_installed = self._is_ollama_installed()
        step1_var = tk.StringVar()
        step1_lbl = ttk.Label(step1, textvariable=step1_var, font=('Arial', 9))
        step1_lbl.pack(anchor=tk.W)

        if ollama_installed:
            step1_var.set("✅ Ollama is installed")
            step1_lbl.configure(foreground='green')
        else:
            step1_var.set("❌ Ollama not detected — download free from ollama.com")
            step1_lbl.configure(foreground='#CC0000')

        s1_row = ttk.Frame(step1)
        s1_row.pack(fill=tk.X, pady=(4, 0))
        ttk.Button(s1_row, text="Download Ollama",
                   command=lambda: webbrowser.open("https://ollama.com/download"),
                   width=16).pack(side=tk.LEFT, padx=2)
        ttk.Label(s1_row, text="One-click install, runs silently in background",
                  font=('Arial', 8), foreground='gray').pack(side=tk.LEFT, padx=5)

        # ── Step 2: Check Connection ──
        step2 = ttk.LabelFrame(content, text="Step 2: Check Connection", padding=8)
        step2.pack(fill=tk.X, padx=15, pady=3)

        step2_var = tk.StringVar()
        step2_lbl = ttk.Label(step2, textvariable=step2_var, font=('Arial', 9))
        step2_lbl.pack(anchor=tk.W)

        base_url = self.config.get("ollama_base_url", "http://localhost:11434")
        conn_state = {'connected': False, 'models': []}
        try:
            c, s, m = check_ollama_connection(base_url)
            conn_state['connected'] = c
            conn_state['models'] = m or []
        except Exception:
            pass

        def _update_step2():
            if conn_state['connected'] and conn_state['models']:
                step2_var.set(f"✅ Connected — {len(conn_state['models'])} model(s) available")
                step2_lbl.configure(foreground='green')
            elif conn_state['connected']:
                step2_var.set("⚠️ Connected but no models downloaded yet (see Step 3)")
                step2_lbl.configure(foreground='#CC6600')
            else:
                step2_var.set("❌ Not connected — is Ollama running? (check system tray)")
                step2_lbl.configure(foreground='#CC0000')

        _update_step2()

        s2_row = ttk.Frame(step2)
        s2_row.pack(fill=tk.X, pady=(4, 0))

        def recheck():
            try:
                c, s, m = check_ollama_connection(base_url)
                conn_state['connected'] = c
                conn_state['models'] = m or []
            except Exception:
                conn_state['connected'] = False
                conn_state['models'] = []
            _update_step2()
            # Also refresh Step 1
            if self._is_ollama_installed():
                step1_var.set("✅ Ollama is installed")
                step1_lbl.configure(foreground='green')

        ttk.Button(s2_row, text="Test Connection", command=recheck, width=16).pack(side=tk.LEFT, padx=2)
        ttk.Label(s2_row, text="Ollama starts automatically after install",
                  font=('Arial', 8), foreground='gray').pack(side=tk.LEFT, padx=5)

        # ── Step 3: Your System & Recommended Models ──
        step3 = ttk.LabelFrame(content, text="Step 3: Download a Model", padding=8)
        step3.pack(fill=tk.X, padx=15, pady=3)

        # Detect system capabilities
        sys_info = None
        recommendations = None
        try:
            from system_detector import get_system_info, get_model_recommendations
            sys_info = get_system_info()
            recommendations = get_model_recommendations(sys_info)
        except Exception:
            pass

        if sys_info:
            # System summary line
            ram_str = f"{sys_info.get('ram_total_gb', '?')} GB RAM"
            gpu_str = sys_info.get('gpu_name', 'No GPU detected') if sys_info.get('gpu_detected') else "No dedicated GPU"
            vram_str = f" ({sys_info.get('gpu_vram_gb', '?')} GB VRAM)" if sys_info.get('gpu_vram_gb') else ""
            profile_name = recommendations.get('profile_name', 'Unknown') if recommendations else 'Unknown'

            sys_frame = tk.Frame(step3, bg='#E8F5E9', padx=8, pady=6)
            sys_frame.pack(fill=tk.X, pady=(0, 6))
            tk.Label(sys_frame, text=f"Your system: {ram_str} · {gpu_str}{vram_str}",
                     font=('Arial', 9), bg='#E8F5E9', fg='#333').pack(anchor=tk.W)
            tk.Label(sys_frame, text=f"Hardware profile: {profile_name} — {recommendations.get('profile_description', '')}",
                     font=('Arial', 8), bg='#E8F5E9', fg='#555').pack(anchor=tk.W)

        if recommendations:
            ttk.Label(step3, text="Recommended models for your machine:",
                      font=('Arial', 9, 'bold')).pack(anchor=tk.W, pady=(4, 2))

            # Show primary recommendations
            for model in recommendations.get('primary_models', [])[:3]:
                m_frame = ttk.Frame(step3)
                m_frame.pack(fill=tk.X, pady=2)

                # Model info
                desc = model.get('description', '')
                size = model.get('size_gb', '?')
                name = model.get('name', '?')

                ttk.Label(m_frame, text=f"• {name} ({size} GB)",
                          font=('Arial', 9, 'bold')).pack(anchor=tk.W)
                ttk.Label(m_frame, text=f"  {desc}",
                          font=('Arial', 8), foreground='gray').pack(anchor=tk.W)

            # Warning for basic profile
            if recommendations.get('warning'):
                warn_frame = tk.Frame(step3, bg='#FFF3E0', padx=6, pady=4)
                warn_frame.pack(fill=tk.X, pady=(4, 0))
                tk.Label(warn_frame, text=recommendations['warning'],
                         font=('Arial', 8), bg='#FFF3E0', fg='#E65100',
                         wraplength=500, justify=tk.LEFT).pack(anchor=tk.W)
        else:
            ttk.Label(step3, text="Could not detect system capabilities. Recommended starting model: Llama 3.2 3B (2 GB).",
                      font=('Arial', 9)).pack(anchor=tk.W)

        # ── Step 4: Download Models ──
        step4 = ttk.LabelFrame(content, text="Step 4: Download a Model", padding=8)
        step4.pack(fill=tk.X, padx=15, pady=3)

        ttk.Label(step4, text="Click Download to install a model. This may take a few minutes.",
                  font=('Arial', 8), foreground='gray').pack(anchor=tk.W, pady=(0, 4))

        # Build download commands from recommendations or defaults
        download_models = []
        if recommendations:
            for m in recommendations.get('primary_models', []):
                name = m.get('name', '')
                size = m.get('size_gb', '?')
                term = m.get('search_term', '').lower()
                ollama_names = {
                    'phi-3-mini': 'phi3:mini',
                    'gemma-2b': 'gemma:2b',
                    'tinyllama': 'tinyllama',
                    'mistral-7b-instruct': 'mistral:7b',
                    'llama-3.2-8b': 'llama3.1:8b',
                    'llama-3.2-3b': 'llama3.2:3b',
                    'llama-3.1-8b': 'llama3.1:8b',
                    'mistral-nemo': 'mistral-nemo',
                    'codellama-13b': 'codellama:13b',
                    'qwen2-7b': 'qwen2:7b',
                    'llama-3.1-70b-q4': 'llama3.1:70b',
                    'mixtral-8x7b': 'mixtral:8x7b',
                    'qwen2-72b-q4': 'qwen2:72b',
                    'deepseek-coder-33b': 'deepseek-coder:33b',
                }
                pull_name = ollama_names.get(term, term.replace('-instruct', ':instruct').replace('-', ':'))
                download_models.append((pull_name, f"{name} ({size} GB)"))

        if not download_models:
            download_models = [
                ("llama3.2:3b", "Llama 3.2 3B (2 GB) — good starter"),
                ("llama3.1:8b", "Llama 3.1 8B (4.7 GB) — excellent quality"),
            ]

        for model_tag, desc in download_models[:3]:
            cmd_row = ttk.Frame(step4)
            cmd_row.pack(fill=tk.X, pady=2)

            def make_download(tag=model_tag, description=desc):
                self._download_ollama_model(tag, description, recheck, settings)

            ttk.Button(cmd_row, text="Download", command=make_download, width=10).pack(side=tk.LEFT, padx=(0, 4))
            ttk.Label(cmd_row, text=desc, font=('Arial', 9)).pack(side=tk.LEFT, padx=4)

        # ── Step 5: Select in DocAnalyser ──
        step5 = ttk.LabelFrame(content, text="Step 5: Use in DocAnalyser", padding=8)
        step5.pack(fill=tk.X, padx=15, pady=3)

        ttk.Label(step5, text=(
            "Once a model is downloaded:\n"
            "1. Open AI Settings (Settings ▾ menu)\n"
            "2. Set AI Provider to \"Ollama (Local)\"\n"
            "3. Click \"Refresh Models\" — your downloaded model will appear\n"
            "4. Select your model and start analysing!"
        ), font=('Arial', 9), justify=tk.LEFT).pack(anchor=tk.W)

        # ── About section ──
        about = ttk.LabelFrame(content, text="About Local AI", padding=5)
        about.pack(fill=tk.X, padx=15, pady=3)
        ttk.Label(about, text=(
            "Local AI keeps your documents completely private — nothing is sent to the cloud. "
            "It's free after setup and works offline. Trade-off: local models are slower than "
            "cloud services and may produce less detailed results for complex tasks. "
            "For a detailed guide, use the Local AI Guide button in AI Settings."
        ), font=('Arial', 8), foreground='gray', wraplength=520, justify=tk.LEFT).pack(anchor=tk.W)

        # Also add buttons to bottom frame
        def open_full_guide():
            self._open_local_ai_guide()

        ttk.Button(bottom_frame, text="Full Guide", command=open_full_guide).pack(side=tk.LEFT, padx=5)
        ttk.Button(bottom_frame, text="System Check",
                   command=self._show_system_recommendations).pack(side=tk.LEFT, padx=5)
        ttk.Button(bottom_frame, text="Manage Models",
                   command=self._open_local_model_manager).pack(side=tk.LEFT, padx=5)

    def _show_system_recommendations(self):
        """Show system analysis and model recommendations for local AI"""
        try:
            from system_detector import get_system_info, get_model_recommendations, format_system_report
            
            # Show loading message
            self.set_status("Analyzing system capabilities...")
            self.root.update()
            
            # Get system info and recommendations
            system_info = get_system_info()
            recommendations = get_model_recommendations(system_info)
            report = format_system_report(system_info)
            
            # Create window
            rec_window = tk.Toplevel(self.root)
            rec_window.title("System Analysis - Local AI Model Recommendations")
            rec_window.geometry("650x600")
            rec_window.transient(self.root)
            self.style_dialog(rec_window)
            
            # Header
            header_frame = ttk.Frame(rec_window, padding=10)
            header_frame.pack(fill=tk.X)
            
            profile = recommendations['profile_name']
            profile_colors = {
                "Basic": "#e74c3c",
                "Standard": "#f39c12", 
                "Good": "#27ae60",
                "Powerful": "#2980b9"
            }
            
            ttk.Label(
                header_frame,
                text=f"Your System Profile: {profile.upper()}",
                font=('Arial', 14, 'bold')
            ).pack()
            
            ttk.Label(
                header_frame,
                text=recommendations['profile_description'],
                font=('Arial', 10)
            ).pack(pady=5)
            
            # Main content - scrollable text
            text_frame = ttk.Frame(rec_window, padding=10)
            text_frame.pack(fill=tk.BOTH, expand=True)
            
            text_widget = tk.Text(text_frame, wrap=tk.WORD, font=('Consolas', 9))
            scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=text_widget.yview)
            text_widget.configure(yscrollcommand=scrollbar.set)
            
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            
            text_widget.insert('1.0', report)
            text_widget.config(state=tk.DISABLED)
            
            # Recommended models - simple and clear
            models_frame = ttk.LabelFrame(rec_window, text="Download These Models in Ollama", padding=10)
            models_frame.pack(fill=tk.X, padx=10, pady=5)
            
            ttk.Label(
                models_frame,
                text="Click a button below to copy the search term, then paste it into Ollama's search bar:",
                font=('Arial', 9),
                wraplength=600
            ).pack(anchor=tk.W, pady=(0, 10))
            
            for model in recommendations['primary_models'][:2]:
                model_row = ttk.Frame(models_frame)
                model_row.pack(fill=tk.X, pady=4)
                
                # Create the copy function with proper closure
                def make_copy_func(term, name):
                    def copy_search():
                        self.root.clipboard_clear()
                        self.root.clipboard_append(term)
                        self.set_status(f"✅ Copied '{term}' - now paste into Ollama's Discover search bar")
                    return copy_search
                
                ttk.Button(
                    model_row,
                    text=f"📋 Copy: {model['search_term']}",
                    command=make_copy_func(model['search_term'], model['name']),
                    width=30
                ).pack(side=tk.LEFT, padx=(0, 10))
                
                ttk.Label(
                    model_row,
                    text=f"{model['name']} ({model['size_gb']} GB)",
                    font=('Arial', 9)
                ).pack(side=tk.LEFT)
            
            # Bottom buttons
            btn_frame = ttk.Frame(rec_window, padding=10)
            btn_frame.pack(fill=tk.X)
            
            ttk.Button(
                btn_frame,
                text="Close",
                command=rec_window.destroy
            ).pack(side=tk.RIGHT, padx=5)
            
            def copy_full_report():
                self.root.clipboard_clear()
                self.root.clipboard_append(report)
                self.set_status("📋 Full report copied to clipboard")
            
            ttk.Button(
                btn_frame,
                text="📋 Copy Full Report",
                command=copy_full_report
            ).pack(side=tk.RIGHT, padx=5)
            
            self.set_status(f"System profile: {profile} - see recommendations above")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to analyze system:\n{str(e)}")
            import traceback
            traceback.print_exc()

    def _open_local_ai_guide(self):
        """
        Open the Local AI Guide in a styled window matching the DocAnalyser Help panel.
        """
        # Get the guide file path (in same directory as Main.py)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        guide_path = os.path.join(script_dir, "LOCAL_AI_GUIDE.md")
        
        if not os.path.exists(guide_path):
            messagebox.showerror(
                "Guide Not Found",
                f"Could not find LOCAL_AI_GUIDE.md in:\n{script_dir}\n\n"
                "Please ensure the guide file is in the same folder as the application."
            )
            return
        
        self._show_guide_in_window(guide_path)
    
    def _show_guide_in_window(self, guide_path):
        """Display the guide in a styled window matching the DocAnalyser Help panel"""
        try:
            with open(guide_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            messagebox.showerror("Error", f"Could not read guide file:\n{str(e)}")
            return
        
        # Create window
        guide_window = tk.Toplevel(self.root)
        guide_window.title("📖 Local AI Guide - Running AI on Your Computer")
        guide_window.geometry("800x700")
        guide_window.transient(self.root)
        self.style_dialog(guide_window)
        
        # Center the window on screen
        guide_window.update_idletasks()
        screen_width = guide_window.winfo_screenwidth()
        screen_height = guide_window.winfo_screenheight()
        x = 50  # Left side of screen with small margin
        y = (screen_height - 700) // 2
        guide_window.geometry(f"800x700+{x}+{y}")
        
        # Make it modal
        guide_window.grab_set()
        
        # Header - matching DocAnalyser app styling
        header_frame = tk.Frame(guide_window, bg='#dcdad5', height=80)
        header_frame.pack(fill=tk.X)
        header_frame.pack_propagate(False)
        
        tk.Label(
            header_frame,
            text="📖 Local AI Guide",
            font=('Arial', 14, 'bold'),
            bg='#dcdad5',
            fg='#333333'
        ).pack(pady=(15, 2))
        
        tk.Label(
            header_frame,
            text="Running AI Locally with Ollama - A Beginner's Guide",
            font=('Arial', 10),
            bg='#dcdad5',
            fg='#555555'
        ).pack(pady=(0, 10))
        
        # Content - matching DocAnalyser app styling
        content_frame = tk.Frame(guide_window, bg='#dcdad5', padx=10, pady=10)
        content_frame.pack(fill=tk.BOTH, expand=True)
        
        # Text area with scrollbar - soft yellow background like rest of app
        text_widget = scrolledtext.ScrolledText(
            content_frame,
            wrap=tk.WORD,
            font=('Arial', 10),
            bg='#FFFDE6',
            fg='#333333',
            padx=15,
            pady=15
        )
        text_widget.pack(fill=tk.BOTH, expand=True)
        text_widget.insert('1.0', content)
        
        # Make URLs clickable
        def make_urls_clickable():
            """Find URLs in text and make them clickable"""
            import re
            # Pattern to match URLs (excluding markdown formatting characters)
            url_pattern = r'https?://[^\s\)\]\*]+'
            
            # Find all URLs and apply tag
            content_text = text_widget.get('1.0', tk.END)
            for match in re.finditer(url_pattern, content_text):
                url = match.group()
                
                # Skip localhost URLs - not useful to click
                if 'localhost' in url or '127.0.0.1' in url:
                    continue
                
                start_idx = f"1.0+{match.start()}c"
                end_idx = f"1.0+{match.end()}c"
                tag_name = f"link_{match.start()}"
                text_widget.tag_configure(tag_name, foreground='#0066CC', underline=True)
                text_widget.tag_add(tag_name, start_idx, end_idx)
                text_widget.tag_bind(tag_name, '<Enter>', lambda e: text_widget.config(cursor='hand2'))
                text_widget.tag_bind(tag_name, '<Leave>', lambda e: text_widget.config(cursor=''))
                text_widget.tag_bind(tag_name, '<Button-1>', lambda e, u=url: webbrowser.open(u))
        
        make_urls_clickable()
        text_widget.config(state=tk.DISABLED)
        
        # Bottom buttons - matching app styling
        btn_frame = tk.Frame(guide_window, bg='#dcdad5', padx=10, pady=10)
        btn_frame.pack(fill=tk.X)
        
        def copy_guide():
            self.root.clipboard_clear()
            self.root.clipboard_append(content)
            self.set_status("📝 Guide copied to clipboard")
        
        ttk.Button(
            btn_frame,
            text="📋 Copy to Clipboard",
            command=copy_guide,
            width=18
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            btn_frame,
            text="Close",
            command=guide_window.destroy,
            width=15
        ).pack(side=tk.RIGHT, padx=5)
        
        # Bind Escape to close
        guide_window.bind('<Escape>', lambda e: guide_window.destroy())
        
        self.set_status("📖 Local AI Guide opened")

    def save_model_selection(self):
        """Save the selected model for the current provider"""
        provider = self.provider_var.get()
        model = self.model_var.get()
        if provider and model:
            self.config["last_model"][provider] = model
            save_config(self.config)

    def open_prompt_manager(self):
        """Open the Prompt Library manager window (NEW tree-view version)"""
        try:
            from prompt_tree_manager import open_prompt_tree_manager
            # Create new tree-view prompts library window
            open_prompt_tree_manager(
                parent=self.root,
                prompts=self.prompts,
                prompts_path=PROMPTS_PATH,
                save_func=save_json_atomic,
                refresh_callback=self.refresh_main_prompt_combo,
                config=self.config,
                save_config_func=lambda: save_config(self.config),
                use_prompt_callback = self.set_prompt_from_library
            )
        except ImportError as e:
            print(f"⚠️ Could not load new Prompts Library (prompt_tree_manager.py): {e}")
            print("   Falling back to old prompts library...")
            # Fallback to old prompts library if new one not available
            from prompt_manager import open_prompt_manager_window
            open_prompt_manager_window(
                parent=self.root,
                prompts=self.prompts,
                prompts_path=PROMPTS_PATH,
                save_func=save_json_atomic,
                refresh_callback=self.refresh_main_prompt_combo,
                config=self.config,
                save_config_func=lambda: save_config(self.config),
                use_prompt_callback=self.set_prompt_from_library
            )

    def save_prompt(self):
        """Legacy method - now handled by prompt_manager module"""
        # This method is kept for compatibility but the actual logic
        # is now in prompt_manager.py
        pass

    def refresh_main_prompt_combo(self):
        """Refresh the prompt dropdown with hierarchical structure"""
        current_selection = self.prompt_combo.get()

        # CRITICAL: Reload prompts from disk to get latest folder/favorite info
        self.prompts = load_prompts()

        # === ADD THIS DEBUG BLOCK ===
        print("\n" + "=" * 60)
        print("DEBUG: refresh_main_prompt_combo()")
        print(f"Prompts type: {type(self.prompts)}")
        print(f"Prompts length: {len(self.prompts) if isinstance(self.prompts, list) else 'N/A'}")
        if isinstance(self.prompts, list) and len(self.prompts) > 0:
            print(f"First prompt keys: {list(self.prompts[0].keys())}")
            print(f"Has 'folder'? {'folder' in self.prompts[0]}")
            print(f"Has 'is_favorite'? {'is_favorite' in self.prompts[0]}")
            if 'folder' in self.prompts[0]:
                print(f"First prompt folder: {self.prompts[0]['folder']}")
            if 'is_favorite' in self.prompts[0]:
                print(f"First prompt is_favorite: {self.prompts[0]['is_favorite']}")
        print("=" * 60 + "\n")
        # === END DEBUG BLOCK ===

        # Build hierarchical dropdown using the new module
        dropdown_list, name_to_prompt = build_dropdown_auto(self.prompts)

        # Store the mapping for later use
        self.prompt_name_map = name_to_prompt

        # Set dropdown values
        self.prompt_combo['values'] = dropdown_list

        # Try to restore previous selection
        clean_name = extract_prompt_name(current_selection)

        # Find matching entry in dropdown
        found = False
        for i, entry in enumerate(dropdown_list):
            if extract_prompt_name(entry) == clean_name:
                self.prompt_combo.current(i)
                found = True
                break

        # If not found, try default or first selectable prompt
        if not found and dropdown_list:
            default_prompt_name = self.config.get('default_prompt', '')
            default_idx = 0

            # Find first selectable (non-header, non-separator) entry
            for i, entry in enumerate(dropdown_list):
                if not is_header(entry) and not is_separator(entry):
                    default_idx = i
                    # Check if it matches default
                    if default_prompt_name and extract_prompt_name(entry) == default_prompt_name:
                        break

            self.prompt_combo.current(default_idx)
            self.on_prompt_select()

    def set_prompt_from_library(self, prompt_name, prompt_text):
        """
        Callback for Prompts Library 'Use Prompt' button.
        Sets the prompt text in the main window.
        """
        # Clear the text area
        self.prompt_text.delete('1.0', tk.END)

        # Insert the new prompt text
        self.prompt_text.insert('1.0', prompt_text)

        # Auto-expand to fit the new prompt content
        self.root.after(10, self._auto_expand_prompt_text)

        # Update the dropdown to match
        try:
            for i, prompt_dict in enumerate(self.prompts):
                if prompt_dict['name'] == prompt_name:
                    self.prompt_combo.current(i)
                    break
        except Exception as e:
            print(f"Note: Could not update dropdown: {e}")

    def open_chunk_settings(self):
        settings = tk.Toplevel(self.root)
        settings.title("Chunk Size Settings")
        settings.geometry("500x560")
        self.style_dialog(settings)

        bottom_frame = ttk.Frame(settings)
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=10, padx=20)

        ttk.Label(settings, text="📄 Chunk Settings", font=('Arial', 12, 'bold')).pack(pady=10)

        content = ttk.Frame(settings)
        content.pack(fill=tk.BOTH, expand=True, padx=20)

        current = self.config.get("chunk_size", "medium")
        selected = tk.StringVar(value=current)
        for key, info in CHUNK_SIZES.items():
            frame = ttk.LabelFrame(content, text=info["label"], padding=10)
            frame.pack(fill=tk.X, pady=5)
            rb = ttk.Radiobutton(frame, text=f"{info['description']}\nQuality: {info['quality']}", variable=selected,
                                 value=key)
            rb.pack(anchor=tk.W)

        # About
        about_frame = ttk.LabelFrame(content, text="\u2139\ufe0f About Chunk Settings", padding=5)
        about_frame.pack(fill=tk.X, pady=5)
        about_text = (
            "Chunking splits large documents into sections for AI processing. "
            "Smaller chunks give more detailed analysis but take more API calls. "
            "Larger chunks are faster and cheaper but may miss detail. "
            "'Medium' is recommended for most use cases."
        )
        ttk.Label(about_frame, text=about_text, font=('Arial', 8), foreground='gray',
                  wraplength=430).pack(anchor=tk.W)

        chunk_initial = {'chunk_size': current}
        saved_flag = [False]

        def get_chunk_current():
            return {'chunk_size': selected.get()}

        def save():
            saved_flag[0] = True
            self._save_and_close_settings({"chunk_size": selected.get()}, settings, "Chunk settings saved")

        def on_close():
            self._close_with_save_check(settings, get_chunk_current, chunk_initial, save, saved_flag)

        ttk.Button(bottom_frame, text="Save Settings", command=save).pack(side=tk.LEFT, padx=5)
        ttk.Button(bottom_frame, text="Close", command=on_close).pack(side=tk.RIGHT, padx=5)
        settings.protocol("WM_DELETE_WINDOW", on_close)

    def open_ocr_settings(self):
        available, error_msg, tesseract_path = get_ocr().check_ocr_availability()

        settings = tk.Toplevel(self.root)
        settings.title("OCR Settings")
        settings.geometry("550x580")
        settings.resizable(True, True)
        self.style_dialog(settings)
        
        if not available:
            if error_msg == "TESSERACT_NOT_FOUND":
                self.show_tesseract_setup_wizard(settings)
            else:
                error_frame = ttk.Frame(settings, padding=20)
                error_frame.pack(fill=tk.BOTH, expand=True)
                ttk.Label(error_frame, text="⚠️ OCR Libraries Not Installed", font=('Arial', 14, 'bold'),
                          foreground='red').pack(pady=10)
                error_text = scrolledtext.ScrolledText(error_frame, wrap=tk.WORD, height=15, font=('Arial', 10))
                error_text.pack(fill=tk.BOTH, expand=True, pady=10)
                error_text.insert('1.0', error_msg)
                error_text.config(state=tk.DISABLED)
                ttk.Label(error_frame, text="Install Python packages first:", font=('Arial', 10, 'bold')).pack(
                    pady=(10, 5))
                install_cmd = "pip install pytesseract pdf2image Pillow"
                cmd_frame = ttk.Frame(error_frame)
                cmd_frame.pack(fill=tk.X, pady=5)
                cmd_entry = ttk.Entry(cmd_frame, font=('Courier', 10))
                cmd_entry.insert(0, install_cmd)
                cmd_entry.config(state='readonly')
                cmd_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

                def copy_command():
                    self.root.clipboard_clear()
                    self.root.clipboard_append(install_cmd)
                    messagebox.showinfo("Copied", "Command copied to clipboard!")

                ttk.Button(cmd_frame, text="Copy", command=copy_command, width=8).pack(side=tk.LEFT)
                ttk.Button(error_frame, text="Close", command=settings.destroy).pack(pady=10)
            return
        
        # Title
        ttk.Label(settings, text="📄 OCR Settings", font=('Arial', 12, 'bold')).pack(pady=(5, 0))
        if tesseract_path:
            ttk.Label(settings, text=f"✓ Tesseract: {tesseract_path}", font=('Arial', 8),
                      foreground='green').pack()
        
        # === Bottom buttons (pack FIRST so they're always visible) ===
        btn_frame = ttk.Frame(settings, padding=5)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)
        
        # Create scrollable content area
        canvas_frame = ttk.Frame(settings)
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        canvas = tk.Canvas(canvas_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        content_frame = ttk.Frame(canvas)
        
        content_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=content_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Mousewheel scrolling
        def on_mousewheel(event):
            try:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except tk.TclError:
                pass
        canvas.bind("<MouseWheel>", on_mousewheel)
        content_frame.bind("<MouseWheel>", on_mousewheel)
        
        # Bind canvas width to content frame
        def configure_content_width(event):
            canvas.itemconfig(canvas.find_all()[0], width=event.width)
        canvas.bind("<Configure>", configure_content_width)
        
        # === OCR Processing Mode ===
        mode_frame = ttk.LabelFrame(content_frame, text="OCR Processing Mode", padding=5)
        mode_frame.pack(fill=tk.X, padx=10, pady=3)
        
        current_mode = self.config.get("ocr_mode", "local_first")
        mode_var = tk.StringVar(value=current_mode)
        from config import OCR_MODES
        
        for key, info in OCR_MODES.items():
            rb = ttk.Radiobutton(mode_frame, text=info['label'], variable=mode_var, value=key)
            rb.pack(anchor=tk.W)
            ttk.Label(mode_frame, text=f"    {info['description']}", font=('Arial', 8), foreground='gray').pack(anchor=tk.W)
        
        ttk.Label(mode_frame, text="💡 Cloud AI: OpenAI GPT-4o, Claude 3.x, Gemini, Grok Vision",
                  font=('Arial', 8), foreground='blue').pack(anchor=tk.W, pady=(3, 0))
        
        # Confidence threshold slider
        threshold_frame = ttk.Frame(mode_frame)
        threshold_frame.pack(fill=tk.X, pady=(5, 0))
        ttk.Label(threshold_frame, text="Confidence threshold:", font=('Arial', 9)).pack(side=tk.LEFT)
        
        current_threshold = self.config.get("ocr_confidence_threshold", 60)
        threshold_var = tk.IntVar(value=current_threshold)
        threshold_label = ttk.Label(threshold_frame, text=f"{current_threshold}%", font=('Arial', 9, 'bold'), width=4)
        threshold_label.pack(side=tk.RIGHT)
        
        def on_threshold_change(val):
            v = int(float(val))
            threshold_var.set(v)
            threshold_label.config(text=f"{v}%")
        
        threshold_slider = ttk.Scale(threshold_frame, from_=10, to=90, orient=tk.HORIZONTAL,
                                      variable=threshold_var, command=on_threshold_change)
        threshold_slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        ttk.Label(mode_frame, text="    In 'Local first' mode: if Tesseract's confidence score falls below this %,\n"
                  "    you'll be offered the option to retry with Cloud AI for better results.",
                  font=('Arial', 8), foreground='gray').pack(anchor=tk.W)
        
        # === Text Type (Printed vs Handwriting) ===
        text_type_frame = ttk.LabelFrame(content_frame, text="📝 Text Type", padding=5)
        text_type_frame.pack(fill=tk.X, padx=10, pady=3)
        
        from ocr_handler import OCR_TEXT_TYPES
        current_text_type = self.config.get("ocr_text_type", "printed")
        text_type_var = tk.StringVar(value=current_text_type)
        
        for key, info in OCR_TEXT_TYPES.items():
            rb = ttk.Radiobutton(text_type_frame, text=info['label'], variable=text_type_var, value=key)
            rb.pack(anchor=tk.W)
            ttk.Label(text_type_frame, text=f"    {info['description']}", font=('Arial', 8), foreground='gray').pack(anchor=tk.W)
        
        # Show info about each mode
        ttk.Label(text_type_frame, text="💡 Printed: Free local OCR. Handwriting: Requires AI provider API key.",
                  font=('Arial', 8), foreground='blue').pack(anchor=tk.W, pady=(3, 0))
        
        # === OCR Language ===
        lang_frame = ttk.LabelFrame(content_frame, text="OCR Language", padding=5)
        lang_frame.pack(fill=tk.X, padx=10, pady=3)
        
        current_lang = self.config.get("ocr_language", "eng")
        lang_var = tk.StringVar(value=current_lang)
        lang_combo = ttk.Combobox(lang_frame, textvariable=lang_var, state="readonly", width=30)
        lang_combo['values'] = [f"{code} - {name}" for code, name in OCR_LANGUAGES.items()]
        for idx, (code, name) in enumerate(OCR_LANGUAGES.items()):
            if code == current_lang:
                lang_combo.current(idx)
                break
        lang_combo.pack(fill=tk.X, pady=2)
        
        # === OCR Quality ===
        quality_frame = ttk.LabelFrame(content_frame, text="OCR Quality", padding=5)
        quality_frame.pack(fill=tk.X, padx=10, pady=3)
        
        current_quality = self.config.get("ocr_quality", "balanced")
        quality_var = tk.StringVar(value=current_quality)
        for key, info in OCR_PRESETS.items():
            rb = ttk.Radiobutton(quality_frame, text=f"{info['label']} - {info['description']}",
                                 variable=quality_var, value=key)
            rb.pack(anchor=tk.W)
        
        # === About OCR (compact) ===
        info_frame = ttk.LabelFrame(content_frame, text="ℹ️ About OCR", padding=5)
        info_frame.pack(fill=tk.X, padx=10, pady=3)
        
        info_text = ("OCR extracts text from scanned PDFs and images. Features: auto-detect scanned vs text PDFs, "
                     "image preprocessing, 100+ languages, caching, resume capability. "
                     "Tip: Use 'Accurate' for poor quality scans.")
        ttk.Label(info_frame, text=info_text, font=('Arial', 8), foreground='gray', wraplength=480).pack(anchor=tk.W)
        
        # Track initial values for unsaved-changes detection
        ocr_initial = {
            'mode': current_mode,
            'threshold': current_threshold,
            'text_type': current_text_type,
            'lang': current_lang,
            'quality': current_quality,
        }
        saved_flag = [False]

        def get_ocr_current():
            lang_sel = lang_var.get()
            lc = lang_sel.split(' - ')[0] if ' - ' in lang_sel else current_lang
            return {
                'mode': mode_var.get(),
                'threshold': threshold_var.get(),
                'text_type': text_type_var.get(),
                'lang': lc,
                'quality': quality_var.get(),
            }

        # === Bottom buttons (fixed, not scrollable) ===
        def save_settings():
            saved_flag[0] = True
            lang_selection = lang_var.get()
            lang_code = lang_selection.split(' - ')[0] if ' - ' in lang_selection else current_lang
            self.config["ocr_language"] = lang_code
            self.config["ocr_quality"] = quality_var.get()
            self.config["ocr_mode"] = mode_var.get()
            self.config["ocr_confidence_threshold"] = threshold_var.get()
            self.config["ocr_text_type"] = text_type_var.get()  # Save text type (printed/handwriting)
            save_config(self.config)
            messagebox.showinfo("Success", "OCR settings saved")
            settings.destroy()
        
        def cleanup_and_close():
            try:
                canvas.unbind("<MouseWheel>")
                content_frame.unbind("<MouseWheel>")
            except:
                pass
            settings.destroy()

        def on_close():
            if saved_flag[0]:
                cleanup_and_close()
                return
            try:
                current = get_ocr_current()
                if current != ocr_initial:
                    result = messagebox.askyesno(
                        "Unsaved Changes",
                        "You have unsaved changes. Save before closing?",
                        parent=settings
                    )
                    if result:
                        save_settings()
                        return
            except Exception:
                pass
            cleanup_and_close()

        # Add buttons to pre-packed bottom frame
        ttk.Button(btn_frame, text="Save Settings", command=save_settings).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Test local OCR", command=self.test_ocr_setup).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Close", command=on_close).pack(side=tk.RIGHT, padx=5)
        settings.protocol("WM_DELETE_WINDOW", on_close)

    def open_audio_settings(self):
        settings = tk.Toplevel(self.root)
        settings.title("Audio & Transcription Settings")
        settings.geometry("650x550")  # Reduced from 600x700
        self.style_dialog(settings)

        # Make window resizable so users can adjust if needed
        settings.resizable(True, True)

        ttk.Label(settings, text="🎤 Audio & Transcription Settings", font=('Arial', 14, 'bold')).pack(
            pady=5)  # Reduced padding

        # Create a canvas with scrollbar for the content
        canvas_frame = ttk.Frame(settings)
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        canvas = tk.Canvas(canvas_frame)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Bind canvas width to content frame (prevents white space on right)
        def configure_content_width(event):
            canvas.itemconfig(canvas.find_all()[0], width=event.width)
        canvas.bind("<Configure>", configure_content_width)

        # Enable mousewheel scrolling with proper cleanup
        def on_mousewheel(event):
            # Check if canvas still exists before scrolling
            try:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except tk.TclError:
                pass  # Canvas was destroyed, ignore

        # Bind to canvas and scrollable_frame for complete coverage
        canvas.bind("<MouseWheel>", on_mousewheel)
        scrollable_frame.bind("<MouseWheel>", on_mousewheel)

        # Engine selection - more compact
        engine_frame = ttk.LabelFrame(scrollable_frame, text="Transcription Engine", padding=5)  # Reduced padding
        engine_frame.pack(fill=tk.X, padx=10, pady=3)  # Reduced padding

        current_engine = self.config.get("transcription_engine", "openai_whisper")
        engine_var = tk.StringVar(value=current_engine)

        for engine, info in TRANSCRIPTION_ENGINES.items():
            desc = f"{info['name']} - {info['description']}"
            if info['requires_api']:
                desc += " (API key required)"
            rb = ttk.Radiobutton(engine_frame, text=desc, variable=engine_var, value=engine)
            rb.pack(anchor=tk.W, pady=1)  # Reduced padding
        
        # Moonshine info panel (shown when Moonshine is selected)
        moonshine_frame = ttk.Frame(engine_frame)
        
        # Check Moonshine availability
        try:
            from audio_handler import MOONSHINE_AVAILABLE, is_moonshine_model_downloaded, download_moonshine_model
            moonshine_installed = MOONSHINE_AVAILABLE
        except ImportError:
            moonshine_installed = False
        
        moonshine_status_label = ttk.Label(moonshine_frame, text="", font=('Arial', 8), foreground='#666')
        moonshine_status_label.pack(anchor=tk.W, padx=20, pady=(0, 3))
        
        moonshine_btn_row = ttk.Frame(moonshine_frame)
        # Not packed initially — update_moonshine_status() will show it only when needed
        
        ttk.Label(moonshine_frame,
                  text="ℹ️ For speaker identification (diarization), use AssemblyAI instead.",
                  font=('Arial', 8), foreground='#888').pack(anchor=tk.W, padx=20, pady=(3, 0))
        
        # Moonshine chunk duration setting
        chunk_subframe = ttk.Frame(moonshine_frame)
        chunk_subframe.pack(anchor=tk.W, padx=20, pady=(5, 0))
        ttk.Label(chunk_subframe, text="Audio chunk size:", font=('Arial', 8)).pack(side=tk.LEFT)
        
        current_chunk = self.config.get("moonshine_chunk_seconds", 15)
        moonshine_chunk_var = tk.IntVar(value=current_chunk)
        
        for sec in [10, 15, 20, 30]:
            label = f"{sec}s"
            if sec == 15:
                label += " ⭐"
            ttk.Radiobutton(chunk_subframe, text=label, variable=moonshine_chunk_var,
                           value=sec).pack(side=tk.LEFT, padx=3)
        
        ttk.Label(moonshine_frame,
                  text="Shorter chunks = finer timestamps & less hallucination. Longer = more context per chunk.",
                  font=('Arial', 7), foreground='#999').pack(anchor=tk.W, padx=20, pady=(1, 0))
        
        def update_moonshine_status():
            if not moonshine_installed:
                moonshine_status_label.config(
                    text="⚠️ Not installed. Run: pip install fastrtc-moonshine-onnx soundfile",
                    foreground='#cc6600')
                moonshine_btn_row.pack_forget()
            else:
                model_ready = is_moonshine_model_downloaded()
                if model_ready:
                    moonshine_status_label.config(
                        text="✅ Moonshine ready — 100% on-device, no API key needed. English only.",
                        foreground='#228B22')
                    moonshine_btn_row.pack_forget()
                else:
                    moonshine_status_label.config(
                        text="📥 Model not yet downloaded (~57MB, one-time). Click below or it downloads automatically on first use.",
                        foreground='#cc6600')
                    for w in moonshine_btn_row.winfo_children():
                        w.destroy()
                    moonshine_btn_row.pack(anchor=tk.W, padx=20)
                    def do_download():
                        import threading
                        moonshine_status_label.config(text="📥 Downloading Moonshine model...", foreground='#336699')
                        def _dl():
                            try:
                                download_moonshine_model("moonshine/base")
                                settings.after(0, lambda: moonshine_status_label.config(
                                    text="✅ Moonshine ready — 100% on-device, no API key needed. English only.",
                                    foreground='#228B22'))
                                settings.after(0, lambda: moonshine_btn_row.pack_forget())
                            except Exception as e:
                                settings.after(0, lambda: moonshine_status_label.config(
                                    text=f"❌ Download failed: {e}", foreground='red'))
                        threading.Thread(target=_dl, daemon=True).start()
                    ttk.Button(moonshine_btn_row, text="📥 Download Model Now",
                               command=do_download).pack(side=tk.LEFT, padx=2)
        
        def update_moonshine_visibility(*args):
            if engine_var.get() == "moonshine":
                moonshine_frame.pack(anchor=tk.W, pady=(0, 3), after=moonshine_pack_anchor)
                update_moonshine_status()
            else:
                moonshine_frame.pack_forget()
        
        # Find the Moonshine radio button to pack details right after it
        moonshine_pack_anchor = None
        for child in engine_frame.winfo_children():
            if isinstance(child, ttk.Radiobutton):
                moonshine_pack_anchor = child  # Will be the last radio button
        
        engine_var.trace_add('write', update_moonshine_visibility)
        update_moonshine_visibility()  # Set initial state
        
        # TurboScribe as an engine option
        try:
            import turboscribe_helper
            turboscribe_ok = True
        except ImportError:
            turboscribe_ok = False
        
        if turboscribe_ok:
            ttk.Separator(engine_frame, orient='horizontal').pack(fill=tk.X, pady=4)
            rb_ts = ttk.Radiobutton(engine_frame, 
                text="TurboScribe (External) - Highest accuracy, speaker labels (manual workflow)",
                variable=engine_var, value="turboscribe")
            rb_ts.pack(anchor=tk.W, pady=1)
            
            # TurboScribe action buttons + explanation (shown/hidden based on selection)
            ts_detail_frame = ttk.Frame(engine_frame)
            
            ttk.Label(ts_detail_frame, 
                      text="ℹ️ Send audio → transcribe on TurboScribe.com → download TXT → Load into DocAnalyser",
                      font=('Arial', 8), foreground='#666').pack(anchor=tk.W, padx=20, pady=(0, 3))
            
            ts_btn_row = ttk.Frame(ts_detail_frame)
            ts_btn_row.pack(anchor=tk.W, padx=20)
            
            ttk.Button(ts_btn_row, text="🚀 Send to TurboScribe",
                       command=lambda: [settings.destroy(), self.send_to_turboscribe()]).pack(side=tk.LEFT, padx=2)
            ttk.Label(ts_btn_row, text="   Then load the downloaded transcript with the normal Load button",
                      font=('Arial', 8), foreground='#666').pack(side=tk.LEFT)
            
            def update_ts_visibility(*args):
                if engine_var.get() == "turboscribe":
                    ts_detail_frame.pack(anchor=tk.W, pady=(0, 3))
                else:
                    ts_detail_frame.pack_forget()
            
            engine_var.trace_add('write', update_ts_visibility)
            update_ts_visibility()  # Set initial state
        
        # API Keys section
        api_frame = ttk.LabelFrame(scrollable_frame, text="🔑 API Keys (for Cloud Services)", padding=5)
        api_frame.pack(fill=tk.X, padx=10, pady=3)
        
        # OpenAI API key (uses same key as AI Provider)
        openai_row = ttk.Frame(api_frame)
        openai_row.pack(fill=tk.X, pady=2)
        ttk.Label(openai_row, text="OpenAI:", width=12).pack(side=tk.LEFT)
        
        # Get current OpenAI key from provider keys
        current_openai_key = self.config.get("keys", {}).get("OpenAI", "")
        openai_key_var = tk.StringVar(value=current_openai_key)
        openai_entry = ttk.Entry(openai_row, textvariable=openai_key_var, width=35, show="*")
        openai_entry.pack(side=tk.LEFT, padx=5)
        
        def open_openai_signup():
            import webbrowser
            webbrowser.open("https://platform.openai.com/api-keys")
        
        ttk.Button(openai_row, text="Get Key", command=open_openai_signup, width=8).pack(side=tk.LEFT, padx=2)
        
        # Show/hide toggle for OpenAI key
        def toggle_openai_show():
            if openai_entry.cget('show') == '*':
                openai_entry.config(show='')
                openai_show_btn.config(text="Hide")
            else:
                openai_entry.config(show='*')
                openai_show_btn.config(text="Show")
        
        openai_show_btn = ttk.Button(openai_row, text="Show", command=toggle_openai_show, width=5)
        openai_show_btn.pack(side=tk.LEFT, padx=2)
        
        ttk.Label(api_frame, text="💡 Same key used for GPT models in AI Provider", 
                  font=('Arial', 8), foreground='gray').pack(anchor=tk.W, padx=12)
        
        # AssemblyAI API key
        assemblyai_row = ttk.Frame(api_frame)
        assemblyai_row.pack(fill=tk.X, pady=2)
        ttk.Label(assemblyai_row, text="AssemblyAI:", width=12).pack(side=tk.LEFT)
        
        current_assemblyai_key = self.config.get("keys", {}).get("AssemblyAI", "")
        assemblyai_key_var = tk.StringVar(value=current_assemblyai_key)
        assemblyai_entry = ttk.Entry(assemblyai_row, textvariable=assemblyai_key_var, width=35, show="*")
        assemblyai_entry.pack(side=tk.LEFT, padx=5)
        
        def open_assemblyai_signup():
            import webbrowser
            webbrowser.open("https://www.assemblyai.com/dashboard/signup")
        
        ttk.Button(assemblyai_row, text="Get Key", command=open_assemblyai_signup, width=8).pack(side=tk.LEFT, padx=2)
        
        # Show/hide toggle for AssemblyAI key
        def toggle_assemblyai_show():
            if assemblyai_entry.cget('show') == '*':
                assemblyai_entry.config(show='')
                assemblyai_show_btn.config(text="Hide")
            else:
                assemblyai_entry.config(show='*')
                assemblyai_show_btn.config(text="Show")
        
        assemblyai_show_btn = ttk.Button(assemblyai_row, text="Show", command=toggle_assemblyai_show, width=5)
        assemblyai_show_btn.pack(side=tk.LEFT, padx=2)
        
        ttk.Label(api_frame, text="💡 Free tier: 100 hours/month. Supports speaker identification.", 
                  font=('Arial', 8), foreground='gray').pack(anchor=tk.W, padx=12)
        
        # Google Cloud Vision API key (for OCR)
        gcv_row = ttk.Frame(api_frame)
        gcv_row.pack(fill=tk.X, pady=2)
        ttk.Label(gcv_row, text="Cloud Vision:", width=12).pack(side=tk.LEFT)
        
        current_gcv_key = self.config.get("keys", {}).get("Google Cloud Vision", "")
        gcv_key_var = tk.StringVar(value=current_gcv_key)
        gcv_entry = ttk.Entry(gcv_row, textvariable=gcv_key_var, width=35, show="*")
        gcv_entry.pack(side=tk.LEFT, padx=5)
        
        def open_gcv_signup():
            import webbrowser
            webbrowser.open("https://console.cloud.google.com/apis/library/vision.googleapis.com")
        
        ttk.Button(gcv_row, text="Get Key", command=open_gcv_signup, width=8).pack(side=tk.LEFT, padx=2)
        
        # Show/hide toggle for Cloud Vision key
        def toggle_gcv_show():
            if gcv_entry.cget('show') == '*':
                gcv_entry.config(show='')
                gcv_show_btn.config(text="Hide")
            else:
                gcv_entry.config(show='*')
                gcv_show_btn.config(text="Show")
        
        gcv_show_btn = ttk.Button(gcv_row, text="Show", command=toggle_gcv_show, width=5)
        gcv_show_btn.pack(side=tk.LEFT, padx=2)
        
        ttk.Label(api_frame, text="🔒 Not yet activated. For future use with Google Cloud Vision OCR.", 
                  font=('Arial', 8), foreground='gray').pack(anchor=tk.W, padx=12)

        # Language selection - more compact
        lang_frame = ttk.LabelFrame(scrollable_frame, text="Transcription Language", padding=5)
        lang_frame.pack(fill=tk.X, padx=10, pady=3)

        current_lang = self.config.get("transcription_language", "")  # Empty for auto-detect
        lang_var = tk.StringVar(value=current_lang)

        ttk.Label(lang_frame, text="Language (leave blank for auto-detect):").pack(anchor=tk.W)
        lang_combo = ttk.Combobox(lang_frame, textvariable=lang_var, width=30)
        lang_combo['values'] = ["en - English", "fr - French", "de - German", "es - Spanish",
                                "it - Italian", "pt - Portuguese", "ru - Russian", "zh - Chinese",
                                "ja - Japanese", "ar - Arabic", "hi - Hindi"]
        lang_combo.pack(fill=tk.X, pady=2)

        # Speaker diarization - more compact
        diarization_frame = ttk.LabelFrame(scrollable_frame, text="Speaker Diarization", padding=5)
        diarization_frame.pack(fill=tk.X, padx=10, pady=3)

        diarization_var = tk.BooleanVar(value=self.config.get("speaker_diarization", False))
        ttk.Checkbutton(diarization_frame, text="Enable Speaker Diarization (AssemblyAI & Moonshine)",
                        variable=diarization_var).pack(anchor=tk.W)

        # 🆕 NEW: VAD Toggle - more compact
        vad_frame = ttk.LabelFrame(scrollable_frame, text="Voice Activity Detection (VAD)", padding=5)
        vad_frame.pack(fill=tk.X, padx=10, pady=3)

        vad_var = tk.BooleanVar(value=self.config.get("enable_vad", True))
        ttk.Checkbutton(vad_frame, text="Enable VAD (faster-whisper only)",
                        variable=vad_var).pack(anchor=tk.W)
        ttk.Label(vad_frame, text="âš ï¸ Disable if audio contains extended laughter, music, or non-speech",
                  font=('Arial', 9), foreground='#666').pack(anchor=tk.W, padx=20)

        # 🆕 NEW: Timestamp Interval
        timestamp_frame = ttk.LabelFrame(scrollable_frame, text="⏱️ Timestamp Frequency", padding=5)
        timestamp_frame.pack(fill=tk.X, padx=10, pady=3)

        current_interval = self.config.get("timestamp_interval", "5min")
        timestamp_var = tk.StringVar(value=current_interval)

        ttk.Label(timestamp_frame, text="How often to show timestamps in transcripts:").pack(anchor=tk.W)
        
        interval_options = {
            "every_segment": "Every segment (every few seconds)",
            "1min": "Every 1 minute",
            "5min": "Every 5 minutes ⭐ Recommended",
            "10min": "Every 10 minutes",
            "never": "Never (no timestamps)"
        }
        
        for value, label in interval_options.items():
            rb = ttk.Radiobutton(timestamp_frame, text=label, variable=timestamp_var, value=value)
            rb.pack(anchor=tk.W, pady=1)

        # faster-whisper model size - more compact
        model_frame = ttk.LabelFrame(scrollable_frame, text="faster-whisper Model Size (Local Only)", padding=5)
        model_frame.pack(fill=tk.X, padx=10, pady=3)

        current_model_size = self.config.get("faster_whisper_model", "base")
        model_size_var = tk.StringVar(value=current_model_size)

        model_info = {
            "tiny": "Tiny - Fastest (~75 MB)",
            "base": "Base - Good balance (~150 MB)",
            "small": "Small - Better quality (~500 MB)",
            "medium": "Medium - High quality (~1.5 GB)",
            "large-v3": "Large V3 - Best quality (~3 GB)"
        }

        for size, description in model_info.items():
            rb = ttk.Radiobutton(model_frame, text=description, variable=model_size_var, value=size)
            rb.pack(anchor=tk.W, pady=1)

        # === Dictation (Speech-to-Text) Settings ===
        dictation_frame = ttk.LabelFrame(scrollable_frame, text="🎙️ Dictation (Speech-to-Text)", padding=5)
        dictation_frame.pack(fill=tk.X, padx=10, pady=3)
        
        ttk.Label(dictation_frame, text="Mode for the Dictate button (record speech → text):",
                  font=('Arial', 9)).pack(anchor=tk.W)
        
        current_dictation_mode = self.config.get("dictation_mode", "local_first")
        dictation_mode_var = tk.StringVar(value=current_dictation_mode)
        
        # Import dictation modes from config
        try:
            from config import DICTATION_MODES
        except ImportError:
            DICTATION_MODES = {
                "local_first": {"label": "Local first (recommended)", "description": "Free & private, falls back to cloud"},
                "cloud_direct": {"label": "Cloud (OpenAI)", "description": "Fastest, costs ~$0.006/min"},
                "local_only": {"label": "Local only", "description": "Fully private, no fallback"}
            }
        
        for mode_key, mode_info in DICTATION_MODES.items():
            rb = ttk.Radiobutton(dictation_frame, text=mode_info['label'], 
                                 variable=dictation_mode_var, value=mode_key)
            rb.pack(anchor=tk.W, pady=1)
            ttk.Label(dictation_frame, text=f"    {mode_info['description']}", 
                      font=('Arial', 8), foreground='gray').pack(anchor=tk.W)
        
        # Dictation model selection (uses same models as faster-whisper)
        ttk.Label(dictation_frame, text="\nLocal model for dictation:", font=('Arial', 9)).pack(anchor=tk.W)
        
        current_whisper_model = self.config.get("whisper_model", "base")
        whisper_model_var = tk.StringVar(value=current_whisper_model)
        
        whisper_models_combo = ttk.Combobox(dictation_frame, textvariable=whisper_model_var, 
                                            state="readonly", width=40)
        whisper_models_combo['values'] = [
            "tiny - Fastest (75 MB)",
            "base - Good balance (150 MB) ⭐",
            "small - Better accuracy (500 MB)",
            "medium - High accuracy (1.5 GB)",
            "large-v3 - Best accuracy (3 GB)"
        ]
        # Set current value
        for i, val in enumerate(whisper_models_combo['values']):
            if val.startswith(current_whisper_model):
                whisper_models_combo.current(i)
                break
        else:
            whisper_models_combo.current(1)  # Default to base
        whisper_models_combo.pack(fill=tk.X, pady=2)
        
        ttk.Label(dictation_frame, 
                  text="💡 Cloud fallback uses your selected Transcription Engine above",
                  font=('Arial', 8), foreground='blue').pack(anchor=tk.W, pady=(3, 0))

        # Device selection - more compact
        device_frame = ttk.LabelFrame(scrollable_frame, text="Processing Device (faster-whisper)", padding=5)
        device_frame.pack(fill=tk.X, padx=10, pady=3)

        current_device = self.config.get("faster_whisper_device", "cpu")
        device_var = tk.StringVar(value=current_device)

        ttk.Radiobutton(device_frame, text="CPU (Compatible with all systems)",
                        variable=device_var, value="cpu").pack(anchor=tk.W, pady=1)
        ttk.Radiobutton(device_frame, text="GPU/CUDA (Requires NVIDIA GPU)",
                        variable=device_var, value="cuda").pack(anchor=tk.W, pady=1)

        # === Cache Control ===
        cache_frame = ttk.LabelFrame(scrollable_frame, text="🔄 Cache Control", padding=5)
        cache_frame.pack(fill=tk.X, padx=10, pady=3)
        
        ttk.Checkbutton(cache_frame, text="Bypass cache (force re-transcription on next load)",
                        variable=self.bypass_cache_var).pack(anchor=tk.W)
        ttk.Label(cache_frame, text="💡 Check this before loading audio to ignore cached transcripts.",
                  font=('Arial', 8), foreground='gray').pack(anchor=tk.W, padx=20)

        # Info section - more compact
        info_frame = ttk.LabelFrame(scrollable_frame, text="ℹ️ About Audio Transcription", padding=5)
        info_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=3)

        info_text = """Audio Transcription converts audio files or YouTube video audio to text.

    Features:
    - Supports MP3, WAV, M4A, and more
    - YouTube audio extraction when captions unavailable
    - Speaker diarization (AssemblyAI)
    - Word-level timestamps
    - Caching for fast re-processing

    Tips:
    - OpenAI Whisper has a 25MB limit
    - AssemblyAI excels at speaker identification
    - faster-whisper is FREE and has no file size limit
    - FFmpeg required for audio processing"""

        info_widget = scrolledtext.ScrolledText(info_frame, wrap=tk.WORD, height=6,
                                                font=('Arial', 10))  # Reduced height
        info_widget.pack(fill=tk.BOTH, expand=True)
        info_widget.insert('1.0', info_text)
        info_widget.config(state=tk.DISABLED)

        # Track initial values for unsaved-changes detection
        audio_initial = {
            'engine': current_engine,
            'openai_key': current_openai_key,
            'assemblyai_key': current_assemblyai_key,
            'gcv_key': current_gcv_key,
            'lang': current_lang,
            'diarization': self.config.get("speaker_diarization", False),
            'vad': self.config.get("enable_vad", True),
            'timestamp': current_interval,
            'model_size': current_model_size,
            'dictation_mode': current_dictation_mode,
            'whisper_model': current_whisper_model,
            'device': current_device,
        }
        saved_flag = [False]

        def get_audio_current():
            ws = whisper_model_var.get()
            wm = ws.split(' - ')[0] if ' - ' in ws else ws
            ls = lang_var.get()
            lc = ls.split(' - ')[0] if ' - ' in ls else ls
            return {
                'engine': engine_var.get(),
                'openai_key': openai_key_var.get().strip(),
                'assemblyai_key': assemblyai_key_var.get().strip(),
                'gcv_key': gcv_key_var.get().strip(),
                'lang': lc,
                'diarization': diarization_var.get(),
                'vad': vad_var.get(),
                'timestamp': timestamp_var.get(),
                'moonshine_chunk_seconds': moonshine_chunk_var.get(),
                'model_size': model_size_var.get(),
                'dictation_mode': dictation_mode_var.get(),
                'whisper_model': wm,
                'device': device_var.get(),
            }

        def save_settings():
            saved_flag[0] = True
            self.config["transcription_engine"] = engine_var.get()
            # Also update the live StringVar so the change takes effect immediately
            self.transcription_engine_var.set(engine_var.get())
            lang_selection = lang_var.get()
            lang_code = lang_selection.split(' - ')[0] if ' - ' in lang_selection else ""
            self.config["transcription_language"] = lang_code
            self.config["speaker_diarization"] = diarization_var.get()
            self.config["enable_vad"] = vad_var.get()
            self.config["timestamp_interval"] = timestamp_var.get()
            self.config["moonshine_chunk_seconds"] = moonshine_chunk_var.get()
            self.config["faster_whisper_model"] = model_size_var.get()
            self.config["faster_whisper_device"] = device_var.get()
            
            # Save dictation settings
            self.config["dictation_mode"] = dictation_mode_var.get()
            # Extract model name from combo selection (e.g., "base - Good balance (150 MB)" -> "base")
            whisper_selection = whisper_model_var.get()
            whisper_model = whisper_selection.split(' - ')[0] if ' - ' in whisper_selection else whisper_selection
            self.config["whisper_model"] = whisper_model
            
            # Save API keys
            if "keys" not in self.config:
                self.config["keys"] = {}
            
            # Save OpenAI key (also used for AI provider)
            openai_key = openai_key_var.get().strip()
            if openai_key:
                self.config["keys"]["OpenAI"] = openai_key
            
            # Save AssemblyAI key
            assemblyai_key = assemblyai_key_var.get().strip()
            if assemblyai_key:
                self.config["keys"]["AssemblyAI"] = assemblyai_key
            
            # Save Google Cloud Vision key
            gcv_key = gcv_key_var.get().strip()
            if gcv_key:
                self.config["keys"]["Google Cloud Vision"] = gcv_key
            
            save_config(self.config)
            messagebox.showinfo("Success", "Audio settings saved")
            settings.destroy()

        def cleanup_and_close():
            canvas.unbind_all("<MouseWheel>")
            settings.destroy()

        def on_close():
            if saved_flag[0]:
                cleanup_and_close()
                return
            try:
                current = get_audio_current()
                if current != audio_initial:
                    result = messagebox.askyesno(
                        "Unsaved Changes",
                        "You have unsaved changes. Save before closing?",
                        parent=settings
                    )
                    if result:
                        save_settings()
                        return
            except Exception:
                pass
            cleanup_and_close()

        # Button frame at the bottom - fixed position
        btn_frame = ttk.Frame(settings)
        btn_frame.pack(fill=tk.X, pady=5, padx=10, side=tk.BOTTOM)

        ttk.Button(btn_frame, text="Save Settings", command=save_settings).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Close", command=on_close).pack(side=tk.RIGHT, padx=5)
        settings.protocol("WM_DELETE_WINDOW", on_close)

    def show_tesseract_setup_wizard(self, parent_window):
        parent_window.title("OCR Setup - Required Components")
        main_frame = ttk.Frame(parent_window, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(main_frame, text="🔧 OCR Setup - Required Components", font=('Arial', 14, 'bold')).pack(pady=(0, 20))
        available, error_msg, tesseract_path = get_ocr().check_ocr_availability()
        if error_msg == "TESSERACT_NOT_FOUND":
            url, instructions = get_ocr().get_tesseract_install_info()
        else:
            url, instructions = get_ocr().get_poppler_install_info()
        ttk.Label(main_frame, text="OCR component missing", font=('Arial', 12)).pack(pady=5)
        text_widget = scrolledtext.ScrolledText(main_frame, wrap=tk.WORD, height=15, font=('Arial', 10))
        text_widget.pack(fill=tk.BOTH, expand=True, pady=10)
        text_widget.insert('1.0', instructions)
        text_widget.config(state=tk.DISABLED)

        def open_download():
            webbrowser.open(url)

        ttk.Button(main_frame, text="Download Tesseract" if error_msg == "TESSERACT_NOT_FOUND" else "Download Poppler",
                   command=open_download).pack(pady=10)
        ttk.Button(main_frame, text="Close", command=parent_window.destroy).pack(pady=10)

    def test_ocr_setup(self):
        available, error_msg, tesseract_path = get_ocr().check_ocr_availability()
        if available:
            messagebox.showinfo("OCR Test",
                                "OCR is properly configured!\n\nTesseract path: {}\nPoppler: Available".format(
                                    tesseract_path))
        else:
            messagebox.showerror("OCR Test", f"OCR setup incomplete: {error_msg}")



