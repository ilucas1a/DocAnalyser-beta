"""
smart_load.py - Smart loading, URL routing, and multi-document handling for DocAnalyser.

Handles smart_load auto-detection, URL validation, multi-input processing,
multi-document dialog, combined document analysis, batch processing,
YouTube/Substack/Twitter URL detection, Google Drive file handling,
and OCR confidence checking.

Extracted from Main.py to reduce file size. Uses a mixin pattern so all
self.xxx references continue to work unchanged.
"""

from __future__ import annotations

import os
import re
import datetime
import logging
import threading
import time
import tempfile
import tkinter as tk
from tkinter import ttk, messagebox

from document_library import add_document_to_library, get_document_by_id
from utils import entries_to_text, entries_to_text_with_speakers

# Substack availability flag
try:
    from substack_utils import is_substack_url
    SUBSTACK_AVAILABLE = True
except ImportError:
    SUBSTACK_AVAILABLE = False

# Twitter support flag
try:
    from twitter_utils import is_twitter_url
    TWITTER_SUPPORT = True
except ImportError:
    TWITTER_SUPPORT = False

# Facebook support flag
try:
    from facebook_utils import is_facebook_video_url
    FACEBOOK_SUPPORT = True
except ImportError:
    FACEBOOK_SUPPORT = False

# Lazy module loaders (mirrors Main.py pattern)
def get_ocr():
    import ocr_handler
    return ocr_handler

def get_doc_fetcher():
    import document_fetcher
    return document_fetcher


