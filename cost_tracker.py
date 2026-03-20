"""
cost_tracker.py - API Cost Tracking and Display

Handles:
- Cost calculation for different AI providers
- Cost logging to SQLite (preferred) or cost_log.txt (fallback)
- Cost display dialog with pricing info

Usage:
    from cost_tracker import (
        log_cost,
        calculate_cost,
        show_costs_dialog,
        get_pricing_info,
        get_pricing_urls,
        build_cost_status,
    )

Updated: February 2026 — Stage A SQLite integration
"""

import os
import json
import datetime
import webbrowser
from pathlib import Path
from typing import Dict, Tuple, Optional

# --- SQLite feature flag (Stage A) ---
# Set to False to revert to cost_log.txt file-based logging/reading
USE_SQLITE_COSTS = True


# ============================================================
# PRICING DATA (loaded from pricing.json)
# ============================================================

def _load_pricing_file() -> dict:
    """Load pricing data from pricing.json."""
    try:
        pricing_path = Path(__file__).parent / "pricing.json"
        with open(pricing_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get("providers", {})
    except Exception as e:
        print(f"\u26a0\ufe0f Could not load pricing.json: {e}")
        return {}


def _get_pricing() -> dict:
    """Get pricing in the flat format {provider: {model: {input, output}}} for display."""
    raw = _load_pricing_file()
    result = {}
    for provider, pdata in raw.items():
        result[provider] = pdata.get("models", {})
    return result


def _get_pricing_urls() -> dict:
    """Get pricing page URLs from pricing.json."""
    raw = _load_pricing_file()
    return {provider: pdata.get("url", "") for provider, pdata in raw.items()}


def get_pricing() -> dict:
    """Get pricing dict: {provider: {model: {input, output}}}."""
    return _get_pricing()


def get_pricing_urls() -> dict:
    """Get pricing URLs dict: {provider: url}."""
    return _get_pricing_urls()


# ============================================================
# COST CALCULATION
# ============================================================

def calculate_cost(provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
    """
    Calculate the cost for an API call.
    
    Args:
        provider: Provider name (e.g., "OpenAI (ChatGPT)")
        model: Model name (e.g., "gpt-4o")
        input_tokens: Number of input/prompt tokens
        output_tokens: Number of output/completion tokens
    
    Returns:
        Cost in dollars
    """
    pricing = get_pricing()
    provider_pricing = pricing.get(provider, {})
    
    model_pricing = None
    model_lower = model.lower()
    
    for key in provider_pricing:
        if key in model_lower:
            model_pricing = provider_pricing[key]
            break
    
    if not model_pricing:
        if provider_pricing:
            model_pricing = list(provider_pricing.values())[0]
        else:
            model_pricing = {"input": 1.00, "output": 3.00}
    
    input_cost = (input_tokens / 1_000_000) * model_pricing["input"]
    output_cost = (output_tokens / 1_000_000) * model_pricing["output"]
    
    return input_cost + output_cost


def get_model_pricing(provider: str, model: str) -> Optional[Dict[str, float]]:
    """
    Get the pricing for a specific model.
    
    Args:
        provider: Provider name
        model: Model name
    
    Returns:
        Dict with 'input' and 'output' pricing per 1M tokens, or None
    """
    pricing = get_pricing()
    provider_pricing = pricing.get(provider, {})
    model_lower = model.lower()
    
    for key in provider_pricing:
        if key in model_lower:
            return provider_pricing[key]
    
    return None


# ============================================================
# COST LOGGING
# ============================================================

def get_cost_log_path() -> Path:
    """Get the path to cost_log.txt"""
    app_dir = Path(__file__).parent
    cost_log_path = app_dir / "cost_log.txt"
    
    if not cost_log_path.exists():
        cost_log_path = Path(os.getcwd()) / "cost_log.txt"
    
    return cost_log_path


def log_cost(provider: str, model: str, cost: float, 
             document_title: str = None, prompt_name: str = None):
    """
    Log API cost — writes to SQLite (if USE_SQLITE_COSTS) or cost_log.txt.
    
    Args:
        provider: Provider name
        model: Model name
        cost: Cost in dollars
        document_title: Optional document title being processed
        prompt_name: Optional prompt name used
    """
    try:
        if USE_SQLITE_COSTS:
            import db_manager as db
            db.init_database()
            db.db_log_cost(
                provider=provider,
                model=model,
                cost=cost,
                document_title=document_title,
                prompt_name=prompt_name,
            )
            return

        # --- Legacy text-file path (fallback) ---
        app_dir = Path(__file__).parent
        cost_log_path = app_dir / "cost_log.txt"
        
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        doc_info = document_title if document_title else "N/A"
        prompt_info = prompt_name if prompt_name else "N/A"
        
        log_entry = f"{timestamp} | {provider} | {model} | ${cost:.6f} | {doc_info} | {prompt_info}\n"
        
        with open(cost_log_path, 'a', encoding='utf-8') as f:
            f.write(log_entry)
            
    except Exception as e:
        print(f"\u26a0\ufe0f Cost logging failed: {e}")


def read_cost_log() -> Tuple[bool, list, dict, dict, float]:
    """
    Read and parse the cost log.
    
    Returns:
        Tuple of (success, entries, cost_by_provider, cost_by_model, total_cost)
    """
    if USE_SQLITE_COSTS:
        return _read_cost_log_sqlite()

    return _read_cost_log_txtfile()


def _read_cost_log_sqlite() -> Tuple[bool, list, dict, dict, float]:
    """Read cost data from SQLite via db_manager."""
    try:
        import db_manager as db
        db.init_database()
        rows = db.db_get_costs()  # all entries, newest first

        if not rows:
            return False, [], {}, {}, 0.0

        total_cost = 0.0
        cost_by_provider = {}
        cost_by_model = {}
        entries = []

        for r in rows:
            cost = r.get('cost', 0.0)
            provider = r.get('provider', 'Unknown')
            model = r.get('model', 'Unknown')

            total_cost += cost
            cost_by_provider[provider] = cost_by_provider.get(provider, 0.0) + cost
            cost_by_model[model] = cost_by_model.get(model, 0.0) + cost

            entries.append({
                'timestamp': r.get('timestamp', ''),
                'provider': provider,
                'model': model,
                'cost': cost,
                'document': r.get('document_title', 'N/A') or 'N/A',
                'prompt': r.get('prompt_name', 'N/A') or 'N/A',
            })

        return True, entries, cost_by_provider, cost_by_model, total_cost

    except Exception as e:
        print(f"\u26a0\ufe0f Failed to read cost log from SQLite: {e}")
        return False, [], {}, {}, 0.0


def _read_cost_log_txtfile() -> Tuple[bool, list, dict, dict, float]:
    """Legacy: read cost data from cost_log.txt."""
    cost_log_path = get_cost_log_path()
    
    if not cost_log_path.exists():
        return False, [], {}, {}, 0.0
    
    try:
        with open(cost_log_path, 'r', encoding='utf-8') as f:
            log_content = f.read()
        
        total_cost = 0.0
        cost_by_provider = {}
        cost_by_model = {}
        entries = []
        
        for line in log_content.strip().split('\n'):
            if not line.strip() or line.startswith('---'):
                continue
            
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 4:
                try:
                    timestamp_str = parts[0]
                    provider = parts[1]
                    model = parts[2]
                    cost_str = parts[3].replace('$', '').strip()
                    cost = float(cost_str)
                    
                    total_cost += cost
                    cost_by_provider[provider] = cost_by_provider.get(provider, 0.0) + cost
                    cost_by_model[model] = cost_by_model.get(model, 0.0) + cost
                    
                    document = parts[4].strip() if len(parts) >= 5 else 'N/A'
                    prompt = parts[5].strip() if len(parts) >= 6 else 'N/A'
                    
                    entries.append({
                        'timestamp': timestamp_str,
                        'provider': provider,
                        'model': model,
                        'cost': cost,
                        'document': document,
                        'prompt': prompt
                    })
                except (ValueError, IndexError):
                    continue
        
        return True, entries, cost_by_provider, cost_by_model, total_cost
        
    except Exception as e:
        print(f"\u26a0\ufe0f Failed to read cost log: {e}")
        return False, [], {}, {}, 0.0


# ============================================================
# 30-DAY COST TOTALS AND STATUS BAR HELPER
# ============================================================

def get_30day_costs(provider_filter: str = None) -> Tuple[float, float]:
    """
    Get cost totals for the last 30 days.
    
    Args:
        provider_filter: If provided, also return cost for this specific provider.
                         Matches if the filter string appears in the provider name (case-insensitive).
    
    Returns:
        Tuple of (provider_30d_cost, all_30d_cost)
        If provider_filter is None, provider_30d_cost will be 0.0
    """
    if USE_SQLITE_COSTS:
        return _get_30day_costs_sqlite(provider_filter)

    return _get_30day_costs_txtfile(provider_filter)


def _get_30day_costs_sqlite(provider_filter: str = None) -> Tuple[float, float]:
    """Read 30-day costs from SQLite."""
    try:
        import db_manager as db
        db.init_database()
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=30)).isoformat()
        rows = db.db_get_costs(since=cutoff)

        all_cost = 0.0
        provider_cost = 0.0
        filter_lower = provider_filter.lower() if provider_filter else ""

        for r in rows:
            c = r.get('cost', 0.0)
            all_cost += c
            if filter_lower and filter_lower in r.get('provider', '').lower():
                provider_cost += c

        return provider_cost, all_cost

    except Exception:
        return 0.0, 0.0


