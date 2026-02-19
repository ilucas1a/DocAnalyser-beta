"""
dependency_checker.py - External Dependency Detection
Checks for Tesseract, Poppler, FFmpeg, and optional Python packages
"""

import os
import sys
import subprocess
import shutil
from typing import Dict, Optional, Tuple, List
from dataclasses import dataclass


@dataclass
class DependencyStatus:
    """Status of a single dependency"""
    name: str
    installed: bool
    version: Optional[str] = None
    path: Optional[str] = None
    required_for: str = ""
    install_url: str = ""
    install_instructions: str = ""


# -------------------------
# Platform Detection
# -------------------------

def get_platform() -> str:
    """Get current platform: 'windows', 'mac', or 'linux'"""
    if sys.platform.startswith("win"):
        return "windows"
    elif sys.platform == "darwin":
        return "mac"
    else:
        return "linux"


def _get_app_dir() -> Optional[str]:
    """
    Get the application directory (where the exe or script is located).
    Used for finding bundled tools.
    """
    try:
        if getattr(sys, 'frozen', False):
            # Running as compiled exe
            return os.path.dirname(sys.executable)
        else:
            # Running as script
            return os.path.dirname(os.path.abspath(__file__))
    except:
        return None


def _get_bundled_tools_dir() -> Optional[str]:
    """
    Get the bundled_tools directory if it exists.
    Handles both development mode and PyInstaller bundled app.
    """
    app_dir = _get_app_dir()
    if app_dir:
        # PyInstaller 6.x puts data files in _internal folder
        if getattr(sys, 'frozen', False):
            # Running as bundled exe - check _internal/tools
            internal_tools = os.path.join(app_dir, '_internal', 'tools')
            if os.path.isdir(internal_tools):
                return internal_tools
            # Also check direct tools folder (older PyInstaller)
            tools_dir = os.path.join(app_dir, 'tools')
            if os.path.isdir(tools_dir):
                return tools_dir
        else:
            # Running as script - check development locations
            tools_dir = os.path.join(app_dir, 'tools')
            if os.path.isdir(tools_dir):
                return tools_dir
            # Also check installer/bundled_tools for development
            bundled_dir = os.path.join(app_dir, 'installer', 'bundled_tools')
            if os.path.isdir(bundled_dir):
                return bundled_dir
    return None


# -------------------------
# Tesseract OCR Detection
# -------------------------

def find_tesseract() -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Find Tesseract OCR installation.
    Checks bundled tools first, then system installation.
    Returns: (installed: bool, path: str or None, version: str or None)
    """
    platform = get_platform()
    tesseract_cmd = None
    
    # Check bundled tools first
    bundled_dir = _get_bundled_tools_dir()
    if bundled_dir and platform == "windows":
        bundled_tess = os.path.join(bundled_dir, 'tesseract', 'tesseract.exe')
        if os.path.exists(bundled_tess):
            tesseract_cmd = bundled_tess
    
    # Check common installation paths on Windows
    if not tesseract_cmd and platform == "windows":
        common_paths = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            r"C:\Tesseract-OCR\tesseract.exe",
            os.path.join(os.environ.get('LOCALAPPDATA', ''), r"Programs\Tesseract-OCR\tesseract.exe"),
        ]
        for path in common_paths:
            if os.path.exists(path):
                tesseract_cmd = path
                break
    
    # Check if tesseract is in PATH
    if not tesseract_cmd:
        tesseract_cmd = shutil.which("tesseract")
    
    if not tesseract_cmd:
        return False, None, None
    
    # Get version
    try:
        result = subprocess.run(
            [tesseract_cmd, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if platform == "windows" else 0
        )
        # Version is usually on first line: "tesseract 5.3.0"
        version_line = result.stdout.split('\n')[0] if result.stdout else ""
        version = version_line.replace("tesseract", "").strip()
        return True, tesseract_cmd, version
    except Exception:
        return True, tesseract_cmd, "unknown"


def get_tesseract_status() -> DependencyStatus:
    """Get full status for Tesseract"""
    installed, path, version = find_tesseract()
    platform = get_platform()
    
    if platform == "windows":
        install_url = "https://github.com/UB-Mannheim/tesseract/wiki"
        instructions = """1. Download the installer from the link above
2. Run the installer (tesseract-ocr-w64-setup-5.x.x.exe)
3. Use default installation options
4. Restart DocAnalyser"""
    elif platform == "mac":
        install_url = "https://formulae.brew.sh/formula/tesseract"
        instructions = """1. Open Terminal
2. Run: brew install tesseract
3. Restart DocAnalyser"""
    else:
        install_url = "https://tesseract-ocr.github.io/tessdoc/Installation.html"
        instructions = """Run: sudo apt-get install tesseract-ocr
