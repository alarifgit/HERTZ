# hertz/bot.py
import os
import asyncio
import logging
import sys
import time
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
        
        # Health monitoring state
        self._last_voice_check = time.time()
        self._voice_issues_count = 0
        
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
                    
                    # Enhanced voice client monitoring
                    await self._check_voice_client_health()
                    
                    # Update the health status file
                    with open('/data/health_status', 'w') as f:
                        f.write(str(int(time.time())))
                    
                    # Wait for next check
                    await asyncio.sleep(60)  # Check every minute
                except Exception as e:
                    logger.error(f"Error in health check: {e}")
                    await asyncio.sleep(10)  # Wait a bit before retrying
        
        # Start the health check task
        asyncio.create_task(health_check())
    
    async def _check_voice_client_health(self):
        """Enhanced voice client health monitoring"""
        current_time = time.time()
        
        for guild_id, player in self.player_manager.players.items():
            try:
                # Skip if no voice client
                if not player.voice_client:
                    continue
                
                guild = self.get_guild(int(guild_id))
                guild_name = guild.name if guild else f"Unknown ({guild_id})"
                
                # Check for basic state mismatches
                voice_playing = player.voice_client.is_playing()
                voice_paused = player.voice_client.is_paused()
                player_playing = player.status == player.Status.PLAYING
                player_paused = player.status == player.Status.PAUSED
                player_idle = player.status == player.Status.IDLE
                
                # Fix state mismatches
                fixed_issue = False
                
                if voice_playing and not player_playing and not player_paused:
                    logger.warning(f"[HEALTH] Voice client playing but player idle in {guild_name}, fixing")
                    player.status = player.Status.PLAYING
                    fixed_issue = True
                    
                elif not voice_playing and not voice_paused and player_playing:
                    logger.warning(f"[HEALTH] Voice client stopped but player thinks it's playing in {guild_name}, fixing")
                    player.status = player.Status.IDLE
                    fixed_issue = True
                    
                elif voice_paused and player_playing:
                    logger.warning(f"[HEALTH] Voice client paused but player thinks it's playing in {guild_name}, fixing")
                    player.status = player.Status.PAUSED
                    fixed_issue = True
                
                # Check for stuck states
                if player.get_current() and player.status == player.Status.PLAYING:
                    # If player thinks it's playing but voice client isn't doing anything
                    if not voice_playing and not voice_paused:
                        logger.warning(f"[HEALTH] Player stuck in playing state in {guild_name}, attempting recovery")
                        try:
                            await player.play()
                            fixed_issue = True
                        except Exception as e:
                            logger.error(f"[HEALTH] Failed to recover player in {guild_name}: {e}")
                
                # Check for disconnected but still thinking connected
                if not player.voice_client.is_connected():
                    logger.warning(f"[HEALTH] Voice client disconnected but player thinks it's connected in {guild_name}")
                    await player.disconnect()
                    fixed_issue = True
                
                # Track consecutive issues
                if fixed_issue:
                    self._voice_issues_count += 1
                    if self._voice_issues_count > 10:
                        logger.error(f"[HEALTH] Too many voice issues ({self._voice_issues_count}), this may indicate a serious problem")
                else:
                    # Reset count if no issues found
                    if current_time - self._last_voice_check > 300:  # 5 minutes
                        self._voice_issues_count = 0
                
            except Exception as e:
                logger.error(f"[HEALTH] Error checking voice health for guild {guild_id}: {e}")
        
        self._last_voice_check = current_time
    
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
    
    async def on_voice_state_update(self, member: disnake.Member, before: disnake.VoiceState, after: disnake.VoiceState):
        """Handle voice state updates to manage auto-disconnect"""
        # Only care about other members leaving/joining channels where we're connected
        if member.bot:
            return
            
        player = self.player_manager.get_player(member.guild.id)
        if not player.voice_client:
            return
            
        # Get the channel we're connected to
        bot_channel = player.voice_client.channel
        if not bot_channel:
            return
        
        # Check if someone left our channel
        if before.channel == bot_channel and after.channel != bot_channel:
            logger.debug(f"[VOICE] Member {member.display_name} left voice channel {bot_channel.name}")
            
            # Check if we should leave due to empty channel
            from .db.client import get_guild_settings
            settings = await get_guild_settings(str(member.guild.id))
            
            if settings.leaveIfNoListeners:
                # Count non-bot members in the channel
                non_bot_members = [m for m in bot_channel.members if not m.bot]
                
                if len(non_bot_members) == 0:
                    logger.info(f"[VOICE] No listeners left in {bot_channel.name}, disconnecting")
                    await player.disconnect()
    
    async def on_guild_join(self, guild: disnake.Guild):
        """Handle the bot joining a new guild with improved owner detection"""
        logger.info(f"Joined new guild: {guild.name} (ID: {guild.id})")
        
        try:
            # Create settings for the guild
            from .db.client import get_guild_settings
            await get_guild_settings(str(guild.id))
            logger.info(f"Created settings for guild: {guild.name}")
            
            # Find a suitable channel for welcoming if we can't reach the owner
            welcome_channel = guild.system_channel or next((c for c in guild.text_channels if c.name.lower() in ["general", "welcome", "chat"]), None)
            
            # Attempt to explicitly fetch the guild owner
            guild_owner = None
            try:
                # Try to get the owner through the owner_id
                if guild.owner_id:
                    logger.info(f"Attempting to fetch owner with ID: {guild.owner_id}")
                    guild_owner = await guild.fetch_member(guild.owner_id)
                    if guild_owner:
                        logger.info(f"Successfully fetched owner: {guild_owner.name}#{guild_owner.discriminator}")
                
                # Fallback to the guild.owner property if the above fails
                if not guild_owner and guild.owner:
                    logger.info(f"Using guild.owner property")
                    guild_owner = guild.owner
            except Exception as owner_error:
                logger.error(f"Error fetching guild owner: {str(owner_error)}")
            
            # Prepare the welcome embeds
            owner_embed = disnake.Embed(
                title="HERTZ Music Bot - Now Online",
                description=(
                    "**🎛️ Setup Complete**\n\n"
                    "Thank you for adding HERTZ to your server! Your music bot is now online and ready.\n\n"
                    "**Quick Start Guide:**\n"
                    "• Use `/play` to start playing music\n"
                    "• Use `/health` to see bot diagnostics\n"
                    "• Administrators can use `/config` to adjust settings\n\n"
                    "By default, all server members can control HERTZ in all channels. "
                    "For better control, consider configuring channel-specific permissions."
                ),
                color=disnake.Color.blue()
            )
            
            owner_embed.add_field(
                name="🎵 Getting Started",
                value="Join a voice channel and use `/play` to start your first song!",
                inline=False
            )
            
            owner_embed.add_field(
                name="🔧 Support",
                value="If you need help, visit our support server or documentation.",
                inline=False
            )
            
            owner_embed.set_footer(text="HERTZ Music Bot - Professional Discord Audio")
            
            channel_embed = disnake.Embed(
                title="HERTZ Music Bot - Now Online",
                description=(
                    "**🎛️ Music Bot Ready**\n\n"
                    "Thanks for adding HERTZ to your server! Your music bot is now online.\n\n"
                    "• Use `/play` to start playing music\n"
                    "• Administrators can use `/config` to adjust settings\n\n"
                    "Join a voice channel to begin!"
                ),
                color=disnake.Color.blue()
            )
            
            # Try to send welcome message to the guild owner first
            owner_dm_sent = False
            if guild_owner:
                try:
                    await guild_owner.send(embed=owner_embed)
                    logger.info(f"Welcome message sent to owner of {guild.name}")
                    owner_dm_sent = True
                except disnake.Forbidden as e:
                    logger.warning(f"Could not DM owner of {guild.name} - their privacy settings prevent DMs: {str(e)}")
                except Exception as e:
                    logger.error(f"Error sending welcome message to owner of {guild.name}: {str(e)}")
            else:
                logger.warning(f"Could not find owner for guild: {guild.name}")
            
            # If we couldn't DM the owner, try a channel instead
            if not owner_dm_sent and welcome_channel and welcome_channel.permissions_for(guild.me).send_messages:
                try:
                    logger.info(f"Attempting to send welcome message to channel: {welcome_channel.name}")
                    await welcome_channel.send(embed=channel_embed)
                    logger.info(f"Welcome message sent to channel {welcome_channel.name} in {guild.name}")
                except Exception as e:
                    logger.error(f"Could not send welcome message to channel: {str(e)}")
            elif not owner_dm_sent:
                logger.warning(f"No suitable channel found to send welcome message in {guild.name}")
            
        except Exception as e:
            logger.error(f"Error in guild join handler: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def on_error(self, event, *args, **kwargs):
        """Handle errors more gracefully"""
        logger.error(f"Error in event {event}: {args}, {kwargs}")
        import traceback
        logger.error(traceback.format_exc())
    
    async def on_application_command_error(self, inter: disnake.ApplicationCommandInteraction, error: Exception):
        """Handle application command errors gracefully"""
        logger.error(f"Command error in {inter.application_command.name}: {error}")
        
        # Try to respond to the interaction if we haven't already
        try:
            if not inter.response.is_done():
                await inter.response.send_message(f"❌ An error occurred: {str(error)}", ephemeral=True)
            else:
                await inter.followup.send(f"❌ An error occurred: {str(error)}", ephemeral=True)
        except Exception as e:
            logger.error(f"Failed to send error message: {e}")