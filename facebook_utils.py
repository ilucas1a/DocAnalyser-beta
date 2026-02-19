"""
facebook_utils.py

Facebook video/reel utilities for DocAnalyser.
Handles URL detection, metadata extraction, audio download, and transcription.

Facebook videos don't have transcripts like YouTube, so we:
1. Extract audio using yt-dlp
2. Transcribe using OpenAI Whisper or AssemblyAI

Usage:
    from facebook_utils import is_facebook_video_url, fetch_facebook_content
"""

import re
import os
import tempfile
import time
from typing import Optional, Tuple, Dict, Any, Callable

# Check for required libraries
try:
    import yt_dlp
    YTDLP_AVAILABLE = True
except ImportError:
    YTDLP_AVAILABLE = False
    print("Warning: yt-dlp not available for Facebook support")

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


def is_facebook_video_url(url: str) -> bool:
    """
    Check if a URL is a Facebook video, reel, or watch URL.
    
    Supports:
    - https://www.facebook.com/reel/XXXXX
    - https://www.facebook.com/watch/?v=XXXXX
    - https://www.facebook.com/username/videos/XXXXX
    - https://fb.watch/XXXXX
    - https://www.facebook.com/share/v/XXXXX
    - https://www.facebook.com/share/r/XXXXX (shared reels)
    
    Args:
        url: URL to check
        
    Returns:
        True if URL is a Facebook video
    """
    if not url:
        return False
    
    url_lower = url.strip().lower()
    
    facebook_patterns = [
        r'facebook\.com/reel/',
        r'facebook\.com/watch',
        r'facebook\.com/[^/]+/videos/',
        r'facebook\.com/video\.php',
        r'facebook\.com/share/v/',
        r'facebook\.com/share/r/',
        r'fb\.watch/',
        r'fb\.com/reel/',
    ]
    
    for pattern in facebook_patterns:
        if re.search(pattern, url_lower):
            return True
    
    return False


def get_facebook_metadata(url: str, status_callback: Optional[Callable] = None) -> Tuple[bool, Dict]:
    """
    Extract metadata from a Facebook video using yt-dlp.
    
    Args:
        url: Facebook video URL
        status_callback: Optional callback for status updates
        
    Returns:
        Tuple of (success, metadata_dict or error_dict)
        metadata_dict contains: title, description, uploader, duration, etc.
    """
    if not YTDLP_AVAILABLE:
        return False, {"error": "yt-dlp not available. Install with: pip install yt-dlp"}
    
    print(f"[Facebook] Getting metadata for: {url}")
    if status_callback:
        status_callback("Connecting to Facebook...")
    
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'skip_download': True,
            'socket_timeout': 30,  # 30 second timeout
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print("[Facebook] Extracting video info (this may take a moment)...")
            if status_callback:
                status_callback("Extracting video info...")
            
            info = ydl.extract_info(url, download=False)
            
            if info:
                metadata = {
                    'title': info.get('title', 'Facebook Video'),
                    'description': info.get('description', ''),
                    'uploader': info.get('uploader', 'Unknown'),
                    'duration': info.get('duration', 0),
                    'thumbnail': info.get('thumbnail', ''),
                    'view_count': info.get('view_count', 0),
                    'like_count': info.get('like_count', 0),
                    'id': info.get('id', ''),
                    'url': url,
                }
                print(f"[Facebook] Got metadata: {metadata.get('title')} ({metadata.get('duration')}s)")
                return True, metadata
            else:
                return False, {"error": "Could not extract metadata"}
                
    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e)
        print(f"[Facebook] yt-dlp DownloadError: {error_msg[:200]}")
        if "login" in error_msg.lower() or "private" in error_msg.lower():
            return False, {"error": "Video may be private or require login. Only public videos are supported."}
        if "unavailable" in error_msg.lower():
            return False, {"error": "Video is unavailable or has been removed."}
        if "timed out" in error_msg.lower() or "timeout" in error_msg.lower():
            return False, {"error": "Connection timed out. Facebook may be blocking the request."}
        return False, {"error": f"Could not access video: {error_msg[:200]}"}
    except Exception as e:
        print(f"[Facebook] Exception: {str(e)[:200]}")
        return False, {"error": f"Error extracting metadata: {str(e)[:200]}"}


