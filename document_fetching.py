"""
document_fetching.py - Document fetching methods for DocAnalyser.

Handles loading content from various sources: YouTube, Substack, Twitter/X,
video platforms, web URLs, local files, and clipboard paste fallback.

Extracted from Main.py to reduce file size. Uses a mixin pattern so all
self.xxx references continue to work unchanged.
"""

from __future__ import annotations

import os
import datetime
import logging
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import List, Dict

from document_library import add_document_to_library, get_document_by_id
from utils import entries_to_text, entries_to_text_with_speakers
from youtube_utils import fetch_youtube_transcript, fetch_youtube_with_audio_fallback

# Twitter support (optional)
try:
    from twitter_utils import fetch_twitter_content, download_twitter_video
except ImportError:
    pass

# Lazy module loaders (mirrors Main.py pattern)
def get_doc_fetcher():
    import document_fetcher
    return document_fetcher

def get_ocr():
    import ocr_handler
    return ocr_handler

# Substack availability flag
try:
    from substack_utils import (
        fetch_substack_transcript,
        format_substack_transcript
    )
    SUBSTACK_AVAILABLE = True
except ImportError:
    SUBSTACK_AVAILABLE = False


class DocumentFetchingMixin:
    """Mixin class providing document fetching methods for DocAnalyzerApp."""

    def _handle_transcription_error(self, error_msg: str):
        """Handle transcription failure."""
        self.processing = False
        self.process_btn.config(state=tk.NORMAL)
        self.set_status(f"❌ Transcription failed: {error_msg}")
        messagebox.showerror("Transcription Error", f"Could not transcribe audio:\n\n{error_msg}")
    

    def fetch_youtube(self):
        print("=" * 60)
        print("📺 fetch_youtube() called")
        
        self.update_context_buttons('youtube')
        print("   Context buttons updated")
        
        # Safety: Force reset processing flag if stuck
        if self.processing:
            if not hasattr(self, 'processing_thread') or self.processing_thread is None or not self.processing_thread.is_alive():
                print("⚠️ Warning: processing flag was stuck, resetting...")
                self.processing = False
        
        if self.processing:
            print("❌ Already processing - showing warning and returning")
            messagebox.showwarning("Warning", "Processing already in progress. Please wait or cancel.")
            return

        url_or_id = self.yt_url_var.get().strip()
        print(f"   URL from yt_url_var: '{url_or_id}'")

        # Validate input
        is_valid, error_msg = self.validate_youtube_url(url_or_id)
        print(f"   Validation result: valid={is_valid}, error='{error_msg}'")
        
        if not is_valid:
            print(f"❌ Validation failed: {error_msg}")
            messagebox.showerror("Invalid Input", error_msg)
            return

        print("✅ Starting YouTube fetch thread...")
        self.processing = True
        self.process_btn.config(state=tk.DISABLED)
        self.set_status("Fetching YouTube transcript...")
        self.processing_thread = threading.Thread(target=self._fetch_youtube_thread)
        self.processing_thread.start()
        self.root.after(100, self.check_processing_thread)
        print("   Thread started successfully")
        print("=" * 60)

    def _get_transcription_api_key(self, engine=None):
        """Get the correct API key for the selected transcription engine.
        
        The AI Provider key (e.g. DeepSeek) is NOT the same as the transcription
        engine key (e.g. AssemblyAI). This helper routes the correct key.
        """
        if engine is None:
            engine = self.transcription_engine_var.get()
        
        if engine == "assemblyai":
            return self.config.get("keys", {}).get("AssemblyAI", "")
        elif engine in ("openai_whisper", "whisper"):
            return self.config.get("keys", {}).get("OpenAI (ChatGPT)", self.api_key_var.get())
        else:
            # Local engines (faster_whisper, local_whisper) don't need an API key
            return self.api_key_var.get()

    def _fetch_youtube_thread(self):
        url_or_id = self.yt_url_var.get().strip()
        if self.yt_fallback_var.get():
            selected_engine = self.transcription_engine_var.get()
            
            success, result, title, source_type, yt_metadata = fetch_youtube_with_audio_fallback(
                url_or_id,
                api_key=self._get_transcription_api_key(selected_engine),
                engine=selected_engine,
                options={
                    'language': self.transcription_lang_var.get().strip() or None,  # None for auto-detect
                    'speaker_diarization': self.diarization_var.get(),
                    'enable_vad': self.config.get("enable_vad", True),  # Pass VAD setting
                    'assemblyai_api_key': self.config.get("keys", {}).get("AssemblyAI", ""),  # Always pass AssemblyAI key in options
                },
                bypass_cache=self.bypass_cache_var.get() if hasattr(self, 'bypass_cache_var') else False,
                progress_callback=self.set_status
            )
        else:
            success, result, title, source_type, yt_metadata = fetch_youtube_transcript(url_or_id)
        self.root.after(0, self._handle_youtube_result, success, result, title, source_type, yt_metadata)

    def _handle_youtube_result(self, success, result, title, source_type, yt_metadata=None):
        try:
            self.processing = False
            self.process_btn.config(state=tk.NORMAL)

            if success:
                logging.debug("YouTube result handler: success=True, processing entries...")
                self.current_entries = result
                self.current_document_source = self.yt_url_var.get().strip()
                self.current_document_type = source_type

                # ===== UPDATED: Auto-save source document to library =====
                try:
                    # Get the URL from input field
                    url = self.yt_url_var.get().strip() if hasattr(self, 'yt_url_var') else ""

                    # Build metadata including published_date if available
                    doc_metadata = {
                        "source": "youtube",
                        "title": title,
                        "fetched": datetime.datetime.now().isoformat() + 'Z'
                    }
                    # Add published_date from YouTube if available
                    if yt_metadata and yt_metadata.get('published_date'):
                        doc_metadata['published_date'] = yt_metadata['published_date']

                    # SAVE TO LIBRARY (replaces old add_document_to_library call)
                    doc_id = self.doc_saver.save_source_document(
                        entries=result,
                        title=title,
                        doc_type=source_type,
                        source=url,
                        metadata=doc_metadata  # Use the full metadata with published_date
                    )

                    if not doc_id:
                        raise Exception("Failed to save document to library")

                    logging.debug(f"Document added with ID: {doc_id}")

                except Exception as e:
                    print(f"⚠️ Failed to auto-save YouTube document: {e}")
                    logging.error(f"Failed to auto-save YouTube document: {e}")
                    import traceback
                    traceback.print_exc()
                    # Set a temporary ID to continue
                    doc_id = "temp_" + str(hash(url))[:12]
                # ===== END AUTO-SAVE CODE =====

                # ✅ FIX: Save old thread BEFORE changing document ID
                if self.thread_message_count > 0 and self.current_document_id:
                    print(
                        f"💾 Saving old thread ({self.thread_message_count} messages) to document {self.current_document_id}")
                    self.save_current_thread()

                # ✅ FIX: Clear thread WITHOUT saving (we already saved above)
                self.current_thread = []
                self.thread_message_count = 0
                self.update_thread_status()

                # ✅ NOW change the document ID
                self.current_document_id = doc_id

                # ✅ Load saved thread for NEW document (if it has one)
                self.load_saved_thread()

                # Get document class and metadata from library
                logging.debug("Getting document from library...")
                doc = get_document_by_id(doc_id)
                if doc:
                    self.current_document_class = doc.get("document_class", "source")
                    self.current_document_metadata = doc.get("metadata", {})
                    # CRITICAL FIX: Add title to metadata if not already there
                    if 'title' not in self.current_document_metadata and 'title' in doc:
                        self.current_document_metadata['title'] = doc['title']
                else:
                    self.current_document_class = "source"
                    self.current_document_metadata = {}

                logging.debug("Converting entries to text...")
                self.current_document_text = (
                    entries_to_text_with_speakers(
                        self.current_entries,
                        timestamp_interval=self.config.get("timestamp_interval", "every_segment")
                    )
                    if source_type == "audio_transcription"
                    else entries_to_text(
                        self.current_entries,
                        timestamp_interval=self.config.get("timestamp_interval", "every_segment")
                    )
                )
                logging.debug(
                    f"Text converted, length: {len(self.current_document_text) if self.current_document_text else 0}")

                # Preview display removed - content stored in current_document_text

                self.set_status("✅ Document loaded - Select prompt and click Run")
                self.refresh_library()
                
                # Update button states
                # Enable Run button highlight for newly loaded document
                self._run_highlight_enabled = True
                self.update_button_states()
                
                logging.debug("YouTube result handler completed successfully")
            else:
                logging.debug(f"YouTube result handler: success=False, error={result}")
                self.set_status(f"❌ Error: {result}")
                messagebox.showerror("Error", result)
        except Exception as e:
            logging.error(f"EXCEPTION in _handle_youtube_result: {e}")
            logging.error(traceback.format_exc())
            self.set_status(f"❌ Error: {str(e)}")
            messagebox.showerror("Error", f"Failed to process YouTube result: {str(e)}")
    def fetch_substack(self):
        """Fetch transcript from Substack video post"""
        print("📰 fetch_substack() called")

        if not SUBSTACK_AVAILABLE:
            messagebox.showerror("Error", "Substack support not available. Install with: pip install beautifulsoup4")
            return

        # Get URL from Text widget (not StringVar which may be out of sync)
        url = self.universal_input_entry.get('1.0', 'end-1c').strip()
        
        # Handle multi-line input - take first line only
        if '\n' in url:
            url = url.split('\n')[0].strip()

        if not url:
            messagebox.showwarning("No URL", "Please enter a Substack URL")
            return
        
        # Verify it's actually a Substack URL
        if 'substack.com' not in url.lower():
            messagebox.showwarning("Invalid URL", "This doesn't appear to be a Substack URL")
            return

        # Clear previous content - clear text display directly
        if hasattr(self, 'text_display'):
            self.text_display.delete('1.0', tk.END)

        # Update status
        self.set_status("Fetching Substack content...")
        
        # Store URL for thread to use (can't safely access widgets from thread)
        self._substack_url = url

        # Start background thread
        self.processing_thread = threading.Thread(target=self._fetch_substack_thread)
        self.processing_thread.daemon = True
        self.processing_thread.start()

    def _fetch_substack_thread(self):
        """Background thread for fetching Substack content (text articles OR video transcripts)"""
        try:
            url = getattr(self, '_substack_url', '').strip()
            if not url:
                # Fallback to StringVar if stored URL not available
                url = self.universal_input_var.get().strip()
            print(f"🔍 Fetching Substack content from: {url}")

            # Step 1: Try to fetch video transcript first
            from substack_utils import fetch_substack_transcript
            video_success, video_result, video_title, source_type, metadata = fetch_substack_transcript(url)
            
            has_video = video_success and isinstance(video_result, list) and len(video_result) > 0
            
            # Step 2: Try to scrape article text
            article_text = None
            article_title = None
            try:
                import requests
                from bs4 import BeautifulSoup
                
                print(f"📄 Attempting to scrape article text...")
                response = requests.get(url, timeout=30)
                response.raise_for_status()
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Extract title
                title_elem = soup.find('h1', class_='post-title')
                if not title_elem:
                    title_elem = soup.find('h1')
                article_title = title_elem.get_text(strip=True) if title_elem else "Substack Article"
                
                # Extract article content
                article_div = soup.find('div', class_='available-content')
                if not article_div:
                    article_div = soup.find('div', class_='body')
                if not article_div:
                    article_div = soup.find('article')
                
                if article_div:
                    # Get all paragraphs
                    paragraphs = article_div.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
                    article_text = '\n\n'.join([p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)])
                    print(f"✅ Scraped article: {len(article_text)} chars")
                else:
                    print(f"⚠️ No article content found")
                    
            except Exception as e:
                print(f"⚠️ Could not scrape article text: {e}")
            
            has_text = bool(article_text and len(article_text) > 100)
            
            print(f"📊 Content found: video={has_video}, text={has_text}")
            
            # Step 3: Decide what to do based on what we found
            if has_video and has_text:
                # BOTH available - ask user
                print(f"🎯 Both video and text available - asking user")
                choice_data = {
                    'video_title': video_title,
                    'video_entries': video_result,
                    'text_title': article_title,
                    'text_content': article_text,
                    'url': url
                }
                self.root.after(0, self._ask_substack_content_choice_simple, choice_data)
                
            elif has_video:
                # Only video available
                print(f"🎥 Only video available - loading transcript")
                self.root.after(0, self._handle_substack_result, True, video_result, video_title, 'substack', url)
                
            elif has_text:
                # Only text available
                print(f"📄 Only text available - loading article")
                
                # Sanitize the text to remove any problematic characters
                import html
                import re
                
                # Decode HTML entities
                clean_text = html.unescape(article_text)
                
                # Remove lines that are just asterisks (markdown separator issue)
                lines = clean_text.split('\n')
                filtered_lines = []
                for line in lines:
                    # Remove lines that are ONLY asterisks/dashes/underscores (common separators)
                    stripped = line.strip()
                    if stripped and not re.match(r'^[\*\-_]+$', stripped):
                        filtered_lines.append(line)
                    elif not stripped:  # Keep blank lines
                        filtered_lines.append(line)
                    # else: skip the separator line
                
                clean_text = '\n'.join(filtered_lines)
                
                # Remove any null bytes or other control characters
                clean_text = ''.join(char for char in clean_text if char.isprintable() or char in '\n\t\r')
                
                entries = [{
                    'text': clean_text,
                    'start': 0,
                    'timestamp': '[Article]'
                }]
                self.root.after(0, self._handle_substack_result, True, entries, article_title, 'substack', url)
                
            else:
                # Nothing found
                error_msg = "No transcript or article text found on this Substack page"
                print(f"❌ {error_msg}")
                self.root.after(0, self._handle_substack_result, False, error_msg, "", "substack", url)

        except Exception as e:
            print(f"❌ Exception in Substack fetch thread: {e}")
            import traceback
            traceback.print_exc()
            error_msg = f"Exception: {str(e)}"
            self.root.after(0, self._handle_substack_result, False, error_msg, "", "substack", url)

    def _ask_substack_content_choice_simple(self, choice_data):
        """Ask user whether they want text article or video transcript when both are available"""
        from tkinter import messagebox
        
        # Build the message
        video_title = choice_data['video_title']
        video_entries = choice_data['video_entries']
        text_title = choice_data['text_title']
        text_content = choice_data['text_content']
        url = choice_data['url']
        
        message = (
            f"This Substack page contains both text and video:\n\n"
            f"📄 Text Article: ~{len(text_content):,} characters\n"
            f"🎥 Video Transcript: {len(video_entries)} segments\n\n"
            f"Which would you like to load?"
        )
        
        # Custom dialog with three buttons
        dialog = tk.Toplevel(self.root)
        dialog.title("Choose Content Type")
        dialog.geometry("450x200")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Center the dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
        
        # Message label
        msg_label = tk.Label(dialog, text=message, justify=tk.LEFT, padx=20, pady=20)
        msg_label.pack()
        
        choice = {'value': None}
        
        def choose_text():
            choice['value'] = 'text'
            dialog.destroy()
        
        def choose_video():
            choice['value'] = 'video'
            dialog.destroy()
        
        def choose_cancel():
            choice['value'] = None
            dialog.destroy()
        
        # Buttons frame
        btn_frame = tk.Frame(dialog)
        btn_frame.pack(pady=10)
        
        text_btn = tk.Button(btn_frame, text="📄 Text Article", command=choose_text, width=15)
        text_btn.pack(side=tk.LEFT, padx=5)
        
        video_btn = tk.Button(btn_frame, text="🎥 Video Transcript", command=choose_video, width=15)
        video_btn.pack(side=tk.LEFT, padx=5)
        
        cancel_btn = tk.Button(btn_frame, text="Cancel", command=choose_cancel, width=10)
        cancel_btn.pack(side=tk.LEFT, padx=5)
        
        # Wait for dialog to close
        self.root.wait_window(dialog)
        
        # Process the choice
        if choice['value'] == 'text':
            print(f"👤 User chose: Text article")
            
            # Sanitize the text to remove any problematic characters
            import html
            import re
            
            # Decode HTML entities
            clean_text = html.unescape(text_content)
            
            # Remove lines that are just asterisks/dashes/underscores (markdown separator issue)
            lines = clean_text.split('\n')
            filtered_lines = []
            for line in lines:
                stripped = line.strip()
                if stripped and not re.match(r'^[\*\-_]+$', stripped):
                    filtered_lines.append(line)
                elif not stripped:  # Keep blank lines
                    filtered_lines.append(line)
                # else: skip the separator line
            
            clean_text = '\n'.join(filtered_lines)
            
            # Remove control characters
            clean_text = ''.join(char for char in clean_text if char.isprintable() or char in '\n\t\r')
            
            entries = [{
                'text': clean_text,
                'start': 0,
                'timestamp': '[Article]'
            }]
            self._handle_substack_result(True, entries, text_title, 'substack', url)
            
        elif choice['value'] == 'video':
            print(f"👤 User chose: Video transcript")
            self._handle_substack_result(True, video_entries, video_title, 'substack', url)
            
        else:
            print(f"👤 User cancelled")
            self.processing = False
            self.process_btn.config(state=tk.NORMAL)
            self.set_status("Ready")

    def parse_transcript_to_entries(text: str) -> List[Dict]:
        """Parse transcript text with timestamps into entries format"""
        entries = []
        lines = text.split('\n')

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Match format like "[0:00] text" or "[12:34] text"
            import re
            match = re.match(r'\[(\d+:\d+)\]\s*(.+)', line)
            if match:
                timestamp, content = match.groups()
                entries.append({
                    "timestamp": timestamp,
                    "text": content
                })

        return entries

    def _display_substack_result(self, text, title, metadata):
        """Display Substack transcript in UI"""
        print(f"\n{'=' * 60}")
        print(f"🎨 _display_substack_result called!")
        print(f"   Title: {title}")
        print(f"   Text length: {len(text)} chars")
        print(f"   Metadata: {metadata}")
        print(f"{'=' * 60}\n")

        try:

            self.current_document_text = text
            self.current_document_source = metadata.get('url', '')
            self.current_document_id = metadata.get('post_slug', '')
            self.current_document_type = 'substack'
            print(f"✅ Stored text in document variables")

            # Update document library label
            author = metadata.get('author', 'Unknown')
            date = metadata.get('published_date', '')
            entry_count = metadata.get('entry_count', 0)

            doc_label = f"{title}\nAuthor: {author}\nEntries: {entry_count}"
            if date:
                doc_label += f"\nDate: {date}"

            self.doc_library_label.config(text=doc_label)
            print(f"✅ Updated doc library label")

            # Update status
            self.set_status("✅ Document loaded - Select prompt and click Run")
            print(f"✅ Updated status")

            # NOW parse and add to library (after display is done)
            print(f"🔍 Parsing entries for library...")
            try:
                parsed_entries = self.parse_transcript_to_entries(text)
                print(f"✅ Parsed {len(parsed_entries)} entries")
            except Exception as e:
                print(f"⚠️ Parse failed, using empty list: {e}")
                import traceback
                traceback.print_exc()
                parsed_entries = []

            # Add to library
            from document_library import add_document_to_library
            doc_id = add_document_to_library(
                doc_type='substack_transcript',
                source=metadata.get('url', ''),
                title=title,
                entries=parsed_entries,
                document_class='source',
                metadata=metadata
            )
            self.current_document_id = doc_id
            print(f"✅ Added to library with ID: {doc_id}")

            # Refresh library to show in Documents Library
            self.refresh_library()
            print(f"✅ Refreshed library")
            self.update_button_states()
            print(f"✅ Updated button states")

            print(f"\n{'=' * 60}")
            print(f"✅ Substack transcript displayed successfully!")
            print(f"{'=' * 60}\n")

        except Exception as e:
            print(f"\n{'=' * 60}")
            print(f"❌ ERROR in _display_substack_result:")
            print(f"   {str(e)}")
            import traceback
            traceback.print_exc()
            print(f"{'=' * 60}\n")

    def browse_file(self):
        file_path = filedialog.askopenfilename(filetypes=[
            ("All supported files", "*.txt *.doc *.docx *.pdf *.rtf *.xlsx *.xls *.csv *.mp3 *.wav *.m4a *.ogg *.flac *.aac *.wma *.opus *.mp4 *.avi *.mov"),
            ("Text files", "*.txt"),
            ("Word documents", "*.doc *.docx"),
            ("PDF files", "*.pdf"),
            ("RTF files", "*.rtf"),
            ("Spreadsheet files", "*.xlsx *.xls *.csv"),
            ("Audio/Video files", "*.mp3 *.wav *.m4a *.ogg *.flac *.aac *.wma *.opus *.mp4 *.avi *.mov")
        ])
        if file_path:
            self.file_path_var.set(file_path)

    # -------------------------
    # Dictation (Speech-to-Text)
    # -------------------------
    
    def start_dictation(self):
        """Open the dictation dialog to record and transcribe speech."""
        # Show loading status (first import can take a moment)
        self.set_status("🎙️ Loading dictation module...")
        self.root.update()  # Force UI refresh
        
        # Check if transcription module is available
        try:
            from transcription_handler import (
                check_microphone_available,
                check_transcription_availability,
                RECORDING_AVAILABLE
            )
        except ImportError as e:
            self.set_status("")
            messagebox.showerror(
                "Module Not Found",
                f"Transcription module not available:\n{e}\n\n"
                f"Please ensure transcription_handler.py is present."
            )
            return
        
        # Check microphone
        self.set_status("🎙️ Checking microphone...")
        self.root.update()
        
        mic_ok, mic_msg = check_microphone_available()
        if not mic_ok:
            self.set_status("")
            # Show installation instructions
            availability = check_transcription_availability()
            if not availability['recording']['available']:
                messagebox.showerror(
                    "Recording Not Available",
                    f"Microphone recording requires additional libraries.\n\n"
                    f"Install with:\n"
                    f"pip install sounddevice soundfile\n\n"
                    f"Error: {availability['recording']['error']}"
                )
            else:
                messagebox.showerror("Microphone Error", mic_msg)
            return
        
        # Clear status and open dialog
        self.set_status("")
        
        # Open dictation dialog
        from dictation_dialog import DictationDialog
        DictationDialog(self.root, self)

    def open_multi_image_ocr(self):
        """Open the multi-image OCR dialog to process multiple images as one document."""
        # Check OCR availability first
        try:
            available, error_msg, _ = get_ocr().check_ocr_availability()
            if not available:
                # Check if it's just a Poppler issue - cloud mode might still work
                if "POPPLER" in error_msg:
                    if messagebox.askyesno(
                        "Local OCR Unavailable",
                        f"Local OCR tools not fully configured (Poppler missing).\n\n"
                        f"You can still use Cloud AI OCR if you have an API key configured.\n\n"
                        f"Continue with Cloud AI mode?"
                    ):
                        pass  # Continue to open dialog
                    else:
                        return
                elif "TESSERACT" in error_msg:
                    messagebox.showerror(
                        "OCR Not Available",
                        f"Tesseract OCR is not installed.\n\n"
                        f"Please install Tesseract or use Settings to configure\n"
                        f"Cloud AI direct mode for OCR."
                    )
                    return
        except Exception as e:
            # If check fails, let the dialog handle it
            pass
        
        # Open the multi-image OCR dialog
        try:
            from ocr_dialog import MultiImageOCRDialog
            MultiImageOCRDialog(self.root, self)
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            messagebox.showerror(
                "Dialog Error",
                f"Failed to open Multi-Page OCR dialog:\n\n{str(e)}\n\n"
                f"Check the console for details."
            )
            print(f"Multi-Page OCR dialog error:\n{error_details}")

    def _handle_multi_image_ocr_result(self, entries: list, source_files: list):
        """
        Handle the result of multi-image OCR.
        Creates a document entry from the combined OCR text.
        
        NOTE: This may be called from a background thread, so all tkinter 
        operations must be scheduled on the main thread via root.after().
        
        Args:
            entries: List of entry dicts with 'start', 'text', 'location' keys
            source_files: List of original image file paths
        """
        if not entries:
            self.root.after(0, lambda: messagebox.showwarning("No Text", "No text could be extracted from the images."))
            return
        
        # Generate title from first file or timestamp
        import datetime
        if source_files:
            first_file = os.path.basename(source_files[0])
            base_name = os.path.splitext(first_file)[0]
            num_pages = len(source_files)
            title = f"{base_name} ({num_pages} pages)"
        else:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            title = f"Multi-page OCR - {timestamp}"
        
        metadata = {
            "ocr_language": self.config.get("ocr_language", "eng"),
            "ocr_quality": self.config.get("ocr_quality", "balanced"),
            "source_files": [os.path.basename(f) for f in source_files],
            "num_pages": len(source_files)
        }
        
        # Add to library (file I/O - safe from thread)
        total_chars = sum(len(e.get('text', '')) for e in entries)
        print(f"📚 Adding to library: '{title}' ({total_chars:,} chars)")
        doc_id = add_document_to_library(
            doc_type="ocr",
            source=title,
            title=title,
            entries=entries,
            document_class="source",
            metadata=metadata
        )
        
        # Schedule all UI updates on the main thread
        def update_ui():
            failed_step = "unknown"
            try:
                # Step 1: Set current document attributes
                failed_step = "set document attributes"
                self.current_entries = entries
                self.current_document_type = "ocr"
                self.current_document_class = "source"
                self.current_document_source = title
                self.current_document_metadata = metadata
                
                # Step 2: Save current thread if needed
                failed_step = "save_current_thread"
                if self.thread_message_count > 0 and self.current_document_id:
                    self.save_current_thread()
                self.current_thread = []
                self.thread_message_count = 0
                self.current_document_id = doc_id
                
                # Step 3: Update thread status
                failed_step = "update_thread_status"
                self.update_thread_status()
                
                # Step 4: Load saved thread
                failed_step = "load_saved_thread"
                self.load_saved_thread()
                
                # Step 5: Convert entries to text
                failed_step = "entries_to_text"
                self.current_document_text = entries_to_text(
                    self.current_entries, 
                    timestamp_interval=self.config.get("timestamp_interval", "every_segment")
                )
                
                # Step 6: Update context buttons
                failed_step = "update_context_buttons"
                self.update_context_buttons('ocr')
                
                # Step 7: Refresh library
                failed_step = "refresh_library"
                self.refresh_library()
                
                # Step 8: Set status
                failed_step = "set_status"
                self.set_status(f"✅ Multi-page OCR complete: {title}")
                
                # Step 9: Update button states
                failed_step = "update_button_states"
                self.update_button_states()
                
                # Step 10: Show success dialog
                failed_step = "show success dialog"
                messagebox.showinfo(
                    "OCR Complete",
                    f"Successfully processed {len(source_files)} page(s).\n\n"
                    f"Extracted {len(entries)} text segments.\n\n"
                    f"The document has been saved to your library."
                )
            except Exception as e:
                import traceback
                tb_str = traceback.format_exc()
                try:
                    print(f"❌ UI update error at step '{failed_step}': {e}")
                    print(tb_str)
                except Exception:
                    pass
                messagebox.showerror("Error", 
                    f"Document saved to library but UI update failed at step:\n"
                    f"'{failed_step}'\n\n"
                    f"Error: {str(e)}\n\n"
                    f"Traceback (last 400 chars):\n{tb_str[-400:]}")
        
        self.root.after(0, update_ui)

    def _handle_dictation_result(self, text: str, metadata: dict):
        """
        Handle the result of dictation.
        Creates a document entry from the transcribed text.
        """
        if not text or not text.strip():
            messagebox.showwarning("Empty Recording", "No speech was detected in the recording.")
            return
        
        # Create entries from the text
        paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
        if not paragraphs:
            paragraphs = [text.strip()]
        
        entries = []
        for para in paragraphs:
            entries.append({
                'start': 0,
                'text': para,
                'location': f"Dictation ({metadata.get('method', 'unknown')})"
            })
        
        # Set as current document - mark as editable so user can fix transcription errors
        self.current_entries = entries
        self.current_document_type = "dictation"
        self.current_document_class = "product"  # Makes it editable
        self.current_document_metadata = {"editable": True, "method": metadata.get('method', 'unknown')}
        
        # Generate title with timestamp
        import datetime
        timestamp = datetime.datetime.now().strftime("%d %b %Y, %I:%M%p").replace("AM", "am").replace("PM", "pm")
        title = f"Dictation - {timestamp}"
        self.current_document_source = title
        
        # Add to library as editable product
        doc_id = add_document_to_library(
            doc_type="dictation",
            source=title,
            title=title,
            entries=entries,
            document_class="product",  # Editable
            metadata={"editable": True, "method": metadata.get('method', 'unknown')}
        )
        
        # Clear thread (but don't update status yet)
        if self.thread_message_count > 0 and self.current_document_id:
            self.save_current_thread()
        self.current_thread = []
        self.thread_message_count = 0
        self.current_document_id = doc_id
        
        # Display in preview - combine entries into text
        combined_text = "\n\n".join([e['text'] for e in entries])
        self.current_document_text = combined_text  # Store for View Source button
        self.update_context_buttons('dictation')
        
        # Show success dialog
        method = metadata.get('method', 'unknown')
        duration = metadata.get('duration', 0)
        
        messagebox.showinfo(
            "Dictation Complete",
            f"Successfully transcribed {len(entries)} paragraph(s).\n\n"
            f"Method: {method}\n"
            f"Duration: {duration:.1f} seconds\n\n"
            f"The text has been saved to Documents Library and is ready for analysis."
        )
        
        # Update button states
        self.update_button_states()
        
        # Set status AFTER dialog closes - use after() to ensure it's not overwritten
        self.root.after(100, lambda: self.set_status(f"✅ Dictation saved to Documents Library ({duration:.1f}s, {method})"))

    # -------------------------
    # Video Platform Content Fetching (Vimeo, Rumble, etc.)
    # -------------------------
    
    def fetch_video_platform(self, url: str):
        """
        Fetch and transcribe video from supported platforms (Vimeo, Rumble, etc.)
        
        Args:
            url: Video URL from supported platform
        """
        from video_platform_utils import get_platform_name
        
        platform_name = get_platform_name(url)
        print("=" * 60)
        print(f"🎬 fetch_video_platform() called")
        print(f"   Platform: {platform_name}")
        print(f"   URL: {url}")
        
        self.update_context_buttons('video_platform')
        
        # Safety: Force reset processing flag if stuck
        if self.processing:
            if not hasattr(self, 'processing_thread') or self.processing_thread is None or not self.processing_thread.is_alive():
                print("⚠️ Warning: processing flag was stuck, resetting...")
                self.processing = False
        
        if self.processing:
            print("❌ Already processing - showing warning and returning")
            messagebox.showwarning("Warning", "Processing already in progress. Please wait or cancel.")
            return
        
        print("✅ Starting video platform fetch thread...")
        self.processing = True
        self.process_btn.config(state=tk.DISABLED)
        self.set_status(f"Fetching from {platform_name}...")
        
        # Store URL for thread to access
        self.video_platform_url = url
        
        self.processing_thread = threading.Thread(target=self._fetch_video_platform_thread)
        self.processing_thread.start()
        self.root.after(100, self.check_processing_thread)
        print("   Thread started successfully")
        print("=" * 60)
    
    def _fetch_video_platform_thread(self):
        """Background thread for video platform fetching"""
        url = self.video_platform_url
        
        from video_platform_utils import fetch_video_platform_content
        
        # Get transcription options
        options = {
            'language': self.transcription_lang_var.get().strip() or None,
            'speaker_diarization': self.diarization_var.get(),
            'enable_vad': self.config.get("enable_vad", True)
        }
        
        # Fetch and transcribe
        success, result, title, source_type, metadata = fetch_video_platform_content(
            url,
            api_key=self._get_transcription_api_key(),
            engine=self.transcription_engine_var.get(),
            options=options,
            status_callback=self.set_status,
            bypass_cache=self.bypass_cache_var.get() if hasattr(self, 'bypass_cache_var') else False
        )
        
        self.root.after(0, self._handle_video_platform_result, success, result, title, source_type, metadata)
    
    def _handle_video_platform_result(self, success, result, title, source_type, metadata):
        """Handle the result from video platform fetch"""
        try:
            self.processing = False
            self.process_btn.config(state=tk.NORMAL)
            
            if success:
                # result is the transcript entries
                logging.debug("Video platform result handler: success=True")
                self.current_entries = result
                self.current_document_source = self.video_platform_url
                self.current_document_type = source_type
                
                # Build metadata
                doc_metadata = {
                    "source": "video_platform",
                    "platform": metadata.get('platform', 'Unknown'),
                    "title": title,
                    "fetched": datetime.datetime.now().isoformat() + 'Z'
                }
                
                logging.debug("Adding document to library...")
                doc_id = add_document_to_library(
                    doc_type=source_type,
                    source=self.current_document_source,
                    title=title,
                    entries=self.current_entries,
                    document_class="source",
                    metadata=doc_metadata
                )
                logging.debug(f"Document added with ID: {doc_id}")
                
                # Save old thread before changing document
                if self.thread_message_count > 0 and self.current_document_id:
                    self.save_current_thread()
                
                # Clear thread
                self.current_thread = []
                self.thread_message_count = 0
                self.update_thread_status()
                
                # Set new document ID
                self.current_document_id = doc_id
                self.load_saved_thread()
                
                # Get document info
                doc = get_document_by_id(doc_id)
                if doc:
                    self.current_document_class = doc.get("document_class", "source")
                    self.current_document_metadata = doc.get("metadata", {})
                    if 'title' not in self.current_document_metadata and 'title' in doc:
                        self.current_document_metadata['title'] = doc['title']
                else:
                    self.current_document_class = "source"
                    self.current_document_metadata = {}
                
                logging.debug("Converting entries to text...")
                self.current_document_text = entries_to_text(self.current_entries)
                logging.debug(f"Text converted, length: {len(self.current_document_text) if self.current_document_text else 0}")
                
                    
                platform_name = metadata.get('platform', 'Video Platform')
                self.set_status("✅ Document loaded - Select prompt and click Run")
                self.refresh_library()
                
                # Update button states
                self.update_button_states()
                
                logging.debug("Video platform result handler completed successfully")
            else:
                # result is an error message
                logging.debug(f"Video platform result handler: success=False")
                
                # Get platform name for error message
                from video_platform_utils import get_platform_name
                platform_name = get_platform_name(self.video_platform_url)
                
                # Show detailed error with manual download option
                error_title = f"{platform_name} Download Failed"
                error_message = result
                
                # Add helpful context
                full_error = f"{error_message}\n\n"
                
                # Check if this looks like a restriction error
                if any(keyword in result.lower() for keyword in ['private', 'password', '403', 'forbidden', 'restricted', 'disabled']):
                    full_error += "💡 TIP: Try the manual download method:\n\n"
                    full_error += "1. Download the video manually from your browser\n"
                    full_error += "2. Drag & drop the video file into DocAnalyser\n"
                    full_error += "3. Automatic transcription will begin\n\n"
                    full_error += "Need help? Check the platform's website for download options."
                
                self.set_status(f"❌ {platform_name} download failed")
                messagebox.showerror(error_title, full_error)
                
        except Exception as e:
            logging.error(f"EXCEPTION in _handle_video_platform_result: {e}")
            logging.error(traceback.format_exc())
            self.set_status(f"❌ Error: {str(e)}")
            messagebox.showerror("Error", f"Failed to process video: {str(e)}")

    # -------------------------
    # Twitter/X Content Fetching
    # -------------------------
    
    def fetch_twitter(self, url: str):
        """
        Fetch content from a Twitter/X post.
        
        Args:
            url: Twitter/X post URL
        """
        if self.processing:
            messagebox.showwarning("Warning", "Processing already in progress. Please wait or cancel.")
            return
        
        self.processing = True
        self.process_btn.config(state=tk.DISABLED)
        self.set_status("🐦 Fetching X/Twitter content...")
        
        # Run in thread to keep UI responsive
        self.processing_thread = threading.Thread(
            target=self._fetch_twitter_thread,
            args=(url,)
        )
        self.processing_thread.start()
        self.root.after(100, self.check_processing_thread)
    
    def _fetch_twitter_thread(self, url: str):
        """Background thread for fetching Twitter content."""
        try:
            success, result, title = fetch_twitter_content(
                url,
                progress_callback=self.set_status
            )
            self.root.after(0, self._handle_twitter_result, success, result, title, url)
        except Exception as e:
            self.root.after(0, self._handle_twitter_result, False, str(e), "", url)
    
    def _handle_twitter_result(self, success: bool, result, title: str, url: str):
        """Handle the result of Twitter content fetch."""
        self.processing = False
        self.process_btn.config(state=tk.NORMAL)
        
        if success:
            # Check if result is the new dict format (with video detection)
            if isinstance(result, dict):
                has_video = result.get('has_video', False)
                text_content = result.get('formatted_text', result.get('text', ''))
                
                # If video is available, ask user what they want
                if has_video and text_content:
                    self._show_twitter_content_choice(result, title, url)
                    return
                elif has_video and not text_content:
                    # Video only - go straight to transcription
                    self._download_and_transcribe_twitter(url, title)
                    return
                else:
                    # Text only - use formatted text
                    result = text_content
            
            # Text-only path (or legacy string result)
            self._load_twitter_text(result, title, url)
        else:
            # Show error with helpful message and paste option
            self.set_status("❌ Failed to fetch X/Twitter content")
            self._show_paste_fallback_dialog(
                url=url,
                source_type="twitter",
                source_name="X/Twitter"
            )
    
    def _show_twitter_content_choice(self, result: dict, title: str, url: str):
        """Ask user whether they want text content or video transcript."""
        text_content = result.get('formatted_text', result.get('text', ''))
        video_duration = result.get('video_duration', 0)
        
        # Format duration string
        if video_duration:
            mins = int(video_duration) // 60
            secs = int(video_duration) % 60
            duration_str = f"{mins}:{secs:02d}"
        else:
            duration_str = "unknown length"
        
        message = (
            f"This X post contains both text and video:\n\n"
            f"📄 Text Content: ~{len(text_content):,} characters\n"
            f"🎥 Video: {duration_str}\n\n"
            f"Which would you like to load?"
        )
        
        # Custom dialog with buttons
        dialog = tk.Toplevel(self.root)
        dialog.title("Choose Content Type")
        dialog.geometry("450x220")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Center the dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
        
        # Message label
        msg_label = tk.Label(dialog, text=message, justify=tk.LEFT, padx=20, pady=20)
        msg_label.pack()
        
        choice = {'value': None}
        
        def choose_text():
            choice['value'] = 'text'
            dialog.destroy()
        
        def choose_video():
            choice['value'] = 'video'
            dialog.destroy()
        
        def choose_cancel():
            choice['value'] = None
            dialog.destroy()
        
        # Buttons frame
        btn_frame = tk.Frame(dialog)
        btn_frame.pack(pady=10)
        
        text_btn = tk.Button(btn_frame, text="📄 Text Content", command=choose_text, width=15)
        text_btn.pack(side=tk.LEFT, padx=5)
        
        video_btn = tk.Button(btn_frame, text="🎥 Video Transcript", command=choose_video, width=15)
        video_btn.pack(side=tk.LEFT, padx=5)
        
        cancel_btn = tk.Button(btn_frame, text="Cancel", command=choose_cancel, width=10)
        cancel_btn.pack(side=tk.LEFT, padx=5)
        
        # Wait for dialog to close
        self.root.wait_window(dialog)
        
        # Process the choice
        if choice['value'] == 'text':
            print(f"👤 User chose: Text content")
            self._load_twitter_text(text_content, title, url)
            
        elif choice['value'] == 'video':
            print(f"👤 User chose: Video transcript")
            self._download_and_transcribe_twitter(url, title)
            
        else:
            print(f"👤 User cancelled")
            self.set_status("Cancelled")
    
    def _load_twitter_text(self, text_content: str, title: str, url: str):
        """Load Twitter text content as a document."""
        # Create entries from the content
        entries = [{
            'start': 0,
            'text': text_content,
            'location': 'X Post'
        }]
        
        # Set as current document
        self.current_entries = entries
        self.current_document_source = url
        self.current_document_type = "twitter"
        self.current_document_class = "source"
        self.current_document_metadata = {
            "source": "twitter",
            "url": url,
            "fetched": datetime.datetime.now().isoformat() + 'Z'
        }
        
        # Add to library
        total_chars = sum(len(e.get('text', '')) for e in entries)
        print(f"📚 Adding to library: '{title}' ({total_chars:,} chars)")
        doc_id = add_document_to_library(
            doc_type="twitter",
            source=url,
            title=title if title else f"X Post",
            entries=entries,
            document_class="source",
            metadata=self.current_document_metadata
        )
        
        # Clear thread (save first if needed)
        if self.thread_message_count > 0 and self.current_document_id:
            self.save_current_thread()
        self.current_thread = []
        self.thread_message_count = 0
        self.current_document_id = doc_id
        self.update_thread_status()
        
        # Load any saved thread for this document
        self.load_saved_thread()
        
        self.current_document_text = text_content
        self.update_context_buttons('web')  # Use web context buttons
        
        # Refresh library and show success
        self.refresh_library()
        self.set_status("✅ Document loaded - Select prompt and click Run")
        
        # Update button states
        self.update_button_states()
    
    def _download_and_transcribe_twitter(self, url: str, title: str):
        """Download Twitter video and transcribe it."""
        self.processing = True
        self.process_btn.config(state=tk.DISABLED)
        self.set_status("🎥 Downloading X/Twitter video...")
        
        # Run download in thread
        self.processing_thread = threading.Thread(
            target=self._twitter_video_download_thread,
            args=(url, title)
        )
        self.processing_thread.start()
        self.root.after(100, self.check_processing_thread)
    
    def _twitter_video_download_thread(self, url: str, title: str):
        """Background thread for downloading Twitter video."""
        try:
            from twitter_utils import download_twitter_video
            success, result, video_title = download_twitter_video(
                url,
                progress_callback=self.set_status
            )
            
            if success:
                # result is the file path - transcribe it
                self.root.after(0, self._transcribe_twitter_video, result, video_title or title, url)
            else:
                self.root.after(0, self._handle_twitter_video_error, result, url)
                
        except Exception as e:
            self.root.after(0, self._handle_twitter_video_error, str(e), url)
    
    def _transcribe_twitter_video(self, file_path: str, title: str, url: str):
        """Transcribe the downloaded Twitter video."""
        self.set_status("🎤 Transcribing video audio...")
        
        # Store metadata for after transcription
        self._twitter_video_metadata = {
            'original_url': url,
            'title': title
        }
        
        # Set the audio path variable (this is what transcribe_audio() reads)
        self.audio_path_var.set(file_path)
        
        # Also update the universal input for visual feedback
        self.universal_input_entry.delete('1.0', 'end')
        self.universal_input_entry.insert('1.0', file_path)
        self.universal_input_entry.config(foreground='black')
        self.placeholder_active = False
        
        # Reset processing flag so transcribe_audio can start
        self.processing = False
        
        # Trigger transcription
        self.transcribe_audio()
    
    def _handle_twitter_video_error(self, error: str, url: str):
        """Handle Twitter video download/transcription error."""
        self.processing = False
        self.process_btn.config(state=tk.NORMAL)
        self.set_status("❌ Failed to download X/Twitter video")
        
        messagebox.showerror(
            "Video Download Failed",
            f"Could not download video from X/Twitter:\n\n{error}\n\n"
            f"You can try:\n"
            f"• Download the video manually and load it into DocAnalyser\n"
            f"• Use the text content instead"
        )
    
    def _show_paste_fallback_dialog(self, url: str, source_type: str = "web", source_name: str = None):
        """
        Show a dialog offering to paste content manually when automated fetching fails.
        
        This is a general-purpose fallback for any blocked or inaccessible web content
        (Twitter/X, Substack, paywalled articles, etc.)
        
        Args:
            url: The URL that failed to fetch
            source_type: Type identifier for the source (e.g., "twitter", "substack", "web")
            source_name: Human-readable name for the source (e.g., "X/Twitter", "Substack")
        """
        if source_name is None:
            # Try to extract domain name for display
            try:
                from urllib.parse import urlparse
                domain = urlparse(url).netloc.replace('www.', '')
                source_name = domain
            except:
                source_name = "this website"
        
        # Create a custom dialog with options
        dialog = tk.Toplevel(self.root)
        dialog.title("Content Fetch Failed")
        dialog.geometry("480x300")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Center on parent
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 480) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 300) // 2
        dialog.geometry(f"+{x}+{y}")
        
        main_frame = ttk.Frame(dialog, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Warning icon and title
        title_frame = ttk.Frame(main_frame)
        title_frame.pack(fill=tk.X, pady=(0, 15))
        
        ttk.Label(title_frame, text="⚠️", font=('Arial', 24)).pack(side=tk.LEFT)
        ttk.Label(title_frame, text="Could not fetch content automatically", 
                  font=('Arial', 11, 'bold')).pack(side=tk.LEFT, padx=(10, 0))
        
        # Explanation
        explanation = (
            f"The content from {source_name} could not be retrieved automatically. "
            f"This may be due to access restrictions, paywalls, or blocking of automated requests.\n\n"
            f"You can manually copy the content from your browser and paste it here "
            f"to add it to your Documents Library for analysis."
        )
        ttk.Label(main_frame, text=explanation, wraplength=430, 
                  font=('Arial', 10)).pack(anchor=tk.W, pady=(0, 15))
        
        # URL display
        url_frame = ttk.Frame(main_frame)
        url_frame.pack(fill=tk.X, pady=(0, 20))
        ttk.Label(url_frame, text="URL:", font=('Arial', 9, 'bold')).pack(side=tk.LEFT)
        url_display = url[:55] + "..." if len(url) > 55 else url
        ttk.Label(url_frame, text=url_display, font=('Arial', 9), 
                  foreground='#0066CC').pack(side=tk.LEFT, padx=(5, 0))
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        def on_paste_manually():
            dialog.destroy()
            # Open the paste content dialog
            from paste_content_dialog import PasteContentDialog
            PasteContentDialog(
                self.root, 
                self, 
                source_url=url,
                source_type=source_type,
                title="Paste Content Manually",
                prompt_text=(
                    f"Copy the content from {source_name} and paste it below.\n"
                    f"Tip: Select the text in your browser and use Ctrl+C to copy."
                )
            )
        
        def on_cancel():
            dialog.destroy()
        
        # Paste Manually button (primary action)
        paste_btn = ttk.Button(
            button_frame,
            text="📋 Paste Manually",
            command=on_paste_manually,
            width=18
        )
        paste_btn.pack(side=tk.LEFT)
        
        # Cancel button
        cancel_btn = ttk.Button(
            button_frame,
            text="Cancel",
            command=on_cancel,
            width=10
        )
        cancel_btn.pack(side=tk.RIGHT)
        
        # Handle window close
        dialog.protocol("WM_DELETE_WINDOW", on_cancel)

    def fetch_local_file(self):
        print("🔵 DEBUG: fetch_local_file() ENTRY")
        print(f"   processing={self.processing}")
        if self.processing:
            messagebox.showwarning("Warning", "Processing already in progress. Please wait or cancel.")
            return

        file_path = self.file_path_var.get()

        # Validate input
        is_valid, error_msg = self.validate_file_path(file_path)
        if not is_valid:
            messagebox.showerror("Invalid Input", error_msg)
            return

        self.processing = True
        self.process_btn.config(state=tk.DISABLED)
        self.set_status("Loading file...")
        print("🔵 DEBUG: Creating and starting thread...")
        self.processing_thread = threading.Thread(target=self._fetch_local_file_thread)
        self.processing_thread.start()
        print("🔵 DEBUG: Thread started!")
        self.root.after(100, self.check_processing_thread)

    def _fetch_local_file_thread(self):
        print("🟢 DEBUG: _fetch_local_file_thread() STARTED", flush=True)
        try:
            file_path = self.file_path_var.get()
            print(f"🟢 DEBUG: file_path='{file_path}'", flush=True)
            ext = os.path.splitext(file_path)[1].lower()
            # Show file size in status bar for user awareness
            try:
                file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
                if file_size_mb >= 1.0:
                    self.root.after(0, lambda: self.set_status(f"Loading {os.path.basename(file_path)} ({file_size_mb:.1f} MB)..."))
                else:
                    self.root.after(0, lambda: self.set_status(f"Loading {os.path.basename(file_path)}..."))
            except Exception:
                self.root.after(0, lambda: self.set_status(f"Loading {os.path.basename(file_path)}..."))

            # Check for spreadsheet files FIRST
            if ext in ('.xlsx', '.xls', '.csv'):
                print(f"📊 Spreadsheet file detected: {ext}")
                
                # Convert spreadsheet to text
                success, text_content, title, error_msg = self.convert_spreadsheet_to_text(file_path)
                
                if not success:
                    self.root.after(0, lambda: messagebox.showerror("Spreadsheet Error", error_msg))
                    self.root.after(0, lambda: setattr(self, 'processing', False))
                    self.root.after(0, lambda: self.process_btn.config(state=tk.NORMAL))
                    return
                
                # Update context buttons
                self.root.after(0, lambda: self.update_context_buttons('spreadsheet'))
                
                # Handle as regular text document
                self.root.after(0, self._handle_spreadsheet_result, text_content, title, file_path)
                return

            # Check for image files FIRST
            if ext in ('.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp', '.gif'):
                print(f"🖼️ Image file detected: {ext}")
                # Notify about image file
                self.root.after(0, lambda: self.update_context_buttons('image'))
                # Call document_fetcher which will return IMAGE_FILE code
                success, result, title, doc_type = get_doc_fetcher().fetch_local_file(file_path)
                self.root.after(0, self._handle_file_result, success, result, title)
                return

            if ext in ('.mp3', '.wav', '.m4a', '.ogg', '.flac', '.aac', '.wma', '.opus', '.mp4', '.avi', '.mov'):
                self.root.after(0, lambda: self.audio_path_var.set(file_path))
                self.root.after(0, lambda: self.update_context_buttons('audio'))
                self.root.after(0, self.transcribe_audio)
                return

            print(f"🟢 Checking if PDF is scanned...", flush=True)
            if ext == '.pdf':
                self.root.after(0, lambda: self.set_status("Checking PDF type..."))
                print(f"🟢 Calling get_ocr().is_pdf_scanned()...", flush=True)
                # Use timeout to prevent hanging on complex PDFs
                import concurrent.futures
                executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                try:
                    future = executor.submit(get_ocr().is_pdf_scanned, file_path)
                    is_scanned = future.result(timeout=15)  # 15 second timeout
                except concurrent.futures.TimeoutError:
                    print("🟠 WARNING: is_pdf_scanned timed out after 15s - treating as scanned", flush=True)
                    is_scanned = True  # Assume scanned if check hangs
                    future.cancel()
                except Exception as e:
                    print(f"🟠 WARNING: is_pdf_scanned error: {e}", flush=True)
                    is_scanned = False
                finally:
                    executor.shutdown(wait=False)
                print(f"🟢 is_pdf_scanned returned: {is_scanned}", flush=True)
            else:
                is_scanned = False
            if ext == '.pdf' and is_scanned:

                # 🆕 UPDATE: Notify context buttons about PDF detection
                # Must use root.after() since we're in a background thread
                self.root.after(0, lambda: self.update_context_buttons('pdf_scanned'))

                # 🆕 NEW: Check if cache exists BEFORE prompting user
                force_reprocess = self.force_reprocess_var.get()
                # Reset force_reprocess so it doesn't persist for future loads
                self.root.after(0, lambda: self.force_reprocess_var.set(False))

                # Check for cached OCR results (to offer as option, not to load silently)
                from ocr_handler import load_cached_ocr, get_ocr_cache_path
                cached = None
                ocr_quality = self.config.get("ocr_quality", "balanced")
                ocr_language = self.config.get("ocr_language", "eng")
                print(f"\n🔵 CACHE CHECK: file='{file_path}', quality='{ocr_quality}', language='{ocr_language}'", flush=True)
                cache_path = get_ocr_cache_path(file_path, ocr_quality, ocr_language)
                print(f"🔵 CACHE CHECK: expected cache file = '{cache_path}'", flush=True)
                print(f"🔵 CACHE CHECK: cache file exists = {os.path.exists(cache_path)}", flush=True)
                if not force_reprocess:
                    cached = get_ocr().load_cached_ocr(
                        file_path,
                        ocr_quality,
                        ocr_language
                    )
                    print(f"🔵 CACHE CHECK: load_cached_ocr returned {type(cached).__name__}, is None={cached is None}", flush=True)

                # Store cached data so the dialog can offer it as an option
                self._cached_ocr_data = cached

                if force_reprocess:
                    print("🔄 Force reprocess - skipping cache, will show OCR prompt")
                elif cached:
                    print("📦 Cache found - will offer choice: re-scan or use cached")
                else:
                    print("📭 No cache found - will show OCR prompt")

                # Always show OCR prompt (default to re-processing)
                success, result, title = False, "SCANNED_PDF", os.path.basename(file_path)
                self.root.after(0, self._handle_ocr_fetch, success, result, title)
                return

            print("🟣 DEBUG: Calling get_doc_fetcher().fetch_local_file()...")
            success, result, title, doc_type = get_doc_fetcher().fetch_local_file(file_path)
            print(f"🟣 DEBUG: Returned success={success}, title='{title}'")
            print("🟣 DEBUG: Scheduling _handle_file_result...")
            self.root.after(0, self._handle_file_result, success, result, title)
            print("🟣 DEBUG: Scheduled!")

            if ext in ('.txt', '.doc', '.docx', '.rtf'):
                # Must use root.after() since we're in a background thread
                self.root.after(0, lambda: self.update_context_buttons('document'))
                
        except Exception as e:
            import traceback
            import sys
            print("\n" + "🔴"*30, flush=True)
            print(f"🔴 EXCEPTION in _fetch_local_file_thread: {e}", flush=True)
            print("🔴"*30, flush=True)
            traceback.print_exc()
            sys.stdout.flush()
            error_msg = f"Error in _fetch_local_file_thread: {str(e)}\n{traceback.format_exc()}"
            print(error_msg, flush=True)
            self.root.after(0, lambda: messagebox.showerror("Error", f"File processing error: {str(e)}"))
            self.root.after(0, lambda: setattr(self, 'processing', False))

    def _load_cached_ocr_directly(self, cached_entries, title):
        """Load OCR results directly from cache without prompting user"""
        self.processing = False
        self.process_btn.config(state=tk.NORMAL)

        self.current_entries = cached_entries
        self.current_document_source = self.file_path_var.get()
        self.current_document_type = "ocr"

        # Add to document library
        doc_id = add_document_to_library(
            doc_type="ocr",
            source=self.current_document_source,
            title=title,
            entries=self.current_entries,
            document_class="source",
            metadata={
                "ocr_language": self.config.get("ocr_language", "eng"),
                "ocr_quality": self.config.get("ocr_quality", "balanced")
            }
        )
        # ✅ FIX: Save old thread BEFORE changing document ID
        if self.thread_message_count > 0 and self.current_document_id:
            self.save_current_thread()
        
        # Clear thread manually
        self.current_thread = []
        self.thread_message_count = 0
        self.update_thread_status()
        
        # NOW change the document ID
        self.current_document_id = doc_id

        # Get document class and metadata from library
        doc = get_document_by_id(doc_id)
        if doc:
            self.current_document_class = doc.get("document_class", "source")
            self.current_document_metadata = doc.get("metadata", {})
        else:
            self.current_document_class = "source"
            self.current_document_metadata = {}

        self.current_document_text = entries_to_text(self.current_entries,
                                                     timestamp_interval=self.config.get("timestamp_interval",
                                                                                        "every_segment"))

        self.set_status("✅ Source document loaded from cache")
        self.refresh_library()
        
        # Update button states
        self.update_button_states()

    def _handle_file_result(self, success, result, title):
        print("🟡 DEBUG: _handle_file_result() CALLED")
        print(f"   success={success}, title='{title}'")
        try:
            self.processing = False
            print("🟡 DEBUG: Set processing=False")
            self.process_btn.config(state=tk.NORMAL)
            if success:
                logging.debug(f"File result handler: success=True, title={title}")
                self.current_entries = result
                self.current_document_source = self.file_path_var.get()
                self.current_document_type = "file"
                
                logging.debug("Adding document to library...")
                doc_id = add_document_to_library(
                    doc_type="file",
                    source=self.current_document_source,
                    title=title,
                    entries=self.current_entries
                )
                logging.debug(f"Document added with ID: {doc_id}")
                
                # ✅ FIX: Save old thread BEFORE changing document ID
                if self.thread_message_count > 0 and self.current_document_id:
                    self.save_current_thread()
                
                # Clear thread manually
                self.current_thread = []
                self.thread_message_count = 0
                self.update_thread_status()
                
                # NOW change the document ID
                self.current_document_id = doc_id
                # 🆕 Load saved thread if exists
                self.load_saved_thread()
                
                # Get document class and metadata from library
                logging.debug("Getting document from library...")
                doc = get_document_by_id(doc_id)
                if doc:
                    self.current_document_class = doc.get("document_class", "source")
                    self.current_document_metadata = doc.get("metadata", {})
                    # CRITICAL FIX: Add title to metadata if not already there
                    if 'title' not in self.current_document_metadata and 'title' in doc:
                        self.current_document_metadata['title'] = doc['title']
                else:
                    self.current_document_class = "source"
                    self.current_document_metadata = {}

                logging.debug("Converting entries to text...")
                self.current_document_text = entries_to_text(self.current_entries, timestamp_interval=self.config.get("timestamp_interval", "every_segment"))
                logging.debug(f"Text converted, length: {len(self.current_document_text) if self.current_document_text else 0}")

                # Preview display removed - content stored in current_document_text

                self.set_status("✅ Document loaded - Select prompt and click Run")
                self.refresh_library()
                
                # Update button states
                self.update_button_states()
                
                logging.debug("File result handler completed successfully")
            else:
                logging.debug(f"File result handler: success=False, result={result}")
                # Check for special codes that need different handling
                if result == "IMAGE_FILE":
                    # Image file detected - route to OCR
                    if messagebox.askyesno("OCR Processing",
                                          "This is an image file. Would you like to extract text using OCR?"):
                        self.process_ocr()
                    else:
                        self.set_status("Cancelled OCR processing")
                elif result == "SCANNED_PDF":
                    # Scanned PDF detected - offer OCR
                    if messagebox.askyesno("OCR Required",
                                          "This PDF appears to be scanned. Would you like to process it with OCR?"):
                        self.process_ocr()
                    else:
                        self.set_status("Cancelled OCR processing")
                else:
                    # Regular error
                    self.set_status(f"❌ Error: {result}")
                    messagebox.showerror("Error", result)
        except Exception as e:
            logging.error(f"EXCEPTION in _handle_file_result: {e}")
            logging.error(traceback.format_exc())
            self.set_status(f"❌ Error: {str(e)}")
            messagebox.showerror("Error", f"Failed to process file: {str(e)}")

    def _handle_spreadsheet_result(self, text_content, title, file_path):
        """Handle loaded spreadsheet data"""
        try:
            self.processing = False
            self.process_btn.config(state=tk.NORMAL)
            
            # Store as plain text document
            self.current_document_source = file_path
            self.current_document_type = "spreadsheet"
            self.current_document_text = text_content
            
            # Convert text to entries format (single entry containing all spreadsheet data)
            entries = [{
                "text": text_content,
                "start": 0,
                "end": len(text_content),
                "metadata": {"type": "spreadsheet_data"}
            }]
            
            # Store entries for library
            self.current_entries = entries
            
            # Add to document library
            doc_id = add_document_to_library(
                doc_type="spreadsheet",
                source=file_path,
                title=title,
                entries=entries,
                document_class="source",
                metadata={"file_type": "spreadsheet"}
            )
            
            # Save old thread before changing document
            if self.thread_message_count > 0 and self.current_document_id:
                self.save_current_thread()
            
            # Clear thread
            self.current_thread = []
            self.thread_message_count = 0
            self.update_thread_status()
            
            # Set new document ID
            self.current_document_id = doc_id
            self.load_saved_thread()
            
            # Get document info
            doc = get_document_by_id(doc_id)
            if doc:
                self.current_document_class = doc.get("document_class", "source")
                self.current_document_metadata = doc.get("metadata", {})
                if 'title' not in self.current_document_metadata and 'title' in doc:
                    self.current_document_metadata['title'] = doc['title']
            else:
                self.current_document_class = "source"
                self.current_document_metadata = {}
            
            
            self.set_status("✅ Document loaded - Select prompt and click Run")
            self.refresh_library()
            
            # Update button states
            self.update_button_states()
            
        except Exception as e:
            logging.error(f"Error in _handle_spreadsheet_result: {e}")
            logging.error(traceback.format_exc())
            self.set_status(f"❌ Error loading spreadsheet: {str(e)}")
            messagebox.showerror("Error", f"Failed to load spreadsheet: {str(e)}")