def _get_30day_costs_txtfile(provider_filter: str = None) -> Tuple[float, float]:
    """Legacy: read 30-day costs from cost_log.txt."""
    cost_log_path = get_cost_log_path()
    if not cost_log_path.exists():
        return 0.0, 0.0
    
    try:
        cutoff = datetime.datetime.now() - datetime.timedelta(days=30)
        all_cost = 0.0
        provider_cost = 0.0
        filter_lower = provider_filter.lower() if provider_filter else ""
        
        with open(cost_log_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('---'):
                    continue
                parts = [p.strip() for p in line.split('|')]
                if len(parts) < 4:
                    continue
                try:
                    ts = datetime.datetime.strptime(parts[0], "%Y-%m-%d %H:%M:%S")
                    if ts < cutoff:
                        continue
                    cost = float(parts[3].replace('$', '').strip())
                    all_cost += cost
                    if filter_lower and filter_lower in parts[1].lower():
                        provider_cost += cost
                except (ValueError, IndexError):
                    continue
        
        return provider_cost, all_cost
    except Exception:
        return 0.0, 0.0


def build_cost_status(prefix: str, provider: str = "") -> str:
    """
    Build a complete cost status string for the status bar.
    
    Args:
        prefix: e.g. "Processing complete" or "Follow-up complete"
        provider: Current provider name (e.g. "DeepSeek", "OpenAI")
    
    Returns:
        Formatted status string like:
        "\u2705 Processing complete \u2014 $0.0006 | Session: $0.0038 | DeepSeek 30d: $0.0142 | All 30d: $0.0891"
    """
    try:
        import ai_handler
        cost = ai_handler.last_call_info.get("cost", 0)
        session = ai_handler.session_cost
        
        if cost <= 0:
            return f"\u2705 {prefix}"
        
        short_provider = provider.split('(')[0].strip() if provider else ""
        provider_30d, all_30d = get_30day_costs(short_provider if short_provider else None)
        
        parts = [f"\u2705 {prefix} \u2014 ${cost:.4f}"]
        parts.append(f"Session: ${session:.4f}")
        
        if short_provider and provider_30d > 0:
            parts.append(f"{short_provider} 30d: ${provider_30d:.4f}")
        
        if all_30d > 0:
            parts.append(f"All 30d: ${all_30d:.4f}")
        
        return " | ".join(parts)
    except Exception:
        return f"\u2705 {prefix}"


# ============================================================
# PRICING INFO (for display)
# ============================================================

def get_pricing_info() -> str:
    """
    Get formatted pricing information for display.
    
    Returns:
        Formatted string with pricing tables
    """
    info = """
API PRICING REFERENCE
\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550

Note: Prices change frequently. Check official pricing pages for current rates.
All prices are per 1 million tokens.

"""
    
    pricing = get_pricing()
    pricing_urls = get_pricing_urls()
    for provider, models in pricing.items():
        info += f"\n{'\u2500' * 60}\n"
        info += f"{provider}\n"
        info += f"{'\u2500' * 60}\n"
        info += f"{'Model':<30} {'Input':>10} {'Output':>10}\n"
        info += f"{'-' * 50}\n"
        
        for model, prices in models.items():
            info += f"{model:<30} ${prices['input']:>8.2f} ${prices['output']:>8.2f}\n"
        
        url = pricing_urls.get(provider, "N/A")
        info += f"\nOfficial Pricing: {url}\n"
    
    return info


# ============================================================
# COST DISPLAY DIALOG
# ============================================================

def show_costs_dialog(parent):
    """
    Display API costs dialog with pricing info and usage summary.
    
    Args:
        parent: Parent tkinter window
    """
    import tkinter as tk
    from tkinter import ttk, scrolledtext, messagebox
    
    costs_window = tk.Toplevel(parent)
    costs_window.title("API Costs Summary")
    costs_window.geometry("900x650")
    
    costs_window.transient(parent)
    costs_window.grab_set()
    
    main_frame = ttk.Frame(costs_window, padding=10)
    main_frame.pack(fill=tk.BOTH, expand=True)
    
    title_label = ttk.Label(main_frame, text="API Cost Summary", 
                           font=('Arial', 14, 'bold'))
    title_label.pack(pady=(0, 10))
    
    notebook = ttk.Notebook(main_frame)
    notebook.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
    
    # ============================================================
    # Tab 1: Pricing Info
    # ============================================================
    pricing_frame = ttk.Frame(notebook, padding=10)
    notebook.add(pricing_frame, text="\U0001f4b0 Pricing Info")
    
    pricing_text = tk.Text(pricing_frame, wrap=tk.WORD, font=('Arial', 10),
                           cursor="arrow", padx=10, pady=10)
    pricing_scrollbar = ttk.Scrollbar(pricing_frame, orient=tk.VERTICAL, 
                                      command=pricing_text.yview)
    pricing_text.configure(yscrollcommand=pricing_scrollbar.set)
    pricing_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    pricing_text.pack(fill=tk.BOTH, expand=True)
    
    pricing_text.tag_configure("title", font=('Arial', 12, 'bold'), foreground='#2c3e50')
    pricing_text.tag_configure("provider", font=('Arial', 11, 'bold'), 
                               foreground='#16537E', spacing1=15)
    pricing_text.tag_configure("model", font=('Courier New', 10), foreground='#333333')
    pricing_text.tag_configure("note", font=('Arial', 9, 'italic'), foreground='#7f8c8d')
    
    pricing_text.insert(tk.END, "\nAPI PRICING REFERENCE\n", "title")
    pricing_text.insert(tk.END, "\u2550" * 60 + "\n\n", "note")
    
    pricing_text.insert(tk.END, "WHAT DOES '1 MILLION TOKENS' MEAN?\n", "provider")
    pricing_text.insert(tk.END, "\u2500" * 55 + "\n", "note")
    pricing_text.insert(tk.END, """A 'token' is roughly \u00be of a word (or about 4 characters).

1 million tokens \u2248 750,000 words \u2248 1,500 pages of text

Practical examples:
 \u2022 A 2-hour interview transcript (~15,000 words) uses ~20,000 tokens
 \u2022 Summarizing that transcript might cost $0.01 - $0.10 depending on model
 \u2022 You could process 50+ such transcripts for about $1-$5

Input tokens = what you send (your document + prompt)
Output tokens = what the AI returns (usually much smaller)
\n""", "model")
    
    pricing_text.insert(tk.END, "\U0001f3e0 FREE ALTERNATIVE: LOCAL AI (OLLAMA)\n", "provider")
    pricing_text.insert(tk.END, "\u2500" * 55 + "\n", "note")
    pricing_text.insert(tk.END, """The prices below apply to cloud-based AI providers.

If your system has sufficient resources, you can use Ollama
to run AI models locally on your computer at NO COST.

Ollama is a free application that lets you download and run
open-source AI models. Available models include:

 \u2022 Lightweight (8GB RAM):  Llama 3.2:1b, Gemma2:2b, Phi-3 Mini
 \u2022 Balanced (16GB RAM):    Llama 3.1:8b, Mistral 7B, Gemma2:9b \u2190 Recommended
 \u2022 Powerful (32GB+ RAM):   Llama 3.1:70b, Qwen2.5:32b, Mixtral
 \u2022 Specialized:            DeepSeek-Coder, CodeLlama, LLaVA (vision)

\u26a0\ufe0f Quality note: Models under 7B parameters may struggle with long
   documents. For reliable summaries of lengthy transcripts, use
   Llama 3.1:8b or larger, or choose a cloud provider.

To manage local models in DocAnalyser:
  Settings \u2192 Ollama section \u2192 Manage Models

The Model Manager will recommend models based on your system's
RAM and GPU capabilities.

Download Ollama from: https://ollama.com
\n""", "model")
    
    pricing_text.insert(tk.END, "Note: Prices change frequently. Click links for current pricing.\n", "note")
    pricing_text.insert(tk.END, "All prices shown are per 1 million tokens.\n\n", "note")
    
    provider_icons = {
        "Anthropic (Claude)": "\U0001f7e3",
        "OpenAI (ChatGPT)": "\U0001f7e2",
        "Google (Gemini)": "\U0001f535",
        "xAI (Grok)": "\u26ab",
        "DeepSeek": "\U0001f7e0",
        "Ollama (Local)": "\U0001f3e0"
    }
    
    current_pricing = get_pricing()
    current_urls = get_pricing_urls()
    for provider, models in current_pricing.items():
        icon = provider_icons.get(provider, "\u2022")
        pricing_text.insert(tk.END, f"\n{icon} {provider}\n", "provider")
        pricing_text.insert(tk.END, "\u2500" * 55 + "\n", "note")
        
        header = f"{'Model':<28} {'Input':>10} {'Output':>10}\n"
        pricing_text.insert(tk.END, header, "model")
        pricing_text.insert(tk.END, "-" * 50 + "\n", "note")
        
        for model, prices in models.items():
            line = f"{model:<28} ${prices['input']:>8.2f} ${prices['output']:>8.2f}\n"
            pricing_text.insert(tk.END, line, "model")
        
        url = current_urls.get(provider, "")
        if url:
            pricing_text.insert(tk.END, "\n\U0001f4ce Official Pricing: ", "note")
            
            link_tag = f"link_{provider.replace(' ', '_').replace('(', '').replace(')', '')}"
            pricing_text.insert(tk.END, url + "\n", link_tag)
            pricing_text.tag_configure(link_tag, font=('Arial', 10, 'underline'), 
                                       foreground='#3498db')
            pricing_text.tag_bind(link_tag, "<Button-1>", 
                                 lambda e, u=url: webbrowser.open(u))
            pricing_text.tag_bind(link_tag, "<Enter>", 
                                 lambda e: pricing_text.config(cursor="hand2"))
            pricing_text.tag_bind(link_tag, "<Leave>", 
                                 lambda e: pricing_text.config(cursor="arrow"))
    
    pricing_text.insert(tk.END, "\n" + "\u2550" * 60 + "\n", "note")
    pricing_text.insert(tk.END, "\u26a0\ufe0f Prices shown are approximate and may have changed.\n", "note")
    pricing_text.insert(tk.END, "   Always check official pricing pages for current rates.\n", "note")
    pricing_text.insert(tk.END, f"   Last updated: February 2026\n", "note")
    
    pricing_text.config(state=tk.DISABLED)
    
    # ============================================================
    # Read cost log for other tabs
    # ============================================================
    cost_log_path = get_cost_log_path()
    success, entries, cost_by_provider, cost_by_model, total_cost = read_cost_log()
    
    if not success or not entries:
        no_log_frame = ttk.Frame(notebook, padding=10)
        notebook.add(no_log_frame, text="\U0001f4ca Summary")
        
        ttk.Label(no_log_frame, text="No cost log found", 
                 font=('Arial', 12)).pack(pady=20)
        
        if USE_SQLITE_COSTS:
            location_text = "Data stored in: SQLite database (docanalyser.db)"
        else:
            location_text = f"Expected location:\n{cost_log_path}"
        
        ttk.Label(no_log_frame, 
                 text=f"{location_text}\n\n"
                      "Cost logging will begin with your next API call.",
                 justify=tk.LEFT).pack(pady=10)
    else:
        # ============================================================
        # Tab 2: Summary
        # ============================================================
        summary_frame = ttk.Frame(notebook, padding=10)
        notebook.add(summary_frame, text="\U0001f4ca Summary")
        
        stats_text = scrolledtext.ScrolledText(summary_frame, wrap=tk.WORD, 
                                               font=('Courier New', 10))
        stats_text.pack(fill=tk.BOTH, expand=True)
        
        summary_content = f"""\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
                API COSTS SUMMARY
\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550

\U0001f4ca TOTAL COST: ${total_cost:.4f}

\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
\U0001f4b3 COST BY PROVIDER
\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
"""
        
        for provider, cost in sorted(cost_by_provider.items(), key=lambda x: -x[1]):
            percentage = (cost / total_cost * 100) if total_cost > 0 else 0
            summary_content += f"\n{provider:20s} ${cost:>8.4f}  ({percentage:5.1f}%)"
        
        summary_content += f"""

\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
\U0001f916 COST BY MODEL
\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
"""
        
        for model, cost in sorted(cost_by_model.items(), key=lambda x: -x[1]):
            percentage = (cost / total_cost * 100) if total_cost > 0 else 0
            summary_content += f"\n{model:30s} ${cost:>8.4f}  ({percentage:5.1f}%)"
        
        avg_cost = (total_cost / len(entries)) if entries else 0
        
        if USE_SQLITE_COSTS:
            log_location = "SQLite database (docanalyser.db)"
        else:
            log_location = str(cost_log_path)
        
        summary_content += f"""

\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
\U0001f4c8 STATISTICS
\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550

Total API Calls:        {len(entries)}
Average Cost per Call:  ${avg_cost:.4f}
Data Source:            {log_location}
"""
        
        stats_text.insert('1.0', summary_content)
        stats_text.config(state=tk.DISABLED)
        
        # ============================================================
        # Tab 3: Detailed Log
        # ============================================================
        details_frame = ttk.Frame(notebook, padding=10)
        notebook.add(details_frame, text="\U0001f4cb Detailed Log")
        
        details_text = scrolledtext.ScrolledText(details_frame, wrap=tk.NONE, 
                                                 font=('Courier New', 9))
        details_text.pack(fill=tk.BOTH, expand=True)
        
        header = f"{'Timestamp':<20} | {'Provider':<12} | {'Model':<18} | {'Cost':>8} | {'Document':<35} | {'Prompt'}\n"
        header += "-" * 130 + "\n"
        details_text.insert('1.0', header)
        
        # entries are already newest-first from SQLite; for txt they were chronological
        display_entries = entries if USE_SQLITE_COSTS else list(reversed(entries))
        for entry in display_entries:
            doc = entry.get('document', 'N/A')
            if len(doc) > 35:
                doc = doc[:32] + '...'
            prompt = entry.get('prompt', 'N/A')
            line = f"{entry['timestamp']:<20} | {entry['provider']:<12} | {entry['model']:<18} | ${entry['cost']:>7.4f} | {doc:<35} | {prompt}\n"
            details_text.insert(tk.END, line)
        
        details_text.config(state=tk.DISABLED)
        
        # ============================================================
        # Tab 4: Raw Log
        # ============================================================
        raw_frame = ttk.Frame(notebook, padding=10)
        notebook.add(raw_frame, text="\U0001f4c4 Raw Log")
        
        raw_text = scrolledtext.ScrolledText(raw_frame, wrap=tk.NONE, 
                                             font=('Courier New', 9))
        raw_text.pack(fill=tk.BOTH, expand=True)
        
        if USE_SQLITE_COSTS:
            # Show formatted data from SQLite
            raw_lines = []
            for entry in entries:
                raw_lines.append(
                    f"{entry['timestamp']} | {entry['provider']} | {entry['model']} "
                    f"| ${entry['cost']:.6f} | {entry.get('document', 'N/A')} "
                    f"| {entry.get('prompt', 'N/A')}"
                )
            raw_text.insert('1.0', "\n".join(raw_lines) if raw_lines else "(empty)")
        else:
            try:
                with open(cost_log_path, 'r', encoding='utf-8') as f:
                    raw_text.insert('1.0', f.read())
            except:
                raw_text.insert('1.0', "Could not read log file")
        
        raw_text.config(state=tk.DISABLED)
    
    # ============================================================
    # Button frame at bottom
    # ============================================================
    button_frame = ttk.Frame(main_frame)
    button_frame.pack(fill=tk.X, pady=(10, 0))
    
    def refresh():
        costs_window.destroy()
        show_costs_dialog(parent)
    
    ttk.Button(button_frame, text="Refresh", command=refresh).pack(side=tk.LEFT, padx=5)
    
    if not USE_SQLITE_COSTS and cost_log_path.exists():
        def open_log():
            if os.name == 'nt':
                os.startfile(str(cost_log_path))
            else:
                os.system(f'open "{cost_log_path}"')
        
        ttk.Button(button_frame, text="Open Log File", 
                  command=open_log).pack(side=tk.LEFT, padx=5)
    
    ttk.Button(button_frame, text="Close", 
              command=costs_window.destroy).pack(side=tk.RIGHT, padx=5)
