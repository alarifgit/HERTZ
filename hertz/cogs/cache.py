# hertz/cogs/cache.py
import logging
import os
from typing import Optional

import disnake
from disnake import ApplicationCommandInteraction
from disnake.ext import commands

from ..utils.embeds import create_cache_embed

logger = logging.getLogger(__name__)

class CacheCommands(commands.Cog):
    """Commands for cache management"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @commands.slash_command(
        name="cache",
        description="Show information about the file cache"
    )
    async def cache_info(self, inter: ApplicationCommandInteraction):
        """Display cache information"""
        await inter.response.defer()
        
        try:
            # Create cache embed using the utility function - note the await!
            embed = await create_cache_embed(self.bot)
            await inter.followup.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error displaying cache info: {e}")
            await inter.followup.send("Error retrieving cache information")