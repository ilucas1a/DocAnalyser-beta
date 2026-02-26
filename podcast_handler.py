"""
podcast_handler.py - Podcast URL Resolution and Episode Extraction
===================================================================
Resolves Apple Podcasts URLs to RSS feeds, finds episodes, and
downloads audio for transcription.

Supports:
  - Apple Podcasts URLs (podcasts.apple.com/...)
  - Direct RSS feed URLs (any URL ending in .rss or .xml, or known feed hosts)
  - Direct MP3/audio URLs (passed through to existing audio pipeline)

Architecture:
  Apple Podcasts URL → iTunes Lookup API → RSS feed URL → feedparser → MP3 URL → download

Usage:
    from podcast_handler import (
        is_podcast_url,
        resolve_podcast_episode,
        download_podcast_audio,
        PodcastEpisode
    )
"""

import re
import os
import json
import tempfile
import logging
from dataclasses import dataclass, field
from typing import Optional, Tuple, List, Callable
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

try:
    import feedparser
    FEEDPARSER_AVAILABLE = True
except ImportError:
    FEEDPARSER_AVAILABLE = False


# ============================================================
# DATA CLASSES
# ============================================================

@dataclass
class PodcastEpisode:
    """Metadata for a single podcast episode."""
    title: str = ""
    podcast_name: str = ""
    description: str = ""
    audio_url: str = ""
    published: str = ""
    duration: str = ""
    episode_url: str = ""       # Original Apple Podcasts or web URL
    episode_guid: str = ""
    artwork_url: str = ""


@dataclass
class PodcastInfo:
    """Metadata for a podcast feed."""
    name: str = ""
    author: str = ""
    feed_url: str = ""
    artwork_url: str = ""
    description: str = ""
    episodes: List[PodcastEpisode] = field(default_factory=list)


# ============================================================
# URL DETECTION
# ============================================================

# Known podcast feed host patterns
KNOWN_FEED_HOSTS = [
    'feeds.megaphone.fm',
    'feeds.buzzsprout.com',
    'feeds.simplecast.com',
    'feeds.transistor.fm',
    'feeds.captivate.fm',
    'feeds.libsyn.com',
    'feeds.soundcloud.com',
    'feeds.feedburner.com',
    'anchor.fm',
    'rss.art19.com',
    'rss.acast.com',
    'omnycontent.com',
    'audioboom.com',
    'pdst.fm',
    'pinecast.com',
    'podbean.com',
    'spreaker.com',
    'podtrac.com',
]


def is_podcast_url(url: str) -> bool:
    """
    Check if a URL is a podcast URL that this handler can process.
    Supports:
      - Apple Podcasts URLs (podcasts.apple.com/...)
      - Direct RSS feed URLs (.rss, .xml, known feed hosts)
    """
    if not url:
        return False
    url_lower = url.lower().strip()
    
    # Apple Podcasts
    if 'podcasts.apple.com' in url_lower:
        return True
    
    # Direct RSS/feed URLs
    if is_feed_url(url):
        return True
    
    return False


def is_feed_url(url: str) -> bool:
    """
    Check if a URL looks like a direct podcast RSS feed.
    """
    if not url:
        return False
    url_lower = url.lower().strip()
    
    # Must be a URL
    if not url_lower.startswith(('http://', 'https://')):
        return False
    
    # Strip query params for extension check
    path_part = url_lower.split('?')[0].split('#')[0]
    
    # Check file extensions
    if path_part.endswith(('.rss', '.xml', '/feed', '/rss')):
        return True
    
    # Check known feed hosts
    for host in KNOWN_FEED_HOSTS:
        if host in url_lower:
            return True
    
    # Check for common feed path patterns
    feed_patterns = ['/feed/', '/feeds/', '/rss/', '/podcast.xml', '/podcast.rss']
    for pattern in feed_patterns:
        if pattern in url_lower:
            return True
    
    return False


def is_specific_episode_url(url: str) -> bool:
    """
    Check if a URL points to a specific episode (not just a feed/podcast page).
    If True, we can skip the browser dialog and go straight to download.
    """
    if not url:
        return False
    url_lower = url.lower().strip()
    
    # Apple Podcasts with ?i= parameter = specific episode
    if 'podcasts.apple.com' in url_lower and '?i=' in url_lower:
        return True
    
    return False


