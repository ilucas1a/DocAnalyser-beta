"""
transcript_cleaner.py
=====================
Core transcript processing engine for DocAnalyser.

Takes raw faster-whisper entries (list of dicts with start/end/text fields)
and produces cleaned, consolidated, speaker-labelled entries ready for
DocAnalyser's document model — with full audio seek-link support.

Processing pipeline
-------------------
Phase 1  — Strip breath fragments
           Remove sub-threshold segments (very short duration or known
           filler words: uh, um, mm, hmm, etc.)
           Back-channel interjections (mm-hmm, right, yeah) are retained
           as bracketed annotations [Mm-hmm] rather than discarded.

Phase 2  — Consolidate into sentences
           Join consecutive segments into sentences using timing gaps.
           Gap below SENTENCE_GAP_THRESHOLD = same sentence continuing.
           Terminal punctuation also signals a sentence boundary.

Phase 3  — Heuristic speaker classification  (Tier 1, sentence level)
           Classify each sentence as SPEAKER_A or SPEAKER_B.
           Runs BEFORE paragraph consolidation so that speaker changes
           can serve as paragraph boundaries.
           Always marked provisional=True — requires user review.

Phase 4  — Consolidate into paragraphs  (speaker-aware)
           Group sentences into paragraphs. New paragraph starts when:
             - gap between sentences exceeds PARAGRAPH_GAP_THRESHOLD, OR
             - speaker label changes between consecutive sentences.
           Each paragraph therefore belongs to a single speaker.

Phase 5  — (Optional, Tier 2)  Pyannote alignment
           Replace heuristic labels with acoustically-verified labels
           from pyannote.audio. Requires HuggingFace token + audio file.

Phase 6  — Speaker name substitution
           Replace SPEAKER_A / SPEAKER_B with real names from dialog.

Audio linking
-------------
Every paragraph retains its start/end timestamps from the original
faster-whisper segments. Two audio-link fields are added to each paragraph:

  audio_seek_seconds  - float, seconds from audio start (e.g. 228.4)
  audio_seek_label    - human-readable string  (e.g. "▶ 03:48")

When paragraphs are converted to DocAnalyser entries via
paragraphs_to_entries(), the start/end values are preserved so
DocAnalyser's existing Thread Viewer seek infrastructure works
automatically with no extra wiring.

Output format (per paragraph dict)
------------------------------------
    {
        "start":              float,  # seconds from audio start
        "end":                float,  # seconds from audio start
        "text":               str,    # cleaned, consolidated text
        "timestamp":          str,    # "[HH:MM:SS]" for display
        "speaker":            str,    # "SPEAKER_A", "SPEAKER_B", or real name
        "provisional":        bool,   # True if speaker label is heuristic
        "audio_seek_seconds": float,  # = start, explicit alias for clarity
        "audio_seek_label":   str,    # "▶ MM:SS" clickable label text
    }

Standalone testing
------------------
    python transcript_cleaner.py dummy_transcript.txt
    python transcript_cleaner.py dummy_transcript.txt --show-phases
    python transcript_cleaner.py dummy_transcript.txt --min-sentence-gap 1.5
"""

from __future__ import annotations

import re
import sys
import os
import argparse
from typing import List, Dict, Optional, Callable, Tuple


# ============================================================================
# TUNING CONSTANTS  (all timing values in seconds)
# ============================================================================

FILLER_DURATION_THRESHOLD = 0.60

FILLER_WORDS = {
    "uh", "um", "mm", "hmm", "hm", "ah", "er", "eh",
}

BACKCHANNEL_WORDS = {
    "mm-hmm", "uh-huh", "mhm", "mmm", "right", "yeah", "yes",
    "okay", "ok", "sure", "good", "ha", "ha.",
}

SENTENCE_GAP_THRESHOLD   = 1.8
PARAGRAPH_GAP_THRESHOLD  = 4.0
SHORT_WORD_THRESHOLD     = 8
LONG_RESPONSE_WORD_COUNT = 50

SENTENCE_END_PAT = re.compile(r'[.!?…]["\')\]]*\s*$')


# ============================================================================
# AUDIO LINK HELPERS
# ============================================================================

