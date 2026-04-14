"""
google_drive_dialog.py - Google Drive browser dialog for DocAnalyser.

Opens a Toplevel window that allows the user to:
  - Authenticate with Google Drive via OAuth 2.0
  - Browse My Drive folders and Shared with Me
  - Open files directly in DocAnalyser
  - Upload the current output back to Drive

Requires google_drive_handler.py and the google-api-python-client /
google-auth-oauthlib packages (pip install google-api-python-client
google-auth-oauthlib).
"""

import os
import tempfile
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from google_drive_handler import get_gdrive_handler, SUPPORTED_MIMES, FOLDER_MIME


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _human_size(size_str):
    """Convert a Drive file size string (bytes) to human-readable."""
    try:
        n = int(size_str)
    except (TypeError, ValueError):
        return ''
    if n < 1024:
        return f"{n} B"
    elif n < 1024 ** 2:
        return f"{n / 1024:.0f} KB"
    elif n < 1024 ** 3:
        return f"{n / 1024 ** 2:.1f} MB"
    else:
        return f"{n / 1024 ** 3:.1f} GB"


def _short_date(dt_str):
    """Trim ISO datetime to YYYY-MM-DD."""
    return dt_str[:10] if dt_str else ''


# ---------------------------------------------------------------------------
# Dialog class
# ---------------------------------------------------------------------------

