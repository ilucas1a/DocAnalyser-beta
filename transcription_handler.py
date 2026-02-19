"""
transcription_handler.py - Audio Recording and Transcription
Handles microphone recording and speech-to-text conversion.
Supports local transcription (faster-whisper) with cloud fallback (OpenAI Whisper API or AssemblyAI).
"""

import os
import sys
import tempfile
import threading
import queue
from pathlib import Path
from typing import Optional, Callable, Tuple, List

# -------------------------
# Dependency Checks
# -------------------------

# Recording dependencies
try:
    import sounddevice as sd
    import soundfile as sf
    RECORDING_AVAILABLE = True
    RECORDING_ERROR = None
except (ImportError, OSError) as e:
    RECORDING_AVAILABLE = False
    RECORDING_ERROR = str(e)

# Local transcription (faster-whisper)
try:
    from faster_whisper import WhisperModel
    LOCAL_WHISPER_AVAILABLE = True
    LOCAL_WHISPER_ERROR = None
except ImportError as e:
    LOCAL_WHISPER_AVAILABLE = False
    LOCAL_WHISPER_ERROR = str(e)

# Cloud transcription (OpenAI)
try:
    from openai import OpenAI
    CLOUD_WHISPER_AVAILABLE = True
    CLOUD_WHISPER_ERROR = None
except ImportError as e:
    CLOUD_WHISPER_AVAILABLE = False
    CLOUD_WHISPER_ERROR = str(e)

# Cloud transcription (AssemblyAI)
try:
    import assemblyai as aai
    ASSEMBLYAI_AVAILABLE = True
    ASSEMBLYAI_ERROR = None
except ImportError as e:
    ASSEMBLYAI_AVAILABLE = False
    ASSEMBLYAI_ERROR = str(e)


# -------------------------
# Configuration
# -------------------------

# Model sizes and their approximate download sizes
WHISPER_MODELS = {
    "tiny": {"size": "75 MB", "description": "Fastest, lowest accuracy"},
    "base": {"size": "150 MB", "description": "Good balance (recommended)"},
    "small": {"size": "500 MB", "description": "Better accuracy, slower"},
    "medium": {"size": "1.5 GB", "description": "High accuracy, much slower"},
    "large-v3": {"size": "3 GB", "description": "Best accuracy, very slow"},
}

DEFAULT_MODEL = "base"
DEFAULT_SAMPLE_RATE = 16000  # Whisper expects 16kHz
DEFAULT_CHANNELS = 1  # Mono

# Transcription modes
TRANSCRIPTION_MODES = {
    "local_first": "Try local first, fall back to cloud if needed",
    "cloud_direct": "Use cloud transcription (fastest, costs ~$0.006/min)",
    "local_only": "Local only (free, private, no internet needed)",
}


# -------------------------
# Model Management
# -------------------------

def get_models_directory() -> Path:
    """Get the directory where Whisper models are stored."""
    # Use app directory for models
    if getattr(sys, 'frozen', False):
        base_dir = Path(sys.executable).parent
    else:
        base_dir = Path(__file__).parent
    
    models_dir = base_dir / "whisper_models"
    models_dir.mkdir(exist_ok=True)
    return models_dir


def is_model_downloaded(model_name: str) -> bool:
    """Check if a model has been downloaded."""
    models_dir = get_models_directory()
    # faster-whisper downloads to a subdirectory with the model name
    model_path = models_dir / f"models--Systran--faster-whisper-{model_name}"
    return model_path.exists()


def get_downloaded_models() -> List[str]:
    """Get list of downloaded models."""
    downloaded = []
    for model_name in WHISPER_MODELS.keys():
        if is_model_downloaded(model_name):
            downloaded.append(model_name)
    return downloaded


