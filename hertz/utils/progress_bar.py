# hertz/utils/progress_bar.py

def get_progress_bar(width: int, progress: float) -> str:
    """
    Generate a text-based progress bar
    
    Args:
        width: Width of the progress bar in characters
        progress: Progress from 0.0 to 1.0
        
    Returns:
        String with progress bar (e.g. '▬▬▬🔘▬▬▬')
    """
    if progress < 0:
        progress = 0
    elif progress > 1:
        progress = 1
    
    # Calculate position of the dot
    dot_position = round(width * progress)
    if dot_position == width and progress < 1:
        dot_position = width - 1
    
    # Build the progress bar
    result = ""
    for i in range(width):
        if i == dot_position:
            result += "🔘"
        else:
            result += "▬"
    
    return result