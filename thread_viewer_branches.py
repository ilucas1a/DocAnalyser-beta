"""
thread_viewer_branches.py - Branch Management Mixin for ThreadViewerWindow

Extracted from thread_viewer.py to improve maintainability.
Handles branch selector UI, branch loading/creating/switching,
copying exchanges to multiple branches, and branch+process workflows.

All methods access the parent ThreadViewerWindow's state via self.
"""

import tkinter as tk
from tkinter import messagebox
import datetime


class BranchMixin:
    """
    Mixin providing branch management for ThreadViewerWindow.
    
    Requires the following attributes on self:
        - window: tk.Toplevel
        - current_document_id: str
        - current_thread: list of message dicts
        - thread_message_count: int
        - model_var, provider_var, api_key_var: tk.StringVar
        - config: dict
        - branch_combo, branch_var: ttk.Combobox and tk.StringVar
        - branch_selector_frame: ttk.Frame
        - _branch_list: list
        - app: reference to main app
        - _set_status(): status display method
        - switch_mode(): mode switching method
        - _refresh_thread_display(): display refresh method
    """

    # === BRANCH SELECTOR METHODS ===

    def _get_source_document_id(self) -> str:
        """
        Get the source document ID for the current context.
        If viewing a response document, returns its parent source ID.
        If viewing a source document, returns the current document ID.
        """
        if not self.current_document_id:
            return None
        
        from document_library import get_document_by_id, is_source_document
        
        # Check if current document is a source
        is_src = is_source_document(self.current_document_id)
        
        if is_src:
            return self.current_document_id
        
        # Otherwise, get parent from metadata
        doc = get_document_by_id(self.current_document_id)
        if doc:
            metadata = doc.get('metadata', {})
            parent_id = metadata.get('parent_document_id') or metadata.get('original_document_id')
            if parent_id:
                return parent_id
        
        return None
    
    def _populate_branch_selector(self):
        """
        Populate the branch selector dropdown with available conversation branches.
        Shows/hides the selector based on whether branches exist.
        """
        from document_library import get_response_branches_for_source, get_document_by_id
        
        # Get source document ID
        source_id = self._get_source_document_id()
        
        if not source_id:
            # No source document - hide branch selector
            self.branch_selector_frame.pack_forget()
            self._branch_list = []
            return
        
        # Get all response branches for this source
        branches = get_response_branches_for_source(source_id)
        
        # Store branch info for later use
        self._branch_list = branches if branches else []
        
        if not branches:
            # No branches yet - hide selector (will show after first response)
            self.branch_selector_frame.pack_forget()
            return
        
        # Build display names for dropdown
        branch_names = []
        current_branch_name = None
        
        for branch in branches:
            # Extract display name from title (remove [Response] prefix if present)
            title = branch.get('title', 'Unknown')
            if title.startswith('[Response]'):
                display_name = title[10:].strip()  # Remove '[Response]' prefix
                # Further trim if it starts with prompt name
                if ':' in display_name:
                    display_name = display_name.split(':', 1)[1].strip()
            else:
                display_name = title
            
            # Truncate if too long
            if len(display_name) > 30:
                display_name = display_name[:27] + "..."
            
            # Add processing indicator if branch is still being processed
            if branch.get('is_processing', False):
                display_name += " ⏳"
            
            branch_names.append(display_name)
            
            # Check if this is the current branch
            if branch.get('doc_id') == self.current_document_id:
                current_branch_name = display_name
        
        # Add "+ New Branch..." option
        branch_names.append("➕ New Branch...")
        
        # Update combobox
        self.branch_combo['values'] = branch_names
        
        # Set current selection
        if current_branch_name:
            self.branch_var.set(current_branch_name)
        elif branches:
            # Default to first branch if current not found
            self.branch_var.set(branch_names[0])
        else:
            pass
        
        
        # Show the selector (in case it was hidden)
        # Pack as its own row below the header
        self.branch_selector_frame.pack(fill=tk.X)
        
        # Update visibility based on mode
        self._update_branch_selector_visibility()
    
    def _update_branch_selector_visibility(self):
        """Show/hide branch selector based on available branches"""
        if not hasattr(self, 'branch_selector_frame'):
            return
        
        # Show branch selector in BOTH modes when there are branches
        # This allows users to see and access conversations from either mode
        if hasattr(self, '_branch_list') and self._branch_list:
            self.branch_selector_frame.pack(fill=tk.X)
        else:
            self.branch_selector_frame.pack_forget()
    
    def _on_branch_selected(self, event=None):
        """
        Handle branch selection from dropdown.
        Switches to the selected conversation branch.
        """
        selected = self.branch_var.get()
        
        if not selected:
            return
        
        # Check if "+ New Branch..." was selected
        if selected in ("+ New Branch...", "➕ New Branch..."):
            self._create_new_branch_from_selector()
            return
        
        # Find the branch ID for the selected name
        if not hasattr(self, '_branch_list') or not self._branch_list:
            return
        
        
        selected_branch_id = None
        for i, branch in enumerate(self._branch_list):
            title = branch.get('title', '')
            branch_id = branch.get('doc_id', '')  # Note: 'doc_id' not 'id'
            
            # Match using same logic as _populate_branch_selector
            if title.startswith('[Response]'):
                display_name = title[10:].strip()
                if ':' in display_name:
                    display_name = display_name.split(':', 1)[1].strip()
            else:
                display_name = title
            
            if len(display_name) > 30:
                display_name = display_name[:27] + "..."
            
            # Add processing indicator to match what _populate_branch_selector shows
            if branch.get('is_processing', False):
                display_name += " ⏳"
            
            is_match = display_name == selected
            match_marker = "✅ MATCH" if is_match else ""
            
            if is_match:
                selected_branch_id = branch_id
                break
        
        if not selected_branch_id:
            # Restore the previous selection
            self._populate_branch_selector()
            return
        
        # Don't switch if already on this branch AND in conversation mode
        # In source mode, we should switch to show the branch's conversation
        if selected_branch_id == self.current_document_id and self.current_mode == 'conversation':
            return
        
        # If in source mode viewing the same branch, just switch to conversation mode
        if selected_branch_id == self.current_document_id and self.current_mode == 'source':
            self.switch_mode('conversation')
            return
        
        
        # Save current edits before switching
        try:
            if self.current_mode == 'conversation':
                self._save_edits_to_thread()
        except ValueError:
            pass
        
        # Load the selected branch
        self._load_branch(selected_branch_id)
    
    def _load_branch(self, branch_doc_id: str):
        """
        Load a conversation branch by document ID.
        Updates the viewer to show the selected branch's content.
        """
        from document_library import get_document_by_id, load_thread_from_document, load_document_entries, save_thread_to_document
        
        
        # =================================================================
        # CRITICAL FIX: Save current thread to its document BEFORE clearing
        # This prevents data loss when switching branches, since current_thread
        # is a shared reference with Main.py
        # =================================================================
        if self.current_document_id and self.current_document_id != branch_doc_id:
            if self.current_thread and len(self.current_thread) > 0:
                try:
                    metadata = {
                        "model": self.model_var.get(),
                        "provider": self.provider_var.get(),
                        "last_updated": datetime.datetime.now().isoformat(),
                        "message_count": self.thread_message_count
                    }
                    save_thread_to_document(self.current_document_id, self.current_thread, metadata)
                except Exception as e:
                    pass
        
        # Get the branch document
        branch_doc = get_document_by_id(branch_doc_id)
        if not branch_doc:
            return
        
        
        # Load thread from this branch
        thread_data, thread_metadata = load_thread_from_document(branch_doc_id)
        
        
        # Update viewer state
        self.current_document_id = branch_doc_id
        self.doc_title = branch_doc.get('title', 'Unknown')
        
        # Update thread
        self.current_thread.clear()
        if thread_data:
            self.current_thread.extend(thread_data)
        self.thread_message_count = len([m for m in self.current_thread if m.get('role') == 'user'])
        
        # Reset exchange collapse state for new thread
        self.exchange_expanded_state.clear()
        self._init_exchange_collapse_state()
        
        # Update window title
        self._update_window_title()
        
        # Switch to conversation mode and refresh display
        self.current_mode = 'conversation'
        self._refresh_thread_display()
        self._update_mode_buttons()
        
        # === CRITICAL: Load source document entries for processing ===
        # Get parent source document ID from metadata
        metadata = branch_doc.get('metadata', {})
        source_doc_id = metadata.get('parent_document_id') or metadata.get('original_document_id')
        
        if source_doc_id:
            source_entries = load_document_entries(source_doc_id)
            if source_entries:
                self.current_entries = source_entries
                
                # Also load source documents for display
                source_doc = get_document_by_id(source_doc_id)
                if source_doc:
                    from utils import entries_to_text_with_speakers, entries_to_text
                    # Determine if audio transcription
                    doc_type = source_doc.get('type', 'text')
                    is_audio = doc_type == 'audio_transcription'
                    
                    if is_audio:
                        source_text = entries_to_text_with_speakers(
                            source_entries,
                            timestamp_interval=self.config.get('timestamp_interval', 'every_segment')
                        )
                    else:
                        source_text = entries_to_text(source_entries)
                    
                    # Update source documents for display
                    self.source_documents = [{
                        'title': source_doc.get('title', 'Source Document'),
                        'text': source_text,
                        'source': source_doc.get('source', ''),
                        'char_count': len(source_text) if source_text else 0
                    }]
                    self.current_document_text = source_text
                    self.current_document_source = source_doc.get('source', '')
            else:
                pass
        else:
            pass
        
        # Update main app context if available
        if hasattr(self, 'app') and self.app:
            self.app.current_document_id = branch_doc_id
            self.app.current_document_class = 'response'
            if hasattr(self.app, 'current_thread'):
                self.app.current_thread.clear()
                if thread_data:
                    self.app.current_thread.extend(thread_data)
            if hasattr(self.app, 'thread_message_count'):
                self.app.thread_message_count = self.thread_message_count
            
            # CRITICAL: Update entries in main app for processing
            if hasattr(self, 'current_entries') and self.current_entries:
                if hasattr(self.app, 'current_entries'):
                    self.app.current_entries = self.current_entries
                    
            # Also update source document reference
            if source_doc_id:
                if hasattr(self.app, 'source_document_id'):
                    self.app.source_document_id = source_doc_id
                if hasattr(self.app, 'current_document_metadata'):
                    self.app.current_document_metadata = metadata
                # CRITICAL: Update document text in main app for processing
                if hasattr(self, 'current_document_text') and self.current_document_text:
                    if hasattr(self.app, 'current_document_text'):
                        self.app.current_document_text = self.current_document_text
                    
            if hasattr(self.app, 'update_button_states'):
                self.app.update_button_states()
        
        if hasattr(self, 'app') and self.app:
            pass
    
    def _create_new_branch_from_selector(self):
        """
        Handle "+ New Branch..." selection from dropdown.
        Shows a dialog to create a new conversation branch.
        """
        from tkinter import simpledialog
        
        # Prompt for branch name
        branch_name = simpledialog.askstring(
            "New Conversation Branch",
            "Enter a name for the new conversation branch:",
            parent=self.window
        )
        
        if not branch_name or not branch_name.strip():
            # Cancelled or empty - restore previous selection
            self._populate_branch_selector()
            return
        
        branch_name = branch_name.strip()
        
        # Get source document ID
        source_id = self._get_source_document_id()
        if not source_id:
            self._populate_branch_selector()
            return
        
        # Create the new branch document
        self._create_new_branch_and_switch(branch_name, source_id)
    
    def _create_new_branch_and_switch(self, branch_name: str, source_doc_id: str):
        """
        Create a new empty conversation branch and switch to it.
        """
        import datetime
        from document_library import add_document_to_library, get_document_by_id
        
        
        # Get source document info
        source_doc = get_document_by_id(source_doc_id)
        if not source_doc:
            return
        
        source_title = source_doc.get('title', 'Unknown')
        source_url = source_doc.get('source', '')
        
        # Create title for the response document
        response_title = f"[Response] {branch_name}"
        
        # Create metadata linking back to source
        # NOTE: pre_created=True ensures get_response_branches_for_source includes
        # this branch even before any exchanges are added (0-exchange filter).
        # manually_created=True distinguishes user-created branches from auto-created
        # ones so they don't show the processing hourglass icon.
        response_metadata = {
            "original_document_id": source_doc_id,
            "parent_document_id": source_doc_id,
            "source_title": source_title,
            "branch_name": branch_name,
            "created": datetime.datetime.now().isoformat(),
            "editable": True,
            "pre_created": True,
            "manually_created": True
        }
        
        # Create the response document
        # CRITICAL: Include branch_name in source to generate UNIQUE doc_id for each branch
        # Without this, all branches for the same source get the same ID and overwrite each other!
        new_doc_id = add_document_to_library(
            doc_type="conversation_thread",
            source=f"Conversation about: {source_url or source_title} - Branch: {branch_name}",
            title=response_title,
            entries=[{"text": f"Conversation branch: {branch_name}", "location": "Header"}],
            metadata=response_metadata,
            document_class="response"
        )
        
        if not new_doc_id:
            self._populate_branch_selector()
            return
        
        
        # Switch to the new branch
        self._load_branch(new_doc_id)
        
        if hasattr(self, 'app') and self.app:
            pass
        
        # Refresh the branch selector to include the new branch
        self._populate_branch_selector()
    
    def _delete_current_branch(self):
        """
        Delete the currently displayed conversation branch.
        The source document is not affected. Cannot be undone.
        """
        if not self.current_document_id:
            return

        from document_library import (
            is_source_document, get_document_by_id,
            delete_thread_document, get_response_branches_for_source
        )

        # Safety: never delete a source document via this button
        if is_source_document(self.current_document_id):
            from tkinter import messagebox
            messagebox.showwarning(
                "Cannot Delete Source",
                "This is a source document, not a conversation branch.\n\n"
                "Only conversation branches can be deleted here.\n"
                "To delete a source document, use the Documents Library."
            )
            return

        doc = get_document_by_id(self.current_document_id)
        if not doc:
            return

        branch_title = doc.get('title', 'this branch')
        # Strip the [Response] prefix for cleaner display
        if branch_title.startswith('[Response]'):
            branch_title = branch_title[10:].strip()

        # Get source doc so we can switch to a sibling after deletion
        metadata = doc.get('metadata', {})
        source_doc_id = (
            metadata.get('parent_document_id') or
            metadata.get('original_document_id')
        )

        # Count siblings so we can warn if this is the last branch
        sibling_branches = []
        if source_doc_id:
            all_branches = get_response_branches_for_source(source_doc_id)
            sibling_branches = [
                b for b in all_branches
                if b.get('doc_id') != self.current_document_id
            ]

        # Confirmation dialog
        from tkinter import messagebox
        if sibling_branches:
            confirm_msg = (
                f"Permanently delete this conversation branch?\n\n"
                f"\"{ branch_title }\"\n\n"
                f"This cannot be undone. The source document is not affected."
            )
        else:
            confirm_msg = (
                f"Permanently delete this conversation branch?\n\n"
                f"\"{ branch_title }\"\n\n"
                f"This is the only branch for this source document.\n"
                f"After deletion no conversation will remain (the source document is not affected).\n\n"
                f"This cannot be undone."
            )

        if not messagebox.askyesno("Delete Branch?", confirm_msg, icon='warning'):
            return

        # Perform deletion
        deleted = delete_thread_document(self.current_document_id)
        if not deleted:
            messagebox.showerror(
                "Delete Failed",
                "Could not delete the branch. It may have already been removed."
            )
            return

        # Clear main app state if it's pointing at the deleted doc
        if hasattr(self, 'app') and self.app:
            if getattr(self.app, 'current_document_id', None) == self.current_document_id:
                self.app.current_document_id = source_doc_id or None
                self.app.current_thread = []
                self.app.thread_message_count = 0
                if hasattr(self.app, 'update_button_states'):
                    self.app.update_button_states()

        # Switch to a sibling branch, or back to the source document
        if sibling_branches:
            next_branch_id = sibling_branches[-1].get('doc_id')
            self._load_branch(next_branch_id)
        elif source_doc_id:
            # Load source document back into the viewer
            from document_library import get_document_by_id as _get_doc, load_document_entries
            from utils import entries_to_text, entries_to_text_with_speakers
            src_doc = _get_doc(source_doc_id)
            if src_doc:
                self.current_document_id = source_doc_id
                self.current_thread.clear()
                self.thread_message_count = 0
                self.exchange_expanded_state.clear()
                src_entries = load_document_entries(source_doc_id)
                if src_entries:
                    self.current_entries = src_entries
                    is_audio = src_doc.get('type') == 'audio_transcription'
                    src_text = (
                        entries_to_text_with_speakers(src_entries)
                        if is_audio else entries_to_text(src_entries)
                    )
                    self.source_documents = [{
                        'title': src_doc.get('title', 'Source Document'),
                        'text': src_text,
                        'source': src_doc.get('source', ''),
                        'char_count': len(src_text),
                    }]
                    self.current_document_text = src_text
                self.current_mode = 'source'
                self._update_window_title()
                self._refresh_thread_display()
                self._update_mode_buttons()
            self._populate_branch_selector()
        else:
            # No source doc known — just close the viewer
            self.window.destroy()
            return

        # Refresh library in main app
        if hasattr(self, 'app') and self.app and hasattr(self.app, 'refresh_library'):
            self.app.refresh_library()

    # === END BRANCH SELECTOR METHODS ===

    # === BRANCH PROCESSING METHODS ===

    def _copy_exchange_to_additional_branches(self, question: str, ai_response: str):
        """
        Copy the exchange (question + AI response) to additional selected branches.
        This implements the multi-save feature where one response can be saved to multiple conversations.
        
        Args:
            question: The user's question
            ai_response: The AI's response
        """
        if not hasattr(self, '_pending_multi_save') or not self._pending_multi_save:
            return
        
        
        from document_library import (
            get_document_by_id, save_thread_to_document, load_thread_from_document,
            add_document_to_library
        )
        import datetime
        
        pending = self._pending_multi_save
        primary_branch_id = self.current_document_id  # The branch we just processed to
        selected_existing = pending.get('existing_branches', [])
        new_branch_names = pending.get('new_branches', [])
        source_doc_id = pending.get('source_doc_id')
        source_title = pending.get('source_title', 'Unknown')
        
        
        # Build the exchange to copy
        exchange = [
            {'role': 'user', 'content': question},
            {'role': 'assistant', 'content': ai_response}
        ]
        
        # Copy to additional EXISTING branches (skip the primary)
        for branch_id in selected_existing:
            if branch_id == primary_branch_id:
                continue
            
            try:
                
                # Load existing thread
                existing_thread, metadata = load_thread_from_document(branch_id)
                if existing_thread is None:
                    existing_thread = []
                
                # Append the new exchange
                existing_thread.extend(exchange)
                
                # Save back
                save_thread_to_document(branch_id, existing_thread)
                
            except Exception as e:
                pass
        
        # Create additional NEW branches (skip the first one if it was the primary)
        # The first new branch was created as primary, so we need to create any additional ones
        branches_created_as_primary = 1 if new_branch_names else 0
        additional_new_branches = new_branch_names[branches_created_as_primary:] if len(new_branch_names) > branches_created_as_primary else []
        
        for branch_name in additional_new_branches:
            try:
                
                # Generate name if not provided
                if not branch_name:
                    # Auto-generate from question
                    branch_name = question[:30].strip()
                    if len(question) > 30:
                        branch_name += "..."
                
                response_title = f"[Response] {branch_name}"
                
                # Create metadata for new branch
                response_metadata = {
                    'original_document_id': source_doc_id,
                    'parent_document_id': source_doc_id,
                    'source_title': source_title,
                    'branch_name': branch_name,
                    'created': datetime.datetime.now().isoformat(),
                    'editable': True,
                    'pre_created': False  # Already has content
                }
                
                # Get source URL for the source field
                source_doc = get_document_by_id(source_doc_id)
                source_url = source_doc.get('source', '') if source_doc else ''
                
                # Create the document
                new_doc_id = add_document_to_library(
                    doc_type="conversation_thread",
                    source=f"Conversation about: {source_url or source_title} - Branch: {branch_name}",
                    title=response_title,
                    entries=[{"text": f"Conversation branch: {branch_name}", "location": "Header"}],
                    metadata=response_metadata,
                    document_class="response"
                )
                
                if new_doc_id:
                    # Save the exchange to it
                    save_thread_to_document(new_doc_id, exchange)
                else:
                    pass
                    
            except Exception as e:
                pass
        
    
    def _create_new_branch_and_process(self, question: str, branch_name: str = None, source_doc_id: str = None):
        """
        Create a new response branch and process the initial prompt.
        
        This creates the response document FIRST with the user's chosen name,
        then switches context and processes the question.
        
        Args:
            question: The prompt/question to process
            branch_name: Optional name for the new branch (used for title)
            source_doc_id: ID of the source document to link to (defaults to current_document_id)
        """
        import datetime
        from document_library import (
            add_document_to_library, get_document_by_id, load_document_entries,
            save_thread_to_document
        )
        
        # Use provided source_doc_id or fall back to current document
        if source_doc_id is None:
            source_doc_id = self.current_document_id
        
        # Get source document info
        source_doc = get_document_by_id(source_doc_id)
        if not source_doc:
            messagebox.showerror("Error", "Could not find source document.")
            return
        
        source_title = source_doc.get('title', 'Unknown')
        source_url = source_doc.get('source', '')
        source_id = source_doc_id  # Use the provided/determined source ID
        
        # Generate branch name if not provided
        if not branch_name:
            # Use first part of the question as branch name
            branch_name = question[:50] + "..." if len(question) > 50 else question
            branch_name = branch_name.replace('\n', ' ')
        
        # Create title for the response document
        response_title = f"[Response] {branch_name}"
        
        # Create metadata linking back to source
        response_metadata = {
            "original_document_id": source_id,
            "parent_document_id": source_id,
            "source_title": source_title,
            "branch_name": branch_name,
            "created": datetime.datetime.now().isoformat(),
            "editable": True,
            "pre_created": True  # Flag so Main.py knows not to create another
        }
        
        # Create the response document
        # CRITICAL: Include branch_name in source to generate UNIQUE doc_id for each branch
        # Without this, all branches for the same source get the same ID and overwrite each other!
        new_doc_id = add_document_to_library(
            doc_type="conversation_thread",
            source=f"Conversation about: {source_url or source_title} - Branch: {branch_name}",
            title=response_title,
            entries=[{"text": f"Conversation branch: {branch_name}", "location": "Header"}],
            metadata=response_metadata,
            document_class="response"
        )
        
        if not new_doc_id:
            messagebox.showerror("Error", "Failed to create response document.")
            return
        
        
        # VERIFY the new document's metadata
        try:
            verify_new = get_document_by_id(new_doc_id)
            if verify_new:
                new_meta = verify_new.get('metadata', {})
            else:
                pass
        except Exception as ve:
            pass
        
        # =================================================================
        # CRITICAL FIX: Save current thread to its document BEFORE clearing
        # This prevents data loss when creating a new branch while another
        # branch has an unsaved conversation
        # =================================================================
        if self.current_document_id and self.current_document_id != new_doc_id:
            if self.current_thread and len(self.current_thread) > 0:
                try:
                    save_metadata = {
                        "model": self.model_var.get(),
                        "provider": self.provider_var.get(),
                        "last_updated": datetime.datetime.now().isoformat(),
                        "message_count": self.thread_message_count
                    }
                    save_thread_to_document(self.current_document_id, self.current_thread, save_metadata)
                    
                    # VERIFY the save worked
                    try:
                        from document_library import get_document_by_id
                        verify_doc = get_document_by_id(self.current_document_id)
                        if verify_doc:
                            saved_thread = verify_doc.get('conversation_thread', [])
                            saved_exchanges = len([m for m in saved_thread if m.get('role') == 'user'])
                        else:
                            pass
                    except Exception as ve:
                        pass
                except Exception as e:
                    pass
            else:
                pass
        else:
            pass
        
        # === CRITICAL: Update Thread Viewer's context ===
        # Snapshot prior exchanges before clearing so the new branch inherits them.
        # When a user creates a branch from an existing conversation, the intent is
        # to continue from that point — the new branch should show all prior exchanges
        # PLUS the new follow-up, not just the follow-up alone.
        prior_exchanges = list(self.current_thread)

        self.current_document_id = new_doc_id
        self.current_thread.clear()
        # Restore prior exchanges so the new branch starts with conversation history
        if prior_exchanges:
            self.current_thread.extend(prior_exchanges)
        self.thread_message_count = len(
            [m for m in self.current_thread if isinstance(m, dict) and m.get('role') == 'user']
        )

        # Pre-save prior exchanges to the new branch document so the database is
        # consistent before processing begins (required for correct reload after
        # the AI response comes back in _handle_initial_prompt_result).
        if prior_exchanges:
            try:
                save_thread_to_document(new_doc_id, list(prior_exchanges), {
                    "model": self.model_var.get(),
                    "provider": self.provider_var.get(),
                    "last_updated": datetime.datetime.now().isoformat(),
                    "message_count": self.thread_message_count
                })
            except Exception as e:
                pass  # Non-fatal — exchanges are still in memory
        
        # Update window title
        self.window.title(f"Conversation - {branch_name}")
        self.doc_title = response_title
        
        # Switch to conversation mode
        self.current_mode = 'conversation'
        
        # Refresh the branch selector to show the new branch immediately
        self._populate_branch_selector()
        
        # === CRITICAL: Update Main App's context via callback ===
        # This ensures the main app also knows we switched documents
        if hasattr(self, 'app') and self.app:
            self.app.current_document_id = new_doc_id
            self.app.current_document_class = 'response'
            # Also update metadata so save function sees it
            if hasattr(self.app, 'current_document_metadata'):
                self.app.current_document_metadata = response_metadata.copy()
            else:
                # Create the attribute if it doesn't exist
                self.app.current_document_metadata = response_metadata.copy()
        
        # Make sure we have the source document's entries for processing
        if not self.current_entries or len(self.current_entries) == 0:
            source_entries = load_document_entries(source_id)
            if source_entries:
                self.current_entries = source_entries
        
        # Now process the question
        # Use chunking for large documents, regular follow-up for small ones
        if self.process_with_chunking and self.current_entries and len(self.current_entries) > 0:
            self._submit_initial_prompt_with_chunking(question)
        else:
            self._submit_followup_direct(question)
    
    def _switch_to_branch_and_process(self, branch_doc_id: str, question: str):
        """
        Switch to an existing response branch and add the follow-up.
        
        Args:
            branch_doc_id: Document ID of the response branch
            question: The prompt/question to process
        """
        from document_library import get_document_by_id, load_thread_from_document, load_document_entries, save_thread_to_document
        import datetime
        
        # Get the branch document
        branch_doc = get_document_by_id(branch_doc_id)
        if not branch_doc:
            messagebox.showerror("Error", "Could not find the selected conversation branch.")
            return
        
        # =================================================================
        # CRITICAL FIX: Check if we're already on this branch
        # If so, DON'T reload from document - keep the in-memory thread
        # (which may have unsaved exchanges)
        # =================================================================
        already_on_this_branch = (self.current_document_id == branch_doc_id)
        
        if already_on_this_branch:
            # Already on this branch - just process the question with current thread
            print(f"📌 Already on branch {branch_doc_id}, keeping in-memory thread ({len(self.current_thread)} messages)")
            
            # Make sure we're in conversation mode
            self.current_mode = 'conversation'
            
            # Refresh the branch selector
            self._populate_branch_selector()
            
            # Process the question directly
            self._submit_followup_direct(question)
            return
        
        # =================================================================
        # SWITCHING TO A DIFFERENT BRANCH
        # Save current thread first, then load the target branch's thread
        # =================================================================
        print(f"🔀 Switching from branch {self.current_document_id} to {branch_doc_id}")
        
        # Save current thread to its document BEFORE switching
        if self.current_document_id and self.current_thread and len(self.current_thread) > 0:
            try:
                save_metadata = {
                    "model": self.model_var.get(),
                    "provider": self.provider_var.get(),
                    "last_updated": datetime.datetime.now().isoformat(),
                    "message_count": self.thread_message_count
                }
                save_thread_to_document(self.current_document_id, self.current_thread, save_metadata)
                print(f"💾 Saved {self.thread_message_count} exchanges to old branch {self.current_document_id}")
            except Exception as e:
                print(f"⚠️ Failed to save old thread: {e}")
        
        # Load existing thread from the target branch
        existing_thread, thread_metadata = load_thread_from_document(branch_doc_id)
        
        # Update our local context to point to the new branch
        self.current_document_id = branch_doc_id
        
        # Load/update thread from the target branch
        if existing_thread:
            self.current_thread.clear()
            self.current_thread.extend(existing_thread)
            self.thread_message_count = len([m for m in existing_thread if m.get('role') == 'user'])
            print(f"📂 Loaded {self.thread_message_count} exchanges from new branch")
        else:
            self.current_thread.clear()
            self.thread_message_count = 0
            print(f"📂 New branch has no existing thread")
        
        # Get the new document info
        self.doc_title = branch_doc.get('title', 'Unknown')
        self.window.title(f"Conversation - {branch_doc.get('source', '')[:60]}")
        
        # Switch to conversation mode since we're adding to a conversation
        self.current_mode = 'conversation'
        
        # Refresh the branch selector to show the new branch immediately
        self._populate_branch_selector()
        
        # Now submit the follow-up using the regular flow
        self._submit_followup_direct(question)
    
