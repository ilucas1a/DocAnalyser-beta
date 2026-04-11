# 09 - Platform Utilities (Content Fetching)

## Overview
Eight modules handling content extraction from various web platforms and podcast sources. Each follows a consistent pattern: URL detection → content fetch → transcript/text extraction, with audio fallback where applicable.

---

## youtube_utils.py (~450 lines)
**Purpose:** YouTube transcript fetching with multi-strategy approach and audio fallback.

**Key Functions:**
- **`extract_video_id(url_or_id)`** — Parses all YouTube URL formats (watch, youtu.be, embed, live, shorts) + bare 11-char IDs.
- **`is_youtube_url(url)`** — Quick domain check.
- **`fetch_youtube_transcript(url_or_id, use_cookies=False)`** — Main transcript fetcher with 4 strategies:
  1. English preference via `YouTubeTranscriptApi.fetch()`
  2. No language restriction
  3. List all transcripts, prefer English → manual → any
  4. Retry with browser cookies if blocked (bot detection)
  - Gets video title + upload date via yt-dlp
  - Pre-formats timestamps using `utils.format_timestamp()` to prevent "Page" bug
  - Returns: `(success, entries, title, source_type, metadata)`
- **`fetch_youtube_with_audio_fallback(url, api_key, engine, options, ...)`** — Tries transcript first, falls back to `audio_handler.transcribe_youtube_audio()`. Handles cookie extraction for yt-dlp. Provides detailed error messages for DPAPI, 403, and bot-block errors.
- **`get_youtube_transcript(url, status_callback)`** — Simplified interface returning dict with text/title/entries.

**Cookie Handling:**
- `_get_browser_cookies_file()` — Uses yt-dlp to extract cookies from Chrome/Firefox/Edge/Brave/Opera/Chromium
- `_load_cookies_for_transcript_api(cookie_file)` — Converts Netscape cookie jar for youtube_transcript_api

**Dependencies:** `re`, `youtube_transcript_api`, `yt_dlp`, `utils.format_timestamp`

---

## substack_utils.py (~450 lines)
**Purpose:** Substack transcript scraping using Selenium browser automation.

**Key Functions:**
- **`is_substack_url(url)`** — Domain check for substack.com
- **`get_webdriver(headless=True)`** — Auto-detects and creates WebDriver: Chrome → Edge → Firefox fallback. Returns (driver, browser_name).
- **`fetch_substack_transcript(url)`** — Opens page in headless browser, finds and clicks transcript button (XPath search for "transcript" text), waits for content, scrapes text, parses into entries. Returns standard 5-tuple.
- **`parse_transcript_text(text)`** — Handles two Substack formats:
  - Separate lines: timestamp on one line, text on next
  - Inline: `[0:13] Hi, Glenn...`
  - Converts timestamps to seconds, filters entries < 10 chars

**Dependencies:** `selenium`, `re`

---

## substack_updates.py (~180 lines)
**Purpose:** Updated/replacement code for Substack content fetching (non-Selenium approach).

**Key Functions:**
- **`fetch_substack_content(url, status_callback)`** — Fast version that extracts text without downloading media:
  1. Fetches page HTML
  2. Extracts preloads data, title, media detection (video/podcast/embedded)
  3. Priority: on-page transcript → API transcript → article text
  4. Returns result dict with `entries`, `text`, `has_audio_video`, `media_info`, `needs_transcription`
- **`download_substack_media(url, media_info, status_callback)`** — Separate download step (called only if user confirms). Tries: yt-dlp on URL → embedded URLs → direct video API → direct podcast URL.

**Note:** This file appears to be replacement/update code referencing helper functions not included in this file (like `extract_preloads_from_html`, `extract_substack_publication`, etc.) — likely defined in the main substack_utils.py or intended to be merged.

---

## twitter_utils.py (~450 lines)
**Purpose:** X/Twitter content fetching with multi-strategy approach.

**Key Functions:**
- **`is_twitter_url(url)`** — Checks twitter.com/x.com domains + /status/ path.
- **`extract_tweet_info(url)`** — Extracts username and tweet_id from URL.
- **`fetch_twitter_content(url, progress_callback)`** — Three strategies:
  1. **FxTwitter API** — JSON API at api.fxtwitter.com (most reliable for text + video detection)
  2. **yt-dlp** — Metadata extraction, especially good for video detection
  3. **Nitter instances** — Fallback for text from privacy-focused Twitter frontends
  - Returns result dict with: text, has_video, video_url, video_duration, author info, formatted_text
- **`extract_text_from_nitter(html)`** — Parses tweet-content from Nitter HTML.
- **`download_twitter_video(url, progress_callback)`** — Downloads via yt-dlp with FFmpeg audio extraction, falls back to video download.

