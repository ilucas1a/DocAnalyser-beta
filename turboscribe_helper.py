"""
TurboScribe Helper - DocAnalyser Integration
=============================================

Helper workflow for using TurboScribe's free tier (3 transcriptions/day, 30 min each)
with superior speaker identification capabilities.

Features:
- Export audio to easy location for TurboScribe upload
- Import TurboScribe transcripts (TXT, DOCX, SRT formats)
- Automatic parsing and formatting
- Maintains speaker labels and timestamps
- Compatible with DocAnalyser's chunking and analysis

Author: DocAnalyser Development Team
Version: 1.0
"""

import os
import re
import shutil
import webbrowser
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Try to import docx for Word document parsing
try:
    from docx import Document
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False
    logger.warning("python-docx not available - DOCX import will be unavailable")
    logger.warning("Install with: pip install python-docx")


# ============================================================================
# EXPORT TO TURBOSCRIBE
# ============================================================================

def export_for_turboscribe(audio_path: str, destination_folder: str = None) -> str:
    """
    Copy audio file to an easy-access location for TurboScribe upload.
    
    Args:
        audio_path: Path to the audio file
        destination_folder: Optional custom destination folder
                          Defaults to Desktop/TurboScribe
    
    Returns:
        str: Path to the copied file
    """
    # Validate source file
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
    
    # Determine destination folder
    if destination_folder is None:
        desktop = Path.home() / "Desktop"
        destination_folder = desktop / "TurboScribe_Uploads"
    else:
        destination_folder = Path(destination_folder)
    
    # Create destination folder
    destination_folder.mkdir(parents=True, exist_ok=True)
    
    # Get filename and copy
    filename = os.path.basename(audio_path)
    destination_path = destination_folder / filename
    
    # Copy file
    shutil.copy2(audio_path, destination_path)
    logger.info(f"✅ Copied to: {destination_path}")
    
    return str(destination_path)


def open_turboscribe_website():
    """Open TurboScribe website in default browser"""
    turboscribe_url = "https://turboscribe.ai/"
    webbrowser.open(turboscribe_url)
    logger.info(f"🌐 Opened TurboScribe website")


# ============================================================================
# IMPORT FROM TURBOSCRIBE
# ============================================================================

def parse_turboscribe_txt(file_path: str) -> List[Dict]:
    """
    Parse TurboScribe TXT format transcript.
    
    TurboScribe TXT format:
    [00:00:05] Speaker 1: Hello everyone...
    [00:00:12] Speaker 2: Hi there...
    
    Args:
        file_path: Path to TXT file
    
    Returns:
        List[Dict]: Parsed segments with start, text, speaker
    """
    segments = []
    
    # Pattern to match: [HH:MM:SS] Speaker Name: Text
    # Also handles: [MM:SS] Speaker Name: Text
    pattern = r'\[(\d{1,2}:\d{2}:\d{2}|\d{1,2}:\d{2})\]\s*([^:]+):\s*(.+)'
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Find all matches
        matches = re.finditer(pattern, content, re.MULTILINE)
        
        for match in matches:
            timestamp_str = match.group(1)
            speaker = match.group(2).strip()
            text = match.group(3).strip()
            
            # Convert timestamp to seconds
            start_seconds = timestamp_to_seconds(timestamp_str)
            
            segments.append({
                'start': start_seconds,
                'text': text,
                'speaker': speaker,
                'timestamp': f"[{timestamp_str}]"
            })
        
        logger.info(f"📄 Parsed {len(segments)} segments from TXT file")
        return segments
        
    except Exception as e:
        logger.error(f"Error parsing TurboScribe TXT: {e}")
        raise


