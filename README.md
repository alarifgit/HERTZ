<p align="center">
  <img src="https://i.imgur.com/nbsaNJu.png" alt="HERTZ Logo" width="250"/>
</p>

<h1 align="center">HERTZ - Discord Music Bot</h1>

<p align="center">
  A powerful, feature-rich Discord music bot for playing music from YouTube, Spotify, and other sources in your Discord server voice channels.
  <br>
  HERTZ is a Python-based rewrite of the popular <a href="https://github.com/codetheweb/muse">muse</a> bot with enhanced features and improved stability.
</p>

## Features

- **Multiple Music Sources**:
  - YouTube videos and playlists with search and autocomplete
  - Spotify tracks, albums, playlists, and artists
  - Direct HTTP stream links
  
- **Advanced Playback Controls**:
  - Seamless play/pause/resume functionality
  - Precise seeking within tracks (`/seek`, `/fseek`)
  - Track looping and queue looping (`/loop`, `/loop-queue`)
  - Dynamic volume control with automatic adjustment during voice chat
  - Skip forward/backward in queue history
  
- **Comprehensive Queue Management**:
  - Intuitive queue display with pagination
  - Shuffle, clear, and move functionality
  - Smart track insertion (next or end of queue)
  - Chapter splitting for long videos
  
- **User-Friendly Experience**:
  - Slash commands with autocomplete suggestions
  - Customizable favorites system for quick access to songs
  - Embedded song information with progress bars
  - Automatic song announcements
  - Automatic volume reduction when people speak
  
- **Server-Specific Configuration**:
  - Customizable playlist limits
  - Adjustable auto-disconnect timers
  - Default volume and queue page settings
  - Channel-specific behavior controls
  
- **Performance Optimized**:
  - Efficient file caching system
  - Smart resource management
  - Asynchronous operations for smooth playback

- **Robust Error Handling**:
  - Automatic recovery from API failures
  - Graceful handling of disconnections
  - Detailed logging for troubleshooting

- **Health Monitoring**:
  - Built-in health dashboard
  - Performance metrics tracking
  - Cache statistics and management

## Installation

### Prerequisites
- Python 3.10+
- ffmpeg
- Docker (optional, for containerized deployment)

### Docker Installation (Recommended)

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/hertz.git
   cd hertz
   ```

2. Configure environment variables in `.env` file:
   ```bash
   DISCORD_TOKEN=your_discord_bot_token
   YOUTUBE_API_KEY=your_youtube_api_key
   # Optional Spotify integration
   SPOTIFY_CLIENT_ID=your_spotify_client_id
   SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
   
   # Optional bot configuration
   BOT_STATUS=online
   BOT_ACTIVITY_TYPE=LISTENING
   BOT_ACTIVITY=music
   ```

3. Build and run with Docker:
   ```bash
   docker build -t hertz .
   docker run -d --name hertz -v ./data:/data --env-file .env hertz
   ```

### Manual Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/hertz.git
   cd hertz
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure environment variables (same as Docker setup)

4. Run the bot:
   ```bash
   python -m hertz
   ```

## Commands

HERTZ uses Discord's slash commands system. Here are the available commands:

### Music Playback

- `/play <query> [immediate] [shuffle] [split] [skip]` - Play music from YouTube, Spotify, or a direct link
  - `immediate` - Add track to the front of the queue
  - `shuffle` - Shuffle playlist items
  - `split` - Split videos into chapters
  - `skip` - Skip the currently playing track
- `/pause` - Pause the current song
- `/resume` - Resume playback
- `/skip [number]` - Skip one or more songs
- `/next` - Skip to the next song (alias for /skip)
- `/unskip` - Go back to the previous song
- `/seek <time>` - Seek to position in the current song (e.g., "1:30", "90s")
- `/fseek <time>` - Seek forward in the current song
- `/replay` - Restart the current song
- `/stop` - Stop playback, disconnect, and clear queue
- `/disconnect` - Disconnect from voice channel

### Queue Management

- `/queue [page] [page-size]` - Display the current queue
- `/clear` - Clear all songs except the current one
- `/remove [position] [range]` - Remove songs from the queue
- `/move <from> <to>` - Move song positions in the queue
- `/shuffle` - Shuffle the current queue
- `/loop` - Toggle looping the current song
- `/loop-queue` - Toggle looping the entire queue
- `/now-playing` - Show the currently playing song

### Playback Settings

- `/volume <level>` - Set playback volume (0-100)

### Favorites

- `/favorites use <name> [immediate] [shuffle] [split] [skip]` - Play a saved favorite
- `/favorites list` - List all favorites
- `/favorites create <name> <query>` - Create a new favorite
- `/favorites remove <name>` - Remove a favorite

### Configuration

- `/config get` - Show all settings
- `/config set-playlist-limit <limit>` - Set maximum tracks from playlists
- `/config set-wait-after-queue-empties <delay>` - Set time before disconnecting
- `/config set-leave-if-no-listeners <value>` - Set auto-leave when channel is empty
- `/config set-queue-add-response-hidden <value>` - Set visibility of responses
- `/config set-auto-announce-next-song <value>` - Set auto-announcements
- `/config set-default-volume <level>` - Set default volume
- `/config set-default-queue-page-size <page-size>` - Set queue page size
- `/config set-reduce-vol-when-voice <value>` - Toggle volume reduction when people speak
- `/config set-reduce-vol-when-voice-target <volume>` - Set reduced volume level

### System Commands

- `/ping` - Check if the bot is responding
- `/health` - Display bot health metrics
- `/cache` - Show cache statistics
- `/dashboard` - Interactive bot metrics dashboard

## Configuration

HERTZ can be configured with the following environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `DISCORD_TOKEN` | Discord bot token (required) | - |
| `YOUTUBE_API_KEY` | YouTube API key (required) | - |
| `SPOTIFY_CLIENT_ID` | Spotify Client ID (optional) | - |
| `SPOTIFY_CLIENT_SECRET` | Spotify Client Secret (optional) | - |
| `DATA_DIR` | Data directory for database and cache | `/data` |
| `CACHE_DIR` | Cache directory (defaults to `DATA_DIR/cache`) | - |
| `CACHE_LIMIT` | Maximum cache size | `2GB` |
| `BOT_STATUS` | Bot status | `online` |
| `BOT_ACTIVITY_TYPE` | Activity type | `LISTENING` |
| `BOT_ACTIVITY` | Activity text | `music` |
| `BOT_ACTIVITY_URL` | Activity URL (for STREAMING type) | - |

## Health Monitoring

HERTZ includes built-in health monitoring to ensure stability:

- Automatically checks bot connectivity
- Monitors voice client state consistency
- Tracks memory and CPU usage
- Implements health check file for container orchestration
- Provides `/health` and `/dashboard` commands for real-time metrics

## License

[MIT License](LICENSE)

## Credits

HERTZ is inspired by [muse](https://github.com/codetheweb/muse), a TypeScript Discord music bot.

## Contributors

- CHAOSEN3
