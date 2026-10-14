import discord
from discord.ext import commands
from discord.ui import View, button, Button, Modal, TextInput

import yt_dlp
import asyncio
import json
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import static_ffmpeg

# =========================================================
# FFmpeg
# =========================================================

try:
    static_ffmpeg.add_paths()
except Exception as e:
    print(f"FFmpeg setup warning: {e}")


# =========================================================
# RENDER HEALTH CHECK SERVER
# =========================================================

class HealthCheckHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Music bot is online and healthy!")

    def log_message(self, format, *args):
        pass


def run_web_server():
    try:
        port = int(os.environ.get("PORT", 8080))
        server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)

        print(f"Health server running on port {port}")

        server.serve_forever()

    except Exception as e:
        print(f"Health server error: {e}")


threading.Thread(
    target=run_web_server,
    daemon=True
).start()


# =========================================================
# DISCORD BOT
# =========================================================

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# =========================================================
# YOUTUBE / YT-DLP
# =========================================================

ytdl_format_options = {
    # Audio only
    "format": "bestaudio/best",

    "noplaylist": True,

    "quiet": True,
    "no_warnings": True,

    "source_address": "0.0.0.0",

    # Cookies support
    # cookies.txt awm loh pawhin bot chu run thei
    "cookiefile": "cookies.txt",

    # YouTube clients
    "extractor_args": {
        "youtube": {
            "player_client": [
                "android",
                "web"
            ]
        }
    },

    # Avoid unnecessary cache
    "cachedir": False,
}


ffmpeg_options = {
    "before_options":
        "-reconnect 1 "
        "-reconnect_streamed 1 "
        "-reconnect_delay_max 5",

    "options":
        "-vn"
}


ytdl = yt_dlp.YoutubeDL(ytdl_format_options)


# =========================================================
# GLOBAL MUSIC DATA
# =========================================================

song_queues = {}
current_songs = {}

PLAYLIST_FILE = "playlists.json"


# =========================================================
# QUEUE
# =========================================================

def get_queue(guild_id):

    if guild_id not in song_queues:
        song_queues[guild_id] = []

    return song_queues[guild_id]


# =========================================================
# PLAYLIST FILE
# =========================================================

def load_saved_playlists():

    if not os.path.exists(PLAYLIST_FILE):
        return {}

    try:
        with open(
            PLAYLIST_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)

    except Exception as e:

        print(f"Playlist load error: {e}")
        return {}


def save_playlists_to_file(data):

    try:

        with open(
            PLAYLIST_FILE,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                data,
                f,
                indent=4,
                ensure_ascii=False
            )

    except Exception as e:

        print(f"Playlist save error: {e}")


# =========================================================
# ADD SONG TO PLAYLIST
# =========================================================

def add_song_to_playlist(
    guild_id,
    playlist_name,
    song_title
):

    playlists = load_saved_playlists()

    gid = str(guild_id)

    if gid not in playlists:
        playlists[gid] = {}

    playlist_name = playlist_name.lower().strip()

    if playlist_name not in playlists[gid]:
        playlists[gid][playlist_name] = []

    if song_title not in playlists[gid][playlist_name]:

        playlists[gid][playlist_name].append(song_title)

        save_playlists_to_file(playlists)

        return True

    return False


# =========================================================
# CACHE CLEANUP
# =========================================================

def cleanup_cache():

    for filename in os.listdir("."):

        if (
            filename.startswith("song_cache.")
            or filename.endswith(".webm")
            or filename.endswith(".m4a")
            or filename.endswith(".mp3")
            or filename.endswith(".opus")
        ):

            try:
                os.remove(filename)

            except Exception:
                pass


# =========================================================
# YOUTUBE SEARCH
# =========================================================

