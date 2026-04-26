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
    Fetch recent videos for a YouTube channel.

    Strategy:
      1. Try the channel RSS feed (fast, returns ISO-8601 published dates).
      2. If that 404s, try the uploads-playlist RSS feed with UU prefix
         (same data, different endpoint — often works when the channel
         endpoint is blocked).
      3. If both RSS attempts fail, fall back to yt-dlp with full
         extraction (NOT extract_flat) so upload_date/timestamp is
         returned for every video — slower but correct.

    The look-back filter in check_subscription() relies on every item
    having a parseable `published` date. The earlier extract_flat path
    returned items with empty `published` strings; that's why we use
    full extraction here.

    Returns a list of dicts: {id, title, published, url, duration_seconds}
    """
    import xml.etree.ElementTree as ET
    import urllib.request

    ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    # Build the list of RSS URLs to try. For channels with an ID starting
    # "UC...", YouTube also exposes the uploads playlist as "UU..." — the
    # same videos, but a different backend that sometimes works when the
    # channel endpoint 404s.
    rss_urls = [
        f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}",
    ]
    if channel_id.startswith("UC"):
        uploads_playlist_id = "UU" + channel_id[2:]
        rss_urls.append(
            f"https://www.youtube.com/feeds/videos.xml?playlist_id={uploads_playlist_id}"
        )

    def _parse_rss_xml(xml_bytes: bytes) -> List[Dict]:
        """Parse a YouTube Atom feed and return an items list."""
        ns = {
            "atom":  "http://www.w3.org/2005/Atom",
            "yt":    "http://www.youtube.com/xml/schemas/2015",
            "media": "http://search.yahoo.com/mrss/",
        }
        root = ET.fromstring(xml_bytes)
        out = []
        for entry in root.findall("atom:entry", ns):
            vid_id    = entry.findtext("yt:videoId",    namespaces=ns) or ""
            title     = entry.findtext("atom:title",    namespaces=ns) or ""
            published = entry.findtext("atom:published", namespaces=ns) or ""
            if vid_id:
                out.append({
                    "id":               vid_id,
                    "title":            title,
                    "published":        published,
                    "url":              f"https://www.youtube.com/watch?v={vid_id}",
                    "duration_seconds": None,
                })
        return out

    # ── Try each RSS URL in turn ──────────────────────────────────────────
    for url in rss_urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": ua})
            with urllib.request.urlopen(req, timeout=15) as resp:
                xml_bytes = resp.read()
        except Exception as exc:
            logger.warning(f"_fetch_youtube_rss: {url} failed: {exc}")
            continue

        try:
            items = _parse_rss_xml(xml_bytes)
            if items:
                logger.info(f"_fetch_youtube_rss: RSS success via {url} — {len(items)} items")
                return items
            logger.warning(f"_fetch_youtube_rss: {url} parsed but empty")
        except ET.ParseError as exc:
            logger.warning(f"_fetch_youtube_rss: XML parse error from {url}: {exc}")

    # ── yt-dlp fallback ───────────────────────────────────────────────────
    # Both RSS endpoints failed. Use yt-dlp with full extraction so
    # upload_date / timestamp come through for every video. Slower than
    # extract_flat but dates are essential for the look-back filter.
    logger.info(f"_fetch_youtube_rss: all RSS attempts failed — using yt-dlp fallback for {channel_id}")
    try:
        import yt_dlp
        channel_url = f"https://www.youtube.com/channel/{channel_id}/videos"
        opts = {
            # No extract_flat — we NEED upload_date/timestamp from each entry.
            # Full extraction is slower (~1-3s per video) but the look-back
            # filter depends on having real dates. This fallback only runs
            # when both RSS endpoints have failed, which is uncommon.
            "playlist_items": "1-15",
            "quiet":          True,
            "no_warnings":    True,
            "skip_download":  True,
            "ignoreerrors":   True,   # don't abort the whole run on one bad video
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(channel_url, download=False)

        entries = (info or {}).get("entries") or []
        items   = []
        for entry in entries:
            if not entry:   # skipped via ignoreerrors
                continue
            vid_id = entry.get("id") or ""
            title  = entry.get("title") or ""

            # Prefer the integer timestamp (unix seconds, UTC) over
            # upload_date (YYYYMMDD, midnight) — timestamps have full
            # precision. Fall back to upload_date when timestamp absent.
            published = ""
            ts = entry.get("timestamp")
            if ts:
                try:
                    published = datetime.datetime.fromtimestamp(
                        int(ts), tz=datetime.timezone.utc
                    ).isoformat()
                except Exception:
                    pass
            if not published and entry.get("upload_date"):
                d = entry["upload_date"]
                try:
                    published = f"{d[:4]}-{d[4:6]}-{d[6:8]}T00:00:00+00:00"
                except Exception:
                    pass

            if vid_id:
                items.append({
                    "id":               vid_id,
                    "title":            title,
                    "published":        published,
                    "url":              f"https://www.youtube.com/watch?v={vid_id}",
                    "duration_seconds": entry.get("duration"),
                })
        return items

    except Exception as exc:
        logger.warning(f"_fetch_youtube_rss yt-dlp fallback failed: {exc}")
        return []


def _extract_interviewee(content_text: str, provider: str, model: str,
                          api_key: str, doc_title: str = "",
                          host_name: str = "") -> str:
    """
    Use a lightweight AI call to extract the interviewee/guest name from
    the opening of a transcript.

    Uses the first 5000 characters (~800 words) plus, when available, the
    document title and the host / channel name as extra context.  The
    wider window covers introductions that come after a cold open or
    sponsor read; the title often names the guest outright; and the host
    name lets the AI rule them out directly rather than guessing who's
    host vs guest.  Returns an empty string on failure so callers can
    treat it as optional enrichment.
    """
    snippet = content_text[:5000].strip()
    if not snippet:
        return ""

    # Build a context preamble from whatever extra signal we have.
    context_lines = []
    if doc_title:
        context_lines.append(f"Document title: {doc_title}")
    if host_name:
        context_lines.append(f"Host / channel name: {host_name}")
    context_block = ("\n".join(context_lines) + "\n\n") if context_lines else ""

    prompt = (
        f"{context_block}"
        "From the following opening of a transcript, identify the main "
        "interviewee or guest speaker (NOT the host or interviewer). "
        "If a host name is given above, DO NOT return that name — return "
        "the guest. "
        "Reply with ONLY their name (first and last name if available), "
        "or 'Unknown' if you cannot determine it. "
        "Do not include any other text or punctuation.\n\n"
        f"{snippet}"
    )
    try:
        # ai_handler exposes call_ai_provider(), not call_ai — use the real name.
        # It takes an OpenAI-style messages list, not a bare prompt string.
        from ai_handler import call_ai_provider
        messages = [{"role": "user", "content": prompt}]
        ok, name = call_ai_provider(
            provider=provider,
            model=model,
            messages=messages,
            api_key=api_key,
            document_title="interviewee extraction",
            prompt_name="_extract_interviewee",
        )
        if ok and name:
            name = name.strip().strip('"').strip("'").strip()
            # Some providers prepend a prefix like "Name:" or wrap the answer in
            # a sentence; take the first line and strip common leading tokens.
            name = name.splitlines()[0].strip()
            for prefix in ("Name:", "Interviewee:", "Guest:", "Answer:"):
                if name.lower().startswith(prefix.lower()):
                    name = name[len(prefix):].strip()
            # Remove any trailing punctuation.
            name = name.rstrip(".,;:!")
            if name and name.lower() != "unknown" and len(name) < 80:
                return name
    except Exception as exc:
        logger.debug(f"_extract_interviewee: {exc}")
    return ""


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

def _resolve_provider(config: Dict) -> str:
    """
    Resolve the effective AI provider for background subscription /
    digest runs. The order:

      1. last_provider     (currently-selected provider in the main UI;
                           after bug #12 was fixed, this always tracks
                           the main-window dropdown, so it's the best
                           signal of "what the user wants to use RIGHT
                           NOW")
      2. default_provider  (fallback — only used when last_provider is
                           unset, e.g. a fresh install before the user
                           has opened the main UI)
      3. hardcoded fallback "Google (Gemini)"

    We prefer last_provider because the user expects subscription checks
    to honour whatever they've set in the main UI. default_provider is
    a "when I restart the app, put me on this provider" preference, not
    an override for live subscription work — if the user temporarily
    switches to a different provider mid-session, subscriptions should
    follow the switch, not cling to the sticky default.

    (This is a change from an earlier implementation that preferred
    default_provider: that meant setting Mistral Le Chat as default and
    then switching the main UI to Claude still routed subscription
    checks through Mistral, which was surprising.)
    """
    last_used = (config.get("last_provider") or "").strip()
    explicit = (config.get("default_provider") or "").strip()
    return last_used or explicit or "Google (Gemini)"


def _is_web_only_provider(provider: str) -> bool:
    """
    Return True if `provider` is a web-only provider (Lumo, Duck.ai,
    Mistral Le Chat, …). These have no API and cannot be driven by
    background subscription checks — the user has to drive them in a
    browser, which isn't available here. Guarded in _run_ai_and_save
    so the subscription fails fast with a clear message (bug #11).
    """
    try:
        from config import PROVIDER_REGISTRY
        return PROVIDER_REGISTRY.get(provider, {}).get("type") == "web"
    except Exception:
        # If PROVIDER_REGISTRY isn't importable for any reason, assume
        # it's an API provider and let the downstream AI call surface
        # whatever error it produces.
        return False


def _available_api_providers(config: Dict) -> List[str]:
    """
    Return the list of providers that are actually usable for a
    background subscription / digest run, given the current config.

    A provider qualifies if ALL of:
      - type != "web"       (can't drive a browser from here)
      - blocked != True     (respects user's opt-out, e.g. OpenAI)
      - has a usable key    (requires_api_key is False, OR the user has
                             configured a non-empty key in config["keys"])

    Local providers (Ollama) qualify automatically because they don't
    need a key. Used to build the suggestion list in the "web-only
    provider" warning so we only suggest providers the user can
    actually switch to — rather than listing every API provider in
    the registry regardless of whether they've configured a key or
    deliberately blocked the provider.
    """
    try:
        from config import PROVIDER_REGISTRY
    except Exception:
        return []

    keys = (config or {}).get("keys") or {}
    available = []
    for name, info in PROVIDER_REGISTRY.items():
        if info.get("type") == "web":
            continue
        if info.get("blocked"):
            continue
        if info.get("requires_api_key", True):
            # API provider — only count it if a non-empty key is on file.
            if not (keys.get(name) or "").strip():
                continue
        # Either local (no key needed) or API with a configured key.
        available.append(name)
    return available


def _suggestable_api_providers() -> List[str]:
    """
    Return the list of non-web, non-blocked providers, regardless of
    whether a key is configured.

    Used by the "no providers configured" branch of the web-only warning
    to suggest providers the user COULD set up — we don't want to hard-
    code a provider list there, because it'd get stale as config.py
    evolves or as the user changes their `blocked` flags (e.g. blocking
    a provider they disapprove of, or unblocking one they'd previously
    opted out of). Respecting `blocked` here matters: suggesting a
    provider the user has explicitly marked as blocked would be rude.
    """
    try:
        from config import PROVIDER_REGISTRY
    except Exception:
        return []

    return [
        name for name, info in PROVIDER_REGISTRY.items()
        if info.get("type") != "web" and not info.get("blocked")
    ]


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
    provider = _resolve_provider(config)

    # Web-only providers (Lumo, Duck.ai, Mistral Le Chat) can't run
    # subscription checks — there's no API to call (bug #11).
    if _is_web_only_provider(provider):
        log(f"  ERROR: {provider} is a web-only provider and cannot run "
            f"subscription checks. Change the AI provider in Settings → "
            f"AI Settings (click Set Default to persist), then retry.")
        return False

    model    = (config.get("last_model") or {}).get(provider, "")
    api_key  = (config.get("keys") or {}).get(provider, "")

    if not model:
        from config import DEFAULT_MODELS
        fallback = DEFAULT_MODELS.get(provider, [])
        model = fallback[0] if fallback else ""

    if not model:
        log(f"  ERROR: No model configured for {provider}.")
        return False

    # Surface the resolved provider/model in the log so the user can
    # verify (e.g. via the Subscriptions dialog's View Log… button) that
    # background checks are actually running through the provider they
    # think is selected. Useful for diagnosing the kind of issue that
    # bug #13 caused, where stale config could route checks through the
    # wrong provider silently.
    log(f"  Using AI: {provider} / {model}")

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
            "published_date":    item.get("published", ""),
            "url":               item.get("url", ""),
            # The subscription name IS the interviewer/channel host for
            # YouTube channel subscriptions (e.g. "Alexander Mercouris",
            # "Glenn Diesen"). Storing it under a dedicated `interviewer`
            # key as well as `subscription_name` lets the thread viewer
            # and digest generator render it symmetrically alongside
            # `interviewee` without having to special-case the name.
            "interviewer":       sub.get("name", "") if sub_type == "youtube_channel" else "",
        }

        # Attempt to identify the interviewee from the transcript opening.
        # YouTube only — Substack/RSS articles don’t follow interview format.
        # Uses the same provider/model as the main summary call. We pass
        # doc_title and the subscription (host) name so the extractor can
        # distinguish host from guest reliably even when the transcript
        # opening is dominated by ads, theme music, or headline banter.
        if sub_type == "youtube_channel" and content_text:
            log("  Identifying interviewee…")
            interviewee = _extract_interviewee(
                content_text, provider, model, api_key,
                doc_title=doc_title,
                host_name=sub.get("name", ""),
            )
            if interviewee:
                metadata["interviewee"] = interviewee
                log(f"  Interviewee identified: {interviewee}")

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
            {"text": p.strip()}
            for p in response.split("\n\n") if p.strip()
        ] or [{"text": response}]

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
            # Copy both interview-role fields across from the source doc
            # metadata so (a) thread_viewer can show the full context
            # ("Source: <n> — interviewer: <x>, interviewee: <y>") when
            # the response is opened, and (b) get_recent_responses can
            # surface both to generate_digest without an extra DB
            # round-trip.
            "interviewer":        metadata.get("interviewer", ""),
            "interviewee":        metadata.get("interviewee", ""),
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
        from email.utils import parsedate_to_datetime
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=look_back_hours)
        log(f"Look-back: {look_back_hours}h — cutoff is {cutoff.isoformat()}")

        def _parse_pub_date(pub_str: str):
            """
            Parse a published-date string to a timezone-aware UTC datetime.
            Tries ISO 8601 first (YouTube RSS, Atom feeds), then RFC 2822
            (generic RSS). Returns None if neither format works.
            """
            if not pub_str:
                return None
            # ISO 8601 first — YouTube's Atom feed uses this
            try:
                dt = datetime.datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=datetime.timezone.utc)
                return dt
            except (ValueError, TypeError):
                pass
            # RFC 2822 fallback — generic RSS feeds
            try:
                dt = parsedate_to_datetime(pub_str)
                if dt is None:
                    return None
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=datetime.timezone.utc)
                return dt
            except (ValueError, TypeError):
                return None

        filtered = []
        for it in new_items:
            pub = it.get("published", "")
            title = it.get("title", "?")
            pub_dt = _parse_pub_date(pub)

            if pub_dt is None:
                # Parse failed — skip rather than include, so look-back is reliable.
                # Mark as seen so it doesn't get retried forever.
                log(f"  Skipping (no/unparseable date '{pub}'): {title}")
                result["new_seen_guids"].append(it["id"])
                result["skipped"] += 1
                continue

            if pub_dt >= cutoff:
                log(f"  Within window ({pub_dt.isoformat()}): {title}")
                filtered.append(it)
            else:
                age_hours = (datetime.datetime.now(datetime.timezone.utc) - pub_dt).total_seconds() / 3600
                log(f"  Skipping (age {age_hours:.1f}h > {look_back_hours}h window): {title}")
                result["new_seen_guids"].append(it["id"])
                result["skipped"] += 1

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

    # Use include_deleted=True so the digest can find ai_responses even
    # when they've been soft-deleted from the library tree view. The
    # digest is a system-internal function — its source of truth is
    # "what ai_responses exist in the database", not "what's currently
    # visible to the user in the library tree". This decoupling means
    # the user can tidy up their library (deleting old source docs and
    # ai_responses to keep the tree manageable) without inadvertently
    # breaking digests, which need the historical ai_responses to fill
    # in subscriptions whose latest content predates the most recent
    # Check All run. The source-doc lookup later in this function also
    # benefits from the same flag — when a YouTube source doc has been
    # removed from the tree we still want its URL/title/published-date
    # available to populate the digest's Sources section.
    # See ProjectMap/14_ROADMAP_STATUS.md polish item P8.
    all_docs = db.db_get_all_documents(include_deleted=True)

    # Index all documents by ID so we can look up source docs for each
    # ai_response doc.  The source doc carries the URL, published date
    # and original title (video / article name) - fields we need to pass
    # into the digest AI call for the Sources section.
    docs_by_id = {d["id"]: d for d in all_docs}

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

        # Look up the source document via the response doc's metadata.
        # `source_document_id` is the canonical key; `parent_document_id`
        # is a legacy alias kept for older response docs.  If the source
        # doc has been deleted we fall back to whatever's available on
        # the response doc itself rather than failing the whole digest.
        source_doc_id = (
            meta.get("source_document_id")
            or meta.get("parent_document_id")
            or ""
        )
        source_doc  = docs_by_id.get(source_doc_id) if source_doc_id else None
        source_meta = (source_doc.get("metadata") if source_doc else {}) or {}

        # The source doc's title is the YouTube video / article title.
        # The response doc's title is of the form "<prompt>: <video title>",
        # which isn't what we want to surface in the Sources section.
        item_title = (source_doc.get("title") if source_doc else "") or ""

        results.append({
            "sub_id":         sid,
            "sub_name":       meta.get("subscription_name", "Unknown"),
            "doc_id":         doc["id"],
            "title":          doc["title"],       # response-doc title, kept for back-compat
            "created_at":     doc["created_at"],
            "text":           text,
            # Source-document fields - these let generate_digest build a
            # structured metadata block per source so the AI can populate
            # the Sources section with real URLs, titles and dates rather
            # than placeholders.
            "item_title":     item_title,
            "url":            source_meta.get("url", ""),
            "published_date": source_meta.get("published_date", ""),
            # Interviewer is the channel host (YouTube) / publication name
            # (Substack / RSS).  Already copied onto the response doc by
            # _run_ai_and_save; fall back to the source doc if the
            # response doc predates that wiring.
            "interviewer":    meta.get("interviewer") or source_meta.get("interviewer", ""),
            # Surface the interviewee so generate_digest can include it in
            # the digest's sources list.  Empty string when not applicable
            # (non-YouTube subscriptions, or older responses saved before
            # this field was carried onto the response doc).
            "interviewee":    meta.get("interviewee", ""),
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

    The digest is saved with a companion conversation thread (user turn =
    the digest prompt, assistant turn = the digest output) so that when it
    is opened in the Thread Viewer it behaves like any other AI response:
    the markdown renders properly, the "Copy formatted for Word/Email" and
    "Copy formatted for WhatsApp" paths work, and the user can ask
    follow-up questions.  Without the thread, the digest would appear as a
    bare source document and the copy path would drop raw markdown.

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
        names = [s.get("name", s.get("id", "")) for s in load_subscriptions()
                 if s.get("id") in missing]
        _log(f"  Warning: no recent response found for: {', '.join(names)}")

    _log(f"  Found {len(responses)} summaries to digest.")

    # ── Build combined text ───────────────────────────────────────────────────
    # Each source is preceded by a structured metadata block so the AI
    # can populate the Sources section with real Channel / Title / URL /
    # Interviewer / Interviewee / Date values rather than placeholders.
    # Fields that are empty for a given source are omitted from the
    # block rather than shown blank - cleaner input, and the digest
    # prompt tells the AI to omit missing fields from its own Sources
    # output too.
    import datetime as _dt

    def _format_date(iso_or_raw: str) -> str:
        if not iso_or_raw:
            return ""
        try:
            dt = _dt.datetime.fromisoformat(iso_or_raw.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d")
        except Exception:
            # Fall back to whatever date-like prefix we have.
            return iso_or_raw[:10]

    sections = []
    for idx, r in enumerate(responses, start=1):
        date_str = _format_date(r.get("published_date") or r.get("created_at", ""))

        lines = [f"[SOURCE {idx}]"]
        if r.get("sub_name"):
            lines.append(f"Channel: {r['sub_name']}")
        if r.get("item_title"):
            lines.append(f"Title: {r['item_title']}")
        if r.get("url"):
            lines.append(f"URL: {r['url']}")
        if r.get("interviewer"):
            lines.append(f"Interviewer: {r['interviewer']}")
        if r.get("interviewee"):
            lines.append(f"Interviewee: {r['interviewee']}")
        if date_str:
            lines.append(f"Date: {date_str}")

        metadata_block = "\n".join(lines)
        sections.append(f"{metadata_block}\n\n{r['text']}")

    combined_text = "\n\n".join(sections)
    combined_entries = [{"text": combined_text, "start": 0}]

    # ── Run AI ────────────────────────────────────────────────────────────────
    provider = _resolve_provider(config)
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
        from document_library import (
            add_document_to_library,
            save_thread_to_document,
        )

        sub_names = ", ".join(r["sub_name"] for r in responses)
        date_str  = datetime.datetime.now().strftime("%d %b %Y")
        # Strip leading zero from day so the date reads "8 Apr 2026" not "08 Apr 2026".
        if date_str.startswith("0"):
            date_str = date_str[1:]

        # Title is now just the prompt name and date.  The list of sources
        # is surfaced separately in the metadata block (see sources below).
        # The internal `source` string still carries sub_names so the MD5
        # hash used to generate doc_id stays unique across digests that
        # share the same prompt name + date but have different source sets.
        title = f"{prompt_name}: {date_str}"

        digest_entries = [
            {"text": p.strip()}
            for p in digest_text.split("\n\n") if p.strip()
        ] or [{"text": digest_text}]

        # Build a structured sources list that pairs each subscription name
        # with its interviewee (if any).  thread_viewer_metadata reads this
        # to render, e.g., "Source(s): Alexander Mercouris (interviewee:
        # Pepe Escobar), Glenn Diesen".  `subscription_names` is kept
        # alongside for backward compatibility with code that expects the
        # old flat list.
        sources_list = [
            {
                "name":        r["sub_name"],
                "interviewee": r.get("interviewee", ""),
            }
            for r in responses
        ]

        metadata = {
            "digest": True,
            "prompt_name":          prompt_name,
            "sources":              sources_list,
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

        # Save a conversation thread on the digest document so the Thread
        # Viewer treats it as a normal AI response and applies its markdown
        # rendering / copy-formatting pipeline.  Mirrors the pattern used by
        # _run_ai_and_save for ordinary per-item subscription responses.
        now_iso = datetime.datetime.now().isoformat()
        thread = [
            {
                "role":      "user",
                "content":   prompt_text,
                "timestamp": now_iso,
            },
            {
                "role":      "assistant",
                "content":   digest_text,
                "provider":  provider,
                "model":     model,
                "timestamp": now_iso,
            },
        ]
        thread_metadata = {
            "model":         model,
            "provider":      provider,
            "last_updated":  now_iso,
            "message_count": 1,
        }
        save_thread_to_document(doc_id, thread, thread_metadata)

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
