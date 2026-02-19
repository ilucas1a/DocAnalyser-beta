"""
twitter_utils.py

X (Twitter) content fetching utilities for DocAnalyser.
Handles URL parsing and content extraction from X/Twitter posts.
Supports both text extraction and video download for transcription.

Note: X/Twitter is notoriously difficult to scrape. This module tries
multiple approaches but may not always succeed.

Usage:
    from twitter_utils import is_twitter_url, fetch_twitter_content, download_twitter_video
"""

import re
import os
import logging
import tempfile
from typing import Optional, Tuple, Any, Dict

# Try to import requests
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


def is_twitter_url(url: str) -> bool:
    """
    Check if a URL is a Twitter/X post URL.
    
    Args:
        url: URL string to check
        
    Returns:
        True if it's a Twitter/X URL, False otherwise
    """
    if not url:
        return False
    
    url_lower = url.lower()
    patterns = [
        'twitter.com/',
        'x.com/',
        'mobile.twitter.com/',
        'mobile.x.com/'
    ]
    
    # Must also contain /status/ to be a post (not just a profile)
    is_twitter_domain = any(pattern in url_lower for pattern in patterns)
    is_post = '/status/' in url_lower
    
    return is_twitter_domain and is_post


def extract_tweet_info(url: str) -> Optional[dict]:
    """
    Extract tweet ID and username from URL.
    
    Args:
        url: Twitter/X URL
        
    Returns:
        Dict with 'tweet_id' and 'username', or None if invalid
    """
    # Pattern: https://x.com/username/status/1234567890
    # or: https://twitter.com/username/status/1234567890
    pattern = r'(?:twitter\.com|x\.com)/([^/]+)/status/(\d+)'
    match = re.search(pattern, url, re.IGNORECASE)
    
    if match:
        return {
            'username': match.group(1),
            'tweet_id': match.group(2)
        }
    return None


