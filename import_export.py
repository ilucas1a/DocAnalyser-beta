"""
import_export.py — Import/Export for DocAnalyser Libraries

Handles exporting and importing prompts (and later documents)
using the .docanalyser package format (a ZIP file containing
manifest.json plus the serialised data).

Format spec:
    myfile.docanalyser          (ZIP archive)
    ├── manifest.json           (metadata: version, type, created, source)
    └── prompts.json            (the actual prompt data with folder structure)

Author: DocAnalyser Development Team
Date: March 2026
"""

import json
import os
import datetime
import zipfile
import tempfile
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
from typing import List, Optional, Callable

# We import these at module level for type hints only;
# actual usage is via the objects passed in by callers.
from tree_manager_base import TreeNode, FolderNode, TreeManager

# Try to import PromptItem for isinstance checks
try:
    from prompt_tree_manager import PromptItem
except ImportError:
    PromptItem = None

# Context help (F1 popups)
try:
    from context_help import add_help, HELP_TEXTS
except ImportError:
    def add_help(*args, **kwargs): pass
    HELP_TEXTS = {}


# ============================================================================
# CONSTANTS
# ============================================================================

EXPORT_VERSION = "1.0"
FILE_EXTENSION = ".docanalyser"
FILE_FILTER = [("DocAnalyser Package", "*.docanalyser"), ("All files", "*.*")]


# ============================================================================
# EMAIL EXPORT HELPER
# ============================================================================

# Email provider URL templates
EMAIL_PROVIDERS = [
    "Gmail",
    "Outlook.com",
    "Yahoo Mail",
    "Other Email",
]


def _open_email_with_attachment(filepath: str, recipient: str,
                                content_type: str, item_count: int,
                                item_names: list = None,
                                email_provider: str = "Gmail",
                                parent: tk.Widget = None):
    """
    Open Explorer (left half of screen) with the exported file selected
    and an email compose window (right half) pre-filled with subject,
    body and recipient, so the user can drag-and-drop the attachment.

    Supports Gmail, Outlook.com, Yahoo Mail, and a generic mailto: fallback.
    """
    import subprocess
    import webbrowser
    import threading
    import time
    from urllib.parse import quote

    # ---- compose email text ----
    type_label = "prompt(s)" if content_type == "prompts" else "document(s)"
    type_singular = "Prompt" if content_type == "prompts" else "Document"
    library_name = "Prompts" if content_type == "prompts" else "Documents"
    filename = os.path.basename(filepath)

    subject = f"DocAnalyser Export \u2014 {item_count} {type_label}"

    # Build the item listing for the email body
    # Cap at 20 to avoid exceeding URL length limits
    MAX_LISTED = 20
    items_section = ""
    if item_names:
        items_section = f"\n{type_singular} titles included in this export:\n"
        for i, name in enumerate(item_names[:MAX_LISTED], 1):
            items_section += f"  {i}. {name}\n"
        if len(item_names) > MAX_LISTED:
            items_section += f"  ... and {len(item_names) - MAX_LISTED} more\n"
        items_section += "\n"

    body = (
        f"Hi,\n\n"
        f"I'm sharing a DocAnalyser export file with you.\n\n"
        f"The attached file '{filename}' contains {item_count} {type_label}.\n\n"
        f"To import this into DocAnalyser:\n"
        f"  1. Save the attached .docanalyser file to your computer\n"
        f"  2. Open DocAnalyser\n"
        f"  3. Open the {library_name} Library\n"
        f"  4. Click the Import button\n"
        f"  5. Select the saved .docanalyser file\n"
        f"  6. Choose which items to import and click Import\n\n"
        f"Note: If you don't have DocAnalyser yet, please ask the sender\n"
        f"for the installer or visit the DocAnalyser download page.\n"
        f"{items_section}"
        f"Best regards"
    )

    # ---- build the compose URL for the chosen provider ----
    if email_provider == "Outlook.com":
        compose_url = (
            f"https://outlook.live.com/mail/0/deeplink/compose"
            f"?to={quote(recipient)}"
            f"&subject={quote(subject)}"
            f"&body={quote(body)}"
        )
    elif email_provider == "Yahoo Mail":
        compose_url = (
            f"https://compose.mail.yahoo.com/"
            f"?to={quote(recipient)}"
            f"&subject={quote(subject)}"
            f"&body={quote(body)}"
        )
    elif email_provider == "Other Email":
        # mailto: link — opens the system default email client
        compose_url = (
            f"mailto:{quote(recipient)}"
            f"?subject={quote(subject)}"
            f"&body={quote(body)}"
        )
    else:  # Gmail (default)
        compose_url = (
            f"https://mail.google.com/mail/?view=cm&fs=1"
            f"&to={quote(recipient)}"
            f"&su={quote(subject)}"
            f"&body={quote(body)}"
        )

    norm = os.path.normpath(filepath)

    # ---- open & position windows in a background thread ----
    def _open_and_position():
        """Open Explorer (left) and email compose (right), snapped to screen halves."""
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32

            # Get the usable work area (screen minus taskbar)
            SPI_GETWORKAREA = 48
            work = wintypes.RECT()
            user32.SystemParametersInfoW(SPI_GETWORKAREA, 0,
                                         ctypes.byref(work), 0)
            x0 = work.left
            y0 = work.top
            half_w = (work.right - work.left) // 2
            full_h = work.bottom - work.top

            # --- 1. Explorer on the LEFT half ---
            subprocess.Popen(['explorer', '/select,', norm])
            time.sleep(1.5)  # let Explorer draw
            hwnd_explorer = user32.GetForegroundWindow()
            if hwnd_explorer:
                user32.MoveWindow(hwnd_explorer,
                                  x0, y0, half_w, full_h, True)

            # --- 2. Email compose on the RIGHT half ---
            webbrowser.open(compose_url)
            time.sleep(2.0)  # let browser/client draw
            hwnd_browser = user32.GetForegroundWindow()
            if hwnd_browser and hwnd_browser != hwnd_explorer:
                user32.MoveWindow(hwnd_browser,
                                  x0 + half_w, y0, half_w, full_h, True)

        except Exception as e:
            print(f"\u26a0\ufe0f Window positioning failed (non-critical): {e}")
            # Fall back to unpositioned open if ctypes fails
            try:
                subprocess.Popen(['explorer', '/select,', norm])
            except Exception:
                pass
            webbrowser.open(compose_url)

    threading.Thread(target=_open_and_position, daemon=True).start()

    # ---- show brief instruction (appears on top while windows arrange) ----
    provider_label = email_provider if email_provider != "Other Email" else "your email app"
    messagebox.showinfo(
        "Email Ready",
        f"A {provider_label} compose window and a File Explorer window\n"
        f"are opening side by side.\n\n"
        f"To complete sending:\n"
        f"  1. Explorer (left) shows the exported file\n"
        f"     '{filename}'\n"
        f"  2. Drag the file from Explorer into the\n"
        f"     compose window (right) to attach it\n"
        f"  3. Click Send",
        parent=parent,
    )


# ============================================================================
# CORE: PACKAGING (ZIP) HELPERS
# ============================================================================

def _build_manifest(content_type: str, item_count: int, source_desc: str = "",
                    includes_folders: bool = False) -> dict:
    """Build the manifest.json content for a .docanalyser package."""
    return {
        "format_version": EXPORT_VERSION,
        "content_type": content_type,       # "prompts" or "documents"
        "created_at": datetime.datetime.now().isoformat(),
        "source_application": "DocAnalyser",
        "source_description": source_desc,
        "item_count": item_count,
        "includes_folders": includes_folders,
    }


def _write_package(filepath: str, manifest: dict, data: dict) -> bool:
    """
    Write a .docanalyser package (ZIP) to disk.

    Args:
        filepath: Full path for the output file.
        manifest: The manifest dict.
        data: The payload dict.

    Returns:
        True on success, False on error.
    """
    try:
        # Determine payload filename from content_type
        content_type = manifest.get("content_type", "prompts")
        payload_name = "documents.json" if content_type == "documents" else "prompts.json"

        # Write to a temp file first, then rename — atomic-ish on Windows
        tmp_path = filepath + ".tmp"
        with zipfile.ZipFile(tmp_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json",
                        json.dumps(manifest, indent=2, ensure_ascii=False))
            zf.writestr(payload_name,
                        json.dumps(data, indent=2, ensure_ascii=False))
        # Replace target
        if os.path.exists(filepath):
            os.remove(filepath)
        os.rename(tmp_path, filepath)
        return True
    except Exception as e:
        print(f"ERROR _write_package: {e}")
        # Clean up temp file if it exists
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except:
                pass
        return False


def _read_package(filepath: str) -> tuple:
    """
    Read a .docanalyser package.

    Returns:
        (manifest: dict, data: dict) or (None, None) on error.
    """
    try:
        with zipfile.ZipFile(filepath, 'r') as zf:
            manifest = json.loads(zf.read("manifest.json").decode('utf-8'))

            # Determine payload filename from content_type
            if manifest.get("content_type") == "documents":
                payload_name = "documents.json"
            else:
                payload_name = "prompts.json"

            data = json.loads(zf.read(payload_name).decode('utf-8'))
        return manifest, data
    except Exception as e:
        print(f"ERROR _read_package: {e}")
        return None, None


# ============================================================================
# SERIALISATION: PROMPTS → FLAT LIST / FOLDER TREE
# ============================================================================

def _serialise_prompt(prompt_item) -> dict:
    """Serialise a single PromptItem to an export-friendly dict."""
    return prompt_item.to_dict()


def _serialise_folder(folder: FolderNode, include_subfolders: bool = True) -> dict:
    """
    Serialise a folder (and optionally its subfolders) for export.

    Returns a dict with folder name, children (prompts), and
    sub_folders (nested folder dicts).
    """
    prompts = []
    sub_folders = []

    for child in folder.children.values():
        if isinstance(child, FolderNode):
            if include_subfolders:
                sub_folders.append(_serialise_folder(child, include_subfolders=True))
        else:
            # It's a prompt (or other TreeNode)
            prompts.append(_serialise_prompt(child))

    return {
        "folder_name": folder.name,
        "prompts": prompts,
        "sub_folders": sub_folders,
    }


def _count_prompts_in_folder(folder: FolderNode) -> int:
    """Recursively count all prompts in a folder and its subfolders."""
    count = 0
    for child in folder.children.values():
        if isinstance(child, FolderNode):
            count += _count_prompts_in_folder(child)
        else:
            count += 1
    return count


def _collect_all_prompts_flat(folder: FolderNode) -> list:
    """Recursively collect all prompt dicts from a folder tree."""
    result = []
    for child in folder.children.values():
        if isinstance(child, FolderNode):
            result.extend(_collect_all_prompts_flat(child))
        else:
            result.append(_serialise_prompt(child))
    return result


# ============================================================================
# EXPORT: PUBLIC API
# ============================================================================

def export_selected_prompts(parent: tk.Widget, prompt_items: list,
                            source_desc: str = ""):
    """
    Export one or more selected PromptItems to a .docanalyser file.

    If a single prompt is selected, the filename defaults to the prompt name.
    If multiple, a generic name is used.

    Called from: PromptTreeManagerUI._export_selected()
    """
    if not prompt_items:
        messagebox.showinfo("Nothing to Export", "No prompts selected.",
                            parent=parent)
        return

    # Build default filename
    if len(prompt_items) == 1:
        default_name = _safe_filename(prompt_items[0].name)
    else:
        default_name = f"prompts_{len(prompt_items)}_items"

    filepath = filedialog.asksaveasfilename(
        parent=parent,
        title="Export Prompts",
        defaultextension=FILE_EXTENSION,
        filetypes=FILE_FILTER,
        initialfile=default_name + FILE_EXTENSION,
    )

    if not filepath:
        return  # User cancelled

    # Serialise
    prompts_data = [_serialise_prompt(p) for p in prompt_items]

    payload = {
        "export_type": "selected_prompts",
        "prompts": prompts_data,
        "folders": [],       # No folder structure for ad-hoc selection
    }

    manifest = _build_manifest(
        content_type="prompts",
        item_count=len(prompts_data),
        source_desc=source_desc,
        includes_folders=False,
    )

    if _write_package(filepath, manifest, payload):
        messagebox.showinfo(
            "Export Complete",
            f"Exported {len(prompts_data)} prompt(s) to:\n\n{filepath}",
            parent=parent,
        )
    else:
        messagebox.showerror(
            "Export Failed",
            "An error occurred while writing the file.\nCheck the console for details.",
            parent=parent,
        )


