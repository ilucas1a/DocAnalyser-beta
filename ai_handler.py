"""
ai_handler.py - AI Provider Management
Handles API calls to different AI providers (OpenAI, Anthropic, xAI, DeepSeek)
"""

import os
import datetime
from pathlib import Path
from typing import List, Dict, Tuple


def _log_cost(provider: str, model: str, cost: float, document_title: str = None, prompt_name: str = None):
    """
    Log API cost to cost_log.txt with document tracking

    Args:
        provider: Provider name
        model: Model name
        cost: Cost in dollars
        document_title: Optional document title being processed
        prompt_name: Optional prompt name used
    """
    try:
        # Get the directory where Main.py is located
        app_dir = Path(__file__).parent
        cost_log_path = app_dir / "cost_log.txt"

        # Create timestamp
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Format log entry with document info
        # Format: timestamp | provider | model | cost | document | prompt
        doc_info = document_title if document_title else "N/A"
        prompt_info = prompt_name if prompt_name else "N/A"

        log_entry = f"{timestamp} | {provider} | {model} | ${cost:.6f} | {doc_info} | {prompt_info}\n"

        # Append to log file
        with open(cost_log_path, 'a', encoding='utf-8') as f:
            f.write(log_entry)

    except Exception as e:
        print(f"⚠️ Cost logging failed: {e}")


def _calculate_openai_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Calculate cost for OpenAI models"""
    # Pricing per 1M tokens (as of 2024)
    pricing = {
        "gpt-4": {"input": 30.00, "output": 60.00},
        "gpt-4o": {"input": 2.50, "output": 10.00},
        "gpt-4o-mini": {"input": 0.150, "output": 0.600},
        "gpt-4-turbo": {"input": 10.00, "output": 30.00},
        "gpt-4-turbo-preview": {"input": 10.00, "output": 30.00},
        "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
        "gpt-3.5-turbo-16k": {"input": 3.00, "output": 4.00},
    }
    
    # Find matching model
    model_pricing = None
    for key in pricing:
        if key in model.lower():
            model_pricing = pricing[key]
            break
    
    if not model_pricing:
        # Default to gpt-4o-mini pricing if unknown
        model_pricing = pricing["gpt-4o-mini"]
    
    # Calculate cost
    input_cost = (prompt_tokens / 1_000_000) * model_pricing["input"]
    output_cost = (completion_tokens / 1_000_000) * model_pricing["output"]
    
    return input_cost + output_cost


def _calculate_anthropic_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate cost for Anthropic models"""
    # Pricing per 1M tokens (as of 2024)
    pricing = {
        "claude-3-opus": {"input": 15.00, "output": 75.00},
        "claude-3-sonnet": {"input": 3.00, "output": 15.00},
        "claude-3-haiku": {"input": 0.25, "output": 1.25},
        "claude-3-5-sonnet": {"input": 3.00, "output": 15.00},
    }
    
    # Find matching model
    model_pricing = None
    for key in pricing:
        if key in model.lower():
            model_pricing = pricing[key]
            break
    
    if not model_pricing:
        # Default to sonnet pricing if unknown
        model_pricing = pricing["claude-3-sonnet"]
    
    # Calculate cost
    input_cost = (input_tokens / 1_000_000) * model_pricing["input"]
    output_cost = (output_tokens / 1_000_000) * model_pricing["output"]
    
    return input_cost + output_cost


def _calculate_gemini_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate cost for Google Gemini models"""
    # Pricing per 1M tokens (as of 2024)
    pricing = {
        "gemini-1.5-pro": {"input": 1.25, "output": 5.00},
        "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
        "gemini-1.0-pro": {"input": 0.50, "output": 1.50},
    }
    
    # Find matching model
    model_pricing = None
    for key in pricing:
        if key in model.lower():
            model_pricing = pricing[key]
            break
    
    if not model_pricing:
        # Default to flash pricing if unknown
        model_pricing = pricing["gemini-1.5-flash"]
    
    # Calculate cost
    input_cost = (input_tokens / 1_000_000) * model_pricing["input"]
    output_cost = (output_tokens / 1_000_000) * model_pricing["output"]
    
    return input_cost + output_cost


def _calculate_xai_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Calculate cost for xAI Grok models"""
    # Pricing per 1M tokens (as of 2024)
    pricing = {
        "grok-beta": {"input": 5.00, "output": 15.00},
        "grok-2": {"input": 5.00, "output": 15.00},
    }
    
    # Find matching model
    model_pricing = None
    for key in pricing:
        if key in model.lower():
            model_pricing = pricing[key]
            break
    
    if not model_pricing:
        # Default to grok-beta pricing
        model_pricing = pricing["grok-beta"]
    
    # Calculate cost
    input_cost = (prompt_tokens / 1_000_000) * model_pricing["input"]
    output_cost = (completion_tokens / 1_000_000) * model_pricing["output"]
    
    return input_cost + output_cost