def fetch_twitter_content(url: str, progress_callback=None) -> Tuple[bool, Any, str]:
    """
    Attempt to fetch content from a Twitter/X post.
    
    Tries multiple strategies:
    1. FxTwitter API (most reliable for text)
    2. yt-dlp for metadata extraction
    3. Nitter instances (Twitter frontend)
    
    Returns a dict with text content AND video info if available.
    
    Args:
        url: Twitter/X post URL
        progress_callback: Optional callback for status updates
        
    Returns:
        Tuple of (success, content_dict_or_error, title)
        
        content_dict contains:
        - 'text': The text content of the tweet
        - 'has_video': True if video is available
        - 'video_url': URL to download video (if has_video)
        - 'video_duration': Duration in seconds (if available)
    """
    if progress_callback:
        progress_callback("Attempting to fetch X/Twitter content...")
    
    tweet_info = extract_tweet_info(url)
    if not tweet_info:
        return False, "Invalid Twitter/X URL format", ""
    
    username = tweet_info['username']
    tweet_id = tweet_info['tweet_id']
    
    # Initialize result dict
    result = {
        'text': '',
        'has_video': False,
        'video_url': None,
        'video_duration': None,
        'author_name': username,
        'author_handle': username,
        'created_at': '',
        'original_url': url
    }
    
    # Strategy 1: Try FxTwitter/VxTwitter API first (most reliable for text)
    if progress_callback:
        progress_callback("Trying FxTwitter API...")
    
    fx_success = False
    if REQUESTS_AVAILABLE:
        try:
            # FxTwitter provides a JSON API
            fx_url = f"https://api.fxtwitter.com/{username}/status/{tweet_id}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(fx_url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if 'tweet' in data:
                    tweet = data['tweet']
                    text = tweet.get('text', '')
                    author_name = tweet.get('author', {}).get('name', username)
                    author_handle = tweet.get('author', {}).get('screen_name', username)
                    created_at = tweet.get('created_at', '')
                    
                    result['text'] = text
                    result['author_name'] = author_name
                    result['author_handle'] = author_handle
                    result['created_at'] = created_at
                    
                    # Check for video in media
                    media = tweet.get('media', {})
                    videos = media.get('videos', [])
                    
                    if videos:
                        result['has_video'] = True
                        # Get the best quality video URL
                        video_info = videos[0]
                        result['video_url'] = video_info.get('url', '')
                        result['video_duration'] = video_info.get('duration', 0)
                        print(f"🎥 FxTwitter found video: duration={result['video_duration']}s")
                    
                    # Also check for external video (YouTube embeds, etc.)
                    if not result['has_video']:
                        external = media.get('external', {})
                        if external and external.get('url'):
                            # External video link (like YouTube)
                            result['has_video'] = True
                            result['video_url'] = external.get('url', '')
                            result['video_type'] = 'external'
                            print(f"🎥 FxTwitter found external video: {result['video_url']}")
                    
                    if text and text.strip():
                        fx_success = True
                        
        except Exception as e:
            logging.info(f"FxTwitter API failed: {e}")
    
    # Strategy 2: Try yt-dlp (works for some tweets, especially with media)
    # This is especially good for detecting video
    if progress_callback:
        progress_callback("Trying yt-dlp extraction...")
    
    try:
        import yt_dlp
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'skip_download': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if info:
                # Extract text content if we don't have it yet
                description = info.get('description', '')
                if not result['text'] and description:
                    result['text'] = description
                    result['author_handle'] = info.get('uploader', username)
                    upload_date = info.get('upload_date', '')
                    if upload_date:
                        result['created_at'] = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"
                
                # Check for video - yt-dlp is great at detecting this
                duration = info.get('duration')
                formats = info.get('formats', [])
                
                # If there's a duration or video formats, it has video
                if duration and duration > 0:
                    result['has_video'] = True
                    result['video_duration'] = duration
                    result['video_url'] = url  # yt-dlp can download from original URL
                    print(f"🎥 yt-dlp found video: duration={duration}s, formats={len(formats)}")
                elif formats:
                    # Check if any format is video
                    video_formats = [f for f in formats if f.get('vcodec') != 'none']
                    if video_formats:
                        result['has_video'] = True
                        result['video_url'] = url
                        print(f"🎥 yt-dlp found video formats: {len(video_formats)}")
                    
    except Exception as e:
        logging.info(f"yt-dlp extraction failed: {e}")
    
    # Strategy 3: Try Nitter instances (for text if we still don't have it)
    if not result['text']:
        if progress_callback:
            progress_callback("Trying Nitter instances...")
        
        nitter_instances = [
            'nitter.net',
            'nitter.privacydev.net', 
            'nitter.poast.org',
            'nitter.bird.froth.zone',
        ]
        
        if REQUESTS_AVAILABLE:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            
            for instance in nitter_instances:
                try:
                    nitter_url = f"https://{instance}/{username}/status/{tweet_id}"
                    response = requests.get(nitter_url, headers=headers, timeout=10)
                    
                    if response.status_code == 200:
                        # Try to extract content from Nitter HTML
                        text = extract_text_from_nitter(response.text)
                        if text and "(No text content)" not in text:
                            result['text'] = text
                            break
                            
                except Exception as e:
                    logging.info(f"Nitter instance {instance} failed: {e}")
                    continue
    
    # Build the formatted content
    if result['text'] or result['has_video']:
        content_parts = []
        content_parts.append(f"Post by {result['author_name']} (@{result['author_handle']})")
        if result['created_at']:
            content_parts.append(f"Date: {result['created_at']}")
        content_parts.append(f"URL: {url}")
        
        if result['has_video']:
            duration_str = ""
            if result['video_duration']:
                mins = int(result['video_duration']) // 60
                secs = int(result['video_duration']) % 60
                duration_str = f" ({mins}:{secs:02d})"
            content_parts.append(f"🎥 Video attached{duration_str}")
        
        content_parts.append("")
        content_parts.append("--- Content ---")
        content_parts.append(result['text'] if result['text'] else "(No text content - video only)")
        
        result['formatted_text'] = '\n'.join(content_parts)
        
        # Build title
        title_text = result['text'][:50] if result['text'] else "Video"
        if len(result['text']) > 50:
            title_text += "..."
        title = f"X: {result['author_name']} - {title_text}"
        
        return True, result, title
    
    # All strategies failed
    return False, (
        "Could not fetch X/Twitter content.\n\n"
        "X/Twitter blocks most automated access. Alternatives:\n"
        "• Copy the tweet text manually and paste it\n"
        "• Use the browser's 'Reader Mode' and copy from there\n"
        "• Take a screenshot and use OCR"
    ), ""


