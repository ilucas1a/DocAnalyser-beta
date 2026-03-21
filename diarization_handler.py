"""
diarization_handler.py
======================
Pyannote.audio wrapper for DocAnalyser — Tier 2 speaker diarization.

This module is intentionally isolated from the rest of DocAnalyser so that
its absence (pyannote not installed, no HuggingFace token, model not yet
downloaded) never causes an import error or crash elsewhere.

All public functions return a success flag as their first value so callers
can degrade gracefully to Tier 1 heuristic labels without exception handling.

What this module does
---------------------
1.  Checks whether pyannote.audio is installed and the model is available.
2.  Runs pyannote speaker diarization on a local audio file, producing a
    timeline of (start_seconds, end_seconds, speaker_id) tuples.
3.  Provides speaker_at(timeline, time_seconds) to look up which speaker
    was active at any given moment — used by transcript_cleaner.py to align
    pyannote's output with faster-whisper's paragraph timestamps.
4.  Handles model download with progress reporting.
5.  Provides is_available() and get_status() for the DocAnalyser UI to
    query before deciding which options to offer the user.

Speaker ID mapping
------------------
Pyannote returns labels like "SPEAKER_00", "SPEAKER_01".  This module
normalises them to uppercase and passes them through unchanged.  The
name substitution step in transcript_cleaner.py (Phase 6) maps them to
real names after the user has assigned names in the cleanup dialog.

CPU performance note
--------------------
On a CPU-only machine, pyannote/speaker-diarization-3.1 takes roughly
the same wall-clock time as the recording duration for a two-speaker
interview.  A 60-minute recording takes approximately 55-70 minutes to
diarise on a modern CPU.  The progress_callback receives periodic updates
so DocAnalyser can show a progress bar.

The newer Community-1 model may be faster and more accurate but requires
the same HuggingFace setup steps.  MODEL_ID can be changed here to switch.

Requirements (Tier 2 only — not needed for Tier 1)
----------------------------------------------------
    pip install pyannote.audio
    pip install torch torchaudio   (may already be present for faster-whisper)

    HuggingFace account:  https://huggingface.co
    Model licence:        https://huggingface.co/pyannote/speaker-diarization-3.1
    Access token:         https://huggingface.co/settings/tokens
"""

from __future__ import annotations

import os
import sys
import logging
from typing import List, Tuple, Optional, Callable, Dict

logger = logging.getLogger(__name__)

# ── Model to use ─────────────────────────────────────────────────────────────
# Change this to "pyannote/speaker-diarization-community-1" to use the newer
# community model (same setup steps, potentially better accuracy).
MODEL_ID = "pyannote/speaker-diarization-community-1"

# ── Type alias ───────────────────────────────────────────────────────────────
# A speaker timeline is a list of (start_secs, end_secs, speaker_id) tuples
# sorted by start time.
SpeakerTimeline = List[Tuple[float, float, str]]


# ============================================================================
# AVAILABILITY CHECKS
# ============================================================================

def is_pyannote_installed() -> bool:
    """Return True if pyannote.audio is importable."""
    try:
        import pyannote.audio  # noqa: F401
        return True
    except ImportError:
        return False


def is_torch_available() -> bool:
    """Return True if PyTorch is importable."""
    try:
        import torch  # noqa: F401
        return True
    except ImportError:
        return False


def is_model_cached(hf_token: Optional[str] = None) -> bool:
    """
    Return True if the pyannote model appears to be downloaded locally.
    Does a lightweight check via huggingface_hub without loading the model.
    """
    try:
        from huggingface_hub import try_to_load_from_cache
        # Check for a small file that is always present in the model repo
        result = try_to_load_from_cache(MODEL_ID, "config.yaml")
        return result is not None
    except Exception:
        # huggingface_hub not installed or check failed — assume not cached
        return False


def is_available(hf_token: Optional[str] = None) -> bool:
    """
    Return True if Tier 2 diarization is fully ready to run:
      - pyannote.audio installed
      - torch installed
      - HuggingFace token provided
      - Model has been downloaded (cached locally)
    """
    return (
        is_pyannote_installed()
        and is_torch_available()
        and bool(hf_token)
        and is_model_cached(hf_token)
    )


