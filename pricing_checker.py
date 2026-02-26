"""
pricing_checker.py - Weekly AI Model Pricing Monitor
=====================================================
Checks each AI provider's pricing in pricing.json is still current
by asking Google Gemini Flash to verify prices from its knowledge
and Google Search grounding (so it can look up current prices
in real-time rather than relying on stale training data).

This approach is MUCH more reliable than trying to scrape JS-rendered
pricing pages with the requests library. Gemini has access to current
pricing data from its training and can cross-reference multiple sources.

Usage:
    python pricing_checker.py              # Run check and email report
    python pricing_checker.py --dry-run    # Run check, print report, don't email
    python pricing_checker.py --test-email # Send a test email to verify setup
    python pricing_checker.py --debug      # Dump raw API response for 1st provider

    Flags can be combined: python pricing_checker.py --dry-run --debug

Setup: See README_pricing_checker.md
"""

import json
import sys
import os
import re
import smtplib
import datetime
import requests
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from typing import Dict, List, Tuple, Optional


# ============================================================
# CONFIGURATION
# ============================================================

SCRIPT_DIR = Path(__file__).parent
CONFIG_PATH = SCRIPT_DIR / "pricing_checker_config.json"
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

# Enable Google Search grounding so Gemini can look up CURRENT pricing
# rather than relying on (potentially stale) training data.
# Free tier: 500 grounded requests/day for Flash — we only need ~5 per run.
USE_GOOGLE_SEARCH_GROUNDING = True

# Providers to skip (no meaningful pricing to check)
SKIP_PROVIDERS = ["Ollama (Local)"]

# Delay between AI calls — Gemini free tier throttles grounded requests
# more aggressively than regular calls. 30s keeps us well within limits.
DELAY_BETWEEN_AI_CALLS = 30

# Max retries for rate-limited AI calls
MAX_RETRIES = 3
RETRY_BACKOFF = 30  # seconds to wait after a 429 error


# Reference URLs for each provider (shown in reports for manual checking)
PROVIDER_REFERENCE_URLS = {
    "OpenAI (ChatGPT)": "https://openai.com/api/pricing",
    "Anthropic (Claude)": "https://www.anthropic.com/pricing",
    "Google (Gemini)": "https://ai.google.dev/gemini-api/docs/pricing",
    "xAI (Grok)": "https://docs.x.ai/developers/models",
    "DeepSeek": "https://api-docs.deepseek.com/quick_start/pricing"
}


def load_config() -> dict:
    """Load configuration from JSON file."""
    if not CONFIG_PATH.exists():
        print(f"ERROR: Config file not found: {CONFIG_PATH}")
        print("Please copy pricing_checker_config.json and fill in your details.")
        print("See README_pricing_checker.md for setup instructions.")
        sys.exit(1)

    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        config = json.load(f)

    # Validate required fields
    if config.get("gemini_api_key", "").startswith("YOUR_"):
        print("ERROR: Please set your Gemini API key in pricing_checker_config.json")
        sys.exit(1)

    email_cfg = config.get("email", {})
    if email_cfg.get("sender", "").startswith("YOUR_"):
        print("ERROR: Please set your Gmail address in pricing_checker_config.json")
        sys.exit(1)

    return config


def load_current_pricing(config: dict) -> dict:
    """Load the current pricing.json file."""
    pricing_path = (SCRIPT_DIR / config.get("pricing_json_path", "../pricing.json")).resolve()
    if not pricing_path.exists():
        print(f"ERROR: pricing.json not found at: {pricing_path}")
        sys.exit(1)

    with open(pricing_path, 'r', encoding='utf-8') as f:
        return json.load(f)


# ============================================================
# AI-BASED PRICING VERIFICATION (Gemini Flash)
# ============================================================

def _redact_key(text: str, api_key: str) -> str:
    """Remove API key from error messages to prevent leaking it in reports."""
    return text.replace(api_key, "[REDACTED]")


