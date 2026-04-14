"""
subscription_manager.py — Content Subscription Logic Engine

Handles subscription data persistence, new content detection,
and AI processing for YouTube channels, Substack publications,
and generic RSS feeds.

Architecture note:
  Currently designed for manual "Check Now" execution only.
  Scheduling fields are included in the data model so that
  Windows Task Scheduler / background polling can be wired up
  later without changing the data schema.

Called by:
  subscription_dialog.py  (UI)
"""

import os
import json
import logging
import datetime
import re
from typing import List, Dict, Optional, Callable

from config import DATA_DIR

SUBSCRIPTIONS_PATH = os.path.join(DATA_DIR, "subscriptions.json")
SUBSCRIPTION_LOG_PATH = os.path.join(DATA_DIR, "subscription_log.txt")

logger = logging.getLogger(__name__)


def _write_log(sub_name: str, msg: str):
    """Append a timestamped line to the subscription log file."""
    try:
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] [{sub_name}] {msg}\n"
        with open(SUBSCRIPTION_LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception:
        pass  # never crash on logging


# ─────────────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────────────

def _make_id() -> str:
    import uuid
    return uuid.uuid4().hex[:12]


def default_subscription() -> Dict:
    """Return a new subscription dict with all fields at their defaults."""
    return {
        # Core identity
        "id":               _make_id(),
        "name":             "",
        "type":             "youtube_channel",  # youtube_channel | substack | rss
        "url":              "",
        "channel_id":       "",       # YouTube only: resolved channel ID
        "enabled":          True,

        # Processing
        "prompt_name":      "",       # Display name of the prompt to use
        "prompt_text":      "",       # Full prompt text
        "min_duration": 25,  # Minutes; 0 = no filter (YouTube only)
        "look_back_hours": 24,  # Only process items published in last N hours; 0 = all new

        # State tracking
        "last_checked":     None,     # ISO datetime string, or None
        "seen_guids":       [],       # Video IDs / post GUIDs already processed

        # ── Scheduling hooks — not active yet; reserved for future use ──────
        "schedule_enabled":      False,
        "check_interval_hours":  6,
        "check_time":            "06:00",   # for a daily "run at" schedule
    }


# ─────────────────────────────────────────────────────────────────────────────
# Persistence
# ─────────────────────────────────────────────────────────────────────────────

def load_subscriptions() -> List[Dict]:
    """Load subscriptions from disk.  Returns [] if the file doesn't exist."""
    if not os.path.exists(SUBSCRIPTIONS_PATH):
        return []
    try:
        with open(SUBSCRIPTIONS_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else data.get("subscriptions", [])
    except Exception as exc:
        logger.error(f"load_subscriptions: {exc}")
        return []


def save_subscriptions(subs: List[Dict]) -> bool:
    """Atomically write the subscriptions list to disk."""
    try:
        tmp = SUBSCRIPTIONS_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(subs, fh, indent=2, ensure_ascii=False)
        os.replace(tmp, SUBSCRIPTIONS_PATH)
        return True
    except Exception as exc:
        logger.error(f"save_subscriptions: {exc}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# CRUD helpers
# ─────────────────────────────────────────────────────────────────────────────

def add_subscription(sub: Dict) -> List[Dict]:
    if not sub.get("id"):
        sub["id"] = _make_id()
    subs = load_subscriptions()
    subs.append(sub)
    save_subscriptions(subs)
    return subs


def remove_subscription(sub_id: str) -> List[Dict]:
    subs = [s for s in load_subscriptions() if s.get("id") != sub_id]
    save_subscriptions(subs)
    return subs


def update_subscription(sub_id: str, updates: Dict) -> List[Dict]:
    subs = load_subscriptions()
    for s in subs:
        if s.get("id") == sub_id:
            s.update(updates)
            break
    save_subscriptions(subs)
    return subs


def get_subscription(sub_id: str) -> Optional[Dict]:
    for s in load_subscriptions():
        if s.get("id") == sub_id:
            return s
    return None


# ─────────────────────────────────────────────────────────────────────────────
# YouTube helpers
# ─────────────────────────────────────────────────────────────────────────────

def resolve_youtube_channel(url_or_handle: str,
                             status_cb: Callable = None) -> Optional[str]:
    """
    Resolve a YouTube channel URL / @handle / username to a channel ID.
    Uses yt-dlp — no API key required.
    Returns the channel_id string, or None on failure.
    """
    if status_cb:
        status_cb("Resolving YouTube channel ID…")
    try:
        import yt_dlp
        opts = {
            "extract_flat": True,
            "playlist_items": "1",
            "quiet": True,
            "no_warnings": True,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url_or_handle, download=False)
        channel_id = (
            info.get("channel_id")
            or info.get("uploader_id")
        )
        if channel_id:
            if status_cb:
                status_cb(f"Channel ID resolved: {channel_id}")
            return channel_id
        logger.warning(f"resolve_youtube_channel: no channel_id in yt-dlp info for {url_or_handle}")
        return None
    except Exception as exc:
        logger.warning(f"resolve_youtube_channel: {exc}")
        if status_cb:
            status_cb(f"Could not resolve channel: {exc}")
        return None


def _fetch_youtube_rss(channel_id: str) -> List[Dict]:
    """
    Fetch YouTube's public channel RSS feed (no API key required).
    Returns a list of dicts: {id, title, published, url}
    The 'duration_seconds' field is None — filled in by _get_duration() if needed.
    """
    import xml.etree.ElementTree as ET
    import urllib.request

    feed_url = (
        f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    )
    try:
        req = urllib.request.Request(
            feed_url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            xml_bytes = resp.read()
    except Exception as exc:
        logger.warning(f"_fetch_youtube_rss({channel_id}): {exc}")
        return []

    ns = {
        "atom":  "http://www.w3.org/2005/Atom",
        "yt":    "http://www.youtube.com/xml/schemas/2015",
        "media": "http://search.yahoo.com/mrss/",
    }
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        logger.warning(f"_fetch_youtube_rss: XML parse error: {exc}")
        return []

    items = []
    for entry in root.findall("atom:entry", ns):
        vid_id    = entry.findtext("yt:videoId", namespaces=ns) or ""
        title     = entry.findtext("atom:title",     namespaces=ns) or ""
        published = entry.findtext("atom:published", namespaces=ns) or ""
        if vid_id:
            items.append({
                "id":               vid_id,
                "title":            title,
                "published":        published,
                "url":              f"https://www.youtube.com/watch?v={vid_id}",
                "duration_seconds": None,
            })
    return items


def _get_duration(video_url: str) -> Optional[int]:
    """
    Fetch the duration (seconds) of a single YouTube video via yt-dlp.
    Returns None if the lookup fails.
    This call hits YouTube's servers; minimise usage by only checking
    unseen videos that pass other filters first.
    """
    try:
        import yt_dlp
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
            info = ydl.extract_info(video_url, download=False)
        return info.get("duration")
    except Exception as exc:
        logger.warning(f"_get_duration({video_url}): {exc}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# RSS / Substack helpers
# ─────────────────────────────────────────────────────────────────────────────

def _to_rss_url(sub_type: str, url: str) -> str:
    """
    Convert a Substack post/homepage URL to its RSS feed URL.
    Generic RSS URLs are returned unchanged.
    """
    if sub_type != "substack":
        return url
    match = re.match(r"(https?://[^/]+)", url)
    if match:
        base = match.group(1).rstrip("/")
        if "substack.com" in base:
            return base + "/feed"
    return url


def _fetch_rss(feed_url: str) -> List[Dict]:
    """
    Fetch items from an RSS feed via feedparser.
    Returns list of dicts: {id, title, published, url, content}
    """
    try:
        import feedparser
        feed = feedparser.parse(feed_url)
        items = []
        for entry in feed.entries:
            guid      = entry.get("id") or entry.get("link") or ""
            title     = entry.get("title", "")
            published = entry.get("published", "")
            url       = entry.get("link", "")
            # Prefer full 'content', fall back to 'summary'
            content = ""
            if hasattr(entry, "content") and entry.content:
                content = entry.content[0].get("value", "")
            elif hasattr(entry, "summary"):
                content = entry.summary or ""
            items.append({
                "id":        guid,
                "title":     title,
                "published": published,
                "url":       url,
                "content":   content,
            })
        return items
    except Exception as exc:
        logger.warning(f"_fetch_rss({feed_url}): {exc}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Content fetching
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_content(item: Dict, sub_type: str,
                   config: Dict, log: Callable):
    """
    Fetch the text content for a single item.
    Returns: (content_text: str | None, entries: list, doc_title: str)
    """
    url   = item.get("url", "")
    title = item.get("title", "")

    # ── YouTube ──────────────────────────────────────────────────────────────
    # Use fetch_youtube_with_audio_fallback — the identical function the main
    # UI calls.  It tries the transcript API first, then falls back to audio
    # transcription, with the same cookie/yt-dlp logic already built in.
    if sub_type == "youtube_channel":
        try:
            from youtube_utils import fetch_youtube_with_audio_fallback
            from utils import entries_to_text

            engine = config.get("transcription_engine", "faster_whisper")
            if engine == "assemblyai":
                transcription_key = (config.get("keys") or {}).get("AssemblyAI", "")
            elif engine in ("openai_whisper", "whisper"):
                transcription_key = (config.get("keys") or {}).get("OpenAI (ChatGPT)", "")
            else:
                transcription_key = ""   # local engines need no key

            log("  Fetching YouTube content (transcript → audio fallback if needed)…")
            success, result, yt_title, source_type, metadata = fetch_youtube_with_audio_fallback(
                url_or_id=url,
                api_key=transcription_key,
                engine=engine,
                options={
                    "language":           config.get("transcription_language") or None,
                    "speaker_diarization": False,
                    "enable_vad":         config.get("enable_vad", True),
                    "assemblyai_api_key": (config.get("keys") or {}).get("AssemblyAI", ""),
                },
                bypass_cache=False,
                progress_callback=log,
            )

            if success and result:
                timestamp_interval = config.get("timestamp_interval", "5min")
                text = entries_to_text(
                    result,
                    include_timestamps=True,
                    timestamp_interval=timestamp_interval,
                )
                return text, result, yt_title or title

            log(f"  YouTube fetch failed: {result}")
            return None, [], title

        except Exception as exc:
            log(f"  YouTube fetch error: {exc}")
            return None, [], title

    # ── Substack / RSS ───────────────────────────────────────────────────────
    # 1. Use the content already in the RSS entry (fastest, no extra HTTP call)
    rss_content = item.get("content", "")
    if rss_content:
        clean = re.sub(r"<[^>]+>", " ", rss_content)
        clean = re.sub(r"\s+", " ", clean).strip()
        if len(clean) > 200:            # enough to be useful
            return clean, [], title

    # 2. Substack: try the dedicated fetch utility for full article text
    if sub_type == "substack" and "substack.com" in url:
        try:
            from substack_updates import fetch_substack_content
            result = fetch_substack_content(url, status_callback=log)
            if result and result.get("text"):
                return result["text"], result.get("entries", []), result.get("title") or title
        except Exception as exc:
            log(f"  Substack utility error: {exc}")

    # 3. Generic URL fetch (plain HTTP, strip HTML)
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        clean = re.sub(r"<[^>]+>", " ", html)
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean[:50_000], [], title
    except Exception as exc:
        log(f"  URL fetch error: {exc}")
        return None, [], title


# ─────────────────────────────────────────────────────────────────────────────
# AI processing & library save
# ─────────────────────────────────────────────────────────────────────────────

def _run_ai_and_save(item: Dict, sub: Dict,
                     content_text: str, entries: list,
                     doc_title: str, config: Dict,
                     log: Callable) -> bool:
    """
    Call the AI provider with the subscription's prompt using the same
    chunk/consolidate logic as the main UI, then save both the source
    document and the processed output to the Documents Library.
    Returns True on success.
    """
    from ai_handler import process_entries_chunked

    prompt_text = sub.get("prompt_text", "").strip()
    prompt_name = sub.get("prompt_name", "Subscription Summary")

    if not prompt_text:
        log("  ERROR: No prompt configured for this subscription.")
        return False

    # Resolve provider / model / key
    provider = config.get("last_provider", "Google (Gemini)")
    model    = (config.get("last_model") or {}).get(provider, "")
    api_key  = (config.get("keys") or {}).get(provider, "")

    if not model:
        from config import DEFAULT_MODELS
        fallback = DEFAULT_MODELS.get(provider, [])
        model = fallback[0] if fallback else ""

    if not model:
        log(f"  ERROR: No model configured for {provider}.")
        return False

    # Build entries if caller only gave us raw text
    if not entries:
        entries = [{"text": content_text, "start": 0}]

    sub_type = sub.get("type", "youtube_channel")
    # YouTube entries carry timestamps; Substack/RSS are plain text
    include_timestamps = (sub_type == "youtube_channel")

    # ── AI call (chunked, exactly as the main UI does it) ─────────────────────
    ok, response = process_entries_chunked(
        entries=entries,
        prompt_text=prompt_text,
        provider=provider,
        model=model,
        api_key=api_key,
        chunk_size_setting=config.get("chunk_size", "medium"),
        include_timestamps=include_timestamps,
        timestamp_interval=config.get("timestamp_interval", "every_segment"),
        doc_title=doc_title,
        prompt_name=prompt_name,
        status_callback=log,
    )

    if not ok:
        log(f"  AI error: {response[:200]}")
        return False

    # ── Save source document + processed output ──────────────────────────────
    try:
        from document_library import add_document_to_library, add_processed_output_to_document
        import datetime

        doc_type = "youtube" if sub_type == "youtube_channel" else "web"

        metadata = {
            "subscription_id":   sub.get("id", ""),
            "subscription_name": sub.get("name", ""),
            "item_id":           item.get("id", ""),
            "published":         item.get("published", ""),
            "url":               item.get("url", ""),
        }

        # 1. Save source document
        doc_id = add_document_to_library(
            doc_type=doc_type,
            source=item.get("url", ""),
            title=doc_title,
            entries=entries,
            metadata=metadata,
        )

        if not doc_id:
            log("  Library save error: could not save source document.")
            return False

        # 2. Save AI response as a standalone response document (visible in the
        #    library tree, matching how the main UI saves AI responses).
        response_entries = [
            {"text": p.strip(), "start": 0}
            for p in response.split("\n\n") if p.strip()
        ] or [{"text": response, "start": 0}]

        response_title = f"{prompt_name}: {doc_title}"
        response_metadata = {
            "parent_document_id": doc_id,
            "source_document_id": doc_id,
            "ai_provider":        provider,
            "ai_model":           model,
            "prompt_name":        prompt_name,
            "created_at":         datetime.datetime.now().isoformat(),
            "subscription_id":    sub.get("id", ""),
            "subscription_name":  sub.get("name", ""),
        }
        # Include item URL in source so each video gets a unique doc_id
        # (without this, all responses from the same subscription overwrite each other)
        response_doc_id = add_document_to_library(
            doc_type="ai_response",
            source=f"AI Response — {item.get('url', '')} — {provider} / {model}",
            title=response_title,
            entries=response_entries,
            metadata=response_metadata,
            document_class="product",
        )

        # 3. Save the conversation thread on the SOURCE document.
        #    library_interaction.load_document_callback redirects current_document_id
        #    to source_doc_id and calls load_saved_thread() from there, so the thread
        #    MUST live on the source document to be found when the response doc is opened.
        from document_library import save_thread_to_document
        thread = [
            {
                "role":      "user",
                "content":   prompt_text,
                "timestamp": datetime.datetime.now().isoformat(),
            },
            {
                "role":      "assistant",
                "content":   response,
                "timestamp": datetime.datetime.now().isoformat(),
            },
        ]
        thread_metadata = {
            "model":         model,
            "provider":      provider,
            "last_updated":  datetime.datetime.now().isoformat(),
            "message_count": 1,
        }
        save_thread_to_document(doc_id, thread, thread_metadata)

        # 4. Also link via processed_outputs table so View Processed Outputs works
        add_processed_output_to_document(
            doc_id=doc_id,
            prompt_name=prompt_name,
            prompt_text=prompt_text,
            provider=provider,
            model=model,
            output_text=response,
        )

        return True

    except Exception as exc:
        log(f"  Library save error: {exc}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Single-subscription check
# ─────────────────────────────────────────────────────────────────────────────

def check_subscription(sub: Dict, config: Dict,
                        status_cb: Callable = None,
                        item_done_cb: Callable = None,
                        stop_flag: Optional[list] = None) -> Dict:
    """
    Check one subscription for new content and process anything new.

    Args:
        sub:          Subscription dict (not modified in place — caller updates state).
        config:       App config dict (read-only).
        status_cb:    Called with (str) for progress messages.
        item_done_cb: Called with (title: str, success: bool) after each item.
        stop_flag:    Single-element list [False]; set to [True] from outside to abort.

    Returns:
        {processed, skipped, errors, new_seen_guids}
    """
    def log(msg: str):
        logger.info(f"[{sub.get('name','?')}] {msg}")
        _write_log(sub.get('name', '?'), msg)
        if status_cb:
            status_cb(msg)

    result = {
        "processed":      0,
        "skipped":        0,
        "errors":         0,
        "new_seen_guids": [],
        "error_messages": [],   # collects human-readable error details
    }

    if not sub.get("enabled", True):
        log("Skipped (disabled).")
        return result

    sub_type = sub.get("type", "youtube_channel")
    seen     = set(sub.get("seen_guids", []))
    min_min  = int(sub.get("min_duration", 0))

    # ── Fetch candidate items ─────────────────────────────────────────────
    if sub_type == "youtube_channel":
        channel_id = sub.get("channel_id", "")
        if not channel_id:
            channel_id = resolve_youtube_channel(sub.get("url", ""), status_cb=log)
            if not channel_id:
                log("ERROR: Could not resolve YouTube channel ID.")
                result["errors"] += 1
                return result

        log(f"Fetching YouTube feed for channel {channel_id}…")
        items = _fetch_youtube_rss(channel_id)

    else:  # substack or rss
        feed_url = _to_rss_url(sub_type, sub.get("url", ""))
        log(f"Fetching RSS: {feed_url}")
        items = _fetch_rss(feed_url)

    if not items:
        log("No items returned from feed.")
        return result

    log(f"Feed returned {len(items)} items.")

    # ── Filter to unseen items ─────────────────────────────────────────────
    new_items = [it for it in items if it["id"] not in seen]
    if not new_items:
        log("No new items since last check.")
        return result

    # ── Filter by look-back window ─────────────────────────────────────────
    look_back_hours = int(sub.get("look_back_hours", 0))
    if look_back_hours > 0:
        import datetime
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=look_back_hours)
        filtered = []
        for it in new_items:
            pub = it.get("published", "")
            if pub:
                try:
                    # Parse ISO 8601 / RFC 2822 published dates
                    from email.utils import parsedate_to_datetime
                    try:
                        pub_dt = parsedate_to_datetime(pub)
                    except Exception:
                        pub_dt = datetime.datetime.fromisoformat(pub.replace("Z", "+00:00"))
                    if pub_dt.tzinfo is None:
                        pub_dt = pub_dt.replace(tzinfo=datetime.timezone.utc)
                    if pub_dt >= cutoff:
                        filtered.append(it)
                    else:
                        log(f"  Skipping (older than {look_back_hours}h): {it.get('title', '?')}")
                        result["new_seen_guids"].append(it["id"])
                        result["skipped"] += 1
                except Exception:
                    filtered.append(it)  # can't parse date — include it
            else:
                filtered.append(it)  # no date — include it
        new_items = filtered
        if not new_items:
            log(f"No items within the last {look_back_hours} hours.")
            return result

    log(f"{len(new_items)} new item(s) to process.")

    # ── Process each new item ─────────────────────────────────────────────
    for item in new_items:
        if stop_flag and stop_flag[0]:
            log("Check cancelled by user.")
            break

        item_title = item.get("title") or item.get("id", "?")

        try:
            # Duration filter (YouTube only)
            if sub_type == "youtube_channel" and min_min > 0:
                log(f"  Checking duration: {item_title}…")
                dur_sec = _get_duration(item["url"])
                if dur_sec is None:
                    log(f"  Duration unavailable — skipping: {item_title}")
                    result["new_seen_guids"].append(item["id"])
                    result["skipped"] += 1
                    continue
                dur_min = dur_sec / 60
                if dur_min < min_min:
                    log(f"  Too short ({dur_min:.0f} min < {min_min} min) — skipping.")
                    result["new_seen_guids"].append(item["id"])
                    result["skipped"] += 1
                    continue
                log(f"  Duration OK ({dur_min:.0f} min).")

            # Fetch content
            log(f"  Fetching content: {item_title}…")
            text, entries, doc_title = _fetch_content(item, sub_type, config, log)

            if not text:
                err_msg = f"Could not fetch content: {item_title}"
                log(f"  ERROR: {err_msg}")
                result["errors"] += 1
                result["error_messages"].append(f"{sub.get('name','?')}: {err_msg}")
                if item_done_cb:
                    item_done_cb(item_title, False)
                continue

            # AI processing + library save
            log(f"  Running AI: {item_title}…")
            ok = _run_ai_and_save(item, sub, text, entries, doc_title, config, log)

            if ok:
                # Only mark as seen on success
                result["new_seen_guids"].append(item["id"])
                result["processed"] += 1
                log(f"  Saved: {doc_title}")
                if item_done_cb:
                    item_done_cb(item_title, True)
            else:
                # AI/save failure — don't mark as seen so it retries next time
                err_msg = f"AI/save failed: {item_title}"
                result["errors"] += 1
                result["error_messages"].append(f"{sub.get('name','?')}: {err_msg}")
                if item_done_cb:
                    item_done_cb(item_title, False)

        except Exception as exc:
            import traceback
            err_msg = f"Exception for '{item.get('title', '?')}': {exc}"
            logger.error(f"check_subscription item error: {exc}", exc_info=True)
            _write_log(sub.get('name', '?'), f"EXCEPTION: {exc}\n{traceback.format_exc()}")
            result["errors"] += 1
            result["error_messages"].append(f"{sub.get('name','?')}: {err_msg}")
            if item_done_cb:
                item_done_cb(item.get("title", "?"), False)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Check-all entry point
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# Digest — summarise recent responses across multiple subscriptions
# ─────────────────────────────────────────────────────────────────────────────

def get_recent_responses(subscription_ids: List[str]) -> List[Dict]:
    """
    For each subscription ID, find the most recently saved AI response document
    (doc_type='ai_response', metadata.subscription_id == sub_id).

    Returns a list of dicts, one per subscription found:
        {
          'sub_id':      str,
          'sub_name':    str,
          'doc_id':      str,
          'title':       str,
          'created_at':  str,
          'text':        str,   # full joined entry text
        }
    Items for which no response exists are silently omitted.
    """
    import db_manager as db
    db.init_database()

    all_docs = db.db_get_all_documents()

    # Group ai_response docs by subscription_id, keeping only the newest
    best: Dict[str, dict] = {}   # sub_id -> doc row
    for doc in all_docs:
        if doc.get("doc_type") != "ai_response":
            continue
        meta = doc.get("metadata") or {}
        sid = meta.get("subscription_id", "")
        if not sid or sid not in subscription_ids:
            continue
        existing = best.get(sid)
        if existing is None or doc["created_at"] > existing["created_at"]:
            best[sid] = doc

    results = []
    for sid in subscription_ids:
        doc = best.get(sid)
        if not doc:
            continue
        entries = db.db_get_entries(doc["id"]) or []
        text = "\n\n".join(e.get("text", "") for e in entries if e.get("text"))
        meta = doc.get("metadata") or {}
        results.append({
            "sub_id":     sid,
            "sub_name":   meta.get("subscription_name", "Unknown"),
            "doc_id":     doc["id"],
            "title":      doc["title"],
            "created_at": doc["created_at"],
            "text":       text,
        })
    return results


def generate_digest(
    subscription_ids: List[str],
    prompt_text: str,
    prompt_name: str,
    config: Dict,
    status_cb: Callable = None,
) -> tuple:
    """
    Collect the most recent AI response for each subscription, concatenate
    them with source headers, run through the AI with `prompt_text`, then
    save the result as a new 'digest' document in the library.

    Returns: (success: bool, doc_id_or_error: str)
    """
    def _log(msg: str):
        logger.info(f"[Digest] {msg}")
        _write_log("Digest", msg)
        if status_cb:
            status_cb(msg)

    if not prompt_text.strip():
        return False, "No digest prompt configured."

    # ── Gather most recent summaries ─────────────────────────────────────────
    _log("Collecting recent summaries\u2026")
    responses = get_recent_responses(subscription_ids)

    if not responses:
        return False, "No recent AI responses found for the selected subscriptions."

    missing = [sid for sid in subscription_ids
               if not any(r["sub_id"] == sid for r in responses)]
    if missing:
        names = [s.get("name", sid) for s in load_subscriptions()
                 if s.get("id") in missing]
        _log(f"  Warning: no recent response found for: {', '.join(names)}")

    _log(f"  Found {len(responses)} summaries to digest.")

    # ── Build combined text ───────────────────────────────────────────────────
    sections = []
    for r in responses:
        try:
            import datetime
            dt = datetime.datetime.fromisoformat(r["created_at"])
            date_str = dt.strftime("%d %b %Y")
        except Exception:
            date_str = r["created_at"][:10]
        header = f"=== {r['sub_name']} ({date_str}) ==="
        sections.append(f"{header}\n\n{r['text']}")

    combined_text = "\n\n" + ("\n\n" + "-" * 60 + "\n\n").join(sections)
    combined_entries = [{"text": combined_text, "start": 0}]

    # ── Run AI ────────────────────────────────────────────────────────────────
    provider = config.get("last_provider", "Google (Gemini)")
    model    = (config.get("last_model") or {}).get(provider, "")
    api_key  = (config.get("keys") or {}).get(provider, "")

    if not model:
        from config import DEFAULT_MODELS
        fallback = DEFAULT_MODELS.get(provider, [])
        model = fallback[0] if fallback else ""

    if not model:
        return False, f"No model configured for {provider}."

    _log(f"Running AI ({provider} / {model})\u2026")

    from ai_handler import process_entries_chunked
    ok, digest_text = process_entries_chunked(
        entries=combined_entries,
        prompt_text=prompt_text,
        provider=provider,
        model=model,
        api_key=api_key,
        chunk_size_setting=config.get("chunk_size", "medium"),
        include_timestamps=False,
        doc_title="Subscription Digest",
        prompt_name=prompt_name,
        status_callback=_log,
    )

    if not ok:
        _log(f"AI error: {digest_text[:200]}")
        return False, f"AI error: {digest_text}"

    # ── Save result ───────────────────────────────────────────────────────────
    try:
        import datetime
        from document_library import add_document_to_library

        sub_names = ", ".join(r["sub_name"] for r in responses)
        date_str  = datetime.datetime.now().strftime("%d %b %Y")
        title = f"{prompt_name}: {date_str} ({sub_names})"

        digest_entries = [
            {"text": p.strip(), "start": 0}
            for p in digest_text.split("\n\n") if p.strip()
        ] or [{"text": digest_text, "start": 0}]

        metadata = {
            "digest": True,
            "prompt_name":          prompt_name,
            "subscription_names":   [r["sub_name"] for r in responses],
            "subscription_ids":     subscription_ids,
            "source_doc_ids":       [r["doc_id"]   for r in responses],
            "ai_provider":          provider,
            "ai_model":             model,
            "created_at":           datetime.datetime.now().isoformat(),
        }

        doc_id = add_document_to_library(
            doc_type="digest",
            source=f"Subscription Digest ({sub_names})",
            title=title,
            entries=digest_entries,
            metadata=metadata,
            document_class="product",
        )
        _log(f"Saved digest: {title}")
        return True, doc_id

    except Exception as exc:
        _log(f"Save error: {exc}")
        return False, str(exc)


def check_all_subscriptions(config: Dict,
                              status_cb:   Callable = None,
                              item_done_cb: Callable = None,
                              sub_done_cb:  Callable = None,
                              stop_flag:    Optional[list] = None) -> Dict:
    """
    Check every enabled subscription for new content.

    Args:
        config:       App config dict.
        status_cb:    Called with (str) for status messages.
        item_done_cb: Called with (title: str, success: bool) per item.
        sub_done_cb:  Called with (sub_name: str, result_dict) per subscription.
        stop_flag:    [False] — set element to True to cancel mid-run.

    Returns:
        {total_processed, total_skipped, total_errors}
    """
    subs    = load_subscriptions()
    enabled = [s for s in subs if s.get("enabled", True)]

    totals = {"total_processed": 0, "total_skipped": 0, "total_errors": 0}

    if not enabled:
        if status_cb:
            status_cb("No enabled subscriptions.")
        return totals

    for i, sub in enumerate(enabled):
        if stop_flag and stop_flag[0]:
            if status_cb:
                status_cb("Check cancelled.")
            break

        if status_cb:
            status_cb(f"Checking {i + 1}/{len(enabled)}: {sub['name']}…")

        result = check_subscription(
            sub, config,
            status_cb=status_cb,
            item_done_cb=item_done_cb,
            stop_flag=stop_flag,
        )

        # Persist new seen GUIDs + last_checked
        new_guids = result.get("new_seen_guids", [])
        if new_guids:
            merged = list(set(sub.get("seen_guids", []) + new_guids))
        else:
            merged = sub.get("seen_guids", [])

        update_subscription(sub["id"], {
            "seen_guids":   merged,
            "last_checked": datetime.datetime.now().isoformat(),
        })

        totals["total_processed"] += result["processed"]
        totals["total_skipped"]   += result["skipped"]
        totals["total_errors"]    += result["errors"]

        if sub_done_cb:
            sub_done_cb(sub["name"], result)

    if status_cb and not (stop_flag and stop_flag[0]):
        p, sk, er = totals["total_processed"], totals["total_skipped"], totals["total_errors"]
        status_cb(
            f"Done — {p} processed, {sk} skipped, {er} error(s)."
        )

    return totals
