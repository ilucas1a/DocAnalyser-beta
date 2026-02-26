"""
Model Updater Module
Fetches current model lists from AI provider APIs and uses AI curation
to select the best models for document analysis.

Updated: February 2026
- AI-powered model curation for intelligent selection
- Ensures vision models are always available for OCR/handwriting
- Limits to 5 models per provider for cleaner UX
- Automatic staleness prevention (AI sees current models)
- Debug logging for troubleshooting
"""

import json
import logging
import requests
from typing import Dict, List, Tuple, Optional, Callable

# =============================================================================
# LOGGING SETUP
# =============================================================================

# Create logger for this module
logger = logging.getLogger("model_updater")
logger.setLevel(logging.DEBUG)

# Console handler - will show in PyCharm/terminal
if not logger.handlers:
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S')
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)


# =============================================================================
# CONFIGURATION
# =============================================================================

# Maximum models to show per provider (after AI curation)
MAX_MODELS_PER_PROVIDER = 5

# Minimal safe fallback models (used when AI curation fails and no API works)
# These are long-standing stable models unlikely to be deprecated soon
SAFE_FALLBACK_MODELS = {
    "OpenAI (ChatGPT)": [
        "gpt-4o",           # Vision ✓ - recommended
        "gpt-4o-mini",      # Vision ✓ - fast/cheap
        "gpt-4-turbo",      # Vision ✓
        "gpt-4",
        "gpt-3.5-turbo"
    ],
    "Anthropic (Claude)": [
        "claude-opus-4-6",              # Vision ✓ - most capable (Feb 2026)
        "claude-opus-4-5-20251101",     # Vision ✓
        "claude-sonnet-4-5-20250929",   # Vision ✓
        "claude-3-5-sonnet-20241022",   # Vision ✓
        "claude-3-5-haiku-20241022"     # Vision ✓ - fast/cheap
    ],
    "Google (Gemini)": [
        "gemini-2.5-flash",         # Vision ✓ - best free tier option
        "gemini-2.5-pro",           # Vision ✓ - requires billing
        "gemini-2.5-flash-lite",    # Vision ✓ - lightweight
        "gemini-2.5-flash-image",   # Vision ✓ - image generation
        "gemini-2.0-flash"          # Vision ✓ - legacy
    ],
    "xAI (Grok)": [
        "grok-3",               # Latest Grok
        "grok-2-vision-1212",   # Vision ✓
        "grok-2-latest",
        "grok-vision-beta",     # Vision ✓
        "grok-beta"
    ],
    "DeepSeek": [
        "deepseek-chat",
        "deepseek-reasoner"
    ]
}

# AI Curation prompt template
CURATION_PROMPT = """You are helping configure a document analysis application called DocAnalyser.

DocAnalyser is used for:
- Analyzing documents (PDF, Word, text files)
- Transcribing audio/video content
- OCR of scanned documents and handwritten text (requires vision capability)
- Summarizing and extracting information from documents
- Having conversations about document content

From the following list of {provider} models, select exactly {max_models} models that would be best for these document analysis tasks.

REQUIREMENTS:
1. MUST include at least one vision-capable model (essential for OCR and handwriting recognition)
   - For OpenAI: gpt-4o and gpt-4o-mini have vision capability
   - For Anthropic: All Claude 3+ models have vision capability
   - For Gemini: All Gemini 1.5+ and 2.0+ models have vision capability
2. PRIORITIZE NEWEST MODELS - prefer higher version numbers (e.g., gpt-5.2 > gpt-5 > gpt-4o > gpt-4)
3. Include variety: most capable (newest/largest), balanced, and fast/economical (mini/nano variants)
4. Prefer base models over dated versions (e.g., "gpt-5" over "gpt-5-2025-08-07")
5. Avoid preview/experimental versions unless no stable alternative exists
6. Only select models that EXACTLY match names in the provided list

AVAILABLE MODELS:
{model_list}

RESPOND WITH ONLY a JSON array of exactly {max_models} model names, ordered from most recommended to least.
No explanation, no markdown, just the JSON array.
Example format: ["model-name-1", "model-name-2", "model-name-3", "model-name-4", "model-name-5"]"""


# =============================================================================
# RAW MODEL FETCHING (from provider APIs)
# =============================================================================

