"""
youtube_utils.py

YouTube transcript fetching utilities for DocAnalyser.
Handles URL parsing, transcript fetching, and audio fallback.

Usage:
    from youtube_utils import extract_video_id, fetch_youtube_transcript, fetch_youtube_with_audio_fallback, is_youtube_url
"""

import re
from typing import Optional, Tuple, Any

import sys
import logging
import os
import tempfile

# Check if youtube-transcript-api is available
try:
    from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
    YOUTUBE_TRANSCRIPT_AVAILABLE = True
except ImportError:
    YOUTUBE_TRANSCRIPT_AVAILABLE = False
    # Use logging instead of print to avoid encoding issues with frozen exe
    if getattr(sys, 'frozen', False):
        logging.warning("youtube-transcript-api not available")
    else:
        print("Warning: youtube-transcript-api not available")
        print("   Install with: pip install youtube-transcript-api")


def _get_browser_cookies_file():
    """
    Try to extract cookies from an available browser using yt-dlp.
    Returns a cookie file path or None.
    """
    try:
        import subprocess
        
        # List of browsers to try, in order of preference
        browsers = ['chrome', 'firefox', 'edge', 'brave', 'opera', 'chromium']
        
        for browser in browsers:
            try:
                # Create a temporary cookie file
                cookie_file = os.path.join(tempfile.gettempdir(), f'docanalyzer_cookies_{browser}.txt')
                
                # Build the command - hide console window on Windows
                cmd = ['yt-dlp', '--cookies-from-browser', browser, '--cookies', cookie_file, 
                       '--skip-download', '--quiet', '--no-warnings', 'https://www.youtube.com/']
                
                # Try to extract cookies using yt-dlp
                kwargs = {'capture_output': True, 'text': True, 'timeout': 30}
                if sys.platform == 'win32':
                    kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
                
                result = subprocess.run(cmd, **kwargs)
                
                if os.path.exists(cookie_file) and os.path.getsize(cookie_file) > 100:
                    logging.info(f"Successfully extracted cookies from {browser}")
                    return cookie_file
            except subprocess.TimeoutExpired:
                logging.debug(f"Timeout extracting cookies from {browser}")
                continue
            except FileNotFoundError:
                logging.debug("yt-dlp not found in PATH")
                return None
            except Exception as e:
                logging.debug(f"Could not extract cookies from {browser}: {e}")
                continue
        
        return None
    except Exception as e:
        logging.debug(f"Cookie extraction failed: {e}")
        return None


def _load_cookies_for_transcript_api(cookie_file: str):
    """
    Load cookies from a Netscape cookie file for use with youtube_transcript_api.
    Returns a cookies dict suitable for requests, or None.
    """
    try:
        from http.cookiejar import MozillaCookieJar
        
        jar = MozillaCookieJar(cookie_file)
        jar.load(ignore_discard=True, ignore_expires=True)
        
        # Convert to dict for youtube_transcript_api
        cookies = {}
        for cookie in jar:
            if 'youtube' in cookie.domain or 'google' in cookie.domain:
                cookies[cookie.name] = cookie.value
        
        if cookies:
            logging.info(f"Loaded {len(cookies)} YouTube cookies")
            return cookies
        return None
    except Exception as e:
        logging.debug(f"Could not load cookies: {e}")
        return None



def extract_video_id(url_or_id: str) -> Optional[str]:
    """
    Extract YouTube video ID from URL or return the ID if already provided.

    Supports:
    - https://www.youtube.com/watch?v=VIDEO_ID
    - https://youtu.be/VIDEO_ID
    - https://youtube.com/embed/VIDEO_ID
    - https://youtube.com/v/VIDEO_ID
    - https://youtube.com/live/VIDEO_ID
    - https://youtube.com/shorts/VIDEO_ID
    - VIDEO_ID (direct ID)

    Args:
        url_or_id: YouTube URL or video ID

    Returns:
        Video ID string or None if invalid format
    """
    if not url_or_id:
        return None

    url_or_id = url_or_id.strip()

    # If it's already just an ID (11 characters, no special chars except - and _)
    if len(url_or_id) == 11 and re.match(r'^[a-zA-Z0-9_-]{11}$', url_or_id):
        return url_or_id

    # Extract from standard YouTube URL
    patterns = [
        r'(?:youtube\.com\/watch\?v=)([a-zA-Z0-9_-]{11})',  # youtube.com/watch?v=
        r'(?:youtu\.be\/)([a-zA-Z0-9_-]{11})',  # youtu.be/
        r'(?:youtube\.com\/embed\/)([a-zA-Z0-9_-]{11})',  # youtube.com/embed/
        r'(?:youtube\.com\/v\/)([a-zA-Z0-9_-]{11})',  # youtube.com/v/
        r'(?:youtube\.com\/live\/)([a-zA-Z0-9_-]{11})',  # youtube.com/live/ (live streams)
        r'(?:youtube\.com\/shorts\/)([a-zA-Z0-9_-]{11})',  # youtube.com/shorts/
    ]

    for pattern in patterns:
        match = re.search(pattern, url_or_id)
        if match:
            return match.group(1)

    return None


