"""
settings_manager.py - Settings dialogs and configuration UI for DocAnalyser.

Extracted from Main.py to reduce file size. Uses a mixin pattern so all
self.xxx references continue to work unchanged.

Methods included:
  - open_settings()           Main settings dialog
  - on_provider_select_in_settings()
  - save_api_key_in_settings()
  - _save_ollama_url(), _test_ollama_connection(), _is_ollama_installed()
  - _show_system_recommendations()
  - _open_local_ai_guide(), _show_guide_in_window()
  - save_model_selection(), save_all_settings()
  - open_prompt_manager(), save_prompt()
  - refresh_main_prompt_combo(), set_prompt_from_library()
  - open_chunk_settings()
  - open_ocr_settings()
  - open_audio_settings()
  - show_tesseract_setup_wizard(), test_ocr_setup()
  - open_cache_manager()
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

    def open_settings(self):
        settings = tk.Toplevel(self.root)
        settings.title("All Settings")
        settings.geometry("650x720")  # Height adjusted for all content
        self.apply_window_style(settings)
        ttk.Label(settings, text="All Settings", font=('Arial', 12, 'bold')).pack(pady=10)

        # AI Provider and Model Frame - Single column layout
        ai_frame = ttk.LabelFrame(settings, text="AI Configuration", padding=10)
        ai_frame.pack(fill=tk.X, padx=20, pady=5)

        # Provider row
        provider_row = ttk.Frame(ai_frame)
        provider_row.pack(fill=tk.X, pady=2)
        ttk.Label(provider_row, text="AI Provider:", width=12).pack(side=tk.LEFT)
        provider_combo = ttk.Combobox(provider_row, textvariable=self.provider_var,
                                      state="readonly", width=25)
        # Include all providers including Ollama (Local)
        provider_combo['values'] = list(self.models.keys())
        provider_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        # Callbacks to run when provider changes (populated later)
        provider_change_callbacks = []

        provider_combo.bind('<<ComboboxSelected>>', lambda e: (self.on_provider_select_in_settings(e),
                                                               [cb() for cb in provider_change_callbacks]))

        # Model row
        model_row = ttk.Frame(ai_frame)
        model_row.pack(fill=tk.X, pady=2)
        ttk.Label(model_row, text="Model:", width=12).pack(side=tk.LEFT)
        self.model_combo = ttk.Combobox(model_row, textvariable=self.model_var,
                                        state="readonly", width=25)
        self.model_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.model_combo.bind('<<ComboboxSelected>>', lambda e: self.save_model_selection())

        # Model refresh button
        refresh_row = ttk.Frame(ai_frame)
        refresh_row.pack(fill=tk.X, pady=2)

        refresh_btn = ttk.Button(
            refresh_row,
            text="🔄 Refresh Models",
            command=self.refresh_models_from_apis,
            width=20
        )
        refresh_btn.pack(side=tk.LEFT, padx=2)
        if HELP_TEXTS:
            add_help(refresh_btn, **HELP_TEXTS.get("settings_refresh_models", {"title": "Refresh Models",
                                                                               "description": "Fetch latest models from APIs"}))

        ttk.Label(
            refresh_row,
            text="(Fetches latest models from APIs)",
            font=('Arial', 8),
            foreground='gray'
        ).pack(side=tk.LEFT, padx=5)

        self.on_provider_select_in_settings()

        # API Key Frame
        api_frame = ttk.LabelFrame(settings, text="API Key", padding=10)
        api_frame.pack(fill=tk.X, padx=20, pady=5)
        if CONTEXT_HELP_AVAILABLE:
            add_help(api_frame, **HELP_TEXTS.get("settings_api_key",
                                                 {"title": "API Key", "description": "API key for cloud AI services"}))

        api_row = ttk.Frame(api_frame)
        api_row.pack(fill=tk.X)
        ttk.Label(api_row, text="API Key:", width=12).pack(side=tk.LEFT)
        api_entry = ttk.Entry(api_row, textvariable=self.api_key_var, show="*")
        api_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        api_entry.bind('<FocusOut>', lambda e: self.save_api_key_in_settings())
        if CONTEXT_HELP_AVAILABLE:
            add_help(api_entry, **HELP_TEXTS.get("settings_api_key",
                                                 {"title": "API Key", "description": "API key for cloud AI services"}))

        # API Key help row - shows link to get API key when field is empty
        api_help_row = tk.Frame(api_frame, bg='#dcdad5')
        # Don't pack yet - will be controlled by update function

        api_help_label = tk.Label(
            api_help_row,
            text="Get an API key from ",
            font=('Arial', 8),
            fg='gray',
            bg='#dcdad5'
        )
        api_help_label.pack(side=tk.LEFT)

        api_help_link = tk.Label(
            api_help_row,
            text="",
            font=('Arial', 8, 'underline'),
            fg='#0066CC',
            bg='#dcdad5',
            cursor='hand2'
        )
        api_help_link.pack(side=tk.LEFT)

        # Provider signup URLs
        provider_signup_urls = {
            "OpenAI (ChatGPT)": ("platform.openai.com", "https://platform.openai.com/api-keys"),
            "Anthropic (Claude)": ("console.anthropic.com", "https://console.anthropic.com/settings/keys"),
            "Google (Gemini)": ("aistudio.google.com", "https://aistudio.google.com/app/apikey"),
            "xAI (Grok)": ("console.x.ai", "https://console.x.ai/"),
            "DeepSeek": ("platform.deepseek.com", "https://platform.deepseek.com/api_keys"),
            "Ollama (Local)": (None, None)  # No API key needed
        }

        api_help_visible = [False]  # Track visibility state

        def update_api_help_visibility(*args):
            """Show/hide API key help based on provider and key presence"""
            try:
                provider = self.provider_var.get()
                api_key = self.api_key_var.get().strip()

                # Get URL info for this provider
                url_info = provider_signup_urls.get(provider, (None, None))
                display_name, url = url_info

                # Should hide if: Ollama selected, or API key is present, or no URL defined
                should_hide = (provider == "Ollama (Local)" or api_key or not url)

                if should_hide and api_help_visible[0]:
                    api_help_row.pack_forget()
                    api_help_visible[0] = False
                elif not should_hide and not api_help_visible[0]:
                    api_help_row.pack(fill=tk.X, pady=(5, 0), after=api_row)
                    api_help_visible[0] = True

                # Update link text and handler if visible
                if not should_hide:
                    api_help_link.config(text=display_name)
                    api_help_link.unbind('<Button-1>')
                    api_help_link.bind('<Button-1>', lambda e, u=url: webbrowser.open(u))
            except tk.TclError:
                pass  # Window was closed

        # Bind to API key entry changes (using KeyRelease for immediate feedback)
        api_entry.bind('<KeyRelease>', update_api_help_visibility)

        # Add to provider change callbacks
        provider_change_callbacks.append(update_api_help_visibility)

        # Initial update
        update_api_help_visibility()

        # Ollama Configuration Frame (only shown when Ollama is selected)
        lm_frame = ttk.LabelFrame(settings, text="Ollama (Local AI)", padding=10)
        lm_frame.pack(fill=tk.X, padx=20, pady=5)

        # Ollama URL
        url_row = ttk.Frame(lm_frame)
        url_row.pack(fill=tk.X, pady=2)
        ttk.Label(url_row, text="Server URL:", width=12).pack(side=tk.LEFT)

        self.ollama_url_var = tk.StringVar(value=self.config.get("ollama_base_url", "http://localhost:11434"))
        url_entry = ttk.Entry(url_row, textvariable=self.ollama_url_var)
        url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        url_entry.bind('<FocusOut>', lambda e: self._save_ollama_url())

        # Test Connection button
        btn_row = ttk.Frame(lm_frame)
        btn_row.pack(fill=tk.X, pady=5)

        test_conn_btn = ttk.Button(
            btn_row,
            text="🔌 Test Connection",
            command=self._test_ollama_connection,
            width=18
        )
        test_conn_btn.pack(side=tk.LEFT, padx=2)
        if CONTEXT_HELP_AVAILABLE:
            add_help(test_conn_btn, **HELP_TEXTS.get("settings_test_connection", {"title": "Test Connection",
                                                                                  "description": "Test Ollama connection"}))

        system_check_btn = ttk.Button(
            btn_row,
            text="💻 System Check",
            command=self._show_system_recommendations,
            width=18
        )
        system_check_btn.pack(side=tk.LEFT, padx=2)
        if CONTEXT_HELP_AVAILABLE:
            add_help(system_check_btn, **HELP_TEXTS.get("settings_system_check", {"title": "System Check",
                                                                                  "description": "Check system suitability for local AI"}))

        # Second row for guide button
        btn_row2 = ttk.Frame(lm_frame)
        btn_row2.pack(fill=tk.X, pady=2)

        guide_btn = ttk.Button(
            btn_row2,
            text="📖 Local AI Guide",
            command=self._open_local_ai_guide,
            width=18
        )
        guide_btn.pack(side=tk.LEFT, padx=2)
        if HELP_TEXTS:
            add_help(guide_btn, **HELP_TEXTS.get("ollama_setup", {"title": "Local AI Guide",
                                                                     "description": "Open the beginner's guide to running AI locally"}))

        # Manage Models button - opens Local AI Model Manager
        manage_models_btn = ttk.Button(
            btn_row2,
            text="📦 Manage Models",
            command=self._open_local_model_manager,
            width=18
        )
        manage_models_btn.pack(side=tk.LEFT, padx=2)
        if HELP_TEXTS:
            add_help(manage_models_btn, **HELP_TEXTS.get("manage_local_models", {
                "title": "Manage Local Models",
                "description": "View installed models, download new ones, or delete unused models"
            }))

        self.ollama_status_var = tk.StringVar(value="")
        ttk.Label(
            btn_row,
            textvariable=self.ollama_status_var,
            font=('Arial', 8)
        ).pack(side=tk.LEFT, padx=10)

        # Info text with clickable link
        info_row = tk.Frame(lm_frame, bg='#dcdad5')
        info_row.pack(anchor=tk.W)

        tk.Label(
            info_row,
            text="Ollama provides free local AI. Download from ",
            font=('Arial', 8),
            fg='gray',
            bg='#dcdad5'
        ).pack(side=tk.LEFT)

        link_label = tk.Label(
            info_row,
            text="ollama.com",
            font=('Arial', 8, 'underline'),
            fg='#0066CC',
            bg='#dcdad5',
            cursor='hand2'
        )
        link_label.pack(side=tk.LEFT)
        link_label.bind('<Button-1>', lambda e: webbrowser.open('https://ollama.com'))

        # ============================================================
        # NEW: Display Settings Frame (Viewer Configuration)
        # ============================================================
        display_frame = ttk.LabelFrame(settings, text="Viewer Display Settings", padding=10)
        display_frame.pack(fill=tk.X, padx=20, pady=5)

        # --- Character warning threshold ---
        char_row = ttk.Frame(display_frame)
        char_row.pack(fill=tk.X, pady=2)

        ttk.Label(char_row, text="Expand warning at:", width=16).pack(side=tk.LEFT)

        self.char_warning_var = tk.StringVar(
            value=str(self.config.get('viewer_char_warning_threshold', 150000))
        )
        char_entry = ttk.Entry(char_row, textvariable=self.char_warning_var, width=12)
        char_entry.pack(side=tk.LEFT, padx=5)

        ttk.Label(char_row, text="characters").pack(side=tk.LEFT)

        # Explanation text
        ttk.Label(
            display_frame,
            text="💡 ~50-75 pages of text. Warns before expanding large content in Viewer.",
            font=('Arial', 8),
            foreground='gray'
        ).pack(anchor=tk.W, padx=(20, 0))

        # --- Collapse threshold for multiple sources ---
        collapse_row = ttk.Frame(display_frame)
        collapse_row.pack(fill=tk.X, pady=(8, 2))

        ttk.Label(collapse_row, text="Auto-collapse when:", width=16).pack(side=tk.LEFT)

        self.collapse_threshold_var = tk.StringVar(
            value=str(self.config.get('viewer_collapse_threshold', 2))
        )
        collapse_spinbox = ttk.Spinbox(
            collapse_row,
            from_=1,
            to=20,
            textvariable=self.collapse_threshold_var,
            width=5
        )
        collapse_spinbox.pack(side=tk.LEFT, padx=5)

        ttk.Label(collapse_row, text="or more source documents").pack(side=tk.LEFT)

        # Explanation text for collapse threshold
        ttk.Label(
            display_frame,
            text="💡 Sources start collapsed when you load many documents at once.",
            font=('Arial', 8),
            foreground='gray'
        ).pack(anchor=tk.W, padx=(20, 0))

        # --- Character count reference guide ---
        reference_text = (
            "📊 Reference: 1 page ≈ 2,500 chars • 50K = ~20 pages • "
            "150K = ~60 pages • 500K = ~200 pages"
        )
        ttk.Label(
            display_frame,
            text=reference_text,
            font=('Arial', 8),
            foreground='#555555'
        ).pack(anchor=tk.W, pady=(8, 0))

        # Additional Settings Buttons
        btn_frame = ttk.Frame(settings)
        btn_frame.pack(fill=tk.X, pady=10, padx=20)

        row1 = ttk.Frame(btn_frame)
        row1.pack(fill=tk.X, pady=2)

        chunk_btn = ttk.Button(row1, text="Chunk Settings", command=self.open_chunk_settings, width=18)
        chunk_btn.pack(side=tk.LEFT, padx=2)
        if HELP_TEXTS:
            add_help(chunk_btn, **HELP_TEXTS.get("settings_chunk", {"title": "Chunk Settings",
                                                                    "description": "Configure document chunking"}))

        ocr_btn = ttk.Button(row1, text="OCR Settings", command=self.open_ocr_settings, width=18)
        ocr_btn.pack(side=tk.LEFT, padx=2)
        if HELP_TEXTS:
            add_help(ocr_btn, **HELP_TEXTS.get("ocr_settings_button",
                                               {"title": "OCR Settings", "description": "Configure text recognition"}))

        row2 = ttk.Frame(btn_frame)
        row2.pack(fill=tk.X, pady=2)

        audio_btn = ttk.Button(row2, text="Audio Settings", command=self.open_audio_settings, width=18)
        audio_btn.pack(side=tk.LEFT, padx=2)
        if HELP_TEXTS:
            add_help(audio_btn, **HELP_TEXTS.get("audio_settings_button",
                                                 {"title": "Audio Settings", "description": "Configure transcription"}))

        cache_btn = ttk.Button(row2, text="Cache Manager", command=self.open_cache_manager, width=18)
        cache_btn.pack(side=tk.LEFT, padx=2)
        if HELP_TEXTS:
            add_help(cache_btn, **HELP_TEXTS.get("settings_cache_manager",
                                                 {"title": "Cache Manager", "description": "Manage cached data"}))

        # Updates & About Section
        about_frame = ttk.LabelFrame(settings, text="Updates & About", padding=10)
        about_frame.pack(fill=tk.X, padx=20, pady=5)

        # Version info
        version_row = ttk.Frame(about_frame)
        version_row.pack(fill=tk.X, pady=2)
        ttk.Label(version_row, text=f"{APP_DISPLAY_NAME} {get_version_string()}", font=('Arial', 10, 'bold')).pack(
            side=tk.LEFT)

        # Update checkbox
        self.check_updates_var = tk.BooleanVar(value=self.config.get("check_for_updates", True))
        update_cb = ttk.Checkbutton(
            about_frame,
            text="Check for updates on startup",
            variable=self.check_updates_var,
            command=self._save_update_preference
        )
        update_cb.pack(anchor=tk.W, pady=2)

        # Buttons row
        about_btn_row = ttk.Frame(about_frame)
        about_btn_row.pack(fill=tk.X, pady=5)

        check_updates_btn = ttk.Button(
            about_btn_row,
            text="🔄 Check for Updates",
            command=self._check_for_updates,
            width=18
        )
        check_updates_btn.pack(side=tk.LEFT, padx=2)
        if CONTEXT_HELP_AVAILABLE:
            add_help(check_updates_btn, **HELP_TEXTS.get("settings_check_for_updates", {"title": "Check for Updates",
                                                                                        "description": "Check for new versions"}))

        feature_status_btn = ttk.Button(
            about_btn_row,
            text="📋 Feature Status",
            command=self._show_system_check,
            width=18
        )
        feature_status_btn.pack(side=tk.LEFT, padx=2)
        if CONTEXT_HELP_AVAILABLE:
            add_help(feature_status_btn, **HELP_TEXTS.get("settings_feature_status", {"title": "Feature Status",
                                                                                      "description": "View feature availability"}))

        export_diag_btn = ttk.Button(
            about_btn_row,
            text="💾 Export Diagnostics",
            command=self._export_diagnostics,
            width=18
        )
        export_diag_btn.pack(side=tk.LEFT, padx=2)
        if CONTEXT_HELP_AVAILABLE:
            add_help(export_diag_btn, **HELP_TEXTS.get("settings_export_diagnostics", {"title": "Export Diagnostics",
                                                                                       "description": "Export diagnostic info"}))

        # Bottom buttons
        bottom_frame = ttk.Frame(settings)
        bottom_frame.pack(fill=tk.X, pady=10, padx=20)
        save_btn = ttk.Button(bottom_frame, text="Save All Settings",
                              command=lambda: self.save_all_settings(settings))
        save_btn.pack(side=tk.LEFT, padx=5)
        if CONTEXT_HELP_AVAILABLE:
            add_help(save_btn, **HELP_TEXTS.get("settings_save_all",
                                                {"title": "Save All Settings", "description": "Save and close"}))
        close_btn = ttk.Button(bottom_frame, text="Close", command=settings.destroy)
        close_btn.pack(side=tk.RIGHT, padx=5)
        if CONTEXT_HELP_AVAILABLE:
            add_help(close_btn,
                     **HELP_TEXTS.get("settings_close", {"title": "Close", "description": "Close without saving"}))

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

    def save_all_settings(self, settings_window):
        """Save all settings and close the window"""
        # Save provider selection
        self.config["last_provider"] = self.provider_var.get()

        # Save model selection
        provider = self.provider_var.get()
        model = self.model_var.get()
        if provider and model:
            self.config["last_model"][provider] = model

        # Save API key
        self.save_api_key_in_settings()

        # Save viewer display settings
        try:
            char_threshold = int(self.char_warning_var.get())
            if char_threshold >= 10000:  # Minimum 10K chars
                self.config['viewer_char_warning_threshold'] = char_threshold
        except (ValueError, AttributeError):
            pass  # Keep existing value if invalid

        try:
            collapse_threshold = int(self.collapse_threshold_var.get())
            if 1 <= collapse_threshold <= 50:  # Reasonable range
                self.config['viewer_collapse_threshold'] = collapse_threshold
        except (ValueError, AttributeError):
            pass  # Keep existing value if invalid

        # Save config
        save_config(self.config)

        messagebox.showinfo("Success", "All settings saved!")
        settings_window.destroy()

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
        settings.geometry("500x480")
        self.style_dialog(settings)
        ttk.Label(settings, text="Choose chunk size for processing:", font=('Arial', 12, 'bold')).pack(pady=10)
        current = self.config.get("chunk_size", "medium")
        selected = tk.StringVar(value=current)
        for key, info in CHUNK_SIZES.items():
            frame = ttk.LabelFrame(settings, text=info["label"], padding=10)
            frame.pack(fill=tk.X, padx=20, pady=5)
            rb = ttk.Radiobutton(frame, text=f"{info['description']}\nQuality: {info['quality']}", variable=selected,
                                 value=key)
            rb.pack(anchor=tk.W)

        def save_and_close():
            self.config["chunk_size"] = selected.get()
            save_config(self.config)
            messagebox.showinfo("Success", "Chunk size setting saved")
            settings.destroy()

        ttk.Button(settings, text="Save & Close", command=save_and_close).pack(pady=20)

    def open_ocr_settings(self):
        available, error_msg, tesseract_path = get_ocr().check_ocr_availability()

        settings = tk.Toplevel(self.root)
        settings.title("OCR Settings")
        settings.geometry("550x500")
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
        
        ttk.Label(mode_frame, text="    (In 'Local first' mode, prompt for Cloud AI below this threshold)",
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
        
        # === Bottom buttons (fixed, not scrollable) ===
        def save_settings():
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
        
        btn_frame = ttk.Frame(settings, padding=5)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Button(btn_frame, text="Save Settings", command=save_settings).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Test local OCR", command=self.test_ocr_setup).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Close", command=settings.destroy).pack(side=tk.RIGHT, padx=5)
        
        # Cleanup on close
        def on_closing():
            try:
                canvas.unbind("<MouseWheel>")
                content_frame.unbind("<MouseWheel>")
            except:
                pass
            settings.destroy()
        settings.protocol("WM_DELETE_WINDOW", on_closing)

    def open_audio_settings(self):
        settings = tk.Toplevel(self.root)
        settings.title("Audio Transcription Settings")
        settings.geometry("650x550")  # Reduced from 600x700
        self.style_dialog(settings)

        # Make window resizable so users can adjust if needed
        settings.resizable(True, True)

        ttk.Label(settings, text="🎤 Audio Transcription Settings", font=('Arial', 14, 'bold')).pack(
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

        # Cleanup bindings when window is closed
        def on_closing():
            try:
                canvas.unbind("<MouseWheel>")
                scrollable_frame.unbind("<MouseWheel>")
            except:
                pass
            settings.destroy()

        settings.protocol("WM_DELETE_WINDOW", on_closing)

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
        ttk.Checkbutton(diarization_frame, text="Enable Speaker Diarization (AssemblyAI only)",
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

        def save_settings():
            self.config["transcription_engine"] = engine_var.get()
            lang_selection = lang_var.get()
            lang_code = lang_selection.split(' - ')[0] if ' - ' in lang_selection else ""
            self.config["transcription_language"] = lang_code
            self.config["speaker_diarization"] = diarization_var.get()
            self.config["enable_vad"] = vad_var.get()  # 🆕 NEW: Save VAD setting
            self.config["timestamp_interval"] = timestamp_var.get()  # 🆕 NEW: Save timestamp interval
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

        # Button frame at the bottom - fixed position
        btn_frame = ttk.Frame(settings)
        btn_frame.pack(fill=tk.X, pady=5, padx=10, side=tk.BOTTOM)

        ttk.Button(btn_frame, text="Save Settings", command=save_settings).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Close", command=settings.destroy).pack(side=tk.RIGHT, padx=5)

        # Cleanup mousewheel binding when window closes
        def on_close():
            canvas.unbind_all("<MouseWheel>")
            settings.destroy()

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

    def open_cache_manager(self):
        cache_window = tk.Toplevel(self.root)
        cache_window.title("Cache Manager")
        cache_window.geometry("500x400")
        self.style_dialog(cache_window)

        ttk.Label(cache_window, text="🗂️ Cache Management", font=('Arial', 14, 'bold')).pack(pady=10)

        # Info frame
        info_frame = ttk.LabelFrame(cache_window, text="Cache Information", padding=10)
        info_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        cache_info_text = scrolledtext.ScrolledText(info_frame, wrap=tk.WORD, height=10, font=('Arial', 10))
        cache_info_text.pack(fill=tk.BOTH, expand=True)

        def refresh_info():
            cache_info_text.delete('1.0', tk.END)
            info = get_cache_info()

            cache_info_text.insert(tk.END, "📊 Cache Statistics\n\n")
            cache_info_text.insert(tk.END, f"OCR Cache:\n")
            cache_info_text.insert(tk.END, f"  • Files: {info['ocr_count']}\n")
            cache_info_text.insert(tk.END, f"  • Size: {format_size(info['ocr_size'])}\n\n")
            cache_info_text.insert(tk.END, f"Audio Cache:\n")
            cache_info_text.insert(tk.END, f"  • Files: {info['audio_count']}\n")
            cache_info_text.insert(tk.END, f"  • Size: {format_size(info['audio_size'])}\n\n")

            # ADD PROCESSED OUTPUTS SECTION
            cache_info_text.insert(tk.END, f"Processed Outputs:\n")
            cache_info_text.insert(tk.END, f"  • Files: {info['outputs_count']}\n")
            cache_info_text.insert(tk.END, f"  • Size: {format_size(info['outputs_size'])}\n\n")

            cache_info_text.insert(tk.END, f"Total Cache:\n")
            cache_info_text.insert(tk.END, f"  • Files: {info['total_count']}\n")
            cache_info_text.insert(tk.END, f"  • Size: {format_size(info['total_size'])}\n\n")
            cache_info_text.insert(tk.END, "ℹ️ About Cache:\n")
            cache_info_text.insert(tk.END,
                                   "Cached files speed up re-processing of documents you've already analyzed.\n")
            cache_info_text.insert(tk.END, "Clearing cache will free disk space but require re-processing files.")
            cache_info_text.config(state=tk.DISABLED)

        def clear_ocr_cache():
            if messagebox.askyesno("Confirm", "Clear OCR cache? This will require re-processing scanned PDFs."):
                success, msg = clear_cache('ocr')
                if success:
                    messagebox.showinfo("Success", msg)
                    cache_info_text.config(state=tk.NORMAL)
                    refresh_info()
                else:
                    messagebox.showerror("Error", msg)

        def clear_audio_cache():
            if messagebox.askyesno("Confirm", "Clear audio cache? This will require re-transcribing audio files."):
                success, msg = clear_cache('audio')
                if success:
                    messagebox.showinfo("Success", msg)
                    cache_info_text.config(state=tk.NORMAL)
                    refresh_info()
                else:
                    messagebox.showerror("Error", msg)

        def clear_all_cache():
            if messagebox.askyesno("Confirm", "Clear ALL cache? This will require re-processing all cached files."):
                success, msg = clear_cache('all')
                if success:
                    messagebox.showinfo("Success", msg)
                    cache_info_text.config(state=tk.NORMAL)
                    refresh_info()
                else:
                    messagebox.showerror("Error", msg)

            # Add this function with the other clear functions:
            def clear_outputs_cache():
                if messagebox.askyesno("Confirm",
                                       "Clear processed outputs cache? This will delete all saved AI outputs."):
                    success, msg = clear_cache('outputs')
                    if success:
                        messagebox.showinfo("Success", msg)
                        cache_info_text.config(state=tk.NORMAL)
                        refresh_info()
                    else:
                        messagebox.showerror("Error", msg)

            # Update the button section to include the new button:
            ttk.Button(btn_frame, text="Clear OCR Cache", command=clear_ocr_cache).pack(side=tk.LEFT, padx=5)
            ttk.Button(btn_frame, text="Clear Audio Cache", command=clear_audio_cache).pack(side=tk.LEFT, padx=5)
            ttk.Button(btn_frame, text="Clear Outputs Cache", command=clear_outputs_cache).pack(side=tk.LEFT,
                                                                                                padx=5)  # NEW!
            ttk.Button(btn_frame, text="Clear All Cache", command=clear_all_cache).pack(side=tk.LEFT, padx=5)
            ttk.Button(btn_frame, text="Refresh",
                       command=lambda: [cache_info_text.config(state=tk.NORMAL), refresh_info()]).pack(side=tk.LEFT,
                                                                                                       padx=5)
            ttk.Button(btn_frame, text="Close", command=cache_window.destroy).pack(side=tk.RIGHT, padx=5)

