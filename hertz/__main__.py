# hertz/__main__.py
import os
import sys
import asyncio
import time
import threading
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

# Define log format with clear, structured messages
log_format = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'

# Create logs directory if it doesn't exist
log_dir = os.path.join('/data', 'logs')
os.makedirs(log_dir, exist_ok=True)

# Setup handlers
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter(log_format))

# Rotating file handler - keeps logs manageable
file_handler = RotatingFileHandler(
    os.path.join(log_dir, 'hertz.log'),
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5  # Keep 5 backup logs
)
file_handler.setFormatter(logging.Formatter(log_format))

# Configure root logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)  # Default level
root_logger.addHandler(console_handler)
root_logger.addHandler(file_handler)

# Adjust levels for specific modules
logging.getLogger('disnake').setLevel(logging.WARNING)
logging.getLogger('disnake.gateway').setLevel(logging.WARNING)
logging.getLogger('disnake.client').setLevel(logging.WARNING)
# Keep voice client logs at INFO since they're useful for playback debugging
logging.getLogger('disnake.voice_client').setLevel(logging.INFO)

# Set HERTZ service levels for better signal-to-noise ratio
logging.getLogger('hertz.services.file_cache').setLevel(logging.INFO)  # Verbose module
logging.getLogger('hertz.services.player').setLevel(logging.INFO)  # Important operations
logging.getLogger('hertz.services.youtube').setLevel(logging.INFO)  # API calls
logging.getLogger('hertz.db.client').setLevel(logging.INFO)  # Database operations

logger = logging.getLogger(__name__)

# Create data directories if they don't exist
os.makedirs('/data', exist_ok=True)
os.makedirs('/data/cache', exist_ok=True)
os.makedirs('/data/cache/tmp', exist_ok=True)

# Health check file writer function
def health_file_writer():
    """Thread that periodically writes to a health check file"""
    health_file = '/data/health_status'
    health_logger = logging.getLogger('hertz.health')
    health_logger.info(f"Health check writer started, writing to {health_file}")
    while True:
        try:
            # Create health status file
            with open(health_file, 'w') as f:
                f.write(str(int(time.time())))
            time.sleep(10)  # Update every 10 seconds
        except Exception as e:
            health_logger.error(f"Health check write failed: {e}")
            time.sleep(1)  # Short delay on error

# Start health check thread
health_thread = threading.Thread(target=health_file_writer, daemon=True)
health_thread.start()

# ASCII Banner Display
def display_banner():
    """Display the HERTZ startup banner"""
    banner = """
    ╭─────────────────────────────────────────────╮
    │                                             │
    │      ██╗  ██╗███████╗██████╗ ████████╗███████╗    │
    │      ██║  ██║██╔════╝██╔══██╗╚══██╔══╝╚══███╔╝    │
    │      ███████║█████╗  ██████╔╝   ██║     ███╔╝     │
    │      ██╔══██║██╔══╝  ██╔══██╗   ██║    ███╔╝      │
    │      ██║  ██║███████╗██║  ██║   ██║   ███████╗    │
    │      ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝   ╚═╝   ╚══════╝    │
    │                                             │
    │           Discord Music Bot v1.0.1          │
    │                                             │
    ╰─────────────────────────────────────────────╯
    """
    print(banner)

try:
    from hertz.bot import HertzBot
    from hertz.config import load_config
    
    def main():
        """Main entry point for the HERTZ bot"""
        logger.info("Initializing HERTZ Discord Music Bot...")
        
        # Load configuration
        config = load_config()
        
        # Validate required configuration
        if not config.DISCORD_TOKEN:
            logger.error("❌ CRITICAL: DISCORD_TOKEN environment variable is required")
            sys.exit(1)
            
        if not config.YOUTUBE_API_KEY:
            logger.error("❌ CRITICAL: YOUTUBE_API_KEY environment variable is required")
            sys.exit(1)
        
        # Display startup banner
        display_banner()
        
        # Create and run the bot
        bot = HertzBot(config)
        
        logger.info("HERTZ bot initialized. Connecting to Discord...")
        
        # Run the bot
        bot.run(config.DISCORD_TOKEN)
    
    if __name__ == "__main__":
        main()
except Exception as e:
    logger.exception(f"❌ CRITICAL: Failed to start HERTZ bot: {str(e)}")
    sys.exit(1)