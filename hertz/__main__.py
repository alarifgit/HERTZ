# hertz/__main__.py
import os
import sys
import asyncio
import logging
import threading
import time
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join('/data', 'hertz.log'))
    ]
)

# Reduce noise from disnake's internal logging
logging.getLogger('disnake').setLevel(logging.WARNING)
logging.getLogger('disnake.gateway').setLevel(logging.WARNING)
logging.getLogger('disnake.client').setLevel(logging.WARNING)
# Keep voice client logs at INFO since they're useful for playback debugging
logging.getLogger('disnake.voice_client').setLevel(logging.INFO)

logger = logging.getLogger(__name__)

# Create data directories if they don't exist
os.makedirs('/data', exist_ok=True)
os.makedirs('/data/cache', exist_ok=True)
os.makedirs('/data/cache/tmp', exist_ok=True)

# Health check file writer function
def health_file_writer():
    """Thread that periodically writes to a health check file"""
    health_file = '/data/health_status'
    logger.info(f"Starting health check writer thread, writing to {health_file}")
    while True:
        try:
            # Create health status file
            with open(health_file, 'w') as f:
                f.write(str(int(time.time())))
            time.sleep(10)  # Update every 10 seconds
        except Exception as e:
            logger.error(f"Error in health check writer: {e}")
            time.sleep(1)  # Short delay on error

# Start health check thread
health_thread = threading.Thread(target=health_file_writer, daemon=True)
health_thread.start()

try:
    from hertz.bot import HertzBot
    from hertz.config import load_config
    
    def main():
        logger.info("Starting HERTZ Discord bot...")
        
        # Load configuration
        config = load_config()
        
        # Validate required configuration
        if not config.DISCORD_TOKEN:
            logger.error("DISCORD_TOKEN environment variable is required")
            sys.exit(1)
            
        if not config.YOUTUBE_API_KEY:
            logger.error("YOUTUBE_API_KEY environment variable is required")
            sys.exit(1)
        
        # Create and run the bot
        bot = HertzBot(config)
        
        # Display startup banner
        print("""
                 HERTZ Discord Music Bot v1.2
        """)
        
        logger.info("Bot is ready to go! Invite URL will be displayed once connected.")
        
        # Run the bot
        bot.run(config.DISCORD_TOKEN)
    
    if __name__ == "__main__":
        main()
except Exception as e:
    logger.exception(f"Error starting bot: {str(e)}")
    sys.exit(1)