def extract_facebook_audio(url: str, output_dir: Optional[str] = None, 
                           status_callback: Optional[Callable] = None) -> Tuple[bool, str]:
    """
    Extract audio from a Facebook video using yt-dlp.
    
    Args:
        url: Facebook video URL
        output_dir: Directory to save audio file (uses temp dir if None)
        status_callback: Optional callback for status updates
        
    Returns:
        Tuple of (success, audio_file_path or error_message)
    """
    if not YTDLP_AVAILABLE:
        return False, "yt-dlp not available. Install with: pip install yt-dlp"
    
    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix='facebook_audio_')
    
    # Generate output filename
    output_template = os.path.join(output_dir, 'facebook_%(id)s.%(ext)s')
    
    print(f"[Facebook] Downloading audio to: {output_dir}")
    if status_callback:
        status_callback("Downloading audio from Facebook...")
    
    # Progress hook to show download progress
    last_update = [0]  # Use list to allow modification in nested function
    def progress_hook(d):
        if d['status'] == 'downloading':
            now = time.time()
            if now - last_update[0] > 2:  # Update every 2 seconds
                last_update[0] = now
                percent = d.get('_percent_str', 'N/A')
                speed = d.get('_speed_str', 'N/A')
                print(f"[Facebook] Downloading: {percent} at {speed}")
                if status_callback:
                    status_callback(f"Downloading: {percent} at {speed}")
        elif d['status'] == 'finished':
            print(f"[Facebook] Download finished, processing...")
            if status_callback:
                status_callback("Download complete, extracting audio...")
    
    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': output_template,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': True,
            'no_warnings': True,
            'socket_timeout': 30,
            'progress_hooks': [progress_hook],
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            if info:
                video_id = info.get('id', 'unknown')
                print(f"[Facebook] Looking for audio file with ID: {video_id}")
                
                # Find the downloaded file
                expected_file = os.path.join(output_dir, f'facebook_{video_id}.mp3')
                if os.path.exists(expected_file):
                    print(f"[Facebook] Found audio file: {expected_file}")
                    return True, expected_file
                
                # Try to find any matching audio file
                for f in os.listdir(output_dir):
                    if f.startswith(f'facebook_{video_id}') and f.endswith(('.mp3', '.m4a', '.wav', '.opus')):
                        filepath = os.path.join(output_dir, f)
                        print(f"[Facebook] Found audio file: {filepath}")
                        return True, filepath
                
                # Look for any audio file in the directory
                for f in os.listdir(output_dir):
                    if f.endswith(('.mp3', '.m4a', '.wav', '.opus')):
                        filepath = os.path.join(output_dir, f)
                        print(f"[Facebook] Found audio file: {filepath}")
                        return True, filepath
                
                print(f"[Facebook] No audio file found in {output_dir}")
                print(f"[Facebook] Directory contents: {os.listdir(output_dir)}")
                return False, "Audio file not found after extraction"
            else:
                return False, "Could not extract video information"
                
    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e)
        print(f"[Facebook] Download error: {error_msg[:300]}")
        if "login" in error_msg.lower():
            return False, "This video requires Facebook login. Only public videos are supported."
        if "private" in error_msg.lower():
            return False, "This video is private and cannot be accessed."
        if "unavailable" in error_msg.lower():
            return False, "This video is unavailable or has been removed."
        if "ffmpeg" in error_msg.lower():
            return False, "FFmpeg not found. Please install FFmpeg for audio extraction."
        if "timed out" in error_msg.lower() or "timeout" in error_msg.lower():
            return False, "Download timed out. Facebook may be blocking the request."
        return False, f"Download error: {error_msg[:200]}"
    except Exception as e:
        print(f"[Facebook] Exception during download: {str(e)[:300]}")
        return False, f"Error extracting audio: {str(e)[:200]}"


def transcribe_audio_openai(audio_path: str, api_key: str, 
                            status_callback: Optional[Callable] = None) -> Tuple[bool, str]:
    """
    Transcribe audio using OpenAI Whisper API.
    
    Args:
        audio_path: Path to audio file
        api_key: OpenAI API key
        status_callback: Optional callback for status updates
        
    Returns:
        Tuple of (success, transcript or error_message)
    """
    if not OPENAI_AVAILABLE:
        return False, "OpenAI library not available. Install with: pip install openai"
    
    if not api_key:
        return False, "OpenAI API key not configured. Please set your API key in Settings."
    
    print(f"[Facebook] Transcribing audio file: {audio_path}")
    if status_callback:
        status_callback("Transcribing with OpenAI Whisper...")
    
    try:
        client = OpenAI(api_key=api_key)
        
        # Check file size
        file_size = os.path.getsize(audio_path)
        print(f"[Facebook] Audio file size: {file_size / 1024 / 1024:.2f} MB")
        
        if file_size > 25 * 1024 * 1024:  # 25MB limit
            return False, f"Audio file too large ({file_size / 1024 / 1024:.1f} MB). Whisper API limit is 25MB."
        
        with open(audio_path, 'rb') as audio_file:
            response = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="text"
            )
        
        if response:
            print(f"[Facebook] Transcription complete: {len(response)} characters")
            return True, response
        else:
            return False, "Empty response from Whisper API"
            
    except Exception as e:
        error_msg = str(e)
        print(f"[Facebook] Transcription error: {error_msg[:200]}")
        if "api_key" in error_msg.lower() or "authentication" in error_msg.lower():
            return False, "Invalid OpenAI API key"
        if "file" in error_msg.lower() and "large" in error_msg.lower():
            return False, "Audio file too large for Whisper API (max 25MB)"
        return False, f"Transcription error: {error_msg[:200]}"


