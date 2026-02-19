"""
local_ai_dialogs.py - Local AI (Ollama) connection and setup dialogs for DocAnalyser.

Extracted from Main.py to reduce file size. Uses a mixin pattern so all
self.xxx references continue to work unchanged.

Methods included:
  - run_via_local_ai()                 Entry point for local AI processing
  - _show_local_ai_dialog()            Setup/connection dialog
  - _show_ollama_launching_dialog()    Auto-launch and polling dialog
"""

import tkinter as tk
from tkinter import ttk, messagebox


class LocalAIMixin:
    """Mixin class providing Local AI (Ollama) dialog methods for DocAnalyzerApp."""

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

