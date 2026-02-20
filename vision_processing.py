"""
vision_processing.py - Vision/image processing and document utility methods for DocAnalyser.

Handles multi-image OCR dialogs, reorder dialogs, vision API processing
(OpenAI, Anthropic, Google), PDF page vision, separate/combined results,
library refresh, document conversion, and AI output saving as product documents.

Extracted from Main.py to reduce file size. Uses a mixin pattern so all
self.xxx references continue to work unchanged.
"""

from __future__ import annotations

import os
import datetime
import json
import logging
import tkinter as tk
from tkinter import ttk, messagebox

from document_library import (
    add_document_to_library,
    get_document_by_id,
    convert_document_to_source,
    save_thread_to_document,
)


class VisionProcessingMixin:
    """Mixin class providing vision processing and document utility methods for DocAnalyzerApp."""

    def _show_multi_image_dialog(self, ocr_files):
        """Wrapper for backwards compatibility."""
        return self._show_multi_ocr_dialog(ocr_files)
    
    def _show_multi_ocr_dialog(self, ocr_files):
        """
        Show dialog for handling multiple files that need OCR (images or scanned PDFs).
        Returns: (action, use_vision, ordered_files) or (None, None, None) if cancelled.
        action: 'separate' or 'combine'
        use_vision: True to use AI vision model, False for standard OCR
        ordered_files: List of files in user-specified order (for combine)
        """
        import tkinter as tk
        from tkinter import ttk
        
        result = {'action': None, 'use_vision': False, 'files': ocr_files.copy()}
        
        dialog = tk.Toplevel(self.root)
        dialog.title("Multiple Files for OCR")
        # Will adjust height later if warning needed
        dialog.geometry("520x400")
        dialog.transient(self.root)
        dialog.grab_set()
        self.style_dialog(dialog)
        
        # Center the dialog
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - dialog.winfo_width()) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")
        
        # Count file types
        pdf_count = sum(1 for f in ocr_files if f.lower().endswith('.pdf'))
        img_count = len(ocr_files) - pdf_count
        
        if pdf_count > 0 and img_count > 0:
            header_text = f"{len(ocr_files)} files detected ({img_count} images, {pdf_count} PDFs)"
        elif pdf_count > 0:
            header_text = f"{pdf_count} scanned PDF{'s' if pdf_count > 1 else ''} detected"
        else:
            header_text = f"{img_count} image file{'s' if img_count > 1 else ''} detected"
        
        # Header
        ttk.Label(
            dialog, 
            text=header_text,
            font=('Arial', 11, 'bold')
        ).pack(pady=(15, 10))
        
        # Check confidence on first file (for auto-detection)
        self.set_status("🔍 Analyzing files...")
        dialog.update()
        first_file = ocr_files[0]
        
        # If PDF, extract first page as image for confidence check
        if first_file.lower().endswith('.pdf'):
            try:
                import tempfile
                from pdf2image import convert_from_path
                images = convert_from_path(first_file, first_page=1, last_page=1, dpi=150)
                if images:
                    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                        images[0].save(tmp.name, 'PNG')
                        confidence, likely_handwriting = self._check_ocr_confidence(tmp.name)
                        os.unlink(tmp.name)
                else:
                    confidence, likely_handwriting = 50, True
            except Exception as e:
                print(f"⚠️ PDF confidence check failed: {e}")
                confidence, likely_handwriting = 50, True
        else:
            confidence, likely_handwriting = self._check_ocr_confidence(first_file)
        
        self.set_status("Ready")
        
        # Action buttons frame
        action_frame = ttk.Frame(dialog)
        action_frame.pack(pady=10, padx=20, fill=tk.X)
        
        def check_vision_before_proceed():
            """Check if vision is selected but provider doesn't support it. Returns True if OK to proceed."""
            if vision_var.get():
                supported, provider = self._provider_supports_vision()
                if not supported:
                    messagebox.showwarning(
                        "⚠️ Vision AI Not Available",
                        f"Your current AI provider ({provider}) does not support "
                        f"vision/image processing needed for handwriting recognition.\n\n"
                        f"To proceed, please:\n\n"
                        f"  • Change 'AI Provider' in the main window to:\n"
                        f"      → OpenAI (uses GPT-4o) - Best for handwriting\n"
                        f"      → Anthropic (uses Claude)\n"
                        f"      → Google (uses Gemini)\n"
                        f"  • Make sure you have an API key entered\n"
                        f"  • Try loading the files again\n\n"
                        f"Or uncheck 'Contains handwriting' to use free local OCR\n"
                        f"(works for printed text only)."
                    )
                    return False  # Cannot proceed without vision support
            return True  # OK to proceed
        
        def on_separate():
            if not check_vision_before_proceed():
                return  # User cancelled
            result['action'] = 'separate'
            dialog.destroy()
        
        def on_combine():
            if not check_vision_before_proceed():
                return  # User cancelled
            result['action'] = 'combine'
            # Show reorder dialog
            ordered = self._show_reorder_dialog(dialog, ocr_files)
            if ordered:
                result['files'] = ordered
                dialog.destroy()
            # If cancelled, stay on this dialog
        
        sep_btn = ttk.Button(
            action_frame, 
            text="📄 Process as Separate Documents",
            command=on_separate,
            width=35
        )
        sep_btn.pack(pady=5)
        
        combine_btn = ttk.Button(
            action_frame,
            text="📑 Combine as Single Document",
            command=on_combine,
            width=35
        )
        combine_btn.pack(pady=5)
        
        # Check if current provider supports vision
        vision_supported, current_provider = self._provider_supports_vision()
        
        # If handwriting detected but vision not supported, show prominent warning
        if likely_handwriting and not vision_supported:
            # Make dialog taller to fit warning
            dialog.geometry("520x580")
            
            # Create a prominent warning frame
            warning_frame = ttk.LabelFrame(dialog, text="⚠️ Vision AI Required for Handwriting", padding=10)
            warning_frame.pack(pady=(10, 5), padx=20, fill=tk.X)
            
            # Warning icon and message
            warning_msg = tk.Text(warning_frame, wrap=tk.WORD, height=9, width=50, 
                                 font=('Arial', 9), bg='#FFF3CD', relief=tk.FLAT)
            warning_msg.pack(fill=tk.X)
            warning_msg.insert('1.0', 
                f"These files appear to contain handwriting.\n\n"
                f"Your current AI provider ({current_provider}) does not support vision/image processing.\n\n"
                f"To transcribe handwriting, please:\n"
                f"1. Close this dialog\n"
                f"2. Change AI Provider (dropdown in main window) to:\n"
                f"   • OpenAI (uses GPT-4o) ← Recommended\n"
                f"   • Anthropic (uses Claude)\n"
                f"   • Google (uses Gemini)\n"
                f"3. Ensure you have an API key for that provider\n"
                f"4. Try loading the files again\n\n"
                f"Or uncheck 'Contains handwriting' below to use local OCR\n"
                f"(works for printed text only, not handwriting)."
            )
            warning_msg.config(state=tk.DISABLED)
            
            # Re-center dialog after resize
            dialog.update_idletasks()
            x = self.root.winfo_x() + (self.root.winfo_width() - 520) // 2
            y = self.root.winfo_y() + (self.root.winfo_height() - 580) // 2
            dialog.geometry(f"520x580+{x}+{y}")
        
        # Handwriting checkbox
        # If vision not supported, don't auto-check handwriting
        initial_vision = likely_handwriting if vision_supported else False
        vision_var = tk.BooleanVar(value=initial_vision)
        
        checkbox_frame = ttk.Frame(dialog)
        checkbox_frame.pack(pady=(15, 5), padx=20, fill=tk.X)
        
        vision_cb = ttk.Checkbutton(
            checkbox_frame,
            text="Contains handwriting (use AI vision)",
            variable=vision_var
        )
        vision_cb.pack(anchor=tk.W)
        
        # Function to check vision support when checkbox is toggled
        def on_vision_checkbox_change(*args):
            if vision_var.get() and not vision_supported:
                # User tried to check the box but vision not supported
                vision_var.set(False)  # Uncheck it
                messagebox.showwarning(
                    "Vision AI Required",
                    f"Your current AI provider ({current_provider}) does not support vision.\n\n"
                    f"To use handwriting recognition:\n\n"
                    f"1. Change AI Provider to:\n"
                    f"   • OpenAI (recommended)\n"
                    f"   • Anthropic\n"
                    f"   • Google\n\n"
                    f"2. Make sure you have an API key for that provider.\n\n"
                    f"3. Try again."
                )
        
        vision_var.trace_add('write', on_vision_checkbox_change)
        
        # Auto-detection hint or vision warning
        if not vision_supported:
            # Show warning that current provider doesn't support vision
            hint_text = f"⚠️ {current_provider} doesn't support vision - switch provider for handwriting"
            hint_color = '#CC0000'  # Red warning color
        elif likely_handwriting:
            hint_text = "✅ Vision AI available - uncheck if printed text only"
            hint_color = '#006600'  # Green
        else:
            hint_text = "ℹ️ Check this box if images contain handwriting"
            hint_color = '#666666'
        
        hint_label = ttk.Label(
            checkbox_frame,
            text=hint_text,
            font=('Arial', 9, 'bold' if not vision_supported else 'normal'),
            foreground=hint_color,
            wraplength=400
        )
        hint_label.pack(anchor=tk.W, padx=(20, 0))
        
        # Show current provider info
        provider_info = ttk.Label(
            checkbox_frame,
            text=f"Current provider: {current_provider}",
            font=('Arial', 8),
            foreground='#888888'
        )
        provider_info.pack(anchor=tk.W, padx=(20, 0), pady=(5, 0))
        
        # Settings hint (italic, gray)
        threshold = self.config.get("ocr_confidence_threshold", 70)
        hint_line1 = f"AI vision used if OCR accuracy falls below {threshold}%."
        hint_line2 = "To adjust threshold, go to Settings → OCR Settings."
        settings_hint = ttk.Label(
            dialog,
            text=hint_line1 + "\n" + hint_line2,
            font=('Arial', 8, 'italic'),
            foreground='#888888',
            justify=tk.LEFT
        )
        settings_hint.pack(pady=(10, 5), padx=20, anchor=tk.W)
        
        # Cancel button
        ttk.Button(
            dialog,
            text="Cancel",
            command=dialog.destroy,
            width=15
        ).pack(pady=15)
        
        # Wait for dialog
        dialog.wait_window()
        
        result['use_vision'] = vision_var.get()
        
        if result['action']:
            return result['action'], result['use_vision'], result['files']
        return None, None, None
    
    def _show_reorder_dialog(self, parent, files):
        """
        Show dialog to reorder files before combining.
        Returns ordered list or None if cancelled.
        """
        import tkinter as tk
        from tkinter import ttk
        
        result = {'files': None}
        
        dialog = tk.Toplevel(parent)
        dialog.title("Arrange Pages")
        dialog.geometry("450x400")
        dialog.transient(parent)
        dialog.grab_set()
        self.style_dialog(dialog)
        
        # Center
        dialog.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - dialog.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")
        
        ttk.Label(
            dialog,
            text="Arrange pages in order:",
            font=('Arial', 10, 'bold')
        ).pack(pady=(15, 10))
        
        # Listbox with scrollbar
        list_frame = ttk.Frame(dialog)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)
        
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        listbox = tk.Listbox(
            list_frame,
            yscrollcommand=scrollbar.set,
            font=('Arial', 10),
            selectmode=tk.SINGLE,
            height=10
        )
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=listbox.yview)
        
        # Populate with filenames
        file_list = list(files)
        for i, f in enumerate(file_list):
            listbox.insert(tk.END, f"{i+1}. {os.path.basename(f)}")
        
        # Move buttons
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)
        
        def move_up():
            sel = listbox.curselection()
            if sel and sel[0] > 0:
                idx = sel[0]
                # Swap in list
                file_list[idx], file_list[idx-1] = file_list[idx-1], file_list[idx]
                # Update listbox
                listbox.delete(0, tk.END)
                for i, f in enumerate(file_list):
                    listbox.insert(tk.END, f"{i+1}. {os.path.basename(f)}")
                listbox.selection_set(idx-1)
        
        def move_down():
            sel = listbox.curselection()
            if sel and sel[0] < len(file_list) - 1:
                idx = sel[0]
                # Swap in list
                file_list[idx], file_list[idx+1] = file_list[idx+1], file_list[idx]
                # Update listbox
                listbox.delete(0, tk.END)
                for i, f in enumerate(file_list):
                    listbox.insert(tk.END, f"{i+1}. {os.path.basename(f)}")
                listbox.selection_set(idx+1)
        
        ttk.Button(btn_frame, text="↑ Move Up", command=move_up, width=12).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="↓ Move Down", command=move_down, width=12).pack(side=tk.LEFT, padx=5)
        
        # Bottom buttons
        bottom_frame = ttk.Frame(dialog)
        bottom_frame.pack(pady=15)
        
        def on_process():
            result['files'] = file_list
            dialog.destroy()
        
        def on_back():
            dialog.destroy()
        
        ttk.Button(bottom_frame, text="Process", command=on_process, width=12).pack(side=tk.LEFT, padx=5)
        ttk.Button(bottom_frame, text="Back", command=on_back, width=12).pack(side=tk.LEFT, padx=5)
        
        dialog.wait_window()
        return result['files']
    
    def _process_images_with_vision(self, ocr_files, combine=True):
        """
        Process image files and PDFs using AI vision model DIRECTLY.
        This method is called when user selects "Contains handwriting" checkbox.
        Bypasses ocr_image_smart and uses direct vision API calls.
        """
        if not ocr_files:
            return
        
        print(f"\n{'='*60}")
        print(f"🚀 _process_images_with_vision started")
        print(f"   Files: {len(ocr_files)}")
        print(f"   Combine: {combine}")
        print(f"{'='*60}\n")
        
        self.set_status("🤖 Processing with AI vision...")
        
        all_text = []
        entries = []
        all_source_files = []
        
        try:
            for i, file_path in enumerate(ocr_files):
                print(f"\n📄 Processing file {i+1}/{len(ocr_files)}: {os.path.basename(file_path)}")
                self.set_status(f"🤖 Processing file {i+1}/{len(ocr_files)} with AI vision...")
                
                try:
                    # Check if it's a PDF
                    if file_path.lower().endswith('.pdf'):
                        # Process PDF pages directly with vision API (NOT through ocr_image_smart)
                        pdf_entries = self._process_pdf_pages_direct_vision(file_path)
                        if pdf_entries:
                            print(f"   ✅ Got {len(pdf_entries)} entries from PDF")
                            for entry in pdf_entries:
                                entries.append({
                                    'start': len(entries),
                                    'text': entry.get('text', ''),
                                    'location': f"{os.path.basename(file_path)} - {entry.get('location', 'Page')}"
                                })
                            all_source_files.append(file_path)
                        else:
                            print(f"   ⚠️ No text extracted from PDF: {file_path}")
                    else:
                        # Use vision API for images
                        text = self._process_single_image_with_vision(file_path)
                        if text:
                            print(f"   ✅ Got {len(text)} characters from image")
                            all_text.append(text)
                            entries.append({
                                'start': len(entries),
                                'text': text,
                                'location': os.path.basename(file_path)
                            })
                            all_source_files.append(file_path)
                except Exception as e:
                    import traceback
                    print(f"   ❌ Vision processing failed for {file_path}: {e}")
                    traceback.print_exc()
        except Exception as e:
            import traceback
            print(f"❌ Batch processing error: {e}")
            traceback.print_exc()
        
        print(f"\n{'='*60}")
        print(f"📊 Processing complete:")
        print(f"   Total entries: {len(entries)}")
        print(f"   Total source files: {len(all_source_files)}")
        print(f"   Combine mode: {combine}")
        print(f"{'='*60}\n")
        
        if not entries:
            self.set_status("❌ No text extracted from any files")
            self.root.after(0, lambda: messagebox.showerror("OCR Error", "Failed to extract text from the files. Check console for details."))
            self.processing = False
            return
        
        if combine:
            print("📚 Calling _handle_multi_image_ocr_result to create COMBINED document...")
            # Handle as single combined document
            self._handle_multi_image_ocr_result(entries, all_source_files if all_source_files else ocr_files)
        else:
            print("📂 Calling _save_separate_vision_results to create SEPARATE documents...")
            # Process each separately - save each file's entries as a document
            self._save_separate_vision_results(entries, ocr_files)
        
        # Reset processing flag
        self.processing = False
    
    def _process_pdf_pages_direct_vision(self, pdf_path):
        """
        Process all pages of a PDF directly through vision API.
        Returns list of entries with text and location.
        """
        from pdf2image import convert_from_path
        import tempfile
        import base64
        
        provider = self.provider_var.get()
        model = self.model_var.get()
        api_key = self.api_key_var.get()
        
        if not api_key:
            print(f"⚠️ No API key for vision processing")
            return None
        
        try:
            self.set_status(f"📄 Converting PDF to images...")
            # Use higher DPI for better quality
            images = convert_from_path(pdf_path, dpi=300)
            total_pages = len(images)
            print(f"📄 PDF has {total_pages} pages")
            
            entries = []
            
            for page_num, image in enumerate(images, start=1):
                self.set_status(f"🤖 Vision processing page {page_num}/{total_pages}...")
                print(f"🤖 Processing page {page_num}...")
                
                # Save to temp file with high quality
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                    # Use PNG for better quality (no JPEG compression artifacts)
                    if image.mode in ('RGBA', 'P', 'LA'):
                        image = image.convert('RGB')
                    image.save(tmp.name, 'PNG')
                    tmp_path = tmp.name
                
                try:
                    # Read and encode
                    with open(tmp_path, 'rb') as f:
                        image_data = base64.b64encode(f.read()).decode('utf-8')
                    
                    # Better prompt that encourages full transcription
                    prompt = (
                        "This image contains a handwritten letter or document. "
                        "Your task is to transcribe EVERY word of handwritten text visible in this image. "
                        "Even if the handwriting is difficult to read, provide your best interpretation of each word. "
                        "DO NOT skip any text. DO NOT say 'illegible' - always give your best guess. "
                        "Preserve the original paragraph structure and line breaks. "
                        "Include ALL text from the beginning to the end of the page. "
                        "Output ONLY the transcribed text, nothing else."
                    )
                    
                    # Call appropriate vision API
                    text = None
                    try:
                        if "OpenAI" in provider or "ChatGPT" in provider:
                            text = self._vision_openai(api_key, model, image_data, 'image/png', prompt)
                        elif "Anthropic" in provider or "Claude" in provider:
                            text = self._vision_anthropic(api_key, model, image_data, 'image/png', prompt)
                        elif "Google" in provider or "Gemini" in provider:
                            text = self._vision_google(api_key, model, image_data, 'image/png', prompt)
                        else:
                            print(f"⚠️ Vision not supported for provider: {provider}")
                    except Exception as e:
                        print(f"⚠️ Vision API error on page {page_num}: {e}")
                        import traceback
                        traceback.print_exc()
                    
                    if text and text.strip():
                        print(f"✅ Page {page_num}: Got {len(text)} characters")
                        entries.append({
                            'text': text.strip(),
                            'location': f'Page {page_num}'
                        })
                    else:
                        print(f"⚠️ Page {page_num}: No text returned")
                finally:
                    try:
                        os.unlink(tmp_path)
                    except:
                        pass
            
            self.set_status(f"✅ Processed {total_pages} pages")
            print(f"📊 Total entries: {len(entries)}")
            return entries if entries else None
            
        except Exception as e:
            print(f"⚠️ PDF vision processing error: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _save_separate_vision_results(self, entries, ocr_files):
        """Save vision results as separate documents for each source file."""
        # Group entries by source file
        file_entries = {}
        for entry in entries:
            location = entry.get('location', '')
            # Extract filename from location
            for f in ocr_files:
                basename = os.path.basename(f)
                if basename in location:
                    if f not in file_entries:
                        file_entries[f] = []
                    file_entries[f].append(entry)
                    break
        
        # Save each file's entries
        for file_path, file_entry_list in file_entries.items():
            if file_entry_list:
                # Combine text from all entries for this file
                combined_text = "\n\n".join([e.get('text', '') for e in file_entry_list])
                if combined_text.strip():
                    self._save_single_ocr_result(file_path, combined_text)
        
        self.set_status(f"✅ Processed {len(file_entries)} files separately")
        self.refresh_library()
    
    def _process_single_image_with_vision(self, image_path):
        """Process a single image with AI vision model."""
        import base64
        
        # Get current provider and model
        provider = self.provider_var.get()
        model = self.model_var.get()
        api_key = self.api_key_var.get()
        
        if not api_key:
            self.root.after(0, lambda: messagebox.showerror("API Key Required", 
                "AI vision requires an API key.\nPlease configure in Settings."))
            return None
        
        # Read and encode image
        with open(image_path, 'rb') as f:
            image_data = base64.b64encode(f.read()).decode('utf-8')
        
        # Determine mime type
        ext = os.path.splitext(image_path)[1].lower()
        mime_types = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
            '.tif': 'image/tiff',
            '.tiff': 'image/tiff',
            '.bmp': 'image/bmp'
        }
        mime_type = mime_types.get(ext, 'image/jpeg')
        
        prompt = (
            "Extract ALL text from this image, preserving the original layout, "
            "paragraphs, and formatting as much as possible. "
            "This may contain handwritten text - please transcribe it accurately. "
            "Return only the extracted text, no explanations."
        )
        
        try:
            if "OpenAI" in provider or "ChatGPT" in provider:
                return self._vision_openai(api_key, model, image_data, mime_type, prompt)
            elif "Anthropic" in provider or "Claude" in provider:
                return self._vision_anthropic(api_key, model, image_data, mime_type, prompt)
            elif "Google" in provider or "Gemini" in provider:
                return self._vision_google(api_key, model, image_data, mime_type, prompt)
            else:
                self.root.after(0, lambda: messagebox.showwarning("Vision Not Supported",
                    f"Vision/OCR not supported for {provider}.\n"
                    "Please use OpenAI, Anthropic, or Google."))
                return None
        except Exception as e:
            print(f"Vision API error: {e}")
            return None
    
    def _provider_supports_vision(self, provider=None):
        """Check if a provider supports vision/image processing.
        
        Args:
            provider: Provider name to check. If None, uses current provider.
            
        Returns:
            tuple: (supports_vision: bool, provider_name: str)
        """
        if provider is None:
            provider = self.provider_var.get()
        
        # Providers that support vision API
        vision_providers = ['OpenAI', 'Anthropic', 'Google']
        
        supports = any(vp in provider for vp in vision_providers)
        return supports, provider
    
    def _vision_openai(self, api_key, model, image_data, mime_type, prompt):
        """Call OpenAI vision API."""
        import requests
        
        # Use gpt-4o for vision if model is old/non-vision capable
        # GPT-4o, GPT-4.5, GPT-5+ all support vision natively
        if not any(x in model.lower() for x in ['gpt-4o', 'gpt-4.5', 'gpt-5', 'vision', 'o1', 'o3', 'o4']):
            model = 'gpt-4o'
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # Newer OpenAI models (gpt-5.x, o1, o3, o4) require max_completion_tokens
        uses_new_param = any(x in model.lower() for x in ['gpt-5', 'o1', 'o3', 'o4'])
        
        payload = {
            "model": model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {
                        "url": f"data:{mime_type};base64,{image_data}"
                    }}
                ]
            }],
        }
        if uses_new_param:
            payload["max_completion_tokens"] = 4096
        else:
            payload["max_tokens"] = 4096
        
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=120
        )
        response.raise_for_status()
        return response.json()['choices'][0]['message']['content']
    
    def _vision_anthropic(self, api_key, model, image_data, mime_type, prompt):
        """Call Anthropic vision API."""
        import requests
        
        headers = {
            "x-api-key": api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01"
        }
        
        payload = {
            "model": model if 'claude' in model.lower() else "claude-3-5-sonnet-20241022",
            "max_tokens": 4096,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image", "source": {
                        "type": "base64",
                        "media_type": mime_type,
                        "data": image_data
                    }},
                    {"type": "text", "text": prompt}
                ]
            }]
        }
        
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=payload,
            timeout=120
        )
        response.raise_for_status()
        return response.json()['content'][0]['text']
    
    def _vision_google(self, api_key, model, image_data, mime_type, prompt):
        """Call Google Gemini vision API."""
        import requests
        
        model_name = model if 'gemini' in model.lower() else "gemini-1.5-flash"
        
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        
        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {"inline_data": {
                        "mime_type": mime_type,
                        "data": image_data
                    }}
                ]
            }]
        }
        
        response = requests.post(url, json=payload, timeout=120)
        response.raise_for_status()
        return response.json()['candidates'][0]['content']['parts'][0]['text']
    
    def _save_single_ocr_result(self, image_path, text):
        """Save a single OCR result to the library."""
        import datetime
        
        title = os.path.splitext(os.path.basename(image_path))[0]
        entries = [{'start': 0, 'text': text, 'location': 'Page 1'}]
        
        doc_id = add_document_to_library(
            doc_type="ocr",
            source=image_path,
            title=title,
            entries=entries,
            document_class="source",
            metadata={"source_file": os.path.basename(image_path)}
        )
        return doc_id


    def refresh_library(self):
        """Refresh is no longer needed - library opens fresh each time"""
        pass

    def convert_to_source_document(self):
        """Convert product document to read-only source"""
        if not self.current_document_id:
            messagebox.showerror("Error", "No document loaded")
            return
        
        response = messagebox.askyesno(
            "Convert to Source Document",
            "Convert this product document to a source document?\n\n"
            "This will:\n"
            "• Make it permanently read-only\n"
            "• Mark it as a source document\n"
            "• Cannot be undone\n\n"
            "Continue?"
        )
        
        if response:
            success = convert_document_to_source(self.current_document_id)
            
            if success:
                # Update local state
                self.current_document_class = "source"
                self.current_document_metadata["editable"] = False
                
                # Close editing window
                if hasattr(self, '_editing_window'):
                    self._editing_window.destroy()
                
                messagebox.showinfo(
                    "Converted",
                    "✅ Document is now a read-only source document"
                )
            else:
                messagebox.showerror("Error", "Failed to convert document")

    def save_ai_output_as_product_document(self, output_text: str):
        """Save AI output as new editable product document"""
        
        # ============================================================
        # CHECK FOR PRE-CREATED DOCUMENT (from Thread Viewer branch creation)
        # If the document was pre-created by ThreadViewer, just save the
        # thread content without creating a duplicate document.
        # ============================================================
        print(f"\n{'='*60}")
        print(f"💾 SAVE_AI_OUTPUT_AS_PRODUCT_DOCUMENT CALLED")
        print(f"   current_document_id: {self.current_document_id}")
        print(f"   thread message count: {len(self.current_thread) if hasattr(self, 'current_thread') else 0}")
        print(f"   has metadata attr: {hasattr(self, 'current_document_metadata')}")
        if hasattr(self, 'current_document_metadata') and self.current_document_metadata:
            print(f"   metadata keys: {list(self.current_document_metadata.keys())}")
            print(f"   pre_created flag: {self.current_document_metadata.get('pre_created', 'NOT SET')}")
        print(f"{'='*60}")
        
        if hasattr(self, 'current_document_metadata') and self.current_document_metadata:
            if self.current_document_metadata.get('pre_created'):
                print(f"🔔 Pre-created document detected, saving thread only")
                print(f"   SAVING TO: {self.current_document_id}")
                # Just save the thread to the existing document
                if self.current_document_id and self.current_thread:
                    from document_library import save_thread_to_document
                    thread_metadata = {
                        "model": self.model_var.get(),
                        "provider": self.provider_var.get(),
                        "last_updated": datetime.datetime.now().isoformat(),
                        "message_count": self.thread_message_count
                    }
                    save_thread_to_document(self.current_document_id, self.current_thread, thread_metadata)
                    print(f"   ✓ Thread saved to pre-created document: {self.current_document_id}")
                # Clear the pre_created flag so subsequent saves work normally
                self.current_document_metadata['pre_created'] = False
                return self.current_document_id

        # Get processing info
        prompt_name = self.prompt_combo.get() if self.prompt_combo.get() else "Custom Prompt"
        provider = self.provider_var.get()
        model = self.model_var.get()

        # Determine if we have a source document
        has_source = bool(self.current_document_id)

        if has_source:
            # Get original document
            original_doc = get_document_by_id(self.current_document_id)
            if not original_doc:
                messagebox.showerror("Error", "Source document not found")
                return

            # Create title with source
            title = f"[Response] {prompt_name}: {original_doc['title']}"
            source_info = f"AI analysis of: {self.current_document_source}"

            metadata = {
                "parent_document_id": self.current_document_id,
                "parent_title": original_doc['title'],
                "prompt_name": prompt_name,
                "prompt_text": self.prompt_text.get('1.0', tk.END).strip(),
                "ai_provider": provider,
                "ai_model": model,
                "created": datetime.datetime.now().isoformat(),
                "editable": True
            }
        else:
            # General chat without source document
            timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
            title = f"[Response] {prompt_name} - {timestamp}"
            source_info = f"AI Chat - {provider} - {model}"

            metadata = {
                "prompt_name": prompt_name,
                "prompt_text": self.prompt_text.get('1.0', tk.END).strip(),
                "ai_provider": provider,
                "ai_model": model,
                "created": datetime.datetime.now().isoformat(),
                "editable": True,
                "general_chat": True
            }

        # Convert to entries (split into paragraphs for better structure)
        paragraphs = [p.strip() for p in output_text.split('\n\n') if p.strip()]
        if not paragraphs:
            entries = [{"text": output_text, "location": "AI Generated"}]
        else:
            entries = [{"text": para, "location": f"Paragraph {i + 1}"} for i, para in enumerate(paragraphs)]

        # Add as response document (using "response" class for consistency)
        doc_id = add_document_to_library(
            doc_type="ai_response",
            document_class="response",  # Changed from "product" to "response"
            source=source_info,
            title=title,
            entries=entries,
            metadata=metadata
        )

        if doc_id:
            # ===== NEW: SAVE CONVERSATION THREAD =====
            # This enables the 💬 icon and thread viewing!
            if hasattr(self, 'current_thread') and self.current_thread:
                try:
                    from document_library import save_thread_to_document

                    thread_metadata = {
                        'model': model,
                        'provider': provider,
                        'last_updated': datetime.datetime.now().isoformat(),
                        'message_count': len([m for m in self.current_thread if m.get('role') == 'user'])
                    }

                    save_thread_to_document(doc_id, self.current_thread, thread_metadata)
                    print(f"✅ Saved conversation thread ({thread_metadata['message_count']} messages)")
                except Exception as e:
                    print(f"⚠️ Failed to save thread: {e}")
            # ===== END NEW CODE =====

            # Status message instead of popup (Thread Viewer opens automatically)
            self.set_status(f"✅ Response saved: {title[:50]}..." if len(title) > 50 else f"✅ Response saved: {title}")
            print(f"✅ Response document created: {title}")

            # Refresh library display if open
            if hasattr(self, 'refresh_library'):
                self.refresh_library()

            return doc_id
        else:
            messagebox.showerror("Error", "Failed to create response document")
            return None

