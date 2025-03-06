<p align="center">
  <img src="https://i.imgur.com/nbsaNJu.png" alt="HERTZ Logo" width="250"/>
</p>

<h1 align="center">HERTZ - Professional Discord Audio Broadcasting</h1>

<p align="center">
  A powerful, feature-rich Discord audio transmission system for broadcasting music from YouTube and Spotify across your Discord server voice channels.
  <br>
  HERTZ is a Python-based evolution of the popular <a href="https://github.com/codetheweb/muse">muse</a> bot with enhanced features and professional-grade audio delivery.
</p>

## 📡 Transmission Capabilities

- **Multiple Signal Sources**:
  - YouTube video and playlist transmission with search and autocomplete
  - Spotify tracks, albums, playlists, and artists integration
  - Direct HTTP stream broadcasting
  
- **Professional Playback Controls**:
  - Precision audio control with play/pause/resume functionality
  - Advanced seeking within tracks (`/seek`, `/fseek`)
  - Track looping and queue looping capabilities (`/loop`, `/loop-queue`)
  - Dynamic volume regulation with automatic adjustment during voice chat
  - Navigate forward/backward in broadcast history
  
- **Broadcast Queue Management**:
  - Intuitive playlist display with pagination
  - Shuffle, clear, and move functionality
  - Intelligent track insertion (front or end of queue)
  - Chapter segmentation for long audio content
  
- **Studio-Quality Interface**:
  - Slash commands with intelligent autocomplete suggestions
  - Frequency preset system for quick access to favorite tracks
  - Embedded track information with dynamic progress indicators
  - Automatic track announcements
  - Automatic volume reduction when people speak
  
- **Station Configuration**:
  - Customizable playlist limits
  - Adjustable auto-disconnect timers
  - Default volume and queue page settings
  - Channel-specific behavior controls
  
- **Performance Engineering**:
  - Efficient audio caching system
  - Intelligent resource allocation
  - Asynchronous operations for uninterrupted playback

- **Error Resilience**:
  - Automatic recovery from API interruptions
  - Smooth handling of connection issues
  - Comprehensive logging for troubleshooting

- **System Monitoring**:
  - Built-in diagnostics dashboard
  - Performance metrics tracking
  - Cache statistics and management

## 🛠️ Installation

### Prerequisites
- Python 3.10+
- ffmpeg
- Docker (optional, for containerized deployment)

### Docker Installation (Recommended)

1. Clone the repository:
   ```bash
   git clone https://github.com/alarifgit/hertz.git
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
   git clone https://github.com/alarifgit/hertz.git
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

## 🎛️ Command Console

HERTZ uses Discord's slash commands system. Here are the available transmission controls:

### Audio Playback

- `/play <query> [immediate] [shuffle] [split] [skip]` - Broadcast audio from YouTube, Spotify, or a direct link
  - `immediate` - Add track to the front of the queue
  - `shuffle` - Randomize playlist items
  - `split` - Segment videos into chapters
  - `skip` - Skip the currently playing track
- `/pause` - Pause the current transmission
- `/resume` - Continue playback
- `/skip [number]` - Skip one or more tracks
- `/next` - Skip to the next track (alias for /skip)
- `/unskip` - Return to the previous track
- `/seek <time>` - Navigate to position in the current track (e.g., "1:30", "90s")
- `/fseek <time>` - Seek forward in the current track
- `/replay` - Restart the current track
- `/stop` - Halt transmission, disconnect, and clear queue
- `/disconnect` - Disconnect from voice channel

### Queue Management

- `/queue [page] [page-size]` - Display the active broadcast queue
- `/clear` - Remove all tracks except the current one
- `/remove [position] [range]` - Remove specific tracks from the queue
- `/move <from> <to>` - Reposition tracks within the queue
- `/shuffle` - Randomize the current queue
- `/loop` - Toggle repeating the current track
- `/loop-queue` - Toggle repeating the entire queue
- `/now-playing` - Display the currently broadcasting track

### Audio Settings

- `/volume <level>` - Adjust broadcast volume (0-100)

### Frequency Presets

- `/favorites use <name> [immediate] [shuffle] [split] [skip]` - Load a saved frequency preset
- `/favorites list` - Show all available presets
- `/favorites create <name> <query>` - Save a new frequency preset
- `/favorites remove <name>` - Delete a preset

### Configuration

- `/config get` - Display all settings
- `/config set-playlist-limit <limit>` - Set maximum tracks from playlists
- `/config set-wait-after-queue-empties <delay>` - Set time before auto-disconnecting
- `/config set-leave-if-no-listeners <value>` - Configure behavior when channel is empty
- `/config set-queue-add-response-hidden <value>` - Set visibility of responses
- `/config set-auto-announce-next-song <value>` - Configure auto-announcements
- `/config set-default-volume <level>` - Set default volume level
- `/config set-default-queue-page-size <page-size>` - Set queue page size
- `/config set-reduce-vol-when-voice <value>` - Configure volume reduction when people speak
- `/config set-reduce-vol-when-voice-target <volume>` - Set voice priority reduced volume level

### System Commands

- `/ping` - Verify signal connection status
- `/health` - Display system diagnostic metrics
- `/cache` - View cache statistics
- `/dashboard` - Interactive station metrics dashboard

## ⚙️ Configuration

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

## 📊 System Monitoring

HERTZ includes built-in diagnostic tools to ensure reliable operation:

- Automatically monitors connection stability
- Tracks voice client state consistency
- Monitors resource utilization
- Implements health checks for container orchestration
- Provides `/health` and `/dashboard` commands for real-time metrics

## 📝 License

[MIT License](LICENSE)

## 🎧 Credits

HERTZ is inspired by [muse](https://github.com/codetheweb/muse), a TypeScript Discord music bot.

## 🔧 Contributors

- CHAOSEN3