def get_youtube_info(query):

    try:

        # Direct URL
        if query.startswith(
            ("http://", "https://")
        ):

            return ytdl.extract_info(
                query,
                download=False
            )

        # YouTube search
        search_query = f"ytsearch1:{query}"

        return ytdl.extract_info(
            search_query,
            download=False
        )

    except Exception as e:

        print(f"YouTube search error: {e}")
        raise


# =========================================================
# PLAY NEXT SONG
# =========================================================

def play_next(ctx):

    queue = get_queue(ctx.guild.id)

    vc = ctx.voice_client

    if not queue or not vc:

        current_songs.pop(
            ctx.guild.id,
            None
        )

        return

    next_song = queue.pop(0)

    current_songs[
        ctx.guild.id
    ] = next_song["title"]

    try:

        cleanup_cache()

        print(
            f"Downloading: {next_song['title']}"
        )

        info = ytdl.extract_info(
            next_song["url"],
            download=True
        )

        if "entries" in info:

            entries = info.get(
                "entries",
                []
            )

            if entries:
                info = entries[0]

        filename = ytdl.prepare_filename(
            info
        )

        print(
            f"Playing file: {filename}"
        )

        source = discord.FFmpegPCMAudio(
            filename,
            **ffmpeg_options
        )

        def after_play(error):

            if error:
                print(
                    f"FFmpeg playback error: {error}"
                )

            # Next song
            if bot.loop:

                bot.loop.call_soon_threadsafe(
                    play_next,
                    ctx
                )

        vc.play(
            source,
            after=after_play
        )

        panel = MusicControlPanel(ctx)

        asyncio.run_coroutine_threadsafe(
            ctx.send(
                f"🎵 **Tunah ka play mek:** "
                f"{next_song['title']}",
                view=panel
            ),
            bot.loop
        )

    except Exception as e:

        print(
            f"play_next error: {e}"
        )

        # Try next song
        if queue:

            play_next(ctx)

        else:

            current_songs.pop(
                ctx.guild.id,
                None
            )


# =========================================================
# PLAYLIST MODAL
# =========================================================

class AddToPlaylistModal(
    Modal,
    title="Playlist-ah Dahna"
):

    playlist_input = TextInput(
        label="Playlist Hming",
        placeholder="myfav, chill, zofolk",
        required=True,
        max_length=30
    )

    def __init__(self, song_title):

        super().__init__()

        self.song_title = song_title

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

        playlist_name = (
            self.playlist_input.value
            .strip()
        )

        added = add_song_to_playlist(
            interaction.guild.id,
            playlist_name,
            self.song_title
        )

        if added:

            await interaction.response.send_message(
                f"✅ **{self.song_title}** "
                f"chu Playlist "
                f"**{playlist_name}**-ah dah a ni!",
                ephemeral=True
            )

        else:

            await interaction.response.send_message(
                f"ℹ️ Chu hla chu Playlist "
                f"**{playlist_name}**-ah "
                f"a awm sa reng.",
                ephemeral=True
            )


# =========================================================
# MUSIC CONTROL PANEL
# =========================================================

