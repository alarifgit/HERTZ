"""
Error handling system for HERTZ bot
py-cord compatible version
"""

import logging
import traceback
import asyncio
from typing import Optional, Dict, Any, Union, Callable
import discord
from discord.ext import commands

logger = logging.getLogger(__name__)

class HertzError(Exception):
    """Base exception for HERTZ bot errors."""
    pass

class VoiceError(HertzError):
    """Voice-related errors."""
    pass

class QueueError(HertzError):
    """Queue-related errors."""
    pass

class TrackError(HertzError):
    """Track processing errors."""
    pass

class ErrorHandler:
    """Centralized error handler for the bot."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        
        # Error message mappings (simplified for py-cord compatibility)
        self.error_messages = {
            # Discord errors
            discord.Forbidden: "I don't have permission to perform this action.",
            discord.NotFound: "The requested resource was not found.",
            discord.HTTPException: "A Discord API error occurred. Please try again.",
            discord.ConnectionClosed: "Connection to Discord was lost. Please try again.",
            
            # Commands errors
            commands.CommandNotFound: "Command not found.",
            commands.MissingPermissions: "You don't have permission to use this command.",
            commands.BotMissingPermissions: "I don't have the required permissions to execute this command.",
            commands.CommandOnCooldown: "This command is on cooldown. Please wait before using it again.",
            commands.MissingRequiredArgument: "Missing required argument. Please check the command syntax.",
            commands.BadArgument: "Invalid argument provided. Please check the command syntax.",
            commands.CheckFailure: "Command check failed. You may not have permission to use this command.",
            
            # Voice errors
            VoiceError: "Voice channel error occurred.",
            
            # Custom errors
            QueueError: "Queue operation failed.",
            TrackError: "Track processing failed.",
            
            # Generic errors
            asyncio.TimeoutError: "Operation timed out. Please try again.",
            ConnectionError: "Network connection error. Please try again.",
            ValueError: "Invalid value provided. Please check your input.",
            FileNotFoundError: "Required file not found.",
            PermissionError: "Permission denied.",
        }
        
        # Setup error handlers
        self._setup_handlers()
        
        logger.info("Error handler initialized (py-cord compatible)")
    
    def _setup_handlers(self):
        """Setup error event handlers."""
        
        # Legacy command error handler
        @self.bot.event
        async def on_command_error(ctx: commands.Context, error: commands.CommandError):
            await self.handle_command_error(ctx, error)
            
        # Try to setup app command error handler if available
        try:
            @self.bot.tree.error
            async def on_app_command_error(interaction: discord.Interaction, error: Exception):
                await self.handle_interaction_error(interaction, error)
        except AttributeError:
            # Tree or app commands not available in this py-cord version
            logger.warning("App commands error handling not available in this py-cord version")
    
    async def handle_interaction_error(self, interaction: discord.Interaction, error: Exception):
        """Handle interaction command errors (slash commands)."""
        try:
            # Log the error
            logger.error(f"Interaction error: {error}", exc_info=error)
            
            # Get user-friendly message
            message = self._get_error_message(error)
            
            # Create error embed
            embed = discord.Embed(
                title="❌ Error",
                description=message,
                color=0xff6b6b
            )
            
            # Send response
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.response.send_message(embed=embed, ephemeral=True)
            except Exception as e:
                logger.error(f"Failed to send error response: {e}")
                
        except Exception as e:
            logger.error(f"Failed to handle interaction error: {e}")
    
    async def handle_command_error(self, ctx: commands.Context, error: commands.CommandError):
        """Handle legacy command errors."""
        try:
            # Log the error
            logger.error(f"Command error in {ctx.command.name if ctx.command else 'unknown'}: {error}", 
                        exc_info=error)
            
            # Get user-friendly message
            message = self._get_error_message(error)
            
            # Create error embed
            embed = discord.Embed(
                title="❌ Error",
                description=message,
                color=0xff6b6b
            )
            
            # Send response
            await ctx.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Failed to handle command error: {e}")
    
    def _get_error_message(self, error: Exception) -> str:
        """Get user-friendly error message."""
        # Check for specific error types
        for error_type, message in self.error_messages.items():
            if isinstance(error, error_type):
                return message
        
        # Handle specific error cases
        if isinstance(error, commands.CommandOnCooldown):
            return f"This command is on cooldown. Please wait {error.retry_after:.1f} seconds."
        
        if isinstance(error, commands.MissingRequiredArgument):
            return f"Missing required argument: `{error.param.name}`"
        
        if isinstance(error, commands.BadArgument):
            return f"Invalid argument: {str(error)}"
        
        # Check if it's a wrapped exception
        if hasattr(error, '__cause__') and error.__cause__:
            return self._get_error_message(error.__cause__)
        
        if hasattr(error, 'original') and error.original:
            return self._get_error_message(error.original)
        
        # Default message
        return "An unexpected error occurred. Please try again."
    
    def create_error_embed(self, message: str, title: str = "❌ Error") -> discord.Embed:
        """Create a standardized error embed."""
        return discord.Embed(
            title=title,
            description=message,
            color=0xff6b6b
        )
    
    def create_warning_embed(self, message: str, title: str = "⚠️ Warning") -> discord.Embed:
        """Create a standardized warning embed."""
        return discord.Embed(
            title=title,
            description=message,
            color=0xffa500
        )
    
    def create_success_embed(self, message: str, title: str = "✅ Success") -> discord.Embed:
        """Create a standardized success embed."""
        return discord.Embed(
            title=title,
            description=message,
            color=0x00ff00
        )
    
    def create_info_embed(self, message: str, title: str = "ℹ️ Information") -> discord.Embed:
        """Create a standardized info embed."""
        return discord.Embed(
            title=title,
            description=message,
            color=0x3498db
        )

# Utility functions for common error scenarios
def require_voice_connection(func):
    """Decorator to require voice connection."""
    async def wrapper(self, interaction: discord.Interaction, *args, **kwargs):
        if not interaction.user.voice:
            embed = discord.Embed(
                title="❌ Error",
                description="You must be in a voice channel to use this command.",
                color=0xff6b6b
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        return await func(self, interaction, *args, **kwargs)
    
    return wrapper

def require_same_voice_channel(func):
    """Decorator to require user and bot in same voice channel."""
    async def wrapper(self, interaction: discord.Interaction, *args, **kwargs):
        if not interaction.user.voice:
            embed = discord.Embed(
                title="❌ Error",
                description="You must be in a voice channel to use this command.",
                color=0xff6b6b
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        bot_voice = interaction.guild.voice_client
        if bot_voice and bot_voice.channel != interaction.user.voice.channel:
            embed = discord.Embed(
                title="❌ Error",
                description="You must be in the same voice channel as the bot.",
                color=0xff6b6b
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        return await func(self, interaction, *args, **kwargs)
    
    return wrapper

def require_playing(func):
    """Decorator to require music to be playing."""
    async def wrapper(self, interaction: discord.Interaction, *args, **kwargs):
        # Check if bot has player manager and music is playing
        if hasattr(self.bot, 'player_manager'):
            player = self.bot.player_manager.get_existing(interaction.guild.id)
            
            if not player or not player.is_playing():
                embed = discord.Embed(
                    title="❌ Error",
                    description="No music is currently playing.",
                    color=0xff6b6b
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
        
        return await func(self, interaction, *args, **kwargs)
    
    return wrapper