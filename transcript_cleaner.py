"""
transcript_cleaner.py
=====================
Core transcript processing engine for DocAnalyser.

Takes raw faster-whisper entries (list of dicts with start/end/text fields)
and produces cleaned, consolidated, speaker-labelled entries ready for
DocAnalyser's document model.

Processing pipeline
-------------------
Phase 1  — Strip breath fragments
           Remove sub-threshold segments (very short duration or known
           filler words: uh, um, mm, hmm, etc.)
           Also strips inline filler words from within segment text so that
           "Um, so I was saying" becomes "So I was saying."
           Back-channel interjections (mm-hmm, uh-huh) are retained as
           bracketed annotations rather than discarded.

Phase 2  — Consolidate into sentences
           Join consecutive segments into sentences using timing gaps.
           A gap below SENTENCE_GAP_THRESHOLD seconds = same sentence still
           in progress.  A terminal punctuation mark also signals sentence end.

Phase 3  — Apply Corrections List  (v1.7-alpha)
           Word-level find-and-replace on sentence text using a Corrections
           List from the SQLite database.  Skipped entirely when
           corrections_list_id is None (the default).  Runs after sentence
           consolidation so multi-word phrases that span whisper-segment
           boundaries are unified before substitution; runs before speaker
           classification so downstream phases see corrected text.

Phase 4  — Heuristic speaker classification  (Tier 1, at sentence level)
           Classify each sentence as SPEAKER_A or SPEAKER_B using three
           signals:
             - ends with a question mark
             - is very short (interviewer interjection / back-channel)
             - follows a long block from the other speaker
           Output is explicitly labelled as provisional.
           Running this BEFORE paragraph consolidation allows speaker
           changes to be used as paragraph boundaries.

Phase 5  — Consolidate into paragraphs  (speaker-aware)
           Group sentences into paragraphs.  A new paragraph starts when
           the gap exceeds PARAGRAPH_GAP_THRESHOLD OR the speaker changes
           OR the accumulated paragraph word count reaches MAX_PARAGRAPH_WORDS.
           The word count cap prevents the entire recording collapsing into
           a handful of very long paragraphs when speaker detection misses
           turn boundaries.

Phase 6  — (Optional, Tier 2)  Pyannote alignment
Phase 7  — Speaker name substitution

Author: DocAnalyser Development Team
"""

from __future__ import annotations

import re
import sys
import os
import argparse
from typing import List, Dict, Optional, Callable, Tuple


# ============================================================================
# TUNING CONSTANTS
# ============================================================================

# Phase 1 — Breath / filler removal
FILLER_DURATION_THRESHOLD = 0.60   # seconds

# Known filler words (exact whole-segment match to discard entirely)
FILLER_WORDS = {
    "uh", "um", "mm", "hmm", "hm", "ah", "er", "eh",
    "mmm", "uhh", "umm",
}

# Short back-channel tokens kept as [Annotation] — conservative list only
BACKCHANNEL_WORDS = {
    "mm-hmm", "uh-huh", "mhm",
}

# Phase 2 — Sentence consolidation
SENTENCE_GAP_THRESHOLD = 1.2      # seconds

# Hard cap on words per sentence regardless of gaps or punctuation.
# Whisper often omits terminal punctuation entirely, so without this cap
# a single "sentence" can grow to 500+ words when the speaker talks for
# several minutes with sub-threshold gaps between segments.
# At ~120 wpm, 30 words ≈ 15 seconds — a natural sentence length.
MAX_SENTENCE_WORDS = 30

# Phase 5 — Paragraph consolidation
PARAGRAPH_GAP_THRESHOLD = 1.5     # seconds
# Hard cap on words per paragraph regardless of gaps/speaker changes.
# Prevents the entire recording collapsing into a handful of huge paragraphs
# when heuristic speaker detection misses many turn boundaries.
MAX_PARAGRAPH_WORDS = 120

# Phase 4 — Heuristic speaker classification
SHORT_WORD_THRESHOLD = 8
LONG_RESPONSE_WORD_COUNT = 40

# Sentence-ending punctuation pattern
SENTENCE_END_PAT = re.compile(r'[.!?\u2026]["\')\]]*\s*$')

# Inline filler word removal — matches whole words only, case-insensitive
# Conservative: only clear noise tokens, not legitimate short words.
_INLINE_FILLER_RE = re.compile(
    r'\b(uh+|um+|hmm+|hm+|ah+|er|eh|mm+|uhh+|umm+)\b[,.]?\s*',
    re.IGNORECASE,
)


