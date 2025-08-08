"""
Hertz Discord Music Bot
A Python implementation replicating Muse's functionality
"""
import discord
from discord.ext import commands
import asyncio
import logging
import os
import sys
from typing import Optional
from datetime import datetime, timezone
import colorlog

# Set up colored logging
handler = colorlog.StreamHandler()
handler.setFormatter(
    colorlog.ColoredFormatter(
        '%(log_color)s%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        log_colors={
            'DEBUG': 'cyan',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'red,bg_white',
        }
    )
)

logger = logging.getLogger('hertz')
logger.setLevel(logging.INFO)
logger.addHandler(handler)

class HertzBot(commands.Bot):
    """Main bot class for Hertz"""
    
    def __init__(self):
        # Set up intents
        intents = discord.Intents.default()
        intents.message_content = True
        intents.voice_states = True
        intents.guilds = True
        intents.members = True
        
        super().__init__(
            command_prefix='/',  # We'll use slash commands primarily
            intents=intents,
            help_command=None,  # We'll create custom help
            activity=discord.Activity(
                type=discord.ActivityType.playing,
                name=os.getenv('BOT_ACTIVITY', 'music 🎵')
            )
        )
        
        # Fix deprecated datetime.utcnow() usage
        self.start_time = datetime.now(timezone.utc)
        self.version = "1.0.0"
        
    async def setup_hook(self):
        """Initialize bot components before connecting to Discord"""
        logger.info("🎵 Setting up Hertz bot...")
        
        # Load cogs
        await self.load_extensions()
        
        # Sync slash commands
        logger.info("📡 Syncing slash commands...")
        try:
            synced = await self.tree.sync()
            logger.info(f"✅ Synced {len(synced)} slash commands")
        except Exception as e:
            logger.error(f"❌ Failed to sync commands: {e}")
    
    async def load_extensions(self):
        """Load all cog extensions"""
        cogs = [
            'cogs.music',
            'cogs.queue',
            'cogs.playback',
            'cogs.config',
            'cogs.utils'
        ]
        
        for cog in cogs:
            try:
                await self.load_extension(cog)
                logger.info(f"✅ Loaded cog: {cog}")
            except Exception as e:
                logger.error(f"❌ Failed to load cog {cog}: {e}")
    
    async def on_ready(self):
        """Called when bot is ready"""
        logger.info(f"🤖 {self.user} is ready and connected to Discord!")
        logger.info(f"📊 Connected to {len(self.guilds)} guilds")
        logger.info(f"🔗 Bot Invite URL:")
        logger.info(f"   {discord.utils.oauth_url(self.user.id, permissions=discord.Permissions(2150657024))}")
        
        print("\n" + "="*80)
        print("🎵 HERTZ DISCORD MUSIC BOT - READY")
        print("="*80)
        print(f"✅ Bot Online: {self.user}")
        print(f"🏠 Guilds: {len(self.guilds)}")
        print(f"📡 Commands: Synced")
        print(f"🔗 Invite URL:")
        print(f"   {discord.utils.oauth_url(self.user.id, permissions=discord.Permissions(2150657024))}")
        print("="*80 + "\n")
        
        logger.info("🚀 Hertz is fully ready!")
    
    async def on_guild_join(self, guild):
        """Called when bot joins a new guild"""
        logger.info(f"🎉 Joined new guild: {guild.name} (ID: {guild.id})")
        
        # Try to send welcome message to owner
        try:
            owner = await self.fetch_user(guild.owner_id)
            embed = discord.Embed(
                title="👋 Thanks for adding Hertz!",
                description=(
                    "I'm a music bot with features like:\n"
                    "• YouTube and Spotify playback\n"
                    "• Queue management with shuffle and loop\n"
                    "• Search with autocomplete\n"
                    "• Beautiful now playing embeds\n\n"
                    "Use `/help` to see all commands!"
                ),
                color=0x00ff00
            )
            await owner.send(embed=embed)
        except:
            pass
    
    async def on_voice_state_update(self, member, before, after):
        """Handle voice state changes for auto-disconnect"""
        if member.bot:
            return
        
        # Check if bot should disconnect (alone in voice channel)
        if before.channel and self.user in before.channel.members:
            # Count non-bot members
            humans = [m for m in before.channel.members if not m.bot]
            if len(humans) == 0:
                # Get voice client for this guild
                voice_client = discord.utils.get(self.voice_clients, guild=member.guild)
                if voice_client and voice_client.is_connected():
                    logger.info(f"📤 Disconnecting from {before.channel.name} (no users left)")
                    await asyncio.sleep(30)  # Wait 30 seconds before disconnecting
                    
                    # Check again if still alone
                    humans = [m for m in before.channel.members if not m.bot]
                    if len(humans) == 0 and voice_client.is_connected():
                        await voice_client.disconnect()

async def main():
    """Main entry point"""
    # Load environment variables
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        logger.error("❌ DISCORD_TOKEN not found in environment variables!")
        sys.exit(1)
    
    # Create bot instance
    bot = HertzBot()
    
    try:
        logger.info("🔐 Starting Discord connection...")
        await bot.start(token)
    except KeyboardInterrupt:
        logger.info("🛑 Received interrupt signal, shutting down...")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        raise
    finally:
        logger.info("🛑 Shutting down Hertz...")
        await bot.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n✅ Shutdown complete")