def export_folder(parent: tk.Widget, folder_node: FolderNode):
    """
    Export an entire folder (including all subfolders and prompts)
    to a .docanalyser file.

    Called from: PromptTreeManagerUI._export_folder()
    """
    prompt_count = _count_prompts_in_folder(folder_node)

    if prompt_count == 0:
        messagebox.showinfo("Nothing to Export",
                            f"Folder '{folder_node.name}' contains no prompts.",
                            parent=parent)
        return

    default_name = _safe_filename(folder_node.name)

    filepath = filedialog.asksaveasfilename(
        parent=parent,
        title=f"Export Folder: {folder_node.name}",
        defaultextension=FILE_EXTENSION,
        filetypes=FILE_FILTER,
        initialfile=default_name + FILE_EXTENSION,
    )

    if not filepath:
        return

    # Serialise folder with full hierarchy
    folder_data = _serialise_folder(folder_node, include_subfolders=True)

    payload = {
        "export_type": "folder",
        "prompts": [],                  # All prompts are inside folders
        "folders": [folder_data],       # Root folder with nested children
    }

    manifest = _build_manifest(
        content_type="prompts",
        item_count=prompt_count,
        source_desc=f"Folder: {folder_node.name}",
        includes_folders=True,
    )

    if _write_package(filepath, manifest, payload):
        messagebox.showinfo(
            "Export Complete",
            f"Exported folder '{folder_node.name}'\n"
            f"({prompt_count} prompt(s)) to:\n\n{filepath}",
            parent=parent,
        )
    else:
        messagebox.showerror(
            "Export Failed",
            "An error occurred while writing the file.\nCheck the console for details.",
            parent=parent,
        )


# ============================================================================
# EXPORT DIALOG (multi-select)
# ============================================================================

def export_prompts_dialog(parent: tk.Widget, tree_manager: TreeManager,
                          ui_instance):
    """
    Open a dialog that lets the user tick which prompts/folders to export,
    then saves a .docanalyser package.

    Called from: PromptTreeManagerUI._export_selected()
    """
    # Check there is something to export
    total = 0
    for folder in tree_manager.root_folders.values():
        total += _count_prompts_in_folder(folder)
    if total == 0:
        messagebox.showinfo("Nothing to Export",
                            "The Prompts Library is empty.",
                            parent=parent)
        return

    _ExportDialog(
        parent=parent,
        tree_manager=tree_manager,
        ui_instance=ui_instance,
    )


class _ExportDialog:
    """
    Modal dialog that shows all prompts/folders in the library
    with checkboxes, lets the user choose what to export.
    """

    def __init__(self, parent, tree_manager, ui_instance):
        self.parent = parent
        self.tree_manager = tree_manager
        self.ui_instance = ui_instance

        self.export_items = []      # list of dicts with checkbox vars
        self.folder_items = []      # folder-level checkboxes

        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Export Prompts")
        self.dialog.transient(parent)
        self.dialog.grab_set()

        self._build_ui()

    # -------------------- UI --------------------

    def _build_ui(self):
        screen_w = self.dialog.winfo_screenwidth()
        dlg_w = min(screen_w // 2, 700)
        dlg_h = 420
        self.dialog.geometry(f"{dlg_w}x{dlg_h}+0+0")
        self.dialog.minsize(500, 380)

        # ---- Header ----
        header = ttk.Frame(self.dialog, padding=(8, 4, 8, 2))
        header.pack(fill=tk.X)

        ttk.Label(header, text="Export Prompts",
                  font=('Arial', 12, 'bold')).pack(anchor=tk.W)
        ttk.Label(header, text="Tick the prompts and/or folders you want to export.",
                  foreground='gray', font=('Arial', 8)).pack(anchor=tk.W)

        # ==== BOTTOM: buttons (pack first to guarantee visibility) ====
        bottom_frame = ttk.Frame(self.dialog)
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=(2, 4))

        # Include folder structure option
        self.include_folders_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(bottom_frame,
                        text="Include folder structure",
                        variable=self.include_folders_var).pack(anchor=tk.W, pady=(0, 2))

        # ---- Email option ----
        email_frame = ttk.Frame(bottom_frame)
        email_frame.pack(fill=tk.X, pady=(0, 4))

        self.email_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(email_frame, text="Also email to:",
                        variable=self.email_var,
                        command=self._toggle_email).pack(side=tk.LEFT)

        self.email_entry = ttk.Entry(email_frame, width=28)
        self.email_entry.pack(side=tk.LEFT, padx=(4, 0))
        self.email_entry.insert(0, "recipient@example.com")
        self.email_entry.config(state=tk.DISABLED)

        ttk.Label(email_frame, text=" via").pack(side=tk.LEFT, padx=(4, 0))
        self.email_provider_var = tk.StringVar(value="Gmail")
        self.email_provider_combo = ttk.Combobox(
            email_frame, textvariable=self.email_provider_var,
            values=EMAIL_PROVIDERS, state=tk.DISABLED, width=12)
        self.email_provider_combo.pack(side=tk.LEFT, padx=(2, 0))

        btn_frame = ttk.Frame(bottom_frame)
        btn_frame.pack(fill=tk.X)
        self.export_btn = ttk.Button(btn_frame, text="Export (0)",
                                     command=self._do_export)
        self.export_btn.pack(side=tk.RIGHT, padx=4)
        ttk.Button(btn_frame, text="Cancel",
                   command=self.dialog.destroy).pack(side=tk.RIGHT, padx=4)

        # ==== VERTICAL PANE: selection list + preview ====
        vpane = ttk.PanedWindow(self.dialog, orient=tk.VERTICAL)
        vpane.pack(fill=tk.BOTH, expand=True, padx=6, pady=(2, 2))

        # ---- Top: scrollable checkbox list ----
        self.list_frame = ttk.LabelFrame(
            vpane,
            text="Select prompt(s) to export (right-click to preview prompt text)",
            padding=(4, 2, 4, 2))
        vpane.add(self.list_frame, weight=3)

        sys_bg = ttk.Style().lookup('TFrame', 'background') or 'SystemButtonFace'
        items_canvas = tk.Canvas(self.list_frame, highlightthickness=0,
                                 borderwidth=0, bg=sys_bg)
        items_sb = ttk.Scrollbar(self.list_frame, orient=tk.VERTICAL,
                                  command=items_canvas.yview)
        self.items_frame = tk.Frame(items_canvas, bg=sys_bg)

        self.items_frame.bind(
            "<Configure>",
            lambda e: items_canvas.configure(scrollregion=items_canvas.bbox("all"))
        )
        self._items_window_id = items_canvas.create_window(
            (0, 0), window=self.items_frame, anchor=tk.NW)
        items_canvas.configure(yscrollcommand=items_sb.set)

        def _resize_items_canvas(event):
            items_canvas.itemconfig(self._items_window_id, width=event.width)
            frame_h = self.items_frame.winfo_reqheight()
            if event.height > frame_h:
                items_canvas.itemconfig(self._items_window_id, height=event.height)
            else:
                items_canvas.itemconfig(self._items_window_id, height=frame_h)
        items_canvas.bind('<Configure>', _resize_items_canvas)

        def _on_items_mousewheel(event):
            items_canvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')
        items_canvas.bind('<MouseWheel>', _on_items_mousewheel)
        self.items_frame.bind('<MouseWheel>', _on_items_mousewheel)

        items_sb.pack(side=tk.RIGHT, fill=tk.Y)
        items_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Populate items
        self._populate_items()

        # Select All / None buttons
        sel_frame = ttk.Frame(self.list_frame)
        sel_frame.pack(fill=tk.X, pady=0)
        ttk.Button(sel_frame, text="Select All",
                   command=self._select_all, width=11).pack(side=tk.LEFT, padx=1)
        ttk.Button(sel_frame, text="Select None",
                   command=self._select_none, width=11).pack(side=tk.LEFT, padx=1)

        # ---- Bottom pane: prompt preview ----
        self.preview_frame = ttk.LabelFrame(vpane, text="Prompt preview", padding=4)
        vpane.add(self.preview_frame, weight=1)
        self.dialog.after(200, lambda: vpane.sashpos(0, 150))

        # Font size controls
        font_row = ttk.Frame(self.preview_frame)
        font_row.pack(fill=tk.X, pady=(0, 2))
        ttk.Label(font_row, text="Aa", font=('Arial', 9)).pack(side=tk.LEFT)
        ttk.Button(font_row, text="\u2212", width=2,
                   command=lambda: self._adjust_preview_font(-1)).pack(side=tk.LEFT, padx=1)
        ttk.Button(font_row, text="+", width=2,
                   command=lambda: self._adjust_preview_font(1)).pack(side=tk.LEFT, padx=1)

        self._font_size = 10
        try:
            self._font_size = self.ui_instance.config.get('font_size', 10)
        except Exception:
            pass
        self.preview_text = scrolledtext.ScrolledText(
            self.preview_frame, wrap=tk.WORD,
            font=('Arial', self._font_size),
            bg='#FFFDE6',
            fg='#999999',
            state=tk.DISABLED,
            relief=tk.SUNKEN,
            borderwidth=1)
        self.preview_text.pack(fill=tk.BOTH, expand=True)

        self.preview_text.config(state=tk.NORMAL)
        self.preview_text.insert('1.0',
            'Right-click or Ctrl+P on a prompt above to preview its full text here.')
        self.preview_text.config(state=tk.DISABLED)

        # Keyboard shortcuts
        self.dialog.bind('<Control-p>', self._preview_selected_prompt)
        self.dialog.bind('<Control-P>', self._preview_selected_prompt)
        self.dialog.bind('<Control-equal>', lambda e: self._adjust_preview_font(1))
        self.dialog.bind('<Control-plus>', lambda e: self._adjust_preview_font(1))
        self.dialog.bind('<Control-KP_Add>', lambda e: self._adjust_preview_font(1))
        self.dialog.bind('<Control-minus>', lambda e: self._adjust_preview_font(-1))
        self.dialog.bind('<Control-KP_Subtract>', lambda e: self._adjust_preview_font(-1))
        self.preview_text.bind('<Control-MouseWheel>', self._on_ctrl_mousewheel)

        self._update_export_count()

    # -------------------- Populate items --------------------

    def _populate_items(self):
        """Build the checkbox list from the live tree_manager data."""
        row = 0
        for folder_name in sorted(self.tree_manager.root_folders.keys()):
            folder = self.tree_manager.root_folders[folder_name]
            row = self._populate_folder(folder, row, indent=0)

    def _populate_folder(self, folder: FolderNode, row: int,
                          indent: int = 0) -> int:
        """Recursively populate a folder and its children. Returns next row."""
        total = _count_prompts_in_folder(folder)
        folder_var = tk.BooleanVar(value=True)
        pad_left = 5 + (indent * 20)

        cb = ttk.Checkbutton(
            self.items_frame,
            text=f"[+] {folder.name}  ({total} prompt(s))",
            variable=folder_var,
        )
        cb.grid(row=row, column=0, columnspan=2, sticky=tk.W,
                padx=pad_left, pady=(4, 1))

        child_vars = []
        row += 1

        # Prompts in this folder
        for child_name in sorted(folder.children.keys()):
            child = folder.children[child_name]
            if isinstance(child, FolderNode):
                continue  # Handle subfolders after prompts
            # It's a prompt
            var = tk.BooleanVar(value=True)
            child_vars.append(var)
            prompt_item = child  # The actual PromptItem object

            prompt_cb = ttk.Checkbutton(
                self.items_frame,
                text=f"    [P] {child.name}",
                variable=var,
                command=self._update_export_count,
            )
            prompt_cb.grid(row=row, column=0, sticky=tk.W,
                           padx=pad_left + 20, pady=1)
            prompt_cb.bind('<Button-3>',
                          lambda e, pi=prompt_item: self._on_item_right_click(e, pi))

            # Brief info text
            versions = child.to_dict().get("versions", [])
            ver_count = len(versions)
            text_preview = ""
            if versions:
                txt = versions[-1].get("text", "")
                text_preview = txt[:50].replace('\n', ' ') + ("..." if len(txt) > 50 else "")
            info_lbl = ttk.Label(self.items_frame,
                                text=f"{text_preview}",
                                foreground='gray', font=('Arial', 8))
            info_lbl.grid(row=row, column=1, sticky=tk.W, padx=5)
            info_lbl.bind('<Button-3>',
                         lambda e, pi=prompt_item: self._on_item_right_click(e, pi))

            self.export_items.append({
                "var": var,
                "prompt_item": prompt_item,
                "type": "prompt",
                "folder": folder,
            })
            row += 1

        # Subfolders
        for child_name in sorted(folder.children.keys()):
            child = folder.children[child_name]
            if isinstance(child, FolderNode):
                row = self._populate_folder(child, row, indent=indent + 1)

        # Folder toggle: tick/untick all children in this folder
        def _toggle_folder(fv=folder_var, cvs=child_vars):
            val = fv.get()
            for cv in cvs:
                cv.set(val)
            self._update_export_count()
        folder_var.trace_add('write', lambda *_, f=_toggle_folder: f())

        self.folder_items.append({
            "var": folder_var,
            "folder": folder,
            "child_vars": child_vars,
        })

        return row

    # -------------------- Selection helpers --------------------

    def _select_all(self):
        for item in self.export_items:
            item["var"].set(True)
        for fi in self.folder_items:
            fi["var"].set(True)
        self._update_export_count()

    def _select_none(self):
        for item in self.export_items:
            item["var"].set(False)
        for fi in self.folder_items:
            fi["var"].set(False)
        self._update_export_count()

    def _update_export_count(self):
        count = sum(1 for item in self.export_items if item["var"].get())
        self.export_btn.config(text=f"Export ({count})")

    # -------------------- Preview --------------------

    def _preview_selected_prompt(self, event=None):
        """Show full text of the most recently ticked prompt."""
        for item in reversed(self.export_items):
            if item["var"].get():
                self._show_preview_from_item(item["prompt_item"])
                return
        self._show_preview_text(None, None)

    def _on_item_right_click(self, event, prompt_item):
        """Handle right-click on a prompt — show preview."""
        self._show_preview_from_item(prompt_item)

    def _show_preview_from_item(self, prompt_item):
        """Display a live PromptItem's text in the preview pane."""
        data = prompt_item.to_dict()
        name = data.get("name", "Unnamed")
        versions = data.get("versions", [])
        idx = data.get("current_version_index", len(versions) - 1)
        if versions and 0 <= idx < len(versions):
            text = versions[idx].get("text", "(no text)")
        elif versions:
            text = versions[-1].get("text", "(no text)")
        else:
            text = "(no text)"
        version_count = len(versions)
        self._show_preview_text(name, text, version_count)

    def _show_preview_text(self, name, text, version_count=0):
        self.preview_text.config(state=tk.NORMAL)
        self.preview_text.delete('1.0', tk.END)
        if name is None:
            self.preview_text.insert('1.0', 'No prompt selected.')
            self.preview_text.config(state=tk.DISABLED, fg='#999999')
            return
        self.preview_text.insert('1.0',
            f"--- {name} ---  ({version_count} version(s))\n\n{text}")
        self.preview_text.config(state=tk.DISABLED, fg='#333333')

    def _adjust_preview_font(self, delta):
        new_size = max(8, min(16, self._font_size + delta))
        if new_size == self._font_size:
            return
        self._font_size = new_size
        self.preview_text.config(font=('Arial', self._font_size))
        try:
            self.ui_instance.config['font_size'] = self._font_size
        except Exception:
            pass

    def _on_ctrl_mousewheel(self, event):
        if event.delta > 0:
            self._adjust_preview_font(1)
        else:
            self._adjust_preview_font(-1)
        return 'break'

    # -------------------- Email toggle --------------------

    def _toggle_email(self):
        """Enable/disable the email entry and provider combo based on checkbox."""
        if self.email_var.get():
            self.email_entry.config(state=tk.NORMAL)
            self.email_provider_combo.config(state='readonly')
            self.email_entry.select_range(0, tk.END)
            self.email_entry.focus_set()
        else:
            self.email_entry.config(state=tk.DISABLED)
            self.email_provider_combo.config(state=tk.DISABLED)

    # -------------------- Export execution --------------------

    def _do_export(self):
        """Collect ticked items and write the .docanalyser package."""
        selected = [item for item in self.export_items if item["var"].get()]

        if not selected:
            messagebox.showinfo("Nothing Selected",
                                "Please tick at least one prompt to export.",
                                parent=self.dialog)
            return

        include_folders = self.include_folders_var.get()

        # Build default filename
        if len(selected) == 1:
            default_name = _safe_filename(selected[0]["prompt_item"].name)
        else:
            default_name = f"prompts_{len(selected)}_items"

        filepath = filedialog.asksaveasfilename(
            parent=self.dialog,
            title="Export Prompts",
            defaultextension=FILE_EXTENSION,
            filetypes=FILE_FILTER,
            initialfile=default_name + FILE_EXTENSION,
        )

        if not filepath:
            return  # User cancelled

        if include_folders:
            # Group selected prompts by folder, preserving hierarchy
            payload = self._build_folder_payload(selected)
        else:
            # Flat export — just the prompts, no folder structure
            prompts_data = [_serialise_prompt(item["prompt_item"]) for item in selected]
            payload = {
                "export_type": "selected_prompts",
                "prompts": prompts_data,
                "folders": [],
            }

        manifest = _build_manifest(
            content_type="prompts",
            item_count=len(selected),
            source_desc=f"Export: {len(selected)} prompt(s)",
            includes_folders=include_folders,
        )

        if _write_package(filepath, manifest, payload):
            # Check if user also wants to email
            want_email = self.email_var.get()
            recipient = self.email_entry.get().strip() if want_email else ""

            if want_email and not recipient:
                messagebox.showwarning("Email Address Required",
                                       "Please enter a recipient email address.",
                                       parent=self.dialog)
                return  # Don't close — file is saved, let user fix email

            messagebox.showinfo(
                "Export Complete",
                f"Exported {len(selected)} prompt(s) to:\n\n{filepath}",
                parent=self.dialog,
            )

            if want_email and recipient:
                provider = self.email_provider_var.get()
                if provider == "Other Email":
                    messagebox.showinfo(
                        "Heads Up",
                        "'Other Email' uses your computer's default email\n"
                        "program. Sometimes line breaks in the message\n"
                        "can look odd (e.g. everything on one line).\n\n"
                        "Please check the message looks OK before sending.",
                        parent=self.dialog,
                    )
                names = [item["prompt_item"].name for item in selected]
                _open_email_with_attachment(
                    filepath=filepath,
                    recipient=recipient,
                    content_type="prompts",
                    item_count=len(selected),
                    item_names=names,
                    email_provider=provider,
                    parent=self.dialog,
                )

            self.dialog.destroy()
        else:
            messagebox.showerror(
                "Export Failed",
                "An error occurred while writing the file.\n"
                "Check the console for details.",
                parent=self.dialog,
            )

    def _build_folder_payload(self, selected_items: list) -> dict:
        """
        Build a payload that preserves folder structure for selected prompts.
        Only includes folders that contain at least one selected prompt.
        """
        # Map: folder object -> list of selected prompt items in that folder
        folder_prompts = {}
        for item in selected_items:
            folder = item["folder"]
            if folder not in folder_prompts:
                folder_prompts[folder] = []
            folder_prompts[folder].append(item["prompt_item"])

        # Build folder dicts — only for folders with selected prompts
        # Group by root folder to preserve hierarchy
        root_folder_data = {}
        for folder, prompt_items in folder_prompts.items():
            # Walk up to find root folder
            root = folder
            path = [folder]
            while hasattr(root, 'parent_folder') and root.parent_folder is not None:
                root = root.parent_folder
                path.insert(0, root)

            root_name = root.name
            if root_name not in root_folder_data:
                root_folder_data[root_name] = {"root": root, "prompts_by_folder": {}}
            root_folder_data[root_name]["prompts_by_folder"][folder] = prompt_items

        # Serialise each root folder, including only selected prompts
        folders_out = []
        for root_info in root_folder_data.values():
            root = root_info["root"]
            prompts_by_folder = root_info["prompts_by_folder"]
            folder_dict = self._serialise_folder_selective(root, prompts_by_folder)
            if folder_dict is not None:
                folders_out.append(folder_dict)

        return {
            "export_type": "folder",
            "prompts": [],
            "folders": folders_out,
        }

    def _serialise_folder_selective(self, folder: FolderNode,
                                     prompts_by_folder: dict) -> Optional[dict]:
        """
        Serialise a folder, but only include prompts that are in
        prompts_by_folder. Returns None if the folder has nothing selected.
        """
        prompts = []
        if folder in prompts_by_folder:
            prompts = [_serialise_prompt(p) for p in prompts_by_folder[folder]]

        sub_folders = []
        for child in folder.children.values():
            if isinstance(child, FolderNode):
                sub = self._serialise_folder_selective(child, prompts_by_folder)
                if sub is not None:
                    sub_folders.append(sub)

        if not prompts and not sub_folders:
            return None  # Nothing selected in this branch

        return {
            "folder_name": folder.name,
            "prompts": prompts,
            "sub_folders": sub_folders,
        }