def download_model(model_name: str, progress_callback: Callable[[str], None] = None) -> Tuple[bool, str]:
    """
    Download a Whisper model.
    
    Args:
        model_name: Name of model to download
        progress_callback: Optional callback for progress updates
        
    Returns:
        Tuple of (success, message)
    """
    if not LOCAL_WHISPER_AVAILABLE:
        return False, f"faster-whisper not installed: {LOCAL_WHISPER_ERROR}"
    
    if model_name not in WHISPER_MODELS:
        return False, f"Unknown model: {model_name}"
    
    def log(msg):
        if progress_callback:
            progress_callback(msg)
        print(msg)
    
    try:
        log(f"📥 Downloading Whisper model '{model_name}' ({WHISPER_MODELS[model_name]['size']})...")
        log("   This is a one-time download.")
        
        models_dir = get_models_directory()
        
        # Loading the model triggers download if not present
        # Use CPU for download to avoid CUDA issues
        model = WhisperModel(
            model_name,
            device="cpu",
            compute_type="int8",
            download_root=str(models_dir)
        )
        
        log(f"✅ Model '{model_name}' downloaded successfully!")
        return True, f"Model '{model_name}' ready"
        
    except Exception as e:
        log(f"❌ Download failed: {str(e)}")
        return False, str(e)


# -------------------------
# Audio Recording
# -------------------------

class AudioRecorder:
    """
    Simple audio recorder using sounddevice.
    Records to a temporary WAV file.
    """
    
    def __init__(self, sample_rate: int = DEFAULT_SAMPLE_RATE, channels: int = DEFAULT_CHANNELS):
        self.sample_rate = sample_rate
        self.channels = channels
        self.recording = False
        self.audio_data = []
        self.stream = None
        self._lock = threading.Lock()
    
    def _audio_callback(self, indata, frames, time, status):
        """Callback for sounddevice stream."""
        if status:
            print(f"Audio status: {status}")
        if self.recording:
            self.audio_data.append(indata.copy())
    
    def start_recording(self) -> Tuple[bool, str]:
        """Start recording audio from the microphone."""
        if not RECORDING_AVAILABLE:
            return False, f"Recording not available: {RECORDING_ERROR}"
        
        if self.recording:
            return False, "Already recording"
        
        try:
            self.audio_data = []
            self.recording = True
            
            self.stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                callback=self._audio_callback,
                dtype='float32'
            )
            self.stream.start()
            
            return True, "Recording started"
            
        except Exception as e:
            self.recording = False
            return False, f"Failed to start recording: {str(e)}"
    
    def stop_recording(self) -> Tuple[bool, str, Optional[str]]:
        """
        Stop recording and save to a temporary file.
        
        Returns:
            Tuple of (success, message, file_path or None)
        """
        if not self.recording:
            return False, "Not recording", None
        
        try:
            self.recording = False
            
            if self.stream:
                self.stream.stop()
                self.stream.close()
                self.stream = None
            
            if not self.audio_data:
                return False, "No audio recorded", None
            
            # Concatenate all audio chunks
            import numpy as np
            audio = np.concatenate(self.audio_data, axis=0)
            
            # Save to temporary WAV file
            temp_file = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
            temp_path = temp_file.name
            temp_file.close()
            
            sf.write(temp_path, audio, self.sample_rate)
            
            # Calculate duration
            duration = len(audio) / self.sample_rate
            
            return True, f"Recorded {duration:.1f} seconds", temp_path
            
        except Exception as e:
            return False, f"Failed to save recording: {str(e)}", None
    
    def is_recording(self) -> bool:
        """Check if currently recording."""
        return self.recording
    
    def get_duration(self) -> float:
        """Get current recording duration in seconds."""
        if not self.audio_data:
            return 0.0
        import numpy as np
        total_samples = sum(chunk.shape[0] for chunk in self.audio_data)
        return total_samples / self.sample_rate