def _format_timestamp(seconds: float) -> str:
    """Format seconds as [HH:MM:SS] for display."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"[{h:02d}:{m:02d}:{s:02d}]"


def _format_seek_label(seconds: float) -> str:
    """
    Format seconds as a short seek label for audio linking.
    Examples:  '▶ 03:48'   '▶ 1:02:15'
    Matches the format DocAnalyser's Thread Viewer renders for seek links.
    """
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"\u25b6 {h}:{m:02d}:{s:02d}"
    return f"\u25b6 {m:02d}:{s:02d}"


def _add_audio_links(item: Dict) -> Dict:
    """
    Inject audio_seek_seconds and audio_seek_label into a paragraph or
    sentence dict.  Called whenever an item is finalised.
    """
    start = item.get("start", 0.0)
    item["audio_seek_seconds"] = start
    item["audio_seek_label"]   = _format_seek_label(start)
    return item


# ============================================================================
# PHASE 1 — BREATH / FILLER REMOVAL
# ============================================================================

def _clean_text(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()


def _is_filler(entry: Dict) -> bool:
    text     = _clean_text(entry.get("text", "")).lower().rstrip(".,")
    duration = entry.get("end", 0) - entry.get("start", 0)

    if text in FILLER_WORDS:
        return True

    if duration < FILLER_DURATION_THRESHOLD:
        words = text.split()
        if len(words) <= 2 and all(len(w) <= 3 for w in words):
            return True

    return False


def _is_backchannel(entry: Dict) -> bool:
    text     = _clean_text(entry.get("text", "")).lower().rstrip(".,")
    duration = entry.get("end", 0) - entry.get("start", 0)
    return (text in BACKCHANNEL_WORDS and
            duration < FILLER_DURATION_THRESHOLD * 1.5)


def strip_fillers(entries: List[Dict]) -> Tuple[List[Dict], int]:
    """
    Phase 1: Remove filler segments; convert back-channels to [annotations].
    Returns (cleaned_entries, count_removed).
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
            new_entry["text"]           = f"[{text.capitalize()}]"
            new_entry["is_backchannel"] = True
            cleaned.append(new_entry)
            continue
        cleaned.append(entry)

    return cleaned, removed


# ============================================================================
# PHASE 2 — SENTENCE CONSOLIDATION
# ============================================================================

def _looks_like_sentence_end(text: str) -> bool:
    return bool(SENTENCE_END_PAT.search(text.rstrip()))


def consolidate_sentences(entries: List[Dict]) -> List[Dict]:
    """
    Phase 2: Join consecutive entries into sentences.

    Entries belong to the same sentence if gap <= SENTENCE_GAP_THRESHOLD
    and the previous entry does not end with terminal punctuation.
    Back-channel annotations are absorbed inline.
    Audio seek fields are added to every output sentence.
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
        joined = " ".join(parts)
        sentence = {
            "start":       buffer[0]["start"],
            "end":         buffer[-1]["end"],
            "text":        joined,
            "timestamp":   _format_timestamp(buffer[0]["start"]),
            "speaker":     buffer[0].get("speaker", ""),
            "provisional": buffer[0].get("provisional", False),
        }
        sentences.append(_add_audio_links(sentence))
        buffer.clear()

    for entry in entries:
        if not buffer:
            buffer.append(entry)
            continue

        prev = buffer[-1]
        gap  = entry["start"] - prev["end"]

        if entry.get("is_backchannel"):
            buffer.append(entry)
            continue

        if (gap <= SENTENCE_GAP_THRESHOLD
                and not _looks_like_sentence_end(prev.get("text", ""))):
            buffer.append(entry)
        else:
            flush_buffer()
            buffer.append(entry)

    flush_buffer()
    return sentences


# ============================================================================
# PHASE 3 — HEURISTIC SPEAKER CLASSIFICATION  (at sentence level)
# ============================================================================

def classify_speakers_heuristic(
        sentences: List[Dict],
        speaker_a_label: str = "SPEAKER_A",
        speaker_b_label: str = "SPEAKER_B",
) -> List[Dict]:
    """
    Phase 3: Assign SPEAKER_A / SPEAKER_B to each sentence heuristically.

    Must run BEFORE consolidate_paragraphs so that speaker changes can
    be used as paragraph boundaries.

    SPEAKER_A = interviewee (primary speaker, longer responses).
    SPEAKER_B = interviewer (questions, short interjections).

    All labels are provisional=True.  Oral history interviews have variable
    structure — these labels need user review.
    """
    if not sentences:
        return []

    result = []
    current_speaker           = speaker_b_label  # interviewer assumed to open
    words_for_current_speaker = 0

    for sentence in sentences:
        text       = sentence.get("text", "")
        word_count = len(text.split())

        has_question = text.rstrip().endswith("?")
        is_short     = word_count <= SHORT_WORD_THRESHOLD
        follows_long = words_for_current_speaker >= LONG_RESPONSE_WORD_COUNT

        switch_likely = has_question or (is_short and follows_long)

        if switch_likely and current_speaker == speaker_a_label:
            current_speaker           = speaker_b_label
            words_for_current_speaker = 0
        elif switch_likely and current_speaker == speaker_b_label:
            if not is_short:
                current_speaker           = speaker_a_label
                words_for_current_speaker = 0
        elif not switch_likely and current_speaker == speaker_b_label:
            if word_count > SHORT_WORD_THRESHOLD:
                current_speaker           = speaker_a_label
                words_for_current_speaker = 0

        new_sentence = dict(sentence)
        new_sentence["speaker"]     = current_speaker
        new_sentence["provisional"] = True
        result.append(new_sentence)

        words_for_current_speaker += word_count

    return result


# ============================================================================
# PHASE 4 — PARAGRAPH CONSOLIDATION  (speaker-aware)
# ============================================================================

def consolidate_paragraphs(sentences: List[Dict]) -> List[Dict]:
    """
    Phase 4: Group speaker-labelled sentences into paragraphs.

    NOTE: Must run AFTER classify_speakers_heuristic.

    A new paragraph starts when:
      - gap between consecutive sentences > PARAGRAPH_GAP_THRESHOLD, OR
      - the speaker label changes

    Each paragraph belongs to one speaker.
    Audio seek fields are set to the paragraph's opening timestamp.
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
                if t[-1] not in ".!?…\"')]}":
                    t += "."
                text_parts.append(t)
        joined = " ".join(text_parts)

        para = {
            "start":       buffer[0]["start"],
            "end":         buffer[-1]["end"],
            "text":        joined,
            "timestamp":   _format_timestamp(buffer[0]["start"]),
            "speaker":     buffer[0].get("speaker", ""),
            "provisional": buffer[0].get("provisional", False),
        }
        paragraphs.append(_add_audio_links(para))
        buffer.clear()

    for sentence in sentences:
        if not buffer:
            buffer.append(sentence)
            continue

        prev = buffer[-1]
        gap  = sentence["start"] - prev["end"]
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
# PHASE 5 — PYANNOTE ALIGNMENT  (Tier 2, optional)
# ============================================================================