def verify_pricing_with_ai(provider_name: str, current_models: dict,
                           api_key: str, provider_url: str,
                           debug: bool = False) -> str:
    """
    Ask Gemini Flash to verify whether our stored pricing is still current.
    Gemini uses Google Search grounding to look up current published prices
    in real-time, then compares against our stored data.
    Returns the AI's analysis as text.
    """
    # Build a readable summary of our stored pricing
    model_lines = []
    for model, prices in current_models.items():
        model_lines.append(
            f"  {model}: input=${prices['input']}/M tokens, "
            f"output=${prices['output']}/M tokens"
        )
    current_summary = "\n".join(model_lines)

    prompt = f"""You are a pricing analyst. I maintain a file of AI API pricing for my
application. I need you to verify whether my stored prices are still accurate for
{provider_name}.

My stored pricing data (all prices per 1 MILLION tokens, USD):
{current_summary}

Official pricing reference: {provider_url}

IMPORTANT: Please use Google Search to look up the CURRENT published API pricing
for {provider_name} as of today ({datetime.datetime.now().strftime('%B %Y')}). 
Do NOT rely on your training data alone, as model names and prices change frequently.
Search for "{provider_name} API pricing per million tokens" or visit {provider_url}.

Then:

1. VERIFY each model's pricing — is it still correct?
2. IDENTIFY any models where my stored price is WRONG and state the correct price.
3. IDENTIFY any significant NEW models that {provider_name} has released that 
   are NOT in my list. Only include text/chat completion models relevant to 
   document analysis. SKIP: embedding models, fine-tuning prices, image 
   generation, audio/speech, TTS, moderation, and deprecated models.
4. IDENTIFY any models in my list that have been DISCONTINUED or removed.

IMPORTANT NOTES:
- My prices are STANDARD tier (not batch, not cached, not long-context).
- For providers with tiered pricing (e.g. different price above/below 200K tokens),
  compare against the standard tier (<=200K tokens).
- "Cache hit" or "batch" prices are NOT standard prices — ignore those.
- If you are not certain about a specific model's price, say so rather than guessing.
- IGNORE trivial decimal formatting differences like $2.5 vs $2.50 or $0.075 vs
  $0.08 — these are NOT price changes. Only flag if the actual numerical value differs.
- Do NOT include citation markers like [cite: X] or [1] in your response.
  Just state the facts plainly.

Format your response EXACTLY as follows:

CHANGES DETECTED: Yes/No

PRICE CHANGES:
- [model]: input should be $X (I have $Y), output should be $X (I have $Y)
(or "None detected")

NEW MODELS TO ADD:
- [model]: input=$X/M tokens, output=$Y/M tokens
(or "None found")

MODELS TO REMOVE:
- [model]: [reason — discontinued, renamed, etc.]
(or "None")

CONFIDENCE: High/Medium/Low
NOTES: [any caveats, uncertainties, or recommendations]
"""

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.post(
                f"{GEMINI_API_URL}?key={api_key}",
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "tools": [{"google_search": {}}] if USE_GOOGLE_SEARCH_GROUNDING else [],
                    "generationConfig": {
                        "temperature": 0.1,
                        "maxOutputTokens": 8000
                    }
                },
                timeout=120
            )
            response.raise_for_status()
            data = response.json()

            # In debug mode, dump the raw response structure
            if debug:
                print("\n    === DEBUG: Raw API response structure ===")
                # Show keys at each level, plus grounding info
                print(f"    Top-level keys: {list(data.keys())}")
                candidates = data.get("candidates", [{}])
                if candidates:
                    print(f"    Candidate keys: {list(candidates[0].keys())}")
                    content = candidates[0].get("content", {})
                    print(f"    Content keys: {list(content.keys())}")
                    parts = content.get("parts", [])
                    print(f"    Parts count: {len(parts)}")
                    for i, p in enumerate(parts):
                        print(f"    Part {i} keys: {list(p.keys())}")
                        if "text" in p:
                            print(f"    Part {i} text: {p['text'][:200]}...")
                    gm = candidates[0].get("groundingMetadata", {})
                    if gm:
                        print(f"    groundingMetadata keys: {list(gm.keys())}")
                        print(f"    webSearchQueries: {gm.get('webSearchQueries', 'NOT PRESENT')}")
                        chunks = gm.get('groundingChunks', [])
                        print(f"    groundingChunks count: {len(chunks)}")
                        if chunks:
                            print(f"    First chunk: {json.dumps(chunks[0], indent=2)[:300]}")
                    else:
                        print("    groundingMetadata: NOT PRESENT")
                print("    === END DEBUG ===")

            # Check if Google Search grounding was actually used
            candidates = data.get("candidates", [])
            if candidates:
                grounding_meta = candidates[0].get("groundingMetadata", {})
                search_queries = grounding_meta.get("webSearchQueries", [])
                grounding_chunks = grounding_meta.get("groundingChunks", [])

                if USE_GOOGLE_SEARCH_GROUNDING:
                    if search_queries:
                        print(f"    ✅ Google Search grounding active "
                              f"({len(search_queries)} searches, "
                              f"{len(grounding_chunks)} source chunks)")
                    else:
                        print(f"    ⚠️  Google Search grounding was requested "
                              f"but no search queries found in response")

                # Extract text — may be spread across multiple parts
                parts = candidates[0].get("content", {}).get("parts", [])
                text_parts = [p.get("text", "") for p in parts if "text" in p]
                if text_parts:
                    result = "\n".join(text_parts)
                    # Clean up citation markers that grounding sometimes injects
                    result = re.sub(r'\[cite:\s*[\d,\s]*\]', '', result)
                    result = re.sub(r'\[\d+(?:,\s*\d+)*\]', '', result)
                    # Remove duplicate response blocks (grounding can echo)
                    # If the response contains the format header twice, keep only the last
                    parts_split = result.split('CHANGES DETECTED:')
                    if len(parts_split) > 2:
                        # Keep the last complete block
                        result = 'CHANGES DETECTED:' + parts_split[-1]
                    return result.strip()

            return "ERROR: Unexpected response format from Gemini"

        except requests.exceptions.HTTPError as e:
            body = ""
            try:
                status = e.response.status_code if e.response else 0
                body = e.response.text[:300] if e.response else str(e)
            except Exception:
                status = 0
                body = str(e)

            # Fallback: parse status from exception text if response was None
            if status == 0:
                import re as _re
                match = _re.search(r'(\d{3})\s+(Client|Server) Error', str(e))
                if match:
                    status = int(match.group(1))
                    body = str(e)[:300]

            if status in (0, 429, 500, 502, 503) and attempt < MAX_RETRIES:
                # 429 = rate limited, need to wait longer
                wait = (RETRY_BACKOFF * 2 * attempt) if status == 429 else (RETRY_BACKOFF * attempt)
                print(f"    HTTP {status} error: {body[:100]}")
                print(f"    Waiting {wait}s before retry "
                      f"{attempt + 1}/{MAX_RETRIES}...")
                time.sleep(wait)
                continue
            detail = f" — {body[:200]}" if body else ""
            return _redact_key(
                f"ERROR: Gemini API error (HTTP {status}) after "
                f"{attempt} attempt(s){detail}",
                api_key
            )
        except requests.exceptions.SSLError as e:
            return _redact_key(f"ERROR: SSL error connecting to Gemini: {e}", api_key)
        except requests.exceptions.ConnectionError as e:
            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF * attempt
                print(f"    Connection error: {str(e)[:100]}")
                print(f"    Waiting {wait}s before retry "
                      f"{attempt + 1}/{MAX_RETRIES}...")
                time.sleep(wait)
                continue
            return _redact_key(
                f"ERROR: Connection failed after {attempt} attempt(s): {str(e)[:200]}",
                api_key
            )
        except requests.exceptions.ReadTimeout as e:
            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF * attempt
                print(f"    Read timeout (Gemini took too long to respond)")
                print(f"    Waiting {wait}s before retry "
                      f"{attempt + 1}/{MAX_RETRIES}...")
                time.sleep(wait)
                continue
            return _redact_key(
                f"ERROR: Gemini timed out after {attempt} attempt(s)",
                api_key
            )
        except Exception as e:
            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF * attempt
                print(f"    {type(e).__name__}: {str(e)[:100]}")
                print(f"    Waiting {wait}s before retry...")
                time.sleep(wait)
                continue
            return _redact_key(
                f"ERROR: {type(e).__name__}: {str(e)[:200]}",
                api_key
            )

    return "ERROR: All retries exhausted"


