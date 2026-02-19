"""
cost_tracker.py - API Cost Tracking and Display

Handles:
- Cost calculation for different AI providers
- Cost logging to cost_log.txt
- Cost display dialog with pricing info

Usage:
    from cost_tracker import (
        log_cost,
        calculate_cost,
        show_costs_dialog,
        get_pricing_info,
        PRICING_URLS
    )
"""

import os
import datetime
import webbrowser
from pathlib import Path
from typing import Dict, Tuple, Optional


# ============================================================
# PRICING DATA (Updated February 2026)
# ============================================================

# Pricing per 1 million tokens
PRICING = {
    "OpenAI (ChatGPT)": {
        "gpt-5.2": {"input": 2.00, "output": 8.00},
        "gpt-5.1": {"input": 5.00, "output": 20.00},
        "gpt-5": {"input": 5.00, "output": 15.00},
        "gpt-4o": {"input": 2.50, "output": 10.00},
        "gpt-4o-mini": {"input": 0.15, "output": 0.60},
        "gpt-4-turbo": {"input": 10.00, "output": 30.00},
        "o3-mini": {"input": 1.10, "output": 4.40},
        "o1": {"input": 15.00, "output": 60.00},
        "o1-mini": {"input": 3.00, "output": 12.00},
    },
    "Anthropic (Claude)": {
        "claude-opus-4-5": {"input": 15.00, "output": 75.00},
        "claude-sonnet-4-5": {"input": 3.00, "output": 15.00},
        "claude-haiku-4-5": {"input": 0.80, "output": 4.00},
        "claude-sonnet-4": {"input": 3.00, "output": 15.00},
        "claude-3-5-sonnet": {"input": 3.00, "output": 15.00},
        "claude-3-5-haiku": {"input": 0.80, "output": 4.00},
        "claude-3-opus": {"input": 15.00, "output": 75.00},
        "claude-3-haiku": {"input": 0.25, "output": 1.25},
    },
    "Google (Gemini)": {
        "gemini-2.5-pro": {"input": 1.25, "output": 10.00},
        "gemini-2.5-flash": {"input": 0.15, "output": 0.60},
        "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
        "gemini-2.0-flash-lite": {"input": 0.075, "output": 0.30},
        "gemini-1.5-pro": {"input": 1.25, "output": 5.00},
        "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
    },
    "xAI (Grok)": {
        "grok-3": {"input": 3.00, "output": 15.00},
        "grok-3-fast": {"input": 5.00, "output": 25.00},
        "grok-2": {"input": 2.00, "output": 10.00},
        "grok-2-vision": {"input": 2.00, "output": 10.00},
    },
    "DeepSeek": {
        "deepseek-chat": {"input": 0.14, "output": 0.28},
        "deepseek-reasoner": {"input": 0.55, "output": 2.19},
    },
    "Ollama (Local)": {
        "all models": {"input": 0.00, "output": 0.00},
    }
}

# Official pricing page URLs
PRICING_URLS = {
    "Anthropic (Claude)": "https://www.anthropic.com/pricing",
    "OpenAI (ChatGPT)": "https://openai.com/api/pricing",
    "Google (Gemini)": "https://ai.google.dev/pricing",
    "xAI (Grok)": "https://docs.x.ai/docs/overview",
    "DeepSeek": "https://platform.deepseek.com/api-docs/pricing",
    "Ollama (Local)": "https://ollama.com",
}


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
    # Get provider pricing
    provider_pricing = PRICING.get(provider, {})
    
    # Find matching model pricing
    model_pricing = None
    model_lower = model.lower()
    
    for key in provider_pricing:
        if key in model_lower:
            model_pricing = provider_pricing[key]
            break
    
    # If no match found, try to find a reasonable default
    if not model_pricing:
        # Use the first pricing entry as default, or a safe fallback
        if provider_pricing:
            model_pricing = list(provider_pricing.values())[0]
        else:
            # Ultimate fallback - assume moderate pricing
            model_pricing = {"input": 1.00, "output": 3.00}
    
    # Calculate cost (pricing is per 1M tokens)
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
    provider_pricing = PRICING.get(provider, {})
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
    # Try to find it relative to this module
    app_dir = Path(__file__).parent
    cost_log_path = app_dir / "cost_log.txt"
    
    if not cost_log_path.exists():
        cost_log_path = Path(os.getcwd()) / "cost_log.txt"
    
    return cost_log_path


