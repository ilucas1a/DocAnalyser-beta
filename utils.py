"""
utils.py - General Utility Functions
Helper functions used throughout the application
"""

import os
import hashlib
import json
import datetime


def format_size(bytes_size: int) -> str:
    """Convert bytes to human-readable format (KB, MB, GB)"""
    if bytes_size < 1024:
        return f"{bytes_size} B"
    elif bytes_size < 1024 ** 2:
        return f"{bytes_size / 1024:.2f} KB"
    elif bytes_size < 1024 ** 3:
        return f"{bytes_size / (1024 ** 2):.2f} MB"
    else:
        return f"{bytes_size / (1024 ** 3):.2f} GB"


def get_directory_size(directory: str) -> tuple:
    """Get total size and file count of a directory"""
    total_size = 0
    file_count = 0

    if not os.path.exists(directory):
        return 0, 0

    for dirpath, dirnames, filenames in os.walk(directory):
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            try:
                total_size += os.path.getsize(filepath)
                file_count += 1
            except Exception:
                pass

    return total_size, file_count


def calculate_file_hash(file_path: str) -> str:
    """Calculate MD5 hash of a file for caching"""
    hash_md5 = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception:
        return None


def save_json(data: dict, file_path: str) -> bool:
    """Save data to JSON file"""
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error saving JSON: {e}")
        return False


def load_json(file_path: str, default=None):
    """Load data from JSON file"""
    if not os.path.exists(file_path):
        return default if default is not None else {}

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading JSON: {e}")
        return default if default is not None else {}


def safe_filename(text: str, max_length: int = 50) -> str:
    """Convert text to safe filename"""
    # Remove invalid characters
    safe = "".join(c for c in text if c.isalnum() or c in (' ', '-', '_')).strip()
    # Replace spaces with underscores
    safe = safe.replace(' ', '_')
    # Truncate if too long
    if len(safe) > max_length:
        safe = safe[:max_length]
    return safe if safe else "untitled"


