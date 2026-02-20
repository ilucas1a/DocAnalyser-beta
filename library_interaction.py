"""
library_interaction.py - Document Library UI interactions for DocAnalyser.

Handles viewing processed outputs, deleting documents, bulk processing,
adding sources, and the main library window.

Extracted from Main.py to reduce file size. Uses a mixin pattern so all
self.xxx references continue to work unchanged.
"""

from __future__ import annotations

import os
import json
import datetime
import logging
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
from typing import List, Dict, Optional

from config import DATA_DIR
from document_library import (
    add_document_to_library,
    get_document_by_id,
    get_processed_outputs_for_document,
    delete_document,
    load_document_entries,
)
from utils import entries_to_text, entries_to_text_with_speakers
from sources_dialog import open_sources_dialog, open_bulk_processing

# Lazy module loaders (mirrors Main.py pattern)
def get_ocr():
    import ocr_handler
    return ocr_handler

def get_doc_fetcher():
    import document_fetcher
    return document_fetcher

def get_ai():
    import ai_handler
    return ai_handler


class LibraryInteractionMixin:
    """Mixin class providing Document Library interaction methods for DocAnalyzerApp."""

    def view_processed_outputs(self, doc_id: str, doc_title: str):
        """Show all processed outputs for a document"""
        outputs = get_processed_outputs_for_document(doc_id)

        if not outputs:
            messagebox.showinfo("No Outputs", f"No processed outputs found for:\n{doc_title}")
            return

        outputs_window = tk.Toplevel(self.root)
        outputs_window.title(f"Processed Outputs - {doc_title}")
        outputs_window.geometry("800x600")
        self.apply_window_style(outputs_window)

        # Header
        header_frame = ttk.Frame(outputs_window, padding=10)
        header_frame.pack(fill=tk.X)
        ttk.Label(header_frame, text=f"📚 Processed Outputs", font=('Arial', 14, 'bold')).pack(side=tk.LEFT)
        ttk.Label(header_frame, text=f"({len(outputs)} saved)", font=('Arial', 10)).pack(side=tk.LEFT, padx=10)

        # Document info
        info_frame = ttk.Frame(outputs_window, padding=(10, 0))
        info_frame.pack(fill=tk.X)
        ttk.Label(info_frame, text=f"Source: {doc_title}", font=('Arial', 9, 'italic')).pack(anchor=tk.W)

        # List of outputs
        list_frame = ttk.LabelFrame(outputs_window, text="Saved Outputs", padding=10)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Scrollable listbox with details
        outputs_listbox = tk.Listbox(list_frame, height=10, font=('Arial', 9))
        outputs_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=outputs_listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        outputs_listbox.config(yscrollcommand=scrollbar.set)

        # Populate list
        for output in outputs:
            timestamp = datetime.datetime.fromisoformat(output['timestamp']).strftime("%Y-%m-%d %H:%M")
            display = f"[{timestamp}] {output['prompt_name']} ({output['provider']} - {output['model']})"
            outputs_listbox.insert(tk.END, display)

        # Preview frame
        preview_frame = ttk.LabelFrame(outputs_window, text="Preview", padding=10)
        preview_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        preview_text = scrolledtext.ScrolledText(preview_frame, wrap=tk.WORD, height=8, font=('Arial', 10))
        preview_text.pack(fill=tk.BOTH, expand=True)
        preview_text.config(state=tk.DISABLED)

        # Selection handler
        def on_output_select(event):
            selection = outputs_listbox.curselection()
            if not selection:
                return

            idx = selection[0]
            output = outputs[idx]

            preview_text.config(state=tk.NORMAL)
            preview_text.delete('1.0', tk.END)

            # Show metadata
            preview_text.insert(tk.END, f"Timestamp: {output['timestamp']}\n")
            preview_text.insert(tk.END, f"Prompt: {output['prompt_name']}\n")
            preview_text.insert(tk.END, f"Model: {output['provider']} - {output['model']}\n")
            if output.get('notes'):
                preview_text.insert(tk.END, f"Notes: {output['notes']}\n")
            preview_text.insert(tk.END, f"\n{'=' * 50}\n\n")
            preview_text.insert(tk.END, output['preview'])

            preview_text.config(state=tk.DISABLED)

        outputs_listbox.bind('<<ListboxSelect>>', on_output_select)

        # Select first item by default
        if outputs:
            outputs_listbox.selection_set(0)
            on_output_select(None)

        # Button frame
        btn_frame = ttk.Frame(outputs_window, padding=10)
        btn_frame.pack(fill=tk.X)

        def export_output():
            selection = outputs_listbox.curselection()
            if not selection:
                messagebox.showwarning("No Selection", "Please select an output to save")
                return

            idx = selection[0]
            output = outputs[idx]
            full_text = load_processed_output(output['id'])

            if not full_text:
                messagebox.showerror("Error", "Could not load output text")
                return

            file_path = filedialog.asksaveasfilename(
                defaultextension=".txt",
                filetypes=[("Text files", "*.txt"), ("RTF files", "*.rtf"), ("All files", "*.*")],
                initialfile=f"{output['prompt_name']}_{output['timestamp'][:10]}"
            )

            if file_path:
                try:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(full_text)
                    messagebox.showinfo("Success", f"Saved to:\n{file_path}")
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to save: {str(e)}")

        def delete_output():
            selection = outputs_listbox.curselection()
            if not selection:
                messagebox.showwarning("No Selection", "Please select an output to delete")
                return

            idx = selection[0]
            output = outputs[idx]

            if messagebox.askyesno("Confirm Delete",
                                   f"Delete this output?\n\n{output['prompt_name']}\n{output['timestamp']}"):
                if delete_processed_output(doc_id, output['id']):
                    messagebox.showinfo("Success", "Output deleted")
                    outputs_window.destroy()
                    self.view_processed_outputs(doc_id, doc_title)  # Refresh
                else:
                    messagebox.showerror("Error", "Failed to delete output")

        # View Full Output button removed - use Thread Viewer instead
        ttk.Button(btn_frame, text="Save", command=export_output).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Delete", command=delete_output).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Close", command=outputs_window.destroy).pack(side=tk.RIGHT, padx=5)

    def delete_from_library(self, doc_id: str, doc_title: str):
        """Delete a document and all its processed outputs from the library"""
        outputs = get_processed_outputs_for_document(doc_id)
        output_count = len(outputs)

        msg = f"Delete this document from the library?\n\n{doc_title}"
        if output_count > 0:
            msg += f"\n\nThis will also delete {output_count} processed output(s)."

        if not messagebox.askyesno("Confirm Delete", msg):
            return

        # Delete all processed outputs
        for output in outputs:
            delete_processed_output(doc_id, output['id'])

        # Delete document entries file
        entries_file = os.path.join(DATA_DIR, f"doc_{doc_id}_entries.json")
        if os.path.exists(entries_file):
            try:
                os.remove(entries_file)
            except Exception:
                pass

        # Remove from library
        library = load_library()
        library["documents"] = [doc for doc in library["documents"] if doc.get("id") != doc_id]
        save_library(library)

        # Refresh library display
        self.refresh_library()

        messagebox.showinfo("Success", "Document deleted from library")

    def open_bulk_processing(self):
        """Open the bulk processing window."""
        
        # Check if an embedding model is selected (can't do chat completions)
        current_model = self.model_var.get().lower()
        embedding_keywords = ['embed', 'embedding', 'nomic', 'bge', 'e5-', 'gte-']
        is_embedding_model = any(keyword in current_model for keyword in embedding_keywords)
        
        if is_embedding_model:
            from tkinter import messagebox
            result = messagebox.askokcancel(
                "Embedding Model Selected",
                f"The currently selected model '{self.model_var.get()}' appears to be an embedding model, "
                f"which cannot process prompts.\n\n"
                f"For bulk processing, please select a chat/instruct model such as:\n"
                f"• Qwen2.5-Instruct\n"
                f"• Llama-3-Instruct\n"
                f"• Mistral-Instruct\n"
                f"• DeepSeek-Chat\n\n"
                f"Click OK to open Bulk Processing anyway, or Cancel to go back and change the model."
            )
            if not result:
                return
        
        def process_single_item(url_or_path: str, status_callback) -> tuple:
            """
            Process a single URL or file path.
            Returns: (success: bool, result_or_error: str, title: Optional[str])
            """
            try:
                # Detect type and process accordingly
                url_or_path = url_or_path.strip()
                
                # Check if it's a file
                if os.path.isfile(url_or_path):
                    status_callback(f"Processing file: {os.path.basename(url_or_path)}")
                    ext = os.path.splitext(url_or_path)[1].lower()
                    
                    # 🆕 NEW: Handle .url files (Windows Internet Shortcuts)
                    if ext == '.url':
                        # Extract the actual URL from the .url file
                        try:
                            with open(url_or_path, 'r', encoding='utf-8', errors='ignore') as f:
                                content = f.read()
                            # Parse the URL from [InternetShortcut] format
                            import re
                            url_match = re.search(r'URL=(.+)', content, re.IGNORECASE)
                            if url_match:
                                extracted_url = url_match.group(1).strip()
                                status_callback(f"Extracted URL: {extracted_url[:50]}...")
                                # Recursively process the extracted URL
                                return process_single_item(extracted_url, status_callback)
                            else:
                                return False, "Could not extract URL from .url file", None
                        except Exception as e:
                            return False, f"Error reading .url file: {str(e)}", None
                    
                    # Check for audio/video files - skip in bulk mode (need transcription)
                    if ext in ('.mp3', '.wav', '.m4a', '.ogg', '.flac', '.aac', '.wma', '.opus', '.mp4', '.avi', '.mov'):
                        return False, "Audio/video files require transcription (not supported in bulk mode yet)", None
                    
                    # Use document fetcher for files
                    doc_fetcher = get_doc_fetcher()
                    success, result, title, doc_type = doc_fetcher.fetch_local_file(url_or_path)
                    
                    if success:
                        # Result is a list of entries, convert to text
                        if isinstance(result, list):
                            text = doc_fetcher.legacy_entries_to_text(result, include_timestamps=False)
                        else:
                            text = str(result)
                        return True, text, title or os.path.basename(url_or_path)
                    
                    elif result == "SCANNED_PDF":
                        # Handle scanned PDF with OCR
                        status_callback(f"OCR processing: {os.path.basename(url_or_path)}...")
                        try:
                            ocr_handler = get_ocr()
                            
                            # Check OCR availability
                            available, error_msg, _ = ocr_handler.check_ocr_availability()
                            if not available:
                                return False, f"OCR not available: {error_msg}", None
                            
                            # Process with smart extraction (includes Cloud AI fallback)
                            provider = self.provider_var.get()
                            model = self.model_var.get()
                            api_key = self.config.get("keys", {}).get(provider, "")
                            all_api_keys = self.config.get("keys", {})
                            
                            success, result, method = ocr_handler.extract_text_from_pdf_smart(
                                filepath=url_or_path,
                                language=self.config.get("ocr_language", "eng"),
                                quality=self.config.get("ocr_quality", "balanced"),
                                provider=provider,
                                model=model,
                                api_key=api_key,
                                all_api_keys=all_api_keys,
                                progress_callback=status_callback,
                                force_cloud=False
                            )
                            
                            if success:
                                text = doc_fetcher.legacy_entries_to_text(result, include_timestamps=False)
                                return True, text, os.path.basename(url_or_path)
                            else:
                                return False, f"OCR failed: {result}", None
                                
                        except Exception as e:
                            return False, f"OCR failed: {str(e)}", None
                    else:
                        error_msg = str(result) if result else "Could not extract text from file"
                        return False, error_msg, None
                
                # Check if it's a YouTube URL
                from youtube_utils import is_youtube_url, get_youtube_transcript
                if is_youtube_url(url_or_path):
                    status_callback("Fetching YouTube transcript...")
                    result = get_youtube_transcript(url_or_path, status_callback=status_callback)
                    if result and result.get('text'):
                        return True, result['text'], result.get('title', 'YouTube Video')
                    else:
                        return False, "Could not fetch YouTube transcript", None
                
                # Check if it's a Substack URL
                from substack_utils import is_substack_url, fetch_substack_content
                if is_substack_url(url_or_path):
                    status_callback("Fetching Substack content...")
                    result = fetch_substack_content(url_or_path, status_callback=status_callback)
                    if result and result.get('text'):
                        return True, result['text'], result.get('title', 'Substack Article')
                    elif result and result.get('audio_file'):
                        # Has audio but needs transcription - skip for now
                        return False, "Audio content requires transcription (not supported in bulk mode yet)", None
                    else:
                        return False, result.get('error', 'Could not fetch Substack content'), None
                
                # Assume it's a web URL
                status_callback("Fetching web content...")
                doc_fetcher = get_doc_fetcher()
                success, result, title, doc_type, web_metadata = doc_fetcher.fetch_web_url(url_or_path)
                if success:
                    # Result is a list of entries, convert to text
                    if isinstance(result, list):
                        text = doc_fetcher.legacy_entries_to_text(result, include_timestamps=False)
                    else:
                        text = str(result)
                    return True, text, title or url_or_path
                else:
                    return False, str(result) if result else "Could not fetch web content", None
                    
            except Exception as e:
                return False, str(e), None
        
        def get_current_settings() -> dict:
            """Get current AI provider/model/prompt settings."""
            return {
                'provider': self.provider_var.get(),
                'model': self.model_var.get(),
                'prompt_name': self.prompt_combo.get() if hasattr(self, 'prompt_combo') else 'Default',
                'prompt_text': self.prompt_text.get('1.0', tk.END).strip() if hasattr(self, 'prompt_text') else ''
            }
        
        def save_to_library(title: str, content: str, source: str, doc_class: str = 'source') -> str:
            """Save processed content to the document library.
            
            Args:
                title: Document title
                content: Document content
                source: Source URL or file path
                doc_class: 'source' for original documents, 'product' for AI responses
                
            Returns:
                Document ID if successful, None otherwise
            """
            try:
                # Create entries from content with appropriate location tag
                if doc_class == 'product':
                    location_tag = 'AI Response'
                else:
                    location_tag = 'Bulk Imported'
                entries = [{'text': content, 'start': 0, 'location': location_tag}]
                
                # Use different doc_type for source vs product to ensure unique IDs
                if doc_class == 'product':
                    doc_type = "bulk_ai_response"
                else:
                    doc_type = "bulk_import"
                
                # Add to document library
                doc_id = add_document_to_library(
                    doc_type=doc_type,
                    source=source,
                    title=title,
                    entries=entries,
                    document_class=doc_class,
                    metadata={
                        "imported_via": "bulk_processing",
                        "fetched": datetime.datetime.now().isoformat() + 'Z'
                    }
                )
                return doc_id
            except Exception as e:
                print(f"Failed to save to library: {e}")
                return None
        
        def ai_process_callback(text: str, title: str, status_callback) -> tuple:
            """Run AI analysis on extracted text.
            
            Args:
                text: The extracted document text
                title: Document title (for logging)
                status_callback: Function to report status updates
                
            Returns:
                (success: bool, result_or_error: str)
            """
            try:
                # Get current prompt
                prompt = self.prompt_text.get('1.0', tk.END).strip()
                if not prompt:
                    return False, "No prompt configured"
                
                # Get current settings
                provider = self.provider_var.get()
                model = self.model_var.get()
                api_key = self.api_key_var.get()
                
                status_callback(f"Sending to {provider}/{model}...")
                
                # Build messages
                messages = [
                    {"role": "system", "content": "You are a helpful AI assistant analyzing documents."},
                    {"role": "user", "content": f"{prompt}\n\n{text}"}
                ]
                
                # Call AI
                success, result = get_ai().call_ai_provider(
                    provider=provider,
                    model=model,
                    messages=messages,
                    api_key=api_key,
                    document_title=title,
                    prompt_name=self.prompt_combo.get() if hasattr(self, 'prompt_combo') else 'Bulk Processing'
                )
                
                return success, result
                
            except Exception as e:
                return False, f"AI processing error: {str(e)}"
        
        # Open the bulk processing window with all callbacks
        # Note: ai_process_callback is set to None so bulk import only fetches and saves
        # AI analysis can be done later via the main interface or attachments
        open_bulk_processing(
            self.root,
            process_single_item,
            get_current_settings,
            save_to_library,
            None  # No AI processing - just fetch and add to library
        )

    def open_add_sources(self):
        """
        Open the unified Add Sources dialog.
        
        Allows users to add sources to either:
        - Documents Library (permanent)
        - Prompt Context (temporary, for multi-document analysis)
        """
        def get_current_settings():
            return {
                'provider': self.provider_var.get(),
                'model': self.model_var.get(),
                'prompt_name': self.prompt_combo.get() if hasattr(self, 'prompt_combo') else 'Default',
                'prompt_text': self.prompt_text.get('1.0', tk.END).strip() if hasattr(self, 'prompt_text') else ''
            }
        
        def process_single_item(url_or_path: str, status_callback) -> tuple:
            """
            Process a single URL or file path.
            Returns: (success: bool, result_or_error: str, title: Optional[str])
            """
            try:
                url_or_path = url_or_path.strip()
                
                # Check if it's a file
                if os.path.isfile(url_or_path):
                    status_callback(f"Processing file: {os.path.basename(url_or_path)}")
                    ext = os.path.splitext(url_or_path)[1].lower()
                    
                    # Handle .url files (Windows Internet Shortcuts)
                    if ext == '.url':
                        try:
                            with open(url_or_path, 'r', encoding='utf-8', errors='ignore') as f:
                                content = f.read()
                            import re
                            url_match = re.search(r'URL=(.+)', content, re.IGNORECASE)
                            if url_match:
                                extracted_url = url_match.group(1).strip()
                                status_callback(f"Extracted URL: {extracted_url[:50]}...")
                                return process_single_item(extracted_url, status_callback)
                            else:
                                return False, "Could not extract URL from .url file", None
                        except Exception as e:
                            return False, f"Error reading .url file: {str(e)}", None
                    
                    # Check for audio/video files - skip (need transcription)
                    if ext in ('.mp3', '.wav', '.m4a', '.ogg', '.flac', '.aac', '.wma', '.opus', '.mp4', '.avi', '.mov'):
                        return False, "Audio/video files require transcription (use Load button instead)", None
                    
                    # Use document fetcher for files
                    doc_fetcher = get_doc_fetcher()
                    success, result, title, doc_type = doc_fetcher.fetch_local_file(url_or_path)
                    
                    if success:
                        if isinstance(result, list):
                            text = doc_fetcher.legacy_entries_to_text(result, include_timestamps=False)
                        else:
                            text = str(result)
                        return True, text, title or os.path.basename(url_or_path)
                    
                    elif result == "SCANNED_PDF":
                        status_callback(f"OCR processing: {os.path.basename(url_or_path)}...")
                        try:
                            ocr_handler = get_ocr()
                            available, error_msg, _ = ocr_handler.check_ocr_availability()
                            if not available:
                                return False, f"OCR not available: {error_msg}", None
                            
                            # Process with smart extraction (includes Cloud AI fallback)
                            provider = self.provider_var.get()
                            model = self.model_var.get()
                            api_key = self.config.get("keys", {}).get(provider, "")
                            all_api_keys = self.config.get("keys", {})
                            
                            success, result, method = ocr_handler.extract_text_from_pdf_smart(
                                filepath=url_or_path,
                                language=self.config.get("ocr_language", "eng"),
                                quality=self.config.get("ocr_quality", "balanced"),
                                provider=provider,
                                model=model,
                                api_key=api_key,
                                all_api_keys=all_api_keys,
                                progress_callback=status_callback,
                                force_cloud=False
                            )
                            
                            if success:
                                text = doc_fetcher.legacy_entries_to_text(result, include_timestamps=False)
                                return True, text, os.path.basename(url_or_path)
                            else:
                                return False, f"OCR failed: {result}", None
                        except Exception as e:
                            return False, f"OCR failed: {str(e)}", None
                    else:
                        error_msg = str(result) if result else "Could not extract text from file"
                        return False, error_msg, None
                
                # Check if it's a YouTube URL
                from youtube_utils import is_youtube_url, get_youtube_transcript
                if is_youtube_url(url_or_path):
                    status_callback("Fetching YouTube transcript...")
                    result = get_youtube_transcript(url_or_path, status_callback=status_callback)
                    if result and result.get('text'):
                        return True, result['text'], result.get('title', 'YouTube Video')
                    else:
                        return False, "Could not fetch YouTube transcript", None
                
                # Check if it's a Substack URL
                from substack_utils import is_substack_url, fetch_substack_content
                if is_substack_url(url_or_path):
                    status_callback("Fetching Substack content...")
                    result = fetch_substack_content(url_or_path, status_callback=status_callback)
                    if result and result.get('text'):
                        return True, result['text'], result.get('title', 'Substack Article')
                    elif result and result.get('audio_file'):
                        return False, "Audio content requires transcription", None
                    else:
                        return False, result.get('error', 'Could not fetch Substack content'), None
                
                # Try as generic web URL
                if url_or_path.startswith(('http://', 'https://')):
                    status_callback("Fetching web content...")
                    try:
                        doc_fetcher = get_doc_fetcher()
                        success, result, title = doc_fetcher.fetch_from_url(url_or_path)
                        if success:
                            if isinstance(result, list):
                                text = doc_fetcher.legacy_entries_to_text(result, include_timestamps=False)
                            else:
                                text = str(result)
                            return True, text, title or url_or_path
                        else:
                            return False, result, None
                    except Exception as e:
                        return False, f"Error fetching URL: {str(e)}", None
                
                return False, "Unknown source type", None
                
            except Exception as e:
                return False, str(e), None
        
        def save_to_library(title: str, content: str, source: str, doc_class: str = 'source') -> Optional[str]:
            """Save content to the document library."""
            try:
                if doc_class == 'product':
                    location_tag = 'AI Response'
                else:
                    location_tag = 'Added via Sources Dialog'
                entries = [{'text': content, 'start': 0, 'location': location_tag}]
                
                if doc_class == 'product':
                    doc_type = "ai_response"
                else:
                    doc_type = "imported"
                
                doc_id = add_document_to_library(
                    doc_type=doc_type,
                    source=source,
                    title=title,
                    entries=entries,
                    document_class=doc_class,
                    metadata={
                        "imported_via": "sources_dialog",
                        "fetched": datetime.datetime.now().isoformat() + 'Z'
                    }
                )
                return doc_id
            except Exception as e:
                print(f"Failed to save to library: {e}")
                return None
        
        def on_complete():
            """Called when sources dialog closes with changes."""
            self.update_add_sources_button()
        
        # Open the unified sources dialog
        open_sources_dialog(
            parent=self.root,
            process_callback=process_single_item,
            get_settings_callback=get_current_settings,
            save_to_library_callback=save_to_library,
            ai_process_callback=None,
            attachment_manager=self.attachment_manager,
            mode="unified",
            status_callback=self.set_status,
            get_provider_callback=lambda: self.provider_var.get(),
            on_complete_callback=on_complete
        )

    def update_add_sources_button(self):
        """Update the Add Sources button to show attachment count."""
        # Add sources button removed - using multi-line input

    def open_library_window(self):
        """Open Documents Library with tree structure"""
        try:
            # Debug: Check if files exist
            import os
            import sys
            
            project_dir = os.path.dirname(os.path.abspath(__file__))
            tree_base_path = os.path.join(project_dir, "tree_manager_base.py")
            doc_tree_path = os.path.join(project_dir, "document_tree_manager.py")
            
            print(f"\n{'='*60}")
            print(f"DEBUG: Opening Documents Library")
            print(f"Project dir: {project_dir}")
            print(f"tree_manager_base.py exists: {os.path.exists(tree_base_path)}")
            print(f"document_tree_manager.py exists: {os.path.exists(doc_tree_path)}")
            print(f"Python path: {sys.path[:3]}")
            print(f"{'='*60}\n")
            
            from document_tree_manager import open_document_tree_manager
            from config import LIBRARY_PATH
            
            # Callback to load document in main window
            def load_document_callback(doc_id):
                """Load a document from the library into the main window"""
                # This is called when user double-clicks or clicks "Load Document"
                from document_library import get_document_by_id, load_document_entries
                
                doc = get_document_by_id(doc_id)
                if not doc:
                    messagebox.showerror("Error", "Document not found")
                    return
                
                doc_title = doc.get('title', 'Unknown Document')
                
                # Check if a viewer is already open and ask user what to do
                viewer_action = self._check_viewer_open_action(doc_title)
                if viewer_action == 'cancel':
                    return  # User cancelled
                
                # Store the action for later use when auto-opening viewer
                force_new_viewer = (viewer_action == 'side_by_side')
                
                # If replacing, close ALL existing viewers first
                if viewer_action == 'replace':
                    if hasattr(self, '_thread_viewer_windows') and self._thread_viewer_windows:
                        for viewer in self._thread_viewer_windows[:]:  # Copy list
                            try:
                                if viewer.window.winfo_exists():
                                    viewer.window.destroy()
                            except:
                                pass
                        self._thread_viewer_windows.clear()
                
                # Check for active thread before loading
                if not self.check_active_thread_before_load(doc_title):
                    return  # User cancelled
                
                # Load the document
                if doc.get('type') == 'conversation_thread':
                    # Thread document
                    self.current_document_source = doc['source']
                    self.current_document_type = doc['type']
                    self.current_document_id = doc_id
                    self.current_document_class = doc.get("document_class", "thread")
                    self.current_document_metadata = doc.get("metadata", {})
                    if 'title' not in self.current_document_metadata:
                        self.current_document_metadata['title'] = doc_title
                    
                    # === CRITICAL: Load source document entries for processing ===
                    # Thread documents need their parent source's entries for follow-ups
                    parent_doc_id = self.current_document_metadata.get('parent_document_id') or \
                                   self.current_document_metadata.get('original_document_id')
                    
                    if parent_doc_id:
                        parent_entries = load_document_entries(parent_doc_id)
                        if parent_entries:
                            self.current_entries = parent_entries
                            print(f"📄 Loaded {len(parent_entries)} entries from parent source document")
                            # Also get source text
                            parent_doc = get_document_by_id(parent_doc_id)
                            if parent_doc:
                                from utils import entries_to_text, entries_to_text_with_speakers
                                parent_type = parent_doc.get('type', 'text')
                                if parent_type == 'audio_transcription':
                                    self.current_document_text = entries_to_text_with_speakers(
                                        parent_entries,
                                        timestamp_interval=self.config.get("timestamp_interval", "every_segment")
                                    )
                                else:
                                    self.current_document_text = entries_to_text(parent_entries)
                        else:
                            self.current_entries = []
                            self.current_document_text = doc.get("text", "No conversation text available")
                            print(f"⚠️ Could not load entries from parent: {parent_doc_id}")
                    else:
                        self.current_entries = []
                        self.current_document_text = doc.get("text", "No conversation text available")
                        print(f"⚠️ Thread document has no parent_document_id in metadata")
                    
                    self.clear_thread()
                    conversation_thread = doc.get("conversation_thread", [])
                    if conversation_thread:
                        self.current_thread = conversation_thread
                        self.thread_message_count = len([m for m in conversation_thread if m.get("role") == "user"])
                        self.update_thread_status()
                    
                    self.set_status(f"✅ Thread loaded ({self.thread_message_count} messages) | View Thread window opening")
                    
                    # Auto-open thread viewer for thread documents
                    # Use force_new_window if user chose side-by-side
                    # (capture force_new_viewer value at lambda creation time)
                    self.root.after(100, lambda fnw=force_new_viewer: self._show_thread_viewer(target_mode='conversation', force_new_window=fnw))
                else:
                    # Regular document
                    entries = load_document_entries(doc_id)
                    if entries:
                        self.current_entries = entries
                        self.current_document_source = doc['source']
                        self.current_document_type = doc['type']
                        
                        # Save old thread BEFORE changing document ID
                        if self.thread_message_count > 0 and self.current_document_id:
                            self.save_current_thread()
                        
                        self.current_thread = []
                        self.thread_message_count = 0
                        self.update_thread_status()
                        
                        self.current_document_id = doc_id
                        self.load_saved_thread()
                        
                        # Get document class and metadata
                        self.current_document_class = doc.get("document_class", "source")
                        self.current_document_metadata = doc.get("metadata", {})
                        if 'title' not in self.current_document_metadata:
                            self.current_document_metadata['title'] = doc_title
                        
                        # Convert entries to text
                        from utils import entries_to_text, entries_to_text_with_speakers
                        self.current_document_text = entries_to_text_with_speakers(
                            entries,
                            timestamp_interval=self.config.get("timestamp_interval", "every_segment")
                        ) if doc['type'] == "audio_transcription" else entries_to_text(entries)
                        
                        
                        # Update the View Source/Thread button state
                        self.update_view_button_state()
                        
                        # Debug output
                        print(f"📄 Source document loaded: thread_count={self.thread_message_count}, class={self.current_document_class}")
                        
                        # Set appropriate status based on document class
                        if self.current_document_class in ['response', 'product', 'processed_output']:
                            if self.thread_message_count > 0:
                                self.set_status(f"✅ Response loaded")
                            else:
                                self.set_status(f"✅ Response document loaded")
                        else:
                            self.set_status("✅ Source document loaded from library")
                        
                        # Auto-open viewer based on document type
                        # Use force_new_window if user chose side-by-side
                        # (capture force_new_viewer value at lambda creation time)
                        if self.thread_message_count > 0 and self.current_document_class in ['product', 'processed_output', 'response']:
                            # Has conversation - open in conversation mode
                            self.root.after(100, lambda fnw=force_new_viewer: self._show_thread_viewer(target_mode='conversation', force_new_window=fnw))
                        else:
                            # Source document - open in source mode
                            self.root.after(100, lambda fnw=force_new_viewer: self._show_thread_viewer(target_mode='source', force_new_window=fnw))
                    else:
                        messagebox.showerror("Error", "Could not load document entries")
            
            # Callback to add library documents as attachments for multi-document analysis
            def send_to_input_callback(doc_info_list: list):
                """Add selected library documents as attachments"""
                if not doc_info_list:
                    return
                
                from document_library import load_document_entries
                from utils import entries_to_text
                
                added_count = 0
                errors = []
                
                for doc_info in doc_info_list:
                    doc_id = doc_info.get('doc_id')
                    title = doc_info.get('title', 'Unknown')
                    
                    try:
                        # Load document content
                        entries = load_document_entries(doc_id)
                        if entries:
                            text = entries_to_text(entries)
                            if text and text.strip():
                                # Add as attachment
                                result = self.attachment_manager.add_from_library(doc_id, title, text)
                                if result.get('error'):
                                    errors.append(f"{title}: {result['error']}")
                                else:
                                    added_count += 1
                            else:
                                errors.append(f"{title}: No text content")
                        else:
                            errors.append(f"{title}: Could not load content")
                    except Exception as e:
                        errors.append(f"{title}: {str(e)}")
                
                # Update status
                if added_count > 0:
                    total = self.attachment_manager.get_attachment_count()
                    words = self.attachment_manager.get_total_words()
                    self.set_status(f"📎 Added {added_count} document(s) as attachments ({total} total, ~{words:,} words)")
                    
                    # Show confirmation
                    if errors:
                        messagebox.showinfo("Documents Added", 
                            f"Added {added_count} document(s) as attachments.\n\n"
                            f"Some documents had issues:\n" + "\n".join(f"• {e}" for e in errors[:5]))
                    else:
                        messagebox.showinfo("Documents Added", 
                            f"Added {added_count} document(s) as attachments.\n\n"
                            f"Total: {total} attachments (~{words:,} words)\n\n"
                            f"Now select a prompt and click 'Run' for multi-document analysis.")
                else:
                    messagebox.showwarning("No Documents Added", 
                        "Could not add any documents:\n\n" + "\n".join(f"• {e}" for e in errors[:5]))
            
            # Open the new tree-based Documents Library
            open_document_tree_manager(
                parent=self.root,
                library_path=LIBRARY_PATH,
                on_load_document=load_document_callback,
                on_send_to_input=send_to_input_callback,
                config=self.config
            )
            
        except ImportError as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"⚠️ ImportError opening Documents Library:")
            print(error_details)
            messagebox.showerror("Import Error", 
                f"Could not import Documents Library modules.\n\n"
                f"Error: {str(e)}\n\n"
                f"Files needed:\n"
                f"- document_tree_manager.py\n"
                f"- tree_manager_base.py\n\n"
                f"Check the console for full error details.")
        except Exception as e:
            import traceback
            print(f"❌ Error opening Documents Library: {e}")
            traceback.print_exc()
            messagebox.showerror("Error", f"Could not open Documents Library:\n\n{str(e)}")
    