def _extract_apple_podcast_ids(url: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract podcast ID and optional episode ID from an Apple Podcasts URL.
    
    Examples:
        https://podcasts.apple.com/au/podcast/triggernometry/id1375568988
        → podcast_id='1375568988', episode_id=None
        
        https://podcasts.apple.com/au/podcast/triggernometry/id1375568988?i=1000749865261
        → podcast_id='1375568988', episode_id='1000749865261'
    """
    # Extract podcast ID (appears as 'id' followed by digits)
    podcast_match = re.search(r'/id(\d+)', url)
    podcast_id = podcast_match.group(1) if podcast_match else None
    
    # Extract episode ID (appears as 'i=' parameter)
    episode_match = re.search(r'[?&]i=(\d+)', url)
    episode_id = episode_match.group(1) if episode_match else None
    
    return podcast_id, episode_id


# ============================================================
# ITUNES API - RSS FEED RESOLUTION
# ============================================================

def _lookup_rss_feed(podcast_id: str, timeout: int = 15) -> Tuple[bool, str, str]:
    """
    Use the iTunes Lookup API to get the RSS feed URL for a podcast.
    
    Args:
        podcast_id: Numeric iTunes podcast ID
        timeout: Request timeout in seconds
    
    Returns:
        (success, feed_url_or_error, podcast_name)
    """
    if not REQUESTS_AVAILABLE:
        return False, "requests library not installed", ""
    
    lookup_url = f"https://itunes.apple.com/lookup?id={podcast_id}&entity=podcast"
    
    try:
        response = requests.get(lookup_url, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        
        results = data.get("results", [])
        if not results:
            return False, f"No podcast found with ID {podcast_id}", ""
        
        feed_url = results[0].get("feedUrl", "")
        podcast_name = results[0].get("collectionName", results[0].get("trackName", "Unknown Podcast"))
        
        if not feed_url:
            return False, f"No RSS feed URL found for podcast '{podcast_name}'", podcast_name
        
        return True, feed_url, podcast_name
    
    except requests.exceptions.Timeout:
        return False, "iTunes API timed out", ""
    except requests.exceptions.RequestException as e:
        return False, f"iTunes API error: {e}", ""
    except (json.JSONDecodeError, KeyError) as e:
        return False, f"Invalid response from iTunes API: {e}", ""


# ============================================================
# RSS FEED PARSING
# ============================================================

def _parse_rss_feed(feed_url: str, timeout: int = 20) -> Tuple[bool, str, PodcastInfo]:
    """
    Parse a podcast RSS feed and extract episode data.
    
    Returns:
        (success, error_message, PodcastInfo)
    """
    if not FEEDPARSER_AVAILABLE:
        return False, (
            "feedparser library not installed.\n\n"
            "Install it with: pip install feedparser"
        ), PodcastInfo()
    
    try:
        # feedparser can handle URLs directly
        feed = feedparser.parse(feed_url)
        
        if feed.bozo and not feed.entries:
            # bozo flag means there was a parse error, but if we got entries it's OK
            error = getattr(feed.bozo_exception, 'getMessage', lambda: str(feed.bozo_exception))()
            return False, f"RSS feed parse error: {error}", PodcastInfo()
        
        if not feed.entries:
            return False, "RSS feed has no episodes", PodcastInfo()
        
        # Build PodcastInfo
        podcast = PodcastInfo(
            name=feed.feed.get("title", "Unknown Podcast"),
            author=feed.feed.get("author", feed.feed.get("itunes_author", "")),
            feed_url=feed_url,
            artwork_url=_get_feed_artwork(feed),
            description=feed.feed.get("subtitle", feed.feed.get("summary", ""))
        )
        
        # Parse episodes
        for entry in feed.entries:
            episode = PodcastEpisode(
                title=entry.get("title", "Untitled Episode"),
                podcast_name=podcast.name,
                description=entry.get("summary", entry.get("subtitle", "")),
                audio_url=_get_episode_audio_url(entry),
                published=entry.get("published", ""),
                duration=entry.get("itunes_duration", ""),
                episode_guid=entry.get("id", entry.get("guid", "")),
                episode_url=entry.get("link", ""),
            )
            if episode.audio_url:  # Only include episodes with audio
                podcast.episodes.append(episode)
        
        return True, "", podcast
    
    except Exception as e:
        return False, f"Error parsing RSS feed: {e}", PodcastInfo()


def _get_feed_artwork(feed) -> str:
    """Extract podcast artwork URL from feed."""
    # Try itunes:image first
    image = getattr(feed.feed, 'image', None)
    if image:
        href = getattr(image, 'href', None)
        if href:
            return href
    # Try itunes_image
    itunes_image = feed.feed.get("itunes_image", {})
    if isinstance(itunes_image, dict):
        return itunes_image.get("href", "")
    return ""


def _get_episode_audio_url(entry) -> str:
    """Extract the audio file URL from an RSS entry."""
    # Check enclosures (standard RSS way to attach media)
    enclosures = entry.get("enclosures", [])
    for enc in enclosures:
        url = enc.get("url", enc.get("href", ""))
        mime = enc.get("type", "")
        if url and ("audio" in mime or url.lower().endswith(('.mp3', '.m4a', '.wav', '.ogg', '.opus', '.aac'))):
            return url
    
    # Fallback: check links
    links = entry.get("links", [])
    for link in links:
        url = link.get("href", "")
        mime = link.get("type", "")
        if "audio" in mime or (url and url.lower().endswith(('.mp3', '.m4a', '.wav', '.ogg'))):
            return url
    
    # Last resort: check for media:content
    media_content = entry.get("media_content", [])
    for media in media_content:
        url = media.get("url", "")
        mime = media.get("type", "")
        if url and ("audio" in mime or url.lower().endswith(('.mp3', '.m4a', '.wav', '.ogg'))):
            return url
    
    return ""


def _find_episode_by_apple_id(podcast: PodcastInfo, episode_id: str) -> Optional[PodcastEpisode]:
    """
    Try to find a specific episode matching an Apple Podcasts episode ID.
    
    Apple episode IDs (the ?i= parameter) sometimes appear in RSS GUIDs
    or can be matched by checking the feed entries. If no exact match,
    returns the most recent episode.
    """
    if not podcast.episodes:
        return None
    
    # Strategy 1: Check if episode_id appears in any GUID
    for ep in podcast.episodes:
        if episode_id in ep.episode_guid:
            return ep
    
    # Strategy 2: Check episode URLs for the ID
    for ep in podcast.episodes:
        if episode_id in ep.episode_url:
            return ep
    
    # Strategy 3: Use the iTunes Lookup API for the specific episode
    if REQUESTS_AVAILABLE:
        try:
            response = requests.get(
                f"https://itunes.apple.com/lookup?id={episode_id}&entity=podcastEpisode",
                timeout=10
            )
            data = response.json()
            results = data.get("results", [])
            
            if results:
                # Get episode name from iTunes
                for result in results:
                    itunes_title = result.get("trackName", "")
                    if itunes_title:
                        # Find by title match
                        itunes_title_lower = itunes_title.lower().strip()
                        for ep in podcast.episodes:
                            if ep.title.lower().strip() == itunes_title_lower:
                                return ep
                        # Fuzzy match — check if significant words overlap
                        itunes_words = set(itunes_title_lower.split())
                        for ep in podcast.episodes:
                            ep_words = set(ep.title.lower().strip().split())
                            overlap = itunes_words & ep_words
                            # Match if more than half the words overlap
                            if len(overlap) > max(len(itunes_words), len(ep_words)) * 0.5:
                                return ep
        except Exception as e:
            logger.debug(f"Episode lookup failed: {e}")
    
    # No match found — return None so the caller can open the browser
    logger.info(f"Could not match episode ID {episode_id} — no fallback, returning None")
    return None


# ============================================================
# HIGH-LEVEL API
# ============================================================

def resolve_podcast_feed(
    url: str,
    progress_callback: Optional[Callable[[str], None]] = None
) -> Tuple[bool, str, Optional[PodcastInfo]]:
    """
    Resolve any podcast URL to a PodcastInfo with all episodes.
    Works with both Apple Podcasts URLs and direct RSS feed URLs.
    
    Returns:
        (success, error_message, PodcastInfo or None)
    """
    def status(msg):
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)
    
    url_lower = url.lower().strip()
    
    # Route 1: Apple Podcasts URL → resolve via iTunes API
    if 'podcasts.apple.com' in url_lower:
        podcast_id, _ = _extract_apple_podcast_ids(url)
        if not podcast_id:
            return False, "Could not extract podcast ID from Apple Podcasts URL", None
        
        status(f"🎙️ Looking up podcast (ID: {podcast_id})...")
        success, feed_url_or_error, podcast_name = _lookup_rss_feed(podcast_id)
        if not success:
            return False, feed_url_or_error, None
        
        status(f"🎙️ Found '{podcast_name}' — loading episodes...")
        success, error, podcast_info = _parse_rss_feed(feed_url_or_error)
        if not success:
            return False, error, None
        
        return True, "", podcast_info
    
    # Route 2: Direct RSS feed URL
    if is_feed_url(url):
        status("🎙️ Loading podcast feed...")
        success, error, podcast_info = _parse_rss_feed(url)
        if not success:
            return False, error, None
        
        status(f"🎙️ Found '{podcast_info.name}' — {len(podcast_info.episodes)} episodes")
        return True, "", podcast_info
    
    return False, f"Not a recognised podcast or feed URL: {url}", None


def resolve_podcast_episode(
    url: str,
    progress_callback: Optional[Callable[[str], None]] = None
) -> Tuple[bool, str, Optional[PodcastEpisode], Optional[PodcastInfo]]:
    """
    Resolve a podcast URL to a specific episode with audio URL.
    
    This is the main entry point — handles the full pipeline:
    Apple Podcasts URL → iTunes API → RSS feed → episode → MP3 URL
    
    Args:
        url: Apple Podcasts URL
        progress_callback: Optional function(status_str) for progress updates
    
    Returns:
        (success, error_or_status, PodcastEpisode or None, PodcastInfo or None)
    """
    def status(msg):
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)
    
    if not is_podcast_url(url):
        return False, "Not a recognized podcast URL", None, None
    
    # Step 1: Extract IDs from URL
    podcast_id, episode_id = _extract_apple_podcast_ids(url)
    if not podcast_id:
        return False, "Could not extract podcast ID from URL", None, None
    
    status(f"🎙️ Looking up podcast (ID: {podcast_id})...")
    
    # Step 2: Resolve RSS feed URL via iTunes API
    success, feed_url_or_error, podcast_name = _lookup_rss_feed(podcast_id)
    if not success:
        return False, feed_url_or_error, None, None
    
    status(f"🎙️ Found '{podcast_name}' — loading episode list...")
    
    # Step 3: Parse RSS feed
    success, error, podcast_info = _parse_rss_feed(feed_url_or_error)
    if not success:
        return False, error, None, None
    
    status(f"🎙️ Found {len(podcast_info.episodes)} episodes — locating requested episode...")
    
    # Step 4: Find the specific episode
    if episode_id:
        episode = _find_episode_by_apple_id(podcast_info, episode_id)
    else:
        # No specific episode requested — use most recent
        episode = podcast_info.episodes[0] if podcast_info.episodes else None
    
    if not episode:
        return False, "Could not find the requested episode", None, podcast_info
    
    if not episode.audio_url:
        return False, f"No audio URL found for episode: {episode.title}", episode, podcast_info
    
    # Preserve the original URL
    episode.episode_url = url
    
    status(f"🎙️ Found: {episode.title}")
    
    return True, "OK", episode, podcast_info


def download_podcast_audio(
    episode: PodcastEpisode,
    dest_folder: Optional[str] = None,
    progress_callback: Optional[Callable[[str], None]] = None
) -> Tuple[bool, str]:
    """
    Download podcast episode audio to a local file.
    
    Args:
        episode: PodcastEpisode with audio_url set
        dest_folder: Where to save (default: temp directory)
        progress_callback: Optional function(status_str)
    
    Returns:
        (success, file_path_or_error)
    """
    if not REQUESTS_AVAILABLE:
        return False, "requests library not installed"
    
    if not episode.audio_url:
        return False, "No audio URL for this episode"
    
    def status(msg):
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)
    
    # Determine file extension from URL
    audio_url_lower = episode.audio_url.lower().split('?')[0]
    if '.m4a' in audio_url_lower:
        ext = '.m4a'
    elif '.ogg' in audio_url_lower:
        ext = '.ogg'
    elif '.opus' in audio_url_lower:
        ext = '.opus'
    elif '.wav' in audio_url_lower:
        ext = '.wav'
    else:
        ext = '.mp3'  # Default for podcasts
    
    # Create safe filename from episode title
    # Replace smart quotes/dashes with ASCII equivalents first
    safe_title = episode.title
    safe_title = safe_title.replace('\u2018', "'").replace('\u2019', "'")  # Smart single quotes
    safe_title = safe_title.replace('\u201c', '"').replace('\u201d', '"')  # Smart double quotes
    safe_title = safe_title.replace('\u2013', '-').replace('\u2014', '-')  # En/em dashes
    # Remove Windows-illegal characters and any remaining non-ASCII that could cause issues
    safe_title = re.sub(r'[<>:"/\\|?*]', '', safe_title)
    # Strip any remaining characters that aren't printable ASCII, spaces, or common punctuation
    safe_title = re.sub(r"[^\w\s\-'.!,()&+]", '', safe_title)[:80].strip()
    if not safe_title:
        safe_title = "podcast_episode"
    filename = f"{safe_title}{ext}"
    
    if dest_folder is None:
        dest_folder = tempfile.gettempdir()
    
    filepath = os.path.join(dest_folder, filename)
    
    try:
        status(f"🎙️ Downloading: {episode.title}...")
        
        response = requests.get(episode.audio_url, stream=True, timeout=300)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0
        
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0 and progress_callback:
                        pct = int(downloaded / total_size * 100)
                        mb = downloaded / (1024 * 1024)
                        total_mb = total_size / (1024 * 1024)
                        progress_callback(
                            f"🎙️ Downloading: {mb:.1f} / {total_mb:.1f} MB ({pct}%)"
                        )
        
        file_size = os.path.getsize(filepath)
        if file_size < 10000:  # Less than 10KB is suspicious
            os.remove(filepath)
            return False, "Downloaded file is too small — may be an error page"
        
        status(f"🎙️ Downloaded: {file_size / (1024*1024):.1f} MB")
        return True, filepath
    
    except requests.exceptions.Timeout:
        return False, "Download timed out (podcast may be too large)"
    except requests.exceptions.RequestException as e:
        return False, f"Download error: {e}"
    except Exception as e:
        return False, f"Error saving audio: {e}"


# ============================================================
# STANDALONE TESTING
# ============================================================

if __name__ == "__main__":
    import sys
    
    print("DocAnalyser Podcast Handler")
    print("=" * 50)
    
    if not FEEDPARSER_AVAILABLE:
        print("❌ feedparser not installed. Run: pip install feedparser")
        sys.exit(1)
    
    # Test URL
    test_url = sys.argv[1] if len(sys.argv) > 1 else \
        "https://podcasts.apple.com/au/podcast/triggernometry/id1375568988?i=1000749865261"
    
    print(f"URL: {test_url}")
    print(f"Is podcast URL: {is_podcast_url(test_url)}")
    print()
    
    # Extract IDs
    pod_id, ep_id = _extract_apple_podcast_ids(test_url)
    print(f"Podcast ID: {pod_id}")
    print(f"Episode ID: {ep_id}")
    print()
    
    # Resolve
    print("Resolving...")
    success, msg, episode, podcast = resolve_podcast_episode(
        test_url, 
        progress_callback=lambda s: print(f"  {s}")
    )
    
    if success and episode:
        print(f"\n✅ Episode found:")
        print(f"  Title:    {episode.title}")
        print(f"  Podcast:  {episode.podcast_name}")
        print(f"  Date:     {episode.published}")
        print(f"  Duration: {episode.duration}")
        print(f"  Audio:    {episode.audio_url[:100]}...")
        
        # Ask whether to download
        answer = input("\nDownload audio? (y/n): ").strip().lower()
        if answer == 'y':
            ok, path = download_podcast_audio(
                episode, 
                progress_callback=lambda s: print(f"  {s}")
            )
            if ok:
                print(f"\n✅ Saved to: {path}")
            else:
                print(f"\n❌ Download failed: {path}")
    else:
        print(f"\n❌ Failed: {msg}")