def transcribe_audio_assemblyai(audio_path: str, api_key: str,
                                status_callback: Optional[Callable] = None) -> Tuple[bool, str]:
    """
    Transcribe audio using AssemblyAI API.
    
    Args:
        audio_path: Path to audio file
        api_key: AssemblyAI API key
        status_callback: Optional callback for status updates
        
    Returns:
        Tuple of (success, transcript or error_message)
    """
    if not REQUESTS_AVAILABLE:
        return False, "requests library not available"
    
    if not api_key:
        return False, "AssemblyAI API key not configured"
    
    headers = {"authorization": api_key}
    
    try:
        # Step 1: Upload the audio file
        print("[Facebook] Uploading audio to AssemblyAI...")
        if status_callback:
            status_callback("Uploading audio to AssemblyAI...")
        
        with open(audio_path, 'rb') as f:
            upload_response = requests.post(
                "https://api.assemblyai.com/v2/upload",
                headers=headers,
                data=f,
                timeout=300
            )
        
        if upload_response.status_code != 200:
            return False, f"Upload failed: {upload_response.text[:200]}"
        
        audio_url = upload_response.json()['upload_url']
        print("[Facebook] Upload complete, requesting transcription...")
        
        # Step 2: Request transcription
        if status_callback:
            status_callback("Transcribing with AssemblyAI...")
        
        transcript_response = requests.post(
            "https://api.assemblyai.com/v2/transcript",
            headers=headers,
            json={"audio_url": audio_url},
            timeout=30
        )
        
        if transcript_response.status_code != 200:
            return False, f"Transcription request failed: {transcript_response.text[:200]}"
        
        transcript_id = transcript_response.json()['id']
        
        # Step 3: Poll for completion
        polling_url = f"https://api.assemblyai.com/v2/transcript/{transcript_id}"
        
        max_attempts = 120  # 10 minutes max
        for attempt in range(max_attempts):
            poll_response = requests.get(polling_url, headers=headers, timeout=30)
            result = poll_response.json()
            
            status = result.get('status')
            
            if status == 'completed':
                print("[Facebook] AssemblyAI transcription complete")
                return True, result.get('text', '')
            elif status == 'error':
                return False, f"Transcription failed: {result.get('error', 'Unknown error')}"
            
            if status_callback and attempt % 6 == 0:  # Update every 30 seconds
                status_callback(f"Transcribing... ({attempt * 5}s)")
            
            time.sleep(5)
        
        return False, "Transcription timed out"
        
    except Exception as e:
        print(f"[Facebook] AssemblyAI error: {str(e)[:200]}")
        return False, f"AssemblyAI error: {str(e)[:200]}"