# ============================================================================
# IMPORT: PUBLIC API
# ============================================================================

def import_prompts(parent: tk.Widget, tree_manager: TreeManager,
                   ui_instance, prompts_path: str,
                   refresh_callback: Callable = None):
    """
    Open a .docanalyser file, preview its contents, let the user choose
    which prompts/folders to import and where to put them, then import.

    Called from: PromptTreeManagerUI._import_prompts()
    """
    filepath = filedialog.askopenfilename(
        parent=parent,
        title="Import Prompts",
        filetypes=FILE_FILTER,
    )

    if not filepath:
        return  # User cancelled

    # Read package
    manifest, data = _read_package(filepath)
    if manifest is None or data is None:
        messagebox.showerror(
            "Import Failed",
            "Could not read the file. It may be corrupted or not a valid "
            ".docanalyser package.",
            parent=parent,
        )
        return

    # Validate content type
    if manifest.get("content_type") != "prompts":
        messagebox.showerror(
            "Wrong Content Type",
            f"This file contains '{manifest.get('content_type')}' data, "
            f"not prompts.\n\nPlease use the Documents Library to import "
            f"document packages.",
            parent=parent,
        )
        return

    # Open the import preview dialog
    _ImportDialog(
        parent=parent,
        filepath=filepath,
        manifest=manifest,
        data=data,
        tree_manager=tree_manager,
        ui_instance=ui_instance,
        prompts_path=prompts_path,
        refresh_callback=refresh_callback,
    )


# ============================================================================
# IMPORT DIALOG
# ============================================================================

