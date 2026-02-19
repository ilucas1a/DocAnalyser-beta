"""
local_ai_setup_dialog.py - Local AI Setup Wizard for DocAnalyzer

A user-friendly dialog that guides users through:
1. Checking if Ollama is installed
2. Starting the Ollama server
3. Downloading recommended models
4. Testing the connection

This integrates with local_ai_manager.py for all backend operations.

Author: DocAnalyzer Development
Version: 1.0.0
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import webbrowser
from typing import Optional, Callable

# Import our local AI manager
try:
    from local_ai_manager import (
        LocalAIManager, 
        detect_system_specs, 
        get_compatible_models,
        get_ollama_install_instructions,
        MODEL_DATABASE,
        SystemSpecs,
        ModelInfo
    )
    LOCAL_AI_AVAILABLE = True
except ImportError:
    LOCAL_AI_AVAILABLE = False


class LocalAISetupDialog:
    """
    Setup wizard dialog for Local AI configuration.
    
    Usage:
        dialog = LocalAISetupDialog(parent_window, on_complete_callback)
        dialog.show()
    """
    
    def __init__(self, parent: tk.Tk, on_complete: Optional[Callable] = None):
        """
        Initialize the setup dialog.
        
        Args:
            parent: Parent Tkinter window
            on_complete: Optional callback when setup is complete
        """
        self.parent = parent
        self.on_complete = on_complete
        self.manager = LocalAIManager() if LOCAL_AI_AVAILABLE else None
        self.dialog: Optional[tk.Toplevel] = None
        self.specs: Optional[SystemSpecs] = None
        
        # Track current state
        self.ollama_installed = False
        self.ollama_running = False
        self.models_available = False
    
    def show(self):
        """Display the setup dialog"""
        if not LOCAL_AI_AVAILABLE:
            messagebox.showerror(
                "Module Not Found",
                "local_ai_manager.py is required.\n\n"
                "Please ensure it's in the same directory as this file."
            )
            return
        
        # Create dialog window
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title("Local AI Setup")
        self.dialog.geometry("600x700")
        self.dialog.resizable(True, True)
        self.dialog.transient(self.parent)
        
        # Center on parent
        self.dialog.update_idletasks()
        x = self.parent.winfo_x() + (self.parent.winfo_width() - 600) // 2
        y = self.parent.winfo_y() + (self.parent.winfo_height() - 700) // 2
        self.dialog.geometry(f"+{x}+{y}")
        
        # Build UI
        self._build_ui()
        
        # Run initial check
        self.dialog.after(100, self._run_initial_check)
        
        # Make modal
        self.dialog.grab_set()
        self.dialog.focus_set()
    
    def _build_ui(self):
        """Build the dialog UI"""
        main_frame = ttk.Frame(self.dialog, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title
        title_label = ttk.Label(
            main_frame,
            text="🤖 Local AI Setup",
            font=("Segoe UI", 16, "bold")
        )
        title_label.pack(pady=(0, 10))
        
        subtitle = ttk.Label(
            main_frame,
            text="Run AI models locally on your computer - free, private, and offline-capable",
            font=("Segoe UI", 10),
            foreground="gray"
        )
        subtitle.pack(pady=(0, 20))
        
        # === SYSTEM SPECS SECTION ===
        specs_frame = ttk.LabelFrame(main_frame, text="Your System", padding=10)
        specs_frame.pack(fill=tk.X, pady=(0, 15))
        
        self.specs_label = ttk.Label(specs_frame, text="Detecting...", justify=tk.LEFT)
        self.specs_label.pack(anchor=tk.W)
        
        # === STATUS SECTION ===
        status_frame = ttk.LabelFrame(main_frame, text="Status", padding=10)
        status_frame.pack(fill=tk.X, pady=(0, 15))
        
        # Ollama installed
        self.install_frame = ttk.Frame(status_frame)
        self.install_frame.pack(fill=tk.X, pady=5)
        
        self.install_status = ttk.Label(self.install_frame, text="⏳ Checking Ollama installation...")
        self.install_status.pack(side=tk.LEFT)
        
        self.install_btn = ttk.Button(
            self.install_frame, 
            text="Install Ollama",
            command=self._show_install_instructions
        )
        self.install_btn.pack(side=tk.RIGHT)
        self.install_btn.pack_forget()  # Hide initially
        
        # Ollama running
        self.running_frame = ttk.Frame(status_frame)
        self.running_frame.pack(fill=tk.X, pady=5)
        
        self.running_status = ttk.Label(self.running_frame, text="⏳ Checking if server is running...")
        self.running_status.pack(side=tk.LEFT)
        
        self.start_btn = ttk.Button(
            self.running_frame,
            text="Start Ollama",
            command=self._start_ollama
        )
        self.start_btn.pack(side=tk.RIGHT)
        self.start_btn.pack_forget()  # Hide initially
        
        # Models available
        self.models_frame = ttk.Frame(status_frame)
        self.models_frame.pack(fill=tk.X, pady=5)
        
        self.models_status = ttk.Label(self.models_frame, text="⏳ Checking installed models...")
        self.models_status.pack(side=tk.LEFT)
        
        # === MODELS SECTION ===
        models_section = ttk.LabelFrame(main_frame, text="Available Models", padding=10)
        models_section.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        
        # Model list with scrollbar
        list_frame = ttk.Frame(models_section)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        self.model_tree = ttk.Treeview(
            list_frame,
            columns=("status", "name", "size", "note"),
            show="headings",
            height=8
        )
        self.model_tree.heading("status", text="")
        self.model_tree.heading("name", text="Model")
        self.model_tree.heading("size", text="Size")
        self.model_tree.heading("note", text="Compatibility")
        
        self.model_tree.column("status", width=30, anchor=tk.CENTER)
        self.model_tree.column("name", width=180)
        self.model_tree.column("size", width=80, anchor=tk.CENTER)
        self.model_tree.column("note", width=200)
        
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.model_tree.yview)
        self.model_tree.configure(yscrollcommand=scrollbar.set)
        
        self.model_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Model action buttons
        model_btn_frame = ttk.Frame(models_section)
        model_btn_frame.pack(fill=tk.X, pady=(10, 0))
        
        self.download_btn = ttk.Button(
            model_btn_frame,
            text="⬇️ Download Selected",
            command=self._download_selected_model
        )
        self.download_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.delete_btn = ttk.Button(
            model_btn_frame,
            text="🗑️ Delete Selected",
            command=self._delete_selected_model
        )
        self.delete_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.refresh_btn = ttk.Button(
            model_btn_frame,
            text="🔄 Refresh",
            command=self._refresh_models
        )
        self.refresh_btn.pack(side=tk.RIGHT)
        
        # Progress bar (hidden initially)
        self.progress_frame = ttk.Frame(models_section)
        self.progress_frame.pack(fill=tk.X, pady=(10, 0))
        
        self.progress_label = ttk.Label(self.progress_frame, text="")
        self.progress_label.pack(anchor=tk.W)
        
        self.progress_bar = ttk.Progressbar(
            self.progress_frame, 
            mode="indeterminate",
            length=400
        )
        
        # === BOTTOM BUTTONS ===
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(
            bottom_frame,
            text="Open Ollama Website",
            command=lambda: webbrowser.open("https://ollama.com")
        ).pack(side=tk.LEFT)
        
        ttk.Button(
            bottom_frame,
            text="Test Connection",
            command=self._test_connection
        ).pack(side=tk.LEFT, padx=10)
        
        ttk.Button(
            bottom_frame,
            text="Close",
            command=self._close_dialog
        ).pack(side=tk.RIGHT)
    
    def _run_initial_check(self):
        """Run the initial system check"""
        # Detect system specs in background
        def detect():
            self.specs = detect_system_specs()
            self.dialog.after(0, self._update_specs_display)
            self.dialog.after(0, self._check_ollama_status)
        
        threading.Thread(target=detect, daemon=True).start()
    
    def _update_specs_display(self):
        """Update the system specs display"""
        if self.specs:
            self.specs_label.config(text=self.specs.to_display_string())
    
    def _check_ollama_status(self):
        """Check Ollama installation and running status"""
        def check():
            # Check installation
            self.ollama_installed, install_msg = self.manager.ollama.is_installed()
            
            if self.ollama_installed:
                self.dialog.after(0, lambda: self.install_status.config(
                    text="✅ Ollama is installed"
                ))
                self.dialog.after(0, lambda: self.install_btn.pack_forget())
                
                # Check if running
                self.ollama_running, run_msg = self.manager.ollama.is_running()
                
                if self.ollama_running:
                    self.dialog.after(0, lambda: self.running_status.config(
                        text="✅ Ollama server is running"
                    ))
                    self.dialog.after(0, lambda: self.start_btn.pack_forget())
                    
                    # Check models
                    self.dialog.after(0, self._check_models)
                else:
                    self.dialog.after(0, lambda: self.running_status.config(
                        text="❌ Ollama server is not running"
                    ))
                    self.dialog.after(0, lambda: self.start_btn.pack(side=tk.RIGHT))
                    self.dialog.after(0, lambda: self.models_status.config(
                        text="⏸️ Start Ollama to see models"
                    ))
            else:
                self.dialog.after(0, lambda: self.install_status.config(
                    text="❌ Ollama is not installed"
                ))
                self.dialog.after(0, lambda: self.install_btn.pack(side=tk.RIGHT))
                self.dialog.after(0, lambda: self.running_status.config(
                    text="⏸️ Install Ollama first"
                ))
                self.dialog.after(0, lambda: self.models_status.config(
                    text="⏸️ Install Ollama first"
                ))
        
        threading.Thread(target=check, daemon=True).start()
    
    def _check_models(self):
        """Check and display available models"""
        def check():
            success, msg, installed_models = self.manager.ollama.get_installed_models()
            
            if success:
                self.models_available = len(installed_models) > 0
                
                if self.models_available:
                    self.dialog.after(0, lambda: self.models_status.config(
                        text=f"✅ {len(installed_models)} model(s) installed"
                    ))
                else:
                    self.dialog.after(0, lambda: self.models_status.config(
                        text="⚠️ No models installed - download one below"
                    ))
                
                # Update model list
                self.dialog.after(0, lambda: self._populate_model_list(installed_models))
            else:
                self.dialog.after(0, lambda: self.models_status.config(
                    text=f"❌ {msg}"
                ))
        
        threading.Thread(target=check, daemon=True).start()
    
    def _populate_model_list(self, installed_models: list):
        """Populate the model list with installed and available models"""
        # Clear existing items
        for item in self.model_tree.get_children():
            self.model_tree.delete(item)
        
        # Get installed model names
        installed_names = {m["name"] for m in installed_models}
        
        # Get compatible models for this system
        compatible = get_compatible_models(self.specs) if self.specs else []
        
        # Add installed models first
        for model in installed_models:
            name = model["name"]
            size_gb = model["size"] / (1024 ** 3)
            
            # Get friendly name if in database
            display_name = name
            if name in MODEL_DATABASE:
                display_name = MODEL_DATABASE[name].name
            
            self.model_tree.insert(
                "", "end",
                values=("✅", display_name, f"{size_gb:.1f} GB", "Installed"),
                tags=("installed",)
            )
        
        # Add recommended models that aren't installed
        for info, note in compatible:
            if info.ollama_id not in installed_names:
                self.model_tree.insert(
                    "", "end",
                    values=("⬇️", info.name, f"{info.size_gb:.1f} GB", note),
                    tags=("available",)
                )
        
        # Style tags
        self.model_tree.tag_configure("installed", foreground="green")
        self.model_tree.tag_configure("available", foreground="gray")
    
    def _show_install_instructions(self):
        """Show Ollama installation instructions"""
        instructions = get_ollama_install_instructions()
        
        # Create instructions window
        inst_window = tk.Toplevel(self.dialog)
        inst_window.title("Install Ollama")
        inst_window.geometry("500x400")
        inst_window.transient(self.dialog)
        
        text = scrolledtext.ScrolledText(inst_window, wrap=tk.WORD, font=("Consolas", 10))
        text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        text.insert("1.0", instructions)
        text.config(state=tk.DISABLED)
        
        btn_frame = ttk.Frame(inst_window)
        btn_frame.pack(fill=tk.X, pady=10, padx=10)
        
        ttk.Button(
            btn_frame,
            text="Open Ollama Download Page",
            command=lambda: webbrowser.open("https://ollama.com/download")
        ).pack(side=tk.LEFT)
        
        ttk.Button(
            btn_frame,
            text="I've Installed It - Check Again",
            command=lambda: [inst_window.destroy(), self._check_ollama_status()]
        ).pack(side=tk.RIGHT)
    
    def _start_ollama(self):
        """Attempt to start Ollama server"""
        self.running_status.config(text="⏳ Starting Ollama...")
        self.start_btn.config(state=tk.DISABLED)
        
        def start():
            success, msg = self.manager.ollama.start_server()
            
            if success:
                self.ollama_running = True
                self.dialog.after(0, lambda: self.running_status.config(
                    text="✅ Ollama server started!"
                ))
                self.dialog.after(0, lambda: self.start_btn.pack_forget())
                self.dialog.after(0, self._check_models)
            else:
                self.dialog.after(0, lambda: self.running_status.config(
                    text=f"❌ {msg}"
                ))
                self.dialog.after(0, lambda: self.start_btn.config(state=tk.NORMAL))
        
        threading.Thread(target=start, daemon=True).start()
    
    def _download_selected_model(self):
        """Download the selected model"""
        selection = self.model_tree.selection()
        if not selection:
            messagebox.showinfo("No Selection", "Please select a model to download")
            return
        
        item = self.model_tree.item(selection[0])
        values = item["values"]
        
        # Check if already installed
        if values[0] == "✅":
            messagebox.showinfo("Already Installed", f"{values[1]} is already installed")
            return
        
        model_name = values[1]
        
        # Find the ollama_id from our database
        model_id = None
        for mid, info in MODEL_DATABASE.items():
            if info.name == model_name:
                model_id = info.ollama_id
                break
        
        if not model_id:
            messagebox.showerror("Error", f"Could not find model ID for {model_name}")
            return
        
        # Confirm download
        if not messagebox.askyesno(
            "Download Model",
            f"Download {model_name}?\n\nSize: {values[2]}\n\nThis may take several minutes."
        ):
            return
        
        # Show progress
        self.progress_label.config(text=f"Downloading {model_name}...")
        self.progress_bar.pack(fill=tk.X, pady=(5, 0))
        self.progress_bar.start()
        
        self.download_btn.config(state=tk.DISABLED)
        self.delete_btn.config(state=tk.DISABLED)
        
        def download():
            def progress_callback(status, percent):
                self.dialog.after(0, lambda s=status: self.progress_label.config(
                    text=f"Downloading: {s}"
                ))
            
            success, msg = self.manager.ollama.pull_model(model_id, progress_callback)
            
            self.dialog.after(0, self.progress_bar.stop)
            self.dialog.after(0, lambda: self.progress_bar.pack_forget())
            self.dialog.after(0, lambda: self.download_btn.config(state=tk.NORMAL))
            self.dialog.after(0, lambda: self.delete_btn.config(state=tk.NORMAL))
            
            if success:
                self.dialog.after(0, lambda: self.progress_label.config(
                    text=f"✅ {model_name} downloaded successfully!"
                ))
                self.dialog.after(0, self._check_models)
            else:
                self.dialog.after(0, lambda: self.progress_label.config(
                    text=f"❌ Download failed: {msg}"
                ))
                self.dialog.after(0, lambda: messagebox.showerror(
                    "Download Failed", msg
                ))
        
        threading.Thread(target=download, daemon=True).start()
    
    def _delete_selected_model(self):
        """Delete the selected model"""
        selection = self.model_tree.selection()
        if not selection:
            messagebox.showinfo("No Selection", "Please select a model to delete")
            return
        
        item = self.model_tree.item(selection[0])
        values = item["values"]
        
        # Check if not installed
        if values[0] != "✅":
            messagebox.showinfo("Not Installed", f"{values[1]} is not installed")
            return
        
        model_name = values[1]
        
        # Find the ollama_id
        model_id = None
        for mid, info in MODEL_DATABASE.items():
            if info.name == model_name:
                model_id = info.ollama_id
                break
        
        # If not in database, it might be installed with the raw name
        if not model_id:
            # Try to match by searching installed models
            success, _, installed = self.manager.ollama.get_installed_models()
            for m in installed:
                if model_name in m["name"]:
                    model_id = m["name"]
                    break
        
        if not model_id:
            messagebox.showerror("Error", f"Could not find model ID for {model_name}")
            return
        
        # Confirm deletion
        if not messagebox.askyesno(
            "Delete Model",
            f"Delete {model_name}?\n\nThis cannot be undone."
        ):
            return
        
        def delete():
            success, msg = self.manager.ollama.delete_model(model_id)
            
            if success:
                self.dialog.after(0, lambda: messagebox.showinfo(
                    "Deleted", f"{model_name} has been deleted"
                ))
                self.dialog.after(0, self._check_models)
            else:
                self.dialog.after(0, lambda: messagebox.showerror(
                    "Delete Failed", msg
                ))
        
        threading.Thread(target=delete, daemon=True).start()
    
    def _refresh_models(self):
        """Refresh the model list"""
        self._check_models()
    
    def _test_connection(self):
        """Test the Local AI connection"""
        if not self.ollama_running:
            messagebox.showinfo(
                "Not Running",
                "Please start Ollama first before testing the connection."
            )
            return
        
        # Get installed models
        success, _, models = self.manager.ollama.get_installed_models()
        
        if not success or not models:
            messagebox.showinfo(
                "No Models",
                "Please download a model first before testing."
            )
            return
        
        # Test with first available model
        model_id = models[0]["name"]
        
        self.progress_label.config(text=f"Testing with {model_id}...")
        self.progress_bar.pack(fill=tk.X, pady=(5, 0))
        self.progress_bar.start()
        
        def test():
            try:
                import requests
                response = requests.post(
                    f"{self.manager.ollama.openai_compatible_url}/chat/completions",
                    json={
                        "model": model_id,
                        "messages": [{"role": "user", "content": "Say 'Hello from Local AI!' in exactly those words."}],
                        "max_tokens": 50
                    },
                    timeout=60
                )
                
                self.dialog.after(0, self.progress_bar.stop)
                self.dialog.after(0, lambda: self.progress_bar.pack_forget())
                
                if response.status_code == 200:
                    data = response.json()
                    reply = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    self.dialog.after(0, lambda: self.progress_label.config(
                        text=f"✅ Success! Model responded."
                    ))
                    self.dialog.after(0, lambda: messagebox.showinfo(
                        "Connection Test Successful",
                        f"Local AI is working!\n\n"
                        f"Model: {model_id}\n"
                        f"Response: {reply[:100]}..."
                    ))
                else:
                    self.dialog.after(0, lambda: self.progress_label.config(
                        text=f"❌ Test failed: HTTP {response.status_code}"
                    ))
                    self.dialog.after(0, lambda: messagebox.showerror(
                        "Test Failed",
                        f"Server returned status {response.status_code}"
                    ))
            
            except Exception as e:
                self.dialog.after(0, self.progress_bar.stop)
                self.dialog.after(0, lambda: self.progress_bar.pack_forget())
                self.dialog.after(0, lambda: self.progress_label.config(
                    text=f"❌ Test failed: {str(e)}"
                ))
                self.dialog.after(0, lambda: messagebox.showerror(
                    "Test Failed",
                    str(e)
                ))
        
        threading.Thread(target=test, daemon=True).start()
    
    def _close_dialog(self):
        """Close the dialog"""
        if self.on_complete:
            # Pass back status
            self.on_complete(
                self.ollama_installed,
                self.ollama_running,
                self.models_available
            )
        
        self.dialog.destroy()


# =============================================================================
# STANDALONE TESTING
# =============================================================================

def main():
    """Test the dialog standalone"""
    root = tk.Tk()
    root.title("DocAnalyzer - Test")
    root.geometry("400x200")
    
    def on_complete(installed, running, models):
        print(f"Setup complete: installed={installed}, running={running}, models={models}")
    
    ttk.Button(
        root,
        text="Open Local AI Setup",
        command=lambda: LocalAISetupDialog(root, on_complete).show()
    ).pack(pady=50)
    
    root.mainloop()


if __name__ == "__main__":
    main()
