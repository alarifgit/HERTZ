# hertz/cogs/health.py
import os
import logging
import time
import asyncio
from typing import Optional

import disnake
from disnake import ApplicationCommandInteraction
from disnake.ext import commands
from disnake.ui import View, Button

from ..utils.embeds import create_health_embed, create_cache_embed, create_music_stats_embed

logger = logging.getLogger(__name__)

class DashboardView(View):
    def __init__(self, bot, inter, timeout=60):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.inter = inter
        self.current_page = 0
        self.pages = ["health", "cache", "music"]
    
    @disnake.ui.button(label="Health", style=disnake.ButtonStyle.primary, disabled=True)
    async def health_button(self, button: Button, interaction: disnake.MessageInteraction):
        self.current_page = 0
        await self.update_view(interaction)
    
    @disnake.ui.button(label="Cache", style=disnake.ButtonStyle.primary)
    async def cache_button(self, button: Button, interaction: disnake.MessageInteraction):
        self.current_page = 1
        await self.update_view(interaction)
    
    @disnake.ui.button(label="Music", style=disnake.ButtonStyle.primary)
    async def music_button(self, button: Button, interaction: disnake.MessageInteraction):
        self.current_page = 2
        await self.update_view(interaction)
    
    async def update_view(self, interaction: disnake.MessageInteraction):
        # Update button states
        for i, child in enumerate(self.children):
            if hasattr(child, "disabled"):
                child.disabled = (i == self.current_page)  # Disable current button
        
        # Get current embed
        embed = await self.get_current_embed()
        
        # Edit the message
        await interaction.response.edit_message(embed=embed, view=self)
    
    async def get_current_embed(self):
        page_type = self.pages[self.current_page]
        
        if page_type == "health":
            return create_health_embed(self.bot)
        elif page_type == "cache":
            return await create_cache_embed(self.bot)  # Note the await here!
        elif page_type == "music":
            return create_music_stats_embed(self.bot)
        
        # Default fallback
        return disnake.Embed(title="Dashboard Error", description="Could not load page")

class HealthCommands(commands.Cog):
    """Commands for health check status and dashboard"""
    
    def __init__(self, bot):
        self.bot = bot
        self.health_file = '/data/health_status'
    
    @commands.slash_command(
        name="health",
        description="Check bot health status"
    )
    async def health_info(self, inter: ApplicationCommandInteraction):
        """Display health information"""
        await inter.response.defer()
        
        try:
            # Create health embed
            embed = create_health_embed(self.bot)
            
            await inter.followup.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error displaying health info: {e}")
            await inter.followup.send("Error retrieving health information")
    
    @commands.slash_command(
        name="dashboard",
        description="Interactive bot metrics dashboard"
    )
    async def dashboard(self, inter: ApplicationCommandInteraction):
        """Display interactive dashboard with all metrics"""
        await inter.response.defer()
        
        try:
            # Create initial health embed
            embed = create_health_embed(self.bot)
            
            # Create the view with buttons
            view = DashboardView(self.bot, inter)
            
            # Send the message with the view
            await inter.followup.send(embed=embed, view=view)
            
        except Exception as e:
            logger.error(f"Error displaying dashboard: {e}")
            await inter.followup.send("Error retrieving dashboard information")