# ============================================================
# REPORT GENERATION
# ============================================================

def run_pricing_check(config: dict) -> Tuple[str, str, bool]:
    """
    Run the full pricing check across all providers.
    Returns (report_text, report_filename, changes_detected).
    """
    pricing_data = load_current_pricing(config)
    api_key = config["gemini_api_key"]
    providers = pricing_data.get("providers", {})

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    date_stamp = datetime.datetime.now().strftime("%Y-%m-%d")

    report_lines = []
    report_lines.append("=" * 70)
    report_lines.append("  DOCANALYSER PRICING MONITOR — WEEKLY REPORT")
    report_lines.append(f"  Generated: {timestamp}")
    report_lines.append(f"  Pricing file last updated: {pricing_data.get('_updated', 'Unknown')}")
    grounding = "with Google Search grounding" if USE_GOOGLE_SEARCH_GROUNDING else "training data only"
    report_lines.append(f"  Method: AI-based verification (Gemini Flash, {grounding})")
    report_lines.append("=" * 70)
    report_lines.append("")

    any_changes = False
    any_errors = False
    provider_results = []

    provider_list = [p for p in providers.keys() if p not in SKIP_PROVIDERS]

    for idx, provider_name in enumerate(provider_list):
        provider_data = providers[provider_name]
        models = provider_data.get("models", {})
        ref_url = PROVIDER_REFERENCE_URLS.get(
            provider_name, provider_data.get("url", "N/A")
        )

        print(f"\nVerifying {provider_name} ({idx + 1}/{len(provider_list)})...")
        report_lines.append("-" * 70)
        report_lines.append(f"  {provider_name}")
        report_lines.append(f"  Reference: {ref_url}")
        report_lines.append(f"  Models checked: {len(models)}")
        report_lines.append("-" * 70)
        report_lines.append("")

        # Ask Gemini to verify pricing (with Google Search grounding)
        analysis = verify_pricing_with_ai(
            provider_name, models, api_key, ref_url,
            debug=("--debug" in sys.argv and idx == 0)
        )

        if analysis.startswith("ERROR:"):
            report_lines.append(f"  ❌ AI VERIFICATION ERROR:")
            report_lines.append(f"  {analysis}")
            report_lines.append("")
            any_errors = True
            provider_results.append((provider_name, "AI ERROR"))
        else:
            report_lines.append(analysis)
            report_lines.append("")

            # Determine result
            analysis_upper = analysis.upper()
            if "CHANGES DETECTED: YES" in analysis_upper:
                any_changes = True
                provider_results.append((provider_name, "CHANGES DETECTED"))
            elif "ERROR" in analysis_upper:
                provider_results.append((provider_name, "POSSIBLE ERROR"))
                any_errors = True
            else:
                provider_results.append((provider_name, "No changes"))

        # Space out AI calls to stay within free-tier rate limits
        if idx < len(provider_list) - 1:
            print(f"  Waiting {DELAY_BETWEEN_AI_CALLS}s before next provider...")
            time.sleep(DELAY_BETWEEN_AI_CALLS)

    # Build summary
    summary_lines = []
    summary_lines.append("")
    summary_lines.append("SUMMARY")
    summary_lines.append("=" * 40)

    if any_changes:
        summary_lines.append(
            "⚠️  PRICING CHANGES DETECTED — review details below"
        )
    else:
        summary_lines.append(
            "✅  No pricing changes detected across any provider"
        )

    if any_errors:
        summary_lines.append(
            "⚠️  Some providers had verification errors — review below"
        )

    summary_lines.append("")
    summary_lines.append("  NOTE: This report is generated by AI (Gemini Flash)")
    summary_lines.append("  and should be treated as an ALERT, not gospel.")
    summary_lines.append("  Gemini uses Google Search to look up current prices.")
    summary_lines.append("  Always verify flagged changes against the official")
    summary_lines.append("  pricing pages before updating pricing.json.")
    summary_lines.append("")

    for provider, result in provider_results:
        if "CHANGE" in result:
            icon = "⚠️"
        elif "ERROR" in result:
            icon = "❌"
        else:
            icon = "✅"
        summary_lines.append(f"  {icon}  {provider}: {result}")

    summary_lines.append("")
    summary_lines.append("  Reference URLs for manual verification:")
    for provider_name in provider_list:
        ref_url = PROVIDER_REFERENCE_URLS.get(provider_name, "N/A")
        summary_lines.append(f"    {provider_name}: {ref_url}")
    summary_lines.append("")
    summary_lines.append("")

    # Insert summary after header
    report_lines = report_lines[:7] + summary_lines + report_lines[7:]

    report_text = "\n".join(report_lines)
    report_filename = f"pricing_check_{date_stamp}.txt"

    return report_text, report_filename, any_changes


