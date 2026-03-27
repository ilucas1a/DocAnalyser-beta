"""
transcript_paragraph_editor.py
================================
Structured paragraph editor for audio transcripts in DocAnalyser.

Unlike the previous free-text approach, this editor maintains the entries
list as the *source of truth*.  The tk.Text widget is a rendered view —
it never needs to be parsed back to reconstruct structure.

Key capabilities
----------------
- Word-level corrections within any sentence
- Paragraph splitting at any sentence boundary (click "Split here")
- Speaker reassignment via click on the speaker label
- Full sentence-level audio click-to-seek preserved through all edits
- Robust save: timestamps survive every editing operation intact

Architecture
------------
Each entry maps to a paragraph block in the text widget.  Two Tkinter
*marks* anchor each block:

    para_start_N   — left-gravity mark at the very start of the block
                     (before the [timestamp] header)
    para_text_N    — left-gravity mark immediately after the header,
                     at the first character of spoken text

On save, the editor reads text from para_text_N to para_start_{N+1}
(or END) for each entry, strips any leading/trailing whitespace, and
distributes the edited text across the original sentence timestamps
proportionally.  Structural edits (split / merge) update self._entries
directly, so their timestamps are always exact.

Integration
-----------
    editor = TranscriptParagraphEditor(
        text_widget  = self.thread_text,
        entries      = self.current_entries,
        doc_id       = self.current_document_id,
        config       = self.config,
        player       = self.transcript_player,   # may be None
        save_callback = lambda entries: setattr(self.app, 'current_entries', entries),
    )
    editor.render()

Author: DocAnalyser Development Team
"""

from __future__ import annotations

import re
import tkinter as tk
from tkinter import messagebox
from typing import List, Dict, Optional, Callable, Tuple

# ---------------------------------------------------------------------------
# TAG / MARK CONSTANTS
# ---------------------------------------------------------------------------
TAG_CLICKABLE  = "seg_click"   # applied to every sentence span
TAG_HIGHLIGHT  = "player_highlight"  # current-playback highlight
SEG_PREFIX     = "seg_"        # prefix for per-sentence tags: seg_0, seg_1 …