class _ImportDialog:
    """
    Modal dialog that shows the contents of a .docanalyser prompt package
    and lets the user choose what to import and where.
    """

    def __init__(self, parent, filepath, manifest, data,
                 tree_manager, ui_instance, prompts_path, refresh_callback):
        self.parent = parent
        self.filepath = filepath
        self.manifest = manifest
        self.data = data
        self.tree_manager = tree_manager
        self.ui_instance = ui_instance
        self.prompts_path = prompts_path
        self.refresh_callback = refresh_callback

        # Collect all importable items (prompts and folders)
        self.import_items = []      # list of dicts with checkbox vars
        self.folder_items = []      # folder-level checkboxes

        # Build the dialog
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Import Prompts")
        self.dialog.geometry("650x580")
        self.dialog.transient(parent)
        self.dialog.grab_set()

        self._build_ui()

    # -------------------- UI --------------------

    def _build_ui(self):
        # Match main UI height (420), half screen width, top-left corner
        screen_w = self.dialog.winfo_screenwidth()
        dlg_w = min(screen_w // 2, 700)
        dlg_h = 420
        self.dialog.geometry(f"{dlg_w}x{dlg_h}+0+0")
        self.dialog.minsize(500, 380)

        # ---- Header (compact) ----
        header = ttk.Frame(self.dialog, padding=(8, 4, 8, 2))
        header.pack(fill=tk.X)

        ttk.Label(header, text="Import Prompts",
                  font=('Arial', 12, 'bold')).pack(anchor=tk.W)

        file_label = os.path.basename(self.filepath)
        created = self.manifest.get("created_at", "unknown")[:16]
        count = self.manifest.get("item_count", "?")
        has_folders = self.manifest.get("includes_folders", False)

        info_text = f"File: {file_label}  |  Created: {created}  |  {count} prompt(s)"
        if has_folders:
            info_text += "  |  Includes folder structure"
        ttk.Label(header, text=info_text, foreground='gray',
                  font=('Arial', 8)).pack(anchor=tk.W)

        # ==== BOTTOM SECTION: Duplicates + buttons (pack FIRST to guarantee visibility) ====
        bottom_frame = ttk.Frame(self.dialog)
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=(2, 4))

        # ==== VERTICAL PANED WINDOW: top columns + preview, user-resizable ====
        vpane = ttk.PanedWindow(self.dialog, orient=tk.VERTICAL)
        vpane.pack(fill=tk.BOTH, expand=True, padx=6, pady=(2, 2))

        # ---- Top pane: two-column layout (gets more space) ----
        top_frame = ttk.Frame(vpane)
        vpane.add(top_frame, weight=3)

        top_pane = ttk.PanedWindow(top_frame, orient=tk.HORIZONTAL)
        top_pane.pack(fill=tk.BOTH, expand=True)

        # -- LEFT COLUMN: Select items to import --
        self.list_frame = ttk.LabelFrame(top_pane, text="Select prompt(s) to import (right-click to preview prompt text)",
                                          padding=(4, 2, 4, 2))
        top_pane.add(self.list_frame, weight=1)

        sys_bg = ttk.Style().lookup('TFrame', 'background') or 'SystemButtonFace'
        items_canvas = tk.Canvas(self.list_frame, highlightthickness=0,
                                 borderwidth=0, bg=sys_bg)
        items_sb = ttk.Scrollbar(self.list_frame, orient=tk.VERTICAL,
                                  command=items_canvas.yview)
        self.items_frame = tk.Frame(items_canvas, bg=sys_bg)

        self.items_frame.bind(
            "<Configure>",
            lambda e: items_canvas.configure(scrollregion=items_canvas.bbox("all"))
        )
        self._items_window_id = items_canvas.create_window(
            (0, 0), window=self.items_frame, anchor=tk.NW)
        items_canvas.configure(yscrollcommand=items_sb.set)

        def _resize_items_canvas(event):
            items_canvas.itemconfig(self._items_window_id, width=event.width)
            # Also stretch height so background fills the full canvas
            frame_h = self.items_frame.winfo_reqheight()
            if event.height > frame_h:
                items_canvas.itemconfig(self._items_window_id, height=event.height)
            else:
                items_canvas.itemconfig(self._items_window_id, height=frame_h)
        items_canvas.bind('<Configure>', _resize_items_canvas)

        def _on_items_mousewheel(event):
            items_canvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')
        items_canvas.bind('<MouseWheel>', _on_items_mousewheel)
        self.items_frame.bind('<MouseWheel>', _on_items_mousewheel)

        items_sb.pack(side=tk.RIGHT, fill=tk.Y)
        items_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Populate items
        self._populate_items()

        # Select All / None buttons
        sel_frame = ttk.Frame(self.list_frame)
        sel_frame.pack(fill=tk.X, pady=0)
        ttk.Button(sel_frame, text="Select All",
                   command=self._select_all, width=11).pack(side=tk.LEFT, padx=1)
        ttk.Button(sel_frame, text="Select None",
                   command=self._select_none, width=11).pack(side=tk.LEFT, padx=1)

        # -- RIGHT COLUMN: Destination folder picker --
        self.dest_frame = ttk.LabelFrame(top_pane, text="Import into folder(s)",
                                          padding=4)
        top_pane.add(self.dest_frame, weight=1)

        # Build folder list
        self.dest_folders = []
        all_folders = self._get_all_folders_with_depth()
        if not all_folders:
            all_folders = [("General", 0, None)]

        # Recreate structure checkbox (only if package has folders)
        if self.manifest.get("includes_folders", False):
            self.recreate_structure_var = tk.BooleanVar(value=True)
            ttk.Checkbutton(
                self.dest_frame,
                text="Recreate original folder structure",
                variable=self.recreate_structure_var,
                command=self._on_recreate_toggle,
            ).pack(anchor=tk.W, pady=(0, 2))

        ttk.Label(self.dest_frame,
                  text="Tick one or more destination folders:",
                  font=('Arial', 8)).pack(anchor=tk.W)

        # Folder checkboxes in a scrollable canvas
        dest_canvas = tk.Canvas(self.dest_frame, highlightthickness=0,
                                borderwidth=0, bg=sys_bg)
        dest_sb = ttk.Scrollbar(self.dest_frame, orient=tk.VERTICAL,
                                 command=dest_canvas.yview)
        dest_inner = tk.Frame(dest_canvas, bg=sys_bg)
        dest_inner.bind(
            "<Configure>",
            lambda e: dest_canvas.configure(
                scrollregion=dest_canvas.bbox("all"))
        )
        _dest_win_id = dest_canvas.create_window(
            (0, 0), window=dest_inner, anchor=tk.NW)
        dest_canvas.configure(yscrollcommand=dest_sb.set)

        def _resize_dest_canvas(event, cid=_dest_win_id):
            dest_canvas.itemconfig(cid, width=event.width)
            frame_h = dest_inner.winfo_reqheight()
            if event.height > frame_h:
                dest_canvas.itemconfig(cid, height=event.height)
            else:
                dest_canvas.itemconfig(cid, height=frame_h)
        dest_canvas.bind('<Configure>', _resize_dest_canvas)

        def _on_dest_mousewheel(event):
            dest_canvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')
        dest_canvas.bind('<MouseWheel>', _on_dest_mousewheel)
        dest_inner.bind('<MouseWheel>', _on_dest_mousewheel)

        dest_sb.pack(side=tk.RIGHT, fill=tk.Y)
        dest_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        for fname, depth, folder_node in all_folders:
            var = tk.BooleanVar(value=(fname == "General" and depth == 0))
            indent_str = "      " * depth
            if depth == 0:
                label = f"{indent_str}[+] {fname}"
            else:
                label = f"{indent_str}  |- {fname}"
            ttk.Checkbutton(dest_inner, text=label,
                            variable=var).pack(anchor=tk.W, padx=3)
            self.dest_folders.append({
                "var": var,
                "folder": folder_node,
                "name": fname,
                "depth": depth,
            })

        # ---- Bottom pane: prompt preview ----
        self.preview_visible = False
        self.preview_frame = ttk.LabelFrame(vpane, text="Prompt preview", padding=4)
        vpane.add(self.preview_frame, weight=1)
        self.dialog.after(50, lambda: vpane.sashpos(0, 150))

        # Font size controls row
        font_row = ttk.Frame(self.preview_frame)
        font_row.pack(fill=tk.X, pady=(0, 2))

        ttk.Label(font_row, text="Aa", font=('Arial', 9)).pack(side=tk.LEFT)
        ttk.Button(font_row, text="\u2212", width=2,
                   command=lambda: self._adjust_preview_font(-1)).pack(side=tk.LEFT, padx=1)
        ttk.Button(font_row, text="+", width=2,
                   command=lambda: self._adjust_preview_font(1)).pack(side=tk.LEFT, padx=1)

        self._font_size = 10
        try:
            self._font_size = self.ui_instance.config.get('font_size', 10)
        except Exception:
            pass
        self.preview_text = scrolledtext.ScrolledText(
            self.preview_frame, wrap=tk.WORD,
            font=('Arial', self._font_size),
            bg='#FFFDE6',
            fg='#999999',
            state=tk.DISABLED,
            relief=tk.SUNKEN,
            borderwidth=1)
        self.preview_text.pack(fill=tk.BOTH, expand=True)

        self.preview_text.config(state=tk.NORMAL)
        self.preview_text.insert('1.0',
            'Right-click or Ctrl+P on a prompt above to preview its full text here.')
        self.preview_text.config(state=tk.DISABLED)

        self.dialog.bind('<Control-p>', self._preview_selected_prompt)
        self.dialog.bind('<Control-P>', self._preview_selected_prompt)

        # Font size shortcuts (Ctrl+Plus / Ctrl+Minus) since modal dialog
        # blocks access to the main window's Aa buttons.
        # Windows needs multiple bindings to cover all keyboard layouts:
        self.dialog.bind('<Control-equal>', lambda e: self._adjust_preview_font(1))      # Ctrl+=
        self.dialog.bind('<Control-plus>', lambda e: self._adjust_preview_font(1))       # Ctrl+Shift+=
        self.dialog.bind('<Control-KP_Add>', lambda e: self._adjust_preview_font(1))     # Ctrl+NumPad+
        self.dialog.bind('<Control-minus>', lambda e: self._adjust_preview_font(-1))      # Ctrl+-
        self.dialog.bind('<Control-KP_Subtract>', lambda e: self._adjust_preview_font(-1))# Ctrl+NumPad-
        # Also bind directly on the preview widget in case dialog doesn't catch it
        self.preview_text.bind('<Control-equal>', lambda e: self._adjust_preview_font(1))
        self.preview_text.bind('<Control-plus>', lambda e: self._adjust_preview_font(1))
        self.preview_text.bind('<Control-KP_Add>', lambda e: self._adjust_preview_font(1))
        self.preview_text.bind('<Control-minus>', lambda e: self._adjust_preview_font(-1))
        self.preview_text.bind('<Control-KP_Subtract>', lambda e: self._adjust_preview_font(-1))
        self.preview_text.bind('<Control-MouseWheel>', self._on_ctrl_mousewheel)

        # Duplicate handling
        self.dup_frame = ttk.LabelFrame(bottom_frame,
                                         text="If prompt name already exists",
                                         padding=6)
        self.dup_frame.pack(fill=tk.X, pady=(0, 4))

        self.dup_mode = tk.StringVar(value="rename")
        ttk.Radiobutton(self.dup_frame, text="Skip duplicate",
                         variable=self.dup_mode, value="skip").pack(
                             side=tk.LEFT, padx=8)
        ttk.Radiobutton(self.dup_frame, text="Rename (add number)",
                         variable=self.dup_mode, value="rename").pack(
                             side=tk.LEFT, padx=8)
        ttk.Radiobutton(self.dup_frame, text="Overwrite",
                         variable=self.dup_mode, value="overwrite").pack(
                             side=tk.LEFT, padx=8)

        # Action buttons
        btn_frame = ttk.Frame(bottom_frame)
        btn_frame.pack(fill=tk.X, pady=(0, 2))

        self.import_btn = ttk.Button(btn_frame, text="Import",
                                      command=self._do_import, width=18)
        self.import_btn.pack(side=tk.RIGHT, padx=5)

        ttk.Button(btn_frame, text="Cancel",
                   command=self.dialog.destroy, width=12).pack(
                       side=tk.RIGHT, padx=5)

        # Update import button text with count
        self._update_import_count()

        # Register F1 context help on dialog sections
        try:
            add_help(self.list_frame, **HELP_TEXTS.get("import_dialog_items", {}))
            add_help(self.dest_frame, **HELP_TEXTS.get("import_dialog_destination", {}))
            add_help(self.dup_frame, **HELP_TEXTS.get("import_dialog_duplicates", {}))
            add_help(self.preview_text, **HELP_TEXTS.get("import_dialog_preview", {}))
        except Exception:
            pass

    def _preview_selected_prompt(self, event=None):
        """Show full text of the most recently ticked prompt in the preview pane."""
        # Find the last ticked prompt item
        for item in reversed(self.import_items):
            if item["var"].get() and item["type"] == "prompt":
                self._show_preview(item["data"])
                return
        # Nothing ticked — clear preview
        self._show_preview(None)

    def _show_preview(self, prompt_data):
        """Display a prompt's full text in the preview pane."""
        self.preview_text.config(state=tk.NORMAL)
        self.preview_text.delete('1.0', tk.END)

        if prompt_data is None:
            self.preview_text.insert('1.0', 'No prompt selected.')
            self.preview_text.config(state=tk.DISABLED, fg='#999999')
            self.preview_visible = False
            return

        # Get prompt name and text
        name = prompt_data.get("name", "Unnamed")
        versions = prompt_data.get("versions", [])
        idx = prompt_data.get("current_version_index", len(versions) - 1)
        if versions and 0 <= idx < len(versions):
            text = versions[idx].get("text", "(no text)")
        elif versions:
            text = versions[-1].get("text", "(no text)")
        else:
            text = "(no text)"

        version_count = len(versions)

        self.preview_text.insert('1.0',
            f"--- {name} ---  ({version_count} version(s))\n\n{text}")
        self.preview_text.config(state=tk.DISABLED, fg='#333333')

        self.preview_visible = True

    def _on_item_right_click(self, event, prompt_data):
        """Handle right-click on a prompt item — show preview."""
        self._show_preview(prompt_data)

    def _adjust_preview_font(self, delta):
        """Adjust preview font size by delta. Ctrl+Plus / Ctrl+Minus."""
        new_size = max(8, min(16, self._font_size + delta))
        if new_size == self._font_size:
            return
        self._font_size = new_size
        self.preview_text.config(font=('Arial', self._font_size))
        # Also save to config so it persists
        try:
            self.ui_instance.config['font_size'] = self._font_size
        except Exception:
            pass

    def _on_ctrl_mousewheel(self, event):
        """Ctrl+MouseWheel to resize preview font."""
        if event.delta > 0:
            self._adjust_preview_font(1)
        else:
            self._adjust_preview_font(-1)
        return 'break'

    # -------------------- Populate items --------------------

    def _populate_items(self):
        """Build the checkbox list of importable items."""
        row = 0

        # --- Loose prompts (not in folders) ---
        for prompt_data in self.data.get("prompts", []):
            var = tk.BooleanVar(value=True)
            name = prompt_data.get("name", "Unnamed")
            text_preview = self._get_text_preview(prompt_data)
            version_count = len(prompt_data.get("versions", []))

            cb = ttk.Checkbutton(
                self.items_frame, text=f"[P] {name}",
                variable=var, command=self._update_import_count,
            )
            cb.grid(row=row, column=0, sticky=tk.W, padx=5, pady=1)
            # Right-click to preview
            cb.bind('<Button-3>',
                    lambda e, pd=prompt_data: self._on_item_right_click(e, pd))

            info = f"{version_count} version(s)  |  {text_preview}"
            info_lbl = ttk.Label(self.items_frame, text=info, foreground='gray',
                      font=('Arial', 8))
            info_lbl.grid(row=row, column=1, sticky=tk.W, padx=5)
            info_lbl.bind('<Button-3>',
                         lambda e, pd=prompt_data: self._on_item_right_click(e, pd))

            self.import_items.append({
                "var": var,
                "data": prompt_data,
                "type": "prompt",
                "folder_path": None,
            })
            row += 1

        # --- Folders (with their prompts) ---
        for folder_data in self.data.get("folders", []):
            row = self._populate_folder(folder_data, row, indent=0)

    def _populate_folder(self, folder_data: dict, row: int,
                          indent: int = 0) -> int:
        """Recursively populate a folder and its children. Returns next row."""
        folder_name = folder_data.get("folder_name", "Unnamed Folder")
        prompts = folder_data.get("prompts", [])
        sub_folders = folder_data.get("sub_folders", [])
        total = self._count_folder_prompts(folder_data)

        # Folder-level checkbox (ticking this ticks/unticks all children)
        folder_var = tk.BooleanVar(value=True)
        pad_left = 5 + (indent * 20)

        cb = ttk.Checkbutton(
            self.items_frame,
            text=f"[+] {folder_name}  ({total} prompt(s))",
            variable=folder_var,
            style='TCheckbutton',
        )
        cb.grid(row=row, column=0, columnspan=2, sticky=tk.W,
                padx=pad_left, pady=(4, 1))

        child_vars = []
        row += 1

        # Prompts in this folder
        for prompt_data in prompts:
            var = tk.BooleanVar(value=True)
            child_vars.append(var)
            name = prompt_data.get("name", "Unnamed")
            text_preview = self._get_text_preview(prompt_data)

            cb_child = ttk.Checkbutton(
                self.items_frame, text=f"[P] {name}",
                variable=var, command=self._update_import_count,
            )
            cb_child.grid(row=row, column=0, sticky=tk.W,
                          padx=pad_left + 20, pady=1)
            # Right-click to preview
            cb_child.bind('<Button-3>',
                          lambda e, pd=prompt_data: self._on_item_right_click(e, pd))

            preview_lbl = ttk.Label(self.items_frame, text=text_preview,
                      foreground='gray', font=('Arial', 8))
            preview_lbl.grid(row=row, column=1, sticky=tk.W, padx=5)
            preview_lbl.bind('<Button-3>',
                            lambda e, pd=prompt_data: self._on_item_right_click(e, pd))

            self.import_items.append({
                "var": var,
                "data": prompt_data,
                "type": "prompt",
                "folder_path": folder_name,
            })
            row += 1

        # Sub-folders
        for sub in sub_folders:
            # Track sub-folder child vars too
            sub_start = len(self.import_items)
            row = self._populate_folder(sub, row, indent=indent + 1)
            # Collect the vars added by the sub-folder
            for item in self.import_items[sub_start:]:
                child_vars.append(item["var"])

        # Wire up the folder checkbox to toggle all children
        def toggle_children(fvar=folder_var, cvars=child_vars):
            val = fvar.get()
            for cv in cvars:
                cv.set(val)
            self._update_import_count()

        folder_var.trace_add("write", lambda *args: toggle_children())

        self.folder_items.append({
            "var": folder_var,
            "folder_name": folder_name,
            "child_vars": child_vars,
        })

        return row

    def _count_folder_prompts(self, folder_data: dict) -> int:
        """Count prompts in a folder recursively."""
        count = len(folder_data.get("prompts", []))
        for sub in folder_data.get("sub_folders", []):
            count += self._count_folder_prompts(sub)
        return count

    # -------------------- Helpers --------------------

    def _get_text_preview(self, prompt_data: dict, max_len: int = 60) -> str:
        """Get a short text preview of a prompt."""
        versions = prompt_data.get("versions", [])
        if versions:
            # Use the current version (last one, or by index)
            idx = prompt_data.get("current_version_index", len(versions) - 1)
            if 0 <= idx < len(versions):
                text = versions[idx].get("text", "")
            else:
                text = versions[-1].get("text", "")
        else:
            text = ""

        text = text.replace('\n', ' ').strip()
        if len(text) > max_len:
            text = text[:max_len] + "…"
        return text

    def _get_all_folders_with_depth(self) -> list:
        """Get list of (folder_name, depth, FolderNode) for all folders.
        
        Returns a list of tuples preserving hierarchy order, so the UI
        can display them with indentation.
        """
        result = []

        def collect(folder: FolderNode, depth: int):
            result.append((folder.name, depth, folder))
            for child in folder.children.values():
                if isinstance(child, FolderNode):
                    collect(child, depth + 1)

        for root_folder in self.tree_manager.root_folders.values():
            collect(root_folder, 0)

        return result

    def _select_all(self):
        for item in self.import_items:
            item["var"].set(True)
        for folder in self.folder_items:
            folder["var"].set(True)
        self._update_import_count()

    def _select_none(self):
        for item in self.import_items:
            item["var"].set(False)
        for folder in self.folder_items:
            folder["var"].set(False)
        self._update_import_count()

    def _update_import_count(self):
        """Update the import button text with selected count."""
        count = sum(1 for item in self.import_items if item["var"].get())
        self.import_btn.config(text=f"Import ({count})")

    def _on_recreate_toggle(self):
        """When 'recreate folder structure' is toggled, enable/disable
        the destination folder checkboxes."""
        recreate = getattr(self, 'recreate_structure_var', None)
        if recreate and recreate.get():
            # Disable manual folder selection — structure will be recreated
            for entry in self.dest_folders:
                entry["var"].set(False)
        else:
            # Re-enable — default to General
            for entry in self.dest_folders:
                if entry["name"] == "General" and entry["depth"] == 0:
                    entry["var"].set(True)

    # -------------------- Import execution --------------------

    def _do_import(self):
        """Execute the import."""
        selected = [item for item in self.import_items if item["var"].get()]

        if not selected:
            messagebox.showinfo("Nothing Selected",
                                "Please select at least one prompt to import.",
                                parent=self.dialog)
            return

        dup_mode = self.dup_mode.get()
        recreate = getattr(self, 'recreate_structure_var', None)
        recreate_structure = recreate.get() if recreate else False

        # Determine destination folders — collect actual FolderNode objects
        dest_folder_entries = [entry for entry in self.dest_folders
                               if entry["var"].get()]

        if not recreate_structure and not dest_folder_entries:
            messagebox.showinfo(
                "No Destination",
                "Please select at least one destination folder,\n"
                "or tick 'Recreate original folder structure'.",
                parent=self.dialog,
            )
            return

        # --- Perform import ---
        imported = 0
        skipped = 0
        errors = []

        for item in selected:
            prompt_data = item["data"]
            prompt_name = prompt_data.get("name", "Unnamed")

            try:
                # Build PromptItem from data
                from prompt_tree_manager import PromptItem

                if recreate_structure and item.get("folder_path"):
                    # Place into the original folder, creating it if needed
                    target_nodes = [self._find_or_create_folder(item["folder_path"])]
                elif dest_folder_entries:
                    # Use the selected destination folder(s) — actual nodes
                    target_nodes = []
                    for entry in dest_folder_entries:
                        if entry["folder"] is not None:
                            target_nodes.append(entry["folder"])
                        else:
                            # Placeholder entry (e.g. "General" when tree was empty)
                            target_nodes.append(
                                self._find_or_create_folder(entry["name"]))
                else:
                    target_nodes = [self._find_or_create_folder("General")]

                placed = False
                for target_folder in target_nodes:
                    if target_folder is None:
                        errors.append(f"{prompt_name}: could not find/create "
                                      f"destination folder")
                        continue

                    # Each destination gets its own copy of the prompt
                    new_prompt = PromptItem.from_dict(prompt_data)
                    new_prompt.is_system_prompt = False

                    # Handle duplicates
                    if target_folder.has_child(prompt_name):
                        if dup_mode == "skip":
                            skipped += 1
                            continue
                        elif dup_mode == "rename":
                            new_prompt.name = self._unique_name(
                                prompt_name, target_folder)
                        elif dup_mode == "overwrite":
                            target_folder.remove_child(prompt_name)

                    target_folder.add_child(new_prompt)
                    placed = True

                if placed:
                    imported += 1

            except Exception as e:
                errors.append(f"{prompt_name}: {e}")
                print(f"ERROR importing '{prompt_name}': {e}")

        # If we also need to recreate subfolder structures from the package
        if recreate_structure:
            for folder_data in self.data.get("folders", []):
                self._recreate_folder_tree(folder_data, selected)

        # Mark unsaved changes on the UI
        if imported > 0:
            self.ui_instance.has_unsaved_changes = True
            self.ui_instance.populate_tree()
            self.ui_instance.save_tree(show_message=False)

        # Report
        msg = f"Imported: {imported} prompt(s)"
        if skipped:
            msg += f"\nSkipped (duplicates): {skipped}"
        if errors:
            msg += f"\nErrors: {len(errors)}"
            msg += "\n\n" + "\n".join(errors[:5])
            if len(errors) > 5:
                msg += f"\n... and {len(errors) - 5} more"

        messagebox.showinfo("Import Complete", msg, parent=self.dialog)
        self.dialog.destroy()

    def _find_or_create_folder(self, folder_name: str) -> Optional[FolderNode]:
        """Find a folder by name, or create it as a root folder."""
        # Check root folders
        if folder_name in self.tree_manager.root_folders:
            return self.tree_manager.root_folders[folder_name]

        # Search nested folders
        def search(folder):
            for child in folder.children.values():
                if isinstance(child, FolderNode) and child.name == folder_name:
                    return child
                if isinstance(child, FolderNode):
                    result = search(child)
                    if result:
                        return result
            return None

        for root in self.tree_manager.root_folders.values():
            result = search(root)
            if result:
                return result

        # Not found — create as root folder
        new_folder = FolderNode(folder_name)
        self.tree_manager.add_root_folder(new_folder)
        return new_folder

    def _recreate_folder_tree(self, folder_data: dict, selected_items: list):
        """
        Recreate the exported folder structure in the tree,
        but only for prompts that were actually selected.
        """
        folder_name = folder_data.get("folder_name", "Imported")
        target_folder = self._find_or_create_folder(folder_name)

        # Process sub-folders recursively
        for sub_data in folder_data.get("sub_folders", []):
            sub_name = sub_data.get("folder_name", "Subfolder")
            # Create subfolder inside target
            if not target_folder.has_child(sub_name):
                sub_folder = FolderNode(sub_name)
                target_folder.add_child(sub_folder)
            self._recreate_folder_tree(sub_data, selected_items)

    def _unique_name(self, base_name: str, folder: FolderNode) -> str:
        """Generate a unique name by appending a number."""
        counter = 2
        new_name = f"{base_name} ({counter})"
        while folder.has_child(new_name):
            counter += 1
            new_name = f"{base_name} ({counter})"
        return new_name