# ============================================================
# EMAIL
# ============================================================

def send_email(config: dict, report_text: str, report_filename: str,
               changes_detected: bool) -> bool:
    """Send the report via Gmail with the report as an attachment."""
    email_cfg = config["email"]
    sender = email_cfg["sender"]
    recipient = email_cfg.get("recipient", sender)  # Default: send to self
    app_password = email_cfg["gmail_app_password"]

    # Subject line indicates whether action is needed
    date_str = datetime.datetime.now().strftime("%d %b %Y")
    if changes_detected:
        subject = f"⚠️ DocAnalyser Pricing Changes Detected — {date_str}"
    else:
        subject = f"✅ DocAnalyser Pricing Check — No Changes — {date_str}"

    try:
        msg = MIMEMultipart()
        msg["From"] = sender
        msg["To"] = recipient
        msg["Subject"] = subject

        # Email body — brief summary
        if changes_detected:
            body = (
                "Pricing changes were detected for one or more AI providers.\n"
                "Please review the attached report and update pricing.json "
                "if needed.\n\n"
                "IMPORTANT: This report is AI-generated. Always verify "
                "flagged changes against official pricing pages before "
                "updating pricing.json.\n\n"
                "The full analysis is in the attached file."
            )
        else:
            body = (
                "Weekly pricing check complete. No changes detected.\n"
                "Full details in the attached report."
            )

        msg.attach(MIMEText(body, "plain"))

        # Attach the full report
        attachment = MIMEBase("application", "octet-stream")
        attachment.set_payload(report_text.encode("utf-8"))
        encoders.encode_base64(attachment)
        attachment.add_header(
            "Content-Disposition",
            f"attachment; filename={report_filename}"
        )
        msg.attach(attachment)

        # Send via Gmail SMTP
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(sender, app_password)
            server.send_message(msg)

        print(f"Email sent to {recipient}")
        return True

    except smtplib.SMTPAuthenticationError as e:
        print(f"ERROR: Gmail authentication failed.")
        print(f"  SMTP response: {e}")
        print(f"  Sender: {sender}")
        print(f"  App password length: {len(app_password)} chars")
        print(f"  App password format: {'xxxx xxxx xxxx xxxx' if len(app_password.split()) == 4 else 'UNEXPECTED FORMAT'}")
        print("\nCommon fixes:")
        print("  1. Regenerate your App Password at https://myaccount.google.com/apppasswords")
        print("  2. Make sure 2-Step Verification is ON for your Google account")
        print("  3. Check the password has no extra spaces at start/end")
        return False
    except Exception as e:
        print(f"ERROR sending email: {e}")
        return False