def log_cost(provider: str, model: str, cost: float, 
             document_title: str = None, prompt_name: str = None):
    """
    Log API cost to cost_log.txt.
    
    Args:
        provider: Provider name
        model: Model name
        cost: Cost in dollars
        document_title: Optional document title being processed
        prompt_name: Optional prompt name used
    """
    try:
        app_dir = Path(__file__).parent
        cost_log_path = app_dir / "cost_log.txt"
        
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Format: timestamp | provider | model | cost | document | prompt
        doc_info = document_title if document_title else "N/A"
        prompt_info = prompt_name if prompt_name else "N/A"
        
        log_entry = f"{timestamp} | {provider} | {model} | ${cost:.6f} | {doc_info} | {prompt_info}\n"
        
        with open(cost_log_path, 'a', encoding='utf-8') as f:
            f.write(log_entry)
            
    except Exception as e:
        print(f"⚠️ Cost logging failed: {e}")


def read_cost_log() -> Tuple[bool, list, dict, dict, float]:
    """
    Read and parse the cost log file.
    
    Returns:
        Tuple of (success, entries, cost_by_provider, cost_by_model, total_cost)
    """
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
                    
                    entries.append({
                        'timestamp': timestamp_str,
                        'provider': provider,
                        'model': model,
                        'cost': cost
                    })
                except (ValueError, IndexError):
                    continue
        
        return True, entries, cost_by_provider, cost_by_model, total_cost
        
    except Exception as e:
        print(f"⚠️ Failed to read cost log: {e}")
        return False, [], {}, {}, 0.0


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
═══════════════════════════════════════════════════════════════════

Note: Prices change frequently. Check official pricing pages for current rates.
All prices are per 1 million tokens.

"""
    
    for provider, models in PRICING.items():
        info += f"\n{'─' * 60}\n"
        info += f"{provider}\n"
        info += f"{'─' * 60}\n"
        info += f"{'Model':<30} {'Input':>10} {'Output':>10}\n"
        info += f"{'-' * 50}\n"
        
        for model, prices in models.items():
            info += f"{model:<30} ${prices['input']:>8.2f} ${prices['output']:>8.2f}\n"
        
        url = PRICING_URLS.get(provider, "N/A")
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
    
    # Create the costs dialog window
    costs_window = tk.Toplevel(parent)
    costs_window.title("API Costs Summary")
    costs_window.geometry("900x650")
    
    # Make dialog modal
    costs_window.transient(parent)
    costs_window.grab_set()
    
    # Main frame
    main_frame = ttk.Frame(costs_window, padding=10)
    main_frame.pack(fill=tk.BOTH, expand=True)
    
    # Title
    title_label = ttk.Label(main_frame, text="API Cost Summary", 
                           font=('Arial', 14, 'bold'))
    title_label.pack(pady=(0, 10))
    
    # Create tabbed interface
    notebook = ttk.Notebook(main_frame)
    notebook.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
    
    # ============================================================
    # Tab 1: Pricing Info
    # ============================================================
    pricing_frame = ttk.Frame(notebook, padding=10)
    notebook.add(pricing_frame, text="💰 Pricing Info")
    
    # Create a text widget with clickable links
    pricing_text = tk.Text(pricing_frame, wrap=tk.WORD, font=('Arial', 10),
                           cursor="arrow", padx=10, pady=10)
    pricing_scrollbar = ttk.Scrollbar(pricing_frame, orient=tk.VERTICAL, 
                                      command=pricing_text.yview)
    pricing_text.configure(yscrollcommand=pricing_scrollbar.set)
    pricing_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    pricing_text.pack(fill=tk.BOTH, expand=True)
    
    # Configure tags for styling
    pricing_text.tag_configure("title", font=('Arial', 12, 'bold'), foreground='#2c3e50')
    pricing_text.tag_configure("provider", font=('Arial', 11, 'bold'), 
                               foreground='#16537E', spacing1=15)
    pricing_text.tag_configure("model", font=('Courier New', 10), foreground='#333333')
    pricing_text.tag_configure("note", font=('Arial', 9, 'italic'), foreground='#7f8c8d')
    
    # Build pricing content with clickable links
    pricing_text.insert(tk.END, "\nAPI PRICING REFERENCE\n", "title")
    pricing_text.insert(tk.END, "═" * 60 + "\n\n", "note")
    
    # Add explanation of what tokens mean
    pricing_text.insert(tk.END, "WHAT DOES '1 MILLION TOKENS' MEAN?\n", "provider")
    pricing_text.insert(tk.END, "─" * 55 + "\n", "note")
    pricing_text.insert(tk.END, """A 'token' is roughly ¾ of a word (or about 4 characters).