def parse_turboscribe_docx(file_path: str) -> List[Dict]:
    """
    Parse TurboScribe DOCX format transcript.
    
    Args:
        file_path: Path to DOCX file
    
    Returns:
        List[Dict]: Parsed segments with start, text, speaker
    """
    if not DOCX_AVAILABLE:
        raise ImportError(
            "python-docx not installed. Install with: pip install python-docx"
        )
    
    segments = []
    
    # Pattern to match timestamps and speakers
    pattern = r'\[(\d{1,2}:\d{2}:\d{2}|\d{1,2}:\d{2})\]\s*([^:]+):\s*(.+)'
    
    try:
        doc = Document(file_path)
        
        # Extract text from all paragraphs
        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue
            
            # Try to parse as timestamped segment
            match = re.match(pattern, text)
            if match:
                timestamp_str = match.group(1)
                speaker = match.group(2).strip()
                segment_text = match.group(3).strip()
                
                # Convert timestamp to seconds
                start_seconds = timestamp_to_seconds(timestamp_str)
                
                segments.append({
                    'start': start_seconds,
                    'text': segment_text,
                    'speaker': speaker,
                    'timestamp': f"[{timestamp_str}]"
                })
        
        logger.info(f"📄 Parsed {len(segments)} segments from DOCX file")
        return segments
        
    except Exception as e:
        logger.error(f"Error parsing TurboScribe DOCX: {e}")
        raise


def parse_turboscribe_srt(file_path: str) -> List[Dict]:
    """
    Parse TurboScribe SRT (subtitle) format.
    
    SRT format:
    1
    00:00:05,000 --> 00:00:08,000
    Speaker 1: Hello everyone...
    
    Args:
        file_path: Path to SRT file
    
    Returns:
        List[Dict]: Parsed segments with start, text, speaker
    """
    segments = []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Split into subtitle blocks
        blocks = content.strip().split('\n\n')
        
        for block in blocks:
            lines = block.split('\n')
            if len(lines) < 3:
                continue
            
            # Parse timestamp line (format: 00:00:05,000 --> 00:00:08,000)
            timestamp_line = lines[1]
            start_time = timestamp_line.split(' --> ')[0]
            start_seconds = srt_timestamp_to_seconds(start_time)
            
            # Parse text (may contain speaker label)
            text_lines = lines[2:]
            full_text = ' '.join(text_lines).strip()
            
            # Try to extract speaker
            speaker_match = re.match(r'^([^:]+):\s*(.+)', full_text)
            if speaker_match:
                speaker = speaker_match.group(1).strip()
                text = speaker_match.group(2).strip()
            else:
                speaker = "Unknown"
                text = full_text
            
            segments.append({
                'start': start_seconds,
                'text': text,
                'speaker': speaker,
                'timestamp': f"[{seconds_to_timestamp(start_seconds)}]"
            })
        
        logger.info(f"📄 Parsed {len(segments)} segments from SRT file")
        return segments
        
    except Exception as e:
        logger.error(f"Error parsing TurboScribe SRT: {e}")
        raise


def parse_turboscribe_file(file_path: str) -> List[Dict]:
    """
    Auto-detect format and parse TurboScribe transcript file.
    
    Args:
        file_path: Path to transcript file (.txt, .docx, or .srt)
    
    Returns:
        List[Dict]: Parsed segments
    """
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext == '.txt':
        return parse_turboscribe_txt(file_path)
    elif ext == '.docx':
        return parse_turboscribe_docx(file_path)
    elif ext == '.srt':
        return parse_turboscribe_srt(file_path)
    else:
        raise ValueError(
            f"Unsupported file format: {ext}\n"
            "Supported formats: .txt, .docx, .srt"
        )


# ============================================================================
# TIMESTAMP UTILITIES
# ============================================================================

def timestamp_to_seconds(timestamp: str) -> float:
    """
    Convert timestamp string to seconds.
    
    Supports formats:
    - HH:MM:SS
    - MM:SS
    - HH:MM:SS.mmm
    
    Args:
        timestamp: Timestamp string
    
    Returns:
        float: Time in seconds
    """
    parts = timestamp.split(':')
    
    if len(parts) == 3:
        # HH:MM:SS format
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2].replace(',', '.'))
        return hours * 3600 + minutes * 60 + seconds
    elif len(parts) == 2:
        # MM:SS format
        minutes = int(parts[0])
        seconds = float(parts[1].replace(',', '.'))
        return minutes * 60 + seconds
    else:
        raise ValueError(f"Invalid timestamp format: {timestamp}")


def srt_timestamp_to_seconds(srt_time: str) -> float:
    """
    Convert SRT timestamp to seconds.
    
    SRT format: 00:00:05,000
    
    Args:
        srt_time: SRT timestamp string
    
    Returns:
        float: Time in seconds
    """
    # Replace comma with dot for milliseconds
    srt_time = srt_time.replace(',', '.')
    
    parts = srt_time.split(':')
    hours = int(parts[0])
    minutes = int(parts[1])
    seconds = float(parts[2])
    
    return hours * 3600 + minutes * 60 + seconds


