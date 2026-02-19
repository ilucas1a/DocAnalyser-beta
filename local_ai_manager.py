"""
local_ai_manager.py - Smart Local AI Integration for DocAnalyzer

This module provides a seamless local AI experience by:
1. Detecting system capabilities (RAM, VRAM, GPU)
2. Managing Ollama installation and models
3. Recommending appropriate models for the user's hardware
4. Pre-flight checking documents against model capabilities
5. Providing clear, actionable error messages

Author: DocAnalyzer Development
Version: 1.0.0
"""

import os
import sys
import json
import subprocess
import shutil
import platform
import requests
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum


# =============================================================================
# DATA CLASSES AND ENUMS
# =============================================================================

class ModelCapability(Enum):
    """Model capability levels based on system resources"""
    MINIMAL = "minimal"      # 4GB RAM, no GPU - very small models only
    BASIC = "basic"          # 8GB RAM, basic GPU - 3B models
    STANDARD = "standard"    # 16GB RAM, 8GB VRAM - 7-8B models
    ADVANCED = "advanced"    # 32GB RAM, 12GB+ VRAM - 13B+ models
    PROFESSIONAL = "professional"  # 64GB+ RAM, 24GB+ VRAM - 70B models


@dataclass
class SystemSpecs:
    """System hardware specifications"""
    total_ram_gb: float
    available_ram_gb: float
    gpu_name: str
    gpu_vram_gb: float
    has_nvidia: bool
    has_amd: bool
    has_apple_silicon: bool
    cpu_name: str
    os_name: str
    capability_level: ModelCapability
    
    def to_display_string(self) -> str:
        """Format specs for display to user"""
        gpu_info = f"{self.gpu_name} ({self.gpu_vram_gb:.1f}GB VRAM)" if self.gpu_vram_gb > 0 else "No dedicated GPU"
        return (
            f"RAM: {self.total_ram_gb:.1f}GB total ({self.available_ram_gb:.1f}GB available)\n"
            f"GPU: {gpu_info}\n"
            f"Capability: {self.capability_level.value.title()}"
        )


@dataclass
class ModelInfo:
    """Information about a local AI model"""
    name: str                    # Display name
    ollama_id: str              # Ollama model identifier
    size_gb: float              # Download size in GB
    ram_required_gb: float      # Minimum RAM needed
    vram_required_gb: float     # Minimum VRAM for GPU acceleration (0 = CPU-only OK)
    context_window: int         # Maximum context length in tokens
    description: str            # User-friendly description
    recommended_for: str        # What it's good for
    quality_tier: str           # "basic", "good", "excellent"
    is_fast: bool              # True if optimized for speed
    supports_vision: bool       # True if multimodal


# =============================================================================
# MODEL DATABASE
# =============================================================================

