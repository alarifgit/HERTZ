# hertz/utils/voice.py
import disnake
from typing import Optional, Tuple, List

def get_member_voice_channel(member: disnake.Member) -> Optional[disnake.VoiceChannel]:
    """Get the voice channel a member is in, or None if not in voice"""
    if not member or not member.voice or not member.voice.channel:
        return None
    
    channel = member.voice.channel
    if isinstance(channel, disnake.VoiceChannel):
        return channel
    
    return None

def get_size_without_bots(channel: disnake.VoiceChannel) -> int:
    """Count non-bot members in a voice channel"""
    return sum(1 for member in channel.members if not member.bot)

def get_most_popular_voice_channel(guild: disnake.Guild) -> disnake.VoiceChannel:
    """Find the voice channel with the most non-bot users"""
    voice_channels = [
        channel for channel in guild.channels 
        if isinstance(channel, disnake.VoiceChannel)
    ]
    
    if not voice_channels:
        raise ValueError("No voice channels found in guild")
    
    # Find channel with most non-bot users
    channels_with_size = [(channel, get_size_without_bots(channel)) for channel in voice_channels]
    channels_with_size.sort(key=lambda x: x[1], reverse=True)
    
    # Return the most popular channel, or the first one if they're all empty
    return channels_with_size[0][0]

def is_user_in_voice(guild: disnake.Guild, user_id: int) -> bool:
    """Check if a user is in any voice channel in the guild"""
    for channel in guild.channels:
        if isinstance(channel, disnake.VoiceChannel):
            for member in channel.members:
                if member.id == user_id:
                    return True
    
    return False