def fetch_anthropic_models_raw(api_key: str) -> Tuple[bool, List[str], str]:
    """
    Fetch available Claude models from Anthropic API by testing known models.
    
    Returns:
        (success, models_list, error_message)
    """
    logger.info("=" * 60)
    logger.info("ANTHROPIC: Starting raw model fetch")
    try:
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        
        # Comprehensive list of known model names to test
        # This list should be periodically updated, but AI curation
        # will handle prioritization even if some models are missing
        models_to_test = [
            # Claude 4.6
            "claude-opus-4-6",
            # Claude 4.5 family
            "claude-opus-4-5-20251101",
            "claude-sonnet-4-5-20250929",
            "claude-haiku-4-5-20251001",
            # Claude 4 family
            "claude-sonnet-4-20250514",
            # Claude 3.5 family
            "claude-3-5-sonnet-20241022",
            "claude-3-5-sonnet-20240620",
            "claude-3-5-haiku-20241022",
            # Claude 3 family
            "claude-3-opus-20240229",
            "claude-3-sonnet-20240229",
            "claude-3-haiku-20240307",
        ]
        
        logger.info(f"ANTHROPIC: Testing {len(models_to_test)} known models...")
        working_models = []
        
        for model in models_to_test:
            data = {
                "model": model,
                "max_tokens": 5,
                "messages": [{"role": "user", "content": "test"}]
            }
            
            try:
                response = requests.post(url, headers=headers, json=data, timeout=5)
                if response.status_code == 200:
                    working_models.append(model)
                    logger.debug(f"  ✓ {model} - AVAILABLE")
                else:
                    logger.debug(f"  ✗ {model} - Status {response.status_code}")
            except Exception as e:
                logger.debug(f"  ✗ {model} - Error: {e}")
        
        if working_models:
            logger.info(f"ANTHROPIC: Raw fetch complete - {len(working_models)} models available:")
            for m in working_models:
                logger.info(f"  • {m}")
            return True, working_models, ""
        else:
            logger.warning("ANTHROPIC: No working models found!")
            return False, [], "No working models found. Check your API key."
            
    except Exception as e:
        logger.error(f"ANTHROPIC: Fetch failed - {e}")
        return False, [], f"Error: {str(e)}"


def fetch_openai_models_raw(api_key: str) -> Tuple[bool, List[str], str]:
    """
    Fetch all available OpenAI chat models.
    
    Returns:
        (success, models_list, error_message)
    """
    logger.info("=" * 60)
    logger.info("OPENAI: Starting raw model fetch")
    try:
        from openai import OpenAI
        
        client = OpenAI(api_key=api_key)
        response = client.models.list()

        # Filter to chat-capable models
        valid_prefixes = ('gpt-4', 'gpt-3.5', 'gpt-5', 'o1', 'o3', 'o4')
        
        exclude_patterns = [
            'tts', 'whisper', 'dall-e', 'embedding', 
            'audio', 'realtime', 'transcribe', 'search'
        ]
        
        # Log ALL models returned by API
        all_models = [m.id for m in response.data]
        logger.info(f"OPENAI: API returned {len(all_models)} total models")
        logger.debug("OPENAI: All models from API:")
        for m in sorted(all_models):
            logger.debug(f"  - {m}")
        
        chat_models = []
        excluded_models = []
        for model in response.data:
            model_id = model.id
            
            if not any(model_id.startswith(p) for p in valid_prefixes):
                continue
                
            if any(exclude in model_id for exclude in exclude_patterns):
                excluded_models.append(model_id)
                continue
                
            chat_models.append(model_id)
        
        # Sort alphabetically for consistent presentation to AI
        chat_models.sort()
        
        logger.info(f"OPENAI: After filtering - {len(chat_models)} chat models:")
        for m in chat_models:
            logger.info(f"  • {m}")
        
        if excluded_models:
            logger.debug(f"OPENAI: Excluded {len(excluded_models)} non-chat models:")
            for m in excluded_models:
                logger.debug(f"  ✗ {m}")
        
        return True, chat_models, ""
        
    except ImportError:
        logger.error("OPENAI: OpenAI library not installed")
        return False, [], "OpenAI library not installed"
    except Exception as e:
        logger.error(f"OPENAI: Fetch failed - {e}")
        return False, [], f"Error: {str(e)}"


