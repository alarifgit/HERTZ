# hertz/__main__.py
import os
import sys
import asyncio
import time
import threading
import logging
import signal
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
logging.getLogger('hertz.services.file_cache').setLevel(logging.INFO)
logging.getLogger('hertz.services.player').setLevel(logging.INFO)
logging.getLogger('hertz.services.youtube').setLevel(logging.INFO)
logging.getLogger('hertz.db.client').setLevel(logging.INFO)

logger = logging.getLogger(__name__)

# Create data directories if they don't exist
os.makedirs('/data', exist_ok=True)
os.makedirs('/data/cache', exist_ok=True)
os.makedirs('/data/cache/tmp', exist_ok=True)

# Global variables for cleanup
bot_instance = None
health_thread = None
should_stop = False

# Health check file writer function
def health_file_writer():
    """Thread that periodically writes to a health check file"""
    global should_stop
    health_file = '/data/health_status'
    health_logger = logging.getLogger('hertz.health')
    health_logger.info(f"Health check writer started, writing to {health_file}")
    
    while not should_stop:
        try:
            # Create health status file
            with open(health_file, 'w') as f:
                f.write(str(int(time.time())))
            time.sleep(10)  # Update every 10 seconds
        except Exception as e:
            health_logger.error(f"Health check write failed: {e}")
            time.sleep(1)  # Short delay on error

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    global should_stop, bot_instance
    logger.info(f"Received signal {signum}, starting graceful shutdown...")
    should_stop = True
    
    if bot_instance:
        try:
            # Try to close the bot gracefully
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(bot_instance.close())
            else:
                loop.run_until_complete(bot_instance.close())
        except Exception as e:
            logger.error(f"Error during bot shutdown: {e}")
    
    sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

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

async def run_bot_with_retry():
    """Run the bot with retry logic for connection issues"""
    global bot_instance
    max_retries = 5
    retry_count = 0
    
    while retry_count < max_retries and not should_stop:
        try:
            from hertz.bot import HertzBot
            from hertz.config import load_config
            
            # Load configuration
            config = load_config()
            
            # Create and start the bot
            bot_instance = HertzBot(config)
            
            logger.info("HERTZ bot initialized. Connecting to Discord...")
            
            # Run the bot
            await bot_instance.start(config.DISCORD_TOKEN)
            
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt, shutting down...")
            break
        except Exception as e:
            retry_count += 1
            logger.error(f"❌ Bot crashed (attempt {retry_count}/{max_retries}): {str(e)}")
            
            if retry_count < max_retries:
                wait_time = min(60, 2 ** retry_count)  # Exponential backoff, max 60s
                logger.info(f"Retrying in {wait_time} seconds...")
                await asyncio.sleep(wait_time)
            else:
                logger.critical("❌ Maximum retry attempts reached, giving up")
                break
        finally:
            # Clean up bot instance
            if bot_instance:
                try:
                    await bot_instance.close()
                except Exception as e:
                    logger.error(f"Error closing bot: {e}")
                bot_instance = None

try:
    def main():
        """Main entry point for the HERTZ bot"""
        global health_thread, should_stop
        
        logger.info("Initializing HERTZ Discord Music Bot...")
        
        # Load configuration early to validate
        try:
            from hertz.config import load_config
            config = load_config()
        except Exception as e:
            logger.error(f"❌ CRITICAL: Configuration error: {str(e)}")
            sys.exit(1)
        
        # Validate required configuration
        if not config.DISCORD_TOKEN:
            logger.error("❌ CRITICAL: DISCORD_TOKEN environment variable is required")
            sys.exit(1)
            
        if not config.YOUTUBE_API_KEY:
            logger.error("❌ CRITICAL: YOUTUBE_API_KEY environment variable is required")
            sys.exit(1)
        
        # Display startup banner
        display_banner()
        
        # Start health check thread
        health_thread = threading.Thread(target=health_file_writer, daemon=True)
        health_thread.start()
        
        # Set up event loop with better error handling
        try:
            # Check if we're in an existing event loop
            try:
                loop = asyncio.get_running_loop()
                logger.warning("Already in an event loop, creating task...")
                # If we're already in a loop, create a task
                task = loop.create_task(run_bot_with_retry())
                return task
            except RuntimeError:
                # No running loop, create one
                if sys.platform == 'win32':
                    # Windows-specific event loop policy
                    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
                
                # Create and run event loop
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                try:
                    loop.run_until_complete(run_bot_with_retry())
                finally:
                    # Clean shutdown
                    should_stop = True
                    
                    # Cancel all remaining tasks
                    pending = asyncio.all_tasks(loop)
                    for task in pending:
                        task.cancel()
                    
                    # Wait for tasks to complete cancellation
                    if pending:
                        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                    
                    loop.close()
                    
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt during startup")
            should_stop = True
        except Exception as e:
            logger.critical(f"❌ CRITICAL: Startup failed: {str(e)}")
            import traceback
            logger.critical(traceback.format_exc())
            sys.exit(1)
        finally:
            should_stop = True
            logger.info("HERTZ shutdown complete")
    
    if __name__ == "__main__":
        main()
        
except Exception as e:
    logger.exception(f"❌ CRITICAL: Failed to start HERTZ bot: {str(e)}")
    sys.exit(1)