# Curated list of models with accurate requirements
# Only includes CHAT models (not embedding models!)
MODEL_DATABASE: Dict[str, ModelInfo] = {
    # --- SMALL MODELS (Good for limited hardware) ---
    "llama3.2:1b": ModelInfo(
        name="Llama 3.2 1B",
        ollama_id="llama3.2:1b",
        size_gb=1.3,
        ram_required_gb=4,
        vram_required_gb=0,
        context_window=131072,
        description="Tiny but capable. Good for basic tasks on any hardware.",
        recommended_for="Quick summaries, simple Q&A",
        quality_tier="basic",
        is_fast=True,
        supports_vision=False
    ),
    "llama3.2:3b": ModelInfo(
        name="Llama 3.2 3B",
        ollama_id="llama3.2:3b",
        size_gb=2.0,
        ram_required_gb=6,
        vram_required_gb=0,
        context_window=131072,
        description="Small but smart. Great balance of speed and quality.",
        recommended_for="Summaries, analysis, general tasks",
        quality_tier="good",
        is_fast=True,
        supports_vision=False
    ),
    "phi3:mini": ModelInfo(
        name="Phi-3 Mini (3.8B)",
        ollama_id="phi3:mini",
        size_gb=2.3,
        ram_required_gb=6,
        vram_required_gb=0,
        context_window=4096,
        description="Microsoft's efficient small model. Strong reasoning.",
        recommended_for="Analysis, coding assistance, reasoning tasks",
        quality_tier="good",
        is_fast=True,
        supports_vision=False
    ),
    "gemma2:2b": ModelInfo(
        name="Gemma 2 2B",
        ollama_id="gemma2:2b",
        size_gb=1.6,
        ram_required_gb=4,
        vram_required_gb=0,
        context_window=8192,
        description="Google's efficient small model. Good quality for size.",
        recommended_for="Quick tasks, summaries",
        quality_tier="basic",
        is_fast=True,
        supports_vision=False
    ),
    
    # --- MEDIUM MODELS (Standard hardware) ---
    "llama3.1:8b": ModelInfo(
        name="Llama 3.1 8B",
        ollama_id="llama3.1:8b",
        size_gb=4.7,
        ram_required_gb=10,
        vram_required_gb=6,
        context_window=131072,
        description="Excellent all-rounder. Strong performance across tasks.",
        recommended_for="Document analysis, writing, complex Q&A",
        quality_tier="excellent",
        is_fast=False,
        supports_vision=False
    ),
    "mistral:7b": ModelInfo(
        name="Mistral 7B",
        ollama_id="mistral:7b",
        size_gb=4.1,
        ram_required_gb=10,
        vram_required_gb=6,
        context_window=32768,
        description="Fast and capable. Great for general use.",
        recommended_for="General tasks, good speed",
        quality_tier="good",
        is_fast=True,
        supports_vision=False
    ),
    "qwen2.5:7b": ModelInfo(
        name="Qwen 2.5 7B",
        ollama_id="qwen2.5:7b",
        size_gb=4.4,
        ram_required_gb=10,
        vram_required_gb=6,
        context_window=131072,
        description="Strong multilingual model with huge context window.",
        recommended_for="Long documents, multilingual content",
        quality_tier="excellent",
        is_fast=False,
        supports_vision=False
    ),
    "gemma2:9b": ModelInfo(
        name="Gemma 2 9B",
        ollama_id="gemma2:9b",
        size_gb=5.5,
        ram_required_gb=12,
        vram_required_gb=8,
        context_window=8192,
        description="Google's quality-focused model. Excellent outputs.",
        recommended_for="High-quality analysis and writing",
        quality_tier="excellent",
        is_fast=False,
        supports_vision=False
    ),
    
    # --- LARGE MODELS (Good hardware required) ---
    "llama3.1:70b-q4_0": ModelInfo(
        name="Llama 3.1 70B (Quantized)",
        ollama_id="llama3.1:70b-q4_0",
        size_gb=40,
        ram_required_gb=48,
        vram_required_gb=24,
        context_window=131072,
        description="Near-GPT-4 quality. Requires powerful hardware.",
        recommended_for="Complex analysis, professional work",
        quality_tier="excellent",
        is_fast=False,
        supports_vision=False
    ),
    "qwen2.5:14b": ModelInfo(
        name="Qwen 2.5 14B",
        ollama_id="qwen2.5:14b",
        size_gb=9.0,
        ram_required_gb=20,
        vram_required_gb=12,
        context_window=131072,
        description="Larger Qwen with improved reasoning.",
        recommended_for="Complex documents, detailed analysis",
        quality_tier="excellent",
        is_fast=False,
        supports_vision=False
    ),
    
    # --- VISION MODELS (Can analyze images) ---
    "llava:7b": ModelInfo(
        name="LLaVA 7B (Vision)",
        ollama_id="llava:7b",
        size_gb=4.5,
        ram_required_gb=10,
        vram_required_gb=6,
        context_window=4096,
        description="Can analyze images and documents visually.",
        recommended_for="Image analysis, visual documents",
        quality_tier="good",
        is_fast=False,
        supports_vision=True
    ),
    "llama3.2-vision:11b": ModelInfo(
        name="Llama 3.2 Vision 11B",
        ollama_id="llama3.2-vision:11b",
        size_gb=7.9,
        ram_required_gb=14,
        vram_required_gb=10,
        context_window=131072,
        description="Meta's vision model. Strong image understanding.",
        recommended_for="Image analysis, visual Q&A",
        quality_tier="excellent",
        is_fast=False,
        supports_vision=True
    ),
    
    # --- SPECIALIZED MODELS ---
    "deepseek-r1:7b": ModelInfo(
        name="DeepSeek R1 7B (Reasoning)",
        ollama_id="deepseek-r1:7b",
        size_gb=4.7,
        ram_required_gb=10,
        vram_required_gb=6,
        context_window=65536,
        description="Specialized for reasoning and step-by-step thinking.",
        recommended_for="Complex reasoning, analysis, problem-solving",
        quality_tier="excellent",
        is_fast=False,
        supports_vision=False
    ),
}


