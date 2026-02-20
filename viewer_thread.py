"""
viewer_thread.py - Viewer and conversation thread management for DocAnalyser.

Handles viewing conversation threads, source document viewing, thread viewer
windows, chunked prompt processing, and thread save/load.

Extracted from Main.py to reduce file size. Uses a mixin pattern so all
self.xxx references continue to work unchanged.
"""

from __future__ import annotations

import datetime
import logging
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from config_manager import save_config
from document_library import get_document_by_id, load_document_entries, save_thread_to_document
from utils import entries_to_text, entries_to_text_with_speakers, chunk_entries

# Lazy module loader
def get_ai():
    import ai_handler
    return ai_handler


class ViewerThreadMixin:
    """Mixin class providing viewer and thread management methods for DocAnalyzerApp."""

    def view_conversation_thread(self):
        """
        Display the current conversation thread in a dedicated window
        Shows full context of the ongoing conversation with the current document
        Now with Follow-up capability directly from the thread viewer!
        """
        # Check for standalone conversation (no source document)
        def proceed_with_view(was_saved, doc_id):
            if was_saved and doc_id:
                # Update current document ID so future saves go to this document
                self.current_document_id = doc_id
                self.set_status("✅ Conversation saved to Documents Library")
            self._show_thread_viewer()
        
        # Check if standalone and prompt to save
        if check_and_prompt_standalone_save(
            parent=self.root,
            current_document_id=self.current_document_id,
            current_thread=self.current_thread,
            thread_message_count=self.thread_message_count,
            provider=self.provider_var.get(),
            model=self.model_var.get(),
            api_key=self.api_key_var.get(),
            config=self.config,
            ai_handler=get_ai(),
            on_complete=proceed_with_view
        ):
            return  # Dialog shown, will call proceed_with_view when done
        
        # Not standalone, proceed directly
        self._show_thread_viewer()
    
    def _view_source(self):
        """Open the unified viewer in Source Mode"""
        self._show_thread_viewer(target_mode='source')
    
    def _check_viewer_source_warning(self) -> bool:
        """
        Check if Thread Viewer is open and warn user that the prompt will
        process the original source, not the AI summary displayed in the viewer.
        
        Returns:
            True to continue with processing, False to cancel
        """
        # Check if warning is disabled
        if self.config.get('suppress_viewer_source_warning', False):
            return True
        
        # Check if any viewer is open
        self._cleanup_closed_viewers()
        if not hasattr(self, '_thread_viewer_windows') or not self._thread_viewer_windows:
            return True  # No viewer open, proceed normally
        
        # Check if we actually have a document loaded (warning only makes sense with a document)
        if not self.current_document_text:
            return True  # No document loaded, proceed normally
        
        # Create warning dialog
        dialog = tk.Toplevel(self.root)
        dialog.title("Process Original Source?")
        dialog.transient(self.root)
        dialog.grab_set()
        
        dialog.geometry("480x280")
        dialog.resizable(False, False)
        
        # Position relative to parent
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - 240
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - 140
        dialog.geometry(f"+{x}+{y}")
        
        result = tk.BooleanVar(value=False)
        dont_show_again = tk.BooleanVar(value=False)
        
        # Content frame
        content_frame = ttk.Frame(dialog, padding=20)
        content_frame.pack(fill=tk.BOTH, expand=True)
        
        # Warning icon and title
        ttk.Label(
            content_frame,
            text="⚠️ Process Original Source?",
            font=('Arial', 12, 'bold')
        ).pack(pady=(0, 15))
        
        # Message
        msg = (
            "This prompt will process the ORIGINAL SOURCE\n"
            "DOCUMENT (the transcript), not the AI summary\n"
            "currently displayed in the Thread Viewer.\n\n"
            "To ask questions about the summary, use the\n"
            "\"Ask a Follow-up Question\" field in the\n"
            "Thread Viewer instead."
        )
        ttk.Label(
            content_frame,
            text=msg,
            font=('Arial', 10),
            justify=tk.CENTER
        ).pack(pady=(0, 15))
        
        # Don't show again checkbox
        check_frame = ttk.Frame(content_frame)
        check_frame.pack(pady=(0, 15))
        ttk.Checkbutton(
            check_frame,
            text="Don't show this again",
            variable=dont_show_again
        ).pack()
        
        # Buttons
        btn_frame = ttk.Frame(content_frame)
        btn_frame.pack(fill=tk.X)
        
        def on_continue():
            result.set(True)
            if dont_show_again.get():
                self.config['suppress_viewer_source_warning'] = True
                save_config(self.config)
            dialog.destroy()
        
        def on_cancel():
            result.set(False)
            dialog.destroy()
        
        ttk.Button(
            btn_frame,
            text="Continue",
            command=on_continue,
            width=12
        ).pack(side=tk.LEFT, padx=10, expand=True)
        
        ttk.Button(
            btn_frame,
            text="Cancel",
            command=on_cancel,
            width=12
        ).pack(side=tk.LEFT, padx=10, expand=True)
        
        # Handle dialog close via X button
        dialog.protocol("WM_DELETE_WINDOW", on_cancel)
        
        # Wait for dialog
        dialog.wait_window()
        
        return result.get()
    
    def _cleanup_closed_viewers(self):
        """Remove closed viewer windows from the tracking list"""
        if not hasattr(self, '_thread_viewer_windows'):
            self._thread_viewer_windows = []
            return
        
        # Filter out closed windows
        open_viewers = []
        for viewer in self._thread_viewer_windows:
            try:
                if viewer.window.winfo_exists():
                    open_viewers.append(viewer)
            except (tk.TclError, AttributeError):
                pass  # Window was closed
        
        self._thread_viewer_windows = open_viewers
    
    def _get_open_viewer_count(self) -> int:
        """Get the count of currently open viewer windows"""
        self._cleanup_closed_viewers()
        return len(self._thread_viewer_windows)
    
    def _check_viewer_open_action(self, new_doc_title: str = "the selected document") -> str:
        """
        Check if Thread Viewer(s) are already open and ask user what to do.
        
        Args:
            new_doc_title: Title of the document being loaded (for display in dialog)
        
        Returns:
            'replace' - Close all existing viewers and open new one
            'side_by_side' - Keep existing, open new one alongside
            'cancel' - Don't load the new document
        """
        # Initialize list if needed and clean up closed viewers
        self._cleanup_closed_viewers()
        
        open_count = len(self._thread_viewer_windows)
        
        # No viewers open - proceed normally
        if open_count == 0:
            return 'replace'
        
        # Viewers are open - ask user what to do
        dialog = tk.Toplevel(self.root)
        dialog.title("Thread Viewer Open")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Adjust height based on whether we show a warning
        show_warning = (open_count >= 4)
        dialog_height = 220 if show_warning else 180
        
        dialog.geometry(f"420x{dialog_height}")
        dialog.resizable(False, False)
        
        # Position relative to parent
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - 210
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (dialog_height // 2)
        dialog.geometry(f"+{x}+{y}")
        
        result = tk.StringVar(value='cancel')
        
        # Message
        msg_frame = ttk.Frame(dialog, padding=20)
        msg_frame.pack(fill=tk.BOTH, expand=True)
        
        # Header message varies based on count
        if open_count == 1:
            header_text = "A Thread Viewer is already open."
        else:
            header_text = f"{open_count} Thread Viewers are already open."
        
        ttk.Label(
            msg_frame,
            text=header_text,
            font=('Arial', 11, 'bold')
        ).pack(pady=(0, 5))
        
        # Warning for 4+ viewers
        if show_warning:
            ttk.Label(
                msg_frame,
                text="⚠️ Having many viewers open may slow down the app.",
                font=('Arial', 9),
                foreground='#856404'
            ).pack(pady=(0, 10))
        
        ttk.Label(
            msg_frame,
            text="What would you like to do?",
            font=('Arial', 10)
        ).pack(pady=(0, 15))
        
        # Buttons
        btn_frame = ttk.Frame(msg_frame)
        btn_frame.pack(fill=tk.X)
        
        def set_result(val):
            result.set(val)
            dialog.destroy()
        
        # Replace button - closes ALL existing viewers
        replace_text = "Replace" if open_count == 1 else "Replace All"
        ttk.Button(
            btn_frame,
            text=replace_text,
            command=lambda: set_result('replace'),
            width=12
        ).pack(side=tk.LEFT, padx=5, expand=True)
        
        ttk.Button(
            btn_frame,
            text="Side by Side",
            command=lambda: set_result('side_by_side'),
            width=12
        ).pack(side=tk.LEFT, padx=5, expand=True)
        
        ttk.Button(
            btn_frame,
            text="Cancel",
            command=lambda: set_result('cancel'),
            width=12
        ).pack(side=tk.LEFT, padx=5, expand=True)
        
        # Wait for dialog to close
        dialog.wait_window()
        
        return result.get()
    
    def _view_thread(self):
        """Open the unified viewer in Conversation Mode"""
        # Check for standalone conversation first
        def proceed_with_view(was_saved=False, doc_id=None):
            if was_saved and doc_id:
                # Update current document ID so future saves go to this document
                self.current_document_id = doc_id
                self.set_status("✅ Conversation saved to Documents Library")
            self._show_thread_viewer(target_mode='conversation')
        
        # Check if this is a standalone conversation that should be saved first
        if check_and_prompt_standalone_save(
            parent=self.root,
            current_document_id=self.current_document_id,
            current_thread=self.current_thread,
            thread_message_count=self.thread_message_count,
            provider=self.provider_var.get(),
            model=self.model_var.get(),
            api_key=self.api_key_var.get(),
            config=self.config,
            ai_handler=get_ai(),
            on_complete=proceed_with_view
        ):
            return  # Dialog shown, will call proceed_with_view when done
        
        # Not standalone, proceed directly
        proceed_with_view()

    def _show_thread_viewer(self, target_mode: str = None, force_new_window: bool = False):
        """
        Show the thread viewer window in the specified mode.

        Args:
            target_mode: 'source' or 'conversation'. If None, auto-determines based on content.
            force_new_window: If True, always create a new window (for side-by-side viewing)
        """
        print(f"🔍 _show_thread_viewer called with target_mode={target_mode}, force_new_window={force_new_window}")

        # Initialize viewer list if needed
        if not hasattr(self, '_thread_viewer_windows'):
            self._thread_viewer_windows = []
        
        # Clean up closed viewers
        self._cleanup_closed_viewers()
        
        # Check if we should reuse an existing viewer (only if not forcing new window)
        if not force_new_window and self._thread_viewer_windows:
            # Use the most recent viewer
            viewer = self._thread_viewer_windows[-1]
            try:
                if viewer.window.winfo_exists():
                    print(f"   📺 Viewer already open, current mode: {viewer.current_mode}, target: {target_mode}")
                    viewer.window.lift()
                    viewer.window.focus_force()

                    # Switch to target mode if specified and different
                    if target_mode and target_mode != viewer.current_mode:
                        if target_mode == 'conversation':
                            has_conversation = self.current_thread and len(self.current_thread) > 0
                            if has_conversation:
                                viewer.switch_mode('conversation')
                            else:
                                print(f"   ⚠️ No conversation to display")
                        else:
                            viewer.switch_mode('source')

                    # Update button state
                    self.update_view_button_state()
                    return
            except (tk.TclError, AttributeError):
                # Window was closed, remove from list
                self._thread_viewer_windows.remove(viewer)
        
        # When forcing new window, don't close the existing ones
        if force_new_window:
            print(f"   📺 Opening NEW viewer window (side-by-side mode, {len(self._thread_viewer_windows)} already open)")

        print(f"   📺 Opening new viewer")

        # Use the new thread_viewer module which handles all UI and follow-up logic
        from thread_viewer import show_thread_viewer

        # ============================================================
        # DETERMINE SOURCE DOCUMENT TEXT FOR COLLAPSIBLE SECTION
        # If viewing a Response document, fetch the ORIGINAL source transcript
        # ============================================================
        source_text_for_viewer = self.current_document_text
        source_entries_for_viewer = self.current_entries

        is_response_document = getattr(self, 'current_document_class', 'source') in ['response', 'product',
                                                                                     'processed_output']
        parent_doc_id = None

        if hasattr(self, 'current_document_metadata') and self.current_document_metadata:
            parent_doc_id = self.current_document_metadata.get('parent_document_id')

        if is_response_document and parent_doc_id:
            # Fetch the original source document's content
            try:
                from document_library import get_document_by_id, load_document_entries
                from utils import entries_to_text, entries_to_text_with_speakers

                parent_doc = get_document_by_id(parent_doc_id)
                if parent_doc:
                    # Load entries from file (not from doc dict - entries are stored separately)
                    parent_entries = load_document_entries(parent_doc_id)
                    parent_doc_type = parent_doc.get('doc_type', parent_doc.get('type', 'text'))

                    if parent_entries:
                        print(f"📄 Loaded {len(parent_entries)} entries from parent source document")
                        # Convert entries to text (use speaker format for audio)
                        if parent_doc_type == 'audio_transcription':
                            source_text_for_viewer = entries_to_text_with_speakers(
                                parent_entries,
                                timestamp_interval=self.config.get("timestamp_interval", "every_segment")
                            )
                        else:
                            source_text_for_viewer = entries_to_text(
                                parent_entries,
                                timestamp_interval=self.config.get("timestamp_interval", "every_segment")
                            )
                        source_entries_for_viewer = parent_entries
                        print(f"📄 Loaded original source document ({len(source_text_for_viewer)} chars) for viewer")
            except Exception as e:
                print(f"⚠️ Could not fetch parent document: {e}")
                # Fall back to current_document_text

        # ============================================================
        # BUILD MULTI-SOURCE DOCUMENTS LIST
        # Combine main document + attachments into separate collapsible sections
        # ============================================================
        source_documents_for_viewer = None

        # Check if this is a multi-doc analysis - use entries as sources
        is_multi_doc = (hasattr(self, 'current_document_type') and 
                        self.current_document_type == 'multi_doc_analysis')
        
        if is_multi_doc and source_entries_for_viewer and len(source_entries_for_viewer) > 1:
            # Build source_documents from entries (each entry is a separate document)
            source_documents_for_viewer = []
            for entry in source_entries_for_viewer:
                entry_text = entry.get('text', '')
                if entry_text and entry_text.strip():
                    source_documents_for_viewer.append({
                        'title': entry.get('location', 'Document'),
                        'text': entry_text,
                        'source': entry.get('location', ''),
                        'char_count': len(entry_text)
                    })
            if source_documents_for_viewer:
                print(f"📚 Built source_documents from multi-doc entries: {len(source_documents_for_viewer)} documents")
            else:
                source_documents_for_viewer = None

        # Check if we have multiple sources (attachments)
        has_attachments = (hasattr(self, 'attachment_manager') and
                           self.attachment_manager.get_attachment_count() > 0)

        if has_attachments and not source_documents_for_viewer:
            # Build source_documents list from main document + attachments
            source_documents_for_viewer = []

            # Add main document as first source (if it exists and has content)
            if source_text_for_viewer and source_text_for_viewer.strip():
                # Don't include placeholder text
                if not source_text_for_viewer.startswith('[Attachments-only mode'):
                    source_documents_for_viewer.append({
                        'title': self.current_document_source or 'Main Document',
                        'text': source_text_for_viewer,
                        'source': self.current_document_source or '',
                        'char_count': len(source_text_for_viewer)
                    })

            # Add each attachment as a separate source
            for att in self.attachment_manager.attachments:
                att_text = att.get('text', '')
                if att_text and att_text.strip():
                    source_documents_for_viewer.append({
                        'title': att.get('filename', 'Attachment'),
                        'text': att_text,
                        'source': att.get('path', att.get('source', '')),
                        'char_count': len(att_text)
                    })

            # If we end up with nothing, fall back to None
            if not source_documents_for_viewer:
                source_documents_for_viewer = None
            else:
                print(f"📚 Built source_documents list with {len(source_documents_for_viewer)} documents")

        def on_followup_complete(question: str, response: str):
            """Callback when follow-up is completed from thread viewer"""
            # Update the preview text in main window with latest response
            self.set_status("✅ Follow-up complete", include_thread_status=True)

        new_viewer = show_thread_viewer(
            parent=self.root,
            current_thread=self.current_thread,
            thread_message_count=self.thread_message_count,
            current_document_id=self.current_document_id,
            current_document_text=source_text_for_viewer,  # Use source text, not response
            current_document_source=self.current_document_source,
            model_var=self.model_var,
            provider_var=self.provider_var,
            api_key_var=self.api_key_var,
            config=self.config,
            on_followup_complete=on_followup_complete,
            on_clear_thread=self.clear_thread,
            refresh_library=self.refresh_library,
            get_ai_handler=get_ai,
            build_threaded_messages=self.build_threaded_messages,
            add_message_to_thread=self.add_message_to_thread,
            attachment_manager=self.attachment_manager,
            font_size=self.font_size,
            # New parameters for "New Conversation (Same Source)" feature
            document_class=getattr(self, 'current_document_class', 'source'),
            source_document_id=self.current_document_metadata.get('parent_document_id') if hasattr(self,
                                                                                                   'current_document_metadata') else None,
            on_start_new_conversation=self.start_new_conversation_same_source,
            # Unified viewer callback for button state updates
            on_mode_change=self.on_viewer_mode_change,
            # Chunking callback for initial prompts from Source Mode
            process_with_chunking=self.process_prompt_with_chunking,
            # Current entries for chunking - use source entries if available
            current_entries=source_entries_for_viewer if source_entries_for_viewer else self.current_entries,
            current_document_type=getattr(self, 'current_document_type', 'text'),
            # Initial mode from caller
            initial_mode=target_mode,
            # NEW: Multi-source document support
            source_documents=source_documents_for_viewer,
            # NEW: App reference for context synchronization (branch creation)
            app=self,
        )
        
        # Add to list of open viewers
        self._thread_viewer_windows.append(new_viewer)
        print(f"   📺 Viewer opened (now {len(self._thread_viewer_windows)} total)")

        # Update button state now that viewer is open
        self.update_view_button_state()
    def process_prompt_with_chunking(self, prompt: str, status_callback, complete_callback):
        """
        Process a prompt with chunking support - callable from unified viewer.
        
        This allows the viewer to process initial prompts on large documents
        using the same chunking logic as the main "Run" button.
        
        Args:
            prompt: The prompt text to process
            status_callback: Function to call with status updates (str)
            complete_callback: Function to call when done (success: bool, result: str)
        """
        def process_thread():
            try:
                from utils import chunk_entries, entries_to_text, entries_to_text_with_speakers
                
                # Check if we have document content
                if not self.current_entries:
                    complete_callback(False, "No document content available for processing")
                    return
                
                # Get chunk size setting
                chunk_size_setting = self.config.get("chunk_size", "medium")
                
                # Chunk the entries
                chunks = chunk_entries(self.current_entries, chunk_size_setting)
                
                # Get document title for cost tracking
                doc_title = "Unknown Document"
                try:
                    if hasattr(self, 'current_document_id') and self.current_document_id:
                        from document_library import get_document_by_id
                        doc = get_document_by_id(self.current_document_id)
                        if doc:
                            doc_title = doc.get('title', 'Unknown Document')
                except Exception as e:
                    print(f"Warning: Could not get document title: {e}")
                
                prompt_name = "Viewer Prompt"
                
                # Determine document type for formatting
                is_audio = getattr(self, 'current_document_type', 'text') == "audio_transcription"
                timestamp_interval = self.config.get("timestamp_interval", "every_segment")
                
                # Check if using Local AI
                is_local = self.provider_var.get() == "Ollama (Local)"
                ai_label = "💻 Local AI" if is_local else "AI"
                
                # ============================================================
                # SINGLE CHUNK PROCESSING
                # ============================================================
                if len(chunks) == 1:
                    if is_audio:
                        chunk_text = entries_to_text_with_speakers(chunks[0], timestamp_interval=timestamp_interval)
                    else:
                        chunk_text = entries_to_text(chunks[0], timestamp_interval=timestamp_interval)
                    
                    # Build messages with document context
                    messages = [
                        {"role": "system", "content": "You are a helpful AI assistant analyzing documents."},
                        {"role": "user", "content": f"{prompt}\n\n{chunk_text}"}
                    ]
                    
                    status_callback(f"⚙️ Processing with {ai_label}...")
                    
                    success, result = get_ai().call_ai_provider(
                        provider=self.provider_var.get(),
                        model=self.model_var.get(),
                        messages=messages,
                        api_key=self.api_key_var.get(),
                        document_title=doc_title,
                        prompt_name=prompt_name
                    )
                    
                    if success:
                        # Add to thread
                        self.add_message_to_thread("user", prompt)
                        self.add_message_to_thread("assistant", result)
                        
                        # Preview update removed - Thread Viewer handles display
                        self.root.after(0, self.update_button_states)
                        
                        # Save as response document (same as main Run button)
                        self.root.after(0, lambda r=result: self.save_ai_output_as_product_document(r))
                    
                    print(f"🔔 Main.py (single chunk): Calling complete_callback with success={success}")
                    complete_callback(success, result)
                    print(f"🔔 Main.py (single chunk): complete_callback returned")
                    return
                
                # ============================================================
                # MULTIPLE CHUNKS PROCESSING
                # ============================================================
                results = []
                
                for i, chunk in enumerate(chunks, 1):
                    if is_audio:
                        chunk_text = entries_to_text_with_speakers(chunk, timestamp_interval=timestamp_interval)
                    else:
                        chunk_text = entries_to_text(chunk, timestamp_interval=timestamp_interval)
                    
                    messages = [
                        {"role": "system", "content": "You are a helpful AI assistant analyzing documents."},
                        {"role": "user", "content": f"{prompt}\n\n{chunk_text}"}
                    ]
                    
                    status_callback(f"⚙️ Processing chunk {i}/{len(chunks)} with {ai_label}...")
                    
                    success, result = get_ai().call_ai_provider(
                        provider=self.provider_var.get(),
                        model=self.model_var.get(),
                        messages=messages,
                        api_key=self.api_key_var.get(),
                        document_title=f"{doc_title} (Chunk {i}/{len(chunks)})",
                        prompt_name=f"{prompt_name} - Chunk {i}"
                    )
                    
                    if not success:
                        complete_callback(False, f"Failed on chunk {i}: {result}")
                        return
                    
                    results.append(result)
                    
                    # Add delay between chunks to avoid rate limiting
                    if i < len(chunks):
                        import time
                        delay_seconds = 12
                        status_callback(f"⏳ Waiting {delay_seconds}s before next chunk...")
                        time.sleep(delay_seconds)
                
                # ============================================================
                # CONSOLIDATE MULTIPLE CHUNKS
                # ============================================================
                combined_chunks = "\n\n---\n\n".join([f"Section {i + 1}:\n{r}" for i, r in enumerate(results)])
                consolidation_prompt = f"{prompt}\n\nHere are the key points extracted from each section of the document:\n\n{combined_chunks}"
                
                status_callback("⚙️ Consolidating results...")
                
                messages = [
                    {"role": "system", "content": "You are a helpful AI assistant consolidating information from multiple document sections."},
                    {"role": "user", "content": consolidation_prompt}
                ]
                
                success, final_result = get_ai().call_ai_provider(
                    provider=self.provider_var.get(),
                    model=self.model_var.get(),
                    messages=messages,
                    api_key=self.api_key_var.get(),
                    document_title=f"{doc_title} (Consolidated)",
                    prompt_name=f"{prompt_name} - Consolidation"
                )
                
                if success:
                    # Add to thread
                    self.add_message_to_thread("user", prompt)
                    self.add_message_to_thread("assistant", final_result)
                    
                    # Preview update removed - Thread Viewer handles display
                    self.root.after(0, self.update_button_states)
                    
                    # Save as response document (same as main Run button)
                    self.root.after(0, lambda r=final_result: self.save_ai_output_as_product_document(r))
                
                print(f"🔔 Main.py: Calling complete_callback with success={success}")
                complete_callback(success, final_result)
                print(f"🔔 Main.py: complete_callback returned")
                
            except Exception as e:
                import traceback
                traceback.print_exc()
                print(f"🔔 Main.py: Calling complete_callback with error: {e}")
                complete_callback(False, f"Error during processing: {str(e)}")
        
        # Run in background thread
        thread = threading.Thread(target=process_thread, daemon=True)
        thread.start()

    def save_current_thread(self):
        """Save current thread to document library"""
        print(f"\n🔍 DEBUG save_current_thread() called")
        print(f"   - current_document_id: {self.current_document_id}")
        print(f"   - thread_message_count: {self.thread_message_count}")
        print(f"   - current_thread length: {len(self.current_thread) if self.current_thread else 0}")
        
        if not self.current_document_id:
            print("   ⚠️  ABORTED: No document ID")
            return

        if not self.current_thread or self.thread_message_count == 0:
            print("   ⚠️  ABORTED: No thread or zero messages")
            return

        # Prepare metadata
        metadata = {
            "model": self.model_var.get(),
            "provider": self.provider_var.get(),
            "last_updated": datetime.datetime.now().isoformat(),
            "message_count": self.thread_message_count
        }

        # Save to library
        from document_library import save_thread_to_document
        save_thread_to_document(self.current_document_id, self.current_thread, metadata)

        print(f"💾 Thread saved for document {self.current_document_id} ({self.thread_message_count} messages)")

    def load_saved_thread(self):
        """Load saved thread for current document"""
        print(f"\n🔍 DEBUG load_saved_thread() called")
        print(f"   - current_document_id: {self.current_document_id}")
        
        if not self.current_document_id:
            print("   ⚠️  ABORTED: No document ID")
            return

        from document_library import load_thread_from_document
        thread, metadata = load_thread_from_document(self.current_document_id)
        
        print(f"   - Thread data retrieved: {thread is not None}")
        print(f"   - Thread length: {len(thread) if thread else 0}")
        print(f"   - Metadata: {metadata}")

        if thread:
            self.current_thread = thread
            self.thread_message_count = len([m for m in thread if m.get("role") == "user"])
            self.thread_needs_document_refresh = True  # Mark that we need to re-include document on next follow-up
            self.update_thread_status()

            print(f"📂 Thread loaded for document {self.current_document_id} ({self.thread_message_count} messages)")
            print(f"   🔄 thread_needs_document_refresh = True (document will be re-sent on next follow-up)")
        else:
            print(f"   ℹ️  No saved thread found for document {self.current_document_id}")

            # Show notification
            if self.thread_message_count > 0:
                self.set_status(
                    f"✅ Loaded document with {self.thread_message_count} message{'s' if self.thread_message_count != 1 else ''} in conversation",
                    include_thread_status=False
                )

    
