"""
document_tree_manager.py - VERSION 1.0

Documents Library with tree structure, preview, and editing.
Built on top of tree_manager_base.py for maximum reusability.

Features:
- 4-level folder hierarchy  
- Drag-and-drop organization
- Preview panel with read-only for sources
- Edit mode for responses/products/processed outputs
- Search functionality
- Document type icons
- Windows Explorer-style interface

Author: DocAnalyser Development Team
Date: January 2026
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import datetime
import json
import os
from typing import Optional, Callable, List, Tuple

# Import base classes
from tree_manager_base import TreeNode, FolderNode, TreeManager, TreeManagerUI

# Import document library functions
from document_library import (
    get_all_documents,
    get_document_by_id,
    load_document_entries,
    load_thread_from_document,
    update_document_entries,
    delete_document,
    rename_document
)

from utils import entries_to_text


# ============================================================================
# DOCUMENT ITEM - Extends TreeNode
# ============================================================================

class DocumentItem(TreeNode):
    """A single document with metadata - extends TreeNode"""
    
    def __init__(self, doc_id: str, title: str, doc_type: str, document_class: str = "source"):
        super().__init__(title)
        self.doc_id = doc_id
        self.doc_type = doc_type  # 'youtube', 'pdf', 'substack', 'audio_transcription', etc.
        self.document_class = document_class  # 'source', 'response', 'product', 'processed_output'
        self.source = None
        self.created = None
        self.has_thread = False
    
    # ========== TreeNode Implementation ==========
    
    def get_icon(self) -> str:
        """Return icon based on document class and type"""
        # Base icon by document class
        if self.document_class == "source":
            # Source documents
            if self.doc_type == "youtube":
                base_icon = "🎥"
            elif self.doc_type == "substack":
                base_icon = "📰"
            elif self.doc_type == "pdf":
                base_icon = "📄"
            elif self.doc_type == "audio_transcription":
                base_icon = "🎵"
            elif self.doc_type == "facebook":
                base_icon = "📘"
            elif self.doc_type == "web_content":
                base_icon = "🌐"
            else:
                base_icon = "📄"
        elif self.document_class == "response":
            base_icon = "💬"
        elif self.document_class == "product":
            base_icon = "📋"
        elif self.document_class == "processed_output":
            base_icon = "✨"
        else:
            base_icon = "📄"
        
        # Add thread indicator if has thread
        if self.has_thread:
            base_icon = base_icon + "💬"
        
        return base_icon
    
    def get_type(self) -> str:
        return "document"
    
    def can_be_renamed(self) -> bool:
        return True
    
    def can_be_deleted(self) -> bool:
        return True
    
    def can_be_moved(self) -> bool:
        return True
    
    def can_be_edited(self) -> bool:
        """Check if this document can be edited"""
        # Sources are read-only, responses/products/processed_outputs can be edited
        return self.document_class in ['response', 'product', 'processed_output']
    
    def to_dict(self) -> dict:
        return {
            'type': 'document',
            'doc_id': self.doc_id,
            'title': self.name,
            'doc_type': self.doc_type,
            'document_class': self.document_class,
            'source': self.source,
            'created': self.created,
            'has_thread': self.has_thread
        }
    
    @staticmethod
    def from_dict(data: dict) -> 'DocumentItem':
        doc = DocumentItem(
            doc_id=data['doc_id'],
            title=data['title'],
            doc_type=data.get('doc_type', 'unknown'),
            document_class=data.get('document_class', 'source')
        )
        doc.source = data.get('source')
        doc.created = data.get('created')
        doc.has_thread = data.get('has_thread', False)
        return doc


# ============================================================================
# DOCUMENT TREE MANAGER UI - Extends TreeManagerUI  
# ============================================================================

class DocumentTreeManagerUI(TreeManagerUI):
    """
    Documents Library UI - extends generic TreeManagerUI.
    Adds document-specific features like preview, editing, search, etc.
    """
    
    def __init__(self, parent, tree_manager: TreeManager,
                 library_path: str, save_func: Callable,
                 on_load_document: Callable = None,
                 on_send_to_input: Callable = None,
                 config: dict = None):
        """
        Initialize Documents Library UI.
        
        Args:
            parent: Parent window
            tree_manager: TreeManager with documents
            library_path: Path to document_library.json
            save_func: Function to save library structure
            on_load_document: Callback to load document in main window
            on_send_to_input: Callback to send source paths to main input box
            config: Config dict
        """
        self.library_path = library_path
        self.save_func_external = save_func
        self.on_load_document = on_load_document
        self.on_send_to_input = on_send_to_input
        self.config = config or {}
        
        # Editing state
        self.editing_mode = False
        self.current_viewing_doc = None
        self.original_text_before_edit = None
        
        # Search state
        self.search_results = []
        self.search_active = False
        self.search_mode_var = None  # Will hold "Title" or "Content"
        
        # UI components (will be created)
        self.preview_frame = None
        self.preview_title_label = None
        self.preview_subtitle_label = None
        self.preview_text = None
        self.edit_indicator = None
        
        # Search components
        self.search_var = None
        self.search_entry = None
        self.search_status_label = None
        
        # Buttons
        self.btn_edit = None
        self.btn_save = None
        self.btn_load = None
        self.btn_view_thread = None
        
        # Initialize base class
        super().__init__(
            parent=parent,
            tree_manager=tree_manager,
            item_type_name="Document",
            on_save_callback=self.save_tree,
            on_item_action=self.load_document
        )
    
    # ========== Override UI Creation ==========
    
    def create_ui(self):
        """Create full UI with search and preview panel"""
        # Create main container
        self.main_frame = ttk.PanedWindow(self.parent, orient=tk.HORIZONTAL)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        
        # LEFT: Tree
        left_frame = ttk.Frame(self.main_frame, relief=tk.RIDGE, borderwidth=2, width=350)
        self.main_frame.add(left_frame, weight=2)
        
        # Tree header
        tree_header = ttk.Frame(left_frame)
        tree_header.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(tree_header, text="📁 Documents Library", 
                 font=('Arial', 12, 'bold')).pack(side=tk.LEFT)
        
        btn_frame = ttk.Frame(tree_header)
        btn_frame.pack(side=tk.RIGHT)
        ttk.Button(btn_frame, text="Expand All", command=self.expand_all, 
                  width=12).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Collapse All", command=self.collapse_all, 
                  width=12).pack(side=tk.LEFT, padx=2)
        
        # Search bar
        search_frame = ttk.LabelFrame(left_frame, text="🔍 Search", padding=5)
        search_frame.pack(fill=tk.X, padx=5, pady=5)
        
        search_input_frame = ttk.Frame(search_frame)
        search_input_frame.pack(fill=tk.X)
        
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_input_frame, textvariable=self.search_var, width=30)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.search_entry.bind('<Return>', lambda e: self.perform_search())
        
        ttk.Button(search_input_frame, text="Search", command=self.perform_search, 
                  width=8).pack(side=tk.LEFT)
        
        # Search mode dropdown
        self.search_mode_var = tk.StringVar(value="Title")
        search_mode_combo = ttk.Combobox(
            search_input_frame,
            textvariable=self.search_mode_var,
            values=["Title", "Content"],
            state="readonly",
            width=8
        )
        search_mode_combo.pack(side=tk.LEFT, padx=(2, 0))
        
        ttk.Button(search_input_frame, text="Clear", command=self.clear_search, 
                  width=6).pack(side=tk.LEFT, padx=(2, 0))
        
        self.search_status_label = ttk.Label(search_frame, text="", font=('Arial', 8), 
                                             foreground='gray')
        self.search_status_label.pack(anchor=tk.W, pady=(5, 0))
        
        # Tree controls (2-column layout)
        controls = ttk.Frame(left_frame)
        controls.pack(fill=tk.X, padx=5, pady=5)
        
        # Row 1: Create operations
        self.btn_new_folder = ttk.Button(controls, text="⊕ Folder", 
                                        command=self.create_new_folder, width=13)
        self.btn_new_folder.grid(row=0, column=0, padx=2, pady=2, sticky=tk.EW)
        
        self.btn_rename = ttk.Button(controls, text="✏️ Rename", 
                                    command=self.rename_selected, width=13, state=tk.DISABLED)
        self.btn_rename.grid(row=0, column=1, padx=2, pady=2, sticky=tk.EW)
        
        # Row 2: Delete and move
        self.btn_delete = ttk.Button(controls, text="🗑️ Delete", 
                                    command=self.delete_selected, width=13, state=tk.DISABLED)
        self.btn_delete.grid(row=1, column=0, padx=2, pady=2, sticky=tk.EW)
        
        # Move up/down in same cell
        move_frame = ttk.Frame(controls)
        move_frame.grid(row=1, column=1, padx=2, pady=2, sticky=tk.EW)
        
        self.btn_move_up = ttk.Button(move_frame, text="↑", 
                                      command=self.move_selected_up, width=6, state=tk.DISABLED)
        self.btn_move_up.pack(side=tk.LEFT, padx=1, expand=True, fill=tk.X)
        
        self.btn_move_down = ttk.Button(move_frame, text="↓", 
                                        command=self.move_selected_down, width=6, state=tk.DISABLED)
        self.btn_move_down.pack(side=tk.LEFT, padx=1, expand=True, fill=tk.X)
        
        # Make columns expand evenly
        controls.columnconfigure(0, weight=1)
        controls.columnconfigure(1, weight=1)
        
        # Tree view
        tree_frame = ttk.Frame(left_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        scrollbar = ttk.Scrollbar(tree_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.tree = ttk.Treeview(tree_frame, yscrollcommand=scrollbar.set, selectmode='extended')
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.tree.yview)
        
        self.tree['columns'] = ('type', 'can_drop')
        self.tree.column('#0', width=300)
        self.tree.column('type', width=0, stretch=False)
        self.tree.column('can_drop', width=0, stretch=False)
        
        # RIGHT: Preview/Edit Panel
        self.create_preview_panel()
        
        # Bind events
        self.tree.bind('<<TreeviewSelect>>', self.on_tree_select)
        self.tree.bind('<Double-Button-1>', self.on_double_click)
        self.tree.bind('<Button-1>', self.on_single_click, add='+')  # Allow deselecting
        
        # Setup features
        self.setup_drag_drop()
        self.setup_keyboard_shortcuts()
        self.setup_context_menu()
        
        # Populate tree
        self.populate_tree()
        
        # Set initial sash position (60/40 split)
        self.parent.update_idletasks()
        self.main_frame.sashpos(0, 350)
    
    def create_preview_panel(self):
        """Create preview/edit panel on right"""
        self.preview_frame = ttk.Frame(self.main_frame, relief=tk.RIDGE, borderwidth=2)
        self.main_frame.add(self.preview_frame, weight=1)
        
        # Header
        preview_header = ttk.Frame(self.preview_frame)
        preview_header.pack(fill=tk.X, padx=10, pady=5)
        
        self.preview_title_label = ttk.Label(preview_header, text="Select a document", 
                                            font=('Arial', 12, 'bold'))
        self.preview_title_label.pack(anchor=tk.W)
        
        self.preview_subtitle_label = ttk.Label(preview_header, text="", 
                                               font=('Arial', 9), foreground='gray')
        self.preview_subtitle_label.pack(anchor=tk.W)
        
        # Text area
        ttk.Label(self.preview_frame, text="Document Preview:").pack(anchor=tk.W, padx=10)
        
        text_frame = ttk.Frame(self.preview_frame)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.preview_text = scrolledtext.ScrolledText(text_frame, wrap=tk.WORD, 
                                                      height=15, bg='#FFFDE6',
                                                      font=('Arial', 10), state=tk.DISABLED)
        self.preview_text.pack(fill=tk.BOTH, expand=True)
        self.preview_text.config(undo=True, maxundo=-1)
        
        # Editing indicator
        self.edit_indicator = ttk.Label(self.preview_frame, 
                                       text="Select a document to view", 
                                       foreground='gray', font=('Arial', 9, 'italic'))
        self.edit_indicator.pack(anchor=tk.W, padx=10)
        
        # Action buttons (2-column layout)
        action_frame = ttk.Frame(self.preview_frame)
        action_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Row 1: Load and Edit
        self.btn_load = ttk.Button(action_frame, text="📂 Load in Main", 
                                   command=self.load_document, state=tk.DISABLED, width=14)
        self.btn_load.grid(row=0, column=0, padx=2, pady=2, sticky=tk.EW)
        
        self.btn_edit = ttk.Button(action_frame, text="✏️ Edit", 
                                   command=self.enter_edit_mode, state=tk.DISABLED, width=14)
        self.btn_edit.grid(row=0, column=1, padx=2, pady=2, sticky=tk.EW)
        
        # Row 2: Save (spans both columns)
        self.btn_save = ttk.Button(action_frame, text="💾 Save Changes", 
                                  command=self.save_current_edit, state=tk.DISABLED, width=30)
        self.btn_save.grid(row=1, column=0, columnspan=2, padx=2, pady=2, sticky=tk.EW)
        
        # Row 3: Add to Prompt (for multi-document analysis)
        self.btn_send_to_input = ttk.Button(action_frame, text="📎 Add to Prompt", 
                                           command=self.send_to_input, state=tk.DISABLED, width=30)
        self.btn_send_to_input.grid(row=2, column=0, columnspan=2, padx=2, pady=2, sticky=tk.EW)
        
        # Add help popup for Add to Prompt button
        try:
            from context_help import add_help, HELP_TEXTS
            if HELP_TEXTS:
                add_help(self.btn_send_to_input, **HELP_TEXTS.get("library_add_to_prompt_button", {
                    "title": "📎 Add to Prompt", 
                    "description": "Add selected documents as attachments for multi-document analysis"
                }))
        except:
            pass  # Help system not available
        
        # Make columns expand evenly
        action_frame.columnconfigure(0, weight=1)
        action_frame.columnconfigure(1, weight=1)
        
        # Bind text events
        self.preview_text.bind('<Control-s>', lambda e: self.save_current_edit())
        self.preview_text.bind('<Escape>', lambda e: self.exit_edit_mode(save=False))
        
        # Bottom buttons
        bottom_frame = ttk.Frame(self.parent)
        bottom_frame.pack(pady=5)
        
        ttk.Button(bottom_frame, text="💾 Save All Changes", 
                  command=self.save_tree).pack(side=tk.LEFT, padx=5)
        ttk.Button(bottom_frame, text="Close", 
                  command=self.on_close).pack(side=tk.LEFT, padx=5)
    
    # ========== Override: Item Selection ==========
    
    def on_item_selected(self, item_name: str, item_type: str):
        """Called when item is selected"""
        if item_type == 'document':
            # Find the document
            parent, item, depth = self.tree_manager.find_item(item_name, 'document')
            if item and isinstance(item, DocumentItem):
                self.show_document_preview(item)
                self.btn_load.config(state=tk.NORMAL)
                
                # Enable edit button only for editable documents
                if item.can_be_edited():
                    self.btn_edit.config(state=tk.NORMAL)
                else:
                    self.btn_edit.config(state=tk.DISABLED)
                
                # Enable Add to Prompt if callback exists (works for any document)
                if self.on_send_to_input:
                    self.btn_send_to_input.config(state=tk.NORMAL)
                else:
                    self.btn_send_to_input.config(state=tk.DISABLED)
        else:
            # It's a folder
            self.clear_preview()
            self.btn_load.config(state=tk.DISABLED)
            self.btn_edit.config(state=tk.DISABLED)
            self.btn_save.config(state=tk.DISABLED)
            self.btn_send_to_input.config(state=tk.DISABLED)
    
    def on_multiple_selected(self, count: int):
        """Called when multiple items selected"""
        self.preview_title_label.config(text=f"📦 {count} items selected")
        self.preview_subtitle_label.config(text="")
        self.preview_text.config(state=tk.NORMAL)
        self.preview_text.delete('1.0', tk.END)
        self.preview_text.insert('1.0', 
            f"You have selected {count} items.\n\n"
            f"You can:\n"
            f"• Delete them all at once\n"
            f"• Drag them to another folder\n"
            f"• Add them to your prompt for multi-document analysis\n\n"
            f"To rename or view details, select a single item.")
        self.preview_text.config(state=tk.DISABLED)
        
        self.edit_indicator.config(
            text=f"{count} items selected - click 'Add to Prompt' for multi-document analysis",
            foreground='#0066CC'
        )
        
        # Disable buttons that don't work with multi-select
        self.btn_load.config(state=tk.DISABLED)
        self.btn_edit.config(state=tk.DISABLED)
        self.btn_save.config(state=tk.DISABLED)
        
        # Enable Add to Prompt for multi-select (if callback exists)
        if self.on_send_to_input:
            self.btn_send_to_input.config(state=tk.NORMAL)
    
    def on_single_click(self, event):
        """Handle single click - allow deselecting by clicking blank space"""
        region = self.tree.identify_region(event.x, event.y)
        if region == "nothing":
            # Clicked on empty space - clear selection
            self.tree.selection_remove(self.tree.selection())
            self.last_selected_item_id = None
            self.clear_preview()
            # Disable buttons when nothing selected
            self.btn_rename.config(state=tk.DISABLED)
            self.btn_delete.config(state=tk.DISABLED)
            self.btn_move_up.config(state=tk.DISABLED)
            self.btn_move_down.config(state=tk.DISABLED)
    
    def activate_selected(self):
        """Called when item is activated (double-click/Enter)"""
        if self.last_selected_item_id:
            item_id = self.last_selected_item_id
            item_type = self.tree.item(item_id, 'values')[0]
            
            if item_type == 'folder':
                # Toggle folder
                current_state = self.tree.item(item_id, 'open')
                self.tree.item(item_id, open=not current_state)
            else:
                # Load document
                self.load_document()
    
    # ========== Override: Create New Item ==========
    
    def create_new_item(self):
        """Documents are not created here - placeholder"""
        messagebox.showinfo("Info", 
                          "Documents are created from the main window.\n\n"
                          "Use this library to organize existing documents into folders.")
    
    # ========== Document Preview ==========
    
    def show_document_preview(self, doc: DocumentItem):
        """Show document in preview pane"""
        self.preview_title_label.config(text=f"{doc.get_icon()} {doc.name}")
        
        # Build subtitle
        subtitle = f"[{doc.document_class.upper()}] {doc.doc_type}"
        if doc.source:
            subtitle += f" • Source: {doc.source[:50]}..."
        if doc.created:
            try:
                created_dt = datetime.datetime.fromisoformat(doc.created)
                subtitle += f" • Created: {created_dt.strftime('%Y-%m-%d %H:%M')}"
            except:
                pass
        
        self.preview_subtitle_label.config(text=subtitle)
        
        # Exit edit mode if active
        if self.editing_mode:
            self.exit_edit_mode(save=False)
        
        # Load document content
        self.current_viewing_doc = doc
        
        try:
            # For response/thread documents, try to show conversation thread content first
            preview_text = None
            is_conversation = doc.doc_type in ("ai_response", "standalone_conversation", "conversation_thread")
            
            if is_conversation:
                # Try to load conversation thread
                thread, thread_meta = load_thread_from_document(doc.doc_id)
                if thread and len(thread) > 0:
                    # Format thread content for preview
                    preview_text = self._format_thread_preview(thread)
            
            # Fall back to entries if no thread content
            if not preview_text:
                entries = load_document_entries(doc.doc_id)
                if entries:
                    text = entries_to_text(entries)
                    preview_text = text
            
            if preview_text:
                # Truncate for preview
                if len(preview_text) > 5000:
                    preview_text = preview_text[:5000] + "\n\n[... Preview truncated at 5000 characters ...]"
                
                self.preview_text.config(state=tk.NORMAL)
                self.preview_text.delete('1.0', tk.END)
                self.preview_text.insert('1.0', preview_text)
                self.preview_text.config(state=tk.DISABLED)
                
                # Update indicator based on document type
                if doc.doc_type == "ai_response":
                    # Response document - double-click opens thread viewer
                    self.edit_indicator.config(
                        text="💬 Double-click to view full conversation thread",
                        foreground='#0066CC'
                    )
                elif doc.doc_type == "standalone_conversation":
                    # Standalone conversation - double-click opens thread viewer
                    self.edit_indicator.config(
                        text="💬 Double-click to view conversation",
                        foreground='#0066CC'
                    )
                elif doc.can_be_edited():
                    # Editable product document
                    self.edit_indicator.config(
                        text="✏️ Click Edit to modify this document",
                        foreground='#0066CC'
                    )
                else:
                    # Read-only source document
                    self.edit_indicator.config(
                        text="📄 Source document (read-only)",
                        foreground='gray'
                    )
            else:
                self.preview_text.config(state=tk.NORMAL)
                self.preview_text.delete('1.0', tk.END)
                self.preview_text.insert('1.0', "No content available")
                self.preview_text.config(state=tk.DISABLED)
                self.edit_indicator.config(text="No content", foreground='gray')
        except Exception as e:
            self.preview_text.config(state=tk.NORMAL)
            self.preview_text.delete('1.0', tk.END)
            self.preview_text.insert('1.0', f"Error loading content: {e}")
            self.preview_text.config(state=tk.DISABLED)
            self.edit_indicator.config(text="Error loading", foreground='red')
    
    def _format_thread_preview(self, thread: list) -> str:
        """Format a conversation thread for preview display."""
        lines = []
        
        # Count exchanges
        exchange_count = len([m for m in thread if m.get('role') == 'user'])
        lines.append(f"Conversation with {exchange_count} exchange{'s' if exchange_count != 1 else ''}")
        lines.append("=" * 50)
        lines.append("")
        
        for msg in thread:
            role = msg.get('role', '').upper()
            content = msg.get('content', '')
            timestamp = msg.get('timestamp', '')
            
            if role == 'USER':
                time_str = f" [{timestamp}]" if timestamp else ""
                lines.append(f"🧑 YOU{time_str}:")
                lines.append(content[:500] + "..." if len(content) > 500 else content)
                lines.append("")
            elif role == 'ASSISTANT':
                provider = msg.get('provider', 'AI')
                time_str = f" [{timestamp}]" if timestamp else ""
                lines.append(f"🤖 {provider}{time_str}:")
                # Truncate long AI responses more aggressively
                lines.append(content[:800] + "..." if len(content) > 800 else content)
                lines.append("")
                lines.append("-" * 30)
                lines.append("")
        
        return '\n'.join(lines)
    
    def clear_preview(self):
        """Clear preview pane"""
        self.preview_title_label.config(text="Select a document")
        self.preview_subtitle_label.config(text="")
        self.preview_text.config(state=tk.NORMAL)
        self.preview_text.delete('1.0', tk.END)
        self.preview_text.config(state=tk.DISABLED)
        self.edit_indicator.config(text="Select a document to view", foreground='gray')
        self.current_viewing_doc = None
        
        # Disable send to input button
        if hasattr(self, 'btn_send_to_input'):
            self.btn_send_to_input.config(state=tk.DISABLED)
        
        if self.editing_mode:
            self.exit_edit_mode(save=False)
    
    # ========== Edit Mode ==========
    
    def enter_edit_mode(self):
        """Enable editing for editable documents"""
        if not self.current_viewing_doc:
            return
        
        if not self.current_viewing_doc.can_be_edited():
            messagebox.showinfo("Read-Only", 
                              "This is a source document and cannot be edited.\n\n"
                              "Only responses, products, and processed outputs can be edited.")
            return
        
        if self.editing_mode:
            return
        
        self.editing_mode = True
        self.original_text_before_edit = self.preview_text.get('1.0', 'end-1c')
        
        self.preview_text.config(state=tk.NORMAL, bg='#FFFFCC')
        self.edit_indicator.config(text="✏️ EDITING - Ctrl+S to save, Escape to cancel", 
                                  foreground='#0066CC', font=('Arial', 9, 'bold'))
        self.btn_save.config(state=tk.NORMAL)
        self.btn_edit.config(state=tk.DISABLED, text="✏️ Editing...")
        self.btn_load.config(state=tk.DISABLED)
        self.preview_text.focus_set()
    
    def exit_edit_mode(self, save=False):
        """Exit editing mode"""
        if not self.editing_mode:
            return
        
        if save and self.current_viewing_doc:
            new_text = self.preview_text.get('1.0', 'end-1c')
            
            if new_text != self.original_text_before_edit:
                # Convert text back to entries
                # Simple approach: split by paragraphs
                paragraphs = [p.strip() for p in new_text.split('\n\n') if p.strip()]
                new_entries = []
                for i, para in enumerate(paragraphs):
                    new_entries.append({
                        'text': para,
                        'start': i,
                        'timestamp': f'[{i}]'
                    })
                
                # Save to library
                try:
                    update_document_entries(self.current_viewing_doc.doc_id, new_entries)
                    self.has_unsaved_changes = True
                    messagebox.showinfo("Saved", 
                                      f"Document '{self.current_viewing_doc.name}' saved successfully!")
                except Exception as e:
                    messagebox.showerror("Save Error", f"Failed to save:\n{e}")
                    return
            else:
                messagebox.showinfo("No Changes", "No changes to save")
        else:
            # Revert
            if self.original_text_before_edit is not None:
                self.preview_text.delete('1.0', tk.END)
                self.preview_text.insert('1.0', self.original_text_before_edit)
        
        self.editing_mode = False
        self.preview_text.config(state=tk.DISABLED, bg='#F5F5F5')
        # Restore appropriate indicator text based on document type
        if self.current_viewing_doc and self.current_viewing_doc.doc_type == "ai_response":
            self.edit_indicator.config(text="💬 Double-click to view full conversation thread", 
                                      foreground='#0066CC', font=('Arial', 9, 'italic'))
        else:
            self.edit_indicator.config(text="✏️ Click Edit to modify this document", 
                                      foreground='#0066CC', font=('Arial', 9, 'italic'))
        self.btn_save.config(state=tk.DISABLED)
        self.btn_edit.config(state=tk.NORMAL, text="✏️ Edit")
        self.btn_load.config(state=tk.NORMAL)
    
    def save_current_edit(self):
        """Save current edit"""
        if self.editing_mode:
            self.exit_edit_mode(save=True)
    
    # ========== Load Document ==========
    
    def load_document(self):
        """Load the selected document in main window"""
        if not self.current_viewing_doc:
            return
        
        doc = self.current_viewing_doc
        
        # Close this window
        self.parent.destroy()
        
        # Callback to main window
        if self.on_load_document:
            self.on_load_document(doc.doc_id)
    
    # ========== Send to Input ==========
    
    def send_to_input(self):
        """Add selected documents to main window as attachments for multi-document analysis"""
        if not self.on_send_to_input:
            messagebox.showinfo("Not Available", 
                              "This feature is not available in this context.")
            return
        
        # Get all selected items
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("No Selection", "Please select one or more documents.")
            return
        
        # Collect document info from selected documents
        doc_info_list = []
        
        for item_id in selected:
            item_text = self.tree.item(item_id, 'text')
            item_type = self.tree.item(item_id, 'values')[0]
            
            if item_type == 'document':
                # Extract name from text (format: "icon name")
                item_name = item_text.split(' ', 1)[1] if ' ' in item_text else item_text
                
                # Find the document
                parent, doc, depth = self.tree_manager.find_item(item_name, 'document')
                if doc and isinstance(doc, DocumentItem):
                    doc_info_list.append({
                        'doc_id': doc.doc_id,
                        'title': doc.name,
                        'doc_type': doc.doc_type
                    })
        
        if not doc_info_list:
            messagebox.showwarning("No Documents", 
                                 "No valid documents found in selection.")
            return
        
        # Call the callback with document info
        self.on_send_to_input(doc_info_list)
        
        # Close the library window
        self.parent.destroy()
    
    # ========== Search ==========
    
    def perform_search(self):
        """Perform search through documents by title or content"""
        query = self.search_var.get().strip().lower()
        
        if not query:
            messagebox.showinfo("Empty Search", "Please enter a search term")
            return
        
        # Get search mode
        search_mode = self.search_mode_var.get() if self.search_mode_var else "Title"
        
        # Clear previous search
        self.clear_search_highlighting()
        
        # Search through all documents
        self.search_results = []
        
        # Show searching indicator for content search
        if search_mode == "Content":
            self.search_status_label.config(text="Searching content...", foreground='blue')
            self.parent.update()
        
        def search_in_folder(folder):
            """Recursively search in folder"""
            for child in folder.children.values():
                if isinstance(child, DocumentItem):
                    found = False
                    
                    # Always search in title first
                    if query in child.name.lower():
                        found = True
                    
                    # If content search and not found in title, search content
                    if not found and search_mode == "Content":
                        try:
                            entries = load_document_entries(child.doc_id)
                            if entries:
                                # Convert entries to text and search
                                for entry in entries:
                                    text = entry.get('text', '')
                                    if query in text.lower():
                                        found = True
                                        break
                        except Exception as e:
                            print(f"Error searching content of {child.name}: {e}")
                    
                    if found:
                        self.search_results.append(child.name)
                        
                elif isinstance(child, FolderNode):
                    search_in_folder(child)
        
        for root_folder in self.tree_manager.root_folders.values():
            search_in_folder(root_folder)
        
        # Update status
        mode_text = f" (by {search_mode.lower()})"
        if self.search_results:
            self.search_active = True
            self.search_status_label.config(
                text=f"Found {len(self.search_results)} match(es){mode_text}",
                foreground='green'
            )
            
            # Highlight results in tree
            self.highlight_search_results()
        else:
            self.search_status_label.config(
                text=f"No matches found{mode_text}",
                foreground='red'
            )
    
    def highlight_search_results(self):
        """Highlight search results in tree and expand folders containing matches"""
        # Configure tag for highlighting
        self.tree.tag_configure('search_result', background='yellow')
        
        # Track which folders need to be expanded
        folders_to_expand = set()
        
        def find_and_highlight(parent_id='', parent_chain=None):
            """Find matches and track parent folders"""
            if parent_chain is None:
                parent_chain = []
            
            has_match_in_subtree = False
            
            for item_id in self.tree.get_children(parent_id):
                item_text = self.tree.item(item_id, 'text')
                item_name = item_text.split(' ', 1)[1] if ' ' in item_text else item_text
                
                # Check if this item is a match
                is_match = item_name in self.search_results
                
                if is_match:
                    self.tree.item(item_id, tags=('search_result',))
                    has_match_in_subtree = True
                    # Add all parent folders to expand list
                    for folder_id in parent_chain:
                        folders_to_expand.add(folder_id)
                
                # Recurse into children
                child_has_match = find_and_highlight(item_id, parent_chain + [item_id])
                if child_has_match:
                    has_match_in_subtree = True
                    # This folder contains matches, add to expand list
                    folders_to_expand.add(item_id)
            
            return has_match_in_subtree
        
        # Find all matches and their parent folders
        find_and_highlight()
        
        # Expand all folders that contain matches
        for folder_id in folders_to_expand:
            try:
                self.tree.item(folder_id, open=True)
            except:
                pass
        
        # Scroll to first result if any
        if self.search_results:
            self._scroll_to_first_result()
    
    def _scroll_to_first_result(self):
        """Scroll tree to show the first search result"""
        def find_first_match(parent_id=''):
            for item_id in self.tree.get_children(parent_id):
                item_text = self.tree.item(item_id, 'text')
                item_name = item_text.split(' ', 1)[1] if ' ' in item_text else item_text
                
                if item_name in self.search_results:
                    return item_id
                
                # Recurse
                result = find_first_match(item_id)
                if result:
                    return result
            return None
        
        first_match = find_first_match()
        if first_match:
            self.tree.see(first_match)
            self.tree.selection_set(first_match)
    
    def clear_search_highlighting(self):
        """Clear search highlighting"""
        def clear_recursive(parent_id=''):
            for item_id in self.tree.get_children(parent_id):
                self.tree.item(item_id, tags=())
                clear_recursive(item_id)
        
        clear_recursive()
    
    def clear_search(self):
        """Clear search"""
        self.search_var.set('')
        self.search_results = []
        self.search_active = False
        self.search_status_label.config(text='')
        self.clear_search_highlighting()
    
    # ========== Override: Delete ==========

    def _find_document_in_folder(self, folder, item_name):
        """
        Find a DocumentItem in a folder - tries name match first, then fuzzy search.
        Returns the DocumentItem and its key name, or (None, None) if not found.
        """
        # Direct name lookup (fastest)
        item = folder.children.get(item_name)
        if item and isinstance(item, DocumentItem):
            return item, item_name
        
        # Fallback: search all children by name (handles minor text differences)
        for key, child in folder.children.items():
            if isinstance(child, DocumentItem) and child.name == item_name:
                return child, key
        
        # Last resort: strip and compare (handles whitespace/encoding differences)
        clean_name = item_name.strip()
        for key, child in folder.children.items():
            if isinstance(child, DocumentItem) and key.strip() == clean_name:
                return child, key
        
        return None, None

    def delete_selected(self):
        """Delete selected item(s) - robust version with verified library deletion"""
        selection = self.tree.selection()
        if not selection:
            return
        
        if len(selection) == 1:
            # ========== SINGLE DELETE ==========
            item_id = selection[0]
            item_text = self.tree.item(item_id, 'text')
            item_name = item_text.split(' ', 1)[1] if ' ' in item_text else item_text
            item_type = self.tree.item(item_id, 'values')[0]
            
            # Confirm deletion
            msg = f"Delete '{item_name}'?"
            if item_type == 'folder':
                msg += "\n\n⚠️ This will remove the folder BUT NOT the documents inside!"
            else:
                msg += "\n\n⚠️ This will delete the document from the library permanently!"
            
            if not messagebox.askyesno("Confirm Delete", msg, icon='warning'):
                return
            
            # Use tree hierarchy to find exact item
            parent_id = self.tree.parent(item_id)
            
            if parent_id == '':
                # Root level
                parent_folder = None
            else:
                # Inside a folder
                parent_text = self.tree.item(parent_id, 'text')
                parent_name = parent_text.split(' ', 1)[1] if ' ' in parent_text else parent_text
                
                _, parent_folder, _ = self.tree_manager.find_item(parent_name, 'folder')
            
            # If it's a document, get the DocumentItem and delete from library
            library_deleted = False
            actual_key = item_name  # The key to use for tree removal
            
            if item_type == 'document':
                doc_item = None
                
                if parent_folder:
                    doc_item, actual_key = self._find_document_in_folder(parent_folder, item_name)
                
                if doc_item:
                    try:
                        result = delete_document(doc_item.doc_id)
                        if result:
                            library_deleted = True
                            print(f"✅ Deleted document '{item_name}' (ID: {doc_item.doc_id}) from library")
                        else:
                            print(f"⚠️ delete_document returned False for '{item_name}' (ID: {doc_item.doc_id})")
                            # Continue anyway - document might not be in library.json
                            library_deleted = True
                    except Exception as e:
                        messagebox.showerror("Delete Error", f"Failed to delete from library:\n{e}")
                        return
                else:
                    print(f"⚠️ Could not find DocumentItem for '{item_name}' in parent folder")
                    print(f"   Parent folder children: {list(parent_folder.children.keys()) if parent_folder else 'None'}")
                    # Still proceed with tree removal
                    library_deleted = True  # Can't delete what we can't find - proceed
            
            # Remove from tree structure
            if parent_folder:
                if actual_key:
                    parent_folder.remove_child(actual_key)
                else:
                    parent_folder.remove_child(item_name)
            else:
                # Root folder
                self.tree_manager.remove_root_folder(item_name)
            
            # Save tree immediately (no need for user to click Save All Changes)
            self.has_unsaved_changes = True
            self.save_tree(show_message=False)
            self.populate_tree()
            
            if item_type == 'document' and not library_deleted:
                messagebox.showwarning("Partial Delete", 
                    f"'{item_name}' removed from tree view, but could not verify library deletion.\n"
                    f"The document may reappear next time you open the library.")
            else:
                messagebox.showinfo("Deleted", f"'{item_name}' permanently deleted.")
        
        else:
            # ========== MULTIPLE DELETE ==========
            items_to_delete = []
            
            # Collect items with parent information
            for item_id in selection:
                item_text = self.tree.item(item_id, 'text')
                item_name = item_text.split(' ', 1)[1] if ' ' in item_text else item_text
                item_type = self.tree.item(item_id, 'values')[0]
                
                parent_id = self.tree.parent(item_id)
                if parent_id == '':
                    parent_name = None
                else:
                    parent_text = self.tree.item(parent_id, 'text')
                    parent_name = parent_text.split(' ', 1)[1] if ' ' in parent_text else parent_text
                
                items_to_delete.append({
                    'name': item_name,
                    'type': item_type,
                    'parent_name': parent_name
                })
            
            # Confirm
            msg = f"Delete {len(items_to_delete)} items?"
            msg += "\n\n⚠️ This will permanently delete all selected items!"
            
            if not messagebox.askyesno("Confirm Delete", msg, icon='warning'):
                return
            
            # Delete all
            success_count = 0
            failed_items = []
            
            for item_info in items_to_delete:
                try:
                    item_name = item_info['name']
                    item_type = item_info['type']
                    parent_name = item_info['parent_name']
                    
                    # Find parent and item
                    if parent_name is None:
                        # Root level
                        if item_type == 'folder':
                            if item_name in self.tree_manager.root_folders:
                                self.tree_manager.remove_root_folder(item_name)
                                success_count += 1
                            else:
                                failed_items.append(f"{item_name}: Not found")
                        # Documents shouldn't be at root
                    else:
                        # Find parent folder
                        _, parent_folder, _ = self.tree_manager.find_item(parent_name, 'folder')
                        
                        if not parent_folder:
                            failed_items.append(f"{item_name}: Parent folder not found")
                            continue
                        
                        # Find the item using robust lookup
                        doc_item, actual_key = self._find_document_in_folder(parent_folder, item_name)
                        
                        # If document, delete from library
                        if item_type == 'document':
                            if doc_item:
                                try:
                                    delete_document(doc_item.doc_id)
                                    print(f"✅ Deleted '{item_name}' (ID: {doc_item.doc_id})")
                                except Exception as e:
                                    failed_items.append(f"{item_name}: {str(e)}")
                                    continue
                            else:
                                print(f"⚠️ Could not find DocumentItem for '{item_name}' in {parent_name}")
                        
                        # Remove from tree
                        if actual_key:
                            parent_folder.remove_child(actual_key)
                        else:
                            parent_folder.remove_child(item_name)
                        success_count += 1
                    
                except Exception as e:
                    failed_items.append(f"{item_name}: {str(e)}")
            
            # Save tree immediately
            self.has_unsaved_changes = True
            self.save_tree(show_message=False)
            self.populate_tree()
            
            # Show results
            if failed_items:
                msg = f"Deleted {success_count} item(s).\n\n"
                msg += f"Failed: {len(failed_items)} item(s)\n\n"
                msg += "\n".join(failed_items[:5])
                if len(failed_items) > 5:
                    msg += f"\n... and {len(failed_items) - 5} more"
                messagebox.showwarning("Partial Success", msg)
            else:
                messagebox.showinfo("Deleted", f"Successfully deleted {success_count} item(s) permanently.")


    # ========== Override: Rename ==========
    
    def rename_selected(self):
        """Rename selected item - override to update library too"""
        if not self.last_selected_item_id:
            return
        
        item_id = self.last_selected_item_id
        item_text = self.tree.item(item_id, 'text')
        old_name = item_text.split(' ', 1)[1] if ' ' in item_text else item_text
        item_type = self.tree.item(item_id, 'values')[0]
        
        # Show rename dialog
        dialog = tk.Toplevel(self.parent)
        dialog.title(f"Rename {item_type.title()}")
        dialog.geometry("450x200")
        dialog.transient(self.parent)
        dialog.grab_set()
        
        ttk.Label(dialog, text=f"Rename {item_type.title()}", 
                 font=('Arial', 12, 'bold')).pack(pady=10)
        
        info_frame = ttk.Frame(dialog)
        info_frame.pack(fill=tk.X, padx=20, pady=5)
        ttk.Label(info_frame, text="Current name:", font=('Arial', 9)).pack(anchor=tk.W)
        ttk.Label(info_frame, text=old_name, font=('Arial', 10, 'bold'), 
                 foreground='gray').pack(anchor=tk.W, padx=10)
        
        ttk.Label(dialog, text="New name:", font=('Arial', 10)).pack(anchor=tk.W, padx=20, pady=(10, 5))
        name_var = tk.StringVar(value=old_name)
        name_entry = ttk.Entry(dialog, textvariable=name_var, width=50, font=('Arial', 10))
        name_entry.pack(padx=20, pady=5, fill=tk.X)
        name_entry.select_range(0, tk.END)
        name_entry.focus()
        
        def do_rename():
            new_name = name_var.get().strip()
            
            if not new_name:
                messagebox.showerror("Error", "Name cannot be empty")
                return
            
            if new_name == old_name:
                dialog.destroy()
                return
            
            # Find the item
            parent, item, depth = self.tree_manager.find_item(old_name, item_type)
            
            if not item:
                messagebox.showerror("Error", f"{item_type.title()} not found")
                return
            
            # For documents, also rename in library
            if item_type == 'document' and isinstance(item, DocumentItem):
                try:
                    rename_document(item.doc_id, new_name)
                except Exception as e:
                    messagebox.showerror("Rename Error", f"Failed to rename in library:\n{e}")
                    return
            
            # Check for name collision
            if parent:
                if parent.has_child(new_name):
                    messagebox.showerror("Error", f"An item named '{new_name}' already exists")
                    return
            else:
                if new_name in self.tree_manager.root_folders:
                    messagebox.showerror("Error", f"A folder named '{new_name}' already exists")
                    return
            
            # Rename in tree
            old_key = item.name
            item.name = new_name
            
            if parent:
                # Update parent's children dict
                parent.children[new_name] = parent.children.pop(old_key)
            else:
                # It's a root folder
                self.tree_manager.root_folders[new_name] = self.tree_manager.root_folders.pop(old_key)
            
            self.has_unsaved_changes = True
            self.populate_tree()
            dialog.destroy()
            messagebox.showinfo("Renamed", f"Renamed to '{new_name}'")
        
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=15)
        ttk.Button(btn_frame, text="✓ Rename", command=do_rename, width=12).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy, width=12).pack(side=tk.LEFT, padx=5)
        
        name_entry.bind('<Return>', lambda e: do_rename())
        dialog.bind('<Escape>', lambda e: dialog.destroy())
    
    # ========== Save Tree ==========
    
    def save_tree(self, show_message=True):
        """Save the entire document tree structure"""
        self.save_folder_states()  # ← ADD THIS LINE!

        tree_dict = self.tree_manager.to_dict()
        
        # Save to file
        tree_path = self.library_path.replace('.json', '_tree.json')
        
        try:
            import json
            temp_path = tree_path + ".tmp"
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(tree_dict, f, indent=2, ensure_ascii=False)
            
            os.replace(temp_path, tree_path)
            
            self.has_unsaved_changes = False
            
            if show_message:
                messagebox.showinfo("Saved", 
                                  f"Document library structure saved!\n\n"
                                  f"Location: {tree_path}\n"
                                  f"{len(self.tree_manager.root_folders)} folders")
        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save tree structure:\n{e}")
    
    def on_close(self):
        """Handle close with unsaved changes check"""
        if self.has_unsaved_changes:
            response = messagebox.askyesnocancel(
                "Unsaved Changes",
                "You have unsaved changes. Save before closing?"
            )
            if response is None:  # Cancel
                return
            elif response:  # Yes
                self.save_tree()
        
        self.parent.destroy()


# ============================================================================
# HELPER FUNCTIONS FOR MAIN.PY INTEGRATION
# ============================================================================

def load_document_tree(library_path: str) -> TreeManager:
    """Load document tree from file, or create from flat library"""
    import json
    
    tree_path = library_path.replace('.json', '_tree.json')
    
    if os.path.exists(tree_path):
        # Load existing tree
        try:
            with open(tree_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            def node_factory(child_data):
                return DocumentItem.from_dict(child_data)
            
            tree = TreeManager.from_dict(data, node_factory)
            print(f"✅ Loaded document tree with {len(tree.root_folders)} folders")
            
            # Sync with actual library (add new docs)
            sync_tree_with_library(tree, library_path)
            return tree
        except Exception as e:
            print(f"❌ Error loading tree: {e}")
            # Fall through to create new
    
    # Create new tree from scratch
    tree = TreeManager()
    
    # Create default folders
    tree.add_root_folder(FolderNode("Sources"))
    tree.add_root_folder(FolderNode("AI Responses"))
    tree.add_root_folder(FolderNode("My Documents"))
    
    # Populate with existing documents
    sync_tree_with_library(tree, library_path)
    
    print(f"✅ Created new document tree with {len(tree.root_folders)} folders")
    return tree


def sync_tree_with_library(tree: TreeManager, library_path: str):
    """Sync tree with actual document library - add missing docs to General folder"""
    all_docs = get_all_documents()
    
    # Get all doc IDs in tree
    def get_doc_ids_in_tree():
        ids = set()
        
        def collect_from_folder(folder):
            for child in folder.children.values():
                if isinstance(child, DocumentItem):
                    ids.add(child.doc_id)
                elif isinstance(child, FolderNode):
                    collect_from_folder(child)
        
        for root_folder in tree.root_folders.values():
            collect_from_folder(root_folder)
        
        return ids
    
    existing_ids = get_doc_ids_in_tree()
    
    # Find docs not in tree
    new_docs = [doc for doc in all_docs if doc['id'] not in existing_ids]
    
    if new_docs:
        # Ensure General folder exists as fallback
        if "General" not in tree.root_folders:
            tree.add_root_folder(FolderNode("General"))
        
        general_folder = tree.root_folders["General"]
        
        # Helper to find which folder contains a document by its ID
        def find_folder_containing_doc(doc_id):
            """Find the folder that contains a document with the given ID"""
            def search_folder(folder, path=""):
                for child_name, child in folder.children.items():
                    if isinstance(child, DocumentItem):
                        if child.doc_id == doc_id:
                            return folder
                    elif isinstance(child, FolderNode):
                        result = search_folder(child, f"{path}/{child_name}")
                        if result:
                            return result
                return None
            
            for folder_name, root_folder in tree.root_folders.items():
                result = search_folder(root_folder)
                if result:
                    return result
            return None
        
        # Helper to extract source document ID from ai_response source field
        def get_source_doc_id(source_info):
            """Try to find a matching source document ID from the source info"""
            if not source_info:
                return None
            
            # The source field might contain the original source URL/path
            # We need to find a document that has this as its source
            for doc in all_docs:
                if doc.get('source') == source_info:
                    return doc['id']
                # Also check if source_info contains the doc's source
                doc_source = doc.get('source', '')
                if doc_source and doc_source in source_info:
                    return doc['id']
            return None
        
        # Add new docs - responses go with their source, others to General
        for doc in new_docs:
            doc_item = DocumentItem(
                doc_id=doc['id'],
                title=doc.get('title', 'Untitled'),
                doc_type=doc.get('type', 'unknown'),
                document_class=doc.get('document_class', 'source')
            )
            doc_item.source = doc.get('source')
            doc_item.created = doc.get('created')
            
            # Check for thread
            from document_library import load_thread_from_document
            try:
                thread = load_thread_from_document(doc['id'])
                doc_item.has_thread = bool(thread and len(thread) > 0)
            except:
                pass
            
            # Determine target folder
            target_folder = general_folder
            
            # For AI responses, try to place in same folder as source document
            if doc.get('type') == 'ai_response':
                source_info = doc.get('source', '')
                source_doc_id = get_source_doc_id(source_info)
                
                if source_doc_id:
                    source_folder = find_folder_containing_doc(source_doc_id)
                    if source_folder:
                        target_folder = source_folder
                        print(f"📁 Placing response with source in folder")
            
            target_folder.add_child(doc_item)
        
        print(f"ℹ️  Added {len(new_docs)} new documents")


def open_document_tree_manager(parent, library_path: str, 
                               on_load_document: Callable = None,
                               on_send_to_input: Callable = None,
                               config: dict = None):
    """
    Open the Documents Library window.
    
    Args:
        parent: Parent window
        library_path: Path to document_library.json
        on_load_document: Callback to load document in main window (receives doc_id)
        on_send_to_input: Callback to send source paths to main input box (receives list of paths)
        config: Config dict
    """
    # Load tree
    tree = load_document_tree(library_path)
    
    # Create window
    window = tk.Toplevel(parent)
    window.title("Documents Library")
    
    # Set size and position - same as Prompts Library
    window_width = 720
    window_height = 506
    
    window.update_idletasks()
    
    # Position in top-left corner
    x_position = 0
    y_position = 0
    
    window.geometry(f"{window_width}x{window_height}+{x_position}+{y_position}")
    
    # Dummy save function
    def save_func():
        pass
    
    # Create UI
    ui = DocumentTreeManagerUI(
        parent=window,
        tree_manager=tree,
        library_path=library_path,
        save_func=save_func,
        on_load_document=on_load_document,
        on_send_to_input=on_send_to_input,
        config=config
    )
    
    # Set window close protocol
    window.protocol("WM_DELETE_WINDOW", ui.on_close)
    
    return ui