# =============================================================================
# SYSTEM DETECTION
# =============================================================================

def detect_system_specs() -> SystemSpecs:
    """
    Detect system hardware specifications.
    Returns a SystemSpecs object with all relevant information.
    """
    import psutil
    
    # Get RAM info
    mem = psutil.virtual_memory()
    total_ram_gb = mem.total / (1024 ** 3)
    available_ram_gb = mem.available / (1024 ** 3)
    
    # Get CPU info
    cpu_name = platform.processor() or "Unknown CPU"
    
    # Get OS info
    os_name = f"{platform.system()} {platform.release()}"
    
    # Detect GPU
    gpu_name, gpu_vram_gb, has_nvidia, has_amd, has_apple_silicon = _detect_gpu()
    
    # Determine capability level
    capability_level = _determine_capability_level(total_ram_gb, gpu_vram_gb, has_apple_silicon)
    
    return SystemSpecs(
        total_ram_gb=total_ram_gb,
        available_ram_gb=available_ram_gb,
        gpu_name=gpu_name,
        gpu_vram_gb=gpu_vram_gb,
        has_nvidia=has_nvidia,
        has_amd=has_amd,
        has_apple_silicon=has_apple_silicon,
        cpu_name=cpu_name,
        os_name=os_name,
        capability_level=capability_level
    )


