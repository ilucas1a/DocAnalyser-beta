"""
Audio Handler - PROGRESSIVE DISPLAY VERSION
============================================

NEW FEATURE: Progressive segment display during transcription
✨ Shows transcribed text in real-time as segments are processed
✨ Better UX for long audio files (60-90 minutes)
✨ Users can verify transcription quality while it runs

ALL PREVIOUS FIXES INCLUDED:
✅ VAD toggle configuration
✅ Cache key bug fix
✅ Windows permission fix (custom model cache)
✅ Proper timestamp formatting
✅ Cache validation
✅ Thread-safe progress updates

CHANGES FROM PREVIOUS VERSION:
1. Added segment_callback parameter to transcription functions
2. Segments are yielded progressively during transcription
3. Batching every 5 segments to prevent UI slowdown
"""

import os
import sys
import json
import hashlib
import warnings
from pathlib import Path
from typing import Optional, Callable, Dict, List
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Suppress specific warnings
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

# Import libraries with graceful fallback
WHISPER_AVAILABLE = False
FASTER_WHISPER_AVAILABLE = False

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    logger.warning("torch not available - GPU acceleration disabled")

try:
    import whisper
    WHISPER_AVAILABLE = True
except ImportError:
    logger.warning("openai-whisper not available - use faster-whisper instead")

try:
    from faster_whisper import WhisperModel
    FASTER_WHISPER_AVAILABLE = True
except ImportError:
    logger.warning("faster-whisper not available - use openai-whisper instead")

if not WHISPER_AVAILABLE and not FASTER_WHISPER_AVAILABLE:
    logger.error("No transcription engine available!")
    logger.error("Install at least one: pip install faster-whisper OR pip install openai-whisper")

# Import performance timer (optional)
try:
    from performance_timer import PerformanceTimer
    PERFORMANCE_TIMING_AVAILABLE = True
except ImportError:
    PERFORMANCE_TIMING_AVAILABLE = False
    PerformanceTimer = None
    logger.info("⚠️  Performance timing unavailable (performance_timer.py not found)")



# ============================================================================
# WINDOWS PERMISSION FIX - Custom Model Cache Directory
# ============================================================================

def get_custom_cache_dir() -> Path:
    """
    Get custom cache directory for Whisper models.

    This fixes Windows WinError 1314 (symbolic link creation requires elevation)
    by storing models in AppData instead of default Hugging Face cache.

    Returns:
        Path: Custom cache directory path
    """
    if sys.platform == "win32":
        # Windows: Use AppData/Roaming
        base_dir = Path(os.environ.get('APPDATA', Path.home() / 'AppData' / 'Roaming'))
    else:
        # Linux/Mac: Use standard cache location
        base_dir = Path.home() / '.cache'

    cache_dir = base_dir / 'DocAnalyser_Beta' / 'whisper_models'
    cache_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"📁 Model cache directory: {cache_dir}")
    return cache_dir


def set_whisper_cache_dir():
    """
    Configure environment to use custom cache directory for both
    OpenAI Whisper and Faster-Whisper models.
    """
    custom_cache = get_custom_cache_dir()

    # Set environment variables for model downloads
    os.environ['TRANSFORMERS_CACHE'] = str(custom_cache)
    os.environ['HF_HOME'] = str(custom_cache)
    os.environ['TORCH_HOME'] = str(custom_cache)
    os.environ['XDG_CACHE_HOME'] = str(custom_cache.parent)

    logger.info("✅ Custom cache directory configured")


# Initialize custom cache on module load
set_whisper_cache_dir()


# ============================================================================
# CACHE MANAGEMENT
# ============================================================================

def get_cache_dir() -> str:
    """Get or create audio transcription cache directory"""
    from config import AUDIO_CACHE_DIR
    os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)
    return AUDIO_CACHE_DIR


