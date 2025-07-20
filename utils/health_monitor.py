"""
Health monitoring service for HERTZ bot
Provides HTTP endpoints for monitoring bot health and metrics
"""

import asyncio
import logging
import time
import json
from typing import Dict, Any, Optional
from datetime import datetime
import psutil
import discord
from discord.ext import commands
from aiohttp import web, ClientSession
import platform

from config.settings import get_config

logger = logging.getLogger(__name__)

class HealthMonitor:
    """Health monitoring service with HTTP endpoints."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = get_config()
        self.start_time = time.time()
        
        # Health metrics
        self.metrics = {
            'commands_processed': 0,
            'songs_played': 0,
            'errors_count': 0,
            'response_times': [],
            'average_response_time': 0.0,
            'last_error': None,
            'last_restart': datetime.utcnow().isoformat()
        }
        
        # HTTP server
        self.app = None
        self.runner = None
        self.site = None
        
        if self.config.health_check_enabled:
            self.setup_http_server()
    
    def setup_http_server(self):
        """Setup HTTP server for health endpoints."""
        self.app = web.Application()
        
        # Health endpoints
        self.app.router.add_get('/health', self.health_endpoint)
        self.app.router.add_get('/metrics', self.metrics_endpoint)
        self.app.router.add_get('/status', self.status_endpoint)
        self.app.router.add_get('/guilds', self.guilds_endpoint)
        
        # Info endpoints
        self.app.router.add_get('/info', self.info_endpoint)
        self.app.router.add_get('/version', self.version_endpoint)
    
    async def start(self):
        """Start the health monitoring service."""
        if not self.config.health_check_enabled:
            return
        
        try:
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()
            
            self.site = web.TCPSite(
                self.runner, 
                '0.0.0.0', 
                self.config.health_check_port
            )
            await self.site.start()
            
            logger.info(f"Health monitor started on port {self.config.health_check_port}")
            
        except Exception as e:
            logger.error(f"Failed to start health monitor: {e}")
    
    async def stop(self):
        """Stop the health monitoring service."""
        if self.runner:
            await self.runner.cleanup()
            logger.info("Health monitor stopped")
    
    async def health_endpoint(self, request):
        """Basic health check endpoint."""
        try:
            # Check bot connectivity
            is_ready = self.bot.is_ready()
            latency = round(self.bot.latency * 1000, 2)  # ms
            
            # Basic system checks
            memory_usage = psutil.virtual_memory().percent
            cpu_usage = psutil.cpu_percent()
            
            # Determine health status
            status = "healthy"
            if not is_ready:
                status = "unhealthy"
            elif latency > 500:  # High latency
                status = "degraded"
            elif memory_usage > 90 or cpu_usage > 90:
                status = "degraded"
            
            health_data = {
                "status": status,
                "timestamp": datetime.utcnow().isoformat(),
                "uptime": time.time() - self.start_time,
                "bot_ready": is_ready,
                "latency_ms": latency,
                "memory_usage_percent": memory_usage,
                "cpu_usage_percent": cpu_usage
            }
            
            # Return appropriate HTTP status
            status_code = 200 if status == "healthy" else 503
            
            return web.json_response(health_data, status=status_code)
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return web.json_response(
                {"status": "error", "message": str(e)}, 
                status=500
            )
    
    async def metrics_endpoint(self, request):
        """Detailed metrics endpoint."""
        try:
            # Bot metrics
            guild_count = len(self.bot.guilds)
            user_count = sum(guild.member_count for guild in self.bot.guilds)
            
            # Player metrics
            if hasattr(self.bot, 'player_manager'):
                player_stats = self.bot.player_manager.get_stats()
            else:
                player_stats = {}
            
            # System metrics
            process = psutil.Process()
            memory_info = process.memory_info()
            
            metrics_data = {
                "timestamp": datetime.utcnow().isoformat(),
                "uptime": time.time() - self.start_time,
                "bot": {
                    "ready": self.bot.is_ready(),
                    "latency_ms": round(self.bot.latency * 1000, 2),
                    "guild_count": guild_count,
                    "user_count": user_count,
                    "commands_processed": self.metrics['commands_processed'],
                    "songs_played": self.metrics['songs_played'],
                    "errors_count": self.metrics['errors_count'],
                    "average_response_time": self.metrics['average_response_time']
                },
                "players": player_stats,
                "system": {
                    "cpu_percent": psutil.cpu_percent(),
                    "memory_percent": psutil.virtual_memory().percent,
                    "memory_used_mb": memory_info.rss / (1024 * 1024),
                    "memory_available_mb": psutil.virtual_memory().available / (1024 * 1024),
                    "disk_usage_percent": psutil.disk_usage('/').percent,
                    "load_average": psutil.getloadavg() if hasattr(psutil, 'getloadavg') else None
                },
                "custom_metrics": self.metrics
            }
            
            return web.json_response(metrics_data)
            
        except Exception as e:
            logger.error(f"Metrics endpoint failed: {e}")
            return web.json_response(
                {"error": str(e)}, 
                status=500
            )
    
    async def status_endpoint(self, request):
        """Bot status endpoint."""
        try:
            status_data = {
                "bot_name": "HERTZ",
                "version": "1.0.0",
                "status": str(self.bot.status) if self.bot.status else "unknown",
                "activity": str(self.bot.activity) if self.bot.activity else None,
                "guilds": len(self.bot.guilds),
                "users": sum(guild.member_count for guild in self.bot.guilds),
                "channels": sum(len(guild.channels) for guild in self.bot.guilds),
                "uptime_seconds": time.time() - self.start_time,
                "started_at": datetime.fromtimestamp(self.start_time).isoformat(),
                "python_version": platform.python_version(),
                "discord_py_version": discord.__version__,
                "platform": platform.platform()
            }
            
            return web.json_response(status_data)
            
        except Exception as e:
            logger.error(f"Status endpoint failed: {e}")
            return web.json_response(
                {"error": str(e)}, 
                status=500
            )
    
    async def guilds_endpoint(self, request):
        """Guilds information endpoint."""
        try:
            guilds_data = []
            
            for guild in self.bot.guilds:
                guild_info = {
                    "id": str(guild.id),
                    "name": guild.name,
                    "member_count": guild.member_count,
                    "channel_count": len(guild.channels),
                    "role_count": len(guild.roles),
                    "created_at": guild.created_at.isoformat(),
                    "owner_id": str(guild.owner_id) if guild.owner_id else None,
                    "region": str(guild.region) if hasattr(guild, 'region') else None,
                    "premium_tier": guild.premium_tier,
                    "premium_subscription_count": guild.premium_subscription_count or 0
                }
                
                # Add player information if available
                if hasattr(self.bot, 'player_manager'):
                    player = self.bot.player_manager.get_existing(guild.id)
                    if player:
                        guild_info["player"] = {
                            "status": player.status.value,
                            "connected": player.is_connected(),
                            "playing": player.is_playing(),
                            "queue_size": player.queue.size(),
                            "current_track": player.current_track['title'] if player.current_track else None
                        }
                
                guilds_data.append(guild_info)
            
            return web.json_response({
                "guild_count": len(guilds_data),
                "guilds": guilds_data
            })
            
        except Exception as e:
            logger.error(f"Guilds endpoint failed: {e}")
            return web.json_response(
                {"error": str(e)}, 
                status=500
            )
    
    async def info_endpoint(self, request):
        """General bot information endpoint."""
        try:
            info_data = {
                "name": "HERTZ Discord Music Bot",
                "version": "1.0.0",
                "description": "A modern Discord music bot with advanced features",
                "author": "HERTZ Development Team",
                "repository": "https://github.com/yourusername/hertz",
                "documentation": "https://hertz-bot.readthedocs.io",
                "support": "https://discord.gg/your-server",
                "features": [
                    "High-quality audio playback",
                    "YouTube and Spotify support",
                    "Advanced queue management",
                    "Playlist support",
                    "User favorites",
                    "Auto-disconnect",
                    "Volume control",
                    "Loop modes",
                    "Search functionality",
                    "Play history"
                ],
                "config": {
                    "youtube_api": self.config.has_youtube_api,
                    "spotify": self.config.has_spotify,
                    "cache_enabled": self.config.cache_enabled,
                    "auto_disconnect": self.config.auto_disconnect,
                    "max_queue_size": self.config.max_queue_size,
                    "default_volume": self.config.default_volume
                }
            }
            
            return web.json_response(info_data)
            
        except Exception as e:
            logger.error(f"Info endpoint failed: {e}")
            return web.json_response(
                {"error": str(e)}, 
                status=500
            )
    
    async def version_endpoint(self, request):
        """Version information endpoint."""
        try:
            version_data = {
                "bot_version": "1.0.0",
                "python_version": platform.python_version(),
                "discord_py_version": discord.__version__,
                "platform": platform.platform(),
                "architecture": platform.architecture()[0],
                "processor": platform.processor(),
                "build_date": "2025-01-20",  # This would be set during build
                "commit_hash": "unknown",  # This would be set during build
                "environment": "production"  # This could be configurable
            }
            
            return web.json_response(version_data)
            
        except Exception as e:
            logger.error(f"Version endpoint failed: {e}")
            return web.json_response(
                {"error": str(e)}, 
                status=500
            )
    
    # Metric tracking methods
    def record_command(self, command_name: str, response_time: float):
        """Record command execution."""
        self.metrics['commands_processed'] += 1
        self.metrics['response_times'].append(response_time)
        
        # Keep only last 100 response times
        if len(self.metrics['response_times']) > 100:
            self.metrics['response_times'] = self.metrics['response_times'][-100:]
        
        # Calculate average
        if self.metrics['response_times']:
            self.metrics['average_response_time'] = sum(self.metrics['response_times']) / len(self.metrics['response_times'])
    
    def record_song_played(self):
        """Record song play."""
        self.metrics['songs_played'] += 1
    
    def record_error(self, error_type: str, error_message: str):
        """Record error occurrence."""
        self.metrics['errors_count'] += 1
        self.metrics['last_error'] = {
            'type': error_type,
            'message': error_message,
            'timestamp': datetime.utcnow().isoformat()
        }
    
    def get_uptime(self) -> float:
        """Get bot uptime in seconds."""
        return time.time() - self.start_time
    
    def get_formatted_uptime(self) -> str:
        """Get formatted uptime string."""
        uptime = self.get_uptime()
        
        days = int(uptime // 86400)
        hours = int((uptime % 86400) // 3600)
        minutes = int((uptime % 3600) // 60)
        seconds = int(uptime % 60)
        
        if days > 0:
            return f"{days}d {hours}h {minutes}m {seconds}s"
        elif hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"