def get_status(hf_token: Optional[str] = None) -> Dict[str, object]:
    """
    Return a status dict for the DocAnalyser UI to display.

    Keys:
        ready          bool   — True if diarization can run immediately
        pyannote       bool   — pyannote.audio installed
        torch          bool   — torch installed
        token_present  bool   — HuggingFace token is non-empty
        model_cached   bool   — model downloaded locally
        message        str    — human-readable summary for UI display
    """
    pyannote_ok  = is_pyannote_installed()
    torch_ok     = is_torch_available()
    token_ok     = bool(hf_token)
    cached_ok    = is_model_cached(hf_token) if (pyannote_ok and token_ok) else False
    ready        = pyannote_ok and torch_ok and token_ok and cached_ok

    if ready:
        msg = "Voice speaker detection is ready."
    elif not pyannote_ok:
        msg = "pyannote.audio is not installed. Run: pip install pyannote.audio"
    elif not torch_ok:
        msg = "PyTorch is not installed. Run: pip install torch torchaudio"
    elif not token_ok:
        msg = "No HuggingFace token configured. Complete the one-time setup."
    elif not cached_ok:
        msg = "Model not yet downloaded. Click 'Download model' to begin."
    else:
        msg = "Status unknown."

    return {
        "ready":         ready,
        "pyannote":      pyannote_ok,
        "torch":         torch_ok,
        "token_present": token_ok,
        "model_cached":  cached_ok,
        "message":       msg,
    }


# ============================================================================
# MODEL DOWNLOAD
# ============================================================================

def download_model(
        hf_token: str,
        progress_callback: Optional[Callable[[str, int], None]] = None,
) -> Tuple[bool, str]:
    """
    Download the pyannote speaker diarization model from HuggingFace.

    This is a one-time operation (~1.5 GB).  The model is stored in the
    HuggingFace local cache and reused on all subsequent runs — no internet
    connection is needed after this step.

    Args:
        hf_token:          HuggingFace access token with read permissions.
        progress_callback: Optional function(message: str, percent: int).
                           percent is 0-100; -1 means indeterminate.

    Returns:
        (success: bool, message: str)
    """
    def _progress(msg: str, pct: int = -1):
        logger.info(msg)
        if progress_callback:
            progress_callback(msg, pct)

    if not is_pyannote_installed():
        return False, (
            "pyannote.audio is not installed.\n\n"
            "Open a terminal in your DocAnalyser folder and run:\n"
            "    pip install pyannote.audio"
        )

    if not is_torch_available():
        return False, (
            "PyTorch is not installed.\n\n"
            "Open a terminal in your DocAnalyser folder and run:\n"
            "    pip install torch torchaudio"
        )

    if not hf_token:
        return False, "No HuggingFace token provided."

    _progress("Connecting to HuggingFace...", 0)

    try:
        from pyannote.audio import Pipeline

        _progress(
            f"Downloading {MODEL_ID}...\n"
            "This is approximately 1.5 GB and may take 10-20 minutes\n"
            "depending on your internet connection.\n"
            "Once downloaded, this model stays on your computer permanently\n"
            "and no internet connection is needed for future use.",
            5,
        )

        # Loading the pipeline triggers the download if not cached.
        # There is no built-in per-file progress hook in pyannote, so we
        # report indeterminate progress during the download.
        pipeline = Pipeline.from_pretrained(
            MODEL_ID,
            token=hf_token,
        )

        # Verify it loaded correctly with a tiny smoke test
        _progress("Verifying model...", 90)
        if pipeline is None:
            return False, "Model loaded but pipeline is None — unexpected error."

        _progress("Model downloaded and verified successfully.", 100)
        logger.info(f"Pyannote model {MODEL_ID} downloaded and ready.")
        return True, "Model downloaded successfully. Voice speaker detection is now available."

    except Exception as e:
        error_str = str(e)
        logger.error(f"Model download failed: {error_str}")

        # Provide specific guidance for the most common errors
        if "401" in error_str or "unauthorized" in error_str.lower():
            return False, (
                "HuggingFace token was rejected (401 Unauthorised).\n\n"
                "Please check:\n"
                "  1. Your token is copied correctly with no extra spaces\n"
                "  2. You have accepted the model licence at:\n"
                f"     huggingface.co/{MODEL_ID}\n"
                "  3. Your token has 'read' permissions"
            )
        elif "403" in error_str or "forbidden" in error_str.lower():
            return False, (
                "Access denied (403 Forbidden).\n\n"
                "You need to accept the model licence before downloading:\n"
                f"  1. Go to: huggingface.co/{MODEL_ID}\n"
                "  2. Log in and click 'Agree and access repository'\n"
                "  3. Then try the download again"
            )
        elif "connection" in error_str.lower() or "timeout" in error_str.lower():
            return False, (
                "Connection failed. Please check your internet connection\n"
                "and try again."
            )
        else:
            return False, f"Download failed: {error_str}"