def is_youtube_url(url: str) -> bool:
    """
    Check if a URL is a YouTube video URL.
    
    Args:
        url: URL string to check
        
    Returns:
        True if it's a YouTube URL, False otherwise
    """
    if not url:
        return False
    
    youtube_patterns = [
        'youtube.com/watch',
        'youtu.be/',
        'youtube.com/embed/',
        'youtube.com/v/',
        'youtube.com/live/',
        'youtube.com/shorts/',
        'm.youtube.com'
    ]
    url_lower = url.lower()
    return any(pattern in url_lower for pattern in youtube_patterns)


def fetch_youtube_transcript(url_or_id: str, use_cookies: bool = False) -> Tuple[bool, Any, str, str, dict]:
    """
    Fetch YouTube transcript using youtube-transcript-api.
    
    Uses yt-dlp to get the actual video title for proper naming.
    Includes pre-formatted timestamps to prevent the "Page" bug.
    
    Tries multiple approaches to find transcripts:
    1. Fetch with English preference
    2. Fetch without language restriction (any available)
    3. List transcripts and fetch the first available one
    4. If blocked, retry with browser cookies

    Args:
        url_or_id: YouTube URL or video ID
        use_cookies: If True, try to use browser cookies to bypass bot detection

    Returns:
        Tuple of (success, result/error, title, source_type, metadata)
        - success: True if transcript fetched successfully
        - result: List of entry dicts if success, error message if failure
        - title: Video title (e.g., "YouTube: Video Title")
        - source_type: Always "youtube"
        - metadata: Dict with additional info including 'published_date'
    """
    # Check if library is available
    if not YOUTUBE_TRANSCRIPT_AVAILABLE:
        return False, "youtube-transcript-api not installed. Install with: pip install youtube-transcript-api", "", "youtube", {}

    try:
        video_id = extract_video_id(url_or_id)
        if not video_id:
            return False, "Invalid YouTube URL or ID", "", "youtube", {}

        # NEW API (v1.2.3+): Create instance with optional cookies
        cookies = None
        if use_cookies:
            cookie_file = _get_browser_cookies_file()
            if cookie_file:
                cookies = _load_cookies_for_transcript_api(cookie_file)
                logging.info("Using browser cookies for transcript fetch")
        
        # Create API instance - the new API supports cookies parameter
        if cookies:
            api = YouTubeTranscriptApi(cookies=cookies)
        else:
            api = YouTubeTranscriptApi()
        
        fetched = None
        last_error = None
        is_blocked = False
        
        # Strategy 1: Try fetching with English preference
        try:
            fetched = api.fetch(video_id, languages=['en', 'en-US', 'en-GB'])
            logging.info(f"Fetched transcript with English preference")
        except Exception as e:
            last_error = e
            error_str = str(e).lower()
            is_blocked = 'blocked' in error_str or 'bot' in error_str or 'sign in' in error_str
            logging.info(f"English preference failed: {e}")
        
        # Strategy 2: Try fetching without language restriction
        if fetched is None and not is_blocked:
            try:
                fetched = api.fetch(video_id)
                logging.info(f"Fetched transcript without language restriction")
            except Exception as e:
                last_error = e
                error_str = str(e).lower()
                is_blocked = 'blocked' in error_str or 'bot' in error_str or 'sign in' in error_str
                logging.info(f"No language restriction failed: {e}")
        
        # Strategy 3: List available transcripts and fetch first one
        if fetched is None and not is_blocked:
            try:
                transcript_list = api.list(video_id)
                available = list(transcript_list)
                if available:
                    logging.info(f"Available transcripts: {[t.language_code for t in available]}")
                    # Prefer English, then any manual, then any auto-generated
                    english_transcripts = [t for t in available if t.language_code.startswith('en')]
                    manual_transcripts = [t for t in available if not t.is_generated]
                    
                    if english_transcripts:
                        fetched = english_transcripts[0].fetch()
                        logging.info(f"Fetched English transcript: {english_transcripts[0].language_code}")
                    elif manual_transcripts:
                        fetched = manual_transcripts[0].fetch()
                        logging.info(f"Fetched manual transcript: {manual_transcripts[0].language_code}")
                    elif available:
                        fetched = available[0].fetch()
                        logging.info(f"Fetched first available transcript: {available[0].language_code}")
            except Exception as e:
                last_error = e
                error_str = str(e).lower()
                is_blocked = 'blocked' in error_str or 'bot' in error_str or 'sign in' in error_str
                logging.info(f"List/fetch strategy failed: {e}")
        
        # Strategy 4: If blocked and we haven't tried cookies yet, retry with cookies
        if fetched is None and is_blocked and not use_cookies:
            logging.info("YouTube appears to be blocking requests. Attempting with browser cookies...")
            return fetch_youtube_transcript(url_or_id, use_cookies=True)
        
        # If we still don't have a transcript, raise the last error
        if fetched is None:
            if last_error:
                raise last_error
            else:
                raise NoTranscriptFound(video_id, [], None)

        # Import the timestamp formatter from utils
        from utils import format_timestamp

        # Extract snippets with properly formatted timestamps
        # Handle both FetchedTranscript objects and raw list results
        entries = []
        
        # Check if fetched has snippets attribute (new API) or is iterable (old API / list result)
        if hasattr(fetched, 'snippets'):
            snippets = fetched.snippets
        elif hasattr(fetched, '__iter__'):
            snippets = fetched
        else:
            snippets = []
        
        for snippet in snippets:
            # Handle both object attributes and dict access
            if hasattr(snippet, 'start'):
                start = snippet.start
                text = snippet.text
                duration = getattr(snippet, 'duration', 0)
            elif isinstance(snippet, dict):
                start = snippet.get('start', 0)
                text = snippet.get('text', '')
                duration = snippet.get('duration', 0)
            else:
                continue
                
            # Format timestamp properly to avoid "Page" bug
            timestamp_str = format_timestamp(start)

            entries.append({
                'text': text,
                'start': start,
                'duration': duration,
                'location': timestamp_str  # Pre-formatted location prevents "Page" bug
            })

        # Get actual video title and upload date using yt-dlp (with cookies if needed)
        published_date = None
        try:
            import yt_dlp
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False  # Need full metadata for upload_date
            }
            
            # Add cookies if we have them
            cookie_file = _get_browser_cookies_file()
            if cookie_file:
                ydl_opts['cookiefile'] = cookie_file
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
                video_title = info.get('title', video_id)
                title = f"YouTube: {video_title}"
                
                # Extract upload date (format: YYYYMMDD)
                upload_date = info.get('upload_date')
                if upload_date and len(upload_date) == 8:
                    # Convert YYYYMMDD to YYYY-MM-DD
                    published_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}"
        except Exception as e:
            # Fallback to video ID if title fetch fails
            logging.warning(f"Could not fetch video title: {e}")
            title = f"YouTube: {video_id}"
        
        # Build metadata dict
        metadata = {}
        if published_date:
            metadata['published_date'] = published_date

        return True, entries, title, "youtube", metadata

    except NoTranscriptFound:
        return False, "No transcript found for this video", "", "youtube", {}
    except TranscriptsDisabled:
        return False, "Transcripts are disabled for this video", "", "youtube", {}
    except Exception as e:
        error_msg = str(e)
        # Check if this is a bot detection error
        if 'blocked' in error_msg.lower() or 'bot' in error_msg.lower() or 'sign in' in error_msg.lower():
            return False, f"YouTube is blocking requests (bot detection). Try again later or sign into YouTube in your browser. Error: {error_msg}", "", "youtube", {}
        return False, f"Error fetching transcript: {error_msg}", "", "youtube", {}