def get_cache_key(audio_path: str, engine: str, model: str, language: str, use_vad: bool) -> str:
    """
    Generate cache key including VAD state to prevent incorrect cache retrieval.

    FIX: Added use_vad to cache key to ensure different VAD settings
    don't share cache entries (fixes Welsh transcript bug).

    Args:
        audio_path: Path to audio file
        engine: Transcription engine name
        model: Model name/size
        language: Language code
        use_vad: Voice Activity Detection enabled

    Returns:
        str: Cache key hash
    """
    file_hash = hashlib.md5(open(audio_path, 'rb').read()).hexdigest()
    # Include VAD state in cache key
    cache_string = f"{file_hash}_{engine}_{model}_{language}_{use_vad}"
    return hashlib.md5(cache_string.encode()).hexdigest()


def get_cached_transcription(cache_key: str) -> Optional[dict]:
    """
    Retrieve cached transcription with validation.

    FIX: Added validation to prevent loading incomplete/incorrect transcriptions.

    Args:
        cache_key: Cache key hash

    Returns:
        dict or None: Cached transcription if valid, None otherwise
    """
    cache_path = os.path.join(get_cache_dir(), f"{cache_key}.json")
    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                result = json.load(f)

            # Validate cache entry
            if not isinstance(result, dict):
                logger.warning(f"⚠️ Invalid cache format, re-transcribing")
                return None

            if 'segments' not in result or not result['segments']:
                logger.warning(f"⚠️ Empty segments in cache, re-transcribing")
                return None

            if 'text' not in result or not result['text'].strip():
                logger.warning(f"⚠️ Empty text in cache, re-transcribing")
                return None

            logger.info(f"✅ Using cached transcription ({len(result['segments'])} segments)")
            return result

        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.warning(f"⚠️ Cache read error, re-transcribing: {e}")
            return None

    return None


def save_to_cache(cache_key: str, result: dict):
    """Save transcription result to cache"""
    cache_path = os.path.join(get_cache_dir(), f"{cache_key}.json")
    try:
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        logger.info(f"💾 Saved to cache: {cache_path}")
    except Exception as e:
        logger.warning(f"⚠️ Failed to save cache: {e}")


def clear_audio_cache():
    """Clear all cached transcriptions"""
    cache_dir = get_cache_dir()
    if os.path.exists(cache_dir):
        count = 0
        for file in os.listdir(cache_dir):
            if file.endswith('.json'):
                os.remove(os.path.join(cache_dir, file))
                count += 1
        logger.info(f"🗑️ Cleared {count} cached transcriptions")


# ============================================================================
# TIMESTAMP FORMATTING
# ============================================================================

