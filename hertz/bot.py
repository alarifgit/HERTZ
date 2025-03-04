# hertz/bot.py
import os
import asyncio
import logging
import sys
from typing import Dict, Optional, List

import disnake
from disnake.ext import commands

from .config import Config
from .services.player_manager import PlayerManager
from .services.file_cache import FileCacheProvider
from .db.client import initialize_db

logger = logging.getLogger(__name__)

class HertzBot(commands.InteractionBot):
    def __init__(self, config: Config):
        intents = disnake.Intents.default()
        intents.message_content = True
        intents.voice_states = True
        intents.guilds = True
        
        self.config = config
        self.file_cache = FileCacheProvider(config)
        self.player_manager = PlayerManager(self.file_cache)
        self.players = self.player_manager.players  # Reference to players dictionary for health checks
        
        # Use your server ID for test_guilds (faster command registration)
        test_guilds = None
        
        super().__init__(
            intents=intents,
            test_guilds=test_guilds,  # This is the key for rapid command registration
            activity=disnake.Activity(
                type=getattr(disnake.ActivityType, config.BOT_ACTIVITY_TYPE.lower()),
                name=config.BOT_ACTIVITY,
                url=config.BOT_ACTIVITY_URL if config.BOT_ACTIVITY_TYPE == "STREAMING" else None
            ),
            status=getattr(disnake.Status, config.BOT_STATUS.lower())
        )
        
        # Add a test slash command directly to verify it works
        @self.slash_command(
            name="ping",
            description="Test command - responds with pong!"
        )
        async def ping(inter: disnake.ApplicationCommandInteraction):
            await inter.response.send_message("Pong!")
            
        logger.info("Added ping command directly to bot")
    
    async def start(self, *args, **kwargs):
        """Override start to initialize database and load cogs before connecting"""
        logger.info("Starting health checks...")
        
        # Test database connection
        try:
            await initialize_db()
            logger.info("Database connection successful")
        except Exception as e:
            logger.critical(f"Database connection failed: {e}")
            sys.exit(1)
            
        # Test YouTube API
        try:
            from .services.youtube import test_youtube_api
            await test_youtube_api(self.config.YOUTUBE_API_KEY)
            logger.info("YouTube API connection successful")
        except Exception as e:
            logger.error(f"YouTube API connection failed: {e}")
            # Continue anyway, but warn
            
        # Test Spotify API if configured
        if self.config.SPOTIFY_CLIENT_ID and self.config.SPOTIFY_CLIENT_SECRET:
            try:
                from .services.spotify import test_spotify_api
                await test_spotify_api(self.config)
                logger.info("Spotify API connection successful")
            except Exception as e:
                logger.error(f"Spotify API connection failed: {e}")
                # Continue anyway, but warn
                
        # Test cache directories
        try:
            await self.file_cache.cleanup()
            logger.info("File cache initialization successful")
        except Exception as e:
            logger.error(f"File cache initialization failed: {e}")
            # Try to create directories again
            try:
                os.makedirs(self.config.CACHE_DIR, exist_ok=True)
                os.makedirs(os.path.join(self.config.CACHE_DIR, 'tmp'), exist_ok=True)
            except Exception:
                pass
        
        # Load cogs before connecting
        await self.load_cogs()
        
        # Start periodic health check task
        self.start_health_check_task()
        
        # Continue with normal startup
        await super().start(*args, **kwargs)
    
    def start_health_check_task(self):
        """Start a periodic task to check bot health"""
        async def health_check():
            while True:
                try:
                    # Check bot connection
                    if not self.is_ready():
                        logger.warning("Bot is not connected, awaiting reconnect")
                        # Let the automatic reconnect handle it
                    
                    # Check voice connections
                    for guild_id, player in self.player_manager.players.items():
                        if player.voice_client and player.voice_client.is_connected():
                            # Check if voice client is playing but status is not PLAYING
                            if player.voice_client.is_playing() and player.status != player.Status.PLAYING:
                                logger.warning(f"Voice client state mismatch in guild {guild_id}, fixing")
                                player.status = player.Status.PLAYING
                            # Check if voice client is not playing but status is PLAYING
                            elif not player.voice_client.is_playing() and player.status == player.Status.PLAYING:
                                logger.warning(f"Voice client state mismatch in guild {guild_id}, fixing")
                                player.status = player.Status.IDLE
                    
                    # Update the health status file
                    with open('/data/health_status', 'w') as f:
                        import time
                        f.write(str(int(time.time())))
                    
                    # Wait for next check
                    await asyncio.sleep(60)  # Check every minute
                except Exception as e:
                    logger.error(f"Error in health check: {e}")
                    await asyncio.sleep(10)  # Wait a bit before retrying
        
        # Start the health check task
        asyncio.create_task(health_check())
    
    async def load_cogs(self) -> None:
        """Load all cogs"""
        try:
            logger.info("Starting to load cogs...")
            
            # Import cog modules
            from .cogs import music, queue, playback, favorites, config, cache, health
            
            # Add cogs with detailed logging
            self.add_cog(music.MusicCommands(self))
            logger.info("Added music commands cog")
            
            self.add_cog(queue.QueueCommands(self))
            logger.info("Added queue commands cog")
            
            self.add_cog(playback.PlaybackCommands(self))
            logger.info("Added playback commands cog")
            
            self.add_cog(favorites.FavoritesCommands(self))
            logger.info("Added favorites commands cog")
            
            self.add_cog(config.ConfigCommands(self))
            logger.info("Added config commands cog")
            
            self.add_cog(cache.CacheCommands(self))
            logger.info("Added cache commands cog")
            
            self.add_cog(health.HealthCommands(self))
            logger.info("Added health commands cog")
            
            # Log registered commands
            all_commands = []
            for cmd in self.application_commands:
                all_commands.append(cmd.name)
            logger.info(f"Registered commands: {', '.join(all_commands)}")
            
        except Exception as e:
            logger.error(f"Error loading cogs: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def on_ready(self):
        """Called when the bot is ready"""
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
        logger.info(f"Connected to {len(self.guilds)} guilds")
        
        # Print all available commands
        all_commands = []
        for cmd in self.application_commands:
            all_commands.append(cmd.name)
        logger.info(f"Commands available: {', '.join(all_commands)}")
        
        logger.info(f"Invite URL: https://discord.com/oauth2/authorize?client_id={self.user.id}&scope=bot%20applications.commands&permissions=277062449216")
    
    async def on_guild_join(self, guild: disnake.Guild):
        """Handle the bot joining a new guild"""
        logger.info(f"Joined new guild: {guild.name} (ID: {guild.id})")
        
        try:
            # Create settings for the guild
            from .db.client import get_guild_settings
            await get_guild_settings(str(guild.id))
            
            # Try to send welcome message to the guild owner
            if guild.owner:
                try:
                    embed = disnake.Embed(
                        title="Thanks for adding HERTZ!",
                        description=(
                            "👋 Hi! Someone (probably you) just invited me to a server you own. "
                            "By default, I'm usable by all guild members in all guild channels. "
                            "Use `/config` commands to configure my behavior."
                        ),
                        color=disnake.Color.blue()
                    )
                    await guild.owner.send(embed=embed)
                except disnake.Forbidden:
                    logger.info(f"Could not DM owner of {guild.name} - their privacy settings prevent DMs")
                    
                    # Alternative: Try to find a system channel or general channel to post welcome message
                    welcome_channel = guild.system_channel or next((c for c in guild.text_channels if c.name.lower() in ["general", "welcome", "chat"]), None)
                    
                    if welcome_channel and welcome_channel.permissions_for(guild.me).send_messages:
                        try:
                            server_embed = disnake.Embed(
                                title="Thanks for adding HERTZ!",
                                description=(
                                    "👋 Hi! Thanks for adding me to your server!\n"
                                    "Use `/play` to start playing music and `/help` to see all commands.\n"
                                    "Server admins can use `/config` to customize my behavior."
                                ),
                                color=disnake.Color.blue()
                            )
                            await welcome_channel.send(embed=server_embed)
                        except Exception as e:
                            logger.info(f"Could not send welcome message to channel: {e}")
            else:
                logger.warning(f"Could not find owner for guild: {guild.name}")
        except Exception as e:
            logger.error(f"Error in guild join handler: {e}")
    
    async def on_voice_state_update(self, member: disnake.Member, before: disnake.VoiceState, after: disnake.VoiceState):
        """Handle voice state updates with improved error handling"""
        # Skip bot updates
        if member.bot:
            return
        
        try:
            # Handle disconnections
            if before.channel and (not after.channel or before.channel.id != after.channel.id):
                player = self.player_manager.get_player(member.guild.id)
                
                if not player.voice_client:
                    return
                    
                if player.voice_client.channel.id == before.channel.id:
                    # Check if any non-bot users remain
                    non_bot_count = sum(1 for m in before.channel.members if not m.bot)
                    
                    if non_bot_count == 0:
                        from .db.client import get_guild_settings
                        settings = await get_guild_settings(str(member.guild.id))
                        
                        if settings.leaveIfNoListeners:
                            logger.info(f"All users left voice channel in {member.guild.name}, disconnecting")
                            await player.disconnect()
                
            # Handle reconnection attempts for moved channels
            if after.channel and member.id == self.user.id:
                player = self.player_manager.get_player(member.guild.id)
                
                if player.voice_client and player.voice_client.channel.id != after.channel.id:
                    logger.info(f"Bot was moved to a new channel in {member.guild.name}, reconnecting")
                    await player.connect(after.channel)
                    if player.status in [player.Status.PLAYING, player.Status.PAUSED]:
                        await player.play()
                        
        except Exception as e:
            logger.error(f"Error in voice state update handler: {e}")
            import traceback
            logger.error(traceback.format_exc())