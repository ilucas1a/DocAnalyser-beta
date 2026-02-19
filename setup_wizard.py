"""
setup_wizard.py - First-Run Setup Wizard and Dependency Status UI
Provides a user-friendly interface for checking and installing dependencies
"""

import os
import sys
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Callable

from version import get_version_string, APP_DISPLAY_NAME
from dependency_checker import (
    check_all_dependencies, 
    get_optional_packages_status,
    get_system_summary,
    get_faster_whisper_status,
    get_lm_studio_status,
    get_system_hardware,
    get_lm_studio_recommendations,
    get_top_lm_recommendation,
    DependencyStatus,
    FasterWhisperStatus,
    LMStudioStatus,
    SystemHardwareInfo,
    LMModelRecommendation,
    WHISPER_MODEL_SIZES
)


class SetupWizard:
    """
    First-run setup wizard that checks dependencies and guides installation.
    Can also be opened from Settings menu for dependency management.
    """
    
    def __init__(self, parent: Optional[tk.Tk] = None, on_complete: Optional[Callable] = None):
        """
        Initialize the setup wizard.
        
        Args:
            parent: Parent window (None to create standalone)
            on_complete: Callback when wizard is closed
        """
        self.on_complete = on_complete
        self.summary = None
        
        # Create window
        if parent:
            self.window = tk.Toplevel(parent)
        else:
            self.window = tk.Tk()
        
        self.window.title(f"{APP_DISPLAY_NAME} - System Check")
        self.window.geometry("600x600")
        self.window.resizable(False, False)
        
        # Center on screen
        self.window.update_idletasks()
        x = (self.window.winfo_screenwidth() - 600) // 2
        y = (self.window.winfo_screenheight() - 600) // 2
        self.window.geometry(f"+{x}+{y}")
        
        # Build UI
        self._create_ui()
        
        # Run checks
        self.refresh_status()
        
        # Handle close
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)
    
    def _create_ui(self):
        """Create the wizard UI"""
        # Main container with padding
        main_frame = ttk.Frame(self.window, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Header
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=tk.X, pady=(0, 15))
        
        title_label = ttk.Label(
            header_frame, 
            text=f"🔧 {APP_DISPLAY_NAME} System Check",
            font=("Segoe UI", 14, "bold")
        )
        title_label.pack(side=tk.LEFT)
        
        version_label = ttk.Label(
            header_frame,
            text=get_version_string(),
            font=("Segoe UI", 10)
        )
        version_label.pack(side=tk.RIGHT)
        
        # Description
        desc_label = ttk.Label(
            main_frame,
            text="Checking your system for required components...",
            font=("Segoe UI", 10),
            foreground="gray"
        )
        desc_label.pack(fill=tk.X, pady=(0, 10))
        
        # Status container with scrollbar
        status_frame = ttk.LabelFrame(main_frame, text="Status", padding="10")
        status_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        
        # Create canvas for scrolling
        canvas = tk.Canvas(status_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(status_frame, orient="vertical", command=canvas.yview)
        self.status_container = ttk.Frame(canvas)
        
        self.status_container.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.status_container, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Summary label
        self.summary_label = ttk.Label(
            main_frame,
            text="",
            font=("Segoe UI", 10)
        )
        self.summary_label.pack(fill=tk.X, pady=(0, 10))
        
        # Button frame
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X)
        
        self.refresh_btn = ttk.Button(
            button_frame,
            text="🔄 Refresh",
            command=self.refresh_status
        )
        self.refresh_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        self.continue_btn = ttk.Button(
            button_frame,
            text="Continue →",
            command=self._on_close
        )
        self.continue_btn.pack(side=tk.RIGHT)
    
    def refresh_status(self):
        """Refresh dependency status"""
        # Clear existing status widgets
        for widget in self.status_container.winfo_children():
            widget.destroy()
        
        # Get fresh status
        self.summary = get_system_summary()
        
        # Core features section
        self._add_section_header("Core Features (Always Available)")
        self._add_feature_row("YouTube Transcripts", True, "Built-in via yt-dlp")
        self._add_feature_row("Web Article Extraction", True, "Built-in")
        self._add_feature_row("Document Files (DOCX, TXT, RTF)", True, "Built-in")
        self._add_feature_row("PDF Text Extraction", True, "Built-in")
        self._add_feature_row("AI Analysis (Cloud)", True, "Requires API keys in Settings")
        
        # Separator
        ttk.Separator(self.status_container, orient="horizontal").pack(fill=tk.X, pady=10)
        
        # External tools section
        self._add_section_header("Optional Features (Require Installation)")
        
        deps = self.summary['dependencies']
        
        # OCR
        tesseract = deps['tesseract']
        poppler = deps['poppler']
        ocr_ready = tesseract.installed and poppler.installed
        self._add_dependency_row(
            "OCR (Scanned Documents & Images)",
            ocr_ready,
            tesseract if not tesseract.installed else (poppler if not poppler.installed else None)
        )
        
        # Audio
        ffmpeg = deps['ffmpeg']
        self._add_dependency_row(
            "Audio/Video Transcription",
            ffmpeg.installed,
            ffmpeg if not ffmpeg.installed else None
        )
        
        # Local Whisper (detailed)
        self._add_whisper_section()
        
        # LM Studio (Local AI)
        self._add_lm_studio_section()
        
        # Drag and drop
        packages = self.summary['packages']
        dnd_installed = packages.get('tkinterdnd2', (False,))[0]
        self._add_feature_row(
            "Drag & Drop Support",
            dnd_installed,
            "pip install tkinterdnd2" if not dnd_installed else "Installed"
        )
        
        # Update summary
        missing = sum(1 for dep in deps.values() if not dep.installed)
        if missing == 0:
            self.summary_label.config(
                text="✅ All external tools are installed! You're ready to go.",
                foreground="green"
            )
        else:
            self.summary_label.config(
                text=f"⚠️ {missing} optional component(s) not installed. Some features will be unavailable.",
                foreground="orange"
            )
    
    def _add_section_header(self, text: str):
        """Add a section header"""
        label = ttk.Label(
            self.status_container,
            text=text,
            font=("Segoe UI", 10, "bold")
        )
        label.pack(fill=tk.X, pady=(10, 5), anchor="w")
    
    def _add_feature_row(self, name: str, available: bool, note: str = ""):
        """Add a simple feature status row"""
        frame = ttk.Frame(self.status_container)
        frame.pack(fill=tk.X, pady=2)
        
        icon = "✅" if available else "⚠️"
        status_color = "green" if available else "gray"
        
        label = ttk.Label(frame, text=f"  {icon}  {name}", font=("Segoe UI", 9))
        label.pack(side=tk.LEFT)
        
        if note:
            note_label = ttk.Label(
                frame, 
                text=f"({note})", 
                font=("Segoe UI", 8),
                foreground="gray"
            )
            note_label.pack(side=tk.LEFT, padx=(10, 0))
    
    def _add_dependency_row(self, name: str, installed: bool, dep_info: Optional[DependencyStatus]):
        """Add a dependency row with install button if missing"""
        frame = ttk.Frame(self.status_container)
        frame.pack(fill=tk.X, pady=3)
        
        icon = "✅" if installed else "❌"
        
        label = ttk.Label(frame, text=f"  {icon}  {name}", font=("Segoe UI", 9))
        label.pack(side=tk.LEFT)
        
        if installed:
            status_label = ttk.Label(
                frame,
                text="Ready",
                font=("Segoe UI", 8),
                foreground="green"
            )
            status_label.pack(side=tk.LEFT, padx=(10, 0))
        elif dep_info:
            install_btn = ttk.Button(
                frame,
                text="Install...",
                width=10,
                command=lambda d=dep_info: self._show_install_dialog(d)
            )
            install_btn.pack(side=tk.RIGHT)
            
            status_label = ttk.Label(
                frame,
                text="Not Found",
                font=("Segoe UI", 8),
                foreground="red"
            )
            status_label.pack(side=tk.LEFT, padx=(10, 0))
    
    def _add_whisper_section(self):
        """Add detailed faster-whisper status section"""
        whisper = get_faster_whisper_status()
        
        # Main row
        frame = ttk.Frame(self.status_container)
        frame.pack(fill=tk.X, pady=3)
        
        if not whisper.package_installed:
            icon = "❌"
            label = ttk.Label(frame, text=f"  {icon}  Local Whisper Transcription", font=("Segoe UI", 9))
            label.pack(side=tk.LEFT)
            
            status_label = ttk.Label(
                frame,
                text="Not Installed",
                font=("Segoe UI", 8),
                foreground="red"
            )
            status_label.pack(side=tk.LEFT, padx=(10, 0))
            
            # Details button
            details_btn = ttk.Button(
                frame,
                text="Details...",
                width=10,
                command=lambda: self._show_whisper_dialog(whisper)
            )
            details_btn.pack(side=tk.RIGHT)
        else:
            icon = "✅"
            label = ttk.Label(frame, text=f"  {icon}  Local Whisper Transcription", font=("Segoe UI", 9))
            label.pack(side=tk.LEFT)
            
            # Summary info
            gpu_str = "GPU" if whisper.cuda_available else "CPU"
            model_count = len(whisper.downloaded_models)
            summary = f"{gpu_str}, {model_count} model(s)"
            
            status_label = ttk.Label(
                frame,
                text=summary,
                font=("Segoe UI", 8),
                foreground="green"
            )
            status_label.pack(side=tk.LEFT, padx=(10, 0))
            
            # Details button
            details_btn = ttk.Button(
                frame,
                text="Details...",
                width=10,
                command=lambda: self._show_whisper_dialog(whisper)
            )
            details_btn.pack(side=tk.RIGHT)
    
    def _show_whisper_dialog(self, whisper: FasterWhisperStatus):
        """Show detailed faster-whisper status dialog"""
        dialog = tk.Toplevel(self.window)
        dialog.title("Local Whisper Status")
        dialog.geometry("520x450")
        dialog.resizable(False, False)
        dialog.transient(self.window)
        dialog.grab_set()
        
        # Center on parent
        dialog.update_idletasks()
        x = self.window.winfo_x() + 40
        y = self.window.winfo_y() + 50
        dialog.geometry(f"+{x}+{y}")
        
        frame = ttk.Frame(dialog, padding="20")
        frame.pack(fill=tk.BOTH, expand=True)
        
        # Title
        title = ttk.Label(
            frame,
            text="🎤 Local Whisper Transcription",
            font=("Segoe UI", 12, "bold")
        )
        title.pack(anchor="w")
        
        # Package status
        if whisper.package_installed:
            pkg_text = f"✅ faster-whisper v{whisper.package_version} installed"
            pkg_color = "green"
        else:
            pkg_text = "❌ faster-whisper not installed"
            pkg_color = "red"
        
        pkg_label = ttk.Label(frame, text=pkg_text, font=("Segoe UI", 9), foreground=pkg_color)
        pkg_label.pack(anchor="w", pady=(10, 5))
        
        if not whisper.package_installed:
            install_label = ttk.Label(
                frame,
                text="Install with: pip install faster-whisper",
                font=("Consolas", 9),
                foreground="gray"
            )
            install_label.pack(anchor="w", pady=(0, 10))
        else:
            # GPU/CUDA Status
            gpu_frame = ttk.LabelFrame(frame, text="GPU/CUDA Status", padding="10")
            gpu_frame.pack(fill=tk.X, pady=(10, 5))
            
            if whisper.cuda_available:
                gpu_text = "✅ CUDA available - GPU acceleration enabled"
                if whisper.gpu_name:
                    gpu_text += f"\n   GPU: {whisper.gpu_name}"
                gpu_text += f"\n   Recommended compute type: {whisper.compute_type}"
            else:
                gpu_text = "⚠️ CUDA not available - using CPU (slower)\n   Compute type: int8"
            
            gpu_label = ttk.Label(gpu_frame, text=gpu_text, font=("Segoe UI", 9), justify=tk.LEFT)
            gpu_label.pack(anchor="w")
            
            # Downloaded Models
            models_frame = ttk.LabelFrame(frame, text="Downloaded Models", padding="10")
            models_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 5))
            
            if whisper.downloaded_models:
                models_text = ""
                for model in whisper.downloaded_models:
                    models_text += f"📦 {model.name} ({model.size_display})\n"
                models_text += f"\nTotal: {len(whisper.downloaded_models)} model(s), {whisper.total_models_size_display}"
            else:
                models_text = "No models downloaded yet.\n\nModels are downloaded automatically on first use.\n\nRecommended models:\n"
                if whisper.cuda_available:
                    models_text += "  • medium or large-v3 (GPU)"
                else:
                    models_text += "  • tiny or base (CPU)"
            
            models_label = ttk.Label(models_frame, text=models_text, font=("Segoe UI", 9), justify=tk.LEFT)
            models_label.pack(anchor="w")
            
            # Recommendation
            rec_frame = ttk.LabelFrame(frame, text="Recommendation", padding="10")
            rec_frame.pack(fill=tk.X, pady=(10, 5))
            
            rec_label = ttk.Label(rec_frame, text=whisper.performance_note, font=("Segoe UI", 9))
            rec_label.pack(anchor="w")
        
        # Close button
        close_btn = ttk.Button(frame, text="Close", command=dialog.destroy)
        close_btn.pack(side=tk.RIGHT, pady=(15, 0))
    
    def _add_lm_studio_section(self):
        """Add LM Studio status section"""
        lm_studio = get_lm_studio_status()
        
        # Main row
        frame = ttk.Frame(self.status_container)
        frame.pack(fill=tk.X, pady=3)
        
        if not lm_studio.installed:
            icon = "❌"
            label = ttk.Label(frame, text=f"  {icon}  Local AI (LM Studio)", font=("Segoe UI", 9))
            label.pack(side=tk.LEFT)
            
            status_label = ttk.Label(
                frame,
                text="Not Installed",
                font=("Segoe UI", 8),
                foreground="red"
            )
            status_label.pack(side=tk.LEFT, padx=(10, 0))
        else:
            icon = "✅"
            label = ttk.Label(frame, text=f"  {icon}  Local AI (LM Studio)", font=("Segoe UI", 9))
            label.pack(side=tk.LEFT)
            
            # Summary info
            if lm_studio.running:
                summary = f"Running, {lm_studio.model_count} model(s)"
                color = "green"
            else:
                summary = f"Installed, {lm_studio.model_count} model(s)"
                color = "green"
            
            status_label = ttk.Label(
                frame,
                text=summary,
                font=("Segoe UI", 8),
                foreground=color
            )
            status_label.pack(side=tk.LEFT, padx=(10, 0))
        
        # Details button (always show)
        details_btn = ttk.Button(
            frame,
            text="Details...",
            width=10,
            command=lambda: self._show_lm_studio_dialog(lm_studio)
        )
        details_btn.pack(side=tk.RIGHT)
    
    def _show_lm_studio_dialog(self, lm_studio: LMStudioStatus):
        """Show detailed LM Studio status dialog with hardware-based recommendations"""
        dialog = tk.Toplevel(self.window)
        dialog.title("Local AI (LM Studio)")
        dialog.geometry("580x620")
        dialog.resizable(False, False)
        dialog.transient(self.window)
        dialog.grab_set()
        
        # Center on parent
        dialog.update_idletasks()
        x = self.window.winfo_x() + 10
        y = self.window.winfo_y() + 10
        dialog.geometry(f"+{x}+{y}")
        
        # Main frame with scrollable content
        main_frame = ttk.Frame(dialog, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title
        title = ttk.Label(
            main_frame,
            text="🤖 Local AI with LM Studio",
            font=("Segoe UI", 12, "bold")
        )
        title.pack(anchor="w")
        
        # Description
        desc = ttk.Label(
            main_frame,
            text="Run AI models locally - completely free, no API costs!",
            font=("Segoe UI", 9),
            foreground="gray"
        )
        desc.pack(anchor="w", pady=(5, 10))
        
        # Get hardware info
        hardware = get_system_hardware()
        
        # System Hardware Section
        hw_frame = ttk.LabelFrame(main_frame, text="Your System", padding="10")
        hw_frame.pack(fill=tk.X, pady=(0, 10))
        
        # RAM info
        ram_text = f"💾 RAM: {hardware.total_ram_gb:.0f} GB"
        if hardware.available_ram_gb > 0:
            ram_text += f" ({hardware.available_ram_gb:.0f} GB available)"
        ttk.Label(hw_frame, text=ram_text, font=("Segoe UI", 9)).pack(anchor="w")
        
        # GPU info
        if hardware.has_nvidia_gpu:
            gpu_text = f"🎮 GPU: {hardware.gpu_name} ({hardware.gpu_vram_gb:.0f} GB VRAM)"
            gpu_color = "green"
        else:
            gpu_text = "🎮 GPU: No NVIDIA GPU detected (will use CPU)"
            gpu_color = "gray"
        ttk.Label(hw_frame, text=gpu_text, font=("Segoe UI", 9), foreground=gpu_color).pack(anchor="w")
        
        # CPU info
        if hardware.cpu_name:
            cpu_text = f"🖥️ CPU: {hardware.cpu_name[:50]}{'...' if len(hardware.cpu_name or '') > 50 else ''}"
            if hardware.cpu_cores > 0:
                cpu_text += f" ({hardware.cpu_cores} cores)"
            ttk.Label(hw_frame, text=cpu_text, font=("Segoe UI", 9)).pack(anchor="w")
        
        # Model Recommendations Section
        rec_frame = ttk.LabelFrame(main_frame, text="Recommended Models for Your System", padding="10")
        rec_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        recommendations = get_lm_studio_recommendations(hardware)
        top_rec = get_top_lm_recommendation(hardware)
        
        # Create scrollable frame for recommendations
        rec_canvas = tk.Canvas(rec_frame, highlightthickness=0, height=180)
        rec_scrollbar = ttk.Scrollbar(rec_frame, orient="vertical", command=rec_canvas.yview)
        rec_inner = ttk.Frame(rec_canvas)
        
        rec_inner.bind(
            "<Configure>",
            lambda e: rec_canvas.configure(scrollregion=rec_canvas.bbox("all"))
        )
        
        rec_canvas.create_window((0, 0), window=rec_inner, anchor="nw")
        rec_canvas.configure(yscrollcommand=rec_scrollbar.set)
        
        rec_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        rec_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        for rec in recommendations:
            row = ttk.Frame(rec_inner)
            row.pack(fill=tk.X, pady=3)
            
            # Highlight top recommendation
            if top_rec and rec.name == top_rec.name:
                icon = "⭐"
                name_suffix = " (RECOMMENDED)"
            elif rec.suitable:
                icon = "✅"
                name_suffix = ""
            else:
                icon = "❌"
                name_suffix = ""
            
            # Model name and size
            name_label = ttk.Label(
                row, 
                text=f"{icon} {rec.name}{name_suffix}",
                font=("Segoe UI", 9, "bold" if top_rec and rec.name == top_rec.name else "normal")
            )
            name_label.pack(anchor="w")
            
            # Description and requirements
            details = f"    {rec.description}"
            details_label = ttk.Label(row, text=details, font=("Segoe UI", 8), foreground="gray")
            details_label.pack(anchor="w")
            
            # Status/reason
            size_info = f"    Download: {rec.download_size_gb:.1f} GB | RAM: {rec.ram_required_gb:.0f} GB"
            if hardware.has_nvidia_gpu:
                size_info += f" | VRAM: {rec.vram_required_gb:.0f} GB"
            ttk.Label(row, text=size_info, font=("Segoe UI", 8), foreground="gray").pack(anchor="w")
            
            status_color = "green" if rec.suitable else "red"
            ttk.Label(row, text=f"    {rec.reason}", font=("Segoe UI", 8), foreground=status_color).pack(anchor="w")
        
        # Installation Status Section
        status_frame = ttk.LabelFrame(main_frame, text="Installation Status", padding="10")
        status_frame.pack(fill=tk.X, pady=(0, 10))
        
        if lm_studio.installed:
            ttk.Label(status_frame, text="✅ LM Studio is installed", font=("Segoe UI", 9), foreground="green").pack(anchor="w")
            
            if lm_studio.running:
                ttk.Label(status_frame, text="✅ Server is running - Ready to use!", font=("Segoe UI", 9), foreground="green").pack(anchor="w")
            else:
                ttk.Label(status_frame, text="⚠️ Server not running - Start LM Studio and load a model", font=("Segoe UI", 9), foreground="orange").pack(anchor="w")
            
            if lm_studio.model_count > 0:
                ttk.Label(status_frame, text=f"📦 {lm_studio.model_count} model(s) downloaded", font=("Segoe UI", 9)).pack(anchor="w")
        else:
            ttk.Label(status_frame, text="❌ LM Studio is not installed", font=("Segoe UI", 9), foreground="red").pack(anchor="w")
            ttk.Label(status_frame, text="   Download from lmstudio.ai (free, ~500 MB)", font=("Segoe UI", 8), foreground="gray").pack(anchor="w")
        
        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(5, 0))
        
        def open_lm_studio_website():
            webbrowser.open("https://lmstudio.ai")
        
        def open_local_ai_guide():
            guide_path = os.path.join(os.path.dirname(__file__), "LOCAL_AI_GUIDE.md")
            if os.path.exists(guide_path):
                webbrowser.open(f"file://{guide_path}")
            else:
                webbrowser.open("https://lmstudio.ai/docs")
        
        if not lm_studio.installed:
            download_btn = ttk.Button(
                btn_frame,
                text="🌐 Download LM Studio",
                command=open_lm_studio_website
            )
            download_btn.pack(side=tk.LEFT)
        
        guide_btn = ttk.Button(
            btn_frame,
            text="📖 Local AI Guide",
            command=open_local_ai_guide
        )
        guide_btn.pack(side=tk.LEFT, padx=(5, 0))
        
        close_btn = ttk.Button(btn_frame, text="Close", command=dialog.destroy)
        close_btn.pack(side=tk.RIGHT)
    
    def _show_install_dialog(self, dep: DependencyStatus):
        """Show installation instructions for a dependency"""
        dialog = tk.Toplevel(self.window)
        dialog.title(f"Install {dep.name}")
        dialog.geometry("500x350")
        dialog.resizable(False, False)
        dialog.transient(self.window)
        dialog.grab_set()
        
        # Center on parent
        dialog.update_idletasks()
        x = self.window.winfo_x() + 50
        y = self.window.winfo_y() + 50
        dialog.geometry(f"+{x}+{y}")
        
        frame = ttk.Frame(dialog, padding="20")
        frame.pack(fill=tk.BOTH, expand=True)
        
        # Title
        title = ttk.Label(
            frame,
            text=f"📦 Install {dep.name}",
            font=("Segoe UI", 12, "bold")
        )
        title.pack(anchor="w")
        
        # Purpose
        purpose = ttk.Label(
            frame,
            text=f"Required for: {dep.required_for}",
            font=("Segoe UI", 9),
            foreground="gray"
        )
        purpose.pack(anchor="w", pady=(5, 15))
        
        # Instructions
        inst_label = ttk.Label(
            frame,
            text="Installation Steps:",
            font=("Segoe UI", 10, "bold")
        )
        inst_label.pack(anchor="w")
        
        inst_text = tk.Text(
            frame,
            height=8,
            width=55,
            font=("Consolas", 9),
            wrap=tk.WORD,
            bg="#f5f5f5"
        )
        inst_text.pack(fill=tk.X, pady=(5, 15))
        inst_text.insert("1.0", dep.install_instructions)
        inst_text.config(state=tk.DISABLED)
        
        # Buttons
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X)
        
        def open_url():
            webbrowser.open(dep.install_url)
        
        download_btn = ttk.Button(
            btn_frame,
            text="🌐 Open Download Page",
            command=open_url
        )
        download_btn.pack(side=tk.LEFT)
        
        close_btn = ttk.Button(
            btn_frame,
            text="Close",
            command=dialog.destroy
        )
        close_btn.pack(side=tk.RIGHT)
    
    def _on_close(self):
        """Handle window close"""
        if self.on_complete:
            self.on_complete()
        self.window.destroy()
    
    def run(self):
        """Run the wizard as main loop (for standalone use)"""
        self.window.mainloop()


