"""
context_help.py - Contextual Help System for DocAnalyser

Provides F1 help popups for any button or widget.
Users press F1 while hovering over a widget to see help, click X to close.

Help texts are loaded from help_texts.json for easy editing.

Usage:
    from context_help import add_help, HELP_TEXTS, show_app_overview, show_elevator_pitch
    
    # Simple usage - add to any button:
    add_help(my_button, **HELP_TEXTS.get("button_key", {}))
    
    # Show app overview:
    show_app_overview(root)
"""

import tkinter as tk
from tkinter import ttk, scrolledtext
import json
import os
import re
from typing import Dict, List, Optional


# =========================================
# LOAD HELP TEXTS FROM JSON
# =========================================

def _get_help_texts_path():
    """Get the path to help_texts.json"""
    # Look in same directory as this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(script_dir, "help_texts.json")


def _load_help_texts():
    """Load help texts from JSON file, with fallback to empty dict"""
    json_path = _get_help_texts_path()
    
    try:
        if os.path.exists(json_path):
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Remove comment keys (but keep the special display entries)
                _KEEP = {'_app_overview', '_elevator_pitch'}
                return {k: v for k, v in data.items() if not k.startswith('_') or k in _KEEP}
        else:
            return {}
    except Exception as e:
        return {}


# Load on import
HELP_TEXTS = _load_help_texts()


def reload_help_texts():
    """Reload help texts from JSON (call after editing the file)"""
    global HELP_TEXTS
    HELP_TEXTS = _load_help_texts()
    return HELP_TEXTS


# =========================================
# LINK HANDLER REGISTRY
# Supports [LINK:target_id|Display text] markers in help descriptions.
# Clicking the rendered hyperlink calls the registered handler.
# =========================================

_LINK_HANDLERS: dict = {}
_LINK_PAT = re.compile(r'\[LINK:([^|]+)\|([^\]]+)\]')


def register_link_handler(target_id: str, handler):
    """
    Register a callable for [LINK:target_id|display text] markers.
    handler(parent_window) is called when the link is clicked in a popup.
    """
    _LINK_HANDLERS[target_id] = handler


def _dispatch_link(target_id: str, parent_window):
    """Dispatch a link click to the registered handler."""
    handler = _LINK_HANDLERS.get(target_id)
    if handler:
        try:
            handler(parent_window)
        except Exception as e:
            tk.messagebox.showerror('Link Error', str(e), parent=parent_window)
    else:
        tk.messagebox.showinfo(
            'Link',
            f'No handler registered for: {target_id}',
            parent=parent_window,
        )


# =========================================
# FULL-SCREEN HELP WINDOWS
# =========================================

def _get_help_window_content(key: str):
    """Return (title, content) for a special full-screen help key."""
    entry = HELP_TEXTS.get(key, {})
    title   = entry.get('title',   'DocAnalyser Help')
    content = entry.get('content', 'No content available. Check help_texts.json.')
    return title, content