def apply_diarization(
        paragraphs: List[Dict],
        audio_path: str,
        hf_token: str,
        progress_callback: Optional[Callable[[str], None]] = None,
) -> Tuple[List[Dict], bool]:
    """
    Phase 5 (optional): Replace heuristic speaker labels with
    acoustically-verified labels from pyannote.audio.
    Falls back gracefully to heuristic labels on any failure.
    Returns (paragraphs, success_flag).
    """
    try:
        import diarization_handler
    except ImportError:
        if progress_callback:
            progress_callback(
                "Warning: diarization_handler not found — using heuristic labels"
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

        result = []
        for para in paragraphs:
            mid     = (para["start"] + para["end"]) / 2.0
            speaker = diarization_handler.speaker_at(speaker_timeline, mid)
            new_para = dict(para)
            new_para["speaker"]     = speaker or para["speaker"]
            new_para["provisional"] = (speaker is None)
            result.append(new_para)

        return result, True

    except Exception as e:
        if progress_callback:
            progress_callback(
                f"Warning: Diarization failed ({e}) — using heuristic labels"
            )
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
    name_map example: {"SPEAKER_A": "Margaret", "SPEAKER_B": "Interviewer"}
    Any ID not in name_map is left unchanged.
    """
    result = []
    for para in paragraphs:
        new_para = dict(para)
        speaker  = para.get("speaker", "")
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
        entries:           Raw faster-whisper entries — list of dicts with
                           start (float), end (float), text (str),
                           timestamp (str)
        audio_path:        Path to the original audio file. Required for
                           Tier 2 diarization; also stored in result so
                           callers can wire up audio seek links.
        hf_token:          HuggingFace access token (Tier 2 only).
        name_map:          Dict mapping speaker IDs to real names.
        use_diarization:   Attempt Tier 2 pyannote if True and prerequisites
                           are available.
        keep_backchannels: Retain [Mm-hmm] style annotations if True.
        progress_callback: Optional function(str) for status messages.

    Returns dict:
        "paragraphs"          List[Dict] — cleaned paragraphs, each with
                              audio_seek_seconds and audio_seek_label fields
        "fillers_removed"     int
        "diarization_used"    bool
        "speaker_ids"         List[str]
        "audio_path"          str or None — original audio file path, stored
                              here so callers can register it for seek links
        "warnings"            List[str]
    """
    warnings_out = []

    def _progress(msg):
        if progress_callback:
            progress_callback(msg)

    # Phase 1
    _progress("Cleaning breath fragments...")
    cleaned, fillers_removed = strip_fillers(entries)
    _progress(f"  Removed {fillers_removed} filler segments.")

    if not keep_backchannels:
        cleaned = [e for e in cleaned if not e.get("is_backchannel")]

    if not cleaned:
        warnings_out.append("No segments remained after filler removal.")
        return {
            "paragraphs":       [],
            "fillers_removed":  fillers_removed,
            "diarization_used": False,
            "speaker_ids":      [],
            "audio_path":       audio_path,
            "warnings":         warnings_out,
        }

    # Phase 2
    _progress("Consolidating fragments into sentences...")
    sentences = consolidate_sentences(cleaned)
    _progress(f"  Formed {len(sentences)} sentences from {len(cleaned)} segments.")

    # Phase 3 — before Phase 4 so speaker changes become paragraph breaks
    _progress("Applying heuristic speaker classification...")
    sentences = classify_speakers_heuristic(sentences)
    _progress("  Speaker classification complete (provisional).")

    # Phase 4
    _progress("Grouping sentences into paragraphs...")
    paragraphs = consolidate_paragraphs(sentences)
    _progress(f"  Formed {len(paragraphs)} paragraphs from {len(sentences)} sentences.")

    # Phase 5 (optional)
    diarization_used = False
    if use_diarization and audio_path and hf_token:
        _progress(
            "Starting voice-based speaker detection "
            "(may take as long as the recording on CPU)..."
        )
        paragraphs, diarization_used = apply_diarization(
            paragraphs, audio_path, hf_token, _progress
        )
        if diarization_used:
            _progress("  Voice-based speaker detection complete.")
        else:
            warnings_out.append(
                "Voice-based speaker detection was unavailable or failed. "
                "Heuristic labels used instead."
            )

    # Phase 6
    if name_map:
        _progress("Applying speaker names...")
        paragraphs = apply_speaker_names(paragraphs, name_map)

    speaker_ids = sorted(
        {p.get("speaker", "") for p in paragraphs if p.get("speaker")}
    )

    return {
        "paragraphs":       paragraphs,
        "fillers_removed":  fillers_removed,
        "diarization_used": diarization_used,
        "speaker_ids":      speaker_ids,
        "audio_path":       audio_path,
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

    The Thread Viewer will render clickable seek links from the start field
    with no extra wiring required.
    """
    entries = []
    for para in paragraphs:
        entries.append({
            "start":       para.get("start", 0.0),
            "end":         para.get("end", 0.0),
            "text":        para.get("text", ""),
            "timestamp":   para.get("timestamp", ""),
            "speaker":     para.get("speaker", ""),
            "provisional": para.get("provisional", False),
        })
    return entries


# ============================================================================
# FORMAT OUTPUT AS PLAIN TEXT  (testing / standalone use)
# ============================================================================

def paragraphs_to_text(
        paragraphs: List[Dict],
        include_timestamps: bool = True,
        include_speaker_labels: bool = True,
        provisional_note: bool = True,
        include_seek_links: bool = True,
) -> str:
    """
    Convert cleaned paragraphs to human-readable plain text.

    Format per paragraph:
        [00:03:48]  SPEAKER_A (suggested)  ▶ 03:48
        Text of the paragraph...

    The ▶ MM:SS marker is in the format DocAnalyser's Thread Viewer
    recognises for audio seek links when embedded in text.
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

        if include_seek_links:
            seek = para.get("audio_seek_label", "")
            if seek:
                header_parts.append(seek)

        if header_parts:
            lines.append("  ".join(header_parts))

        lines.append(para.get("text", ""))
        lines.append("")

    return "\n".join(lines).strip()


# ============================================================================
# STANDALONE TEST RUNNER
# ============================================================================

def _parse_dummy_transcript(filepath: str) -> List[Dict]:
    """
    Parse faster-whisper style .txt into DocAnalyser entries.
    Handles lines with or without a SPEAKER_XX column.
    """
    entries = []
    pat = re.compile(
        r'\[(\d{2}:\d{2}:\d{2}\.\d+)\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d+)\]'
        r'(?:\s+SPEAKER_\w+)?\s+(.*)'
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
                text    = m.group(3).strip()
                if text:
                    entries.append({
                        "start":     start_s,
                        "end":       end_s,
                        "text":      text,
                        "timestamp": _format_timestamp(start_s),
                    })
    return entries


def _print_phase_stats(label: str, items: List[Dict]):
    print(f"\n{'─'*60}")
    print(f"  {label}  ({len(items)} items)")
    print(f"{'─'*60}")
    for item in items[:10]:
        ts   = item.get("timestamp", "")
        spk  = item.get("speaker", "")
        txt  = item.get("text", "")
        dur  = item.get("end", 0) - item.get("start", 0)
        seek = item.get("audio_seek_label", "")
        if spk:
            print(f"  {ts}  [{spk}]  {seek}  ({dur:.1f}s)  {txt[:65]}")
        else:
            print(f"  {ts}  ({dur:.2f}s)  {txt[:80]}")
    if len(items) > 10:
        print(f"  ... and {len(items) - 10} more")


def main():
    global SENTENCE_GAP_THRESHOLD, PARAGRAPH_GAP_THRESHOLD

    parser = argparse.ArgumentParser(
        description="Test transcript_cleaner.py on a faster-whisper transcript."
    )
    parser.add_argument(
        "input", nargs="?", default="dummy_transcript.txt",
        help="Path to .txt transcript file (default: dummy_transcript.txt)",
    )
    parser.add_argument(
        "--show-phases", action="store_true",
        help="Print intermediate results after each phase",
    )
    parser.add_argument(
        "--min-sentence-gap", type=float, default=SENTENCE_GAP_THRESHOLD,
        help=f"Sentence gap threshold seconds (default: {SENTENCE_GAP_THRESHOLD})",
    )
    parser.add_argument(
        "--min-para-gap", type=float, default=PARAGRAPH_GAP_THRESHOLD,
        help=f"Paragraph gap threshold seconds (default: {PARAGRAPH_GAP_THRESHOLD})",
    )
    args = parser.parse_args()

    SENTENCE_GAP_THRESHOLD  = args.min_sentence_gap
    PARAGRAPH_GAP_THRESHOLD = args.min_para_gap

    if not os.path.exists(args.input):
        print(f"ERROR: File not found: {args.input}")
        sys.exit(1)

    print(f"\nTranscript Cleaner — Test Run")
    print(f"{'='*60}")
    print(f"Input file:          {args.input}")
    print(f"Sentence gap:        {SENTENCE_GAP_THRESHOLD}s")
    print(f"Paragraph gap:       {PARAGRAPH_GAP_THRESHOLD}s")
    print(f"Short word limit:    {SHORT_WORD_THRESHOLD} words")
    print(f"Long response limit: {LONG_RESPONSE_WORD_COUNT} words")

    print(f"\nParsing transcript...")
    entries = _parse_dummy_transcript(args.input)
    print(f"  {len(entries)} segments loaded.")

    if args.show_phases:
        _print_phase_stats("RAW ENTRIES", entries)

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

    print(f"\n{'='*60}")
    print(f"RESULTS SUMMARY")
    print(f"{'='*60}")
    print(f"  Input segments:      {len(entries)}")
    print(f"  Fillers removed:     {result['fillers_removed']}")
    print(f"  Output paragraphs:   {len(paragraphs)}")
    print(f"  Speaker IDs found:   {result['speaker_ids']}")
    if result["warnings"]:
        for w in result["warnings"]:
            print(f"  WARNING: {w}")

    # Write text output
    txt_path = os.path.splitext(args.input)[0] + "_cleaned.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(paragraphs_to_text(
            paragraphs,
            include_timestamps=True,
            include_speaker_labels=True,
            provisional_note=True,
            include_seek_links=True,
        ))
    print(f"\n  Cleaned transcript written to: {txt_path}")

    # Show first 4 paragraphs with full audio link data
    print(f"\nFirst 4 paragraphs with audio seek data:")
    print(f"{'─'*60}")
    for i, para in enumerate(paragraphs[:4]):
        print(f"  [{i+1}] Speaker:   {para.get('speaker', '')}  "
              f"({'suggested' if para.get('provisional') else 'verified'})")
        print(f"       Timestamp: {para.get('timestamp', '')}")
        print(f"       Seek link: {para.get('audio_seek_label', '')}")
        print(f"       Seek secs: {para.get('audio_seek_seconds', 0.0):.1f}s")
        text_preview = para.get('text', '')[:90]
        print(f"       Text:      {text_preview}...")
        print()

    print(f"Tip: --show-phases for full phase breakdown")
    print(f"     --min-sentence-gap / --min-para-gap to tune thresholds")


if __name__ == "__main__":
    main()
