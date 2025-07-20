#!/usr/bin/env python3
"""
HERTZ - A modern Discord music bot
Production-ready music bot with advanced features
Inspired by muse's service-oriented architecture
"""

import asyncio
import logging
import signal
import sys
import time
from pathlib import Path
import traceback

import discord
from discord.ext import commands
import aiohttp

# Try to use uvloop for better performance
try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
except ImportError:
    pass

# Import our modules
from config.settings import get_config, setup_logging, create_directories
from database.connection import db_manager
from services.player_manager import PlayerManager
from services.spotify_service import spotify_service
from utils.error_handler import ErrorHandler
from utils.health_monitor import HealthMonitor

logger = logging.getLogger(__name__)

class HertzBot(commands.Bot):
    """Main HERTZ bot class with proper service management."""
    
    def __init__(self):
        # Get configuration
        self.config = get_config()
        
        # Setup intents (minimal required)
        intents = discord.Intents.default()
        intents.message_content = False  # We only use slash commands
        intents.voice_states = True
        intents.guilds = True
        intents.guild_messages = True
        
        # Initialize bot
        super().__init__(
            command_prefix="!",  # Unused but required
            intents=intents,
            help_command=None,
            case_insensitive=True,
            activity=discord.Activity(
                type=discord.ActivityType.listening,
                name="Starting up..."
            ),
            status=discord.Status.idle
        )
        
        # Bot state
        self.startup_time = None
        self.ready = False
        
        # Services (initialized in setup_hook)
        self.player_manager: PlayerManager = None
        self.error_handler: ErrorHandler = None
        self.health_monitor: HealthMonitor = None
        self.session: aiohttp.ClientSession = None
        
        # Graceful shutdown handling
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        asyncio.create_task(self.shutdown())
    
    async def setup_hook(self):
        """Called when the bot is starting up."""
        logger.info("🔧 Setting up HERTZ bot...")
        
        try:
            # Create HTTP session
            self.session = aiohttp.ClientSession()
            
            # Initialize database
            await db_manager.initialize()
            logger.info("✅ Database initialized")
            
            # Initialize services
            self.player_manager = PlayerManager(self)
            self.error_handler = ErrorHandler(self)
            self.health_monitor = HealthMonitor(self)
            
            logger.info("✅ Services initialized")
            
            # Initialize Spotify if configured
            if self.config.has_spotify:
                await spotify_service.initialize(self.session)
                logger.info("✅ Spotify integration enabled")
            else:
                logger.info("ℹ️  Spotify integration disabled (no credentials)")
            
            # Load command modules
            await self.load_commands()
            
            # Start health monitor
            if self.config.health_check_enabled:
                await self.health_monitor.start()
                logger.info("✅ Health monitor started")
            
            # Start player manager cleanup task
            await self.player_manager.start_cleanup_task()
            
            logger.info("✅ Bot setup completed successfully!")
            
        except Exception as e:
            logger.error(f"❌ Failed to setup bot: {e}")
            logger.error(traceback.format_exc())
            await self.shutdown()
            sys.exit(1)
    
    async def load_commands(self):
        """Load all command modules."""
        extensions = [
            "commands.player_commands",
            "commands.queue_commands",
        ]
        
        for extension in extensions:
            try:
                await self.load_extension(extension)
                logger.info(f"✅ Loaded extension: {extension}")
            except Exception as e:
                logger.error(f"❌ Failed to load extension {extension}: {e}")
                # Don't raise - allow bot to start with partial functionality
    
    async def on_ready(self):
        """Called when the bot is ready."""
        self.startup_time = time.time()
        self.ready = True
        
        logger.info("=" * 60)
        logger.info("🎵 HERTZ Discord Music Bot - Ready!")
        logger.info("=" * 60)
        logger.info(f"Bot User: {self.user} (ID: {self.user.id})")
        logger.info(f"Connected to {len(self.guilds)} guilds")
        logger.info(f"Serving {sum(guild.member_count for guild in self.guilds)} users")
        logger.info("=" * 60)
        
        # Sync slash commands if configured
        if self.config.register_commands_on_bot:
            try:
                synced = await self.tree.sync()
                logger.info(f"✅ Synced {len(synced)} slash commands")
            except Exception as e:
                logger.error(f"❌ Failed to sync slash commands: {e}")
        
        # Update activity
        activity_type = getattr(discord.ActivityType, self.config.bot_activity_type.lower(), discord.ActivityType.listening)
        activity = discord.Activity(
            type=activity_type,
            name=self.config.bot_activity
        )
        status = getattr(discord.Status, self.config.bot_status.lower(), discord.Status.online)
        
        await self.change_presence(activity=activity, status=status)
        
        logger.info("🚀 Bot is ready to serve music!")
    
    async def on_guild_join(self, guild: discord.Guild):
        """Called when the bot joins a guild."""
        logger.info(f"Joined guild: {guild.name} (ID: {guild.id})")
        
        # Create guild settings
        try:
            await self.player_manager.get_guild_settings(guild.id)
            logger.info(f"Created settings for guild: {guild.name}")
        except Exception as e:
            logger.error(f"Failed to create guild settings for {guild.name}: {e}")
    
    async def on_guild_remove(self, guild: discord.Guild):
        """Called when the bot leaves a guild."""
        logger.info(f"Left guild: {guild.name} (ID: {guild.id})")
        
        # Cleanup player if exists
        try:
            await self.player_manager.remove(guild.id)
            logger.info(f"Cleaned up player for guild: {guild.name}")
        except Exception as e:
            logger.error(f"Failed to cleanup player for {guild.name}: {e}")
    
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """Handle voice state updates."""
        # Check if bot was disconnected
        if member == self.user and before.channel and not after.channel:
            logger.info(f"Bot was disconnected from {before.channel.name} in {member.guild.name}")
            
            # Cleanup player
            try:
                player = self.player_manager.get_existing(member.guild.id)
                if player:
                    await player.stop()
                    player.voice_client = None
                    logger.info(f"Cleaned up player after disconnect in {member.guild.name}")
            except Exception as e:
                logger.error(f"Failed to cleanup after voice disconnect: {e}")
    
    async def close(self):
        """Close the bot and cleanup resources."""
        logger.info("🔄 Shutting down bot...")
        
        try:
            # Stop health monitor
            if self.health_monitor:
                await self.health_monitor.stop()
            
            # Shutdown player manager
            if self.player_manager:
                await self.player_manager.shutdown()
            
            # Close HTTP session
            if self.session and not self.session.closed:
                await self.session.close()
            
            # Close database connections
            await db_manager.close()
            
            logger.info("✅ Cleanup completed")
            
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
        
        # Call parent close
        await super().close()
    
    async def shutdown(self):
        """Graceful shutdown."""
        try:
            await self.close()
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
        finally:
            # Force exit if needed
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.stop()

async def main():
    """Main entry point."""
    try:
        # Create directories first
        create_directories()
        
        # Setup logging
        setup_logging()
        logger.info("🚀 Starting HERTZ Discord Music Bot...")
        
        # Create and run bot
        bot = HertzBot()
        
        # Get token from config
        config = get_config()
        
        if not config.discord_token:
            logger.error("❌ No Discord token provided!")
            logger.error("Please set DISCORD_TOKEN in your environment or .env file")
            sys.exit(1)
        
        # Run the bot
        async with bot:
            await bot.start(config.discord_token)
        
    except KeyboardInterrupt:
        logger.info("🛑 Received keyboard interrupt")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        logger.info("🔄 Bot shutdown complete")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown requested by user")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)