class SmartLoadMixin:
    """Mixin class providing smart loading and URL routing methods for DocAnalyzerApp."""

    def smart_load(self):
        """
        Smart loader that auto-detects input type...
        """
        # Reset Load button highlight immediately
        if hasattr(self, 'load_btn'):
            self.load_btn.configure(style='TButton')
            self.root.update_idletasks()  # Force immediate UI update
        
        print("=" * 60)
        print("🚀 DEBUG smart_load() ENTRY")
        print(f"   universal_input_var='{self.universal_input_var.get()}'")
        print(f"   processing={self.processing}")

        if self.processing:
            print("⚠️ Already processing, showing warning")
            messagebox.showwarning("Warning", "Processing already in progress. Please wait or cancel.")
            return
        print("✅ Not currently processing")

        # Read from Text widget (supports multiple lines)
        try:
            raw_input = self.universal_input_entry.get('1.0', 'end-1c').strip()
        except:
            raw_input = self.universal_input_var.get().strip()
        
        # Split into lines and filter empty ones
        input_lines = [line.strip() for line in raw_input.split('\n') if line.strip()]
        
        # If multiple lines, process them as batch
        if len(input_lines) > 1:
            print(f"📝 Multiple inputs detected: {len(input_lines)} items")
            self._process_multiple_inputs(input_lines)
            return
        
        # Single line - process normally
        input_value = input_lines[0] if input_lines else ''
        print(f"📝 Input value from Text widget: '{input_value}'")
        print(f"📝 StringVar value: '{self.universal_input_var.get()}'")
        print(f"📝 Placeholder active: {getattr(self, 'placeholder_active', 'N/A')}")
        
        # Skip if it's placeholder text
        if hasattr(self, 'placeholder_active') and self.placeholder_active:
            print("⚠️ Placeholder is active, ignoring")
            messagebox.showwarning("Empty Input", "Please enter a URL or select a file.")
            return
        
        if not input_value:
            print("❌ Empty input")
            messagebox.showwarning("Empty Input", "Please enter a URL or select a file.")
            return
        
        # Check for active conversation thread before loading new document
        # Extract a title preview from input for the dialog
        if input_value.startswith('http'):
            new_doc_preview = input_value[:60] + "..." if len(input_value) > 60 else input_value
        else:
            # File path - use filename
            import os
            new_doc_preview = os.path.basename(input_value)
        
        if not self.check_active_thread_before_load(new_doc_preview):
            print("❌ User cancelled loading due to active thread")
            return

        # Clear preview immediately so user knows something is happening
        self.clear_preview_for_new_document()
        
        # ============================================
        # AUTO-DETECTION LOGIC
        # ============================================

        # 1. CHECK FOR YOUTUBE
        is_youtube = self.is_youtube_url(input_value)
        print(f"🎬 Is YouTube URL? {is_youtube}")

        if is_youtube:
            print(f"✅ Detected as YouTube, setting yt_url_var and calling fetch_youtube()")
            self.yt_url_var.set(input_value)
            print(f"   yt_url_var now contains: '{self.yt_url_var.get()}'")
            self.fetch_youtube()
            print("   fetch_youtube() called")
            return

        # 2. CHECK FOR SUBSTACK
        print(f"🔍 Checking Substack... SUBSTACK_AVAILABLE={SUBSTACK_AVAILABLE}")
        if SUBSTACK_AVAILABLE:
            from substack_utils import is_substack_url
            is_sub = is_substack_url(input_value)
            print(f"🔍 is_substack_url returned: {is_sub}")
            if is_sub:
                print(f"✅ Detected as Substack, fetching transcript")
                self.fetch_substack()
                return
        else:
            # If substack_utils not available, check pattern manually
            if 'substack.com' in input_value.lower():
                print(f"⚠️ Substack URL detected but substack_utils not available")
                messagebox.showinfo("Substack Support",
                                    "This appears to be a Substack URL.\n\n"
                                    "To enable Substack transcript scraping:\n"
                                    "1. Install: pip install beautifulsoup4\n"
                                    "2. Add substack_utils.py to project folder\n"
                                    "3. Restart DocAnalyser")
        
        # 2.4 CHECK FOR VIDEO PLATFORMS (Vimeo, Rumble, etc.)
        from video_platform_utils import is_video_platform_url
        if is_video_platform_url(input_value):
            print(f"🎬 Detected: Video Platform URL")
            self.fetch_video_platform(input_value)
            return
        
        # 2.5 CHECK FOR FACEBOOK VIDEO/REEL
        if FACEBOOK_SUPPORT and is_facebook_video_url(input_value):
            print("📘 Detected: Facebook Video/Reel")
            self.fetch_facebook(input_value)
            return
        
        # 2.6 CHECK FOR TWITTER/X POST
        if TWITTER_SUPPORT and is_twitter_url(input_value):
            print("🐦 Detected: Twitter/X Post")
            self.fetch_twitter(input_value)
            return
        
        # 2.7 CHECK FOR GOOGLE DRIVE FILE
        # 2.7a CHECK FOR GOOGLE DRIVE FOLDER (can't process directly)
        if self._is_google_drive_folder_url(input_value):
            print("📁 Detected: Google Drive FOLDER URL (not a file)")
            messagebox.showinfo(
                "Google Drive Folder",
                "This is a Google Drive folder link, not a file link.\n\n"
                "To load a specific file from this folder:\n\n"
                "Option 1: Right-click the file in Google Drive, then\n"
                "select Share > Copy link, and paste that link here.\n\n"
                "Option 2: Download the file to your computer,\n"
                "then drag it into DocAnalyser or use Browse."
            )
            self.set_status("Google Drive folder detected - need a direct file link")
            return
        
        if self._is_google_drive_file_url(input_value):
            print("📁 Detected: Google Drive file URL")
            self._fetch_google_drive_file(input_value)
            return
        
        # 3. CHECK FOR WEB URL
        if input_value.startswith('http://') or input_value.startswith('https://'):
            print("🌐 Detected: Web URL")
            self.web_url_var.set(input_value)
            self.fetch_web()
            return
        
        # 4. CHECK FOR LOCAL FILE
        # Try os.path.exists first, then fallback with normpath for Unicode edge cases
        resolved_path = input_value
        if not os.path.exists(resolved_path):
            # Try normalising the path (fixes forward slashes and some Unicode issues)
            resolved_path = os.path.normpath(input_value)
        if not os.path.exists(resolved_path):
            # Last resort: if it looks like a file path, try pathlib (handles Unicode better on Windows)
            try:
                import pathlib
                p = pathlib.Path(input_value)
                if p.exists():
                    resolved_path = str(p)
            except Exception:
                pass
        if os.path.exists(resolved_path):
            print(f"📁 Detected: Local file ({os.path.splitext(resolved_path)[1]})")
            self.file_path_var.set(resolved_path)
            print(f"📁 DEBUG: Calling fetch_local_file() for: {resolved_path}")
            self.fetch_local_file()
            print("📁 DEBUG: fetch_local_file() returned")
            return
        
        # 5. CHECK IF IT'S A YOUTUBE ID (no URL, just ID)
        if self.could_be_youtube_id(input_value):
            print("🎬 Detected: Possible YouTube video ID")
            response = messagebox.askyesno(
                "YouTube Video ID?",
                f"'{input_value}' looks like it might be a YouTube video ID.\n\n"
                "Try loading it as a YouTube video?"
            )
            if response:
                self.yt_url_var.set(input_value)
                self.fetch_youtube()
                return
        
        # 6. COULDN'T DETECT - SHOW HELPFUL ERROR
        # Add diagnostic info for file path issues
        extra_info = ""
        if ':' in input_value or input_value.startswith('/'):
            # Looks like a file path that wasn't found
            extra_info = (
                f"\n\nos.path.exists returned False."
                f"\nPath length: {len(input_value)} chars"
                f"\nTip: If the filename has special characters "
                f"(like \u2022 or accented letters), try using the Browse "
                f"button instead of pasting the path."
            )
        messagebox.showerror(
            "Could Not Detect Input Type",
            f"Unable to process: {input_value}\n\n"
            "Please check that:\n"
            "• URLs start with http:// or https://\n"
            "• File paths are correct and the file exists\n"
            "• YouTube URLs are complete\n\n"
            "Use the Browse button to select local files."
            + extra_info
        )

    def process_url_or_id(self):  # or whatever the method is called
        input_value = self.universal_input_var.get().strip()
        print(f"\n{'=' * 60}")
        print(f"🔍 STARTING URL PROCESSING")
        print(f"Input value: {input_value}")
        print(f"SUBSTACK_AVAILABLE: {SUBSTACK_AVAILABLE}")
        print(f"{'=' * 60}\n")

    def _process_multiple_inputs(self, input_lines):
        """Process multiple files/URLs from multi-line input."""
        print(f"🔄 Processing {len(input_lines)} inputs...")
        
        # Check if items need OCR (images or scanned PDFs)
        ocr_files = []
        for f in input_lines:
            if os.path.exists(f):
                ext = os.path.splitext(f)[1].lower()
                if ext in ('.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp', '.gif', '.webp'):
                    ocr_files.append(f)
                elif ext == '.pdf':
                    try:
                        if get_ocr().is_pdf_scanned(f):
                            ocr_files.append(f)
                    except:
                        pass
        
        if len(ocr_files) == len(input_lines) and len(ocr_files) > 1:
            # All items need OCR - show special handling dialog
            print(f"📷 All {len(ocr_files)} items need OCR - showing dialog")
            action, use_vision, ordered_files = self._show_multi_ocr_dialog(ocr_files)
            
            if action is None:
                # Cancelled
                return
            
            # Process in background thread to avoid UI freeze
            def process_thread():
                try:
                    if action == 'combine':
                        # Combine into single document
                        if use_vision:
                            self._process_images_with_vision(ordered_files, combine=True)
                        else:
                            # Use standard OCR and combine
                            self._process_images_standard_ocr(ordered_files, combine=True)
                    else:
                        # Process separately
                        if use_vision:
                            self._process_images_with_vision(ordered_files, combine=False)
                        else:
                            self._process_images_standard_ocr(ordered_files, combine=False)
                except Exception as e:
                    import traceback
                    tb_str = traceback.format_exc()
                    print(f"❌ Multi-file processing error: {e}")
                    print(tb_str)
                    self.root.after(0, lambda: self.set_status(f"❌ Processing failed: {str(e)}"))
                    # Show traceback in error dialog so we can diagnose the issue
                    error_detail = f"Multi-file processing failed:\n{str(e)}\n\nTraceback:\n{tb_str[-500:]}"
                    self.root.after(0, lambda m=error_detail: messagebox.showerror("Processing Error", m))
                    self.processing = False
            
            import threading
            self.processing = True
            self.processing_thread = threading.Thread(target=process_thread)
            self.processing_thread.start()
            self.root.after(100, self.check_processing_thread)
            return
        
        # Show multi-document options dialog
        self._show_multi_document_dialog(input_lines)
    
    def _process_images_standard_ocr(self, ocr_files, combine=True):
        """Process images and PDFs with standard Tesseract OCR."""
        if not ocr_files:
            return
        
        entries = []
        all_source_files = []
        
        for i, file_path in enumerate(ocr_files):
            self.set_status(f"📄 OCR processing file {i+1}/{len(ocr_files)}...")
            
            try:
                if file_path.lower().endswith('.pdf'):
                    # Process PDF with local OCR
                    provider = self.provider_var.get()
                    model = self.model_var.get()
                    api_key = self.config.get("keys", {}).get(provider, "")
                    all_api_keys = self.config.get("keys", {})
                    
                    success, result, method = get_ocr().extract_text_from_pdf_smart(
                        filepath=file_path,
                        language=self.config.get("ocr_language", "eng"),
                        quality=self.config.get("ocr_quality", "balanced"),
                        provider=provider,
                        model=model,
                        api_key=api_key,
                        all_api_keys=all_api_keys,
                        progress_callback=self.set_status,
                        force_cloud=False
                    )
                    
                    if success and result:
                        for j, entry in enumerate(result):
                            entries.append({
                                'start': len(entries),
                                'text': entry.get('text', ''),
                                'location': f"{os.path.basename(file_path)} - {entry.get('location', f'Page {j+1}')}"
                            })
                        all_source_files.append(file_path)
                else:
                    # Process image
                    import pytesseract
                    from PIL import Image
                    
                    img = Image.open(file_path)
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    
                    language = self.config.get("ocr_language", "eng")
                    text = pytesseract.image_to_string(img, lang=language)
                    
                    if text.strip():
                        entries.append({
                            'start': len(entries),
                            'text': text.strip(),
                            'location': os.path.basename(file_path)
                        })
                        all_source_files.append(file_path)
            except Exception as e:
                print(f"⚠️ OCR failed for {file_path}: {e}")
        
        if combine:
            self._handle_multi_image_ocr_result(entries, all_source_files if all_source_files else ocr_files)
        else:
            # Save each separately
            for entry in entries:
                location = entry.get('location', '')
                for f in ocr_files:
                    if os.path.basename(f) in location:
                        self._save_single_ocr_result(f, entry['text'])
                        break
            self.set_status(f"✅ Processed {len(ocr_files)} files separately")
            self.root.after(0, self.refresh_library)
        
        # Reset processing flag
        self.processing = False
    
    def _show_multi_document_dialog(self, input_lines):
        """
        Show dialog for handling multiple documents.
        Radio buttons for Combine/Separate, with conditional name entry and reorder list.
        """
        # Create custom dialog
        dialog = tk.Toplevel(self.root)
        dialog.title("Multiple Documents")
        dialog.geometry("520x480")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Center the dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (260)
        y = (dialog.winfo_screenheight() // 2) - (240)
        dialog.geometry(f"+{x}+{y}")
        
        # Content header
        ttk.Label(dialog, text=f"You've selected {len(input_lines)} documents:", 
                  font=('Arial', 11, 'bold')).pack(pady=(15, 5))
        
        ttk.Label(dialog, text="How would you like to process them?",
                  font=('Arial', 10)).pack(pady=(5, 10))
        
        # Radio button variable
        choice_var = tk.StringVar(value="")
        
        # Frame for radio buttons and options
        options_frame = ttk.Frame(dialog)
        options_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)
        
        # Option 1: Combine for Analysis
        combine_frame = ttk.Frame(options_frame)
        combine_frame.pack(fill=tk.X, pady=5)
        
        combine_rb = ttk.Radiobutton(combine_frame, text="📚 Combine for Analysis", 
                                      variable=choice_var, value="combine")
        combine_rb.pack(anchor=tk.W)
        ttk.Label(combine_frame, text="      Load all as equal sources for group analysis",
                  font=('Arial', 8), foreground='gray').pack(anchor=tk.W)
        
        # Combine options frame (initially hidden) - contains name AND reorder list
        combine_options_frame = ttk.Frame(options_frame)
        # Don't pack yet - will be shown/hidden dynamically
        
        # Name entry row
        name_row = ttk.Frame(combine_options_frame)
        name_row.pack(fill=tk.X, pady=(5, 5))
        ttk.Label(name_row, text="Analysis name:", font=('Arial', 9)).pack(side=tk.LEFT)
        default_name = f"Multi-doc Analysis ({len(input_lines)} docs)"
        name_var = tk.StringVar(value=default_name)
        name_entry = ttk.Entry(name_row, textvariable=name_var, width=35, font=('Arial', 10))
        name_entry.pack(side=tk.LEFT, padx=(10, 0), fill=tk.X, expand=True)
        
        # Document order section
        ttk.Label(combine_options_frame, text="Document order (use buttons to reorder):", 
                  font=('Arial', 9)).pack(anchor=tk.W, pady=(10, 5))
        
        # Listbox and buttons row
        list_row = ttk.Frame(combine_options_frame)
        list_row.pack(fill=tk.BOTH, expand=True)
        
        # Listbox with scrollbar
        list_container = ttk.Frame(list_row)
        list_container.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(list_container)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        listbox = tk.Listbox(
            list_container,
            yscrollcommand=scrollbar.set,
            font=('Arial', 9),
            selectmode=tk.SINGLE,
            height=8
        )
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=listbox.yview)
        
        # Ordered file list (mutable copy)
        ordered_files = list(input_lines)
        
        def refresh_listbox():
            listbox.delete(0, tk.END)
            for i, f in enumerate(ordered_files):
                display_name = os.path.basename(f) if os.path.exists(f) else f[:40]
                listbox.insert(tk.END, f"{i+1}. {display_name}")
        
        refresh_listbox()
        
        # Move buttons
        btn_col = ttk.Frame(list_row)
        btn_col.pack(side=tk.LEFT, padx=(10, 0), fill=tk.Y)
        
        def move_up():
            sel = listbox.curselection()
            if sel and sel[0] > 0:
                idx = sel[0]
                ordered_files[idx], ordered_files[idx-1] = ordered_files[idx-1], ordered_files[idx]
                refresh_listbox()
                listbox.selection_set(idx-1)
                listbox.see(idx-1)
        
        def move_down():
            sel = listbox.curselection()
            if sel and sel[0] < len(ordered_files) - 1:
                idx = sel[0]
                ordered_files[idx], ordered_files[idx+1] = ordered_files[idx+1], ordered_files[idx]
                refresh_listbox()
                listbox.selection_set(idx+1)
                listbox.see(idx+1)
        
        ttk.Button(btn_col, text="↑ Up", command=move_up, width=8).pack(pady=2)
        ttk.Button(btn_col, text="↓ Down", command=move_down, width=8).pack(pady=2)
        
        # Option 2: Process Separately  
        separate_frame = ttk.Frame(options_frame)
        separate_frame.pack(fill=tk.X, pady=(15, 5))
        
        separate_rb = ttk.Radiobutton(separate_frame, text="📄 Process Separately", 
                                       variable=choice_var, value="separate")
        separate_rb.pack(anchor=tk.W)
        ttk.Label(separate_frame, text="      Each document becomes its own library entry",
                  font=('Arial', 8), foreground='gray').pack(anchor=tk.W)
        
        # Function to show/hide combine options based on selection
        def on_choice_change(*args):
            if choice_var.get() == "combine":
                combine_options_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 0), after=combine_frame)
                name_entry.focus_set()
                name_entry.select_range(0, tk.END)
                # Resize dialog to show list
                dialog.geometry("520x520")
            else:
                combine_options_frame.pack_forget()
                # Reset name to default when switching away
                name_var.set(default_name)
                # Reset order when switching away
                ordered_files.clear()
                ordered_files.extend(input_lines)
                refresh_listbox()
                # Shrink dialog
                dialog.geometry("520x280")
        
        choice_var.trace_add('write', on_choice_change)
        
        result = {'choice': None, 'name': None, 'ordered_files': None}
        
        def on_ok():
            if not choice_var.get():
                # No selection made
                return
            result['choice'] = choice_var.get()
            if choice_var.get() == "combine":
                result['name'] = name_var.get().strip() or default_name
                result['ordered_files'] = list(ordered_files)
            dialog.destroy()
        
        def on_cancel():
            result['choice'] = None
            dialog.destroy()
        
        # Buttons frame
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=15)
        
        ok_btn = ttk.Button(btn_frame, text="OK", command=on_ok, width=10)
        ok_btn.pack(side=tk.LEFT, padx=5)
        
        cancel_btn = ttk.Button(btn_frame, text="Cancel", command=on_cancel, width=10)
        cancel_btn.pack(side=tk.LEFT, padx=5)
        
        # Bind Enter and Escape
        dialog.bind('<Return>', lambda e: on_ok())
        dialog.bind('<Escape>', lambda e: on_cancel())
        
        # Wait for dialog
        self.root.wait_window(dialog)
        
        # Process result
        if result['choice'] == 'combine':
            self._combine_documents_for_analysis(result['ordered_files'], result['name'])
        elif result['choice'] == 'separate':
            self._batch_process_inputs(input_lines)
        # else: cancelled, do nothing
    
    def _combine_documents_for_analysis(self, input_lines, analysis_name):
        """
        Combine multiple documents as equal sources for group analysis.
        """
        self.set_status(f"📚 Loading {len(input_lines)} documents...")
        
        # Process in background thread
        def load_thread():
            self._load_combined_documents(input_lines, analysis_name)
        
        self.processing = True
        self.process_btn.config(state=tk.DISABLED)
        self.processing_thread = threading.Thread(target=load_thread)
        self.processing_thread.start()
        self.root.after(100, self.check_processing_thread)
    
    def _load_combined_documents(self, input_lines, analysis_name):
        """
        Load all documents as equal sources and create a multi-doc analysis entry.
        Runs in background thread.
        """
        import time
        
        loaded_documents = []
        total = len(input_lines)
        print(f"📚 Starting to load {total} documents...")
        
        for i, item in enumerate(input_lines):
            # Thread-safe status update - show filename
            display_name = os.path.basename(item) if os.path.exists(item) else item[:30]
            self.root.after(0, lambda idx=i, name=display_name: self.set_status(f"📚 Loading {idx+1}/{total}: {name}"))
            print(f"📚 Loading {i+1}/{total}: {display_name}")
            
            # Small delay to allow status to update in UI
            time.sleep(0.05)
            
            try:
                if os.path.exists(item):
                    ext = os.path.splitext(item)[1].lower()
                    file_name = os.path.basename(item)
                    
                    # Skip audio/video files - they need transcription
                    if ext in ('.mp3', '.wav', '.m4a', '.ogg', '.flac', '.aac', '.wma', '.opus', '.mp4', '.avi', '.mov'):
                        print(f"⚠️ Audio/video files not supported in combine mode: {item}")
                        loaded_documents.append({
                            'path': item,
                            'title': file_name,
                            'text': f"[Audio/video file - requires transcription: {file_name}]",
                            'char_count': 0,
                            'skipped': True,
                            'reason': 'audio_video'
                        })
                        continue
                    
                    # Skip image files - they need OCR
                    if ext in ('.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp', '.gif', '.webp'):
                        print(f"⚠️ Image files not supported in combine mode: {item}")
                        loaded_documents.append({
                            'path': item,
                            'title': file_name,
                            'text': f"[Image file - requires OCR: {file_name}]",
                            'char_count': 0,
                            'skipped': True,
                            'reason': 'image'
                        })
                        continue
                    
                    # Handle spreadsheets
                    if ext in ('.xlsx', '.xls', '.csv'):
                        success, text_content, title, error_msg = self.convert_spreadsheet_to_text(item)
                        if success:
                            loaded_documents.append({
                                'path': item,
                                'title': file_name,
                                'text': text_content,
                                'char_count': len(text_content),
                                'doc_type': 'spreadsheet'
                            })
                        else:
                            loaded_documents.append({
                                'path': item,
                                'title': file_name,
                                'text': f"[Failed to load spreadsheet: {error_msg}]",
                                'char_count': 0,
                                'error': error_msg
                            })
                        continue
                    
                    # Handle scanned PDFs
                    if ext == '.pdf':
                        is_scanned = get_ocr().is_pdf_scanned(item)
                        if is_scanned:
                            # Check for cached OCR
                            cached = get_ocr().load_cached_ocr(
                                item,
                                self.config.get("ocr_quality", "balanced"),
                                self.config.get("ocr_language", "eng")
                            )
                            if cached:
                                text = "\n".join(entry.get('text', '') for entry in cached.get('entries', []))
                                loaded_documents.append({
                                    'path': item,
                                    'title': file_name,
                                    'text': text,
                                    'char_count': len(text),
                                    'doc_type': 'pdf_ocr_cached'
                                })
                                continue
                            else:
                                loaded_documents.append({
                                    'path': item,
                                    'title': file_name,
                                    'text': f"[Scanned PDF - requires OCR: {file_name}]",
                                    'char_count': 0,
                                    'skipped': True,
                                    'reason': 'scanned_pdf'
                                })
                                continue
                    
                    # Use document fetcher for regular files (txt, docx, pdf, rtf, html)
                    success, result, title, doc_type = get_doc_fetcher().fetch_local_file(item)
                    
                    if success:
                        # Extract text from result
                        if isinstance(result, list):
                            text = "\n".join(entry.get('text', '') for entry in result)
                        else:
                            text = str(result)
                        
                        loaded_documents.append({
                            'path': item,
                            'title': file_name,
                            'text': text,
                            'char_count': len(text),
                            'doc_type': doc_type
                        })
                    else:
                        print(f"⚠️ Failed to load {item}: {result}")
                        loaded_documents.append({
                            'path': item,
                            'title': file_name,
                            'text': f"[Failed to load: {result}]",
                            'char_count': 0,
                            'error': str(result)
                        })
                        
                elif item.startswith('http'):
                    # URL - note limitation
                    print(f"⚠️ URL loading not yet supported in combine mode: {item}")
                    loaded_documents.append({
                        'path': item,
                        'title': item[:50],
                        'text': "[URL loading not yet supported in combine mode]",
                        'char_count': 0,
                        'is_url': True
                    })
                    
            except Exception as e:
                import traceback
                print(f"❌ Error loading {item}: {e}")
                traceback.print_exc()
                loaded_documents.append({
                    'path': item,
                    'title': os.path.basename(item) if os.path.exists(item) else item[:50],
                    'text': f"[Error: {str(e)}]",
                    'char_count': 0,
                    'error': str(e)
                })
        
        # Finalize on main thread
        print(f"📚 Finished loading loop. {len(loaded_documents)} documents. Calling finalize...")
        self.root.after(0, self._finalize_combined_documents, loaded_documents, analysis_name)
    
    def _finalize_combined_documents(self, loaded_documents, analysis_name):
        """
        Finalize the combined documents - create library entry and set up UI.
        Runs on main thread.
        """
        print(f"📚 _finalize_combined_documents ENTERED with {len(loaded_documents)} documents")
        
        from document_library import add_document_to_library
        import datetime
        
        self.processing = False
        self.process_btn.config(state=tk.NORMAL)
        
        # Count successfully loaded documents
        success_count = len([d for d in loaded_documents if d.get('char_count', 0) > 0])
        print(f"📚 Successfully loaded: {success_count}/{len(loaded_documents)}")
        
        if success_count == 0:
            messagebox.showerror("Error", "Failed to load any documents.")
            self.set_status("❌ Failed to load documents")
            return
        
        # Build combined text for the analysis
        combined_parts = []
        total_chars = 0
        
        for doc in loaded_documents:
            title = doc.get('title', 'Unknown')
            text = doc.get('text', '')
            combined_parts.append(f"\n\n{'='*60}\n=== {title} ===\n{'='*60}\n{text}")
            total_chars += len(text)
        
        combined_text = "\n".join(combined_parts).strip()
        
        # Build metadata
        metadata = {
            "type": "multi_doc_analysis",
            "analysis_name": analysis_name,
            "source_documents": [
                {
                    'path': d.get('path', ''),
                    'title': d.get('title', ''),
                    'char_count': d.get('char_count', 0),
                    'doc_type': d.get('doc_type', 'unknown'),
                    'error': d.get('error')
                }
                for d in loaded_documents
            ],
            "document_count": len(loaded_documents),
            "successful_count": success_count,
            "total_chars": total_chars,
            "created": datetime.datetime.now().isoformat()
        }
        
        # Create entries structure - one entry per document for cleaner viewing
        entries = []
        current_start = 0
        for doc in loaded_documents:
            if doc.get('char_count', 0) > 0:
                entries.append({
                    'text': doc.get('text', ''),
                    'start': current_start,
                    'location': doc.get('title', 'Unknown Document')
                })
                current_start += doc.get('char_count', 0)
        
        # Create library title with icon
        library_title = f"📚 {analysis_name}"
        
        # Add to library
        total_chars = sum(len(e.get('text', '')) for e in entries)
        print(f"📚 Adding to library: '{title}' ({total_chars:,} chars)")
        print(f"📚 DEBUG: entries length = {len(entries)}")
        print(f"📚 DEBUG: metadata keys = {list(metadata.keys())}")
        print(f"📚 DEBUG: About to call add_document_to_library...")
        import sys
        sys.stdout.flush()  # Force output
        
        try:
            doc_id = add_document_to_library(
                doc_type="multi_doc_analysis",
                source=f"multi_doc_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}",
                title=library_title,
                entries=entries,
                document_class="source",
                metadata=metadata
            )
            print(f"📚 DEBUG: add_document_to_library returned: {doc_id}")
            sys.stdout.flush()
        except Exception as e:
            import traceback
            print(f"❌ EXCEPTION in add_document_to_library: {e}")
            traceback.print_exc()
            sys.stdout.flush()
            doc_id = None
        
        print(f"📚 DEBUG: doc_id is now: {doc_id}")
        sys.stdout.flush()
        
        if doc_id:
            try:
                print(f"📚 Library entry created: {doc_id}")
                sys.stdout.flush()
                # Set as current document
                print(f"📚 DEBUG: Setting current_document_id...")
                sys.stdout.flush()
                self.current_document_id = doc_id
                self.current_document_source = library_title
                self.current_document_type = "multi_doc_analysis"
                self.current_document_class = "source"
                self.current_document_text = combined_text
                self.current_document_metadata = metadata
                self.current_entries = entries
                print(f"📚 DEBUG: Current document set")
                sys.stdout.flush()
                
                # Clear any existing attachments - the combined text already has all content
                print(f"📚 DEBUG: Clearing attachments (combined_text has all content)...")
                sys.stdout.flush()
                self.attachment_manager.attachments.clear()
                print(f"📚 DEBUG: Attachments cleared")
                sys.stdout.flush()
                
                # Update UI
                print(f"📚 DEBUG: Calling update_context_buttons...")
                sys.stdout.flush()
                self.update_context_buttons('document')
                print(f"📚 DEBUG: Calling update_button_states...")
                sys.stdout.flush()
                # Enable Run button highlight for newly loaded document
                self._run_highlight_enabled = True
                self.update_button_states()
                print(f"📚 DEBUG: Calling refresh_library...")
                sys.stdout.flush()
                self.refresh_library()
                print(f"📚 DEBUG: UI updated")
                sys.stdout.flush()
                
                # Show success
                print(f"📚 DEBUG: About to set success status...")
                sys.stdout.flush()
                self.set_status(f"✅ Loaded {success_count} documents as '{analysis_name}' - Select prompt and click Run")
                print(f"📚 Created Multi-doc Analysis: {doc_id} ({success_count} documents, {total_chars:,} chars)")
                sys.stdout.flush()
                print(f"📚 DEBUG: _finalize_combined_documents COMPLETE")
                sys.stdout.flush()
            except Exception as e:
                import traceback
                print(f"❌ EXCEPTION in post-save processing: {e}")
                traceback.print_exc()
                sys.stdout.flush()
            
            # Show brief confirmation
            if success_count < len(loaded_documents):
                failed = len(loaded_documents) - success_count
                messagebox.showinfo(
                    "Documents Loaded",
                    f"✅ Loaded {success_count} of {len(loaded_documents)} documents.\n\n"
                    f"⚠️ {failed} document(s) failed to load.\n\n"
                    f"Ready for analysis. Select a prompt and click Run."
                )
        else:
            messagebox.showerror("Error", "Failed to create library entry.")
            self.set_status("❌ Failed to save to library")
    
    def _batch_process_inputs(self, input_lines):
        """Process multiple inputs sequentially."""
        messagebox.showinfo(
            "Batch Processing",
            f"Batch processing {len(input_lines)} items sequentially.\n\n"
            "Each item will be loaded and can be processed with your selected prompt.\n"
            "Use 'Documents Library' to review results."
        )
        
        # Process first item
        self.universal_input_entry.delete('1.0', 'end')
        self.universal_input_entry.insert('1.0', input_lines[0])
        self.placeholder_active = False
        self.smart_load()
        
        # Store remaining for sequential processing
        self._batch_queue = input_lines[1:]
        if self._batch_queue:
            self.set_status(f"📋 {len(self._batch_queue)} more items in queue - click 'Run' to process, then load next")

    def is_youtube_url(self, url):
        """Check if URL is a YouTube video"""
        youtube_patterns = [
            'youtube.com/watch',
            'youtu.be/',
            'youtube.com/embed/',
            'youtube.com/v/',
            'youtube.com/live/',
            'youtube.com/shorts/',
            'm.youtube.com'
        ]
        url_lower = url.lower()
        return any(pattern in url_lower for pattern in youtube_patterns)

    def is_substack_url(self, url):
     """Check if URL is a Substack post"""
     if not SUBSTACK_AVAILABLE:
            return False
     from substack_utils import is_substack_url
     return is_substack_url(url)

    def _is_google_drive_file_url(self, url):
        """Check if URL is a Google Drive file link (PDF, doc, etc.)"""
        url_lower = url.lower()
        patterns = [
            'drive.google.com/file/d/',
            'drive.google.com/u/',  # Multi-account paths like /u/0/file/d/
            'drive.google.com/open?id=',
            'docs.google.com/document/d/',
            'docs.google.com/spreadsheets/d/',
            'docs.google.com/presentation/d/',
        ]
        return any(pattern in url_lower for pattern in patterns)

    def _is_google_drive_folder_url(self, url):
        """Check if URL is a Google Drive folder link (not a downloadable file)"""
        url_lower = url.lower()
        folder_patterns = [
            'drive.google.com/drive/folders/',
            'drive.google.com/drive/u/',  # Multi-account folder paths
        ]
        # It's a folder if it matches folder patterns AND is NOT a file URL
        is_folder = any(pattern in url_lower for pattern in folder_patterns)
        is_file = self._is_google_drive_file_url(url)
        return is_folder and not is_file

    def _extract_google_drive_file_id(self, url):
        """Extract file ID from various Google Drive URL formats."""
        import re
        # drive.google.com/file/d/FILE_ID/view
        match = re.search(r'drive\.google\.com/(?:u/\d+/)?file/d/([a-zA-Z0-9_-]+)', url)
        if match:
            return match.group(1)
        # drive.google.com/open?id=FILE_ID
        match = re.search(r'drive\.google\.com/open\?id=([a-zA-Z0-9_-]+)', url)
        if match:
            return match.group(1)
        # docs.google.com/document/d/FILE_ID
        match = re.search(r'docs\.google\.com/(?:document|spreadsheets|presentation)/d/([a-zA-Z0-9_-]+)', url)
        if match:
            return match.group(1)
        return None

    def _fetch_google_drive_file(self, url):
        """
        Download a file from Google Drive and process it locally.
        Works with publicly shared files. For private files, instructs user to download manually.
        """
        file_id = self._extract_google_drive_file_id(url)
        if not file_id:
            messagebox.showerror("Google Drive Error",
                                "Could not extract file ID from this Google Drive URL.\n\n"
                                "Please download the file manually and load it from your computer.")
            return

        # Check if it's a Google Docs/Sheets/Slides native document (not a file)
        url_lower = url.lower()
        if 'docs.google.com/document/' in url_lower:
            # Google Doc - export as docx
            export_url = f"https://docs.google.com/document/d/{file_id}/export?format=docx"
            ext = '.docx'
            file_type_name = "Google Doc"
        elif 'docs.google.com/spreadsheets/' in url_lower:
            export_url = f"https://docs.google.com/spreadsheets/d/{file_id}/export?format=xlsx"
            ext = '.xlsx'
            file_type_name = "Google Sheet"
        elif 'docs.google.com/presentation/' in url_lower:
            export_url = f"https://docs.google.com/presentation/d/{file_id}/export?format=pptx"
            ext = '.pptx'
            file_type_name = "Google Slides"
        else:
            # Regular Drive file (PDF, etc.) - use direct download
            export_url = f"https://drive.google.com/uc?export=download&id={file_id}"
            ext = '.pdf'  # Default; actual extension determined from response headers
            file_type_name = "Google Drive file"

        self.processing = True
        self.set_status(f"Downloading {file_type_name} from Google Drive...")

        def download_thread():
            import re  # Must be at top of nested function to avoid UnboundLocalError
            temp_path = None
            try:
                import urllib.request
                import urllib.error

                # Build request with browser-like headers
                req = urllib.request.Request(export_url, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                })

                response = urllib.request.urlopen(req, timeout=60)

                # Try to get filename from Content-Disposition header
                content_disp = response.headers.get('Content-Disposition', '')
                if 'filename=' in content_disp:
                    fname_match = re.search(r'filename\*?=(?:UTF-8\'\')?("?)(.+?)\1(?:;|$)', content_disp)
                    if fname_match:
                        filename = fname_match.group(2).strip('"')
                        # URL-decode the filename
                        from urllib.parse import unquote
                        filename = unquote(filename)
                        _, file_ext = os.path.splitext(filename)
                        if file_ext:
                            ext_actual = file_ext
                        else:
                            ext_actual = ext
                    else:
                        filename = f"gdrive_{file_id}{ext}"
                        ext_actual = ext
                else:
                    filename = f"gdrive_{file_id}{ext}"
                    ext_actual = ext

                # Check for Google's virus scan warning page (large files)
                content_type = response.headers.get('Content-Type', '')
                if 'text/html' in content_type and ext_actual == '.pdf':
                    # Likely a "virus scan" interstitial or access denied page
                    html_content = response.read().decode('utf-8', errors='ignore')
                    if 'confirm=' in html_content or 'download_warning' in html_content:
                        # Try to extract confirm token for large files
                        confirm_match = re.search(r'confirm=([0-9A-Za-z_-]+)', html_content)
                        if confirm_match:
                            confirm_url = f"https://drive.google.com/uc?export=download&confirm={confirm_match.group(1)}&id={file_id}"
                            req2 = urllib.request.Request(confirm_url, headers={
                                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                            })
                            response = urllib.request.urlopen(req2, timeout=60)
                        else:
                            # Access denied or not a downloadable file
                            self.root.after(0, lambda: messagebox.showwarning(
                                "Google Drive Access",
                                "This file cannot be downloaded directly.\n\n"
                                "Possible reasons:\n"
                                "  • The file is not publicly shared\n"
                                "  • The file requires sign-in to access\n"
                                "  • The file is too large for direct download\n\n"
                                "Please download the file manually from Google Drive\n"
                                "and then load it from your computer."
                            ))
                            self.root.after(0, lambda: self.set_status(""))
                            self.processing = False
                            return

                # Save to temp file with progress indication
                temp_dir = tempfile.mkdtemp()
                # Sanitise filename for filesystem
                safe_filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
                temp_path = os.path.join(temp_dir, safe_filename)

                # Get total size if available (for percentage display)
                total_size = response.headers.get('Content-Length')
                total_size = int(total_size) if total_size else None
                downloaded = 0
                last_update_time = 0

                with open(temp_path, 'wb') as f:
                    while True:
                        chunk = response.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)

                        # Update status bar every ~100KB to avoid flooding the UI
                        import time
                        now = time.time()
                        if now - last_update_time >= 0.3:  # Max ~3 updates per second
                            last_update_time = now
                            dl_mb = downloaded / (1024 * 1024)
                            if total_size:
                                total_mb = total_size / (1024 * 1024)
                                pct = (downloaded / total_size) * 100
                                status_msg = f"Downloading from Google Drive: {dl_mb:.1f} / {total_mb:.1f} MB ({pct:.0f}%)"
                            else:
                                status_msg = f"Downloading from Google Drive: {dl_mb:.1f} MB downloaded..."
                            self.root.after(0, lambda m=status_msg: self.set_status(m))

                file_size = os.path.getsize(temp_path)
                dl_mb_final = file_size / (1024 * 1024)
                self.root.after(0, lambda: self.set_status(f"Download complete ({dl_mb_final:.1f} MB). Processing..."))
                print(f"✅ Downloaded Google Drive file: {safe_filename} ({file_size:,} bytes)")

                if file_size < 1000:
                    # Probably an error page, not the actual file
                    with open(temp_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content_preview = f.read(500)
                    if '<html' in content_preview.lower():
                        self.root.after(0, lambda: messagebox.showwarning(
                            "Google Drive Access",
                            "Could not download the file. It may not be publicly shared.\n\n"
                            "Please download the file manually from Google Drive\n"
                            "and then load it from your computer."
                        ))
                        self.root.after(0, lambda: self.set_status(""))
                        self.processing = False
                        return

                # Process as local file
                self.root.after(0, lambda p=temp_path: self._load_downloaded_gdrive_file(p))

            except urllib.error.HTTPError as e:
                error_msg = f"HTTP {e.code}"
                if e.code == 403:
                    error_msg = "Access denied. The file is not publicly shared."
                elif e.code == 404:
                    error_msg = "File not found. The link may be invalid or expired."
                print(f"❌ Google Drive download failed: {error_msg}")
                self.root.after(0, lambda m=error_msg: messagebox.showerror(
                    "Google Drive Error",
                    f"Could not download file: {m}\n\n"
                    f"Please download the file manually from Google Drive\n"
                    f"and then load it from your computer."
                ))
                self.root.after(0, lambda: self.set_status(""))
                self.processing = False
            except Exception as e:
                print(f"❌ Google Drive download error: {e}")
                self.root.after(0, lambda m=str(e): messagebox.showerror(
                    "Google Drive Error",
                    f"Download failed: {m}\n\n"
                    f"Please download the file manually and load it from your computer."
                ))
                self.root.after(0, lambda: self.set_status(""))
                self.processing = False

        thread = threading.Thread(target=download_thread, daemon=True)
        thread.start()

    def _load_downloaded_gdrive_file(self, file_path):
        """Load a file downloaded from Google Drive through the normal local file pipeline."""
        self.processing = False
        self.file_path_var.set(file_path)
        self.set_status(f"Processing downloaded file: {os.path.basename(file_path)}")
        self.fetch_local_file()

    def could_be_youtube_id(self, text):
        """Check if text could be a YouTube video ID (11 characters, alphanumeric + - and _)"""
        if len(text) == 11:
            return bool(re.match(r'^[A-Za-z0-9_-]{11}$', text))
        return False

    def _is_image_file(self, filepath):
        """Check if a file is an image that needs OCR."""
        if not os.path.exists(filepath):
            return False
        ext = os.path.splitext(filepath)[1].lower()
        return ext in ('.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp', '.gif', '.webp')
    
    def _needs_ocr(self, filepath):
        """Check if a file needs OCR processing (image or scanned PDF)."""
        if not os.path.exists(filepath):
            return False
        ext = os.path.splitext(filepath)[1].lower()
        
        # Images always need OCR
        if ext in ('.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp', '.gif', '.webp'):
            return True
        
        # PDFs might need OCR if scanned
        if ext == '.pdf':
            try:
                return get_ocr().is_pdf_scanned(filepath)
            except:
                return False
        
        return False
    
    def _check_ocr_confidence(self, image_path):
        """
        Quick OCR confidence check on an image.
        Returns (confidence_score, likely_handwriting).
        """
        try:
            import pytesseract
            from PIL import Image
            
            # Open and optionally resize for speed
            img = Image.open(image_path)
            
            # Resize if too large (for speed)
            max_size = 1000
            if max(img.size) > max_size:
                ratio = max_size / max(img.size)
                new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
            
            # Convert to RGB if necessary
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Get OCR data with confidence scores
            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
            
            # Calculate average confidence (excluding -1 which means no text detected)
            confidences = [int(c) for c in data['conf'] if int(c) > 0]
            
            if not confidences:
                # No text detected - likely handwriting or very poor quality
                return 0, True
            
            avg_confidence = sum(confidences) / len(confidences)
            threshold = self.config.get("ocr_confidence_threshold", 70)
            likely_handwriting = avg_confidence < threshold
            
            return avg_confidence, likely_handwriting
            
        except Exception as e:
            print(f"⚠️ OCR confidence check failed: {e}")
            # On error, default to suggesting vision model
            return 0, True
    