def _remove_inline_fillers(text: str) -> str:
    """
    Remove filler words from within a segment's text.

    "Um, so I was..."   -> "So I was..."
    "I was, uh, going" -> "I was, going"

    Uses whole-word matching so 'umbrella' and 'err...' are not affected.
    """
    cleaned = _INLINE_FILLER_RE.sub(' ', text).strip()
    cleaned = re.sub(r'\s+', ' ', cleaned)
    cleaned = re.sub(r',\s*,', ',', cleaned)
    cleaned = re.sub(r'^,\s*', '', cleaned)
    if cleaned and text and text[0].isupper():
        cleaned = cleaned[0].upper() + cleaned[1:]
    return cleaned.strip()


# ============================================================================
# PHASE 1 — BREATH / FILLER REMOVAL
# ============================================================================

def _clean_text(text: str) -> str:
    """Normalise whitespace and strip leading/trailing space."""
    return re.sub(r'\s+', ' ', text).strip()


def _is_filler(entry: Dict) -> bool:
    """
    Return True if this entry is a pure filler to be discarded.

    1. Text is a known filler word — always discard.
    2. Very short duration AND text consists entirely of 1-2 very short
       tokens (2 chars or fewer) — likely noise.
    """
    text = _clean_text(entry.get("text", "")).lower().rstrip(".,")
    duration = entry.get("end", 0) - entry.get("start", 0)

    if text in FILLER_WORDS:
        return True

    if duration < FILLER_DURATION_THRESHOLD:
        words = text.split()
        if len(words) <= 2 and all(len(w) <= 2 for w in words):
            return True

    return False


def _is_backchannel(entry: Dict) -> bool:
    """
    Return True if this entry is a short back-channel (mm-hmm, uh-huh)
    that should be retained as a bracketed annotation.
    """
    text = _clean_text(entry.get("text", "")).lower().rstrip(".,")
    duration = entry.get("end", 0) - entry.get("start", 0)
    return (text in BACKCHANNEL_WORDS and
            duration < FILLER_DURATION_THRESHOLD * 2.0)


def strip_fillers(entries: List[Dict], remove_inline: bool = True) -> Tuple[List[Dict], int]:
    """
    Phase 1: Remove filler segments, convert back-channels to annotations,
    and strip inline filler words from within remaining segment text.

    Returns:
        (cleaned_entries, filler_count_removed)
    """
    cleaned = []
    removed = 0

    for entry in entries:
        if _is_filler(entry):
            removed += 1
            continue

        if _is_backchannel(entry):
            new_entry = dict(entry)
            text = _clean_text(entry.get("text", ""))
            new_entry["text"] = f"[{text.capitalize()}]"
            new_entry["is_backchannel"] = True
            cleaned.append(new_entry)
            continue

        new_entry = dict(entry)
        if remove_inline:
            original_text = new_entry.get("text", "")
            stripped = _remove_inline_fillers(original_text)
            if stripped:
                new_entry["text"] = stripped
            else:
                # Entire content was fillers
                removed += 1
                continue
        cleaned.append(new_entry)

    return cleaned, removed


# ============================================================================
# PHASE 2 — SENTENCE CONSOLIDATION
# ============================================================================

