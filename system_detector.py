"""
system_detector.py - Hardware Detection and Model Recommendations
Detects system capabilities and recommends appropriate local AI models
"""

import os
import platform
import subprocess
from typing import Dict, List, Tuple, Optional


def get_system_info() -> Dict:
    """
    Gather comprehensive system information for model recommendations.
    
    Returns:
        Dictionary containing system specs and capabilities
    """
    info = {
        "os": platform.system(),
        "os_version": platform.version(),
        "architecture": platform.machine(),
        "processor": platform.processor(),
        "cpu_cores": os.cpu_count(),
        "ram_total_gb": 0,
        "ram_available_gb": 0,
        "gpu_detected": False,
        "gpu_name": None,
        "gpu_vram_gb": None,
        "gpu_type": None,  # "nvidia", "amd", "intel", or None
    }
    
    # Get RAM information
    try:
        info["ram_total_gb"], info["ram_available_gb"] = _get_ram_info()
    except Exception as e:
        print(f"Warning: Could not detect RAM: {e}")
    
    # Get GPU information
    try:
        gpu_info = _get_gpu_info()
        info.update(gpu_info)
    except Exception as e:
        print(f"Warning: Could not detect GPU: {e}")
    
    return info


def _get_ram_info() -> Tuple[float, float]:
    """Get total and available RAM in GB"""
    
    if platform.system() == "Windows":
        try:
            import ctypes
            
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(stat)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            
            total_gb = stat.ullTotalPhys / (1024 ** 3)
            available_gb = stat.ullAvailPhys / (1024 ** 3)
            return round(total_gb, 1), round(available_gb, 1)
        except Exception:
            pass
    
    # Fallback: try psutil if available
    try:
        import psutil
        mem = psutil.virtual_memory()
        return round(mem.total / (1024 ** 3), 1), round(mem.available / (1024 ** 3), 1)
    except ImportError:
        pass
    
    return 0, 0


def _get_gpu_info() -> Dict:
    """Detect GPU type and VRAM"""
    
    gpu_info = {
        "gpu_detected": False,
        "gpu_name": None,
        "gpu_vram_gb": None,
        "gpu_type": None,
    }
    
    # Try NVIDIA first (most common for AI)
    nvidia_info = _detect_nvidia_gpu()
    if nvidia_info["detected"]:
        gpu_info["gpu_detected"] = True
        gpu_info["gpu_name"] = nvidia_info["name"]
        gpu_info["gpu_vram_gb"] = nvidia_info["vram_gb"]
        gpu_info["gpu_type"] = "nvidia"
        return gpu_info
    
    # Try Intel GPU
    intel_info = _detect_intel_gpu()
    if intel_info["detected"]:
        gpu_info["gpu_detected"] = True
        gpu_info["gpu_name"] = intel_info["name"]
        gpu_info["gpu_vram_gb"] = intel_info["vram_gb"]
        gpu_info["gpu_type"] = "intel"
        return gpu_info
    
    # Try AMD GPU
    amd_info = _detect_amd_gpu()
    if amd_info["detected"]:
        gpu_info["gpu_detected"] = True
        gpu_info["gpu_name"] = amd_info["name"]
        gpu_info["gpu_vram_gb"] = amd_info["vram_gb"]
        gpu_info["gpu_type"] = "amd"
        return gpu_info
    
    # Fallback: Try Windows WMI
    if platform.system() == "Windows":
        wmi_info = _detect_gpu_windows_wmi()
        if wmi_info["detected"]:
            gpu_info.update(wmi_info)
    
    return gpu_info


def _detect_nvidia_gpu() -> Dict:
    """Detect NVIDIA GPU using nvidia-smi"""
    result = {"detected": False, "name": None, "vram_gb": None}
    
    try:
        output = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            stderr=subprocess.DEVNULL,
            timeout=5
        ).decode("utf-8").strip()
        
        if output:
            parts = output.split(",")
            if len(parts) >= 2:
                result["detected"] = True
                result["name"] = parts[0].strip()
                # VRAM is in MB from nvidia-smi
                vram_mb = float(parts[1].strip())
                result["vram_gb"] = round(vram_mb / 1024, 1)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        pass
    
    return result