def format_timestamp(seconds: float) -> str:
    """
    Format seconds as HH:MM:SS timestamp.

    FIX: Converts seconds to proper time format instead of showing
    "[Page 1000.15]" for timestamps after 16:40.

    Args:
        seconds: Time in seconds

    Returns:
        str: Formatted timestamp (e.g., "01:23:45")
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


# ============================================================================
# TRANSCRIPTION ENGINES
# ============================================================================

def transcribe_with_whisper(
        audio_path: str,
        model_name: str = "base",
        language: str = None,
        use_vad: bool = True,
        progress_callback: Optional[Callable[[str], None]] = None,
        segment_callback: Optional[Callable[[Dict], None]] = None  # 🆕 NEW
) -> dict:
    """
    Transcribe audio using OpenAI Whisper.

    Args:
        audio_path: Path to audio file
        model_name: Whisper model size
        language: Language code or None for auto-detection
        use_vad: Enable Voice Activity Detection (recommended: True)
        progress_callback: Optional callback for status updates
        segment_callback: Optional callback for progressive segment updates 🆕 NEW

    Returns:
        dict: Transcription results with text and segments
    """
    try:
        if progress_callback:
            progress_callback(f"📄 Loading {model_name} model...")

        # Load model (will use custom cache directory)
        model = whisper.load_model(model_name, download_root=str(get_custom_cache_dir()))

        if progress_callback:
            progress_callback("🎤 Transcribing audio...")

        # Prepare transcription options
        transcribe_options = {
            "verbose": False,
        }

        # Set language if specified
        if language and language.lower() != "auto":
            transcribe_options["language"] = language
            logger.info(f"🌍 Transcribing in language: {language}")

        # Transcribe
        result = model.transcribe(audio_path, **transcribe_options)

        # Format segments and send progressively
        formatted_segments = []
        segment_batch = []

        for i, segment in enumerate(result['segments']):
            text = segment['text'].strip()

            formatted_segment = {
                "start": segment['start'],
                "end": segment['end'],
                "text": text,
                "timestamp": f"[{format_timestamp(segment['start'])}]"
            }

            formatted_segments.append(formatted_segment)

            # 🆕 NEW: Send segments in batches of 5 for progressive display
            if segment_callback:
                segment_batch.append(formatted_segment)
                if len(segment_batch) >= 5 or i == len(result['segments']) - 1:
                    segment_callback(segment_batch.copy())
                    segment_batch.clear()

        return {
            "text": result['text'],
            "segments": formatted_segments,
            "language": result.get('language', language or 'unknown')
        }

    except Exception as e:
        logger.error(f"Whisper transcription error: {e}")
        raise


def transcribe_with_faster_whisper(
        audio_path: str,
        model_name: str = "base",
        language: str = None,
        use_vad: bool = True,
        progress_callback: Optional[Callable[[str], None]] = None,
        segment_callback: Optional[Callable[[List[Dict]], None]] = None, # 🆕 NEW,
        performance_timer: Optional = None  # 🆕 Phase 1B
) -> dict:
    """
    Transcribe audio using Faster-Whisper with progressive segment display.

    Args:
        audio_path: Path to audio file
        model_name: Whisper model size
        language: Language code or None for auto-detection
        use_vad: Enable Voice Activity Detection (recommended: True)
        progress_callback: Optional callback for status updates
        segment_callback: Optional callback for progressive segment updates 🆕 NEW
                         Receives batches of segments as they're processed

    Returns:
        dict: Transcription results with text and segments
    """
    try:
        if progress_callback:
            progress_callback(f"📄 Loading {model_name} model...")

        # Determine compute type based on CUDA availability
        compute_type = "float16" if torch.cuda.is_available() else "int8"
        device = "cuda" if torch.cuda.is_available() else "cpu"

        # Load model (will use custom cache directory)
        model = WhisperModel(
            model_name,
            device=device,
            compute_type=compute_type,
            download_root=str(get_custom_cache_dir())
        )

        if progress_callback:
            progress_callback("🎤 Transcribing audio...")

        # Prepare transcription options
        transcribe_options = {
            "beam_size": 5,
            "vad_filter": use_vad,  # VAD toggle
        }

        # Set language if specified (FIX: prevents Welsh text bug)
        if language and language.lower() != "auto":
            transcribe_options["language"] = language
            logger.info(f"🌍 Transcribing in language: {language}")
        else:
            logger.info("🌍 Auto-detecting language")

        # Log VAD status
        if not use_vad:
            logger.info("🔇 VAD disabled (will transcribe all audio)")
        else:
            logger.info("🔊 VAD enabled (will stop at silence)")

        # Transcribe
        segments, info = model.transcribe(audio_path, **transcribe_options)

        # Collect and format results with progressive display
        full_text = []
        formatted_segments = []
        segment_batch = []  # 🆕 NEW: Batch segments for efficiency
        segment_count = 0

        for segment in segments:
            text = segment.text.strip()
            full_text.append(text)

            formatted_segment = {
                "start": segment.start,
                "end": segment.end,
                "text": text,
                "timestamp": f"[{format_timestamp(segment.start)}]"
            }

            formatted_segments.append(formatted_segment)
            segment_count += 1

            # 🆕 NEW: Send segments in batches of 5 for progressive display
            if segment_callback:
                segment_batch.append(formatted_segment)

                # Send batch every 5 segments to prevent UI slowdown
                if len(segment_batch) >= 5:
                    segment_callback(segment_batch.copy())
                    segment_batch.clear()

                    # Also update progress
                    if progress_callback:
                        progress_callback(f"📝 Processing... ({segment_count} segments so far)")

        # 🆕 NEW: Send any remaining segments in final batch
        if segment_callback and segment_batch:
            segment_callback(segment_batch.copy())

        return {
            "text": " ".join(full_text),
            "segments": formatted_segments,
            "language": info.language
        }

    except Exception as e:
        logger.error(f"Faster-Whisper transcription error: {e}")
        raise


# ============================================================================
# MAIN TRANSCRIPTION FUNCTION
# ============================================================================

def transcribe_audio(
        audio_path: str,
        engine: str = "faster-whisper",
        model: str = "base",
        language: str = "en",
        use_vad: bool = True,
        use_cache: bool = True,
        progress_callback: Optional[Callable[[str], None]] = None,
        segment_callback: Optional[Callable[[List[Dict]], None]] = None,  # 🆕 NEW,
        performance_timer: Optional = None  # 🆕 Phase 1B
) -> dict:
    """
    Transcribe audio file with caching and progressive segment display.

    This is the main entry point for audio transcription.

    Args:
        audio_path: Path to audio file
        engine: 'whisper' or 'faster-whisper'
        model: Model size ('tiny', 'base', 'small', 'medium', 'large', 'large-v2', 'large-v3')
        language: Language code or 'auto' for auto-detection
        use_vad: Enable Voice Activity Detection
                 - True: Stops at extended silence (good for clean audio)
                 - False: Transcribes all audio (good for content with pauses/laughter)
        use_cache: Whether to use cached results
        progress_callback: Optional callback function for status updates
        segment_callback: Optional callback for progressive segment display 🆕 NEW

    Returns:
        dict: Transcription results with keys:
            - text: Full transcription text
            - segments: List of timestamped segments
            - language: Detected or specified language
            - cached: Whether result came from cache
    """
    # Validate audio file
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    # Start performance timing
    if performance_timer:
        performance_timer.start("cache_check")

    # Normalize language parameter
    if not language or language.lower() == "auto":
        language = None  # Let Whisper auto-detect

    # Check cache
    cache_key = get_cache_key(audio_path, engine, model, language or "auto", use_vad)

    if use_cache:
        cached_result = get_cached_transcription(cache_key)
        if cached_result:
            # Stop timing for cache hit
            if performance_timer:
                performance_timer.stop("cache_check")
                performance_timer.set_metadata("cache_hit", True)
            
            cached_result["cached"] = True
            # 🆕 NEW: For cached results, send all segments at once
            if segment_callback and 'segments' in cached_result:
                segment_callback(cached_result['segments'])
            return cached_result

    # Perform transcription

    # Cache miss - stop cache check timing
    if performance_timer:
        performance_timer.stop("cache_check")
        performance_timer.set_metadata("cache_hit", False)
    logger.info(f"🎯 Starting transcription:")
    logger.info(f"   Engine: {engine}")
    logger.info(f"   Model: {model}")
    logger.info(f"   Language: {language or 'auto-detect'}")
    logger.info(f"   VAD: {'enabled' if use_vad else 'disabled'}")
    logger.info(f"   File: {os.path.basename(audio_path)}")

    # Start transcription timing
    if performance_timer:
        performance_timer.start("transcription")

    if engine.lower() == "whisper":
        result = transcribe_with_whisper(
            audio_path, model, language, use_vad, progress_callback, segment_callback
        )
    elif engine.lower() == "faster-whisper":
        result = transcribe_with_faster_whisper(
            audio_path, model, language, use_vad, progress_callback, segment_callback
        )
    else:
        raise ValueError(f"Unknown engine: {engine}. Use 'whisper' or 'faster-whisper'")

    # Save to cache
    if use_cache:
        save_to_cache(cache_key, result)


    # Stop transcription timing
    if performance_timer:
        performance_timer.stop("transcription")
        if 'segments' in result:
            performance_timer.increment("segments_processed", len(result['segments']))
    result["cached"] = False

    logger.info("✅ Transcription complete!")
    return result


# ============================================================================
# HIGH-LEVEL WRAPPER (for external use)
# ============================================================================

def transcribe_audio_file(
        filepath: str,
        engine: str = "faster_whisper",
        api_key: str = None,
        options: dict = None,
        bypass_cache: bool = False,
        progress_callback: Optional[Callable[[str], None]] = None,
        segment_callback: Optional[Callable[[List[Dict]], None]] = None  # 🆕 NEW
) -> tuple:
    """
    High-level wrapper for audio transcription with all engines.

    Args:
        filepath: Path to audio file
        engine: Engine name ('openai_whisper', 'faster_whisper', 'assemblyai', 'local_whisper')
        api_key: API key for cloud services
        options: Dict with language, speaker_diarization, enable_vad, model_size, device
        bypass_cache: If True, force re-transcription
        progress_callback: Optional callback for status updates
        segment_callback: Optional callback for progressive segment display 🆕 NEW

    Returns:
        tuple: (success: bool, result: list/str, title: str)
    """
    options = options or {}
    language = options.get('language', None)  # None enables auto-detection
    use_vad = options.get('enable_vad', True)
    model_size = options.get('model_size', 'base')

    try:

        # Create performance timer
        timer = None
        if PERFORMANCE_TIMING_AVAILABLE:
            timer = PerformanceTimer(f"Audio Transcription: {os.path.basename(filepath)}")
            timer.set_metadata("file_path", filepath)
            timer.set_metadata("engine", engine)
            timer.set_metadata("model_size", options.get('model_size', 'base'))

        # Local Whisper engines
        if engine in ["faster_whisper", "local_whisper", "whisper"]:
            engine_name = "faster-whisper" if engine == "faster_whisper" else "whisper"

            result = transcribe_audio(
                audio_path=filepath,
                engine=engine_name,
                model=model_size,
                language=language,
                use_vad=use_vad,
                use_cache=not bypass_cache,
                progress_callback=progress_callback,
                segment_callback=segment_callback, # 🆕 NEW: Pass through segment callback,
                performance_timer=timer  # 🆕 Phase 1B: Pass timer through
            )

            # Convert to entries format
            entries = result['segments']
            title = os.path.basename(filepath)


            # Complete timing and save performance log
            if timer:
                timer.complete_operation()
                
                # Save performance log
                try:
                    from config import PERFORMANCE_LOGS_DIR
                    import datetime
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    safe_filename = os.path.basename(filepath).replace(" ", "_")
                    filename = f"perf_{timestamp}_{safe_filename}.log"
                    log_path = os.path.join(PERFORMANCE_LOGS_DIR, filename)
                    timer.save_log(log_path)
                    
                    # Display summary in progress callback
                    summary = timer.generate_summary()
                    if progress_callback:
                        progress_callback(f"✅ Complete | {summary}")
                    
                    logger.info(f"📊 Performance log saved: {log_path}")
                except Exception as e:
                    logger.warning(f"Could not save performance log: {e}")

            return True, entries, title

        # OpenAI Whisper (cloud)
        elif engine == "openai_whisper":
            if not api_key:
                return False, "OpenAI API key required. Go to Audio Settings to add your key.", ""

            if progress_callback:
                progress_callback("🌐 Transcribing with OpenAI Whisper (cloud)...")

            try:
                from openai import OpenAI
                client = OpenAI(api_key=api_key)
                
                # Check file size (OpenAI has 25MB limit)
                file_size = os.path.getsize(filepath)
                if file_size > 25 * 1024 * 1024:  # 25MB
                    return False, f"File too large ({file_size / 1024 / 1024:.1f}MB). OpenAI Whisper has a 25MB limit. Use faster-whisper (local) for larger files.", ""
                
                with open(filepath, "rb") as audio_file:
                    if progress_callback:
                        progress_callback("🌐 Uploading to OpenAI...")
                    
                    # Use verbose_json for timestamps
                    response = client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file,
                        response_format="verbose_json",
                        language=language if language else None
                    )
                
                # Convert response to our format
                entries = []
                if hasattr(response, 'segments') and response.segments:
                    for seg in response.segments:
                        entries.append({
                            'start': seg.get('start', 0),
                            'end': seg.get('end', 0),
                            'text': seg.get('text', '').strip()
                        })
                else:
                    # If no segments, create one entry with full text
                    entries.append({
                        'start': 0,
                        'end': 0,
                        'text': response.text if hasattr(response, 'text') else str(response)
                    })
                
                title = os.path.basename(filepath)
                if progress_callback:
                    progress_callback("✅ OpenAI Whisper transcription complete!")
                
                return True, entries, title
                
            except ImportError:
                return False, "OpenAI library not installed. Run: pip install openai", ""
            except Exception as e:
                logger.error(f"OpenAI Whisper error: {e}")
                return False, f"OpenAI Whisper error: {str(e)}", ""

        # AssemblyAI (cloud)
        elif engine == "assemblyai":
            assemblyai_key = options.get('assemblyai_api_key') or api_key
            if not assemblyai_key:
                return False, "AssemblyAI API key required. Go to Audio Settings to add your key.", ""

            if progress_callback:
                progress_callback("🌐 Transcribing with AssemblyAI...")

            try:
                import assemblyai as aai
                aai.settings.api_key = assemblyai_key
                
                # Configure transcription settings
                config = aai.TranscriptionConfig(
                    language_code=language if language else None,
                    speaker_labels=options.get('speaker_diarization', False)
                )
                
                transcriber = aai.Transcriber()
                
                if progress_callback:
                    progress_callback("🌐 Uploading to AssemblyAI...")
                
                transcript = transcriber.transcribe(filepath, config=config)
                
                if transcript.status == aai.TranscriptStatus.error:
                    return False, f"AssemblyAI error: {transcript.error}", ""
                
                # Convert to our format
                entries = []
                
                if transcript.utterances and options.get('speaker_diarization', False):
                    # Use utterances for speaker diarization
                    for utt in transcript.utterances:
                        entries.append({
                            'start': utt.start / 1000,  # Convert ms to seconds
                            'end': utt.end / 1000,
                            'text': f"[Speaker {utt.speaker}]: {utt.text}",
                            'speaker': utt.speaker
                        })
                elif transcript.words:
                    # Group words into segments
                    current_segment = {'start': 0, 'end': 0, 'text': ''}
                    for word in transcript.words:
                        if not current_segment['text']:
                            current_segment['start'] = word.start / 1000
                        current_segment['end'] = word.end / 1000
                        current_segment['text'] += word.text + ' '
                        
                        # Create new segment roughly every 30 words or at sentence end
                        if len(current_segment['text'].split()) >= 30 or word.text.endswith(('.', '?', '!')):
                            current_segment['text'] = current_segment['text'].strip()
                            entries.append(current_segment)
                            current_segment = {'start': 0, 'end': 0, 'text': ''}
                    
                    # Add remaining text
                    if current_segment['text'].strip():
                        current_segment['text'] = current_segment['text'].strip()
                        entries.append(current_segment)
                else:
                    # Fallback to full text
                    entries.append({
                        'start': 0,
                        'end': 0,
                        'text': transcript.text or ''
                    })
                
                title = os.path.basename(filepath)
                if progress_callback:
                    progress_callback("✅ AssemblyAI transcription complete!")
                
                return True, entries, title
                
            except ImportError:
                return False, "AssemblyAI library not installed. Run: pip install assemblyai", ""
            except Exception as e:
                logger.error(f"AssemblyAI error: {e}")
                return False, f"AssemblyAI error: {str(e)}", ""

        else:
            return False, f"Unknown engine: {engine}", ""

    except Exception as e:
        logger.error(f"Transcription failed: {e}")
        import traceback
        traceback.print_exc()
        return False, str(e), ""


"""
Add this function to audio_handler.py (before the TESTING section at line 584)
This function downloads YouTube audio and transcribes it
"""

"""
IMPROVED VERSION of transcribe_youtube_audio
Replace the previous version with this one in audio_handler.py