def check_microphone_available() -> Tuple[bool, str]:
    """Check if a microphone is available."""
    if not RECORDING_AVAILABLE:
        return False, f"Recording libraries not installed.\n\nInstall with: pip install sounddevice soundfile"
    
    try:
        devices = sd.query_devices()
        input_devices = [d for d in devices if d['max_input_channels'] > 0]
        
        if not input_devices:
            return False, "No microphone found"
        
        # Get default input device
        default_input = sd.query_devices(kind='input')
        return True, f"Microphone: {default_input['name']}"
        
    except Exception as e:
        return False, f"Error checking microphone: {str(e)}"


def get_input_devices() -> List[dict]:
    """Get list of available input devices."""
    if not RECORDING_AVAILABLE:
        return []
    
    try:
        devices = sd.query_devices()
        input_devices = []
        for i, d in enumerate(devices):
            if d['max_input_channels'] > 0:
                input_devices.append({
                    'index': i,
                    'name': d['name'],
                    'channels': d['max_input_channels'],
                    'sample_rate': d['default_samplerate']
                })
        return input_devices
    except:
        return []


# -------------------------
# Local Transcription
# -------------------------

# Cache for loaded model (avoid reloading)
_cached_model = None
_cached_model_name = None


def _get_whisper_model(model_name: str, device: str = "auto") -> WhisperModel:
    """Get or load a Whisper model (cached)."""
    global _cached_model, _cached_model_name
    
    if _cached_model is not None and _cached_model_name == model_name:
        return _cached_model
    
    models_dir = get_models_directory()
    
    # Determine device
    if device == "auto":
        try:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            device = "cpu"
    
    # Compute type based on device
    compute_type = "float16" if device == "cuda" else "int8"
    
    _cached_model = WhisperModel(
        model_name,
        device=device,
        compute_type=compute_type,
        download_root=str(models_dir)
    )
    _cached_model_name = model_name
    
    return _cached_model


def transcribe_local(
    audio_path: str,
    model_name: str = DEFAULT_MODEL,
    device: str = "auto",
    language: str = None,
    progress_callback: Callable[[str], None] = None
) -> Tuple[bool, str, dict]:
    """
    Transcribe audio using local faster-whisper.
    
    Args:
        audio_path: Path to audio file
        model_name: Whisper model name
        device: "auto", "cpu", or "cuda"
        language: Language code (None for auto-detect)
        progress_callback: Progress callback function
        
    Returns:
        Tuple of (success, text_or_error, metadata)
    """
    if not LOCAL_WHISPER_AVAILABLE:
        return False, f"Local transcription not available: {LOCAL_WHISPER_ERROR}", {}
    
    def log(msg):
        if progress_callback:
            progress_callback(msg)
        print(msg)
    
    try:
        log(f"🔒 Transcribing locally with '{model_name}' model...")
        log("   Audio stays on your computer.")
        
        # Check if model is downloaded
        if not is_model_downloaded(model_name):
            log(f"📥 Model '{model_name}' not found. Downloading...")
            success, msg = download_model(model_name, progress_callback)
            if not success:
                return False, f"Failed to download model: {msg}", {}
        
        # Load model
        model = _get_whisper_model(model_name, device)
        
        # Transcribe
        log("🎯 Processing audio...")
        segments, info = model.transcribe(
            audio_path,
            language=language,
            beam_size=5,
            vad_filter=True,  # Filter out silence
            vad_parameters=dict(min_silence_duration_ms=500)
        )
        
        # Collect all segments
        text_parts = []
        for segment in segments:
            text_parts.append(segment.text.strip())
        
        full_text = " ".join(text_parts)
        
        # Clean up extra whitespace
        full_text = " ".join(full_text.split())
        
        metadata = {
            "language": info.language,
            "language_probability": info.language_probability,
            "duration": info.duration,
            "method": "local",
            "model": model_name
        }
        
        log(f"✅ Transcription complete ({info.duration:.1f}s audio, detected: {info.language})")
        
        return True, full_text, metadata
        
    except Exception as e:
        log(f"❌ Local transcription failed: {str(e)}")
        return False, str(e), {}