class UpdateNotificationDialog:
    """
    Simple dialog to notify user of available update.
    """
    
    def __init__(self, parent: tk.Tk, update_info):
        """
        Show update notification dialog.
        
        Args:
            parent: Parent window
            update_info: UpdateInfo object from update_checker
        """
        from update_checker import create_update_message, open_download_page
        
        self.update_info = update_info
        self.result = None  # 'download', 'skip', 'later'
        
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Update Available")
        self.dialog.geometry("450x300")
        self.dialog.resizable(False, False)
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        # Center
        self.dialog.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 450) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 300) // 2
        self.dialog.geometry(f"+{x}+{y}")
        
        frame = ttk.Frame(self.dialog, padding="20")
        frame.pack(fill=tk.BOTH, expand=True)
        
        # Icon and title
        title = ttk.Label(
            frame,
            text="🎉 Update Available!",
            font=("Segoe UI", 14, "bold")
        )
        title.pack(anchor="w")
        
        # Version info
        version_text = f"Version {update_info.latest_version} is available (you have {update_info.current_version})"
        version_label = ttk.Label(
            frame,
            text=version_text,
            font=("Segoe UI", 10)
        )
        version_label.pack(anchor="w", pady=(5, 15))
        
        # Changelog
        if update_info.changelog:
            changes_label = ttk.Label(
                frame,
                text="What's New:",
                font=("Segoe UI", 10, "bold")
            )
            changes_label.pack(anchor="w")
            
            changes_text = tk.Text(
                frame,
                height=6,
                width=50,
                font=("Segoe UI", 9),
                wrap=tk.WORD,
                bg="#f5f5f5"
            )
            changes_text.pack(fill=tk.X, pady=(5, 15))
            changes_text.insert("1.0", update_info.changelog)
            changes_text.config(state=tk.DISABLED)
        
        # Buttons
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        
        def on_download():
            self.result = 'download'
            open_download_page(update_info)
            self.dialog.destroy()
        
        def on_later():
            self.result = 'later'
            self.dialog.destroy()
        
        def on_skip():
            self.result = 'skip'
            self.dialog.destroy()
        
        download_btn = ttk.Button(
            btn_frame,
            text="⬇️ Download Update",
            command=on_download
        )
        download_btn.pack(side=tk.LEFT)
        
        skip_btn = ttk.Button(
            btn_frame,
            text="Skip This Version",
            command=on_skip
        )
        skip_btn.pack(side=tk.RIGHT)
        
        later_btn = ttk.Button(
            btn_frame,
            text="Remind Me Later",
            command=on_later
        )
        later_btn.pack(side=tk.RIGHT, padx=(0, 10))
        
        self.dialog.wait_window()


# -------------------------
# Convenience Functions
# -------------------------

def show_setup_wizard(parent: Optional[tk.Tk] = None, on_complete: Optional[Callable] = None):
    """Show the setup wizard dialog"""
    wizard = SetupWizard(parent, on_complete)
    if parent is None:
        wizard.run()
    return wizard


def show_update_notification(parent: tk.Tk, update_info) -> Optional[str]:
    """
    Show update notification dialog.
    Returns: 'download', 'skip', 'later', or None if cancelled
    """
    dialog = UpdateNotificationDialog(parent, update_info)
    return dialog.result


def should_show_first_run_wizard(config: dict) -> bool:
    """Check if we should show the first-run wizard"""
    return not config.get("setup_wizard_completed", False)


def mark_wizard_completed(config: dict) -> dict:
    """Mark that the wizard has been completed"""
    config["setup_wizard_completed"] = True
    return config


# -------------------------
# Standalone Test
# -------------------------

if __name__ == "__main__":
    # Test the wizard standalone
    wizard = SetupWizard()
    wizard.run()
