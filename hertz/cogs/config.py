# hertz/cogs/config.py
import logging
from typing import Optional, Union

import disnake
from disnake import ApplicationCommandInteraction
from disnake.ext import commands

logger = logging.getLogger(__name__)

class ConfigCommands(commands.Cog):
    """Commands for configuring the bot"""
    
    def __init__(self, bot):
        self.bot = bot
    
    # Changed from variable assignment to decorator pattern
    @commands.slash_command(
        name="config",
        description="Configure bot settings",
        default_member_permissions=disnake.Permissions(manage_guild=True)
    )
    async def config_group(self, inter: ApplicationCommandInteraction):
        """Base command for config - never called directly"""
        pass  # This is a group and not called directly
    
    @config_group.sub_command(
        name="get",
        description="Show all settings"
    )
    async def get_config(self, inter: ApplicationCommandInteraction):
        """Display all current settings"""
        await inter.response.defer()
        
        # Get current settings
        from ..db.client import get_guild_settings
        settings = await get_guild_settings(str(inter.guild.id))
        
        # Create embed with settings
        embed = disnake.Embed(
            title="📡 HERTZ Control Panel",
            description="Current broadcast configuration parameters",
            color=disnake.Color.blue()
        )
        
        settings_to_show = {
            "Playlist Limit": settings.playlistLimit,
            "Wait before leaving after queue empty": (
                "never leave" if settings.secondsToWaitAfterQueueEmpties == 0
                else f"{settings.secondsToWaitAfterQueueEmpties}s"
            ),
            "Leave if there are no listeners": "yes" if settings.leaveIfNoListeners else "no",
            "Auto announce next track in queue": "yes" if settings.autoAnnounceNextSong else "no",
            "Add to queue responses show for requester only": "yes" if settings.queueAddResponseEphemeral else "no",
            "Default Volume": f"{settings.defaultVolume}%",
            "Default queue page size": settings.defaultQueuePageSize,
            "Reduce volume when people speak": "yes" if settings.turnDownVolumeWhenPeopleSpeak else "no",
            "Volume reduction target": f"{settings.turnDownVolumeWhenPeopleSpeakTarget}%",
        }
        
        # Add all settings to the embed description
        description = ""
        for key, value in settings_to_show.items():
            description += f"**{key}**: {value}\n"
        
        embed.description = description
        
        await inter.followup.send(embed=embed)
    
    @config_group.sub_command(
        name="set-playlist-limit",
        description="Set the maximum number of tracks from a playlist"
    )
    async def set_playlist_limit(
        self,
        inter: ApplicationCommandInteraction,
        limit: int = commands.Param(
            description="Maximum number of tracks (min: 1)",
            ge=1
        )
    ):
        """Set maximum tracks to add from playlists"""
        await inter.response.defer()
        
        from ..db.client import get_guild_settings
        settings = await get_guild_settings(str(inter.guild.id))
        
        # Update setting
        settings.playlistLimit = limit
        await settings.save()
        
        await inter.followup.send("📊 Signal calibrated: playlist limit updated")
    
    @config_group.sub_command(
        name="set-wait-after-queue-empties",
        description="Set the time to wait before leaving when queue empties"
    )
    async def set_wait_after_queue_empties(
        self,
        inter: ApplicationCommandInteraction,
        delay: int = commands.Param(
            description="Delay in seconds (0 = never leave)",
            ge=0
        )
    ):
        """Set wait time before disconnecting when queue is empty"""
        await inter.response.defer()
        
        from ..db.client import get_guild_settings
        settings = await get_guild_settings(str(inter.guild.id))
        
        # Update setting
        settings.secondsToWaitAfterQueueEmpties = delay
        await settings.save()
        
        await inter.followup.send("⏱️ Timing protocol updated: automatic disconnect delay configured")
    
    @config_group.sub_command(
        name="set-leave-if-no-listeners",
        description="Set whether to leave when all other participants leave"
    )
    async def set_leave_if_no_listeners(
        self,
        inter: ApplicationCommandInteraction,
        value: bool = commands.Param(
            description="Whether to leave when everyone else leaves"
        )
    ):
        """Set whether to leave when all users leave the channel"""
        await inter.response.defer()
        
        from ..db.client import get_guild_settings
        settings = await get_guild_settings(str(inter.guild.id))
        
        # Update setting
        settings.leaveIfNoListeners = value
        await settings.save()
        
        await inter.followup.send("🔌 Auto-disconnect protocol updated: empty channel behavior configured")
    
    @config_group.sub_command(
        name="set-queue-add-response-hidden",
        description="Set whether bot responses to queue additions are only for requester"
    )
    async def set_queue_add_response_hidden(
        self,
        inter: ApplicationCommandInteraction,
        value: bool = commands.Param(
            description="Whether responses should be ephemeral (only visible to requester)"
        )
    ):
        """Set whether queue add responses are only visible to requester"""
        await inter.response.defer()
        
        from ..db.client import get_guild_settings
        settings = await get_guild_settings(str(inter.guild.id))
        
        # Update setting
        settings.queueAddResponseEphemeral = value
        await settings.save()
        
        await inter.followup.send("📲 Notification protocol updated: queue addition visibility configured")
    
    @config_group.sub_command(
        name="set-auto-announce-next-song",
        description="Set whether to announce next song automatically"
    )
    async def set_auto_announce_next_song(
        self,
        inter: ApplicationCommandInteraction,
        value: bool = commands.Param(
            description="Whether to announce the next song in the queue automatically"
        )
    ):
        """Set whether to auto-announce next song when track changes"""
        await inter.response.defer()
        
        from ..db.client import get_guild_settings
        settings = await get_guild_settings(str(inter.guild.id))
        
        # Update setting
        settings.autoAnnounceNextSong = value
        await settings.save()
        
        await inter.followup.send("📣 Broadcast protocol updated: auto-announce setting configured")
    
    @config_group.sub_command(
        name="set-default-volume",
        description="Set default volume used when entering voice channel"
    )
    async def set_default_volume(
        self,
        inter: ApplicationCommandInteraction,
        level: int = commands.Param(
            description="Volume percentage (0-100)",
            ge=0,
            le=100
        )
    ):
        """Set the default volume level"""
        await inter.response.defer()
        
        from ..db.client import get_guild_settings
        settings = await get_guild_settings(str(inter.guild.id))
        
        # Update setting
        settings.defaultVolume = level
        await settings.save()
        
        await inter.followup.send(f"🔊 Audio gain calibrated: default volume set to {level}%")
    
    @config_group.sub_command(
        name="set-default-queue-page-size",
        description="Set the default page size of the /queue command"
    )
    async def set_default_queue_page_size(
        self,
        inter: ApplicationCommandInteraction,
        page_size: int = commands.Param(
            description="Page size (1-30)",
            ge=1,
            le=30
        )
    ):
        """Set the default page size for queue display"""
        await inter.response.defer()
        
        from ..db.client import get_guild_settings
        settings = await get_guild_settings(str(inter.guild.id))
        
        # Update setting
        settings.defaultQueuePageSize = page_size
        await settings.save()
        
        await inter.followup.send("📋 Display parameters updated: queue page size configured")
    
    @config_group.sub_command(
        name="set-reduce-vol-when-voice",
        description="Set whether to turn down volume when people speak"
    )
    async def set_reduce_vol_when_voice(
        self,
        inter: ApplicationCommandInteraction,
        value: bool = commands.Param(
            description="Whether to turn down volume when people speak"
        )
    ):
        """Set whether to reduce volume when people speak"""
        await inter.response.defer()
        
        from ..db.client import get_guild_settings
        settings = await get_guild_settings(str(inter.guild.id))
        
        # Update setting
        settings.turnDownVolumeWhenPeopleSpeak = value
        await settings.save()
        
        await inter.followup.send("🎤 Voice priority protocol updated: volume reduction during speech configured")
    
    @config_group.sub_command(
        name="set-reduce-vol-when-voice-target",
        description="Set the target volume when people speak"
    )
    async def set_reduce_vol_when_voice_target(
        self,
        inter: ApplicationCommandInteraction,
        volume: int = commands.Param(
            description="Volume percentage when people speak (0-100)",
            ge=0,
            le=100
        )
    ):
        """Set the volume reduction target percentage"""
        await inter.response.defer()
        
        from ..db.client import get_guild_settings
        settings = await get_guild_settings(str(inter.guild.id))
        
        # Update setting
        settings.turnDownVolumeWhenPeopleSpeakTarget = volume
        await settings.save()
        
        await inter.followup.send(f"🎚️ Voice priority threshold calibrated: speech volume set to {volume}%")