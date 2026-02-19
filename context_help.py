"""
context_help.py - Contextual Help System for DocAnalyser

Provides right-click help popups for any button or widget.
Users right-click to see help, click X to close.

Help texts are loaded from help_texts.json for easy editing.

Usage:
    from context_help import add_help, HELP_TEXTS, show_app_overview
    
    # Simple usage - add to any button:
    add_help(my_button, **HELP_TEXTS.get("button_key", {}))
    
    # Show app overview:
    show_app_overview(root)
"""

import tkinter as tk
from tkinter import ttk, scrolledtext
import json
import os
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
                # Remove comment keys (but keep _app_overview)
                return {k: v for k, v in data.items() if not k.startswith('_') or k == '_app_overview'}
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
# APP OVERVIEW - Loaded from JSON
# =========================================

def _get_app_overview():
    """Get app overview content from HELP_TEXTS (loaded from JSON)"""
    overview_data = HELP_TEXTS.get('_app_overview', {})
    return overview_data.get('content', 'No overview available. Check help_texts.json.')

def _get_app_overview_title():
    """Get app overview title from HELP_TEXTS (loaded from JSON)"""
    overview_data = HELP_TEXTS.get('_app_overview', {})
    return overview_data.get('title', 'DocAnalyser Intro')


def show_app_overview(parent):
    """Show the application overview window"""
    
    # Get title and content from JSON
    window_title = _get_app_overview_title()
    overview_content = _get_app_overview()
    
    overview = tk.Toplevel(parent)
    overview.title(window_title)
    overview.geometry("700x600")
    overview.transient(parent)
    
    # Make it modal
    overview.grab_set()
    
    # Header - matching context help popup colors
    header_frame = tk.Frame(overview, bg='#C0C0C0', height=60)  # Silver header
    header_frame.pack(fill=tk.X)
    header_frame.pack_propagate(False)
    
    tk.Label(
        header_frame,
        text=f"❓ {window_title}",
        font=('Arial', 16, 'bold'),
        bg='#C0C0C0',
        fg='#000080'  # Navy blue
    ).pack(pady=15)
    
    # Content - matching context help popup colors
    content_frame = tk.Frame(overview, bg='#D3D3D3', padx=10, pady=10)  # Light gray
    content_frame.pack(fill=tk.BOTH, expand=True)
    
    # Scrolled text for overview
    text_widget = scrolledtext.ScrolledText(
        content_frame,
        wrap=tk.WORD,
        font=('Consolas', 10),
        bg='#D3D3D3',  # Light gray background
        fg='#000080',  # Navy blue text
        padx=15,
        pady=15
    )
    text_widget.pack(fill=tk.BOTH, expand=True)
    text_widget.insert('1.0', overview_content)
    text_widget.config(state=tk.DISABLED)
    
    # Bottom buttons - matching colors
    button_frame = tk.Frame(overview, bg='#D3D3D3', padx=10, pady=10)
    button_frame.pack(fill=tk.X)
    
    ttk.Button(
        button_frame,
        text="Close",
        command=overview.destroy,
        width=15
    ).pack(side=tk.RIGHT, padx=5)
    
    # Center on parent
    overview.update_idletasks()
    x = parent.winfo_x() + (parent.winfo_width() - overview.winfo_width()) // 2
    y = parent.winfo_y() + (parent.winfo_height() - overview.winfo_height()) // 2
    overview.geometry(f"+{x}+{y}")
    
    # Bind Escape to close
    overview.bind('<Escape>', lambda e: overview.destroy())


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
        
        # Description
        desc_label = tk.Label(
            content_frame,
            text=description,
            font=('Arial', 9),
            bg='#D3D3D3',
            fg='#000080',  # Navy blue
            justify='left',
            anchor='w',
            wraplength=self.popup_width - 30
        )
        desc_label.pack(fill='x', pady=(0, 5))
        
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


class HelpSystem:
    """
    Manages contextual help for the entire application.
    """
    
    def __init__(self, root: tk.Tk):
        self.root = root
        self.help_data: Dict[int, Dict] = {}  # widget id -> help info
        self.current_popup: Optional[HelpPopup] = None
    
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
        
        # Bind right-click
        widget.bind('<Button-3>', lambda e: self._show_help(e, widget))
    
    def _show_help(self, event, widget: tk.Widget):
        """Show help popup for a widget"""
        
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
        
        # Create popup as child of the widget's toplevel window (not the root)
        # This ensures proper event handling for popups in secondary windows
        parent_window = widget.winfo_toplevel()
        
        # Create popup with close callback
        self.current_popup = HelpPopup(
            parent_window,
            title=help_info["title"],
            description=help_info["description"],
            tips=help_info["tips"],
            x=event.x_root,
            y=event.y_root,
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
    Add right-click help to any widget.
    
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
        text="Right-click any button for help",
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
        text="Click the red ❓ for app overview\nRight-click buttons for context help",
        fg='gray'
    ).pack(pady=10)
    
    root.mainloop()


if __name__ == "__main__":
    demo()
