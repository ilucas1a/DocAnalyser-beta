"""
local_model_manager.py - Local AI Model Manager for Ollama

Provides a user-friendly GUI for managing Ollama models:
- View installed models with sizes
- Download recommended models with one click
- System-aware recommendations aligned with Local AI Setup wizard
- Delete unused models

Uses system_detector.py for hardware detection so recommendations
are consistent across the app (Setup wizard and Manage Models agree).
"""

import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import threading
import webbrowser
import platform
import re
import logging


# =============================================================================
# SYSTEM DETECTION - delegates to system_detector.py for consistency
# =============================================================================

def _get_system_info_from_detector():
    """
    Get system info from system_detector.py (shared with Local AI Setup wizard).
    Returns (profile, system_info, recommendations) or None on failure.
    """
    try:
        from system_detector import get_system_info, get_system_profile, get_model_recommendations
        sys_info = get_system_info()
        profile = get_system_profile(sys_info)
        recommendations = get_model_recommendations(sys_info)
        return profile, sys_info, recommendations
    except ImportError:
        logging.warning("system_detector not available — using built-in detection")
        return None
    except Exception as e:
        logging.warning(f"system_detector error: {e} — using built-in detection")
        return None


def _get_system_info_fallback():
    """Fallback system detection if system_detector is unavailable."""
    ram_gb = None
    gpu_info = None

    # RAM detection
    try:
        if platform.system() == "Windows":
            import ctypes
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ('dwLength', ctypes.c_ulong),
                    ('dwMemoryLoad', ctypes.c_ulong),
                    ('ullTotalPhys', ctypes.c_ulonglong),
                    ('ullAvailPhys', ctypes.c_ulonglong),
                    ('ullTotalPageFile', ctypes.c_ulonglong),
                    ('ullAvailPageFile', ctypes.c_ulonglong),
                    ('ullTotalVirtual', ctypes.c_ulonglong),
                    ('ullAvailVirtual', ctypes.c_ulonglong),
                    ('ullAvailExtendedVirtual', ctypes.c_ulonglong)
                ]
            memoryStatus = MEMORYSTATUSEX()
            memoryStatus.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memoryStatus))
            ram_gb = memoryStatus.ullTotalPhys / (1024**3)
    except Exception:
        pass

    # GPU detection (NVIDIA only in fallback)
    try:
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=name,memory.total', '--format=csv,noheader,nounits'],
            capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split(',')
            if len(parts) == 2:
                gpu_info = (parts[0].strip(), float(parts[1].strip()) / 1024)
    except Exception:
        pass

    return ram_gb, gpu_info


def get_system_specs():
    """
    Get system specifications using system_detector when available.
    Returns: (profile, ram_gb, gpu_info, description, recommendations)
      - profile: 'basic', 'standard', 'good', 'powerful', or 'unknown'
      - ram_gb: float or None
      - gpu_info: (name, vram_gb) or None
      - description: human-readable summary
      - recommendations: dict from system_detector, or None
    """
    # Try system_detector first (shared with Local AI Setup wizard)
    result = _get_system_info_from_detector()

    if result:
        profile, sys_info, recommendations = result
        ram_gb = sys_info.get('ram_total_gb', 0)
        gpu_name = sys_info.get('gpu_name')
        gpu_vram = sys_info.get('gpu_vram_gb')
        gpu_info = (gpu_name, gpu_vram) if gpu_name else None

        desc = f"{ram_gb:.0f}GB RAM"
        if gpu_info:
            desc += f" · {gpu_name} ({gpu_vram:.0f}GB VRAM)"

        return profile, ram_gb, gpu_info, desc, recommendations

    # Fallback: built-in detection
    ram_gb, gpu_info = _get_system_info_fallback()

    if ram_gb is None:
        return 'unknown', None, gpu_info, "Could not detect system specs", None

    # Map RAM to profile (aligned with system_detector thresholds)
    if ram_gb < 8:
        profile = 'basic'
    elif ram_gb < 16:
        profile = 'standard'  # system_detector: 16GB+ for standard, but 8-16 can run 7B models
    elif ram_gb < 32:
        profile = 'good'
    else:
        profile = 'powerful'

    desc = f"{ram_gb:.0f}GB RAM"
    if gpu_info:
        desc += f" · {gpu_info[0]} ({gpu_info[1]:.0f}GB VRAM)"

    return profile, ram_gb, gpu_info, desc, None