def _detect_intel_gpu() -> Dict:
    """Detect Intel GPU (Arc, Iris, UHD)"""
    result = {"detected": False, "name": None, "vram_gb": None}
    
    if platform.system() == "Windows":
        try:
            # Use PowerShell to query GPU info
            cmd = 'powershell "Get-WmiObject Win32_VideoController | Where-Object {$_.Name -like \'*Intel*\'} | Select-Object Name, AdapterRAM | ConvertTo-Json"'
            output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL, timeout=10).decode("utf-8").strip()
            
            if output and "Intel" in output:
                import json
                data = json.loads(output)
                
                # Handle single result vs array
                if isinstance(data, list):
                    data = data[0] if data else {}
                
                if data.get("Name"):
                    result["detected"] = True
                    result["name"] = data["Name"]
                    
                    # AdapterRAM is in bytes
                    adapter_ram = data.get("AdapterRAM", 0)
                    if adapter_ram:
                        result["vram_gb"] = round(adapter_ram / (1024 ** 3), 1)
                    
                    # Intel Arc GPUs - estimate VRAM from name if not detected
                    if result["vram_gb"] == 0 or result["vram_gb"] is None:
                        name_lower = result["name"].lower()
                        if "a770" in name_lower:
                            result["vram_gb"] = 16.0
                        elif "a750" in name_lower:
                            result["vram_gb"] = 8.0
                        elif "a580" in name_lower:
                            result["vram_gb"] = 8.0
                        elif "a380" in name_lower:
                            result["vram_gb"] = 6.0
                        elif "a310" in name_lower:
                            result["vram_gb"] = 4.0
                        elif "arc" in name_lower:
                            result["vram_gb"] = 8.0  # Default estimate for Arc
        except Exception:
            pass
    
    return result


def _detect_amd_gpu() -> Dict:
    """Detect AMD GPU"""
    result = {"detected": False, "name": None, "vram_gb": None}
    
    if platform.system() == "Windows":
        try:
            cmd = 'powershell "Get-WmiObject Win32_VideoController | Where-Object {$_.Name -like \'*AMD*\' -or $_.Name -like \'*Radeon*\'} | Select-Object Name, AdapterRAM | ConvertTo-Json"'
            output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL, timeout=10).decode("utf-8").strip()
            
            if output and ("AMD" in output or "Radeon" in output):
                import json
                data = json.loads(output)
                
                if isinstance(data, list):
                    data = data[0] if data else {}
                
                if data.get("Name"):
                    result["detected"] = True
                    result["name"] = data["Name"]
                    
                    adapter_ram = data.get("AdapterRAM", 0)
                    if adapter_ram:
                        result["vram_gb"] = round(adapter_ram / (1024 ** 3), 1)
        except Exception:
            pass
    
    return result


def _detect_gpu_windows_wmi() -> Dict:
    """Fallback GPU detection using Windows WMI"""
    result = {"detected": False, "name": None, "vram_gb": None, "gpu_type": None}
    
    try:
        cmd = 'powershell "Get-WmiObject Win32_VideoController | Select-Object Name, AdapterRAM | ConvertTo-Json"'
        output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL, timeout=10).decode("utf-8").strip()
        
        if output:
            import json
            data = json.loads(output)
            
            if isinstance(data, list):
                # Find the best GPU (highest VRAM, skip basic display adapters)
                best_gpu = None
                best_vram = 0
                for gpu in data:
                    name = gpu.get("Name", "").lower()
                    vram = gpu.get("AdapterRAM", 0)
                    
                    # Skip basic display adapters
                    if "basic" in name or "microsoft" in name:
                        continue
                    
                    if vram > best_vram:
                        best_vram = vram
                        best_gpu = gpu
                
                if best_gpu:
                    data = best_gpu
            
            if data and data.get("Name"):
                result["detected"] = True
                result["name"] = data["Name"]
                
                adapter_ram = data.get("AdapterRAM", 0)
                if adapter_ram:
                    result["vram_gb"] = round(adapter_ram / (1024 ** 3), 1)
                
                # Determine GPU type from name
                name_lower = data["Name"].lower()
                if "nvidia" in name_lower or "geforce" in name_lower or "quadro" in name_lower:
                    result["gpu_type"] = "nvidia"
                elif "amd" in name_lower or "radeon" in name_lower:
                    result["gpu_type"] = "amd"
                elif "intel" in name_lower:
                    result["gpu_type"] = "intel"
    except Exception:
        pass
    
    return result


