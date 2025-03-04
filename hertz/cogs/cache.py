# hertz/cogs/cache.py
import logging
import os
from typing import Optional

import disnake
from disnake import ApplicationCommandInteraction
from disnake.ext import commands

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
            from ..db.client import get_total_cache_size
            total_size = await get_total_cache_size()
            
            # Get cache limit
            cache_limit = self.bot.config.cache_limit_bytes
            
            # Get count of cached files
            cache_dir = self.bot.config.CACHE_DIR
            file_count = len([f for f in os.listdir(cache_dir) if os.path.isfile(os.path.join(cache_dir, f)) and not f.endswith('.tmp')])
            
            # Get recent cached songs (limited to 5)
            from ..db.client import get_recent_file_caches  # You'll need to add this
            recent_files = await get_recent_file_caches(5)
            
            # Create embed with cache info
            embed = disnake.Embed(
                title="Cache Information",
                color=disnake.Color.blue()
            )
            
            embed.add_field(name="Cache Size", value=f"{total_size/1024/1024:.2f} MB / {cache_limit/1024/1024:.2f} MB", inline=False)
            embed.add_field(name="Usage", value=f"{(total_size/cache_limit)*100:.1f}%", inline=True)
            embed.add_field(name="Files Cached", value=str(file_count), inline=True)
            
            if recent_files:
                embed.add_field(name="Recently Cached Songs", value="\n".join([f"{i+1}. {file.hash}" for i, file in enumerate(recent_files)]), inline=False)
            
            await inter.followup.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error displaying cache info: {e}")
            await inter.followup.send("Error retrieving cache information")