**Dependencies:** `re`, `requests`, `yt_dlp`, `tempfile`

---

## facebook_utils.py (~500 lines)
**Purpose:** Facebook video/reel audio extraction and transcription.

**Key Functions:**
- **`is_facebook_video_url(url)`** — Detects reel, watch, share/v, share/r, fb.watch URLs.
- **`get_facebook_metadata(url, status_callback)`** — Uses yt-dlp to get title, description, uploader, duration, thumbnail.
- **`extract_facebook_audio(url, output_dir, status_callback)`** — Downloads audio via yt-dlp with FFmpeg extraction to MP3 192kbps. Progress hook shows download percentage.
- **`transcribe_audio_openai(audio_path, api_key, status_callback)`** — OpenAI Whisper transcription (25MB limit).
- **`transcribe_audio_assemblyai(audio_path, api_key, status_callback)`** — AssemblyAI upload → transcribe → poll workflow.
- **`fetch_facebook_content(url, openai_api_key, assemblyai_api_key, ...)`** — Full pipeline: metadata → audio extraction → transcription → formatted result. Cleans up temp files.

**Dependencies:** `yt_dlp`, `requests`, `openai`, `tempfile`

---

## video_platform_utils.py (~50 lines)
**Purpose:** Stub module for detecting URLs from other video platforms.

**Key Functions:**
- **`is_video_platform_url(url)`** — Checks for Vimeo, Rumble, Dailymotion, BitChute, Odysee, LBRY, Brighteon, Banned.video.
- **`get_video_platform_name(url)`** — Returns human-readable platform name.

**Note:** Detection only — no actual content fetching implemented. Serves as a placeholder for future platform support.

---

## podcast_handler.py (~400 lines)
**Purpose:** Podcast URL resolution and episode extraction. Resolves Apple Podcasts URLs to RSS feeds, finds episodes, and downloads audio for transcription.

**Supports:**
- Apple Podcasts URLs (podcasts.apple.com/...)
- Direct RSS feed URLs (.rss, .xml, known feed hosts)
- Direct MP3/audio URLs (passed through to audio pipeline)

**Architecture:** Apple Podcasts URL → iTunes Lookup API → RSS feed URL → feedparser → MP3 URL → download

**Key Exports:**
- `is_podcast_url(url)` → bool — detects Apple Podcasts and RSS feed URLs
- `resolve_podcast_episode(url, status_callback)` → PodcastEpisode — resolves URL to episode metadata
- `download_podcast_audio(episode, output_dir, status_callback)` → filepath — downloads episode audio
- `PodcastEpisode` — dataclass with title, audio_url, duration, description, etc.

**Dependencies:** `re`, `os`, `json`, `tempfile`, `feedparser`, `requests`
**Called By:** smart_load.py, document_fetching.py

---

## podcast_browser_dialog.py (~500 lines)
**Purpose:** Tkinter dialog for browsing podcast episodes from an RSS feed. Displays episode list with search/filter, multi-select, and podcast favourites.

**Key Function:**
- `open_podcast_browser(parent, url, config, save_config_callback)` → (list, dict) — returns selected PodcastEpisode objects and podcast info

**Features:**
- Episode list with title, date, duration
- Search/filter within episodes
- Multi-select for batch processing
- Save podcast to favourites (persisted in config)

**Dependencies:** `tkinter`, `podcast_handler`, `feedparser`
**Called By:** smart_load.py, document_fetching.py

---

## turboscribe_helper.py — REMOVED
**Note:** This module no longer exists as a standalone file. TurboScribe integration (export and import) is handled inline within `export_utilities.py` (`send_to_turboscribe()`, `import_turboscribe()`).

---

---

## google_drive_handler.py (~290 lines)
**Purpose:** Google Drive API integration — OAuth 2.0 authentication, file listing, downloading, and uploading. All API calls are wrapped in an optional-dependency guard so the rest of DocAnalyser runs normally if the Google packages are absent.

**Availability guard:**
```python
try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    ...
    GDRIVE_AVAILABLE = True
except ImportError:
    GDRIVE_AVAILABLE = False
```