# =============================================================================
# UNIFIED MODEL CATALOG
# =============================================================================
# This is the single source of truth for all model recommendations in the app.
# Both the Manage Models dialog and the Local AI Setup wizard should ultimately
# draw from this catalog (Setup wizard currently uses system_detector.py).
#
# Format: (ollama_id, display_name, description, size_str, min_ram_gb, category, profiles)
#   - profiles: list of system_detector profiles that recommend this model
#     'basic', 'standard', 'good', 'powerful'
#     A model appears as "recommended" if the user's profile is in this list
#     or is higher than the highest profile in the list.

UNIFIED_MODELS = [
    # ── Lightweight (suitable for basic systems, < 8GB RAM) ──
    ("tinyllama",       "TinyLlama (1.1B)",       "Smallest option — very limited, last resort.",                "0.6 GB",   4,  "lightweight", ["basic"]),
    ("gemma:2b",        "Gemma 2B",               "Google's compact model. Basic tasks only.",                   "1.5 GB",   4,  "lightweight", ["basic"]),
    ("llama3.2:1b",     "Llama 3.2 (1B)",         "Very fast, minimal resources. Simple tasks.",                 "1.3 GB",   4,  "lightweight", ["basic"]),
    ("qwen2.5:1.5b",    "Qwen 2.5 (1.5B)",       "Fast multilingual model.",                                   "1.0 GB",   4,  "lightweight", ["basic"]),
    ("gemma2:2b",       "Gemma 2 (2B)",           "Google's newer compact model.",                              "1.6 GB",   4,  "lightweight", ["basic"]),
    ("phi3:mini",       "Phi-3 Mini (3.8B)",      "Microsoft's efficient small model. Best for limited HW.",    "2.3 GB",   6,  "lightweight", ["basic"]),

    # ── Balanced (standard systems, 8-16GB RAM) ──
    ("llama3.2:3b",     "Llama 3.2 (3B)",         "Great balance of speed and quality.",                        "2.0 GB",   6,  "balanced",    ["basic", "standard"]),
    ("qwen2.5:3b",      "Qwen 2.5 (3B)",         "Good multilingual support.",                                 "1.9 GB",   6,  "balanced",    ["standard"]),
    ("mistral:7b",      "Mistral 7B",             "Excellent quality, very popular. Recommended.",              "4.1 GB",   8,  "balanced",    ["standard"]),
    ("llama3.1:8b",     "Llama 3.1 (8B)",         "Meta's workhorse. Very capable all-rounder.",                "4.7 GB",  10,  "balanced",    ["standard", "good"]),
    ("qwen2.5:7b",      "Qwen 2.5 (7B)",         "Strong reasoning and multilingual.",                         "4.4 GB",  10,  "balanced",    ["standard"]),
    ("gemma2:9b",       "Gemma 2 (9B)",           "Google's best mid-size model.",                              "5.5 GB",  12,  "balanced",    ["standard"]),

    # ── Capable (good systems, 16-32GB RAM) ──
    ("mistral-nemo",    "Mistral Nemo (12B)",     "Larger context window, more nuanced output.",                "7.1 GB",  14,  "capable",     ["good"]),
    ("qwen2.5:14b",     "Qwen 2.5 (14B)",        "High-quality reasoning.",                                   "8.5 GB",  16,  "capable",     ["good"]),
    ("codellama:13b",   "Code Llama (13B)",       "Meta's coding specialist — larger variant.",                 "7.4 GB",  16,  "specialized", ["good"]),

    # ── Powerful (high-end systems, 32GB+ RAM) ──
    ("qwen2.5:32b",     "Qwen 2.5 (32B)",        "Excellent for complex tasks.",                               "18 GB",   24,  "powerful",    ["powerful"]),
    ("mixtral:8x7b",    "Mixtral 8x7B",           "Mixture of experts. Very capable.",                         "26 GB",   32,  "powerful",    ["powerful"]),
    ("llama3.1:70b",    "Llama 3.1 (70B)",        "Near GPT-4 quality. Best local experience.",                "40 GB",   48,  "powerful",    ["powerful"]),

    # ── Specialized ──
    ("deepseek-coder:6.7b", "DeepSeek Coder (6.7B)", "Optimized for programming tasks.",                      "3.8 GB",   8,  "specialized", ["standard"]),
    ("codellama:7b",    "Code Llama (7B)",        "Meta's coding specialist.",                                  "3.8 GB",   8,  "specialized", ["standard"]),
    ("llava:7b",        "LLaVA (7B)",             "Vision model — can analyse images.",                         "4.5 GB",  10,  "specialized", ["standard", "good"]),
    ("llava:13b",       "LLaVA (13B)",            "Better vision model.",                                       "8.0 GB",  16,  "specialized", ["good"]),
    ("deepseek-r1:7b",  "DeepSeek R1 (7B)",       "Strong reasoning model.",                                   "4.7 GB",  10,  "specialized", ["standard", "good"]),
]

