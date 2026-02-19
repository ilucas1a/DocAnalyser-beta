"""
tree_manager_base.py - VERSION 1.0

Generic tree manager component with Windows Explorer-style functionality.
Reusable base for Prompts Library, Documents Library, and any hierarchical data.

Features:
- 4-level depth hierarchy
- Full drag-and-drop support
- Keyboard shortcuts (F2, Delete, Ctrl+X/C/V, arrows)
- Right-click context menus
- Visual feedback
- Validation and error handling

Author: DocAnalyser Development Team
Date: January 11, 2026
"""

import tkinter as tk
from tkinter import ttk, messagebox
import json
from typing import Dict, List, Optional, Tuple, Callable, Any
from collections import OrderedDict
from abc import ABC, abstractmethod


# ============================================================================
# CONSTANTS
# ============================================================================

MAX_TREE_DEPTH = 4  # Maximum nesting levels


# ============================================================================
# BASE CLASSES - Override these for specific implementations
# ============================================================================

class TreeNode(ABC):
    """
    Abstract base class for tree nodes (items that appear in the tree).
    
    Subclass this for specific types (PromptItem, DocumentItem, etc.)
    """
    
    def __init__(self, name: str):
        self.name = name
    
    @abstractmethod
    def get_icon(self) -> str:
        """Return icon/emoji for this node type"""
        pass
    
    @abstractmethod
    def get_type(self) -> str:
        """Return type identifier ('prompt', 'document', etc.)"""
        pass
    
    @abstractmethod
    def to_dict(self) -> dict:
        """Serialize to dictionary"""
        pass
    
    @staticmethod
    @abstractmethod
    def from_dict(data: dict) -> 'TreeNode':
        """Deserialize from dictionary"""
        pass
    
    @abstractmethod
    def can_be_renamed(self) -> bool:
        """Check if this node can be renamed"""
        return True
    
    @abstractmethod
    def can_be_deleted(self) -> bool:
        """Check if this node can be deleted"""
        return True
    
    @abstractmethod
    def can_be_moved(self) -> bool:
        """Check if this node can be moved via drag-drop"""
        return True


class FolderNode:
    """
    Folder node - contains other nodes (folders or items).
    This is generic and doesn't need subclassing usually.
    """
    
    def __init__(self, name: str):
        self.name = name
        self.children: OrderedDict[str, Any] = OrderedDict()  # Preserves insertion order
        self.expanded = True
    
    def add_child(self, child):
        """Add a child node"""
        self.children[child.name] = child
    
    def remove_child(self, name: str) -> bool:
        """Remove a child by name"""
        if name in self.children:
            del self.children[name]
            return True
        return False
    
    def get_child(self, name: str):
        """Get child by name"""
        return self.children.get(name)
    
    def has_child(self, name: str) -> bool:
        """Check if child exists"""
        return name in self.children
    
    def get_child_names(self) -> List[str]:
        """Get list of child names in order"""
        return list(self.children.keys())
    
    def get_child_index(self, name: str) -> int:
        """Get index of child in order (-1 if not found)"""
        try:
            return list(self.children.keys()).index(name)
        except ValueError:
            return -1
    
    def move_child_up(self, name: str) -> bool:
        """Move child up one position (returns True if moved)"""
        if name not in self.children:
            return False
        
        names = list(self.children.keys())
        index = names.index(name)
        
        if index == 0:
            return False  # Already at top
        
        # Swap with previous item
        names[index], names[index-1] = names[index-1], names[index]
        
        # Rebuild OrderedDict in new order
        self.children = OrderedDict((n, self.children[n]) for n in names)
        return True
    
    def move_child_down(self, name: str) -> bool:
        """Move child down one position (returns True if moved)"""
        if name not in self.children:
            return False
        
        names = list(self.children.keys())
        index = names.index(name)
        
        if index == len(names) - 1:
            return False  # Already at bottom
        
        # Swap with next item
        names[index], names[index+1] = names[index+1], names[index]
        
        # Rebuild OrderedDict in new order
        self.children = OrderedDict((n, self.children[n]) for n in names)
        return True
    
    def move_child_to_position(self, name: str, new_index: int) -> bool:
        """Move child to specific position (returns True if moved)"""
        if name not in self.children:
            return False
        
        names = list(self.children.keys())
        old_index = names.index(name)
        
        if old_index == new_index:
            return False
        
        # Remove from old position
        names.pop(old_index)
        
        # Insert at new position
        names.insert(new_index, name)
        
        # Rebuild OrderedDict in new order
        self.children = OrderedDict((n, self.children[n]) for n in names)
        return True
    
    def get_depth(self) -> int:
        """Calculate maximum depth of this folder tree"""
        if not self.children:
            return 1
        
        max_child_depth = 0
        for child in self.children.values():
            if isinstance(child, FolderNode):
                child_depth = child.get_depth()
                max_child_depth = max(max_child_depth, child_depth)
        
        return 1 + max_child_depth
    
    def get_icon(self) -> str:
        """Return folder icon"""
        return "📁"
    
    def get_type(self) -> str:
        """Return type identifier"""
        return "folder"
    
    def can_be_renamed(self) -> bool:
        return True
    
    def can_be_deleted(self) -> bool:
        return True
    
    def can_be_moved(self) -> bool:
        return True
    
    def to_dict(self) -> dict:
        """Serialize folder and all children"""
        return {
            'type': 'folder',
            'name': self.name,
            'expanded': self.expanded,
            'children': {name: child.to_dict() for name, child in self.children.items()}
        }
    
    @staticmethod
    def from_dict(data: dict, node_factory: Callable) -> 'FolderNode':
        """
        Deserialize folder from dictionary.
        node_factory: function that creates TreeNode from dict based on type
        """
        folder = FolderNode(data['name'])
        folder.expanded = data.get('expanded', True)
        
        for name, child_data in data.get('children', {}).items():
            if child_data['type'] == 'folder':
                folder.children[name] = FolderNode.from_dict(child_data, node_factory)
            else:
                folder.children[name] = node_factory(child_data)
        
        return folder


