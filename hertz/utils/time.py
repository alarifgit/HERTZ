# hertz/utils/time.py
import re
from typing import Union

def pretty_time(seconds: int) -> str:
    """Format seconds as MM:SS or HH:MM:SS"""
    if seconds < 0:
        return "0:00"
    
    n_seconds = seconds % 60
    n_minutes = seconds // 60
    n_hours = n_minutes // 60
    n_minutes %= 60
    
    if n_hours > 0:
        return f"{n_hours:02d}:{n_minutes:02d}:{n_seconds:02d}"
    else:
        return f"{n_minutes:02d}:{n_seconds:02d}"

def parse_time(time_str: str) -> int:
    """
    Parse a time string (e.g. '1:30') into seconds
    
    Supports formats:
    - MM:SS (1:30)
    - HH:MM:SS (1:30:45)
    """
    if not time_str:
        return 0
    
    # Split by colons
    parts = time_str.split(':')
    
    # Convert all parts to integers, with 0 for invalid parts
    parts = [int(part) if part.isdigit() else 0 for part in parts]
    
    # Calculate seconds based on number of parts
    if len(parts) == 1:
        return parts[0]
    elif len(parts) == 2:
        return parts[0] * 60 + parts[1]
    elif len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    else:
        return 0

def parse_duration(duration_str: str) -> int:
    """
    Parse a duration string into seconds
    
    Supports formats:
    - Simple seconds: '90'
    - Minutes and seconds: '1m30s', '1m 30s'
    - Hours, minutes, seconds: '1h30m15s', '1h 30m 15s'
    """
    if not duration_str:
        return 0
    
    # Check if it's just a number (seconds)
    if duration_str.isdigit():
        return int(duration_str)
    
    # Use regex to extract hours, minutes, seconds
    hours = re.search(r'(\d+)h', duration_str)
    minutes = re.search(r'(\d+)m', duration_str)
    seconds = re.search(r'(\d+)s', duration_str)
    
    total_seconds = 0
    
    if hours:
        total_seconds += int(hours.group(1)) * 3600
    
    if minutes:
        total_seconds += int(minutes.group(1)) * 60
    
    if seconds:
        total_seconds += int(seconds.group(1))
    
    return total_seconds