def format_timestamp(seconds: float) -> str:
    """Convert seconds to MM:SS or HH:MM:SS format"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes:02d}:{secs:02d}"


def format_display_date(date_input) -> str:
    """
    Format a date for display as DD-Mon-YYYY (e.g., "06-Jan-2026").
    
    Args:
        date_input: Can be:
            - YYYYMMDD string (from yt-dlp)
            - YYYY-MM-DD string
            - ISO datetime string (with or without time)
            - datetime object
            - Any other parseable date string
    
    Returns:
        Formatted date string like "06-Jan-2026", or original input if parsing fails
    """
    from datetime import datetime
    
    if not date_input:
        return ""
    
    # If it's already a datetime object
    if isinstance(date_input, datetime):
        return date_input.strftime('%d-%b-%Y')
    
    # Convert to string if needed
    date_str = str(date_input).strip()
    
    # Try various formats
    formats_to_try = [
        '%Y%m%d',           # YYYYMMDD (from yt-dlp)
        '%Y-%m-%d',         # YYYY-MM-DD (ISO date only)
        '%Y-%m-%dT%H:%M:%S.%f',   # ISO with microseconds, no timezone
        '%Y-%m-%dT%H:%M:%S.%f%z',  # ISO with microseconds and timezone
        '%Y-%m-%dT%H:%M:%S%z',  # ISO with timezone
        '%Y-%m-%dT%H:%M:%SZ',   # ISO with Z
        '%Y-%m-%dT%H:%M:%S',    # ISO without timezone
    ]
    
    for fmt in formats_to_try:
        try:
            dt = datetime.strptime(date_str[:len(date_str)], fmt)
            return dt.strftime('%d-%b-%Y')
        except ValueError:
            continue
    
    # Try dateutil as fallback
    try:
        from dateutil import parser
        dt = parser.parse(date_str)
        return dt.strftime('%d-%b-%Y')
    except:
        pass
    
    # Return original if all parsing fails
    return date_str


# Alias for backward compatibility
format_published_date = format_display_date


def chunk_text(text: str, chunk_size: int, overlap: int = 200) -> list:
    """
    Split text into overlapping chunks
    Similar to how you might split large datasets in VBA
    """
    chunks = []
    start = 0
    text_length = len(text)

    while start < text_length:
        end = start + chunk_size

        # Find a good breaking point (end of sentence)
        if end < text_length:
            # Look for period, question mark, or exclamation within last 200 chars
            search_start = max(start, end - 200)
            search_text = text[search_start:end]

            for separator in ['. ', '? ', '! ', '\n\n']:
                last_sep = search_text.rfind(separator)
                if last_sep != -1:
                    end = search_start + last_sep + len(separator)
                    break

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        start = end - overlap if end < text_length else text_length

    return chunks


def extract_youtube_id(url: str) -> str:
    """Extract video ID from various YouTube URL formats"""
    import re

    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com\/shorts\/([a-zA-Z0-9_-]{11})',
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    return None


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """Truncate text to maximum length"""
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def get_file_extension(filename: str) -> str:
    """Get lowercase file extension without the dot"""
    _, ext = os.path.splitext(filename)
    return ext.lower().lstrip('.')


def is_valid_url(url: str) -> bool:
    """Check if string is a valid URL"""
    import re
    url_pattern = re.compile(
        r'^https?://'  # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
        r'localhost|'  # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    return url_pattern.match(url) is not None


def get_timestamp() -> str:
    """Get current timestamp in ISO format"""
    return datetime.datetime.now().isoformat()


def parse_timestamp(timestamp_str: str):
    """Parse ISO timestamp string"""
    try:
        return datetime.datetime.fromisoformat(timestamp_str)
    except Exception:
        return None


def save_json_atomic(path: str, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def chunk_entries(entries: list, chunk_size: str) -> list:
    """
    Split entries into chunks based on size preset.

    IMPORTANT: If a single entry exceeds the chunk size limit,
    it will be split into multiple smaller entries first.
    This prevents token limit errors for large documents.

    Args:
        entries: List of entry dicts with 'text' field
        chunk_size: 'small', 'medium', or 'large'

    Returns:
        List of entry lists (chunks)
    """
    from config import CHUNK_SIZES

    max_chars = CHUNK_SIZES[chunk_size]["chars"]

    # Step 1: Split any oversized entries into smaller pieces
    processed_entries = []

    for entry in entries:
        text = entry.get('text', '')
        text_len = len(text)

        # If entry fits within chunk size, keep it as-is
        if text_len <= max_chars:
            processed_entries.append(entry)
        else:
            # Entry is too large - split it into multiple entries
            # Use the chunk_text function to intelligently split at sentence boundaries
            text_chunks = chunk_text(text, max_chars, overlap=200)

            # Create new entries from the splits
            for i, chunk_text_part in enumerate(text_chunks):
                new_entry = entry.copy()
                new_entry['text'] = chunk_text_part
                # Update location to show it's a split piece
                original_location = entry.get('location', 'Document')
                new_entry['location'] = f"{original_location} (Part {i + 1}/{len(text_chunks)})"
                processed_entries.append(new_entry)

    # Step 2: Group processed entries into chunks
    chunks = []
    current_chunk = []
    current_length = 0

    for entry in processed_entries:
        entry_text = entry.get('text', '')
        entry_len = len(entry_text)

        # Check if adding this entry would exceed the chunk size
        if current_length + entry_len > max_chars and current_chunk:
            # Save current chunk and start a new one
            chunks.append(current_chunk)
            current_chunk = []
            current_length = 0

        # Add entry to current chunk
        current_chunk.append(entry)
        current_length += entry_len

    # Don't forget the last chunk
    if current_chunk:
        chunks.append(current_chunk)

    # If no chunks were created (empty document), return one empty chunk
    if not chunks:
        chunks = [[]]

    return chunks


"""
PATCHED entries_to_text function for utils.py

Replace the existing entries_to_text function (around line 253) in utils.py with this version.