# -------------------------
# Cloud Transcription (OpenAI)
# -------------------------

def transcribe_cloud(
    audio_path: str,
    api_key: str,
    language: str = None,
    progress_callback: Callable[[str], None] = None
) -> Tuple[bool, str, dict]:
    """
    Transcribe audio using OpenAI Whisper API.
    
    Args:
        audio_path: Path to audio file
        api_key: OpenAI API key
        language: Language code (None for auto-detect)
        progress_callback: Progress callback function
        
    Returns:
        Tuple of (success, text_or_error, metadata)
    """
    if not CLOUD_WHISPER_AVAILABLE:
        return False, f"Cloud transcription not available: {CLOUD_WHISPER_ERROR}", {}
    
    if not api_key:
        return False, "OpenAI API key required for cloud transcription", {}
    
    def log(msg):
        if progress_callback:
            progress_callback(msg)
        print(msg)
    
    try:
        # Get file size for cost estimate
        file_size = os.path.getsize(audio_path)
        
        log(f"☁️ Transcribing via OpenAI Whisper API...")
        log(f"   Audio will be sent to OpenAI servers.")
        
        client = OpenAI(api_key=api_key)
        
        with open(audio_path, "rb") as audio_file:
            kwargs = {"model": "whisper-1", "file": audio_file}
            if language:
                kwargs["language"] = language
            
            response = client.audio.transcriptions.create(**kwargs)
        
        text = response.text.strip()
        
        # Estimate cost (roughly based on duration, assuming ~1MB per minute for WAV)
        estimated_minutes = max(0.1, file_size / (1024 * 1024))  # Very rough estimate
        estimated_cost = estimated_minutes * 0.006
        
        metadata = {
            "method": "cloud",
            "model": "whisper-1",
            "estimated_cost": estimated_cost
        }
        
        log(f"✅ Transcription complete (estimated cost: ${estimated_cost:.3f})")
        
        return True, text, metadata
        
    except Exception as e:
        error_msg = str(e)
        log(f"❌ Cloud transcription failed: {error_msg}")
        return False, error_msg, {}


def transcribe_assemblyai(
    audio_path: str,
    api_key: str,
    language: str = None,
    speaker_labels: bool = False,
    progress_callback: Callable[[str], None] = None
) -> Tuple[bool, str, dict]:
    """
    Transcribe audio using AssemblyAI API.
    
    Args:
        audio_path: Path to audio file
        api_key: AssemblyAI API key
        language: Language code (None for auto-detect)
        speaker_labels: Enable speaker diarization
        progress_callback: Progress callback function
        
    Returns:
        Tuple of (success, text_or_error, metadata)
    """
    if not ASSEMBLYAI_AVAILABLE:
        return False, f"AssemblyAI not available: {ASSEMBLYAI_ERROR}\n\nInstall with: pip install assemblyai", {}
    
    if not api_key:
        return False, "AssemblyAI API key required for cloud transcription", {}
    
    def log(msg):
        if progress_callback:
            progress_callback(msg)
        print(msg)
    
    try:
        # Get file size for info
        file_size = os.path.getsize(audio_path)
        file_size_mb = file_size / (1024 * 1024)
        
        log(f"☁️ Transcribing via AssemblyAI...")
        log(f"   File size: {file_size_mb:.1f} MB")
        log(f"   Audio will be sent to AssemblyAI servers.")
        
        # Configure AssemblyAI
        aai.settings.api_key = api_key
        
        # Create transcription config
        config_kwargs = {}
        if language:
            config_kwargs["language_code"] = language
        if speaker_labels:
            config_kwargs["speaker_labels"] = True
            log("   Speaker diarization enabled.")
        
        config = aai.TranscriptionConfig(**config_kwargs) if config_kwargs else None
        
        # Create transcriber and transcribe
        transcriber = aai.Transcriber()
        
        log("   Uploading and processing...")
        transcript = transcriber.transcribe(audio_path, config=config)
        
        if transcript.status == aai.TranscriptStatus.error:
            return False, f"AssemblyAI error: {transcript.error}", {}
        
        # Format output
        if speaker_labels and transcript.utterances:
            # Format with speaker labels
            lines = []
            for utterance in transcript.utterances:
                lines.append(f"Speaker {utterance.speaker}: {utterance.text}")
            text = "\n\n".join(lines)
        else:
            text = transcript.text
        
        # Calculate approximate cost (~$0.00025 per second)
        duration_seconds = (transcript.audio_duration or 0)
        estimated_cost = duration_seconds * 0.00025
        
        metadata = {
            "method": "assemblyai",
            "duration": duration_seconds,
            "estimated_cost": estimated_cost,
            "speaker_labels": speaker_labels
        }
        
        log(f"✅ Transcription complete!")
        log(f"   Duration: {duration_seconds:.1f}s, Est. cost: ${estimated_cost:.4f}")
        
        return True, text, metadata
        
    except Exception as e:
        error_msg = str(e)
        log(f"❌ AssemblyAI transcription failed: {error_msg}")
        return False, error_msg, {}