class GoogleDriveDialog:
    """
    Google Drive file browser dialog.

    Instantiate with a parent Tk widget and the main DocAnalyzerApp instance:
        GoogleDriveDialog(parent_window, app_instance)
    """

    def __init__(self, parent, app):
        self.app = app

        # Resolve the data directory (where credentials/token live)
        data_dir = getattr(app, 'data_dir', None) or os.path.join(
            os.path.expanduser('~'), 'AppData', 'Roaming', 'DocAnalyser_Beta'
        )
        self.handler = get_gdrive_handler(data_dir)

        # Navigation state
        self._folder_stack = []    # list of (folder_id, folder_name) breadcrumb
        self._current_files = []   # metadata dicts currently shown in the list
        self._search_active = False
        self._pending_downloads = 0
        self._completed_paths = []   # accumulates successfully downloaded file paths
        self._failed_downloads = []  # accumulates names of failed downloads
        self._download_semaphore = threading.Semaphore(5)  # max 5 concurrent downloads

        # Build window
        self.win = tk.Toplevel(parent)
        self.win.title("Google Drive")
        self.win.geometry("740x560")
        self.win.resizable(True, True)
        self.win.transient(parent)

        self._build_ui()
        self._refresh_state()

    # -----------------------------------------------------------------------
    # UI construction
    # -----------------------------------------------------------------------

    def _build_ui(self):
        self.win.columnconfigure(0, weight=1)
        self.win.rowconfigure(1, weight=1)

        # ── Top bar: title  /  status  /  sign-in button ──────────────────
        top = tk.Frame(self.win, padx=8, pady=6)
        top.grid(row=0, column=0, sticky='ew')
        top.columnconfigure(1, weight=1)

        tk.Label(top, text="Google Drive", font=('Segoe UI', 10, 'bold')).grid(
            row=0, column=0, sticky='w'
        )
        self._status_label = tk.Label(top, text='', fg='grey', font=('Segoe UI', 9))
        self._status_label.grid(row=0, column=1, sticky='w', padx=12)

        self._auth_btn = tk.Button(top, text='Sign in', width=10,
                                   command=self._on_auth_click)
        self._auth_btn.grid(row=0, column=2, sticky='e')

        # ── Setup notice (shown when not yet configured) ───────────────────
        self._setup_frame = self._build_setup_frame()
        self._setup_frame.grid(row=1, column=0, sticky='nsew', padx=8, pady=4)

        # ── File browser (shown when authenticated) ────────────────────────
        self._browse_frame = self._build_browse_frame()
        self._browse_frame.grid(row=1, column=0, sticky='nsew', padx=8, pady=4)

        # ── Bottom buttons ─────────────────────────────────────────────────
        btm = tk.Frame(self.win, padx=8, pady=6)
        btm.grid(row=2, column=0, sticky='ew')

        self._open_btn = tk.Button(
            btm, text='Open Files', width=14,
            command=self._on_open, state='disabled'
        )
        self._open_btn.pack(side='left', padx=(0, 4))

        self._open_folders_btn = tk.Button(
            btm, text='Open Folder(s)', width=16,
            command=self._on_open_folders, state='disabled'
        )
        self._open_folders_btn.pack(side='left', padx=(0, 6))

        self._upload_btn = tk.Button(
            btm, text='Upload Output to Drive', width=22,
            command=self._on_upload, state='disabled'
        )
        self._upload_btn.pack(side='left')

        tk.Button(btm, text='Close', width=10,
                  command=self.win.destroy).pack(side='right')

    def _build_setup_frame(self):
        """Panel shown when credentials file is missing or packages absent."""
        f = tk.Frame(self.win)

        msg = (
            "Google Drive integration requires an OAuth credentials file.\n\n"
            "Steps to set up:\n"
            "  1.  Go to  console.cloud.google.com\n"
            "  2.  Create or select a project\n"
            "  3.  Enable the Google Drive API\n"
            "  4.  Go to  APIs & Services  \u203a  Credentials\n"
            "  5.  Create an OAuth 2.0 Client ID  (type: Desktop app)\n"
            "  6.  Download the JSON file\n"
            "  7.  Rename it to  gdrive_credentials.json  and save to:\n"
            f"      {self.handler.credentials_path}\n\n"
            "Once the file is in place, click  Check Again  below, then  Sign in."
        )
        tk.Label(f, text=msg, justify='left', font=('Segoe UI', 9),
                 wraplength=680).pack(padx=20, pady=20, anchor='w')

        btn_row = tk.Frame(f)
        btn_row.pack(pady=4)
        tk.Button(btn_row, text='Open Setup Guide',
                  command=self._open_setup_guide).pack(side='left', padx=6)
        tk.Button(btn_row, text='Check Again',
                  command=self._refresh_state).pack(side='left', padx=6)

        return f

    def _build_browse_frame(self):
        """The actual file browser panel."""
        f = tk.Frame(self.win)
        f.columnconfigure(0, weight=1)
        f.rowconfigure(2, weight=1)

        # Breadcrumb / navigation row
        nav = tk.Frame(f)
        nav.grid(row=0, column=0, sticky='ew', pady=(0, 4))

        self._back_btn = tk.Button(nav, text='\u25c4 Back', width=8,
                                   command=self._nav_back, state='disabled')
        self._back_btn.pack(side='left')

        self._crumb_label = tk.Label(nav, text='My Drive', font=('Segoe UI', 9),
                                     anchor='w')
        self._crumb_label.pack(side='left', padx=8)

        tk.Button(nav, text='My Drive', width=9,
                  command=self._go_root).pack(side='right', padx=2)
        tk.Button(nav, text='Shared with Me', width=14,
                  command=self._go_shared).pack(side='right', padx=2)

        # Search row
        search_row = tk.Frame(f)
        search_row.grid(row=1, column=0, sticky='ew', pady=(0, 4))

        self._search_var = tk.StringVar()
        self._search_entry = tk.Entry(search_row, textvariable=self._search_var,
                                      width=48, font=('Segoe UI', 9))
        self._search_entry.pack(side='left', padx=(0, 6))
        self._search_entry.bind('<Return>', lambda e: self._on_search())

        tk.Button(search_row, text='Search', width=8,
                  command=self._on_search).pack(side='left')
        tk.Button(search_row, text='Clear', width=6,
                  command=self._clear_search).pack(side='left', padx=4)

        # File list
        list_frame = tk.Frame(f)
        list_frame.grid(row=2, column=0, sticky='nsew')
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        cols = ('name', 'type', 'size', 'modified')
        self._tree = ttk.Treeview(list_frame, columns=cols, show='headings',
                                   selectmode='extended')

        self._tree.heading('name',     text='Name')
        self._tree.heading('type',     text='Type')
        self._tree.heading('size',     text='Size')
        self._tree.heading('modified', text='Modified')

        self._tree.column('name',     width=330, stretch=True)
        self._tree.column('type',     width=100, stretch=False)
        self._tree.column('size',     width=70,  stretch=False, anchor='e')
        self._tree.column('modified', width=95,  stretch=False)

        vsb = ttk.Scrollbar(list_frame, orient='vertical',
                             command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)

        self._tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')

        self._tree.bind('<<TreeviewSelect>>', self._on_select)
        self._tree.bind('<Double-1>', self._on_double_click)
        self._tree.bind('<Control-a>', self._select_all)

        # Info bar
        self._info_var = tk.StringVar(value='')
        tk.Label(f, textvariable=self._info_var, font=('Segoe UI', 8),
                 fg='grey', anchor='w').grid(row=3, column=0, sticky='ew',
                                              pady=(2, 0))
        return f

    # -----------------------------------------------------------------------
    # State helpers
    # -----------------------------------------------------------------------

    def _refresh_state(self):
        """Decide which panel to show based on current auth status."""
        if not self.handler.is_available():
            self._set_status('Google API packages not installed', 'red')
            self._show_setup()
            self._auth_btn.config(state='disabled', text='Sign in')
            return

        if not self.handler.has_credentials_file():
            self._set_status('Credentials file not found', 'orange')
            self._show_setup()
            self._auth_btn.config(state='disabled', text='Sign in')
            return

        if self.handler.is_authenticated():
            email = self.handler.get_account_email() or 'Google Drive'
            self._set_status(f'Signed in as  {email}', '#2a7a2a')
            self._auth_btn.config(state='normal', text='Sign out')
            self._upload_btn.config(state='normal')
            self._show_browse()
            if not self._folder_stack and not self._search_active:
                self._go_root()
        else:
            self._set_status('Not signed in  \u2014  click Sign in to continue', 'grey')
            self._auth_btn.config(state='normal', text='Sign in')
            self._show_setup()

    def _show_setup(self):
        self._browse_frame.grid_remove()
        self._setup_frame.grid()

    def _show_browse(self):
        self._setup_frame.grid_remove()
        self._browse_frame.grid()

    def _set_status(self, text, colour='grey'):
        self._status_label.config(text=text, fg=colour)

    def _set_info(self, text):
        self._info_var.set(text)

    # -----------------------------------------------------------------------
    # Authentication
    # -----------------------------------------------------------------------

    def _on_auth_click(self):
        if self.handler.is_authenticated():
            self.handler.sign_out()
            self._current_files = []
            self._folder_stack = []
            self._search_active = False
            self._refresh_state()
        else:
            self._do_sign_in()

    def _do_sign_in(self):
        self._set_status('Opening browser for sign-in\u2026', 'grey')
        self._auth_btn.config(state='disabled')

        def worker():
            ok, err = self.handler.authenticate()
            self.win.after(0, lambda: self._sign_in_done(ok, err))

        threading.Thread(target=worker, daemon=True).start()

    def _sign_in_done(self, ok, err):
        self._auth_btn.config(state='normal')
        if ok:
            self._refresh_state()
        else:
            self._set_status('Sign-in failed', 'red')
            messagebox.showerror("Sign-in Failed", err or "Unknown error.",
                                 parent=self.win)

    # -----------------------------------------------------------------------
    # Navigation
    # -----------------------------------------------------------------------

    def _go_root(self):
        self._search_active = False
        self._search_var.set('')
        self._folder_stack = []
        self._load_folder('root', 'My Drive')

    def _go_shared(self):
        self._search_active = True
        self._search_var.set('')
        self._folder_stack = []
        self._update_breadcrumb()
        self._set_info('Loading shared files\u2026')
        self._tree.delete(*self._tree.get_children())

        def worker():
            files = self.handler.list_shared_with_me()
            self.win.after(0, lambda: self._populate_list(files))

        threading.Thread(target=worker, daemon=True).start()

    def _nav_back(self):
        """Go up one level in the folder stack."""
        if not self._folder_stack:
            return
        self._folder_stack.pop()
        if self._folder_stack:
            fid, fname = self._folder_stack.pop()
            self._load_folder(fid, fname)
        else:
            self._go_root()

    def _load_folder(self, folder_id, folder_name):
        self._folder_stack.append((folder_id, folder_name))
        self._search_active = False
        self._update_breadcrumb()
        self._set_info('Loading\u2026')
        self._tree.delete(*self._tree.get_children())
        self._open_btn.config(state='disabled')
        self._open_folders_btn.config(state='disabled')

        def worker():
            files = self.handler.list_files(folder_id)
            self.win.after(0, lambda: self._populate_list(files))

        threading.Thread(target=worker, daemon=True).start()

    def _update_breadcrumb(self):
        if self._search_active:
            crumb = 'Search results'
        elif not self._folder_stack:
            crumb = 'My Drive'
        else:
            parts = ['My Drive'] + [name for _, name in self._folder_stack[1:]]
            crumb = '  \u203a  '.join(parts)
        self._crumb_label.config(text=crumb)
        self._back_btn.config(
            state='normal' if self._folder_stack else 'disabled'
        )

    def _populate_list(self, files):
        """Refresh the Treeview with a list of Drive metadata dicts."""
        self._current_files = files
        self._tree.delete(*self._tree.get_children())

        folders = [f for f in files if f.get('mimeType') == FOLDER_MIME]
        docs    = [f for f in files if f.get('mimeType') != FOLDER_MIME]

        for item in folders + docs:
            mime = item.get('mimeType', '')
            is_folder = (mime == FOLDER_MIME)
            type_label = ('Folder' if is_folder
                          else SUPPORTED_MIMES.get(mime, 'File'))
            size_str = '' if is_folder else _human_size(item.get('size'))
            date_str = _short_date(item.get('modifiedTime', ''))

            self._tree.insert('', 'end',
                              iid=item['id'],
                              values=(item['name'], type_label, size_str, date_str))

        nf = len(folders)
        nd = len(docs)
        self._set_info(
            f"{nf + nd} items  "
            f"({nf} folder{'s' if nf != 1 else ''}, "
            f"{nd} file{'s' if nd != 1 else ''})"
        )

    # -----------------------------------------------------------------------
    # Search
    # -----------------------------------------------------------------------

    def _on_search(self):
        query = self._search_var.get().strip()
        if not query:
            return
        self._search_active = True
        self._folder_stack = []
        self._update_breadcrumb()
        self._set_info(f'Searching for \u201c{query}\u201d\u2026')
        self._tree.delete(*self._tree.get_children())
        self._open_btn.config(state='disabled')
        self._open_folders_btn.config(state='disabled')

        def worker():
            files = self.handler.search_files(query)
            self.win.after(0, lambda: self._populate_list(files))

        threading.Thread(target=worker, daemon=True).start()

    def _clear_search(self):
        self._search_var.set('')
        self._go_root()

    # -----------------------------------------------------------------------
    # List interactions
    # -----------------------------------------------------------------------

    def _select_all(self, event=None):
        """Select all items in the file list (Ctrl+A)."""
        self._tree.selection_set(self._tree.get_children())
        return 'break'

    def _on_select(self, event=None):
        sel = self._tree.selection()
        has_file = any(
            self._get_meta(iid) and
            self._get_meta(iid).get('mimeType') != FOLDER_MIME
            for iid in sel
        )
        has_folder = any(
            self._get_meta(iid) and
            self._get_meta(iid).get('mimeType') == FOLDER_MIME
            for iid in sel
        )
        self._open_btn.config(state='normal' if has_file else 'disabled')
        self._open_folders_btn.config(state='normal' if has_folder else 'disabled')

    def _on_double_click(self, event):
        sel = self._tree.selection()
        if not sel:
            return
        iid = sel[0]
        meta = self._get_meta(iid)
        if not meta:
            return
        if meta.get('mimeType') == FOLDER_MIME:
            self._load_folder(iid, meta['name'])
        else:
            self._on_open()

    def _get_meta(self, iid):
        """Return the metadata dict for a given Treeview item id."""
        return next((f for f in self._current_files if f['id'] == iid), None)

    # -----------------------------------------------------------------------
    # Open in DocAnalyser
    # -----------------------------------------------------------------------

    def _on_open(self):
        sel = self._tree.selection()
        # Snapshot metadata NOW before any downloads can mutate _current_files
        metas = [
            self._get_meta(iid) for iid in sel
            if self._get_meta(iid) and
               self._get_meta(iid).get('mimeType') != FOLDER_MIME
        ]
        if not metas:
            return
        self._open_btn.config(state='disabled')
        self._pending_downloads = len(metas)
        self._completed_paths = []
        self._failed_downloads = []
        for meta in metas:
            self._download_and_open(meta)

    def _on_open_folders(self):
        """
        Collect all files from every selected folder (non-recursive),
        then batch-download them all into DocAnalyser.
        Ctrl+click folders to select multiple before clicking this button.
        """
        sel = self._tree.selection()
        folder_metas = [
            self._get_meta(iid) for iid in sel
            if self._get_meta(iid) and
               self._get_meta(iid).get('mimeType') == FOLDER_MIME
        ]
        if not folder_metas:
            return

        self._open_folders_btn.config(state='disabled')
        self._open_btn.config(state='disabled')
        n = len(folder_metas)
        names = ', '.join(fm['name'] for fm in folder_metas)
        self._set_info(f'Listing {n} folder{"s" if n != 1 else ""}: {names}\u2026')

        def worker():
            all_metas = []
            for fm in folder_metas:
                files = self.handler.list_files(fm['id'])
                # Only include files (skip sub-folders)
                file_metas = [f for f in files if f.get('mimeType') != FOLDER_MIME]
                all_metas.extend(file_metas)
            self.win.after(0, lambda m=all_metas: self._start_folder_download(m))

        threading.Thread(target=worker, daemon=True).start()

    def _start_folder_download(self, all_metas):
        """Called on main thread once folder listing is complete."""
        if not all_metas:
            self._set_info('No files found in selected folder(s)')
            self._open_folders_btn.config(state='normal')
            return
        self._set_info(f'Downloading {len(all_metas)} file(s)\u2026')
        self._pending_downloads = len(all_metas)
        self._completed_paths = []
        self._failed_downloads = []
        for meta in all_metas:
            self._download_and_open(meta)

    # MIME type -> file extension fallback table
    _MIME_TO_EXT = {
        'application/pdf':                  '.pdf',
        'application/msword':               '.doc',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':       '.xlsx',
        'application/vnd.openxmlformats-officedocument.presentationml.presentation': '.pptx',
        'application/vnd.google-apps.document':     '.docx',
        'application/vnd.google-apps.spreadsheet':  '.xlsx',
        'application/vnd.google-apps.presentation': '.pptx',
        'text/plain':  '.txt',
        'text/csv':    '.csv',
        'audio/mpeg':  '.mp3',
        'audio/mp3':   '.mp3',
        'audio/wav':   '.wav',
        'audio/x-wav': '.wav',
        'audio/x-m4a': '.m4a',
        'audio/mp4':   '.m4a',
        'video/mp4':   '.mp4',
    }

    def _download_and_open(self, meta):
        """Download a single file given its full metadata dict."""
        file_id = meta['id']
        name    = meta.get('name', f'gdrive_{file_id}')
        mime    = meta.get('mimeType', '')

        # Determine extension: prefer filename, fall back to MIME map, then .bin
        ext = os.path.splitext(name)[1]
        if not ext:
            ext = self._MIME_TO_EXT.get(mime, '.bin')
            name = name + ext

        # Use a per-file temp subfolder so the file keeps its original name.
        subdir = os.path.join(tempfile.gettempdir(), f'da_gdrive_{file_id}')
        os.makedirs(subdir, exist_ok=True)
        dest = os.path.join(subdir, name)

        def worker():
            # Semaphore caps concurrent downloads at 5 to avoid rate-limiting
            with self._download_semaphore:
                ok, result = self.handler.download_file(file_id, dest, mime_type=mime)
            self.win.after(0, lambda: self._download_done(ok, result, name))

        threading.Thread(target=worker, daemon=True).start()

    def _download_done(self, ok, result, name):
        """Called on the main thread when each download completes."""
        self._pending_downloads = max(0, self._pending_downloads - 1)

        if ok:
            self._completed_paths.append(result)
            done = len(self._completed_paths)
            remaining = self._pending_downloads
            self._set_info(f'Downloaded {done}  \u2014  {remaining} remaining\u2026'
                           if remaining else f'Downloaded {done}  \u2014  loading\u2026')
        else:
            self._failed_downloads.append(name)

        if self._pending_downloads == 0:
            # All downloads finished — load everything in one batch call
            self._open_btn.config(state='normal')
            self._open_folders_btn.config(state='normal')
            paths  = self._completed_paths[:]
            failed = self._failed_downloads[:]

            if paths:
                if len(paths) == 1:
                    if hasattr(self.app, '_load_downloaded_gdrive_file'):
                        self.app._load_downloaded_gdrive_file(paths[0])
                else:
                    if hasattr(self.app, '_process_multiple_inputs'):
                        self.app._process_multiple_inputs(paths)
                    elif hasattr(self.app, '_load_downloaded_gdrive_file'):
                        for p in paths:
                            self.app._load_downloaded_gdrive_file(p)
                n = len(paths)
                self._set_info(f'\u2714  {n} file{"s" if n != 1 else ""}  loaded into DocAnalyser')
                self.win.after(3000, lambda: self._set_info(''))

            if failed:
                names = '\n'.join(f'  \u2022  {n}' for n in failed)
                messagebox.showwarning(
                    f'{len(failed)} Download(s) Failed',
                    f'The following files could not be downloaded:\n\n{names}\n\n'
                    'You can try selecting them again.',
                    parent=self.win
                )

    # -----------------------------------------------------------------------
    # Upload output
    # -----------------------------------------------------------------------

    def _on_upload(self):
        """Upload the current DocAnalyser output text to Google Drive."""
        output = ''
        if hasattr(self.app, 'output_text'):
            output = self.app.output_text.get('1.0', tk.END).strip()

        if not output:
            messagebox.showinfo(
                "Nothing to Upload",
                "The output panel is empty.\n\n"
                "Process a document first, then use Upload Output to Drive "
                "to save the result.",
                parent=self.win
            )
            return

        default_name = 'DocAnalyser_output.txt'
        if hasattr(self.app, 'file_path_var'):
            src = self.app.file_path_var.get()
            if src:
                base = os.path.splitext(os.path.basename(src))[0]
                default_name = f'{base}_output.txt'

        folder_id = self._folder_stack[-1][0] if self._folder_stack else 'root'

        self._set_info(f'Uploading {default_name}\u2026')
        self._upload_btn.config(state='disabled')

        def worker():
            tmp = os.path.join(tempfile.gettempdir(), default_name)
            try:
                with open(tmp, 'w', encoding='utf-8') as fh:
                    fh.write(output)
                ok, _fid, err = self.handler.upload_file(
                    tmp, default_name, folder_id
                )
                self.win.after(0, lambda: self._upload_done(ok, default_name, err))
            except Exception as e:
                self.win.after(0, lambda: self._upload_done(False, default_name, str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _upload_done(self, ok, name, err):
        self._upload_btn.config(state='normal')
        if ok:
            self._set_info(f'\u2714  {name}  uploaded successfully')
            if self._folder_stack:
                fid, fname = self._folder_stack.pop()
                self._load_folder(fid, fname)
        else:
            self._set_info('')
            messagebox.showerror(
                "Upload Failed",
                f"Could not upload  {name}:\n\n{err}",
                parent=self.win
            )

    # -----------------------------------------------------------------------
    # Misc
    # -----------------------------------------------------------------------

    def _open_setup_guide(self):
        import webbrowser
        webbrowser.open(
            'https://developers.google.com/drive/api/quickstart/python'
        )


# ---------------------------------------------------------------------------
# Convenience entry point
# ---------------------------------------------------------------------------

def open_google_drive_dialog(parent, app):
    """Create and show the Google Drive dialog. Returns the dialog instance."""
    return GoogleDriveDialog(parent, app)