def extract_text_from_nitter(html: str) -> Optional[str]:
    """
    Extract tweet text content from Nitter HTML response.
    
    Args:
        html: Raw HTML from Nitter
        
    Returns:
        Extracted text, or None if extraction failed
    """
    try:
        # Look for tweet-content class
        content_match = re.search(
            r'<div class="tweet-content[^"]*"[^>]*>(.*?)</div>',
            html,
            re.DOTALL | re.IGNORECASE
        )
        
        if content_match:
            content_html = content_match.group(1)
            
            # Strip HTML tags
            text = re.sub(r'<[^>]+>', ' ', content_html)
            text = re.sub(r'\s+', ' ', text).strip()
            
            # Decode HTML entities
            import html as html_module
            text = html_module.unescape(text)
            
            return text if text else None
                
    except Exception as e:
        logging.info(f"Nitter content extraction failed: {e}")
    
    return None


def download_twitter_video(url: str, progress_callback=None) -> Tuple[bool, str, str]:
    """
    Download video from a Twitter/X post for transcription.
    
    Args:
        url: Twitter/X post URL
        progress_callback: Optional callback for status updates
        
    Returns:
        Tuple of (success, file_path_or_error, title)
    """
    if progress_callback:
        progress_callback("🎥 Downloading X/Twitter video...")
    
    try:
        import yt_dlp
        
        # Create temp file for the download
        temp_dir = tempfile.gettempdir()
        output_template = os.path.join(temp_dir, 'twitter_%(id)s.%(ext)s')
        
        ydl_opts = {
            'format': 'bestaudio/best',  # Prefer audio-only for transcription
            'outtmpl': output_template,
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }
        
        # First try audio extraction
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                if progress_callback:
                    progress_callback("🎥 Extracting audio from video...")
                info = ydl.extract_info(url, download=True)
                
                if info:
                    # Find the downloaded file
                    tweet_id = info.get('id', 'unknown')
                    expected_path = os.path.join(temp_dir, f'twitter_{tweet_id}.mp3')
                    
                    if os.path.exists(expected_path):
                        title = info.get('title', f'X video by @{info.get("uploader", "unknown")}')
                        return True, expected_path, title
                    
                    # Try to find any matching file
                    for ext in ['mp3', 'm4a', 'wav', 'mp4', 'webm']:
                        alt_path = os.path.join(temp_dir, f'twitter_{tweet_id}.{ext}')
                        if os.path.exists(alt_path):
                            title = info.get('title', f'X video by @{info.get("uploader", "unknown")}')
                            return True, alt_path, title
                            
        except Exception as e:
            logging.info(f"Audio extraction failed, trying video download: {e}")
        
        # Fallback: download video (will be larger but should work)
        ydl_opts_video = {
            'format': 'best[ext=mp4]/best',
            'outtmpl': output_template,
            'quiet': True,
            'no_warnings': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts_video) as ydl:
            if progress_callback:
                progress_callback("🎥 Downloading video...")
            info = ydl.extract_info(url, download=True)
            
            if info:
                tweet_id = info.get('id', 'unknown')
                
                # Find the downloaded file
                for ext in ['mp4', 'webm', 'mkv', 'mp3', 'm4a']:
                    path = os.path.join(temp_dir, f'twitter_{tweet_id}.{ext}')
                    if os.path.exists(path):
                        title = info.get('title', f'X video by @{info.get("uploader", "unknown")}')
                        return True, path, title
        
        return False, "Could not download video - file not found after download", ""
        
    except ImportError:
        return False, "yt-dlp is required for video download. Install with: pip install yt-dlp", ""
    except Exception as e:
        return False, f"Video download failed: {str(e)}", ""
