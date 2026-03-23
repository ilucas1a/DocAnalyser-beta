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
           Back-channel interjections (mm-hmm, right, yeah during another
           speaker's turn) are retained as bracketed annotations rather than
           discarded, because they carry information about engagement.

Phase 2  — Consolidate into sentences
           Join consecutive segments into sentences using timing gaps.
           A gap below SENTENCE_GAP_THRESHOLD seconds = same sentence still
           in progress.  A terminal punctuation mark also signals sentence end.

Phase 3  — Heuristic speaker classification  (Tier 1, at sentence level)
           Classify each sentence as SPEAKER_A or SPEAKER_B using three
           signals drawn from transcript_qa_splitter.py:
             - ends with a question mark
             - is very short (interviewer interjection / back-channel)
             - follows a long block from the other speaker
           Output is explicitly labelled as provisional.
           Running this BEFORE paragraph consolidation allows speaker
           changes to be used as paragraph boundaries.

Phase 4  — Consolidate into paragraphs  (speaker-aware)
           Group sentences into paragraphs.  A new paragraph starts when
           the gap exceeds PARAGRAPH_GAP_THRESHOLD OR the speaker changes.
           Each output paragraph therefore belongs to a single speaker.

Phase 5  — (Optional, Tier 2)  Pyannote alignment
           If diarization_handler is available and a HuggingFace token is
           configured, replace the heuristic labels with acoustically-verified
           SPEAKER_00 / SPEAKER_01 labels from pyannote.audio.

Phase 6  — Speaker name substitution
           Replace SPEAKER_A / SPEAKER_B (or SPEAKER_00 / SPEAKER_01) with
           real names supplied via the DocAnalyser cleanup dialog.

Output format
-------------
Each item in the returned list is a dict compatible with DocAnalyser's
existing entries format:

    {
        "start":     float,   # seconds from audio start
        "end":       float,   # seconds from audio start
        "text":      str,     # cleaned, consolidated text
        "timestamp": str,     # "[HH:MM:SS]" formatted string
        "speaker":   str,     # "SPEAKER_A", "SPEAKER_B", or real name
        "provisional": bool,  # True if speaker label is heuristic only
    }

Standalone testing
------------------
    python transcript_cleaner.py path/to/dummy_transcript.txt
    python transcript_cleaner.py path/to/dummy_transcript.txt --show-phases

This module is intentionally self-contained — it imports nothing from
DocAnalyser so it can be tested independently.
"""

from __future__ import annotations

import re
import sys
import os
import argparse
from typing import List, Dict, Optional, Callable, Tuple


# ============================================================================
# TUNING CONSTANTS
# All timing values are in seconds.  Adjust here to tune behaviour.
# ============================================================================

# Phase 1 — Breath / filler removal
# ----------------------------------
# Segment duration below this is a candidate filler (before text check)
FILLER_DURATION_THRESHOLD = 0.60   # seconds

# Known filler words / back-channel tokens (lowercase, stripped)
# Exact-match only — a segment whose entire text is one of these is a filler.
FILLER_WORDS = {
    "uh", "um", "mm", "hmm", "hm", "ah", "er", "eh",
    "uh-huh", "mm-hmm", "mhm", "mmm",
    # Short back-channels kept as annotations rather than discarded:
    # handled separately below
}

# Short back-channel tokens that are KEPT but bracketed as annotations
# e.g. [Mm-hmm]  rather than being stripped entirely
BACKCHANNEL_WORDS = {
    "mm-hmm", "uh-huh", "mhm", "right", "yeah", "yes",
    "okay", "ok", "sure", "good", "ha", "ha.",
}

# Phase 2 — Sentence consolidation
# ---------------------------------
# Gap smaller than this → same sentence still in progress
SENTENCE_GAP_THRESHOLD = 1.8      # seconds

# Phase 3 — Paragraph consolidation
# -----------------------------------
# Gap larger than this → new paragraph / topic break
PARAGRAPH_GAP_THRESHOLD = 3.5     # seconds
# Speaker changes also trigger paragraph breaks (see consolidate_paragraphs)

# Phase 4 — Heuristic speaker classification
# -------------------------------------------
# Fragments at or below this word count are "short" (interviewer-like)
SHORT_WORD_THRESHOLD = 8

# If accumulated word count for current speaker exceeds this, the next
# short-or-question fragment is assumed to be the other speaker returning
LONG_RESPONSE_WORD_COUNT = 50

# Sentence-ending punctuation pattern
SENTENCE_END_PAT = re.compile(r'[.!?…]["\')\]]*\s*$')


# ============================================================================
# PHASE 1 — BREATH / FILLER REMOVAL
# ============================================================================

def _clean_text(text: str) -> str:
    """Normalise whitespace and strip leading/trailing space."""
    return re.sub(r'\s+', ' ', text).strip()


def _is_filler(entry: Dict) -> bool:
    """
    Return True if this entry is a pure filler to be discarded.
    Criteria: very short duration AND text is a known filler word,
    OR text is a known filler word regardless of duration (single-word
    fillers like 'uh' are always noise).
    """
    text = _clean_text(entry.get("text", "")).lower().rstrip(".,")
    duration = entry.get("end", 0) - entry.get("start", 0)

    # Single-word known filler → always discard
    if text in FILLER_WORDS and text not in BACKCHANNEL_WORDS:
        return True

    # Very short AND text looks like noise
    if duration < FILLER_DURATION_THRESHOLD:
        # Allow if it's a real word (more than 2 chars, not a filler)
        words = text.split()
        if len(words) <= 2 and all(len(w) <= 3 for w in words):
            return True

    return False


def _is_backchannel(entry: Dict) -> bool:
    """
    Return True if this entry is a short back-channel that should be
    retained as a bracketed annotation rather than discarded or kept as
    a full segment.
    """
    text = _clean_text(entry.get("text", "")).lower().rstrip(".,")
    duration = entry.get("end", 0) - entry.get("start", 0)
    return (text in BACKCHANNEL_WORDS and
            duration < FILLER_DURATION_THRESHOLD * 1.5)


def strip_fillers(entries: List[Dict]) -> Tuple[List[Dict], int]:
    """
    Phase 1: Remove filler segments, convert back-channels to annotations.

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
            # Keep but mark as annotation — will be bracketed in output
            new_entry = dict(entry)
            text = _clean_text(entry.get("text", ""))
            # Capitalise first letter for display
            new_entry["text"] = f"[{text.capitalize()}]"
            new_entry["is_backchannel"] = True
            cleaned.append(new_entry)
            continue

        cleaned.append(entry)

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
    below SENTENCE_GAP_THRESHOLD and the first does not end with terminal
    punctuation.

    Back-channel annotations are absorbed into the preceding sentence
    as inline text (e.g. "... and I think [Right] we need to...").
    """
    if not entries:
        return []

    sentences = []
    buffer: List[Dict] = []

    def flush_buffer():
        if not buffer:
            return
        # Join all texts in buffer
        parts = []
        for e in buffer:
            t = _clean_text(e.get("text", ""))
            if t:
                parts.append(t)
        joined_text = " ".join(parts)

        sentences.append({
            "start":     buffer[0]["start"],
            "end":       buffer[-1]["end"],
            "text":      joined_text,
            "timestamp": _format_timestamp(buffer[0]["start"]),
            "speaker":   buffer[0].get("speaker", ""),
            "provisional": buffer[0].get("provisional", False),
        })
        buffer.clear()

    for i, entry in enumerate(entries):
        if not buffer:
            buffer.append(entry)
            continue

        prev = buffer[-1]
        gap = entry["start"] - prev["end"]

        # Back-channels are always absorbed into the surrounding sentence
        if entry.get("is_backchannel"):
            buffer.append(entry)
            continue

        # Decide whether to continue the current sentence or start a new one
        if gap <= SENTENCE_GAP_THRESHOLD and not _looks_like_sentence_end(prev.get("text", "")):
            # Same sentence — keep accumulating
            buffer.append(entry)
        else:
            # New sentence
            flush_buffer()
            buffer.append(entry)

    flush_buffer()
    return sentences


# ============================================================================
# PHASE 3 — PARAGRAPH CONSOLIDATION
# ============================================================================

def consolidate_paragraphs(sentences: List[Dict]) -> List[Dict]:
    """
    Phase 3: Group speaker-labelled sentences into paragraphs.

    NOTE: This function now runs AFTER classify_speakers_heuristic, so
    each sentence already carries a "speaker" field.

    A new paragraph starts when ANY of the following occur:
      - The gap between consecutive sentences exceeds PARAGRAPH_GAP_THRESHOLD
      - The speaker label changes between consecutive sentences
      - A topic-break silence (very large gap) occurs regardless of speaker

    This means each paragraph in the output belongs to a single speaker,
    which is the correct structure for a cleaned interview transcript.
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
                # Ensure sentence ends with punctuation for readability
                if t[-1] not in ".!?\u2026\"')]}":
                    t = t + "."
                text_parts.append(t)
        joined = " ".join(text_parts)

        # Preserve per-sentence timestamps so the audio player can seek
        # to individual sentences within the paragraph, not just the start.
        sentence_timestamps = [
            {"text": t, "start": s.get("start", 0.0), "end": s.get("end", 0.0)}
            for s, t in zip(buffer, text_parts)
            if t
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

        if gap > PARAGRAPH_GAP_THRESHOLD or speaker_changed:
            flush_buffer()
            buffer.append(sentence)
        else:
            buffer.append(sentence)

    flush_buffer()
    return paragraphs


# ============================================================================
# PHASE 4 — HEURISTIC SPEAKER CLASSIFICATION
# ============================================================================

def classify_speakers_heuristic(
        paragraphs: List[Dict],
        speaker_a_label: str = "SPEAKER_A",
        speaker_b_label: str = "SPEAKER_B",
) -> List[Dict]:
    """
    Phase 4: Heuristic speaker classification.

    Assigns SPEAKER_A or SPEAKER_B to each paragraph using signals adapted
    from transcript_qa_splitter.py.

    Logic:
    - SPEAKER_A is assumed to be the primary speaker (interviewee) for most
      of the recording.
    - SPEAKER_B is assumed to be the interviewer — characterised by:
        * Paragraphs ending with a question mark
        * Very short paragraphs following a long SPEAKER_A block
        * Very short back-channel paragraphs

    IMPORTANT: These labels are always marked provisional=True.
    They should be presented to users as suggestions requiring review,
    not as reliable determinations.  Oral history interviews in particular
    can have very variable structure that defeats heuristic classification.

    Returns paragraphs with "speaker" and "provisional" fields populated.
    """
    if not paragraphs:
        return []

    result = []
    current_speaker = speaker_b_label  # Assume interviewer speaks first
    words_for_current_speaker = 0

    for para in paragraphs:
        text = para.get("text", "")
        word_count = len(text.split())

        has_question = text.rstrip().endswith("?")
        is_short = word_count <= SHORT_WORD_THRESHOLD
        follows_long_block = words_for_current_speaker >= LONG_RESPONSE_WORD_COUNT

        # Determine if this looks like the other speaker
        switch_likely = has_question or (is_short and follows_long_block)

        if switch_likely and current_speaker == speaker_a_label:
            # Long A block followed by short/question → B (interviewer)
            current_speaker = speaker_b_label
            words_for_current_speaker = 0
        elif switch_likely and current_speaker == speaker_b_label:
            # Short B question followed by longer text → A (interviewee)
            # Only switch if this paragraph itself is not also short
            if not is_short:
                current_speaker = speaker_a_label
                words_for_current_speaker = 0
        elif not switch_likely and current_speaker == speaker_b_label:
            # Sustained non-question content → likely switched to A
            if word_count > SHORT_WORD_THRESHOLD:
                current_speaker = speaker_a_label
                words_for_current_speaker = 0

        new_para = dict(para)
        new_para["speaker"] = current_speaker
        new_para["provisional"] = True
        result.append(new_para)

        words_for_current_speaker += word_count

    return result


# ============================================================================
# PHASE 5 — PYANNOTE ALIGNMENT  (Tier 2)
# ============================================================================

def apply_diarization(
        paragraphs: List[Dict],
        audio_path: str,
        hf_token: str,
        progress_callback: Optional[Callable[[str], None]] = None,
) -> Tuple[List[Dict], bool]:
    """
    Phase 5 (optional): Replace heuristic speaker labels with acoustically-
    verified labels from pyannote.audio.

    Requires:
        - diarization_handler.py in the same folder
        - A valid HuggingFace access token
        - The original audio file (same one faster-whisper transcribed)

    Returns:
        (paragraphs_with_verified_labels, success_flag)
    If diarization fails for any reason, returns the original heuristic-
    labelled paragraphs unchanged and success_flag=False.
    """
    try:
        import diarization_handler
    except ImportError:
        if progress_callback:
            progress_callback(
                "⚠️ diarization_handler not found — using heuristic labels"
            )
        return paragraphs, False

    try:
        success, speaker_timeline = diarization_handler.run_diarization(
            audio_path=audio_path,
            hf_token=hf_token,
            progress_callback=progress_callback,
        )

        if not success:
            return paragraphs, False

        # Align pyannote timeline with paragraph timestamps
        result = []
        for para in paragraphs:
            mid = (para["start"] + para["end"]) / 2.0
            speaker = diarization_handler.speaker_at(speaker_timeline, mid)
            new_para = dict(para)
            new_para["speaker"] = speaker or para["speaker"]
            new_para["provisional"] = (speaker is None)
            result.append(new_para)

        return result, True

    except Exception as e:
        if progress_callback:
            progress_callback(f"⚠️ Diarization failed: {e} — using heuristic labels")
        return paragraphs, False


# ============================================================================
# PHASE 6 — SPEAKER NAME SUBSTITUTION
# ============================================================================

def apply_speaker_names(
        paragraphs: List[Dict],
        name_map: Dict[str, str],
) -> List[Dict]:
    """
    Phase 6: Replace internal speaker IDs with real names.

    name_map examples:
        {"SPEAKER_A": "Margaret", "SPEAKER_B": "Interviewer"}
        {"SPEAKER_00": "John Smith", "SPEAKER_01": "Dr. Jones"}

    Any speaker ID not in name_map is left unchanged.
    """
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
        progress_callback: Optional[Callable[[str], None]] = None,
) -> Dict:
    """
    Full transcript cleaning pipeline.

    Args:
        entries:           Raw faster-whisper entries (list of dicts with
                           start, end, text, timestamp fields)
        audio_path:        Path to the original audio file (needed for
                           Tier 2 pyannote diarization only)
        hf_token:          HuggingFace access token (Tier 2 only)
        name_map:          Dict mapping speaker IDs to real names, e.g.
                           {"SPEAKER_A": "Margaret", "SPEAKER_B": "John"}
        use_diarization:   If True and audio_path + hf_token are provided,
                           attempt Tier 2 pyannote diarization
        keep_backchannels: If True (default), retain [Mm-hmm] style annotations
                           in output text.  If False, strip them.
        progress_callback: Optional function(str) for status updates

    Returns:
        dict with keys:
            "paragraphs"         List[Dict] — cleaned, labelled paragraphs
            "fillers_removed"    int  — count of filler segments stripped
            "diarization_used"   bool — True if pyannote was used
            "speaker_ids"        List[str] — unique speaker IDs found
            "warnings"           List[str] — any non-fatal issues encountered
    """
    warnings_out = []

    def _progress(msg):
        if progress_callback:
            progress_callback(msg)

    # ── Phase 1: Strip fillers ──────────────────────────────────────────
    _progress("Cleaning breath fragments...")
    cleaned, fillers_removed = strip_fillers(entries)
    _progress(f"  Removed {fillers_removed} filler segments.")

    if not keep_backchannels:
        cleaned = [e for e in cleaned if not e.get("is_backchannel")]

    if not cleaned:
        warnings_out.append("No segments remained after filler removal.")
        return {
            "paragraphs": [],
            "fillers_removed": fillers_removed,
            "diarization_used": False,
            "speaker_ids": [],
            "warnings": warnings_out,
        }

    # ── Phase 2: Consolidate sentences ─────────────────────────────────
    _progress("Consolidating fragments into sentences...")
    sentences = consolidate_sentences(cleaned)
    _progress(f"  Formed {len(sentences)} sentences from {len(cleaned)} segments.")

    # ── Phase 3: Heuristic speaker classification (at sentence level) ───
    # Must run BEFORE paragraph consolidation so that speaker changes
    # can be used as paragraph boundaries.
    _progress("Applying heuristic speaker classification...")
    sentences = classify_speakers_heuristic(sentences)
    _progress("  Speaker classification complete (provisional).")

    # ── Phase 4: Consolidate paragraphs (speaker-aware) ─────────────────
    # Now groups sentences into paragraphs, starting a new paragraph
    # whenever the speaker changes or a large gap occurs.
    _progress("Grouping sentences into paragraphs...")
    paragraphs = consolidate_paragraphs(sentences)
    _progress(f"  Formed {len(paragraphs)} paragraphs from {len(sentences)} sentences.")

    # ── Phase 5: Optional pyannote diarization ──────────────────────────
    diarization_used = False
    if use_diarization and audio_path and hf_token:
        _progress("Starting voice-based speaker detection (this may take a while)...")
        paragraphs, diarization_used = apply_diarization(
            paragraphs, audio_path, hf_token, _progress
        )
        if diarization_used:
            _progress("  Voice-based speaker detection complete.")
        else:
            warnings_out.append(
                "Voice-based speaker detection failed or was unavailable. "
                "Heuristic labels used instead."
            )

    # ── Phase 6: Speaker name substitution ─────────────────────────────
    if name_map:
        _progress("Applying speaker names...")
        paragraphs = apply_speaker_names(paragraphs, name_map)

    # ── Collect unique speaker IDs ──────────────────────────────────────
    speaker_ids = sorted({p.get("speaker", "") for p in paragraphs if p.get("speaker")})

    return {
        "paragraphs":       paragraphs,
        "fillers_removed":  fillers_removed,
        "diarization_used": diarization_used,
        "speaker_ids":      speaker_ids,
        "warnings":         warnings_out,
    }


# ============================================================================
# CONVERT TO DOCANALYSER ENTRIES  (primary integration output)
# ============================================================================

def paragraphs_to_entries(paragraphs: List[Dict]) -> List[Dict]:
    """
    Convert cleaned paragraphs to DocAnalyser's native entries format.

    This is the preferred output when integrating with DocAnalyser because
    it preserves start/end timestamps so DocAnalyser's existing audio-seek
    infrastructure (Thread Viewer seek links) works automatically.

    Each returned entry is compatible with entries_to_text_with_speakers()
    and can be stored directly in current_entries.
    """
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
        # Preserve sentence-level timestamps if present — used by the
        # audio player for fine-grained sentence-click-to-seek.
        if "sentences" in para:
            entry["sentences"] = para["sentences"]
        entries.append(entry)
    return entries


# ============================================================================
# FORMAT OUTPUT AS PLAIN TEXT  (for DocAnalyser document model)
# ============================================================================

def paragraphs_to_text(
        paragraphs: List[Dict],
        include_timestamps: bool = True,
        include_speaker_labels: bool = True,
        provisional_note: bool = True,
) -> str:
    """
    Convert cleaned paragraphs to plain text for DocAnalyser.

    Format:
        [00:01:23]  SPEAKER_A  (provisional)
        Text of the paragraph...

        [00:04:12]  SPEAKER_B  (provisional)
        Text of the next paragraph...

    Args:
        paragraphs:            Output from clean_transcript()["paragraphs"]
        include_timestamps:    Prepend [HH:MM:SS] to each paragraph
        include_speaker_labels: Include speaker name/ID
        provisional_note:      Append "(suggested)" to provisional labels

    Returns:
        Plain text string ready to be stored in DocAnalyser's
        current_document_text
    """
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
        lines.append("")   # blank line between paragraphs

    return "\n".join(lines).strip()


# ============================================================================
# STANDALONE TEST RUNNER
# ============================================================================

def _parse_dummy_transcript(filepath: str) -> List[Dict]:
    """
    Parse the dummy_transcript.txt file format:
        [HH:MM:SS.mmm --> HH:MM:SS.mmm]  SPEAKER_XX  text

    Or the plain faster-whisper format (no speaker column):
        [HH:MM:SS.mmm --> HH:MM:SS.mmm]  text

    Returns entries in DocAnalyser format.
    """
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
                # m.group(3) is the speaker if present (ignored for testing)
                text    = m.group(4).strip()
                if text:
                    entries.append({
                        "start":     start_s,
                        "end":       end_s,
                        "text":      text,
                        "timestamp": f"[{m.group(1)[:8]}]",
                    })
    return entries


def _print_phase_stats(label: str, items: List[Dict]):
    print(f"\n{'─'*60}")
    print(f"  {label}  ({len(items)} items)")
    print(f"{'─'*60}")
    for item in items[:8]:   # show first 8 only
        ts  = item.get("timestamp", "")
        spk = item.get("speaker", "")
        txt = item.get("text", "")
        dur = item.get("end", 0) - item.get("start", 0)
        if spk:
            print(f"  {ts}  [{spk}]  ({dur:.2f}s)  {txt[:80]}")
        else:
            print(f"  {ts}  ({dur:.2f}s)  {txt[:80]}")
    if len(items) > 8:
        print(f"  ... and {len(items) - 8} more")


def main():
    global SENTENCE_GAP_THRESHOLD, PARAGRAPH_GAP_THRESHOLD

    parser = argparse.ArgumentParser(
        description="Test transcript_cleaner.py on a dummy transcript file."
    )
    parser.add_argument(
        "input",
        nargs="?",
        default="dummy_transcript.txt",
        help="Path to transcript .txt file (default: dummy_transcript.txt)",
    )
    parser.add_argument(
        "--show-phases",
        action="store_true",
        help="Print intermediate results after each phase",
    )
    parser.add_argument(
        "--min-sentence-gap",
        type=float,
        default=SENTENCE_GAP_THRESHOLD,
        help=f"Sentence gap threshold in seconds (default: {SENTENCE_GAP_THRESHOLD})",
    )
    parser.add_argument(
        "--min-para-gap",
        type=float,
        default=PARAGRAPH_GAP_THRESHOLD,
        help=f"Paragraph gap threshold in seconds (default: {PARAGRAPH_GAP_THRESHOLD})",
    )
    args = parser.parse_args()

    # Allow threshold overrides from command line
    SENTENCE_GAP_THRESHOLD  = args.min_sentence_gap
    PARAGRAPH_GAP_THRESHOLD = args.min_para_gap

    if not os.path.exists(args.input):
        print(f"ERROR: File not found: {args.input}")
        print("Tip: run generate_final.py first to create dummy_transcript.txt")
        sys.exit(1)

    print(f"\nTranscript Cleaner — Test Run")
    print(f"{'='*60}")
    print(f"Input file:          {args.input}")
    print(f"Sentence gap:        {SENTENCE_GAP_THRESHOLD}s")
    print(f"Paragraph gap:       {PARAGRAPH_GAP_THRESHOLD}s")
    print(f"Short word limit:    {SHORT_WORD_THRESHOLD} words")
    print(f"Long response limit: {LONG_RESPONSE_WORD_COUNT} words")

    # Parse
    print(f"\nParsing transcript...")
    entries = _parse_dummy_transcript(args.input)
    print(f"  {len(entries)} segments loaded.")

    if args.show_phases:
        _print_phase_stats("RAW ENTRIES", entries)

    # Run pipeline
    def progress(msg):
        print(f"  {msg}")

    result = clean_transcript(
        entries=entries,
        progress_callback=progress,
        keep_backchannels=True,
    )

    paragraphs = result["paragraphs"]

    if args.show_phases:
        _print_phase_stats("CLEANED PARAGRAPHS", paragraphs)

    # Summary
    print(f"\n{'='*60}")
    print(f"RESULTS SUMMARY")
    print(f"{'='*60}")
    print(f"  Input segments:      {len(entries)}")
    print(f"  Fillers removed:     {result['fillers_removed']}")
    print(f"  Output paragraphs:   {len(paragraphs)}")
    print(f"  Speaker IDs found:   {result['speaker_ids']}")
    if result["warnings"]:
        print(f"  Warnings:")
        for w in result["warnings"]:
            print(f"    ⚠  {w}")

    # Write output
    output_path = os.path.splitext(args.input)[0] + "_cleaned.txt"
    text_output = paragraphs_to_text(
        paragraphs,
        include_timestamps=True,
        include_speaker_labels=True,
        provisional_note=True,
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(text_output)

    print(f"\n✅ Cleaned transcript written to:\n   {output_path}")
    print(f"\nTip: re-run with --show-phases to see intermediate results")
    print(f"     re-run with different --min-sentence-gap / --min-para-gap")
    print(f"     values to tune consolidation behaviour")


if __name__ == "__main__":
    main()
