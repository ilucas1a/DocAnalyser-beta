"""
hf_setup_wizard.py
==================
One-time setup wizard for HuggingFace voice speaker detection in DocAnalyser.

This wizard walks users through the four steps needed to enable Tier 2
(voice-based) speaker detection using pyannote.audio:

  Step 1 — Create a free HuggingFace account
  Step 2 — Accept the model licence
  Step 3 — Create and paste an access token
  Step 4 — Download the model (~1.5 GB, one time only)

The wizard is designed for non-technical users.  Every step has:
  - Plain English instructions with no jargon
  - A clickable link that opens the correct page in the browser
  - A clear "I've done this — Next" confirmation button
  - A back button so users can correct mistakes

After successful completion, the HuggingFace token is saved to DocAnalyser's
config so the user never needs to repeat this process.

Usage (called from DocAnalyser settings or transcript cleanup dialog):
    from hf_setup_wizard import run_hf_setup_wizard
    token = run_hf_setup_wizard(parent_window, config_save_callback)
    if token:
        # Setup complete — token is ready to use
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import webbrowser
import logging
from typing import Optional, Callable

logger = logging.getLogger(__name__)

# ── URLs ─────────────────────────────────────────────────────────────────────
URL_SIGNUP   = "https://huggingface.co/join"
URL_LICENCE  = "https://huggingface.co/pyannote/speaker-diarization-3.1"
URL_TOKENS   = "https://huggingface.co/settings/tokens"

# ── Appearance — matches DocAnalyser's grey palette ──────────────────────────
BG           = "#f0f0f0"
BG_DARK      = "#e0e0e0"
BG_STEP      = "#ffffff"
FG           = "#1a1a1a"
FG_MUTED     = "#555555"
FG_LINK      = "#0066cc"
FG_SUCCESS   = "#2e7d32"
FG_ERROR     = "#c62828"
FONT_HEADING = ("Arial", 13, "bold")
FONT_BODY    = ("Arial", 10)
FONT_SMALL   = ("Arial", 9)
FONT_MONO    = ("Consolas", 9)
FONT_LINK    = ("Arial", 10, "underline")
BTN_WIDTH    = 26
WIZARD_W     = 560
WIZARD_H     = 540


# ============================================================================
# MAIN WIZARD CLASS
# ============================================================================

class HFSetupWizard:
    """
    Four-step wizard window.  Blocks until closed.

    After completion, self.result_token holds the validated token,
    or None if the user cancelled.
    """

    def __init__(self, parent: tk.Tk, config_save_callback: Optional[Callable] = None):
        """
        Args:
            parent:               Parent Tkinter window.
            config_save_callback: Optional function(token: str) called when
                                  the wizard completes successfully.  Use this
                                  to persist the token to DocAnalyser's config.
        """
        self.parent               = parent
        self.config_save_callback = config_save_callback
        self.result_token: Optional[str] = None

        self._current_step  = 0   # 0-based index into STEPS
        self._token_var     = tk.StringVar()
        self._download_done = False

        self._build_window()
        self._show_step(0)

    # ── Window setup ─────────────────────────────────────────────────────────

    def _build_window(self):
        self.win = tk.Toplevel(self.parent)
        self.win.title("Set Up Voice Speaker Detection")
        self.win.configure(bg=BG)
        self.win.resizable(False, False)
        self.win.transient(self.parent)
        self.win.grab_set()

        # ── Header bar ───────────────────────────────────────────────────────
        header = tk.Frame(self.win, bg="#37474f", height=52)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        tk.Label(
            header,
            text="Voice Speaker Detection — One-Time Setup",
            font=("Arial", 12, "bold"),
            bg="#37474f", fg="white",
        ).pack(side=tk.LEFT, padx=16, pady=12)

        # ── Step indicator strip ──────────────────────────────────────────────
        self._step_bar = tk.Frame(self.win, bg=BG_DARK, height=32)
        self._step_bar.pack(fill=tk.X)
        self._step_bar.pack_propagate(False)
        self._step_labels = []
        step_names = ["1  Create account", "2  Accept licence",
                      "3  Paste token", "4  Download"]
        for i, name in enumerate(step_names):
            lbl = tk.Label(
                self._step_bar, text=name,
                font=FONT_SMALL, bg=BG_DARK, fg=FG_MUTED,
                padx=10, pady=6,
            )
            lbl.pack(side=tk.LEFT)
            self._step_labels.append(lbl)

        # ── Content area ─────────────────────────────────────────────────────
        self._content = tk.Frame(self.win, bg=BG)
        self._content.pack(fill=tk.BOTH, expand=True, padx=20, pady=(14, 0))

        # ── Bottom button bar ─────────────────────────────────────────────────
        btn_bar = tk.Frame(self.win, bg=BG_DARK, height=52)
        btn_bar.pack(fill=tk.X, side=tk.BOTTOM)
        btn_bar.pack_propagate(False)

        self._cancel_btn = tk.Button(
            btn_bar, text="Cancel", width=10,
            font=FONT_BODY, command=self._on_cancel,
            relief=tk.FLAT, bg=BG_DARK, activebackground="#cccccc",
        )
        self._cancel_btn.pack(side=tk.LEFT, padx=12, pady=10)

        self._back_btn = tk.Button(
            btn_bar, text="◀  Back", width=10,
            font=FONT_BODY, command=self._on_back,
            relief=tk.FLAT, bg=BG_DARK, activebackground="#cccccc",
            state=tk.DISABLED,
        )
        self._back_btn.pack(side=tk.LEFT, padx=4, pady=10)

        self._next_btn = tk.Button(
            btn_bar, text="Next  ▶", width=BTN_WIDTH,
            font=("Arial", 10, "bold"), command=self._on_next,
            relief=tk.FLAT, bg="#1565c0", fg="white",
            activebackground="#0d47a1", activeforeground="white",
        )
        self._next_btn.pack(side=tk.RIGHT, padx=12, pady=10)

        # Centre on parent
        self.win.update_idletasks()
        px = self.parent.winfo_x() + (self.parent.winfo_width()  - WIZARD_W) // 2
        py = self.parent.winfo_y() + (self.parent.winfo_height() - WIZARD_H) // 2
        self.win.geometry(f"{WIZARD_W}x{WIZARD_H}+{px}+{py}")

        self.win.protocol("WM_DELETE_WINDOW", self._on_cancel)

    # ── Step indicator update ─────────────────────────────────────────────────

    def _update_step_bar(self, active: int):
        for i, lbl in enumerate(self._step_labels):
            if i < active:
                lbl.config(bg=BG_DARK, fg=FG_SUCCESS, font=("Arial", 9, "bold"))
            elif i == active:
                lbl.config(bg="#1565c0", fg="white",   font=("Arial", 9, "bold"))
            else:
                lbl.config(bg=BG_DARK, fg=FG_MUTED,   font=FONT_SMALL)

    # ── Content builder helpers ───────────────────────────────────────────────

    def _clear_content(self):
        for w in self._content.winfo_children():
            w.destroy()

    def _heading(self, text: str) -> tk.Label:
        lbl = tk.Label(
            self._content, text=text,
            font=FONT_HEADING, bg=BG, fg=FG,
            anchor="w", justify=tk.LEFT,
        )
        lbl.pack(fill=tk.X, pady=(0, 8))
        return lbl

    def _body(self, text: str, colour: str = FG) -> tk.Label:
        lbl = tk.Label(
            self._content, text=text,
            font=FONT_BODY, bg=BG, fg=colour,
            anchor="w", justify=tk.LEFT, wraplength=WIZARD_W - 52,
        )
        lbl.pack(fill=tk.X, pady=(0, 6))
        return lbl

    def _link_button(self, label: str, url: str):
        """A plain-text link that opens a URL in the browser."""
        btn = tk.Button(
            self._content, text=f"   🔗  {label}",
            font=FONT_LINK, fg=FG_LINK, bg=BG,
            activeforeground="#003d99", activebackground=BG,
            relief=tk.FLAT, cursor="hand2", anchor="w",
            command=lambda u=url: webbrowser.open(u),
        )
        btn.pack(fill=tk.X, pady=(2, 6))

    def _separator(self, pady: int = 8):
        ttk.Separator(self._content, orient="horizontal").pack(
            fill=tk.X, pady=pady
        )

    def _info_box(self, text: str, colour: str = "#e3f2fd",
                  border: str = "#1565c0"):
        """A coloured information box."""
        frame = tk.Frame(
            self._content, bg=colour,
            highlightbackground=border, highlightthickness=1,
        )
        frame.pack(fill=tk.X, pady=(4, 8))
        tk.Label(
            frame, text=text, bg=colour, fg=FG,
            font=FONT_BODY, justify=tk.LEFT,
            wraplength=WIZARD_W - 80, anchor="w",
            padx=10, pady=8,
        ).pack(fill=tk.X)

    # ── Step renderers ────────────────────────────────────────────────────────

    def _show_step(self, step: int):
        self._current_step = step
        self._clear_content()
        self._update_step_bar(step)

        self._back_btn.config(state=tk.NORMAL if step > 0 else tk.DISABLED)

        if   step == 0: self._step_1_account()
        elif step == 1: self._step_2_licence()
        elif step == 2: self._step_3_token()
        elif step == 3: self._step_4_download()

    # ── Step 1: Create account ────────────────────────────────────────────────

    def _step_1_account(self):
        self._next_btn.config(
            text="I've created my account  ▶",
            state=tk.NORMAL, bg="#1565c0", fg="white",
        )
        self._heading("Step 1 of 4 — Create a free account")
        self._body(
            "Voice speaker detection uses an AI model from HuggingFace, "
            "a free platform that hosts open-source AI tools.\n\n"
            "You need a free HuggingFace account to download the model. "
            "This takes about two minutes and requires only an email address "
            "— no credit card, no subscription."
        )
        self._link_button("Open HuggingFace sign-up page", URL_SIGNUP)
        self._separator()
        self._info_box(
            "Once the model is on your computer, it stays there permanently.\n"
            "No internet connection is needed for any future transcriptions.\n"
            "Your recordings never leave your computer.",
            colour="#e8f5e9", border="#2e7d32",
        )
        self._body(
            "Click the link above to open the sign-up page in your browser, "
            "then return here and click the button below.",
            colour=FG_MUTED,
        )

    # ── Step 2: Accept licence ────────────────────────────────────────────────

    def _step_2_licence(self):
        self._next_btn.config(
            text="I've accepted the licence  ▶",
            state=tk.NORMAL, bg="#1565c0", fg="white",
        )
        self._heading("Step 2 of 4 — Accept the model licence")
        self._body(
            "The speaker detection model has a free-to-use licence that "
            "requires a one-time click to accept. You only need to do this "
            "once, while logged in to your HuggingFace account."
        )
        self._link_button(
            "Open model licence page (log in and click 'Agree')", URL_LICENCE
        )
        self._separator()
        self._body(
            "On that page you will see a box asking you to agree to the "
            "conditions. Click it, then return here.",
            colour=FG_MUTED,
        )
        self._info_box(
            "If you see a message saying 'You need to agree to share your "
            "contact information', fill in the short form and click Agree. "
            "Your information goes only to the model's authors, not to "
            "DocAnalyser or anyone else."
        )

    # ── Step 3: Paste token ───────────────────────────────────────────────────

    def _step_3_token(self):
        self._next_btn.config(
            text="Next  ▶", state=tk.DISABLED,
            bg="#888888", fg="white",
        )
        self._heading("Step 3 of 4 — Create and paste your access token")
        self._body(
            "An access token is a password that lets DocAnalyser download "
            "the model on your behalf. You create it on HuggingFace and "
            "paste it here. DocAnalyser stores it on your computer so "
            "you never need to do this again."
        )
        self._link_button("Open HuggingFace token page", URL_TOKENS)

        instructions = (
            "On that page:\n"
            "  1.  Click  'New token'\n"
            "  2.  Give it any name, e.g.  DocAnalyser\n"
            "  3.  Select  'Read'  (not 'Write')\n"
            "  4.  Click  'Generate a token'\n"
            "  5.  Copy the token (it starts with  hf_...)\n"
            "  6.  Paste it in the box below"
        )
        self._body(instructions)

        # Token entry
        entry_frame = tk.Frame(self._content, bg=BG)
        entry_frame.pack(fill=tk.X, pady=(4, 4))

        tk.Label(
            entry_frame, text="Paste token here:",
            font=FONT_BODY, bg=BG, fg=FG,
        ).pack(anchor="w")

        self._token_entry = tk.Entry(
            entry_frame,
            textvariable=self._token_var,
            font=FONT_MONO, width=52,
            relief=tk.SOLID, bd=1,
            show="•",   # mask by default for privacy
        )
        self._token_entry.pack(fill=tk.X, pady=(4, 2))
        self._token_entry.bind("<KeyRelease>", self._on_token_changed)
        self._token_entry.bind("<FocusIn>",
                               lambda e: self._token_entry.config(show=""))
        self._token_entry.bind("<FocusOut>",
                               lambda e: self._token_entry.config(show="•"))

        self._token_status = tk.Label(
            entry_frame, text="",
            font=FONT_SMALL, bg=BG, fg=FG_MUTED, anchor="w",
        )
        self._token_status.pack(anchor="w")

    def _on_token_changed(self, _event=None):
        token = self._token_var.get().strip()
        if token.startswith("hf_") and len(token) >= 20:
            self._token_status.config(
                text="Token looks valid.", fg=FG_SUCCESS
            )
            self._next_btn.config(
                state=tk.NORMAL, bg="#1565c0", fg="white"
            )
        elif token:
            self._token_status.config(
                text="Token should start with  hf_  and be at least 20 characters.",
                fg=FG_ERROR,
            )
            self._next_btn.config(state=tk.DISABLED, bg="#888888", fg="white")
        else:
            self._token_status.config(text="", fg=FG_MUTED)
            self._next_btn.config(state=tk.DISABLED, bg="#888888", fg="white")

    # ── Step 4: Download ──────────────────────────────────────────────────────

    def _step_4_download(self):
        self._next_btn.config(
            text="Download now", state=tk.NORMAL,
            bg="#2e7d32", fg="white",
        )
        self._back_btn.config(state=tk.DISABLED)
        self._cancel_btn.config(state=tk.DISABLED)

        self._heading("Step 4 of 4 — Download the model")

        self._body(
            "DocAnalyser will now download the speaker detection model to "
            "your computer. This is a one-time download of approximately "
            "1.5 GB and may take 10–20 minutes depending on your internet "
            "connection speed."
        )
        self._info_box(
            "After this download, the model lives on your computer permanently.\n"
            "No internet connection is needed for future use.\n"
            "Your audio recordings never leave your computer — "
            "all processing happens locally.",
            colour="#e8f5e9", border="#2e7d32",
        )
        self._body(
            "Click 'Download now' and keep this window open until the "
            "download completes. You can continue working in DocAnalyser "
            "while it runs.",
            colour=FG_MUTED,
        )

        self._separator(pady=6)

        # Progress area (hidden until download starts)
        self._progress_frame = tk.Frame(self._content, bg=BG)
        self._progress_frame.pack(fill=tk.X, pady=(4, 0))

        self._progress_label = tk.Label(
            self._progress_frame, text="",
            font=FONT_SMALL, bg=BG, fg=FG_MUTED,
            anchor="w", justify=tk.LEFT,
            wraplength=WIZARD_W - 52,
        )
        self._progress_label.pack(fill=tk.X)

        self._progress_bar = ttk.Progressbar(
            self._progress_frame,
            mode="indeterminate", length=WIZARD_W - 52,
        )
        # Not packed yet — shown when download starts

        self._progress_detail = tk.Label(
            self._progress_frame, text="",
            font=FONT_SMALL, bg=BG, fg=FG_MUTED,
            anchor="w", justify=tk.LEFT,
            wraplength=WIZARD_W - 52,
        )
        self._progress_detail.pack(fill=tk.X)

    def _start_download(self):
        """Called when user clicks 'Download now' on step 4."""
        self._next_btn.config(state=tk.DISABLED, text="Downloading...",
                              bg="#888888")
        self._back_btn.config(state=tk.DISABLED)
        self._cancel_btn.config(state=tk.DISABLED)

        self._progress_bar.pack(fill=tk.X, pady=(4, 4))
        self._progress_bar.start(12)

        token = self._token_var.get().strip()

        def _run():
            try:
                import diarization_handler
                success, message = diarization_handler.download_model(
                    hf_token=token,
                    progress_callback=self._download_progress,
                )
                self.win.after(0, self._download_finished, success, message)
            except Exception as e:
                self.win.after(0, self._download_finished, False, str(e))

        threading.Thread(target=_run, daemon=True).start()

    def _download_progress(self, message: str, percent: int = -1):
        """Called from background thread — must schedule UI update via after()."""
        def _update():
            self._progress_label.config(text=message)
            if percent >= 0:
                self._progress_bar.stop()
                self._progress_bar.config(mode="determinate")
                self._progress_bar["value"] = percent
            else:
                if self._progress_bar["mode"] != "indeterminate":
                    self._progress_bar.config(mode="indeterminate")
                    self._progress_bar.start(12)
        self.win.after(0, _update)

    def _download_finished(self, success: bool, message: str):
        """Called on the main thread when download completes."""
        self._progress_bar.stop()
        self._back_btn.config(state=tk.DISABLED)

        if success:
            self._download_done = True
            self._progress_bar.config(mode="determinate")
            self._progress_bar["value"] = 100
            self._progress_label.config(
                text="Download complete.",
                fg=FG_SUCCESS,
            )
            self._progress_detail.config(
                text="Voice speaker detection is now available.\n"
                     "Click 'Finish' to close this wizard.",
                fg=FG_SUCCESS,
            )
            self._next_btn.config(
                text="Finish", state=tk.NORMAL,
                bg=FG_SUCCESS, fg="white",
            )

            # Save token via callback
            token = self._token_var.get().strip()
            if self.config_save_callback:
                try:
                    self.config_save_callback(token)
                except Exception as e:
                    logger.warning(f"Could not save HF token to config: {e}")

            self.result_token = token

        else:
            self._progress_label.config(
                text="Download failed.", fg=FG_ERROR
            )
            self._progress_detail.config(text=message, fg=FG_ERROR)
            self._next_btn.config(
                text="Try again", state=tk.NORMAL,
                bg="#c62828", fg="white",
            )
            self._back_btn.config(state=tk.NORMAL)
            self._cancel_btn.config(state=tk.NORMAL)

    # ── Navigation ────────────────────────────────────────────────────────────

    def _on_next(self):
        step = self._current_step

        if step == 3:
            # Step 4 button is either "Download now", "Try again", or "Finish"
            if self._download_done:
                self.win.destroy()
            else:
                self._start_download()
            return

        # Steps 1-3: just advance
        if step == 2:
            # Validate token before advancing to download
            token = self._token_var.get().strip()
            if not (token.startswith("hf_") and len(token) >= 20):
                messagebox.showwarning(
                    "Token required",
                    "Please paste a valid HuggingFace token before continuing.\n\n"
                    "The token should start with  hf_  and be at least 20 characters.",
                    parent=self.win,
                )
                return

        self._show_step(step + 1)

    def _on_back(self):
        if self._current_step > 0:
            self._show_step(self._current_step - 1)

    def _on_cancel(self):
        if self._download_done:
            # Download already succeeded — just close
            self.win.destroy()
            return

        if messagebox.askyesno(
            "Cancel setup",
            "Are you sure you want to cancel the setup?\n\n"
            "Voice speaker detection will not be available until\n"
            "you complete the setup.",
            parent=self.win,
        ):
            self.result_token = None
            self.win.destroy()


# ============================================================================
# CONVENIENCE FUNCTIONS  (called from DocAnalyser)
# ============================================================================

def run_hf_setup_wizard(
        parent: tk.Tk,
        config_save_callback: Optional[Callable[[str], None]] = None,
) -> Optional[str]:
    """
    Show the HuggingFace setup wizard and block until it closes.

    Args:
        parent:               DocAnalyser's root Tk window.
        config_save_callback: function(token: str) — called on successful
                              completion to save the token to DocAnalyser config.
                              If None, the token is returned but not saved.

    Returns:
        The HuggingFace token string if setup completed successfully,
        or None if the user cancelled or setup failed.
    """
    wizard = HFSetupWizard(parent, config_save_callback)
    parent.wait_window(wizard.win)
    return wizard.result_token


def show_already_configured(parent: tk.Tk):
    """
    Show a simple info dialog when the user tries to open the wizard
    but setup is already complete.
    """
    messagebox.showinfo(
        "Voice Speaker Detection",
        "Voice speaker detection is already set up and ready to use.\n\n"
        "You can re-run the setup from Settings if you need to update\n"
        "your HuggingFace token or re-download the model.",
        parent=parent,
    )


def show_setup_required_prompt(parent: tk.Tk) -> bool:
    """
    Ask the user whether they want to run the setup wizard now.
    Called when voice diarization is selected but not yet configured.

    Returns True if the user wants to proceed with setup, False to skip.
    """
    return messagebox.askyesno(
        "One-time setup required",
        "Voice speaker detection requires a one-time setup.\n\n"
        "This involves creating a free account on HuggingFace and\n"
        "downloading a speaker detection model (~1.5 GB).\n\n"
        "Once done, the model lives on your computer permanently —\n"
        "no internet connection is needed for future use.\n\n"
        "Would you like to set this up now?",
        parent=parent,
    )


# ============================================================================
# STANDALONE PREVIEW  (run this file directly to preview the wizard)
# ============================================================================

if __name__ == "__main__":
    root = tk.Tk()
    root.title("DocAnalyser — Wizard Preview")
    root.geometry("900x600")
    root.configure(bg="#f0f0f0")

    # Simulate DocAnalyser's main window
    tk.Label(
        root, text="DocAnalyser (preview)",
        font=("Arial", 14), bg="#f0f0f0",
    ).pack(pady=20)

    def _save_token(token: str):
        print(f"[Config save callback] Token saved: {token[:8]}...")

    def _open_wizard():
        token = run_hf_setup_wizard(root, _save_token)
        if token:
            print(f"Setup complete. Token: {token[:8]}...")
            result_label.config(
                text=f"Setup complete. Token starts with: {token[:8]}",
                fg="#2e7d32",
            )
        else:
            print("Setup cancelled.")
            result_label.config(text="Setup cancelled.", fg="#c62828")

    tk.Button(
        root, text="Open Setup Wizard",
        command=_open_wizard,
        font=("Arial", 11), padx=16, pady=8,
    ).pack(pady=10)

    result_label = tk.Label(root, text="", font=("Arial", 10), bg="#f0f0f0")
    result_label.pack(pady=8)

    root.mainloop()