Then restart DocAnalyser"""
    
    return DependencyStatus(
        name="Tesseract OCR",
        installed=installed,
        version=version,
        path=path,
        required_for="OCR (scanned PDFs and images)",
        install_url=install_url,
        install_instructions=instructions
    )


# -------------------------
# Poppler Detection
# -------------------------

def find_poppler() -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Find Poppler installation (provides pdftoppm, pdftocairo).
    Checks bundled tools first, then system installation.
    Returns: (installed: bool, path: str or None, version: str or None)
    """
    platform = get_platform()
    pdftoppm_cmd = None
    
    # Check bundled tools first
    bundled_dir = _get_bundled_tools_dir()
    if bundled_dir and platform == "windows":
        # Check both possible structures from different Poppler distributions
        bundled_paths = [
            os.path.join(bundled_dir, 'poppler', 'Library', 'bin', 'pdftoppm.exe'),
            os.path.join(bundled_dir, 'poppler', 'bin', 'pdftoppm.exe'),
        ]
        for path in bundled_paths:
            if os.path.exists(path):
                pdftoppm_cmd = path
                break
    
    # Look for pdftoppm in PATH
    if not pdftoppm_cmd:
        pdftoppm_cmd = shutil.which("pdftoppm")
    
    # On Windows, also check common paths
    if not pdftoppm_cmd and platform == "windows":
        common_paths = [
            r"C:\poppler\Library\bin\pdftoppm.exe",
            r"C:\Program Files\poppler\bin\pdftoppm.exe",
            r"C:\poppler\bin\pdftoppm.exe",
        ]
        for path in common_paths:
            if os.path.exists(path):
                pdftoppm_cmd = path
                break
    
    if not pdftoppm_cmd:
        return False, None, None
    
    # Get version
    try:
        result = subprocess.run(
            [pdftoppm_cmd, "-v"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if platform == "windows" else 0
        )
        # Version in stderr: "pdftoppm version 23.07.0"
        version_text = result.stderr if result.stderr else result.stdout
        version = version_text.strip().replace("pdftoppm version", "").strip()
        return True, os.path.dirname(pdftoppm_cmd), version
    except Exception:
        return True, os.path.dirname(pdftoppm_cmd), "unknown"


def get_poppler_status() -> DependencyStatus:
    """Get full status for Poppler"""
    installed, path, version = find_poppler()
    platform = get_platform()
    
    if platform == "windows":
        install_url = "https://github.com/oschwartz10612/poppler-windows/releases/"
        instructions = """1. Download the latest Release ZIP from the link
2. Extract to C:\\poppler
3. Add C:\\poppler\\Library\\bin to your PATH:
   - Open System Properties → Environment Variables
   - Edit 'Path' under System Variables
   - Add: C:\\poppler\\Library\\bin
4. Restart DocAnalyser"""
    elif platform == "mac":
        install_url = "https://formulae.brew.sh/formula/poppler"
        instructions = """1. Open Terminal
2. Run: brew install poppler
3. Restart DocAnalyser"""
    else:
        install_url = "https://poppler.freedesktop.org/"
        instructions = """Run: sudo apt-get install poppler-utils
Then restart DocAnalyser"""
    
    return DependencyStatus(
        name="Poppler",
        installed=installed,
        version=version,
        path=path,
        required_for="PDF to image conversion (for OCR)",
        install_url=install_url,
        install_instructions=instructions
    )


# -------------------------
# FFmpeg Detection
# -------------------------

def find_ffmpeg() -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Find FFmpeg installation.
    Checks bundled tools first, then system installation.
    Returns: (installed: bool, path: str or None, version: str or None)
    """
    platform = get_platform()
    ffmpeg_cmd = None
    
    # Check bundled tools first
    bundled_dir = _get_bundled_tools_dir()
    if bundled_dir and platform == "windows":
        bundled_ffmpeg = os.path.join(bundled_dir, 'ffmpeg', 'bin', 'ffmpeg.exe')
        if os.path.exists(bundled_ffmpeg):
            ffmpeg_cmd = bundled_ffmpeg
    
    # Check PATH
    if not ffmpeg_cmd:
        ffmpeg_cmd = shutil.which("ffmpeg")
    
    # On Windows, check common paths
    if not ffmpeg_cmd and platform == "windows":
        common_paths = [
            r"C:\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
            os.path.join(os.environ.get('LOCALAPPDATA', ''), r"Programs\ffmpeg\bin\ffmpeg.exe"),
        ]
        for path in common_paths:
            if os.path.exists(path):
                ffmpeg_cmd = path
                break
    
    if not ffmpeg_cmd:
        return False, None, None
    
    # Get version
    try:
        result = subprocess.run(
            [ffmpeg_cmd, "-version"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if platform == "windows" else 0
        )
        # First line: "ffmpeg version 6.0-full_build..."
        version_line = result.stdout.split('\n')[0] if result.stdout else ""
        parts = version_line.split()
        version = parts[2] if len(parts) > 2 else "unknown"
        return True, os.path.dirname(ffmpeg_cmd), version
    except Exception:
        return True, os.path.dirname(ffmpeg_cmd), "unknown"


def get_ffmpeg_status() -> DependencyStatus:
    """Get full status for FFmpeg"""
    installed, path, version = find_ffmpeg()
    platform = get_platform()
    
    if platform == "windows":
        install_url = "https://www.gyan.dev/ffmpeg/builds/"
        instructions = """1. Download 'ffmpeg-release-essentials.zip' from the link
2. Extract to C:\\ffmpeg
3. Add C:\\ffmpeg\\bin to your PATH:
   - Open System Properties → Environment Variables
   - Edit 'Path' under System Variables
   - Add: C:\\ffmpeg\\bin
4. Restart DocAnalyser"""
    elif platform == "mac":
        install_url = "https://formulae.brew.sh/formula/ffmpeg"
        instructions = """1. Open Terminal
2. Run: brew install ffmpeg
3. Restart DocAnalyser"""
    else:
        install_url = "https://ffmpeg.org/download.html"
        instructions = """Run: sudo apt-get install ffmpeg
Then restart DocAnalyser"""
    
    return DependencyStatus(
        name="FFmpeg",
        installed=installed,
        version=version,
        path=path,
        required_for="Audio/video transcription",
        install_url=install_url,
        install_instructions=instructions
    )


# -------------------------
# System Hardware Detection
# -------------------------

@dataclass
class SystemHardwareInfo:
    """System hardware information for model recommendations"""
    # RAM
    total_ram_gb: float = 0.0
    available_ram_gb: float = 0.0
    
    # GPU
    has_nvidia_gpu: bool = False
    gpu_name: Optional[str] = None
    gpu_vram_gb: float = 0.0
    
    # CPU
    cpu_name: Optional[str] = None
    cpu_cores: int = 0
    
    # Platform
    platform: str = ""


def _get_ram_info() -> Tuple[float, float]:
    """
    Get total and available RAM in GB.
    Returns: (total_gb, available_gb)
    """
    try:
        import psutil
        mem = psutil.virtual_memory()
        total_gb = mem.total / (1024 ** 3)
        available_gb = mem.available / (1024 ** 3)
        return total_gb, available_gb
    except ImportError:
        pass
    
    # Fallback for Windows without psutil
    platform = get_platform()
    if platform == "windows":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            c_ulonglong = ctypes.c_ulonglong
            
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ('dwLength', ctypes.c_ulong),
                    ('dwMemoryLoad', ctypes.c_ulong),
                    ('ullTotalPhys', c_ulonglong),
                    ('ullAvailPhys', c_ulonglong),
                    ('ullTotalPageFile', c_ulonglong),
                    ('ullAvailPageFile', c_ulonglong),
                    ('ullTotalVirtual', c_ulonglong),
                    ('ullAvailVirtual', c_ulonglong),
                    ('ullAvailExtendedVirtual', c_ulonglong),
                ]
            
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(stat)
            kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            
            total_gb = stat.ullTotalPhys / (1024 ** 3)
            available_gb = stat.ullAvailPhys / (1024 ** 3)
            return total_gb, available_gb
        except:
            pass
    
    return 0.0, 0.0


def _get_nvidia_gpu_info() -> Tuple[bool, Optional[str], float]:
    """
    Get NVIDIA GPU information.
    Returns: (has_nvidia, gpu_name, vram_gb)
    """
    platform = get_platform()
    
    # Try nvidia-smi
    try:
        nvidia_smi = shutil.which('nvidia-smi')
        if nvidia_smi:
            result = subprocess.run(
                [nvidia_smi, '--query-gpu=name,memory.total', '--format=csv,noheader,nounits'],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW if platform == "windows" else 0
            )
            if result.returncode == 0 and result.stdout.strip():
                lines = result.stdout.strip().split('\n')
                # Take first GPU
                parts = lines[0].split(',')
                if len(parts) >= 2:
                    gpu_name = parts[0].strip()
                    vram_mb = float(parts[1].strip())
                    vram_gb = vram_mb / 1024
                    return True, gpu_name, vram_gb
    except:
        pass
    
    return False, None, 0.0


def _get_cpu_info() -> Tuple[Optional[str], int]:
    """
    Get CPU information.
    Returns: (cpu_name, core_count)
    """
    import platform as plat
    
    cpu_name = plat.processor()
    
    # Get core count
    try:
        import os
        cores = os.cpu_count() or 0
    except:
        cores = 0
    
    # Try to get better CPU name on Windows
    if get_platform() == "windows" and (not cpu_name or cpu_name == ""):
        try:
            result = subprocess.run(
                ['wmic', 'cpu', 'get', 'name'],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                if len(lines) > 1:
                    cpu_name = lines[1].strip()
        except:
            pass
    
    return cpu_name, cores


def get_system_hardware() -> SystemHardwareInfo:
    """
    Get comprehensive system hardware information.
    """
    total_ram, available_ram = _get_ram_info()
    has_nvidia, gpu_name, vram_gb = _get_nvidia_gpu_info()
    cpu_name, cpu_cores = _get_cpu_info()
    
    return SystemHardwareInfo(
        total_ram_gb=total_ram,
        available_ram_gb=available_ram,
        has_nvidia_gpu=has_nvidia,
        gpu_name=gpu_name,
        gpu_vram_gb=vram_gb,
        cpu_name=cpu_name,
        cpu_cores=cpu_cores,
        platform=get_platform()
    )


# -------------------------
# LM Studio Model Recommendations
# -------------------------

@dataclass
class LMModelRecommendation:
    """A recommended LM Studio model"""
    name: str
    size_label: str  # e.g., "7B", "13B"
    ram_required_gb: float
    vram_required_gb: float  # For GPU inference
    description: str
    suitable: bool  # True if system can run it
    reason: str  # Why suitable or not
    download_size_gb: float


# Model database with requirements
LM_STUDIO_MODELS = [
    {
        'name': 'Llama 3.2 3B Instruct',
        'size_label': '3B',
        'ram_required_gb': 4,
        'vram_required_gb': 3,
        'download_size_gb': 2.0,
        'description': 'Smallest Llama - fast, good for basic tasks',
    },
    {
        'name': 'Mistral 7B Instruct',
        'size_label': '7B',
        'ram_required_gb': 6,
        'vram_required_gb': 5,
        'download_size_gb': 4.1,
        'description': 'Excellent balance of speed and quality',
    },
    {
        'name': 'Llama 3.2 8B Instruct',
        'size_label': '8B',
        'ram_required_gb': 8,
        'vram_required_gb': 6,
        'download_size_gb': 4.9,
        'description': 'Great all-rounder, good for document analysis',
    },
    {
        'name': 'Phi-3 Medium (14B)',
        'size_label': '14B',
        'ram_required_gb': 12,
        'vram_required_gb': 10,
        'download_size_gb': 8.0,
        'description': 'Microsoft model, strong reasoning',
    },
    {
        'name': 'Llama 3.1 70B Instruct',
        'size_label': '70B',
        'ram_required_gb': 48,
        'vram_required_gb': 40,
        'download_size_gb': 40.0,
        'description': 'Top quality, requires high-end hardware',
    },
]


def get_lm_studio_recommendations(hardware: SystemHardwareInfo) -> List[LMModelRecommendation]:
    """
    Get LM Studio model recommendations based on system hardware.
    """
    recommendations = []
    
    for model in LM_STUDIO_MODELS:
        # Determine if suitable and why
        if hardware.has_nvidia_gpu and hardware.gpu_vram_gb >= model['vram_required_gb']:
            # Can run on GPU
            suitable = True
            reason = f"✅ GPU: {hardware.gpu_vram_gb:.0f}GB VRAM available"
        elif hardware.total_ram_gb >= model['ram_required_gb']:
            # Can run on CPU
            suitable = True
            if hardware.has_nvidia_gpu:
                reason = f"⚠️ CPU only (needs {model['vram_required_gb']}GB VRAM, you have {hardware.gpu_vram_gb:.0f}GB)"
            else:
                reason = f"✅ CPU: {hardware.total_ram_gb:.0f}GB RAM available"
        else:
            # Cannot run
            suitable = False
            reason = f"❌ Needs {model['ram_required_gb']}GB RAM (you have {hardware.total_ram_gb:.0f}GB)"
        
        recommendations.append(LMModelRecommendation(
            name=model['name'],
            size_label=model['size_label'],
            ram_required_gb=model['ram_required_gb'],
            vram_required_gb=model['vram_required_gb'],
            description=model['description'],
            suitable=suitable,
            reason=reason,
            download_size_gb=model['download_size_gb']
        ))
    
    return recommendations


def get_top_lm_recommendation(hardware: SystemHardwareInfo) -> Optional[LMModelRecommendation]:
    """
    Get the single best model recommendation for this system.
    Picks the largest suitable model that will run well.
    """
    recommendations = get_lm_studio_recommendations(hardware)
    
    # Filter to suitable models
    suitable = [r for r in recommendations if r.suitable]
    
    if not suitable:
        return None
    
    # If we have GPU, prefer models that fit in VRAM
    if hardware.has_nvidia_gpu and hardware.gpu_vram_gb > 0:
        gpu_suitable = [r for r in suitable if r.vram_required_gb <= hardware.gpu_vram_gb]
        if gpu_suitable:
            # Return largest that fits in GPU
            return max(gpu_suitable, key=lambda r: r.ram_required_gb)
    
    # Otherwise return largest that fits in RAM
    return max(suitable, key=lambda r: r.ram_required_gb)


# -------------------------
# LM Studio Detection
# -------------------------

@dataclass
class LMStudioStatus:
    """Status of LM Studio installation"""
    installed: bool
    path: Optional[str] = None
    version: Optional[str] = None
    running: bool = False
    models_dir: Optional[str] = None
    model_count: int = 0


def _check_lm_studio_running(base_url: str = "http://localhost:1234") -> bool:
    """
    Check if LM Studio server is currently running.
    """
    import urllib.request
    import urllib.error
    
    try:
        req = urllib.request.Request(
            f"{base_url}/v1/models",
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=2) as response:
            return response.status == 200
    except:
        return False


def _find_lm_studio_models_dir() -> Tuple[Optional[str], int]:
    """
    Find LM Studio models directory and count models.
    Returns: (models_dir, model_count)
    """
    platform = get_platform()
    home = os.path.expanduser('~')
    
    # LM Studio default model locations
    if platform == "windows":
        possible_paths = [
            os.path.join(home, ".cache", "lm-studio", "models"),
            os.path.join(os.environ.get('USERPROFILE', ''), ".cache", "lm-studio", "models"),
        ]
    elif platform == "mac":
        possible_paths = [
            os.path.join(home, ".cache", "lm-studio", "models"),
        ]
    else:
        possible_paths = [
            os.path.join(home, ".cache", "lm-studio", "models"),
        ]
    
    for path in possible_paths:
        if os.path.exists(path) and os.path.isdir(path):
            # Count model folders (each model is typically a folder)
            try:
                model_count = sum(1 for item in os.listdir(path) 
                                  if os.path.isdir(os.path.join(path, item)))
                return path, model_count
            except:
                return path, 0
    
    return None, 0


def find_lm_studio() -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Find LM Studio installation.
    Returns: (installed: bool, path: str or None, version: str or None)
    """
    platform = get_platform()
    lm_studio_path = None
    
    if platform == "windows":
        # Check common Windows installation paths
        possible_paths = [
            os.path.join(os.environ.get('LOCALAPPDATA', ''), "Programs", "LM Studio", "LM Studio.exe"),
            os.path.join(os.environ.get('PROGRAMFILES', ''), "LM Studio", "LM Studio.exe"),
            os.path.join(os.environ.get('LOCALAPPDATA', ''), "LM-Studio", "LM Studio.exe"),
            # User might have it in different location
            os.path.join(os.path.expanduser('~'), "AppData", "Local", "Programs", "LM Studio", "LM Studio.exe"),
        ]
        for path in possible_paths:
            if os.path.exists(path):
                lm_studio_path = path
                break
    
    elif platform == "mac":
        # Check macOS application paths
        possible_paths = [
            "/Applications/LM Studio.app",
            os.path.expanduser("~/Applications/LM Studio.app"),
        ]
        for path in possible_paths:
            if os.path.exists(path):
                lm_studio_path = path
                break
    
    else:  # Linux
        # Check if lm-studio is available (AppImage or installed)
        lm_studio_path = shutil.which("lm-studio")
        if not lm_studio_path:
            # Check common Linux paths
            possible_paths = [
                os.path.expanduser("~/.local/bin/lm-studio"),
                os.path.expanduser("~/LM-Studio.AppImage"),
            ]
            for path in possible_paths:
                if os.path.exists(path):
                    lm_studio_path = path
                    break
    
    if not lm_studio_path:
        return False, None, None
    
    # Version detection is tricky - LM Studio doesn't have a CLI version flag
    # We just return "installed" for now
    return True, lm_studio_path, "installed"


def get_lm_studio_status() -> LMStudioStatus:
    """
    Get comprehensive LM Studio status.
    """
    installed, path, version = find_lm_studio()
    models_dir, model_count = _find_lm_studio_models_dir()
    running = _check_lm_studio_running()
    
    return LMStudioStatus(
        installed=installed,
        path=path,
        version=version,
        running=running,
        models_dir=models_dir,
        model_count=model_count
    )


# -------------------------
# Faster-Whisper Detection
# -------------------------

@dataclass
class WhisperModelInfo:
    """Information about a downloaded Whisper model"""
    name: str
    size_bytes: int
    size_display: str
    path: str


@dataclass 
class FasterWhisperStatus:
    """Comprehensive status of faster-whisper installation"""
    package_installed: bool
    package_version: Optional[str] = None
    
    # CUDA/GPU status
    cuda_available: bool = False
    cuda_version: Optional[str] = None
    gpu_name: Optional[str] = None
    compute_type: str = "int8"  # Best compute type for this system
    
    # Model information
    cache_dir: Optional[str] = None
    downloaded_models: List[WhisperModelInfo] = None
    total_models_size: int = 0
    total_models_size_display: str = "0 MB"
    
    # Recommendations
    recommended_model: str = "base"
    performance_note: str = ""
    
    def __post_init__(self):
        if self.downloaded_models is None:
            self.downloaded_models = []


# Whisper model sizes (approximate, for recommendations)
WHISPER_MODEL_SIZES = {
    'tiny': {'params': '39M', 'size_mb': 75, 'vram_gb': 1, 'relative_speed': 32},
    'tiny.en': {'params': '39M', 'size_mb': 75, 'vram_gb': 1, 'relative_speed': 32},
    'base': {'params': '74M', 'size_mb': 145, 'vram_gb': 1, 'relative_speed': 16},
    'base.en': {'params': '74M', 'size_mb': 145, 'vram_gb': 1, 'relative_speed': 16},
    'small': {'params': '244M', 'size_mb': 465, 'vram_gb': 2, 'relative_speed': 6},
    'small.en': {'params': '244M', 'size_mb': 465, 'vram_gb': 2, 'relative_speed': 6},
    'medium': {'params': '769M', 'size_mb': 1500, 'vram_gb': 5, 'relative_speed': 2},
    'medium.en': {'params': '769M', 'size_mb': 1500, 'vram_gb': 5, 'relative_speed': 2},
    'large-v1': {'params': '1550M', 'size_mb': 3000, 'vram_gb': 10, 'relative_speed': 1},
    'large-v2': {'params': '1550M', 'size_mb': 3000, 'vram_gb': 10, 'relative_speed': 1},
    'large-v3': {'params': '1550M', 'size_mb': 3000, 'vram_gb': 10, 'relative_speed': 1},
}


def _format_size(size_bytes: int) -> str:
    """Format bytes as human-readable size"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def _get_dir_size(path: str) -> int:
    """Get total size of directory in bytes"""
    total = 0
    try:
        for dirpath, dirnames, filenames in os.walk(path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if os.path.exists(fp):
                    total += os.path.getsize(fp)
    except Exception:
        pass
    return total


def _find_whisper_cache_dir() -> Optional[str]:
    """
    Find the Hugging Face cache directory where Whisper models are stored.
    Returns the path if found, None otherwise.
    """
    # Check environment variable first
    hf_home = os.environ.get('HF_HOME')
    if hf_home:
        cache_dir = os.path.join(hf_home, 'hub')
        if os.path.exists(cache_dir):
            return cache_dir
    
    # Check XDG cache (Linux)
    xdg_cache = os.environ.get('XDG_CACHE_HOME')
    if xdg_cache:
        cache_dir = os.path.join(xdg_cache, 'huggingface', 'hub')
        if os.path.exists(cache_dir):
            return cache_dir
    
    # Default locations by platform
    home = os.path.expanduser('~')
    
    possible_paths = [
        os.path.join(home, '.cache', 'huggingface', 'hub'),  # Linux/Mac default
        os.path.join(home, '.cache', 'huggingface'),  # Alternative
        os.path.join(os.environ.get('LOCALAPPDATA', ''), 'huggingface', 'hub'),  # Windows
        os.path.join(home, 'AppData', 'Local', 'huggingface', 'hub'),  # Windows fallback
    ]
    
    for path in possible_paths:
        if path and os.path.exists(path):
            return path
    
    return None


def _find_downloaded_whisper_models(cache_dir: Optional[str]) -> List[WhisperModelInfo]:
    """
    Find all downloaded faster-whisper models in the cache directory.
    Models are stored as 'models--Systran--faster-whisper-*' directories.
    """
    models = []
    
    if not cache_dir or not os.path.exists(cache_dir):
        return models
    
    try:
        for item in os.listdir(cache_dir):
            # Look for faster-whisper model directories
            if item.startswith('models--') and 'faster-whisper' in item.lower():
                model_path = os.path.join(cache_dir, item)
                if os.path.isdir(model_path):
                    # Extract model name from directory name
                    # Format: models--Systran--faster-whisper-large-v3
                    parts = item.split('--')
                    if len(parts) >= 3:
                        model_name = parts[-1].replace('faster-whisper-', '')
                    else:
                        model_name = item
                    
                    # Get size
                    size_bytes = _get_dir_size(model_path)
                    
                    models.append(WhisperModelInfo(
                        name=model_name,
                        size_bytes=size_bytes,
                        size_display=_format_size(size_bytes),
                        path=model_path
                    ))
    except Exception as e:
        print(f"Error scanning whisper models: {e}")
    
    return models


def _check_cuda_availability() -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Check if CUDA is available for GPU acceleration.
    Returns: (available: bool, cuda_version: str or None, gpu_name: str or None)
    """
    # Method 1: Try torch (most reliable if installed)
    try:
        import torch
        if torch.cuda.is_available():
            cuda_version = torch.version.cuda
            gpu_name = torch.cuda.get_device_name(0) if torch.cuda.device_count() > 0 else None
            return True, cuda_version, gpu_name
    except ImportError:
        pass
    except Exception:
        pass
    
    # Method 2: Try ctranslate2 (what faster-whisper actually uses)
    try:
        import ctranslate2
        # ctranslate2 doesn't have a direct CUDA check, but we can try to detect
        # by checking if cuda compute types are available
        cuda_available = 'cuda' in str(ctranslate2.get_supported_compute_types('cuda')).lower()
        if cuda_available:
            return True, "available", None
    except Exception:
        pass
    
    # Method 3: Check for nvidia-smi (Windows/Linux)
    try:
        platform = get_platform()
        nvidia_smi = shutil.which('nvidia-smi')
        
        if nvidia_smi:
            result = subprocess.run(
                [nvidia_smi, '--query-gpu=name,driver_version', '--format=csv,noheader'],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW if platform == "windows" else 0
            )
            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split(',')
                gpu_name = parts[0].strip() if parts else None
                return True, "available", gpu_name
    except Exception:
        pass
    
    return False, None, None


def _get_recommended_compute_type(cuda_available: bool) -> str:
    """
    Get the recommended compute type based on hardware.
    """
    if cuda_available:
        # For CUDA, float16 is usually fastest
        return "float16"
    else:
        # For CPU, int8 is fastest
        return "int8"


def _get_recommended_model(cuda_available: bool, has_models: List[WhisperModelInfo]) -> Tuple[str, str]:
    """
    Get recommended model and performance note based on hardware.
    Returns: (recommended_model, performance_note)
    """
    downloaded_names = [m.name for m in has_models]
    
    if cuda_available:
        # With GPU, can use larger models
        if 'large-v3' in downloaded_names:
            return 'large-v3', "GPU detected - using large-v3 for best accuracy"
        elif 'large-v2' in downloaded_names:
            return 'large-v2', "GPU detected - using large-v2 for best accuracy"
        elif 'medium' in downloaded_names or 'medium.en' in downloaded_names:
            return 'medium', "GPU detected - medium model offers good balance"
        elif any('small' in n for n in downloaded_names):
            return 'small', "GPU detected - consider downloading 'medium' or 'large-v3' for better accuracy"
        else:
            return 'medium', "GPU detected - recommend downloading 'medium' model (1.5 GB)"
    else:
        # CPU only - recommend smaller models
        if 'base' in downloaded_names or 'base.en' in downloaded_names:
            return 'base', "CPU mode - 'base' model offers good speed/accuracy balance"
        elif 'small' in downloaded_names or 'small.en' in downloaded_names:
            return 'small', "CPU mode - 'small' model is accurate but slower"
        elif 'tiny' in downloaded_names or 'tiny.en' in downloaded_names:
            return 'tiny', "CPU mode - 'tiny' is fastest but less accurate"
        else:
            return 'base', "CPU mode - recommend downloading 'base' model (145 MB)"


def get_faster_whisper_status() -> FasterWhisperStatus:
    """
    Get comprehensive status of faster-whisper installation.
    Checks package, models, and CUDA availability.
    """
    status = FasterWhisperStatus(package_installed=False)
    
    # Check if package is installed
    try:
        import faster_whisper
        status.package_installed = True
        status.package_version = getattr(faster_whisper, '__version__', 'unknown')
    except ImportError:
        return status  # Return early if not installed
    
    # Check CUDA availability
    cuda_available, cuda_version, gpu_name = _check_cuda_availability()
    status.cuda_available = cuda_available
    status.cuda_version = cuda_version
    status.gpu_name = gpu_name
    status.compute_type = _get_recommended_compute_type(cuda_available)
    
    # Find cache directory and models
    status.cache_dir = _find_whisper_cache_dir()
    status.downloaded_models = _find_downloaded_whisper_models(status.cache_dir)
    
    # Calculate total size
    status.total_models_size = sum(m.size_bytes for m in status.downloaded_models)
    status.total_models_size_display = _format_size(status.total_models_size)
    
    # Get recommendations
    status.recommended_model, status.performance_note = _get_recommended_model(
        cuda_available, status.downloaded_models
    )
    
    return status


# -------------------------
# Python Package Detection
# -------------------------

def check_python_package(package_name: str, import_name: str = None) -> Tuple[bool, Optional[str]]:
    """
    Check if a Python package is installed.
    Returns: (installed: bool, version: str or None)
    """
    if import_name is None:
        import_name = package_name
    
    try:
        module = __import__(import_name)
        version = getattr(module, '__version__', getattr(module, 'VERSION', 'unknown'))
        return True, str(version)
    except ImportError:
        return False, None


def get_optional_packages_status() -> Dict[str, Tuple[bool, str]]:
    """
    Check status of optional Python packages.
    Returns dict of {package_name: (installed, required_for)}
    """
    packages = {
        'tkinterdnd2': ('tkinterdnd2', "Drag-and-drop support"),
        'faster_whisper': ('faster_whisper', "Local audio transcription"),
        'pytesseract': ('pytesseract', "OCR processing"),
        'pdf2image': ('pdf2image', "PDF OCR processing"),
        'PyMuPDF': ('fitz', "Enhanced PDF text extraction"),
    }
    
    results = {}
    for display_name, (import_name, purpose) in packages.items():
        installed, version = check_python_package(display_name, import_name)
        results[display_name] = (installed, purpose, version)
    
    return results


# -------------------------
# Complete System Check
# -------------------------

def check_all_dependencies() -> Dict[str, DependencyStatus]:
    """
    Check all external dependencies.
    Returns dict of {name: DependencyStatus}
    """
    return {
        'tesseract': get_tesseract_status(),
        'poppler': get_poppler_status(),
        'ffmpeg': get_ffmpeg_status(),
    }


def get_missing_dependencies() -> List[DependencyStatus]:
    """Get list of dependencies that are not installed"""
    all_deps = check_all_dependencies()
    return [dep for dep in all_deps.values() if not dep.installed]


def get_system_summary() -> dict:
    """
    Get a summary of system readiness.
    Returns dict with status info for display.
    """
    deps = check_all_dependencies()
    packages = get_optional_packages_status()
    
    # Determine feature availability
    features = {
        'youtube': True,  # Always available (uses yt-dlp)
        'web': True,  # Always available (uses requests/beautifulsoup)
        'documents': True,  # Always available (basic file reading)
        'ocr': deps['tesseract'].installed and deps['poppler'].installed,
        'audio': deps['ffmpeg'].installed,
        'local_ai': packages.get('faster_whisper', (False,))[0],
        'drag_drop': packages.get('tkinterdnd2', (False,))[0],
    }
    
    return {
        'dependencies': deps,
        'packages': packages,
        'features': features,
        'platform': get_platform(),
        'all_ready': all(dep.installed for dep in deps.values()),
    }


# -------------------------
# Quick Test
# -------------------------

if __name__ == "__main__":
    print("DocAnalyser Dependency Check")
    print("=" * 50)
    
    summary = get_system_summary()
    
    print(f"\nPlatform: {summary['platform']}")
    print("\nExternal Tools:")
    print("-" * 30)
    
    for name, dep in summary['dependencies'].items():
        status = "✅ Installed" if dep.installed else "❌ Not Found"
        version = f" (v{dep.version})" if dep.version else ""
        print(f"  {dep.name}: {status}{version}")
        if not dep.installed:
            print(f"    → Required for: {dep.required_for}")
    
    print("\nPython Packages:")
    print("-" * 30)
    
    for name, (installed, purpose, version) in summary['packages'].items():
        status = "✅" if installed else "⚠️"
        ver = f" (v{version})" if version else ""
        print(f"  {status} {name}{ver} - {purpose}")
    
    print("\nFeature Availability:")
    print("-" * 30)
    
    feature_names = {
        'youtube': 'YouTube Transcripts',
        'web': 'Web Articles',
        'documents': 'Document Files',
        'ocr': 'OCR (Scanned Docs)',
        'audio': 'Audio Transcription',
        'local_ai': 'Local Whisper',
        'drag_drop': 'Drag & Drop',
    }
    
    for key, name in feature_names.items():
        status = "✅ Ready" if summary['features'].get(key) else "⚠️ Needs Setup"
        print(f"  {name}: {status}")
    
    # Detailed Faster-Whisper status
    print("\n" + "=" * 50)
    print("Faster-Whisper Details")
    print("=" * 50)
    
    whisper = get_faster_whisper_status()
    
    if not whisper.package_installed:
        print("\n❌ faster-whisper not installed")
        print("   Install with: pip install faster-whisper")
    else:
        print(f"\n✅ Package installed (v{whisper.package_version})")
        
        # GPU status
        print("\nGPU/CUDA Status:")
        print("-" * 30)
        if whisper.cuda_available:
            print(f"  ✅ CUDA available")
            if whisper.gpu_name:
                print(f"     GPU: {whisper.gpu_name}")
            if whisper.cuda_version:
                print(f"     CUDA version: {whisper.cuda_version}")
            print(f"     Recommended compute type: {whisper.compute_type}")
        else:
            print(f"  ⚠️ CUDA not available (CPU mode)")
            print(f"     Compute type: {whisper.compute_type}")
        
        # Downloaded models
        print("\nDownloaded Models:")
        print("-" * 30)
        if whisper.downloaded_models:
            for model in whisper.downloaded_models:
                print(f"  📦 {model.name} ({model.size_display})")
            print(f"\n  Total: {len(whisper.downloaded_models)} model(s), {whisper.total_models_size_display}")
        else:
            print("  No models downloaded yet")
            print("  Models download automatically on first use")
        
        # Recommendations
        print("\nRecommendation:")
        print("-" * 30)
        print(f"  {whisper.performance_note}")
        
        if whisper.cache_dir:
            print(f"\nCache location: {whisper.cache_dir}")
    
    # Detailed LM Studio status
    print("\n" + "=" * 50)
    print("LM Studio Details")
    print("=" * 50)
    
    lm_studio = get_lm_studio_status()
    
    if not lm_studio.installed:
        print("\n❌ LM Studio not installed")
        print("   Download from: https://lmstudio.ai")
    else:
        print(f"\n✅ LM Studio installed")
        if lm_studio.path:
            print(f"   Path: {lm_studio.path}")
        
        # Server status
        print("\nServer Status:")
        print("-" * 30)
        if lm_studio.running:
            print("  ✅ Server is running (ready to use!)")
        else:
            print("  ⚠️ Server is not running")
            print("     Start LM Studio and load a model to use local AI")
        
        # Models
        print("\nDownloaded Models:")
        print("-" * 30)
        if lm_studio.model_count > 0:
            print(f"  📦 {lm_studio.model_count} model(s) found")
            if lm_studio.models_dir:
                print(f"     Location: {lm_studio.models_dir}")
        else:
            print("  No models downloaded yet")
    
    # System Hardware & Model Recommendations
    print("\n" + "=" * 50)
    print("System Hardware & LM Studio Recommendations")
    print("=" * 50)
    
    hardware = get_system_hardware()
    
    print("\nYour System:")
    print("-" * 30)
    print(f"  💾 RAM: {hardware.total_ram_gb:.1f} GB total, {hardware.available_ram_gb:.1f} GB available")
    
    if hardware.has_nvidia_gpu:
        print(f"  🎮 GPU: {hardware.gpu_name}")
        print(f"       VRAM: {hardware.gpu_vram_gb:.1f} GB")
    else:
        print("  🎮 GPU: No NVIDIA GPU detected (will use CPU)")
    
    if hardware.cpu_name:
        print(f"  🖥️ CPU: {hardware.cpu_name}")
        if hardware.cpu_cores > 0:
            print(f"       Cores: {hardware.cpu_cores}")
    
    print("\nModel Recommendations:")
    print("-" * 30)
    
    recommendations = get_lm_studio_recommendations(hardware)
    top_rec = get_top_lm_recommendation(hardware)
    
    for rec in recommendations:
        if top_rec and rec.name == top_rec.name:
            icon = "⭐ RECOMMENDED:"
        elif rec.suitable:
            icon = "✅"
        else:
            icon = "❌"
        
        print(f"  {icon} {rec.name}")
        print(f"       {rec.description}")
        print(f"       Download: {rec.download_size_gb:.1f} GB | RAM: {rec.ram_required_gb:.0f} GB | VRAM: {rec.vram_required_gb:.0f} GB")
        print(f"       {rec.reason}")
        print()
