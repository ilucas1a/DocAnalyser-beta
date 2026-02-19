"""
video_platform_utils.py - Stub for video platform URL detection
================================================================
This module detects URLs from video platforms like Vimeo, Rumble, etc.
"""

def is_video_platform_url(url: str) -> bool:
    """
    Check if URL is from a supported video platform (Vimeo, Rumble, etc.)
    
    Args:
        url: The URL to check
        
    Returns:
        True if URL is from a supported video platform, False otherwise
    """
    if not url:
        return False
    
    url_lower = url.lower()
    
    # List of video platform domains
    video_platforms = [
        'vimeo.com',
        'rumble.com',
        'dailymotion.com',
        'bitchute.com',
        'odysee.com',
        'lbry.tv',
        'brighteon.com',
        'banned.video',
    ]
    
    for platform in video_platforms:
        if platform in url_lower:
            return True
    
    return False


def get_video_platform_name(url: str) -> str:
    """Get the name of the video platform from URL"""
    if not url:
        return "Unknown"
    
    url_lower = url.lower()
    
    platform_names = {
        'vimeo.com': 'Vimeo',
        'rumble.com': 'Rumble',
        'dailymotion.com': 'Dailymotion',
        'bitchute.com': 'BitChute',
        'odysee.com': 'Odysee',
        'lbry.tv': 'LBRY',
        'brighteon.com': 'Brighteon',
        'banned.video': 'Banned.video',
    }
    
    for domain, name in platform_names.items():
        if domain in url_lower:
            return name
    
    return "Unknown"
