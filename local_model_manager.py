"""
local_model_manager.py - Local AI Model Manager for Ollama

Provides a user-friendly GUI for managing Ollama models:
- View installed models
- Download recommended models with one click
- Delete unused models
- System-aware recommendations based on RAM/GPU
"""

import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import threading
import webbrowser
import platform


# =============================================================================
# SYSTEM DETECTION
# =============================================================================

def get_system_ram_gb():
    """Get total system RAM in GB."""
    try:
        if platform.system() == "Windows":
            import ctypes
            kernel32 = ctypes.windll.kernel32
            
            # Use MEMORYSTATUSEX for systems with >4GB RAM
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
            kernel32.GlobalMemoryStatusEx(ctypes.byref(memoryStatus))
            return memoryStatus.ullTotalPhys / (1024**3)
        else:
            # Linux/Mac
            if platform.system() == "Darwin":  # macOS
                result = subprocess.run(['sysctl', '-n', 'hw.memsize'], 
                                       capture_output=True, text=True)
                return int(result.stdout.strip()) / (1024**3)
            else:  # Linux
                with open('/proc/meminfo', 'r') as f:
                    for line in f:
                        if line.startswith('MemTotal:'):
                            return int(line.split()[1]) / (1024**2)
    except:
        pass
    return None


def get_nvidia_gpu_info():
    """Get NVIDIA GPU info if available. Returns (name, vram_gb) or None."""
    try:
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=name,memory.total', '--format=csv,noheader,nounits'],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        )
        if result.returncode == 0:
            line = result.stdout.strip().split('\n')[0]
            parts = line.split(', ')
            if len(parts) == 2:
                name = parts[0].strip()
                vram_mb = int(parts[1].strip())
                return (name, vram_mb / 1024)
    except:
        pass
    return None


def get_system_tier():
    """
    Determine system capability tier based on RAM and GPU.
    Returns: (tier, ram_gb, gpu_info, description)
    
    Tiers:
    - 'minimal': < 8GB RAM - only tiny models
    - 'basic': 8-15GB RAM - small models
    - 'standard': 16-31GB RAM - medium models  
    - 'high': 32-63GB RAM - large models
    - 'extreme': 64GB+ RAM - very large models
    """
    ram_gb = get_system_ram_gb()
    gpu_info = get_nvidia_gpu_info()
    
    if ram_gb is None:
        return ('unknown', None, gpu_info, "Could not detect system RAM")
    
    # Determine tier based on RAM
    if ram_gb < 8:
        tier = 'minimal'
        desc = f"{ram_gb:.0f}GB RAM - Lightweight models only"
    elif ram_gb < 16:
        tier = 'basic'
        desc = f"{ram_gb:.0f}GB RAM - Small to medium models"
    elif ram_gb < 32:
        tier = 'standard'
        desc = f"{ram_gb:.0f}GB RAM - Most models will run well"
    elif ram_gb < 64:
        tier = 'high'
        desc = f"{ram_gb:.0f}GB RAM - Large models supported"
    else:
        tier = 'extreme'
        desc = f"{ram_gb:.0f}GB RAM - All models supported"
    
    # Add GPU info if available
    if gpu_info:
        gpu_name, vram = gpu_info
        desc += f"\n{gpu_name} ({vram:.0f}GB VRAM) - GPU acceleration available"
    
    return (tier, ram_gb, gpu_info, desc)


# =============================================================================
# MODEL DEFINITIONS WITH REQUIREMENTS
# =============================================================================