# ============================================================
# MAIN
# ============================================================

def main():
    print("DocAnalyser Pricing Monitor")
    print("=" * 40)

    dry_run = "--dry-run" in sys.argv
    test_email = "--test-email" in sys.argv
    debug = "--debug" in sys.argv

    if debug:
        print("DEBUG mode: will dump raw API response for first provider")

    config = load_config()

    if test_email:
        print("Sending test email...")
        test_report = (
            "This is a test email from the DocAnalyser Pricing Monitor.\n\n"
            f"Sent at: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            "If you received this, your email configuration is working correctly."
        )
        success = send_email(config, test_report, "pricing_check_TEST.txt",
                             changes_detected=False)
        if success:
            print("Test email sent successfully!")
        else:
            print("Test email failed — check your configuration.")
        return

    print("Loading pricing data...")
    report_text, report_filename, changes_detected = run_pricing_check(config)

    # Save report locally
    report_path = SCRIPT_DIR / report_filename
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report_text)
    print(f"\nReport saved: {report_path}")

    if dry_run:
        print("\n--- DRY RUN — Report follows ---\n")
        print(report_text)
        print("\n--- End of report (email not sent in dry-run mode) ---")
    else:
        print("Sending email...")
        send_email(config, report_text, report_filename, changes_detected)

    if changes_detected:
        print("\n⚠️  CHANGES DETECTED — check the report!")
    else:
        print("\n✅ No changes detected.")


if __name__ == "__main__":
    main()