class MusicControlPanel(View):

    def __init__(self, ctx):

        super().__init__(
            timeout=None
        )

        self.ctx = ctx


    # -----------------------------------------------------
    # PAUSE
    # -----------------------------------------------------

    @button(
        label="Pause",
        style=discord.ButtonStyle.secondary,
        emoji="⏸️",
        row=0
    )
    async def pause_button(
        self,
        interaction: discord.Interaction,
        btn: Button
    ):

        vc = interaction.guild.voice_client

        if vc and vc.is_playing():

            vc.pause()

            await interaction.response.send_message(
                "⏸️ Hla pause a ni e.",
                ephemeral=True
            )

        else:

            await interaction.response.send_message(
                "Hla play mek a awm lo.",
                ephemeral=True
            )


    # -----------------------------------------------------
    # RESUME
    # -----------------------------------------------------

    @button(
        label="Resume",
        style=discord.ButtonStyle.success,
        emoji="▶️",
        row=0
    )
    async def resume_button(
        self,
        interaction: discord.Interaction,
        btn: Button
    ):

        vc = interaction.guild.voice_client

        if vc and vc.is_paused():

            vc.resume()

            await interaction.response.send_message(
                "▶️ Hla play chhunzawm a ni e.",
                ephemeral=True
            )

        else:

            await interaction.response.send_message(
                "Hla pause lai a awm lo.",
                ephemeral=True
            )


    # -----------------------------------------------------
    # SKIP
    # -----------------------------------------------------

    @button(
        label="Skip",
        style=discord.ButtonStyle.primary,
        emoji="⏭️",
        row=0
    )
    async def skip_button(
        self,
        interaction: discord.Interaction,
        btn: Button
    ):

        vc = interaction.guild.voice_client

        if vc and (
            vc.is_playing()
            or vc.is_paused()
        ):

            vc.stop()

            await interaction.response.send_message(
                "⏭️ A dawt chu play ang e!",
                ephemeral=True
            )

        else:

            await interaction.response.send_message(
                "Hla skip tur a awm lo.",
                ephemeral=True
            )


    # -----------------------------------------------------
    # STOP
    # -----------------------------------------------------

    @button(
        label="Stop",
        style=discord.ButtonStyle.danger,
        emoji="⏹️",
        row=0
    )
    async def stop_button(
        self,
        interaction: discord.Interaction,
        btn: Button
    ):

        get_queue(
            interaction.guild.id
        ).clear()

        vc = interaction.guild.voice_client

        if vc:

            if vc.is_playing() or vc.is_paused():

                vc.stop()

            current_songs.pop(
                interaction.guild.id,
                None
            )

            await interaction.response.send_message(
                "⏹️ Hla leh queue tih tawp a ni e.",
                ephemeral=True
            )

        else:

            await interaction.response.send_message(
                "Voice channel-ah ka awm lo.",
                ephemeral=True
            )


    # -----------------------------------------------------
    # SAVE
    # -----------------------------------------------------

    @button(
        label="Save",
        style=discord.ButtonStyle.success,
        emoji="💾",
        row=1
    )
    async def save_button(
        self,
        interaction: discord.Interaction,
        btn: Button
    ):

        song = current_songs.get(
            interaction.guild.id
        )

        if not song:

            await interaction.response.send_message(
                "Hla play mek a awm lo.",
                ephemeral=True
            )

            return

        await interaction.response.send_modal(
            AddToPlaylistModal(song)
        )


    # -----------------------------------------------------
    # PLAYLISTS
    # -----------------------------------------------------

    @button(
        label="Playlists",
        style=discord.ButtonStyle.primary,
        emoji="📂",
        row=1
    )
    async def playlists_button(
        self,
        interaction: discord.Interaction,
        btn: Button
    ):

        playlists = load_saved_playlists()

        gid = str(
            interaction.guild.id
        )

        if (
            gid not in playlists
            or not playlists[gid]
        ):

            await interaction.response.send_message(
                "📂 Playlist save a la awm lo. "
                "**💾 Save** button hmetin save rawh.",
                ephemeral=True
            )

            return

        msg = "📂 **I Playlist-te:**\n\n"

        for name, songs in playlists[gid].items():

            msg += (
                f"• **{name}** "
                f"({len(songs)} songs)\n"
            )

        await interaction.response.send_message(
            msg,
            ephemeral=True
        )


    # -----------------------------------------------------
    # QUEUE
    # -----------------------------------------------------

    @button(
        label="Queue",
        style=discord.ButtonStyle.secondary,
        emoji="📋",
        row=1
    )
    async def queue_button(
        self,
        interaction: discord.Interaction,
        btn: Button
    ):

        queue = get_queue(
            interaction.guild.id
        )

        current = current_songs.get(
            interaction.guild.id,
            "Awm lo"
        )

        msg = (
            f"🎵 **Play mek:** {current}\n\n"
            f"📋 **Queue:**\n"
        )

        if not queue:

            msg += "Queue-ah hla awm lo."

        else:

            for i, song in enumerate(
                queue[:10],
                start=1
            ):

                msg += (
                    f"{i}. "
                    f"{song['title']}\n"
                )

        await interaction.response.send_message(
            msg,
            ephemeral=True
        )


    # -----------------------------------------------------
    # LEAVE
    # -----------------------------------------------------

    @button(
        label="Leave",
        style=discord.ButtonStyle.secondary,
        emoji="👋",
        row=1
    )
    async def leave_button(
        self,
        interaction: discord.Interaction,
        btn: Button
    ):

        get_queue(
            interaction.guild.id
        ).clear()

        current_songs.pop(
            interaction.guild.id,
            None
        )

        vc = interaction.guild.voice_client

        if vc:

            await vc.disconnect()

            await interaction.response.send_message(
                "👋 Ka chhuak ta e!",
                ephemeral=True
            )

        else:

            await interaction.response.send_message(
                "Voice channel-ah ka awm lo.",
                ephemeral=True
            )