def get_system_profile(system_info: Dict = None) -> str:
    """
    Categorize system into a profile based on capabilities.
    
    Returns:
        Profile name: "basic", "standard", "good", or "powerful"
    """
    if system_info is None:
        system_info = get_system_info()
    
    ram = system_info.get("ram_total_gb", 0)
    vram = system_info.get("gpu_vram_gb", 0) or 0
    has_gpu = system_info.get("gpu_detected", False)
    
    # Powerful: 32GB+ RAM with 16GB+ VRAM
    if ram >= 32 and vram >= 16:
        return "powerful"
    
    # Good: 16-32GB RAM with 8GB+ VRAM, or 32GB+ RAM with any GPU
    if (ram >= 16 and vram >= 8) or (ram >= 32 and has_gpu):
        return "good"
    
    # Standard: 16GB+ RAM, or 8GB+ RAM with decent GPU
    if ram >= 16 or (ram >= 8 and vram >= 4):
        return "standard"
    
    # Basic: Everything else
    return "basic"


def get_model_recommendations(system_info: Dict = None) -> Dict:
    """
    Get model recommendations based on system capabilities.
    
    Returns:
        Dictionary with profile, recommended models, and explanations
    """
    if system_info is None:
        system_info = get_system_info()
    
    profile = get_system_profile(system_info)
    
    recommendations = {
        "basic": {
            "profile_name": "Basic",
            "profile_description": "Limited hardware - smaller models only, reduced quality for complex tasks",
            "primary_models": [
                {
                    "name": "Phi-3 Mini (3.8B)",
                    "search_term": "phi-3-mini",
                    "size_gb": 2.3,
                    "description": "Best option for limited hardware, but expect reduced quality",
                    "best_for": "Short summaries, simple Q&A, basic text tasks",
                    "limitation": "May struggle with long documents - review outputs carefully"
                },
                {
                    "name": "Gemma 2B",
                    "search_term": "gemma-2b",
                    "size_gb": 1.5,
                    "description": "Very lightweight, basic capabilities only",
                    "best_for": "Simple questions, short text cleanup",
                    "limitation": "NOT recommended for long document analysis"
                },
            ],
            "alternative_models": [
                {
                    "name": "TinyLlama 1.1B",
                    "search_term": "tinyllama",
                    "size_gb": 0.6,
                    "description": "Smallest option - very limited capabilities",
                    "best_for": "Last resort when nothing else fits"
                },
            ],
            "warning": (
                "⚠️ IMPORTANT: Models under 7B parameters cannot reliably summarize long documents "
                "(e.g., 1-2 hour interview transcripts). For important analysis work, consider using "
                "cloud APIs (OpenAI, Claude, Gemini) which work on any hardware."
            ),
            "document_quality": "Poor to Marginal",
            "tip": "For serious document analysis, 7B+ models are recommended. Consider cloud APIs if local hardware is limited."
        },
        
        "standard": {
            "profile_name": "Standard",
            "profile_description": "Good hardware - can run recommended 7B models with reliable quality",
            "primary_models": [
                {
                    "name": "Mistral 7B Instruct",
                    "search_term": "mistral-7b-instruct",
                    "size_gb": 4.1,
                    "description": "RECOMMENDED - Excellent quality-to-size ratio, reliable results",
                    "best_for": "Document summaries, analysis, long transcripts, Q&A",
                    "limitation": None
                },
                {
                    "name": "Llama 3.2 8B",
                    "search_term": "llama-3.2-8b",
                    "size_gb": 4.9,
                    "description": "Meta's latest - very capable and well-rounded",
                    "best_for": "Complex analysis, reasoning, long documents",
                    "limitation": None
                },
            ],
            "alternative_models": [
                {
                    "name": "Phi-3 Mini (3.8B)",
                    "search_term": "phi-3-mini",
                    "size_gb": 2.3,
                    "description": "Lighter option if 7B feels slow",
                    "best_for": "When speed is priority over quality"
                },
                {
                    "name": "Qwen2 7B",
                    "search_term": "qwen2-7b",
                    "size_gb": 4.4,
                    "description": "Strong multilingual support",
                    "best_for": "Non-English content"
                },
            ],
            "document_quality": "Good - Reliable for long documents",
            "tip": "7B models are the sweet spot for document analysis. Mistral 7B or Llama 3 8B are excellent choices."
        },
        
        "good": {
            "profile_name": "Good",
            "profile_description": "Strong hardware - can handle larger models with GPU acceleration",
            "primary_models": [
                {
                    "name": "Llama 3.2 8B",
                    "search_term": "llama-3.2-8b",
                    "size_gb": 4.9,
                    "description": "Excellent quality with fast GPU-accelerated processing",
                    "best_for": "Complex analysis, reasoning, any document task",
                    "limitation": None
                },
                {
                    "name": "Mistral Nemo 12B",
                    "search_term": "mistral-nemo",
                    "size_gb": 7.1,
                    "description": "Larger context window, more detailed and nuanced output",
                    "best_for": "Very long documents, detailed analysis",
                    "limitation": None
                },
            ],
            "alternative_models": [
                {
                    "name": "CodeLlama 13B",
                    "search_term": "codellama-13b",
                    "size_gb": 7.4,
                    "description": "Specialized for code understanding",
                    "best_for": "Technical documents, code"
                },
                {
                    "name": "Llama 3.1 8B",
                    "search_term": "llama-3.1-8b",
                    "size_gb": 4.7,
                    "description": "Previous generation, very stable",
                    "best_for": "Proven reliability"
                },
            ],
            "document_quality": "Very Good - Handles any document reliably",
            "tip": "Your system can handle 8-13B models comfortably. GPU acceleration makes processing fast."
        },
        
        "powerful": {
            "profile_name": "Powerful",
            "profile_description": "High-end hardware - can run the largest, most capable models",
            "primary_models": [
                {
                    "name": "Llama 3.1 70B (Q4)",
                    "search_term": "llama-3.1-70b-q4",
                    "size_gb": 40,
                    "description": "Near GPT-4 quality - the best local AI experience",
                    "best_for": "Everything - best possible local quality",
                    "limitation": None
                },
                {
                    "name": "Mixtral 8x7B",
                    "search_term": "mixtral-8x7b",
                    "size_gb": 26,
                    "description": "Mixture of experts - excellent all-around performance",
                    "best_for": "Complex reasoning, diverse tasks",
                    "limitation": None
                },
            ],
            "alternative_models": [
                {
                    "name": "Qwen2 72B (Q4)",
                    "search_term": "qwen2-72b-q4",
                    "size_gb": 41,
                    "description": "Strong multilingual, competitive with GPT-4",
                    "best_for": "Multilingual, complex analysis"
                },
                {
                    "name": "DeepSeek Coder 33B",
                    "search_term": "deepseek-coder-33b",
                    "size_gb": 19,
                    "description": "Excellent for technical content",
                    "best_for": "Code, technical documents"
                },
            ],
            "document_quality": "Excellent - Premium quality for any task",
            "tip": "Your powerful system can run the largest models for the best possible local AI experience."
        }
    }
    
    result = recommendations.get(profile, recommendations["basic"])
    result["profile"] = profile
    result["system_info"] = system_info
    
    return result


