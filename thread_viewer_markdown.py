"""
thread_viewer_markdown.py - Markdown Rendering Mixin for ThreadViewerWindow

Extracted from thread_viewer.py to improve maintainability.
Handles rendering markdown into the Tkinter Text widget, reconstructing
markdown from widget formatting, and making URLs clickable.

All methods access the parent ThreadViewerWindow's state via self.
"""

import tkinter as tk
from tkinter import messagebox
import re
import webbrowser


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
        Supports: **bold**, *italic*, # headers, and bullets
        """
        lines = content.split('\n')
        
        for line in lines:
            # Headers: # Header or ## Header
            if line.strip().startswith('#'):
                text = line.lstrip('# ').strip()
                self.thread_text.insert(tk.END, text + '\n', 'header')
                continue
            
            # Bullets: - item or * item
            if line.strip().startswith(('- ', '* ')):
                text = '• ' + line.strip()[2:]
                self.thread_text.insert(tk.END, text + '\n', 'bullet')
                continue
            
            # Process bold and italic inline
            self._render_inline_markdown(line)
            self.thread_text.insert(tk.END, '\n', 'normal')
    
    def _render_inline_markdown(self, line: str):
        """
        Render inline markdown (bold, italic) in a line of text.
        """
        # Pattern: **bold** or *italic*
        combined_pattern = r'(\*\*(.*?)\*\*|\*(.*?)\*)'
        
        current_pos = 0
        matches = list(re.finditer(combined_pattern, line))
        
        if matches:
            for match in matches:
                # Insert text before the match
                if match.start() > current_pos:
                    self.thread_text.insert(tk.END, line[current_pos:match.start()], 'normal')
                
                # Insert the formatted text
                if match.group(0).startswith('**'):
                    # Bold
                    self.thread_text.insert(tk.END, match.group(2), 'bold')
                else:
                    # Italic
                    self.thread_text.insert(tk.END, match.group(3), 'italic')
                
                current_pos = match.end()
            
            # Insert remaining text
            if current_pos < len(line):
                self.thread_text.insert(tk.END, line[current_pos:], 'normal')
        else:
            # No markdown formatting, just insert the line
            self.thread_text.insert(tk.END, line, 'normal')
    
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
        Reconstruct inline markdown (**bold**, *italic*) by reading tags from the Text widget.
        
        Args:
            line_num: The line number in the Text widget
            text: The text content
            col_offset: Column offset (for indented lines)
            
        Returns:
            Text with markdown markers for bold/italic
        """
        if not text:
            return ""
        
        result = []
        current_bold = False
        current_italic = False
        current_segment = []
        
        for i, char in enumerate(text):
            col = col_offset + i
            pos = f"{line_num}.{col}"
            
            try:
                tags = self.thread_text.tag_names(pos)
            except:
                tags = ()
            
            # Check for bold (but not header/user/assistant which are whole-line bold)
            is_bold = 'bold' in tags and 'header' not in tags and 'user' not in tags and 'assistant' not in tags
            is_italic = 'italic' in tags
            
            # If formatting changed, flush current segment
            if is_bold != current_bold or is_italic != current_italic:
                if current_segment:
                    segment_text = ''.join(current_segment)
                    if current_bold and current_italic:
                        result.append(f"***{segment_text}***")
                    elif current_bold:
                        result.append(f"**{segment_text}**")
                    elif current_italic:
                        result.append(f"*{segment_text}*")
                    else:
                        result.append(segment_text)
                    current_segment = []
                
                current_bold = is_bold
                current_italic = is_italic
            
            current_segment.append(char)
        
        # Flush final segment
        if current_segment:
            segment_text = ''.join(current_segment)
            if current_bold and current_italic:
                result.append(f"***{segment_text}***")
            elif current_bold:
                result.append(f"**{segment_text}**")
            elif current_italic:
                result.append(f"*{segment_text}*")
            else:
                result.append(segment_text)
        
        return ''.join(result)