def _detect_gpu() -> Tuple[str, float, bool, bool, bool]:
    """
    Detect GPU information.
    Returns: (gpu_name, vram_gb, has_nvidia, has_amd, has_apple_silicon)
    """
    gpu_name = "No dedicated GPU"
    gpu_vram_gb = 0.0
    has_nvidia = False
    has_amd = False
    has_apple_silicon = False
    
    # Check for Apple Silicon first
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        has_apple_silicon = True
        # Apple Silicon shares memory, estimate usable for ML
        import psutil
        total_ram = psutil.virtual_memory().total / (1024 ** 3)
        # Apple Silicon can typically use ~75% of RAM for ML workloads
        gpu_vram_gb = total_ram * 0.75
        
        # Try to get chip name
        try:
            result = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True, text=True, timeout=5
            )
            chip_info = result.stdout.strip()
            if "Apple" in chip_info:
                gpu_name = chip_info
            else:
                gpu_name = "Apple Silicon"
        except:
            gpu_name = "Apple Silicon"
        
        return gpu_name, gpu_vram_gb, has_nvidia, has_amd, has_apple_silicon
    
    # Try NVIDIA detection (Windows/Linux)
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.strip().split('\n')
            if lines:
                parts = lines[0].split(',')
                if len(parts) >= 2:
                    gpu_name = parts[0].strip()
                    gpu_vram_gb = float(parts[1].strip()) / 1024  # Convert MB to GB
                    has_nvidia = True
                    return gpu_name, gpu_vram_gb, has_nvidia, has_amd, has_apple_silicon
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        pass
    
    # Try Windows WMI for any GPU
    if platform.system() == "Windows":
        try:
            import wmi
            w = wmi.WMI()
            for gpu in w.Win32_VideoController():
                if gpu.AdapterRAM and gpu.AdapterRAM > 0:
                    gpu_name = gpu.Name
                    gpu_vram_gb = gpu.AdapterRAM / (1024 ** 3)
                    has_nvidia = "nvidia" in gpu_name.lower()
                    has_amd = "amd" in gpu_name.lower() or "radeon" in gpu_name.lower()
                    return gpu_name, gpu_vram_gb, has_nvidia, has_amd, has_apple_silicon
        except ImportError:
            pass
        except Exception:
            pass
        
        # Fallback: Try PowerShell
        try:
            result = subprocess.run(
                ["powershell", "-Command", 
                 "Get-CimInstance Win32_VideoController | Select-Object Name, AdapterRAM | ConvertTo-Json"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                if isinstance(data, list):
                    data = data[0] if data else {}
                if data.get("AdapterRAM"):
                    gpu_name = data.get("Name", "Unknown GPU")
                    gpu_vram_gb = data["AdapterRAM"] / (1024 ** 3)
                    has_nvidia = "nvidia" in gpu_name.lower()
                    has_amd = "amd" in gpu_name.lower() or "radeon" in gpu_name.lower()
        except:
            pass
    
    return gpu_name, gpu_vram_gb, has_nvidia, has_amd, has_apple_silicon


def _determine_capability_level(ram_gb: float, vram_gb: float, apple_silicon: bool) -> ModelCapability:
    """Determine system capability level based on hardware"""
    
    # Apple Silicon uses unified memory efficiently
    if apple_silicon:
        if ram_gb >= 64:
            return ModelCapability.PROFESSIONAL
        elif ram_gb >= 32:
            return ModelCapability.ADVANCED
        elif ram_gb >= 16:
            return ModelCapability.STANDARD
        elif ram_gb >= 8:
            return ModelCapability.BASIC
        else:
            return ModelCapability.MINIMAL
    
    # For discrete GPUs, VRAM is the key factor
    if vram_gb >= 24:
        return ModelCapability.PROFESSIONAL
    elif vram_gb >= 12:
        return ModelCapability.ADVANCED
    elif vram_gb >= 8:
        return ModelCapability.STANDARD
    elif vram_gb >= 4 or ram_gb >= 16:
        return ModelCapability.BASIC
    else:
        return ModelCapability.MINIMAL


# =============================================================================
# OLLAMA MANAGEMENT
# =============================================================================

class OllamaManager:
    """Manages Ollama installation, models, and API communication"""
    
    DEFAULT_URL = "http://localhost:11434"
    
    def __init__(self, base_url: str = None):
        self.base_url = base_url or self.DEFAULT_URL
        self._api_url = f"{self.base_url}/api"
        self._openai_url = f"{self.base_url}/v1"
    
    @property
    def openai_compatible_url(self) -> str:
        """Get the OpenAI-compatible API URL for use with existing code"""
        return self._openai_url
    
    def is_installed(self) -> Tuple[bool, str]:
        """
        Check if Ollama is installed on the system.
        Returns: (installed: bool, message: str)
        """
        # Check if ollama command exists
        ollama_path = shutil.which("ollama")
        
        if ollama_path:
            return True, f"Ollama found at: {ollama_path}"
        
        # Check common installation locations
        if platform.system() == "Windows":
            common_paths = [
                Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe",
                Path(os.environ.get("PROGRAMFILES", "")) / "Ollama" / "ollama.exe",
            ]
        elif platform.system() == "Darwin":
            common_paths = [
                Path("/usr/local/bin/ollama"),
                Path.home() / ".ollama" / "ollama",
            ]
        else:  # Linux
            common_paths = [
                Path("/usr/local/bin/ollama"),
                Path("/usr/bin/ollama"),
            ]
        
        for path in common_paths:
            if path.exists():
                return True, f"Ollama found at: {path}"
        
        return False, "Ollama is not installed"
    
    def is_running(self) -> Tuple[bool, str]:
        """
        Check if Ollama server is running.
        Returns: (running: bool, message: str)
        """
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                return True, "Ollama server is running"
            else:
                return False, f"Ollama server returned status {response.status_code}"
        except requests.exceptions.ConnectionError:
            return False, "Cannot connect to Ollama server"
        except requests.exceptions.Timeout:
            return False, "Connection to Ollama server timed out"
        except Exception as e:
            return False, f"Error checking Ollama: {str(e)}"
    
    def start_server(self) -> Tuple[bool, str]:
        """
        Attempt to start Ollama server.
        Returns: (success: bool, message: str)
        """
        try:
            if platform.system() == "Windows":
                # On Windows, try to start Ollama app
                subprocess.Popen(
                    ["ollama", "serve"],
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            else:
                subprocess.Popen(
                    ["ollama", "serve"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            
            # Wait for server to start
            import time
            for _ in range(10):
                time.sleep(1)
                running, _ = self.is_running()
                if running:
                    return True, "Ollama server started successfully"
            
            return False, "Ollama server did not start in time"
        
        except FileNotFoundError:
            return False, "Ollama command not found. Please install Ollama first."
        except Exception as e:
            return False, f"Failed to start Ollama: {str(e)}"
    
    def get_installed_models(self) -> Tuple[bool, str, List[Dict]]:
        """
        Get list of models installed in Ollama.
        Returns: (success: bool, message: str, models: list)
        """
        try:
            response = requests.get(f"{self._api_url}/tags", timeout=10)
            if response.status_code == 200:
                data = response.json()
                models = data.get("models", [])
                
                # Extract relevant info
                model_list = []
                for m in models:
                    model_list.append({
                        "name": m.get("name", "unknown"),
                        "size": m.get("size", 0),
                        "modified": m.get("modified_at", ""),
                        "digest": m.get("digest", "")[:12],
                    })
                
                return True, f"Found {len(model_list)} installed model(s)", model_list
            else:
                return False, f"Failed to get models: HTTP {response.status_code}", []
        
        except requests.exceptions.ConnectionError:
            return False, "Cannot connect to Ollama server", []
        except Exception as e:
            return False, f"Error getting models: {str(e)}", []
    
    def pull_model(self, model_id: str, progress_callback=None) -> Tuple[bool, str]:
        """
        Download a model from Ollama.
        
        Args:
            model_id: Ollama model identifier (e.g., "llama3.2:3b")
            progress_callback: Optional callback function(status: str, percent: float)
        
        Returns: (success: bool, message: str)
        """
        try:
            response = requests.post(
                f"{self._api_url}/pull",
                json={"name": model_id, "stream": True},
                stream=True,
                timeout=600  # 10 minute timeout for downloads
            )
            
            if response.status_code != 200:
                return False, f"Failed to start download: HTTP {response.status_code}"
            
            last_status = ""
            for line in response.iter_lines():
                if line:
                    try:
                        data = json.loads(line)
                        status = data.get("status", "")
                        
                        # Calculate progress if available
                        total = data.get("total", 0)
                        completed = data.get("completed", 0)
                        percent = (completed / total * 100) if total > 0 else 0
                        
                        if progress_callback and status != last_status:
                            progress_callback(status, percent)
                            last_status = status
                        
                        if data.get("error"):
                            return False, f"Download error: {data['error']}"
                    
                    except json.JSONDecodeError:
                        continue
            
            return True, f"Successfully downloaded {model_id}"
        
        except requests.exceptions.Timeout:
            return False, "Download timed out. Please try again."
        except Exception as e:
            return False, f"Download failed: {str(e)}"
    
    def delete_model(self, model_id: str) -> Tuple[bool, str]:
        """Delete a model from Ollama"""
        try:
            response = requests.delete(
                f"{self._api_url}/delete",
                json={"name": model_id},
                timeout=30
            )
            
            if response.status_code == 200:
                return True, f"Deleted {model_id}"
            else:
                return False, f"Failed to delete: HTTP {response.status_code}"
        
        except Exception as e:
            return False, f"Delete failed: {str(e)}"
    
    def get_model_info(self, model_id: str) -> Tuple[bool, Dict]:
        """Get detailed information about a model"""
        try:
            response = requests.post(
                f"{self._api_url}/show",
                json={"name": model_id},
                timeout=10
            )
            
            if response.status_code == 200:
                return True, response.json()
            else:
                return False, {}
        
        except Exception as e:
            return False, {}


# =============================================================================
# SMART MODEL SELECTION
# =============================================================================

def get_compatible_models(specs: SystemSpecs) -> List[Tuple[ModelInfo, str]]:
    """
    Get list of models compatible with the user's system.
    
    Returns: List of (ModelInfo, compatibility_note) tuples
             Sorted by recommendation (best first)
    """
    compatible = []
    
    for model_id, info in MODEL_DATABASE.items():
        # Check RAM requirement
        if info.ram_required_gb > specs.total_ram_gb:
            continue
        
        # Determine compatibility note
        note = ""
        
        if specs.has_apple_silicon:
            # Apple Silicon can use most models efficiently
            note = "✅ Recommended"
        elif specs.gpu_vram_gb >= info.vram_required_gb and info.vram_required_gb > 0:
            # Good GPU acceleration available
            note = "✅ GPU accelerated"
        elif info.vram_required_gb == 0 or specs.total_ram_gb >= info.ram_required_gb + 4:
            # Can run on CPU with sufficient RAM
            note = "⚠️ CPU mode (slower)"
        else:
            # Marginal - might work but not recommended
            note = "⚠️ Marginal (may be slow)"
        
        compatible.append((info, note))
    
    # Sort: Recommended first, then by quality tier, then by size
    def sort_key(item):
        info, note = item
        # Priority: recommended > GPU accelerated > CPU mode > marginal
        priority = 0 if "Recommended" in note else (1 if "GPU" in note else (2 if "CPU" in note else 3))
        # Quality: excellent > good > basic
        quality = {"excellent": 0, "good": 1, "basic": 2}.get(info.quality_tier, 3)
        return (priority, quality, info.size_gb)
    
    compatible.sort(key=sort_key)
    return compatible


def get_recommended_model(specs: SystemSpecs) -> Optional[ModelInfo]:
    """Get the single best recommended model for the user's system"""
    compatible = get_compatible_models(specs)
    if compatible:
        return compatible[0][0]
    return None


# =============================================================================
# PRE-FLIGHT CHECKS
# =============================================================================

def estimate_tokens(text: str) -> int:
    """
    Estimate the number of tokens in text.
    Uses rough approximation: ~4 characters per token for English.
    """
    # More accurate: ~3.5-4 chars per token for English
    # Use 3.5 to be conservative (better to overestimate)
    return int(len(text) / 3.5)


def check_document_fits(text: str, model_info: ModelInfo) -> Tuple[bool, str, Dict]:
    """
    Check if a document fits within a model's context window.
    
    Returns: (fits: bool, message: str, details: dict)
    """
    estimated_tokens = estimate_tokens(text)
    
    # Reserve tokens for the response (~2000) and prompt template (~500)
    available_context = model_info.context_window - 2500
    
    details = {
        "estimated_tokens": estimated_tokens,
        "model_context_window": model_info.context_window,
        "available_for_document": available_context,
        "utilization_percent": (estimated_tokens / available_context * 100) if available_context > 0 else 999
    }
    
    if estimated_tokens <= available_context:
        if details["utilization_percent"] > 80:
            return True, f"Document fits but uses {details['utilization_percent']:.0f}% of available context", details
        return True, "Document fits within context window", details
    else:
        overflow = estimated_tokens - available_context
        return False, (
            f"Document too large for {model_info.name}.\n\n"
            f"• Document: ~{estimated_tokens:,} tokens\n"
            f"• Model limit: {available_context:,} tokens\n"
            f"• Overflow: {overflow:,} tokens\n\n"
            f"Options:\n"
            f"1. Use a model with larger context (e.g., Llama 3.2 with 128K context)\n"
            f"2. Enable chunking in DocAnalyzer settings\n"
            f"3. Summarize or shorten the document"
        ), details


def recommend_model_for_document(text: str, specs: SystemSpecs) -> Optional[ModelInfo]:
    """
    Recommend the best model for a specific document based on length and system capabilities.
    """
    tokens = estimate_tokens(text)
    compatible = get_compatible_models(specs)
    
    # Find smallest model that can handle the document
    for info, note in compatible:
        available_context = info.context_window - 2500
        if tokens <= available_context and "Recommended" in note or "GPU" in note:
            return info
    
    # Fallback: any model that fits
    for info, note in compatible:
        available_context = info.context_window - 2500
        if tokens <= available_context:
            return info
    
    return None


# =============================================================================
# INSTALLATION HELPERS
# =============================================================================

def get_ollama_install_instructions() -> str:
    """Get platform-specific installation instructions for Ollama"""
    system = platform.system()
    
    if system == "Windows":
        return """
## Installing Ollama on Windows

**Option 1: Automatic (Recommended)**
1. Open PowerShell as Administrator
2. Run: `winget install Ollama.Ollama`
3. Restart your terminal

**Option 2: Manual Download**
1. Go to https://ollama.com/download
2. Download the Windows installer
3. Run the installer
4. Ollama will start automatically

After installation, Ollama runs in the background.
You can verify by opening a terminal and typing: `ollama list`
"""
    
    elif system == "Darwin":  # macOS
        return """
## Installing Ollama on macOS

**Option 1: Homebrew (Recommended)**
```
brew install ollama
```

**Option 2: Manual Download**
1. Go to https://ollama.com/download
2. Download the macOS app
3. Move Ollama.app to Applications
4. Open Ollama from Applications

Ollama runs as a menu bar app on macOS.
"""
    
    else:  # Linux
        return """
## Installing Ollama on Linux

**One-line install:**
```
curl -fsSL https://ollama.com/install.sh | sh
```

This installs Ollama and sets it up as a systemd service.

After installation, start the service:
```
sudo systemctl start ollama
```
"""


# =============================================================================
# HIGH-LEVEL INTERFACE
# =============================================================================

class LocalAIManager:
    """
    High-level interface for local AI in DocAnalyzer.
    
    This class provides a simple API for:
    - Checking system readiness
    - Managing models
    - Running inference
    - Handling errors gracefully
    """
    
    def __init__(self):
        self.ollama = OllamaManager()
        self._specs: Optional[SystemSpecs] = None
        self._current_model: Optional[str] = None
    
    @property
    def specs(self) -> SystemSpecs:
        """Get cached system specs (detects on first access)"""
        if self._specs is None:
            self._specs = detect_system_specs()
        return self._specs
    
    def refresh_specs(self) -> SystemSpecs:
        """Force refresh of system specs"""
        self._specs = detect_system_specs()
        return self._specs
    
    def check_readiness(self) -> Tuple[bool, str, Dict]:
        """
        Check if local AI is ready to use.
        
        Returns: (ready: bool, message: str, details: dict)
        """
        details = {
            "ollama_installed": False,
            "ollama_running": False,
            "models_available": False,
            "installed_models": [],
            "system_specs": None,
        }
        
        # Check Ollama installation
        installed, install_msg = self.ollama.is_installed()
        details["ollama_installed"] = installed
        
        if not installed:
            return False, (
                "Ollama is not installed.\n\n"
                "Ollama is a free, open-source tool that runs AI models locally.\n"
                "Click 'Install Ollama' to see installation instructions."
            ), details
        
        # Check if server is running
        running, run_msg = self.ollama.is_running()
        details["ollama_running"] = running
        
        if not running:
            return False, (
                "Ollama is installed but not running.\n\n"
                "Click 'Start Ollama' to start the server,\n"
                "or start it manually from your system tray/menu bar."
            ), details
        
        # Check for installed models
        success, msg, models = self.ollama.get_installed_models()
        details["installed_models"] = models
        details["models_available"] = len(models) > 0
        
        if not models:
            return False, (
                "Ollama is running but no models are installed.\n\n"
                "Click 'Download Model' to get started with a recommended model."
            ), details
        
        # Get system specs
        details["system_specs"] = self.specs.to_display_string()
        
        # All good!
        model_names = [m["name"] for m in models]
        return True, (
            f"✅ Local AI is ready!\n\n"
            f"Installed models: {', '.join(model_names)}\n\n"
            f"System: {self.specs.capability_level.value.title()} capability"
        ), details
    
    def get_available_models_for_dropdown(self) -> List[Tuple[str, str]]:
        """
        Get models for display in a dropdown.
        
        Returns: List of (display_name, model_id) tuples
        """
        success, _, installed = self.ollama.get_installed_models()
        
        if not success or not installed:
            return []
        
        results = []
        for model in installed:
            model_name = model["name"]
            
            # Try to get friendly name from our database
            if model_name in MODEL_DATABASE:
                display_name = MODEL_DATABASE[model_name].name
            else:
                # Use the model name directly
                display_name = model_name
            
            # Add size info
            size_gb = model["size"] / (1024 ** 3)
            display_name = f"{display_name} ({size_gb:.1f}GB)"
            
            results.append((display_name, model_name))
        
        return results
    
    def get_recommended_models_to_download(self) -> List[Tuple[ModelInfo, str]]:
        """Get list of recommended models to download based on system specs"""
        return get_compatible_models(self.specs)
    
    def pre_flight_check(self, document_text: str, model_id: str) -> Tuple[bool, str]:
        """
        Check if a document can be processed with the selected model.
        
        Returns: (ok: bool, message: str)
        """
        # Check Ollama is ready
        running, _ = self.ollama.is_running()
        if not running:
            return False, "Ollama server is not running. Please start it first."
        
        # Get model info
        if model_id in MODEL_DATABASE:
            model_info = MODEL_DATABASE[model_id]
        else:
            # Unknown model - assume 8K context
            model_info = ModelInfo(
                name=model_id,
                ollama_id=model_id,
                size_gb=0,
                ram_required_gb=0,
                vram_required_gb=0,
                context_window=8192,
                description="Unknown model",
                recommended_for="General use",
                quality_tier="unknown",
                is_fast=False,
                supports_vision=False
            )
        
        # Check document size
        fits, message, details = check_document_fits(document_text, model_info)
        
        if not fits:
            return False, message
        
        if details["utilization_percent"] > 90:
            return True, (
                f"⚠️ Warning: Document uses {details['utilization_percent']:.0f}% "
                f"of available context.\nResponse quality may be affected."
            )
        
        return True, "Ready to process"


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def quick_check() -> Tuple[bool, str]:
    """Quick check if local AI is ready to use"""
    manager = LocalAIManager()
    ready, message, _ = manager.check_readiness()
    return ready, message


def get_openai_compatible_url() -> str:
    """Get the OpenAI-compatible API URL for Ollama"""
    return OllamaManager.DEFAULT_URL + "/v1"


def get_optimal_chunk_size(model_id: str) -> Tuple[str, str]:
    """
    Determine the optimal chunk size setting for a given model.
    
    Args:
        model_id: Ollama model identifier (e.g., "llama3.2:3b")
        
    Returns:
        Tuple of (chunk_size_key, explanation)
        chunk_size_key is one of: "tiny", "small", "medium", "large"
    """
    # Get model info from database, or use conservative defaults for unknown models
    if model_id in MODEL_DATABASE:
        model_info = MODEL_DATABASE[model_id]
        context_window = model_info.context_window
    else:
        # Try to match partial model names (e.g., "llama3.2:3b-q4_0" matches "llama3.2:3b")
        context_window = 8192  # Conservative default
        for known_id, info in MODEL_DATABASE.items():
            # Check if the model_id starts with a known model
            if model_id.startswith(known_id.split(':')[0]):
                context_window = info.context_window
                break
    
    # Chunk size mapping based on context window
    # Reserve ~2500 tokens for prompt template and response
    # Chunk sizes from config.py:
    #   tiny: 6000 chars (~1,700 tokens)
    #   small: 12000 chars (~3,400 tokens)  
    #   medium: 24000 chars (~6,800 tokens)
    #   large: 52000 chars (~14,800 tokens)
    
    available_context = context_window - 2500
    
    if context_window >= 65536:  # 64K+ context (Llama 3.2, Qwen 2.5, etc.)
        return "large", f"Model has {context_window//1024}K context - using Large chunks for efficiency"
    elif context_window >= 32768:  # 32K context (Mistral, etc.)
        return "medium", f"Model has {context_window//1024}K context - using Medium chunks"
    elif context_window >= 8192:  # 8K context (Gemma, etc.)
        return "small", f"Model has {context_window//1024}K context - using Small chunks"
    else:  # <8K context (Phi-3 mini, older models)
        return "tiny", f"Model has limited {context_window//1024}K context - using Tiny chunks to ensure quality"


def get_model_context_window(model_id: str) -> int:
    """
    Get the context window size for a model.
    
    Args:
        model_id: Ollama model identifier
        
    Returns:
        Context window size in tokens
    """
    if model_id in MODEL_DATABASE:
        return MODEL_DATABASE[model_id].context_window
    
    # Try partial match
    for known_id, info in MODEL_DATABASE.items():
        if model_id.startswith(known_id.split(':')[0]):
            return info.context_window
    
    # Conservative default for unknown models
    return 8192


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Local AI Manager - System Check")
    print("=" * 60)
    
    # Detect system specs
    print("\n📊 Detecting system specifications...")
    specs = detect_system_specs()
    print(specs.to_display_string())
    
    # Check Ollama
    print("\n🔍 Checking Ollama...")
    manager = LocalAIManager()
    ready, message, details = manager.check_readiness()
    print(message)
    
    # Show compatible models
    print("\n📦 Compatible models for your system:")
    compatible = get_compatible_models(specs)
    for info, note in compatible[:5]:
        print(f"  • {info.name}: {note}")
    
    print("\n" + "=" * 60)
