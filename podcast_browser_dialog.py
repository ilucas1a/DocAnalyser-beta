"""
podcast_browser_dialog.py - Podcast Episode Browser Dialog
============================================================
A Tkinter dialog that displays podcast episodes from an RSS feed,
allowing the user to search, filter, select one or more episodes,
and save the podcast to favourites.

Called from smart_load.py (for feed URLs) and document_fetching.py.
Does NOT touch Main.py.

Usage:
    from podcast_browser_dialog import open_podcast_browser
    
    selected_episodes, podcast_info = open_podcast_browser(
        parent=root_window,
        url="https://feeds.megaphone.fm/provoked",
        config=app_config,
        save_config_callback=save_config_func
    )
    # selected_episodes is a list of PodcastEpisode objects, or empty if cancelled
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import logging
import re
from typing import List, Optional, Callable, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Import podcast handler types
try:
    from podcast_handler import (
        PodcastEpisode, PodcastInfo,
        resolve_podcast_feed
    )
    PODCAST_HANDLER_AVAILABLE = True
except ImportError:
    PODCAST_HANDLER_AVAILABLE = False


class PodcastBrowserDialog:
    """
    Dialog window for browsing and selecting podcast episodes.
    
    Shows all episodes from a podcast feed with search/filter,
    multi-select checkboxes, and favourites support.
    """
    
    def __init__(self, parent: tk.Tk, url: str, config: dict,
                 save_config_callback: Optional[Callable] = None,
                 podcast_info: Optional['PodcastInfo'] = None):
        """
        Args:
            parent: Parent Tkinter window
            url: Podcast feed URL or Apple Podcasts URL
            config: App config dict (for saved_podcasts)
            save_config_callback: Function to persist config changes
            podcast_info: Pre-resolved PodcastInfo (skip resolution if provided)
        """
        self.parent = parent
        self.url = url
        self.config = config
        self.save_config_callback = save_config_callback
        self.podcast_info: Optional[PodcastInfo] = podcast_info
        self.all_episodes: List[PodcastEpisode] = []
        self.selected_episodes: List[PodcastEpisode] = []
        self.check_vars: dict = {}  # episode index → BooleanVar
        self._cancelled = True
        
        # Build the dialog
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("🎙️ Podcast Browser")
        self.dialog.geometry("700x560")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        # Centre on screen
        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() // 2) - 350
        y = (self.dialog.winfo_screenheight() // 2) - 280
        self.dialog.geometry(f"+{x}+{y}")
        
        self._build_ui()
        
        # If podcast_info already provided, populate immediately
        if self.podcast_info and self.podcast_info.episodes:
            self.all_episodes = list(self.podcast_info.episodes)
            self._populate_episodes()
        else:
            # Resolve feed in background
            self._start_resolution()
        
        self.dialog.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.dialog.bind('<Escape>', lambda e: self._on_cancel())
    
    def _build_ui(self):
        """Build the dialog UI."""
        # ---- Header section ----
        header_frame = ttk.Frame(self.dialog)
        header_frame.pack(fill=tk.X, padx=15, pady=(12, 5))
        
        self.title_label = ttk.Label(
            header_frame, text="Loading podcast...",
            font=('Arial', 12, 'bold')
        )
        self.title_label.pack(anchor=tk.W)
        
        self.subtitle_label = ttk.Label(
            header_frame, text="",
            font=('Arial', 9), foreground='gray'
        )
        self.subtitle_label.pack(anchor=tk.W)
        
        # ---- Search / filter row ----
        search_frame = ttk.Frame(self.dialog)
        search_frame.pack(fill=tk.X, padx=15, pady=(8, 4))
        
        ttk.Label(search_frame, text="🔍").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_var.trace_add('write', self._on_search_changed)
        self.search_entry = ttk.Entry(
            search_frame, textvariable=self.search_var,
            font=('Arial', 10), width=40
        )
        self.search_entry.pack(side=tk.LEFT, padx=(5, 10), fill=tk.X, expand=True)
        
        # Episode count label
        self.count_label = ttk.Label(search_frame, text="", font=('Arial', 9))
        self.count_label.pack(side=tk.RIGHT)
        
        # ---- Episode list ----
        list_frame = ttk.Frame(self.dialog)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Canvas + inner frame for checkboxes (Treeview doesn't support checkboxes natively)
        self.canvas = tk.Canvas(list_frame, yscrollcommand=scrollbar.set, highlightthickness=0)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.canvas.yview)
        
        self.episodes_frame = ttk.Frame(self.canvas)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.episodes_frame, anchor='nw')
        
        # Bind resize/scroll events
        self.episodes_frame.bind('<Configure>', self._on_frame_configure)
        self.canvas.bind('<Configure>', self._on_canvas_configure)
        self.canvas.bind_all('<MouseWheel>', self._on_mousewheel)
        
        # ---- Status / loading indicator ----
        self.status_label = ttk.Label(
            self.dialog, text="⏳ Resolving feed...",
            font=('Arial', 9), foreground='gray'
        )
        self.status_label.pack(fill=tk.X, padx=15, pady=(0, 5))
        
        # ---- Button row ----
        btn_frame = ttk.Frame(self.dialog)
        btn_frame.pack(fill=tk.X, padx=15, pady=(5, 12))
        
        # Left side: Select All, Clear, Favourites
        left_btns = ttk.Frame(btn_frame)
        left_btns.pack(side=tk.LEFT)
        
        ttk.Button(left_btns, text="Select All", command=self._select_all, width=10).pack(side=tk.LEFT, padx=(0, 3))
        ttk.Button(left_btns, text="Clear", command=self._clear_all, width=7).pack(side=tk.LEFT, padx=(0, 8))
        
        self.fav_btn = ttk.Button(left_btns, text="⭐ Save to Favourites", command=self._toggle_favourite, width=20)
        self.fav_btn.pack(side=tk.LEFT, padx=(0, 3))
        self._update_fav_button()
        
        # Right side: Load & Cancel
        right_btns = ttk.Frame(btn_frame)
        right_btns.pack(side=tk.RIGHT)
        
        ttk.Button(right_btns, text="Cancel", command=self._on_cancel, width=10).pack(side=tk.RIGHT, padx=(5, 0))
        self.load_btn = ttk.Button(right_btns, text="Load && Transcribe", command=self._on_load, width=18)
        self.load_btn.pack(side=tk.RIGHT)
    
    # --------------------------------------------------
    # Feed resolution (background thread)
    # --------------------------------------------------
    
    def _start_resolution(self):
        """Start resolving the podcast feed in a background thread."""
        self.load_btn.config(state=tk.DISABLED)
        
        def resolve_thread():
            try:
                success, error, podcast_info = resolve_podcast_feed(
                    self.url,
                    progress_callback=lambda msg: self.dialog.after(
                        0, lambda m=msg: self.status_label.config(text=m)
                    )
                )
                if success and podcast_info:
                    self.podcast_info = podcast_info
                    self.all_episodes = list(podcast_info.episodes)
                    self.dialog.after(0, self._populate_episodes)
                else:
                    self.dialog.after(0, lambda: self._show_error(error or "Failed to load feed"))
            except Exception as e:
                logger.error(f"Feed resolution error: {e}")
                self.dialog.after(0, lambda: self._show_error(str(e)))
        
        threading.Thread(target=resolve_thread, daemon=True).start()
    
    def _show_error(self, msg):
        """Show error state in the dialog."""
        self.status_label.config(text=f"❌ {msg}")
        self.title_label.config(text="Failed to load podcast")
    
    # --------------------------------------------------
    # Episode list population
    # --------------------------------------------------
    
    def _populate_episodes(self, filter_text: str = ""):
        """Populate the episode list, optionally filtered."""
        # Clear existing
        for widget in self.episodes_frame.winfo_children():
            widget.destroy()
        self.check_vars.clear()
        
        # Update header
        if self.podcast_info:
            self.title_label.config(text=f"🎙️ {self.podcast_info.name}")
            author = self.podcast_info.author
            ep_count = len(self.all_episodes)
            subtitle_parts = []
            if author:
                subtitle_parts.append(author)
            subtitle_parts.append(f"{ep_count} episodes")
            self.subtitle_label.config(text=" · ".join(subtitle_parts))
        
        # Filter episodes
        filter_lower = filter_text.lower().strip()
        visible_episodes = []
        for i, ep in enumerate(self.all_episodes):
            if filter_lower:
                searchable = f"{ep.title} {ep.description} {ep.published}".lower()
                if filter_lower not in searchable:
                    continue
            visible_episodes.append((i, ep))
        
        # Update count
        if filter_lower:
            self.count_label.config(text=f"Showing {len(visible_episodes)} of {len(self.all_episodes)}")
        else:
            self.count_label.config(text=f"{len(self.all_episodes)} episodes")
        
        # Populate rows
        for row_idx, (ep_idx, ep) in enumerate(visible_episodes):
            row = ttk.Frame(self.episodes_frame)
            row.pack(fill=tk.X, padx=2, pady=1)
            
            # Checkbox
            var = tk.BooleanVar(value=False)
            self.check_vars[ep_idx] = var
            cb = ttk.Checkbutton(row, variable=var, command=self._update_load_button)
            cb.pack(side=tk.LEFT, padx=(2, 5))
            
            # Episode info
            info_frame = ttk.Frame(row)
            info_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
            
            # Title (clickable to toggle checkbox)
            title_text = ep.title
            if len(title_text) > 75:
                title_text = title_text[:72] + "..."
            title_lbl = ttk.Label(
                info_frame, text=title_text,
                font=('Arial', 10, 'bold'), cursor='hand2'
            )
            title_lbl.pack(anchor=tk.W)
            title_lbl.bind('<Button-1>', lambda e, v=var: v.set(not v.get()) or self._update_load_button())
            
            # Date + duration line
            meta_parts = []
            if ep.published:
                # Try to format date nicely
                date_str = self._format_date(ep.published)
                meta_parts.append(date_str)
            if ep.duration:
                meta_parts.append(self._format_duration(ep.duration))
            
            if meta_parts:
                meta_lbl = ttk.Label(
                    info_frame, text=" · ".join(meta_parts),
                    font=('Arial', 8), foreground='gray'
                )
                meta_lbl.pack(anchor=tk.W)
            
            # Subtle separator
            if row_idx < len(visible_episodes) - 1:
                ttk.Separator(self.episodes_frame, orient='horizontal').pack(fill=tk.X, padx=10, pady=1)
        
        # Enable UI
        self.load_btn.config(state=tk.NORMAL)
        self.status_label.config(text="Select one or more episodes, then click Load & Transcribe")
        self._update_load_button()
        self._update_fav_button()
        
        # Reset scroll position
        self.canvas.yview_moveto(0)
    
    # --------------------------------------------------
    # Selection helpers
    # --------------------------------------------------
    
    def _get_selected_count(self) -> int:
        return sum(1 for v in self.check_vars.values() if v.get())
    
    def _update_load_button(self, *args):
        count = self._get_selected_count()
        if count == 0:
            self.load_btn.config(text="Load && Transcribe")
        elif count == 1:
            self.load_btn.config(text="Load && Transcribe (1)")
        else:
            self.load_btn.config(text=f"Load && Transcribe ({count})")
    
    def _select_all(self):
        for v in self.check_vars.values():
            v.set(True)
        self._update_load_button()
    
    def _clear_all(self):
        for v in self.check_vars.values():
            v.set(False)
        self._update_load_button()
    
    # --------------------------------------------------
    # Favourites
    # --------------------------------------------------
    
    def _is_favourite(self) -> bool:
        saved = self.config.get("saved_podcasts", [])
        return any(p.get("url") == self.url or p.get("feed_url") == getattr(self.podcast_info, 'feed_url', '') 
                   for p in saved)
    
    def _update_fav_button(self):
        if self._is_favourite():
            self.fav_btn.config(text="⭐ Remove from Favourites")
        else:
            self.fav_btn.config(text="☆ Save to Favourites")
    
    def _toggle_favourite(self):
        saved = self.config.get("saved_podcasts", [])
        
        if self._is_favourite():
            # Remove
            saved = [p for p in saved 
                     if p.get("url") != self.url and 
                     p.get("feed_url") != getattr(self.podcast_info, 'feed_url', '')]
            self.config["saved_podcasts"] = saved
        else:
            # Add
            entry = {
                "name": self.podcast_info.name if self.podcast_info else "Unknown",
                "url": self.url,
                "feed_url": self.podcast_info.feed_url if self.podcast_info else self.url,
                "author": self.podcast_info.author if self.podcast_info else ""
            }
            saved.append(entry)
            self.config["saved_podcasts"] = saved
        
        # Persist
        if self.save_config_callback:
            try:
                self.save_config_callback()
            except Exception as e:
                logger.warning(f"Could not save config: {e}")
        
        self._update_fav_button()
    
    # --------------------------------------------------
    # Search / filter
    # --------------------------------------------------
    
    def _on_search_changed(self, *args):
        self._populate_episodes(filter_text=self.search_var.get())
    
    # --------------------------------------------------
    # Scroll / resize handlers
    # --------------------------------------------------
    
    def _on_frame_configure(self, event):
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))
    
    def _on_canvas_configure(self, event):
        self.canvas.itemconfig(self.canvas_window, width=event.width)
    
    def _on_mousewheel(self, event):
        # Only scroll if the dialog is active
        if self.dialog.winfo_exists():
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')
    
    # --------------------------------------------------
    # OK / Cancel
    # --------------------------------------------------
    
    def _on_load(self):
        """Gather selected episodes and close."""
        self.selected_episodes = []
        for ep_idx, var in self.check_vars.items():
            if var.get():
                self.selected_episodes.append(self.all_episodes[ep_idx])
        
        if not self.selected_episodes:
            messagebox.showinfo("No Selection", "Please select at least one episode.", parent=self.dialog)
            return
        
        self._cancelled = False
        # Unbind mousewheel before destroying to avoid errors
        self.canvas.unbind_all('<MouseWheel>')
        self.dialog.destroy()
    
    def _on_cancel(self):
        self.selected_episodes = []
        self._cancelled = True
        self.canvas.unbind_all('<MouseWheel>')
        self.dialog.destroy()
    
    # --------------------------------------------------
    # Date/time formatting helpers
    # --------------------------------------------------
    
    @staticmethod
    def _format_date(date_str: str) -> str:
        """Try to format a published date string nicely."""
        try:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(date_str)
            return dt.strftime('%d %b %Y')
        except Exception:
            # Return first ~16 chars as fallback
            return date_str[:16] if len(date_str) > 16 else date_str
    
    @staticmethod
    def _format_duration(duration) -> str:
        """Format duration to a readable string."""
        try:
            dur_str = str(duration)
            if ':' in dur_str:
                return dur_str  # Already formatted
            secs = int(dur_str)
            hours, remainder = divmod(secs, 3600)
            mins, secs = divmod(remainder, 60)
            if hours:
                return f"{hours}h {mins:02d}m"
            return f"{mins}m {secs:02d}s"
        except Exception:
            return str(duration)


# ============================================================
# PUBLIC API
# ============================================================

def open_podcast_browser(
    parent: tk.Tk,
    url: str,
    config: dict,
    save_config_callback: Optional[Callable] = None,
    podcast_info: Optional['PodcastInfo'] = None
) -> Tuple[List['PodcastEpisode'], Optional['PodcastInfo']]:
    """
    Open the Podcast Browser dialog and wait for user selection.
    
    Args:
        parent: Parent Tkinter window
        url: Podcast feed or Apple Podcasts URL
        config: App config dict
        save_config_callback: Function to persist config
        podcast_info: Pre-resolved PodcastInfo (optional, skips resolution)
    
    Returns:
        (selected_episodes, podcast_info) — episodes is empty list if cancelled
    """
    if not PODCAST_HANDLER_AVAILABLE:
        messagebox.showerror(
            "Missing Dependencies",
            "Podcast support requires:\n\n"
            "  pip install feedparser\n\n"
            "Install and restart DocAnalyser.",
            parent=parent
        )
        return [], None
    
    browser = PodcastBrowserDialog(
        parent=parent,
        url=url,
        config=config,
        save_config_callback=save_config_callback,
        podcast_info=podcast_info
    )
    
    # Wait for dialog to close
    parent.wait_window(browser.dialog)
    
    return browser.selected_episodes, browser.podcast_info