def _calculate_deepseek_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Calculate cost for DeepSeek models"""
    # Pricing per 1M tokens (as of 2024)
    pricing = {
        "deepseek-chat": {"input": 0.14, "output": 0.28},
        "deepseek-coder": {"input": 0.14, "output": 0.28},
    }
    
    # Find matching model
    model_pricing = None
    for key in pricing:
        if key in model.lower():
            model_pricing = pricing[key]
            break
    
    if not model_pricing:
        # Default to chat pricing
        model_pricing = pricing["deepseek-chat"]
    
    # Calculate cost
    input_cost = (prompt_tokens / 1_000_000) * model_pricing["input"]
    output_cost = (completion_tokens / 1_000_000) * model_pricing["output"]
    
    return input_cost + output_cost

def call_ai_provider(provider: str, model: str, messages: List[Dict], api_key: str,
                         document_title: str = None, prompt_name: str = None) -> tuple[bool, str]:
    """
    Call an AI provider with the given model and messages

    Args:
        provider: Provider name (e.g., "OpenAI (ChatGPT)", "Anthropic (Claude)", "Ollama (Local)")
        model: Model name (e.g., "gpt-4", "claude-3-opus-20240229")
        messages: List of message dictionaries with 'role' and 'content' keys
        api_key: API key for the provider (not required for Ollama)
        document_title: Optional document title for cost logging
        prompt_name: Optional prompt name for cost logging

    Returns:
        Tuple of (success: bool, response: str or error message)
    """
    try:
        if provider == "OpenAI (ChatGPT)":
            return _call_openai(model, messages, api_key, document_title, prompt_name)

        elif provider == "Anthropic (Claude)":
            return _call_anthropic(model, messages, api_key, document_title, prompt_name)

        elif provider == "Google (Gemini)":
            return _call_gemini(model, messages, api_key, document_title, prompt_name)

        elif provider == "xAI (Grok)":
            return _call_xai(model, messages, api_key, document_title, prompt_name)

        elif provider == "DeepSeek":
            return _call_deepseek(model, messages, api_key, document_title, prompt_name)

        elif provider == "Ollama (Local)":
            # Ollama uses local server, no API key needed
            return _call_ollama(model, messages, document_title, prompt_name)

        else:
            return False, f"Unknown provider: {provider}"

    except Exception as e:
        return False, f"{provider} error: {str(e)}"


def _call_openai(model: str, messages: List[Dict], api_key: str,
                 document_title: str = None, prompt_name: str = None) -> Tuple[bool, str]:
    """Call OpenAI API"""
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.7
        )

        # Extract usage and calculate cost
        usage = response.usage
        cost = _calculate_openai_cost(model, usage.prompt_tokens, usage.completion_tokens)

        # Log the cost with document info
        _log_cost("OpenAI", model, cost, document_title, prompt_name)

        return True, response.choices[0].message.content

    except ImportError:
        return False, "OpenAI library not installed. Install with: pip install openai"
    except Exception as e:
        return False, f"OpenAI error: {str(e)}"


def _call_anthropic(model: str, messages: List[Dict], api_key: str,
                    document_title: str = None, prompt_name: str = None) -> Tuple[bool, str]:
    """Call Anthropic Claude API"""
    try:
        from anthropic import Anthropic
    except ImportError:
        return False, "Anthropic library not installed. Install with: pip install anthropic"

    try:
        client = Anthropic(api_key=api_key)

        # Convert messages format - Anthropic requires system message separate
        system_message = ""
        converted_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_message = msg["content"]
            else:
                converted_messages.append(msg)

        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=system_message,
            messages=converted_messages,
            temperature=0.7
        )

        # Extract usage and calculate cost
        usage = response.usage
        cost = _calculate_anthropic_cost(model, usage.input_tokens, usage.output_tokens)

        # Log the cost with document info
        _log_cost("Anthropic", model, cost, document_title, prompt_name)

        return True, response.content[0].text

    except Exception as e:
        return False, f"Anthropic error: {str(e)}"


def _call_gemini(model: str, messages: List[Dict], api_key: str,
                 document_title: str = None, prompt_name: str = None) -> Tuple[bool, str]:
    """Call Google Gemini API"""
    try:
        import google.generativeai as genai
    except ImportError:
        return False, "Google Generative AI library not installed. Install with: pip install google-generativeai"

    try:
        genai.configure(api_key=api_key)

        # Convert messages format - Gemini uses a different format
        system_instruction = None
        user_message = ""

        # Combine all messages into a single prompt
        for msg in messages:
            if msg["role"] == "system":
                system_instruction = msg["content"]
            elif msg["role"] == "user":
                user_message += msg["content"] + "\n"
            elif msg["role"] == "assistant":
                user_message += "Assistant: " + msg["content"] + "\n"

        # Create the model
        if system_instruction:
            gemini_model = genai.GenerativeModel(
                model_name=model,
                system_instruction=system_instruction
            )
        else:
            gemini_model = genai.GenerativeModel(model_name=model)

        # Generate response
        response = gemini_model.generate_content(user_message.strip())

        # Try to get token counts if available
        try:
            input_tokens = response.usage_metadata.prompt_token_count
            output_tokens = response.usage_metadata.candidates_token_count
            cost = _calculate_gemini_cost(model, input_tokens, output_tokens)
            # Log the cost with document info
            _log_cost("Google Gemini", model, cost, document_title, prompt_name)
        except:
            # If token counts not available, log a nominal cost
            _log_cost("Google Gemini", model, 0.001, document_title, prompt_name)

        return True, response.text

    except Exception as e:
        return False, f"Google Gemini error: {str(e)}"


def _call_xai(model: str, messages: List[Dict], api_key: str,
              document_title: str = None, prompt_name: str = None) -> Tuple[bool, str]:
    """Call xAI Grok API (OpenAI-compatible)"""
    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=api_key,
            base_url="https://api.x.ai/v1"
        )
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.7
        )

        # Extract usage and calculate cost
        usage = response.usage
        cost = _calculate_xai_cost(model, usage.prompt_tokens, usage.completion_tokens)

        # Log the cost with document info
        _log_cost("xAI", model, cost, document_title, prompt_name)

        return True, response.choices[0].message.content

    except ImportError:
        return False, "OpenAI library not installed. Install with: pip install openai"
    except Exception as e:
        return False, f"xAI (Grok) error: {str(e)}"


def _call_deepseek(model: str, messages: List[Dict], api_key: str,
                   document_title: str = None, prompt_name: str = None) -> Tuple[bool, str]:
    """Call DeepSeek API (OpenAI-compatible)"""
    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com"
        )
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.7
        )

        # Extract usage and calculate cost
        usage = response.usage
        cost = _calculate_deepseek_cost(model, usage.prompt_tokens, usage.completion_tokens)

        # Log the cost with document info
        _log_cost("DeepSeek", model, cost, document_title, prompt_name)

        return True, response.choices[0].message.content

    except ImportError:
        return False, "OpenAI library not installed. Install with: pip install openai"
    except Exception as e:
        return False, f"DeepSeek error: {str(e)}"


# -------------------------
# Ollama Local AI Support
# -------------------------

OLLAMA_DEFAULT_URL = "http://localhost:11434"


def _call_ollama(model: str, messages: List[Dict],
                 document_title: str = None, prompt_name: str = None,
                 base_url: str = None) -> Tuple[bool, str]:
    """
    Call Ollama local server (OpenAI-compatible API)
    
    Ollama runs a local server that provides an OpenAI-compatible API.
    Default URL is http://localhost:11434/v1
    
    Args:
        model: Model identifier (e.g., "llama3.2:3b")
        messages: List of message dictionaries
        document_title: Optional document title for logging
        prompt_name: Optional prompt name for logging
        base_url: Ollama server URL (default: http://localhost:11434)
        
    Returns:
        Tuple of (success: bool, response: str or error message)
    """
    try:
        from openai import OpenAI
        import requests
        
        # Use default URL if not provided
        if not base_url:
            base_url = OLLAMA_DEFAULT_URL
        
        openai_url = f"{base_url}/v1"
        
        # First, check if Ollama server is running
        try:
            health_url = f"{base_url}/api/tags"
            health_check = requests.get(health_url, timeout=5)
            if health_check.status_code != 200:
                return False, (
                    "Ollama server not responding.\n\n"
                    "Please ensure:\n"
                    "1. Ollama is installed (https://ollama.com)\n"
                    "2. Ollama is running (check system tray)\n"
                    "3. A model is downloaded (e.g., 'ollama pull llama3.2')\n\n"
                    f"Tried URL: {base_url}"
                )
        except requests.exceptions.ConnectionError:
            return False, (
                "Cannot connect to Ollama server.\n\n"
                "Please ensure Ollama is running.\n"
                "If not installed, download from: https://ollama.com\n\n"
                "After installation, Ollama runs automatically in the background.\n"
                f"Expected URL: {base_url}"
            )
        except requests.exceptions.Timeout:
            return False, (
                "Ollama server connection timed out.\n\n"
                "The server may be busy loading a model.\n"
                "Please wait and try again."
            )
        
        # Ollama handles system messages well
        converted_messages = []
        for msg in messages:
            converted_messages.append(msg.copy())
        
        # Create OpenAI client pointing to Ollama
        client = OpenAI(
            api_key="ollama",  # Ollama doesn't require a real API key
            base_url=openai_url
        )
        
        # Make the API call
        try:
            response = client.chat.completions.create(
                model=model,
                messages=converted_messages,
                temperature=0.7
            )
        except Exception as api_error:
            error_str = str(api_error)
            if "404" in error_str or "not found" in error_str.lower():
                return False, (
                    f"Model '{model}' not found in Ollama.\n\n"
                    f"To download this model, run:\n"
                    f"  ollama pull {model}\n\n"
                    f"Or open DocAnalyzer Settings → Local AI Setup to download models."
                )
            elif "400" in error_str:
                return False, (
                    f"Ollama returned 400 Bad Request.\n\n"
                    f"Model: {model}\n"
                    f"This usually means:\n"
                    f"1. The document is too large for the model's context window\n"
                    f"2. The model name is incorrect\n\n"
                    f"Try a model with larger context (e.g., llama3.2 supports 128K tokens)."
                )
            raise  # Re-raise other errors
        
        # Log the usage (cost is $0 for local models)
        _log_cost("Ollama (Local)", model, 0.0, document_title, prompt_name)
        
        return True, response.choices[0].message.content
        
    except ImportError:
        return False, "OpenAI library not installed. Install with: pip install openai"
    except Exception as e:
        error_msg = str(e)
        
        # Provide helpful error messages for common issues
        if "Connection refused" in error_msg or "ConnectionError" in error_msg:
            return False, (
                "Ollama server is not running.\n\n"
                "To start Ollama:\n"
                "• Windows/Mac: Ollama runs automatically after installation\n"
                "• Check your system tray for the Ollama icon\n"
                "• Or run 'ollama serve' in a terminal\n\n"
                f"Expected URL: {OLLAMA_DEFAULT_URL}"
            )
        else:
            return False, f"Ollama error: {error_msg}"


def check_ollama_connection(base_url: str = None) -> Tuple[bool, str, List[str]]:
    """
    Check if Ollama server is running and get available models
    
    Args:
        base_url: Ollama server URL (default: http://localhost:11434)
        
    Returns:
        Tuple of (connected: bool, status_message: str, available_models: list)
    """
    import requests
    
    if not base_url:
        base_url = OLLAMA_DEFAULT_URL
    
    try:
        # Try to get models list from Ollama API
        models_url = f"{base_url}/api/tags"
        response = requests.get(models_url, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            models = [m.get('name', 'unknown') for m in data.get('models', [])]
            
            if models:
                return True, f"✅ Connected! {len(models)} model(s) available", models
            else:
                return True, "✅ Connected, but no models installed. Download one first.", []
        else:
            return False, f"Server returned status {response.status_code}", []
            
    except requests.exceptions.ConnectionError:
        return False, "❌ Cannot connect - is Ollama running?", []
    except requests.exceptions.Timeout:
        return False, "❌ Connection timed out", []
    except Exception as e:
        return False, f"❌ Error: {str(e)}", []


def get_ollama_models() -> List[str]:
    """
    Get list of models currently installed in Ollama.
    
    Returns:
        List of model names, or empty list if Ollama not running
    """
    connected, _, models = check_ollama_connection()
    return models if connected else []


def validate_api_key(provider: str, api_key: str) -> Tuple[bool, str]:
    """
    Validate an API key by making a minimal test call

    Args:
        provider: Provider name
        api_key: API key to validate

    Returns:
        Tuple of (valid: bool, message: str)
    """
    if not api_key or not api_key.strip():
        return False, "API key cannot be empty"

    # Simple test message
    test_messages = [
        {"role": "user", "content": "Hello"}
    ]

    # Try a minimal call
    success, response = call_ai_provider(provider, "", test_messages, api_key)

    if success:
        return True, "API key is valid"
    else:
        return False, f"API key validation failed: {response}"


def get_provider_base_url(provider: str) -> str:
    """
    Get the base URL for a provider (useful for debugging/logging)

    Args:
        provider: Provider name

    Returns:
        Base URL string or empty string if not applicable
    """
    urls = {
        "OpenAI (ChatGPT)": "https://api.openai.com/v1",
        "Anthropic (Claude)": "https://api.anthropic.com",
        "Google (Gemini)": "https://generativelanguage.googleapis.com",
        "xAI (Grok)": "https://api.x.ai/v1",
        "DeepSeek": "https://api.deepseek.com"
    }
    return urls.get(provider, "")


def format_conversation_for_provider(provider: str, conversation: List[Dict]) -> List[Dict]:
    """
    Format a conversation history for a specific provider's requirements

    Args:
        provider: Provider name
        conversation: List of conversation messages

    Returns:
        Formatted conversation list
    """
    # Most providers use the same format
    # Anthropic is handled internally in _call_anthropic
    return conversation


# -------------------------
# Vision AI for OCR
# -------------------------

# Image size limits by provider (in bytes)
PROVIDER_IMAGE_LIMITS = {
    "OpenAI (ChatGPT)": 20 * 1024 * 1024,  # 20 MB
    "Anthropic (Claude)": 5 * 1024 * 1024,  # 5 MB (strict)
    "Google (Gemini)": 20 * 1024 * 1024,    # 20 MB
    "xAI (Grok)": 20 * 1024 * 1024,         # 20 MB (assumed)
}

# Default max dimension for images (pixels on longest edge)
DEFAULT_MAX_DIMENSION = 2000  # Good balance of quality and size
OCR_MAX_DIMENSION = 3000  # Higher resolution for OCR - preserves small text


def _optimize_image_for_api(image_path: str, provider: str, 
                             max_dimension: int = None,
                             target_size_bytes: int = None,
                             log_callback=None) -> tuple:
    """
    Optimize an image for API upload - resize and compress if needed.
    
    Args:
        image_path: Path to the original image
        provider: AI provider name (determines size limits)
        max_dimension: Max pixels on longest edge (default: 2000)
        target_size_bytes: Target file size in bytes (default: provider limit)
        log_callback: Optional function to log progress messages
        
    Returns:
        Tuple of (optimized_image_bytes, media_type, was_resized, message)
    """
    from PIL import Image
    from io import BytesIO
    import os
    
    def log(msg):
        if log_callback:
            log_callback(msg)
        print(msg)
    
    # Get provider-specific limit
    if target_size_bytes is None:
        target_size_bytes = PROVIDER_IMAGE_LIMITS.get(provider, 5 * 1024 * 1024)
    
    if max_dimension is None:
        max_dimension = DEFAULT_MAX_DIMENSION
    
    # Determine media type from extension
    ext = os.path.splitext(image_path)[1].lower()
    media_type_map = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg', 
        '.png': 'image/png',
        '.gif': 'image/gif',
        '.webp': 'image/webp',
        '.bmp': 'image/bmp'
    }
    media_type = media_type_map.get(ext, 'image/jpeg')
    
    # Check original file size
    original_size = os.path.getsize(image_path)
    was_resized = False
    message = ""
    
    # Load image
    try:
        img = Image.open(image_path)
        original_dimensions = img.size
        
        # Convert to RGB if necessary (for JPEG output)
        if img.mode in ('RGBA', 'P', 'LA'):
            # Create white background for transparent images
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
            img = background
            media_type = 'image/jpeg'  # Switch to JPEG for converted images
        elif img.mode != 'RGB':
            img = img.convert('RGB')
            
    except Exception as e:
        # If PIL fails, return original file bytes
        with open(image_path, 'rb') as f:
            return f.read(), media_type, False, f"Could not optimize: {e}"
    
    # Check if resizing is needed (either too large in pixels or bytes)
    needs_resize = (
        original_size > target_size_bytes * 0.9 or  # File too large
        max(img.size) > max_dimension  # Dimensions too large
    )
    
    if not needs_resize:
        # Return original file
        with open(image_path, 'rb') as f:
            return f.read(), media_type, False, "Image within limits, no optimization needed"
    
    # Resize if dimensions exceed max
    if max(img.size) > max_dimension:
        # Calculate new dimensions maintaining aspect ratio
        ratio = max_dimension / max(img.size)
        new_size = (int(img.width * ratio), int(img.height * ratio))
        img = img.resize(new_size, Image.Resampling.LANCZOS)
        was_resized = True
        log(f"📐 Resized image from {original_dimensions[0]}x{original_dimensions[1]} to {new_size[0]}x{new_size[1]}")
    
    # Try different quality levels to get under target size
    quality_levels = [90, 85, 80, 70, 60, 50, 40]
    
    for quality in quality_levels:
        buffer = BytesIO()
        
        # Save as JPEG for best compression
        img.save(buffer, format='JPEG', quality=quality, optimize=True)
        compressed_size = buffer.tell()
        
        if compressed_size <= target_size_bytes:
            buffer.seek(0)
            compression_ratio = (1 - compressed_size / original_size) * 100
            message = f"Optimized: {original_size/1024/1024:.1f}MB → {compressed_size/1024/1024:.1f}MB ({compression_ratio:.0f}% reduction, quality={quality})"
            log(f"✅ {message}")
            return buffer.read(), 'image/jpeg', True, message
    
    # If still too large after max compression, resize further
    for scale in [0.75, 0.5, 0.35, 0.25]:
        new_size = (int(img.width * scale), int(img.height * scale))
        scaled_img = img.resize(new_size, Image.Resampling.LANCZOS)
        
        buffer = BytesIO()
        scaled_img.save(buffer, format='JPEG', quality=70, optimize=True)
        compressed_size = buffer.tell()
        
        if compressed_size <= target_size_bytes:
            buffer.seek(0)
            message = f"Optimized with scaling: {original_size/1024/1024:.1f}MB → {compressed_size/1024/1024:.1f}MB (scaled to {new_size[0]}x{new_size[1]})"
            log(f"✅ {message}")
            return buffer.read(), 'image/jpeg', True, message
    
    # Last resort - return whatever we have
    buffer = BytesIO()
    img.resize((int(img.width * 0.25), int(img.height * 0.25)), Image.Resampling.LANCZOS).save(
        buffer, format='JPEG', quality=50, optimize=True
    )
    buffer.seek(0)
    message = "Warning: Image heavily compressed to fit API limits"
    log(f"⚠️ {message}")
    return buffer.read(), 'image/jpeg', True, message


def check_provider_supports_vision(provider: str, model: str) -> bool:
    """
    Check if a provider/model combination supports vision (image analysis)
    
    Args:
        provider: Provider name
        model: Model name
        
    Returns:
        True if vision is supported
    """
    # Import here to avoid circular dependency
    try:
        from config import VISION_CAPABLE_PROVIDERS
    except ImportError:
        # Fallback if config not available
        # These are pattern prefixes - if the model contains any of these, it supports vision
        VISION_CAPABLE_PROVIDERS = {
            "OpenAI (ChatGPT)": ["gpt-4o", "gpt-4-turbo", "gpt-4.1", "gpt-4.5", "gpt-5", "o1", "o3", "o4"],
            "Anthropic (Claude)": ["claude"],  # All Claude models support vision (v3+)
            "Google (Gemini)": ["gemini"],
            "xAI (Grok)": ["grok-2-vision", "grok-vision"],
            # NOTE: DeepSeek does not support vision/image input
        }
    
    if provider not in VISION_CAPABLE_PROVIDERS:
        return False
    
    # Check if model matches any of the vision-capable patterns
    vision_patterns = VISION_CAPABLE_PROVIDERS[provider]
    model_lower = model.lower()
    
    for pattern in vision_patterns:
        if pattern.lower() in model_lower:
            return True
    
    return False


# -------------------------
# OCR Prompts for Different Text Types
# -------------------------

OCR_PROMPT_PRINTED = (
    "VERBATIM TRANSCRIPTION ONLY. "
    "Type out exactly what you see in the image, character by character. "
    "Do NOT correct spelling. Do NOT fix grammar. Do NOT paraphrase. "
    "Do NOT use strikethrough or suggest edits. "
    "Do NOT interpret or improve the text in any way. "
    "If a word looks like 'teh', type 'teh' not 'the'. "
    "Copy the text exactly as printed, even if it seems wrong. "
    "Use straight quotes (\" ') not curly quotes. "
    "Output only the raw text, nothing else."
)

OCR_PROMPT_HANDWRITING = (
    "Transcribe this handwritten document as accurately as possible. "
    "The handwriting may be difficult to read - use your best judgment. "
    "\n\nGuidelines:"
    "\n- Use context and common sense to interpret unclear words"
    "\n- If you're uncertain about a word, provide your best guess in [brackets]"
    "\n- Mark completely illegible words as [illegible]"
    "\n- Preserve paragraph structure and line breaks where visible"
    "\n- Focus on producing readable, coherent text"
    "\n- Consider what makes sense in context (e.g., names, dates, common phrases)"
    "\n\nOutput only the transcribed text with uncertainty markers where needed."
)


def build_ocr_prompt_with_context(text_type: str, context_hint: str = "") -> str:
    """
    Build an OCR prompt with optional user-provided context.
    
    For handwriting recognition, user context dramatically improves accuracy
    by anchoring the AI's interpretation.
    
    Args:
        text_type: "printed" or "handwriting"
        context_hint: User-provided context (e.g., "Letter from father to daughter, ~1975")
        
    Returns:
        Complete prompt string for the vision AI
    """
    if text_type == "printed":
        # Printed text doesn't benefit much from context
        return OCR_PROMPT_PRINTED
    
    # Handwriting mode - build contextual prompt
    if context_hint and context_hint.strip():
        # User provided context - incorporate it prominently
        prompt = (
            f"DOCUMENT CONTEXT: {context_hint.strip()}\n\n"
            "Transcribe this handwritten document as accurately as possible. "
            "The handwriting may be difficult to read - use your best judgment "
            "guided by the context provided above.\n\n"
            "Guidelines:\n"
            "- Use the document context to help interpret unclear words\n"
            "- Names, dates, and topics mentioned in the context are likely to appear\n"
            "- If you're uncertain about a word, provide your best guess in [brackets]\n"
            "- Mark completely illegible words as [illegible]\n"
            "- Preserve paragraph structure and line breaks where visible\n"
            "- Focus on producing readable, coherent text\n\n"
            "Output only the transcribed text with uncertainty markers where needed."
        )
    else:
        # No context provided - use generic handwriting prompt
        prompt = OCR_PROMPT_HANDWRITING
    
    return prompt


def call_vision_ai(provider: str, model: str, image_path: str, api_key: str,
                   prompt: str = None, document_title: str = None,
                   progress_callback=None, is_ocr: bool = True,
                   text_type: str = "printed") -> Tuple[bool, str]:
    """
    Call a vision-capable AI model to analyze/transcribe an image.
    Automatically optimizes large images to fit within provider limits.
    
    Args:
        provider: Provider name (e.g., "OpenAI (ChatGPT)")
        model: Model name (e.g., "gpt-4o")
        image_path: Path to image file
        api_key: API key for the provider
        prompt: Custom prompt (default: based on text_type)
        document_title: Optional document title for logging
        progress_callback: Optional callback for progress messages
        is_ocr: If True, uses higher quality settings for text extraction
        text_type: "printed" or "handwriting" - selects appropriate default prompt
        
    Returns:
        Tuple of (success: bool, transcribed_text: str or error message)
    """
    import base64
    
    def log(msg):
        if progress_callback:
            progress_callback(msg)
        print(msg)
    
    if not prompt:
        # Select prompt based on text type
        if text_type == "handwriting":
            prompt = OCR_PROMPT_HANDWRITING
            log("✍️ Using handwriting-optimized prompt (interpretive mode)")
        else:
            prompt = OCR_PROMPT_PRINTED
            log("📖 Using printed text prompt (verbatim mode)")
    
    # Use higher resolution for OCR to preserve small text
    max_dim = OCR_MAX_DIMENSION if is_ocr else DEFAULT_MAX_DIMENSION
    
    # Optimize image for API (resize/compress if needed)
    try:
        image_bytes, media_type, was_optimized, opt_message = _optimize_image_for_api(
            image_path, 
            provider,
            max_dimension=max_dim,
            log_callback=log
        )
        image_data = base64.b64encode(image_bytes).decode('utf-8')
        
        if was_optimized:
            log(f"📷 Image optimized for {provider}: {opt_message}")
        
    except Exception as e:
        return False, f"Failed to read/optimize image: {str(e)}"
    
    # Use higher token limit for OCR
    max_tokens = 8192 if is_ocr else 4096
    
    # Route to appropriate provider
    try:
        if provider == "OpenAI (ChatGPT)":
            return _call_openai_vision(model, image_data, media_type, prompt, api_key, document_title, max_tokens)
        
        elif provider == "Anthropic (Claude)":
            return _call_anthropic_vision(model, image_data, media_type, prompt, api_key, document_title, max_tokens)
        
        elif provider == "Google (Gemini)":
            return _call_gemini_vision(model, image_path, prompt, api_key, document_title, max_tokens)
        
        elif provider == "xAI (Grok)":
            return _call_xai_vision(model, image_data, media_type, prompt, api_key, document_title, max_tokens)
        
        else:
            return False, f"Provider '{provider}' does not support vision or is not configured for vision AI."
    
    except Exception as e:
        return False, f"Vision AI error: {str(e)}"


def _call_openai_vision(model: str, image_data: str, media_type: str, 
                         prompt: str, api_key: str, document_title: str = None,
                         max_tokens: int = 8192) -> Tuple[bool, str]:
    """Call OpenAI vision API"""
    try:
        from openai import OpenAI
        
        client = OpenAI(api_key=api_key)
        
        # Newer OpenAI models (gpt-5.x, o1, o3, o4) require max_completion_tokens
        # instead of the deprecated max_tokens parameter
        model_lower = model.lower()
        uses_new_param = any(x in model_lower for x in ['gpt-5', 'o1', 'o3', 'o4'])
        
        token_param = {}
        if uses_new_param:
            token_param['max_completion_tokens'] = max_tokens
        else:
            token_param['max_tokens'] = max_tokens
        
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{media_type};base64,{image_data}"
                            }
                        }
                    ]
                }
            ],
            **token_param,
            temperature=0  # Use temperature=0 for deterministic OCR output
        )
        
        # Log cost
        usage = response.usage
        cost = _calculate_openai_cost(model, usage.prompt_tokens, usage.completion_tokens)
        _log_cost("OpenAI Vision", model, cost, document_title, "OCR Transcription")
        
        return True, response.choices[0].message.content
        
    except Exception as e:
        return False, f"OpenAI Vision error: {str(e)}"


def _call_anthropic_vision(model: str, image_data: str, media_type: str,
                            prompt: str, api_key: str, document_title: str = None,
                            max_tokens: int = 8192) -> Tuple[bool, str]:
    """Call Anthropic Claude vision API"""
    try:
        from anthropic import Anthropic
        
        # Note: Image optimization is now handled by _optimize_image_for_api() in call_vision_ai()
        # before this function is called, so we don't need to resize here.
            
        client = Anthropic(api_key=api_key)
        
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=0,  # Use temperature=0 for deterministic OCR output
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_data
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }
            ]
        )
        
        # Log cost
        usage = response.usage
        cost = _calculate_anthropic_cost(model, usage.input_tokens, usage.output_tokens)
        _log_cost("Anthropic Vision", model, cost, document_title, "OCR Transcription")
        
        return True, response.content[0].text
        
    except Exception as e:
        return False, f"Anthropic Vision error: {str(e)}"


def _call_gemini_vision(model: str, image_path: str, prompt: str,
                         api_key: str, document_title: str = None,
                         max_tokens: int = 8192) -> Tuple[bool, str]:
    """Call Google Gemini vision API"""
    try:
        import google.generativeai as genai
        from PIL import Image
        
        genai.configure(api_key=api_key)
        
        # Load image
        image = Image.open(image_path)
        
        # Create model with generation config for max tokens and temperature=0 for OCR
        generation_config = genai.types.GenerationConfig(
            max_output_tokens=max_tokens,
            temperature=0  # Use temperature=0 for deterministic OCR output
        )
        gemini_model = genai.GenerativeModel(model_name=model, generation_config=generation_config)
        
        # Generate response with image
        response = gemini_model.generate_content([prompt, image])
        
        # Check if response was blocked or empty
        if not response.candidates:
            # Check for prompt feedback (safety blocking)
            if hasattr(response, 'prompt_feedback') and response.prompt_feedback:
                block_reason = getattr(response.prompt_feedback, 'block_reason', 'Unknown')
                return False, f"Gemini blocked the request. Reason: {block_reason}"
            return False, "Gemini returned no response candidates"
        
        # Check the first candidate
        candidate = response.candidates[0]
        
        # Check finish reason
        finish_reason = getattr(candidate, 'finish_reason', None)
        if finish_reason and str(finish_reason) not in ['STOP', 'FinishReason.STOP', '1']:
            return False, f"Gemini stopped early. Finish reason: {finish_reason}"
        
        # Try to get text from the response
        try:
            result_text = response.text
        except ValueError as e:
            # response.text raises ValueError if response was blocked
            if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                parts = candidate.content.parts
                if parts:
                    result_text = ''.join(p.text for p in parts if hasattr(p, 'text'))
                else:
                    return False, f"Gemini response has no text parts. Error: {str(e)}"
            else:
                return False, f"Cannot extract text from Gemini response: {str(e)}"
        
        if not result_text or not result_text.strip():
            return False, "Gemini returned empty text"
        
        # Try to get token counts for cost logging
        try:
            input_tokens = response.usage_metadata.prompt_token_count
            output_tokens = response.usage_metadata.candidates_token_count
            cost = _calculate_gemini_cost(model, input_tokens, output_tokens)
            _log_cost("Gemini Vision", model, cost, document_title, "OCR Transcription")
        except:
            _log_cost("Gemini Vision", model, 0.01, document_title, "OCR Transcription")
        
        return True, result_text
        
    except Exception as e:
        error_msg = str(e)
        # Provide more helpful error messages
        if "API_KEY" in error_msg.upper() or "401" in error_msg:
            return False, f"Gemini API key error: {error_msg}"
        elif "quota" in error_msg.lower() or "429" in error_msg:
            return False, f"Gemini rate limit/quota exceeded: {error_msg}"
        elif "not found" in error_msg.lower() or "404" in error_msg:
            return False, f"Gemini model '{model}' not found. Try a different model like 'gemini-1.5-flash'."
        else:
            return False, f"Gemini Vision error: {error_msg}"


def _call_xai_vision(model: str, image_data: str, media_type: str,
                      prompt: str, api_key: str, document_title: str = None,
                      max_tokens: int = 8192) -> Tuple[bool, str]:
    """Call xAI Grok vision API (OpenAI-compatible)"""
    try:
        from openai import OpenAI
        
        client = OpenAI(
            api_key=api_key,
            base_url="https://api.x.ai/v1"
        )
        
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{media_type};base64,{image_data}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=max_tokens,
            temperature=0  # Use temperature=0 for deterministic OCR output
        )
        
        # Log cost
        usage = response.usage
        cost = _calculate_xai_cost(model, usage.prompt_tokens, usage.completion_tokens)
        _log_cost("xAI Vision", model, cost, document_title, "OCR Transcription")
        
        return True, response.choices[0].message.content
        
    except Exception as e:
        return False, f"xAI Vision error: {str(e)}"


def get_provider_info(provider: str) -> Dict:
    """
    Get information about a provider

    Args:
        provider: Provider name

    Returns:
        Dictionary with provider information
    """
    info = {
        "OpenAI (ChatGPT)": {
            "name": "OpenAI",
            "models": ["gpt-4", "gpt-4-turbo", "gpt-3.5-turbo"],
            "api_docs": "https://platform.openai.com/docs/api-reference",
            "requires_library": "openai",
            "requires_api_key": True
        },
        "Anthropic (Claude)": {
            "name": "Anthropic",
            "models": ["claude-3-opus-20240229", "claude-3-sonnet-20240229", "claude-3-haiku-20240307"],
            "api_docs": "https://docs.anthropic.com/claude/reference",
            "requires_library": "anthropic",
            "requires_api_key": True
        },
        "Google (Gemini)": {
            "name": "Google",
            "models": ["gemini-1.5-pro-latest", "gemini-1.5-flash-latest"],
            "api_docs": "https://ai.google.dev/gemini-api/docs",
            "requires_library": "google-generativeai",
            "requires_api_key": True
        },
        "xAI (Grok)": {
            "name": "xAI",
            "models": ["grok-beta"],
            "api_docs": "https://docs.x.ai/",
            "requires_library": "openai",
            "requires_api_key": True
        },
        "DeepSeek": {
            "name": "DeepSeek",
            "models": ["deepseek-chat", "deepseek-coder"],
            "api_docs": "https://platform.deepseek.com/api-docs/",
            "requires_library": "openai",
            "requires_api_key": True
        },
        "Ollama (Local)": {
            "name": "Ollama",
            "models": ["(Models installed in Ollama)"],
            "api_docs": "https://ollama.com",
            "requires_library": "openai",
            "requires_api_key": False,
            "is_local": True,
            "default_url": "http://localhost:11434/v1"
        }
    }
    return info.get(provider, {"name": "Unknown", "models": [], "api_docs": "", "requires_library": "", "requires_api_key": True})


# -------------------------
# Direct PDF Processing (bypasses pdf2image/poppler)
# -------------------------

# Providers that support direct PDF input
PDF_CAPABLE_PROVIDERS = {
    "Anthropic (Claude)": True,   # Claude can process PDFs directly
    "Google (Gemini)": True,      # Gemini can process PDFs directly
    # OpenAI and others require images, not direct PDF
}

# PDF size limits by provider
PDF_SIZE_LIMITS = {
    "Anthropic (Claude)": 32 * 1024 * 1024,  # 32 MB
    "Google (Gemini)": 50 * 1024 * 1024,     # 50 MB (approximate)
}

PDF_PAGE_LIMITS = {
    "Anthropic (Claude)": 100,  # Max 100 pages
    "Google (Gemini)": 300,     # Approximate
}


def check_provider_supports_pdf(provider: str) -> bool:
    """Check if a provider can process PDF files directly."""
    return PDF_CAPABLE_PROVIDERS.get(provider, False)


def process_pdf_with_cloud_ai(
    pdf_path: str,
    provider: str,
    model: str,
    api_key: str,
    prompt: str = None,
    document_title: str = None,
    progress_callback=None
) -> Tuple[bool, str]:
    """
    Process a PDF file directly with Cloud AI (Claude or Gemini).
    
    This bypasses pdf2image/poppler entirely, sending the raw PDF to the AI.
    Useful for corrupt/elderly PDFs that crash local conversion tools.
    
    Args:
        pdf_path: Path to the PDF file
        provider: AI provider name
        model: Model name
        api_key: API key
        prompt: Custom prompt (default: transcribe all text)
        document_title: Optional title for logging
        progress_callback: Optional callback for progress messages
        
    Returns:
        Tuple of (success, extracted_text_or_error)
    """
    def log(msg):
        if progress_callback:
            progress_callback(msg)
        print(msg)
    
    # Check provider supports direct PDF
    if not check_provider_supports_pdf(provider):
        return False, (
            f"Provider '{provider}' does not support direct PDF processing.\n"
            f"Only Anthropic (Claude) and Google (Gemini) can process PDFs directly."
        )
    
    # Check file exists and size
    if not os.path.exists(pdf_path):
        return False, f"PDF file not found: {pdf_path}"
    
    file_size = os.path.getsize(pdf_path)
    max_size = PDF_SIZE_LIMITS.get(provider, 32 * 1024 * 1024)
    
    if file_size > max_size:
        return False, (
            f"PDF file too large for {provider}.\n"
            f"File size: {file_size / 1024 / 1024:.1f} MB\n"
            f"Maximum: {max_size / 1024 / 1024:.0f} MB"
        )
    
    # Default prompt for PDF transcription
    if not prompt:
        prompt = (
            "Please transcribe ALL text from this PDF document exactly as written. "
            "Preserve the structure, paragraphs, and formatting as much as possible. "
            "If the document contains handwritten text, transcribe it to the best of your ability. "
            "For each page, indicate the page number if there are multiple pages. "
            "If any text is unclear, indicate with [unclear]. "
            "Return only the transcribed text, no additional commentary."
        )
    
    log(f"📄 Sending PDF directly to {provider} for processing...")
    log(f"   File: {os.path.basename(pdf_path)} ({file_size / 1024 / 1024:.1f} MB)")
    
    try:
        if provider == "Anthropic (Claude)":
            return _process_pdf_with_claude(pdf_path, model, api_key, prompt, document_title, log)
        elif provider == "Google (Gemini)":
            return _process_pdf_with_gemini(pdf_path, model, api_key, prompt, document_title, log)
        else:
            return False, f"PDF processing not implemented for {provider}"
    except Exception as e:
        return False, f"PDF processing error: {str(e)}"


def _process_pdf_with_claude(
    pdf_path: str,
    model: str,
    api_key: str,
    prompt: str,
    document_title: str,
    log_func
) -> Tuple[bool, str]:
    """Process PDF directly with Claude API."""
    try:
        from anthropic import Anthropic
        import base64
        
        log_func("🤖 Using Claude direct PDF processing...")
        
        # Read PDF file
        with open(pdf_path, 'rb') as f:
            pdf_data = base64.standard_b64encode(f.read()).decode('utf-8')
        
        client = Anthropic(api_key=api_key)
        
        # Send PDF to Claude
        response = client.messages.create(
            model=model,
            max_tokens=8192,  # Higher limit for full document transcription
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": pdf_data
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }
            ]
        )
        
        # Log cost
        usage = response.usage
        cost = _calculate_anthropic_cost(model, usage.input_tokens, usage.output_tokens)
        _log_cost("Anthropic PDF", model, cost, document_title, "Direct PDF Processing")
        
        log_func(f"✅ Claude processed PDF successfully ({usage.input_tokens} input tokens)")
        
        return True, response.content[0].text
        
    except Exception as e:
        error_msg = str(e)
        if "document" in error_msg.lower() and "not supported" in error_msg.lower():
            return False, (
                "This Claude model doesn't support PDF documents.\n"
                "Try using claude-3-5-sonnet or claude-3-opus."
            )
        return False, f"Claude PDF error: {error_msg}"


def _process_pdf_with_gemini(
    pdf_path: str,
    model: str,
    api_key: str,
    prompt: str,
    document_title: str,
    log_func
) -> Tuple[bool, str]:
    """Process PDF directly with Gemini API."""
    try:
        import google.generativeai as genai
        
        log_func("🤖 Using Gemini direct PDF processing...")
        
        genai.configure(api_key=api_key)
        
        # Upload the PDF file to Gemini
        log_func("   Uploading PDF to Gemini...")
        uploaded_file = genai.upload_file(pdf_path)
        
        # Create model and generate
        gemini_model = genai.GenerativeModel(model_name=model)
        
        response = gemini_model.generate_content([prompt, uploaded_file])
        
        # Try to get token counts for cost logging
        try:
            input_tokens = response.usage_metadata.prompt_token_count
            output_tokens = response.usage_metadata.candidates_token_count
            cost = _calculate_gemini_cost(model, input_tokens, output_tokens)
            _log_cost("Gemini PDF", model, cost, document_title, "Direct PDF Processing")
            log_func(f"✅ Gemini processed PDF successfully ({input_tokens} input tokens)")
        except:
            _log_cost("Gemini PDF", model, 0.05, document_title, "Direct PDF Processing")
            log_func("✅ Gemini processed PDF successfully")
        
        # Clean up uploaded file
        try:
            uploaded_file.delete()
        except:
            pass  # Ignore cleanup errors
        
        return True, response.text
        
    except Exception as e:
        return False, f"Gemini PDF error: {str(e)}"


def extract_text_from_pdf_cloud_ai(
    pdf_path: str,
    provider: str,
    model: str,
    api_key: str,
    document_title: str = None,
    progress_callback=None
) -> List[Dict]:
    """
    Extract text from PDF using Cloud AI direct processing.
    
    This is the high-level function to use for scanned/corrupt PDFs.
    Returns entries in the same format as local OCR for compatibility.
    
    Args:
        pdf_path: Path to PDF file
        provider: AI provider name  
        model: Model name
        api_key: API key
        document_title: Optional document title
        progress_callback: Optional progress callback
        
    Returns:
        List of entry dicts with 'start', 'text', 'location' keys
    """
    def log(msg):
        if progress_callback:
            progress_callback(msg)
        print(msg)
    
    success, result = process_pdf_with_cloud_ai(
        pdf_path=pdf_path,
        provider=provider,
        model=model,
        api_key=api_key,
        document_title=document_title,
        progress_callback=progress_callback
    )
    
    if not success:
        raise RuntimeError(result)
    
    # Convert the text result to entries format
    # Split into paragraphs for the entries list
    entries = []
    paragraphs = [p.strip() for p in result.split('\n\n') if p.strip()]
    
    for i, para in enumerate(paragraphs):
        entries.append({
            'start': 1,  # Cloud AI doesn't give page numbers easily
            'text': para,
            'location': 'Cloud AI Transcription'
        })
    
    log(f"✅ Extracted {len(entries)} text segments from PDF via Cloud AI")
    
    return entries


# -------------------------
# Google Cloud Vision OCR (Dedicated OCR Service)
# -------------------------

def ocr_with_google_cloud_vision(
    image_path: str,
    api_key: str,
    document_title: str = None,
    progress_callback=None
) -> Tuple[bool, str]:
    """
    Perform OCR using Google Cloud Vision API - a dedicated OCR service.
    
    This is different from Gemini vision - Cloud Vision is purpose-built for
    accurate text extraction without interpretation or paraphrasing.
    
    Args:
        image_path: Path to image file
        api_key: Google Cloud API key (with Vision API enabled)
        document_title: Optional title for logging
        progress_callback: Optional callback for progress updates
        
    Returns:
        Tuple of (success, text_or_error)
    """
    import base64
    import requests
    import json
    
    def log(msg):
        if progress_callback:
            progress_callback(msg)
        print(msg)
    
    log("🔍 Using Google Cloud Vision API for OCR...")
    
    # Read and encode image
    try:
        with open(image_path, 'rb') as f:
            image_content = base64.b64encode(f.read()).decode('utf-8')
    except Exception as e:
        return False, f"Failed to read image: {str(e)}"
    
    # Prepare the API request
    # Using DOCUMENT_TEXT_DETECTION for best results on printed text
    url = f"https://vision.googleapis.com/v1/images:annotate?key={api_key}"
    
    payload = {
        "requests": [
            {
                "image": {
                    "content": image_content
                },
                "features": [
                    {
                        "type": "DOCUMENT_TEXT_DETECTION",
                        "maxResults": 1
                    }
                ],
                "imageContext": {
                    "languageHints": ["en"]  # Hint for English, but will detect others
                }
            }
        ]
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    try:
        log("📤 Sending image to Google Cloud Vision...")
        response = requests.post(url, json=payload, headers=headers, timeout=60)
        
        if response.status_code == 200:
            result = response.json()
            
            # Extract text from response
            if 'responses' in result and len(result['responses']) > 0:
                response_data = result['responses'][0]
                
                # Check for errors in the response
                if 'error' in response_data:
                    error_msg = response_data['error'].get('message', 'Unknown error')
                    return False, f"Vision API error: {error_msg}"
                
                # Get the full text annotation (best for documents)
                if 'fullTextAnnotation' in response_data:
                    text = response_data['fullTextAnnotation']['text']
                    log(f"✅ Cloud Vision OCR complete - extracted {len(text)} characters")
                    return True, text
                
                # Fallback to text annotations if no full text
                elif 'textAnnotations' in response_data and len(response_data['textAnnotations']) > 0:
                    # First annotation contains the entire text
                    text = response_data['textAnnotations'][0]['description']
                    log(f"✅ Cloud Vision OCR complete - extracted {len(text)} characters")
                    return True, text
                
                else:
                    return False, "No text detected in image"
            else:
                return False, "Empty response from Vision API"
        
        elif response.status_code == 400:
            error_data = response.json()
            error_msg = error_data.get('error', {}).get('message', 'Bad request')
            return False, f"Vision API error (400): {error_msg}"
        
        elif response.status_code == 403:
            error_data = response.json()
            error_msg = error_data.get('error', {}).get('message', 'Access denied')
            return False, (
                f"Vision API access denied: {error_msg}\n\n"
                "Make sure:\n"
                "1. Cloud Vision API is enabled in your Google Cloud project\n"
                "2. Your API key has access to the Vision API\n"
                "3. Billing is enabled on your project"
            )
        
        else:
            return False, f"Vision API HTTP error {response.status_code}: {response.text[:200]}"
    
    except requests.exceptions.Timeout:
        return False, "Vision API request timed out"
    except requests.exceptions.RequestException as e:
        return False, f"Network error: {str(e)}"
    except Exception as e:
        return False, f"Unexpected error: {str(e)}"
