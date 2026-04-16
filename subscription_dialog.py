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
        ttk.Entry(parent, textvariable=self.channel_id_var, width=30,
                  state="readonly").grid(row=3, column=1, columnspan=2, sticky=tk.W, pady=3)

        # Min duration
        lbl("Min duration:", 4)
        dur_frame = ttk.Frame(parent)
        dur_frame.grid(row=4, column=1, sticky=tk.W, pady=3)
        self.min_dur_var = tk.IntVar(value=25)
        ttk.Spinbox(dur_frame, textvariable=self.min_dur_var,
                    from_=0, to=999, width=6).pack(side=tk.LEFT)
        ttk.Label(dur_frame, text="minutes  (0 = no filter, YouTube only)",
                  foreground="#666").pack(side=tk.LEFT, padx=(6, 0))

        # Look-back
        lbl("Look back:", 5)
        lb_frame = ttk.Frame(parent)
        lb_frame.grid(row=5, column=1, sticky=tk.W, pady=3)
        self.look_back_var = tk.IntVar(value=48)
        ttk.Spinbox(lb_frame, textvariable=self.look_back_var,
                    from_=0, to=9999, width=6).pack(side=tk.LEFT)
        ttk.Label(lb_frame, text="hours  (0 = all new since last check)",
                  foreground="#666").pack(side=tk.LEFT, padx=(6, 0))

        # Prompt
        lbl("Prompt:", 6)
        prompt_row = ttk.Frame(parent)
        prompt_row.grid(row=6, column=1, columnspan=2, sticky=tk.EW, pady=3)
        self.prompt_name_var = tk.StringVar()
        self.prompt_combo = ttk.Combobox(prompt_row, textvariable=self.prompt_name_var,
                                          width=24, state="readonly")
        self.prompt_combo.pack(side=tk.LEFT)
        self.prompt_combo.bind("<<ComboboxSelected>>", self._on_prompt_select)
        ttk.Button(prompt_row, text="Prompts Library", width=15,
                   command=self._open_prompts_library).pack(side=tk.LEFT, padx=(6, 0))

        # Prompt text
        lbl("", 7)
        pt_frame = ttk.Frame(parent)
        pt_frame.grid(row=7, column=1, columnspan=2, sticky=tk.EW, pady=(0, 4))
        self.prompt_text = tk.Text(pt_frame, height=5, wrap=tk.WORD,
                                   font=("Arial", 9), relief=tk.SUNKEN, borderwidth=1)
        pt_sb = ttk.Scrollbar(pt_frame, orient=tk.VERTICAL,
                               command=self.prompt_text.yview)
        self.prompt_text.configure(yscrollcommand=pt_sb.set)
        self.prompt_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        pt_sb.pack(side=tk.RIGHT, fill=tk.Y)

        # Enabled checkbox
        lbl("", 8)
        self.enabled_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(parent, text="Enabled",
                        variable=self.enabled_var).grid(row=8, column=1, sticky=tk.W, pady=3)

        # Last checked
        lbl("Last checked:", 9)
        self.last_checked_var = tk.StringVar(value="Never")
        ttk.Label(parent, textvariable=self.last_checked_var,
                  foreground="#666").grid(row=9, column=1, sticky=tk.W, pady=3)

        # Scheduling (placeholder)
        ttk.Separator(parent, orient=tk.HORIZONTAL).grid(
            row=10, column=0, columnspan=3, sticky=tk.EW, pady=(8, 4))
        ttk.Label(parent, text="Scheduling (coming soon)",
                  foreground="#e07020", font=("Arial", 9, "bold")).grid(
            row=11, column=0, columnspan=3, sticky=tk.W, padx=(0, 0))

        sched_frame = ttk.Frame(parent)
        sched_frame.grid(row=12, column=0, columnspan=3, sticky=tk.EW, pady=3)

        self.sched_enabled_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(sched_frame, text="Enable automatic scheduled checking",
                        variable=self.sched_enabled_var,
                        state=tk.DISABLED).pack(anchor=tk.W)

        interval_row = ttk.Frame(sched_frame)
        interval_row.pack(anchor=tk.W, pady=(2, 0))
        ttk.Label(interval_row, text="Check every").pack(side=tk.LEFT)
        self.interval_var = tk.IntVar(value=6)
        ttk.Spinbox(interval_row, textvariable=self.interval_var,
                    from_=1, to=168, width=5,
                    state=tk.DISABLED).pack(side=tk.LEFT, padx=(4, 4))
        ttk.Label(interval_row, text="hours").pack(side=tk.LEFT)

        ttk.Label(sched_frame,
                  text="Scheduled checking will be available in a future update.",
                  foreground="#888", font=("Arial", 8)).pack(anchor=tk.W, pady=(2, 0))

        # Save button
        save_row = ttk.Frame(parent)
        save_row.grid(row=13, column=0, columnspan=3, sticky=tk.E, pady=(8, 0))
        ttk.Button(save_row, text="Save Changes", width=14,
                   command=self._save_current).pack(side=tk.RIGHT)

        parent.columnconfigure(1, weight=1)

    # ──────────────────────────────────────────────────────────────────────
    # List management
    # ──────────────────────────────────────────────────────────────────────

    def _load_list(self):
        from subscription_manager import load_subscriptions
        self._subs = load_subscriptions()
        self.sub_listbox.delete(0, tk.END)
        for sub in self._subs:
            label = sub.get("name", "?")
            if not sub.get("enabled", True):
                label += " (disabled)"
            self.sub_listbox.insert(tk.END, label)

    def _on_list_select(self, _event=None):
        sel = self.sub_listbox.curselection()
        if not sel:
            return
        idx = sel[-1]
        if idx < len(self._subs):
            self._current_idx = idx
            self._populate_form(self._subs[idx])

    def _populate_form(self, sub: dict):
        self.no_sel_label.pack_forget()
        self.form_frame.pack(fill=tk.BOTH, expand=True)
        self._refresh_prompt_combo()

        self.name_var.set(sub.get("name", ""))
        sub_type_internal = sub.get("type", "youtube_channel")
        self.type_var.set(TYPE_LABELS.get(sub_type_internal, "YouTube Channel"))
        self.url_var.set(sub.get("url", ""))
        self.channel_id_var.set(sub.get("channel_id", ""))
        self.min_dur_var.set(sub.get("min_duration", 25))
        self.look_back_var.set(sub.get("look_back_hours", 48))
        self.enabled_var.set(sub.get("enabled", True))
        self.sched_enabled_var.set(sub.get("schedule_enabled", False))
        self.interval_var.set(sub.get("check_interval_hours", 6))

        # Prompt
        pname = sub.get("prompt_name", "")
        self.prompt_name_var.set(pname)
        self.prompt_text.delete("1.0", tk.END)
        self.prompt_text.insert("1.0", sub.get("prompt_text", ""))

        # Last checked
        lc = sub.get("last_checked")
        if lc:
            try:
                import datetime
                dt = datetime.datetime.fromisoformat(lc)
                self.last_checked_var.set(dt.strftime("%d %b %Y  %H:%M"))
            except Exception:
                self.last_checked_var.set(str(lc))
        else:
            self.last_checked_var.set("Never")

        # Toggle resolve button visibility for YouTube
        self._on_type_change()

    def _on_type_change(self, _event=None):
        is_yt = (SUB_TYPES.get(self.type_var.get()) == "youtube_channel")
        self.resolve_btn.config(state=tk.NORMAL if is_yt else tk.DISABLED)

    # ──────────────────────────────────────────────────────────────────────
    # CRUD
    # ──────────────────────────────────────────────────────────────────────

    def _add_new(self):
        from subscription_manager import default_subscription, add_subscription
        name = "New Subscription"
        sub = default_subscription()
        sub["name"] = name
        self._subs = add_subscription(sub)
        self._load_list()
        self.sub_listbox.selection_clear(0, tk.END)
        self.sub_listbox.selection_set(tk.END)
        self.sub_listbox.see(tk.END)
        self._current_idx = len(self._subs) - 1
        self._populate_form(self._subs[-1])

    def _remove(self):
        sel = self.sub_listbox.curselection()
        if not sel:
            return
        names = [self._subs[i]["name"] for i in sel if i < len(self._subs)]
        if not messagebox.askyesno(
            "Remove Subscriptions",
            f"Remove {len(sel)} subscription(s)?\n\n" + "\n".join(names),
            parent=self.window,
        ):
            return
        from subscription_manager import remove_subscription
        for idx in sel:
            if idx < len(self._subs):
                remove_subscription(self._subs[idx]["id"])
        self._current_idx = None
        self._load_list()
        self.no_sel_label.pack(expand=True)
        self.form_frame.pack_forget()

    def _rename(self):
        sel = self.sub_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx >= len(self._subs):
            return
        current = self._subs[idx]["name"]
        from tkinter import simpledialog
        new_name = simpledialog.askstring(
            "Rename", "New name:", initialvalue=current, parent=self.window
        )
        if new_name and new_name.strip():
            from subscription_manager import update_subscription
            update_subscription(self._subs[idx]["id"], {"name": new_name.strip()})
            self._load_list()
            self.sub_listbox.selection_set(idx)
            self._current_idx = idx
            self._subs[idx]["name"] = new_name.strip()
            self.name_var.set(new_name.strip())

    def _duplicate(self):
        sel = self.sub_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx >= len(self._subs):
            return
        import copy
        from subscription_manager import add_subscription, _make_id
        dup = copy.deepcopy(self._subs[idx])
        dup["id"]         = _make_id()
        dup["name"]       = dup["name"] + " (copy)"
        dup["last_checked"] = None
        dup["seen_guids"] = []
        self._subs = add_subscription(dup)
        self._load_list()
        self.sub_listbox.selection_clear(0, tk.END)
        self.sub_listbox.selection_set(tk.END)
        self._current_idx = len(self._subs) - 1
        self._populate_form(self._subs[-1])

    def _reset_history(self):
        sel = self.sub_listbox.curselection()
        if not sel:
            messagebox.showwarning("Reset History",
                                   "Select one or more subscriptions first.",
                                   parent=self.window)
            return
        names = [self._subs[i]["name"] for i in sel if i < len(self._subs)]
        if not messagebox.askyesno(
            "Reset History",
            f"Clear check history for:\n\n" + "\n".join(names) +
            "\n\nThe next Check will re-process recent items.",
            parent=self.window,
        ):
            return
        from subscription_manager import update_subscription
        for idx in sel:
            if idx < len(self._subs):
                update_subscription(self._subs[idx]["id"],
                                    {"seen_guids": [], "last_checked": None})
        self._load_list()
        sel_idx = sel[0]
        self.sub_listbox.selection_set(sel_idx)
        self._current_idx = sel_idx
        if sel_idx < len(self._subs):
            self._populate_form(self._subs[sel_idx])
        names_str = ", ".join(f"'{n}'" for n in names)
        messagebox.showinfo("History Cleared",
                            f"Check history cleared for {names_str}.\n\n"
                            "The next Check will re-process recent items.",
                            parent=self.window)
        self.status_var.set(f"History cleared for: {', '.join(names)}")

    def _save_current(self):
        if self._current_idx is None:
            return
        sub = self._subs[self._current_idx]
        sub["name"]               = self.name_var.get().strip() or "Unnamed"
        sub["type"]               = SUB_TYPES.get(self.type_var.get(), "youtube_channel")
        sub["url"]                = self.url_var.get().strip()
        sub["channel_id"]         = self.channel_id_var.get().strip()
        sub["min_duration"]       = self.min_dur_var.get()
        sub["look_back_hours"]    = self.look_back_var.get()
        sub["enabled"]            = self.enabled_var.get()
        sub["schedule_enabled"]   = self.sched_enabled_var.get()
        sub["check_interval_hours"] = self.interval_var.get()
        sub["prompt_name"]        = self.prompt_name_var.get()
        sub["prompt_text"]        = self.prompt_text.get("1.0", tk.END).strip()

        from subscription_manager import update_subscription
        update_subscription(sub["id"], sub)
        self._load_list()
        self.sub_listbox.selection_set(self._current_idx)
        self.status_var.set(f"Saved: {sub['name']}")

    # ──────────────────────────────────────────────────────────────────────
    # Channel resolution
    # ──────────────────────────────────────────────────────────────────────

    def _resolve_channel(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("Resolve", "Enter a YouTube URL or @handle first.",
                                   parent=self.window)
            return
        self.resolve_btn.config(state=tk.DISABLED)
        self.status_var.set("Resolving channel ID…")

        def _worker():
            from subscription_manager import resolve_youtube_channel
            ch_id = resolve_youtube_channel(url)
            self._queue.put(("resolved", ch_id))

        threading.Thread(target=_worker, daemon=True).start()

    # ──────────────────────────────────────────────────────────────────────
    # Prompt helpers
    # ──────────────────────────────────────────────────────────────────────

    def _refresh_prompt_combo(self):
        try:
            from config_manager import load_prompts
            raw   = load_prompts()
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

    def _on_prompt_select(self, _event=None):
        name = self.prompt_name_var.get()
        if not name:
            return
        try:
            from config_manager import load_prompts
            raw = load_prompts()
            if isinstance(raw, list):
                for p in raw:
                    if isinstance(p, dict) and p.get("name") == name:
                        self.prompt_text.delete("1.0", tk.END)
                        self.prompt_text.insert("1.0", p.get("text", ""))
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
                        self.prompt_text.delete("1.0", tk.END)
                        self.prompt_text.insert("1.0", txt)
                        return
        except Exception as exc:
            logger.warning(f"_on_prompt_select: {exc}")

    def _open_prompts_library(self):
        def _on_chosen(name: str, text: str):
            self.prompt_name_var.set(name)
            self.prompt_text.delete("1.0", tk.END)
            self.prompt_text.insert("1.0", text)
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
            logger.warning(f"_open_prompts_library: {exc}")
            self._refresh_prompt_combo()
            messagebox.showinfo("Prompts Library",
                                "Please select a prompt from the dropdown.",
                                parent=self.window)

    # ──────────────────────────────────────────────────────────────────────
    # Check operations
    # ──────────────────────────────────────────────────────────────────────

    def _check_all(self):
        if self._running:
            return
        self._start_check(None)

    def _check_selected(self):
        if self._running:
            return
        sel = self.sub_listbox.curselection()
        if not sel:
            messagebox.showwarning(
                "Check Selected",
                "Please select one or more subscriptions from the list first.",
                parent=self.window,
            )
            return
        ids = [self._subs[i]["id"] for i in sel if i < len(self._subs)]
        self._start_check(ids)

    def _cancel_check(self):
        self._stop[0] = True
        self.cancel_btn.config(state=tk.DISABLED)
        self.status_var.set("Cancelling…")

    def _start_check(self, sub_ids=None):
        self._running  = True
        self._stop[0]  = False
        self.check_all_btn.config(state=tk.DISABLED)
        self.check_sel_btn.config(state=tk.DISABLED)
        self.cancel_btn.config(state=tk.NORMAL)
        self.progress_bar.start(10)
        self.status_var.set("Starting check…")

        config = getattr(self.app, "config", {})

        def _worker():
            from subscription_manager import (
                check_all_subscriptions, check_subscription, load_subscriptions
            )
            def _cb(msg):
                self._queue.put(("status", msg))
            def _item_done(title, ok):
                self._queue.put(("item_done", (title, ok)))
            def _sub_done(name, result):
                self._queue.put(("sub_done", (name, result)))

            if sub_ids is None:
                totals = check_all_subscriptions(
                    config,
                    status_cb=_cb,
                    item_done_cb=_item_done,
                    sub_done_cb=_sub_done,
                    stop_flag=self._stop,
                )
            else:
                all_subs = load_subscriptions()
                subs = [s for s in all_subs if s["id"] in sub_ids]
                totals = {"total_processed": 0, "total_skipped": 0, "total_errors": 0}
                errors = []
                for sub in subs:
                    if self._stop[0]:
                        break
                    result = check_subscription(
                        sub, config,
                        status_cb=_cb,
                        item_done_cb=_item_done,
                        stop_flag=self._stop,
                    )
                    totals["total_processed"] += result["processed"]
                    totals["total_skipped"]   += result["skipped"]
                    totals["total_errors"]    += result["errors"]
                    errors.extend(result.get("error_messages", []))
                    from subscription_manager import update_subscription
                    import datetime
                    new_guids = result.get("new_seen_guids", [])
                    merged = list(set(sub.get("seen_guids", []) + new_guids))
                    update_subscription(sub["id"], {
                        "seen_guids":   merged,
                        "last_checked": datetime.datetime.now().isoformat(),
                    })
                    _sub_done(sub["name"], result)
                p, sk, er = totals["total_processed"], totals["total_skipped"], totals["total_errors"]
                _cb(f"Done — {p} processed, {sk} skipped, {er} error(s).")

            self._queue.put(("done", totals))

        threading.Thread(target=_worker, daemon=True).start()

    # ──────────────────────────────────────────────────────────────────────
    # Digest dialog
    # ──────────────────────────────────────────────────────────────────────

    def _open_digest_dialog(self):
        """Open the Generate Digest dialog."""
        subs = [s for s in self._subs if s.get("enabled", True)]
        if not subs:
            messagebox.showwarning("Generate Digest",
                                   "No enabled subscriptions found.",
                                   parent=self.window)
            return
        DigestDialog(self.window, self.app, subs)

    # ──────────────────────────────────────────────────────────────────────
    # Queue polling
    # ──────────────────────────────────────────────────────────────────────

    def _poll_queue(self):
        try:
            while True:
                msg_type, payload = self._queue.get_nowait()
                if msg_type == "status":
                    self.status_var.set(str(payload))
                elif msg_type == "resolved":
                    ch_id = payload
                    if ch_id:
                        self.channel_id_var.set(ch_id)
                        self.status_var.set(f"Channel ID resolved: {ch_id}")
                    else:
                        self.status_var.set("Could not resolve channel ID.")
                    self.resolve_btn.config(state=tk.NORMAL)
                elif msg_type == "item_done":
                    title, ok = payload
                    icon = "✔" if ok else "✘"
                    self.status_var.set(f"{icon} {title}")
                elif msg_type == "sub_done":
                    name, result = payload
                    self._load_list()
                elif msg_type == "done":
                    self._running = False
                    self.progress_bar.stop()
                    self.check_all_btn.config(state=tk.NORMAL)
                    self.check_sel_btn.config(state=tk.NORMAL)
                    self.cancel_btn.config(state=tk.DISABLED)
                    self._load_list()
                    try:
                        if hasattr(self.app, "refresh_document_library"):
                            self.app.refresh_document_library()
                        elif hasattr(self.app, "document_tree_manager") and self.app.document_tree_manager:
                            self.app.document_tree_manager.refresh_tree()
                    except Exception:
                        pass
        except queue.Empty:
            pass
        if self.window.winfo_exists():
            self.window.after(200, self._poll_queue)

    def _on_close(self):
        if self._running:
            self._stop[0] = True
        self.window.destroy()


# ─────────────────────────────────────────────────────────────────────────────
# Digest Dialog
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
        self._last_digest_doc_id = None   # set after a successful digest run

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
        self._send_btn = ttk.Button(btn_row, text="📧 Send by Email", width=18,
                                    command=self._open_send_dialog,
                                    state=tk.DISABLED)
        self._send_btn.pack(side=tk.LEFT, padx=(8, 0))
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
        self._status_var.set("Starting digest…")

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
                        # Offer to send by email
                        self._last_digest_doc_id = result
                        self._send_btn.config(state=tk.NORMAL)
                    else:
                        self._status_var.set(f"Error: {result}")
                        messagebox.showerror("Digest Failed", str(result),
                                             parent=self.window)
        except queue.Empty:
            pass
        if self.window.winfo_exists():
            self.window.after(100, self._poll_queue)

    def _open_send_dialog(self):
        """Open the Send Digest by Email dialog."""
        if not self._last_digest_doc_id:
            messagebox.showwarning(
                "Send by Email",
                "Please generate a digest first.",
                parent=self.window,
            )
            return
        # Retrieve digest text from library
        try:
            from document_library import get_document_by_id, load_document_entries
            doc = get_document_by_id(self._last_digest_doc_id)
            entries = load_document_entries(self._last_digest_doc_id) or []
            digest_text = '\n\n'.join(
                e.get('text', '') for e in entries if e.get('text')
            )
            subject = doc.get('title', 'DocAnalyser Digest') if doc else 'DocAnalyser Digest'
        except Exception as exc:
            messagebox.showerror('Send by Email', f'Could not load digest:\n{exc}',
                                 parent=self.window)
            return

        data_dir = getattr(self.app, '_data_dir',
                   getattr(self.app, 'data_dir',
                   __import__('config').DATA_DIR))
        SendDigestDialog(self.window, self.app, subject, digest_text, data_dir)


# ─────────────────────────────────────────────────────────────────────────────
# Send Digest Dialog
# ─────────────────────────────────────────────────────────────────────────────

class SendDigestDialog:
    """
    Modal dialog for sending a digest by email.

    Layout:
      ┌──────────────────────────────────────────────────────────────────┐
      │ From: you@gmail.com (detected automatically)                     │
      │ Subject: [editable]                                              │
      │ Recipients: [listbox]  [Remove] [Select all] [Deselect all]      │
      │ Add contact: [Name]  [Email]  [Add]                              │
      │ Status: ...                    [Send]  [Cancel]                  │
      └──────────────────────────────────────────────────────────────────┘
    """

    def __init__(self, parent, app, subject: str, digest_text: str, data_dir: str):
        self.app         = app
        self.parent      = parent
        self.digest_text = digest_text
        self.data_dir    = data_dir
        self._queue      = queue.Queue()
        self._running    = False

        self.window = tk.Toplevel(parent)
        self.window.title('Send Digest by Email')
        self.window.geometry('580x520')
        self.window.minsize(480, 440)
        self.window.transient(parent)
        self.window.grab_set()

        self._build_ui(subject)
        self._load_contacts_to_list()
        self._poll_queue()
        self._detect_sender()

    # ── UI ─────────────────────────────────────────────────────────────────

    def _build_ui(self, subject: str):
        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        # From row
        from_row = ttk.Frame(outer)
        from_row.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(from_row, text='From:', width=10, anchor=tk.E).pack(side=tk.LEFT)
        self._from_var = tk.StringVar(value='(authorising…)')
        ttk.Label(from_row, textvariable=self._from_var,
                  foreground='#555').pack(side=tk.LEFT, padx=(6, 0))

        # Subject row
        subj_row = ttk.Frame(outer)
        subj_row.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(subj_row, text='Subject:', width=10, anchor=tk.E).pack(side=tk.LEFT)
        self._subject_var = tk.StringVar(value=subject)
        ttk.Entry(subj_row, textvariable=self._subject_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0)
        )

        # Recipients section
        ttk.Label(outer, text='Recipients:',
                  font=('Arial', 9, 'bold')).pack(anchor=tk.W)

        rec_frame = ttk.Frame(outer)
        rec_frame.pack(fill=tk.BOTH, expand=True, pady=(4, 0))

        sb = ttk.Scrollbar(rec_frame, orient=tk.VERTICAL)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._rec_list = tk.Listbox(
            rec_frame, yscrollcommand=sb.set,
            selectmode=tk.EXTENDED, height=8,
            font=('Arial', 9),
        )
        self._rec_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.config(command=self._rec_list.yview)

        # Add / Remove buttons for recipient list
        rec_btn_row = ttk.Frame(outer)
        rec_btn_row.pack(fill=tk.X, pady=(4, 8))
        ttk.Button(rec_btn_row, text='Remove selected',
                   command=self._remove_selected).pack(side=tk.LEFT)
        ttk.Button(rec_btn_row, text='Select all',
                   command=self._select_all).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(rec_btn_row, text='Deselect all',
                   command=self._deselect_all).pack(side=tk.LEFT, padx=(6, 0))

        # Add new contact
        ttk.Separator(outer, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(0, 8))
        ttk.Label(outer, text='Add contact:',
                  font=('Arial', 9, 'bold')).pack(anchor=tk.W)
        add_row = ttk.Frame(outer)
        add_row.pack(fill=tk.X, pady=(4, 0))
        ttk.Label(add_row, text='Name:', width=7).pack(side=tk.LEFT)
        self._new_name = tk.StringVar()
        ttk.Entry(add_row, textvariable=self._new_name, width=16).pack(
            side=tk.LEFT, padx=(4, 8)
        )
        ttk.Label(add_row, text='Email:', width=7).pack(side=tk.LEFT)
        self._new_email = tk.StringVar()
        ttk.Entry(add_row, textvariable=self._new_email, width=22).pack(
            side=tk.LEFT, padx=(4, 8)
        )
        ttk.Button(add_row, text='Add', command=self._add_contact).pack(side=tk.LEFT)

        # Status
        self._status_var = tk.StringVar(value='Select recipients and click Send.')
        ttk.Label(outer, textvariable=self._status_var, foreground='#444',
                  font=('Arial', 8), wraplength=520,
                  justify=tk.LEFT).pack(anchor=tk.W, pady=(8, 4))

        # Buttons
        btn_row = ttk.Frame(outer)
        btn_row.pack(fill=tk.X)
        self._send_btn = ttk.Button(btn_row, text='📤 Send',
                                    command=self._send, width=12)
        self._send_btn.pack(side=tk.LEFT)
        self._prog = ttk.Progressbar(btn_row, mode='indeterminate', length=100)
        self._prog.pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(btn_row, text='Cancel', width=10,
                   command=self.window.destroy).pack(side=tk.RIGHT)

    # ── Helpers ───────────────────────────────────────────────────────────

    def _detect_sender(self):
        """Authenticate silently in background and update the From label."""
        def _worker():
            try:
                from email_handler import get_gmail_handler
                handler = get_gmail_handler(self.data_dir)
                ok, err = handler.authenticate()
                if ok:
                    email = handler.get_sender_email() or 'your Gmail account'
                    self._queue.put(('from', email))
                else:
                    self._queue.put(('from_err', err))
            except Exception as exc:
                self._queue.put(('from_err', str(exc)))
        threading.Thread(target=_worker, daemon=True).start()

    def _load_contacts_to_list(self):
        from email_handler import load_contacts
        self._contacts = load_contacts(self.data_dir)
        self._rec_list.delete(0, tk.END)
        for c in self._contacts:
            display = f"{c.get('name', '')}  <{c.get('email', '')}>"
            self._rec_list.insert(tk.END, display)
        # Select all by default
        self._rec_list.select_set(0, tk.END)

    def _add_contact(self):
        name  = self._new_name.get().strip()
        email = self._new_email.get().strip()
        if not email:
            messagebox.showwarning('Add Contact', 'Please enter an email address.',
                                   parent=self.window)
            return
        import re as _re
        if not _re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
            messagebox.showwarning('Add Contact',
                                   f'\'{email}\' doesn\'t look like a valid email address.',
                                   parent=self.window)
            return
        from email_handler import add_contact
        self._contacts = add_contact(self.data_dir, name or email, email)
        self._new_name.set('')
        self._new_email.set('')
        self._load_contacts_to_list()
        self._status_var.set(f'Added {email} to contacts.')

    def _remove_selected(self):
        sel = list(self._rec_list.curselection())
        if not sel:
            return
        from email_handler import remove_contact
        for idx in reversed(sel):
            if idx < len(self._contacts):
                remove_contact(self.data_dir, self._contacts[idx]['email'])
        self._load_contacts_to_list()

    def _select_all(self):
        self._rec_list.select_set(0, tk.END)

    def _deselect_all(self):
        self._rec_list.selection_clear(0, tk.END)

    def _get_selected_emails(self):
        sel = self._rec_list.curselection()
        return [self._contacts[i]['email'] for i in sel if i < len(self._contacts)]

    # ── Send ────────────────────────────────────────────────────────────

    def _send(self):
        if self._running:
            return
        recipients = self._get_selected_emails()
        if not recipients:
            messagebox.showwarning('Send Digest',
                                   'Please select at least one recipient.',
                                   parent=self.window)
            return
        subject = self._subject_var.get().strip() or 'DocAnalyser Digest'

        self._running = True
        self._send_btn.config(state=tk.DISABLED)
        self._prog.start(12)
        self._status_var.set(f'Sending to {len(recipients)} recipient(s)…')

        digest_text = self.digest_text

        def _worker():
            try:
                from email_handler import (
                    get_gmail_handler, markdown_to_html, markdown_to_plaintext
                )
                handler  = get_gmail_handler(self.data_dir)
                html     = markdown_to_html(digest_text)
                plain    = markdown_to_plaintext(digest_text)
                ok, msg  = handler.send_digest(
                    subject=subject,
                    html_body=html,
                    plain_body=plain,
                    recipients=recipients,
                )
                self._queue.put(('done', (ok, msg)))
            except Exception as exc:
                self._queue.put(('done', (False, str(exc))))

        threading.Thread(target=_worker, daemon=True).start()

    # ── Queue poll ─────────────────────────────────────────────────────────

    def _poll_queue(self):
        try:
            while True:
                msg_type, payload = self._queue.get_nowait()
                if msg_type == 'from':
                    self._from_var.set(payload)
                elif msg_type == 'from_err':
                    self._from_var.set('(not authorised — will prompt on Send)')
                elif msg_type == 'done':
                    ok, msg = payload
                    self._running = False
                    self._prog.stop()
                    self._send_btn.config(state=tk.NORMAL)
                    if ok:
                        self._status_var.set(msg)
                        messagebox.showinfo('Email Sent', msg, parent=self.window)
                    else:
                        self._status_var.set(f'Error: {msg}')
                        messagebox.showerror('Send Failed', msg, parent=self.window)
        except queue.Empty:
            pass
        if self.window.winfo_exists():
            self.window.after(150, self._poll_queue)
