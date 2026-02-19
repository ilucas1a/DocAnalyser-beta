"""
Sources Dialog Module for DocAnalyser

Provides dialogs for adding sources to:
- Documents Library (permanent storage)
- Prompt Context (temporary, for multi-document AI analysis)

Supports:
- Multiple URLs and file paths
- Drag and drop
- YouTube, Substack, web articles, local files
- Documents from the library
- Scheduling (library mode only)

Replaces and extends the former bulk_processing.py module.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import queue
import os
import re
from datetime import datetime, timedelta
from typing import List, Tuple, Optional, Callable, Dict, Any
from urllib.parse import urlparse

# Try to import TkinterDnD for drag-and-drop support
try:
    from tkinterdnd2 import DND_FILES, DND_TEXT, DND_ALL
    TKDND_AVAILABLE = True
except ImportError:
    TKDND_AVAILABLE = False
    DND_ALL = None

# Context Help System
try:
    from context_help import add_help, HELP_TEXTS
    CONTEXT_HELP_AVAILABLE = True
except ImportError:
    CONTEXT_HELP_AVAILABLE = False
    HELP_TEXTS = {}
    def add_help(*args, **kwargs): pass


class SourcesDialog:
    """
    Unified dialog for adding sources to DocAnalyser.
    
    Supports three modes:
    - "library": Save sources to Documents Library (permanent)
    - "prompt_context": Add sources to current prompt context (temporary)
    - "unified": Let user choose between library and prompt context
    
    Features:
    - Enter multiple URLs/file paths
    - Drag and drop files or URLs
    - Add documents from existing library
    - Process all items sequentially
    - Schedule processing for later (library mode only)
    - View results summary
    """
    
    def __init__(self, parent, process_callback: Callable, get_current_settings: Callable,
                 save_to_library_callback: Optional[Callable] = None,
                 ai_process_callback: Optional[Callable] = None,
                 # New parameters for unified mode:
                 attachment_manager: Optional[Any] = None,
                 mode: str = "library",  # "library", "prompt_context", or "unified"
                 status_callback: Optional[Callable] = None,
                 get_provider_callback: Optional[Callable] = None,
                 on_complete_callback: Optional[Callable] = None):
        """
        Initialize the sources dialog.
        
        Args:
            parent: Parent tkinter window
            process_callback: Function to process a single item (extract text).
                             Signature: (url_or_path: str, status_callback: Callable) -> Tuple[bool, str, Optional[str]]
                             Returns: (success, result_text_or_error, title)
            get_current_settings: Function to get current AI provider/model/prompt settings
                                 Returns: dict with 'provider', 'model', 'prompt', 'prompt_text' keys
            save_to_library_callback: Optional function to save results to document library
                                     Signature: (title: str, content: str, source: str, doc_class: str) -> Optional[str]
                                     Returns: document_id if successful, None otherwise
            ai_process_callback: Optional function to run AI analysis on extracted text
                                Signature: (text: str, title: str, status_callback: Callable) -> Tuple[bool, str]
                                Returns: (success, ai_response_or_error)
            attachment_manager: AttachmentManager instance (for prompt_context mode)
            mode: "library", "prompt_context", or "unified"
            status_callback: Function to update main window status bar
            get_provider_callback: Function to get current AI provider name
            on_complete_callback: Function called when dialog closes with changes
        """
        self.parent = parent
        self.process_callback = process_callback
        self.get_current_settings = get_current_settings
        self.save_to_library_callback = save_to_library_callback
        self.ai_process_callback = ai_process_callback
        self.attachment_manager = attachment_manager
        self.mode = mode
        self.status_callback = status_callback
        self.get_provider_callback = get_provider_callback
        self.on_complete_callback = on_complete_callback
        
        # Processing state
        self.is_processing = False
        self.cancel_requested = False
        self.processing_thread = None
        self.results_queue = queue.Queue()
        self.changes_made = False  # Track if any sources were added
        
        # Results tracking
        self.results = {
            'successful': [],        # List of (source, title)
            'failed': [],            # List of (source, error_message)
            'skipped': [],           # List of (source, reason)
            'saved_to_library': [],  # List of titles (source docs)
            'added_to_context': [],  # List of titles (prompt context)
            'ai_processed': [],      # List of (source, title)
            'ai_failed': [],         # List of (source, error)
            'ai_saved': []           # List of titles (AI response docs)
        }
        
        # Schedule timer
        self.schedule_timer = None
        self.scheduled_time = None
        
        # Create window
        self._create_window()
        
    def _create_window(self):
        """Create the sources dialog window UI."""
        self.window = tk.Toplevel(self.parent)
        
        # Set title based on mode
        if self.mode == "unified":
            self.window.title("Add Files/URLs")
        elif self.mode == "prompt_context":
            self.window.title("Add to Prompt Context")
        else:
            self.window.title("Bulk Import")
        
        self.window.geometry("500x520")
        self.window.minsize(400, 350)
        self.window.configure(bg='#dcdad5')  # Match main window background
        
        # Configure grid
        self.window.columnconfigure(0, weight=1)
        
        current_row = 0
        
        # === Auto-save behavior: always save to library AND add to context ===
        # No destination frame needed - behavior is automatic
        self.save_to_library_var = tk.BooleanVar(value=True)
        self.add_to_context_var = tk.BooleanVar(value=True)
        self.destination_var = tk.StringVar(value="both")
        
        # Info label about auto-save behavior (shown at top)
        if self.mode == "unified":
            info_frame = ttk.Frame(self.window, padding=(10, 10, 10, 0))
            info_frame.grid(row=current_row, column=0, sticky="ew")
            
            self.autosave_label = ttk.Label(
                info_frame,
                text="📚 All items are automatically saved to Documents Library and added to current prompt",
                font=('Segoe UI', 9),
                foreground='#006600'
            )
            self.autosave_label.pack(anchor="w")
            current_row += 1
        
        # === Header Frame ===
        header_frame = ttk.Frame(self.window, padding="10")
        header_frame.grid(row=current_row, column=0, sticky="ew")
        current_row += 1
        
        ttk.Label(
            header_frame, 
            text="Add file(s)/URL(s) by dragging-and-dropping, browsing, or selecting from Library:",
            foreground='red'
        ).pack(anchor="w")
        
        support_text = "Supports: YouTube, Substack, web articles, local files (.pdf, .docx, .txt, etc.)"
        ttk.Label(
            header_frame,
            text=support_text,
            font=('Segoe UI', 9),
            foreground='gray'
        ).pack(anchor="w")
        
        # === Input Frame ===
        input_frame = ttk.Frame(self.window, padding="10")
        input_frame.grid(row=current_row, column=0, sticky="nsew")
        input_frame.columnconfigure(0, weight=1)
        input_frame.rowconfigure(1, weight=1)  # Listbox row gets the weight
        self.window.rowconfigure(current_row, weight=1)
        current_row += 1
        
        # === Drop/Paste Entry Field ===
        # This Entry widget accepts drag-and-drop and paste (Ctrl+V)
        drop_frame = ttk.Frame(input_frame)
        drop_frame.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        drop_frame.columnconfigure(0, weight=1)
        
        self.drop_entry_var = tk.StringVar()
        self.drop_entry = tk.Entry(drop_frame, textvariable=self.drop_entry_var, font=('Consolas', 10), bg='#FFFDE6')
        self.drop_entry.grid(row=0, column=0, sticky="ew")
        if HELP_TEXTS:
            add_help(self.drop_entry, **HELP_TEXTS.get("sources_drop_entry", {"title": "Input", "description": "Drop or paste URLs/files here"}))
        
        # Placeholder text
        self.drop_entry.insert(0, "Drop files/URLs here, or paste/type and press Enter...")
        self.drop_entry.config(foreground='gray')
        self.drop_entry_has_placeholder = True
        
        def on_entry_focus_in(event):
            if self.drop_entry_has_placeholder:
                self.drop_entry.delete(0, tk.END)
                self.drop_entry.config(foreground='black')
                self.drop_entry_has_placeholder = False
        
        def on_entry_focus_out(event):
            if not self.drop_entry_var.get().strip():
                self.drop_entry.insert(0, "Drop files/URLs here, or paste/type and press Enter...")
                self.drop_entry.config(foreground='gray')
                self.drop_entry_has_placeholder = True
        
        self.drop_entry.bind('<FocusIn>', on_entry_focus_in)
        self.drop_entry.bind('<FocusOut>', on_entry_focus_out)
        
        # Bind Enter key to add the item
        self.drop_entry.bind('<Return>', self._add_from_entry)
        
        # Setup drag-and-drop on the Entry widget (this works!)
        self._setup_drag_drop()
        
        # Listbox with scrollbar
        list_frame = ttk.Frame(input_frame)
        list_frame.grid(row=1, column=0, sticky="nsew")
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        
        # Use Listbox with extended selection mode (Ctrl+click, Shift+click)
        self.input_listbox = tk.Listbox(
            list_frame,
            selectmode=tk.EXTENDED,
            font=('Consolas', 10),
            height=10,
            activestyle='dotbox',
            bg='#FFFDE6'
        )
        self.input_listbox.grid(row=0, column=0, sticky="nsew")
        
        # Ensure minimum height for the list_frame
        list_frame.config(height=120)
        if HELP_TEXTS:
            add_help(self.input_listbox, **HELP_TEXTS.get("sources_listbox", {"title": "Sources List", "description": "Items to process"}))
        
        # Scrollbars
        y_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.input_listbox.yview)
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll = ttk.Scrollbar(list_frame, orient="horizontal", command=self.input_listbox.xview)
        x_scroll.grid(row=1, column=0, sticky="ew")
        self.input_listbox.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        
        # Bind Delete key to remove selected items from listbox
        self.input_listbox.bind('<Delete>', self._delete_selected)
        self.input_listbox.bind('<BackSpace>', self._delete_selected)
        
        # Item count and selection info label
        self.count_label = ttk.Label(input_frame, text="0 items", foreground='gray')
        self.count_label.grid(row=2, column=0, sticky="w", pady=(5, 0))
        
        # Bind selection changes to update count label
        self.input_listbox.bind('<<ListboxSelect>>', self._update_item_count)
        
        # === Buttons Frame (Row 1: Add buttons and Fetch) ===
        buttons_frame1 = ttk.Frame(self.window, padding=(10, 5, 10, 0))
        buttons_frame1.grid(row=current_row, column=0, sticky="ew")
        current_row += 1
        
        # Left side - Browse dropdown (matches main UI style)
        self.browse_menu_btn = tk.Menubutton(
            buttons_frame1, 
            text="Browse... ▼", 
            relief=tk.RAISED,
            font=('Segoe UI', 9), 
            width=12
        )
        self.browse_menu_btn.pack(side="left", padx=(0, 5))
        
        browse_menu = tk.Menu(self.browse_menu_btn, tearoff=0)
        self.browse_menu_btn.config(menu=browse_menu)
        
        browse_menu.add_command(
            label="📁 Files",
            command=self._browse_files
        )
        browse_menu.add_command(
            label="🌐 Web URL",
            command=self._open_browser
        )
        browse_menu.add_command(
            label="📚 Documents Library",
            command=self._add_from_library
        )
        
        if HELP_TEXTS:
            add_help(self.browse_menu_btn, **HELP_TEXTS.get("sources_browse_dropdown", 
                {"title": "Browse", "description": "Browse for files, open browser for URLs, or select from Documents Library"}))
        
        # Right side - Fetch button with schedule dropdown
        self.process_btn_frame = ttk.Frame(buttons_frame1)
        self.process_btn_frame.pack(side="right")
        
        # Combined Fetch button with schedule dropdown (single button, no double arrows)
        self.process_btn = tk.Menubutton(
            self.process_btn_frame,
            text="📥 Add to Context ▼",
            relief=tk.RAISED,
            font=('Segoe UI', 9),
            width=18
        )
        self.process_btn.pack(side="right")
        
        # The menu will be attached in _update_process_button
        self.process_menu = tk.Menu(self.process_btn, tearoff=0)
        self.process_btn.config(menu=self.process_menu)
        
        self.process_menu.add_command(label="📥 Add to Context Now", command=self._start_processing)
        self.process_menu.add_separator()
        self.process_menu.add_command(label="⏰ In 5 minutes", command=lambda: self._schedule_processing(5))
        self.process_menu.add_command(label="⏰ In 15 minutes", command=lambda: self._schedule_processing(15))
        self.process_menu.add_command(label="⏰ In 30 minutes", command=lambda: self._schedule_processing(30))
        self.process_menu.add_command(label="⏰ In 1 hour", command=lambda: self._schedule_processing(60))
        self.process_menu.add_separator()
        self.process_menu.add_command(label="📅 Schedule for specific time...", command=self._schedule_custom)
        
        # Remove the old separate schedule button reference
        self.schedule_btn = None
        if HELP_TEXTS:
            add_help(self.process_btn, **HELP_TEXTS.get("sources_fetch_button", {"title": "Fetch", "description": "Process items"}))
        
        # === Buttons Frame (Row 2: Remove/Clear and Cancel) ===
        buttons_frame2 = ttk.Frame(self.window, padding=(10, 5, 10, 5))
        buttons_frame2.grid(row=current_row, column=0, sticky="ew")
        current_row += 1
        
        # Left side - Remove and Clear
        remove_btn = ttk.Button(
            buttons_frame2,
            text="🗑️ Remove",
            command=self._delete_selected
        )
        remove_btn.pack(side="left", padx=(0, 5))
        if HELP_TEXTS:
            add_help(remove_btn, **HELP_TEXTS.get("sources_remove_button", {"title": "Remove", "description": "Remove selected"}))
        
        clear_btn = ttk.Button(
            buttons_frame2,
            text="🧹 Clear",
            command=self._clear_input
        )
        clear_btn.pack(side="left")
        if HELP_TEXTS:
            add_help(clear_btn, **HELP_TEXTS.get("sources_clear_button", {"title": "Clear", "description": "Clear all"}))
        
        # Right side - Cancel button
        self.cancel_btn = ttk.Button(
            buttons_frame2,
            text="Cancel",
            command=self._cancel_processing,
            state=tk.DISABLED
        )
        self.cancel_btn.pack(side="right")
        if HELP_TEXTS:
            add_help(self.cancel_btn, **HELP_TEXTS.get("sources_cancel_button", {"title": "Cancel", "description": "Stop processing"}))
        
        # Schedule menu is now part of process_btn dropdown
        
        # Update button text based on mode
        self._update_process_button()
        
        # === Progress Frame ===
        progress_frame = ttk.Frame(self.window, padding="10")
        progress_frame.grid(row=current_row, column=0, sticky="ew")
        progress_frame.columnconfigure(0, weight=1)
        current_row += 1
        
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(
            progress_frame,
            variable=self.progress_var,
            maximum=100
        )
        self.progress_bar.grid(row=0, column=0, sticky="ew")
        
        self.status_label = ttk.Label(progress_frame, text="Ready")
        self.status_label.grid(row=1, column=0, sticky="w", pady=(5, 0))
        
        self.schedule_label = ttk.Label(progress_frame, text="", foreground='blue')
        self.schedule_label.grid(row=2, column=0, sticky="w")
        
        # === Settings Reminder Frame (only for library mode) ===
        if self.mode != "prompt_context":
            reminder_frame = ttk.Frame(self.window, padding="10")
            reminder_frame.grid(row=current_row, column=0, sticky="ew")
            current_row += 1
            
            settings = self.get_current_settings()
            provider = settings.get('provider', 'Not selected')
            model = settings.get('model', 'Not selected')
            
            reminder_text = f"⚙️ Current AI: {provider} / {model}"
            self.reminder_label = ttk.Label(
                reminder_frame,
                text=reminder_text,
                font=('Segoe UI', 9),
                foreground='#666666'
            )
            self.reminder_label.pack(anchor="w")

        # Handle window close
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)
        
        # Load existing attachments into the listbox (for prompt_context mode)
        self._load_existing_attachments()
        
        # Start polling for results
        self._poll_results()
    
    def _on_destination_change(self):
        """Handle destination checkbox change - now always both enabled."""
        # Auto-save behavior: always save to library AND add to context
        # These vars are kept for compatibility but always True
        if hasattr(self, 'save_to_library_var'):
            self.save_to_library_var.set(True)
        if hasattr(self, 'add_to_context_var'):
            self.add_to_context_var.set(True)
        
        save_to_lib = True
        add_to_ctx = True
        
        # Update destination_var for compatibility with existing code
        if add_to_ctx and not save_to_lib:
            self.destination_var.set("prompt_context")
        elif save_to_lib and not add_to_ctx:
            self.destination_var.set("library")
        else:  # Both selected
            self.destination_var.set("both")
        
        # Update note text based on selection
        if hasattr(self, 'context_note'):
            if add_to_ctx and save_to_lib:
                self.context_note.config(
                    text="✅ Items will be saved to library AND added to current analysis",
                    foreground='#006600'  # Dark green
                )
            elif add_to_ctx:
                self.context_note.config(
                    text="⚠️ Items will be cleared when you close the app or start a new document",
                    foreground='#996600'  # Dark orange/brown
                )
            else:
                self.context_note.config(
                    text="💡 Tip: Select both to save AND use in current analysis",
                    foreground='#666666'  # Gray
                )
        
        # Schedule options are now in the dropdown menu (always available)
        pass
        
        # Update process button text (only if it exists)
        if hasattr(self, 'process_btn'):
            self._update_process_button()
    
    def _update_process_button(self):
        """Update the process button text - now always shows Add to Context."""
        # With auto-save behavior, always saving to library AND adding to context
        if hasattr(self, 'process_btn') and self.process_btn:
            self.process_btn.config(text="📥 Add to Context ▼")
    
    def _load_existing_attachments(self):
        """
        Load existing attachments from the attachment_manager into the listbox.
        
        This allows users to see what's already been added when they reopen the dialog.
        Items are shown with a checkmark prefix to indicate they're already processed.
        """
        if not self.attachment_manager:
            return
        
        # Only show existing attachments if in prompt_context mode or unified mode
        if self.mode == "library":
            return
        
        existing_count = 0
        for att in self.attachment_manager.attachments:
            # Get display name
            filename = att.get('filename', att.get('path', 'Unknown'))
            source = att.get('source', att.get('path', ''))
            
            # Format: show with checkmark to indicate already added
            display = f"✓ {filename}"
            if att.get('from_sources_dialog'):
                display += " [in context]"
            elif att.get('from_library'):
                display += " [from library]"
            
            self.input_listbox.insert(tk.END, display)
            
            # Color it differently to show it's already processed
            idx = self.input_listbox.size() - 1
            self.input_listbox.itemconfig(idx, fg='#006600')  # Dark green
            
            existing_count += 1
        
        if existing_count > 0:
            self._update_item_count()
            self.status_label.config(text=f"{existing_count} item(s) already in prompt context")
        
    def _setup_drag_drop(self):
        """Set up drag-and-drop support on the Entry widget."""
        if not TKDND_AVAILABLE:
            print("TkinterDnD not available - drag-drop disabled for Sources dialog")
            return
        
        try:
            # Register drag-and-drop on the Entry widget (same approach as main window)
            self.drop_entry.drop_target_register(DND_ALL if DND_ALL else DND_FILES)
            self.drop_entry.dnd_bind('<<Drop>>', self._on_drop)
            print("Drag-and-drop enabled on Sources dialog entry field")
        except Exception as e:
            print(f"Could not enable drag-drop for Sources dialog: {e}")
            import traceback
            traceback.print_exc()
            
    def _on_drop(self, event):
        """Handle dropped files or text (including URLs from browsers)."""
        data = event.data
        
        # Clear placeholder if present
        if self.drop_entry_has_placeholder:
            self.drop_entry.delete(0, tk.END)
            self.drop_entry.config(foreground='black')
            self.drop_entry_has_placeholder = False
        
        # Parse dropped data
        items = self._parse_drop_data(data)
        
        # Add items to listbox
        added = 0
        existing = set(self._get_items())
        
        for item in items:
            if item and item not in existing:  # Avoid duplicates
                self.input_listbox.insert(tk.END, item)
                existing.add(item)
                added += 1
        
        self._update_item_count()
        
        # Clear the entry field after successful drop
        self.drop_entry.delete(0, tk.END)
        
        if added > 0:
            self.status_label.config(text=f"Added {added} item(s) via drag-and-drop")
        
        return event.action
    
    def _add_from_entry(self, event=None):
        """Add item(s) from the entry field to the listbox."""
        # Don't process if placeholder is showing
        if self.drop_entry_has_placeholder:
            return
        
        text = self.drop_entry_var.get().strip()
        if not text:
            return
        
        # Parse the text (could be URL, file path, or multiple items)
        items = self._parse_drop_data(text)
        
        # Add items to listbox
        added = 0
        existing = set(self._get_items())
        for item in items:
            if item and item not in existing:
                self.input_listbox.insert(tk.END, item)
                existing.add(item)
                added += 1
        
        self._update_item_count()
        
        # Clear the entry field
        self.drop_entry.delete(0, tk.END)
        
        if added > 0:
            self.status_label.config(text=f"Added {added} item(s)")
        elif items:
            self.status_label.config(text="Item already in list")
        
    def _parse_drop_data(self, data: str) -> List[str]:
        """Parse dropped data into list of paths/URLs."""
        items = []
        data = data.strip()
        
        # Check if it's a URL first (most common case for browser drops)
        if data.startswith(('http://', 'https://')):
            # Could be single URL or multiple URLs separated by newlines
            if '\n' in data:
                items.extend([url.strip() for url in data.split('\n') if url.strip()])
            else:
                items.append(data)
        
        # Handle Windows file drops (may be in braces or space-separated)
        elif data.startswith('{'):
            # Multiple files in braces
            matches = re.findall(r'\{([^}]+)\}', data)
            items.extend(matches)
        
        elif '\n' in data:
            # Newline separated (could be files or URLs)
            for line in data.split('\n'):
                line = line.strip()
                if line:
                    items.append(line)
        
        else:
            # Single item - could be file path or URL
            # Check if it exists as a file first
            if os.path.exists(data):
                items.append(data)
            elif ' ' in data and not data.startswith(('http://', 'https://')):
                # Could be space-separated paths, but be careful
                # Only split if none of the parts look like a URL
                parts = data.split()
                has_url = any(p.startswith(('http://', 'https://')) for p in parts)
                if has_url:
                    items.append(data)  # Keep as-is if it contains a URL
                else:
                    items.extend(parts)
            else:
                items.append(data)
        
        # Process items - extract URLs from .url files and clean up
        processed_items = []
        for item in items:
            item = item.strip()
            if not item:
                continue
            
            # Remove any trailing/leading quotes that browsers sometimes add
            if (item.startswith('"') and item.endswith('"')) or \
               (item.startswith("'") and item.endswith("'")):
                item = item[1:-1]
                
            # Handle .url files (Windows Internet Shortcuts)
            if item.lower().endswith('.url') and os.path.isfile(item):
                extracted_url = self._extract_url_from_shortcut(item)
                if extracted_url:
                    processed_items.append(extracted_url)
                else:
                    processed_items.append(item)
            else:
                processed_items.append(item)
        
        print(f"Parsed drop data into {len(processed_items)} items: {processed_items[:3]}..." 
              if len(processed_items) > 3 else f"Parsed drop data into {len(processed_items)} items: {processed_items}")
                
        return processed_items
    
    def _extract_url_from_shortcut(self, filepath: str) -> Optional[str]:
        """Extract the actual URL from a Windows .url shortcut file."""
        try:
            import configparser
            config = configparser.ConfigParser(interpolation=None)
            config.read(filepath, encoding='utf-8')
            
            if 'InternetShortcut' in config and 'URL' in config['InternetShortcut']:
                url = config['InternetShortcut']['URL']
                print(f"📎 Extracted URL from shortcut: {url}")
                return url
        except Exception as e:
            print(f"❌ Error reading .url file: {e}")
        
        return None
        
    def _update_item_count(self, event=None):
        """Update the item count label with selection info and auto-save reminder."""
        items = self._get_items()
        count = len(items)
        selected = self.input_listbox.curselection()
        sel_count = len(selected)
        
        # Count pending items (not yet processed - no checkmark)
        pending_count = sum(1 for item in items if not item.startswith('✓ '))
        
        if sel_count > 0:
            base_text = f"{count} item{'s' if count != 1 else ''} ({sel_count} selected)"
        else:
            base_text = f"{count} item{'s' if count != 1 else ''}"
        
        # Add pending info if there are unprocessed items
        if pending_count > 0 and pending_count < count:
            base_text += f" • {pending_count} pending"
        
        self.count_label.config(text=base_text)
        
    def _get_items(self) -> List[str]:
        """Get list of items from the listbox."""
        return list(self.input_listbox.get(0, tk.END))
        
    def _browse_files(self):
        """Open file browser to add files."""
        filetypes = [
            ("All supported files", "*.pdf;*.docx;*.doc;*.txt;*.md;*.html;*.htm;*.rtf;*.url;*.csv;*.json"),
            ("URL shortcuts", "*.url"),
            ("PDF files", "*.pdf"),
            ("Word documents", "*.docx;*.doc"),
            ("Text files", "*.txt;*.md"),
            ("HTML files", "*.html;*.htm"),
            ("Data files", "*.csv;*.json"),
            ("All files", "*.*")
        ]
        
        files = filedialog.askopenfilenames(
            title="Select files to add",
            filetypes=filetypes
        )
        
        if files:
            existing = set(self._get_items())
            for f in files:
                # Handle .url files - extract the actual URL
                if f.lower().endswith('.url'):
                    extracted_url = self._extract_url_from_shortcut(f)
                    if extracted_url and extracted_url not in existing:
                        self.input_listbox.insert(tk.END, extracted_url)
                        existing.add(extracted_url)
                elif f not in existing:
                    self.input_listbox.insert(tk.END, f)
                    existing.add(f)
            self._update_item_count()
            
    def _clear_input(self):
        """Clear the input listbox and optionally clear attachments."""
        # Check if there are any already-processed attachments
        has_attachments = False
        for i in range(self.input_listbox.size()):
            if self.input_listbox.get(i).startswith("✓ "):
                has_attachments = True
                break
        
        if has_attachments and self.attachment_manager:
            # Ask user if they want to clear attachments too
            from tkinter import messagebox
            result = messagebox.askyesnocancel(
                "Clear Items",
                "Some items are already added to prompt context.\n\n"
                "Yes = Clear ALL (including from prompt context)\n"
                "No = Clear only pending items\n"
                "Cancel = Don't clear anything"
            )
            
            if result is None:  # Cancel
                return
            elif result:  # Yes - clear all including attachments
                self.attachment_manager.clear_all()
                self.changes_made = True
                self.input_listbox.delete(0, tk.END)
                self.status_label.config(text="Cleared all items including prompt context")
            else:  # No - only clear pending (non-checkmarked) items
                # Delete non-checkmarked items in reverse order
                for idx in reversed(range(self.input_listbox.size())):
                    if not self.input_listbox.get(idx).startswith("✓ "):
                        self.input_listbox.delete(idx)
                self.status_label.config(text="Cleared pending items (kept context items)")
        else:
            # No attachments, just clear the listbox
            self.input_listbox.delete(0, tk.END)
        
        self._update_item_count()
    
    def _delete_selected(self, event=None):
        """Delete selected items from the listbox and attachment_manager if applicable."""
        selected = self.input_listbox.curselection()
        if not selected:
            return
        
        # Track if we removed any attachments
        removed_attachments = 0
        
        # Delete in reverse order to maintain correct indices
        for idx in reversed(selected):
            item_text = self.input_listbox.get(idx)
            
            # Check if this is an already-processed attachment (starts with checkmark)
            if item_text.startswith("✓ ") and self.attachment_manager:
                # Extract the filename (remove checkmark and any suffix like " [in context]")
                filename = item_text[2:]  # Remove "✓ "
                if " [" in filename:
                    filename = filename.split(" [")[0]
                
                # Find and remove from attachment_manager
                for i, att in enumerate(self.attachment_manager.attachments):
                    att_filename = att.get('filename', '')
                    if att_filename == filename:
                        self.attachment_manager.attachments.pop(i)
                        removed_attachments += 1
                        self.changes_made = True
                        break
            
            self.input_listbox.delete(idx)
        
        self._update_item_count()
        
        if removed_attachments > 0:
            self.status_label.config(text=f"Removed {removed_attachments} item(s) from prompt context")
    
    def _open_browser(self):
        """Open the default web browser so user can find URLs to drag/copy."""
        import webbrowser
        
        try:
            # Open a useful starting page - YouTube is common for this app
            webbrowser.open('https://www.youtube.com')
        except Exception:
            self.status_label.config(text="Could not open browser")
    
    def _add_from_library(self):
        """Open library picker to add documents."""
        try:
            from document_library import get_all_documents, load_document_entries
            from utils import entries_to_text
        except ImportError as e:
            messagebox.showerror("Error", f"Could not import library functions: {e}")
            return
        
        # Get all documents from library
        documents = get_all_documents()
        if not documents:
            messagebox.showinfo("Library Empty", "No documents in library yet.")
            return
        
        # Auto-switch destination to prompt_context when adding from library
        # (documents are already in library, so saving them there again makes no sense)
        if self.destination_var.get() == "library":
            self.destination_var.set("prompt_context")
            self._on_destination_change()
            self.status_label.config(text="Switched to 'Add to prompt context' (documents already in library)")
        
        # Create picker dialog
        picker = tk.Toplevel(self.window)
        picker.title("Add from Library")
        picker.geometry("600x450")
        picker.transient(self.window)
        picker.grab_set()
        picker.configure(bg='#dcdad5')  # Match main window background
        
        # Instructions
        ttk.Label(
            picker, 
            text="Select documents to add (Ctrl+click for multiple):",
            font=('Segoe UI', 10)
        ).pack(padx=10, pady=(10, 5), anchor=tk.W)
        
        # Listbox with scrollbar
        list_frame = ttk.Frame(picker)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        listbox = tk.Listbox(
            list_frame,
            selectmode=tk.EXTENDED,
            font=('Segoe UI', 10)
        )
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        listbox.config(yscrollcommand=scrollbar.set)
        
        # Store document data
        doc_data = []
        existing_items = set(self._get_items())
        
        # Populate list (sorted by date, newest first)
        sorted_docs = sorted(documents, key=lambda d: d.get('added', ''), reverse=True)
        for doc in sorted_docs:
            doc_id = doc.get('id', '')
            title = doc.get('title', 'Untitled')
            doc_type = doc.get('type', 'unknown')
            
            # Format display string
            type_icon = {
                'youtube': '🎬',
                'web': '🌐',
                'file': '📄',
                'audio_transcription': '🎤',
                'conversation_thread': '💬',
                'substack': '📰'
            }.get(doc_type, '📄')
            
            display = f"{type_icon} {title[:55]}{'...' if len(title) > 55 else ''}"
            
            # Check if already in our list
            source = doc.get('source', '')
            if source in existing_items or f"library://{doc_id}" in existing_items:
                display += " [already added]"
            
            listbox.insert(tk.END, display)
            doc_data.append({
                'id': doc_id,
                'title': title,
                'type': doc_type,
                'source': source
            })
        
        # Button frame
        btn_frame = ttk.Frame(picker)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        
        def add_selected():
            selection = listbox.curselection()
            if not selection:
                messagebox.showinfo("No Selection", "Please select at least one document.")
                return
            
            added = 0
            for idx in selection:
                doc = doc_data[idx]
                
                # Use library:// prefix for library documents
                item_id = f"library://{doc['id']}"
                
                if item_id not in existing_items:
                    # Add with special library:// prefix
                    self.input_listbox.insert(tk.END, item_id)
                    existing_items.add(item_id)
                    added += 1
            
            self._update_item_count()
            
            if added > 0:
                self.status_label.config(text=f"Added {added} document(s) from library")
            
            picker.destroy()
        
        ttk.Button(btn_frame, text="Add Selected", command=add_selected, width=15).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=picker.destroy, width=10).pack(side=tk.RIGHT, padx=5)
        ttk.Label(btn_frame, text=f"{len(documents)} documents in library", foreground='gray').pack(side=tk.RIGHT, padx=10)
        
    def _start_processing(self):
        """Start processing all items."""
        items = self._get_items()
        
        if not items:
            messagebox.showwarning("No Items", "Please add URLs, files, or library documents to process.")
            return
        
        dest = self.destination_var.get()
        
        # Check for local AI context warning (prompt_context mode only)
        if dest == 'prompt_context' and self.get_provider_callback and self.attachment_manager:
            try:
                from attachment_handler import check_local_ai_context_warning
                
                # Estimate words (rough: 500 words per item average)
                estimated_words = len(items) * 500 + self.attachment_manager.get_total_words()
                
                warning = check_local_ai_context_warning(
                    provider=self.get_provider_callback(),
                    total_words=estimated_words,
                    attachment_count=len(items) + self.attachment_manager.get_attachment_count()
                )
                
                if warning:
                    if not messagebox.askyesno("Local AI Context Warning", warning):
                        return
            except ImportError:
                pass  # attachment_handler not available
            
        # Clear any scheduled processing
        if self.schedule_timer:
            self.window.after_cancel(self.schedule_timer)
            self.schedule_timer = None
            self.scheduled_time = None
            self.schedule_label.config(text="")
            
        # Reset results
        self.results = {
            'successful': [],
            'failed': [],
            'skipped': [],
            'saved_to_library': [],
            'added_to_context': []
        }
        
        # Update UI state
        self.is_processing = True
        self.cancel_requested = False
        self.process_btn.config(state=tk.DISABLED)
        if hasattr(self, 'schedule_btn') and self.schedule_btn:
            self.schedule_btn.config(state=tk.DISABLED)
        self.cancel_btn.config(state=tk.NORMAL)
        self.input_listbox.config(state=tk.DISABLED)
        self.status_label.config(foreground='black')  # Reset color from previous run
        
        # Start processing thread
        self.processing_thread = threading.Thread(
            target=self._process_items,
            args=(items,),
            daemon=True
        )
        self.processing_thread.start()
        
    def _process_items(self, items: List[str]):
        """Process all items (runs in separate thread)."""
        total = len(items)
        dest = self.destination_var.get()
        
        # Get checkbox states for status messages
        save_to_lib = self.save_to_library_var.get() if hasattr(self, 'save_to_library_var') else False
        add_to_ctx = self.add_to_context_var.get() if hasattr(self, 'add_to_context_var') else False
        
        for i, item in enumerate(items):
            if self.cancel_requested:
                self.results_queue.put(('cancelled', None, None, None))
                return
            
            # Generate a friendly display name for the item
            display_name = self._get_display_name(item)
            
            # Build descriptive status message
            action_parts = ["Fetching"]
            if add_to_ctx and save_to_lib:
                suffix = " (saving to library & adding to prompt)"
            elif add_to_ctx:
                suffix = " (adding to current prompt)"
            elif save_to_lib:
                suffix = " (saving to library)"
            else:
                suffix = ""
                
            # Update progress
            progress = (i / total) * 100
            status_msg = f"Fetching {i+1}/{total}: {display_name}{suffix}"
            self.results_queue.put(('progress', progress, status_msg, None))
            
            # Check if it's a library document
            if item.startswith('library://'):
                doc_id = item[10:]  # Remove 'library://' prefix
                self._process_library_item(doc_id, dest)
                continue
            
            # Validate item
            item_type = self._detect_item_type(item)
            
            if item_type == 'invalid':
                self.results_queue.put(('skipped', item, "Invalid URL or file path", None))
                continue
                
            if item_type == 'file' and not os.path.exists(item):
                self.results_queue.put(('skipped', item, "File not found", None))
                continue
                
            # Process item - extract text
            try:
                success, result, title = self.process_callback(
                    item,
                    lambda msg: self.results_queue.put(('status', None, msg, None))
                )
                
                if success:
                    extracted_text = result
                    doc_title = title or item
                    
                    # Show what we're doing with the content
                    if add_to_ctx:
                        self.results_queue.put(('status', None, f"Adding '{doc_title}' to current prompt...", None))
                    
                    # Queue success with destination info
                    self.results_queue.put(('success', item, doc_title, extracted_text))
                else:
                    self.results_queue.put(('failed', item, result, None))
                    
            except Exception as e:
                self.results_queue.put(('failed', item, str(e), None))
                
        # Done
        self.results_queue.put(('complete', None, None, None))
    
    def _get_display_name(self, item: str) -> str:
        """Get a friendly display name for an item."""
        # Library document - get actual title from database
        if item.startswith('library://'):
            try:
                from document_library import get_document_by_id
                doc_id = item[10:]  # Remove 'library://' prefix
                doc = get_document_by_id(doc_id)
                if doc:
                    title = doc.get('title', 'Untitled')
                    return f"Library: {title[:40]}" + ('...' if len(title) > 40 else '')
            except:
                pass
            return "library document"
        
        # YouTube URL
        if 'youtube.com' in item or 'youtu.be' in item:
            return "YouTube video"
        
        # Substack URL
        if 'substack.com' in item:
            return "Substack article"
        
        # Local file - show filename
        if os.path.isfile(item):
            return os.path.basename(item)
        
        # URL - show domain and path
        if item.startswith(('http://', 'https://')):
            try:
                parsed = urlparse(item)
                domain = parsed.netloc.replace('www.', '')
                path = parsed.path[:30] + '...' if len(parsed.path) > 30 else parsed.path
                return f"{domain}{path}" if path and path != '/' else domain
            except:
                return item[:50]
        
        # Fallback - truncate if needed
        return item[:50] + '...' if len(item) > 50 else item
    
    def _process_library_item(self, doc_id: str, dest: str):
        """Process a library document."""
        try:
            from document_library import get_document_by_id, load_document_entries
            from utils import entries_to_text, entries_to_text_with_speakers
            
            # Get checkbox states
            save_to_lib = self.save_to_library_var.get() if hasattr(self, 'save_to_library_var') else False
            add_to_ctx = self.add_to_context_var.get() if hasattr(self, 'add_to_context_var') else False
            
            # Check if trying to save library item back to library only (redundant)
            if save_to_lib and not add_to_ctx:
                self.results_queue.put(('skipped', f"library://{doc_id}", 
                    "Already in library - check 'Add to prompt context' to use this document", None))
                return
            
            doc = get_document_by_id(doc_id)
            if not doc:
                self.results_queue.put(('failed', f"library://{doc_id}", "Document not found in library", None))
                return
            
            title = doc.get('title', 'Untitled')
            
            # Show loading status
            self.results_queue.put(('status', None, f"Loading from library: {title}...", None))
            
            entries = load_document_entries(doc_id)
            if not entries:
                self.results_queue.put(('failed', f"library://{doc_id}", "Could not load document content", None))
                return
            
            # Convert entries to text
            if doc.get('type') == 'audio_transcription':
                text = entries_to_text_with_speakers(entries)
            else:
                text = entries_to_text(entries)
            
            # Show what we're doing with the content
            if add_to_ctx:
                self.results_queue.put(('status', None, f"Adding '{title}' to current prompt...", None))
            
            self.results_queue.put(('success', f"library://{doc_id}", title, text))
            
        except Exception as e:
            self.results_queue.put(('failed', f"library://{doc_id}", str(e), None))
        
    def _detect_item_type(self, item: str) -> str:
        """Detect whether item is a URL, file path, or invalid."""
        item = item.strip()
        
        # Library items handled separately
        if item.startswith('library://'):
            return 'library'
        
        # Check if it's a URL
        if item.startswith(('http://', 'https://', 'www.')):
            return 'url'
            
        # Check if it looks like a file path
        if os.path.isabs(item) or item.startswith(('./', '../')):
            return 'file'
            
        # Check for Windows drive letter
        if len(item) > 2 and item[1] == ':':
            return 'file'
            
        # Check if file exists (relative path)
        if os.path.exists(item):
            return 'file'
            
        # Could be a partial URL
        parsed = urlparse('http://' + item)
        if '.' in parsed.netloc:
            return 'url'
            
        return 'invalid'
        
    def _poll_results(self):
        """Poll the results queue and update UI."""
        # Get checkbox states for determining destination
        save_to_lib = self.save_to_library_var.get() if hasattr(self, 'save_to_library_var') else False
        add_to_ctx = self.add_to_context_var.get() if hasattr(self, 'add_to_context_var') else False
        
        # Fallback to destination_var for non-unified modes
        if not hasattr(self, 'save_to_library_var'):
            dest = self.destination_var.get()
            save_to_lib = (dest == 'library')
            add_to_ctx = (dest == 'prompt_context')
        
        try:
            while True:
                msg_type, source, message, content = self.results_queue.get_nowait()
                
                if msg_type == 'progress':
                    self.progress_var.set(source)  # source is progress value
                    self.status_label.config(text=message)
                    
                elif msg_type == 'status':
                    self.status_label.config(text=message)
                    
                elif msg_type == 'success':
                    self.results['successful'].append((source, message))
                    
                    # Handle based on checkbox states (can do BOTH now)
                    
                    # Save to library if checkbox is checked
                    if save_to_lib:
                        if self.save_to_library_callback and content:
                            try:
                                doc_id = self.save_to_library_callback(message, content, source, 'source')
                                if doc_id:
                                    self.results['saved_to_library'].append(message)
                                    self.changes_made = True
                            except Exception as e:
                                print(f"Failed to save to library: {e}")
                    
                    # Add to prompt context if checkbox is checked
                    if add_to_ctx:
                        if self.attachment_manager and content:
                            try:
                                result = self.attachment_manager.add_from_text(
                                    title=message,
                                    text=content,
                                    source=source
                                )
                                if not result.get('error'):
                                    self.results['added_to_context'].append(message)
                                    self.changes_made = True
                            except Exception as e:
                                print(f"Failed to add to prompt context: {e}")
                            
                elif msg_type == 'failed':
                    self.results['failed'].append((source, message))
                    
                elif msg_type == 'skipped':
                    self.results['skipped'].append((source, message))
                    
                elif msg_type == 'complete':
                    self._processing_complete()
                    
                elif msg_type == 'cancelled':
                    self._processing_cancelled()
                    
        except queue.Empty:
            pass
            
        # Continue polling if window exists
        if self.window.winfo_exists():
            self.window.after(100, self._poll_results)
            
    def _processing_complete(self):
        """Handle processing completion."""
        self.is_processing = False
        self.progress_var.set(100)
        
        # Reset UI state
        self.process_btn.config(state=tk.NORMAL)
        if hasattr(self, 'schedule_btn') and self.schedule_btn:
            self.schedule_btn.config(state=tk.NORMAL)
        self.cancel_btn.config(state=tk.DISABLED)
        self.input_listbox.config(state=tk.NORMAL)
        
        # Update listbox to show which items were successful
        self._update_listbox_with_results()
        
        # Show summary in status bar instead of popup dialog
        self._show_status_summary()
    
    def _update_listbox_with_results(self):
        """Update the listbox to show checkmarks for successfully processed items."""
        # Build a set of successful sources for quick lookup
        successful_sources = set()
        for source, title in self.results.get('successful', []):
            successful_sources.add(source)
        
        # Also track failed sources
        failed_sources = set()
        for source, error in self.results.get('failed', []):
            failed_sources.add(source)
        
        # Update each item in the listbox
        for i in range(self.input_listbox.size()):
            item = self.input_listbox.get(i)
            
            # Skip items that already have a status prefix
            if item.startswith(('✓ ', '✗ ')):
                continue
            
            if item in successful_sources:
                # Mark as successful with checkmark and green color
                self.input_listbox.delete(i)
                self.input_listbox.insert(i, f"✓ {item}")
                self.input_listbox.itemconfig(i, fg='#006600')  # Dark green
            elif item in failed_sources:
                # Mark as failed with X and red color
                self.input_listbox.delete(i)
                self.input_listbox.insert(i, f"✗ {item}")
                self.input_listbox.itemconfig(i, fg='#cc0000')  # Red
        
    def _processing_cancelled(self):
        """Handle processing cancellation."""
        self.is_processing = False
        
        # Reset UI state
        self.process_btn.config(state=tk.NORMAL)
        if hasattr(self, 'schedule_btn') and self.schedule_btn:
            self.schedule_btn.config(state=tk.NORMAL)
        self.cancel_btn.config(state=tk.DISABLED)
        self.input_listbox.config(state=tk.NORMAL)
        
        # Update listbox with partial results
        self._update_listbox_with_results()
        
        # Show partial results in status bar
        self._show_status_summary(cancelled=True)
        
    def _cancel_processing(self):
        """Cancel the current processing operation."""
        if self.is_processing:
            self.cancel_requested = True
            self.status_label.config(text="Cancelling...")
            
    def _show_status_summary(self, cancelled: bool = False):
        """Show a summary of processing results in the status bar."""
        success_count = len(self.results.get('successful', []))
        failed_count = len(self.results.get('failed', []))
        skipped_count = len(self.results.get('skipped', []))
        saved_count = len(self.results.get('saved_to_library', []))
        context_count = len(self.results.get('added_to_context', []))
        
        # Build summary parts
        parts = []
        
        if cancelled:
            parts.append("Cancelled.")
        else:
            parts.append("✅ Done:")
        
        if success_count > 0:
            parts.append(f"{success_count} fetched")
        if failed_count > 0:
            parts.append(f"{failed_count} failed")
        if skipped_count > 0:
            parts.append(f"{skipped_count} skipped")
        
        # Add destination info
        dest_parts = []
        if saved_count > 0:
            dest_parts.append(f"📚 {saved_count} to library")
        if context_count > 0:
            dest_parts.append(f"📎 {context_count} to prompt")
        
        if dest_parts:
            summary = f"{' '.join(parts)} → {', '.join(dest_parts)}"
        else:
            summary = ' '.join(parts)
        
        self.status_label.config(text=summary)
        
        # If there were failures, also show in a different color or add tooltip info
        if failed_count > 0:
            # Get first failure reason for tooltip
            first_failure = self.results.get('failed', [('', 'Unknown')])[0]
            self.status_label.config(foreground='#cc6600')  # Orange for partial success
        elif success_count > 0:
            self.status_label.config(foreground='#006600')  # Green for full success
        else:
            self.status_label.config(foreground='#cc0000')  # Red for all failed
        
    def _schedule_processing(self, minutes: int):
        """Schedule processing to start after specified minutes."""
        items = self._get_items()
        
        if not items:
            messagebox.showwarning("No Items", "Please add items to process.")
            return
            
        # Cancel any existing schedule
        if self.schedule_timer:
            self.window.after_cancel(self.schedule_timer)
            
        # Calculate start time
        self.scheduled_time = datetime.now() + timedelta(minutes=minutes)
        start_str = self.scheduled_time.strftime("%H:%M")
        
        self.schedule_label.config(text=f"⏰ Scheduled to start at {start_str}")
        
        # Schedule the processing
        self.schedule_timer = self.window.after(
            minutes * 60 * 1000,
            self._start_processing
        )
        
        messagebox.showinfo(
            "Processing Scheduled",
            f"Processing will start at {start_str}"
        )
        
    def _schedule_custom(self):
        """Show dialog for custom scheduling."""
        dialog = DateTimeScheduleDialog(self.window)
        if dialog.result:
            now = datetime.now()
            delta = dialog.result - now
            
            if delta.total_seconds() <= 0:
                messagebox.showwarning("Invalid Time", "Please select a time in the future.")
                return
                
            self._schedule_processing_at(dialog.result)
            
    def _schedule_processing_at(self, scheduled_datetime: datetime):
        """Schedule processing to start at a specific datetime."""
        items = self._get_items()
        
        if not items:
            messagebox.showwarning("No Items", "Please add items to process.")
            return
            
        if self.schedule_timer:
            self.window.after_cancel(self.schedule_timer)
            
        self.scheduled_time = scheduled_datetime
        now = datetime.now()
        delta = scheduled_datetime - now
        
        if delta.total_seconds() <= 0:
            messagebox.showwarning("Invalid Time", "Please select a time in the future.")
            return
            
        if scheduled_datetime.date() == now.date():
            start_str = f"today at {scheduled_datetime.strftime('%H:%M')}"
        elif scheduled_datetime.date() == (now + timedelta(days=1)).date():
            start_str = f"tomorrow at {scheduled_datetime.strftime('%H:%M')}"
        else:
            start_str = scheduled_datetime.strftime("%Y-%m-%d %H:%M")
        
        self.schedule_label.config(text=f"⏰ Scheduled to start {start_str}")
        
        ms = int(delta.total_seconds() * 1000)
        self.schedule_timer = self.window.after(ms, self._start_processing)
        
        messagebox.showinfo("Processing Scheduled", f"Processing will start {start_str}")
            
    def _on_close(self):
        """Handle window close."""
        if self.is_processing:
            if messagebox.askyesno("Processing in Progress",
                                   "Processing is still in progress. Cancel and close?"):
                self.cancel_requested = True
                self.window.after(500, self._finish_close)
        else:
            if self.schedule_timer:
                if messagebox.askyesno("Scheduled Processing",
                                       "Processing is scheduled. Cancel and close?"):
                    self.window.after_cancel(self.schedule_timer)
                    self._finish_close()
            else:
                self._finish_close()
    
    def _finish_close(self):
        """Finish closing the window and call completion callback."""
        if self.changes_made and self.on_complete_callback:
            self.on_complete_callback()
        self.window.destroy()


class DateTimeScheduleDialog:
    """Dialog for selecting a specific date and time for scheduling."""
    
    def __init__(self, parent):
        self.result = None
        
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Schedule Processing")
        self.dialog.geometry("350x250")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        self.dialog.configure(bg='#dcdad5')  # Match main window background
        
        frame = ttk.Frame(self.dialog, padding="20")
        frame.pack(fill="both", expand=True)
        
        ttk.Label(frame, text="Schedule processing for:", font=('Segoe UI', 10, 'bold')).pack(anchor="w")
        
        # Date selection
        date_frame = ttk.Frame(frame)
        date_frame.pack(fill="x", pady=(10, 5))
        
        ttk.Label(date_frame, text="Date:", width=8).pack(side="left")
        
        now = datetime.now()
        
        self.year_var = tk.StringVar(value=str(now.year))
        year_spin = ttk.Spinbox(date_frame, from_=now.year, to=now.year + 1, 
                                textvariable=self.year_var, width=6)
        year_spin.pack(side="left", padx=2)
        ttk.Label(date_frame, text="-").pack(side="left")
        
        self.month_var = tk.StringVar(value=f"{now.month:02d}")
        month_spin = ttk.Spinbox(date_frame, from_=1, to=12, 
                                 textvariable=self.month_var, width=4, format="%02.0f")
        month_spin.pack(side="left", padx=2)
        ttk.Label(date_frame, text="-").pack(side="left")
        
        self.day_var = tk.StringVar(value=f"{now.day:02d}")
        day_spin = ttk.Spinbox(date_frame, from_=1, to=31, 
                               textvariable=self.day_var, width=4, format="%02.0f")
        day_spin.pack(side="left", padx=2)
        
        # Time selection
        time_frame = ttk.Frame(frame)
        time_frame.pack(fill="x", pady=5)
        
        ttk.Label(time_frame, text="Time:", width=8).pack(side="left")
        
        self.hour_var = tk.StringVar(value=f"{now.hour:02d}")
        hour_spin = ttk.Spinbox(time_frame, from_=0, to=23, 
                                textvariable=self.hour_var, width=4, format="%02.0f")
        hour_spin.pack(side="left", padx=2)
        ttk.Label(time_frame, text=":").pack(side="left")
        
        self.minute_var = tk.StringVar(value=f"{((now.minute // 5) + 1) * 5 % 60:02d}")
        minute_spin = ttk.Spinbox(time_frame, from_=0, to=59, increment=5,
                                  textvariable=self.minute_var, width=4, format="%02.0f")
        minute_spin.pack(side="left", padx=2)
        
        # Quick buttons
        quick_frame = ttk.Frame(frame)
        quick_frame.pack(fill="x", pady=(15, 5))
        
        ttk.Label(quick_frame, text="Quick select:", font=('Segoe UI', 9)).pack(anchor="w")
        
        quick_btn_frame = ttk.Frame(quick_frame)
        quick_btn_frame.pack(fill="x", pady=5)
        
        ttk.Button(quick_btn_frame, text="Tonight 22:00", width=14,
                   command=lambda: self._set_quick_time(22, 0)).pack(side="left", padx=2)
        ttk.Button(quick_btn_frame, text="Tomorrow 06:00", width=14,
                   command=lambda: self._set_quick_time(6, 0, tomorrow=True)).pack(side="left", padx=2)
        ttk.Button(quick_btn_frame, text="Tomorrow 12:00", width=14,
                   command=lambda: self._set_quick_time(12, 0, tomorrow=True)).pack(side="left", padx=2)
        
        # Buttons
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill="x", pady=(15, 0))
        
        ttk.Button(btn_frame, text="Cancel", command=self.dialog.destroy).pack(side="right")
        ttk.Button(btn_frame, text="Schedule", command=self._on_schedule).pack(side="right", padx=(0, 5))
        
        # Center dialog
        self.dialog.update_idletasks()
        width = self.dialog.winfo_width()
        height = self.dialog.winfo_height()
        x = (self.dialog.winfo_screenwidth() // 2) - (width // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (height // 2)
        self.dialog.geometry(f"{width}x{height}+{x}+{y}")
        
        self.dialog.wait_window()
        
    def _set_quick_time(self, hour: int, minute: int, tomorrow: bool = False):
        """Set a quick preset time."""
        now = datetime.now()
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        if tomorrow or target <= now:
            target += timedelta(days=1)
            
        self.year_var.set(str(target.year))
        self.month_var.set(f"{target.month:02d}")
        self.day_var.set(f"{target.day:02d}")
        self.hour_var.set(f"{target.hour:02d}")
        self.minute_var.set(f"{target.minute:02d}")
        
    def _on_schedule(self):
        """Handle schedule button click."""
        try:
            year = int(self.year_var.get())
            month = int(self.month_var.get())
            day = int(self.day_var.get())
            hour = int(self.hour_var.get())
            minute = int(self.minute_var.get())
            
            scheduled_time = datetime(year, month, day, hour, minute)
            
            if scheduled_time <= datetime.now():
                messagebox.showwarning("Invalid Time", "Please select a time in the future.")
                return
                
            self.result = scheduled_time
            self.dialog.destroy()
            
        except ValueError as e:
            messagebox.showwarning("Invalid Input", f"Please enter valid date and time values.\n\nError: {e}")


# =============================================================================
# Convenience functions for backward compatibility and easy access
# =============================================================================

def open_sources_dialog(parent, process_callback, get_settings_callback,
                        save_to_library_callback=None, ai_process_callback=None,
                        attachment_manager=None, mode="unified",
                        status_callback=None, get_provider_callback=None,
                        on_complete_callback=None):
    """
    Open the unified sources dialog.
    
    This is the main entry point for the new unified Add Sources feature.
    
    Args:
        parent: Parent tkinter window
        process_callback: Function to process a single item (extract text)
        get_settings_callback: Function to get current AI settings
        save_to_library_callback: Optional function to save to document library
        ai_process_callback: Optional function to run AI analysis
        attachment_manager: AttachmentManager instance (for prompt_context mode)
        mode: "library", "prompt_context", or "unified" (default)
        status_callback: Function to update status bar
        get_provider_callback: Function to get current AI provider
        on_complete_callback: Function called when dialog closes with changes
        
    Returns:
        SourcesDialog instance
    """
    return SourcesDialog(
        parent,
        process_callback,
        get_settings_callback,
        save_to_library_callback,
        ai_process_callback,
        attachment_manager,
        mode,
        status_callback,
        get_provider_callback,
        on_complete_callback
    )


def open_bulk_processing(parent, process_callback, get_settings_callback,
                         save_to_library_callback=None, ai_process_callback=None):
    """
    Open the bulk processing window (library mode only).
    
    This is the legacy entry point - kept for backward compatibility.
    Opens the sources dialog in library-only mode.
    
    Args:
        parent: Parent tkinter window
        process_callback: Function to process a single item (extract text)
        get_settings_callback: Function to get current AI settings
        save_to_library_callback: Optional function to save to document library
        ai_process_callback: Optional function to run AI analysis on extracted text
        
    Returns:
        SourcesDialog instance (in library mode)
    """
    return SourcesDialog(
        parent,
        process_callback,
        get_settings_callback,
        save_to_library_callback,
        ai_process_callback,
        attachment_manager=None,
        mode="library",
        status_callback=None,
        get_provider_callback=None,
        on_complete_callback=None
    )
