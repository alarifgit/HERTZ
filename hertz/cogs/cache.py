# hertz/cogs/cache.py
import logging
import os
from typing import Optional, List

import disnake
from disnake import ApplicationCommandInteraction
from disnake.ext import commands

logger = logging.getLogger(__name__)

class CacheCommands(commands.Cog):
    """Commands for cache management"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @commands.slash_command(
        name="cache-info",
        description="Show information about the file cache"
    )
    async def cache_info(self, inter: ApplicationCommandInteraction):
        """Display cache information"""
        await inter.response.defer()
        
        try:
            from ..db.client import get_total_cache_size, get_recent_file_caches
            total_size = await get_total_cache_size()
            
            # Get cache limit
            cache_limit = self.bot.config.cache_limit_bytes
            
            # Get count of cached files
            cache_dir = self.bot.config.CACHE_DIR
            file_count = len([f for f in os.listdir(cache_dir) if os.path.isfile(os.path.join(cache_dir, f)) and not f.endswith('.tmp')])
            
            # Get recent cached songs (limited to 5)
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
                recent_details = []
                for idx, file in enumerate(recent_files):
                    song_title = file.hash  # Ideally we'd have song titles here, but we'd need to track those in DB
                    file_size = f"{file.bytes/1024/1024:.2f} MB"
                    access_time = file.accessedAt.strftime("%Y-%m-%d %H:%M:%S")
                    recent_details.append(f"{idx+1}. {song_title} ({file_size}) - Last accessed: {access_time}")
                
                embed.add_field(name="Recently Accessed Songs", value="\n".join(recent_details), inline=False)
            
            await inter.followup.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error displaying cache info: {e}")
            await inter.followup.send("Error retrieving cache information")