class TreeManager:
    """
    Generic tree data structure manager.
    Handles tree operations independent of UI.
    """
    
    def __init__(self):
        self.root_folders: OrderedDict[str, FolderNode] = OrderedDict()
    
    def add_root_folder(self, folder: FolderNode):
        """Add a top-level folder"""
        self.root_folders[folder.name] = folder
    
    def remove_root_folder(self, name: str) -> bool:
        """Remove a top-level folder"""
        if name in self.root_folders:
            del self.root_folders[name]
            return True
        return False
    
    def get_root_folder(self, name: str) -> Optional[FolderNode]:
        """Get a top-level folder"""
        return self.root_folders.get(name)
    
    def find_item(self, item_name: str, item_type: str) -> Tuple[Optional[FolderNode], Any, int]:
        """
        Find an item in the tree.
        
        Returns:
            (parent_folder, item, depth) - parent is None for root folders
        """
        def search_in_folder(folder: FolderNode, depth: int = 1):
            for name, child in folder.children.items():
                # Check if this is the item we're looking for
                if name == item_name:
                    if (item_type == 'folder' and isinstance(child, FolderNode)) or \
                       (item_type != 'folder' and child.get_type() == item_type):
                        return (folder, child, depth)
                
                # Recursively search subfolders
                if isinstance(child, FolderNode):
                    result = search_in_folder(child, depth + 1)
                    if result:
                        return result
            return None
        
        # Check root level
        if item_type == 'folder' and item_name in self.root_folders:
            return (None, self.root_folders[item_name], 0)
        
        # Search in all root folders
        for folder in self.root_folders.values():
            result = search_in_folder(folder)
            if result:
                return result
        
        return (None, None, -1)
    
    def can_move_to(self, source_name: str, source_type: str, 
                    target_name: str, target_type: str) -> Tuple[bool, str]:
        """
        Check if source can be moved to target.
        
        Returns:
            (can_move: bool, reason: str)
        """
        # Can't move to itself
        if source_name == target_name:
            return (False, "Cannot move an item into itself")
        
        # Can only move into folders
        if target_type != 'folder':
            return (False, "Can only move items into folders")
        
        # Find source and target
        source_parent, source_item, source_depth = self.find_item(source_name, source_type)
        target_parent, target_folder, target_depth = self.find_item(target_name, 'folder')
        
        if not source_item or not target_folder:
            return (False, "Source or target not found")
        
        # Check if target is a descendant of source (can't move folder into its own subfolder)
        if source_type == 'folder' and isinstance(source_item, FolderNode):
            if self._is_descendant(source_item, target_folder):
                return (False, "Cannot move a folder into its own subfolder")
        
        # Check depth limit
        if isinstance(source_item, FolderNode):
            source_tree_depth = source_item.get_depth()
            new_depth = target_depth + 1 + source_tree_depth - 1
        else:
            new_depth = target_depth + 1
        
        if new_depth > MAX_TREE_DEPTH:
            return (False, f"Would exceed maximum depth of {MAX_TREE_DEPTH} levels")
        
        # Check for name collision
        if target_folder.has_child(source_name):
            return (False, f"An item named '{source_name}' already exists in the target folder")
        
        return (True, "")
    
    def _is_descendant(self, ancestor: FolderNode, potential_descendant: FolderNode) -> bool:
        """Check if potential_descendant is a descendant of ancestor"""
        if ancestor == potential_descendant:
            return True
        
        for child in ancestor.children.values():
            if isinstance(child, FolderNode):
                if self._is_descendant(child, potential_descendant):
                    return True
        return False
    
    def move_item(self, source_name: str, source_type: str, 
                  target_folder_name: str) -> bool:
        """
        Move an item to a different folder.
        
        Returns:
            True if successful, False otherwise
        """
        # Validate move
        can_move, reason = self.can_move_to(source_name, source_type, 
                                            target_folder_name, 'folder')
        if not can_move:
            return False
        
        # Find items
        source_parent, source_item, _ = self.find_item(source_name, source_type)
        target_parent, target_folder, _ = self.find_item(target_folder_name, 'folder')
        
        if not source_item or not target_folder:
            return False
        
        # Remove from source
        if source_parent is None:
            # It's a root folder
            if source_name in self.root_folders:
                del self.root_folders[source_name]
        else:
            source_parent.remove_child(source_name)
        
        # Add to target
        target_folder.add_child(source_item)
        
        return True
    
    def move_item_up(self, item_name: str, item_type: str) -> bool:
        """
        Move item up one position within its parent folder.
        Returns True if moved, False if already at top or not found.
        """
        parent, item, depth = self.find_item(item_name, item_type)
        
        if parent is None:
            # It's a root folder - move in root_folders
            if item_name not in self.root_folders:
                return False
            
            names = list(self.root_folders.keys())
            index = names.index(item_name)
            
            if index == 0:
                return False  # Already at top
            
            # Swap
            names[index], names[index-1] = names[index-1], names[index]
            self.root_folders = OrderedDict((n, self.root_folders[n]) for n in names)
            return True
        else:
            # Move within parent folder
            return parent.move_child_up(item_name)
    
    def move_item_down(self, item_name: str, item_type: str) -> bool:
        """
        Move item down one position within its parent folder.
        Returns True if moved, False if already at bottom or not found.
        """
        parent, item, depth = self.find_item(item_name, item_type)
        
        if parent is None:
            # It's a root folder - move in root_folders
            if item_name not in self.root_folders:
                return False
            
            names = list(self.root_folders.keys())
            index = names.index(item_name)
            
            if index == len(names) - 1:
                return False  # Already at bottom
            
            # Swap
            names[index], names[index+1] = names[index+1], names[index]
            self.root_folders = OrderedDict((n, self.root_folders[n]) for n in names)
            return True
        else:
            # Move within parent folder
            return parent.move_child_down(item_name)
    
    def can_move_up(self, item_name: str, item_type: str) -> bool:
        """Check if item can be moved up"""
        parent, item, depth = self.find_item(item_name, item_type)
        
        if parent is None:
            # Root folder
            if item_name not in self.root_folders:
                return False
            names = list(self.root_folders.keys())
            return names.index(item_name) > 0
        else:
            # In folder
            if item_name not in parent.children:
                return False
            index = parent.get_child_index(item_name)
            return index > 0
    
    def can_move_down(self, item_name: str, item_type: str) -> bool:
        """Check if item can be moved down"""
        parent, item, depth = self.find_item(item_name, item_type)
        
        if parent is None:
            # Root folder
            if item_name not in self.root_folders:
                return False
            names = list(self.root_folders.keys())
            return names.index(item_name) < len(names) - 1
        else:
            # In folder
            if item_name not in parent.children:
                return False
            index = parent.get_child_index(item_name)
            return index < len(parent.children) - 1
    
    def to_dict(self) -> dict:
        """Serialize entire tree"""
        return {
            'version': '2.0',
            'max_depth': MAX_TREE_DEPTH,
            'root_folders': {name: folder.to_dict() 
                           for name, folder in self.root_folders.items()}
        }
    
    @staticmethod
    def from_dict(data: dict, node_factory: Callable) -> 'TreeManager':
        """
        Deserialize tree from dictionary.
        node_factory: function that creates TreeNode from dict based on type
        """
        tree = TreeManager()
        
        for name, folder_data in data.get('root_folders', {}).items():
            tree.root_folders[name] = FolderNode.from_dict(folder_data, node_factory)
        
        return tree