def _format_timestamp(seconds: float) -> str:
    """Format seconds as [HH:MM:SS]."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"[{h:02d}:{m:02d}:{s:02d}]"


def _looks_like_sentence_end(text: str) -> bool:
    """Return True if text appears to end a sentence."""
    return bool(SENTENCE_END_PAT.search(text.rstrip()))


def consolidate_sentences(entries: List[Dict]) -> List[Dict]:
    """
    Phase 2: Join consecutive entries into sentences.

    Two entries belong to the same sentence if the gap between them is
    below SENTENCE_GAP_THRESHOLD and the previous entry does not end with
    terminal punctuation.
    """
    if not entries:
        return []

    sentences = []
    buffer: List[Dict] = []

    def flush_buffer():
        if not buffer:
            return
        parts = [_clean_text(e.get("text", "")) for e in buffer]
        parts = [p for p in parts if p]
        joined_text = " ".join(parts)
        sentences.append({
            "start":       buffer[0]["start"],
            "end":         buffer[-1]["end"],
            "text":        joined_text,
            "timestamp":   _format_timestamp(buffer[0]["start"]),
            "speaker":     buffer[0].get("speaker", ""),
            "provisional": buffer[0].get("provisional", False),
        })
        buffer.clear()

    for entry in entries:
        if not buffer:
            buffer.append(entry)
            continue

        prev = buffer[-1]
        gap = entry["start"] - prev["end"]

        if entry.get("is_backchannel"):
            buffer.append(entry)
            continue

        # Count words accumulated in the current sentence buffer
        buffer_words = sum(len((e.get("text") or "").split()) for e in buffer)
        over_sentence_limit = buffer_words >= MAX_SENTENCE_WORDS

        if over_sentence_limit:
            # Hard cap reached — flush regardless of gap or punctuation
            flush_buffer()
            buffer.append(entry)
        elif gap <= SENTENCE_GAP_THRESHOLD and not _looks_like_sentence_end(prev.get("text", "")):
            buffer.append(entry)
        else:
            flush_buffer()
            buffer.append(entry)

    flush_buffer()
    return sentences


# ============================================================================
# PHASE 3 — APPLY CORRECTIONS LIST  (v1.7-alpha)
# ============================================================================

def apply_corrections_list(
        sentences: List[Dict],
        list_id: Optional[int],
        progress_callback: Optional[Callable[[str], None]] = None,
) -> Tuple[List[Dict], int]:
    """
    Phase 3: Apply a Corrections List to each sentence's text.

    Args:
        sentences:          List of sentence dicts from Phase 2.
        list_id:            Corrections list to apply, or None to skip the
                            phase entirely.
        progress_callback:  Optional status callback.

    Returns:
        (modified_sentences, total_hits)

    If list_id is None, the list does not exist, or the list is empty,
    sentences are returned unchanged with total_hits=0.

    The corrections engine is invoked once per sentence with a single
    pre-fetched copy of the list's entries — no per-sentence database
    round-trips. Sentences with no hits are passed through by reference.
    """
    if list_id is None:
        return sentences, 0

    # Lazy imports to keep transcript_cleaner importable in environments
    # where corrections support hasn't been wired in yet (older databases
    # that haven't run the v1.7-alpha migration, etc.).
    try:
        import corrections_engine
        import db_manager as _db
    except ImportError as exc:
        if progress_callback:
            progress_callback(f"  ⚠ Corrections module not available: {exc}")
        return sentences, 0

    try:
        entries = _db.db_get_corrections(list_id)
    except Exception as exc:
        if progress_callback:
            progress_callback(f"  ⚠ Could not load corrections list {list_id}: {exc}")
        return sentences, 0

    if not entries:
        return sentences, 0

    result: List[Dict] = []
    total_hits = 0
    for sent in sentences:
        original_text = sent.get("text", "")
        if not original_text:
            result.append(sent)
            continue
        new_text, stats = corrections_engine.apply_entries_to_text_with_stats(
            original_text, entries
        )
        sent_hits = sum(s.get("hits", 0) for s in stats)
        if sent_hits > 0:
            total_hits += sent_hits
            new_sent = dict(sent)
            new_sent["text"] = new_text
            result.append(new_sent)
        else:
            result.append(sent)

    return result, total_hits


# ============================================================================
# PHASE 4 — HEURISTIC SPEAKER CLASSIFICATION
# ============================================================================

def classify_speakers_heuristic(
        sentences: List[Dict],
        speaker_a_label: str = "SPEAKER_A",
        speaker_b_label: str = "SPEAKER_B",
) -> List[Dict]:
    """
    Phase 4: Assign provisional SPEAKER_A / SPEAKER_B labels.

    Runs at sentence level (before paragraph consolidation) so that
    speaker changes can drive paragraph boundaries.

    Always marks results provisional=True — these are suggestions only.
    """
    if not sentences:
        return []

    result = []
    current_speaker = speaker_b_label   # interviewer assumed to speak first
    words_for_current_speaker = 0

    for sent in sentences:
        text = sent.get("text", "")
        word_count = len(text.split())

        has_question   = text.rstrip().endswith("?")
        is_short       = word_count <= SHORT_WORD_THRESHOLD
        follows_long   = words_for_current_speaker >= LONG_RESPONSE_WORD_COUNT

        switch_likely = has_question or (is_short and follows_long)

        if switch_likely and current_speaker == speaker_a_label:
            current_speaker = speaker_b_label
            words_for_current_speaker = 0
        elif switch_likely and current_speaker == speaker_b_label:
            if not is_short:
                current_speaker = speaker_a_label
                words_for_current_speaker = 0
        elif not switch_likely and current_speaker == speaker_b_label:
            if word_count > SHORT_WORD_THRESHOLD:
                current_speaker = speaker_a_label
                words_for_current_speaker = 0

        new_sent = dict(sent)
        new_sent["speaker"]     = current_speaker
        new_sent["provisional"] = True
        result.append(new_sent)

        words_for_current_speaker += word_count

    return result


# ============================================================================
# PHASE 5 — PARAGRAPH CONSOLIDATION
# ============================================================================

def consolidate_paragraphs(sentences: List[Dict]) -> List[Dict]:
    """
    Phase 5: Group speaker-labelled sentences into paragraphs.

    A new paragraph starts when ANY of:
      - gap > PARAGRAPH_GAP_THRESHOLD
      - speaker label changes
      - accumulated word count >= MAX_PARAGRAPH_WORDS  (hard cap)
    """
    if not sentences:
        return []

    paragraphs = []
    buffer: List[Dict] = []

    def flush_buffer():
        if not buffer:
            return
        text_parts = []
        for s in buffer:
            t = _clean_text(s.get("text", ""))
            if t:
                if t[-1] not in ".!?\u2026\"')]}":
                    t = t + "."
                text_parts.append(t)
        joined = " ".join(text_parts)

        sentence_timestamps = [
            {"text": t, "start": s.get("start", 0.0), "end": s.get("end", 0.0)}
            for s, t in zip(buffer, text_parts) if t
        ]

        paragraphs.append({
            "start":       buffer[0]["start"],
            "end":         buffer[-1]["end"],
            "text":        joined,
            "timestamp":   _format_timestamp(buffer[0]["start"]),
            "speaker":     buffer[0].get("speaker", ""),
            "provisional": buffer[0].get("provisional", False),
            "sentences":   sentence_timestamps,
        })
        buffer.clear()

    for sentence in sentences:
        if not buffer:
            buffer.append(sentence)
            continue

        prev = buffer[-1]
        gap = sentence["start"] - prev["end"]

        speaker_changed = (
            sentence.get("speaker", "") != prev.get("speaker", "")
            and sentence.get("speaker", "") != ""
            and prev.get("speaker", "") != ""
        )

        buffer_words = sum(len((s.get("text") or "").split()) for s in buffer)
        over_word_limit = buffer_words >= MAX_PARAGRAPH_WORDS

        if gap > PARAGRAPH_GAP_THRESHOLD or speaker_changed or over_word_limit:
            flush_buffer()

        buffer.append(sentence)

    flush_buffer()
    return paragraphs


# ============================================================================
# PHASE 6 — PYANNOTE ALIGNMENT  (Tier 2, optional)
# ============================================================================

def apply_diarization(
        paragraphs: List[Dict],
        audio_path: str,
        hf_token: str,
        progress_callback: Optional[Callable[[str], None]] = None,
) -> Tuple[List[Dict], bool]:
    """Phase 6: Replace heuristic labels with pyannote.audio labels."""
    try:
        import diarization_handler
    except ImportError:
        if progress_callback:
            progress_callback("\u26a0\ufe0f diarization_handler not found")
        return paragraphs, False

    try:
        success, speaker_timeline = diarization_handler.run_diarization(
            audio_path=audio_path,
            hf_token=hf_token,
            progress_callback=progress_callback,
        )
        if not success:
            return paragraphs, False

        result = []
        for para in paragraphs:
            mid = (para["start"] + para["end"]) / 2.0
            speaker = diarization_handler.speaker_at(speaker_timeline, mid)
            new_para = dict(para)
            new_para["speaker"]     = speaker or para["speaker"]
            new_para["provisional"] = (speaker is None)
            result.append(new_para)
        return result, True

    except Exception as e:
        if progress_callback:
            progress_callback(f"\u26a0\ufe0f Diarization failed: {e}")
        return paragraphs, False


# ============================================================================
# PHASE 7 — SPEAKER NAME SUBSTITUTION
# ============================================================================

def apply_speaker_names(
        paragraphs: List[Dict],
        name_map: Dict[str, str],
) -> List[Dict]:
    """Phase 7: Replace SPEAKER_A / SPEAKER_B with real names."""
    result = []
    for para in paragraphs:
        new_para = dict(para)
        speaker = para.get("speaker", "")
        new_para["speaker"] = name_map.get(speaker, speaker)
        result.append(new_para)
    return result


# ============================================================================
# TOP-LEVEL PIPELINE
# ============================================================================

def clean_transcript(
        entries: List[Dict],
        audio_path: Optional[str] = None,
        hf_token: Optional[str] = None,
        name_map: Optional[Dict[str, str]] = None,
        use_diarization: bool = False,
        keep_backchannels: bool = True,
        corrections_list_id: Optional[int] = None,
        progress_callback: Optional[Callable[[str], None]] = None,
) -> Dict:
    """
    Full transcript cleaning pipeline.

    Args:
        entries:             Raw faster-whisper entries (start, end, text)
        audio_path:          Path to original audio (for Tier 2 diarization)
        hf_token:            HuggingFace token (Tier 2 only)
        name_map:            {"SPEAKER_A": "Chris", "SPEAKER_B": "Tony"}
        use_diarization:     Attempt pyannote voice detection
        keep_backchannels:   Retain [Mm-hmm] annotations in output
        corrections_list_id: Optional Corrections List id to apply during
                             Phase 3.  Defaults to None (Phase 3 is
                             skipped entirely).  Pass an integer id to
                             apply that list's entries to every sentence
                             before speaker classification runs.
        progress_callback:   Optional status function(str)

    Returns dict with: paragraphs, fillers_removed, corrections_applied,
                       diarization_used, speaker_ids, warnings
    """
    warnings_out = []

    def _progress(msg):
        if progress_callback:
            progress_callback(msg)

    # Phase 1
    _progress("Cleaning breath fragments and inline fillers...")
    cleaned, fillers_removed = strip_fillers(entries, remove_inline=True)
    _progress(f"  Removed {fillers_removed} filler segments/words.")

    if not keep_backchannels:
        cleaned = [e for e in cleaned if not e.get("is_backchannel")]

    if not cleaned:
        warnings_out.append("No segments remained after filler removal.")
        return {
            "paragraphs": [], "fillers_removed": fillers_removed,
            "corrections_applied": 0,
            "diarization_used": False, "speaker_ids": [], "warnings": warnings_out,
        }

    # Phase 2
    _progress("Consolidating segments into sentences...")
    sentences = consolidate_sentences(cleaned)
    _progress(f"  Formed {len(sentences)} sentences from {len(cleaned)} segments.")

    # Phase 3 — Apply Corrections List (skipped when corrections_list_id is None)
    corrections_applied = 0
    if corrections_list_id is not None:
        _progress("Applying corrections list...")
        sentences, corrections_applied = apply_corrections_list(
            sentences, corrections_list_id, _progress
        )
        _progress(f"  Applied {corrections_applied} corrections.")

    # Phase 4 (before paragraph consolidation so speaker changes drive breaks)
    _progress("Applying heuristic speaker classification...")
    sentences = classify_speakers_heuristic(sentences)
    _progress("  Speaker classification complete (provisional).")

    # Phase 5
    _progress("Grouping sentences into paragraphs...")
    paragraphs = consolidate_paragraphs(sentences)
    _progress(f"  Formed {len(paragraphs)} paragraphs from {len(sentences)} sentences.")

    # Phase 6 (optional)
    diarization_used = False
    if use_diarization and audio_path and hf_token:
        _progress("Starting voice-based speaker detection...")
        paragraphs, diarization_used = apply_diarization(
            paragraphs, audio_path, hf_token, _progress
        )
        if not diarization_used:
            warnings_out.append(
                "Voice-based speaker detection failed. Heuristic labels used."
            )

    # Phase 7
    if name_map:
        _progress("Applying speaker names...")
        paragraphs = apply_speaker_names(paragraphs, name_map)

    speaker_ids = sorted({p.get("speaker", "") for p in paragraphs if p.get("speaker")})

    return {
        "paragraphs":          paragraphs,
        "fillers_removed":     fillers_removed,
        "corrections_applied": corrections_applied,
        "diarization_used":    diarization_used,
        "speaker_ids":         speaker_ids,
        "warnings":            warnings_out,
    }


# ============================================================================
# CONVERT TO DOCANALYSER ENTRIES
# ============================================================================

def paragraphs_to_entries(paragraphs: List[Dict]) -> List[Dict]:
    """Convert cleaned paragraphs to DocAnalyser's native entries format."""
    entries = []
    for para in paragraphs:
        entry = {
            "start":       para.get("start", 0.0),
            "end":         para.get("end", 0.0),
            "text":        para.get("text", ""),
            "timestamp":   para.get("timestamp", ""),
            "speaker":     para.get("speaker", ""),
            "provisional": para.get("provisional", False),
        }
        if "sentences" in para:
            entry["sentences"] = para["sentences"]
        entries.append(entry)
    return entries


