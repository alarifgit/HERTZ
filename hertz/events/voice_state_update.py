# hertz/events/voice_state_update.py
import logging
import asyncio
from typing import Optional

import disnake

from ..utils.voice import get_size_without_bots

logger = logging.getLogger(__name__)

async def handle_voice_state_update(
    bot,
    member: disnake.Member,
    before: disnake.VoiceState,
    after: disnake.VoiceState
) -> None:
    """
    Handle voice state updates to manage auto-disconnect like muse does
    
    This function is called whenever someone joins/leaves/moves between voice channels
    and handles automatic disconnection when the bot is alone.
    """
    # Only care about other members (not bots) leaving/joining channels where we're connected
    if member.bot:
        return
    
    # Get the player for this guild
    player = bot.player_manager.get_player(member.guild.id)
    
    # Only proceed if we have a voice connection
    if not player.voice_client:
        return
    
    # Get the channel we're connected to
    try:
        bot_channel = player.voice_client.channel
    except AttributeError:
        # Voice client might not have channel attribute in some states
        bot_channel = player.current_channel
    
    if not bot_channel:
        return
    
    # Check if someone left our channel
    if before.channel == bot_channel and after.channel != bot_channel:
        logger.debug(f"[VOICE] Member {member.display_name} left voice channel {bot_channel.name}")
        
        # Check if we should leave due to empty channel
        try:
            from ..db.client import get_guild_settings
            settings = await get_guild_settings(str(member.guild.id))
            
            if settings.leaveIfNoListeners:
                # Count non-bot members in the channel
                non_bot_count = get_size_without_bots(bot_channel)
                
                if non_bot_count == 0:
                    logger.info(f"[VOICE] No listeners left in {bot_channel.name}, disconnecting")
                    
                    # Disconnect the player
                    try:
                        await player.disconnect()
                    except Exception as e:
                        logger.error(f"[ERROR] Error during auto-disconnect: {e}")
        
        except Exception as e:
            logger.error(f"[ERROR] Error in voice state update handler: {e}")
    
    # Check if someone joined our channel (for logging/monitoring)
    elif after.channel == bot_channel and before.channel != bot_channel:
        logger.debug(f"[VOICE] Member {member.display_name} joined voice channel {bot_channel.name}")
        
        # Cancel any pending disconnect timer since we have listeners again
        if hasattr(player, 'disconnect_timer') and player.disconnect_timer:
            try:
                player.disconnect_timer.cancel()
                player.disconnect_timer = None
                logger.debug(f"[VOICE] Cancelled auto-disconnect timer - member joined")
            except Exception as e:
                logger.error(f"[ERROR] Error cancelling disconnect timer: {e}")

async def setup_voice_events(bot):
    """Set up voice state update event handler"""
    
    @bot.event
    async def on_voice_state_update(member: disnake.Member, before: disnake.VoiceState, after: disnake.VoiceState):
        """Event handler for voice state updates"""
        try:
            await handle_voice_state_update(bot, member, before, after)
        except Exception as e:
            logger.error(f"[ERROR] Unhandled error in voice state update: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    logger.info("Voice state update events registered")