# =========================================================
# BOT READY
# =========================================================

@bot.event
async def on_ready():

    print(
        f"✅ Bot a inpeih fel ta e: "
        f"{bot.user}"
    )


# =========================================================
# JOIN
# =========================================================

@bot.command()
async def join(ctx):

    if not ctx.author.voice:

        await ctx.send(
            "Voice channel-ah lut hmasa phawt rawh!"
        )

        return

    channel = ctx.author.voice.channel

    try:

        if ctx.voice_client:

            await ctx.voice_client.move_to(
                channel
            )

        else:

            await channel.connect()

        await ctx.send(
            f"🔊 **{channel.name}**-ah ka lo lut e!"
        )

    except Exception as e:

        await ctx.send(
            f"❌ Join error: {e}"
        )


# =========================================================
# LEAVE COMMAND
# =========================================================

@bot.command()
async def leave(ctx):

    get_queue(
        ctx.guild.id
    ).clear()

    current_songs.pop(
        ctx.guild.id,
        None
    )

    if ctx.voice_client:

        await ctx.voice_client.disconnect()

        await ctx.send(
            "👋 Ka chhuak ta e!"
        )

    else:

        await ctx.send(
            "Voice channel-ah ka awm lo."
        )


# =========================================================
# PLAY COMMAND
# =========================================================

@bot.command()
async def play(
    ctx,
    *,
    search
):

    if not ctx.author.voice:

        await ctx.send(
            "Voice channel-ah lut hmasa phawt rawh!"
        )

        return


    # Connect
    if not ctx.voice_client:

        try:

            await ctx.author.voice.channel.connect()

        except Exception as e:

            await ctx.send(
                f"❌ Voice connect error: {e}"
            )

            return


    async with ctx.typing():

        try:

            loop = asyncio.get_running_loop()


            # ---------------------------------------------
            # YouTube search / URL
            # ---------------------------------------------

            data = await loop.run_in_executor(
                None,
                lambda: get_youtube_info(search)
            )


            # ---------------------------------------------
            # Get first result
            # ---------------------------------------------

            if "entries" in data:

                entries = [
                    e for e in data["entries"]
                    if e
                ]

                if not entries:

                    await ctx.send(
                        "❌ Hla zawng chhuah theih a ni lo."
                    )

                    return

                entry = entries[0]

            else:

                entry = data


            title = entry.get(
                "title",
                "Unknown Song"
            )

            url = entry.get(
                "webpage_url"
            )


            if not url:

                url = entry.get(
                    "original_url"
                )


            if not url:

                await ctx.send(
                    "❌ YouTube URL hmuhtheih a ni lo."
                )

                return


            # ---------------------------------------------
            # Queue
            # ---------------------------------------------

            queue = ge
