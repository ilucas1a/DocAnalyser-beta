"""
ocr_processing.py - OCR processing and web content fetching for DocAnalyser.

Handles OCR text type dialogs, cloud AI escalation, OCR threading,
web page fetching, web video processing, and web PDF OCR.

Extracted from Main.py to reduce file size. Uses a mixin pattern so all
self.xxx references continue to work unchanged.
"""

from __future__ import annotations

import os
import re
import datetime
import logging
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from document_library import add_document_to_library, get_document_by_id
from utils import entries_to_text

# Lazy module loaders (mirrors Main.py pattern)
def get_ocr():
    import ocr_handler
    return ocr_handler

def get_doc_fetcher():
    import document_fetcher
    return document_fetcher


class OCRProcessingMixin:
    """Mixin class providing OCR processing and web fetching methods for DocAnalyzerApp."""

    def _handle_ocr_fetch(self, success, result, title):
        self.processing = False
        self.process_btn.config(state=tk.NORMAL)
        print(f"\n🔵 _handle_ocr_fetch called: success={success}, result='{result}', title='{title}'", flush=True)
        if result == "SCANNED_PDF":
            cached = getattr(self, '_cached_ocr_data', None)
            print(f"🔵 _handle_ocr_fetch: cached={type(cached).__name__}, is None={cached is None}, bool={bool(cached) if cached is not None else 'N/A'}", flush=True)

            if cached:
                # Cache exists - offer choice: re-scan, use cached, or cancel
                answer = messagebox.askyesnocancel(
                    "Scanned PDF — OCR Options",
                    "This PDF has been scanned before.\n\n"
                    "• Yes — Re-scan with OCR (choose Printed or Handwriting)\n"
                    "• No — Use previous OCR results\n"
                    "• Cancel — Do nothing"
                )
                self._cached_ocr_data = None  # Clear stored cache reference
                if answer is True:     # Yes → re-scan
                    self.process_ocr()
                elif answer is False:  # No → use cached
                    self._load_cached_ocr_directly(cached, title)
                else:                  # Cancel
                    self.set_status("Cancelled OCR processing")
            else:
                # No cache - standard prompt
                if messagebox.askyesno("OCR Required",
                                       "This PDF appears to be scanned. Would you like to process it with OCR?"):
                    self.process_ocr()
                else:
                    self.set_status("Cancelled OCR processing")
        else:
            self.set_status(f"❌ Error: {result}")
            messagebox.showerror("Error", result)

    def process_ocr(self):
        file_path = self.file_path_var.get()
        if not file_path or not os.path.exists(file_path):
            messagebox.showerror("Error", "Please select a valid PDF file.")
            return
        available, error_msg, _ = get_ocr().check_ocr_availability()
        if not available:
            self.set_status(f"❌ OCR unavailable: {error_msg}")
            messagebox.showerror("OCR Error", error_msg)
            return
        self.processing = True
        self.process_btn.config(state=tk.DISABLED)
        self.set_status("Processing OCR...")
        self.processing_thread = threading.Thread(target=self._process_ocr_thread)
        self.processing_thread.start()
        self.root.after(100, self.check_processing_thread)

    def _ask_text_type(self, image_path=None):
        """
        Ask user what type of text is in the image: Printed or Handwriting.
        Auto-detects based on OCR confidence and pre-selects accordingly.
        Returns "printed" or "handwriting".
        This is called from a background thread, so we need to use threading events.
        """
        import threading
        
        result = ["printed"]  # Default to printed
        event = threading.Event()
        
        # Auto-detect handwriting if we have a path
        likely_handwriting = False
        confidence = 100
        if image_path and os.path.exists(image_path):
            try:
                confidence, likely_handwriting = self._check_ocr_confidence(image_path)
            except Exception as e:
                print(f"⚠️ Auto-detection failed: {e}")
        
        def ask():
            try:
                # Create dialog
                dialog = tk.Toplevel(self.root)
                dialog.title("Text Type")
                dialog.geometry("450x260")
                dialog.resizable(False, False)
                dialog.transient(self.root)
                dialog.grab_set()
                self.style_dialog(dialog)
                
                # Center on parent
                dialog.update_idletasks()
                x = self.root.winfo_x() + (self.root.winfo_width() - 450) // 2
                y = self.root.winfo_y() + (self.root.winfo_height() - 260) // 2
                dialog.geometry(f"+{x}+{y}")
                
                # Question
                ttk.Label(
                    dialog,
                    text="What type of text is in this image?",
                    font=('Arial', 11)
                ).pack(pady=(15, 5))
                
                # Auto-detection status
                threshold = self.config.get("ocr_confidence_threshold", 70)
                if likely_handwriting:
                    status_text = f"⚠️ Low OCR confidence ({confidence:.0f}%) - handwriting detected"
                    status_color = '#CC6600'
                else:
                    status_text = f"✓ Good OCR confidence ({confidence:.0f}%) - likely printed text"
                    status_color = '#006600'
                
                ttk.Label(
                    dialog,
                    text=status_text,
                    font=('Arial', 9),
                    foreground=status_color
                ).pack(pady=(0, 10))
                
                # Check if vision is supported
                vision_supported, current_provider = self._provider_supports_vision()
                
                # Show provider status
                if vision_supported:
                    provider_text = f"✅ {current_provider} supports vision AI"
                    provider_color = '#006600'
                else:
                    provider_text = f"⚠️ {current_provider} does not support vision AI"
                    provider_color = '#CC0000'
                
                ttk.Label(
                    dialog,
                    text=provider_text,
                    font=('Arial', 9),
                    foreground=provider_color
                ).pack(pady=(0, 10))
                
                # Buttons frame
                btn_frame = ttk.Frame(dialog)
                btn_frame.pack(pady=10)
                
                def select_printed():
                    result[0] = "printed"
                    dialog.destroy()
                
                def select_handwriting():
                    print(f"🔵 select_handwriting() called! vision_supported={vision_supported}", flush=True)
                    # Check if vision is supported
                    if not vision_supported:
                        messagebox.showwarning(
                            "⚠️ Vision AI Not Available",
                            f"Your current AI provider ({current_provider}) does not support "
                            f"vision/image processing needed for handwriting recognition.\n\n"
                            f"To proceed, please:\n\n"
                            f"  • Change 'AI Provider' in the main window to:\n"
                            f"      → OpenAI (uses GPT-4o) - Best for handwriting\n"
                            f"      → Anthropic (uses Claude)\n"
                            f"      → Google (uses Gemini)\n"
                            f"  • Make sure you have an API key entered\n"
                            f"  • Try loading the file again\n\n"
                            f"Or select 'Printed Text' to use free local OCR\n"
                            f"(works for printed text only)."
                        )
                        return  # Cannot proceed without vision support
                    result[0] = "handwriting"
                    print(f"🔵 result[0] set to '{result[0]}' - dialog closing", flush=True)
                    dialog.destroy()
                
                printed_btn = ttk.Button(
                    btn_frame,
                    text="📄 Printed Text (Free OCR)",
                    command=select_printed,
                    width=22
                )
                printed_btn.pack(side=tk.LEFT, padx=10)
                
                handwriting_btn = ttk.Button(
                    btn_frame,
                    text="✍️ Handwriting (AI Vision)",
                    command=select_handwriting,
                    width=22
                )
                handwriting_btn.pack(side=tk.LEFT, padx=10)
                
                # Highlight recommended option based on detection AND vision support
                if likely_handwriting and vision_supported:
                    handwriting_btn.focus_set()
                else:
                    printed_btn.focus_set()
                
                # Settings hint
                hint_line1 = f"AI vision recommended if OCR accuracy falls below {threshold}%."
                hint_line2 = "To adjust threshold, go to Settings → OCR Settings."
                ttk.Label(
                    dialog,
                    text=hint_line1 + "\n" + hint_line2,
                    font=('Arial', 8, 'italic'),
                    foreground='#888888',
                    justify=tk.CENTER
                ).pack(pady=(15, 10))
                
                # Handle window close (use recommended)
                def on_close():
                    result[0] = "handwriting" if likely_handwriting else "printed"
                    dialog.destroy()
                
                dialog.protocol("WM_DELETE_WINDOW", on_close)
                
                # Wait for dialog to close
                dialog.wait_window()
            finally:
                event.set()
        
        # Schedule dialog in main thread
        self.root.after(0, ask)
        
        # Wait for dialog to complete
        event.wait(timeout=120)
        
        return result[0]


    def _ask_text_type_pdf(self, pdf_path=None):
        """
        Ask user what type of text is in the PDF: Printed or Handwriting.
        Auto-detects based on OCR confidence of first page.
        Returns "printed" or "handwriting".
        This is called from a background thread, so we need to use threading events.
        """
        import threading
        import tempfile
        
        result = ["printed"]  # Default to printed
        event = threading.Event()
        
        # Auto-detect handwriting by checking first page
        likely_handwriting = False
        confidence = 100
        
        if pdf_path and os.path.exists(pdf_path):
            try:
                # Convert first page to image for confidence check
                from pdf2image import convert_from_path
                import concurrent.futures
                print(f"🟢 _ask_text_type_pdf: converting first page for confidence check...", flush=True)
                self.set_status("Analysing PDF for handwriting...")
                executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                try:
                    future = executor.submit(convert_from_path, pdf_path, first_page=1, last_page=1, dpi=150)
                    images = future.result(timeout=30)  # 30 second timeout for Poppler
                finally:
                    executor.shutdown(wait=False)
                print(f"🟢 _ask_text_type_pdf: conversion done, {len(images)} images", flush=True)
                if images:
                    # Save temp image
                    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                        images[0].save(tmp.name, 'PNG')
                        confidence, likely_handwriting = self._check_ocr_confidence(tmp.name)
                        os.unlink(tmp.name)
            except concurrent.futures.TimeoutError:
                print(f"⚠️ PDF confidence check timed out - defaulting to handwriting likely", flush=True)
                likely_handwriting = True
                confidence = 40
            except Exception as e:
                print(f"⚠️ PDF auto-detection failed: {e}", flush=True)
        
        def ask():
            try:
                # Create dialog
                dialog = tk.Toplevel(self.root)
                dialog.title("PDF Text Type")
                dialog.geometry("450x260")
                dialog.resizable(False, False)
                dialog.transient(self.root)
                dialog.grab_set()
                self.style_dialog(dialog)
                
                # Center on parent
                dialog.update_idletasks()
                x = self.root.winfo_x() + (self.root.winfo_width() - 450) // 2
                y = self.root.winfo_y() + (self.root.winfo_height() - 260) // 2
                dialog.geometry(f"+{x}+{y}")
                
                # Question
                ttk.Label(
                    dialog,
                    text="What type of text is in this PDF?",
                    font=('Arial', 11)
                ).pack(pady=(15, 5))
                
                # Auto-detection status
                threshold = self.config.get("ocr_confidence_threshold", 70)
                if likely_handwriting:
                    status_text = f"⚠️ Low OCR confidence ({confidence:.0f}%) - handwriting likely"
                    status_color = '#CC6600'
                else:
                    status_text = f"✓ Good OCR confidence ({confidence:.0f}%) - likely printed text"
                    status_color = '#006600'
                
                ttk.Label(
                    dialog,
                    text=status_text,
                    font=('Arial', 9),
                    foreground=status_color
                ).pack(pady=(0, 10))
                
                # Check if vision is supported
                vision_supported, current_provider = self._provider_supports_vision()
                
                # Show provider status
                if vision_supported:
                    provider_text = f"✅ {current_provider} supports vision AI"
                    provider_color = '#006600'
                else:
                    provider_text = f"⚠️ {current_provider} does not support vision AI"
                    provider_color = '#CC0000'
                
                ttk.Label(
                    dialog,
                    text=provider_text,
                    font=('Arial', 9),
                    foreground=provider_color
                ).pack(pady=(0, 10))
                
                # Buttons frame
                btn_frame = ttk.Frame(dialog)
                btn_frame.pack(pady=10)
                
                def select_printed():
                    result[0] = "printed"
                    dialog.destroy()
                
                def select_handwriting():
                    # Check if vision is supported
                    if not vision_supported:
                        messagebox.showwarning(
                            "⚠️ Vision AI Not Available",
                            f"Your current AI provider ({current_provider}) does not support "
                            f"vision/image processing needed for handwriting recognition.\n\n"
                            f"To proceed, please:\n\n"
                            f"  • Change 'AI Provider' in the main window to:\n"
                            f"      → OpenAI (uses GPT-4o) - Best for handwriting\n"
                            f"      → Anthropic (uses Claude)\n"
                            f"      → Google (uses Gemini)\n"
                            f"  • Make sure you have an API key entered\n"
                            f"  • Try loading the file again\n\n"
                            f"Or select 'Printed Text' to use free local OCR\n"
                            f"(works for printed text only)."
                        )
                        return  # Cannot proceed without vision support
                    result[0] = "handwriting"
                    dialog.destroy()
                
                printed_btn = ttk.Button(
                    btn_frame,
                    text="📄 Printed Text (Free OCR)",
                    command=select_printed,
                    width=22
                )
                printed_btn.pack(side=tk.LEFT, padx=10)
                
                handwriting_btn = ttk.Button(
                    btn_frame,
                    text="✍️ Handwriting (AI Vision)",
                    command=select_handwriting,
                    width=22
                )
                handwriting_btn.pack(side=tk.LEFT, padx=10)
                
                # Highlight recommended option based on detection AND vision support
                if likely_handwriting and vision_supported:
                    handwriting_btn.focus_set()
                else:
                    printed_btn.focus_set()
                
                # Settings hint
                hint_line1 = f"AI vision recommended if OCR accuracy falls below {threshold}%."
                hint_line2 = "To adjust threshold, go to Settings → OCR Settings."
                ttk.Label(
                    dialog,
                    text=hint_line1 + "\n" + hint_line2,
                    font=('Arial', 8, 'italic'),
                    foreground='#888888',
                    justify=tk.CENTER
                ).pack(pady=(15, 10))
                
                # Handle window close (use recommended)
                def on_close():
                    result[0] = "handwriting" if likely_handwriting else "printed"
                    dialog.destroy()
                
                dialog.protocol("WM_DELETE_WINDOW", on_close)
                
                # Wait for dialog to close
                dialog.wait_window()
            finally:
                event.set()
        
        # Schedule dialog in main thread
        self.root.after(0, ask)
        
        # Wait for dialog to complete
        event.wait(timeout=120)
        
        print(f"🔵 _ask_text_type_pdf RETURNING: '{result[0]}'", flush=True)
        return result[0]


    def _ask_cloud_ai_escalation(self, confidence, provider, model):
        """
        Ask user if they want to retry OCR with Cloud AI after low confidence local result.
        Returns True if user wants to escalate, False otherwise.
        This is called from a background thread, so we need to use threading events.
        """
        import threading
        
        result = [False]  # Use list to allow modification in nested function
        event = threading.Event()
        
        def ask():
            try:
                response = messagebox.askyesno(
                    "Low OCR Confidence",
                    f"Local OCR confidence is low ({confidence:.1f}%).\n\n"
                    f"The result may be unreliable, especially for handwriting.\n\n"
                    f"Would you like to retry with Cloud AI ({provider})?\n\n"
                    f"This will use your API key and may incur a small cost.",
                    icon='question'
                )
                result[0] = response
            finally:
                event.set()  # Signal that dialog is complete
        
        # Schedule dialog in main thread
        self.root.after(0, ask)
        
        # Wait for dialog to complete (with timeout)
        event.wait(timeout=120)  # 2 minute timeout
        
        return result[0]

    def _ask_text_type_for_image(self):
        """
        Ask user what type of text is in the image (Printed or Handwriting).
        Returns "printed" or "handwriting".
        This is called from a background thread, so we need to use threading events.
        """
        import threading
        
        result = ["printed"]  # Default to printed
        event = threading.Event()
        
        def ask():
            try:
                # Create a simple popup dialog
                popup = tk.Toplevel(self.root)
                popup.title("Text Type")
                popup.geometry("300x120")
                popup.resizable(False, False)
                popup.transient(self.root)
                popup.grab_set()
                
                # Center on parent
                popup.update_idletasks()
                x = self.root.winfo_x() + (self.root.winfo_width() - 300) // 2
                y = self.root.winfo_y() + (self.root.winfo_height() - 120) // 2
                popup.geometry(f"+{x}+{y}")
                
                # Question label
                ttk.Label(
                    popup,
                    text="What type of text is in this image?",
                    font=('Arial', 11)
                ).pack(pady=(20, 15))
                
                # Button frame
                btn_frame = ttk.Frame(popup)
                btn_frame.pack(pady=5)
                
                def select_printed():
                    result[0] = "printed"
                    popup.destroy()
                    event.set()
                
                def select_handwriting():
                    result[0] = "handwriting"
                    popup.destroy()
                    event.set()
                
                ttk.Button(
                    btn_frame,
                    text="📄 Printed Text",
                    command=select_printed,
                    width=15
                ).pack(side=tk.LEFT, padx=10)
                
                ttk.Button(
                    btn_frame,
                    text="✍️ Handwriting",
                    command=select_handwriting,
                    width=15
                ).pack(side=tk.LEFT, padx=10)
                
                # Handle window close (default to printed)
                def on_close():
                    result[0] = "printed"
                    popup.destroy()
                    event.set()
                
                popup.protocol("WM_DELETE_WINDOW", on_close)
                
            except Exception as e:
                print(f"Text type dialog error: {e}")
                event.set()
        
        # Schedule dialog in main thread
        self.root.after(0, ask)
        
        # Wait for dialog to complete (with timeout)
        event.wait(timeout=120)  # 2 minute timeout
        
        return result[0]

    def _process_image_with_cloud_ai(self, image_path, title):
        """
        Process a single image using the smart OCR router.
        Routes to Cloud Vision (printed) or Vision AI (handwriting) based on settings.
        Returns (success, entries_or_error)
        """
        from ocr_handler import ocr_image_smart
        
        # Get settings
        text_type = self.config.get("ocr_text_type", "printed")
        language = self.config.get("ocr_language", "eng")
        quality = self.config.get("ocr_quality", "balanced")
        
        # Get API keys
        cloud_vision_key = self.config.get("keys", {}).get("Google Cloud Vision", "")
        
        # For handwriting, use the selected AI provider
        provider = self.provider_var.get()
        model = self.model_var.get()
        vision_api_key = self.config.get("keys", {}).get(provider, "")
        
        success, result, method = ocr_image_smart(
            image_path=image_path,
            text_type=text_type,
            language=language,
            quality=quality,
            cloud_vision_api_key=cloud_vision_key,
            vision_provider=provider,
            vision_model=model,
            vision_api_key=vision_api_key,
            document_title=title,
            progress_callback=self.set_status
        )
        
        if success:
            # Format as entries
            entries = [{
                'location': f'Image ({method})',
                'text': result.strip()
            }]
            return True, entries
        else:
            return False, result

    def _process_pdf_with_cloud_ai(self, pdf_path, title, text_type="handwriting"):
        """
        Process a scanned PDF using the smart OCR router (page by page).
        Routes to Cloud Vision (printed) or Vision AI (handwriting) based on text_type.
        Returns (success, entries_or_error)
        """
        from pdf2image import convert_from_path
        from ocr_handler import ocr_image_smart
        import tempfile
        
        # Get settings
        # text_type is now passed as parameter from the user's dialog choice
        language = self.config.get("ocr_language", "eng")
        quality = self.config.get("ocr_quality", "balanced")
        
        # Get API keys
        cloud_vision_key = self.config.get("keys", {}).get("Google Cloud Vision", "")
        
        # For handwriting, use the selected AI provider
        provider = self.provider_var.get()
        model = self.model_var.get()
        vision_api_key = self.config.get("keys", {}).get(provider, "")
        
        # Check if at least one OCR method is available
        if not cloud_vision_key and (not vision_api_key or vision_api_key == "not-required"):
            return False, "No OCR service configured. Add Google Cloud Vision key or AI provider API key in Settings."
        
        try:
            self.set_status("Converting PDF pages to images...")
            print(f"🟢 _process_pdf_with_cloud_ai: converting PDF to images (dpi=200)...", flush=True)
            
            # Raise Pillow's decompression bomb limit for large scanned pages
            # This is safe because the user deliberately loaded this file
            from PIL import Image as PILImage
            old_max_pixels = PILImage.MAX_IMAGE_PIXELS
            PILImage.MAX_IMAGE_PIXELS = 500_000_000  # ~500MP (raised from 178MP default)
            
            import concurrent.futures as cf
            try:
                with cf.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(convert_from_path, pdf_path, dpi=200)
                    images = future.result(timeout=60)  # 60 second timeout for full PDF conversion
            except cf.TimeoutError:
                print(f"🔴 convert_from_path timed out after 60s", flush=True)
                PILImage.MAX_IMAGE_PIXELS = old_max_pixels  # Restore limit
                return False, "PDF to image conversion timed out. The PDF may be too large or Poppler may not be responding."
            except Exception as conv_err:
                # If still too large even with raised limit, try lower DPI
                if 'decompression bomb' in str(conv_err).lower() or 'exceeds limit' in str(conv_err).lower():
                    print(f"🟠 DPI 200 too large, retrying at 150 DPI...", flush=True)
                    self.set_status("Large PDF — retrying at lower resolution...")
                    try:
                        with cf.ThreadPoolExecutor(max_workers=1) as executor:
                            future = executor.submit(convert_from_path, pdf_path, dpi=150)
                            images = future.result(timeout=60)
                    except Exception as retry_err:
                        PILImage.MAX_IMAGE_PIXELS = old_max_pixels
                        return False, f"PDF pages too large even at reduced resolution: {str(retry_err)}"
                else:
                    PILImage.MAX_IMAGE_PIXELS = old_max_pixels
                    raise
            PILImage.MAX_IMAGE_PIXELS = old_max_pixels  # Restore limit after conversion
            total_pages = len(images)
            print(f"🟢 _process_pdf_with_cloud_ai: {total_pages} pages converted", flush=True)
            self.set_status(f"Processing {total_pages} pages with Cloud AI (text_type={text_type})...")
            
            entries = []
            
            for page_num, image in enumerate(images, start=1):
                self.set_status(f"🤖 Cloud AI processing page {page_num}/{total_pages}...")
                
                # Save image to temp file - use JPEG for much faster upload (smaller files)
                with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                    # Convert to RGB if necessary (JPEG doesn't support transparency)
                    if image.mode in ('RGBA', 'P', 'LA'):
                        image = image.convert('RGB')
                    image.save(tmp.name, 'JPEG', quality=85, optimize=True)
                    tmp_path = tmp.name
                
                try:
                    print(f"\n🟢 Page {page_num}: calling ocr_image_smart(text_type='{text_type}', provider='{provider}', model='{model}')", flush=True)
                    success, result, method = ocr_image_smart(
                        image_path=tmp_path,
                        text_type=text_type,
                        language=language,
                        quality=quality,
                        cloud_vision_api_key=cloud_vision_key,
                        vision_provider=provider,
                        vision_model=model,
                        vision_api_key=vision_api_key,
                        document_title=f"{title} - Page {page_num}",
                        progress_callback=None  # Don't spam status for each page
                    )
                    
                    print(f"🟢 Page {page_num}: ocr_image_smart returned success={success}, method={method}, result_len={len(result) if isinstance(result, str) else 'N/A'}", flush=True)
                    if success and result.strip():
                        # Split into paragraphs like the local OCR does
                        paragraphs = [p.strip() for p in result.split('\n\n') if p.strip()]
                        for para in paragraphs:
                            entries.append({
                                'start': page_num,
                                'text': para,
                                'location': f'Page {page_num} ({method})'
                            })
                finally:
                    # Clean up temp file
                    try:
                        os.unlink(tmp_path)
                    except:
                        pass
            
            if entries:
                # Save to OCR cache so the 3-option dialog works on reload
                from ocr_handler import save_ocr_cache
                save_ocr_cache(pdf_path, quality, language, entries)
                print(f"💾 Vision AI results saved to OCR cache for: {pdf_path}", flush=True)
                self.set_status(f"✅ Cloud AI complete! Extracted text from {total_pages} pages")
                return True, entries
            else:
                return False, "No text could be extracted from PDF"
                
        except Exception as e:
            return False, f"Cloud AI PDF processing error: {str(e)}"

    def _process_ocr_thread(self):
        file_path = self.file_path_var.get()
        ext = os.path.splitext(file_path)[1].lower()
        title = os.path.basename(file_path)
        print(f"\n🔵 _process_ocr_thread started: ext='{ext}', title='{title}'", flush=True)
        
        try:
            # Check if it's an image file (not a PDF)
            if ext in ('.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp', '.gif'):
                
                # Ask user what type of text is in the image (with auto-detection)
                text_type = self._ask_text_type(file_path)
                
                if text_type == "handwriting":
                    # Handwriting -> Use Cloud AI
                    provider = self.provider_var.get()
                    api_key = self.config.get("keys", {}).get(provider, "")
                    
                    if not api_key or api_key == "not-required":
                        self.set_status(f"⚠️ No API key for {provider}")
                        self.root.after(0, lambda: messagebox.showwarning(
                            "API Key Required",
                            f"Handwriting OCR requires a Cloud AI provider."
                            f"Please configure an API key for {provider} in Settings → API Keys."
                        ))
                        self.root.after(0, self._handle_ocr_result, False, "No API key configured", title)
                        return
                    
                    self.set_status("🤖 Processing handwriting with Cloud AI...")
                    success, result = self._process_image_with_cloud_ai(file_path, title)
                    if success:
                        self.root.after(0, self._handle_ocr_result, True, result, title)
                    else:
                        self.set_status(f"⚠️ Cloud AI failed: {result}")
                        self.root.after(0, lambda: messagebox.showwarning(
                            "Cloud AI Failed",
                            f"Cloud AI processing failed:{result}"
                        ))
                        self.root.after(0, self._handle_ocr_result, False, result, title)
                    return
                
                # Printed text -> Use local Tesseract
                import pytesseract
                from PIL import Image
                from ocr_handler import preprocess_image_for_ocr, get_tesseract_confidence
                
                self.set_status("📄 Processing printed text with local OCR...")
                image = Image.open(file_path)
                
                # Get OCR configuration
                language = self.config.get("ocr_language", "eng")
                quality = self.config.get("ocr_quality", "balanced")
                preset = OCR_PRESETS.get(quality, OCR_PRESETS["balanced"])
                custom_config = f'--psm {preset["psm"]} --oem 3'
                
                # Preprocess image
                processed_image = preprocess_image_for_ocr(image, quality)
                
                # Get OCR with confidence score
                text, confidence = get_tesseract_confidence(processed_image, language, custom_config)
                
                self.set_status(f"📊 OCR confidence: {confidence:.1f}%")
                
                # Use local result
                entries = [{
                    'location': 'Image',
                    'text': text.strip()
                }]
                
                self.root.after(0, self._handle_ocr_result, True, entries, title)
            else:
                # Process as PDF
                
                # Ask user what type of text is in the PDF (with auto-detection)
                text_type = self._ask_text_type_pdf(file_path)
                print(f"\n🔵 _process_ocr_thread: _ask_text_type_pdf returned: '{text_type}'", flush=True)
                print(f"🔵 _process_ocr_thread: text_type == 'handwriting' → {text_type == 'handwriting'}", flush=True)
                
                if text_type == "handwriting":
                    # Handwriting -> Use Cloud AI page by page
                    provider = self.provider_var.get()
                    api_key = self.config.get("keys", {}).get(provider, "")
                    
                    if not api_key or api_key == "not-required":
                        self.set_status(f"⚠️ No API key for {provider}")
                        self.root.after(0, lambda: messagebox.showwarning(
                            "API Key Required",
                            f"Handwriting OCR requires a Cloud AI provider.\n\n"
                            f"Please configure an API key for {provider} in Settings → API Keys."
                        ))
                        self.root.after(0, self._handle_ocr_result, False, "No API key configured", title)
                        return
                    
                    self.set_status("🤖 Processing PDF handwriting with Cloud AI...")
                    print(f"🔵 HANDWRITING BRANCH TAKEN! provider='{provider}', model='{self.model_var.get()}', has_key={bool(api_key)}", flush=True)
                    success, result = self._process_pdf_with_cloud_ai(file_path, title)
                    if success:
                        self.root.after(0, self._handle_ocr_result, True, result, title)
                    else:
                        self.set_status(f"⚠️ Cloud AI failed: {result}")
                        self.root.after(0, lambda: messagebox.showwarning(
                            "Cloud AI Failed",
                            f"Cloud AI processing failed:\n{result}"
                        ))
                        self.root.after(0, self._handle_ocr_result, False, result, title)
                    return
                
                # Printed text -> Use local Tesseract with smart fallback
                # This will: 1) Try local Poppler+Tesseract, 2) If fails, try Cloud AI direct PDF
                # 3) If that fails, offer iLovePDF repair
                print(f"🔵 PRINTED BRANCH TAKEN (local Tesseract) - text_type was '{text_type}'", flush=True)
                provider = self.provider_var.get()
                model = self.model_var.get()
                api_key = self.config.get("keys", {}).get(provider, "")
                all_api_keys = self.config.get("keys", {})
                
                self.set_status("📄 Processing PDF with local OCR...")
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
                
                if success:
                    if method == 'cloud_direct':
                        self.set_status(f"✅ PDF processed via Cloud AI (local conversion failed)")
                    self.root.after(0, self._handle_ocr_result, True, result, title)
                else:
                    # Smart extraction failed completely - result contains error message
                    self.root.after(0, self._handle_ocr_result, False, result, title)
        except Exception as e:
            self.root.after(0, self._handle_ocr_result, False, str(e), os.path.basename(file_path))

    def _handle_ocr_result(self, success, result, title):
        self.processing = False
        self.process_btn.config(state=tk.NORMAL)
        if success:
            self.current_entries = result
            self.current_document_source = self.file_path_var.get()
            self.current_document_type = "ocr"
            doc_id = add_document_to_library(
                doc_type="ocr",
                source=self.current_document_source,
                title=title,
                entries=self.current_entries,
                document_class="source",
                metadata={"ocr_language": self.config.get("ocr_language", "eng"),
                          "ocr_quality": self.config.get("ocr_quality", "balanced")}
            )
            # ✅ FIX: Save old thread BEFORE changing document ID
            if self.thread_message_count > 0 and self.current_document_id:
                print(f"💾 Saving old thread ({self.thread_message_count} messages) to document {self.current_document_id}")
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

            self.current_document_text = entries_to_text(self.current_entries, timestamp_interval=self.config.get("timestamp_interval", "every_segment"))

            self.set_status(f"✅ OCR completed: {title}")
            self.refresh_library()
            
            # Update button states
            self.update_button_states()
        else:
            self.set_status(f"❌ OCR Error: {result}")
            messagebox.showerror("OCR Error", result)

    def fetch_web(self):

        self.update_context_buttons('web')

        if self.processing:
            messagebox.showwarning("Warning", "Processing already in progress. Please wait or cancel.")
            return

        url = self.web_url_var.get().strip()

        # Validate input
        is_valid, error_msg = self.validate_web_url(url)
        if not is_valid:
            messagebox.showerror("Invalid Input", error_msg)
            return

        self.processing = True
        self.process_btn.config(state=tk.DISABLED)
        self.set_status("Fetching web content...")
        self.processing_thread = threading.Thread(target=self._fetch_web_thread)
        self.processing_thread.start()
        self.root.after(100, self.check_processing_thread)

    # -------------------------
    # GUI Thread Handler for Web Fetching
    # -------------------------

    def _fetch_web_thread(self):
        """Thread function for fetching web content"""
        url = self.web_url_var.get().strip()
        success, result, title, doc_type, web_metadata = get_doc_fetcher().fetch_web_url(url)
        self.root.after(0, self._handle_web_result, success, result, title, doc_type, web_metadata)

    """
    ADD THESE THREE METHODS TO Main.py DocAnalyserApp CLASS
    Location: After fetch_web method (around line 1100)
    """

    def process_web_video(self):
        """Process a web URL that contains video"""
        url = self.web_url_var.get().strip()

        if not url:
            messagebox.showerror("Error", "No URL specified")
            return

        self.processing = True
        self.process_btn.config(state=tk.DISABLED)
        self.set_status("Processing web video...")

        self.processing_thread = threading.Thread(target=self._process_web_video_thread, args=(url,))
        self.processing_thread.start()
        self.root.after(100, self.check_processing_thread)

    def _process_web_video_thread(self, url):
        """Thread function for processing web video"""
        try:
            from document_fetcher import fetch_web_video

            success, result, title, source_type = fetch_web_video(
                url=url,
                api_key=self._get_transcription_api_key(),
                engine=self.transcription_engine_var.get(),
                options={
                    'language': self.transcription_lang_var.get().strip() or None,
                    'speaker_diarization': self.diarization_var.get(),
                    'enable_vad': self.config.get("enable_vad", True)
                },
                bypass_cache=self.bypass_cache_var.get() if hasattr(self, 'bypass_cache_var') else False,
                progress_callback=self.set_status
            )

            if success:
                # Process like audio transcription result
                self.root.after(0, self._handle_web_video_result, True, result, title, source_type)
            else:
                self.root.after(0, self._handle_web_video_result, False, result, title, source_type)

        except Exception as e:
            error_msg = f"Error processing web video: {str(e)}"
            self.root.after(0, self._handle_web_video_result, False, error_msg, url, "web_video")

    def _handle_web_video_result(self, success, result, title, source_type):
        """Handle web video processing result"""
        self.processing = False
        self.process_btn.config(state=tk.NORMAL)

        if success:
            self.current_entries = result
            self.current_document_source = self.web_url_var.get().strip()
            self.current_document_type = source_type

            doc_id = add_document_to_library(
                doc_type=source_type,
                source=self.current_document_source,
                title=title,
                entries=self.current_entries,
                document_class="source",
                metadata={"source": "web_video"}
            )

            self.current_document_id = doc_id
            self.clear_thread()

            # Get document class and metadata from library
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

            self.current_document_text = entries_to_text_with_speakers(
                self.current_entries,
                timestamp_interval=self.config.get("timestamp_interval", "every_segment")
            )

            self.set_status("✅ Document loaded - Select prompt and click Run")
            self.refresh_library()
            
            # Update button states
            self.update_button_states()
        else:
            self.set_status(f"❌ Error: {result}")
            messagebox.showerror("Error", f"Failed to process web video:\n\n{result}")

    def process_web_pdf_with_ocr(self):
        """Download PDF from URL and process with OCR"""
        url = self.web_url_var.get().strip()

        # Check OCR availability
        available, error_msg, _ = get_ocr().check_ocr_availability()
        if not available:
            self.set_status(f"❌ OCR unavailable: {error_msg}")
            messagebox.showerror("OCR Error", error_msg)
            return

        self.processing = True
        self.process_btn.config(state=tk.DISABLED)
        self.set_status("Downloading PDF...")

        self.processing_thread = threading.Thread(target=self._process_web_pdf_ocr_thread, args=(url,))
        self.processing_thread.start()
        self.root.after(100, self.check_processing_thread)

    def _process_web_pdf_ocr_thread(self, url):
        """Thread function for downloading and OCR processing web PDF"""
        try:
            # Download PDF
            self.set_status("📥 Downloading PDF from URL...")
            response = requests.get(url, timeout=30)
            response.raise_for_status()

            # Save to temp file
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_pdf:
                temp_pdf.write(response.content)
                temp_pdf_path = temp_pdf.name

            # Extract title from URL
            title = url.split('/')[-1].replace('.pdf', '').replace('_', ' ')
            
            # Get OCR mode setting
            ocr_mode = self.config.get("ocr_mode", "local_first")

            try:
                # Cloud AI direct mode
                if ocr_mode == "cloud_direct":
                    self.set_status("🤖 Processing PDF with Cloud AI...")
                    web_text_type = self.config.get("ocr_text_type", "printed")
                    success, result = self._process_pdf_with_cloud_ai(temp_pdf_path, title, text_type=web_text_type)
                    if success:
                        self.root.after(0, self._handle_web_ocr_result, True, result, title, url)
                    else:
                        self.set_status(f"⚠️ Cloud AI failed: {result}")
                        self.root.after(0, lambda: messagebox.showwarning(
                            "Cloud AI Failed",
                            f"Cloud AI processing failed:\n{result}\n\n"
                            f"You can try switching to 'Local first' mode in OCR Settings."
                        ))
                        self.root.after(0, self._handle_web_ocr_result, False, result, title, url)
                    return
                
                # Local first mode - use smart extraction with Cloud AI fallback
                self.set_status("🔍 Processing PDF with OCR...")
                provider = self.provider_var.get()
                model = self.model_var.get()
                api_key = self.config.get("keys", {}).get(provider, "")
                all_api_keys = self.config.get("keys", {})
                
                success, result, method = get_ocr().extract_text_from_pdf_smart(
                    filepath=temp_pdf_path,
                    language=self.config.get("ocr_language", "eng"),
                    quality=self.config.get("ocr_quality", "balanced"),
                    provider=provider,
                    model=model,
                    api_key=api_key,
                    all_api_keys=all_api_keys,
                    progress_callback=self.set_status,
                    force_cloud=False
                )
                
                if success:
                    if method == 'cloud_direct':
                        self.set_status(f"✅ PDF processed via Cloud AI (local conversion failed)")
                    self.root.after(0, self._handle_web_ocr_result, True, result, title, url)
                else:
                    self.root.after(0, self._handle_web_ocr_result, False, result, title, url)
            finally:
                # Clean up temp file
                try:
                    os.remove(temp_pdf_path)
                except:
                    pass

        except Exception as e:
            title = url.split('/')[-1] if '/' in url else url
            self.root.after(0, self._handle_web_ocr_result, False, str(e), title, url)

    def _handle_web_ocr_result(self, success, result, title, url):
        """Handle the result of OCR processing for web PDF"""
        self.processing = False
        self.process_btn.config(state=tk.NORMAL)

        if success:
            self.current_entries = result
            self.current_document_source = url
            self.current_document_type = "web_pdf_ocr"

            doc_id = add_document_to_library(
                doc_type="web_pdf_ocr",
                source=url,
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
                # CRITICAL FIX: Add title to metadata if not already there
                if 'title' not in self.current_document_metadata and 'title' in doc:
                    self.current_document_metadata['title'] = doc['title']
            else:
                self.current_document_class = "source"
                self.current_document_metadata = {}

            # Get document class and metadata from library
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

            self.current_document_text = entries_to_text(self.current_entries, timestamp_interval=self.config.get("timestamp_interval", "every_segment"))

            self.set_status(f"✅ OCR completed: {title}")
            self.refresh_library()
            
            # Update button states
            self.update_button_states()
        else:
            self.set_status(f"❌ OCR Error: {result}")
            messagebox.showerror("OCR Error", result)

    """
    REPLACE THE _handle_web_result METHOD IN Main.py
    Location: Around line 1145
    Find the existing _handle_web_result method and replace it entirely with this version
    """

    def _handle_web_result(self, success, result, title, doc_type, web_metadata=None):
        """Handle the result of web URL fetching"""
        self.processing = False
        self.process_btn.config(state=tk.NORMAL)

        if success:
            self.current_entries = result
            self.current_document_source = self.web_url_var.get().strip()
            self.current_document_type = doc_type

            # Build metadata including published_date if available
            doc_metadata = {
                "source": "web",
                "title": title,
                "fetched": datetime.datetime.now().isoformat() + 'Z'
            }
            # Add published_date from web page if available
            if web_metadata and web_metadata.get('published_date'):
                doc_metadata['published_date'] = web_metadata['published_date']

            doc_id = add_document_to_library(
                doc_type=doc_type,
                source=self.current_document_source,
                title=title,
                entries=self.current_entries,
                document_class="source",
                metadata=doc_metadata
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
            
            # Load saved thread for NEW document
            self.load_saved_thread()
            # Get document class and metadata from library
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

            self.current_document_text = entries_to_text(self.current_entries,
                                                         timestamp_interval=self.config.get("timestamp_interval",
                                                                                            "every_segment"))

            self.set_status("✅ Document loaded - Select prompt and click Run")
            self.refresh_library()
            
            # Update button states
            self.update_button_states()

        elif result == "SCANNED_PDF":
            # Handle scanned PDF from web URL
            if messagebox.askyesno("OCR Required",
                                   f"The PDF at this URL appears to be scanned.\n\n" +
                                   "Would you like to download and process it with OCR?\n\n" +
                                   "Note: This may take a few minutes."):
                self.process_web_pdf_with_ocr()
            else:
                self.set_status("Cancelled OCR processing")

        elif result == "NOT_A_VIDEO":
            # URL doesn't contain a video - offer paste fallback
            url = self.web_url_var.get().strip()
            self.set_status(f"❌ Error: No meaningful content found")
            response = messagebox.askyesno(
                "No Content Found",
                "No text content found on this page.\n\n"
                "This page doesn't contain paragraphs of text or a supported video.\n\n"
                "Would you like to paste the content manually instead?"
            )
            if response:
                self._show_paste_fallback_dialog(
                    url=url,
                    source_type="web"
                )

        elif result == "No meaningful content found":
            # This might be a video page - try video extraction or paste fallback
            url = self.web_url_var.get().strip()

            # Create custom dialog with three options
            dialog = tk.Toplevel(self.root)
            dialog.title("No Text Content Found")
            dialog.geometry("450x220")
            dialog.transient(self.root)
            dialog.grab_set()
            
            # Center on parent
            dialog.update_idletasks()
            x = self.root.winfo_x() + (self.root.winfo_width() - 450) // 2
            y = self.root.winfo_y() + (self.root.winfo_height() - 220) // 2
            dialog.geometry(f"+{x}+{y}")
            
            main_frame = ttk.Frame(dialog, padding=20)
            main_frame.pack(fill=tk.BOTH, expand=True)
            
            ttk.Label(main_frame, text="This page doesn't contain readable text.",
                      font=('Arial', 10, 'bold')).pack(anchor=tk.W, pady=(0, 10))
            
            ttk.Label(main_frame, text=(
                "Choose an option:\n\n"
                "• Try Video - Attempt to download and transcribe video content\n"
                "• Paste Manually - Copy content from browser and paste it here"
            ), font=('Arial', 9), wraplength=400).pack(anchor=tk.W, pady=(0, 15))
            
            button_frame = ttk.Frame(main_frame)
            button_frame.pack(fill=tk.X, pady=(10, 0))
            
            def on_try_video():
                dialog.destroy()
                self.process_web_video()
            
            def on_paste():
                dialog.destroy()
                self._show_paste_fallback_dialog(url=url, source_type="web")
            
            def on_cancel():
                dialog.destroy()
                self.set_status("Cancelled")
            
            ttk.Button(button_frame, text="🎥 Try Video", command=on_try_video, width=14).pack(side=tk.LEFT, padx=(0, 5))
            ttk.Button(button_frame, text="📋 Paste Manually", command=on_paste, width=16).pack(side=tk.LEFT, padx=5)
            ttk.Button(button_frame, text="Cancel", command=on_cancel, width=10).pack(side=tk.RIGHT)
            
            dialog.protocol("WM_DELETE_WINDOW", on_cancel)
        else:
            # Generic error - offer paste fallback option
            url = self.web_url_var.get().strip()
            self.set_status(f"❌ Error: {result}")
            
            # Check if this looks like an access/blocking issue
            access_keywords = ['403', '401', 'forbidden', 'blocked', 'access denied', 
                              'paywall', 'subscribe', 'login required', 'restricted']
            is_access_issue = any(kw in str(result).lower() for kw in access_keywords)
            
            if is_access_issue:
                # Show paste fallback dialog for access issues
                self._show_paste_fallback_dialog(
                    url=url,
                    source_type="web"
                )
            else:
                # Regular error - show message box but mention paste option
                response = messagebox.askyesno(
                    "Fetch Error",
                    f"{result}\n\n"
                    f"Would you like to paste the content manually instead?"
                )
                if response:
                    self._show_paste_fallback_dialog(
                        url=url,
                        source_type="web"
                    )