# ============================================================================
# RUN DIARIZATION
# ============================================================================

def run_diarization(
        audio_path: str,
        hf_token: str,
        num_speakers: Optional[int] = None,
        min_speakers: int = 1,
        max_speakers: int = 5,
        progress_callback: Optional[Callable[[str], None]] = None,
) -> Tuple[bool, SpeakerTimeline]:
    """
    Run pyannote speaker diarization on an audio file.

    Args:
        audio_path:        Path to the audio file to diarise.
                           faster-whisper transcribed this same file.
        hf_token:          HuggingFace access token.
        num_speakers:      If the exact number of speakers is known, pass it
                           here for better accuracy. None = auto-detect.
        min_speakers:      Lower bound on speaker count (used if num_speakers
                           is None). Default 1.
        max_speakers:      Upper bound on speaker count (used if num_speakers
                           is None). Default 5.
        progress_callback: Optional function(str) for status updates.

    Returns:
        (success: bool, timeline: SpeakerTimeline)

        On failure, returns (False, []) and logs the error.
        The caller (transcript_cleaner.apply_diarization) handles the
        fallback to heuristic labels.

    Performance note:
        On CPU, expect roughly 1x real-time (60 min audio ≈ 60 min processing).
        progress_callback will be called periodically but pyannote does not
        expose fine-grained per-segment progress, so updates are coarse.
    """
    def _progress(msg: str):
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)

    # ── Pre-flight checks ────────────────────────────────────────────────────
    if not os.path.exists(audio_path):
        _progress(f"Audio file not found: {audio_path}")
        return False, []

    if not is_pyannote_installed():
        _progress("pyannote.audio is not installed.")
        return False, []

    if not hf_token:
        _progress("No HuggingFace token — cannot load model.")
        return False, []

    # ── Load pipeline ────────────────────────────────────────────────────────
    try:
        import torch
        from pyannote.audio import Pipeline

        _progress(f"Loading speaker detection model...")

        pipeline = Pipeline.from_pretrained(
            MODEL_ID,
            token=hf_token,
        )

        # Use GPU if available, otherwise CPU
        device_name = "cuda" if torch.cuda.is_available() else "cpu"
        pipeline.to(torch.device(device_name))

        if device_name == "cpu":
            _progress(
                "Running on CPU — this will take approximately as long as "
                "the recording itself. Please wait..."
            )
        else:
            _progress(f"Running on GPU ({device_name}) — this will be much faster.")

    except Exception as e:
        _progress(f"Failed to load diarization model: {e}")
        return False, []

    # ── Run diarization ──────────────────────────────────────────────────────
    try:
        _progress("Analysing audio for speaker changes...")

        # Build pipeline kwargs
        pipeline_kwargs = {}
        if num_speakers is not None:
            pipeline_kwargs["num_speakers"] = num_speakers
        else:
            pipeline_kwargs["min_speakers"] = min_speakers
            pipeline_kwargs["max_speakers"] = max_speakers

        # Attempt to use the progress hook if available
        try:
            from pyannote.audio.pipelines.utils.hook import ProgressHook

            with ProgressHook() as hook:
                diarization = pipeline(
                    audio_path,
                    hook=hook,
                    **pipeline_kwargs,
                )
        except ImportError:
            # Older pyannote version without ProgressHook
            diarization = pipeline(audio_path, **pipeline_kwargs)

        # ── Convert to our SpeakerTimeline format ────────────────────────────
        timeline: SpeakerTimeline = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            timeline.append((
                float(turn.start),
                float(turn.end),
                str(speaker).upper(),   # normalise to uppercase
            ))

        # Sort by start time (should already be sorted, but ensure it)
        timeline.sort(key=lambda x: x[0])

        n_speakers = len({spk for _, _, spk in timeline})
        n_segments = len(timeline)
        _progress(
            f"Speaker detection complete: "
            f"{n_speakers} speaker(s) found across {n_segments} segments."
        )

        return True, timeline

    except Exception as e:
        _progress(f"Speaker detection failed: {e}")
        logger.error(f"Diarization error: {e}", exc_info=True)
        return False, []


