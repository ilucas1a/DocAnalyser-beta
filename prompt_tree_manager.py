"""
prompt_tree_manager.py - VERSION 3.0

Prompts Library with tree structure, drag-drop, and version control.
Built on top of tree_manager_base.py for maximum reusability.

Features:
- 4-level folder hierarchy
- Drag-and-drop organization  
- Version control for prompts
- Edit mode with Ctrl+S save
- Version history dialog
- Windows Explorer-style interface

Author: DocAnalyser Development Team
Date: January 11, 2026
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import datetime
import json
from typing import Optional, Callable

# Import base classes
from tree_manager_base import TreeNode, FolderNode, TreeManager, TreeManagerUI

try:
    from context_help import add_help, HELP_TEXTS
    HELP_AVAILABLE = True
except ImportError:
    HELP_AVAILABLE = False
    def add_help(*args, **kwargs): pass
    HELP_TEXTS = {}


# ============================================================================
# PROMPT VERSION CONTROL
# ============================================================================

class PromptVersion:
    """Single version of a prompt"""
    def __init__(self, text: str, note: str = "", is_default: bool = False, is_system: bool = False):
        self.timestamp = datetime.datetime.now().isoformat()
        self.text = text
        self.note = note
        self.is_default = is_default
        self.is_system = is_system
        self.user_modified = not is_system
    
    def to_dict(self):
        return {
            'timestamp': self.timestamp,
            'text': self.text,
            'note': self.note,
            'is_default': self.is_default,
            'is_system': self.is_system,
            'user_modified': self.user_modified
        }
    
    @staticmethod
    def from_dict(data):
        version = PromptVersion(
            text=data['text'],
            note=data.get('note', ''),
            is_default=data.get('is_default', False),
            is_system=data.get('is_system', False)
        )
        version.timestamp = data.get('timestamp', datetime.datetime.now().isoformat())
        version.user_modified = data.get('user_modified', True)
        return version


# ============================================================================
# PROMPT ITEM - Extends TreeNode
# ============================================================================

class PromptItem(TreeNode):
    """A single prompt with version control - extends TreeNode"""
    
    def __init__(self, name: str, text: str = "", is_system_prompt: bool = False, is_favorite: bool = False):
        super().__init__(name)
        self.is_system_prompt = is_system_prompt
        self.is_favorite = is_favorite  # For hierarchical dropdown organization
        self.last_used = None
        self.versions = []
        self.current_version_index = 0
        self.max_versions = 10
        
        # Create initial version
        initial_version = PromptVersion(text, "Initial version", 
                                       is_default=is_system_prompt, is_system=is_system_prompt)
        self.versions.append(initial_version)
        
        if is_system_prompt:
            self.default_version_index = 0
    
    # ========== TreeNode Implementation ==========
    
    def get_icon(self) -> str:
        """Return icon based on prompt status"""
        base_icon = ""
        
        if self.is_modified_from_default():
            base_icon = "📄⭐"  # Modified system prompt
        elif not self.is_system_prompt:
            base_icon = "📄✏️"  # User-created prompt
        else:
            base_icon = "📄"  # Unmodified system prompt
        
        # Add favorite indicator
        if self.is_favorite:
            base_icon = "⭐" + base_icon
        
        return base_icon
    
    def get_type(self) -> str:
        return "prompt"
    
    def can_be_renamed(self) -> bool:
        return True
    
    def can_be_deleted(self) -> bool:
        return True
    
    def can_be_moved(self) -> bool:
        return True
    
    def to_dict(self) -> dict:
        return {
            'type': 'prompt',
            'name': self.name,
            'is_system_prompt': self.is_system_prompt,
            'is_favorite': self.is_favorite,
            'last_used': self.last_used,
            'current_version_index': self.current_version_index,
            'max_versions': self.max_versions,
            'versions': [v.to_dict() for v in self.versions]
        }
    
    @staticmethod
    def from_dict(data: dict) -> 'PromptItem':
        first_version_text = data['versions'][0]['text'] if data['versions'] else ""
        prompt = PromptItem(
            name=data['name'],
            text=first_version_text,
            is_system_prompt=data.get('is_system_prompt', False),
            is_favorite=data.get('is_favorite', False)
        )
        
        prompt.versions = []
        for v_data in data['versions']:
            prompt.versions.append(PromptVersion.from_dict(v_data))
        
        prompt.current_version_index = data.get('current_version_index', 0)
        prompt.last_used = data.get('last_used')
        prompt.max_versions = data.get('max_versions', 10)
        
        return prompt
    
    # ========== Version Control Methods ==========
    
    def get_current_text(self):
        """Get text of current version"""
        if 0 <= self.current_version_index < len(self.versions):
            return self.versions[self.current_version_index].text
        return ""
    
    def save_new_version(self, text: str, note: str = "User modified"):
        """Save a new version of the prompt"""
        new_version = PromptVersion(text, note, is_default=False, is_system=False)
        self.versions.append(new_version)
        self.current_version_index = len(self.versions) - 1
        
        # Trim old versions (keep default always)
        if len(self.versions) > self.max_versions:
            versions_to_keep = []
            for i, v in enumerate(self.versions):
                if v.is_default or i >= len(self.versions) - self.max_versions:
                    versions_to_keep.append(v)
            self.versions = versions_to_keep
            self.current_version_index = len(self.versions) - 1
    
    def restore_version(self, index: int):
        """Restore a specific version"""
        if 0 <= index < len(self.versions):
            self.current_version_index = index
            return True
        return False
    
    def restore_default(self):
        """Restore to default version"""
        if self.is_system_prompt:
            for i, v in enumerate(self.versions):
                if v.is_default:
                    self.current_version_index = i
                    return True
        return False
    
    def is_modified_from_default(self):
        """Check if modified from default"""
        if not self.is_system_prompt:
            return False
        
        default_text = ""
        for v in self.versions:
            if v.is_default:
                default_text = v.text
                break
        
        return self.get_current_text() != default_text
    
    # ========== Favorite Management ==========
    
    def toggle_favorite(self):
        """Toggle favorite status"""
        self.is_favorite = not self.is_favorite
        return self.is_favorite
    
    def set_favorite(self, is_favorite: bool):
        """Set favorite status"""
        self.is_favorite = is_favorite


# ============================================================================
# PROMPT TREE MANAGER UI - Extends TreeManagerUI
# ============================================================================

class PromptTreeManagerUI(TreeManagerUI):
    """
    Prompts Library UI - extends generic TreeManagerUI.
    Adds prompt-specific features like editing, version history, etc.
    """
    
    def __init__(self, parent, tree_manager: TreeManager, 
                 prompts_path: str, save_func: Callable,
                 refresh_callback: Callable, config: dict = None,
                 use_prompt_callback: Callable = None):
        """
        Initialize Prompts Library UI.
        
        Args:
            parent: Parent window
            tree_manager: TreeManager with prompts
            prompts_path: Path to prompts.json
            save_func: Function to save prompts
            refresh_callback: Callback to refresh main window
            config: Config dict
            use_prompt_callback: Callback to use selected prompt (set text in main window)
        """
        self.prompts_path = prompts_path
        self.save_func_external = save_func
        self.refresh_callback = refresh_callback
        self.use_prompt_callback = use_prompt_callback
        self.config = config or {}
        
        # Editing state
        self.editing_mode = False
        self.current_editing_prompt = None
        self.original_text_before_edit = None
        self._hint_after_id = None
        
        # UI components (will be created)
        self.preview_frame = None
        self.preview_title_label = None
        self.preview_subtitle_label = None
        self.preview_text = None
        self.edit_indicator = None
        
        # Buttons
        self.btn_edit = None
        self.btn_save = None
        self.btn_use = None
        self.btn_history = None
        self.btn_favorite = None
        self.btn_restore_default = None
        
        # Initialize base class
        super().__init__(
            parent=parent,
            tree_manager=tree_manager,
            item_type_name="Prompt",
            on_save_callback=self.save_tree,
            on_item_action=self.use_prompt
        )
    
    # ========== Override UI Creation ==========
    
    def create_ui(self):
        """Create full UI with preview panel"""
        # Create main container
        self.main_frame = ttk.PanedWindow(self.parent, orient=tk.HORIZONTAL)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        
        # LEFT: Tree
        left_frame = ttk.Frame(self.main_frame, relief=tk.RIDGE, borderwidth=2, width=200)
        self.main_frame.add(left_frame, weight=2)  # Wider left pane
        
        # Tree header
        tree_header = ttk.Frame(left_frame)
        tree_header.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(tree_header, text="📁 Prompts Library", 
                 font=('Arial', 12, 'bold')).pack(side=tk.LEFT)
        
        btn_frame = ttk.Frame(tree_header)
        btn_frame.pack(side=tk.RIGHT)
        ttk.Button(btn_frame, text="Expand All", command=self.expand_all, 
                  width=12).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Collapse All", command=self.collapse_all, 
                  width=12).pack(side=tk.LEFT, padx=2)
        
        # Tree controls (2-column layout for 350px left pane)
        controls = ttk.Frame(left_frame)
        controls.pack(fill=tk.X, padx=5, pady=5)
        
        # Row 1: Create operations
        self.btn_new_folder = ttk.Button(controls, text="⊕ Folder", 
                                        command=self.create_new_folder, width=13)
        self.btn_new_folder.grid(row=0, column=0, padx=2, pady=2, sticky=tk.EW)
        
        self.btn_new_item = ttk.Button(controls, text="⊕ Prompt", 
                                      command=self.create_new_item, width=13)
        self.btn_new_item.grid(row=0, column=1, padx=2, pady=2, sticky=tk.EW)
        
        # Row 2: Edit operations
        self.btn_rename = ttk.Button(controls, text="✏️ Rename", 
                                    command=self.rename_selected, width=13, state=tk.DISABLED)
        self.btn_rename.grid(row=1, column=0, padx=2, pady=2, sticky=tk.EW)
        
        self.btn_delete = ttk.Button(controls, text="🗑️ Delete", 
                                    command=self.delete_selected, width=13, state=tk.DISABLED)
        self.btn_delete.grid(row=1, column=1, padx=2, pady=2, sticky=tk.EW)
        
        # Row 3: Move operations
        self.btn_move_up = ttk.Button(controls, text="↑ Up",
                                      command=self.move_selected_up, width=13, state=tk.DISABLED)
        self.btn_move_up.grid(row=2, column=0, padx=2, pady=2, sticky=tk.EW)

        self.btn_move_down = ttk.Button(controls, text="↓ Down",
                                        command=self.move_selected_down, width=13, state=tk.DISABLED)
        self.btn_move_down.grid(row=2, column=1, padx=2, pady=2, sticky=tk.EW)
        
        # Make columns expand evenly
        controls.columnconfigure(0, weight=1)
        controls.columnconfigure(1, weight=1)



        # Tree view
        tree_frame = ttk.Frame(left_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        scrollbar = ttk.Scrollbar(tree_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.tree = ttk.Treeview(tree_frame, yscrollcommand=scrollbar.set, selectmode='browse')
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.tree.yview)
        
        self.tree['columns'] = ('type', 'can_drop')
        self.tree.column('#0', width=240)  # Wider tree column
        self.tree.column('type', width=0, stretch=False)
        self.tree.column('can_drop', width=0, stretch=False)
        
        # Hint label below tree
        ttk.Label(left_frame, text="💡 Double-click a prompt to load it in the main window",
                 foreground='#0066CC', font=('Arial', 8)).pack(anchor=tk.W, padx=5, pady=(0, 3))
        
        # RIGHT: Preview/Edit Panel
        self.create_preview_panel()
        
        # Bind events
        self.tree.bind('<<TreeviewSelect>>', self.on_tree_select)
        self.tree.bind('<Double-Button-1>', self.on_double_click)
        
        # Setup features
        self.setup_drag_drop()
        self.setup_keyboard_shortcuts()
        self.setup_context_menu()
        
        # Populate tree
        self.populate_tree()
        
        # Set initial sash position (60/40 split - left pane wider)
        self.parent.update_idletasks()
        self.main_frame.sashpos(0, 350)  # Position first sash at 510px (60% of 850px)
    
    def create_preview_panel(self):
        """Create preview/edit panel on right"""
        self.preview_frame = ttk.Frame(self.main_frame, relief=tk.RIDGE, borderwidth=2)
        self.main_frame.add(self.preview_frame, weight=1)
        
        # Header
        preview_header = ttk.Frame(self.preview_frame)
        preview_header.pack(fill=tk.X, padx=10, pady=5)
        
        self.preview_title_label = ttk.Label(preview_header, text="Select a prompt", 
                                            font=('Arial', 12, 'bold'))
        self.preview_title_label.pack(anchor=tk.W)
        
        self.preview_subtitle_label = ttk.Label(preview_header, text="", 
                                               font=('Arial', 9), foreground='gray')
        self.preview_subtitle_label.pack(anchor=tk.W)
        
        # Text area
        ttk.Label(self.preview_frame, text="Prompt Text:").pack(anchor=tk.W, padx=10)
        
        text_frame = ttk.Frame(self.preview_frame)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.preview_text = scrolledtext.ScrolledText(text_frame, wrap=tk.WORD, 
                                                      height=10, bg='#FFFDE6', 
                                                      font=('Arial', 10))
        self.preview_text.pack(fill=tk.BOTH, expand=True)
        self.preview_text.config(undo=True, maxundo=-1)
        self.preview_text.config(state=tk.DISABLED)  # Read-only until Edit mode entered
        
        # Editing indicator
        self.edit_indicator = ttk.Label(self.preview_frame, 
                                       text="Double-click text, press F2, or click Edit to modify", 
                                       foreground='gray', font=('Arial', 9, 'italic'))
        self.edit_indicator.pack(anchor=tk.W, padx=10)
        
        # Shortcuts info
        shortcuts_frame = ttk.Frame(self.preview_frame)
        shortcuts_frame.pack(fill=tk.X, padx=10, pady=(0, 5))
        
        ttk.Label(shortcuts_frame, text="⌨️ While editing:", 
                 foreground='#0066CC', font=('Arial', 8, 'bold')).pack(side=tk.LEFT)
        ttk.Label(shortcuts_frame, text="Ctrl+Z: Undo | Ctrl+Y: Redo | Ctrl+S: Save | Esc: Cancel", 
                 foreground='#0066CC', font=('Arial', 8)).pack(side=tk.LEFT, padx=5)
        
        # Action buttons (2-column layout for 370px right pane)
        action_frame = ttk.Frame(self.preview_frame)
        action_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Row 1: Primary actions
        self.btn_edit = ttk.Button(action_frame, text="✏️ Edit", 
                                   command=self.enter_edit_mode, state=tk.DISABLED, width=14)
        self.btn_edit.grid(row=0, column=0, padx=2, pady=2, sticky=tk.EW)
        
        self.btn_use = ttk.Button(action_frame, text="✓ Use Prompt", 
                                 command=self.use_prompt, state=tk.DISABLED, width=14)
        self.btn_use.grid(row=0, column=1, padx=2, pady=2, sticky=tk.EW)
        
        # Row 2: Save and History
        self.btn_save = ttk.Button(action_frame, text="💾 Save", 
                                  command=self.save_current_edit, state=tk.DISABLED, width=14)
        self.btn_save.grid(row=1, column=0, padx=2, pady=2, sticky=tk.EW)
        
        self.btn_history = ttk.Button(action_frame, text="📜 History", 
                                     command=self.show_version_history, state=tk.DISABLED, width=14)
        self.btn_history.grid(row=1, column=1, padx=2, pady=2, sticky=tk.EW)
        
        # Add contextual help to History button
        try:
            add_help(self.btn_history, **HELP_TEXTS.get("prompt_history_button", {}))
        except Exception as e:
            print(f"Warning: Could not add help to History button: {e}")
        
        # Row 3: Favorite toggle
        self.btn_favorite = ttk.Button(action_frame, text="☆ Add to Favorites", 
                                       command=self.toggle_favorite_status, state=tk.DISABLED, width=30)
        self.btn_favorite.grid(row=2, column=0, columnspan=2, padx=2, pady=2, sticky=tk.EW)
        
        # Row 4: Restore default (spans both columns for emphasis)
        self.btn_restore_default = ttk.Button(action_frame, text="🔄 Restore Default", 
                                             command=self.restore_default, state=tk.DISABLED, width=30)
        self.btn_restore_default.grid(row=3, column=0, columnspan=2, padx=2, pady=2, sticky=tk.EW)
        
        # Make columns expand evenly
        action_frame.columnconfigure(0, weight=1)
        action_frame.columnconfigure(1, weight=1)
        
        # Bind text events
        self.preview_text.bind('<Button-1>', self._on_preview_click)
        self.preview_text.bind('<Double-Button-1>', lambda e: self.enter_edit_mode())
        self.preview_text.bind('<Control-s>', lambda e: self.save_current_edit())
        self.preview_text.bind('<Escape>', lambda e: self.exit_edit_mode(save=False))
        
        # Bottom buttons
        bottom_frame = ttk.Frame(self.parent)
        bottom_frame.pack(pady=5)
        
        ttk.Button(bottom_frame, text="💾 Save All Changes", 
                  command=self.save_tree).pack(side=tk.LEFT, padx=5)
        ttk.Button(bottom_frame, text="Close", 
                  command=self.on_close).pack(side=tk.LEFT, padx=5)
    
    # ========== Override: Keyboard Shortcuts (Edit Mode Protection) ==========
    
    def delete_selected(self):
        """Override to prevent deletion while in edit mode"""
        if self.editing_mode:
            print("DEBUG: Ignoring Delete key - currently in edit mode")
            return  # Ignore delete while editing text
        # Call parent class method
        super().delete_selected()
    
    def rename_selected(self):
        """Override to prevent renaming while in edit mode"""
        if self.editing_mode:
            print("DEBUG: Ignoring F2 key - currently in edit mode")
            return  # Ignore rename while editing text
        # Call parent class method
        super().rename_selected()
    
    def cut_selected(self):
        """Override to let text widget handle Ctrl+X while in edit mode"""
        if self.editing_mode:
            return  # Let the text widget handle Ctrl+X natively
        super().cut_selected()
    
    def copy_selected(self):
        """Override to let text widget handle Ctrl+C while in edit mode"""
        if self.editing_mode:
            return  # Let the text widget handle Ctrl+C natively
        super().copy_selected()
    
    def paste(self):
        """Override to let text widget handle Ctrl+V while in edit mode"""
        if self.editing_mode:
            return  # Let the text widget handle Ctrl+V natively
        super().paste()
    
    # ========== Override: Item Selection ==========
    
    def on_item_selected(self, item_name: str, item_type: str):
        """Called when item is selected"""
        if item_type == 'prompt':
            # Find the prompt
            parent, item, depth = self.tree_manager.find_item(item_name, 'prompt')
            if item and isinstance(item, PromptItem):
                self.show_prompt_preview(item)
                self.btn_edit.config(state=tk.NORMAL)
                self.btn_use.config(state=tk.NORMAL)
                self.btn_history.config(state=tk.NORMAL)
                self.btn_favorite.config(state=tk.NORMAL)
                
                # Update favorite button text based on current status
                if item.is_favorite:
                    self.btn_favorite.config(text="⭐ Remove from Favorites")
                else:
                    self.btn_favorite.config(text="☆ Add to Favorites")
                
                if item.is_system_prompt and item.is_modified_from_default():
                    self.btn_restore_default.config(state=tk.NORMAL)
                else:
                    self.btn_restore_default.config(state=tk.DISABLED)
        else:
            # It's a folder
            self.clear_preview()
            self.btn_edit.config(state=tk.DISABLED)
            self.btn_use.config(state=tk.DISABLED)
            self.btn_history.config(state=tk.DISABLED)
            self.btn_favorite.config(state=tk.DISABLED)
            self.btn_restore_default.config(state=tk.DISABLED)
    
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
                # Use prompt
                self.use_prompt()
    
    # ========== Override: Create New Item ==========
    
    def create_new_item(self):
        """Create new prompt"""
        # Get selected parent folder
        parent_folder = None
        parent_depth = 0
        
        if not self.tree_manager.root_folders:
            messagebox.showerror("Error", "Please create a folder first")
            return
        
        selection = self.tree.selection()
        if selection:
            item_id = selection[0]
            item_type = self.tree.item(item_id, 'values')[0]
            if item_type == 'folder':
                item_text = self.tree.item(item_id, 'text')
                parent_name = item_text.split(' ', 1)[1] if ' ' in item_text else item_text
                _, parent_folder, parent_depth = self.tree_manager.find_item(parent_name, 'folder')
        
        # Dialog
        dialog = tk.Toplevel(self.parent)
        dialog.title("Create New Prompt")
        dialog.geometry("500x450")
        dialog.transient(self.parent)
        dialog.grab_set()
        
        ttk.Label(dialog, text="Prompt Name:", font=('Arial', 10)).pack(pady=5, padx=10, anchor=tk.W)
        name_var = tk.StringVar(value="New Prompt")
        name_entry = ttk.Entry(dialog, textvariable=name_var, width=50)
        name_entry.pack(pady=5, padx=10, fill=tk.X)
        name_entry.select_range(0, tk.END)
        
        ttk.Label(dialog, text="Select Folder:", font=('Arial', 10)).pack(pady=5, padx=10, anchor=tk.W)
        folder_names = list(self.tree_manager.root_folders.keys())
        folder_var = tk.StringVar(value=folder_names[0] if folder_names else "")
        folder_combo = ttk.Combobox(dialog, textvariable=folder_var, values=folder_names, 
                                   state='readonly', width=47)
        folder_combo.pack(pady=5, padx=10, fill=tk.X)
        
        ttk.Label(dialog, text="Prompt Text:", font=('Arial', 10)).pack(pady=5, padx=10, anchor=tk.W)
        text_area = scrolledtext.ScrolledText(dialog, wrap=tk.WORD, height=12, width=50)
        text_area.pack(pady=5, padx=10, fill=tk.BOTH, expand=True)
        text_area.insert('1.0', 'Enter your prompt text here...')
        text_area.focus()
        
        def create():
            name = name_var.get().strip()
            folder_name = folder_var.get()
            text = text_area.get('1.0', 'end-1c').strip()
            
            if not name or not text:
                messagebox.showerror("Error", "Name and text cannot be empty")
                return
            
            folder = self.tree_manager.get_root_folder(folder_name)
            if not folder:
                messagebox.showerror("Error", f"Folder '{folder_name}' not found")
                return
            
            if folder.has_child(name):
                messagebox.showerror("Error", f"Prompt '{name}' already exists in this folder")
                return
            
            new_prompt = PromptItem(name, text, is_system_prompt=False)
            folder.add_child(new_prompt)
            self.has_unsaved_changes = True
            self.populate_tree()
            dialog.destroy()
            messagebox.showinfo("Success", f"Created prompt '{name}'")
        
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="Create", command=create).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
    
    # ========== Prompt Preview & Editing ==========
    
    def show_prompt_preview(self, prompt: PromptItem):
        """Show prompt in preview pane"""
        self.preview_title_label.config(text=f"📄 {prompt.name}")
        
        subtitle = []
        if prompt.is_modified_from_default():
            subtitle.append("(Modified from template) ⭐")
        elif not prompt.is_system_prompt:
            subtitle.append("(User-created) ✏️")
        
        if prompt.last_used:
            try:
                last_used_dt = datetime.datetime.fromisoformat(prompt.last_used)
                subtitle.append(f"Last used: {last_used_dt.strftime('%Y-%m-%d %H:%M')}")
            except:
                pass
        
        self.preview_subtitle_label.config(text=" ".join(subtitle))
        
        # Exit edit mode if active
        if self.editing_mode:
            self.exit_edit_mode(save=False)
        
        # Temporarily enable to insert text, then disable again
        self.preview_text.config(state=tk.NORMAL)
        self.preview_text.delete('1.0', tk.END)
        self.preview_text.insert('1.0', prompt.get_current_text())
        self.preview_text.config(state=tk.DISABLED)
        
        self.current_editing_prompt = prompt
    
    def clear_preview(self):
        """Clear preview pane"""
        self.preview_title_label.config(text="Select a prompt")
        self.preview_subtitle_label.config(text="")
        self.preview_text.config(state=tk.NORMAL)
        self.preview_text.delete('1.0', tk.END)
        self.preview_text.config(state=tk.DISABLED)
        self.current_editing_prompt = None
        
        if self.editing_mode:
            self.exit_edit_mode(save=False)
    
    def _on_preview_click(self, event=None):
        """Handle click on preview text - show hint if not in edit mode"""
        if self.editing_mode:
            return  # Already editing, no hint needed
        
        if not self.current_editing_prompt:
            hint_text = "✏️ Select a prompt first, then click Edit"
        else:
            hint_text = "✏️ Click Edit or double-click to start editing"
        
        self.edit_indicator.config(
            text=hint_text,
            foreground='#CC6600', font=('Arial', 9, 'bold')
        )
        # Revert to normal hint after 3 seconds
        if self._hint_after_id:
            self.parent.after_cancel(self._hint_after_id)
        self._hint_after_id = self.parent.after(3000, lambda: self.edit_indicator.config(
            text="Double-click text, press F2, or click Edit to modify",
            foreground='gray', font=('Arial', 9, 'italic')
        ))
    
    def enter_edit_mode(self):
        """Enable editing"""
        print(f"\n{'='*60}")
        print(f"DEBUG enter_edit_mode called")
        
        if not self.current_editing_prompt:
            print(f"DEBUG: No current_editing_prompt set!")
            print(f"{'='*60}\n")
            return
            
        if self.editing_mode:
            print(f"DEBUG: Already in editing mode!")
            print(f"{'='*60}\n")
            return
        
        self.editing_mode = True
        self.original_text_before_edit = self.preview_text.get('1.0', 'end-1c')
        
        print(f"  Prompt: {self.current_editing_prompt.name}")
        print(f"  Original text length: {len(self.original_text_before_edit)}")
        print(f"  Edit mode: {self.editing_mode}")
        
        self.preview_text.config(state=tk.NORMAL, bg='#FFFFCC')
        self.edit_indicator.config(text="✏️ EDITING - Ctrl+S to save, Escape to cancel", 
                                  foreground='#0066CC', font=('Arial', 9, 'bold'))
        self.btn_save.config(state=tk.NORMAL)
        self.btn_edit.config(state=tk.DISABLED, text="✏️ Editing...")
        self.preview_text.focus_set()
        
        print("DEBUG: Edit mode enabled successfully")
        print(f"{'='*60}\n")
    
    def exit_edit_mode(self, save=False):
        """Exit editing mode"""
        print(f"\n{'='*60}")
        print(f"DEBUG exit_edit_mode called: save={save}, editing_mode={self.editing_mode}")
        
        if not self.editing_mode:
            print(f"DEBUG: Not in editing mode, returning early")
            print(f"{'='*60}\n")
            return
        
        if save and self.current_editing_prompt:
            new_text = self.preview_text.get('1.0', 'end-1c')
            print(f"DEBUG: Attempting to save...")
            print(f"  Current prompt: {self.current_editing_prompt.name}")
            print(f"  Original text length: {len(self.original_text_before_edit)}")
            print(f"  New text length: {len(new_text)}")
            print(f"  Text changed: {new_text != self.original_text_before_edit}")
            
            if new_text != self.original_text_before_edit:
                print(f"  Calling save_new_version...")
                self.current_editing_prompt.save_new_version(new_text, "User modified")
                print(f"  Version saved! Total versions: {len(self.current_editing_prompt.versions)}")
                print(f"  Current version index: {self.current_editing_prompt.current_version_index}")
                
                self.has_unsaved_changes = True
                self.populate_tree()  # Refresh icons
                
                # CRITICAL: Update preview text to show saved version
                # Otherwise the text area still shows the editing text
                self.preview_text.delete('1.0', tk.END)
                self.preview_text.insert('1.0', self.current_editing_prompt.get_current_text())
                
                # Don't show messagebox here - let save_current_edit show the final message
            else:
                print(f"  No changes detected, not saving")
        else:
            if not save:
                print(f"DEBUG: save=False, reverting changes")
            if not self.current_editing_prompt:
                print(f"DEBUG: No current_editing_prompt!")
            
            # Revert
            if self.original_text_before_edit is not None:
                self.preview_text.delete('1.0', tk.END)
                self.preview_text.insert('1.0', self.original_text_before_edit)
        
        self.editing_mode = False
        self.preview_text.config(state=tk.DISABLED, bg='#FFFDE6')
        self.edit_indicator.config(text="Double-click text, press F2, or click Edit to modify", 
                                  foreground='gray', font=('Arial', 9, 'italic'))
        self.btn_save.config(state=tk.DISABLED)
        self.btn_edit.config(state=tk.NORMAL, text="✏️ Edit")
        
        print(f"DEBUG: Edit mode exited successfully")
        print(f"{'='*60}\n")
    
    def save_current_edit(self):
        """Save current edit"""
        print(f"DEBUG save_current_edit: Button clicked! Calling exit_edit_mode(save=True)")
        
        if not self.editing_mode:
            print(f"DEBUG save_current_edit: Not in edit mode, nothing to save")
            return
        
        self.exit_edit_mode(save=True)
        
        # CRITICAL: Also save to disk immediately!
        # Otherwise changes are lost if the user closes and reopens the Prompts Library
        print(f"DEBUG save_current_edit: Now saving to disk...")
        self.save_tree(show_message=False)  # Don't show save_tree's message
        
        # Show combined success message
        if self.current_editing_prompt:
            messagebox.showinfo("Saved", f"Prompt version saved and written to disk!\n\nPrompt: {self.current_editing_prompt.name}\nTotal versions: {len(self.current_editing_prompt.versions)}")
    
    # ========== Version History ==========
    
    def show_version_history(self):
        """Show version history dialog"""
        if not self.current_editing_prompt:
            return
        
        prompt = self.current_editing_prompt
        
        # Create dialog
        history_window = tk.Toplevel(self.parent)
        history_window.title(f"Version History: {prompt.name}")
        history_window.geometry("800x600")
        history_window.transient(self.parent)
        
        # Header
        header_frame = ttk.Frame(history_window, padding=10)
        header_frame.pack(fill=tk.X)
        
        ttk.Label(header_frame, text=f"📜 Version History: {prompt.name}", 
                 font=('Arial', 12, 'bold')).pack(anchor=tk.W)
        ttk.Label(header_frame, text=f"Total versions: {len(prompt.versions)} (keeping last 10)", 
                 font=('Arial', 9), foreground='gray').pack(anchor=tk.W)
        
        # Legend
        legend = ttk.Frame(history_window, padding=10)
        legend.pack(fill=tk.X)
        ttk.Label(legend, text="Legend:", font=('Arial', 9, 'bold')).pack(side=tk.LEFT)
        ttk.Label(legend, text="✓ = Current version", font=('Arial', 9), 
                 foreground='green').pack(side=tk.LEFT, padx=10)
        ttk.Label(legend, text="⭐ = Original template", font=('Arial', 9), 
                 foreground='blue').pack(side=tk.LEFT, padx=10)
        
        # List frame
        list_frame = ttk.LabelFrame(history_window, text="Version List (newest first)", padding=10)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        version_listbox = tk.Listbox(list_frame, height=8, font=('Arial', 10), bg='#FFFDE6')
        version_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=version_listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        version_listbox.config(yscrollcommand=scrollbar.set)
        
        # Populate versions
        version_indices = []
        for i, version in enumerate(reversed(prompt.versions)):
            idx = len(prompt.versions) - 1 - i
            version_indices.append(idx)
            timestamp = datetime.datetime.fromisoformat(version.timestamp).strftime("%Y-%m-%d %H:%M")
            current_marker = " ✓ CURRENT" if idx == prompt.current_version_index else ""
            default_marker = " ⭐ ORIGINAL" if version.is_default else ""
            version_listbox.insert(tk.END, f"[{timestamp}] {version.note}{current_marker}{default_marker}")
        
        # Preview frame
        preview_frame = ttk.LabelFrame(history_window, text="Preview", padding=10)
        preview_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        version_text = scrolledtext.ScrolledText(preview_frame, wrap=tk.WORD, height=8, 
                                                font=('Arial', 10), bg='#FFFDE6')
        version_text.pack(fill=tk.BOTH, expand=True)
        
        def on_version_select(event):
            selection = version_listbox.curselection()
            if selection:
                display_idx = selection[0]
                actual_idx = version_indices[display_idx]
                version = prompt.versions[actual_idx]
                version_text.delete('1.0', tk.END)
                version_text.insert('1.0', version.text)
        
        version_listbox.bind('<<ListboxSelect>>', on_version_select)
        
        # Buttons
        btn_frame = ttk.Frame(history_window, padding=10)
        btn_frame.pack(fill=tk.X)
        
        def restore_selected():
            selection = version_listbox.curselection()
            if not selection:
                messagebox.showerror("Error", "Please select a version to restore")
                return
            
            display_idx = selection[0]
            actual_idx = version_indices[display_idx]
            
            if actual_idx == prompt.current_version_index:
                messagebox.showinfo("Already Current", "This version is already current")
                return
            
            # Save current before restoring
            current_text = prompt.get_current_text()
            prompt.save_new_version(current_text, "Auto-saved before restore")
            
            prompt.restore_version(actual_idx)
            self.has_unsaved_changes = True
            history_window.destroy()
            self.show_prompt_preview(prompt)
            self.populate_tree()
            messagebox.showinfo("Restored", "Version restored successfully!")
        
        ttk.Button(btn_frame, text="↶ Restore Selected Version", 
                  command=restore_selected, width=25).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Close", 
                  command=history_window.destroy, width=10).pack(side=tk.LEFT, padx=5)
        
        # Select current version
        current_display_idx = len(prompt.versions) - 1 - prompt.current_version_index
        version_listbox.selection_set(current_display_idx)
        version_listbox.see(current_display_idx)
        version_listbox.event_generate('<<ListboxSelect>>')
    
    def restore_default(self):
        """Restore prompt to default"""
        if not self.current_editing_prompt:
            return
        
        prompt = self.current_editing_prompt
        
        if not prompt.is_system_prompt:
            messagebox.showinfo("Info", "This is a user-created prompt with no default template")
            return
        
        if not messagebox.askyesno("Confirm Restore", 
                                   f"Restore '{prompt.name}' to original template?"):
            return
        
        # Save current first
        current_text = prompt.get_current_text()
        prompt.save_new_version(current_text, "Auto-saved before restoring default")
        
        if prompt.restore_default():
            self.has_unsaved_changes = True
            self.show_prompt_preview(prompt)
            self.populate_tree()
            messagebox.showinfo("Restored", "Original template restored!")
        else:
            messagebox.showerror("Error", "Could not find default version")
    
    # ========== Use Prompt ==========

    def use_prompt(self):
        """Use the selected prompt"""
        if not self.current_editing_prompt:
            return

        prompt = self.current_editing_prompt
        prompt.last_used = datetime.datetime.now().isoformat()
        self.has_unsaved_changes = True

        # Get the current prompt text
        prompt_text = prompt.get_current_text()
        prompt_name = prompt.name

        # CRITICAL FIX: Call callbacks BEFORE destroying window
        # This ensures they run in the proper Tkinter context

        # 1. Refresh the dropdown list (updates self.prompts in main window)
        if self.refresh_callback:
            self.refresh_callback()

        # 2. Actually set the prompt text in the main window
        if self.use_prompt_callback:
            self.use_prompt_callback(prompt_name, prompt_text)

        # 3. Schedule window close AFTER callbacks complete
        # Using after() ensures everything finishes before destroying
        self.parent.after(100, self.parent.destroy)

    # ========== Favorite Management ==========
    
    def toggle_favorite_status(self):
        """Toggle the favorite status of the currently selected prompt"""
        if not self.current_editing_prompt:
            return
        
        prompt = self.current_editing_prompt
        prompt.toggle_favorite()
        self.has_unsaved_changes = True
        
        # Update button text
        if prompt.is_favorite:
            self.btn_favorite.config(text="⭐ Remove from Favorites")
        else:
            self.btn_favorite.config(text="☆ Add to Favorites")
        
        # Refresh the tree to show updated icon
        self.populate_tree()
        
        # Re-select the current item
        self.select_item_by_name(prompt.name, 'prompt')
    
    # ========== Save Tree ==========
    
    def save_tree(self, show_message=True):
        """Save the entire prompt tree"""
        
        # CRITICAL: If user is currently editing a prompt, save those changes first!
        # Otherwise clicking "Save All Changes" while editing loses the current edits
        if self.editing_mode and self.current_editing_prompt:
            print(f"DEBUG save_tree: Currently in edit mode - saving current edits first...")
            new_text = self.preview_text.get('1.0', 'end-1c')
            original_text = self.original_text_before_edit
            
            if new_text != original_text:
                print(f"DEBUG save_tree: Text changed, committing to prompt...")
                self.current_editing_prompt.save_new_version(new_text, "User modified")
                self.has_unsaved_changes = True
                
                # Update preview text
                self.preview_text.delete('1.0', tk.END)
                self.preview_text.insert('1.0', self.current_editing_prompt.get_current_text())
                
                # Exit edit mode
                self.editing_mode = False
                self.preview_text.config(state=tk.DISABLED, bg='#FFFDE6')
                self.edit_indicator.config(text="Double-click text, press F2, or click Edit to modify", 
                                          foreground='gray', font=('Arial', 9, 'italic'))
                self.btn_save.config(state=tk.DISABLED)
                self.btn_edit.config(state=tk.NORMAL, text="✏️ Edit")
                
                # Refresh tree to show updated icons
                self.populate_tree()
                
                print(f"DEBUG save_tree: Current edits committed and saved")
            else:
                print(f"DEBUG save_tree: No changes in edit mode, proceeding...")
        
        tree_dict = self.tree_manager.to_dict()
        
        # Save directly to file - don't rely on external save function
        # This ensures we save in the correct tree format
        try:
            import json
            import os
            
            # Use atomic write to prevent corruption
            temp_path = self.prompts_path + ".tmp"
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(tree_dict, f, indent=2, ensure_ascii=False)
            
            # Replace old file with new one
            os.replace(temp_path, self.prompts_path)
            
            print(f"DEBUG save_tree: Successfully saved to {self.prompts_path}")
            
            # Verify the file was written
            if os.path.exists(self.prompts_path):
                file_size = os.path.getsize(self.prompts_path)
                print(f"DEBUG save_tree: Verified file exists, size: {file_size} bytes")
                
                # Double-check we can read it back
                with open(self.prompts_path, 'r', encoding='utf-8') as f:
                    verify_data = json.load(f)
                    print(f"DEBUG save_tree: Verified file is valid JSON, version: {verify_data.get('version', 'unknown')}")
            else:
                print(f"DEBUG save_tree: WARNING - File does not exist after save!")
                
        except Exception as e:
            print(f"DEBUG save_tree: Error saving: {e}")
            import traceback
            traceback.print_exc()
            messagebox.showerror("Save Error", f"Failed to save prompts:\n{e}")
            return
        
        # Update in-memory prompts list for Main.py (for backwards compatibility)
        flat_list = []
        
        def collect_prompts(folder):
            for child in folder.children.values():
                if isinstance(child, PromptItem):
                    flat_list.append({
                        'name': child.name,
                        'text': child.get_current_text()
                    })
                elif isinstance(child, FolderNode):
                    collect_prompts(child)
        
        for folder in self.tree_manager.root_folders.values():
            collect_prompts(folder)
        
        print(f"DEBUG save_tree: Collected {len(flat_list)} prompts for in-memory update")
        
        # Note: The prompts list update should be handled by caller through refresh_callback
        
        self.has_unsaved_changes = False
        
        if show_message:
            messagebox.showinfo("Saved", f"Prompt library saved successfully!\n\nLocation: {self.prompts_path}\n{len(flat_list)} prompts in {len(self.tree_manager.root_folders)} folders")
        
        if self.refresh_callback:
            print(f"DEBUG save_tree: Calling refresh_callback")
            self.refresh_callback()
    
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
        
        # Refresh main window dropdown before closing
        if self.refresh_callback:
            self.refresh_callback()
        
        self.parent.destroy()


# ============================================================================
# HELPER FUNCTIONS FOR MAIN.PY INTEGRATION
# ============================================================================

def load_prompts_from_file(filepath: str):
    """Load prompts from file (backwards compatibility)"""
    import json
    import os
    
    if not os.path.exists(filepath):
        return []
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if isinstance(data, dict) and 'version' in data and data['version'] == '2.0':
            # New tree format - convert to flat
            def node_factory(child_data):
                return PromptItem.from_dict(child_data)
            
            tree = TreeManager.from_dict(data, node_factory)
            
            # Convert to flat list
            flat_list = []
            def collect(folder):
                for child in folder.children.values():
                    if isinstance(child, PromptItem):
                        flat_list.append({
                            'name': child.name,
                            'text': child.get_current_text()
                        })
                    elif isinstance(child, FolderNode):
                        collect(child)
            
            for folder in tree.root_folders.values():
                collect(folder)
            
            return flat_list
        else:
            # Old flat format
            return data if isinstance(data, list) else []
    except Exception as e:
        print(f"Error loading prompts: {e}")
        return []


def open_prompt_tree_manager(parent, prompts: list, prompts_path: str,
                             save_func, refresh_callback, config: dict = None,
                             save_config_func = None, use_prompt_callback = None):
    """
    Open the Prompts Library window.
    
    Args:
        parent: Parent window
        prompts: List of prompts (reference will be updated on save)
        prompts_path: Path to prompts.json
        save_func: Save function
        refresh_callback: Callback to refresh main window
        config: Config dict
        save_config_func: Config save function
        use_prompt_callback: Callback to use selected prompt (set text in main window)
    """
    import json
    import os
    
    # Debug output
    print(f"\n{'='*60}")
    print(f"DEBUG open_prompt_tree_manager: Opening Prompts Library")
    print(f"DEBUG: prompts_path = {prompts_path}")
    print(f"DEBUG: File exists? {os.path.exists(prompts_path)}")
    if os.path.exists(prompts_path):
        print(f"DEBUG: File size: {os.path.getsize(prompts_path)} bytes")
    print(f"{'='*60}\n")
    
    # CRITICAL FIX: Always load from FILE first, not from in-memory list
    # This ensures we get the latest saved changes
    def node_factory(child_data):
        return PromptItem.from_dict(child_data)
    
    if os.path.exists(prompts_path):
        try:
            # Load from file
            print(f"DEBUG: Loading prompts from file: {prompts_path}")
            with open(prompts_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if isinstance(data, dict) and 'version' in data:
                # New tree format
                print(f"DEBUG: Loading tree format version {data.get('version')}")
                print(f"DEBUG: Number of root folders: {len(data.get('root_folders', {}))}")
                tree = TreeManager.from_dict(data, node_factory)
            else:
                # Old flat format - migrate
                print(f"DEBUG: Migrating from flat format")
                tree = TreeManager()
                if isinstance(data, list) and data:
                    general_folder = FolderNode("General")
                    for prompt_data in data:
                        prompt = PromptItem(
                            name=prompt_data['name'],
                            text=prompt_data['text'],
                            is_system_prompt=False
                        )
                        general_folder.add_child(prompt)
                    tree.add_root_folder(general_folder)
                else:
                    # Empty or invalid - create default
                    general_folder = FolderNode("General")
                    tree.add_root_folder(general_folder)
        except Exception as e:
            print(f"ERROR loading from file: {e}")
            # Fall back to in-memory list if file load fails
            tree = TreeManager()
            if prompts:
                general_folder = FolderNode("General")
                for prompt_data in prompts:
                    prompt = PromptItem(
                        name=prompt_data['name'],
                        text=prompt_data['text'],
                        is_system_prompt=False
                    )
                    general_folder.add_child(prompt)
                tree.add_root_folder(general_folder)
            else:
                general_folder = FolderNode("General")
                tree.add_root_folder(general_folder)
    else:
        # File doesn't exist - use in-memory list
        print(f"DEBUG: File doesn't exist, using in-memory list")
        tree = TreeManager()
        if prompts:
            general_folder = FolderNode("General")
            for prompt_data in prompts:
                prompt = PromptItem(
                    name=prompt_data['name'],
                    text=prompt_data['text'],
                    is_system_prompt=False
                )
                general_folder.add_child(prompt)
            tree.add_root_folder(general_folder)
        else:
            general_folder = FolderNode("General")
            tree.add_root_folder(general_folder)
    
    # Create window
    window = tk.Toplevel(parent)
    window.title("Prompts Library")
    
    # Set size and position firmly in top-left corner (no overlap, half screen height)
    window_width = 720
    window_height = 500  # Half screen height for typical 1080p display
    
    # Position window after it's created
    window.update_idletasks()
    
    # Position firmly in top-left corner
    x_position = 0
    y_position = 0
    
    window.geometry(f"{window_width}x{window_height}+{x_position}+{y_position}")
    
    # Create UI
    ui = PromptTreeManagerUI(
        parent=window,
        tree_manager=tree,
        prompts_path=prompts_path,
        save_func=save_func,
        refresh_callback=refresh_callback,
        config=config,
        use_prompt_callback=use_prompt_callback
    )
    
    # Set window close protocol to call on_close (handles X button)
    window.protocol("WM_DELETE_WINDOW", ui.on_close)


# Backwards compatibility wrapper
def open_prompt_manager_window(parent, prompts, prompts_path, save_func, 
                               refresh_callback, config=None, save_config_func=None,
                               use_prompt_callback=None):
    """Backwards compatibility wrapper"""
    return open_prompt_tree_manager(parent, prompts, prompts_path, save_func,
                                    refresh_callback, config, save_config_func,
                                    use_prompt_callback)
