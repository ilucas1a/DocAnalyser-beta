"""
paste_content_dialog.py

Simple dialog for manually pasting content into DocAnalyser.
Useful when automated fetching fails (e.g., Twitter/X posts).

Usage:
    from paste_content_dialog import PasteContentDialog
    
    dialog = PasteContentDialog(parent, app, source_url="https://x.com/...")
    # Dialog handles saving to library and updating the app
"""

import tkinter as tk
from tkinter import ttk, messagebox
import datetime


class PasteContentDialog:
    """
    Dialog for manually pasting content that couldn't be fetched automatically.
    """
    
    def __init__(self, parent, app, source_url: str = "", source_type: str = "pasted", 
                 title: str = "Paste Content", prompt_text: str = None):
        """
        Initialize the paste content dialog.
        
        Args:
            parent: Parent window
            app: Main DocAnalyserApp instance
            source_url: Original URL that failed to fetch (for reference)
            source_type: Type of source (e.g., "twitter", "pasted")
            title: Dialog window title
            prompt_text: Custom prompt text to show user
        """
        self.app = app
        self.source_url = source_url
        self.source_type = source_type
        self.result = None
        
        # Create dialog window
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(title)
        self.dialog.geometry("600x450")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        # Center on parent
        self.dialog.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 600) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 450) // 2
        self.dialog.geometry(f"+{x}+{y}")
        
        self._create_widgets(prompt_text)
        
        # Focus the text area
        self.text_area.focus_set()
        
        # Handle window close
        self.dialog.protocol("WM_DELETE_WINDOW", self._on_cancel)
        
        # Wait for dialog to close
        parent.wait_window(self.dialog)
    
    def _create_widgets(self, prompt_text: str = None):
        """Create the dialog widgets."""
        main_frame = ttk.Frame(self.dialog, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Instructions
        if prompt_text is None:
            prompt_text = (
                "Paste the content below. You can copy text from the webpage, \n"
                "a document, or any other source."
            )
        
        instructions = ttk.Label(
            main_frame, 
            text=prompt_text,
            font=('Arial', 10),
            wraplength=550
        )
        instructions.pack(anchor=tk.W, pady=(0, 10))
        
        # Show source URL if provided
        if self.source_url:
            url_frame = ttk.Frame(main_frame)
            url_frame.pack(fill=tk.X, pady=(0, 10))
            
            ttk.Label(url_frame, text="Source:", font=('Arial', 9, 'bold')).pack(side=tk.LEFT)
            
            url_label = ttk.Label(
                url_frame, 
                text=self.source_url[:70] + "..." if len(self.source_url) > 70 else self.source_url,
                font=('Arial', 9),
                foreground='#0066CC'
            )
            url_label.pack(side=tk.LEFT, padx=(5, 0))
        
        # Title field
        title_frame = ttk.Frame(main_frame)
        title_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(title_frame, text="Title (optional):", font=('Arial', 9)).pack(side=tk.LEFT)
        
        self.title_var = tk.StringVar()
        self.title_entry = ttk.Entry(title_frame, textvariable=self.title_var, width=50)
        self.title_entry.pack(side=tk.LEFT, padx=(10, 0), fill=tk.X, expand=True)
        
        # Text area with scrollbar
        text_frame = ttk.Frame(main_frame)
        text_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        self.text_area = tk.Text(
            text_frame,
            wrap=tk.WORD,
            font=('Arial', 10),
            bg='#FFFEF0',
            relief=tk.SUNKEN,
            borderwidth=2
        )
        
        scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self.text_area.yview)
        self.text_area.configure(yscrollcommand=scrollbar.set)
        
        self.text_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Character count
        self.char_count_var = tk.StringVar(value="0 characters")
        char_count_label = ttk.Label(main_frame, textvariable=self.char_count_var, font=('Arial', 8))
        char_count_label.pack(anchor=tk.E)
        
        # Update character count on text change
        self.text_area.bind('<KeyRelease>', self._update_char_count)
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        # Paste from clipboard button
        paste_btn = ttk.Button(
            button_frame,
            text="📋 Paste from Clipboard",
            command=self._paste_from_clipboard,
            width=20
        )
        paste_btn.pack(side=tk.LEFT)
        
        # Cancel button
        cancel_btn = ttk.Button(
            button_frame,
            text="Cancel",
            command=self._on_cancel,
            width=10
        )
        cancel_btn.pack(side=tk.RIGHT, padx=(5, 0))
        
        # Save button
        save_btn = ttk.Button(
            button_frame,
            text="💾 Save to Library",
            command=self._on_save,
            width=15
        )
        save_btn.pack(side=tk.RIGHT)
    
    def _update_char_count(self, event=None):
        """Update the character count display."""
        content = self.text_area.get('1.0', tk.END).strip()
        char_count = len(content)
        word_count = len(content.split()) if content else 0
        self.char_count_var.set(f"{char_count} characters, ~{word_count} words")
    
    def _paste_from_clipboard(self):
        """Paste content from clipboard into the text area."""
        try:
            clipboard_content = self.dialog.clipboard_get()
            if clipboard_content:
                # Insert at cursor position (or replace selection)
                try:
                    self.text_area.delete(tk.SEL_FIRST, tk.SEL_LAST)
                except tk.TclError:
                    pass  # No selection
                self.text_area.insert(tk.INSERT, clipboard_content)
                self._update_char_count()
        except tk.TclError:
            messagebox.showinfo("Clipboard Empty", "No text found in clipboard.")
    
    def _on_save(self):
        """Save the pasted content to the library."""
        content = self.text_area.get('1.0', tk.END).strip()
        
        if not content:
            messagebox.showwarning("No Content", "Please paste some content before saving.")
            return
        
        # Get or generate title
        title = self.title_var.get().strip()
        if not title:
            # Generate title from first line or content preview
            first_line = content.split('\n')[0][:50]
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            if self.source_type == "twitter":
                title = f"X Post - {timestamp}"
            else:
                title = f"Pasted: {first_line}..." if len(first_line) >= 50 else f"Pasted: {first_line}"
        
        # Store result and close
        self.result = {
            'content': content,
            'title': title,
            'source_url': self.source_url,
            'source_type': self.source_type
        }
        
        self.dialog.destroy()
        
        # Save to library via the app
        self._save_to_library()
    
    def _save_to_library(self):
        """Save the pasted content to the document library."""
        if not self.result:
            return
        
        from document_library import add_document_to_library
        
        content = self.result['content']
        title = self.result['title']
        source_url = self.result['source_url']
        source_type = self.result['source_type']
        
        # Check if this looks like a YouTube transcript with timestamps
        entries = self._parse_youtube_transcript(content) if source_type == "youtube" else None
        
        if not entries:
            # Create entries from the content
            # Split into paragraphs for better structure
            paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
            if not paragraphs:
                paragraphs = [content]
            
            entries = []
            for i, para in enumerate(paragraphs):
                entries.append({
                    'start': i,
                    'text': para,
                    'location': f"Paragraph {i+1}"
                })
        
        # Set as current document
        self.app.current_entries = entries
        self.app.current_document_source = source_url if source_url else title
        self.app.current_document_type = source_type
        self.app.current_document_class = "source"
        self.app.current_document_metadata = {
            "source": source_type,
            "url": source_url,
            "pasted": True,
            "imported": datetime.datetime.now().isoformat() + 'Z'
        }
        
        # Add to library
        doc_id = add_document_to_library(
            doc_type=source_type,
            source=source_url if source_url else "Manual paste",
            title=title,
            entries=entries,
            document_class="source",
            metadata=self.app.current_document_metadata
        )
        
        # Clear thread (save first if needed)
        if self.app.thread_message_count > 0 and self.app.current_document_id:
            self.app.save_current_thread()
        self.app.current_thread = []
        self.app.thread_message_count = 0
        self.app.current_document_id = doc_id
        self.app.update_thread_status()
        
        # Load any saved thread for this document
        self.app.load_saved_thread()
        
        # Display in preview
        self.app.current_document_text = content
        self.app.display_source_in_preview(self.app.current_document_text)
        self.app.update_context_buttons('web')
        self.app.update_full_text_button()
        
        # Refresh library and show success
        self.app.refresh_library()
        self.app.set_status(f"✅ Saved: {title}")
    
    def _on_cancel(self):
        """Cancel and close the dialog."""
        self.result = None
        self.dialog.destroy()

    def _parse_youtube_transcript(self, content: str) -> list:
        """
        Parse YouTube transcript format with timestamps.
        
        YouTube transcripts typically look like:
        0:01
        hello everyone welcome to the show
        0:05
        today we're going to talk about...
        
        Or sometimes:
        0:01 hello everyone welcome to the show
        0:05 today we're going to talk about...
        
        Returns:
            List of entry dicts with 'text', 'start', 'location' keys,
            or None if content doesn't look like a YouTube transcript.
        """
        import re
        
        lines = content.strip().split('\n')
        
        # Check if this looks like a YouTube transcript
        # Look for timestamp patterns at the start of lines
        timestamp_pattern = re.compile(r'^(\d{1,2}):(\d{2})(?::(\d{2}))?(?:\s|$)')
        
        # Count lines that start with timestamps
        timestamp_lines = sum(1 for line in lines if timestamp_pattern.match(line.strip()))
        
        # If less than 20% of lines have timestamps, probably not a YouTube transcript
        if timestamp_lines < len(lines) * 0.1:
            return None
        
        entries = []
        current_timestamp = None
        current_seconds = 0
        current_text = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Check if line starts with a timestamp
            match = timestamp_pattern.match(line)
            
            if match:
                # Save previous entry if we have text
                if current_text and current_timestamp is not None:
                    entries.append({
                        'start': current_seconds,
                        'text': ' '.join(current_text),
                        'location': current_timestamp
                    })
                    current_text = []
                
                # Parse new timestamp
                hours_or_mins = int(match.group(1))
                mins_or_secs = int(match.group(2))
                secs = int(match.group(3)) if match.group(3) else 0
                
                # Determine if format is H:MM:SS or M:SS
                if match.group(3):  # Has seconds, so format is H:MM:SS
                    current_seconds = hours_or_mins * 3600 + mins_or_secs * 60 + secs
                    current_timestamp = f"{hours_or_mins}:{mins_or_secs:02d}:{secs:02d}"
                else:  # Format is M:SS
                    current_seconds = hours_or_mins * 60 + mins_or_secs
                    if hours_or_mins >= 60:
                        # Actually hours:minutes
                        current_timestamp = f"{hours_or_mins}:{mins_or_secs:02d}:00"
                        current_seconds = hours_or_mins * 3600 + mins_or_secs * 60
                    else:
                        current_timestamp = f"{hours_or_mins}:{mins_or_secs:02d}"
                
                # Check if there's text after the timestamp on the same line
                rest_of_line = line[match.end():].strip()
                if rest_of_line:
                    current_text.append(rest_of_line)
            else:
                # Regular text line
                if current_timestamp is not None:
                    current_text.append(line)
                else:
                    # Text before first timestamp - create entry with timestamp 0
                    if not entries:
                        current_timestamp = "0:00"
                        current_seconds = 0
                    current_text.append(line)
        
        # Don't forget the last entry
        if current_text and current_timestamp is not None:
            entries.append({
                'start': current_seconds,
                'text': ' '.join(current_text),
                'location': current_timestamp
            })
        
        return entries if entries else None
