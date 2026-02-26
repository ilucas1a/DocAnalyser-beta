# DocAnalyser Pricing Monitor — Setup Guide

## What This Does

A Python script that checks each AI provider's pricing page weekly, compares it
against your current `pricing.json`, and emails you a report. It uses Google
Gemini Flash (the cheapest available model — less than 1 cent per run) to
intelligently read the pricing pages and detect changes.

## Files

| File | Purpose |
|------|---------|
| `pricing_checker.py` | The main script |
| `pricing_checker_config.json` | Your API key, email settings |
| `pricing_check_YYYY-MM-DD.txt` | Generated reports (one per run) |

## Setup (One-Time, ~10 Minutes)

### Step 1: Get a Gemini API Key

1. Go to https://aistudio.google.com/apikey
2. Sign in with your Google account
3. Click **Create API Key**
4. Copy the key (starts with `AIza...`)

### Step 2: Create a Gmail App Password

Google doesn't allow scripts to use your regular Gmail password. You need an
"App Password" — a special 16-character password just for this script.

1. Go to https://myaccount.google.com/apppasswords
   - If you don't see this option, you need to enable 2-Step Verification first:
     https://myaccount.google.com/signinoptions/two-step-verification
2. Under "App name", type: `DocAnalyser Pricing Monitor`
3. Click **Create**
4. Google will show you a 16-character password (like `abcd efgh ijkl mnop`)
5. Copy it — you won't be able to see it again

### Step 3: Edit the Config File

Open `pricing_checker_config.json` and fill in your details:

```json
{
    "gemini_api_key": "AIzaSy...(your Gemini key)",
    "email": {
        "sender": "yourname@gmail.com",
        "recipient": "yourname@gmail.com",
        "gmail_app_password": "abcd efgh ijkl mnop"
    },
    "pricing_json_path": "../pricing.json"
}
```

- **sender** and **recipient** can be the same address (send to yourself)
- **recipient** can be a different address if you prefer
- **gmail_app_password** — the 16-character password from Step 2 (spaces are fine)

### Step 4: Test It

Open a terminal in the maintenance folder and run:

```
cd C:\Ian\Python\GetTextFromYouTube\DocAnalyzer_DEV\maintenance

# First, test that email works:
python pricing_checker.py --test-email

# Then do a dry run (checks pricing but doesn't email):
python pricing_checker.py --dry-run

# Full run (checks pricing AND emails report):
python pricing_checker.py
```

## Usage

### Manual (Recommended to Start)

Run weekly from a terminal:

```
cd C:\Ian\Python\GetTextFromYouTube\DocAnalyzer_DEV\maintenance
python pricing_checker.py
```

### Automated via Windows Task Scheduler (Optional)

If you'd like it to run automatically every week:

1. Open **Task Scheduler** (search for it in the Start menu)
2. Click **Create Basic Task**
3. Name: `DocAnalyser Pricing Check`
4. Trigger: **Weekly** — pick a day (e.g. Monday morning)
5. Action: **Start a program**
6. Program: `C:\Ian\Python\GetTextFromYouTube\DocAnalyzer_DEV\.venv\Scripts\python.exe`
7. Arguments: `pricing_checker.py`
8. Start in: `C:\Ian\Python\GetTextFromYouTube\DocAnalyzer_DEV\maintenance`
9. Finish

The script will run silently in the background and email you the report.

## What the Email Looks Like

**Subject line tells you immediately if action is needed:**
- `✅ DocAnalyser Pricing Check — No Changes — 21 Feb 2026`
- `⚠️ DocAnalyser Pricing Changes Detected — 21 Feb 2026`

**The attached report** contains a per-provider breakdown showing:
- Price changes on existing models
- New models found on the pricing page
- Models that may have been removed
- Confidence level of each analysis

## What to Do When Changes Are Detected

1. Open the report and review the changes
2. Verify them against the provider's actual pricing page (the AI is good but not infallible)
3. Update `pricing.json` in the DocAnalyser_DEV folder
4. Push the updated `pricing.json` to GitHub
5. All users will pick up the new prices on their next app launch

## Troubleshooting

**"Gmail authentication failed"**
- Make sure you're using the App Password, not your regular Gmail password
- Make sure 2-Step Verification is enabled on your Google account
- Try generating a new App Password

**"Could not fetch pricing page"**
- The provider may have changed their URL — check if it still works in a browser
- Some providers use heavy JavaScript rendering; the script may not get all content
- The AI analysis will note when it has low confidence

**"Gemini API error"**
- Check your API key is correct
- Check you haven't hit the free tier limit (1,500 requests/day — this uses 5)

## Cost

Each run makes ~5 Gemini Flash API calls (one per provider). At current pricing
this costs well under $0.01 per run — roughly $0.50 per year if run weekly.
