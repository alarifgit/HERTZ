# hertz/cogs/favorites.py
import logging
from typing import List, Optional

import disnake
from disnake import ApplicationCommandInteraction
from disnake.ext import commands

from ..utils.error_msg import error_msg
from ..utils.responses import Responses

logger = logging.getLogger(__name__)

class FavoritesCommands(commands.Cog):
    """Commands for managing favorites"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @commands.slash_command(
        name="favorites",
        description="Manage your favorite tracks and playlists"
    )
    async def favorites_group(self, inter: ApplicationCommandInteraction):
        """Base command for favorites - never called directly"""
        pass  # This is a group and not called directly
    
    @favorites_group.sub_command(
        name="use",
        description="Play a favorite frequency"
    )
    async def use_favorite(
        self,
        inter: ApplicationCommandInteraction,
        name: str = commands.Param(
            description="Name of the favorite frequency",
            autocomplete=True
        ),
        immediate: bool = commands.Param(
            description="Add track to front of queue",
            default=False
        ),
        shuffle: bool = commands.Param(
            description="Shuffle playlist items",
            default=False
        ),
        split: bool = commands.Param(
            description="Split videos into chapters",
            default=False
        ),
        skip: bool = commands.Param(
            description="Skip current track after adding",
            default=False
        )
    ):
        """Use a saved favorite"""
        await inter.response.defer()
        
        # Check if user is in voice
        if not inter.author.voice:
            await inter.followup.send(error_msg("you need to be in a voice channel"))
            return
        
        # Get the favorite
        from ..db.client import get_favorite_query
        favorite = await get_favorite_query(str(inter.guild.id), name)
        if not favorite:
            await inter.followup.send(error_msg("no favorite with that name exists"))
            return
        
        logger.info(f"[COMMAND] {inter.author.display_name} used favorite '{name}'")
        
        # Use play command to play this query
        play_command = self.bot.get_slash_command("play")
        if not play_command:
            await inter.followup.send(error_msg("play command not found"))
            return
            
        # Create a new interaction context to invoke the play command
        context = await self.bot.get_application_context(inter)
        await play_command(context, 
                         query=favorite.query, 
                         immediate=immediate, 
                         shuffle=shuffle, 
                         split=split, 
                         skip=skip)
    
    @favorites_group.sub_command(
        name="list",
        description="List all saved frequencies"
    )
    async def list_favorites(self, inter: ApplicationCommandInteraction):
        """List all favorites for this server"""
        await inter.response.defer()
        
        from ..db.client import get_favorite_queries
        favorites = await get_favorite_queries(str(inter.guild.id))
        
        if not favorites:
            await inter.followup.send("📭 No saved frequencies found. Create favorites with `/favorites create`")
            return
        
        logger.info(f"[COMMAND] {inter.author.display_name} listed favorites")
        
        # Create embed with favorites
        embed = disnake.Embed(
            title="🎵 Saved Frequencies",
            description="Your preferred tracks and playlists",
            color=disnake.Color.blue()
        )
        
        # Group by author
        favorites_by_author = {}
        for fav in favorites:
            if fav.authorId not in favorites_by_author:
                favorites_by_author[fav.authorId] = []
            favorites_by_author[fav.authorId].append(fav)
        
        # Add fields for each user's favorites
        for author_id, favs in favorites_by_author.items():
            # Format each favorite as a line in the field
            field_value = "\n".join([
                f"**{fav.name}**: {fav.query[:50]}{'...' if len(fav.query) > 50 else ''}"
                for fav in favs
            ])
            
            embed.add_field(
                name=f"<@{author_id}>'s Frequencies",
                value=field_value,
                inline=False
            )
        
        # Send the embed
        await inter.followup.send(embed=embed)
    
    @favorites_group.sub_command(
        name="create",
        description="Save a new favorite frequency"
    )
    async def create_favorite(
        self,
        inter: ApplicationCommandInteraction,
        name: str = commands.Param(
            description="Name for this frequency preset"
        ),
        query: str = commands.Param(
            description="YouTube URL, Spotify URL, or search query"
        )
    ):
        """Create a new favorite"""
        await inter.response.defer()
        
        # Check if favorite already exists
        from ..db.client import get_favorite_query, create_favorite_query
        existing = await get_favorite_query(str(inter.guild.id), name)
        if existing:
            await inter.followup.send(error_msg("a favorite with that name already exists"))
            return
        
        # Create the favorite
        try:
            await create_favorite_query(
                guild_id=str(inter.guild.id),
                author_id=str(inter.author.id),
                name=name,
                query=query
            )
            
            logger.info(f"[COMMAND] {inter.author.display_name} created favorite '{name}'")
            await inter.followup.send("💾 Frequency saved to presets! Ready for recall")
        except Exception as e:
            logger.error(f"[ERROR] Error creating favorite: {e}")
            await inter.followup.send(error_msg(str(e)))
    
    @favorites_group.sub_command(
        name="remove",
        description="Remove a saved frequency"
    )
    async def remove_favorite(
        self,
        inter: ApplicationCommandInteraction,
        name: str = commands.Param(
            description="Name of the frequency to remove",
            autocomplete=True
        )
    ):
        """Remove a favorite"""
        await inter.response.defer()
        
        # Get the favorite
        from ..db.client import get_favorite_query, delete_favorite_query
        favorite = await get_favorite_query(str(inter.guild.id), name)
        if not favorite:
            await inter.followup.send(error_msg("no favorite with that name exists"))
            return
        
        # Check if user is allowed to remove
        is_owner = inter.author.id == inter.guild.owner_id
        if favorite.authorId != str(inter.author.id) and not is_owner:
            await inter.followup.send(error_msg("you can only remove your own favorites"))
            return
        
        # Remove the favorite
        try:
            await delete_favorite_query(favorite.id)
            logger.info(f"[COMMAND] {inter.author.display_name} removed favorite '{name}'")
            await inter.followup.send("🗑️ Frequency deleted from presets")
        except Exception as e:
            logger.error(f"[ERROR] Error removing favorite: {e}")
            await inter.followup.send(error_msg(str(e)))
    
    @use_favorite.autocomplete("name")
    @remove_favorite.autocomplete("name")
    async def favorite_name_autocomplete(
        self,
        inter: ApplicationCommandInteraction,
        string: str
    ):
        """Provide autocomplete for favorite names"""
        try:
            # Get all favorites for this guild
            from ..db.client import get_favorite_queries
            favorites = await get_favorite_queries(str(inter.guild.id))
            
            # Filter by provided string
            if string:
                string = string.lower()
                favorites = [
                    f for f in favorites 
                    if string in f.name.lower()
                ]
            
            # For remove command, only show user's favorites unless they're the owner
            if inter.application_command.name == "remove" and inter.author.id != inter.guild.owner_id:
                favorites = [
                    f for f in favorites 
                    if f.authorId == str(inter.author.id)
                ]
            
            # Return formatted choices (up to 25)
            return [
                {"name": f.name, "value": f.name}
                for f in favorites[:25]
            ]
        except Exception as e:
            logger.error(f"[ERROR] Error in favorites autocomplete: {e}")
            return []