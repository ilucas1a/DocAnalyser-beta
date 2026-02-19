# ================================================================
# REPLACEMENT CODE FOR substack_utils.py
# ================================================================
# 
# Replace the existing fetch_substack_content function (starting at line 1044)
# with this new version, and add the download_substack_media function.
#
# The key change: fetch_substack_content NO LONGER downloads audio/video.
# Instead, it returns metadata about what's available, and Main.py
# calls download_substack_media separately if the user wants transcription.
# ================================================================

def fetch_substack_content(url: str, status_callback=None) -> Tuple[bool, Any, str, str]:
    """
    Fetch content from a Substack post.
    
    FAST VERSION: Extracts text and detects media WITHOUT downloading.
    
    Priority:
    1. Extract on-page transcript (fastest, most accurate)
    2. Fetch transcript from API
    3. Extract article text
    4. Return info about available audio/video for optional later download
    
    Args:
        url: Substack post URL
        status_callback: Optional callback for status updates
        
    Returns:
        Tuple of (success, result_dict, title, content_type)
        
        result_dict contains:
        - 'entries': List of text entries (if text found)
        - 'text': Plain text content (if found)
        - 'has_audio_video': True if downloadable media detected
        - 'media_info': Dict with video_id, podcast_url, embedded_urls for later download
        - 'needs_transcription': False (we don't auto-download anymore)
        - 'source_url': Original URL
    """
    publication = extract_substack_publication(url)
    post_slug = extract_substack_slug(url)
    base_domain = extract_domain_from_url(url)
    
    if status_callback:
        status_callback("Fetching Substack page...")
    
    # Fetch the page
    page_success, html = fetch_substack_page(url)
    if not page_success:
        return False, html, "", "substack"
    
    # Verify this is actually a Substack page (important for custom domains)
    if not is_likely_substack_page(html):
        return False, "This doesn't appear to be a Substack page", "", "web"
    
    preloads = extract_preloads_from_html(html)
    title = "Unknown Substack Post"
    
    # Try to get title
    if preloads:
        title = extract_title_from_preloads(preloads)
    if title == "Unknown Substack Post":
        html_title = extract_title_from_html(html)
        if html_title:
            title = html_title
    
    # Check if this post has video or podcast content (detection only, no download)
    video_id = extract_video_id_from_preloads(preloads) if preloads else None
    podcast_url = extract_podcast_url_from_preloads(preloads) if preloads else None
    embedded_urls = extract_embedded_video_urls(html)
    
    has_video = bool(video_id)
    has_podcast = bool(podcast_url)
    has_embedded = bool(embedded_urls)
    has_audio_video = has_video or has_podcast or has_embedded
    
    # Store media info for potential later download
    media_info = {
        'video_id': video_id,
        'podcast_url': podcast_url,
        'embedded_urls': embedded_urls,
        'has_video': has_video,
        'has_podcast': has_podcast,
        'has_embedded': has_embedded,
    }
    
    # Debug output
    print(f"\n=== Substack Content Detection ===")
    print(f"URL: {url}")
    print(f"Title: {title}")
    print(f"Preloads extracted: {preloads is not None}")
    print(f"Has video: {has_video}")
    print(f"Has podcast: {has_podcast}")
    print(f"Has embedded videos: {has_embedded} ({len(embedded_urls)} found)")
    print(f"==================================\n")
    
    if status_callback:
        status_callback(f"Processing: {title}")
    
    # ================================================================
    # PRIORITY 1: Check for existing transcript (fastest option)
    # ================================================================
    if status_callback:
        status_callback("Checking for existing transcript...")
    
    transcript = None
    
    # Try preloads first
    if preloads:
        transcript = extract_transcript_from_preloads(preloads)
    
    # Try HTML patterns
    if not transcript:
        transcript = extract_transcript_from_html(html)
    
    # Try API endpoints
    if not transcript and post_slug:
        if status_callback:
            status_callback("Checking API for transcript...")
        
        podcast_upload_id = extract_podcast_upload_id_from_preloads(preloads) if preloads else None
        transcript = fetch_transcript_from_api(publication, post_slug, podcast_upload_id, base_domain)
    
    if transcript and len(transcript) > 200:
        if status_callback:
            status_callback("Found existing transcript!")
        
        entries = [{
            'text': transcript,
            'start': 0,
            'location': 'Transcript'
        }]
        
        content_type = "substack_video" if has_video else "substack_podcast" if has_podcast else "substack_article"
        return True, {
            'entries': entries,
            'text': transcript,
            'has_audio_video': False,  # Already have transcript, no need to offer download
            'media_info': media_info,
            'needs_transcription': False,
            'source_url': url
        }, f"Substack: {title}", content_type
    
    # ================================================================
    # PRIORITY 2: Extract article text
    # ================================================================
    if status_callback:
        status_callback("Extracting article text...")
    
    article_text = None
    
    # Try preloads first (most complete)
    if preloads:
        article_text = extract_article_text_from_preloads(preloads)
        if article_text:
            print(f"Extracted article text from preloads: {len(article_text)} chars")
    
    # Fallback: Try HTML extraction if preloads failed or didn't have article text
    if not article_text or len(article_text) < 100:
        print("Trying HTML-based article extraction as fallback...")
        article_text = extract_article_text_from_html(html)
        if article_text:
            print(f"Extracted article text from HTML: {len(article_text)} chars")
    
    # Build result
    entries = []
    if article_text and len(article_text) > 100:
        entries = [{
            'text': article_text,
            'start': 0,
            'location': 'Article'
        }]
    
    # Determine content type
    if has_video:
        content_type = "substack_video"
    elif has_podcast:
        content_type = "substack_podcast"
    elif has_embedded:
        content_type = "substack_video"
    else:
        content_type = "substack_article"
    
    # Return success if we have either text OR media available
    if entries or has_audio_video:
        if status_callback:
            if entries:
                status_callback("Article text extracted!")
            else:
                status_callback("Media detected, no article text found")
        
        return True, {
            'entries': entries,
            'text': article_text or '',
            'has_audio_video': has_audio_video,
            'media_info': media_info,
            'needs_transcription': False,  # We don't auto-download anymore
            'source_url': url
        }, f"Substack: {title}", content_type
    
    return False, "Could not extract text or detect media. The post may be paywalled or contain unsupported content.", "", "substack"