# -------------------------
# Smart Transcription (with Fallback)
# -------------------------

def transcribe_audio(
    audio_path: str,
    mode: str = "local_first",
    model_name: str = DEFAULT_MODEL,
    device: str = "auto",
    language: str = None,
    openai_api_key: str = None,
    assemblyai_api_key: str = None,
    cloud_provider: str = "openai",
    speaker_labels: bool = False,
    progress_callback: Callable[[str], None] = None
) -> Tuple[bool, str, dict]:
    """
    Smart transcription with automatic fallback.
    
    Modes:
        - "local_first": Try local, fall back to cloud if needed
        - "cloud_direct": Use cloud directly
        - "local_only": Use local only, no fallback
    
    Args:
        audio_path: Path to audio file
        mode: Transcription mode
        model_name: Local Whisper model name
        device: Device for local model
        language: Language code (None for auto-detect)
        openai_api_key: API key for OpenAI cloud fallback
        assemblyai_api_key: API key for AssemblyAI cloud fallback
        cloud_provider: Which cloud provider to use ("openai" or "assemblyai")
        speaker_labels: Enable speaker diarization (AssemblyAI only)
        progress_callback: Progress callback function
        
    Returns:
        Tuple of (success, text_or_error, metadata)
    """
    def log(msg):
        if progress_callback:
            progress_callback(msg)
        print(msg)
    
    def do_cloud_transcription():
        """Helper to perform cloud transcription with chosen provider."""
        if cloud_provider == "assemblyai":
            if not assemblyai_api_key:
                return False, "AssemblyAI API key required.\n\nGo to Settings → Audio Settings to add your API key.", {}
            return transcribe_assemblyai(audio_path, assemblyai_api_key, language, speaker_labels, progress_callback)
        else:  # openai (default)
            if not openai_api_key:
                return False, "OpenAI API key required.\n\nGo to Settings → API Keys to add your OpenAI key.", {}
            return transcribe_cloud(audio_path, openai_api_key, language, progress_callback)
    
    def has_cloud_key():
        """Check if the user has the required API key for their chosen cloud provider."""
        if cloud_provider == "assemblyai":
            return bool(assemblyai_api_key)
        return bool(openai_api_key)
    
    def get_cloud_provider_name():
        """Get human-readable name of the chosen cloud provider."""
        return "AssemblyAI" if cloud_provider == "assemblyai" else "OpenAI Whisper"
    
    # Cloud direct mode
    if mode == "cloud_direct":
        return do_cloud_transcription()
    
    # Local only mode
    if mode == "local_only":
        if not LOCAL_WHISPER_AVAILABLE:
            return False, (
                "Local transcription not available.\n\n"
                "Install with: pip install faster-whisper\n\n"
                "Or switch to cloud mode in Settings."
            ), {}
        return transcribe_local(audio_path, model_name, device, language, progress_callback)
    
    # Local first mode (with fallback)
    if mode == "local_first":
        # Try local first
        if LOCAL_WHISPER_AVAILABLE:
            success, text, metadata = transcribe_local(
                audio_path, model_name, device, language, progress_callback
            )
            
            if success and text.strip():
                return True, text, metadata
            else:
                log(f"\n⚠️ Local transcription failed or empty: {text[:100] if not success else 'No text'}")
        else:
            log(f"\n⚠️ Local transcription not available: {LOCAL_WHISPER_ERROR}")
        
        # Fall back to cloud
        if has_cloud_key():
            log("\n" + "="*50)
            log(f"💡 Falling back to {get_cloud_provider_name()}...")
            log("="*50)
            
            return do_cloud_transcription()
        else:
            provider_name = get_cloud_provider_name()
            log(f"\n⚠️ No {provider_name} API key configured for cloud fallback")
            _show_cloud_suggestion(log, cloud_provider)
            return False, f"Local transcription failed and no cloud fallback available.\n\nTo enable cloud fallback, add your {provider_name} API key in Settings.", {}
    
    return False, f"Unknown transcription mode: {mode}", {}


