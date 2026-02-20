# 09 - Platform Utilities (Content Fetching)

## Overview
Seven modules handling content extraction from various web platforms. Each follows a consistent pattern: URL detection → content fetch → transcript/text extraction, with audio fallback where applicable.

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

## turboscribe_helper.py (~400 lines)
**Purpose:** Integration helper for TurboScribe external transcription service (free tier: 3/day, 30 min each).

**Export Functions:**
- **`export_for_turboscribe(audio_path, destination_folder)`** — Copies audio to Desktop/TurboScribe_Uploads.
- **`open_turboscribe_website()`** — Opens turboscribe.ai in browser.

**Import/Parsing Functions:**
- **`parse_turboscribe_txt(file_path)`** — Parses `[HH:MM:SS] Speaker: Text` format.
- **`parse_turboscribe_docx(file_path)`** — Same pattern from Word docs (uses python-docx).
- **`parse_turboscribe_srt(file_path)`** — Standard SRT subtitle format with speaker detection.
- **`parse_turboscribe_file(file_path)`** — Auto-detects format by extension (.txt/.docx/.srt).

**Utilities:**
- `timestamp_to_seconds()`, `srt_timestamp_to_seconds()`, `seconds_to_timestamp()` — Format conversion.
- `validate_turboscribe_import(segments)` — Checks required fields, types, timestamp ordering.
- `get_transcript_stats(segments)` — Segment count, duration, speakers, avg length.

**Dependencies:** `os`, `re`, `shutil`, `webbrowser`, `python-docx` (optional)

---

## Common Patterns Across Platform Modules
- **Consistent return signatures:** Most return `(success, result/error, title, source_type, metadata)` tuples
- **Progressive fallback:** Each module tries multiple strategies in priority order
- **Status callbacks:** All accept optional `progress_callback` / `status_callback` for UI updates
- **Cookie handling:** YouTube and Substack handle browser cookies for authenticated access
- **yt-dlp as backbone:** YouTube, Twitter, Facebook, and Substack all leverage yt-dlp for media download
- **Graceful import failures:** Each module checks for optional dependencies at module level