# Format: (model_name, display_name, description, size_str, min_ram_gb, category)
# Categories: 'lightweight', 'balanced', 'powerful', 'specialized'
RECOMMENDED_MODELS = [
    # Lightweight (< 8GB RAM)
    ("llama3.2:1b", "Llama 3.2 (1B)", "Very fast, minimal resources. Good for simple tasks.", "1.3 GB", 4, "lightweight"),
    ("gemma2:2b", "Gemma 2 (2B)", "Google's compact model. Quick responses.", "1.6 GB", 4, "lightweight"),
    ("qwen2.5:1.5b", "Qwen 2.5 (1.5B)", "Fast multilingual model.", "1.0 GB", 4, "lightweight"),
    ("phi3:mini", "Phi-3 Mini (3.8B)", "Microsoft's efficient small model.", "2.3 GB", 6, "lightweight"),
    
    # Balanced (8-16GB RAM)
    ("llama3.2:3b", "Llama 3.2 (3B)", "Great balance of speed and quality.", "2.0 GB", 6, "balanced"),
    ("qwen2.5:3b", "Qwen 2.5 (3B)", "Strong multilingual, good quality.", "1.9 GB", 6, "balanced"),
    ("mistral:7b", "Mistral (7B)", "Excellent quality, very popular.", "4.1 GB", 8, "balanced"),
    ("llama3.1:8b", "Llama 3.1 (8B)", "Meta's workhorse model. Very capable.", "4.7 GB", 10, "balanced"),
    ("gemma2:9b", "Gemma 2 (9B)", "Google's best mid-size model.", "5.5 GB", 12, "balanced"),
    ("qwen2.5:7b", "Qwen 2.5 (7B)", "Strong reasoning and multilingual.", "4.4 GB", 10, "balanced"),
    
    # Powerful (16-32GB RAM)
    ("llama3.1:70b", "Llama 3.1 (70B)", "Top quality, needs significant RAM.", "40 GB", 48, "powerful"),
    ("qwen2.5:32b", "Qwen 2.5 (32B)", "Excellent for complex tasks.", "18 GB", 24, "powerful"),
    ("mixtral:8x7b", "Mixtral 8x7B", "Mixture of experts. Very capable.", "26 GB", 32, "powerful"),
    
    # Specialized
    ("deepseek-coder:6.7b", "DeepSeek Coder (6.7B)", "Optimized for programming tasks.", "3.8 GB", 8, "specialized"),
    ("codellama:7b", "Code Llama (7B)", "Meta's coding specialist.", "3.8 GB", 8, "specialized"),
    ("llava:7b", "LLaVA (7B)", "Vision model - analyzes images.", "4.5 GB", 10, "specialized"),
    ("llava:13b", "LLaVA (13B)", "Better vision model.", "8.0 GB", 16, "specialized"),
]


def get_recommended_models(tier, ram_gb):
    """Get models recommended for the system tier."""
    if ram_gb is None:
        ram_gb = 8  # Assume basic if unknown
    
    recommended = []
    compatible = []
    too_large = []
    
    for model in RECOMMENDED_MODELS:
        model_name, display_name, desc, size, min_ram, category = model
        
        # Add recommendation status
        if min_ram <= ram_gb * 0.6:  # Comfortable margin
            recommended.append(model)
        elif min_ram <= ram_gb * 0.85:  # Will work but tight
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
            capture_output=True,
            text=True,
            timeout=5,
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
    except:
        return False


def get_installed_models():
    """Get list of installed Ollama models."""
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        )
        if result.returncode != 0:
            return []
        
        models = []
        lines = result.stdout.strip().split('\n')
        
        for line in lines[1:]:  # Skip header
            if line.strip():
                parts = line.split()
                if parts:
                    name = parts[0]
                    size = ""
                    # Look for size pattern: number followed by GB or MB
                    for i, part in enumerate(parts):
                        if part in ('GB', 'MB') and i > 0:
                            # Previous part should be the number
                            size = f"{parts[i-1]} {part}"
                            break
                        elif 'GB' in part or 'MB' in part:
                            # Size might be combined like "4.7GB"
                            size = part
                            break
                    models.append((name, size))
        
        return models
    except Exception as e:
        print(f"Error getting installed models: {e}")
        return []


