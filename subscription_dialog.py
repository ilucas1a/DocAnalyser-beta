"""
subscription_dialog.py — Subscriptions Manager UI

Provides a Tkinter dialog for adding, editing, and running subscriptions
(YouTube channels, Substack publications, RSS feeds).

The "Check Now" button runs the subscription check in a background thread
and streams progress updates back to the UI via a thread-safe queue.

Called by:  Main.py  (open_subscriptions_dialog)
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import queue
import logging

logger = logging.getLogger(__name__)

# Subscription type labels  →  internal type string
SUB_TYPES = {
    "YouTube Channel":      "youtube_channel",
    "Substack Publication": "substack",
    "RSS Feed":             "rss",
}
TYPE_LABELS = {v: k for k, v in SUB_TYPES.items()}   # reverse lookup


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def open_subscriptions_dialog(parent, app):
    """Open (or raise) the Subscriptions Manager dialog."""
    dialog = SubscriptionDialog(parent, app)
    dialog.window.focus_set()
    return dialog


# ─────────────────────────────────────────────────────────────────────────────
# Main dialog class
# ─────────────────────────────────────────────────────────────────────────────

class SubscriptionDialog:
    """
    Subscriptions Manager window.

    Layout:
      ┌──────────────────────────────────────────────────────────────────┐
      │ [Subscriptions list]  │  [Detail / edit panel]                   │
      │                       │                                          │
      │ [Add][Remove][Rename] │                          [Save Changes]  │
      │ [Duplicate]           │                                          │
      ├───────────────────────┴──────────────────────────────────────────┤
      │  [Check All Now]  [Check Selected]  [Cancel]   ████░ status      │
      └──────────────────────────────────────────────────────────────────┘
    """

    def __init__(self, parent, app):
        self.app      = app
        self.parent   = parent
        self._stop    = [False]
        self._queue   = queue.Queue()
        self._running = False
        self._current_idx = None  # index of the subscription currently shown in the form

        self.window = tk.Toplevel(parent)
        self.window.title("Subscriptions")
        self.window.geometry("820x620")
        self.window.minsize(720, 520)
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()
        self._load_list()
        self._poll_queue()

    # ──────────────────────────────────────────────────────────────────────
    # UI construction
    # ──────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        outer = ttk.Frame(self.window, padding=8)
        outer.pack(fill=tk.BOTH, expand=True)

        paned = ttk.PanedWindow(outer, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # ── Left panel ────────────────────────────────────────────────────
        left = ttk.Frame(paned, width=230)
        left.pack_propagate(False)
        paned.add(left, weight=1)

        ttk.Label(left, text="Subscriptions", font=("Arial", 9, "bold")).pack(anchor=tk.W)

        list_frame = ttk.Frame(left)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(4, 4))

        self.sub_listbox = tk.Listbox(
            list_frame, selectmode=tk.EXTENDED,
            activestyle="none", font=("Arial", 9),
        )
        sb = ttk.Scrollbar(list_frame, orient=tk.VERTICAL,
                           command=self.sub_listbox.yview)
        self.sub_listbox.configure(yscrollcommand=sb.set)
        self.sub_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        self.sub_listbox.bind("<<ListboxSelect>>", self._on_list_select)
        self.sub_listbox.bind("<Double-Button-1>", lambda e: self._rename())

        btn_row1 = ttk.Frame(left)
        btn_row1.pack(fill=tk.X, pady=(0, 2))
        ttk.Button(btn_row1, text="Add",    width=7, command=self._add_new).pack(side=tk.LEFT, padx=(0, 2))
        ttk.Button(btn_row1, text="Remove", width=7, command=self._remove).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_row1, text="Rename", width=7, command=self._rename).pack(side=tk.LEFT, padx=2)

        btn_row2 = ttk.Frame(left)
        btn_row2.pack(fill=tk.X)
        ttk.Button(btn_row2, text="Duplicate", width=10, command=self._duplicate).pack(side=tk.LEFT)
        ttk.Button(btn_row2, text="Reset History", width=13, command=self._reset_history).pack(side=tk.LEFT, padx=(4, 0))

        # ── Right panel ───────────────────────────────────────────────────
        right = ttk.Frame(paned, padding=(8, 0, 0, 0))
        paned.add(right, weight=3)
        self._build_detail_panel(right)

        # ── Bottom bar ────────────────────────────────────────────────────
        ttk.Separator(outer, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(6, 4))

        bottom = ttk.Frame(outer)
        bottom.pack(fill=tk.X)

        self.check_all_btn = ttk.Button(bottom, text="Check All Now",   width=16, command=self._check_all)
        self.check_all_btn.pack(side=tk.LEFT, padx=(0, 4))

        self.check_sel_btn = ttk.Button(bottom, text="Check Selected",  width=16, command=self._check_selected)
        self.check_sel_btn.pack(side=tk.LEFT, padx=(0, 4))

        self.cancel_btn = ttk.Button(bottom, text="Cancel Check", width=14,
                                     command=self._cancel_check, state=tk.DISABLED)
        self.cancel_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.digest_btn = ttk.Button(bottom, text="Generate Digest", width=16,
                                     command=self._open_digest_dialog)
        self.digest_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.progress_bar = ttk.Progressbar(bottom, mode="indeterminate", length=120)
        self.progress_bar.pack(side=tk.LEFT, padx=(0, 8))

        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(bottom, textvariable=self.status_var,
                  font=("Arial", 8), foreground="#444",
                  wraplength=280, justify=tk.LEFT).pack(side=tk.LEFT, fill=tk.X, expand=True)

    def _build_detail_panel(self, parent):
        self.detail_frame = ttk.LabelFrame(parent, text="Subscription Details", padding=8)
        self.detail_frame.pack(fill=tk.BOTH, expand=True)

        self.no_sel_label = ttk.Label(
            self.detail_frame,
            text="Select a subscription on the left, or click Add to create one.",
            foreground="#888",
        )
        self.no_sel_label.pack(expand=True)

        self.form_frame = ttk.Frame(self.detail_frame)
        self._build_form(self.form_frame)

    def _build_form(self, parent):
        def lbl(text, row_idx):
            ttk.Label(parent, text=text, width=14, anchor=tk.E).grid(
                row=row_idx, column=0, sticky=tk.E, padx=(0, 6), pady=3)

        # Name
        lbl("Name:", 0)
        self.name_var = tk.StringVar()
        ttk.Entry(parent, textvariable=self.name_var, width=38).grid(
            row=0, column=1, columnspan=2, sticky=tk.W, pady=3)

        # Type
        lbl("Type:", 1)
        self.type_var = tk.StringVar(value="YouTube Channel")
        type_combo = ttk.Combobox(parent, textvariable=self.type_var,
                                  values=list(SUB_TYPES.keys()), state="readonly", width=24)
        type_combo.grid(row=1, column=1, sticky=tk.W, pady=3)
        type_combo.bind("<<ComboboxSelected>>", self._on_type_change)

        # URL
        lbl("URL:", 2)
        url_frame = ttk.Frame(parent)
        url_frame.grid(row=2, column=1, columnspan=2, sticky=tk.EW, pady=3)
        self.url_var = tk.StringVar()
        ttk.Entry(url_frame, textvariable=self.url_var, width=32).pack(
            side=tk.LEFT, fill=tk.X, expand=True)
        self.resolve_btn = ttk.Button(url_frame, text="Resolve", width=9,
                                      command=self._resolve_channel)
        self.resolve_btn.pack(side=tk.LEFT, padx=(4, 0))

        # Channel ID
        lbl("Channel ID:", 3)
        self.channel_id_var = tk.StringVar()
        self.channel_id_entry = ttk.Entry(parent, textvariable=self.channel_id_var,
                                          width=28, state="readonly")
        self.channel_id_entry.grid(row=3, column=1, sticky=tk.W, pady=3)

        # Min duration
        lbl("Min duration:", 4)
        dur_frame = ttk.Frame(parent)
        dur_frame.grid(row=4, column=1, sticky=tk.W, pady=3)
        self.min_dur_var = tk.IntVar(value=25)
        self.min_dur_spin = ttk.Spinbox(dur_frame, textvariable=self.min_dur_var,
                                        from_=0, to=300, width=6)
        self.min_dur_spin.pack(side=tk.LEFT)
        ttk.Label(dur_frame, text=" minutes  (0 = no filter, YouTube only)",
                  foreground="#666", font=("Arial", 8)).pack(side=tk.LEFT)

        # Look-back window
        lbl("Look back:", 5)
        look_frame = ttk.Frame(parent)
        look_frame.grid(row=5, column=1, sticky=tk.W, pady=3)
        self.look_back_var = tk.IntVar(value=48)
        ttk.Spinbox(look_frame, textvariable=self.look_back_var,
                    from_=0, to=8760, width=6).pack(side=tk.LEFT)
        ttk.Label(look_frame, text=" hours  (0 = all new since last check)",
                  foreground="#666", font=("Arial", 8)).pack(side=tk.LEFT)

        # ── Prompt row ─────────────────────────────────────────────────────
        lbl("Prompt:", 6)
        prompt_frame = ttk.Frame(parent)
        prompt_frame.grid(row=6, column=1, columnspan=2, sticky=tk.EW, pady=3)

        self.prompt_var = tk.StringVar()
        self.prompt_combo = ttk.Combobox(prompt_frame, textvariable=self.prompt_var,
                                         width=24, state="readonly")
        self.prompt_combo.pack(side=tk.LEFT)
        self.prompt_combo.bind("<<ComboboxSelected>>", self._on_prompt_select)

        ttk.Button(prompt_frame, text="Prompts Library", width=15,
                   command=self._open_prompts_library).pack(side=tk.LEFT, padx=(6, 0))

        # ── Prompt text ────────────────────────────────────────────────────
        lbl("Prompt text:", 7)
        text_frame = ttk.Frame(parent)
        text_frame.grid(row=7, column=1, columnspan=2, sticky=tk.NSEW, pady=3)

        self.prompt_text_widget = tk.Text(text_frame, height=6, width=38,
                                          wrap=tk.WORD, font=("Arial", 9),
                                          relief=tk.SUNKEN, borderwidth=1)
        pt_scroll = ttk.Scrollbar(text_frame, orient=tk.VERTICAL,
                                  command=self.prompt_text_widget.yview)
        self.prompt_text_widget.configure(yscrollcommand=pt_scroll.set)
        self.prompt_text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        pt_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Enabled
        lbl("", 7)
        self.enabled_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(parent, text="Enabled", variable=self.enabled_var).grid(
            row=7, column=1, sticky=tk.W, pady=3)

        # Last checked
        lbl("Last checked:", 8)
        self.last_checked_var = tk.StringVar(value="Never")
        ttk.Label(parent, textvariable=self.last_checked_var,
                  foreground="#555", font=("Arial", 8)).grid(
            row=8, column=1, sticky=tk.W, pady=3)

        # ── Scheduling (reserved) ──────────────────────────────────────────
        sched_lf = ttk.LabelFrame(parent, text="Scheduling (coming soon)", padding=4)
        sched_lf.grid(row=9, column=0, columnspan=3, sticky=tk.EW, pady=(8, 2))

        self.sched_enabled_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(sched_lf, text="Enable automatic scheduled checking",
                        variable=self.sched_enabled_var, state=tk.DISABLED).pack(anchor=tk.W)

        sched_inner = ttk.Frame(sched_lf)
        sched_inner.pack(anchor=tk.W, padx=16)
        ttk.Label(sched_inner, text="Check every").pack(side=tk.LEFT)
        self.interval_var = tk.IntVar(value=6)
        ttk.Spinbox(sched_inner, textvariable=self.interval_var,
                    from_=1, to=72, width=4, state=tk.DISABLED).pack(side=tk.LEFT, padx=4)
        ttk.Label(sched_inner, text="hours").pack(side=tk.LEFT)
        ttk.Label(sched_lf, text="Scheduled checking will be available in a future update.",
                  foreground="#999", font=("Arial", 8)).pack(anchor=tk.W)

        # Save button
        save_row = ttk.Frame(parent)
        save_row.grid(row=10, column=0, columnspan=3, sticky=tk.E, pady=(8, 0))
        self.save_btn = ttk.Button(save_row, text="Save Changes", width=14,
                                   command=self._save_current)
        self.save_btn.pack(side=tk.RIGHT)

        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(7, weight=1)

    # ──────────────────────────────────────────────────────────────────────
    # List management
    # ──────────────────────────────────────────────────────────────────────

    def _load_list(self):
        from subscription_manager import load_subscriptions
        self._subs = load_subscriptions()
        self._current_idx = None
        self.sub_listbox.delete(0, tk.END)
        for s in self._subs:
            marker = "" if s.get("enabled", True) else "  [off]"
            self.sub_listbox.insert(tk.END, s.get("name", "(unnamed)") + marker)
        self._show_placeholder()

    def _selected_index(self):
        sel = self.sub_listbox.curselection()
        return sel[0] if sel else None

    def _selected_sub(self):
        idx = self._selected_index()
        return self._subs[idx] if idx is not None and idx < len(self._subs) else None

    # ──────────────────────────────────────────────────────────────────────
    # Form show / hide
    # ──────────────────────────────────────────────────────────────────────

    def _show_placeholder(self):
        self.form_frame.pack_forget()
        self.no_sel_label.pack(expand=True)

    def _show_form(self):
        self.no_sel_label.pack_forget()
        self.form_frame.pack(fill=tk.BOTH, expand=True)

    # ──────────────────────────────────────────────────────────────────────
    # List callbacks
    # ──────────────────────────────────────────────────────────────────────

    def _on_list_select(self, _event=None):
        # Guard: ignore spurious empty-selection events (e.g. fired when the
        # prompt combobox dropdown steals focus from the listbox).
        sel = self.sub_listbox.curselection()
        if not sel:
            return
        # With EXTENDED mode use the last item in curselection() — that is
        # always the item the user just clicked (single click, Ctrl+click, or
        # the anchor of a Shift+click range).  tk.ACTIVE lags behind mouse
        # clicks in EXTENDED mode and causes the wrong item to be displayed.
        idx = sel[-1]
        # If the form already shows this item, do nothing — prevents the form
        # being wiped when the prompt combobox steals focus and fires a spurious
        # <<ListboxSelect>> with the same selection still in place.
        if idx == self._current_idx and self._current_idx is not None:
            return
        self._current_idx = idx
        sub = self._subs[idx] if idx < len(self._subs) else None
        if sub is None:
            self._show_placeholder()
            return
        self._show_form()
        self._populate_form(sub)

    def _populate_form(self, sub: dict):
        self.name_var.set(sub.get("name", ""))
        self.type_var.set(TYPE_LABELS.get(sub.get("type", "youtube_channel"), "YouTube Channel"))
        self.url_var.set(sub.get("url", ""))
        self.channel_id_var.set(sub.get("channel_id", ""))
        self.min_dur_var.set(sub.get("min_duration", 25))
        self.look_back_var.set(sub.get("look_back_hours", 48))
        self.enabled_var.set(sub.get("enabled", True))
        self.sched_enabled_var.set(sub.get("schedule_enabled", False))
        self.interval_var.set(sub.get("check_interval_hours", 6))

        lc = sub.get("last_checked")
        if lc:
            try:
                import datetime
                dt = datetime.datetime.fromisoformat(lc)
                self.last_checked_var.set(dt.strftime("%d %b %Y  %H:%M"))
            except Exception:
                self.last_checked_var.set(lc)
        else:
            self.last_checked_var.set("Never")

        self._refresh_prompt_combo()
        self.prompt_var.set(sub.get("prompt_name", ""))

        self.prompt_text_widget.delete("1.0", tk.END)
        pt = sub.get("prompt_text", "")
        if pt:
            self.prompt_text_widget.insert("1.0", pt)

        self._on_type_change()

    def _collect_form(self) -> dict:
        return {
            "name":                  self.name_var.get().strip(),
            "type":                  SUB_TYPES.get(self.type_var.get(), "youtube_channel"),
            "url":                   self.url_var.get().strip(),
            "channel_id":            self.channel_id_var.get().strip(),
            "min_duration":          self.min_dur_var.get(),
            "look_back_hours":       self.look_back_var.get(),
            "enabled":               self.enabled_var.get(),
            "prompt_name":           self.prompt_var.get().strip(),
            "prompt_text":           self.prompt_text_widget.get("1.0", tk.END).strip(),
            "schedule_enabled":      self.sched_enabled_var.get(),
            "check_interval_hours":  self.interval_var.get(),
        }

    # ──────────────────────────────────────────────────────────────────────
    # Type change
    # ──────────────────────────────────────────────────────────────────────

    def _on_type_change(self, _event=None):
        is_yt = (self.type_var.get() == "YouTube Channel")
        self.resolve_btn.config(state=tk.NORMAL if is_yt else tk.DISABLED)
        self.min_dur_spin.config(state=tk.NORMAL if is_yt else tk.DISABLED)
        if is_yt:
            self.channel_id_entry.grid()
        else:
            self.channel_id_entry.grid_remove()

    # ──────────────────────────────────────────────────────────────────────
    # Prompt helpers
    # ──────────────────────────────────────────────────────────────────────

    def _refresh_prompt_combo(self):
        """Reload prompt names into the combo dropdown."""
        try:
            from config_manager import load_prompts
            raw = load_prompts()
            names = []
            if isinstance(raw, list):
                names = [p["name"] for p in raw if isinstance(p, dict) and p.get("name")]
            else:
                def _walk(node):
                    if isinstance(node, dict):
                        if node.get("type") == "item" and node.get("name"):
                            names.append(node["name"])
                        for child in (list(node.get("children", {}).values()) +
                                      list(node.get("items", {}).values())):
                            _walk(child)
                for folder in raw.get("folders", {}).values():
                    _walk(folder)
            self.prompt_combo["values"] = [n for n in names if n]
        except Exception as exc:
            logger.warning(f"_refresh_prompt_combo: {exc}")
            self.prompt_combo["values"] = []

    def _on_prompt_select(self, _event=None):
        """Combo selection → load prompt text."""
        self._load_prompt_by_name(self.prompt_var.get())

    def _load_prompt_by_name(self, name: str):
        if not name:
            return
        try:
            from config_manager import load_prompts
            raw = load_prompts()
            prompt_text = None
            if isinstance(raw, list):
                for p in raw:
                    if isinstance(p, dict) and p.get("name") == name:
                        prompt_text = p.get("text", "")
                        break
            else:
                def _find(node):
                    if isinstance(node, dict):
                        if node.get("type") == "item" and node.get("name") == name:
                            return node.get("content", node.get("text", ""))
                        for child in (list(node.get("children", {}).values()) +
                                      list(node.get("items", {}).values())):
                            res = _find(child)
                            if res is not None:
                                return res
                    return None
                for folder in raw.get("folders", {}).values():
                    prompt_text = _find(folder)
                    if prompt_text is not None:
                        break
            if prompt_text is not None:
                self.prompt_text_widget.delete("1.0", tk.END)
                self.prompt_text_widget.insert("1.0", prompt_text)
        except Exception as exc:
            logger.warning(f"_load_prompt_by_name: {exc}")

    def _open_prompts_library(self):
        """Open the Prompts Library tree picker; on selection fill name + text."""
        def _on_chosen(name: str, text: str):
            self.prompt_var.set(name)
            self.prompt_text_widget.delete("1.0", tk.END)
            self.prompt_text_widget.insert("1.0", text)
            self.window.lift()

        # Strategy 1: dedicated selection function in prompt_tree_manager
        try:
            from prompt_tree_manager import open_prompt_tree_for_selection
            open_prompt_tree_for_selection(self.window, _on_chosen)
            return
        except (ImportError, AttributeError):
            pass

        # Strategy 2: hijack the app's set_prompt_from_library callback
        try:
            original_cb = getattr(self.app, "set_prompt_from_library", None)

            def _intercept(name, text):
                _on_chosen(name, text)
                if original_cb:
                    self.app.set_prompt_from_library = original_cb

            self.app.set_prompt_from_library = _intercept
            self.app.open_prompt_manager()
            return
        except Exception as exc:
            logger.warning(f"_open_prompts_library strategy 2: {exc}")

        # Strategy 3: refresh combo and ask user to pick from it
        self._refresh_prompt_combo()
        messagebox.showinfo(
            "Prompts Library",
            "The full library picker is not available in this context.\n\n"
            "The dropdown above has been refreshed — please select your prompt from it.",
            parent=self.window,
        )

    # ──────────────────────────────────────────────────────────────────────
    # Resolve YouTube channel
    # ──────────────────────────────────────────────────────────────────────

    def _resolve_channel(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("Resolve Channel",
                                   "Please enter a YouTube channel URL first.",
                                   parent=self.window)
            return
        self.resolve_btn.config(state=tk.DISABLED)
        self.status_var.set("Resolving channel ID…")

        def _worker():
            from subscription_manager import resolve_youtube_channel
            ch_id = resolve_youtube_channel(url, status_cb=lambda m: self._enqueue("status", m))
            self._enqueue("resolve_done", ch_id or "")

        threading.Thread(target=_worker, daemon=True).start()

    # ──────────────────────────────────────────────────────────────────────
    # CRUD
    # ──────────────────────────────────────────────────────────────────────

    def _add_new(self):
        from subscription_manager import default_subscription, add_subscription
        sub = default_subscription()
        sub["name"] = "New Subscription"
        add_subscription(sub)
        self._load_list()
        last = len(self._subs) - 1
        self.sub_listbox.selection_clear(0, tk.END)
        self.sub_listbox.selection_set(last)
        self.sub_listbox.see(last)
        self._on_list_select()
        self.window.after(100, self._rename)   # immediately prompt for a name

    def _rename(self):
        """Small inline dialog to rename the selected subscription."""
        sub = self._selected_sub()
        if sub is None:
            messagebox.showinfo("Rename", "Please select a subscription first.",
                                parent=self.window)
            return

        dlg = tk.Toplevel(self.window)
        dlg.title("Rename Subscription")
        dlg.geometry("340x110")
        dlg.resizable(False, False)
        dlg.transient(self.window)
        dlg.grab_set()

        ttk.Label(dlg, text="New name:").pack(anchor=tk.W, padx=12, pady=(12, 2))
        name_var = tk.StringVar(value=sub.get("name", ""))
        entry = ttk.Entry(dlg, textvariable=name_var, width=38)
        entry.pack(padx=12, pady=(0, 8))
        entry.select_range(0, tk.END)
        entry.focus_set()

        def _apply():
            new_name = name_var.get().strip()
            if not new_name:
                messagebox.showwarning("Rename", "Name cannot be empty.", parent=dlg)
                return
            self._auto_save()  # preserve URL/channel/prompt before reload
            from subscription_manager import update_subscription
            update_subscription(sub["id"], {"name": new_name})
            self.name_var.set(new_name)          # keep form in sync
            saved_idx = self._selected_index()
            self._load_list()
            if saved_idx is not None and saved_idx < len(self._subs):
                self.sub_listbox.selection_set(saved_idx)
                self._on_list_select()
            self.status_var.set(f"Renamed to: {new_name}")
            dlg.destroy()

        btn_row = ttk.Frame(dlg)
        btn_row.pack(fill=tk.X, padx=12)
        ttk.Button(btn_row, text="OK",     width=8, command=_apply).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(btn_row, text="Cancel", width=8, command=dlg.destroy).pack(side=tk.LEFT)

        entry.bind("<Return>", lambda e: _apply())
        entry.bind("<Escape>", lambda e: dlg.destroy())

    def _remove(self):
        sub = self._selected_sub()
        if sub is None:
            return
        name = sub.get("name", "this subscription")
        if not messagebox.askyesno(
            "Remove Subscription",
            f"Remove '{name}'?\n\nThis will not delete any already-processed documents.",
            parent=self.window,
        ):
            return
        from subscription_manager import remove_subscription
        remove_subscription(sub["id"])
        self._load_list()

    def _duplicate(self):
        sub = self._selected_sub()
        if sub is None:
            return
        import copy
        from subscription_manager import add_subscription
        new_sub = copy.deepcopy(sub)
        new_sub["id"]           = ""
        new_sub["name"]         = sub.get("name", "") + " (copy)"
        new_sub["last_checked"] = None
        new_sub["seen_guids"]   = []
        add_subscription(new_sub)
        self._load_list()

    def _reset_history(self):
        """Clear seen_guids for the selected subscription so all items are retried."""
        sub = self._selected_sub()
        if sub is None:
            messagebox.showinfo("Reset History",
                                "Please select a subscription first.",
                                parent=self.window)
            return
        name  = sub.get("name", "this subscription")
        count = len(sub.get("seen_guids", []))
        if not messagebox.askyesno(
            "Reset Check History",
            f"Clear the check history for '{name}'?\n\n"
            f"This will remove {count} recorded item ID(s), so the next check "
            f"will treat recent videos as new and process them again.\n\n"
            "Already-saved documents in the library will not be affected.",
            parent=self.window,
        ):
            return
        from subscription_manager import update_subscription
        update_subscription(sub["id"], {"seen_guids": [], "last_checked": None})
        # Update in-memory copy
        saved_idx = self._selected_index()
        if saved_idx is not None and saved_idx < len(self._subs):
            self._subs[saved_idx]["seen_guids"]   = []
            self._subs[saved_idx]["last_checked"] = None
        self.last_checked_var.set("Never")
        self._current_idx = None   # force form repopulate on next select
        self.status_var.set(f"History cleared for: {name}")
        messagebox.showinfo("History Cleared",
                            f"Check history cleared for '{name}'.\n\n"
                            "The next Check will re-process recent items.",
                            parent=self.window)

    def _auto_save(self):
        """Silently save the current form to disk without validation popups.
        Called before any operation that reloads the list from disk."""
        sub = self._selected_sub()
        if sub is None:
            return
        values = self._collect_form()
        if not values.get("name"):
            return
        from subscription_manager import update_subscription
        update_subscription(sub["id"], values)

    def _save_current(self):
        sub = self._selected_sub()
        if sub is None:
            messagebox.showwarning("Save", "Please select a subscription first.",
                                   parent=self.window)
            return
        values = self._collect_form()
        if not values["name"]:
            messagebox.showwarning("Save", "Please enter a name.",
                                   parent=self.window)
            return

        # Update in-memory list directly (same pattern as prompt_manager)
        saved_idx = self._selected_index()
        if saved_idx is not None and saved_idx < len(self._subs):
            self._subs[saved_idx].update(values)

        # Write the whole list to disk in one step
        from subscription_manager import save_subscriptions
        ok = save_subscriptions(self._subs)

        if ok:
            # Refresh the listbox label in case the name changed
            if saved_idx is not None and saved_idx < len(self._subs):
                marker = "" if values.get("enabled", True) else "  [off]"
                self.sub_listbox.delete(saved_idx)
                self.sub_listbox.insert(saved_idx, values["name"] + marker)
                self.sub_listbox.selection_set(saved_idx)
            self.status_var.set(f"Saved: {values['name']}")
            messagebox.showinfo("Saved",
                                f"'{values['name']}' saved successfully.",
                                parent=self.window)
        else:
            messagebox.showerror("Save Failed",
                                 "Could not write to disk.\n\nCheck that DocAnalyser "
                                 "has write access to its data folder.",
                                 parent=self.window)

    def _flash_save_button(self):
        """Flash the Save button to confirm success (cosmetic only)."""
        try:
            self.save_btn.config(text="✓ Saved", state=tk.DISABLED)
            self.window.after(
                2000,
                lambda: self.save_btn.config(text="Save Changes", state=tk.NORMAL)
            )
        except Exception:
            pass

    # ──────────────────────────────────────────────────────────────────────
    # Check Now
    # ──────────────────────────────────────────────────────────────────────

    def _check_all(self):
        self._run_check(selected_only=False)

    def _check_selected(self):
        sel = self.sub_listbox.curselection()
        if not sel:
            messagebox.showinfo("Check Selected",
                                "Please select one or more subscriptions first.", parent=self.window)
            return
        self._run_check(selected_indices=list(sel))

    def _cancel_check(self):
        self._stop[0] = True
        self.status_var.set("Cancelling…")

    def _run_check(self, selected_only: bool = False, selected_indices: list = None):
        if self._running:
            return

        config = getattr(self.app, "config", {})

        if selected_indices is not None:
            subs_to_check = [self._subs[i] for i in selected_indices if i < len(self._subs)]
        elif selected_only:
            sub = self._selected_sub()
            if not sub:
                return
            subs_to_check = [sub]
        else:
            from subscription_manager import load_subscriptions
            subs_to_check = [s for s in load_subscriptions() if s.get("enabled", True)]

        if not subs_to_check:
            self.status_var.set("No enabled subscriptions to check.")
            return

        self._auto_save()  # ensure URL/channel/prompt are on disk before check
        self._running = True
        self._stop[0] = False
        self.check_all_btn.config(state=tk.DISABLED)
        self.check_sel_btn.config(state=tk.DISABLED)
        self.cancel_btn.config(state=tk.NORMAL)
        self.progress_bar.start(12)

        def _worker():
            from subscription_manager import check_subscription, check_all_subscriptions, update_subscription
            import datetime

            def status_cb(msg):  self._enqueue("status", msg)
            def item_cb(t, ok):  self._enqueue("item_done", f"{'OK' if ok else 'FAIL'}  {t}")
            def sub_cb(n, r):
                self._enqueue("status",
                    f"{n}: {r['processed']} processed, {r['skipped']} skipped, {r['errors']} error(s)")

            all_errors = []   # collect error messages across all subs

            try:
                if selected_indices is not None or selected_only:
                    # Run each selected subscription in sequence, persisting state after each
                    totals = {"processed": 0, "skipped": 0, "errors": 0}
                    total_subs = len(subs_to_check)
                    for sub_num, sub in enumerate(subs_to_check, 1):
                        if self._stop[0]:
                            break
                        sub_name = sub.get('name', '?')
                        prefix = f"[{sub_num}/{total_subs}] {sub_name}: "
                        self._enqueue("status", f"{prefix}Starting…")

                        def make_prefixed_cb(pfx):
                            def _cb(msg): self._enqueue("status", pfx + msg.lstrip())
                            return _cb

                        result = check_subscription(sub, config,
                                                   status_cb=make_prefixed_cb(prefix),
                                                   item_done_cb=item_cb, stop_flag=self._stop)
                        new_guids = result.get("new_seen_guids", [])
                        if new_guids:
                            update_subscription(sub["id"], {
                                "seen_guids":   list(set(sub.get("seen_guids", []) + new_guids)),
                                "last_checked": datetime.datetime.now().isoformat(),
                            })
                        totals["processed"] += result["processed"]
                        totals["skipped"]   += result["skipped"]
                        totals["errors"]    += result["errors"]
                        all_errors.extend(result.get("error_messages", []))
                        sub_cb(sub.get("name", "?"), result)
                    msg = (f"Done — {totals['processed']} processed, "
                           f"{totals['skipped']} skipped, {totals['errors']} error(s).")
                else:
                    t = check_all_subscriptions(config, status_cb=status_cb,
                                                item_done_cb=item_cb, sub_done_cb=sub_cb,
                                                stop_flag=self._stop)
                    msg = (f"Done — {t['total_processed']} processed, "
                           f"{t['total_skipped']} skipped, {t['total_errors']} error(s).")
            except Exception as exc:
                msg = f"Error: {exc}"
                logger.error(f"_run_check: {exc}", exc_info=True)

            self._enqueue("done", (msg, all_errors))

        threading.Thread(target=_worker, daemon=True).start()

    # ──────────────────────────────────────────────────────────────────────
    # Queue polling
    # ──────────────────────────────────────────────────────────────────────

    def _enqueue(self, msg_type: str, payload=None):
        self._queue.put((msg_type, payload))

    def _poll_queue(self):
        try:
            while True:
                msg_type, payload = self._queue.get_nowait()
                if msg_type in ("status", "item_done"):
                    self.status_var.set(str(payload))
                elif msg_type == "resolve_done":
                    if payload:
                        self.channel_id_var.set(payload)
                        self.status_var.set(f"Channel ID resolved: {payload}")
                    else:
                        self.status_var.set("Could not resolve channel ID — check the URL.")
                    self.resolve_btn.config(state=tk.NORMAL)
                elif msg_type == "done":
                    self._running = False
                    self.progress_bar.stop()
                    self.check_all_btn.config(state=tk.NORMAL)
                    self.check_sel_btn.config(state=tk.NORMAL)
                    self.cancel_btn.config(state=tk.DISABLED)
                    # payload is now (summary_msg, error_messages_list)
                    if isinstance(payload, tuple):
                        summary_msg, error_list = payload
                    else:
                        summary_msg, error_list = str(payload), []
                    self.status_var.set(summary_msg)
                    # Refresh the last-checked label without wiping the form
                    sub = self._selected_sub()
                    if sub:
                        import datetime
                        self.last_checked_var.set(
                            datetime.datetime.now().strftime("%d %b %Y  %H:%M"))
                    # Refresh the Documents Library tree so newly saved docs appear
                    try:
                        if hasattr(self.app, 'refresh_document_library'):
                            self.app.refresh_document_library()
                        elif hasattr(self.app, 'document_tree_manager') and self.app.document_tree_manager:
                            self.app.document_tree_manager.refresh_tree()
                    except Exception:
                        pass
                    # Show error details if any
                    if error_list:
                        self._show_error_summary(error_list)
        except queue.Empty:
            pass

        if not self.window.winfo_exists():
            return
        self.window.after(100, self._poll_queue)

    def _open_digest_dialog(self):
        """Open the Generate Digest dialog."""
        DigestDialog(self.window, self.app, self._subs)

    def _show_error_summary(self, errors: list):
        """Show a small dialog listing what failed, with a path to the log file."""
        from subscription_manager import SUBSCRIPTION_LOG_PATH
        dlg = tk.Toplevel(self.window)
        dlg.title(f"Check Errors ({len(errors)})")
        dlg.geometry("560x280")
        dlg.resizable(True, True)
        dlg.transient(self.window)

        ttk.Label(dlg, text="The following items could not be processed:",
                  font=("Arial", 9, "bold")).pack(anchor=tk.W, padx=10, pady=(10, 4))

        frame = ttk.Frame(dlg)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 4))
        txt = tk.Text(frame, height=8, wrap=tk.WORD, font=("Arial", 8),
                      relief=tk.SUNKEN, borderwidth=1, state=tk.NORMAL)
        sb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        for err in errors:
            txt.insert(tk.END, f"• {err}\n")
        txt.config(state=tk.DISABLED)

        ttk.Label(dlg,
                  text=f"Full details in: {SUBSCRIPTION_LOG_PATH}",
                  foreground="#555", font=("Arial", 8)).pack(anchor=tk.W, padx=10)

        btn_row = ttk.Frame(dlg)
        btn_row.pack(fill=tk.X, padx=10, pady=(4, 10))
        ttk.Button(btn_row, text="OK", width=10, command=dlg.destroy).pack(side=tk.RIGHT)
        ttk.Button(btn_row, text="Open Log", width=10,
                   command=lambda: self._open_log_file()).pack(side=tk.RIGHT, padx=(0, 6))

    def _open_log_file(self):
        """Open the subscription log file in Notepad."""
        from subscription_manager import SUBSCRIPTION_LOG_PATH
        import subprocess, os
        if os.path.exists(SUBSCRIPTION_LOG_PATH):
            subprocess.Popen(["notepad", SUBSCRIPTION_LOG_PATH])
        else:
            messagebox.showinfo("Log File", "No log file yet.", parent=self.window)

    # ──────────────────────────────────────────────────────────────────────
    # Close
    # ──────────────────────────────────────────────────────────────────────

    def _on_close(self):
        if self._running:
            if not messagebox.askyesno("Close",
                                       "A subscription check is running.\nCancel it and close?",
                                       parent=self.window):
                return
            self._stop[0] = True
        self.window.destroy()


# ─────────────────────────────────────────────────────────────────────────────
# Digest dialog
# ─────────────────────────────────────────────────────────────────────────────

class DigestDialog:
    """
    Modal dialog for generating a digest across selected subscriptions.

    Layout:
      ┌──────────────────────────────────────────────────────────────────┐
      │ Include subscriptions (checklist)                                 │
      │ Prompt: [combo dropdown]  [Prompts Library]                        │
      │ Prompt text: [editable text area]                                 │
      │ Status: ............                                               │
      │                          [Generate Digest]  [Close]               │
      └──────────────────────────────────────────────────────────────────┘
    """

    def __init__(self, parent, app, subs: list):
        self.app    = app
        self.parent = parent
        self.subs   = subs
        self._running = False
        self._queue   = queue.Queue()

        self.window = tk.Toplevel(parent)
        self.window.title("Generate Digest")
        self.window.geometry("660x560")
        self.window.minsize(560, 460)
        self.window.transient(parent)
        self.window.grab_set()

        self._build_ui()
        self._poll_queue()

    # ──────────────────────────────────────────────────────────────────
    # UI
    # ──────────────────────────────────────────────────────────────────

    def _build_ui(self):
        outer = ttk.Frame(self.window, padding=10)
        outer.pack(fill=tk.BOTH, expand=True)

        # ── Subscription checklist ───────────────────────────────────────
        ttk.Label(outer, text="Include subscriptions:",
                  font=("Arial", 9, "bold")).pack(anchor=tk.W)

        check_frame = ttk.Frame(outer)
        check_frame.pack(fill=tk.X, pady=(2, 8))

        self._sub_vars = {}   # sub_id -> BooleanVar
        for sub in self.subs:
            var = tk.BooleanVar(value=True)
            self._sub_vars[sub["id"]] = var
            ttk.Checkbutton(check_frame, text=sub.get("name", "?"),
                            variable=var).pack(side=tk.LEFT, padx=(0, 12))

        # ── Prompt row ───────────────────────────────────────────────
        prompt_row = ttk.Frame(outer)
        prompt_row.pack(fill=tk.X, pady=(0, 4))

        ttk.Label(prompt_row, text="Prompt:", width=9, anchor=tk.E).pack(side=tk.LEFT)

        self._prompt_var = tk.StringVar()
        self._prompt_combo = ttk.Combobox(prompt_row, textvariable=self._prompt_var,
                                          width=28, state="readonly")
        self._prompt_combo.pack(side=tk.LEFT, padx=(4, 6))
        self._prompt_combo.bind("<<ComboboxSelected>>", self._on_prompt_select)

        ttk.Button(prompt_row, text="Prompts Library", width=15,
                   command=self._open_prompts_library).pack(side=tk.LEFT)

        self._refresh_prompt_combo()

        # ── Prompt text ───────────────────────────────────────────────
        ttk.Label(outer, text="Prompt text:",
                  font=("Arial", 9, "bold")).pack(anchor=tk.W, pady=(4, 2))

        text_frame = ttk.Frame(outer)
        text_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        self._prompt_text = tk.Text(text_frame, height=8, wrap=tk.WORD,
                                    font=("Arial", 9), relief=tk.SUNKEN, borderwidth=1)
        pt_sb = ttk.Scrollbar(text_frame, orient=tk.VERTICAL,
                              command=self._prompt_text.yview)
        self._prompt_text.configure(yscrollcommand=pt_sb.set)
        self._prompt_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        pt_sb.pack(side=tk.RIGHT, fill=tk.Y)

        # ── Status bar ───────────────────────────────────────────────
        self._status_var = tk.StringVar(value="Ready.")
        ttk.Label(outer, textvariable=self._status_var, foreground="#444",
                  font=("Arial", 8), wraplength=580,
                  justify=tk.LEFT).pack(anchor=tk.W, pady=(0, 6))

        # ── Button row ───────────────────────────────────────────────
        btn_row = ttk.Frame(outer)
        btn_row.pack(fill=tk.X)
        self._go_btn = ttk.Button(btn_row, text="Generate Digest", width=18,
                                   command=self._run_digest)
        self._go_btn.pack(side=tk.LEFT)
        self._progress = ttk.Progressbar(btn_row, mode="indeterminate", length=120)
        self._progress.pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(btn_row, text="Close", width=10,
                   command=self.window.destroy).pack(side=tk.RIGHT)

    # ──────────────────────────────────────────────────────────────────
    # Prompt helpers (same pattern as SubscriptionDialog detail form)
    # ──────────────────────────────────────────────────────────────────

    def _refresh_prompt_combo(self):
        try:
            from config_manager import load_prompts
            raw = load_prompts()
            names = []
            if isinstance(raw, list):
                names = [p["name"] for p in raw if isinstance(p, dict) and p.get("name")]
            else:
                def _walk(node):
                    if isinstance(node, dict):
                        if node.get("type") == "item" and node.get("name"):
                            names.append(node["name"])
                        for child in (list(node.get("children", {}).values()) +
                                      list(node.get("items", {}).values())):
                            _walk(child)
                for folder in raw.get("folders", {}).values():
                    _walk(folder)
            self._prompt_combo["values"] = [n for n in names if n]
        except Exception as exc:
            logger.warning(f"DigestDialog._refresh_prompt_combo: {exc}")
            self._prompt_combo["values"] = []

    def _on_prompt_select(self, _event=None):
        name = self._prompt_var.get()
        if not name:
            return
        try:
            from config_manager import load_prompts
            raw = load_prompts()
            if isinstance(raw, list):
                for p in raw:
                    if isinstance(p, dict) and p.get("name") == name:
                        self._prompt_text.delete("1.0", tk.END)
                        self._prompt_text.insert("1.0", p.get("text", ""))
                        return
            else:
                def _find(node):
                    if isinstance(node, dict):
                        if node.get("type") == "item" and node.get("name") == name:
                            return node.get("content", node.get("text", ""))
                        for child in (list(node.get("children", {}).values()) +
                                      list(node.get("items", {}).values())):
                            res = _find(child)
                            if res is not None:
                                return res
                    return None
                for folder in raw.get("folders", {}).values():
                    txt = _find(folder)
                    if txt is not None:
                        self._prompt_text.delete("1.0", tk.END)
                        self._prompt_text.insert("1.0", txt)
                        return
        except Exception as exc:
            logger.warning(f"DigestDialog._on_prompt_select: {exc}")

    def _open_prompts_library(self):
        def _on_chosen(name: str, text: str):
            self._prompt_var.set(name)
            self._prompt_text.delete("1.0", tk.END)
            self._prompt_text.insert("1.0", text)
            self.window.lift()

        try:
            from prompt_tree_manager import open_prompt_tree_for_selection
            open_prompt_tree_for_selection(self.window, _on_chosen)
            return
        except (ImportError, AttributeError):
            pass

        try:
            original_cb = getattr(self.app, "set_prompt_from_library", None)
            def _intercept(name, text):
                _on_chosen(name, text)
                if original_cb:
                    self.app.set_prompt_from_library = original_cb
            self.app.set_prompt_from_library = _intercept
            self.app.open_prompt_manager()
        except Exception as exc:
            logger.warning(f"DigestDialog._open_prompts_library: {exc}")
            self._refresh_prompt_combo()
            messagebox.showinfo("Prompts Library",
                                "Please select a prompt from the dropdown.",
                                parent=self.window)

    # ──────────────────────────────────────────────────────────────────
    # Run
    # ──────────────────────────────────────────────────────────────────

    def _run_digest(self):
        if self._running:
            return

        selected_ids = [sid for sid, var in self._sub_vars.items() if var.get()]
        if not selected_ids:
            messagebox.showwarning("Generate Digest",
                                   "Please tick at least one subscription.",
                                   parent=self.window)
            return

        prompt_text = self._prompt_text.get("1.0", tk.END).strip()
        if not prompt_text:
            messagebox.showwarning("Generate Digest",
                                   "Please enter or select a digest prompt.",
                                   parent=self.window)
            return

        prompt_name = self._prompt_var.get().strip() or "Subscription Digest"
        config = getattr(self.app, "config", {})

        self._running = True
        self._go_btn.config(state=tk.DISABLED)
        self._progress.start(12)
        self._status_var.set("Starting digest\u2026")

        def _worker():
            from subscription_manager import generate_digest
            def _cb(msg): self._queue.put(("status", msg))
            ok, result = generate_digest(
                subscription_ids=selected_ids,
                prompt_text=prompt_text,
                prompt_name=prompt_name,
                config=config,
                status_cb=_cb,
            )
            self._queue.put(("done", (ok, result)))

        threading.Thread(target=_worker, daemon=True).start()

    def _poll_queue(self):
        try:
            while True:
                msg_type, payload = self._queue.get_nowait()
                if msg_type == "status":
                    self._status_var.set(str(payload))
                elif msg_type == "done":
                    ok, result = payload
                    self._running = False
                    self._progress.stop()
                    self._go_btn.config(state=tk.NORMAL)
                    if ok:
                        self._status_var.set("Digest saved to Documents Library.")
                        # Refresh library tree
                        try:
                            if hasattr(self.app, "refresh_document_library"):
                                self.app.refresh_document_library()
                            elif hasattr(self.app, "document_tree_manager") and self.app.document_tree_manager:
                                self.app.document_tree_manager.refresh_tree()
                        except Exception:
                            pass
                        messagebox.showinfo("Digest Complete",
                                            "The digest has been saved to the Documents Library.",
                                            parent=self.window)
                    else:
                        self._status_var.set(f"Error: {result}")
                        messagebox.showerror("Digest Failed", str(result),
                                             parent=self.window)
        except queue.Empty:
            pass
        if self.window.winfo_exists():
            self.window.after(100, self._poll_queue)