# ============================================================================
# UTILITY
# ============================================================================

def _safe_filename(name: str) -> str:
    """Convert a name to a safe filename (remove/replace bad chars)."""
    # Replace common problematic characters
    bad_chars = '<>:"/\\|?*'
    result = name
    for c in bad_chars:
        result = result.replace(c, '_')
    # Trim whitespace and dots from ends
    result = result.strip('. ')
    return result if result else "export"


# ============================================================================
# DOCUMENT SERIALISATION HELPERS
# ============================================================================

def _load_doc_record(doc_id: str) -> Optional[dict]:
    """Load the document record (metadata) from the library."""
    try:
        from document_library import USE_SQLITE_DOCUMENTS
        if USE_SQLITE_DOCUMENTS:
            import db_manager as db
            return db.db_get_document(doc_id)
        else:
            from document_library import get_document_by_id
            return get_document_by_id(doc_id)
    except Exception as e:
        print(f"ERROR _load_doc_record: {e}")
        return None


def _load_doc_entries(doc_id: str) -> list:
    """Load the text entries for a document."""
    try:
        from document_library import USE_SQLITE_DOCUMENTS
        if USE_SQLITE_DOCUMENTS:
            import db_manager as db
            entries = db.db_get_entries(doc_id)
            return entries if entries else []
        else:
            from document_library import load_document_entries
            entries = load_document_entries(doc_id)
            return entries if entries else []
    except Exception as e:
        print(f"ERROR _load_doc_entries: {e}")
        return []


