"""
branch_picker_dialog.py

Enhanced dialog for selecting which conversation branch(es) to add a response to,
with support for:
- Multi-select (save to multiple branches at once)
- Pre-selecting current conversation
- Option to stay in current view after saving (capture thought without diversion)

This implements the architecture where:
- Source documents contain only the raw content (no threads)
- Response documents contain AI conversations about a source
- Multiple response branches can exist for one source document
- A single response can be saved to multiple branches
"""

import tkinter as tk
from tkinter import ttk, simpledialog, messagebox
from typing import Optional, List, Dict, Tuple
import datetime


class BranchPickerDialog:
    """
    Enhanced dialog for selecting conversation branch(es) when following up.
    
    Features:
    - Multi-select: Save response to one or more existing branches
    - Create new branch option
    - Pre-selects current conversation (if provided)
    - Option to stay in current view after saving
    - Returns list of selected branch IDs and navigation preference
    """
    
    def __init__(
        self,
        parent: tk.Tk,
        source_document_id: str,
        source_title: str,
        existing_branches: List[Dict],
        current_branch_id: Optional[str] = None,
        current_mode: str = 'source',
        action_description: str = "save this response"
    ):
        """
        Initialize the branch picker dialog.
        
        Args:
            parent: Parent window
            source_document_id: ID of the source document
            source_title: Title of the source document (for display)
            existing_branches: List of dicts with branch info:
                [{'doc_id': str, 'title': str, 'exchange_count': int, 'last_updated': str}, ...]
            current_branch_id: ID of currently active branch (to pre-select)
            current_mode: Current viewing mode ('source' or 'conversation')
            action_description: What we're doing (e.g., "save this response")
        """
        self.parent = parent
        self.source_document_id = source_document_id
        self.source_title = source_title
        self.existing_branches = existing_branches
        self.current_branch_id = current_branch_id
        self.current_mode = current_mode
        self.action_description = action_description
        
        # Results
        self.selected_branch_ids = []  # List of selected existing branch IDs
        self.new_branch_names = []     # List of new branch names to create
        self.stay_in_current_view = False  # Whether to stay in current view after saving
        self.cancelled = False
        
        # Checkbox variables for existing branches
        self.branch_vars = {}  # doc_id -> BooleanVar
        self.create_new_var = tk.BooleanVar(value=False)
        self.new_branch_name_var = tk.StringVar(value="")
        self.stay_here_var = tk.BooleanVar(value=(current_mode == 'source'))  # Default based on mode
        
        self._create_dialog()
    
    def _create_dialog(self):
        """Create and show the dialog."""
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title("Where to Save Response")
        self.dialog.transient(self.parent)
        self.dialog.grab_set()
        
        # Size based on content
        width = 520
        height = 480 + min(len(self.existing_branches) * 35, 180)
        
        # Center on parent
        self.dialog.geometry(f"{width}x{height}")
        self.dialog.update_idletasks()
        x = self.parent.winfo_x() + (self.parent.winfo_width() - width) // 2
        y = self.parent.winfo_y() + (self.parent.winfo_height() - height) // 2
        self.dialog.geometry(f"+{x}+{y}")
        
        # Main frame with padding
        main_frame = ttk.Frame(self.dialog, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Header
        header_label = ttk.Label(
            main_frame,
            text="Where should this response be saved?",
            font=('Arial', 12, 'bold')
        )
        header_label.pack(anchor=tk.W, pady=(0, 5))
        
        # Source info
        source_display = self.source_title[:55] + "..." if len(self.source_title) > 55 else self.source_title
        source_label = ttk.Label(
            main_frame,
            text=f"Source: {source_display}",
            font=('Arial', 9),
            foreground='#666666'
        )
        source_label.pack(anchor=tk.W, pady=(0, 10))
        
        # Explanation
        explain_text = (
            "Select one or more conversations to save this response to.\n"
            "You can also create a new conversation branch."
        )
        explain_label = ttk.Label(
            main_frame,
            text=explain_text,
            font=('Arial', 10),
            wraplength=width - 60
        )
        explain_label.pack(anchor=tk.W, pady=(0, 15))
        
        # Existing branches section (if any)
        if self.existing_branches:
            branches_frame = ttk.LabelFrame(main_frame, text="Existing Conversations", padding=10)
            branches_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
            
            # Canvas for scrolling if needed
            if len(self.existing_branches) > 5:
                canvas = tk.Canvas(branches_frame, height=160)
                scrollbar = ttk.Scrollbar(branches_frame, orient=tk.VERTICAL, command=canvas.yview)
                scrollable_frame = ttk.Frame(canvas)
                
                scrollable_frame.bind(
                    "<Configure>",
                    lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
                )
                
                canvas.create_window((0, 0), window=scrollable_frame, anchor=tk.NW)
                canvas.configure(yscrollcommand=scrollbar.set)
                
                canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
                scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
                
                checkbox_parent = scrollable_frame
            else:
                checkbox_parent = branches_frame
            
            # Add checkboxes for each branch
            for branch in self.existing_branches:
                doc_id = branch.get('doc_id', '')
                title = branch.get('title', 'Untitled')
                exchange_count = branch.get('exchange_count', 0)
                last_updated = branch.get('last_updated', '')
                
                # Create checkbox variable
                var = tk.BooleanVar(value=(doc_id == self.current_branch_id))
                self.branch_vars[doc_id] = var
                
                # Format display text
                title_display = title.replace('[Response] ', '')
                if len(title_display) > 35:
                    title_display = title_display[:35] + "..."
                
                info_text = f"{exchange_count} exchange{'s' if exchange_count != 1 else ''}"
                if last_updated:
                    try:
                        dt = datetime.datetime.fromisoformat(last_updated.replace('Z', '+00:00'))
                        info_text += f" • {dt.strftime('%d-%b %H:%M')}"
                    except:
                        pass
                
                # Mark current branch
                is_current = (doc_id == self.current_branch_id)
                if is_current:
                    title_display += " (current)"
                
                frame = ttk.Frame(checkbox_parent)
                frame.pack(fill=tk.X, pady=3)
                
                cb = ttk.Checkbutton(
                    frame,
                    text=title_display,
                    variable=var,
                    style='Bold.TCheckbutton' if is_current else 'TCheckbutton'
                )
                cb.pack(side=tk.LEFT)
                
                info_label = ttk.Label(
                    frame,
                    text=f"  ({info_text})",
                    font=('Arial', 8),
                    foreground='#666666' if is_current else '#888888'
                )
                info_label.pack(side=tk.LEFT)
        
        # Separator
        ttk.Separator(main_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)
        
        # New branch option
        new_frame = ttk.Frame(main_frame)
        new_frame.pack(fill=tk.X, pady=(0, 5))
        
        new_cb = ttk.Checkbutton(
            new_frame,
            text="Create new conversation branch:",
            variable=self.create_new_var,
            command=self._on_new_branch_toggle
        )
        new_cb.pack(side=tk.LEFT)
        
        # New branch name entry
        self.new_name_entry = ttk.Entry(new_frame, textvariable=self.new_branch_name_var, width=25)
        self.new_name_entry.pack(side=tk.LEFT, padx=(10, 0))
        self.new_name_entry.config(state=tk.DISABLED)
        
        # Hint for new branch
        hint_label = ttk.Label(
            main_frame,
            text="(Leave name empty for auto-generated name based on your question)",
            font=('Arial', 8),
            foreground='#888888'
        )
        hint_label.pack(anchor=tk.W, pady=(0, 10))
        
        # If no existing branches, auto-check "create new"
        if not self.existing_branches:
            self.create_new_var.set(True)
            self.new_name_entry.config(state=tk.NORMAL)
        
        # ============================================================
        # NAVIGATION PREFERENCE SECTION
        # ============================================================
        ttk.Separator(main_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)
        
        nav_frame = ttk.LabelFrame(main_frame, text="After saving", padding=10)
        nav_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Determine what "stay here" means based on current mode
        if self.current_mode == 'source':
            stay_text = "📄 Stay here and keep reading the source document"
            go_text = "💬 Go to the conversation to see the response"
        else:
            stay_text = "💬 Stay in current conversation"
            go_text = "💬 Go to the saved conversation"
        
        stay_rb = ttk.Radiobutton(
            nav_frame,
            text=stay_text,
            variable=self.stay_here_var,
            value=True
        )
        stay_rb.pack(anchor=tk.W, pady=2)
        
        go_rb = ttk.Radiobutton(
            nav_frame,
            text=go_text,
            variable=self.stay_here_var,
            value=False
        )
        go_rb.pack(anchor=tk.W, pady=2)
        
        # Helpful note
        note_text = (
            "💡 Tip: Choose 'Stay here' to capture thoughts without interrupting your reading."
        )
        note_label = ttk.Label(
            nav_frame,
            text=note_text,
            font=('Arial', 8, 'italic'),
            foreground='#666666',
            wraplength=width - 80
        )
        note_label.pack(anchor=tk.W, pady=(8, 0))
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(15, 0))
        
        cancel_btn = ttk.Button(
            button_frame,
            text="Cancel",
            command=self._on_cancel,
            width=12
        )
        cancel_btn.pack(side=tk.RIGHT, padx=(5, 0))
        
        self.continue_btn = ttk.Button(
            button_frame,
            text="Save & Continue",
            command=self._on_continue,
            width=16
        )
        self.continue_btn.pack(side=tk.RIGHT)
        
        # Handle window close
        self.dialog.protocol("WM_DELETE_WINDOW", self._on_cancel)
        
        # Focus
        self.continue_btn.focus_set()
        
        # Wait for dialog
        self.parent.wait_window(self.dialog)
    
    def _on_new_branch_toggle(self):
        """Handle toggling the 'create new branch' checkbox."""
        if self.create_new_var.get():
            self.new_name_entry.config(state=tk.NORMAL)
            self.new_name_entry.focus_set()
        else:
            self.new_name_entry.config(state=tk.DISABLED)
    
    def _on_continue(self):
        """Handle Continue button click."""
        # Collect selected existing branches
        self.selected_branch_ids = [
            doc_id for doc_id, var in self.branch_vars.items() if var.get()
        ]
        
        # Check for new branch
        if self.create_new_var.get():
            name = self.new_branch_name_var.get().strip()
            self.new_branch_names = [name if name else None]
        else:
            self.new_branch_names = []
        
        # Get navigation preference
        self.stay_in_current_view = self.stay_here_var.get()
        
        # Validate: at least one destination
        if not self.selected_branch_ids and not self.new_branch_names:
            messagebox.showwarning(
                "No Destination",
                "Please select at least one conversation to save to,\n"
                "or create a new conversation branch.",
                parent=self.dialog
            )
            return
        
        self.cancelled = False
        self.dialog.destroy()
    
    def _on_cancel(self):
        """Handle Cancel button click."""
        self.cancelled = True
        self.selected_branch_ids = []
        self.new_branch_names = []
        self.dialog.destroy()
    
    def get_result(self) -> Dict:
        """
        Get the dialog result.
        
        Returns:
            Dict with:
            - 'cancelled': bool - True if user cancelled
            - 'existing_branches': List[str] - IDs of existing branches to save to
            - 'new_branches': List[Optional[str]] - Names for new branches (None = auto-generate)
            - 'stay_in_current_view': bool - True to stay in current view, False to go to conversation
        """
        return {
            'cancelled': self.cancelled,
            'existing_branches': self.selected_branch_ids,
            'new_branches': self.new_branch_names,
            'stay_in_current_view': self.stay_in_current_view
        }


def show_branch_picker(
    parent: tk.Tk,
    source_document_id: str,
    source_title: str,
    existing_branches: List[Dict],
    current_branch_id: Optional[str] = None,
    current_mode: str = 'source',
    action_description: str = "save this response"
) -> Dict:
    """
    Show the branch picker dialog and return the selection.
    
    Args:
        parent: Parent window
        source_document_id: ID of the source document
        source_title: Title of the source document
        existing_branches: List of branch info dicts
        current_branch_id: ID of currently active branch (to pre-select)
        current_mode: Current viewing mode ('source' or 'conversation')
        action_description: What action is being performed
    
    Returns:
        Dict with:
        - 'cancelled': bool
        - 'existing_branches': List[str] - IDs of existing branches
        - 'new_branches': List[Optional[str]] - Names for new branches
        - 'stay_in_current_view': bool - Navigation preference
    """
    dialog = BranchPickerDialog(
        parent=parent,
        source_document_id=source_document_id,
        source_title=source_title,
        existing_branches=existing_branches,
        current_branch_id=current_branch_id,
        current_mode=current_mode,
        action_description=action_description
    )
    return dialog.get_result()
