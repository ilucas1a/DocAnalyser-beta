"""
corrections_engine.py — Apply corrections lists to text (v1.7-alpha)

The runtime side of Corrections Lists. Given a transcript and a list_id,
substitute every match of every entry's original_text with its corrected_text,
honouring per-entry case_sensitive and word_boundary flags.

This is what Phase 3 of transcript_cleaner.clean_transcript() will call
once Day 5 wires it in. It's also what the cleanup dialog's "preview
corrections" button will call so the user can see what the list will do
before committing.

Behaviour notes:
  * Longest original_text first — "tell vision" wins over "tell" if both
    are in the same list. Sequential application: earlier substitutions
    feed into later ones. This is intentional; matches user expectations
    from word processors. For the bundled General list this is a non-
    issue (no entries overlap).
  * Word boundary anchors only added where they make sense. Python's \\b
    only matches between a word character and a non-word character, so
    punctuation entries like " ." get no boundary anchors even when
    word_boundary=True (it would be a no-op).
  * Case preservation is intentionally NOT smart in v1.7-alpha:
    case_sensitive=False means case-insensitive search with literal
    replacement. So "Alot" with rule "alot" -> "a lot" becomes "a lot"
    (loses the capital). Smart case preservation is a known follow-up
    captured on the v1.7 roadmap.

Author: DocAnalyser Development Team
Date: 28 April 2026 (v1.7-alpha Day 2)
"""

from __future__ import annotations

import logging
import re
from typing import List, Tuple

import db_manager as db


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def apply_corrections_to_text(text: str, list_id: int) -> str:
    """
    Apply every entry from list_id to text. Returns the modified text.

    If the list does not exist or has no entries, returns text unchanged.
    Bad entries (e.g. malformed regex characters in original_text after
    escape) are logged and skipped, never raised.
    """
    if not text:
        return text
    entries = db.db_get_corrections(list_id)
    if not entries:
        return text
    return _apply_entries(text, entries)


def apply_corrections_with_stats(text: str,
                                 list_id: int) -> Tuple[str, List[dict]]:
    """
    Apply corrections and also return per-entry hit counts.

    Returns (new_text, stats) where stats is a list of dicts:
        [{"original": "...", "corrected": "...", "hits": int}, ...]

    Useful for the cleanup dialog's "preview" button so the user can
    see exactly what the list did to their transcript.
    """
    if not text:
        return text, []
    entries = db.db_get_corrections(list_id)
    if not entries:
        return text, []
    return _apply_entries_with_stats(text, entries)


def apply_entries_to_text(text: str, entries: List[dict]) -> str:
    """
    Apply a pre-fetched list of entry dicts to text. Useful in tests
    and when callers already have entries in hand without needing
    another round-trip to the database.

    Each entry dict must have: original_text, corrected_text,
    case_sensitive, word_boundary.
    """
    if not text or not entries:
        return text
    return _apply_entries(text, entries)


def apply_entries_to_text_with_stats(
        text: str, entries: List[dict]) -> Tuple[str, List[dict]]:
    """
    Same as apply_entries_to_text() but also returns per-entry hit counts.

    Used by transcript_cleaner Phase 3 so it can iterate over many
    sentences without re-fetching entries from the database for each one.
    Returns (new_text, stats) where stats is a list of
        {"original": str, "corrected": str, "hits": int} dicts.
    """
    if not text or not entries:
        return text, []
    return _apply_entries_with_stats(text, entries)


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _build_pattern(original_text: str,
                   case_sensitive: bool,
                   word_boundary: bool) -> "re.Pattern":
    """Build a compiled regex for one correction entry."""
    pattern = re.escape(original_text)
    if word_boundary and original_text:
        # \b only matches at a transition between a word char and a non-
        # word char, so adding it next to a non-word char is harmless but
        # adds nothing. Be defensive: only add when the adjacent char is
        # actually a word character.
        if _is_word_char(original_text[0]):
            pattern = r"\b" + pattern
        if _is_word_char(original_text[-1]):
            pattern = pattern + r"\b"
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(pattern, flags)


def _is_word_char(ch: str) -> bool:
    """Match Python re's \\w semantics (alphanumeric or underscore)."""
    return ch.isalnum() or ch == "_"


def _sort_entries_longest_first(entries: List[dict]) -> List[dict]:
    """Sort entries by len(original_text) descending so multi-word
    phrases get applied before any of their constituent shorter matches."""
    return sorted(entries, key=lambda e: len(e["original_text"]), reverse=True)


def _apply_entries(text: str, entries: List[dict]) -> str:
    """Inner loop without stats — slightly faster than the stats version."""
    for entry in _sort_entries_longest_first(entries):
        try:
            pattern = _build_pattern(
                entry["original_text"],
                bool(entry.get("case_sensitive", False)),
                bool(entry.get("word_boundary", True)),
            )
        except re.error as exc:
            logging.warning(
                "Skipping bad correction entry %r: %s",
                entry.get("original_text"), exc
            )
            continue
        text = pattern.sub(entry["corrected_text"], text)
    return text


def _apply_entries_with_stats(text: str,
                              entries: List[dict]) -> Tuple[str, List[dict]]:
    """Inner loop with stats — returns (text, [{original, corrected, hits}, ...])."""
    stats: List[dict] = []
    for entry in _sort_entries_longest_first(entries):
        try:
            pattern = _build_pattern(
                entry["original_text"],
                bool(entry.get("case_sensitive", False)),
                bool(entry.get("word_boundary", True)),
            )
        except re.error as exc:
            logging.warning(
                "Skipping bad correction entry %r: %s",
                entry.get("original_text"), exc
            )
            stats.append({
                "original": entry.get("original_text", ""),
                "corrected": entry.get("corrected_text", ""),
                "hits": 0,
                "error": str(exc),
            })
            continue
        new_text, n = pattern.subn(entry["corrected_text"], text)
        text = new_text
        stats.append({
            "original": entry["original_text"],
            "corrected": entry["corrected_text"],
            "hits": n,
        })
    return text, stats