# ============================================================================
# UI COMPONENT - Generic Tree View with Drag-Drop
# ============================================================================

class TreeManagerUI:
    """
    Generic tree UI component with Windows Explorer-style functionality.
    
    This is the reusable UI component. Subclass this and override:
    - create_item_node() - to create your specific item types
    - on_item_selected() - to show preview/details
    - get_context_menu_items() - to add custom menu items
    """
    
    def __init__(self, parent, tree_manager: TreeManager, 
                 item_type_name: str = "Item",
                 on_save_callback: Callable = None,
                 on_item_action: Callable = None):
        """
        Initialize tree UI.
        
        Args:
            parent: Parent tkinter window
            tree_manager: TreeManager instance
            item_type_name: Display name for items ("Prompt", "Document", etc.)
            on_save_callback: Called when tree needs to be saved
            on_item_action: Called when item is double-clicked or activated
        """
        self.parent = parent
        self.tree_manager = tree_manager
        self.item_type_name = item_type_name
        self.on_save_callback = on_save_callback
        self.on_item_action = on_item_action
        
        # State
        self.has_unsaved_changes = False
        self.clipboard = None  # For cut/copy/paste
        self.clipboard_operation = None  # 'cut' or 'copy'
        self.drag_data = None  # Data being dragged
        self.last_selected_item_id = None
        self.selection_before_press = None  # For preserving multi-selection during drag
        
        # Create UI
        self.create_ui()
        
        # Populate tree
        self.populate_tree()
    
    def create_ui(self):
        """Create the UI components - override to customize"""
        # This creates a basic layout - subclass can override
        self.main_frame = ttk.Frame(self.parent)
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Header
        self.create_header()
        
        # Tree
        self.create_tree_view()
        
        # Setup drag-drop
        self.setup_drag_drop()
        
        # Setup keyboard shortcuts
        self.setup_keyboard_shortcuts()
        
        # Setup context menu
        self.setup_context_menu()
    
    def create_header(self):
        """Create header with buttons"""
        header = ttk.Frame(self.main_frame)
        header.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(header, text=f"📁 {self.item_type_name} Library", 
                 font=('Arial', 12, 'bold')).pack(side=tk.LEFT)
        
        # Expand/Collapse buttons
        btn_frame = ttk.Frame(header)
        btn_frame.pack(side=tk.RIGHT)
        
        ttk.Button(btn_frame, text="Expand All", 
                  command=self.expand_all, width=12).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Collapse All", 
                  command=self.collapse_all, width=12).pack(side=tk.LEFT, padx=2)
    
    def create_tree_view(self):
        """Create the tree view component"""
        # Container frame
        tree_container = ttk.Frame(self.main_frame)
        tree_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Control buttons
        controls = ttk.Frame(tree_container)
        controls.pack(fill=tk.X, pady=(0, 5))
        
        self.btn_new_folder = ttk.Button(controls, text="⊕ New Folder", 
                                        command=self.create_new_folder, width=14)
        self.btn_new_folder.pack(side=tk.LEFT, padx=2)
        
        self.btn_new_item = ttk.Button(controls, text=f"⊕ New {self.item_type_name}", 
                                      command=self.create_new_item, width=14)
        self.btn_new_item.pack(side=tk.LEFT, padx=2)
        
        self.btn_rename = ttk.Button(controls, text="✏️ Rename", 
                                    command=self.rename_selected, width=14, state=tk.DISABLED)
        self.btn_rename.pack(side=tk.LEFT, padx=2)
        
        self.btn_delete = ttk.Button(controls, text="🗑️ Delete", 
                                    command=self.delete_selected, width=14, state=tk.DISABLED)
        self.btn_delete.pack(side=tk.LEFT, padx=2)
        
        # Reorder buttons
        ttk.Label(controls, text=" │ ", foreground='gray').pack(side=tk.LEFT)  # Separator
        
        self.btn_move_up = ttk.Button(controls, text="↑ Move Up", 
                                      command=self.move_selected_up, width=12, state=tk.DISABLED)
        self.btn_move_up.pack(side=tk.LEFT, padx=2)
        
        self.btn_move_down = ttk.Button(controls, text="↓ Move Down", 
                                        command=self.move_selected_down, width=12, state=tk.DISABLED)
        self.btn_move_down.pack(side=tk.LEFT, padx=2)
        
        # Tree view
        tree_frame = ttk.Frame(tree_container)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(tree_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.tree = ttk.Treeview(tree_frame, yscrollcommand=scrollbar.set, 
                                selectmode='extended')  # Multi-select enabled
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.tree.yview)
        
        # Configure columns
        self.tree['columns'] = ('type', 'can_drop')
        self.tree.column('#0', width=400)
        self.tree.column('type', width=0, stretch=False)  # Hidden
        self.tree.column('can_drop', width=0, stretch=False)  # Hidden
        
        # Bind selection
        self.tree.bind('<<TreeviewSelect>>', self.on_tree_select, add='+')
        self.tree.bind('<Double-Button-1>', self.on_double_click, add='+')

    def setup_drag_drop(self):
        """Setup drag-and-drop functionality - motion-based only"""
        # DON'T bind to Button-1 - let Tkinter handle all clicks for selection!
        # Only start drag when mouse actually moves

        # Track where mouse was pressed
        self.mouse_press_x = None
        self.mouse_press_y = None
        self.selection_before_press = None  # Store selection before click

        def on_press(event):
            """Remember where click happened and preserve multi-selection"""
            print(f"\n{'='*80}")
            print(f"🖱️ MOUSE PRESS at ({event.x}, {event.y})")
            
            self.mouse_press_x = event.x
            self.mouse_press_y = event.y
            self.drag_data = None  # Clear any previous drag
            
            # Store current selection
            current_selection = self.tree.selection()
            print(f"   Current selection: {len(current_selection)} item(s)")
            for item_id in current_selection:
                item_text = self.tree.item(item_id, 'text')
                print(f"      - {item_text}")
            
            # Check what item was clicked
            clicked_item = self.tree.identify_row(event.y)
            if clicked_item:
                clicked_text = self.tree.item(clicked_item, 'text')
                print(f"   Clicked on: {clicked_text}")
                print(f"   Is in selection: {clicked_item in current_selection}")
            else:
                print(f"   Clicked on: empty space")
            
            # If clicking on an item that's already selected, and multiple items are selected,
            # preserve the multi-selection (don't let Tkinter deselect the others)
            if clicked_item and clicked_item in current_selection and len(current_selection) > 1:
                print(f"   → PRESERVING multi-selection of {len(current_selection)} items")
                # Store selection to restore after Tkinter processes the click
                self.selection_before_press = current_selection
                
                # Use after_idle to restore selection after Tkinter's handler runs
                def restore_selection():
                    if self.selection_before_press:
                        print(f"   → RESTORING {len(self.selection_before_press)} items")
                        self.tree.selection_set(self.selection_before_press)
                        self.selection_before_press = None
                
                self.tree.after_idle(restore_selection)
            else:
                print(f"   → Single item or empty click - letting Tkinter handle normally")
                self.selection_before_press = None
            
            print(f"{'='*80}\n")

        # Bind handlers - note we DON'T bind to <Button-1> for drag start!
        self.tree.bind('<ButtonPress-1>', on_press, add='+')
        self.tree.bind('<B1-Motion>', self.on_drag_motion, add='+')
        self.tree.bind('<ButtonRelease-1>', self.on_drag_release, add='+')
    
    def setup_keyboard_shortcuts(self):
        """Setup keyboard shortcuts"""
        # F2 - Rename
        self.tree.bind('<F2>', lambda e: self.rename_selected(), add='+')
        self.parent.bind('<F2>', lambda e: self.rename_selected(), add='+')
        
        # Delete - Delete
        self.tree.bind('<Delete>', lambda e: self.delete_selected(), add='+')
        self.parent.bind('<Delete>', lambda e: self.delete_selected(), add='+')
        
        # Ctrl+X - Cut
        self.tree.bind('<Control-x>', lambda e: self.cut_selected(), add='+')
        self.parent.bind('<Control-x>', lambda e: self.cut_selected(), add='+')
        
        # Ctrl+C - Copy
        self.tree.bind('<Control-c>', lambda e: self.copy_selected(), add='+')
        self.parent.bind('<Control-c>', lambda e: self.copy_selected(), add='+')
        
        # Ctrl+V - Paste
        self.tree.bind('<Control-v>', lambda e: self.paste(), add='+')
        self.parent.bind('<Control-v>', lambda e: self.paste(), add='+')
        
        # Enter - Activate item
        self.tree.bind('<Return>', lambda e: self.activate_selected(), add='+')
        
        # Ctrl+Up - Move Up
        self.tree.bind('<Control-Up>', lambda e: self.move_selected_up(), add='+')
        self.parent.bind('<Control-Up>', lambda e: self.move_selected_up(), add='+')
        
        # Ctrl+Down - Move Down
        self.tree.bind('<Control-Down>', lambda e: self.move_selected_down(), add='+')
        self.parent.bind('<Control-Down>', lambda e: self.move_selected_down())
    
    def setup_context_menu(self):
        """Setup right-click context menu"""
        self.context_menu = tk.Menu(self.parent, tearoff=0)
        
        # These are default items - subclass can override get_context_menu_items()
        self.context_menu.add_command(label="✏️ Rename", command=self.rename_selected)
        self.context_menu.add_command(label="🗑️ Delete", command=self.delete_selected)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="↑ Move Up", command=self.move_selected_up)
        self.context_menu.add_command(label="↓ Move Down", command=self.move_selected_down)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="✂️ Cut", command=self.cut_selected)
        self.context_menu.add_command(label="📋 Copy", command=self.copy_selected)
        self.context_menu.add_command(label="📌 Paste", command=self.paste)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="⊕ New Folder", command=self.create_new_folder)
        self.context_menu.add_command(label=f"⊕ New {self.item_type_name}", 
                                     command=self.create_new_item)
        
        # Bind right-click
        self.tree.bind('<Button-3>', self.show_context_menu, add='+')
    
    # ========== TREE POPULATION ==========
    
    def populate_tree(self):
        """Populate tree from tree_manager"""
        print(f"\n{'='*80}")
        print(f"🌳 POPULATE_TREE CALLED")
        print(f"{'='*80}")
        
        # Save current folder expand/collapse states before rebuilding
        self.save_folder_states()
        
        # Count items before delete
        items_before = list(self.tree.get_children())
        print(f"📊 Tree UI has {len(items_before)} root items before clearing")
        
        # Clear and rebuild tree
        self.tree.delete(*self.tree.get_children())
        
        # Verify deletion
        items_after_delete = list(self.tree.get_children())
        print(f"📊 Tree UI has {len(items_after_delete)} root items after clearing")
        if items_after_delete:
            print(f"   ⚠️ WARNING: {len(items_after_delete)} items remain!")
        
        # Count items in tree_manager data structure
        print(f"\n📁 tree_manager DATA STRUCTURE:")
        print(f"   Root folders: {len(self.tree_manager.root_folders)}")
        total_items = 0
        for folder_name, folder in self.tree_manager.root_folders.items():
            item_count = self._count_items_recursive(folder)
            total_items += item_count
            print(f"   - {folder_name}: {item_count} children")
        print(f"   TOTAL items in data structure: {total_items}")
        
        # Rebuild tree from tree_manager
        print(f"\n🔄 Rebuilding UI tree from data structure...")
        for name, folder in self.tree_manager.root_folders.items():
            folder_id = self.tree.insert('', 'end', text=f"📁 {name}", 
                                        values=('folder', 'true'), open=folder.expanded)
            self.populate_folder(folder_id, folder)
        
        # Count items after rebuild
        items_after_rebuild = list(self.tree.get_children())
        print(f"📊 Tree UI has {len(items_after_rebuild)} root items after rebuild")
        print(f"{'='*80}\n")
    
    def _count_items_recursive(self, folder: FolderNode) -> int:
        """Count total items in a folder recursively"""
        count = 0
        for child in folder.children.values():
            if isinstance(child, FolderNode):
                count += 1  # Count the folder itself
                count += self._count_items_recursive(child)  # Count its children
            else:
                count += 1  # Count the item
        return count
    
    def populate_folder(self, parent_id: str, folder: FolderNode):
        """Recursively populate a folder"""
        for name, child in folder.children.items():
            if isinstance(child, FolderNode):
                # It's a subfolder
                child_id = self.tree.insert(parent_id, 'end', text=f"📁 {name}", 
                                          values=('folder', 'true'), open=child.expanded)
                self.populate_folder(child_id, child)
            else:
                # It's an item
                icon = child.get_icon()
                item_type = child.get_type()
                self.tree.insert(parent_id, 'end', text=f"{icon} {name}", 
                               values=(item_type, 'false'))
    
    def save_folder_states(self):
        """Save current expand/collapse state of all folders in the tree"""
        def save_state_recursive(item_id=''):
            """Recursively save folder states"""
            items = self.tree.get_children(item_id)
            for child_id in items:
                item_text = self.tree.item(child_id, 'text')
                item_type = self.tree.item(child_id, 'values')[0]
                
                if item_type == 'folder':
                    # Get folder name (remove icon)
                    folder_name = item_text.split(' ', 1)[1] if ' ' in item_text else item_text
                    
                    # Get current expand state from UI
                    is_open = self.tree.item(child_id, 'open')
                    
                    # Find this folder in tree_manager and update its expanded property
                    if item_id == '':
                        # Root level folder
                        if folder_name in self.tree_manager.root_folders:
                            self.tree_manager.root_folders[folder_name].expanded = is_open
                    else:
                        # Need to find parent folder and update child
                        parent_text = self.tree.item(item_id, 'text')
                        parent_name = parent_text.split(' ', 1)[1] if ' ' in parent_text else parent_text
                        parent_type = self.tree.item(item_id, 'values')[0]
                        
                        if parent_type == 'folder':
                            _, parent_folder, _ = self.tree_manager.find_item(parent_name, 'folder')
                            if parent_folder and hasattr(parent_folder, 'children'):
                                if folder_name in parent_folder.children:
                                    child_folder = parent_folder.children[folder_name]
                                    if isinstance(child_folder, FolderNode):
                                        child_folder.expanded = is_open
                    
                    # Recurse into this folder
                    save_state_recursive(child_id)
        
        save_state_recursive()
    
    def expand_all(self):
        """Expand all folders"""
        def expand_recursive(item_id):
            self.tree.item(item_id, open=True)
            for child in self.tree.get_children(item_id):
                expand_recursive(child)
        
        for item in self.tree.get_children():
            expand_recursive(item)
        
        # Save the expanded states to folder objects
        self.save_folder_states()
    
    def collapse_all(self):
        """Collapse all folders"""
        for item in self.tree.get_children():
            self.tree.item(item, open=False)
        
        # Save the collapsed states to folder objects
        self.save_folder_states()
    
    # ========== DRAG-DROP HANDLERS ==========

    def on_drag_motion(self, event):
        """Handle drag motion - with IMPROVED target identification"""
        # Initialize drag on first motion
        if self.drag_data is None and self.mouse_press_x is not None:
            dx = abs(event.x - self.mouse_press_x)
            dy = abs(event.y - self.mouse_press_y)

            # Need 5px movement to start drag
            if dx < 5 and dy < 5:
                return

            # Start drag - capture current selection
            selection = self.tree.selection()
            if not selection:
                return

            self.drag_data = {
                'item_ids': selection,
                'start_x': self.mouse_press_x,
                'start_y': self.mouse_press_y
            }

        if not self.drag_data:
            return

        # AUTO-SCROLL: Check if near top or bottom edge
        widget_height = self.tree.winfo_height()
        scroll_zone = 30  # pixels from edge to trigger scroll
        scroll_speed = 3  # lines to scroll per event

        if event.y < scroll_zone:
            # Near top - scroll up
            self.tree.yview_scroll(-scroll_speed, 'units')
            self.tree.update_idletasks()
        elif event.y > widget_height - scroll_zone:
            # Near bottom - scroll down
            self.tree.yview_scroll(scroll_speed, 'units')
            self.tree.update_idletasks()

        # ====== FIX FOR BUG #11: Better target identification ======
        # Convert event coordinates to proper tree coordinates
        # Use bbox to verify the target is actually visible
        target_id = self.tree.identify_row(event.y)

        if target_id:
            # Verify target is actually visible by checking its bounding box
            try:
                bbox = self.tree.bbox(target_id)
                if bbox is None:
                    # Item exists but is not visible (scrolled out of view)
                    target_id = None
                else:
                    # Check if mouse Y is actually within this item's bbox
                    item_y_min = bbox[1]
                    item_y_max = bbox[1] + bbox[3]
                    if not (item_y_min <= event.y <= item_y_max):
                        # Mouse is not actually over this item
                        target_id = None
            except:
                target_id = None

        if not target_id:
            self.tree.config(cursor='')
            return

        # Validate the target
        try:
            target_type = self.tree.item(target_id, 'values')[0]
        except:
            self.tree.config(cursor='')
            return

        if target_type == 'folder':
            # Check if valid drop (just check first item)
            source_id = self.drag_data['item_ids'][0]
            source_text = self.tree.item(source_id, 'text')
            source_name = source_text.split(' ', 1)[1] if ' ' in source_text else source_text
            source_type = self.tree.item(source_id, 'values')[0]

            target_text = self.tree.item(target_id, 'text')
            target_name = target_text.split(' ', 1)[1] if ' ' in target_text else target_text

            can_drop, _ = self.tree_manager.can_move_to(
                source_name, source_type, target_name, target_type
            )

            self.tree.config(cursor='hand2' if can_drop else 'X_cursor')
        else:
            self.tree.config(cursor='X_cursor')

    def on_drag_release(self, event):
        """Handle drag release - with PROPER item tracking to prevent ghosts"""
        if not self.drag_data:
            return

        source_ids = self.drag_data['item_ids']

        # Get target
        self.tree.update_idletasks()
        target_id = self.tree.identify_row(event.y)

        # Validate target with bbox check
        if target_id:
            try:
                bbox = self.tree.bbox(target_id)
                if bbox is None:
                    target_id = None
                else:
                    item_y_min = bbox[1]
                    item_y_max = bbox[1] + bbox[3]
                    if not (item_y_min <= event.y <= item_y_max):
                        target_id = None
            except:
                target_id = None

        self.drag_data = None
        self.tree.config(cursor='')

        if not target_id:
            return

        # Get target info
        try:
            target_text = self.tree.item(target_id, 'text')
            target_name = target_text.split(' ', 1)[1] if ' ' in target_text else target_text
            target_type = self.tree.item(target_id, 'values')[0]
        except:
            return

        # Only allow drops on folders
        if target_type != 'folder':
            return

        # ====== FIX FOR BUG #10: Use tree hierarchy instead of find_item() ======
        # Build list of moves with FULL PATH information
        moves_to_execute = []

        for source_id in source_ids:
            if source_id == target_id:
                continue

            try:
                source_text = self.tree.item(source_id, 'text')
                source_name = source_text.split(' ', 1)[1] if ' ' in source_text else source_text
                source_type = self.tree.item(source_id, 'values')[0]

                # Get source parent using tree hierarchy
                source_parent_id = self.tree.parent(source_id)

                if source_parent_id == '':
                    # Root level item
                    source_parent_name = None
                else:
                    source_parent_text = self.tree.item(source_parent_id, 'text')
                    source_parent_name = source_parent_text.split(' ', 1)[
                        1] if ' ' in source_parent_text else source_parent_text

                # Check if move is valid
                can_move, reason = self.tree_manager.can_move_to(
                    source_name, source_type, target_name, target_type
                )

                if can_move:
                    moves_to_execute.append({
                        'source_name': source_name,
                        'source_type': source_type,
                        'source_parent_name': source_parent_name,
                        'target_name': target_name
                    })
            except Exception as e:
                print(f"Error preparing move: {e}")
                continue

        if not moves_to_execute:
            return

        # Execute moves using SPECIFIC parent information
        moved_count = 0
        failed_items = []

        for move_info in moves_to_execute:
            try:
                # Find source item using BOTH name AND parent
                source_name = move_info['source_name']
                source_type = move_info['source_type']
                source_parent_name = move_info['source_parent_name']
                target_name = move_info['target_name']

                # Locate the SPECIFIC item by parent context
                if source_parent_name is None:
                    # Root level
                    if source_type == 'folder':
                        source_item = self.tree_manager.root_folders.get(source_name)
                        source_parent = None
                    else:
                        source_item = None
                        source_parent = None
                else:
                    # Find parent folder first
                    _, source_parent, _ = self.tree_manager.find_item(source_parent_name, 'folder')
                    if source_parent:
                        source_item = source_parent.children.get(source_name)
                    else:
                        source_item = None

                if not source_item:
                    failed_items.append(f"{source_name}: Could not locate item")
                    continue

                # Find target folder
                _, target_folder, _ = self.tree_manager.find_item(target_name, 'folder')

                if not target_folder:
                    failed_items.append(f"{source_name}: Target folder not found")
                    continue

                # Perform the move MANUALLY (not using move_item which uses find_item)
                # Remove from source
                if source_parent is None:
                    # Root level
                    if source_name in self.tree_manager.root_folders:
                        del self.tree_manager.root_folders[source_name]
                else:
                    source_parent.remove_child(source_name)

                # Add to target
                target_folder.add_child(source_item)

                moved_count += 1

            except Exception as e:
                failed_items.append(f"{source_name}: {str(e)}")

        # Update tree
        if moved_count > 0:
            self.has_unsaved_changes = True
            self.populate_tree()

            if failed_items:
                messagebox.showwarning("Partial Success",
                                       f"Moved {moved_count} item(s) to '{target_name}'.\n"
                                       f"Could not move {len(failed_items)} item(s).")
            else:
                messagebox.showinfo("Moved",
                                    f"Moved {moved_count} item(s) to '{target_name}'")

    # ========== SELECTION HANDLERS ==========
    
    def on_tree_select(self, event):
        """Handle tree selection - supports multi-select"""
        selection = self.tree.selection()
        
        if not selection:
            # Nothing selected
            self.btn_rename.config(state=tk.DISABLED)
            self.btn_delete.config(state=tk.DISABLED)
            self.btn_move_up.config(state=tk.DISABLED)
            self.btn_move_down.config(state=tk.DISABLED)
            self.last_selected_item_id = None
            return
        
        # Single or multiple selection
        if len(selection) == 1:
            # Single selection - enable all buttons
            item_id = selection[0]
            self.last_selected_item_id = item_id
            
            self.btn_rename.config(state=tk.NORMAL)
            self.btn_delete.config(state=tk.NORMAL)
            
            # Get item info
            item_text = self.tree.item(item_id, 'text')
            item_name = item_text.split(' ', 1)[1] if ' ' in item_text else item_text
            item_type = self.tree.item(item_id, 'values')[0]
            
            # Update Move Up/Down button states
            if self.tree_manager.can_move_up(item_name, item_type):
                self.btn_move_up.config(state=tk.NORMAL)
            else:
                self.btn_move_up.config(state=tk.DISABLED)
            
            if self.tree_manager.can_move_down(item_name, item_type):
                self.btn_move_down.config(state=tk.NORMAL)
            else:
                self.btn_move_down.config(state=tk.DISABLED)
            
            # Call subclass handler
            self.on_item_selected(item_name, item_type)
        else:
            # Multiple selection
            self.last_selected_item_id = selection[0]  # Store first for reference
            
            # Enable delete, disable rename and move (can't rename/reorder multiple items)
            self.btn_rename.config(state=tk.DISABLED)
            self.btn_delete.config(state=tk.NORMAL)
            self.btn_move_up.config(state=tk.DISABLED)
            self.btn_move_down.config(state=tk.DISABLED)
            
            # Call subclass handler with count
            self.on_multiple_selected(len(selection))
    
    def on_double_click(self, event):
        """Handle double-click"""
        item_id = self.tree.identify_row(event.y)
        if item_id:
            item_text = self.tree.item(item_id, 'text')
            item_name = item_text.split(' ', 1)[1] if ' ' in item_text else item_text
            item_type = self.tree.item(item_id, 'values')[0]
            
            if item_type == 'folder':
                # Toggle folder
                current_state = self.tree.item(item_id, 'open')
                self.tree.item(item_id, open=not current_state)
                
                # Save the new state to the folder object
                self.save_folder_states()
            else:
                # Activate item
                self.activate_selected()
    
    # ========== CRUD OPERATIONS ==========
    
    def create_new_folder(self):
        """Create a new folder"""
        # Get selected parent (if any)
        parent_folder = None
        parent_depth = 0
        
        selection = self.tree.selection()
        if selection:
            item_id = selection[0]
            item_type = self.tree.item(item_id, 'values')[0]
            if item_type == 'folder':
                item_text = self.tree.item(item_id, 'text')
                parent_name = item_text.split(' ', 1)[1] if ' ' in item_text else item_text
                _, parent_folder, parent_depth = self.tree_manager.find_item(parent_name, 'folder')
        
        # Check depth limit
        if parent_depth >= MAX_TREE_DEPTH:
            messagebox.showerror("Depth Limit", 
                               f"Cannot create folder: maximum depth of {MAX_TREE_DEPTH} levels reached")
            return
        
        # Show dialog
        dialog = tk.Toplevel(self.parent)
        dialog.title("Create New Folder")
        dialog.geometry("400x150")
        dialog.transient(self.parent)
        dialog.grab_set()
        
        ttk.Label(dialog, text="Folder Name:", font=('Arial', 10)).pack(pady=10)
        name_var = tk.StringVar(value="New Folder")
        name_entry = ttk.Entry(dialog, textvariable=name_var, width=40)
        name_entry.pack(pady=5)
        name_entry.select_range(0, tk.END)
        name_entry.focus()
        
        if parent_folder:
            ttk.Label(dialog, text=f"Will be created in: {parent_folder.name}", 
                     font=('Arial', 9), foreground='gray').pack()
        
        def create():
            name = name_var.get().strip()
            if not name:
                messagebox.showerror("Error", "Folder name cannot be empty")
                return
            
            # Check if name exists
            if parent_folder:
                if parent_folder.has_child(name):
                    messagebox.showerror("Error", f"Folder '{name}' already exists")
                    return
            else:
                if name in self.tree_manager.root_folders:
                    messagebox.showerror("Error", f"Folder '{name}' already exists")
                    return
            
            # Create folder
            new_folder = FolderNode(name)
            if parent_folder:
                parent_folder.add_child(new_folder)
            else:
                self.tree_manager.add_root_folder(new_folder)
            
            self.has_unsaved_changes = True
            self.populate_tree()
            dialog.destroy()
            messagebox.showinfo("Success", f"Created folder '{name}'")
        
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="Create", command=create).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
        
        name_entry.bind('<Return>', lambda e: create())
    
    def create_new_item(self):
        """Create a new item - override in subclass"""
        # This should be overridden by subclass
        messagebox.showinfo("Info", f"Override create_new_item() to create {self.item_type_name}s")
    
    def rename_selected(self):
        """Rename selected item"""
        if not self.last_selected_item_id:
            return
        
        item_id = self.last_selected_item_id
        item_text = self.tree.item(item_id, 'text')
        old_name = item_text.split(' ', 1)[1] if ' ' in item_text else item_text
        item_type = self.tree.item(item_id, 'values')[0]
        
        # Show rename dialog
        dialog = tk.Toplevel(self.parent)
        dialog.title(f"Rename {item_type.title()}")
        dialog.geometry("450x180")
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
            
            # Check for name collision
            if parent:
                if parent.has_child(new_name):
                    messagebox.showerror("Error", f"An item named '{new_name}' already exists")
                    return
            else:
                if new_name in self.tree_manager.root_folders:
                    messagebox.showerror("Error", f"A folder named '{new_name}' already exists")
                    return
            
            # Rename
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

    def delete_selected(self):
        """Delete selected item(s) - with PROPER item tracking"""
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
                msg += "\n\n⚠️ This will delete the folder and ALL items inside it!"

            if not messagebox.askyesno("Confirm Delete", msg, icon='warning'):
                return

            # Use tree hierarchy to find exact item
            parent_id = self.tree.parent(item_id)

            if parent_id == '':
                # Root level
                if item_type == 'folder' and item_name in self.tree_manager.root_folders:
                    self.tree_manager.remove_root_folder(item_name)
            else:
                # Inside a folder
                parent_text = self.tree.item(parent_id, 'text')
                parent_name = parent_text.split(' ', 1)[1] if ' ' in parent_text else parent_text

                _, parent_folder, _ = self.tree_manager.find_item(parent_name, 'folder')
                if parent_folder:
                    parent_folder.remove_child(item_name)

            self.has_unsaved_changes = True
            self.populate_tree()
            messagebox.showinfo("Deleted", f"'{item_name}' deleted")

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

                    if parent_name is None:
                        # Root level
                        if item_type == 'folder' and item_name in self.tree_manager.root_folders:
                            self.tree_manager.remove_root_folder(item_name)
                            success_count += 1
                    else:
                        # Find parent
                        _, parent_folder, _ = self.tree_manager.find_item(parent_name, 'folder')
                        if parent_folder:
                            parent_folder.remove_child(item_name)
                            success_count += 1
                        else:
                            failed_items.append(f"{item_name}: Parent not found")

                except Exception as e:
                    failed_items.append(f"{item_name}: {str(e)}")

            # Update tree
            self.has_unsaved_changes = True
            self.populate_tree()

            if failed_items:
                msg = f"Deleted {success_count} item(s).\n\n"
                msg += f"Failed: {len(failed_items)} item(s)\n\n"
                msg += "\n".join(failed_items[:5])
                if len(failed_items) > 5:
                    msg += f"\n... and {len(failed_items) - 5} more"
                messagebox.showwarning("Partial Success", msg)
            else:
                messagebox.showinfo("Deleted", f"Deleted {success_count} item(s)")
    
    # ========== REORDER OPERATIONS ==========
    
    def move_selected_up(self):
        """Move selected item up one position"""
        if not self.last_selected_item_id:
            return
        
        item_id = self.last_selected_item_id
        item_text = self.tree.item(item_id, 'text')
        item_name = item_text.split(' ', 1)[1] if ' ' in item_text else item_text
        item_type = self.tree.item(item_id, 'values')[0]
        
        # Try to move
        if self.tree_manager.move_item_up(item_name, item_type):
            self.has_unsaved_changes = True
            
            # Remember selection
            selected_name = item_name
            
            # Repopulate tree
            self.populate_tree()
            
            # Reselect the item (it moved, so we need to find it again)
            self._reselect_item(selected_name, item_type)
    
    def move_selected_down(self):
        """Move selected item down one position"""
        if not self.last_selected_item_id:
            return
        
        item_id = self.last_selected_item_id
        item_text = self.tree.item(item_id, 'text')
        item_name = item_text.split(' ', 1)[1] if ' ' in item_text else item_text
        item_type = self.tree.item(item_id, 'values')[0]
        
        # Try to move
        if self.tree_manager.move_item_down(item_name, item_type):
            self.has_unsaved_changes = True
            
            # Remember selection
            selected_name = item_name
            
            # Repopulate tree
            self.populate_tree()
            
            # Reselect the item
            self._reselect_item(selected_name, item_type)
    
    def _reselect_item(self, item_name: str, item_type: str):
        """Helper to reselect an item after tree refresh"""
        def find_item_recursive(parent_id=''):
            for item_id in self.tree.get_children(parent_id):
                item_text = self.tree.item(item_id, 'text')
                name = item_text.split(' ', 1)[1] if ' ' in item_text else item_text
                i_type = self.tree.item(item_id, 'values')[0]
                
                if name == item_name and i_type == item_type:
                    self.tree.selection_set(item_id)
                    self.tree.see(item_id)
                    self.tree.focus(item_id)
                    return True
                
                # Search children
                if find_item_recursive(item_id):
                    return True
            return False
        
        find_item_recursive()
    
    # ========== CUT/COPY/PASTE ==========
    
    def cut_selected(self):
        """Cut selected item"""
        if not self.last_selected_item_id:
            return
        
        item_id = self.last_selected_item_id
        item_text = self.tree.item(item_id, 'text')
        item_name = item_text.split(' ', 1)[1] if ' ' in item_text else item_text
        item_type = self.tree.item(item_id, 'values')[0]
        
        self.clipboard = (item_name, item_type)
        self.clipboard_operation = 'cut'
        
        # Visual feedback (gray out item)
        self.tree.item(item_id, tags=('cut',))
        self.tree.tag_configure('cut', foreground='gray')
        
        print(f"Cut: {item_name}")
    
    def copy_selected(self):
        """Copy selected item"""
        if not self.last_selected_item_id:
            return
        
        item_id = self.last_selected_item_id
        item_text = self.tree.item(item_id, 'text')
        item_name = item_text.split(' ', 1)[1] if ' ' in item_text else item_text
        item_type = self.tree.item(item_id, 'values')[0]
        
        self.clipboard = (item_name, item_type)
        self.clipboard_operation = 'copy'
        
        print(f"Copy: {item_name}")
    
    def paste(self):
        """Paste clipboard contents"""
        if not self.clipboard:
            messagebox.showinfo("Nothing to Paste", "Clipboard is empty")
            return
        
        # Get target folder
        target_folder = None
        target_name = None
        
        if self.last_selected_item_id:
            item_id = self.last_selected_item_id
            item_type = self.tree.item(item_id, 'values')[0]
            if item_type == 'folder':
                item_text = self.tree.item(item_id, 'text')
                target_name = item_text.split(' ', 1)[1] if ' ' in item_text else item_text
        
        if not target_name:
            messagebox.showinfo("No Target", "Please select a folder to paste into")
            return
        
        source_name, source_type = self.clipboard
        
        # Check if can move/copy
        can_move, reason = self.tree_manager.can_move_to(
            source_name, source_type, target_name, 'folder'
        )
        
        if not can_move:
            messagebox.showerror("Cannot Paste", reason)
            return
        
        if self.clipboard_operation == 'cut':
            # Move
            if self.tree_manager.move_item(source_name, source_type, target_name):
                self.clipboard = None
                self.clipboard_operation = None
                self.has_unsaved_changes = True
                self.populate_tree()
                messagebox.showinfo("Moved", f"'{source_name}' moved to '{target_name}'")
        else:
            # Copy (would need to deep copy the item)
            messagebox.showinfo("Not Implemented", "Copy functionality not yet implemented")
    
    # ========== CONTEXT MENU ==========
    
    def show_context_menu(self, event):
        """Show context menu"""
        item_id = self.tree.identify_row(event.y)
        if item_id:
            self.tree.selection_set(item_id)
            self.tree.focus(item_id)
            self.tree.event_generate('<<TreeviewSelect>>')
        
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()
    
    # ========== ABSTRACT METHODS - Override in subclass ==========
    
    def on_item_selected(self, item_name: str, item_type: str):
        """Called when an item is selected - override in subclass"""
        pass
    
    def on_multiple_selected(self, count: int):
        """Called when multiple items are selected - override in subclass"""
        pass
    
    def activate_selected(self):
        """Called when item is activated (double-click/Enter) - override in subclass"""
        pass
    
    def create_item_node(self, name: str, **kwargs) -> TreeNode:
        """Create a new item node - override in subclass"""
        raise NotImplementedError("Subclass must implement create_item_node()")
    
    def get_context_menu_items(self) -> List[Tuple[str, Callable]]:
        """Get custom context menu items - override in subclass"""
        return []


# ============================================================================
# TESTING / EXAMPLE
# ============================================================================

if __name__ == "__main__":
    print("tree_manager_base.py - Generic tree component")
    print("This is a base module. Import and subclass TreeNode and TreeManagerUI")
    print("See prompt_tree_manager.py for example implementation")