def format_system_report(system_info: Dict = None) -> str:
    """
    Generate a human-readable system report.
    
    Returns:
        Formatted string with system specs and recommendations
    """
    if system_info is None:
        system_info = get_system_info()
    
    recommendations = get_model_recommendations(system_info)
    profile = recommendations["profile"]
    
    lines = [
        "=" * 60,
        "SYSTEM ANALYSIS FOR LOCAL AI - DOCUMENT ANALYSIS",
        "=" * 60,
        "",
        "DETECTED HARDWARE:",
        f"  • Operating System: {system_info['os']} ({system_info['architecture']})",
        f"  • CPU: {system_info['processor'] or 'Unknown'}",
        f"  • CPU Cores: {system_info['cpu_cores']}",
        f"  • Total RAM: {system_info['ram_total_gb']} GB",
        f"  • Available RAM: {system_info['ram_available_gb']} GB",
    ]
    
    if system_info['gpu_detected']:
        lines.extend([
            f"  • GPU: {system_info['gpu_name']}",
            f"  • GPU VRAM: {system_info['gpu_vram_gb']} GB",
            f"  • GPU Type: {system_info['gpu_type'].upper() if system_info['gpu_type'] else 'Unknown'}",
        ])
    else:
        lines.append("  • GPU: None detected (will use CPU)")
    
    lines.extend([
        "",
        "-" * 60,
        f"SYSTEM PROFILE: {recommendations['profile_name'].upper()}",
        f"{recommendations['profile_description']}",
        "",
        f"DOCUMENT ANALYSIS QUALITY: {recommendations.get('document_quality', 'N/A')}",
        "-" * 60,
        "",
        "RECOMMENDED MODELS:",
    ])
    
    for i, model in enumerate(recommendations["primary_models"], 1):
        lines.extend([
            f"",
            f"  {i}. {model['name']}",
            f"     Size: ~{model['size_gb']} GB",
            f"     {model['description']}",
            f"     Best for: {model['best_for']}",
        ])
        if model.get('limitation'):
            lines.append(f"     ⚠️  Limitation: {model['limitation']}")
        lines.append(f"     Search in LM Studio: \"{model['search_term']}\"")
    
    lines.extend([
        "",
        "ALTERNATIVE OPTIONS:",
    ])
    
    for model in recommendations["alternative_models"]:
        lines.append(f"  • {model['name']} ({model['size_gb']} GB) - {model['best_for']}")
    
    lines.extend([
        "",
        "-" * 60,
    ])
    
    if "warning" in recommendations:
        lines.append(f"")
        lines.append(f"{recommendations['warning']}")
        lines.append(f"")
    
    if "tip" in recommendations:
        lines.append(f"💡 {recommendations['tip']}")
    
    lines.extend([
        "",
        "-" * 60,
        "KEY INFORMATION FOR DOCUMENT ANALYSIS:",
        "-" * 60,
        "",
        "• For summarizing long documents (1-2 hour interviews, reports):",
        "  MINIMUM RECOMMENDED: Mistral 7B or Llama 3 8B (requires 16GB RAM)",
        "",
        "• Models under 7B parameters (TinyLlama, Gemma 2B, Phi-3 Mini):",
        "  - May miss key points in long documents",
        "  - Can produce inconsistent or incomplete summaries",
        "  - Best used for short texts or simple tasks only",
        "",
        "• If your hardware is limited, consider:",
        "  - Using cloud APIs (OpenAI, Claude, Gemini) for important work",
        "  - They work on any hardware and produce reliable results",
        "",
        "=" * 60,
    ])
    
    return "\n".join(lines)


# Quick test when run directly
if __name__ == "__main__":
    print("Detecting system capabilities...")
    print()
    print(format_system_report())