def fetch_facebook_content(url: str, 
                          openai_api_key: Optional[str] = None,
                          assemblyai_api_key: Optional[str] = None,
                          transcription_provider: str = 'openai',
                          status_callback: Optional[Callable] = None) -> Tuple[bool, Any, str, str]:
    """
    Fetch and transcribe content from a Facebook video/reel.
    
    This is the main entry point, matching substack_utils.fetch_substack_content signature.
    
    Args:
        url: Facebook video URL
        openai_api_key: OpenAI API key for Whisper transcription
        assemblyai_api_key: AssemblyAI API key (alternative)
        transcription_provider: 'openai' or 'assemblyai'
        status_callback: Optional callback for status updates
        
    Returns:
        Tuple of (success, result_dict, title, content_type)
        
        result_dict contains:
        - 'text': Transcribed text content
        - 'entries': List with single entry containing transcript
        - 'duration': Video duration in seconds
        - 'uploader': Video uploader name
        - 'source_url': Original URL
        - 'needs_transcription': False (already transcribed)
    """
    print(f"\n{'='*60}")
    print(f"[Facebook] Starting fetch for: {url}")
    print(f"[Facebook] Provider: {transcription_provider}")
    print(f"[Facebook] OpenAI key: {'Yes' if openai_api_key else 'No'}")
    print(f"[Facebook] AssemblyAI key: {'Yes' if assemblyai_api_key else 'No'}")
    print(f"{'='*60}\n")
    
    if not YTDLP_AVAILABLE:
        return False, "yt-dlp not available. Install with: pip install yt-dlp", "", "facebook"
    
    # Step 1: Get metadata
    if status_callback:
        status_callback("Fetching Facebook video info...")
    
    success, metadata = get_facebook_metadata(url, status_callback)
    
    if not success:
        error = metadata.get('error', 'Unknown error')
        print(f"[Facebook] Metadata fetch failed: {error}")
        return False, error, "", "facebook"
    
    title = metadata.get('title', 'Facebook Video')
    duration = metadata.get('duration', 0)
    uploader = metadata.get('uploader', 'Unknown')
    
    # Format duration for display
    if duration:
        mins, secs = divmod(int(duration), 60)
        duration_str = f"{mins}:{secs:02d}"
    else:
        duration_str = "Unknown"
    
    print(f"[Facebook] Video found: {title} ({duration_str}) by {uploader}")
    if status_callback:
        status_callback(f"Found: {title} ({duration_str})")
    
    # Step 2: Extract audio
    success, audio_result = extract_facebook_audio(url, status_callback=status_callback)
    
    if not success:
        print(f"[Facebook] Audio extraction failed: {audio_result}")
        return False, f"Failed to extract audio: {audio_result}", title, "facebook"
    
    audio_path = audio_result
    print(f"[Facebook] Audio extracted to: {audio_path}")
    
    # Step 3: Transcribe
    transcript = None
    transcript_error = None
    
    try:
        if transcription_provider == 'assemblyai' and assemblyai_api_key:
            print("[Facebook] Using AssemblyAI for transcription")
            success, transcript_result = transcribe_audio_assemblyai(
                audio_path, assemblyai_api_key, status_callback
            )
        elif openai_api_key:
            print("[Facebook] Using OpenAI Whisper for transcription")
            success, transcript_result = transcribe_audio_openai(
                audio_path, openai_api_key, status_callback
            )
        else:
            # No API key available
            print("[Facebook] No API key available for transcription")
            success = False
            transcript_result = "No transcription API key configured. Please set OpenAI or AssemblyAI API key in Settings."
        
        if success:
            transcript = transcript_result
            print(f"[Facebook] Transcription successful: {len(transcript)} characters")
        else:
            transcript_error = transcript_result
            print(f"[Facebook] Transcription failed: {transcript_error}")
            
    finally:
        # Clean up temp audio file
        try:
            if audio_path and os.path.exists(audio_path):
                os.remove(audio_path)
                print(f"[Facebook] Cleaned up temp file: {audio_path}")
            # Try to remove temp directory too
            audio_dir = os.path.dirname(audio_path)
            if audio_dir and 'facebook_audio_' in audio_dir and os.path.isdir(audio_dir):
                os.rmdir(audio_dir)
        except Exception as e:
            print(f"[Facebook] Cleanup error (non-fatal): {e}")
    
    if not transcript:
        return False, transcript_error or "Transcription failed", title, "facebook"
    
    # Step 4: Build result
    # Format similar to substack_utils for consistency
    formatted_text = f"[Facebook Video Transcript]\n"
    formatted_text += f"Title: {title}\n"
    formatted_text += f"Uploader: {uploader}\n"
    formatted_text += f"Duration: {duration_str}\n"
    formatted_text += f"URL: {url}\n"
    formatted_text += f"{'=' * 50}\n\n"
    formatted_text += transcript
    
    result = {
        'text': formatted_text,
        'transcript': transcript,
        'entries': [{'text': formatted_text, 'type': 'transcript'}],
        'duration': duration,
        'uploader': uploader,
        'source_url': url,
        'needs_transcription': False,
        'has_audio_video': True,
        'media_info': {
            'has_video': True,
            'has_podcast': False,
            'has_embedded': False,
        }
    }
    
    if status_callback:
        status_callback(f"Transcribed: {title}")
    
    print(f"[Facebook] Complete! Returning {len(formatted_text)} characters")
    return True, result, title, "facebook"


# For testing
if __name__ == "__main__":
    test_url = "https://www.facebook.com/reel/2986443194874917"
    print(f"Testing URL: {test_url}")
    print(f"Is Facebook video: {is_facebook_video_url(test_url)}")
    
    print("\nFetching metadata...")
    success, meta = get_facebook_metadata(test_url)
    if success:
        print(f"Title: {meta.get('title')}")
        print(f"Uploader: {meta.get('uploader')}")
        print(f"Duration: {meta.get('duration')}s")
    else:
        print(f"Error: {meta.get('error')}")