1 million tokens ≈ 750,000 words ≈ 1,500 pages of text

Practical examples:
 • A 2-hour interview transcript (~15,000 words) uses ~20,000 tokens
 • Summarizing that transcript might cost $0.01 - $0.10 depending on model
 • You could process 50+ such transcripts for about $1-$5

Input tokens = what you send (your document + prompt)
Output tokens = what the AI returns (usually much smaller)
\n""", "model")
    
    # Add note about local AI
    pricing_text.insert(tk.END, "🏠 FREE ALTERNATIVE: LOCAL AI (OLLAMA)\n", "provider")
    pricing_text.insert(tk.END, "─" * 55 + "\n", "note")
    pricing_text.insert(tk.END, """The prices below apply to cloud-based AI providers.

If your system has sufficient resources, you can use Ollama
to run AI models locally on your computer at NO COST.

Ollama is a free application that lets you download and run
open-source AI models. Available models include:

 • Lightweight (8GB RAM):  Llama 3.2:1b, Gemma2:2b, Phi-3 Mini
 • Balanced (16GB RAM):    Llama 3.1:8b, Mistral 7B, Gemma2:9b ← Recommended
 • Powerful (32GB+ RAM):   Llama 3.1:70b, Qwen2.5:32b, Mixtral
 • Specialized:            DeepSeek-Coder, CodeLlama, LLaVA (vision)

⚠️ Quality note: Models under 7B parameters may struggle with long
   documents. For reliable summaries of lengthy transcripts, use
   Llama 3.1:8b or larger, or choose a cloud provider.

To manage local models in DocAnalyser:
  Settings → Ollama section → Manage Models

The Model Manager will recommend models based on your system's
RAM and GPU capabilities.

Download Ollama from: https://ollama.com
\n""", "model")
    
    pricing_text.insert(tk.END, "Note: Prices change frequently. Click links for current pricing.\n", "note")
    pricing_text.insert(tk.END, "All prices shown are per 1 million tokens.\n\n", "note")
    
    # Provider colors for visual distinction
    provider_icons = {
        "Anthropic (Claude)": "🟣",
        "OpenAI (ChatGPT)": "🟢",
        "Google (Gemini)": "🔵",
        "xAI (Grok)": "⚫",
        "DeepSeek": "🟠",
        "Ollama (Local)": "🏠"
    }
    
    for provider, models in PRICING.items():
        icon = provider_icons.get(provider, "•")
        pricing_text.insert(tk.END, f"\n{icon} {provider}\n", "provider")
        pricing_text.insert(tk.END, "─" * 55 + "\n", "note")
        
        # Header
        header = f"{'Model':<28} {'Input':>10} {'Output':>10}\n"
        pricing_text.insert(tk.END, header, "model")
        pricing_text.insert(tk.END, "-" * 50 + "\n", "note")
        
        # Model prices
        for model, prices in models.items():
            line = f"{model:<28} ${prices['input']:>8.2f} ${prices['output']:>8.2f}\n"
            pricing_text.insert(tk.END, line, "model")
        
        # Add clickable link
        url = PRICING_URLS.get(provider, "")
        if url:
            pricing_text.insert(tk.END, "\n📎 Official Pricing: ", "note")
            
            # Create unique tag for this link
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
    
    # Footer
    pricing_text.insert(tk.END, "\n" + "═" * 60 + "\n", "note")
    pricing_text.insert(tk.END, "⚠️ Prices shown are approximate and may have changed.\n", "note")
    pricing_text.insert(tk.END, "   Always check official pricing pages for current rates.\n", "note")
    pricing_text.insert(tk.END, f"   Last updated: February 2026\n", "note")
    
    pricing_text.config(state=tk.DISABLED)
    
    # ============================================================
    # Read cost log for other tabs
    # ============================================================
    cost_log_path = get_cost_log_path()
    success, entries, cost_by_provider, cost_by_model, total_cost = read_cost_log()
    
    if not success or not entries:
        # No log - add simple info tab
        no_log_frame = ttk.Frame(notebook, padding=10)
        notebook.add(no_log_frame, text="📊 Summary")
        
        ttk.Label(no_log_frame, text="No cost log found", 
                 font=('Arial', 12)).pack(pady=20)
        ttk.Label(no_log_frame, 
                 text=f"Expected location:\n{cost_log_path}\n\n"
                      "Cost logging will begin with your next API call.",
                 justify=tk.LEFT).pack(pady=10)
    else:
        # ============================================================
        # Tab 2: Summary
        # ============================================================
        summary_frame = ttk.Frame(notebook, padding=10)
        notebook.add(summary_frame, text="📊 Summary")
        
        stats_text = scrolledtext.ScrolledText(summary_frame, wrap=tk.WORD, 
                                               font=('Courier New', 10))
        stats_text.pack(fill=tk.BOTH, expand=True)
        
        summary_content = f"""═══════════════════════════════════════════════════════
                API COSTS SUMMARY