def show_help_window(parent, key: str):
    """
    Generic full-screen help window.  Reads title and content from
    HELP_TEXTS[key].  Both _app_overview and _elevator_pitch use this.

    Styling matches the main DocAnalyser UI palette:
      - Dark slate header (#37474f) with title + Minimise + Close buttons
      - Light grey body (#f0f0f0) with near-black Arial text
      - Non-modal: does not block the main window
      - Centred on screen with at least 60 px inset from each edge
    """
    window_title, overview_content = _get_help_window_content(key)

    # ── Window setup ──────────────────────────────────────────────────────
    win = tk.Toplevel(parent)
    win.title(window_title)
    win.resizable(True, True)
    # Non-modal: no grab_set(), no transient() — window can be moved freely
    # and the main app remains usable while it's open.
    win.lift()
    win.focus_force()

    # ── Dimensions & position ─────────────────────────────────────────────
    W, H = 720, 640
    sw = win.winfo_screenwidth()
    sh = win.winfo_screenheight()
    x  = max(60, (sw - W) // 2)
    y  = max(40, (sh - H) // 2)
    win.geometry(f"{W}x{H}+{x}+{y}")
    win.minsize(500, 400)

    # ── Colour / font constants (matches main DocAnalyser palette) ────────
    HDR_BG   = "#37474f"   # dark slate — matches dialog headers throughout app
    HDR_FG   = "#ffffff"
    BODY_BG  = "#f0f0f0"   # standard app background
    TEXT_FG  = "#1a1a1a"   # near-black — standard app text colour
    BTN_BG   = "#e0e0e0"   # button-bar background
    FONT_HDR = ("Arial", 13, "bold")
    FONT_TXT = ("Arial", 10)

    win.configure(bg=BODY_BG)

    # ── Header bar with title + Minimise + Close ──────────────────────────
    hdr = tk.Frame(win, bg=HDR_BG, height=48)
    hdr.pack(fill=tk.X)
    hdr.pack_propagate(False)

    tk.Label(
        hdr,
        text=f"  {window_title}",
        font=FONT_HDR,
        bg=HDR_BG,
        fg=HDR_FG,
        anchor="w",
    ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))

    # Close button (×)
    _close_btn = tk.Button(
        hdr, text=" ✕ ", font=("Arial", 11, "bold"),
        bg=HDR_BG, fg=HDR_FG,
        activebackground="#c62828", activeforeground="white",
        relief=tk.FLAT, bd=0, cursor="hand2",
        command=win.destroy,
    )
    _close_btn.pack(side=tk.RIGHT, padx=(0, 4), pady=8)
    _close_btn.bind("<Enter>", lambda e: _close_btn.config(bg="#c62828", fg="white"))
    _close_btn.bind("<Leave>", lambda e: _close_btn.config(bg=HDR_BG,   fg=HDR_FG))

    # Minimise button (–)
    _min_btn = tk.Button(
        hdr, text=" – ", font=("Arial", 11, "bold"),
        bg=HDR_BG, fg=HDR_FG,
        activebackground="#546e7a", activeforeground="white",
        relief=tk.FLAT, bd=0, cursor="hand2",
        command=win.iconify,
    )
    _min_btn.pack(side=tk.RIGHT, padx=(0, 2), pady=8)
    _min_btn.bind("<Enter>", lambda e: _min_btn.config(bg="#546e7a", fg="white"))
    _min_btn.bind("<Leave>", lambda e: _min_btn.config(bg=HDR_BG,   fg=HDR_FG))

    # ── Scrollable content area ───────────────────────────────────────────
    content_frame = tk.Frame(win, bg=BODY_BG, padx=14, pady=10)
    content_frame.pack(fill=tk.BOTH, expand=True)

    text_widget = scrolledtext.ScrolledText(
        content_frame,
        wrap=tk.WORD,
        font=FONT_TXT,
        bg="#fffde7",          # soft yellow — matches editable text areas throughout app
        fg=TEXT_FG,
        relief=tk.FLAT,
        highlightthickness=1,
        highlightbackground="#cccccc",
        padx=14,
        pady=10,
    )
    text_widget.pack(fill=tk.BOTH, expand=True)

    # Configure tags for headings and normal body text
    text_widget.tag_config(
        "heading",
        font=("Arial", 11, "bold"),
        foreground=TEXT_FG,
        spacing1=8,    # space above heading
        spacing3=2,    # space below heading
    )
    text_widget.tag_config(
        "body",
        font=FONT_TXT,
        foreground=TEXT_FG,
    )

    # Render content line by line.
    # Lines beginning with "## " are rendered as bold headings (marker stripped).
    # All other lines are rendered as body text.
    # Lines consisting only of separator characters (━ ─ = ╔ ╗ ╚ ╝ ║) are skipped.
    _SEPARATOR_CHARS = set("━─═╔╗╚╝║╠╣╦╩╪")
    for line in overview_content.splitlines():
        stripped = line.strip()
        # Skip pure separator / box-drawing lines
        if stripped and all(ch in _SEPARATOR_CHARS for ch in stripped):
            continue
        if stripped.startswith("## "):
            text_widget.insert(tk.END, stripped[3:] + "\n", "heading")
        else:
            text_widget.insert(tk.END, line + "\n", "body")

    text_widget.config(state=tk.DISABLED)

    # ── Bottom button bar ─────────────────────────────────────────────────
    btn_bar = tk.Frame(win, bg=BTN_BG, height=48)
    btn_bar.pack(fill=tk.X, side=tk.BOTTOM)
    btn_bar.pack_propagate(False)

    tk.Button(
        btn_bar,
        text="Close",
        font=("Arial", 10),
        width=12,
        relief=tk.FLAT,
        bg=BTN_BG,
        activebackground="#cccccc",
        command=win.destroy,
    ).pack(side=tk.RIGHT, padx=12, pady=10)

    win.bind("<Escape>", lambda e: win.destroy())


def show_app_overview(parent):
    """Show the application feature-reference overview window."""
    show_help_window(parent, '_app_overview')


def show_elevator_pitch(parent):
    """Show the 'Why Use DocAnalyser?' elevator pitch window."""
    show_help_window(parent, '_elevator_pitch')


# =========================================
# HELP POPUP CLASSES
# =========================================

class HelpPopup(tk.Toplevel):
    """
    A popup window showing contextual help.
    Has an X button in the top-right corner to close.
    Also closes when mouse leaves the popup area.
    """
    
    def __init__(
        self, 
        parent, 
        title: str, 
        description: str, 
        tips: List[str] = None,
        x: int = None,
        y: int = None,
        width: int = 300,
        on_close: callable = None  # Callback when popup closes
    ):
        super().__init__(parent)
        
        # Store close callback
        self.on_close = on_close
        
        # Track if popup is still alive
        self._is_alive = True
        
        # Remove window decorations (title bar, borders)
        self.overrideredirect(True)
        
        # Make it stay on top
        self.attributes('-topmost', True)
        
        # Make transient to parent (helps with modal windows)
        self.transient(parent)
        
        # Lift above other windows
        self.lift()
        
        # Store width for layout
        self.popup_width = width
        
        # Create content
        self._create_content(title, description, tips)
        
        # Position the popup
        self._position(x, y)
        
        # Start periodic mouse position check (more reliable than Leave events)
        self.after(500, self._check_mouse_position)  # Start after 500ms delay
    
    def _check_mouse_position(self):
        """Periodically check if mouse is still over popup"""
        if not self._is_alive:
            return
        
        try:
            # Get mouse position
            mouse_x = self.winfo_pointerx()
            mouse_y = self.winfo_pointery()
            
            # Get popup bounds
            popup_x = self.winfo_rootx()
            popup_y = self.winfo_rooty()
            popup_width = self.winfo_width()
            popup_height = self.winfo_height()
            
            # Add margin for less sensitive edges
            margin = 15
            
            # Check if mouse is outside popup bounds
            if (mouse_x < popup_x - margin or mouse_x > popup_x + popup_width + margin or
                mouse_y < popup_y - margin or mouse_y > popup_y + popup_height + margin):
                self._close_popup()
            else:
                # Schedule next check (every 250ms)
                self.after(250, self._check_mouse_position)
        except tk.TclError:
            # Window was destroyed
            self._is_alive = False
    
    def _close_popup(self, event=None):
        """Close the popup and notify callback"""
        if not self._is_alive:
            return
        
        self._is_alive = False
        
        if self.on_close:
            self.on_close()
        try:
            self.destroy()
        except:
            pass
        
        return "break"  # Prevent event propagation
    
    def _create_content(self, title: str, description: str, tips: List[str]):
        """Create the popup content"""
        
        # Main frame with border
        main_frame = tk.Frame(
            self, 
            bg='#D3D3D3',  # Light gray background
            bd=1, 
            relief='solid',
            highlightbackground='#808080',
            highlightthickness=1
        )
        main_frame.pack(fill='both', expand=True)
        
        # Header frame (title + X button)
        header_frame = tk.Frame(main_frame, bg='#C0C0C0')  # Slightly darker gray for header
        header_frame.pack(fill='x', padx=1, pady=1)
        
        # Title
        title_label = tk.Label(
            header_frame,
            text=f"  {title}",
            font=('Arial', 10, 'bold'),
            bg='#C0C0C0',
            fg='#000080',  # Navy blue
            anchor='w'
        )
        title_label.pack(side='left', fill='x', expand=True, pady=5)
        
        # X close button - using Button for more reliable click handling
        close_btn = tk.Button(
            header_frame,
            text="✕",
            font=('Arial', 9, 'bold'),
            bg='#C0C0C0',
            fg='#000080',
            activebackground='#ff6b6b',
            activeforeground='white',
            bd=0,
            padx=5,
            pady=2,
            cursor='hand2',
            command=self._close_popup
        )
        close_btn.pack(side='right', padx=5, pady=5)
        
        # Hover effect for close button
        close_btn.bind('<Enter>', lambda e: close_btn.config(bg='#ff6b6b', fg='white'))
        close_btn.bind('<Leave>', lambda e: close_btn.config(bg='#C0C0C0', fg='#000080'))
        
        # Content frame
        content_frame = tk.Frame(main_frame, bg='#D3D3D3')  # Light gray
        content_frame.pack(fill='both', expand=True, padx=10, pady=(5, 10))
        
        # Description (supports [LINK:target_id|Display text] hyperlink markers)
        self._render_description(content_frame, description)
        
        # Tips (if any)
        if tips:
            # Separator line
            separator = tk.Frame(content_frame, bg='#808080', height=1)  # Medium gray
            separator.pack(fill='x', pady=5)
            
            # Tips label
            tips_header = tk.Label(
                content_frame,
                text="💡 Tips:",
                font=('Arial', 9, 'bold'),
                bg='#D3D3D3',
                fg='#000080',  # Navy blue
                anchor='w'
            )
            tips_header.pack(fill='x')
            
            # Individual tips
            for tip in tips:
                tip_label = tk.Label(
                    content_frame,
                    text=f"  • {tip}",
                    font=('Arial', 9),
                    bg='#D3D3D3',
                    fg='#000080',  # Navy blue
                    justify='left',
                    anchor='w',
                    wraplength=self.popup_width - 40
                )
                tip_label.pack(fill='x')
    
    def _render_description(self, parent_frame: tk.Frame, description: str):
        """
        Render description text into parent_frame.

        Plain text with no markers uses a tk.Label (original auto-sizing).
        Text containing [LINK:target_id|Display text] markers uses a tk.Text
        widget so the link spans can be made clickable.
        """
        if not _LINK_PAT.search(description):
            # No links — use Label exactly as before
            tk.Label(
                parent_frame,
                text=description,
                font=('Arial', 9),
                bg='#D3D3D3',
                fg='#000080',
                justify='left',
                anchor='w',
                wraplength=self.popup_width - 30,
            ).pack(fill='x', pady=(0, 5))
            return

        # Description contains at least one link — use tk.Text for clickability.
        # Estimate display height from hard newlines + rough wrap estimate.
        n_lines   = description.count('\n')
        n_chars   = len(description)
        chars_per_line = max(20, (self.popup_width - 40) // 7)
        wrap_extra = max(0, n_chars // chars_per_line - n_lines)
        est_height = min(max(n_lines + wrap_extra + 2, 3), 25)

        text_w = tk.Text(
            parent_frame,
            font=('Arial', 9),
            bg='#D3D3D3',
            fg='#000080',
            bd=0,
            relief='flat',
            highlightthickness=0,
            wrap=tk.WORD,
            height=est_height,
            cursor='arrow',
            padx=0,
            pady=0,
        )
        text_w.pack(fill='x', pady=(0, 5))

        text_w.tag_config('normal', foreground='#000080', font=('Arial', 9))

        # re.split with capturing groups yields:
        # [pre_text, target, display, mid_text, target, display, ..., post_text]
        parts = _LINK_PAT.split(description)
        link_idx = 0
        i = 0
        while i < len(parts):
            chunk = parts[i]
            if chunk:
                text_w.insert(tk.END, chunk, 'normal')
            i += 1
            if i + 1 < len(parts):       # next two: target, display
                target  = parts[i]
                display = parts[i + 1]
                tag     = f'_link_{link_idx}'
                link_idx += 1
                text_w.tag_config(
                    tag,
                    foreground='#1565C0',
                    underline=True,
                    font=('Arial', 9, 'bold'),
                )
                text_w.insert(tk.END, display, (tag,))
                text_w.tag_bind(
                    tag, '<Button-1>',
                    lambda e, t=target, p=self: _dispatch_link(t, p),
                )
                text_w.tag_bind(
                    tag, '<Enter>',
                    lambda e, w=text_w: w.config(cursor='hand2'),
                )
                text_w.tag_bind(
                    tag, '<Leave>',
                    lambda e, w=text_w: w.config(cursor='arrow'),
                )
                i += 2      # consumed target + display

        text_w.config(state=tk.DISABLED)

        # Shrink height to actual line count after insertion
        try:
            text_w.update_idletasks()
            actual = int(text_w.index('end-1c').split('.')[0])
            text_w.config(height=max(actual, 1))
        except Exception:
            pass

    def _position(self, x: int, y: int):
        """Position the popup near the mouse cursor"""
        
        # Update to get actual size
        self.update_idletasks()
        
        # Get popup dimensions
        popup_width = self.winfo_reqwidth()
        popup_height = self.winfo_reqheight()
        
        # Get screen dimensions
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        
        # Default to mouse position if not specified
        if x is None:
            x = self.winfo_pointerx() + 10
        if y is None:
            y = self.winfo_pointery() + 10
        
        # Adjust if popup would go off screen
        if x + popup_width > screen_width:
            x = screen_width - popup_width - 10
        if y + popup_height > screen_height:
            y = screen_height - popup_height - 10
        
        # Ensure not negative
        x = max(10, x)
        y = max(10, y)
        
        self.geometry(f"+{x}+{y}")


# =========================================
# BUILT-IN LINK TARGET: SUPPORTED FORMATS
# =========================================

def show_supported_formats(parent):
    """
    Show a formatted dialog listing every file type DocAnalyser can process.
    Called when the user clicks a [LINK:supported_formats|...] link in a help popup.
    """
    try:
        from config import SUPPORTED_AUDIO_FORMATS as _AUDIO
    except ImportError:
        _AUDIO = {}

    dlg = tk.Toplevel(parent)
    dlg.title('Supported File Formats — DocAnalyser')
    dlg.geometry('600x640')
    dlg.transient(parent)
    dlg.grab_set()
    dlg.resizable(True, True)

    # Header
    hdr = tk.Frame(dlg, bg='#C0C0C0')
    hdr.pack(fill=tk.X)
    tk.Label(
        hdr,
        text='📋  Supported File Formats',
        font=('Arial', 13, 'bold'),
        bg='#C0C0C0',
        fg='#000080',
        pady=10,
    ).pack()

    # Scrolled text body
    body = scrolledtext.ScrolledText(
        dlg,
        font=('Arial', 9),
        bg='#D3D3D3',
        fg='#000080',
        wrap=tk.WORD,
        padx=14,
        pady=8,
        bd=0,
        relief='flat',
        highlightthickness=0,
    )
    body.pack(fill=tk.BOTH, expand=True, padx=10, pady=(8, 4))

    body.tag_config('h',    font=('Arial', 10, 'bold'), foreground='#000080',
                    spacing1=10, spacing3=2)
    body.tag_config('sub',  font=('Arial', 9, 'bold'),  foreground='#333333')
    body.tag_config('item', font=('Arial', 9),           foreground='#000080',
                    lmargin1=12, lmargin2=12)
    body.tag_config('note', font=('Arial', 8, 'italic'), foreground='#555555',
                    lmargin1=28, lmargin2=28)

    def h(t):    body.insert(tk.END, t + '\n', 'h')
    def item(t): body.insert(tk.END, '  •  ' + t + '\n', 'item')
    def sub(t):  body.insert(tk.END, t + '\n', 'sub')
    def note(t): body.insert(tk.END, t + '\n', 'note')
    def gap():   body.insert(tk.END, '\n')

    h('📄 Documents')
    item('.pdf — PDF files  (text extraction + automatic OCR for scanned pages)')
    item('.docx — Word documents  (modern format)')
    item('.doc — Legacy Word format  (Windows only; requires Microsoft Word installed)')
    item('.txt — Plain text')
    item('.rtf — Rich Text Format')
    item('.html — HTML files  (readable text extracted)')
    gap()

    h('📊 Spreadsheets')
    item('.xlsx / .xls — Excel spreadsheets  (first sheet, with numeric column summaries)')
    item('.csv — Comma-separated values')
    gap()

    h('🎵 Audio Files  (transcribed to text)')
    for ext in ['.mp3', '.wav', '.m4a', '.ogg', '.flac', '.aac', '.wma', '.opus']:
        label = _AUDIO.get(ext, ext.upper().lstrip('.') + ' Audio')
        item(f'{ext} — {label}')
    gap()

    h('🎬 Video Files  (audio extracted and transcribed)')
    for ext in ['.mp4', '.avi', '.mov']:
        label = _AUDIO.get(ext, ext.upper().lstrip('.') + ' Video')
        item(f'{ext} — {label}')
    gap()

    h('🖼️ Image Files  (text extracted via OCR)')
    item('.png, .jpg / .jpeg — Common image formats')
    item('.tif / .tiff — TIFF images')
    item('.bmp — Bitmap images')
    item('.gif — GIF images')
    sub('   OCR modes available:')
    note('   Local (Tesseract) — free, fast, private; best for clearly printed text')
    note('   Cloud AI (Claude / GPT-4o / Gemini / Grok Vision) — handles handwriting,')
    note('   poor-quality scans, and complex layouts')
    gap()

    h('🌐 Online Sources')
    item('YouTube — captions fetched automatically; audio transcribed if no captions available')
    item('1,000+ video sites — TED, Vimeo, IAI.tv, and more  (via yt-dlp)')
    item('Substack — articles fetched directly')
    item('Twitter / X — threads fetched directly')
    item('Any web page — readable text extracted via URL')
    item('Direct PDF links — PDFs linked on web pages are downloaded and processed')
    gap()

    body.config(state=tk.DISABLED)

    # Close button
    btn_row = tk.Frame(dlg, bg='#D3D3D3', pady=6)
    btn_row.pack(fill=tk.X)
    ttk.Button(btn_row, text='Close', command=dlg.destroy, width=12).pack()

    # Centre on parent
    dlg.update_idletasks()
    x = parent.winfo_rootx() + (parent.winfo_width()  - dlg.winfo_width())  // 2
    y = parent.winfo_rooty() + (parent.winfo_height() - dlg.winfo_height()) // 2
    dlg.geometry(f'+{x}+{y}')
    dlg.bind('<Escape>', lambda e: dlg.destroy())


# Register built-in link handler
register_link_handler('supported_formats', show_supported_formats)


class HelpSystem:
    """
    Manages contextual help for the entire application.
    """
    
    def __init__(self, root: tk.Tk):
        self.root = root
        self.help_data: Dict[int, Dict] = {}  # widget id -> help info
        self.current_popup: Optional[HelpPopup] = None
        self._f1_bindings: set = set()  # track which toplevels have F1 bound
        
        # Bind F1 on root window
        self._bind_f1_on_toplevel(root)
    
    def _bind_f1_on_toplevel(self, toplevel):
        """Bind F1 key handler on a toplevel window"""
        wid = id(toplevel)
        if wid not in self._f1_bindings:
            toplevel.bind_all('<F1>', self._on_f1_pressed)
            self._f1_bindings.add(wid)
    
    def _on_f1_pressed(self, event):
        """Handle F1 key press — find widget under mouse and show its help"""
        # Get widget under mouse pointer
        try:
            x = event.widget.winfo_pointerx()
            y = event.widget.winfo_pointery()
            widget_under_mouse = event.widget.winfo_containing(x, y)
        except (tk.TclError, AttributeError):
            return
        
        if widget_under_mouse is None:
            return
        
        # Walk up the widget hierarchy to find one with help registered
        widget = widget_under_mouse
        while widget is not None:
            if id(widget) in self.help_data:
                self._show_help_for_widget(widget)
                return
            try:
                widget = widget.master
            except AttributeError:
                break
    
    def register(
        self, 
        widget: tk.Widget, 
        title: str,
        description: str,
        tips: List[str] = None
    ):
        """Register a widget for contextual help"""
        
        help_info = {
            "title": title,
            "description": description,
            "tips": tips or []
        }
        
        self.help_data[id(widget)] = help_info
        
        # Ensure F1 is bound on the widget's toplevel (for secondary windows)
        try:
            toplevel = widget.winfo_toplevel()
            self._bind_f1_on_toplevel(toplevel)
        except (tk.TclError, AttributeError):
            pass
    
    def _show_help_for_widget(self, widget: tk.Widget):
        """Show help popup for a widget (called from F1 handler)"""
        
        # Close any existing popup
        if self.current_popup:
            try:
                self.current_popup.destroy()
            except:
                pass
            self.current_popup = None
        
        # Get help data
        help_info = self.help_data.get(id(widget))
        if not help_info:
            return
        
        # Position near the mouse pointer
        try:
            x = widget.winfo_pointerx() + 10
            y = widget.winfo_pointery() + 10
        except tk.TclError:
            x, y = None, None
        
        # Create popup as child of the widget's toplevel window (not the root)
        # This ensures proper event handling for popups in secondary windows
        parent_window = widget.winfo_toplevel()
        
        # Create popup with close callback
        self.current_popup = HelpPopup(
            parent_window,
            title=help_info["title"],
            description=help_info["description"],
            tips=help_info["tips"],
            x=x,
            y=y,
            on_close=self._on_popup_closed
        )
    
    def _on_popup_closed(self):
        """Callback when popup is closed"""
        self.current_popup = None
    
    def close_popup(self):
        """Close the current popup if open"""
        if self.current_popup:
            try:
                self.current_popup.destroy()
            except:
                pass
            self.current_popup = None


# =========================================
# Simple Function Interface
# =========================================

# Global help system instance (created on first use)
_help_system: Optional[HelpSystem] = None


def add_help(
    widget: tk.Widget, 
    title: str = "Very quick intro",
    description: str = "No description available.",
    tips: List[str] = None
):
    """
    Add F1 help to any widget. User presses F1 while hovering to see help.
    
    Args:
        widget: The button or widget to add help to
        title: Title shown in popup header
        description: Main description text
        tips: Optional list of tips
    
    Example:
        add_help(my_button, **HELP_TEXTS.get("button_key", {}))
    """
    global _help_system
    
    # Skip if no valid info provided
    if not title and not description:
        return
    
    # Create help system if needed (uses widget's root window)
    if _help_system is None:
        root = widget.winfo_toplevel()
        _help_system = HelpSystem(root)
    
    _help_system.register(widget, title, description, tips)


def get_help(key: str) -> dict:
    """
    Get help text dictionary for a key.
    Returns empty dict if key not found.
    
    Usage:
        add_help(my_button, **get_help("button_key"))
    """
    return HELP_TEXTS.get(key, {})


# =========================================
# Demo / Test
# =========================================

def demo():
    """Demo the help system"""
    
    root = tk.Tk()
    root.title("Context Help Demo")
    root.geometry("500x400")
    
    # Header with help button
    header = tk.Frame(root)
    header.pack(fill=tk.X, padx=10, pady=10)
    
    tk.Label(
        header, 
        text="Press F1 over any button for help",
        font=('Arial', 11, 'bold')
    ).pack(side=tk.LEFT)
    
    # Red help button
    help_btn = tk.Label(
        header,
        text=" ❓ ",
        font=('Arial', 14, 'bold'),
        fg='white',
        bg='#cc0000',
        cursor='hand2',
        relief='raised',
        bd=2
    )
    help_btn.pack(side=tk.RIGHT)
    help_btn.bind('<Button-1>', lambda e: show_app_overview(root))
    
    # Create some buttons with help
    frame = ttk.Frame(root)
    frame.pack(pady=20)
    
    # Check if JSON loaded
    if HELP_TEXTS:
        status = f"✅ Loaded {len(HELP_TEXTS)} help entries from JSON"
    else:
        status = "⚠️ No help texts loaded - check help_texts.json"
    
    tk.Label(frame, text=status, fg='gray').pack(pady=10)
    
    btn1 = ttk.Button(frame, text="📚 Documents Library")
    btn1.pack(pady=5)
    add_help(btn1, **get_help("documents_library_button"))
    
    btn2 = ttk.Button(frame, text="⚙️ Settings")
    btn2.pack(pady=5)
    add_help(btn2, **get_help("settings_button"))
    
    btn3 = ttk.Button(frame, text="▶ Run Prompt")
    btn3.pack(pady=5)
    add_help(btn3, **get_help("run_prompt_button"))
    
    btn4 = ttk.Button(frame, text="🎤 Transcribe Audio")
    btn4.pack(pady=5)
    add_help(btn4, **get_help("transcribe_audio_button"))
    
    tk.Label(
        root,
        text="Click the red ❓ for app overview\nPress F1 over buttons for context help",
        fg='gray'
    ).pack(pady=10)
    
    root.mainloop()


if __name__ == "__main__":
    demo()
