# hertz/bot.py
import os
import asyncio
import logging
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
        
        # Use your server ID for test_guilds (faster command registration)
        test_guilds = [1139634906943733760]
        
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
        """Override start to initialize database before connecting"""
        logger.info("Initializing database before starting bot...")
        await initialize_db()
        await self.file_cache.cleanup()
        await super().start(*args, **kwargs)
    
    async def load_cogs(self) -> None:
        """Load all cogs"""
        try:
            logger.info("Starting to load cogs...")
            
            # Import cog modules
            from .cogs import music, queue, playback, favorites, config
            
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
        
        # Load cogs after the bot is ready - THIS IS THE KEY CHANGE
        await self.load_cogs()
        
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
            from .db.client import get_guild_settings
            await get_guild_settings(str(guild.id))
            
            # Try to send a welcome message to the guild owner
            if guild.owner:  # Check if owner exists before sending
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
            else:
                logger.warning(f"Could not find owner for guild: {guild.name}")
        except Exception as e:
            logger.error(f"Error in guild join handler: {e}")
    
    async def on_voice_state_update(self, member: disnake.Member, before: disnake.VoiceState, after: disnake.VoiceState):
        """Handle voice state updates"""
        if member.bot:
            return
            
        if before.channel and (not after.channel or before.channel.id != after.channel.id):
            player = self.player_manager.get_player(member.guild.id)
            
            if not player.voice_client:
                return
                
            if player.voice_client.channel.id == before.channel.id:
                non_bot_count = sum(1 for m in before.channel.members if not m.bot)
                
                if non_bot_count == 0:
                    try:
                        from .db.client import get_guild_settings
                        settings = await get_guild_settings(str(member.guild.id))
                        
                        if settings.leaveIfNoListeners:
                            logger.info(f"All users left voice channel in {member.guild.name}, disconnecting")
                            await player.disconnect()
                    except Exception as e:
                        logger.error(f"Error in voice state update handler: {e}")