def seconds_to_timestamp(seconds: float) -> str:
    """
    Convert seconds to HH:MM:SS timestamp.
    
    Args:
        seconds: Time in seconds
    
    Returns:
        str: Formatted timestamp
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


# ============================================================================
# VALIDATION
# ============================================================================

def validate_turboscribe_import(segments: List[Dict]) -> Tuple[bool, str]:
    """
    Validate imported TurboScribe segments.
    
    Args:
        segments: List of parsed segments
    
    Returns:
        Tuple[bool, str]: (is_valid, error_message)
    """
    if not segments:
        return False, "No segments found in file"
    
    # Check required fields
    required_fields = ['start', 'text', 'speaker']
    for i, segment in enumerate(segments):
        for field in required_fields:
            if field not in segment:
                return False, f"Segment {i} missing required field: {field}"
        
        # Check data types
        if not isinstance(segment['start'], (int, float)):
            return False, f"Segment {i} has invalid start time type"
        
        if not isinstance(segment['text'], str) or not segment['text'].strip():
            return False, f"Segment {i} has empty or invalid text"
        
        if not isinstance(segment['speaker'], str):
            return False, f"Segment {i} has invalid speaker type"
    
    # Check timestamps are in order
    for i in range(1, len(segments)):
        if segments[i]['start'] < segments[i-1]['start']:
            return False, f"Timestamps out of order at segment {i}"
    
    logger.info(f"✅ Validation passed: {len(segments)} segments")
    return True, ""


# ============================================================================
# STATISTICS
# ============================================================================

def get_transcript_stats(segments: List[Dict]) -> Dict:
    """
    Get statistics about imported transcript.
    
    Args:
        segments: List of segments
    
    Returns:
        Dict: Statistics
    """
    if not segments:
        return {
            'total_segments': 0,
            'total_duration': 0,
            'speakers': [],
            'avg_segment_length': 0
        }
    
    # Count speakers
    speakers = set(seg['speaker'] for seg in segments)
    
    # Calculate duration
    total_duration = segments[-1]['start'] if segments else 0
    
    # Calculate average segment length
    total_text_length = sum(len(seg['text']) for seg in segments)
    avg_segment_length = total_text_length / len(segments) if segments else 0
    
    return {
        'total_segments': len(segments),
        'total_duration': total_duration,
        'total_duration_formatted': seconds_to_timestamp(total_duration),
        'speakers': sorted(list(speakers)),
        'speaker_count': len(speakers),
        'avg_segment_length': round(avg_segment_length, 1),
        'total_text_length': total_text_length
    }


# ============================================================================
# TESTING
# ============================================================================

if __name__ == "__main__":
    print("TurboScribe Helper - Test Mode")
    print("=" * 60)
    
    # Test timestamp conversion
    test_timestamps = [
        "00:05:30",
        "5:30",
        "01:23:45",
        "00:00:05"
    ]
    
    print("\nTimestamp Conversion Tests:")
    for ts in test_timestamps:
        seconds = timestamp_to_seconds(ts)
        back = seconds_to_timestamp(seconds)
        print(f"  {ts} → {seconds}s → {back}")
    
    print("\n" + "=" * 60)
    print("To test file parsing:")
    print("  python turboscribe_helper.py <transcript_file>")
    
    import sys
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        print(f"\n📄 Parsing: {file_path}")
        
        try:
            segments = parse_turboscribe_file(file_path)
            
            # Validate
            is_valid, error = validate_turboscribe_import(segments)
            if not is_valid:
                print(f"❌ Validation failed: {error}")
            else:
                print(f"✅ Validation passed")
            
            # Show stats
            stats = get_transcript_stats(segments)
            print(f"\n📊 Statistics:")
            print(f"  Total segments: {stats['total_segments']}")
            print(f"  Duration: {stats['total_duration_formatted']}")
            print(f"  Speakers: {', '.join(stats['speakers'])}")
            print(f"  Avg segment length: {stats['avg_segment_length']} chars")
            
            # Show first 3 segments
            print(f"\n🔤 First 3 segments:")
            for seg in segments[:3]:
                print(f"  {seg['timestamp']} {seg['speaker']}: {seg['text']}")
                
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
