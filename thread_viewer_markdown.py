"""
thread_viewer_markdown.py - Markdown Rendering Mixin for ThreadViewerWindow

Extracted from thread_viewer.py to improve maintainability.
Handles rendering markdown into the Tkinter Text widget, reconstructing
markdown from widget formatting, and making URLs clickable.

All methods access the parent ThreadViewerWindow's state via self.
"""

import os
import tkinter as tk
from tkinter import messagebox
import re
import webbrowser
from typing import Optional, Tuple


class MarkdownMixin:
    """
    Mixin providing markdown rendering and reconstruction for ThreadViewerWindow.
    
    Requires the following attributes on self:
        - thread_text: tk.Text widget for displaying content
        - url_locations: list (initialized by _make_links_clickable)
    """

    def _render_markdown_content(self, content: str):
        """
        Render markdown-formatted content into the thread text widget.
        Supports: **bold**, *italic*, # headers, bullets, numbered lists,
        and [SOURCE: "..."] seek links.
        """
        lines = content.split('\n')

        # SOURCE pattern — two variants:
        #   New (timestamp): [SOURCE: 14:23] or [SOURCE: 1:04:23]
        #   Old (sentence):  [SOURCE: "first sentence of paragraph"]
        # Use search() not match() so the marker is found anywhere on the line.
        _source_ts_pat = re.compile(
            r'\[SOURCE:\s*(\d{1,2}:\d{2}(?::\d{2})?)\s*\]',
            re.IGNORECASE
        )
        _source_sent_pat = re.compile(
            r'\[SOURCE:\s*["\u2018\u2019\u201c\u201d\'](.+?)["\u2018\u2019\u201c\u201d\']\]',
            re.IGNORECASE
        )
        # Numbered list item: leading digits, period, space  e.g. "1. " or "12. "
        _numbered_pat = re.compile(r'^\s*\d+\.\s+')

        # Auto-incrementing counter for numbered lists.
        # Resets whenever a non-numbered-list line is encountered (blank lines
        # between items are fine — blank lines don't reset the counter).
        _list_counter  = 0
        _last_was_heading = False   # suppress blank line immediately after a heading

        for line in lines:
            # New-style: [SOURCE: 14:23] — direct timestamp lookup (fast, local-AI friendly)
            ts_match = _source_ts_pat.search(line)
            if ts_match:
                _list_counter = 0
                _last_was_heading = False
                self._render_timestamp_seek_link(ts_match.group(1))
                continue

            # Old-style: [SOURCE: "sentence"] — verbatim text search (cloud AI)
            source_match = _source_sent_pat.search(line)
            if source_match:
                _list_counter = 0
                _last_was_heading = False
                self._render_source_seek_link(source_match.group(1))
                continue

            # Suppress blank lines that immediately follow a heading — they
            # create an unwanted gap between the heading and its body text.
            if not line.strip() and _last_was_heading:
                continue

            # Headers: # Header or ## Header
            if line.strip().startswith('#'):
                _list_counter = 0
                _last_was_heading = True
                text = line.lstrip('# ').strip()
                self.thread_text.insert(tk.END, text + '\n', 'header')
                continue

            _last_was_heading = False

            # Bullets: - item or * item
            if line.strip().startswith(('- ', '* ')):
                _list_counter = 0
                text = '• ' + line.strip()[2:]
                self.thread_text.insert(tk.END, text + '\n', 'bullet')
                continue

            # Numbered list items: "1. text", "2. text", etc.
            # Auto-increment so items always display in order even when the AI
            # outputs all items as "1." (standard Markdown practice).
            num_match = _numbered_pat.match(line)
            if num_match:
                _list_counter += 1
                item_text = line[num_match.end():]
                prefix = f"{_list_counter}. "
                self.thread_text.insert(tk.END, prefix, 'numbered')
                self._render_inline_markdown(item_text)
                self.thread_text.insert(tk.END, '\n', 'numbered')
                continue

            # Any other line (blank or body text) — do NOT reset the counter.
            # Body text, quotes, and blank lines sitting between numbered items
            # are common in AI output and must not break the sequence.
            # The counter only resets on structural Markdown elements (headers,
            # bullets) which are handled above with their own explicit resets.

            # Process bold and italic inline
            self._render_inline_markdown(line)
            self.thread_text.insert(tk.END, '\n', 'normal')
    
    def _render_inline_markdown(self, line: str):
        """
        Render inline markdown (bold, italic, underline) in a line of text.

        Handles: **bold**, *italic*, <u>underline</u>
        """
        # Pattern: **bold**, *italic*, or <u>underline</u>
        # Negative lookahead/lookbehind on the italic pattern ensures a lone *
        # never steals a character from a ** bold ** pair.
        combined_pattern = r'((?<![a-zA-Z0-9])\*\*(.*?)\*\*(?![a-zA-Z0-9])|\*(?!\*|\s)((?:(?!\*\*).)*?)(?<!\s|\*)\*(?!\*)|<u>(.*?)</u>)'

        current_pos = 0
        matches = list(re.finditer(combined_pattern, line))

        if matches:
            for match in matches:
                # Insert text before the match
                if match.start() > current_pos:
                    self.thread_text.insert(tk.END, line[current_pos:match.start()], 'normal')

                # Insert the formatted text
                if match.group(0).startswith('**'):
                    self.thread_text.insert(tk.END, match.group(2), 'bold')
                elif match.group(0).startswith('<u>'):
                    self.thread_text.insert(tk.END, match.group(4), 'underline')
                else:
                    self.thread_text.insert(tk.END, match.group(3), 'italic')

                current_pos = match.end()

            # Insert remaining text
            if current_pos < len(line):
                self.thread_text.insert(tk.END, line[current_pos:], 'normal')
        else:
            # No markdown formatting, just insert the line
            self.thread_text.insert(tk.END, line, 'normal')
    
    # ------------------------------------------------------------------
    # Audio seek links  ([SOURCE: "..."] markers in AI output)
    # ------------------------------------------------------------------

    def _find_entry_for_text(self, search_text: str):
        """
        Search self.current_entries for the entry whose text best matches
        search_text (a sentence quoted verbatim by the AI from the transcript).

        Strategy:
          1. Exact substring match on single entries and on sliding windows of
             2-3 consecutive entries (handles sentences that span a segment
             boundary in faster-whisper output).
          2. Word-overlap scoring as a fuzzy fallback (>=40% of significant
             words, length 4+, must overlap).

        Returns (entry_index, start_seconds) or None.
        """
        entries = getattr(self, 'current_entries', None)
        if not entries or not search_text:
            return None

        # Strip leading timestamp prefixes that the AI may have copied verbatim
        # from the formatted transcript (e.g. "[00:02] But the problem is...")
        # so they don't prevent an exact match against raw entry text.
        search_text_stripped = re.sub(r'^\[\d+:\d{2}(?::\d{2})?\]\s*', '', search_text.strip())
        search_clean = re.sub(r'\s+', ' ', search_text_stripped.lower())

        # Build (starting_entry_index, window_text) pairs for 1-, 2-, 3-entry windows
        windows = []
        for i, entry in enumerate(entries):
            t0 = entry.get('text', '').strip().lower()
            windows.append((i, t0))
            if i + 1 < len(entries):
                windows.append((i, t0 + ' ' + entries[i + 1].get('text', '').strip().lower()))
            if i + 2 < len(entries):
                windows.append((i, t0 + ' '
                                + entries[i + 1].get('text', '').strip().lower() + ' '
                                + entries[i + 2].get('text', '').strip().lower()))

        # Pass 1: exact substring match
        for idx, window_text in windows:
            if search_clean in window_text or window_text in search_clean:
                return (idx, entries[idx].get('start', 0.0))

        # Pass 2: word-overlap scoring (words 4+ chars only)
        search_words = set(re.findall(r'\b\w{4,}\b', search_clean))
        if len(search_words) < 2:
            return None

        best_score = 0.0
        best_idx = -1
        for idx, window_text in windows:
            window_words = set(re.findall(r'\b\w{4,}\b', window_text))
            if not window_words:
                continue
            score = len(search_words & window_words) / len(search_words)
            if score > best_score:
                best_score = score
                best_idx = idx

        if best_score >= 0.4 and best_idx >= 0:
            return (best_idx, entries[best_idx].get('start', 0.0))

        return None

    @staticmethod
    def _fmt_seek_time(seconds: float) -> str:
        """Format seconds as MM:SS or H:MM:SS for seek link labels."""
        s = max(0, int(seconds))
        if s >= 3600:
            return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"
        return f"{s // 60:02d}:{s % 60:02d}"

    def _render_timestamp_seek_link(self, ts_str: str):
        """
        Resolve a [SOURCE: MM:SS] marker to a direct seek link.

        Unlike _render_source_seek_link (which searches entries for matching
        text), this converts the timestamp string directly to seconds and
        renders a clickable \u25b6 Jump to MM:SS link.  No entry lookup needed.

        This is the preferred mechanism for local AI models since copying
        a timestamp token is far more reliable than reproducing exact sentences.
        """
        seconds = self._ts_to_seconds(ts_str)
        time_str = self._fmt_seek_time(seconds)
        link_text = f"\u25b6 Jump to {time_str}"

        if not hasattr(self, '_seek_locations'):
            self._seek_locations = []

        seek_idx = len(self._seek_locations)
        tag_name = f"seek_{seek_idx}"

        font_size = self._get_font_size()
        self.thread_text.tag_config(
            tag_name,
            foreground='#1565C0',
            underline=True,
            font=('Arial', font_size, 'bold'),
        )
        self.thread_text.insert(tk.END, link_text, (tag_name,))
        self.thread_text.insert(tk.END, '\n', 'normal')

        self._seek_locations.append((tag_name, seconds))

        self.thread_text.tag_bind(
            tag_name, "<Button-1>",
            lambda e, s=seconds: self._on_seek_link_click(s)
        )
        self.thread_text.tag_bind(
            tag_name, "<Enter>",
            lambda e: self.thread_text.config(cursor="hand2")
        )
        self.thread_text.tag_bind(
            tag_name, "<Leave>",
            lambda e: self.thread_text.config(cursor="")
        )

    def _render_source_seek_link(self, search_text: str):
        """
        Resolve a [SOURCE: "..."] marker to an audio timestamp and insert a
        clickable seek link (e.g. "\u25b6 Jump to 01:23") into the text widget.

        If no entry matches the search_text the marker is silently omitted,
        keeping the summary clean even when the model quotes imprecisely.
        """
        result = self._find_entry_for_text(search_text)
        if result is None:
            return  # No match — silently omit

        entry_idx, start_seconds = result
        time_str = self._fmt_seek_time(start_seconds)
        link_text = f"\u25b6 Jump to {time_str}"

        if not hasattr(self, '_seek_locations'):
            self._seek_locations = []

        seek_idx = len(self._seek_locations)
        tag_name = f"seek_{seek_idx}"

        font_size = self._get_font_size()
        self.thread_text.tag_config(
            tag_name,
            foreground='#1565C0',
            underline=True,
            font=('Arial', font_size, 'bold'),
        )
        self.thread_text.insert(tk.END, link_text, (tag_name,))
        self.thread_text.insert(tk.END, '\n', 'normal')

        self._seek_locations.append((tag_name, start_seconds))

        # Bind click: seek to position and auto-start playback
        self.thread_text.tag_bind(
            tag_name, "<Button-1>",
            lambda e, s=start_seconds: self._on_seek_link_click(s)
        )
        self.thread_text.tag_bind(
            tag_name, "<Enter>",
            lambda e: self.thread_text.config(cursor="hand2")
        )
        self.thread_text.tag_bind(
            tag_name, "<Leave>",
            lambda e: self.thread_text.config(cursor="")
        )

    def _on_seek_link_click(self, seconds: float):
        """
        Seek the transcript player to `seconds` and start playback.
        If the player is unavailable because the audio file has moved,
        offer a Locate File browser so the user can relink it without
        re-transcribing.
        """
        if getattr(self, '_edit_mode_active', False):
            return

        player = getattr(self, 'transcript_player', None)
        if player is not None:
            # play() seeks AND starts playback; seek_to() only repositions silently
            player.play(from_position=seconds)
            return

        # No player — try to locate and link the audio file
        self._locate_and_link_audio_file(seek_to_seconds=seconds)

    def _locate_and_link_audio_file(self, seek_to_seconds: float = None):
        """
        Open a file-browser so the user can locate a moved/renamed audio file.
        On success:
          - updates self._audio_path
          - persists the new path to the library record
          - spins up the transcript player immediately
          - optionally seeks to seek_to_seconds

        Called from:
          - _on_seek_link_click  (when no player exists and a link was clicked)
          - the 'Locate File' button in _create_player_bar (file-not-found notice)
        """
        import tkinter.filedialog as fd

        # Check whether pygame is even installed first
        try:
            import importlib.util as _ilu
            if _ilu.find_spec('pygame') is None:
                messagebox.showinfo(
                    "Audio Not Available",
                    "Audio playback requires pygame.\n\n"
                    "Install it with:\n    pip install pygame\n\n"
                    "Then restart DocAnalyser."
                )
                return
        except Exception:
            pass

        stored_path = getattr(self, '_audio_path', None)
        initial_dir = (
            os.path.dirname(stored_path)
            if stored_path and os.path.isdir(os.path.dirname(stored_path))
            else os.path.expanduser('~')
        )

        new_path = fd.askopenfilename(
            title="Locate audio file",
            filetypes=[
                ("Audio / Video files",
                 "*.mp3 *.wav *.m4a *.aac *.ogg *.flac "
                 "*.mp4 *.mkv *.mov *.avi *.webm"),
                ("All files", "*.*"),
            ],
            initialdir=initial_dir,
        )
        if not new_path or not os.path.isfile(new_path):
            return  # User cancelled or picked nothing

        # Persist new path to library so next open finds it automatically
        self._audio_path = new_path
        doc_id = getattr(self.app, 'current_document_id', None) if self.app else None
        if doc_id:
            try:
                from document_library import get_document_by_id, update_document_metadata
                lib_doc = get_document_by_id(doc_id)
                if lib_doc:
                    meta = dict(lib_doc.get('metadata') or {})
                    meta['audio_file_path'] = new_path
                    update_document_metadata(doc_id, meta)
            except Exception as e:
                print(f"Could not persist new audio path: {e}")

        # Remove the "file not found" notice widget if present
        notice = getattr(self, '_audio_missing_notice', None)
        if notice is not None:
            try:
                notice.destroy()
            except Exception:
                pass
            self._audio_missing_notice = None

        # Spin up the player
        try:
            from transcript_player import TranscriptPlayer, is_player_available

            if not is_player_available(new_path, self.current_entries):
                messagebox.showwarning(
                    "File Linked",
                    f"File linked but could not start player.\n\n"
                    "Please close and reopen the Thread Viewer."
                )
                return

            # Create player frame if it doesn't exist yet (file was missing at startup)
            if not hasattr(self, '_player_frame') or not self._player_frame.winfo_exists():
                player_frame = ttk.LabelFrame(
                    self.window, text="Audio Playback", padding=(4, 2)
                )
                # Pack it just before the main content frame so it sits above the text
                content = getattr(self, '_content_frame', None)
                if content and content.winfo_exists():
                    player_frame.pack(fill=tk.X, padx=10, pady=(0, 4),
                                      before=content)
                else:
                    player_frame.pack(fill=tk.X, padx=10, pady=(0, 4))
                self._player_frame = player_frame

            _status_cb = None
            if getattr(self, 'app', None) and hasattr(self.app, 'set_status'):
                _status_cb = self.app.set_status
            self.transcript_player = TranscriptPlayer(
                parent=self._player_frame,
                audio_path=new_path,
                entries=self.current_entries,
                text_widget=self.thread_text,
                config=self.config,
                status_callback=_status_cb,
            )
            self.transcript_player.pack(fill=tk.X)
            if seek_to_seconds is not None:
                self.transcript_player.play(from_position=seek_to_seconds)
            return

        except Exception as e:
            print(f"Could not reinitialise transcript player: {e}")
            messagebox.showinfo(
                "File Linked",
                f"Audio file linked:\n  {new_path}\n\n"
                "Please close and reopen the Thread Viewer to "
                "activate the audio player."
            )

    # ------------------------------------------------------------------
    # Source-text timestamp seek links
    # ------------------------------------------------------------------

    @staticmethod
    def _ts_to_seconds(ts_str: str) -> float:
        """
        Convert a MM:SS or HH:MM:SS string to a float number of seconds.
        Used when making source-document timestamps clickable.
        """
        parts = ts_str.split(':')
        try:
            if len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
            elif len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        except (ValueError, IndexError):
            pass
        return 0.0

    def _insert_source_text_with_seek_links(self, text: str) -> None:
        """
        Insert source-document text into thread_text, turning any
        [MM:SS] or [HH:MM:SS] timestamp tokens into clickable seek links.

        Seek links use the same _seek_locations list and _on_seek_link_click
        handler as the [SOURCE: "..."] mechanism, so reset timing (handled
        in _refresh_thread_display) applies to both automatically.

        If the transcript player is not active the timestamps are still
        rendered as links; _on_seek_link_click shows a friendly "Audio Not
        Available" dialog in that case.

        Falls back to a plain source_text insert if anything goes wrong so
        the viewer is never left blank.
        """
        import re
        TS_PAT = re.compile(r'\[(\d{1,2}:\d{2}(?::\d{2})?)\]')

        if not hasattr(self, '_seek_locations'):
            self._seek_locations = []

        font_size = self._get_font_size()
        last_end = 0

        try:
            for m in TS_PAT.finditer(text):
                # Plain text before this timestamp
                before = text[last_end:m.start()]
                if before:
                    self.thread_text.insert(tk.END, before, 'source_text')

                ts_str  = m.group(1)
                seconds = self._ts_to_seconds(ts_str)
                link_text = f'[{ts_str}]'

                seek_idx = len(self._seek_locations)
                tag_name = f'seek_{seek_idx}'

                self.thread_text.tag_config(
                    tag_name,
                    foreground='#1565C0',
                    underline=True,
                    font=('Arial', font_size),
                )
                self.thread_text.insert(tk.END, link_text, (tag_name,))
                self._seek_locations.append((tag_name, seconds))

                self.thread_text.tag_bind(
                    tag_name, '<Button-1>',
                    lambda e, s=seconds: self._on_seek_link_click(s)
                )
                self.thread_text.tag_bind(
                    tag_name, '<Enter>',
                    lambda e: self.thread_text.config(cursor='hand2')
                )
                self.thread_text.tag_bind(
                    tag_name, '<Leave>',
                    lambda e: self.thread_text.config(cursor='')
                )

                last_end = m.end()

            # Any remaining text after the last timestamp
            remainder = text[last_end:]
            if remainder:
                self.thread_text.insert(tk.END, remainder, 'source_text')

        except Exception:
            # Safety fallback: plain insert so viewer is never blank
            self.thread_text.insert(tk.END, text, 'source_text')

    # ------------------------------------------------------------------
    # URL hyperlinks
    # ------------------------------------------------------------------

    def _make_links_clickable(self):
        """
        Find all URLs in the thread text and make them clickable.
        Handles both plain URLs and Markdown-style links [text](url).
        """
        # Configure hyperlink tag
        self.thread_text.tag_config("hyperlink", foreground="blue", underline=True)
        
        # Get all content
        content = self.thread_text.get('1.0', tk.END)
        
        # Pattern to find Markdown-style links: [text](url)
        markdown_pattern = r'\[([^\]]+)\]\((https?://[^\)]+)\)'
        # Pattern to find plain URLs (not already in markdown format)
        plain_url_pattern = r'(?<!\()(?<!\]\()(https?://[^\s\)\]\>"]+)'
        
        # Store URL positions and cleaned URLs
        self.url_locations = []
        
        # Find Markdown-style links
        for match in re.finditer(markdown_pattern, content):
            link_text = match.group(1)
            raw_url = match.group(2)
            # Remove spaces from URL (AI sometimes adds them)
            clean_url = raw_url.replace(' ', '')
            start_pos = f"1.0+{match.start()}c"
            end_pos = f"1.0+{match.end()}c"
            
            # Tag the entire link
            self.thread_text.tag_add("hyperlink", start_pos, end_pos)
            # Store for click handling
            self.url_locations.append((start_pos, end_pos, clean_url))
        
        # Find plain URLs (that aren't part of markdown links)
        for match in re.finditer(plain_url_pattern, content):
            url = match.group(0)
            # Clean up URL - remove trailing punctuation that's likely not part of the URL
            while url and url[-1] in '.,;:!?\'"':
                url = url[:-1]
            
            start_pos = f"1.0+{match.start()}c"
            end_pos = f"1.0+{match.start() + len(url)}c"
            
            # Check if this URL is already tagged (part of a markdown link)
            already_tagged = False
            for existing_start, existing_end, _ in self.url_locations:
                if (self.thread_text.compare(start_pos, ">=", existing_start) and 
                    self.thread_text.compare(end_pos, "<=", existing_end)):
                    already_tagged = True
                    break
            
            if not already_tagged:
                # Tag the URL
                self.thread_text.tag_add("hyperlink", start_pos, end_pos)
                # Store for click handling
                self.url_locations.append((start_pos, end_pos, url))
        
        # Bind click event
        self.thread_text.tag_bind("hyperlink", "<Button-1>", self._on_link_click)
        
        # Change cursor when hovering over links
        self.thread_text.tag_bind("hyperlink", "<Enter>",
                                   lambda e: self.thread_text.config(cursor="hand2"))
        self.thread_text.tag_bind("hyperlink", "<Leave>",
                                   lambda e: self.thread_text.config(cursor=""))
    
    def _on_link_click(self, event):
        """Handle click on a hyperlink."""
        # Get the index of the click
        index = self.thread_text.index(f"@{event.x},{event.y}")
        
        # Check which URL was clicked
        for start, end, url in self.url_locations:
            # Check if click is within this URL's range
            if (self.thread_text.compare(index, ">=", start) and 
                self.thread_text.compare(index, "<=", end)):
                # Open the URL in the default browser
                try:
                    webbrowser.open(url)
                except Exception as e:
                    messagebox.showerror("Error", f"Could not open URL:\n{url}\n\nError: {e}")
                return "break"

    def _reconstruct_markdown_content(self, content_lines: list) -> str:
        """
        Reconstruct markdown from content lines by reading formatting tags.
        
        Args:
            content_lines: List of (line_number, text) tuples
            
        Returns:
            Text with markdown formatting (## for headers, ** for bold, etc.)
        """
        result_lines = []
        
        for line_num, line_text in content_lines:
            if not line_text.strip():
                result_lines.append('')
                continue
            
            # Check block-level formatting at the start of the line
            line_start_pos = f"{line_num}.0"
            try:
                tags_at_start = self.thread_text.tag_names(line_start_pos)
            except:
                tags_at_start = ()
            
            is_header = 'header' in tags_at_start
            is_bullet = 'bullet' in tags_at_start or line_text.strip().startswith('•')
            is_numbered = 'numbered' in tags_at_start

            # Handle header lines
            if is_header:
                # Remove any existing ## prefix to avoid doubling
                clean_text = line_text.strip()
                if clean_text.startswith('## '):
                    clean_text = clean_text[3:]
                elif clean_text.startswith('### '):
                    clean_text = clean_text[4:]
                result_lines.append(f"## {clean_text}")
                continue

            # Handle numbered list lines
            if is_numbered:
                clean_text = line_text.strip()
                # Strip the leading "N. " so we can rewrite with the correct number
                import re as _re
                clean_text = _re.sub(r'^\d+\.\s+', '', clean_text)
                formatted_text = self._reconstruct_inline_markdown(
                    line_num, clean_text,
                    len(line_text) - len(line_text.lstrip())
                )
                # Use the line counter from the widget text as-is (already correct)
                # Reconstruct as "N. text" preserving inline formatting
                result_lines.append(f"1. {formatted_text}")
                continue
            
            # Handle bullet lines
            if is_bullet:
                clean_text = line_text.strip()
                if clean_text.startswith('•'):
                    clean_text = clean_text[1:].strip()
                elif clean_text.startswith('- '):
                    clean_text = clean_text[2:].strip()
                elif clean_text.startswith('* '):
                    clean_text = clean_text[2:].strip()
                # Reconstruct inline formatting within the bullet
                formatted_text = self._reconstruct_inline_markdown(line_num, clean_text, len(line_text) - len(line_text.lstrip()))
                result_lines.append(f"- {formatted_text}")
                continue
            
            # Regular line - check for inline formatting (bold, italic)
            formatted_text = self._reconstruct_inline_markdown(line_num, line_text, 0)
            result_lines.append(formatted_text)
        
        return '\n'.join(result_lines).strip()

    def _reconstruct_inline_markdown(self, line_num: int, text: str, col_offset: int) -> str:
        """
        Reconstruct inline markdown (**bold**, *italic*, <u>underline</u>)
        by reading tags from the Text widget.

        Args:
            line_num: The line number in the Text widget
            text: The text content
            col_offset: Column offset (for indented lines)

        Returns:
            Text with markdown markers for bold/italic and <u> tags for underline
        """
        if not text:
            return ""

        result = []
        current_bold      = False
        current_italic    = False
        current_underline = False
        current_segment   = []

        def _flush(seg, bold, italic, underline):
            """Wrap accumulated segment in the appropriate markers."""
            if not seg:
                return
            s = ''.join(seg)
            if bold and italic:
                result.append(f"***{s}***")
            elif bold:
                result.append(f"**{s}**")
            elif italic:
                result.append(f"*{s}*")
            elif underline:
                result.append(f"<u>{s}</u>")
            else:
                result.append(s)

        for i, char in enumerate(text):
            col = col_offset + i
            pos = f"{line_num}.{col}"

            try:
                tags = self.thread_text.tag_names(pos)
            except Exception:
                tags = ()

            # Bold: exclude whole-line bold tags (headers, speaker labels)
            is_bold      = 'bold'      in tags and 'header' not in tags and \
                           'user'      not in tags and 'assistant' not in tags
            is_italic    = 'italic'    in tags
            is_underline = 'underline' in tags

            if is_bold != current_bold or is_italic != current_italic or \
                    is_underline != current_underline:
                _flush(current_segment, current_bold, current_italic, current_underline)
                current_segment   = []
                current_bold      = is_bold
                current_italic    = is_italic
                current_underline = is_underline

            current_segment.append(char)

        _flush(current_segment, current_bold, current_italic, current_underline)
        return ''.join(result)