def fetch_youtube_with_audio_fallback(
    url_or_id: str,
    api_key: str,
    engine: str,
    options: dict,
    bypass_cache: bool,
    progress_callback,
    get_audio_func=None
) -> Tuple[bool, Any, str, str, dict]:
    """
    Try to get YouTube transcript, fallback to audio transcription if unavailable.

    Args:
        url_or_id: YouTube URL or video ID
        api_key: API key for audio transcription service
        engine: Transcription engine to use
        options: Dict with transcription options (language, speaker_diarization, enable_vad)
        bypass_cache: Whether to bypass cached transcripts
        progress_callback: Function to call with progress updates
        get_audio_func: Function to get audio module (for lazy loading)

    Returns:
        Tuple of (success, result/error, title, source_type, metadata)
    """
    # First try regular transcript
    progress_callback("Attempting to fetch YouTube transcript...")
    success, result, title, source_type, metadata = fetch_youtube_transcript(url_or_id)

    if success:
        return True, result, title, "youtube", metadata

    # Save the transcript error for later
    transcript_error = result
    
    # Check if this is a bot detection error - if so, provide more helpful message
    if 'blocked' in transcript_error.lower() or 'bot' in transcript_error.lower():
        progress_callback("YouTube is blocking requests. Trying audio fallback with cookies...")
    else:
        progress_callback(f"Transcript unavailable ({transcript_error}). Trying audio fallback...")

    try:
        video_id = extract_video_id(url_or_id)
        if not video_id:
            return False, "Invalid YouTube URL or ID", "", "youtube", {}

        # Download audio and transcribe using audio_handler
        if get_audio_func:
            audio_module = get_audio_func()
        else:
            from audio_handler import transcribe_youtube_audio
            import audio_handler as audio_module

        # Try to get cookies for yt-dlp
        cookie_file = _get_browser_cookies_file()
        
        # If there's an AssemblyAI key in options, use it as the primary api_key for AssemblyAI engine
        effective_api_key = api_key
        if engine == 'assemblyai' and options.get('assemblyai_api_key'):
            effective_api_key = options['assemblyai_api_key']
        
        # Pass cookie_file to yt-dlp for authenticated downloads (bypasses 403 errors)
        entries = audio_module.transcribe_youtube_audio(
            video_id=video_id,
            api_key=effective_api_key,
            engine=engine,
            language=options.get('language', None),  # None for auto-detect
            speaker_diarization=options.get('speaker_diarization', False),
            enable_vad=options.get('enable_vad', True),
            bypass_cache=bypass_cache,
            progress_callback=progress_callback,
            cookie_file=cookie_file
        )

        # Try to get video metadata for published_date
        published_date = None
        try:
            import yt_dlp
            ydl_opts = {'quiet': True, 'no_warnings': True}
            if cookie_file:
                ydl_opts['cookiefile'] = cookie_file
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
                video_title = info.get('title', video_id)
                title = f"YouTube (Audio): {video_title}"
                upload_date = info.get('upload_date')
                if upload_date and len(upload_date) == 8:
                    published_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}"
        except:
            title = f"YouTube (Audio): {video_id}"
        
        audio_metadata = {}
        if published_date:
            audio_metadata['published_date'] = published_date
            
        return True, entries, title, "audio_transcription", audio_metadata

    except Exception as e:
        audio_error = str(e)
        
        # Build a helpful combined error message
        error_parts = []
        error_parts.append(f"Transcript fetch failed: {transcript_error}")
        error_parts.append(f"Audio fallback failed: {audio_error}")
        
        # Check error types and provide helpful suggestions
        audio_lower = audio_error.lower()
        is_bot_block = ('blocked' in transcript_error.lower() or 'bot' in transcript_error.lower() or 
            'sign in' in audio_lower or 'bot' in audio_lower)
        is_403 = '403' in audio_lower or 'forbidden' in audio_lower
        is_dpapi = 'dpapi' in audio_lower
        
        if is_dpapi:
            error_parts.append("")
            error_parts.append("💡 yt-dlp couldn't read browser cookies (DPAPI issue).")
            error_parts.append("   Fix options:")
            error_parts.append("   1. Update yt-dlp:  pip install -U yt-dlp")
            error_parts.append("   2. Install Firefox and sign into YouTube there")
            error_parts.append("      (Firefox cookies don't have this issue)")
            error_parts.append("   3. Close all Chrome windows and retry")
        elif is_403:
            error_parts.append("")
            error_parts.append("💡 This is usually fixed by updating yt-dlp:")
            error_parts.append("   pip install -U yt-dlp")
            error_parts.append("")
            error_parts.append("If that doesn't help, try signing into YouTube")
            error_parts.append("in your browser first, then retry.")
        elif is_bot_block:
            error_parts.append("")
            error_parts.append("YouTube is blocking automated requests.")
            error_parts.append("Try signing into YouTube in your browser, then try again.")
        
        combined_error = "\n".join(error_parts)
        return False, combined_error, "", "youtube", {}


def get_youtube_transcript(url_or_id: str, status_callback=None) -> Optional[dict]:
    """
    Simplified interface to fetch YouTube transcript.
    
    Args:
        url_or_id: YouTube URL or video ID
        status_callback: Optional callback for status updates
        
    Returns:
        Dict with 'text' and 'title' keys if successful, None otherwise
    """
    # First, try to get the video title (quick operation)
    video_id = extract_video_id(url_or_id)
    video_title = None
    
    if video_id:
        try:
            import yt_dlp
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True  # Don't download, just get metadata
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
                video_title = info.get('title')
        except Exception:
            pass  # Fall back to generic message
    
    # Update status with actual title if we have it
    if status_callback:
        if video_title:
            status_callback(f"Fetching: YouTube: {video_title}")
        else:
            status_callback("Fetching YouTube transcript...")
    
    success, result, title, _, _ = fetch_youtube_transcript(url_or_id)
    
    if success and isinstance(result, list):
        # Convert entries to plain text
        text_parts = []
        for entry in result:
            text_parts.append(entry.get('text', ''))
        
        full_text = '\n'.join(text_parts)
        return {
            'text': full_text,
            'title': title,
            'entries': result
        }
    
    return None