class TranscriptParagraphEditor:
    """
    Structured editor for audio transcript paragraphs.

    All editing operations update self._entries (the source of truth).
    The tk.Text widget is re-rendered after structural changes.
    For word-level edits the widget is left editable and synced on save.
    """

    def __init__(
        self,
        text_widget:   tk.Text,
        entries:       List[Dict],
        doc_id:        Optional[str],
        config:        Dict,
        player=None,                        # TranscriptPlayer instance, may be None
        save_callback: Optional[Callable] = None,   # called with new entries after save
        preview_callback: Optional[Callable] = None, # called with split-preview string
    ):
        self.tw             = text_widget
        self._entries       = [dict(e) for e in (entries or [])]
        self.doc_id         = doc_id
        self.config         = config
        self.player         = player
        self.save_callback  = save_callback

        self._edit_mode     = False
        self.preview_callback = preview_callback
        self.undo_state_callback = None
        self.paragraph_click_callback = None
        self._pending_split_entry: Optional[int] = None
        self._pending_split_char_offset: Optional[int] = None
        self._segment_map: List[Tuple[int, int, float]] = []
        self._n_paragraphs  = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def render(self, speaker_filter: Optional[str] = None,
                restore_scroll: Optional[float] = None):
        """
        Clear the text widget and render all entries as paragraph blocks.
        Sentence-level click-to-seek tags are set up automatically.
        restore_scroll: if given, yview_moveto(restore_scroll) is called at
        the end of render, after all content is inserted.
        """
        tw = self.tw
        tw.config(state=tk.NORMAL)
        tw.delete("1.0", tk.END)

        for i in range(self._n_paragraphs + 2):
            for kind in ("para_start", "para_text"):
                try:
                    tw.mark_unset(f"{kind}_{i}")
                except Exception:
                    pass

        self._segment_map = []
        seg_idx = 0

        ts_interval  = self.config.get("timestamp_interval", "every_segment")
        interval_map = {
            "every_segment": 0,
            "1min": 60, "5min": 300, "10min": 600, "never": float("inf"),
        }
        interval_secs = interval_map.get(ts_interval, 0)
        last_ts_time  = -interval_secs
        font_size = self.config.get("font_size", 10)

        for entry_idx, entry in enumerate(self._entries):
            speaker = entry.get("speaker", "")
            if speaker_filter and speaker.strip() != speaker_filter:
                continue

            start = entry.get("start", 0.0)

            mark_start = f"para_start_{entry_idx}"
            tw.mark_set(mark_start, tk.END)
            tw.mark_gravity(mark_start, tk.LEFT)

            show_ts = (
                ts_interval == "every_segment"
                or (start - last_ts_time) >= interval_secs
            )
            header = ""
            if show_ts and ts_interval != "never":
                header += f"[{self._fmt_time(start)}] "
                last_ts_time = start
            if speaker and speaker_filter is None:
                header += f"[{speaker}]: "

            if header:
                spk_tag = f"speaker_{entry_idx}"
                provisional = entry.get("provisional", False)
                if provisional:
                    tw.tag_configure(spk_tag, foreground="#aaaaaa",
                                     font=("Arial", font_size, "italic"))
                else:
                    tw.tag_configure(spk_tag, foreground="#555555",
                                     font=("Arial", font_size))
                tw.insert(tk.END, header, ("source_text", spk_tag))
                tw.tag_bind(spk_tag, "<Button-1>",
                            lambda e, idx=entry_idx: self._on_speaker_click(idx))

            mark_text = f"para_text_{entry_idx}"
            tw.mark_set(mark_text, tk.END)
            tw.mark_gravity(mark_text, tk.LEFT)
            if entry_idx < 3:
                print(f"\U0001f3b5 render mark {mark_text} set at {tw.index(tk.END)!r}",
                      flush=True)

            sentences = entry.get("sentences", [])
            if sentences and len(sentences) > 1:
                for sent_idx, sent in enumerate(sentences):
                    tag = f"{SEG_PREFIX}{seg_idx}"
                    sent_text  = sent.get("text", "")
                    sent_start = float(sent.get("start", start))
                    tw.insert(tk.END, sent_text, (tag, TAG_CLICKABLE, "source_text"))
                    self._segment_map.append((entry_idx, sent_idx, sent_start))
                    seg_idx += 1
                    if sent_idx < len(sentences) - 1:
                        tw.insert(tk.END, " ", "source_text")
            else:
                tag  = f"{SEG_PREFIX}{seg_idx}"
                text = entry.get("text", "")
                tw.insert(tk.END, text, (tag, TAG_CLICKABLE, "source_text"))
                self._segment_map.append((entry_idx, 0, float(start)))
                seg_idx += 1

            tw.insert(tk.END, "\n\n", "source_text")

        self._n_paragraphs = len(self._entries)

        tw.tag_bind(TAG_CLICKABLE, "<Button-1>", self._on_segment_click)
        tw.tag_configure(TAG_HIGHLIGHT, background="#FFF3CD", relief="flat")
        tw.tag_bind(TAG_CLICKABLE, "<Enter>", lambda e: tw.configure(cursor="hand2"))
        tw.tag_bind(TAG_CLICKABLE, "<Leave>", lambda e: tw.configure(cursor=""))

        if not self._edit_mode:
            tw.config(state=tk.DISABLED)
            # Flush deferred Windows scroll events generated by DISABLED transition
            # so they fire BEFORE yview_moveto rather than after.
            tw.update_idletasks()

        if self.player is not None:
            self.player.playback_segments = [
                {"start": s[2], "text": "", "speaker": "", "is_first_in_entry": True}
                for s in self._segment_map
            ]

        if restore_scroll is not None:
            tw.yview_moveto(restore_scroll)
            # Lock the scroll position for 500ms by intercepting yscrollcommand.
            # Windows sends WM_PAINT/WM_SETFOCUS messages after geometry changes
            # that fire via mainloop and override our yview_moveto.  By locking
            # yscrollcommand we absorb those events without letting them move
            # the viewport.  The lock is released after 500ms.
            _locked_pos = restore_scroll
            _orig_ysc = tw.cget('yscrollcommand')
            def _locked_yscroll(first, last):
                # While locked: restore our position, then pass through to scrollbar
                tw.yview_moveto(_locked_pos)
                if _orig_ysc:
                    try:
                        _orig_ysc(first, last)
                    except Exception:
                        pass
            tw.config(yscrollcommand=_locked_yscroll)
            def _unlock():
                tw.config(yscrollcommand=_orig_ysc or '')
            tw.after(500, _unlock)

        tw.edit_modified(False)
        if self.player is not None:
            self.player._current_seg_idx = -1
            import time as _time
            self.player._scroll_suppressed_until = _time.time() + 1.0

    def enter_edit_mode(self):
        """Enable text editing; suppress click-to-seek."""
        self._edit_mode = True
        self.tw.config(state=tk.NORMAL, cursor="xterm")
        self.tw.bind("<Return>", self._on_enter_key)
        if self.player is not None:
            self.player.edit_mode = True
        self.tw.bind("<KeyRelease>", self._update_split_preview)
        self.tw.bind("<ButtonRelease-1>", self._on_button_release_edit)
        self.tw.after(50, self._update_split_preview)

    def _on_button_release_edit(self, event=None):
        if self.paragraph_click_callback is not None:
            return
        self._update_split_preview(event)

    def _on_enter_key(self, event=None):
        if self.paragraph_click_callback is None:
            self.split_paragraph_at_cursor()
        return "break"

    def exit_edit_mode(self):
        """
        Save word-level edits from the widget into self._entries,
        then re-render and return to audio-link mode.
        Scroll position is preserved so the viewport stays where the user
        was editing rather than jumping to the top of the document.
        """
        scroll_pos = self.tw.yview()[0]

        self._sync_from_widget()
        self._save_to_library()
        self._edit_mode = False
        self.tw.unbind("<Return>")
        self.tw.unbind("<KeyRelease>")
        self.tw.unbind("<ButtonRelease-1>")
        self._pending_split_entry = None
        self._pending_split_char_offset = None
        if self.preview_callback:
            self.preview_callback("")
        self.render(restore_scroll=scroll_pos)
        if self.player is not None:
            self.player.edit_mode = False

    def split_paragraph_at_cursor(self):
        """
        WYSIWYG split: divide the paragraph at the nearest sentence-ending
        punctuation mark (.  ?  !) to the cursor.
        """
        if not self._edit_mode:
            return

        entry_idx   = self._pending_split_entry
        char_offset = self._pending_split_char_offset

        if entry_idx is None or char_offset is None:
            cursor    = self.tw.index(tk.INSERT)
            entry_idx = self._find_entry_at_cursor(cursor)
            if entry_idx is None:
                print("\u2702\ufe0f  split: no entry found at cursor, aborting", flush=True)
                return
            char_offset = self._cursor_to_para_char_offset(cursor, entry_idx)
            if char_offset is None:
                return

        self._pending_split_entry       = None
        self._pending_split_char_offset = None

        entry    = self._entries[entry_idx]
        raw_text = entry.get("text", "").strip()
        if not raw_text:
            return

        split_pos = self._nearest_sentence_end(raw_text, char_offset)
        if split_pos is None or split_pos <= 0 or split_pos >= len(raw_text):
            messagebox.showinfo(
                "Cannot split",
                "Could not find a sentence boundary near the cursor.\n\n"
                "Click inside a sentence that ends with . ? or !",
                parent=self.tw.winfo_toplevel(),
            )
            return

        text_a = raw_text[:split_pos].strip()
        text_b = raw_text[split_pos:].strip()

        if not text_a or not text_b:
            messagebox.showinfo(
                "Cannot split",
                "The split would leave one paragraph empty. "
                "Try clicking further into the paragraph.",
                parent=self.tw.winfo_toplevel(),
            )
            return

        print(f"\u2702\ufe0f  WYSIWYG split entry {entry_idx} at char {split_pos}: "
              f"A={len(text_a)}ch B={len(text_b)}ch", flush=True)

        start_a  = float(entry.get("start", 0.0))
        end_a    = float(entry.get("end", start_a))
        duration = max(0.0, end_a - start_a)
        ratio    = split_pos / max(1, len(raw_text))
        start_b  = start_a + duration * ratio

        def _make_sentences(text, base_start, base_end):
            parts = [p.strip() for p in re.split(r'(?<=[.!?])\s+', text) if p.strip()]
            if not parts:
                parts = [text]
            total_chars = sum(len(p) for p in parts) or 1
            result = []
            t = float(base_start)
            dur = max(0.0, float(base_end) - float(base_start))
            for i, part in enumerate(parts):
                frac  = len(part) / total_chars
                t_end = t + dur * frac
                result.append({"text": part, "start": t, "end": t_end,
                                "speaker": entry.get("speaker", "")})
                t = t_end
            return result

        new_a = dict(entry)
        new_a["text"]      = text_a
        new_a["start"]     = start_a
        new_a["end"]       = start_b
        new_a["sentences"] = _make_sentences(text_a, start_a, start_b)

        new_b = dict(entry)
        new_b["text"]      = text_b
        new_b["start"]     = start_b
        new_b["end"]       = end_a
        new_b["sentences"] = _make_sentences(text_b, start_b, end_a)

        self._entries = (
            self._entries[:entry_idx] + [new_a, new_b] + self._entries[entry_idx + 1:]
        )

        self._save_to_library()
        self.render()
        self.enter_edit_mode()

        target_entry_idx = entry_idx + 1
        for seg_i, (e_idx, s_idx, _) in enumerate(self._segment_map):
            if e_idx == target_entry_idx and s_idx == 0:
                tag    = f"{SEG_PREFIX}{seg_i}"
                ranges = self.tw.tag_ranges(tag)
                if ranges:
                    self.tw.mark_set(tk.INSERT, ranges[0])
                    self.tw.see(ranges[0])
                break

        print(f"\u2702\ufe0f  Split done: A={len(new_a['sentences'])} sents "
              f"B={len(new_b['sentences'])} sents  start_b={start_b:.1f}s", flush=True)

    def merge_with_next(self, entry_idx: int):
        if entry_idx >= len(self._entries) - 1:
            return

        a = self._entries[entry_idx]
        b = self._entries[entry_idx + 1]

        merged       = dict(a)
        merged_sents = []
        for s in a.get("sentences", []) + b.get("sentences", []):
            clean = dict(s)
            clean["text"] = s.get("text", "").strip()
            if clean["text"]:
                merged_sents.append(clean)
        merged["sentences"] = merged_sents
        merged["text"]      = " ".join(s["text"] for s in merged_sents) \
                              or (a.get("text", "").strip() + " " + b.get("text", "").strip()).strip()
        merged["end"]       = b.get("end", b.get("start", a.get("end", 0)))

        self._entries = (
            self._entries[:entry_idx] + [merged] + self._entries[entry_idx + 2:]
        )

        self._save_to_library()
        self.render()
        if self._edit_mode:
            self.enter_edit_mode()
        print(f"🔗 Merged entries {entry_idx} and {entry_idx + 1}", flush=True)

    def get_entries(self) -> List[Dict]:
        return list(self._entries)

    def highlight_segment(self, seg_idx: int):
        tw = self.tw
        tw.tag_remove(TAG_HIGHLIGHT, "1.0", tk.END)
        tag = f"{SEG_PREFIX}{seg_idx}"
        ranges = tw.tag_ranges(tag)
        if ranges:
            tw.tag_add(TAG_HIGHLIGHT, ranges[0], ranges[1])
            tw.tag_raise(TAG_HIGHLIGHT)
            tw.see(ranges[0])

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _fmt_time(seconds: float) -> str:
        s = max(0, int(seconds))
        if s >= 3600:
            return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"
        return f"{s // 60:02d}:{s % 60:02d}"

    def _on_segment_click(self, event):
        idx  = self.tw.index(f"@{event.x},{event.y}")
        tags = self.tw.tag_names(idx)
        for tag in tags:
            suffix = tag[len(SEG_PREFIX):]
            if tag.startswith(SEG_PREFIX) and suffix.isdigit():
                seg_i = int(suffix)
                if seg_i < len(self._segment_map):
                    entry_idx, _, start_secs = self._segment_map[seg_i]
                    if self.paragraph_click_callback is not None:
                        self.paragraph_click_callback(entry_idx)
                        return
                    if not self._edit_mode and self.player is not None:
                        self.player.play(from_position=start_secs)
                break

    def _on_speaker_click(self, entry_idx: int):
        if not self._edit_mode:
            return

        entry   = self._entries[entry_idx]
        current = entry.get("speaker", "")

        dialog = tk.Toplevel(self.tw.winfo_toplevel())
        dialog.title("Change speaker")
        dialog.resizable(False, False)

        tk.Label(dialog, text="Speaker name:", font=("Arial", 10)).pack(padx=14, pady=(12, 4))
        var = tk.StringVar(value=current)
        ent = tk.Entry(dialog, textvariable=var, width=26, font=("Arial", 10))
        ent.pack(padx=14, pady=4)
        ent.select_range(0, tk.END)
        ent.focus_set()

        def _apply():
            new_name = var.get().strip()
            self._entries[entry_idx]["speaker"] = new_name
            if "sentences" in self._entries[entry_idx]:
                for s in self._entries[entry_idx]["sentences"]:
                    s["speaker"] = new_name
            dialog.destroy()
            self.render()
            self.enter_edit_mode()

        ent.bind("<Return>", lambda e: _apply())
        btn_row = tk.Frame(dialog)
        btn_row.pack(padx=14, pady=(4, 12))
        tk.Button(btn_row, text="OK",     command=_apply,         width=8).pack(side=tk.LEFT, padx=4)
        tk.Button(btn_row, text="Cancel", command=dialog.destroy, width=8).pack(side=tk.LEFT, padx=4)

        dialog.update_idletasks()
        parent = self.tw.winfo_toplevel()
        x = parent.winfo_x() + (parent.winfo_width()  - dialog.winfo_width())  // 2
        y = parent.winfo_y() + (parent.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")

    def _find_entry_at_cursor(self, cursor: str) -> Optional[int]:
        best = None
        for entry_idx in range(len(self._entries)):
            try:
                mark_pos = self.tw.index(f"para_start_{entry_idx}")
            except tk.TclError:
                continue
            if self.tw.compare(mark_pos, "<=", cursor):
                best = entry_idx
            else:
                break
        return best

    # ------------------------------------------------------------------
    # WYSIWYG split helpers
    # ------------------------------------------------------------------

    def _cursor_to_para_char_offset(self, cursor: str, entry_idx: int) -> Optional[int]:
        para_start_widget = None
        for seg_i, (e_idx, s_idx, _) in enumerate(self._segment_map):
            if e_idx == entry_idx and s_idx == 0:
                tag    = f"{SEG_PREFIX}{seg_i}"
                ranges = self.tw.tag_ranges(tag)
                if ranges:
                    para_start_widget = ranges[0]
                break

        if para_start_widget is None:
            return None

        try:
            offset = int(self.tw.count(para_start_widget, cursor, "chars")[0])
        except Exception:
            return None

        full_para_text = self._get_para_text_from_widget(entry_idx)
        if full_para_text is None:
            return None

        return max(0, min(offset, len(full_para_text)))

    def _get_para_text_from_widget(self, entry_idx: int) -> Optional[str]:
        """
        Extract the spoken text for entry_idx from the widget using
        segment tags — avoids marks which are unreliable.
        """
        first_seg      = None
        next_first_seg = None
        for seg_i, (e_idx, s_idx, _) in enumerate(self._segment_map):
            if e_idx == entry_idx and first_seg is None:
                first_seg = seg_i
            if e_idx > entry_idx and next_first_seg is None:
                next_first_seg = seg_i
                break

        if first_seg is None:
            return None

        first_ranges = self.tw.tag_ranges(f"seg_{first_seg}")
        if not first_ranges:
            return None
        try:
            block_start = self.tw.index(f"{first_ranges[0]} linestart")
        except Exception:
            return None

        block_end = tk.END
        if next_first_seg is not None:
            nr = self.tw.tag_ranges(f"seg_{next_first_seg}")
            if nr:
                try:
                    block_end = self.tw.index(f"{nr[0]} linestart")
                except Exception:
                    pass

        try:
            block = self.tw.get(block_start, block_end)
        except Exception:
            return None

        first_nl   = block.find('\n')
        first_line = block[:first_nl] if first_nl != -1 else block
        pos = first_line.rfind(']: ')
        if pos != -1:
            spoken = block[pos + 3:]
        else:
            pos = first_line.find('] ')
            if pos != -1:
                spoken = block[pos + 2:]
            else:
                spoken = block

        return spoken.strip() or None

    @staticmethod
    def _nearest_sentence_end(text: str, char_offset: int) -> Optional[int]:
        punct = set(".!?")
        trail = set('"\')')

        fwd = None
        for i in range(char_offset, len(text)):
            if text[i] in punct:
                j = i + 1
                while j < len(text) and text[j] in trail:
                    j += 1
                while j < len(text) and text[j] == " ":
                    j += 1
                fwd = j
                break

        bwd = None
        for i in range(min(char_offset, len(text) - 1), -1, -1):
            if text[i] in punct:
                j = i + 1
                while j < len(text) and text[j] in trail:
                    j += 1
                while j < len(text) and text[j] == " ":
                    j += 1
                bwd = j
                break

        if fwd is None and bwd is None:
            return None
        if fwd is None:
            return bwd
        if bwd is None:
            return fwd

        if abs(fwd - char_offset) <= abs(bwd - char_offset):
            return fwd
        return bwd

    def _update_split_preview(self, event=None):
        if not self._edit_mode or self.preview_callback is None:
            return
        try:
            self._update_split_preview_inner()
        except Exception as e:
            print(f"\U0001f441  preview error: {e}", flush=True)
            self.preview_callback(f"Preview error: {e}")

    def _update_split_preview_inner(self, event=None):
        self._pending_split_entry       = None
        self._pending_split_char_offset = None

        def _trim_tail(s, n=50):
            s = s.strip()
            return ("\u2026" + s[-n:]) if len(s) > n else s

        def _trim_head(s, n=50):
            s = s.strip()
            return (s[:n] + "\u2026") if len(s) > n else s

        cursor    = self.tw.index(tk.INSERT)
        entry_idx = self._find_entry_at_cursor(cursor)

        if entry_idx is None:
            self.preview_callback(
                "Click anywhere in the transcript to see where \u21b5 Enter will split"
            )
            return

        para_text = self._get_para_text_from_widget(entry_idx)
        if not para_text:
            self.preview_callback("\u21b5  Cannot read paragraph text")
            return

        char_offset = self._cursor_to_para_char_offset(cursor, entry_idx)
        if char_offset is None:
            self.preview_callback(
                "Click anywhere in the transcript to see where \u21b5 Enter will split"
            )
            return

        split_pos = self._nearest_sentence_end(para_text, char_offset)

        if split_pos is None or split_pos <= 0 or split_pos >= len(para_text):
            self.preview_callback(
                "\u21b5  No sentence boundary found near cursor — "
                "click inside a sentence ending with . ? or !"
            )
            return

        text_a = para_text[:split_pos].strip()
        text_b = para_text[split_pos:].strip()

        if not text_a or not text_b:
            self.preview_callback(
                "\u21b5  Split would leave one paragraph empty — "
                "try clicking further into the paragraph"
            )
            return

        self._pending_split_entry       = entry_idx
        self._pending_split_char_offset = split_pos

        self.preview_callback(
            f'\u21b5  A ends: "{_trim_tail(text_a)}"   \u2016   B starts: "{_trim_head(text_b)}"'
        )

    @staticmethod
    def _rebuild_sentences(text: str, entry: dict) -> list:
        parts   = [p.strip() for p in re.split(r'(?<=[.!?])\s+', text) if p.strip()]
        if not parts:
            parts = [text.strip()]
        start   = float(entry.get("start", 0.0))
        end     = float(entry.get("end", start))
        dur     = max(0.0, end - start)
        total   = sum(len(p) for p in parts) or 1
        speaker = entry.get("speaker", "")
        result  = []
        t = start
        for part in parts:
            frac  = len(part) / total
            t_end = t + dur * frac
            result.append({"text": part, "start": t, "end": t_end, "speaker": speaker})
            t = t_end
        return result

    def _sync_from_widget(self):
        print(f"\U0001f4be _sync_from_widget: {len(self._entries)} entries", flush=True)

        for entry_idx, entry in enumerate(self._entries):
            raw = self._get_para_text_from_widget(entry_idx)

            if raw is None:
                print(f"\U0001f4be   entry {entry_idx}: no widget text found, skipping", flush=True)
                continue

            raw = raw.strip()
            if not raw:
                continue

            old_text = entry.get("text", "").strip()
            if raw == old_text:
                continue

            if entry_idx < 3:
                print(f"\U0001f4be   entry {entry_idx} changed: {raw[:60]!r}", flush=True)

            entry["text"]      = raw
            entry["sentences"] = self._rebuild_sentences(raw, entry)

    def _save_to_library(self) -> bool:
        if not self.doc_id:
            print("💾 TranscriptParagraphEditor: no doc_id, skipping save", flush=True)
            return False
        try:
            from document_library import update_transcript_entries
            result = update_transcript_entries(self.doc_id, self._entries)
            print(
                f"💾 TranscriptParagraphEditor: saved {len(self._entries)} entries → {result}",
                flush=True,
            )
            if self.save_callback:
                self.save_callback(list(self._entries))
            return bool(result)
        except Exception as e:
            print(f"💾 TranscriptParagraphEditor save error: {e}", flush=True)
            return False