def delete_model(model_name):
    """Delete an Ollama model."""
    try:
        result = subprocess.run(
            ["ollama", "rm", model_name],
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        )
        return result.returncode == 0
    except Exception as e:
        print(f"Error deleting model: {e}")
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
        
        # Get system info
        self.tier, self.ram_gb, self.gpu_info, self.system_desc = get_system_tier()
        self.recommended, self.compatible, self.too_large = get_recommended_models(self.tier, self.ram_gb)
        
        # Create dialog window
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Local AI Model Manager")
        self.dialog.geometry("750x620")
        self.dialog.minsize(650, 550)
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        # Center on parent, but ensure dialog stays within screen bounds
        self.dialog.update_idletasks()
        dialog_width = 750
        dialog_height = 620
        
        # Calculate centered position
        x = parent.winfo_x() + (parent.winfo_width() - dialog_width) // 2
        y = parent.winfo_y() + (parent.winfo_height() - dialog_height) // 2
        
        # Get screen dimensions
        screen_width = self.dialog.winfo_screenwidth()
        screen_height = self.dialog.winfo_screenheight()
        
        # Ensure dialog stays within screen bounds (with some margin)
        margin = 50
        x = max(margin, min(x, screen_width - dialog_width - margin))
        y = max(margin, min(y, screen_height - dialog_height - margin))
        
        self.dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")
        
        self._create_ui()
        self._refresh_installed_models()
        
        self.dialog.protocol("WM_DELETE_WINDOW", self._on_close)
    
    def _create_ui(self):
        """Create the dialog UI."""
        main_frame = ttk.Frame(self.dialog, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Check Ollama status
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
        
        # Model selection with category filter
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
        """Create the system info banner with recommendations."""
        banner_frame = ttk.Frame(parent)
        banner_frame.pack(fill=tk.X, pady=(0, 10))
        
        # System info
        if self.ram_gb:
            # Determine banner color/icon based on tier
            tier_info = {
                'minimal': ("⚠️", "Limited - Only lightweight models recommended"),
                'basic': ("💻", "Basic - Small models work well"),
                'standard': ("✅", "Good - Most models will run smoothly"),
                'high': ("🚀", "Powerful - Large models supported"),
                'extreme': ("🔥", "Excellent - All models supported"),
                'unknown': ("❓", "Unknown - Could not detect system specs")
            }
            icon, tier_desc = tier_info.get(self.tier, ("❓", "Unknown"))
            
            # Main system line
            ram_text = f"{self.ram_gb:.0f}GB RAM" if self.ram_gb else "RAM unknown"
            system_text = f"{icon} Your System: {ram_text}"
            
            if self.gpu_info:
                gpu_name, vram = self.gpu_info
                # Shorten GPU name
                short_gpu = gpu_name.replace("NVIDIA ", "").replace("GeForce ", "")
                system_text += f" • {short_gpu} ({vram:.0f}GB VRAM)"
            
            ttk.Label(
                banner_frame, 
                text=system_text,
                font=('Arial', 10, 'bold')
            ).pack(anchor=tk.W)
            
            # Recommendation line
            rec_count = len(self.recommended)
            compat_count = len(self.compatible)
            
            if rec_count > 0:
                rec_text = f"✓ {rec_count} models recommended for your system"
                if compat_count > 0:
                    rec_text += f", {compat_count} more compatible"
            else:
                rec_text = f"⚠️ Limited options - consider models under 4GB"
            
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
    
    def _populate_model_dropdown(self):
        """Populate the model dropdown based on filter."""
        filter_val = self.filter_var.get()
        
        if filter_val == "recommended":
            models = self.recommended
        elif filter_val == "all compatible":
            models = self.recommended + self.compatible
        else:  # all models
            models = RECOMMENDED_MODELS
        
        if not models:
            # Fallback to all if no recommendations
            models = RECOMMENDED_MODELS
        
        # Build display list
        display_names = []
        self.current_models = []
        
        for model in models:
            model_name, display_name, desc, size, min_ram, category = model
            
            # Add indicator for fit
            if model in self.recommended:
                indicator = "✓"
            elif model in self.compatible:
                indicator = "~"
            else:
                indicator = "⚠️"
            
            display = f"{indicator} {display_name} ({size})"
            display_names.append(display)
            self.current_models.append(model)
        
        self.model_combo['values'] = display_names
        if display_names:
            self.model_combo.current(0)
            self._on_model_selected(None)
    
    def _on_filter_changed(self, event):
        """Handle filter dropdown change."""
        self._populate_model_dropdown()
    
    def _on_model_selected(self, event):
        """Handle model selection."""
        idx = self.model_combo.current()
        if idx >= 0 and idx < len(self.current_models):
            model = self.current_models[idx]
            model_name, display_name, desc, size, min_ram, category = model
            
            # Show description
            self.desc_label.config(text=f"{desc}\nDownload size: {size} • Category: {category.title()}")
            
            # Show warning if model might be too large
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
    
    def _show_ollama_not_installed(self, parent):
        """Show message when Ollama is not installed."""
        frame = ttk.Frame(parent)
        frame.pack(expand=True)
        
        ttk.Label(frame, text="⚠️ Ollama Not Installed", font=("", 14, "bold")).pack(pady=(0, 10))
        
        ttk.Label(frame, text="Ollama is required to run local AI models.\n\nTo install:", wraplength=500).pack(pady=(0, 10))
        
        ttk.Label(frame, text="1. Visit ollama.com/download\n2. Download and run the installer\n3. Restart DocAnalyser", justify=tk.LEFT).pack(pady=(0, 20))
        
        link = ttk.Label(frame, text="Click here to open ollama.com/download", foreground="blue", cursor="hand2")
        link.pack()
        link.bind("<Button-1>", lambda e: webbrowser.open("https://ollama.com/download"))
        
        ttk.Button(frame, text="Close", command=self.dialog.destroy).pack(pady=(20, 0))
    
    def _show_ollama_not_running(self, parent):
        """Show message when Ollama server is not running."""
        frame = ttk.Frame(parent)
        frame.pack(expand=True)
        
        ttk.Label(frame, text="⚠️ Ollama Server Not Running", font=("", 14, "bold")).pack(pady=(0, 10))
        
        ttk.Label(frame, text="Ollama is installed but the server isn't running.\n\nTo start:", wraplength=500).pack(pady=(0, 10))
        
        ttk.Label(frame, text="• Windows: Look for Ollama in system tray, or run 'ollama serve'\n• Mac: Click Ollama in Applications\n• Linux: Run 'ollama serve' in terminal", justify=tk.LEFT, wraplength=500).pack(pady=(0, 20))
        
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
    
    def _refresh_installed_models(self):
        """Refresh the installed models list."""
        for item in self.installed_tree.get_children():
            self.installed_tree.delete(item)
        
        models = get_installed_models()
        
        if not models:
            self.installed_tree.insert("", tk.END, values=("No models installed", ""))
        else:
            for name, size in models:
                self.installed_tree.insert("", tk.END, values=(name, size))
    
    def _delete_selected(self):
        """Delete the selected model."""
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
    
    def _start_download(self):
        """Start downloading the selected model."""
        if self.is_downloading:
            messagebox.showwarning("Download in Progress", "Please wait for the current download to finish.", parent=self.dialog)
            return
        
        idx = self.model_combo.current()
        if idx < 0 or idx >= len(self.current_models):
            return
        
        model = self.current_models[idx]
        model_name, display_name, desc, size, min_ram, category = model
        
        # Check if already installed
        installed = get_installed_models()
        installed_names = [m[0] for m in installed]
        if model_name in installed_names:
            messagebox.showinfo("Already Installed", f"'{display_name}' is already installed.", parent=self.dialog)
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
        
        thread = threading.Thread(target=self._download_model, args=(model_name, display_name), daemon=True)
        thread.start()
    
    def _download_model(self, model_name, display_name):
        """Download a model (runs in thread)."""
        try:
            process = subprocess.Popen(
                ["ollama", "pull", model_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
            self.download_process = process
            
            for line in process.stdout:
                line = line.strip()
                if line:
                    # Try to parse progress percentage
                    if '%' in line:
                        try:
                            import re
                            match = re.search(r'(\d+)%', line)
                            if match:
                                pct = int(match.group(1))
                                self.dialog.after(0, lambda p=pct: self.progress_var.set(p))
                        except:
                            pass
                    
                    self.dialog.after(0, lambda l=line: self.status_label.config(text=l[:80]))
            
            process.wait()
            
            if process.returncode == 0:
                self.dialog.after(0, self._download_complete_success, display_name)
            else:
                self.dialog.after(0, self._download_complete_error, display_name)
                
        except Exception as e:
            print(f"Download error: {e}")
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
        messagebox.showerror("Download Failed", f"Failed to download '{display_name}'.\n\nCheck your internet connection and try again.", parent=self.dialog)
    
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
                except:
                    pass
        
        self.dialog.destroy()


def show_local_model_manager(parent, on_models_changed=None):
    """Show the Local Model Manager dialog."""
    LocalModelManagerDialog(parent, on_models_changed)
