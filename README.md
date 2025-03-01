# HERTZ - Discord Music Bot

A feature-rich Discord music bot for playing music from YouTube, Spotify, and other sources in your Discord server voice channels.

![HERTZ Logo](https://via.placeholder.com/150?text=HERTZ)

## Features

- **Multiple Music Sources**:
  - YouTube videos and playlists
  - Spotify tracks, albums, playlists, and artists
  - Direct HTTP stream links
  
- **Advanced Playback Controls**:
  - Play/pause/resume/skip/previous track controls
  - Queue management with shuffle and loop
  - Volume adjustment
  - Seeking within tracks
  - Automatic disconnection when voice channel is empty
  
- **User-Friendly Commands**:
  - Intuitive slash commands
  - Autocomplete for search queries
  - Playlist management
  - User favorites system
  
- **Performance Optimized**:
  - Song caching for faster playback
  - Smart resource management
  - Stable playback experience

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

- `/play <query>` - Play music from YouTube, Spotify, or direct link
  - Options: `immediate`, `shuffle`, `split`, `skip`
- `/pause` - Pause the current song
- `/resume` - Resume playback
- `/skip [number]` - Skip one or more songs
- `/next` - Skip to the next song (alias for /skip)
- `/unskip` - Go back to the previous song
- `/seek <time>` - Seek to position in the current song
- `/fseek <time>` - Seek forward in the current song
- `/replay` - Restart the current song
- `/stop` - Stop playback and clear queue
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

- `/favorites use <name>` - Play a saved favorite
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
- `/config set-reduce-vol-when-voice <value>` - Toggle volume reduction
- `/config set-reduce-vol-when-voice-target <volume>` - Set reduced volume level

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

## License

[MIT License](LICENSE)

## Credits

HERTZ is inspired by [Muse](https://github.com/codetheweb/muse), a TypeScript Discord music bot.

## Contributors

- CHAOSEN3