def _show_cloud_suggestion(log_func, cloud_provider: str = "openai"):
    """Show helpful message about using cloud transcription."""
    log_func("")
    log_func("═" * 55)
    log_func("💡 TIP: Cloud transcription is fast and accurate")
    log_func("═" * 55)
    log_func("")
    if cloud_provider == "assemblyai":
        log_func("AssemblyAI costs ~$0.015 per minute of audio.")
        log_func("It also supports speaker diarization (who said what).")
        log_func("")
        log_func("To enable cloud fallback:")
        log_func("  1. Go to Settings → Audio Settings")
        log_func("  2. Add your AssemblyAI API key")
        log_func("  3. Get a key at: https://www.assemblyai.com/dashboard/signup")
    else:
        log_func("OpenAI's Whisper API costs ~$0.006 per minute of audio.")
        log_func("")
        log_func("To enable cloud fallback:")
        log_func("  1. Go to Settings → API Keys")
        log_func("  2. Add your OpenAI API key")
        log_func("  3. Get a key at: https://platform.openai.com/api-keys")
    log_func("")


# -------------------------
# Utility Functions
# -------------------------

def get_audio_duration(audio_path: str) -> float:
    """Get duration of an audio file in seconds."""
    try:
        import soundfile as sf
        info = sf.info(audio_path)
        return info.duration
    except:
        return 0.0


def check_transcription_availability() -> dict:
    """
    Check what transcription options are available.
    
    Returns:
        Dict with availability status for each method
    """
    return {
        "recording": {
            "available": RECORDING_AVAILABLE,
            "error": RECORDING_ERROR
        },
        "local": {
            "available": LOCAL_WHISPER_AVAILABLE,
            "error": LOCAL_WHISPER_ERROR,
            "models_downloaded": get_downloaded_models() if LOCAL_WHISPER_AVAILABLE else []
        },
        "cloud": {
            "available": CLOUD_WHISPER_AVAILABLE,
            "error": CLOUD_WHISPER_ERROR
        }
    }


def get_transcription_install_info() -> str:
    """Get installation instructions for transcription dependencies."""
    instructions = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  🎤 Transcription Setup
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

RECORDING (Required):
  pip install sounddevice soundfile

LOCAL TRANSCRIPTION (Recommended):
  pip install faster-whisper

  First use will download a model (~150MB for 'base').
  Models are stored locally and work offline.

CLOUD TRANSCRIPTION (Optional):
  Requires OpenAI API key (configure in Settings).
  Uses OpenAI's Whisper API (~$0.006 per minute).

FFMPEG (Required for some audio formats):
  Windows: Download from https://ffmpeg.org/download.html
  Mac: brew install ffmpeg
  Linux: sudo apt install ffmpeg
"""
    return instructions