# ============================================================================
# FORMAT OUTPUT AS PLAIN TEXT
# ============================================================================

def paragraphs_to_text(
        paragraphs: List[Dict],
        include_timestamps: bool = True,
        include_speaker_labels: bool = True,
        provisional_note: bool = True,
) -> str:
    """Convert cleaned paragraphs to plain text."""
    lines = []
    for para in paragraphs:
        header_parts = []
        if include_timestamps:
            header_parts.append(para.get("timestamp", ""))
        if include_speaker_labels:
            speaker = para.get("speaker", "")
            if speaker:
                if provisional_note and para.get("provisional"):
                    speaker = f"{speaker} (suggested)"
                header_parts.append(speaker)
        if header_parts:
            lines.append("  ".join(header_parts))
        lines.append(para.get("text", ""))
        lines.append("")
    return "\n".join(lines).strip()


# ============================================================================
# STANDALONE TEST RUNNER
# ============================================================================

def _parse_dummy_transcript(filepath: str) -> List[Dict]:
    entries = []
    pat = re.compile(
        r'\[(\d{2}:\d{2}:\d{2}\.\d+)\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d+)\]'
        r'(?:\s+(SPEAKER_\w+))?\s+(.*)'
    )

    def ts_to_seconds(ts: str) -> float:
        h, m, s = ts.split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)

    with open(filepath, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = pat.match(line)
            if m:
                start_s = ts_to_seconds(m.group(1))
                end_s   = ts_to_seconds(m.group(2))
                text    = m.group(4).strip()
                if text:
                    entries.append({
                        "start":     start_s,
                        "end":       end_s,
                        "text":      text,
                        "timestamp": f"[{m.group(1)[:8]}]",
                    })
    return entries


def main():
    global SENTENCE_GAP_THRESHOLD, PARAGRAPH_GAP_THRESHOLD

    parser = argparse.ArgumentParser(
        description="Test transcript_cleaner.py on a transcript file."
    )
    parser.add_argument("input", nargs="?", default="dummy_transcript.txt")
    parser.add_argument("--show-phases", action="store_true")
    parser.add_argument("--min-sentence-gap", type=float, default=SENTENCE_GAP_THRESHOLD)
    parser.add_argument("--min-para-gap",     type=float, default=PARAGRAPH_GAP_THRESHOLD)
    args = parser.parse_args()

    SENTENCE_GAP_THRESHOLD  = args.min_sentence_gap
    PARAGRAPH_GAP_THRESHOLD = args.min_para_gap

    if not os.path.exists(args.input):
        print(f"ERROR: File not found: {args.input}")
        sys.exit(1)

    print(f"\nTranscript Cleaner  v2")
    print(f"{'='*60}")
    print(f"Input:              {args.input}")
    print(f"Sentence gap:       {SENTENCE_GAP_THRESHOLD}s")
    print(f"Paragraph gap:      {PARAGRAPH_GAP_THRESHOLD}s")
    print(f"Max para words:     {MAX_PARAGRAPH_WORDS}")
    print(f"Short word limit:   {SHORT_WORD_THRESHOLD}")

    entries = _parse_dummy_transcript(args.input)
    print(f"\n{len(entries)} segments loaded.")

    result = clean_transcript(
        entries=entries,
        progress_callback=lambda msg: print(f"  {msg}"),
        keep_backchannels=True,
    )

    paragraphs = result["paragraphs"]
    print(f"\n{'='*60}")
    print(f"Input segments:     {len(entries)}")
    print(f"Fillers removed:    {result['fillers_removed']}")
    print(f"Output paragraphs:  {len(paragraphs)}")
    print(f"Speaker IDs:        {result['speaker_ids']}")
    for w in result["warnings"]:
        print(f"  \u26a0  {w}")

    output_path = os.path.splitext(args.input)[0] + "_cleaned.txt"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(paragraphs_to_text(paragraphs))
    print(f"\n\u2705 Written to: {output_path}")


if __name__ == "__main__":
    main()
