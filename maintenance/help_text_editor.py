"""
help_text_editor.py — DocAnalyser Help Text Editor
====================================================

Standalone maintenance tool for editing help_texts.json without touching
raw JSON. Run directly from PyCharm or double-click to launch.

Usage:
    python maintenance/help_text_editor.py

Features:
    - Searchable list of all 143+ help entries
    - Form-based editing (title, description, tips)
    - Handles the special _app_overview entry
    - Atomic save (writes to temp file then renames)
    - Add / Delete entries
    - "Reload in app" button (calls context_help.reload_help_texts if main app is running)
    - Unsaved-change guard on entry switch and window close
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import json
import os
import sys
import shutil
import datetime

# ---------------------------------------------------------------------------
# Path setup — make sure we can find help_texts.json regardless of CWD
# ---------------------------------------------------------------------------
_THIS_FILE = os.path.abspath(__file__)
_MAINT_DIR = os.path.dirname(_THIS_FILE)
_PROJECT_DIR = os.path.dirname(_MAINT_DIR)
_JSON_PATH = os.path.join(_PROJECT_DIR, "help_texts.json")

# Add project dir to path so we can optionally import context_help
if _PROJECT_DIR not in sys.path:
    sys.path.insert(0, _PROJECT_DIR)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
WINDOW_TITLE = "DocAnalyser — Help Text Editor"
WINDOW_GEOMETRY = "1100x720"
APP_OVERVIEW_KEY    = "_app_overview"
ELEVATOR_PITCH_KEY  = "_elevator_pitch"
_SPECIAL_KEYS = (APP_OVERVIEW_KEY, ELEVATOR_PITCH_KEY)


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------

def load_json():
    """Load help_texts.json and return the raw dict."""
    if not os.path.exists(_JSON_PATH):
        messagebox.showerror(
            "File Not Found",
            f"Cannot find help_texts.json at:\n{_JSON_PATH}"
        )
        sys.exit(1)
    with open(_JSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data: dict):
    """Atomic write: write to .tmp then rename."""
    tmp_path = _JSON_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    shutil.move(tmp_path, _JSON_PATH)


def sorted_entry_keys(data: dict) -> list:
    """
    Return sorted list of editable keys (excludes _comment, _instructions
    but includes _app_overview and _elevator_pitch which have special forms).
    """
    skip = {"_comment", "_instructions"}
    keys = [k for k in data if k not in skip]
    # Put special keys first (in defined order), then alphabetical
    result = [k for k in _SPECIAL_KEYS if k in keys]
    remaining = [k for k in keys if k not in _SPECIAL_KEYS]
    result.extend(sorted(remaining))
    return result


# ---------------------------------------------------------------------------
# Main editor window
# ---------------------------------------------------------------------------

class HelpTextEditor:

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(WINDOW_TITLE)
        self.root.minsize(900, 600)

        # Centre on screen, inset at least 60px from each edge so the
        # title bar and resize handles are always reachable
        _W, _H = 1100, 720
        _sw = self.root.winfo_screenwidth()
        _sh = self.root.winfo_screenheight()
        _x  = max(60, (_sw - _W) // 2)
        _y  = max(40, (_sh - _H) // 2)
        self.root.geometry(f"{_W}x{_H}+{_x}+{_y}")

        # Data
        self._data: dict = {}          # full raw JSON dict
        self._keys: list = []          # ordered editable keys
        self._current_key: str = None  # key displayed in form
        self._dirty_form: bool = False # unsaved edits in current form
        self._dirty_file: bool = False # unsaved changes to JSON

        # Build UI
        self._build_ui()

        # Load data
        self._load()

        # Keyboard shortcut
        self.root.bind("<Control-s>", lambda e: self._save_file())
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        # ── Top toolbar ──────────────────────────────────────────────
        toolbar = ttk.Frame(self.root, padding=(8, 6, 8, 4))
        toolbar.pack(fill=tk.X, side=tk.TOP)

        ttk.Label(toolbar, text="DocAnalyser Help Text Editor",
                  font=("Arial", 13, "bold")).pack(side=tk.LEFT)

        # Right-side buttons
        btn_frame = ttk.Frame(toolbar)
        btn_frame.pack(side=tk.RIGHT)

        self._btn_save = ttk.Button(btn_frame, text="💾  Save All  (Ctrl+S)",
                                    command=self._save_file, width=20)
        self._btn_save.pack(side=tk.LEFT, padx=4)

        ttk.Button(btn_frame, text="🔄  Reload in App",
                   command=self._reload_in_app, width=17).pack(side=tk.LEFT, padx=4)

        ttk.Button(btn_frame, text="🗕  Minimise",
                   command=self.root.iconify, width=12).pack(side=tk.LEFT, padx=4)

        ttk.Separator(self.root, orient="horizontal").pack(fill=tk.X)

        # ── Main paned area ───────────────────────────────────────────
        pane = tk.PanedWindow(self.root, orient=tk.HORIZONTAL,
                              sashwidth=6, sashrelief=tk.FLAT)
        pane.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)

        # Left panel
        left = ttk.Frame(pane, padding=(6, 6, 0, 6))
        pane.add(left, minsize=280, width=320)

        # Right panel
        right = ttk.Frame(pane, padding=(6, 6, 6, 6))
        pane.add(right, minsize=500)

        self._build_left(left)
        self._build_right(right)

        # ── Status bar ───────────────────────────────────────────────
        status_bar = ttk.Frame(self.root, relief=tk.SUNKEN)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)
        self._status_var = tk.StringVar(value="Ready")
        ttk.Label(status_bar, textvariable=self._status_var,
                  anchor=tk.W, padding=(6, 2)).pack(fill=tk.X)

    def _build_left(self, parent):
        """Search box + list of keys."""
        # Search row
        search_row = ttk.Frame(parent)
        search_row.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(search_row, text="🔍").pack(side=tk.LEFT)
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", self._on_search_change)
        ttk.Entry(search_row, textvariable=self._search_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))
        ttk.Button(search_row, text="✕", width=3,
                   command=self._clear_search).pack(side=tk.LEFT, padx=(2, 0))

        # Entry count label
        self._count_var = tk.StringVar(value="")
        ttk.Label(parent, textvariable=self._count_var,
                  foreground="gray", font=("Arial", 8)).pack(anchor=tk.W)

        # Listbox with scrollbar
        lb_frame = ttk.Frame(parent)
        lb_frame.pack(fill=tk.BOTH, expand=True)

        vsb = ttk.Scrollbar(lb_frame, orient=tk.VERTICAL)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        self._listbox = tk.Listbox(
            lb_frame,
            yscrollcommand=vsb.set,
            selectmode=tk.SINGLE,
            activestyle="dotbox",
            font=("Consolas", 9),
            exportselection=False,
        )
        self._listbox.pack(fill=tk.BOTH, expand=True)
        vsb.config(command=self._listbox.yview)
        self._listbox.bind("<<ListboxSelect>>", self._on_list_select)
        self._listbox.bind("<Return>", self._on_list_select)

        # Add / Delete buttons
        btn_row = ttk.Frame(parent)
        btn_row.pack(fill=tk.X, pady=(4, 0))
        ttk.Button(btn_row, text="➕ Add New",
                   command=self._add_entry).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 2))
        ttk.Button(btn_row, text="🗑 Delete",
                   command=self._delete_entry).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(2, 0))

    def _build_right(self, parent):
        """Form: key, title, description, tips."""
        # Key row (read-only)
        key_row = ttk.Frame(parent)
        key_row.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(key_row, text="Key:", width=11, anchor=tk.W,
                  font=("Arial", 9, "bold")).pack(side=tk.LEFT)
        self._key_var = tk.StringVar()
        key_entry = ttk.Entry(key_row, textvariable=self._key_var,
                              state="readonly", font=("Consolas", 9))
        key_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Title row
        title_row = ttk.Frame(parent)
        title_row.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(title_row, text="Title:", width=11, anchor=tk.W,
                  font=("Arial", 9, "bold")).pack(side=tk.LEFT)
        self._title_var = tk.StringVar()
        self._title_var.trace_add("write", self._mark_dirty)
        ttk.Entry(title_row, textvariable=self._title_var,
                  font=("Arial", 9)).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Description label + char count
        desc_header = ttk.Frame(parent)
        desc_header.pack(fill=tk.X)
        ttk.Label(desc_header, text="Description:",
                  font=("Arial", 9, "bold")).pack(side=tk.LEFT)
        self._desc_chars_var = tk.StringVar(value="")
        ttk.Label(desc_header, textvariable=self._desc_chars_var,
                  foreground="gray", font=("Arial", 8)).pack(side=tk.RIGHT)

        # Description text area (large)
        self._desc_text = scrolledtext.ScrolledText(
            parent, height=14, font=("Arial", 9), wrap=tk.WORD, undo=True,
            bg="#fffde7", insertbackground="#333333")
        self._desc_text.pack(fill=tk.BOTH, expand=True, pady=(2, 6))
        self._desc_text.bind("<<Modified>>", self._on_desc_modified)

        # Tips label + hint
        tips_header = ttk.Frame(parent)
        tips_header.pack(fill=tk.X)
        ttk.Label(tips_header, text="Tips:",
                  font=("Arial", 9, "bold")).pack(side=tk.LEFT)
        ttk.Label(tips_header, text="(one tip per line — optional)",
                  foreground="gray", font=("Arial", 8)).pack(side=tk.LEFT, padx=6)
        self._tips_chars_var = tk.StringVar(value="")
        ttk.Label(tips_header, textvariable=self._tips_chars_var,
                  foreground="gray", font=("Arial", 8)).pack(side=tk.RIGHT)

        # Tips text area (smaller)
        self._tips_text = scrolledtext.ScrolledText(
            parent, height=5, font=("Arial", 9), wrap=tk.WORD, undo=True,
            bg="#fffde7", insertbackground="#333333")
        self._tips_text.pack(fill=tk.X, pady=(2, 0))
        self._tips_text.bind("<<Modified>>", self._on_tips_modified)

        # Apply / Discard row
        apply_row = ttk.Frame(parent)
        apply_row.pack(fill=tk.X, pady=(6, 0))
        self._btn_apply = ttk.Button(apply_row, text="✔  Apply Changes",
                                     command=self._apply_form, state=tk.DISABLED)
        self._btn_apply.pack(side=tk.LEFT, padx=(0, 6))
        self._btn_discard = ttk.Button(apply_row, text="✖  Discard",
                                       command=self._discard_form, state=tk.DISABLED)
        self._btn_discard.pack(side=tk.LEFT)
        ttk.Label(apply_row,
                  text="Apply saves to memory — use 💾 Save All to write to disk.",
                  foreground="gray", font=("Arial", 8)).pack(side=tk.LEFT, padx=12)

    # ------------------------------------------------------------------
    # Data loading / list population
    # ------------------------------------------------------------------

    def _load(self):
        """Load JSON, populate list."""
        self._data = load_json()
        self._keys = sorted_entry_keys(self._data)
        self._populate_list(self._keys)
        self._update_count()
        self._status("Loaded %d entries from %s" % (len(self._keys), _JSON_PATH))
        # Select first entry
        if self._listbox.size() > 0:
            self._listbox.selection_set(0)
            self._listbox.activate(0)
            self._load_form(self._keys[0])

    def _populate_list(self, keys: list):
        """Refill listbox with the given key list."""
        self._listbox.delete(0, tk.END)
        for k in keys:
            entry = self._data.get(k, {})
            # Show key + title preview
            if k == APP_OVERVIEW_KEY:
                title = entry.get("title", "")
                display = f"[APP OVERVIEW]  {title}"
            elif k == ELEVATOR_PITCH_KEY:
                title = entry.get("title", "")
                display = f"[ELEVATOR PITCH]  {title}"
            else:
                title = entry.get("title", "") if isinstance(entry, dict) else ""
                display = f"{k}  —  {title[:40]}"
            self._listbox.insert(tk.END, display)
        self._update_count(len(keys))

    def _update_count(self, shown: int = None):
        total = len([k for k in self._keys if k not in _SPECIAL_KEYS])
        if shown is None:
            shown = len(self._keys)
        if shown == len(self._keys):
            specials = sum(1 for k in _SPECIAL_KEYS if k in self._keys)
            special_label = "app overview + elevator pitch" if specials == 2 else "special entry"
            self._count_var.set(f"{total} regular entries  +  {special_label}")
        else:
            self._count_var.set(f"Showing {shown} of {len(self._keys)}")

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def _on_search_change(self, *_):
        term = self._search_var.get().strip().lower()
        if not term:
            filtered = self._keys
        else:
            filtered = []
            for k in self._keys:
                entry = self._data.get(k, {})
                title = entry.get("title", "").lower() if isinstance(entry, dict) else ""
                desc = entry.get("description", "").lower() if isinstance(entry, dict) else ""
                content = entry.get("content", "").lower() if isinstance(entry, dict) else ""
                if term in k.lower() or term in title or term in desc or term in content:
                    filtered.append(k)
        self._populate_list(filtered)
        self._update_count(len(filtered))

    def _clear_search(self):
        self._search_var.set("")
        self._listbox.focus_set()

    # ------------------------------------------------------------------
    # Form load / apply / discard
    # ------------------------------------------------------------------

    def _on_list_select(self, event=None):
        sel = self._listbox.curselection()
        if not sel:
            return
        # Map listbox index back to a key — need to recompute filtered list
        term = self._search_var.get().strip().lower()
        if not term:
            visible_keys = self._keys
        else:
            visible_keys = [
                k for k in self._keys
                if term in k.lower()
                or term in self._data.get(k, {}).get("title", "").lower()
                or term in self._data.get(k, {}).get("description", "").lower()
                or term in self._data.get(k, {}).get("content", "").lower()
            ]
        idx = sel[0]
        if idx >= len(visible_keys):
            return
        new_key = visible_keys[idx]

        if new_key == self._current_key:
            return

        # Guard unsaved form changes
        if self._dirty_form:
            ans = messagebox.askyesnocancel(
                "Unsaved Changes",
                f"You have unsaved changes to '{self._current_key}'.\n\nApply them before switching?",
                parent=self.root
            )
            if ans is None:   # Cancel — stay on current
                # Re-select previous item in listbox
                self._reselect_current()
                return
            if ans:           # Yes — apply
                self._apply_form()

        self._load_form(new_key)

    def _reselect_current(self):
        """Re-select the current key in the listbox after a cancelled switch."""
        if self._current_key is None:
            return
        term = self._search_var.get().strip().lower()
        visible_keys = [k for k in self._keys] if not term else [
            k for k in self._keys
            if term in k.lower()
            or term in self._data.get(k, {}).get("title", "").lower()
        ]
        try:
            idx = visible_keys.index(self._current_key)
            self._listbox.selection_clear(0, tk.END)
            self._listbox.selection_set(idx)
            self._listbox.see(idx)
        except ValueError:
            pass

    def _load_form(self, key: str):
        """Populate form fields from data[key]."""
        self._current_key = key
        entry = self._data.get(key, {})

        # Key field
        self._key_var.set(key)

        # Suppress dirty tracking while loading
        self._dirty_form = False
        self._btn_apply.config(state=tk.DISABLED)
        self._btn_discard.config(state=tk.DISABLED)

        # Title
        self._title_var.set(entry.get("title", "") if isinstance(entry, dict) else "")

        # Description / content
        self._desc_text.config(state=tk.NORMAL)
        self._desc_text.delete("1.0", tk.END)
        if isinstance(entry, dict):
            # Special keys (_app_overview, _elevator_pitch) use "content";
            # all regular entries use "description"
            use_content = key in _SPECIAL_KEYS
            text = entry.get("content" if use_content else "description", "")
            self._desc_text.insert("1.0", text or "")
        self._desc_text.edit_modified(False)

        # Tips — not applicable to special keys
        self._tips_text.config(state=tk.NORMAL)
        self._tips_text.delete("1.0", tk.END)
        if key not in _SPECIAL_KEYS and isinstance(entry, dict):
            tips = entry.get("tips", [])
            if tips:
                self._tips_text.insert("1.0", "\n".join(tips))
        self._tips_text.config(
            state=tk.NORMAL if key not in _SPECIAL_KEYS else tk.DISABLED
        )
        self._tips_text.edit_modified(False)

        self._update_char_counts()
        self._dirty_form = False

    def _apply_form(self):
        """Write form values back to _data[current_key]."""
        if self._current_key is None:
            return
        key = self._current_key
        entry = self._data.get(key, {})
        if not isinstance(entry, dict):
            entry = {}

        entry["title"] = self._title_var.get().strip()

        desc = self._desc_text.get("1.0", tk.END).rstrip("\n")
        if key in _SPECIAL_KEYS:
            entry["content"] = desc
        else:
            entry["description"] = desc

        if key not in _SPECIAL_KEYS:
            tips_raw = self._tips_text.get("1.0", tk.END).strip()
            tips = [t.strip() for t in tips_raw.splitlines() if t.strip()]
            if tips:
                entry["tips"] = tips
            elif "tips" in entry:
                del entry["tips"]

        self._data[key] = entry
        self._dirty_form = False
        self._dirty_file = True
        self._btn_apply.config(state=tk.DISABLED)
        self._btn_discard.config(state=tk.DISABLED)
        self._update_save_button()
        self._status(f"Applied changes to '{key}'  (not yet saved to disk)")

    def _discard_form(self):
        """Reload form from _data — discard edits."""
        if self._current_key:
            self._load_form(self._current_key)
        self._status("Discarded edits")

    # ------------------------------------------------------------------
    # Dirty tracking
    # ------------------------------------------------------------------

    def _mark_dirty(self, *_):
        if self._current_key is None:
            return
        self._dirty_form = True
        self._btn_apply.config(state=tk.NORMAL)
        self._btn_discard.config(state=tk.NORMAL)

    def _on_desc_modified(self, event=None):
        if self._desc_text.edit_modified():
            self._mark_dirty()
            self._update_char_counts()
            self._desc_text.edit_modified(False)

    def _on_tips_modified(self, event=None):
        if self._tips_text.edit_modified():
            self._mark_dirty()
            self._update_char_counts()
            self._tips_text.edit_modified(False)

    def _update_char_counts(self):
        desc = self._desc_text.get("1.0", tk.END).strip()
        self._desc_chars_var.set(f"{len(desc)} chars")
        tips = self._tips_text.get("1.0", tk.END).strip()
        lines = [t for t in tips.splitlines() if t.strip()]
        self._tips_chars_var.set(f"{len(lines)} tip(s)")

    def _update_save_button(self):
        if self._dirty_file:
            self._btn_save.config(text="💾  Save All *  (Ctrl+S)")
        else:
            self._btn_save.config(text="💾  Save All  (Ctrl+S)")

    # ------------------------------------------------------------------
    # Save / Reload in App
    # ------------------------------------------------------------------

    def _save_file(self):
        """Apply pending form changes, then save JSON."""
        # Apply current form if dirty
        if self._dirty_form:
            self._apply_form()

        try:
            save_json(self._data)
            self._dirty_file = False
            self._update_save_button()
            ts = datetime.datetime.now().strftime("%H:%M:%S")
            self._status(f"✅  Saved to {_JSON_PATH}  ({ts})")
        except Exception as e:
            messagebox.showerror("Save Failed", str(e), parent=self.root)

    def _reload_in_app(self):
        """Call context_help.reload_help_texts() if importable (main app must be running)."""
        try:
            import context_help
            context_help.reload_help_texts()
            self._status("✅  Reloaded help texts in running DocAnalyser instance")
        except ImportError:
            messagebox.showinfo(
                "Not Available",
                "Could not import context_help.\n\n"
                "This button works when DocAnalyser is already running in the same Python process.\n\n"
                "Restart DocAnalyser to see help text changes.",
                parent=self.root
            )
        except Exception as e:
            messagebox.showerror("Reload Failed", str(e), parent=self.root)

    # ------------------------------------------------------------------
    # Add / Delete entries
    # ------------------------------------------------------------------

    def _add_entry(self):
        """Prompt for a new key name and add a blank entry."""
        dialog = _InputDialog(self.root, title="Add New Entry",
                              prompt="Enter a new help key (e.g. my_new_button):",
                              initial="")
        new_key = dialog.result
        if not new_key:
            return
        new_key = new_key.strip()
        if not new_key:
            return
        if new_key in self._data:
            messagebox.showwarning("Duplicate Key",
                                   f"Key '{new_key}' already exists.", parent=self.root)
            return
        if new_key.startswith("_") and new_key not in _SPECIAL_KEYS:
            messagebox.showwarning("Reserved Key",
                                   "Keys starting with _ are reserved.", parent=self.root)
            return

        self._data[new_key] = {"title": "", "description": "", "tips": []}
        self._keys = sorted_entry_keys(self._data)
        self._dirty_file = True
        self._update_save_button()

        # Clear search so new key is visible
        self._search_var.set("")
        self._populate_list(self._keys)
        self._update_count()

        # Select the new key
        try:
            idx = self._keys.index(new_key)
            self._listbox.selection_clear(0, tk.END)
            self._listbox.selection_set(idx)
            self._listbox.see(idx)
            self._load_form(new_key)
            # Focus title field
            self.root.after(50, lambda: self._title_var.set(""))
        except ValueError:
            pass

        self._status(f"Added new entry '{new_key}'  (not yet saved to disk)")

    def _delete_entry(self):
        """Delete the currently selected entry after confirmation."""
        if self._current_key is None:
            return
        if self._current_key in _SPECIAL_KEYS:
            messagebox.showwarning("Cannot Delete",
                                   "This entry cannot be deleted.",
                                   parent=self.root)
            return

        ans = messagebox.askyesno(
            "Confirm Delete",
            f"Delete entry '{self._current_key}'?\n\nThis cannot be undone (until you save and restore from backup).",
            parent=self.root
        )
        if not ans:
            return

        deleted_key = self._current_key
        del self._data[deleted_key]
        self._keys = sorted_entry_keys(self._data)
        self._current_key = None
        self._dirty_form = False
        self._dirty_file = True
        self._update_save_button()

        self._populate_list(self._keys)
        self._update_count()

        # Select first item
        if self._listbox.size() > 0:
            self._listbox.selection_set(0)
            self._load_form(self._keys[0])
        else:
            self._key_var.set("")
            self._title_var.set("")
            self._desc_text.delete("1.0", tk.END)
            self._tips_text.delete("1.0", tk.END)

        self._status(f"Deleted '{deleted_key}'  (not yet saved to disk)")

    # ------------------------------------------------------------------
    # Status bar
    # ------------------------------------------------------------------

    def _status(self, msg: str):
        self._status_var.set(msg)

    # ------------------------------------------------------------------
    # Window close
    # ------------------------------------------------------------------

    def _on_close(self):
        if self._dirty_form:
            ans = messagebox.askyesnocancel(
                "Unsaved Form Changes",
                f"You have unsaved changes to '{self._current_key}'.\n\nApply them before closing?",
                parent=self.root
            )
            if ans is None:
                return
            if ans:
                self._apply_form()

        if self._dirty_file:
            ans = messagebox.askyesnocancel(
                "Unsaved File",
                "You have unsaved changes to help_texts.json.\n\nSave before closing?",
                parent=self.root
            )
            if ans is None:
                return
            if ans:
                self._save_file()

        self.root.destroy()


# ---------------------------------------------------------------------------
# Simple input dialog
# ---------------------------------------------------------------------------

class _InputDialog(tk.Toplevel):

    def __init__(self, parent, title: str, prompt: str, initial: str = ""):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.result = None

        ttk.Label(self, text=prompt, padding=(12, 12, 12, 4)).pack()
        self._var = tk.StringVar(value=initial)
        entry = ttk.Entry(self, textvariable=self._var, width=40)
        entry.pack(padx=12, pady=4)
        entry.focus_set()
        entry.select_range(0, tk.END)

        btn_row = ttk.Frame(self)
        btn_row.pack(pady=(4, 12))
        ttk.Button(btn_row, text="OK", command=self._ok, width=10).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_row, text="Cancel", command=self.destroy, width=10).pack(side=tk.LEFT, padx=4)

        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self.destroy())

        # Centre on parent
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")
        parent.wait_window(self)

    def _ok(self):
        self.result = self._var.get()
        self.destroy()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    root = tk.Tk()

    # App icon (suppress error if not found)
    icon_path = os.path.join(_PROJECT_DIR, "DocAnalyser.ico")
    if os.path.exists(icon_path):
        try:
            root.iconbitmap(icon_path)
        except Exception:
            pass

    app = HelpTextEditor(root)
    root.mainloop()


if __name__ == "__main__":
    main()
