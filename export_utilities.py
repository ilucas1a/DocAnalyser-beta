"""
export_utilities.py - Export, utility, and lifecycle methods for DocAnalyser.

Handles app closing, new conversation creation, export to web chat,
save thread to library, PDF reprocessing, YouTube download, web URL opening,
document export, TurboScribe send/import, semantic search, cost display,
and add sources dialog.

Extracted from Main.py to reduce file size. Uses a mixin pattern so all
self.xxx references continue to work unchanged.
"""

from __future__ import annotations

import os
import re
import datetime
import logging
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path

from document_library import (
    get_document_by_id,
    add_document_to_library,
    load_document_entries,
    save_thread_to_document,
)
from utils import entries_to_text, entries_to_text_with_speakers

# Lazy module loaders (mirrors Main.py pattern)
def get_doc_fetcher():
    import document_fetcher
    return document_fetcher


class ExportUtilitiesMixin:
    """Mixin class providing export, utility, and lifecycle methods for DocAnalyzerApp."""

    def on_app_closing(self):
        """
        Handle application close event
        Save current thread before exiting to preserve conversation
        """
        print("\n" + "=" * 60)
        print("🚪 Application closing...")
        
        # Save thread if there are messages
        if self.thread_message_count > 0 and self.current_document_id:
            print(f"💾 Auto-saving thread ({self.thread_message_count} messages) before exit...")
            self.save_current_thread()
            print("✅ Thread saved!")
        else:
            print("ℹ️  No thread to save (either no messages or no document loaded)")
        
        print("👋 Goodbye!")
        print("=" * 60)
        
        # Close the window
        self.root.destroy()

    def start_new_conversation_same_source(self, source_doc_id: str) -> bool:
        """
        Start a new conversation using the original source document.
        
        Called from Thread Viewer when user wants to start a fresh conversation
        about the same source document that a Response was based on.
        
        Args:
            source_doc_id: The ID of the parent document (may be Response or Source)
            
        Returns:
            True if successful, False otherwise
        """
        from document_library import get_document_by_id, load_document_entries
        
        # Follow the parent chain to find the ORIGINAL source document
        # (in case parent_document_id points to another Response)
        original_source_id = source_doc_id
        visited = set()  # Prevent infinite loops
        
        while original_source_id and original_source_id not in visited:
            visited.add(original_source_id)
            doc = get_document_by_id(original_source_id)
            
            if not doc:
                break
            
            # Check if this is a source document (not a response/product)
            doc_class = doc.get('document_class', 'source')
            if doc_class not in ['response', 'product', 'processed_output']:
                # Found the original source!
                break
            
            # This is a Response/Product - look for its parent
            parent_id = doc.get('metadata', {}).get('parent_document_id')
            if not parent_id or parent_id == original_source_id:
                # No parent or self-reference - use this as the source
                break
            
            # Follow the chain
            print(f"🔗 Following parent chain: {original_source_id} -> {parent_id}")
            original_source_id = parent_id
        
        # Check if source document exists
        source_doc = get_document_by_id(original_source_id)
        if not source_doc:
            messagebox.showerror(
                "Source Not Found",
                "The original source document is no longer available.\n\n"
                "It may have been deleted from the Documents Library."
            )
            return False
        
        # Verify we found an actual source (not another Response)
        doc_class = source_doc.get('document_class', 'source')
        if doc_class in ['response', 'product', 'processed_output']:
            messagebox.showwarning(
                "Source Unavailable",
                "Could not find the original source document.\n\n"
                "The parent document chain leads to another Response document.\n"
                "The original source may have been deleted."
            )
            return False
        
        # Load the source document entries
        entries = load_document_entries(original_source_id)
        if not entries:
            messagebox.showerror(
                "Load Error",
                "Could not load the source document content."
            )
            return False
        
        # Clear current thread (saves if needed)
        self.clear_thread()
        
        # Load the source document
        self.current_entries = entries
        self.current_document_id = original_source_id
        self.current_document_source = source_doc.get('source', 'Unknown')
        self.current_document_type = source_doc.get('type', 'unknown')
        self.current_document_class = source_doc.get('document_class', 'source')
        self.current_document_metadata = source_doc.get('metadata', {})
        if 'title' not in self.current_document_metadata:
            self.current_document_metadata['title'] = source_doc.get('title', 'Unknown')
        
        # Convert entries to text
        from utils import entries_to_text, entries_to_text_with_speakers
        if source_doc.get('type') == 'audio_transcription':
            self.current_document_text = entries_to_text_with_speakers(
                entries,
                timestamp_interval=self.config.get("timestamp_interval", "every_segment")
            )
        else:
            self.current_document_text = entries_to_text(entries)
        
        # Reset standalone conversation state
        from standalone_conversation import reset_standalone_state
        reset_standalone_state()
        
        # Note: Don't close viewer windows here - the caller (viewer) will handle itself
        # Just clean up the tracking list of closed windows
        self._cleanup_closed_viewers()
        
        # Update UI
        self.update_button_states()
        
        # Explicitly set preview title to source_ready mode (prompts user to click Run)
        
        doc_title = source_doc.get('title', 'Unknown')
        self.set_status("✅ Source document loaded - Ready for new conversation")
        
        return True

    def export_to_web_chat(self):
        """
        Run prompt via web: Copy document and prompt to clipboard and open
        the provider's web-based chat interface (ChatGPT, Claude, Gemini, etc.)
        This is an alternative to the API method - free but requires manual paste.
        """
        import webbrowser
        
        # Reset Run button highlight immediately
        self._run_highlight_enabled = False
        if hasattr(self, 'process_btn'):
            self.process_btn.configure(style='TButton')
            self.root.update_idletasks()
        
        # Clear the input field and restore placeholder (document is already loaded)
        self.universal_input_entry.delete('1.0', 'end')
        self.placeholder_active = False  # Reset so update_placeholder will work
        self.update_placeholder()
        
        # 🆕 NEW: Smart context check - allow prompts without documents
        has_document = bool(self.current_document_text)
        has_attachments = (hasattr(self, 'attachment_manager') and 
                          self.attachment_manager.get_attachment_count() > 0)
        has_any_content = has_document or has_attachments
        
        # Get the current prompt
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
                    f"Your prompt mentions document-related content but no document is loaded.\n\n"
                    f"💡 Tip: Load a document first, or rephrase your prompt.\n\n"
                    f"Continue anyway (only prompt will be copied)?",
                    icon='warning'
                )
                if not response:
                    return
        
        # Get the selected provider
        provider = self.provider_var.get()
        
        # Define provider info: URL, name, and any special notes
        provider_info = {
            "OpenAI (ChatGPT)": {
                "url": "https://chat.openai.com",
                "name": "ChatGPT",
                "notes": "Free tier available. For very long documents, ChatGPT may truncate the input."
            },
            "Anthropic (Claude)": {
                "url": "https://claude.ai",
                "name": "Claude",
                "notes": "Free tier available. Claude handles very long documents well (200K+ tokens)."
            },
            "Google (Gemini)": {
                "url": "https://gemini.google.com",
                "name": "Gemini",
                "notes": "Free tier available. Requires a Google account."
            },
            "xAI (Grok)": {
                "url": "https://x.com/i/grok",
                "name": "Grok",
                "notes": "⚠️ Requires an X (Twitter) account to access."
            },
            "DeepSeek": {
                "url": "https://chat.deepseek.com",
                "name": "DeepSeek",
                "notes": "Free tier available with generous limits."
            },
            "Ollama (Local)": {
                "url": None,  # No web interface
                "name": "Ollama",
                "notes": "Ollama is a local application. Open it directly and paste your content there."
            }
        }
        
        # Get info for selected provider, with fallback
        info = provider_info.get(provider, {
            "url": None,
            "name": provider,
            "notes": "Web interface URL not configured for this provider."
        })
        
        # Build the export text
        export_parts = [prompt]
        
        # Add main document if present
        if has_document:
            export_parts.append("\n\n" + "=" * 50 + "\nDOCUMENT\n" + "=" * 50 + f"\n\n{self.current_document_text}")
        
        # 🆕 NEW: Add attachments if present
        if has_attachments:
            export_parts.append("\n\n" + self.attachment_manager.build_attachment_text())
        
        export_text = "".join(export_parts)
        
        # Calculate approximate size
        char_count = len(export_text)
        word_count = len(export_text.split())
        token_estimate = char_count // 4  # Rough estimate
        
        # Build content description for message
        content_desc = []
        content_desc.append("• Your selected prompt")
        if has_document:
            content_desc.append(f"• The loaded document")
        if has_attachments:
            att_count = self.attachment_manager.get_attachment_count()
            content_desc.append(f"• {att_count} attached document{'s' if att_count > 1 else ''}")
        content_desc.append(f"\nTotal: {word_count:,} words, ~{token_estimate:,} tokens")
        content_list = "\n".join(content_desc)
        
        # Build the message
        if info["url"]:
            message = (
                f"Run prompt via {info['name']} Web Chat\n\n"
                f"The following will be copied to your clipboard:\n"
                f"{content_list}\n\n"
                f"After clicking OK:\n"
                f"1. Your browser will open {info['name']}\n"
                f"2. Press Ctrl+V to paste into the chat input\n"
                f"3. Press Enter or click Send to run the prompt\n\n"
                f"Note: {info['notes']}\n\n"
                f"Continue?"
            )
        else:
            # Ollama or unknown provider
            message = (
                f"Run prompt via {info['name']}\n\n"
                f"The following will be copied to your clipboard:\n"
                f"{content_list}\n\n"
                f"Note: {info['notes']}\n\n"
                f"After clicking OK, press Ctrl+V in your AI application to paste.\n\n"
                f"Continue?"
            )
        
        # Ask user to confirm
        response = messagebox.askyesno("Run Prompt Via Web", message)
        
        if not response:
            return
        
        # Copy to clipboard
        self.root.clipboard_clear()
        self.root.clipboard_append(export_text)
        self.root.update()  # Required for clipboard to persist
        
        # Open web browser if URL available
        if info["url"]:
            try:
                webbrowser.open(info["url"])
                self.set_status(f"✅ Copied to clipboard & opened {info['name']} - press Ctrl+V in browser to paste, or right-click and select Paste.")
            except Exception as e:
                self.set_status(f"✅ Copied to clipboard - open {info['url']} manually")
                messagebox.showinfo(
                    "Browser Error",
                    f"Copied to clipboard but couldn't open browser.\n\n"
                    f"Please open {info['url']} manually and press Ctrl+V to paste."
                )
        else:
            self.set_status(f"✅ Copied to clipboard - paste into {info['name']} with Ctrl+V")
            messagebox.showinfo(
                "Copied to Clipboard",
                f"Content copied!\n\nOpen {info['name']} and press Ctrl+V to paste."
            )
        
        # 🆕 NEW: Show the web response capture banner
        # Build context for later capture - get document title from library
        source_name = "Unknown source"
        if self.current_document_id:
            try:
                from document_library import get_document_by_id
                doc = get_document_by_id(self.current_document_id)
                if doc and doc.get('title'):
                    source_name = doc.get('title')
                    # Remove [Source], [Product], etc. prefixes if present
                    for prefix in ['[Source] ', '[Product] ', '[Response] ', '[Thread] ']:
                        if source_name.startswith(prefix):
                            source_name = source_name[len(prefix):]
                            break
                    # Remove source type prefixes like "YouTube: ", "Substack: "
                    for type_prefix in ['YouTube: ', 'Substack: ', 'Web: ', 'Audio: ', 'File: ', 'PDF: ']:
                        if source_name.startswith(type_prefix):
                            source_name = source_name[len(type_prefix):]
                            break
            except:
                pass
        if source_name == "Unknown source" and self.current_document_source:
            source_name = self.current_document_source
        
        attachment_names = []
        if has_attachments:
            attachment_names = [a.get('name', 'Attachment') for a in self.attachment_manager.get_attachments()]
        
        web_response_context = {
            "prompt": prompt,
            "provider": info['name'],
            "source_name": source_name,
            "document_id": self.current_document_id,
            "attachment_names": attachment_names,
            "sent_at": datetime.datetime.now().isoformat()
        }
        
        self.show_web_response_banner(web_response_context)

    def save_thread_to_library(self):
        """Save current conversation thread as a new document in the library"""
        if not self.current_document_id:
            messagebox.showinfo("No Document", "Please load a document first.")
            return

        if not self.current_thread or self.thread_message_count == 0:
            messagebox.showinfo("No Thread",
                                "No conversation thread to save.\n\nStart a conversation by running a prompt first.")
            return

        # Confirm with user
        response = messagebox.askyesno(
            "Save Thread to Library",
            f"Save this conversation thread to the Documents Library?\n\n"
            f"Messages: {self.thread_message_count}\n"
            f"Model: {self.model_var.get()}\n\n"
            f"The thread will be saved as a new entry with [Thread] prefix."
        )

        if not response:
            return

        # Prepare metadata
        metadata = {
            "model": self.model_var.get(),
            "provider": self.provider_var.get(),
            "last_updated": datetime.datetime.now().isoformat(),
            "message_count": self.thread_message_count
        }

        # Save as new document
        from document_library import save_thread_as_new_document
        thread_id = save_thread_as_new_document(
            self.current_document_id,
            self.current_thread,
            metadata
        )

        if thread_id:
            messagebox.showinfo(
                "Thread Saved!",
                f"✅ Conversation thread saved to library!\n\n"
                f"📊 Details:\n"
                f"  • Messages: {self.thread_message_count}\n"
                f"  • Model: {self.model_var.get()}\n"
                f"  • Provider: {self.provider_var.get()}\n\n"
                f"You can find it in the Documents Library with the [Thread] prefix."
            )
            # Refresh library if it's open
            self.refresh_library()
        else:
            messagebox.showerror(
                "Save Failed",
                "Failed to save thread to library.\n\nCheck console for error details."
            )

    """
    BUTTON CODE TO ADD

    Find the conversation buttons row around line 1611 and add this button:
    """

    def force_reprocess_pdf(self):
        """Force re-OCR of current PDF"""
        self.force_reprocess_var.set(True)
        self.fetch_local_file()

    def download_youtube_video(self):
        """Download YouTube video (placeholder for now)"""
        messagebox.showinfo("Download Video",
                            "Video download feature coming soon!\n\n" +
                            "For now, you can use:\n" +
                            "• youtube-dl or yt-dlp command line tools\n" +
                            "• Online YouTube downloaders")

    def open_web_url_in_browser(self):
        """Open current web URL in default browser"""
        url = self.web_url_var.get()
        if url:
            webbrowser.open(url)
        else:
            messagebox.showwarning("No URL", "Please enter a web URL first")

    def export_document(self):
        """Export current document (placeholder for now)"""
        if not self.current_document_text and not self.current_entries:
            messagebox.showwarning("No Document", "Please load a document first")
            return

        messagebox.showinfo("Export Document",
                            "Document export feature coming soon!\n\n" +
                            "For now, you can:\n" +
                            "• Copy text from preview\n" +
                            "• Use the Save button to save outputs")

    def send_to_turboscribe(self):
        """
        Phase 1 of the streamlined TurboScribe workflow.

        Copies the audio file to Desktop/TurboScribe_Uploads, opens TurboScribe
        on the left half of the screen, File Explorer showing the copied file on
        the right half, and a compact two-phase instruction dialog in the centre.
        """
        audio_path = self.audio_path_var.get()

        if not audio_path:
            messagebox.showerror("No Audio File",
                                 "Please load an audio file first, then try again.")
            return

        if not os.path.exists(audio_path):
            messagebox.showerror("File Not Found",
                                 f"Audio file not found: {audio_path}")
            return

        try:
            import turboscribe_helper

            # Copy file to the upload staging folder
            destination = turboscribe_helper.export_for_turboscribe(audio_path)
            audio_filename = os.path.basename(audio_path)

            # Remember the audio title so the import step can name the library entry
            self._turboscribe_audio_title = os.path.splitext(audio_filename)[0]

            # Open TurboScribe website (will appear on the left after positioning)
            turboscribe_helper.open_turboscribe_website()

            # Open File Explorer at the upload folder, selecting the copied file
            try:
                import subprocess
                subprocess.Popen(['explorer', '/select,', destination])
            except Exception:
                pass

            # Show the two-phase instruction dialog (centred, always on top)
            self._show_turboscribe_dialog(audio_filename, destination)

            # Position windows: TurboScribe LEFT, Explorer RIGHT
            self._turboscribe_position_attempts = 0
            self.root.after(1500,
                            lambda: self._ts_position_phase1(destination))

            self.set_status("🚀 TurboScribe — drag the audio file across to upload")

        except Exception as e:
            messagebox.showerror("Export Failed",
                                 f"Failed to export audio:\n{str(e)}")

    # ------------------------------------------------------------------
    # Two-phase instruction dialog
    # ------------------------------------------------------------------

    def _show_turboscribe_dialog(self, audio_filename, destination):
        """
        Compact, always-on-top dialog that guides the user through both
        phases of the TurboScribe workflow.
        """
        dlg = tk.Toplevel(self.root)
        dlg.title("TurboScribe Helper")
        dlg.attributes('-topmost', True)
        dlg.resizable(False, False)

        if hasattr(self, 'apply_window_style'):
            self.apply_window_style(dlg)

        # Keep a reference so other methods can close it
        self._turboscribe_dialog = dlg

        main = ttk.Frame(dlg, padding=(18, 14))
        main.pack(fill=tk.BOTH, expand=True)

        # --- Phase 1 content ---
        ttk.Label(main, text="Step 1 — Upload to TurboScribe",
                  font=('Arial', 11, 'bold')).pack(anchor=tk.W, pady=(0, 6))

        ttk.Label(main, text=f"File: {audio_filename}",
                  font=('Arial', 9, 'italic')).pack(anchor=tk.W, pady=(0, 10))

        phase1_text = (
            "Drag the audio file from the Explorer window on\n"
            "the right into TurboScribe's upload area on the left.\n\n"
            "When TurboScribe has finished transcribing,\n"
            "export the transcript as TXT, then click below."
        )
        ttk.Label(main, text=phase1_text, font=('Arial', 9),
                  justify=tk.LEFT).pack(anchor=tk.W, pady=(0, 14))

        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=tk.X)

        ttk.Button(
            btn_frame, text="Transcription Complete  \u2192",
            command=lambda: self._turboscribe_phase2(dlg, main)
        ).pack(side=tk.RIGHT)

        ttk.Button(btn_frame, text="Cancel",
                   command=lambda: self._turboscribe_cancel(dlg)).pack(side=tk.LEFT)

        # Centre on screen
        self._centre_dialog(dlg, min_width=400)

        dlg.transient(self.root)
        dlg.focus_force()

    def _turboscribe_phase2(self, dlg, main_frame):
        """
        Transition the dialog to Phase 2 (import) and rearrange windows
        so Downloads is on the left and DocAnalyser is on the right.
        """
        # Clear Phase 1 widgets
        for widget in main_frame.winfo_children():
            widget.destroy()

        # Flag so that dragging a .txt into the Universal Input routes
        # through the TurboScribe parser instead of plain-text loading
        self._turboscribe_awaiting_import = True

        # --- Phase 2 content ---
        ttk.Label(main_frame, text="Step 2 — Import Transcript",
                  font=('Arial', 11, 'bold')).pack(anchor=tk.W, pady=(0, 10))

        phase2_text = (
            "Drag the downloaded transcript (.txt) from the\n"
            "Downloads folder on the left into DocAnalyser's\n"
            "input area on the right, then click Load."
        )
        ttk.Label(main_frame, text=phase2_text, font=('Arial', 9),
                  justify=tk.LEFT).pack(anchor=tk.W, pady=(0, 14))

        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X)

        ttk.Button(btn_frame, text="Done",
                   command=lambda: self._turboscribe_cancel(dlg)
                   ).pack(side=tk.RIGHT)

        # Open Downloads folder (will appear on the left after positioning)
        try:
            import subprocess
            downloads = os.path.join(os.path.expanduser('~'), 'Downloads')
            subprocess.Popen(['explorer', downloads])
        except Exception:
            pass

        # Position windows: Downloads LEFT, DocAnalyser RIGHT
        self._turboscribe_position_attempts = 0
        self.root.after(500, self._ts_position_phase2)

        self.set_status("📥 Drag the transcript file into the input area, then click Load")

        # Re-centre
        self._centre_dialog(dlg, min_width=400)

    def _turboscribe_cancel(self, dlg):
        """Clean up flags and close the TurboScribe helper dialog."""
        self._turboscribe_awaiting_import = False
        try:
            dlg.destroy()
        except Exception:
            pass
        self._turboscribe_dialog = None

    # ------------------------------------------------------------------
    # Window-positioning helpers (best-effort, Windows only)
    # ------------------------------------------------------------------

    def _ts_get_work_area(self):
        """Return (x, y, width, height) of the desktop work area."""
        import ctypes
        from ctypes import wintypes
        rect = wintypes.RECT()
        ctypes.windll.user32.SystemParametersInfoW(
            0x0030, 0, ctypes.byref(rect), 0)
        return (rect.left, rect.top,
                rect.right - rect.left, rect.bottom - rect.top)

    def _ts_find_window(self, search_text, exclude_text=None):
        """Find a visible window whose title contains *search_text*."""
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        found = None
        WNDENUMPROC = ctypes.WINFUNCTYPE(
            wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def cb(hwnd, _):
            nonlocal found
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value.lower()
            if search_text.lower() in title:
                if exclude_text and exclude_text.lower() in title:
                    return True
                found = hwnd
                return False
            return True

        user32.EnumWindows(WNDENUMPROC(cb), 0)
        return found

    def _ts_place_window(self, hwnd, x, y, w, h):
        """Move / resize a window, un-maximising first if necessary."""
        import ctypes
        import time
        user32 = ctypes.windll.user32

        # Always send WM_SYSCOMMAND + SC_RESTORE — this is the most
        # reliable way to un-maximise Chrome/Edge.  They sometimes
        # ignore ShowWindow, and IsZoomed can return False even when
        # the window fills the screen.
        WM_SYSCOMMAND = 0x0112
        SC_RESTORE = 0xF120
        user32.SendMessageW(hwnd, WM_SYSCOMMAND, SC_RESTORE, 0)
        time.sleep(0.15)

        user32.ShowWindow(hwnd, 1)           # SW_SHOWNORMAL (belt & braces)
        user32.SetWindowPos(hwnd, 0,
                            x, y, w, h,
                            0x0004 | 0x0020 | 0x0040)
                            # SWP_NOZORDER | SWP_FRAMECHANGED | SWP_SHOWWINDOW

    def _ts_position_phase1(self, destination):
        """Phase 1 layout: TurboScribe LEFT, Explorer RIGHT."""
        try:
            x0, y0, ww, wh = self._ts_get_work_area()
            hw = ww // 2

            # Find browser with TurboScribe loaded
            browser = self._ts_find_window('turboscribe',
                                           exclude_text='helper')
            if not browser:
                self._turboscribe_position_attempts += 1
                if self._turboscribe_position_attempts < 6:
                    self.root.after(1000,
                                    lambda: self._ts_position_phase1(destination))
                return

            self._ts_place_window(browser, x0, y0, hw, wh)

            # Find the Explorer window showing the uploads folder
            folder_name = os.path.basename(os.path.dirname(destination))
            explorer = self._ts_find_window(folder_name)
            if explorer:
                self._ts_place_window(explorer, x0 + hw, y0, hw, wh)
        except Exception:
            pass  # Best effort — silently ignore on non-Windows / failure

    def _ts_position_phase2(self):
        """Phase 2 layout: Downloads Explorer LEFT, DocAnalyser RIGHT."""
        try:
            x0, y0, ww, wh = self._ts_get_work_area()
            hw = ww // 2

            downloads = self._ts_find_window('downloads')
            if not downloads:
                self._turboscribe_position_attempts += 1
                if self._turboscribe_position_attempts < 6:
                    self.root.after(1000, self._ts_position_phase2)
                return

            self._ts_place_window(downloads, x0, y0, hw, wh)

            # DocAnalyser on the RIGHT
            try:
                da = int(self.root.wm_frame(), 16)
                self._ts_place_window(da, x0 + hw, y0, hw, wh)
            except Exception:
                pass
        except Exception:
            pass

    def _centre_dialog(self, dlg, min_width=380):
        """Centre a dialog on screen."""
        dlg.update_idletasks()
        dw = max(dlg.winfo_reqwidth(), min_width)
        dh = dlg.winfo_reqheight()
        sw = dlg.winfo_screenwidth()
        sh = dlg.winfo_screenheight()
        dlg.geometry(f"{dw}x{dh}+{(sw - dw) // 2}+{(sh - dh) // 3}")

    # ------------------------------------------------------------------
    # TurboScribe import (also used as the manual fallback button)
    # ------------------------------------------------------------------

    def import_turboscribe(self, file_path=None):
        """
        Import TurboScribe transcript file and convert to DocAnalyser format.
        Supports TXT, DOCX, and SRT formats.

        Args:
            file_path: If provided, imports this file directly.
                       If None, opens a file-chooser dialog.
        """
        # Close the helper dialog if it is still open
        if (hasattr(self, '_turboscribe_dialog')
                and self._turboscribe_dialog
                and self._turboscribe_dialog.winfo_exists()):
            try:
                self._turboscribe_dialog.destroy()
            except Exception:
                pass
            self._turboscribe_dialog = None

        # Clear the awaiting flag
        self._turboscribe_awaiting_import = False

        if file_path is None:
            # Manual mode — open a file chooser
            downloads_folder = (str(Path.home() / "Downloads")
                                if hasattr(Path, 'home') else "")
            file_path = filedialog.askopenfilename(
                title="Select TurboScribe Transcript",
                initialdir=downloads_folder,
                filetypes=[
                    ("All Supported", "*.txt *.docx *.srt"),
                    ("Text files", "*.txt"),
                    ("Word documents", "*.docx"),
                    ("Subtitle files", "*.srt"),
                    ("All files", "*.*")
                ]
            )

        if not file_path:
            return

        try:
            self.set_status("📄 Parsing TurboScribe transcript...")

            import turboscribe_helper
            # Parse the transcript file
            segments = turboscribe_helper.parse_turboscribe_file(file_path)

            # Validate
            is_valid, error = turboscribe_helper.validate_turboscribe_import(segments)
            if not is_valid:
                messagebox.showerror("Invalid Transcript",
                                     f"Validation failed:\n{error}")
                return

            # Get statistics
            stats = turboscribe_helper.get_transcript_stats(segments)

            # Convert to DocAnalyser entries format
            entries = []
            for seg in segments:
                entries.append({
                    'start': seg['start'],
                    'text': seg['text'],
                    'speaker': seg.get('speaker', 'Unknown'),
                    'timestamp': seg.get('timestamp', '')
                })

            # Store in current document
            self.current_entries = entries
            self.current_document_source = file_path
            self.current_document_type = "turboscribe_import"

            # Convert to text for display
            self.current_document_text = entries_to_text_with_speakers(
                self.current_entries,
                timestamp_interval=self.config.get("timestamp_interval", "5min")
            )

            # Display in preview
            self.display_source_in_preview(self.current_document_text)

            # Add to library — use original audio name if we remember it
            audio_title = getattr(self, '_turboscribe_audio_title', None)
            if audio_title:
                title = f"🎤 {audio_title}"
            else:
                title = f"TurboScribe: {os.path.basename(file_path)}"
            doc_id = add_document_to_library(
                doc_type="turboscribe_import",
                source=file_path,
                title=title,
                entries=self.current_entries,
                document_class="source",
                metadata={
                    "speakers": stats['speakers'],
                    "duration": stats['total_duration_formatted'],
                    "segment_count": stats['total_segments']
                }
            )
            # Save old thread BEFORE changing document ID
            if self.thread_message_count > 0 and self.current_document_id:
                self.save_current_thread()

            # Clear thread
            self.current_thread = []
            self.thread_message_count = 0
            self.update_thread_status()

            # Set new document ID
            self.current_document_id = doc_id
            doc = get_document_by_id(doc_id)
            if doc:
                self.current_document_class = doc.get("document_class", "source")
                self.current_document_metadata = doc.get("metadata", {})
                if 'title' not in self.current_document_metadata and 'title' in doc:
                    self.current_document_metadata['title'] = doc['title']
            else:
                self.current_document_class = "source"
                self.current_document_metadata = {}

            # Success feedback
            success_msg = (
                f"✅ TurboScribe transcript imported successfully!\n\n"
                f"📊 Statistics:\n"
                f"  • Segments: {stats['total_segments']}\n"
                f"  • Duration: {stats['total_duration_formatted']}\n"
                f"  • Speakers: {', '.join(stats['speakers'])}\n\n"
                f"The transcript is now ready for AI analysis!"
            )

            self.set_status(f"✅ Imported TurboScribe transcript: {title}")
            messagebox.showinfo("Import Successful", success_msg)
            self.refresh_library()
            self.update_button_states()

        except Exception as e:
            error_msg = f"Failed to import transcript:\n{str(e)}"
            messagebox.showerror("Import Failed", error_msg)
            self.set_status("❌ TurboScribe import failed")
            import traceback
            traceback.print_exc()

    def test_semantic_search(self):
        """
        Test the semantic search module with a real API call.
        This verifies the module is working with your OpenAI key.
        """
        try:
            from semantic_search import SemanticSearch, test_semantic_search
            
            # First run basic tests (no API)
            test_semantic_search()
            
            # Get OpenAI key from config
            openai_key = self.config.get("keys", {}).get("OpenAI (ChatGPT)", "")
            
            if not openai_key:
                messagebox.showwarning(
                    "No API Key",
                    "No OpenAI API key found.\n\n"
                    "Semantic search requires an OpenAI key for generating embeddings.\n\n"
                    "Please add your OpenAI key in Settings."
                )
                return
            
            # Test with real API call
            self.set_status("🧠 Testing semantic search with OpenAI API...")
            self.root.update()
            
            ss = SemanticSearch(api_key=openai_key, provider="openai")
            
            # Generate a test embedding
            test_text = "This is a test document about Python programming and machine learning."
            embedding, cost = ss.generate_embedding(test_text)
            
            # Log the cost
            from cost_tracker import log_cost
            log_cost(
                provider="OpenAI (ChatGPT)",
                model="text-embedding-3-small",
                cost=cost,
                document_title="Semantic Search Test",
                prompt_name="embedding_generation"
            )
            
            messagebox.showinfo(
                "Semantic Search Test",
                f"✅ Semantic search is working!\n\n"
                f"Generated embedding with {len(embedding)} dimensions\n"
                f"Cost: ${cost:.6f}\n\n"
                f"You're ready to use semantic search in the Document Library!"
            )
            
            self.set_status("✅ Semantic search test successful!")
            
        except ImportError as e:
            messagebox.showerror(
                "Module Not Found",
                f"Could not import semantic_search module.\n\n"
                f"Make sure semantic_search.py is in your project folder.\n\n"
                f"Error: {str(e)}"
            )
        except Exception as e:
            messagebox.showerror(
                "Test Failed",
                f"Semantic search test failed:\n\n{str(e)}"
            )
            self.set_status("❌ Semantic search test failed")

    def show_costs(self):
        """Display API costs dialog - delegates to cost_tracker module"""
        from cost_tracker import show_costs_dialog
        show_costs_dialog(self.root)

    def open_add_sources(self):
        """
        Open the unified Add Sources dialog.
        
        Allows users to add sources to either:
        - Documents Library (permanent)
        - Prompt Context (temporary, for multi-document analysis)
        """
        print("Opening Add Sources dialog...")
        
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
        
        def save_to_library(title: str, content: str, source: str, doc_class: str = 'source'):
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