def fetch_gemini_models_raw(api_key: str) -> Tuple[bool, List[str], str]:
    """
    Fetch all available Gemini models.
    
    Returns:
        (success, models_list, error_message)
    """
    logger.info("=" * 60)
    logger.info("GEMINI: Starting raw model fetch")
    try:
        import google.generativeai as genai
        
        genai.configure(api_key=api_key)
        models = genai.list_models()
        
        all_models = []
        model_names = []
        excluded_models = []
        
        for model in models:
            name = model.name.replace('models/', '')
            all_models.append(name)
            
            if 'generateContent' in model.supported_generation_methods:
                # Skip clearly problematic models
                if 'gemma' in name or 'nano-banana' in name:
                    excluded_models.append(name)
                else:
                    model_names.append(name)
        
        logger.info(f"GEMINI: API returned {len(all_models)} total models")
        logger.debug("GEMINI: All models from API:")
        for m in sorted(all_models):
            logger.debug(f"  - {m}")
        
        model_names.sort()
        
        logger.info(f"GEMINI: After filtering - {len(model_names)} generateContent models:")
        for m in model_names:
            logger.info(f"  • {m}")
        
        if excluded_models:
            logger.debug(f"GEMINI: Excluded {len(excluded_models)} models:")
            for m in excluded_models:
                logger.debug(f"  ✗ {m}")
        
        return True, model_names, ""
        
    except ImportError:
        logger.error("GEMINI: Google Generative AI library not installed")
        return False, [], "Google Generative AI library not installed"
    except Exception as e:
        logger.error(f"GEMINI: Fetch failed - {e}")
        return False, [], f"Error: {str(e)}"


# =============================================================================
# AI CURATION
# =============================================================================

def curate_with_openai(raw_models: List[str], provider_name: str, api_key: str) -> Tuple[bool, List[str], str]:
    """Use OpenAI to curate model list."""
    logger.info(f"CURATION: Using OpenAI to curate {provider_name} models")
    try:
        from openai import OpenAI
        
        client = OpenAI(api_key=api_key)
        
        prompt = CURATION_PROMPT.format(
            provider=provider_name,
            max_models=MAX_MODELS_PER_PROVIDER,
            model_list="\n".join(f"- {m}" for m in raw_models)
        )
        
        logger.debug(f"CURATION: Sending {len(raw_models)} models to OpenAI for curation")
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Use cheap, fast model for curation
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,  # Low temperature for consistent results
            max_tokens=200
        )
        
        result_text = response.choices[0].message.content.strip()
        logger.debug(f"CURATION: OpenAI raw response: {result_text}")
        
        # Parse JSON response
        curated = json.loads(result_text)
        
        if isinstance(curated, list) and len(curated) > 0:
            logger.info(f"CURATION: OpenAI suggested {len(curated)} models:")
            for m in curated:
                logger.info(f"  → {m}")
            
            # Validate all models exist in raw list
            validated = [m for m in curated if m in raw_models]
            invalid = [m for m in curated if m not in raw_models]
            
            if invalid:
                logger.warning(f"CURATION: {len(invalid)} suggested models not in raw list:")
                for m in invalid:
                    logger.warning(f"  ✗ {m}")
            
            if len(validated) >= 3:  # Accept if at least 3 valid models
                logger.info(f"CURATION: Final validated list ({len(validated)} models):")
                for m in validated[:MAX_MODELS_PER_PROVIDER]:
                    logger.info(f"  ✓ {m}")
                return True, validated[:MAX_MODELS_PER_PROVIDER], ""
        
        logger.warning("CURATION: OpenAI returned invalid model selection")
        return False, [], "AI returned invalid model selection"
        
    except Exception as e:
        logger.error(f"CURATION: OpenAI curation failed - {e}")
        return False, [], f"OpenAI curation failed: {str(e)}"