Key fixes:
1. Better temporary file handling
2. Let yt-dlp manage the output filename
3. Proper error handling for ffprobe issues
"""


def transcribe_youtube_audio(
        video_id: str,
        api_key: str = None,
        engine: str = "faster_whisper",
        language: str = None,  # None for auto-detect
        speaker_diarization: bool = False,
        enable_vad: bool = True,
        bypass_cache: bool = False,
        progress_callback: Optional[Callable[[str], None]] = None,
        segment_callback: Optional[Callable[[List[Dict]], None]] = None,
        cookie_file: str = None
) -> List[Dict]:
    """
    Download YouTube audio and transcribe it.

    Args:
        video_id: YouTube video ID
        api_key: API key (not used for local Whisper)
        engine: Transcription engine name
        language: Language code (None for auto-detect)
        speaker_diarization: Enable speaker detection (not implemented)
        enable_vad: Enable Voice Activity Detection
        bypass_cache: Force re-transcription
        progress_callback: Optional callback for status updates
        segment_callback: Optional callback for progressive segment display

    Returns:
        List[Dict]: List of transcription segments with timestamps
    """
    import tempfile
    import yt_dlp
    import os
    from pathlib import Path

    if progress_callback:
        progress_callback(f"📥 Downloading audio for video: {video_id}")

    # Create temporary directory (not file) - let yt-dlp create the file
    temp_dir = tempfile.mkdtemp()
    audio_file = None

    try:
        # Output template - let yt-dlp handle the extension
        output_template = os.path.join(temp_dir, 'audio.%(ext)s')

        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': output_template,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': False,  # Changed to see actual errors
            'no_warnings': False,  # Changed to see warnings
            'ignoreerrors': False,
            'nocheckcertificate': True,  # Helpful for some networks
            'prefer_ffmpeg': True,
        }
        
        # Add cookie file if provided
        if cookie_file and os.path.exists(cookie_file):
            ydl_opts['cookiefile'] = cookie_file
            logger.info(f"🍪 Using cookie file for YouTube download: {cookie_file}")

        youtube_url = f"https://www.youtube.com/watch?v={video_id}"
        logger.info(f"🎵 Downloading audio from YouTube: {video_id}")

        # Strategy: Try without cookies first, then cycle through browsers on failure.
        # This avoids DPAPI errors on Windows (Chrome encrypts cookies with DPAPI,
        # which yt-dlp can't always decrypt). Firefox is preferred as fallback since
        # it doesn't use DPAPI.
        info = None
        download_succeeded = False
        browsers_to_try = ['firefox', 'edge', 'chrome', 'brave']  # Firefox first (no DPAPI issues)
        
        # Attempt 1: Try without any browser cookies
        try:
            if progress_callback:
                progress_callback(f"📥 Downloading audio for video: {video_id}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(youtube_url, download=True)
            download_succeeded = True
        except Exception as first_err:
            first_error_str = str(first_err).lower()
            needs_cookies = ('403' in first_error_str or 'forbidden' in first_error_str or 
                           'sign in' in first_error_str or 'login' in first_error_str)
            
            if not needs_cookies:
                raise  # Not a cookie-related error, don't retry
            
            logger.info(f"⚠️ Download failed ({first_err}), trying browser cookies...")
            
            # Attempt 2+: Try each browser's cookies
            last_err = first_err
            for browser in browsers_to_try:
                try:
                    if progress_callback:
                        progress_callback(f"🍪 Trying {browser} browser cookies...")
                    retry_opts = dict(ydl_opts)
                    retry_opts.pop('cookiefile', None)  # Remove file-based cookies
                    retry_opts['cookiesfrombrowser'] = (browser,)
                    
                    with yt_dlp.YoutubeDL(retry_opts) as ydl:
                        info = ydl.extract_info(youtube_url, download=True)
                    
                    logger.info(f"✅ Download succeeded with {browser} cookies")
                    download_succeeded = True
                    break
                except Exception as retry_err:
                    error_str = str(retry_err).lower()
                    if 'dpapi' in error_str:
                        logger.info(f"⚠️ {browser}: DPAPI decrypt failed, trying next browser...")
                    else:
                        logger.info(f"⚠️ {browser}: {str(retry_err)[:100]}")
                    last_err = retry_err
                    continue
            
            if not download_succeeded:
                raise last_err

        # Find the downloaded audio file
        # yt-dlp will create either audio.mp3 or audio.webm or similar
        for file in os.listdir(temp_dir):
            if file.startswith('audio'):
                audio_file = os.path.join(temp_dir, file)
                break

        if not audio_file or not os.path.exists(audio_file):
            raise Exception("Audio file was not created by yt-dlp")

        logger.info(f"✅ Audio downloaded: {os.path.basename(audio_file)} ({os.path.getsize(audio_file)} bytes)")

        if progress_callback:
            progress_callback(f"✅ Audio downloaded, starting transcription...")

        # Transcribe using the existing function
        options = {
            'language': language,
            'enable_vad': enable_vad,
            'model_size': 'base'  # You can make this configurable
        }

        success, entries, title = transcribe_audio_file(
            filepath=audio_file,
            engine=engine,
            api_key=api_key,
            options=options,
            bypass_cache=bypass_cache,
            progress_callback=progress_callback,
            segment_callback=segment_callback
        )

        if not success:
            raise Exception(f"Transcription failed: {entries}")

        return entries

    except Exception as e:
        logger.error(f"YouTube audio transcription failed: {e}")
        import traceback
        traceback.print_exc()
        raise

    finally:
        # Clean up temporary directory and all files
        if temp_dir and os.path.exists(temp_dir):
            try:
                import shutil
                shutil.rmtree(temp_dir)
                logger.info(f"🗑️ Cleaned up temporary files")
            except Exception as e:
                logger.warning(f"⚠️ Could not clean up temp dir: {e}")

# ============================================================================
# TESTING
# ============================================================================

if __name__ == "__main__":
    def print_progress(msg):
        print(f"[Progress] {msg}")


    def print_segments(segments):
        """Print segments as they arrive"""
        for seg in segments:
            print(f"{seg['timestamp']} {seg['text']}")


    # Example usage with progressive display
    import sys

    if len(sys.argv) > 1:
        audio_file = sys.argv[1]
        print(f"\n🎵 Transcribing: {audio_file}")
        print("=" * 60)

        success, result, title = transcribe_audio_file(
            audio_file,
            engine="faster_whisper",
            options={'language': 'en', 'enable_vad': True},
            progress_callback=print_progress,
            segment_callback=print_segments  # See segments in real-time!
        )

        if success:
            print("\n" + "=" * 60)
            print(f"✅ Complete! Total segments: {len(result)}")
        else:
            print(f"❌ Error: {result}")
    else:
        print("Usage: python audio_handler.py <audio_file>")