# ============================================================================
# TIMELINE QUERY
# ============================================================================

def speaker_at(
        timeline: SpeakerTimeline,
        time_seconds: float,
) -> Optional[str]:
    """
    Return the speaker ID active at time_seconds in the timeline.

    Uses the midpoint of the paragraph (start + end) / 2 to find the
    best matching speaker segment.  If no segment covers that exact
    midpoint, returns the speaker from the nearest segment instead.

    Returns None if the timeline is empty.
    """
    if not timeline:
        return None

    # First pass: exact coverage
    for start, end, speaker in timeline:
        if start <= time_seconds <= end:
            return speaker

    # Second pass: nearest segment by midpoint distance
    best_speaker = None
    best_dist    = float("inf")
    for start, end, speaker in timeline:
        mid  = (start + end) / 2.0
        dist = abs(mid - time_seconds)
        if dist < best_dist:
            best_dist    = dist
            best_speaker = speaker

    return best_speaker


def dominant_speaker(
        timeline: SpeakerTimeline,
        start_seconds: float,
        end_seconds: float,
) -> Optional[str]:
    """
    Return the speaker who spoke for the longest duration within
    the window [start_seconds, end_seconds].

    More accurate than speaker_at() for longer paragraphs that may
    span a speaker transition, but more expensive to compute.
    """
    if not timeline:
        return None

    duration_by_speaker: Dict[str, float] = {}

    for seg_start, seg_end, speaker in timeline:
        # Find overlap between [start_seconds, end_seconds] and this segment
        overlap_start = max(start_seconds, seg_start)
        overlap_end   = min(end_seconds,   seg_end)
        if overlap_end > overlap_start:
            duration = overlap_end - overlap_start
            duration_by_speaker[speaker] = (
                duration_by_speaker.get(speaker, 0.0) + duration
            )

    if not duration_by_speaker:
        return speaker_at(timeline, (start_seconds + end_seconds) / 2.0)

    return max(duration_by_speaker, key=duration_by_speaker.get)


def get_speaker_ids(timeline: SpeakerTimeline) -> List[str]:
    """Return a sorted list of unique speaker IDs found in the timeline."""
    return sorted({speaker for _, _, speaker in timeline})


# ============================================================================
# STANDALONE TEST
# ============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Test diarization_handler.py on an audio file."
    )
    parser.add_argument("audio",  help="Path to audio file (.mp3/.wav/.m4a)")
    parser.add_argument("--token", help="HuggingFace access token")
    parser.add_argument(
        "--num-speakers", type=int, default=None,
        help="Known number of speakers (omit for auto-detect)"
    )
    args = parser.parse_args()

    token = args.token or os.environ.get("HF_TOKEN", "")

    print(f"\nDiarization Handler — Test Run")
    print(f"{'='*50}")
    print(f"Audio file:    {args.audio}")
    print(f"Model:         {MODEL_ID}")
    print(f"Token present: {'Yes' if token else 'No'}")
    print()

    # Status check
    status = get_status(token)
    print("Status:")
    for k, v in status.items():
        print(f"  {k:<15} {v}")
    print()

    if not status["ready"]:
        print(f"Not ready: {status['message']}")
        print("\nIf model not downloaded, run with a valid token to trigger download.")
        sys.exit(1)

    def cb(msg):
        print(f"  {msg}")

    success, timeline = run_diarization(
        audio_path=args.audio,
        hf_token=token,
        num_speakers=args.num_speakers,
        progress_callback=cb,
    )

    if success:
        speakers = get_speaker_ids(timeline)
        print(f"\nFound {len(speakers)} speaker(s): {speakers}")
        print(f"Timeline has {len(timeline)} segments")
        print(f"\nFirst 10 segments:")
        for start, end, spk in timeline[:10]:
            print(f"  {start:7.2f}s - {end:7.2f}s  {spk}")
    else:
        print("Diarization failed — check log output above.")