# Profile hierarchy for comparison
PROFILE_ORDER = {'basic': 0, 'standard': 1, 'good': 2, 'powerful': 3, 'unknown': 1}


def classify_models(profile, ram_gb):
    """
    Classify models into recommended / compatible / too_large based on system profile.
    This aligns with system_detector's recommendations so both dialogs agree.

    Returns: (recommended, compatible, too_large) — each a list of model tuples.
    """
    if ram_gb is None:
        ram_gb = 8  # Assume basic if unknown

    user_level = PROFILE_ORDER.get(profile, 1)
    recommended = []
    compatible = []
    too_large = []

    for model in UNIFIED_MODELS:
        ollama_id, display_name, desc, size_str, min_ram, category, profiles = model

        # A model is "recommended" if the user's profile matches or exceeds
        # the profiles that recommend it
        model_min_level = min(PROFILE_ORDER.get(p, 99) for p in profiles)
        model_max_level = max(PROFILE_ORDER.get(p, 0) for p in profiles)

        if user_level >= model_min_level and min_ram <= ram_gb * 0.85:
            recommended.append(model)
        elif min_ram <= ram_gb:
            # Will technically fit but not in the recommended set
            compatible.append(model)
        else:
            too_large.append(model)

    return recommended, compatible, too_large


# =============================================================================
# OLLAMA UTILITIES
# =============================================================================