This version automatically detects if entries have timestamps ('start' field) and includes
them in the output, fixing the "Page" bug for YouTube transcripts.
"""



def entries_to_text(entries: list, include_timestamps: bool = True, timestamp_interval: str = "every_segment") -> str:
    """
    Convert entries to plain text with configurable timestamp frequency.

    Args:
        entries: List of entry dicts
        include_timestamps: Whether to include timestamp info (defaults to True)
        timestamp_interval: How often to show timestamps:
            - "every_segment": Show timestamp for every segment (original behavior)
            - "1min": Show timestamp every 1 minute
            - "5min": Show timestamp every 5 minutes  
            - "10min": Show timestamp every 10 minutes
            - "never": Don't show any timestamps

    Returns:
        Formatted text string
    """
    if not entries:
        return ""

    # Parse interval into seconds
    interval_seconds = {
        "every_segment": 0,  # 0 means show every segment
        "1min": 60,
        "5min": 300,
        "10min": 600,
        "never": float('inf')  # Never show timestamps
    }.get(timestamp_interval, 0)

    lines = []
    last_timestamp = -interval_seconds  # Start negative so first timestamp always shows
    last_page = None  # Track page changes for OCR entries

    for entry in entries:
        text = entry.get('text', '').strip()
        if not text:
            continue

        # Check if entry has timestamps AND should include them
        if include_timestamps and 'start' in entry:
            current_time = entry['start']
            location = entry.get('location', '')
            
            # Detect if this is an OCR/page-based entry (location starts with "Page")
            is_page_entry = location.startswith('Page')
            
            if is_page_entry:
                # For OCR entries: always show location when page changes
                current_page = location
                show_location = (current_page != last_page)
                
                if show_location:
                    lines.append(f"[{location}] {text}")
                    last_page = current_page
                else:
                    lines.append(text)
            else:
                # For timestamp-based entries (video/audio): use interval logic
                show_timestamp = (
                    timestamp_interval == "every_segment" or 
                    (current_time - last_timestamp) >= interval_seconds
                )
                
                if show_timestamp:
                    # Use pre-formatted location if available, otherwise format the timestamp
                    if location:
                        timestamp_str = location
                    else:
                        timestamp_str = format_timestamp(entry['start'])
                    
                    lines.append(f"[{timestamp_str}] {text}")
                    last_timestamp = current_time
                else:
                    # No timestamp for this segment
                    lines.append(text)
        else:
            # No timestamp available, just add the text
            lines.append(text)

    return '\n\n'.join(lines)

def entries_to_text_with_speakers(entries: list, timestamp_interval: str = "every_segment") -> str:
    """
    Convert entries with speaker information to formatted text.
    Used for audio transcriptions with speaker diarization.

    Args:
        entries: List of entry dicts with 'speaker' field
        timestamp_interval: How often to show timestamps (same options as entries_to_text)

    Returns:
        Formatted text with speaker labels
    """
    if not entries:
        return ""
    
    # Parse interval into seconds
    interval_seconds = {
        "every_segment": 0,
        "1min": 60,
        "5min": 300,
        "10min": 600,
        "never": float('inf')
    }.get(timestamp_interval, 0)
    
    lines = []
    last_speaker = None
    last_timestamp = -interval_seconds  # Start negative so first timestamp always shows

    for entry in entries:
        text = entry.get('text', '').strip()
        if not text:
            continue

        speaker = entry.get('speaker', 'Unknown')

        # Add speaker label if it changed
        if speaker != last_speaker:
            lines.append(f"\n**{speaker}:**")
            last_speaker = speaker

        # Add timestamp if available AND if interval allows
        if 'start' in entry:
            current_time = entry['start']
            
            # Determine if we should show timestamp
            show_timestamp = (
                timestamp_interval == "every_segment" or 
                (current_time - last_timestamp) >= interval_seconds
            )
            
            if show_timestamp:
                timestamp = format_timestamp(entry['start'])
                lines.append(f"[{timestamp}] {text}")
                last_timestamp = current_time
            else:
                # No timestamp for this segment
                lines.append(text)
        else:
            lines.append(text)

    return '\n'.join(lines)