def _load_doc_conversation(doc_id: str) -> Optional[dict]:
    """Load the conversation thread for a document.
    Returns {'messages': [...], 'metadata': {...}} or None."""
    try:
        from document_library import USE_SQLITE_DOCUMENTS
        if USE_SQLITE_DOCUMENTS:
            import db_manager as db
            return db.db_get_conversation(doc_id)
        else:
            from document_library import load_thread_from_document
            thread, metadata = load_thread_from_document(doc_id)
            if thread:
                return {'messages': thread, 'metadata': metadata or {}}
            return None
    except Exception as e:
        print(f"ERROR _load_doc_conversation: {e}")
        return None


def _load_branches_for_source(doc_id: str) -> list:
    """Load all conversation branch documents linked to a source document.
    Returns list of dicts: [{'doc_id', 'title', 'exchange_count', 'doc_record', 'conversation'}, ...]"""
    try:
        from document_library import USE_SQLITE_DOCUMENTS
        if USE_SQLITE_DOCUMENTS:
            import db_manager as db
            db_branches = db.db_get_branches_for_source(doc_id)
            result = []
            for bd in db_branches:
                conv = db.db_get_conversation(bd["id"])
                messages = conv.get("messages", []) if conv else []
                exchange_count = len([m for m in messages if m.get("role") == "user"])
                if exchange_count == 0:
                    continue  # skip empty branches
                result.append({
                    'doc_id': bd["id"],
                    'title': bd.get("title", "Untitled"),
                    'exchange_count': exchange_count,
                    'doc_record': bd,
                    'conversation': conv,
                })
            return result
        else:
            from document_library import load_library, load_thread_from_document
            lib = load_library()
            library = lib.get("documents", [])
            result = []
            for doc in library:
                metadata = doc.get("metadata", {})
                parent_id = metadata.get("original_document_id") or metadata.get("parent_document_id")
                if parent_id != doc_id:
                    continue
                thread = doc.get("conversation_thread", [])
                exchange_count = len([m for m in thread if m.get("role") == "user"])
                if exchange_count == 0:
                    continue
                result.append({
                    'doc_id': doc["id"],
                    'title': doc.get("title", "Untitled"),
                    'exchange_count': exchange_count,
                    'doc_record': doc,
                    'conversation': {'messages': thread,
                                     'metadata': doc.get("thread_metadata", {})},
                })
            return result
    except Exception as e:
        print(f"ERROR _load_branches_for_source: {e}")
        return []


def _serialise_document_for_export(doc_id: str, include_conversations: bool = True,
                                    selected_branch_ids: list = None) -> Optional[dict]:
    """
    Serialise a single document for export.

    Args:
        doc_id: The document ID.
        include_conversations: Whether to include conversation branches.
        selected_branch_ids: If set, only export these branch IDs. None means all.

    Returns:
        A dict ready for JSON serialisation, or None on error.
    """
    record = _load_doc_record(doc_id)
    if not record:
        return None

    entries = _load_doc_entries(doc_id)

    doc_data = {
        'id': doc_id,
        'title': record.get('title', 'Untitled'),
        'doc_type': record.get('doc_type') or record.get('type', 'unknown'),
        'document_class': record.get('document_class', 'source'),
        'source': record.get('source', ''),
        'metadata': record.get('metadata', {}),
        'created_at': record.get('created_at') or record.get('created') or record.get('fetched', ''),
        'entries': entries,
        'branches': [],
    }

    if include_conversations:
        # Also include the document's own conversation (for non-branch docs)
        own_conv = _load_doc_conversation(doc_id)
        if own_conv and own_conv.get('messages'):
            doc_data['conversation'] = own_conv

        # Load branches (for source documents)
        if record.get('document_class', 'source') == 'source':
            all_branches = _load_branches_for_source(doc_id)
            for branch in all_branches:
                if selected_branch_ids is not None and branch['doc_id'] not in selected_branch_ids:
                    continue
                branch_entries = _load_doc_entries(branch['doc_id'])
                branch_data = {
                    'id': branch['doc_id'],
                    'title': branch['title'],
                    'doc_type': branch['doc_record'].get('doc_type') or
                                branch['doc_record'].get('type', 'conversation_thread'),
                    'document_class': branch['doc_record'].get('document_class', 'response'),
                    'source': branch['doc_record'].get('source', ''),
                    'metadata': branch['doc_record'].get('metadata', {}),
                    'entries': branch_entries,
                    'conversation': branch['conversation'],
                    'exchange_count': branch['exchange_count'],
                }
                doc_data['branches'].append(branch_data)

    return doc_data


# ============================================================================
# DOCUMENT EXPORT: PUBLIC API
# ============================================================================

def export_documents_dialog(parent: tk.Widget, tree_manager: TreeManager,
                            ui_instance):
    """
    Open a dialog that lets the user tick which documents to export,
    optionally including conversation branches.

    Called from: DocumentTreeManagerUI._export_selected()
    """
    # Check there is something to export
    total = 0
    for folder in tree_manager.root_folders.values():
        total += _count_items_in_folder(folder)
    if total == 0:
        messagebox.showinfo("Nothing to Export",
                            "The Documents Library is empty.",
                            parent=parent)
        return

    _DocExportDialog(parent=parent, tree_manager=tree_manager,
                     ui_instance=ui_instance)


def _count_items_in_folder(folder: FolderNode) -> int:
    """Count all non-folder items in a folder recursively."""
    count = 0
    for child in folder.children.values():
        if isinstance(child, FolderNode):
            count += _count_items_in_folder(child)
        else:
            count += 1
    return count