═══════════════════════════════════════════════════════

📊 TOTAL COST: ${total_cost:.4f}

═══════════════════════════════════════════════════════
💳 COST BY PROVIDER
═══════════════════════════════════════════════════════
"""
        
        for provider, cost in sorted(cost_by_provider.items(), key=lambda x: -x[1]):
            percentage = (cost / total_cost * 100) if total_cost > 0 else 0
            summary_content += f"\n{provider:20s} ${cost:>8.4f}  ({percentage:5.1f}%)"
        
        summary_content += f"""

═══════════════════════════════════════════════════════
🤖 COST BY MODEL
═══════════════════════════════════════════════════════
"""
        
        for model, cost in sorted(cost_by_model.items(), key=lambda x: -x[1]):
            percentage = (cost / total_cost * 100) if total_cost > 0 else 0
            summary_content += f"\n{model:30s} ${cost:>8.4f}  ({percentage:5.1f}%)"
        
        avg_cost = (total_cost / len(entries)) if entries else 0
        summary_content += f"""

═══════════════════════════════════════════════════════
📈 STATISTICS
═══════════════════════════════════════════════════════

Total API Calls:        {len(entries)}
Average Cost per Call:  ${avg_cost:.4f}
Log File Location:      {cost_log_path}
"""
        
        stats_text.insert('1.0', summary_content)
        stats_text.config(state=tk.DISABLED)
        
        # ============================================================
        # Tab 3: Detailed Log
        # ============================================================
        details_frame = ttk.Frame(notebook, padding=10)
        notebook.add(details_frame, text="📋 Detailed Log")
        
        details_text = scrolledtext.ScrolledText(details_frame, wrap=tk.NONE, 
                                                 font=('Courier New', 9))
        details_text.pack(fill=tk.BOTH, expand=True)
        
        header = f"{'Timestamp':<20} | {'Provider':<12} | {'Model':<30} | {'Cost':>10}\n"
        header += "-" * 80 + "\n"
        details_text.insert('1.0', header)
        
        for entry in reversed(entries):
            line = f"{entry['timestamp']:<20} | {entry['provider']:<12} | {entry['model']:<30} | ${entry['cost']:>9.4f}\n"
            details_text.insert(tk.END, line)
        
        details_text.config(state=tk.DISABLED)
        
        # ============================================================
        # Tab 4: Raw Log
        # ============================================================
        raw_frame = ttk.Frame(notebook, padding=10)
        notebook.add(raw_frame, text="📄 Raw Log")
        
        raw_text = scrolledtext.ScrolledText(raw_frame, wrap=tk.NONE, 
                                             font=('Courier New', 9))
        raw_text.pack(fill=tk.BOTH, expand=True)
        
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
    
    if cost_log_path.exists():
        def open_log():
            if os.name == 'nt':
                os.startfile(str(cost_log_path))
            else:
                os.system(f'open "{cost_log_path}"')
        
        ttk.Button(button_frame, text="Open Log File", 
                  command=open_log).pack(side=tk.LEFT, padx=5)
    
    ttk.Button(button_frame, text="Close", 
              command=costs_window.destroy).pack(side=tk.RIGHT, padx=5)