def curate_with_anthropic(raw_models: List[str], provider_name: str, api_key: str) -> Tuple[bool, List[str], str]:
    """Use Anthropic to curate model list."""
    logger.info(f"CURATION: Using Anthropic to curate {provider_name} models")
    try:
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        
        prompt = CURATION_PROMPT.format(
            provider=provider_name,
            max_models=MAX_MODELS_PER_PROVIDER,
            model_list="\n".join(f"- {m}" for m in raw_models)
        )
        
        logger.debug(f"CURATION: Sending {len(raw_models)} models to Anthropic for curation")
        
        data = {
            "model": "claude-3-5-haiku-20241022",  # Use cheap, fast model
            "max_tokens": 200,
            "messages": [{"role": "user", "content": prompt}]
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            result_text = result['content'][0]['text'].strip()
            logger.debug(f"CURATION: Anthropic raw response: {result_text}")
            
            curated = json.loads(result_text)
            
            if isinstance(curated, list) and len(curated) > 0:
                logger.info(f"CURATION: Anthropic suggested {len(curated)} models:")
                for m in curated:
                    logger.info(f"  → {m}")
                
                validated = [m for m in curated if m in raw_models]
                invalid = [m for m in curated if m not in raw_models]
                
                if invalid:
                    logger.warning(f"CURATION: {len(invalid)} suggested models not in raw list:")
                    for m in invalid:
                        logger.warning(f"  ✗ {m}")
                
                if len(validated) >= 3:
                    logger.info(f"CURATION: Final validated list ({len(validated)} models):")
                    for m in validated[:MAX_MODELS_PER_PROVIDER]:
                        logger.info(f"  ✓ {m}")
                    return True, validated[:MAX_MODELS_PER_PROVIDER], ""
        else:
            logger.warning(f"CURATION: Anthropic returned status {response.status_code}")
        
        logger.warning("CURATION: Anthropic returned invalid model selection")
        return False, [], "AI returned invalid model selection"
        
    except Exception as e:
        logger.error(f"CURATION: Anthropic curation failed - {e}")
        return False, [], f"Anthropic curation failed: {str(e)}"


def curate_with_gemini(raw_models: List[str], provider_name: str, api_key: str) -> Tuple[bool, List[str], str]:
    """Use Gemini to curate model list."""
    logger.info(f"CURATION: Using Gemini to curate {provider_name} models")
    try:
        import google.generativeai as genai
        
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')  # Use cheap, fast model
        
        prompt = CURATION_PROMPT.format(
            provider=provider_name,
            max_models=MAX_MODELS_PER_PROVIDER,
            model_list="\n".join(f"- {m}" for m in raw_models)
        )
        
        logger.debug(f"CURATION: Sending {len(raw_models)} models to Gemini for curation")
        
        response = model.generate_content(prompt)
        result_text = response.text.strip()
        logger.debug(f"CURATION: Gemini raw response: {result_text}")
        
        # Handle potential markdown code blocks
        if result_text.startswith('```'):
            result_text = result_text.split('```')[1]
            if result_text.startswith('json'):
                result_text = result_text[4:]
        
        curated = json.loads(result_text)
        
        if isinstance(curated, list) and len(curated) > 0:
            logger.info(f"CURATION: Gemini suggested {len(curated)} models:")
            for m in curated:
                logger.info(f"  → {m}")
            
            validated = [m for m in curated if m in raw_models]
            invalid = [m for m in curated if m not in raw_models]
            
            if invalid:
                logger.warning(f"CURATION: {len(invalid)} suggested models not in raw list:")
                for m in invalid:
                    logger.warning(f"  ✗ {m}")
            
            if len(validated) >= 3:
                logger.info(f"CURATION: Final validated list ({len(validated)} models):")
                for m in validated[:MAX_MODELS_PER_PROVIDER]:
                    logger.info(f"  ✓ {m}")
                return True, validated[:MAX_MODELS_PER_PROVIDER], ""
        
        logger.warning("CURATION: Gemini returned invalid model selection")
        return False, [], "AI returned invalid model selection"
        
    except Exception as e:
        logger.error(f"CURATION: Gemini curation failed - {e}")
        return False, [], f"Gemini curation failed: {str(e)}"


def curate_models_with_ai(
    provider_name: str,
    raw_models: List[str],
    available_keys: Dict[str, str]
) -> Tuple[bool, List[str], str]:
    """
    Use any available AI to curate the model list for a provider.
    
    Tries AI providers in order of preference until one succeeds.
    
    Args:
        provider_name: Name of provider whose models we're curating
        raw_models: Full list of available models from that provider
        available_keys: Dict of provider -> API key for AI curation
    
    Returns:
        (success, curated_models, status_message)
    """
    logger.info("=" * 60)
    logger.info(f"CURATION: Starting AI curation for {provider_name}")
    logger.info(f"CURATION: Input: {len(raw_models)} raw models")
    
    if len(raw_models) <= MAX_MODELS_PER_PROVIDER:
        logger.info(f"CURATION: Skipping - only {len(raw_models)} models (≤ {MAX_MODELS_PER_PROVIDER})")
        return True, raw_models, "No curation needed"
    
    # Try each AI provider in order of preference
    curation_attempts = [
        ("OpenAI (ChatGPT)", curate_with_openai),
        ("Anthropic (Claude)", curate_with_anthropic),
        ("Google (Gemini)", curate_with_gemini),
    ]
    
    available_providers = [p for p, _ in curation_attempts if available_keys.get(p)]
    logger.info(f"CURATION: Available AI providers: {available_providers}")
    
    for ai_provider, curate_func in curation_attempts:
        api_key = available_keys.get(ai_provider)
        if api_key:
            logger.info(f"CURATION: Trying {ai_provider}...")
            success, curated, error = curate_func(raw_models, provider_name, api_key)
            if success:
                logger.info(f"CURATION: Success! Curated by {ai_provider}")
                return True, curated, f"Curated by {ai_provider}"
            else:
                logger.warning(f"CURATION: {ai_provider} failed - {error}")
    
    logger.warning("CURATION: All AI providers failed - falling back to basic curation")
    return False, [], "No AI available for curation"


# =============================================================================
# BASIC FALLBACK CURATION (when AI is not available)
# =============================================================================

def basic_curate_openai(raw_models: List[str]) -> List[str]:
    """Basic sorting/selection for OpenAI models without AI."""
    logger.info("BASIC CURATION: Using pattern-based selection for OpenAI")
    # Prioritize newest models with vision capability
    priority_patterns = [
        'gpt-5.2',       # Latest GPT-5
        'gpt-5.1',       # GPT-5.1
        'gpt-5',         # GPT-5 base
        'gpt-4o',        # Vision, capable (NOT gpt-4o-mini first to ensure gpt-4o is picked)
        'gpt-4o-mini',   # Vision, fast, cheap
        'gpt-5-mini',    # Fast GPT-5
        'gpt-4.1',       # GPT-4.1
        'gpt-4-turbo',   # Vision
        'o3',            # Reasoning
        'o1',            # Reasoning
    ]
    
    result = []
    for pattern in priority_patterns:
        for model in raw_models:
            # Match base model name, avoid dated versions when base exists
            if model.startswith(pattern) and model not in result:
                # Prefer base model (e.g., "gpt-5" over "gpt-5-2025-08-07")
                if model == pattern or not any(m == pattern for m in raw_models):
                    result.append(model)
                    logger.debug(f"  + {model} (matched: {pattern})")
                    break
        if len(result) >= MAX_MODELS_PER_PROVIDER:
            break
    
    # Fill remaining slots
    for model in raw_models:
        if model not in result:
            result.append(model)
            logger.debug(f"  + {model} (filler)")
        if len(result) >= MAX_MODELS_PER_PROVIDER:
            break
    
    logger.info(f"BASIC CURATION: Selected {len(result[:MAX_MODELS_PER_PROVIDER])} models:")
    for m in result[:MAX_MODELS_PER_PROVIDER]:
        logger.info(f"  ✓ {m}")
    
    return result[:MAX_MODELS_PER_PROVIDER]


def basic_curate_anthropic(raw_models: List[str]) -> List[str]:
    """Basic sorting/selection for Anthropic models without AI."""
    logger.info("BASIC CURATION: Using pattern-based selection for Anthropic")
    # Prioritize newer models
    priority_patterns = [
        'claude-opus-4-6',
        'claude-opus-4-5',
        'claude-sonnet-4-5',
        'claude-haiku-4-5',
        'claude-sonnet-4-',
        'claude-3-5-sonnet',
        'claude-3-5-haiku',
        'claude-3-opus',
    ]
    
    result = []
    for pattern in priority_patterns:
        for model in raw_models:
            if pattern in model and model not in result:
                result.append(model)
                logger.debug(f"  + {model} (matched: {pattern})")
                break
        if len(result) >= MAX_MODELS_PER_PROVIDER:
            break
    
    for model in raw_models:
        if model not in result:
            result.append(model)
            logger.debug(f"  + {model} (filler)")
        if len(result) >= MAX_MODELS_PER_PROVIDER:
            break
    
    logger.info(f"BASIC CURATION: Selected {len(result[:MAX_MODELS_PER_PROVIDER])} models:")
    for m in result[:MAX_MODELS_PER_PROVIDER]:
        logger.info(f"  ✓ {m}")
    
    return result[:MAX_MODELS_PER_PROVIDER]


def basic_curate_gemini(raw_models: List[str]) -> List[str]:
    """Basic sorting/selection for Gemini models without AI."""
    logger.info("BASIC CURATION: Using pattern-based selection for Gemini")
    priority_patterns = [
        'gemini-2.5-flash',
        'gemini-2.5-pro',
        'gemini-2.5-flash-lite',
        'gemini-2.5-flash-image',
        'gemini-2.0-flash',
    ]
    
    result = []
    for pattern in priority_patterns:
        # First try exact match, then prefix match
        exact = [m for m in raw_models if m == pattern and m not in result]
        prefix = [m for m in raw_models if m.startswith(pattern) and m not in result and 'preview' not in m]
        match = exact[0] if exact else (prefix[0] if prefix else None)
        if match:
            result.append(match)
            logger.debug(f"  + {match} (matched: {pattern})")
            continue
        if len(result) >= MAX_MODELS_PER_PROVIDER:
            break
    
    for model in raw_models:
        if model not in result:
            result.append(model)
            logger.debug(f"  + {model} (filler)")
        if len(result) >= MAX_MODELS_PER_PROVIDER:
            break
    
    logger.info(f"BASIC CURATION: Selected {len(result[:MAX_MODELS_PER_PROVIDER])} models:")
    for m in result[:MAX_MODELS_PER_PROVIDER]:
        logger.info(f"  ✓ {m}")
    
    return result[:MAX_MODELS_PER_PROVIDER]


# =============================================================================
# MAIN FETCH FUNCTION
# =============================================================================

def fetch_all_models(
    config: dict,
    status_callback: Callable[[str], None] = None
) -> Dict[str, List[str]]:
    """
    Fetch and curate models for all providers with API keys configured.
    
    Uses AI curation when available for intelligent model selection.
    Falls back to basic curation or safe defaults when AI is unavailable.
    
    Args:
        config: App configuration dict with API keys
        status_callback: Optional function to report progress (e.g., update status bar)
    
    Returns:
        Dictionary of provider -> curated model list (max 5 per provider)
    """
    
    logger.info("=" * 70)
    logger.info("MODEL REFRESH: Starting")
    logger.info("=" * 70)
    
    def update_status(msg: str):
        if status_callback:
            status_callback(msg)
        print(f"📋 {msg}")  # Console output for debugging
    
    updated_models = {}
    keys = config.get("keys", {})
    
    # Collect available API keys for AI curation
    available_keys = {
        provider: key for provider, key in keys.items() if key
    }
    
    logger.info(f"Configured providers: {list(available_keys.keys())}")
    
    # ===================
    # OPENAI
    # ===================
    if keys.get("OpenAI (ChatGPT)"):
        update_status("Fetching OpenAI models...")
        success, raw_models, error = fetch_openai_models_raw(keys["OpenAI (ChatGPT)"])
        
        if success and raw_models:
            update_status("Optimizing OpenAI model selection...")
            ai_success, curated, _ = curate_models_with_ai(
                "OpenAI", raw_models, available_keys
            )
            
            if ai_success:
                updated_models["OpenAI (ChatGPT)"] = curated
            else:
                # Basic fallback curation
                updated_models["OpenAI (ChatGPT)"] = basic_curate_openai(raw_models)
        else:
            logger.warning(f"OPENAI: Fetch failed - {error}")
    
    # ===================
    # ANTHROPIC
    # ===================
    if keys.get("Anthropic (Claude)"):
        update_status("Fetching Anthropic models...")
        success, raw_models, error = fetch_anthropic_models_raw(keys["Anthropic (Claude)"])
        
        if success and raw_models:
            update_status("Optimizing Anthropic model selection...")
            ai_success, curated, _ = curate_models_with_ai(
                "Anthropic Claude", raw_models, available_keys
            )
            
            if ai_success:
                updated_models["Anthropic (Claude)"] = curated
            else:
                updated_models["Anthropic (Claude)"] = basic_curate_anthropic(raw_models)
        else:
            logger.warning(f"ANTHROPIC: Fetch failed - {error}")
    
    # ===================
    # GEMINI
    # ===================
    if keys.get("Google (Gemini)"):
        update_status("Fetching Gemini models...")
        success, raw_models, error = fetch_gemini_models_raw(keys["Google (Gemini)"])
        
        if success and raw_models:
            update_status("Optimizing Gemini model selection...")
            ai_success, curated, _ = curate_models_with_ai(
                "Google Gemini", raw_models, available_keys
            )
            
            if ai_success:
                # Ensure gemini-2.5-flash is always included (best free tier model)
                if 'gemini-2.5-flash' in raw_models and 'gemini-2.5-flash' not in curated:
                    curated.insert(0, 'gemini-2.5-flash')
                    curated = curated[:MAX_MODELS_PER_PROVIDER]
                updated_models["Google (Gemini)"] = curated
            else:
                updated_models["Google (Gemini)"] = basic_curate_gemini(raw_models)
        else:
            logger.warning(f"GEMINI: Fetch failed - {error}")
    
    # ===================
    # xAI (no API for listing, use fallback)
    # ===================
    if keys.get("xAI (Grok)"):
        logger.info("=" * 60)
        logger.info("XAI: No model listing API - using hardcoded fallback")
        logger.info(f"XAI: Fallback models: {SAFE_FALLBACK_MODELS['xAI (Grok)']}")
        updated_models["xAI (Grok)"] = SAFE_FALLBACK_MODELS["xAI (Grok)"]
    
    # ===================
    # DeepSeek (no API for listing, use fallback)
    # ===================
    if keys.get("DeepSeek"):
        logger.info("=" * 60)
        logger.info("DEEPSEEK: No model listing API - using hardcoded fallback")
        logger.info(f"DEEPSEEK: Fallback models: {SAFE_FALLBACK_MODELS['DeepSeek']}")
        updated_models["DeepSeek"] = SAFE_FALLBACK_MODELS["DeepSeek"]
    
    # ===================
    # SUMMARY
    # ===================
    logger.info("=" * 70)
    logger.info("MODEL REFRESH: COMPLETE - FINAL SUMMARY")
    logger.info("=" * 70)
    for provider, models in updated_models.items():
        logger.info(f"\n{provider}:")
        for m in models:
            logger.info(f"  • {m}")
    logger.info("=" * 70)
    
    update_status("Model refresh complete.")
    return updated_models


def get_safe_fallback_models() -> Dict[str, List[str]]:
    """
    Return safe fallback models when no API keys are configured.
    
    These are stable, well-known models that are unlikely to be
    deprecated in the near future.
    
    Returns:
        Dictionary of provider -> model list
    """
    return SAFE_FALLBACK_MODELS.copy()


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def is_vision_capable(provider: str, model: str) -> bool:
    """
    Check if a specific model supports vision/image input.
    
    Args:
        provider: Provider name (e.g., "OpenAI (ChatGPT)")
        model: Model name (e.g., "gpt-4o")
        
    Returns:
        True if model likely supports vision, False otherwise
    """
    vision_patterns = {
        "OpenAI (ChatGPT)": ["gpt-4o", "gpt-4-turbo", "gpt-4-vision"],
        "Anthropic (Claude)": ["claude-3", "claude-sonnet-4", "claude-opus-4", "claude-haiku-4"],  # covers opus-4-6, opus-4-5, etc.
        "Google (Gemini)": ["gemini"],  # All Gemini 1.5+ support vision
        "xAI (Grok)": ["vision"],
        "DeepSeek": [],
    }
    
    patterns = vision_patterns.get(provider, [])
    return any(pattern in model.lower() for pattern in patterns)
