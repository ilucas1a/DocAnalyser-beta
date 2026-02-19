"""
output_formatter.py - Output Formatting
Handles formatting for different output types (RTF, Markdown rendering)
"""

import tkinter as tk
from tkinter import scrolledtext
from tkinter.font import Font
from typing import Dict
import re

# Import from our modules
from document_fetcher import clean_text_encoding


# -------------------------
# RTF Generation
# -------------------------

def generate_rtf_content(title: str, content: str, metadata: Dict = None) -> str:
    """
    Generate RTF content with proper character escaping and Unicode handling

    Args:
        title: Document title
        content: Main content text
        metadata: Optional metadata dictionary

    Returns:
        RTF-formatted string ready to save to .rtf file
    """

    def escape_rtf(text: str) -> str:
        """Escape special RTF characters and convert Unicode to RTF codes"""
        # First, replace backslash (must be first!)
        text = text.replace('\\', '\\\\')

        # Replace curly braces
        text = text.replace('{', '\\{')
        text = text.replace('}', '\\}')

        # Convert common Unicode characters to RTF escape codes
        unicode_replacements = {
            '—': '\\u8212-',  # em dash
            '–': '\\u8211-',  # en dash
            ''': '\\u8216-',   # left single quote
            ''': '\\u8217-',  # right single quote
            '"': '\\u8220-',  # left double quote
            '"': '\\u8221-',  # right double quote
            '…': '\\u8230-',  # ellipsis
            '•': '\\u8226-',  # bullet
            '€': '\\u8364-',  # euro
            '£': '\\u163-',  # pound
            '©': '\\u169-',  # copyright
            '®': '\\u174-',  # registered
            '™': '\\u8482-',  # trademark
            '°': '\\u176-',  # degree
            'é': '\\u233-',  # e acute
            'è': '\\u232-',  # e grave
            'à': '\\u224-',  # a grave
            'á': '\\u225-',  # a acute
            'í': '\\u237-',  # i acute
            'ó': '\\u243-',  # o acute
            'ú': '\\u250-',  # u acute
            'ñ': '\\u241-',  # n tilde
            'ü': '\\u252-',  # u umlaut
            'ö': '\\u246-',  # o umlaut
            'ä': '\\u228-',  # a umlaut
            'ç': '\\u231-',  # c cedilla
            'É': '\\u201-',  # E acute
            'Ñ': '\\u209-',  # N tilde
            'Ü': '\\u220-',  # U umlaut
        }

        for char, code in unicode_replacements.items():
            text = text.replace(char, code)

        # Replace newlines with RTF line breaks
        text = text.replace('\n', '\\par\n')

        return text

    # Clean the content first to remove any encoding issues
    content = clean_text_encoding(content)
    title = clean_text_encoding(title)

    # Escape title and content
    escaped_title = escape_rtf(title)
    escaped_content = escape_rtf(content)

    # Build metadata string
    metadata_lines = []
    if metadata:
        for k, v in metadata.items():
            cleaned_key = clean_text_encoding(str(k))
            cleaned_val = clean_text_encoding(str(v))
            metadata_lines.append(f"{escape_rtf(cleaned_key)}: {escape_rtf(cleaned_val)}")
    metadata_str = '\\par\n'.join(metadata_lines) if metadata_lines else ''

    # Build RTF document with proper header
    rtf_content = (
        r'{\rtf1\ansi\ansicpg1252\deff0'
        r'{\fonttbl{\f0\fnil\fcharset0 Arial;}}'
        r'{\colortbl;\red0\green0\blue0;}'
        r'\viewkind4\uc1\pard\f0\fs24'
        '\n'
        rf'\b {escaped_title}\b0\par'
        '\n'
    )

    if metadata_str:
        rtf_content += rf'{metadata_str}\par' + '\n'

    rtf_content += (
        r'\par'
        '\n'
        rf'{escaped_content}'
        '\n'
        r'\par}'
    )

    return rtf_content


# -------------------------
# Markdown Rendering for Preview
# -------------------------

def render_markdown_in_text_widget(text_widget: scrolledtext.ScrolledText, content: str, font_size: int = 10):
    """
    Render markdown-style formatting in a tk.Text widget.
    Supports: **bold**, *italic*, # headers, and bullets

    Args:
        text_widget: Tkinter ScrolledText widget to render into
        content: Markdown-formatted text content
        font_size: Base font size (default 10)
    """

    # Clear existing content
    text_widget.config(state=tk.NORMAL)
    text_widget.delete('1.0', tk.END)

    # Create Font objects - all same size for clean look
    normal_font = Font(family='Arial', size=font_size)
    bold_font = Font(family='Arial', size=font_size, weight='bold')
    italic_font = Font(family='Arial', size=font_size, slant='italic')
    header_font = Font(family='Arial', size=font_size, weight='bold')

    # Configure tags
    text_widget.tag_configure('bold', font=bold_font)
    text_widget.tag_configure('italic', font=italic_font)
    text_widget.tag_configure('header', font=header_font, foreground='#2c3e50')
    text_widget.tag_configure('bullet', lmargin1=20, lmargin2=35)

    # Process line by line
    lines = content.split('\n')

    for line in lines:
        # Headers: # Header or ## Header
        if line.strip().startswith('#'):
            level = len(line) - len(line.lstrip('#'))
            text = line.lstrip('# ').strip()
            text_widget.insert(tk.END, text + '\n', 'header')
            continue

        # Bullets: - item or * item
        if line.strip().startswith(('- ', '* ')):
            text = '• ' + line.strip()[2:]
            text_widget.insert(tk.END, text + '\n', 'bullet')
            continue

        # Process bold and italic inline
        # Pattern: **bold** or *italic*
        current_pos = 0

        # Find all markdown patterns
        bold_pattern = r'\*\*(.*?)\*\*'
        italic_pattern = r'\*(.*?)\*'

        # Combine patterns - bold first (to avoid matching ** as two *)
        combined_pattern = r'(\*\*(.*?)\*\*|\*(.*?)\*)'

        matches = list(re.finditer(combined_pattern, line))

        if matches:
            for match in matches:
                # Insert text before the match
                if match.start() > current_pos:
                    text_widget.insert(tk.END, line[current_pos:match.start()])

                # Insert the formatted text
                if match.group(0).startswith('**'):
                    # Bold
                    text_widget.insert(tk.END, match.group(2), 'bold')
                else:
                    # Italic
                    text_widget.insert(tk.END, match.group(3), 'italic')

                current_pos = match.end()

            # Insert remaining text
            if current_pos < len(line):
                text_widget.insert(tk.END, line[current_pos:])
            text_widget.insert(tk.END, '\n')
        else:
            # No markdown formatting, just insert the line
            text_widget.insert(tk.END, line + '\n')

    text_widget.config(state=tk.DISABLED)


# -------------------------
# Future Format Support
# -------------------------

def generate_html_content(title: str, content: str, metadata: Dict = None) -> str:
    """
    Generate HTML content (placeholder for future implementation)

    Args:
        title: Document title
        content: Main content text
        metadata: Optional metadata dictionary

    Returns:
        HTML-formatted string
    """
    # Placeholder for future HTML export functionality
    raise NotImplementedError("HTML export not yet implemented")


def generate_markdown_content(title: str, content: str, metadata: Dict = None) -> str:
    """
    Generate Markdown content (placeholder for future implementation)

    Args:
        title: Document title
        content: Main content text
        metadata: Optional metadata dictionary

    Returns:
        Markdown-formatted string
    """
    # Placeholder for future Markdown export functionality
    raise NotImplementedError("Markdown export not yet implemented")