class _DocExportDialog:
    """
    Modal dialog showing all documents in the library with checkboxes.
    Source documents can expand to show conversation branches.
    """

    def __init__(self, parent, tree_manager, ui_instance):
        self.parent = parent
        self.tree_manager = tree_manager
        self.ui_instance = ui_instance

        self.export_items = []      # list of dicts: {var, doc_item, folder, ...}
        self.folder_items = []      # folder-level checkboxes
        self.branch_items = []      # branch checkboxes (nested under source docs)

        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Export Documents")
        self.dialog.transient(parent)
        self.dialog.grab_set()

        self._build_ui()

    # -------------------- UI --------------------

    def _build_ui(self):
        screen_w = self.dialog.winfo_screenwidth()
        dlg_w = min(screen_w // 2, 750)
        dlg_h = 480
        self.dialog.geometry(f"{dlg_w}x{dlg_h}+0+0")
        self.dialog.minsize(550, 400)

        # ---- Header ----
        header = ttk.Frame(self.dialog, padding=(8, 4, 8, 2))
        header.pack(fill=tk.X)
        ttk.Label(header, text="Export Documents",
                  font=('Arial', 12, 'bold')).pack(anchor=tk.W)
        ttk.Label(header, text="Tick the documents you want to export. "
                  "Source documents can include conversation branches.",
                  foreground='gray', font=('Arial', 8)).pack(anchor=tk.W)

        # ==== BOTTOM: buttons (pack first for visibility) ====
        bottom_frame = ttk.Frame(self.dialog)
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=(2, 4))

        # Options row
        opts_frame = ttk.Frame(bottom_frame)
        opts_frame.pack(fill=tk.X, pady=(0, 4))

        self.include_folders_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(opts_frame, text="Include folder structure",
                        variable=self.include_folders_var).pack(side=tk.LEFT, padx=(0, 12))

        self.include_convos_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(opts_frame, text="Include conversations",
                        variable=self.include_convos_var,
                        command=self._toggle_conversations).pack(side=tk.LEFT)

        # ---- Email option ----
        email_frame = ttk.Frame(bottom_frame)
        email_frame.pack(fill=tk.X, pady=(0, 4))

        self.email_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(email_frame, text="Also email to:",
                        variable=self.email_var,
                        command=self._toggle_email).pack(side=tk.LEFT)

        self.email_entry = ttk.Entry(email_frame, width=28)
        self.email_entry.pack(side=tk.LEFT, padx=(4, 0))
        self.email_entry.insert(0, "recipient@example.com")
        self.email_entry.config(state=tk.DISABLED)

        ttk.Label(email_frame, text=" via").pack(side=tk.LEFT, padx=(4, 0))
        self.email_provider_var = tk.StringVar(value="Gmail")
        self.email_provider_combo = ttk.Combobox(
            email_frame, textvariable=self.email_provider_var,
            values=EMAIL_PROVIDERS, state=tk.DISABLED, width=12)
        self.email_provider_combo.pack(side=tk.LEFT, padx=(2, 0))

        btn_frame = ttk.Frame(bottom_frame)
        btn_frame.pack(fill=tk.X)
        self.export_btn = ttk.Button(btn_frame, text="Export (0)",
                                     command=self._do_export)
        self.export_btn.pack(side=tk.RIGHT, padx=4)
        ttk.Button(btn_frame, text="Cancel",
                   command=self.dialog.destroy).pack(side=tk.RIGHT, padx=4)

        # ==== Scrollable checkbox list ====
        list_outer = ttk.LabelFrame(
            self.dialog,
            text="Select document(s) to export",
            padding=(4, 2, 4, 2))
        list_outer.pack(fill=tk.BOTH, expand=True, padx=6, pady=(2, 2))

        sys_bg = ttk.Style().lookup('TFrame', 'background') or 'SystemButtonFace'
        self._canvas = tk.Canvas(list_outer, highlightthickness=0,
                                  borderwidth=0, bg=sys_bg)
        sb = ttk.Scrollbar(list_outer, orient=tk.VERTICAL,
                            command=self._canvas.yview)
        self.items_frame = tk.Frame(self._canvas, bg=sys_bg)

        self.items_frame.bind(
            "<Configure>",
            lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._items_window = self._canvas.create_window(
            (0, 0), window=self.items_frame, anchor=tk.NW)
        self._canvas.configure(yscrollcommand=sb.set)

        def _resize(event):
            self._canvas.itemconfig(self._items_window, width=event.width)
        self._canvas.bind('<Configure>', _resize)

        def _wheel(event):
            self._canvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')
        self._canvas.bind('<MouseWheel>', _wheel)
        self.items_frame.bind('<MouseWheel>', _wheel)

        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._populate_items()

        # Select All / None
        sel_frame = ttk.Frame(list_outer)
        sel_frame.pack(fill=tk.X, pady=0)
        ttk.Button(sel_frame, text="Select All",
                   command=self._select_all, width=11).pack(side=tk.LEFT, padx=1)
        ttk.Button(sel_frame, text="Select None",
                   command=self._select_none, width=11).pack(side=tk.LEFT, padx=1)

        self._update_export_count()

    # -------------------- Populate --------------------

    def _populate_items(self):
        """Build checkbox list from the tree_manager data."""
        row = 0
        for folder_name in sorted(self.tree_manager.root_folders.keys()):
            folder = self.tree_manager.root_folders[folder_name]
            row = self._populate_folder(folder, row, indent=0)

    def _populate_folder(self, folder: FolderNode, row: int,
                          indent: int = 0) -> int:
        """Recursively populate a folder and its documents. Returns next row."""
        total = _count_items_in_folder(folder)
        if total == 0:
            return row

        # Folder header with its own checkbox
        folder_var = tk.BooleanVar(value=True)
        pad_left = 8 + indent * 20

        cb = ttk.Checkbutton(
            self.items_frame,
            text=f"\U0001F4C1 {folder.name}  ({total} document{'s' if total != 1 else ''})",
            variable=folder_var,
            command=lambda fv=folder_var, f=folder: self._toggle_folder(fv, f))
        cb.grid(row=row, column=0, sticky=tk.W, padx=(pad_left, 4), pady=1)
        self.folder_items.append({'var': folder_var, 'folder': folder, 'widget': cb})
        row += 1

        # Child items
        for child in sorted(folder.children.values(), key=lambda c: c.name):
            if isinstance(child, FolderNode):
                row = self._populate_folder(child, row, indent + 1)
            else:
                # Document item
                from document_tree_manager import DocumentItem
                if not isinstance(child, DocumentItem):
                    continue

                doc_var = tk.BooleanVar(value=True)
                icon = child.get_icon()
                label_text = f"{icon} {child.name}"
                doc_class = child.document_class
                if doc_class and doc_class != 'source':
                    label_text += f"  [{doc_class}]"

                cb = ttk.Checkbutton(
                    self.items_frame, text=label_text, variable=doc_var,
                    command=self._update_export_count)
                cb.grid(row=row, column=0, sticky=tk.W,
                        padx=(pad_left + 20, 4), pady=1)

                item_entry = {
                    'var': doc_var,
                    'doc_item': child,
                    'folder': folder,
                    'widget': cb,
                    'branch_entries': [],
                }
                self.export_items.append(item_entry)
                row += 1

                # If source document, load branches and show sub-checkboxes
                if child.document_class == 'source':
                    branches = _load_branches_for_source(child.doc_id)
                    if branches:
                        for branch in branches:
                            br_var = tk.BooleanVar(value=True)
                            br_label = (f"    \U0001F4AC {branch['title']}  "
                                        f"({branch['exchange_count']} exchange"
                                        f"{'s' if branch['exchange_count'] != 1 else ''})")
                            br_cb = ttk.Checkbutton(
                                self.items_frame, text=br_label,
                                variable=br_var,
                                command=self._update_export_count)
                            br_cb.grid(row=row, column=0, sticky=tk.W,
                                       padx=(pad_left + 40, 4), pady=0)

                            br_entry = {
                                'var': br_var,
                                'branch_id': branch['doc_id'],
                                'title': branch['title'],
                                'widget': br_cb,
                                'parent_doc_item': child,
                            }
                            item_entry['branch_entries'].append(br_entry)
                            self.branch_items.append(br_entry)
                            row += 1

        return row

    # -------------------- Actions --------------------

    def _toggle_folder(self, folder_var, folder):
        """When a folder checkbox is toggled, set all children to match."""
        val = folder_var.get()
        for item in self.export_items:
            if item['folder'] is folder:
                item['var'].set(val)
                for br in item['branch_entries']:
                    br['var'].set(val)
        self._update_export_count()

    def _toggle_conversations(self):
        """Enable/disable branch checkboxes based on the include-conversations toggle."""
        enabled = self.include_convos_var.get()
        state = tk.NORMAL if enabled else tk.DISABLED
        for br in self.branch_items:
            br['widget'].configure(state=state)
            if not enabled:
                br['var'].set(False)
            else:
                br['var'].set(True)
        self._update_export_count()

    def _select_all(self):
        for item in self.export_items:
            item['var'].set(True)
        for br in self.branch_items:
            br['var'].set(True)
        for fi in self.folder_items:
            fi['var'].set(True)
        self._update_export_count()

    def _select_none(self):
        for item in self.export_items:
            item['var'].set(False)
        for br in self.branch_items:
            br['var'].set(False)
        for fi in self.folder_items:
            fi['var'].set(False)
        self._update_export_count()

    def _update_export_count(self):
        count = sum(1 for item in self.export_items if item['var'].get())
        br_count = sum(1 for br in self.branch_items if br['var'].get())
        label = f"Export ({count} doc{'s' if count != 1 else ''}"
        if br_count > 0 and self.include_convos_var.get():
            label += f", {br_count} branch{'es' if br_count != 1 else ''}"
        label += ")"
        self.export_btn.configure(text=label)

    # -------------------- Email toggle --------------------

    def _toggle_email(self):
        """Enable/disable the email entry and provider combo based on checkbox."""
        if self.email_var.get():
            self.email_entry.config(state=tk.NORMAL)
            self.email_provider_combo.config(state='readonly')
            self.email_entry.select_range(0, tk.END)
            self.email_entry.focus_set()
        else:
            self.email_entry.config(state=tk.DISABLED)
            self.email_provider_combo.config(state=tk.DISABLED)

    # -------------------- Export logic --------------------

    def _do_export(self):
        """Collect ticked items and write the .docanalyser package."""
        selected = [item for item in self.export_items if item['var'].get()]
        if not selected:
            messagebox.showinfo("Nothing Selected",
                                "Please tick at least one document to export.",
                                parent=self.dialog)
            return

        include_convos = self.include_convos_var.get()
        include_folders = self.include_folders_var.get()

        # Build default filename
        if len(selected) == 1:
            default_name = _safe_filename(selected[0]['doc_item'].name)
        else:
            default_name = f"documents_{len(selected)}_items"

        filepath = filedialog.asksaveasfilename(
            parent=self.dialog,
            title="Export Documents",
            defaultextension=FILE_EXTENSION,
            filetypes=FILE_FILTER,
            initialfile=default_name + FILE_EXTENSION,
        )
        if not filepath:
            return

        # Serialise each selected document
        documents_out = []
        total_branches = 0
        for item in selected:
            doc_item = item['doc_item']

            # Determine which branches are selected for this document
            selected_branch_ids = None
            if include_convos and item['branch_entries']:
                sel_br = [br['branch_id'] for br in item['branch_entries']
                          if br['var'].get()]
                if sel_br:
                    selected_branch_ids = sel_br
                    total_branches += len(sel_br)
                else:
                    selected_branch_ids = []  # explicitly none

            doc_data = _serialise_document_for_export(
                doc_item.doc_id,
                include_conversations=include_convos,
                selected_branch_ids=selected_branch_ids,
            )
            if doc_data:
                # Add folder path for structure recreation
                if include_folders:
                    doc_data['_folder_path'] = self._get_folder_path(item['folder'])
                documents_out.append(doc_data)

        if not documents_out:
            messagebox.showerror("Export Failed",
                                 "Could not serialise any documents.",
                                 parent=self.dialog)
            return

        payload = {
            'export_type': 'documents',
            'documents': documents_out,
            'includes_folders': include_folders,
            'includes_conversations': include_convos,
        }

        manifest = _build_manifest(
            content_type="documents",
            item_count=len(documents_out),
            source_desc=f"Export: {len(documents_out)} document(s), {total_branches} branch(es)",
            includes_folders=include_folders,
        )

        if _write_package(filepath, manifest, payload):
            # Check if user also wants to email
            want_email = self.email_var.get()
            recipient = self.email_entry.get().strip() if want_email else ""

            if want_email and not recipient:
                messagebox.showwarning("Email Address Required",
                                       "Please enter a recipient email address.",
                                       parent=self.dialog)
                return  # Don't close — file is saved, let user fix email

            messagebox.showinfo(
                "Export Complete",
                f"Exported {len(documents_out)} document(s) to:\n\n{filepath}",
                parent=self.dialog,
            )

            if want_email and recipient:
                provider = self.email_provider_var.get()
                if provider == "Other Email":
                    messagebox.showinfo(
                        "Heads Up",
                        "'Other Email' uses your computer's default email\n"
                        "program. Sometimes line breaks in the message\n"
                        "can look odd (e.g. everything on one line).\n\n"
                        "Please check the message looks OK before sending.",
                        parent=self.dialog,
                    )
                names = [item['doc_item'].name for item in selected]
                _open_email_with_attachment(
                    filepath=filepath,
                    recipient=recipient,
                    content_type="documents",
                    item_count=len(documents_out),
                    item_names=names,
                    email_provider=provider,
                    parent=self.dialog,
                )

            self.dialog.destroy()
        else:
            messagebox.showerror(
                "Export Failed",
                "An error occurred while writing the file.\n"
                "Check the console for details.",
                parent=self.dialog,
            )

    def _get_folder_path(self, folder: FolderNode) -> str:
        """Walk up to build the folder path string, e.g. 'Research/AI Papers'."""
        parts = [folder.name]
        current = folder
        while hasattr(current, 'parent_folder') and current.parent_folder is not None:
            current = current.parent_folder
            parts.insert(0, current.name)
        return '/'.join(parts)


# ============================================================================
# DOCUMENT IMPORT: PUBLIC API
# ============================================================================

def import_documents(parent: tk.Widget, tree_manager: TreeManager,
                     ui_instance, library_path: str,
                     refresh_callback: Callable = None):
    """
    Open a .docanalyser file, preview its documents, let the user choose
    what to import, then import them into the Documents Library.

    Called from: DocumentTreeManagerUI._import_documents()
    """
    filepath = filedialog.askopenfilename(
        parent=parent,
        title="Import Documents",
        filetypes=FILE_FILTER,
    )
    if not filepath:
        return

    manifest, data = _read_package(filepath)
    if manifest is None or data is None:
        messagebox.showerror(
            "Import Failed",
            "Could not read the file. It may be corrupted or not a valid "
            ".docanalyser package.",
            parent=parent,
        )
        return

    if manifest.get("content_type") != "documents":
        messagebox.showerror(
            "Wrong Content Type",
            f"This file contains '{manifest.get('content_type')}' data, "
            f"not documents.\n\nPlease use the Prompts Library to import "
            f"prompt packages.",
            parent=parent,
        )
        return

    _DocImportDialog(
        parent=parent,
        filepath=filepath,
        manifest=manifest,
        data=data,
        tree_manager=tree_manager,
        ui_instance=ui_instance,
        library_path=library_path,
        refresh_callback=refresh_callback,
    )


# ============================================================================
# DOCUMENT IMPORT DIALOG
# ============================================================================

class _DocImportDialog:
    """
    Modal dialog for importing documents from a .docanalyser package.
    Shows each document with checkboxes, scope controls, branch selection,
    destination folder picker, and duplicate handling.
    """

    def __init__(self, parent, filepath, manifest, data,
                 tree_manager, ui_instance, library_path, refresh_callback):
        self.parent = parent
        self.filepath = filepath
        self.manifest = manifest
        self.data = data
        self.tree_manager = tree_manager
        self.ui_instance = ui_instance
        self.library_path = library_path
        self.refresh_callback = refresh_callback

        self.import_items = []      # dicts: {var, doc_data, branch_entries, ...}
        self.branch_import_items = []
        self.dest_folders = []      # destination folder entries

        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Import Documents")
        self.dialog.transient(parent)
        self.dialog.grab_set()

        self._build_ui()

    def _build_ui(self):
        screen_w = self.dialog.winfo_screenwidth()
        dlg_w = min(screen_w // 2, 750)
        dlg_h = 520
        self.dialog.geometry(f"{dlg_w}x{dlg_h}+0+0")
        self.dialog.minsize(550, 440)

        # ---- Header ----
        header = ttk.Frame(self.dialog, padding=(8, 4, 8, 2))
        header.pack(fill=tk.X)
        ttk.Label(header, text="Import Documents",
                  font=('Arial', 12, 'bold')).pack(anchor=tk.W)

        fname = os.path.basename(self.filepath)
        doc_count = len(self.data.get('documents', []))
        has_convos = self.data.get('includes_conversations', False)
        info_parts = [f"{doc_count} document{'s' if doc_count != 1 else ''}"]
        if has_convos:
            info_parts.append("includes conversations")
        ttk.Label(header, text=f"File: {fname}  ({', '.join(info_parts)})",
                  foreground='gray', font=('Arial', 8)).pack(anchor=tk.W)

        # ==== BOTTOM SECTION (pack first for visibility) ====
        bottom_frame = ttk.Frame(self.dialog, padding=(8, 2, 8, 4))
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.X)

        # Scope option
        scope_frame = ttk.LabelFrame(bottom_frame, text="Import scope", padding=4)
        scope_frame.pack(fill=tk.X, pady=(0, 4))

        self.scope_var = tk.StringVar(value="full")
        ttk.Radiobutton(scope_frame, text="Full (source + conversations)",
                        variable=self.scope_var, value="full",
                        command=self._on_scope_change).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Radiobutton(scope_frame, text="Source content only",
                        variable=self.scope_var, value="source_only",
                        command=self._on_scope_change).pack(side=tk.LEFT)

        # Duplicate handling
        dup_frame = ttk.LabelFrame(bottom_frame, text="If document title already exists", padding=4)
        dup_frame.pack(fill=tk.X, pady=(0, 4))

        self.dup_mode = tk.StringVar(value="skip")
        ttk.Radiobutton(dup_frame, text="Skip", variable=self.dup_mode,
                        value="skip").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Radiobutton(dup_frame, text="Rename (add number)", variable=self.dup_mode,
                        value="rename").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Radiobutton(dup_frame, text="Overwrite", variable=self.dup_mode,
                        value="overwrite").pack(side=tk.LEFT)

        # Destination folder
        dest_frame = ttk.LabelFrame(bottom_frame, text="Import into folder(s)", padding=4)
        dest_frame.pack(fill=tk.X, pady=(0, 4))

        self.recreate_structure_var = tk.BooleanVar(value=True)
        has_folders = self.data.get('includes_folders', False)
        if has_folders:
            ttk.Checkbutton(dest_frame, text="Recreate original folder structure",
                            variable=self.recreate_structure_var,
                            command=self._on_recreate_toggle).pack(anchor=tk.W)

        # Existing folders as targets
        self._dest_inner = ttk.Frame(dest_frame)
        self._dest_inner.pack(fill=tk.X)
        self._populate_dest_folders()

        # Buttons
        btn_frame = ttk.Frame(bottom_frame)
        btn_frame.pack(fill=tk.X, pady=(2, 0))
        self.import_btn = ttk.Button(btn_frame, text="Import (0)",
                                      command=self._do_import)
        self.import_btn.pack(side=tk.RIGHT, padx=4)
        ttk.Button(btn_frame, text="Cancel",
                   command=self.dialog.destroy).pack(side=tk.RIGHT, padx=4)

        # ==== Scrollable document list ====
        list_outer = ttk.LabelFrame(
            self.dialog,
            text="Select document(s) to import",
            padding=(4, 2, 4, 2))
        list_outer.pack(fill=tk.BOTH, expand=True, padx=6, pady=(2, 2))

        sys_bg = ttk.Style().lookup('TFrame', 'background') or 'SystemButtonFace'
        self._canvas = tk.Canvas(list_outer, highlightthickness=0,
                                  borderwidth=0, bg=sys_bg)
        sb = ttk.Scrollbar(list_outer, orient=tk.VERTICAL,
                            command=self._canvas.yview)
        self.items_frame = tk.Frame(self._canvas, bg=sys_bg)

        self.items_frame.bind(
            "<Configure>",
            lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._items_window = self._canvas.create_window(
            (0, 0), window=self.items_frame, anchor=tk.NW)
        self._canvas.configure(yscrollcommand=sb.set)

        def _resize(event):
            self._canvas.itemconfig(self._items_window, width=event.width)
        self._canvas.bind('<Configure>', _resize)

        def _wheel(event):
            self._canvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')
        self._canvas.bind('<MouseWheel>', _wheel)
        self.items_frame.bind('<MouseWheel>', _wheel)

        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._populate_items()

        # Select All / None
        sel_frame = ttk.Frame(list_outer)
        sel_frame.pack(fill=tk.X, pady=0)
        ttk.Button(sel_frame, text="Select All",
                   command=self._select_all, width=11).pack(side=tk.LEFT, padx=1)
        ttk.Button(sel_frame, text="Select None",
                   command=self._select_none, width=11).pack(side=tk.LEFT, padx=1)

        self._update_import_count()

    # -------------------- Populate items --------------------

    def _populate_items(self):
        """Build the checkbox list from the package data."""
        documents = self.data.get('documents', [])
        row = 0
        for doc_data in documents:
            doc_var = tk.BooleanVar(value=True)
            doc_class = doc_data.get('document_class', 'source')
            title = doc_data.get('title', 'Untitled')

            # Build label
            label = f"\U0001F4C4 {title}"
            if doc_class != 'source':
                label += f"  [{doc_class}]"
            entry_count = len(doc_data.get('entries', []))
            if entry_count:
                label += f"  ({entry_count} entries)"

            cb = ttk.Checkbutton(
                self.items_frame, text=label, variable=doc_var,
                command=self._update_import_count)
            cb.grid(row=row, column=0, sticky=tk.W, padx=(8, 4), pady=1)

            item_entry = {
                'var': doc_var,
                'data': doc_data,
                'widget': cb,
                'branch_entries': [],
                'folder_path': doc_data.get('_folder_path', 'General'),
            }
            self.import_items.append(item_entry)
            row += 1

            # Show branches if present
            branches = doc_data.get('branches', [])
            for branch in branches:
                br_var = tk.BooleanVar(value=True)
                ex_count = branch.get('exchange_count', 0)
                br_label = (f"    \U0001F4AC {branch.get('title', 'Branch')}  "
                            f"({ex_count} exchange{'s' if ex_count != 1 else ''})")
                br_cb = ttk.Checkbutton(
                    self.items_frame, text=br_label,
                    variable=br_var,
                    command=self._update_import_count)
                br_cb.grid(row=row, column=0, sticky=tk.W, padx=(28, 4), pady=0)

                br_entry = {
                    'var': br_var,
                    'data': branch,
                    'widget': br_cb,
                    'parent_item': item_entry,
                }
                item_entry['branch_entries'].append(br_entry)
                self.branch_import_items.append(br_entry)
                row += 1

    def _populate_dest_folders(self):
        """Populate destination folder checkboxes."""
        for w in self._dest_inner.winfo_children():
            w.destroy()
        self.dest_folders = []

        folder_names = sorted(self.tree_manager.root_folders.keys())
        if not folder_names:
            folder_names = ["General"]

        for fname in folder_names:
            var = tk.BooleanVar(value=(fname == folder_names[0]))
            folder_obj = self.tree_manager.root_folders.get(fname)
            ttk.Checkbutton(self._dest_inner, text=fname,
                            variable=var).pack(side=tk.LEFT, padx=(0, 8))
            self.dest_folders.append({'name': fname, 'var': var, 'folder': folder_obj})

    # -------------------- Toggle / Selection --------------------

    def _on_scope_change(self):
        """Enable/disable branch checkboxes based on scope."""
        source_only = (self.scope_var.get() == "source_only")
        state = tk.DISABLED if source_only else tk.NORMAL
        for br in self.branch_import_items:
            br['widget'].configure(state=state)
            if source_only:
                br['var'].set(False)
            else:
                br['var'].set(True)
        self._update_import_count()

    def _on_recreate_toggle(self):
        """When recreate-structure is toggled, show/hide destination pickers."""
        if self.recreate_structure_var.get():
            self._dest_inner.pack_forget()
        else:
            self._dest_inner.pack(fill=tk.X)

    def _select_all(self):
        for item in self.import_items:
            item['var'].set(True)
        for br in self.branch_import_items:
            br['var'].set(True)
        self._update_import_count()

    def _select_none(self):
        for item in self.import_items:
            item['var'].set(False)
        for br in self.branch_import_items:
            br['var'].set(False)
        self._update_import_count()

    def _update_import_count(self):
        count = sum(1 for item in self.import_items if item['var'].get())
        br_count = sum(1 for br in self.branch_import_items if br['var'].get())
        label = f"Import ({count} doc{'s' if count != 1 else ''}"
        if br_count > 0 and self.scope_var.get() != 'source_only':
            label += f", {br_count} branch{'es' if br_count != 1 else ''}"
        label += ")"
        self.import_btn.configure(text=label)

    # -------------------- Import logic --------------------

    def _do_import(self):
        """Import selected documents into the library."""
        selected = [item for item in self.import_items if item['var'].get()]
        if not selected:
            messagebox.showinfo("Nothing Selected",
                                "Please select at least one document to import.",
                                parent=self.dialog)
            return

        source_only = (self.scope_var.get() == 'source_only')
        dup_mode = self.dup_mode.get()
        recreate = self.recreate_structure_var.get()

        # Determine destination
        dest_folder_entries = [e for e in self.dest_folders if e['var'].get()]
        if not recreate and not dest_folder_entries:
            messagebox.showinfo(
                "No Destination",
                "Please select at least one destination folder,\n"
                "or tick 'Recreate original folder structure'.",
                parent=self.dialog)
            return

        imported = 0
        branches_imported = 0
        skipped = 0
        errors = []

        from document_library import add_document_to_library, load_library
        from document_tree_manager import DocumentItem
        import uuid

        for item in selected:
            doc_data = item['data']
            title = doc_data.get('title', 'Untitled')

            try:
                # Check for duplicate by title
                existing = self._find_existing_doc_by_title(title)

                if existing:
                    if dup_mode == 'skip':
                        skipped += 1
                        continue
                    elif dup_mode == 'rename':
                        title = self._unique_title(title)
                    elif dup_mode == 'overwrite':
                        # Delete existing and re-add
                        from document_library import delete_document
                        delete_document(existing['id'])

                # Generate a new doc ID
                new_id = str(uuid.uuid4())[:12]

                # Add document to library
                doc_id = add_document_to_library(
                    doc_type=doc_data.get('doc_type', 'imported'),
                    source=doc_data.get('source', f'Imported from {os.path.basename(self.filepath)}'),
                    title=title,
                    entries=doc_data.get('entries', []),
                    metadata=doc_data.get('metadata', {}),
                    document_class=doc_data.get('document_class', 'source'),
                )

                if not doc_id:
                    errors.append(f"{title}: failed to add to library")
                    continue

                # Add to tree
                doc_item = DocumentItem(
                    doc_id=doc_id,
                    title=title,
                    doc_type=doc_data.get('doc_type', 'imported'),
                    document_class=doc_data.get('document_class', 'source'),
                )
                doc_item.source = doc_data.get('source', '')

                target_folder = self._get_target_folder(
                    item, recreate, dest_folder_entries)
                target_folder.add_child(doc_item)

                imported += 1

                # Import branches if not source-only
                if not source_only:
                    for br_entry in item.get('branch_entries', []):
                        if not br_entry['var'].get():
                            continue
                        br_data = br_entry['data']
                        br_title = br_data.get('title', 'Branch')

                        # Create the branch document
                        br_meta = br_data.get('metadata', {})
                        br_meta['original_document_id'] = doc_id  # link to new parent
                        br_meta['parent_document_id'] = doc_id

                        br_doc_id = add_document_to_library(
                            doc_type=br_data.get('doc_type', 'conversation_thread'),
                            source=br_data.get('source', ''),
                            title=br_title,
                            entries=br_data.get('entries', []),
                            metadata=br_meta,
                            document_class=br_data.get('document_class', 'response'),
                        )

                        if br_doc_id:
                            # Save the conversation thread
                            conv = br_data.get('conversation')
                            if conv and conv.get('messages'):
                                from document_library import save_thread_to_document
                                save_thread_to_document(
                                    br_doc_id,
                                    conv['messages'],
                                    conv.get('metadata', {}),
                                )

                            # Add branch to tree (same folder as parent)
                            br_item = DocumentItem(
                                doc_id=br_doc_id,
                                title=br_title,
                                doc_type=br_data.get('doc_type', 'conversation_thread'),
                                document_class=br_data.get('document_class', 'response'),
                            )
                            br_item.has_thread = True
                            target_folder.add_child(br_item)
                            branches_imported += 1

                # Also restore the source document's own conversation if present
                if not source_only:
                    own_conv = doc_data.get('conversation')
                    if own_conv and own_conv.get('messages'):
                        from document_library import save_thread_to_document
                        save_thread_to_document(
                            doc_id,
                            own_conv['messages'],
                            own_conv.get('metadata', {}),
                        )
                        doc_item.has_thread = True

            except Exception as e:
                errors.append(f"{title}: {e}")
                print(f"ERROR importing document '{title}': {e}")
                import traceback
                traceback.print_exc()

        # Save tree and refresh
        if imported > 0:
            self.ui_instance.has_unsaved_changes = True
            self.ui_instance.populate_tree()
            self.ui_instance.save_tree(show_message=False)

        # Report
        msg = f"Imported: {imported} document(s)"
        if branches_imported:
            msg += f"\nConversation branches: {branches_imported}"
        if skipped:
            msg += f"\nSkipped (duplicates): {skipped}"
        if errors:
            msg += f"\nErrors: {len(errors)}"
            msg += "\n\n" + "\n".join(errors[:5])
            if len(errors) > 5:
                msg += f"\n... and {len(errors) - 5} more"

        messagebox.showinfo("Import Complete", msg, parent=self.dialog)
        self.dialog.destroy()

    # -------------------- Helpers --------------------

    def _find_existing_doc_by_title(self, title: str) -> Optional[dict]:
        """Search the library for a document with the same title."""
        try:
            from document_library import USE_SQLITE_DOCUMENTS
            if USE_SQLITE_DOCUMENTS:
                import db_manager as db
                all_docs = db.db_get_all_documents()
            else:
                from document_library import get_all_documents
                all_docs = get_all_documents()
            for doc in all_docs:
                if doc.get('title', '') == title:
                    return doc
        except Exception:
            pass
        return None

    def _unique_title(self, base_title: str) -> str:
        """Generate a unique title by appending a number."""
        counter = 2
        new_title = f"{base_title} ({counter})"
        while self._find_existing_doc_by_title(new_title):
            counter += 1
            new_title = f"{base_title} ({counter})"
        return new_title

    def _get_target_folder(self, item, recreate, dest_folder_entries):
        """Determine the target folder for a document."""
        if recreate and item.get('folder_path'):
            return self._find_or_create_folder(item['folder_path'])
        elif dest_folder_entries:
            # Use first selected destination
            entry = dest_folder_entries[0]
            if entry['folder'] is not None:
                return entry['folder']
            return self._find_or_create_folder(entry['name'])
        return self._find_or_create_folder('General')

    def _find_or_create_folder(self, folder_path: str) -> FolderNode:
        """Find or create a folder by path (e.g. 'Research/AI Papers')."""
        parts = folder_path.split('/') if '/' in folder_path else [folder_path]

        # Start from root
        root_name = parts[0]
        if root_name in self.tree_manager.root_folders:
            current = self.tree_manager.root_folders[root_name]
        else:
            current = FolderNode(root_name)
            self.tree_manager.add_root_folder(current)

        # Navigate/create subfolders
        for part in parts[1:]:
            found = None
            for child in current.children.values():
                if isinstance(child, FolderNode) and child.name == part:
                    found = child
                    break
            if found:
                current = found
            else:
                new_sub = FolderNode(part)
                current.add_child(new_sub)
                current = new_sub

        return current