**Credentials & token paths** (both in `%APPDATA%\DocAnalyser_Beta\`):
- `gdrive_credentials.json` — OAuth client secret downloaded from Google Cloud Console. User must supply this manually.
- `gdrive_token.json` — Saved access/refresh token. Written automatically after first sign-in; refreshed silently on subsequent launches.

**Scopes:**
- `drive.readonly` — read any Drive file
- `drive.file` — create/write files this app created

**SSL bypass:** Uses `httplib2.Http(disable_ssl_certificate_validation=True)` and `requests` with `verify=False` for download calls. Required when Kaspersky (or similar security software) intercepts googleapis.com traffic and replaces Google's certificate with its own.

**Key Class — `GoogleDriveHandler`:**

| Method | Purpose |
|---|---|
| `is_available()` | True if Google API packages are installed |
| `has_credentials_file()` | True if `gdrive_credentials.json` exists |
| `is_authenticated()` | True if signed in with a valid token |
| `get_account_email()` | Returns signed-in user's email via `about().get()` |
| `authenticate(force_new=False)` | OAuth flow: load saved token → refresh if expired → full browser auth if needed. Returns `(success, error_message)` |
| `sign_out()` | Clears credentials and deletes `gdrive_token.json` |
| `list_files(folder_id)` | Lists files/folders in a Drive folder, paginated, folders first |
| `list_shared_with_me()` | Lists files shared with the authenticated user |
| `search_files(query_text)` | Full-text name search across My Drive |
| `get_file_metadata(file_id)` | Returns metadata dict for one file |
| `download_file(file_id, dest_path, ...)` | Downloads binary or native Google file. Exports Docs→.docx, Sheets→.xlsx, Slides→.pptx via `GDRIVE_EXPORT_MAP`. Uses `requests` with streaming and progress callback. Returns `(True, dest_path)` or `(False, error)` |
| `upload_file(local_path, ...)` | Uploads via resumable `MediaFileUpload`. Returns `(True, file_id, None)` or `(False, None, error)` |
| `create_folder(name, parent_id)` | Creates a Drive folder, returns new folder ID |

**Module-level singleton:**
```python
_handler_instance = None
def get_gdrive_handler(data_dir=None) -> GoogleDriveHandler
```
First call creates the instance; subsequent calls return the cached one.

**Dependencies:** `google.oauth2.credentials`, `google_auth_oauthlib.flow`, `google.auth.transport.requests`, `googleapiclient`, `httplib2`, `google_auth_httplib2`, `requests`  
**Called By:** `google_drive_dialog.py`

---

## google_drive_dialog.py (~500 lines)
**Purpose:** Tkinter dialog providing a full Google Drive file browser within DocAnalyser. Non-modal Toplevel, 740×560.

**Entry point:**
```python
open_google_drive_dialog(parent, app)  # returns GoogleDriveDialog instance
```

**UI layout:**
- **Top bar:** title, status label (shows signed-in email in green), Sign in/Sign out button
- **Setup panel:** shown when credentials file is missing or packages absent. Includes step-by-step instructions, Open Setup Guide button (links to Google quickstart), and Check Again button
- **Browse panel:** shown when authenticated. Contains:
  - Breadcrumb navigation with Back, My Drive, Shared with Me buttons
  - Search row with entry field + Search / Clear buttons
  - `ttk.Treeview` with columns: Name, Type, Size, Modified — multi-select enabled (Ctrl+A, Ctrl+click)
  - Info bar showing item counts
- **Bottom bar:** Open Files, Open Folder(s), Upload Output to Drive, Close buttons

**Key behaviours:**

| Feature | Detail |
|---|---|
| Authentication | Delegates entirely to `GoogleDriveHandler.authenticate()`. Browser tab opens on first use. |
| Folder navigation | `_folder_stack` list maintains breadcrumb history. `_load_folder()` / `_nav_back()` / `_go_root()` / `_go_shared()` |
| Batch download | Up to 5 concurrent downloads via `threading.Semaphore(5)`. Each file gets a per-file temp subfolder (`da_gdrive_{id}/filename`) so original filenames are preserved |
| Open single file | Calls `app._load_downloaded_gdrive_file(path)` |
| Open multiple files | Calls `app._process_multiple_inputs(paths)` |
| Open folder(s) | Lists all files in selected folders (non-recursive), then batch-downloads and opens them all |
| Upload output | Reads `app.output_text`, writes to a temp `.txt` file, uploads to current Drive folder via `handler.upload_file()` |
| Google native files | `.gdoc`/`.gsheet`/`.gslides` are automatically exported to `.docx`/`.xlsx`/`.pptx` by the download handler |

**Dependencies:** `tkinter`, `threading`, `tempfile`, `google_drive_handler`  
**Called By:** `Main.py` (via toolbar/settings button — wiring in Main.py)

---

## Common Patterns Across Platform Modules
- **Consistent return signatures:** Most return `(success, result/error, title, source_type, metadata)` tuples
- **Progressive fallback:** Each module tries multiple strategies in priority order
- **Status callbacks:** All accept optional `progress_callback` / `status_callback` for UI updates
- **Cookie handling:** YouTube and Substack handle browser cookies for authenticated access
- **yt-dlp as backbone:** YouTube, Twitter, Facebook, and Substack all leverage yt-dlp for media download
- **Graceful import failures:** Each module checks for optional dependencies at module level