def download_substack_media(url: str, media_info: dict, status_callback=None) -> Tuple[bool, str]:
    """
    Download audio/video from a Substack post for transcription.
    
    Call this AFTER fetch_substack_content, when user confirms they want transcription.
    
    Args:
        url: Original Substack post URL
        media_info: Dict from fetch_substack_content containing video_id, podcast_url, embedded_urls
        status_callback: Optional callback for status updates
        
    Returns:
        Tuple of (success, audio_file_path or error_message)
    """
    if not media_info:
        return False, "No media info provided"
    
    video_id = media_info.get('video_id')
    podcast_url = media_info.get('podcast_url')
    embedded_urls = media_info.get('embedded_urls', [])
    
    # Try yt-dlp on the main URL first (works for many Substack posts)
    if YTDLP_AVAILABLE:
        if status_callback:
            status_callback("Downloading audio with yt-dlp...")
        
        success, result = download_audio_with_ytdlp(url, status_callback=status_callback)
        if success:
            return True, result
        else:
            print(f"Warning: yt-dlp failed on Substack URL: {result}")
    
    # Try embedded video URLs (YouTube, Rumble, etc.)
    if YTDLP_AVAILABLE and embedded_urls:
        for embed_url in embedded_urls:
            if status_callback:
                status_callback(f"Trying embedded video: {embed_url[:50]}...")
            
            success, result = download_audio_with_ytdlp(embed_url, status_callback=status_callback)
            if success:
                print(f"Downloaded from embedded URL: {embed_url}")
                return True, result
            else:
                print(f"Warning: Embedded URL failed: {result}")
    
    # Try direct video API download
    if video_id:
        if status_callback:
            status_callback("Downloading video from Substack API...")
        
        success, result = download_video_direct(video_id, status_callback=status_callback)
        if success:
            # Extract audio from video
            audio_success, audio_result = extract_audio_from_video(result, status_callback=status_callback)
            if audio_success:
                return True, audio_result
            else:
                # Try to use the video file directly for transcription
                return True, result
    
    # Try direct podcast URL
    if podcast_url:
        if status_callback:
            status_callback("Downloading audio directly...")
        
        success, result = download_audio_direct(podcast_url, status_callback=status_callback)
        if success:
            return True, result
    
    return False, "Could not download audio/video from any available source"