def is_ollama_installed():
    """Check if Ollama is installed and accessible."""
    try:
        result = subprocess.run(
            ["ollama", "--version"],
            capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def is_ollama_running():
    """Check if Ollama server is running."""
    try:
        import urllib.request
        req = urllib.request.Request("http://localhost:11434/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=3) as response:
            return response.status == 200
    except Exception:
        return False


def get_installed_models():
    """
    Get list of installed Ollama models.
    Returns list of (name, size_string) tuples.
    """
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        )
        if result.returncode != 0:
            return []

        models = []
        lines = result.stdout.strip().split('\n')

        for line in lines[1:]:  # Skip header
            if not line.strip():
                continue
            parts = line.split()
            if not parts:
                continue

            name = parts[0]
            size = ""

            # Look for size pattern: number followed by GB or MB
            for i, part in enumerate(parts):
                if part in ('GB', 'MB') and i > 0:
                    size = f"{parts[i-1]} {part}"
                    break
                elif re.match(r'^\d+\.?\d*[GM]B$', part):
                    size = part
                    break

            models.append((name, size))

        return models
    except Exception as e:
        logging.error(f"Error getting installed models: {e}")
        return []


def delete_model(model_name):
    """Delete an Ollama model. Returns True on success."""
    try:
        result = subprocess.run(
            ["ollama", "rm", model_name],
            capture_output=True, text=True, timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        )
        return result.returncode == 0
    except Exception as e:
        logging.error(f"Error deleting model: {e}")
        return False


# =============================================================================
# DIALOG CLASS
# =============================================================================

class LocalModelManagerDialog:
    """Dialog for managing local Ollama models with system-aware recommendations."""

    def __init__(self, parent, on_models_changed=None):
        self.parent = parent
        self.on_models_changed = on_models_changed
        self.download_process = None
        self.is_downloading = False

        # Get system info (uses system_detector when available)
        self.profile, self.ram_gb, self.gpu_info, self.system_desc, self.recommendations = get_system_specs()
        self.recommended, self.compatible, self.too_large = classify_models(self.profile, self.ram_gb)

        # Create dialog window
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Local AI Model Manager")
        self.dialog.geometry("750x620")
        self.dialog.minsize(650, 550)
        self.dialog.transient(parent)
        self.dialog.grab_set()

        # Centre on parent within screen bounds
        self.dialog.update_idletasks()
        dw, dh = 750, 620
        x = parent.winfo_x() + (parent.winfo_width() - dw) // 2
        y = parent.winfo_y() + (parent.winfo_height() - dh) // 2
        sw = self.dialog.winfo_screenwidth()
        sh = self.dialog.winfo_screenheight()
        margin = 50
        x = max(margin, min(x, sw - dw - margin))
        y = max(margin, min(y, sh - dh - margin))
        self.dialog.geometry(f"{dw}x{dh}+{x}+{y}")

        self._create_ui()
        self._refresh_installed_models()

        self.dialog.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # UI CONSTRUCTION
    # ------------------------------------------------------------------

    def _create_ui(self):
        """Create the dialog UI."""
        main_frame = ttk.Frame(self.dialog, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Check Ollama status first
        if not is_ollama_installed():
            self._show_ollama_not_installed(main_frame)
            return
        if not is_ollama_running():
            self._show_ollama_not_running(main_frame)
            return

        # === System Info Banner ===
        self._create_system_banner(main_frame)

        # === Installed Models Section ===
        installed_frame = ttk.LabelFrame(main_frame, text="Installed Models", padding="10")
        installed_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        list_frame = ttk.Frame(installed_frame)
        list_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("Model", "Size")
        self.installed_tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=5)
        self.installed_tree.heading("Model", text="Model Name")
        self.installed_tree.heading("Size", text="Size")
        self.installed_tree.column("Model", width=400)
        self.installed_tree.column("Size", width=100)

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.installed_tree.yview)
        self.installed_tree.configure(yscrollcommand=scrollbar.set)
        self.installed_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        btn_frame = ttk.Frame(installed_frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))

        self.refresh_btn = ttk.Button(btn_frame, text="🔄 Refresh", command=self._refresh_installed_models)
        self.refresh_btn.pack(side=tk.LEFT, padx=(0, 5))

        self.delete_btn = ttk.Button(btn_frame, text="🗑️ Delete Selected", command=self._delete_selected)
        self.delete_btn.pack(side=tk.LEFT)

        # === Download New Models Section ===
        download_frame = ttk.LabelFrame(main_frame, text="Download New Models", padding="10")
        download_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # Filter and model selection row
        select_frame = ttk.Frame(download_frame)
        select_frame.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(select_frame, text="Show:").pack(side=tk.LEFT, padx=(0, 5))

        self.filter_var = tk.StringVar(value="recommended")
        filter_combo = ttk.Combobox(
            select_frame,
            textvariable=self.filter_var,
            state="readonly",
            width=20,
            values=["recommended", "all compatible", "all models"]
        )
        filter_combo.pack(side=tk.LEFT, padx=(0, 15))
        filter_combo.bind("<<ComboboxSelected>>", self._on_filter_changed)

        ttk.Label(select_frame, text="Model:").pack(side=tk.LEFT, padx=(0, 5))

        self.model_var = tk.StringVar()
        self.model_combo = ttk.Combobox(
            select_frame,
            textvariable=self.model_var,
            state="readonly",
            width=35
        )
        self.model_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        self.model_combo.bind("<<ComboboxSelected>>", self._on_model_selected)

        self.download_btn = ttk.Button(select_frame, text="⬇️ Download", command=self._start_download)
        self.download_btn.pack(side=tk.LEFT)

        # Model description
        self.desc_label = ttk.Label(download_frame, text="", wraplength=700)
        self.desc_label.pack(fill=tk.X, pady=(5, 5))

        # Warning label for large models
        self.warning_label = ttk.Label(download_frame, text="", foreground="orange", wraplength=700)
        self.warning_label.pack(fill=tk.X)

        # Progress section
        progress_frame = ttk.Frame(download_frame)
        progress_frame.pack(fill=tk.X, pady=(5, 0))

        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X, pady=(0, 5))

        self.status_label = ttk.Label(progress_frame, text="")
        self.status_label.pack(fill=tk.X)

        # Populate initial dropdown
        self._populate_model_dropdown()

        # === Bottom buttons ===
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.pack(fill=tk.X)

        ttk.Button(bottom_frame, text="Close", command=self._on_close).pack(side=tk.RIGHT)

        help_label = ttk.Label(
            bottom_frame,
            text="Browse all models at ollama.com/library",
            foreground="blue",
            cursor="hand2"
        )
        help_label.pack(side=tk.LEFT)
        help_label.bind("<Button-1>", lambda e: webbrowser.open("https://ollama.com/library"))

    def _create_system_banner(self, parent):
        """Create the system info banner."""
        banner_frame = ttk.Frame(parent)
        banner_frame.pack(fill=tk.X, pady=(0, 10))

        if self.ram_gb:
            # Profile-based display
            profile_display = {
                'basic':    ("⚠️", "Limited — lightweight models only"),
                'standard': ("💻", "Good — most models will run well"),
                'good':     ("✅", "Strong — large models supported"),
                'powerful': ("🚀", "Excellent — all models supported"),
                'unknown':  ("❓", "Unknown capabilities")
            }
            icon, tier_desc = profile_display.get(self.profile, ("❓", "Unknown"))

            system_text = f"{icon} Your System: {self.system_desc}"

            ttk.Label(
                banner_frame,
                text=system_text,
                font=('Arial', 10, 'bold')
            ).pack(anchor=tk.W)

            rec_count = len(self.recommended)
            compat_count = len(self.compatible)

            if rec_count > 0:
                rec_text = f"✓ {rec_count} models recommended for your system"
                if compat_count > 0:
                    rec_text += f", {compat_count} more compatible"
            else:
                rec_text = "⚠️ Limited options — consider models under 4GB"

            ttk.Label(
                banner_frame,
                text=rec_text,
                font=('Arial', 9),
                foreground='#666666'
            ).pack(anchor=tk.W)
        else:
            ttk.Label(
                banner_frame,
                text="❓ Could not detect system specifications",
                font=('Arial', 9),
                foreground='#666666'
            ).pack(anchor=tk.W)

    # ------------------------------------------------------------------
    # MODEL DROPDOWN
    # ------------------------------------------------------------------

    def _populate_model_dropdown(self):
        """Populate the model dropdown based on filter selection."""
        filter_val = self.filter_var.get()

        if filter_val == "recommended":
            models = self.recommended
        elif filter_val == "all compatible":
            models = self.recommended + self.compatible
        else:  # all models
            models = list(UNIFIED_MODELS)

        if not models:
            # Fallback to all if no recommendations
            models = list(UNIFIED_MODELS)

        # Get currently installed model names to mark them
        installed = get_installed_models()
        installed_names = {m[0] for m in installed}

        # Build display list
        display_names = []
        self.current_models = []

        for model in models:
            ollama_id, display_name, desc, size_str, min_ram, category, profiles = model

            # Skip if already installed
            if ollama_id in installed_names:
                continue

            # Indicator
            if model in self.recommended:
                indicator = "✓"
            elif model in self.compatible:
                indicator = "~"
            else:
                indicator = "⚠️"

            display = f"{indicator} {display_name} ({size_str})"
            display_names.append(display)
            self.current_models.append(model)

        if not display_names:
            display_names = ["(All recommended models are already installed)"]
            self.current_models = []

        self.model_combo['values'] = display_names
        if display_names:
            self.model_combo.current(0)
            self._on_model_selected(None)

    def _on_filter_changed(self, event):
        """Handle filter dropdown change."""
        self._populate_model_dropdown()

    def _on_model_selected(self, event):
        """Handle model selection — show description and RAM warnings."""
        idx = self.model_combo.current()
        if idx < 0 or idx >= len(self.current_models):
            self.desc_label.config(text="")
            self.warning_label.config(text="")
            return

        model = self.current_models[idx]
        ollama_id, display_name, desc, size_str, min_ram, category, profiles = model

        self.desc_label.config(text=f"{desc}\nDownload size: ~{size_str} · Category: {category.title()}")

        # RAM warning
        if self.ram_gb and min_ram > self.ram_gb * 0.85:
            if min_ram > self.ram_gb:
                self.warning_label.config(
                    text=f"⚠️ This model needs ~{min_ram}GB RAM. Your system has {self.ram_gb:.0f}GB. May not run or be very slow.",
                    foreground="red"
                )
            else:
                self.warning_label.config(
                    text=f"⚠️ This model needs ~{min_ram}GB RAM. Should work but may be slow.",
                    foreground="orange"
                )
        else:
            self.warning_label.config(text="")

    # ------------------------------------------------------------------
    # INSTALLED MODELS
    # ------------------------------------------------------------------

    def _refresh_installed_models(self):
        """Refresh the installed models list with visual feedback."""
        # Show "refreshing" state
        self.refresh_btn.config(state=tk.DISABLED)
        old_text = self.refresh_btn.cget('text')

        for item in self.installed_tree.get_children():
            self.installed_tree.delete(item)

        models = get_installed_models()

        if not models:
            self.installed_tree.insert("", tk.END, values=("No models installed", ""))
            self.status_label.config(text="No Ollama models found. Download one below.")
        else:
            for name, size in models:
                self.installed_tree.insert("", tk.END, values=(name, size))
            self.status_label.config(text=f"✓ {len(models)} model(s) installed")

        # Also refresh the download dropdown (hide already-installed models)
        self._populate_model_dropdown()

        # Brief visual feedback then restore
        self.refresh_btn.config(text="✓ Refreshed")
        self.dialog.after(1500, lambda: self.refresh_btn.config(text=old_text, state=tk.NORMAL))

    def _delete_selected(self):
        """Delete the selected installed model."""
        selection = self.installed_tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a model to delete.", parent=self.dialog)
            return

        item = selection[0]
        model_name = self.installed_tree.item(item)['values'][0]

        if model_name == "No models installed":
            return

        if not messagebox.askyesno(
            "Confirm Delete",
            f"Delete '{model_name}'?\n\nYou'll need to re-download if you want to use it again.",
            parent=self.dialog
        ):
            return

        self.status_label.config(text=f"Deleting {model_name}...")
        self.dialog.update()

        if delete_model(model_name):
            self.status_label.config(text=f"✅ Deleted {model_name}")
            self._refresh_installed_models()
            if self.on_models_changed:
                self.on_models_changed()
        else:
            self.status_label.config(text=f"❌ Failed to delete {model_name}")
            messagebox.showerror("Error", f"Failed to delete '{model_name}'.", parent=self.dialog)

    # ------------------------------------------------------------------
    # DOWNLOAD
    # ------------------------------------------------------------------

    def _start_download(self):
        """Start downloading the selected model."""
        if self.is_downloading:
            messagebox.showwarning("Download in Progress",
                                   "Please wait for the current download to finish.",
                                   parent=self.dialog)
            return

        idx = self.model_combo.current()
        if idx < 0 or idx >= len(self.current_models):
            return

        model = self.current_models[idx]
        ollama_id, display_name, desc, size_str, min_ram, category, profiles = model

        # Check if already installed
        installed = get_installed_models()
        installed_names = [m[0] for m in installed]
        if ollama_id in installed_names:
            messagebox.showinfo("Already Installed",
                                f"'{display_name}' is already installed.",
                                parent=self.dialog)
            return

        # Warn if model might be too large
        if self.ram_gb and min_ram > self.ram_gb:
            if not messagebox.askyesno(
                "Large Model Warning",
                f"'{display_name}' needs ~{min_ram}GB RAM but your system has {self.ram_gb:.0f}GB.\n\n"
                f"It may not run or be very slow. Download anyway?",
                parent=self.dialog
            ):
                return

        self.is_downloading = True
        self.download_btn.config(state=tk.DISABLED)
        self.progress_var.set(0)
        self.status_label.config(text=f"Downloading {display_name}... This may take several minutes.")

        thread = threading.Thread(
            target=self._download_model,
            args=(ollama_id, display_name),
            daemon=True
        )
        thread.start()

    def _download_model(self, ollama_id, display_name):
        """Download a model (runs in background thread)."""
        try:
            process = subprocess.Popen(
                ["ollama", "pull", ollama_id],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=0,  # unbuffered binary
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
            self.download_process = process

            # Read raw bytes and split on \r or \n so we catch
            # ollama's carriage-return progress updates in real time
            buf = b''
            while True:
                chunk = process.stdout.read(256)
                if not chunk:
                    break
                buf += chunk

                # Split on \r or \n
                while b'\r' in buf or b'\n' in buf:
                    r_pos = buf.find(b'\r')
                    n_pos = buf.find(b'\n')
                    if r_pos == -1:
                        r_pos = len(buf)
                    if n_pos == -1:
                        n_pos = len(buf)
                    pos = min(r_pos, n_pos)

                    line_bytes = buf[:pos]
                    if pos < len(buf) - 1 and buf[pos:pos+2] == b'\r\n':
                        buf = buf[pos+2:]
                    else:
                        buf = buf[pos+1:]

                    line = line_bytes.decode('utf-8', errors='replace').strip()
                    if not line:
                        continue

                    # Try to extract percentage
                    match = re.search(r'(\d+)%', line)
                    if match:
                        pct = int(match.group(1))
                        self.dialog.after(0, lambda p=pct: self.progress_var.set(p))

                    # Always update status with the latest line
                    self.dialog.after(0, lambda l=line: self.status_label.config(text=l[:80]))

            process.wait()

            if process.returncode == 0:
                self.dialog.after(0, self._download_complete_success, display_name)
            else:
                self.dialog.after(0, self._download_complete_error, display_name)

        except Exception as e:
            logging.error(f"Download error: {e}")
            self.dialog.after(0, self._download_complete_error, display_name)

    def _download_complete_success(self, display_name):
        """Handle successful download."""
        self.is_downloading = False
        self.download_btn.config(state=tk.NORMAL)
        self.progress_var.set(100)
        self.status_label.config(text=f"✅ Downloaded {display_name} successfully!")
        self._refresh_installed_models()
        if self.on_models_changed:
            self.on_models_changed()

    def _download_complete_error(self, display_name):
        """Handle download error."""
        self.is_downloading = False
        self.download_btn.config(state=tk.NORMAL)
        self.progress_var.set(0)
        self.status_label.config(text=f"❌ Failed to download {display_name}")
        messagebox.showerror("Download Failed",
                             f"Failed to download '{display_name}'.\n\n"
                             "Check your internet connection and try again.",
                             parent=self.dialog)

    # ------------------------------------------------------------------
    # OLLAMA STATUS SCREENS
    # ------------------------------------------------------------------

    def _show_ollama_not_installed(self, parent):
        """Show message when Ollama is not installed."""
        frame = ttk.Frame(parent)
        frame.pack(expand=True)

        ttk.Label(frame, text="⚠️ Ollama Not Installed", font=("", 14, "bold")).pack(pady=(0, 10))
        ttk.Label(frame, text="Ollama is required to run local AI models.\n\nTo install:",
                  wraplength=500).pack(pady=(0, 10))
        ttk.Label(frame, text="1. Visit ollama.com/download\n2. Download and run the installer\n3. Restart DocAnalyser",
                  justify=tk.LEFT).pack(pady=(0, 20))

        link = ttk.Label(frame, text="Click here to open ollama.com/download",
                         foreground="blue", cursor="hand2")
        link.pack()
        link.bind("<Button-1>", lambda e: webbrowser.open("https://ollama.com/download"))

        ttk.Button(frame, text="Close", command=self.dialog.destroy).pack(pady=(20, 0))

    def _show_ollama_not_running(self, parent):
        """Show message when Ollama server is not running."""
        frame = ttk.Frame(parent)
        frame.pack(expand=True)

        ttk.Label(frame, text="⚠️ Ollama Server Not Running", font=("", 14, "bold")).pack(pady=(0, 10))
        ttk.Label(frame, text="Ollama is installed but the server isn't running.\n\nTo start:",
                  wraplength=500).pack(pady=(0, 10))
        ttk.Label(frame,
                  text="• Windows: Look for Ollama in system tray, or run 'ollama serve'\n"
                       "• Mac: Click Ollama in Applications\n"
                       "• Linux: Run 'ollama serve' in terminal",
                  justify=tk.LEFT, wraplength=500).pack(pady=(0, 20))

        btn_frame = ttk.Frame(frame)
        btn_frame.pack()
        ttk.Button(btn_frame, text="🔄 Retry", command=self._retry_connection).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Close", command=self.dialog.destroy).pack(side=tk.LEFT, padx=5)

    def _retry_connection(self):
        """Retry connection to Ollama."""
        for widget in self.dialog.winfo_children():
            widget.destroy()
        self._create_ui()
        self._refresh_installed_models()

    # ------------------------------------------------------------------
    # CLOSE
    # ------------------------------------------------------------------

    def _on_close(self):
        """Handle dialog close."""
        if self.is_downloading:
            if not messagebox.askyesno(
                "Download in Progress",
                "A download is in progress. Cancel it and close?",
                parent=self.dialog
            ):
                return
            if self.download_process:
                try:
                    self.download_process.terminate()
                except Exception:
                    pass

        self.dialog.destroy()


# =============================================================================
# PUBLIC ENTRY POINT
# =============================================================================

def show_local_model_manager(parent, on_models_changed=None):
    """Show the Local Model Manager dialog."""
    LocalModelManagerDialog(parent, on_models_changed)
