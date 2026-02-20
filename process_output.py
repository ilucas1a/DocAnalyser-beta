"""
process_output.py - Document processing and output saving for DocAnalyser.

Handles AI prompt processing, result handling, output saving (including
RTF export, product documents, metadata), cancel/restart, and thread management.

Extracted from Main.py to reduce file size. Uses a mixin pattern so all
self.xxx references continue to work unchanged.
"""

from __future__ import annotations

import os
import re
import hashlib
import time
import datetime
import logging
import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog

from config_manager import save_config
from document_library import (
    get_document_by_id,
    add_document_to_library,
    add_processed_output_to_document,
    save_thread_to_document,
    load_document_entries,
)
from utils import entries_to_text, entries_to_text_with_speakers, chunk_entries

# Lazy module loaders (mirrors Main.py pattern)
def get_ai():
    import ai_handler
    return ai_handler

def get_formatter():
    import output_formatter
    return output_formatter


class ProcessOutputMixin:
    """Mixin class providing document processing and output saving methods for DocAnalyzerApp."""

    def process_document(self):
        print("🔧 DEBUG: process_document() called")
        if self.processing:
            print("❌ DEBUG: Already processing!")
            messagebox.showwarning("Warning", "Processing already in progress. Please wait or cancel.")
            return
        print("✅ DEBUG: Not currently processing")
        
        # Reset Run button highlight immediately and disable re-highlighting
        self._run_highlight_enabled = False
        if hasattr(self, 'process_btn'):
            self.process_btn.configure(style='TButton')
            self.root.update_idletasks()  # Force immediate UI update
        
        # Clear the input field and restore placeholder (document is already loaded)
        self.universal_input_entry.delete('1.0', 'end')
        self.placeholder_active = False  # Reset so update_placeholder will work
        self.update_placeholder()
        
        # Check if Thread Viewer is open and warn user about source vs summary
        if not self._check_viewer_source_warning():
            return  # User cancelled
        
        # 🆕 NEW: Smart context check - allow prompts without documents
        has_document = bool(self.current_document_text)
        has_attachments = (hasattr(self, 'attachment_manager') and 
                          self.attachment_manager.get_attachment_count() > 0)
        has_any_content = has_document or has_attachments
        
        # Get the prompt first to check if it's document-specific
        prompt = self.prompt_text.get('1.0', tk.END).strip()
        if not prompt:
            messagebox.showinfo("No Prompt", "Please enter or select a prompt first.")
            return
        
        # Check if prompt appears to be document-specific
        document_keywords = [
            'document', 'text', 'article', 'content', 'passage', 
            'summary', 'summarize', 'extract', 'analyze', 'review',
            'above', 'provided', 'following', 'attached', 'this file'
        ]
        prompt_lower = prompt.lower()
        is_document_specific = any(keyword in prompt_lower for keyword in document_keywords)
        
        # Smart warning system
        if not has_any_content:
            if is_document_specific:
                # Prompt mentions document-related terms but no document loaded
                response = messagebox.askyesno(
                    "No Document Loaded",
                    f"Your prompt mentions document-related content:\n\n"
                    f"\"{prompt[:100]}{'...' if len(prompt) > 100 else ''}\"\n\n"
                    f"But no document or attachments are loaded.\n\n"
                    f"💡 Tip: Load a document first, or rephrase your prompt for general conversation.\n\n"
                    f"Continue anyway without document context?",
                    icon='warning'
                )
                if not response:
                    print("❌ DEBUG: User chose not to continue without document")
                    return
                print("✅ DEBUG: User chose to continue without document")
            else:
                # Generic prompt, no document needed - just proceed
                print("✅ DEBUG: Generic prompt without document - proceeding")
        
        print(f"✅ DEBUG: Content status (document: {has_document}, attachments: {has_attachments})")
        
        if not self.model_var.get():
            print(f"❌ DEBUG: No model! model_var={self.model_var.get()}")
            messagebox.showerror("Error", "Please select an AI model.")
            return
        print(f"✅ DEBUG: Model: {self.model_var.get()}")
        
        # Ollama doesn't require an API key
        provider = self.provider_var.get()
        if provider != "Ollama (Local)" and not self.api_key_var.get():
            print(f"❌ DEBUG: No API key! api_key_var={bool(self.api_key_var.get())}")
            messagebox.showerror("Error", "Please enter an API key.")
            return
        print(f"✅ DEBUG: API key present (or Ollama - not required)")
        
        # 🆕 Check for local AI context limitations when using attachments
        if has_attachments:
            from attachment_handler import check_local_ai_context_warning
            
            # Calculate total words (main document + attachments)
            main_doc_words = len(self.current_document_text.split()) if self.current_document_text else 0
            attachment_words = self.attachment_manager.get_total_words()
            total_words = main_doc_words + attachment_words
            attachment_count = self.attachment_manager.get_attachment_count()
            
            warning = check_local_ai_context_warning(provider, total_words, attachment_count)
            if warning:
                response = messagebox.askyesno("Local AI Context Warning", warning)
                if not response:
                    print("❌ DEBUG: User cancelled due to local AI context warning")
                    return
        
        print("✅ DEBUG: Starting thread...")
        self.processing = True
        self.process_btn.config(state=tk.DISABLED)
        
        # Build status message that includes attachment count if any
        attachment_count = 0
        if hasattr(self, 'attachment_manager'):
            attachment_count = self.attachment_manager.get_attachment_count()
        
        # Check if using Local AI for more specific status message
        provider = self.provider_var.get()
        is_local_ai = provider == "Ollama (Local)"
        ai_label = "💻 Local AI" if is_local_ai else "AI"
        
        if not has_any_content:
            self.set_status(f"⚙️ Processing general query with {ai_label}...")
        elif attachment_count > 0:
            self.set_status(f"⚙️ Processing with {ai_label}: main document + {attachment_count} attachment{'s' if attachment_count != 1 else ''}...")
        else:
            self.set_status(f"⚙️ Processing with {ai_label}...")
        
        self.processing_thread = threading.Thread(target=self._process_document_thread)
        self.processing_thread.start()
        print(f"✅ DEBUG: Thread started, alive={self.processing_thread.is_alive()}")
        self.root.after(100, self.check_processing_thread)

    def _process_document_thread(self):
        prompt = self.prompt_text.get('1.0', tk.END).strip()
        self.current_prompt_text = prompt
        if not prompt:
            self.root.after(0, self._handle_process_result, False, "No prompt provided")
            return

        # 🆕 NEW: Check if we're processing attachments only (no main document)
        has_main_document = bool(self.current_entries)
        has_attachments = (hasattr(self, 'attachment_manager') and 
                          self.attachment_manager.get_attachment_count() > 0)
        
        # If no main document but have attachments, use simplified path
        if not has_main_document and has_attachments:
            # Skip chunking - just process attachments with prompt
            doc_title = "Attachments Only"
            prompt_name = "Custom Prompt"
            try:
                if hasattr(self, 'prompt_combo'):
                    prompt_name = self.prompt_combo.get() or "Custom Prompt"
            except:
                pass
            
            # Build messages (will include attachments)
            messages = self.build_threaded_messages(prompt)
            
            # Check if using Local AI
            is_local = self.provider_var.get() == "Ollama (Local)"
            ai_label = "💻 Local AI" if is_local else "AI"
            
            self.set_status(f"⚙️ Processing {self.attachment_manager.get_attachment_count()} attachments with {ai_label}...")
            success, result = get_ai().call_ai_provider(
                provider=self.provider_var.get(),
                model=self.model_var.get(),
                messages=messages,
                api_key=self.api_key_var.get(),
                document_title=doc_title,
                prompt_name=prompt_name
            )
            
            if not success:
                self.root.after(0, self._handle_process_result, False, result)
                return
            
            # Add to thread
            self.add_message_to_thread("user", prompt)
            self.add_message_to_thread("assistant", result)
            
            self.root.after(0, self._handle_process_result, True, result)
            return

        # Get chunk size setting
        chunk_size_setting = self.config.get("chunk_size", "medium")

        # Chunk the entries
        chunks = chunk_entries(self.current_entries, chunk_size_setting)

        # ============================================================
        # Get document title and prompt name for cost tracking
        # ============================================================
        doc_title = "Unknown Document"
        try:
            if hasattr(self, 'current_document_id') and self.current_document_id:
                from document_library import get_document_by_id
                doc = get_document_by_id(self.current_document_id)
                if doc:
                    doc_title = doc.get('title', 'Unknown Document')
        except Exception as e:
            print(f"Warning: Could not get document title: {e}")

        prompt_name = "Custom Prompt"
        try:
            if hasattr(self, 'prompt_combo'):
                prompt_name = self.prompt_combo.get()
                if not prompt_name:
                    prompt_name = "Custom Prompt"
        except Exception as e:
            print(f"Warning: Could not get prompt name: {e}")

        # ============================================================
        # SINGLE CHUNK PROCESSING (with threading support)
        # ============================================================
        if len(chunks) == 1:
            chunk_text = entries_to_text_with_speakers(
                chunks[0],
                timestamp_interval=self.config.get("timestamp_interval", "every_segment")
            ) if self.current_document_type == "audio_transcription" else entries_to_text(
                chunks[0],
                timestamp_interval=self.config.get("timestamp_interval", "every_segment")
            )

            # 🆕 MVP: Build messages with thread context
            messages = self.build_threaded_messages(prompt)

            # Build status message that includes attachment count if any
            attachment_count = 0
            if hasattr(self, 'attachment_manager'):
                attachment_count = self.attachment_manager.get_attachment_count()
            
            # Check if using Local AI
            is_local = self.provider_var.get() == "Ollama (Local)"
            ai_label = "💻 Local AI" if is_local else "AI"
            
            if attachment_count > 0:
                self.set_status(f"⚙️ Processing with {ai_label}: document + {attachment_count} attachment{'s' if attachment_count != 1 else ''}...")
            else:
                self.set_status(f"⚙️ Processing with {ai_label} (with conversation context)...")
            
            success, result = get_ai().call_ai_provider(
                provider=self.provider_var.get(),
                model=self.model_var.get(),
                messages=messages,
                api_key=self.api_key_var.get(),
                document_title=doc_title,
                prompt_name=prompt_name
            )

            if not success:
                self.root.after(0, self._handle_process_result, False, result)
                return

            # 🆕 MVP: Add to thread
            self.add_message_to_thread("user", prompt)
            self.add_message_to_thread("assistant", result)
            
            # 🆕 Save thread to SOURCE document so it appears when reloading the source
            if self.current_document_id:
                from document_library import save_thread_to_document
                thread_metadata = {
                    "model": self.model_var.get(),
                    "provider": self.provider_var.get(),
                    "last_updated": datetime.datetime.now().isoformat(),
                    "message_count": self.thread_message_count
                }
                save_thread_to_document(self.current_document_id, self.current_thread, thread_metadata)
                print(f"💾 Saved thread to source document {self.current_document_id}")

            # Update button states
            self.update_button_states()

            self.root.after(0, self._handle_process_result, True, result)
            return

        # ============================================================
        # MULTIPLE CHUNKS PROCESSING
        # ============================================================
        # NOTE: Multi-chunk doesn't use threading yet in MVP
        # This maintains existing behavior for chunked documents

        results = []
        chunk_prompt = prompt

        for i, chunk in enumerate(chunks, 1):
            if not self.processing:
                self.root.after(0, self._handle_process_result, False, "Processing cancelled")
                return

            chunk_text = entries_to_text_with_speakers(
                chunk,
                timestamp_interval=self.config.get("timestamp_interval", "every_segment")
            ) if self.current_document_type == "audio_transcription" else entries_to_text(
                chunk,
                timestamp_interval=self.config.get("timestamp_interval", "every_segment")
            )

            # For multi-chunk, use simple messages (threading works better with single chunk)
            messages = [
                {"role": "system", "content": "You are a helpful AI assistant analyzing documents."},
                {"role": "user", "content": f"{chunk_prompt}\n\n{chunk_text}"}
            ]

            # Build status message that includes attachment count if any
            attachment_count = 0
            if hasattr(self, 'attachment_manager'):
                attachment_count = self.attachment_manager.get_attachment_count()
            
            if attachment_count > 0:
                self.set_status(f"⚙️ Chunk {i}/{len(chunks)} (+ {attachment_count} attachment{'s' if attachment_count != 1 else ''})...")
            else:
                self.set_status(f"⚙️ Processing chunk {i}/{len(chunks)}...")
            success, result = get_ai().call_ai_provider(
                provider=self.provider_var.get(),
                model=self.model_var.get(),
                messages=messages,
                api_key=self.api_key_var.get(),
                document_title=f"{doc_title} (Chunk {i}/{len(chunks)})",
                prompt_name=f"{prompt_name} - Chunk {i}"
            )

            if not success:
                self.root.after(0, self._handle_process_result, False, result)
                return

            results.append(result)

            # Add delay between chunks to avoid rate limiting
            if i < len(chunks):
                import time
                delay_seconds = 12
                self.set_status(f"⏳ Waiting {delay_seconds}s before next chunk to avoid rate limits...")
                time.sleep(delay_seconds)

        # ============================================================
        # CONSOLIDATE MULTIPLE CHUNKS
        # ============================================================
        combined_chunks = "\n\n---\n\n".join([f"Section {i + 1}:\n{r}" for i, r in enumerate(results)])
        
        # 🆕 Include attachments in consolidation so AI sees all documents
        attachment_text = ""
        if hasattr(self, 'attachment_manager'):
            att_count = self.attachment_manager.get_attachment_count()
            print(f"📎 DEBUG CONSOLIDATION: attachment_manager exists, count = {att_count}")
            if att_count > 0:
                attachment_text = "\n\n" + self.attachment_manager.build_attachment_text()
                print(f"📎 DEBUG CONSOLIDATION: Attachment text length: {len(attachment_text)} chars")
        else:
            print(f"📎 DEBUG CONSOLIDATION: attachment_manager does NOT exist!")
        
        consolidation_prompt = f"{prompt}\n\nHere are the key points extracted from each section of the document:\n\n{combined_chunks}"
        if attachment_text:
            consolidation_prompt += attachment_text
            print(f"📎 DEBUG CONSOLIDATION: Added attachments. Final prompt length: {len(consolidation_prompt)} chars")
        else:
            print(f"📎 DEBUG CONSOLIDATION: No attachments added. Prompt length: {len(consolidation_prompt)} chars")

        # Build status message that includes attachment count if any
        attachment_count = 0
        if hasattr(self, 'attachment_manager'):
            attachment_count = self.attachment_manager.get_attachment_count()
        
        if attachment_count > 0:
            self.set_status(f"Consolidating results (including {attachment_count} attachment{'s' if attachment_count != 1 else ''})...")
        else:
            self.set_status("Consolidating results...")
        
        messages = [
            {"role": "system",
             "content": "You are a helpful AI assistant consolidating information from multiple document sections."},
            {"role": "user", "content": consolidation_prompt}
        ]

        success, final_result = get_ai().call_ai_provider(
            provider=self.provider_var.get(),
            model=self.model_var.get(),
            messages=messages,
            api_key=self.api_key_var.get(),
            document_title=f"{doc_title} (Consolidation)",
            prompt_name=f"{prompt_name} - Final"
        )

        if not success:
            self.root.after(0, self._handle_process_result, False, final_result)
            return

        # 🆕 MVP: Add consolidated result to thread
        self.add_message_to_thread("user", prompt)
        self.add_message_to_thread("assistant", final_result)
        
        # 🆕 Save thread to SOURCE document so it appears when reloading the source
        if self.current_document_id:
            from document_library import save_thread_to_document
            thread_metadata = {
                "model": self.model_var.get(),
                "provider": self.provider_var.get(),
                "last_updated": datetime.datetime.now().isoformat(),
                "message_count": self.thread_message_count
            }
            save_thread_to_document(self.current_document_id, self.current_thread, thread_metadata)
            print(f"💾 Saved thread to source document {self.current_document_id}")

        self.root.after(0, self._handle_process_result, True, final_result)
        # Add delay between chunks to avoid rate limiti

    def reset_ui_state(self):
        """Reset all UI elements to their normal (non-processing) state"""
        try:
            self.processing = False
            self.process_btn.config(state=tk.NORMAL)
            
            # Ensure the All Settings button remains visible
            if hasattr(self, 'settings_btn'):
                self.settings_btn.pack(side=tk.RIGHT, padx=5)
        except Exception as e:
            print(f"Error resetting UI state: {e}")

    def _handle_process_result(self, success, result):
        # Reset UI state including ensuring All Settings button is visible
        self.reset_ui_state()

        if success:
            # Apply automatic cleanup if enabled
            if True:  # Auto-cleanup always enabled
                result = get_formatter().clean_text_encoding(result)

            # Result will be displayed in Thread Viewer (auto-opened in Phase 2)
            

            # 🆕 NEW: Automatically save as processed output to library
            if self.current_document_id:
                self.save_ai_output_as_product_document(result)
            elif hasattr(self, 'attachment_manager') and self.attachment_manager.get_attachment_count() > 0:
                # Attachments-only processing - save as cross-document analysis
                self._save_attachments_output(result)

            self.set_status("✅ Processing complete")
            
            # Auto-open Thread Viewer to show the response
            self.root.after(100, lambda: self._show_thread_viewer(target_mode='conversation'))

        else:
            # User-friendly error handling
            self.set_status(f"❌ Error: {result}")

            # Build helpful error message
            error_text = f"AI Processing Error:\n\n{result}\n\n{'=' * 50}\n\n"
            result_lower = str(result).lower()

            # Check for specific error types
            if any(word in result_lower for word in ['model', '404', 'not_found', 'not found', 'does not exist']):
                error_text += "POSSIBLE CAUSE: Invalid or inactive model\n\nSolutions:\n"
                error_text += "1. Click 'All Settings' → AI Configuration\n"
                error_text += "2. Try a different model from the dropdown\n"
                error_text += "3. Click 'Refresh Models' to get the latest available models"
            elif any(word in result_lower for word in ['401', 'unauthorized', 'authentication', 'api key']):
                error_text += "POSSIBLE CAUSE: API Key issue\n\nSolutions:\n"
                error_text += "1. Check your API key in Settings\n"
                error_text += "2. Get a new key from console.anthropic.com or platform.openai.com"
            elif any(word in result_lower for word in ['429', 'rate limit', 'quota']):
                error_text += "POSSIBLE CAUSE: Rate limit exceeded\n\nSolutions:\n"
                error_text += "1. Wait a few minutes before trying again\n"
                error_text += "2. Check your API usage limits"
            elif any(word in result_lower for word in ['billing', 'payment', '403']):
                error_text += "POSSIBLE CAUSE: Billing issue\n\nSolutions:\n"
                error_text += "1. Check that billing is set up on your API account\n"
                error_text += "2. Verify your payment method is valid"
            else:
                error_text += "TROUBLESHOOTING:\n"
                error_text += "1. Check your API key in Settings\n"
                error_text += "2. Try a different model\n"
                error_text += "3. Check your internet connection"

            messagebox.showerror("AI Processing Error", error_text)

    def _save_processed_output(self, ai_response):
        """Save AI-generated output as a processed document in library"""

        # Get source document info
        source_doc = get_document_by_id(self.current_document_id)
        if not source_doc:
            print("⚠️ Warning: Source document not found, cannot save output")
            return

        source_title = source_doc.get('title', 'Unknown Document')

        # Determine output type from prompt
        prompt_text = getattr(self, 'current_prompt_text', 'Unknown prompt')

        # Detect type from prompt
        prompt_lower = prompt_text.lower()
        if "summary" in prompt_lower or "summarize" in prompt_lower:
            output_type = "summary"
            title_prefix = "Summary"
        elif "analysis" in prompt_lower or "analyze" in prompt_lower:
            output_type = "analysis"
            title_prefix = "Analysis"
        elif "extract" in prompt_lower or "key points" in prompt_lower:
            output_type = "extraction"
            title_prefix = "Key Points"
        elif "translate" in prompt_lower:
            output_type = "translation"
            title_prefix = "Translation"
        elif "dotpoints" in prompt_lower or "dot points" in prompt_lower:
            output_type = "dotpoints"
            title_prefix = "Dotpoints"
        elif "counter" in prompt_lower:
            output_type = "counter_arguments"
            title_prefix = "Counter Arguments"
        else:
            output_type = "output"
            title_prefix = "Output"

        # Convert AI response to entries format
        output_entries = [{
            "start": 0,
            "end": 0,
            "text": ai_response
        }]

        # Create metadata
        output_metadata = {
            'title': f"{title_prefix}: {source_title}",  # Add title for save functions
            'source_document_id': self.current_document_id,
            'source_document_title': source_title,
            'prompt_used': prompt_text,
            'model': self.model_var.get(),
            'provider': self.provider_var.get(),
            'generated_date': datetime.datetime.now().isoformat(),
            'output_type': output_type,
            'editable': True  # Response documents are editable
        }

        # Save to library as processed output
        output_id = add_document_to_library(
            doc_type=output_type,
            source=self.current_document_id,
            title=source_title,
            entries=output_entries,
            document_class="processed_output",
            metadata=output_metadata
        )

        print(f"📝 Saved processed output: {output_id}")
        print(f"   Type: {output_type}")
        print(f"   Title: {title_prefix}: {source_title}")
        
        # Update current document state to reflect the AI response (not source)
        self.current_document_class = "processed_output"
        self.current_document_metadata = output_metadata

    def _save_attachments_output(self, ai_response):
        """
        Save AI-generated output from attachments-only processing.
        Creates a new cross-document analysis document in the library.
        """
        # Get attachment info
        att_count = self.attachment_manager.get_attachment_count()
        att_names = [att['filename'] for att in self.attachment_manager.attachments]
        
        # Determine output type from prompt
        prompt_text = getattr(self, 'current_prompt_text', 'Unknown prompt')
        prompt_lower = prompt_text.lower()
        
        if "compar" in prompt_lower:
            output_type = "comparison"
            title_prefix = "Comparison"
        elif "summary" in prompt_lower or "summarize" in prompt_lower:
            output_type = "summary"
            title_prefix = "Summary"
        elif "analysis" in prompt_lower or "analyze" in prompt_lower:
            output_type = "analysis"
            title_prefix = "Cross-Document Analysis"
        elif "theme" in prompt_lower:
            output_type = "thematic_analysis"
            title_prefix = "Thematic Analysis"
        else:
            output_type = "cross_document_analysis"
            title_prefix = "Cross-Document Analysis"
        
        # Create a descriptive title
        if att_count == 1:
            title = f"{title_prefix}: {att_names[0][:50]}"
        elif att_count <= 3:
            title = f"{title_prefix}: {', '.join(n[:20] for n in att_names)}"
        else:
            title = f"{title_prefix}: {att_count} Documents"
        
        # Convert AI response to entries format
        output_entries = [{
            "start": 0,
            "end": 0,
            "text": ai_response
        }]
        
        # Create metadata
        output_metadata = {
            'title': title,  # Add title for save functions
            'source_documents': att_names,
            'source_count': att_count,
            'prompt_used': prompt_text,
            'model': self.model_var.get(),
            'provider': self.provider_var.get(),
            'generated_date': datetime.datetime.now().isoformat(),
            'output_type': output_type,
            'editable': True
        }
        
        # Generate a unique source identifier for the document ID
        import hashlib
        source_hash = hashlib.md5('|'.join(att_names).encode()).hexdigest()[:8]
        source_id = f"attachments_{source_hash}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Save to library
        output_id = add_document_to_library(
            doc_type=output_type,
            source=source_id,
            title=title,
            entries=output_entries,
            document_class="processed_output",
            metadata=output_metadata
        )
        
        print(f"📝 Saved cross-document analysis: {output_id}")
        print(f"   Type: {output_type}")
        print(f"   Title: {title}")
        print(f"   Sources: {att_count} attachments")
        
        # Update current document state to reflect the AI response (not source)
        self.current_document_class = "processed_output"
        self.current_document_metadata = output_metadata
        
        # Refresh library to show new document
        self.refresh_library()

    def _save_as_product(self, output_text, dialog):
        """Save AI output as new editable product document and load it"""
        doc_id = self.save_ai_output_as_product_document(output_text)
        if doc_id:
            dialog.destroy()

            # Load the newly created product document into the preview
            doc = get_document_by_id(doc_id)
            if doc:
                entries = load_document_entries(doc_id)
                if entries:
                    self.current_entries = entries
                    self.current_document_source = doc['source']
                    self.current_document_type = doc['type']
                    # ✅ FIX: Save old thread BEFORE changing document ID
                    if self.thread_message_count > 0 and self.current_document_id:
                        self.save_current_thread()
                    
                    # Clear thread manually
                    self.current_thread = []
                    self.thread_message_count = 0
                    self.update_thread_status()
                    
                    # NOW change the document ID
                    self.current_document_id = doc_id
                    self.current_document_class = doc.get("document_class", "source")
                    self.current_document_metadata = doc.get("metadata", {})

                    # Update preview with the product document text
                    self.current_document_text = entries_to_text(entries, timestamp_interval=self.config.get(
                        "timestamp_interval", "every_segment"))

                    self.set_status(f"✅ Product document loaded and ready to edit")
                    
                    # Update button states
                    self.update_button_states()

    def _save_as_metadata(self, output_text, dialog):
        """Save AI output as metadata attached to source document"""
        self.save_current_output(output_text)
        dialog.destroy()
    def save_current_output(self, output_text: str):
        """Save the current processed output to the library"""
        if not self.current_document_id:
            messagebox.showerror("Error", "No document loaded")
            return

        # Get prompt info
        prompt_name = self.prompt_combo.get() if self.prompt_combo.get() else "Custom Prompt"
        prompt_text = self.prompt_text.get('1.0', tk.END).strip()

        # Get model info
        provider = self.provider_var.get()
        model = self.model_var.get()

        # Optional notes dialog
        notes_window = tk.Toplevel(self.root)
        notes_window.title("Add Notes (Optional)")
        notes_window.geometry("400x200")
        self.apply_window_style(notes_window)

        ttk.Label(notes_window, text="Add optional notes about this output:",
                  font=('Arial', 10, 'bold')).pack(pady=10)

        notes_text = scrolledtext.ScrolledText(notes_window, wrap=tk.WORD, height=5, font=('Arial', 10))
        notes_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        def save_with_notes():
            notes = notes_text.get('1.0', tk.END).strip()
            output_id = add_processed_output_to_document(
                doc_id=self.current_document_id,
                prompt_name=prompt_name,
                prompt_text=prompt_text,
                provider=provider,
                model=model,
                output_text=output_text,
                notes=notes
            )

            if output_id:
                messagebox.showinfo("Success", "Output saved to library!")
                self.refresh_library()
            else:
                messagebox.showerror("Error", "Failed to save output")

            notes_window.destroy()

        def skip_notes():
            output_id = add_processed_output_to_document(
                doc_id=self.current_document_id,
                prompt_name=prompt_name,
                prompt_text=prompt_text,
                provider=provider,
                model=model,
                output_text=output_text,
                notes=""
            )

            if output_id:
                messagebox.showinfo("Success", "Output saved to library!")
                self.refresh_library()
            else:
                messagebox.showerror("Error", "Failed to save output")

            notes_window.destroy()

        btn_frame = ttk.Frame(notes_window)
        btn_frame.pack(fill=tk.X, pady=10)
        ttk.Button(btn_frame, text="Save with Notes", command=save_with_notes).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Save without Notes", command=skip_notes).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=notes_window.destroy).pack(side=tk.RIGHT, padx=5)

    def cancel_processing(self):
        """Restart DocAnalyser - useful to cancel processing or reset the application."""
        # Check if user has opted to skip confirmation
        skip_confirm = self.config.get("cancel_restart_no_confirm", False)
        
        if not skip_confirm:
            # Show confirmation dialog with "don't ask again" option
            result = self._show_cancel_confirmation()
            if result is None:  # User clicked No or closed dialog
                return
        
        # Perform restart
        self._restart_application()
    
    def _show_cancel_confirmation(self):
        """Show cancel confirmation dialog with 'don't ask again' checkbox."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Restart DocAnalyser")
        dialog.geometry("400x180")
        dialog.transient(self.root)
        dialog.grab_set()
        self.apply_window_style(dialog)
        
        # Center on parent
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 400) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 180) // 2
        dialog.geometry(f"+{x}+{y}")
        
        result = [None]  # Use list to allow modification in nested function
        
        # Message
        ttk.Label(
            dialog,
            text="⚠️ This will restart DocAnalyser.\n\nAny work in progress will be lost.\nDocuments already saved to the Library are safe.",
            wraplength=360,
            justify=tk.CENTER
        ).pack(pady=(20, 15))
        
        # Don't ask again checkbox
        dont_ask_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            dialog,
            text="Don't ask me again",
            variable=dont_ask_var
        ).pack(pady=(0, 15))
        
        # Buttons
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=(0, 15))
        
        def on_yes():
            if dont_ask_var.get():
                self.config["cancel_restart_no_confirm"] = True
                save_config(self.config)
            result[0] = True
            dialog.destroy()
        
        def on_no():
            result[0] = None
            dialog.destroy()
        
        ttk.Button(btn_frame, text="Yes, Restart", command=on_yes, width=12).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="No, Continue", command=on_no, width=12).pack(side=tk.LEFT, padx=5)
        
        dialog.protocol("WM_DELETE_WINDOW", on_no)
        dialog.wait_window()
        
        return result[0]
    
    def _restart_application(self):
        """Restart the application using os.execv for a clean restart."""
        import sys
        import os
        
        self.set_status("Restarting...")
        self.root.update()
        
        try:
            # Get the Python executable and script path
            python = sys.executable
            script = os.path.abspath(sys.argv[0])
            
            # If running as a compiled exe, just restart the exe
            if getattr(sys, 'frozen', False):
                # Running as compiled executable (PyInstaller)
                os.execv(sys.executable, [sys.executable] + sys.argv[1:])
            else:
                # Running as Python script
                os.execv(python, [python, script] + sys.argv[1:])
        except Exception as e:
            # Fallback: just quit and let user restart manually
            messagebox.showinfo(
                "Restart Required",
                f"Please restart DocAnalyser manually.\n\nError: {e}"
            )
            self.root.quit()

    def check_processing_thread(self):
        alive = self.processing_thread.is_alive() if self.processing_thread else False
        print(f"⏰ check_processing: processing={self.processing}, alive={alive}")
        if self.processing and self.processing_thread and self.processing_thread.is_alive():
            self.root.after(100, self.check_processing_thread)
        else:
            self.processing = False
            self.process_btn.config(state=tk.NORMAL)
            # Don't set status here - let the result handlers set the appropriate status
            # This avoids race conditions where check_processing_thread runs before
            # the result handler has a chance to set the status

    def save_output(self):
        if not self.current_document_text:
            messagebox.showerror("Error", "No content to save. Use Thread Viewer for export options.")
            return

        content = self.current_document_text

        # Clean up any encoding issues before saving
        content = get_formatter().clean_text_encoding(content)

        file_path = filedialog.asksaveasfilename(
            defaultextension=".rtf",
            filetypes=[("RTF files", "*.rtf"), ("Text files", "*.txt")]
        )
        if not file_path:
            return

        if file_path.endswith('.rtf'):
            rtf_content = get_formatter().generate_rtf_content(
                title=self.current_document_source or "Document",
                content=content,
                metadata={"Source": self.current_document_source, "Type": self.current_document_type}
            )
            # Use ASCII encoding for RTF - Unicode is handled by RTF codes
            with open(file_path, 'w', encoding='ascii', errors='ignore') as f:
                f.write(rtf_content)
        else:
            # Use UTF-8 for plain text files
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)

        self.set_status(f"✅ Saved to {file_path}")

