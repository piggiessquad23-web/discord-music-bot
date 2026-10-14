import os
import asyncio
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import discord
from discord.ext import commands
import yt_dlp


# =========================================================
# CONFIG
# =========================================================

TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN environment variable is missing.")


# =========================================================
# RENDER HEALTH SERVER
# =========================================================

PORT = int(os.getenv("PORT", "8080"))


class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Discord Music Bot is running!")

    def log_message(self, format, *args):
        return


def start_health_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    server.serve_forever()


threading.Thread(
    target=start_health_server,
    daemon=True
).start()


# =========================================================
# DISCORD SETUP
# =========================================================

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# =========================================================
# YT-DLP CONFIG
# =========================================================

ytdl_options = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
    "cachedir": False,

    "extractor_args": {
        "youtube": {
            "player_client": [
                "android",
                "web"
            ]
        }
    },

    "http_headers": {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Linux; Android 12) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/140.0 Mobile Safari/537.36"
        )
    }
}


# ---------------------------------------------------------
# COOKIES
# ---------------------------------------------------------

COOKIE_FILE = "cookies.txt"

if os.path.exists(COOKIE_FILE):
    ytdl_options["cookiefile"] = COOKIE_FILE
    print("🍪 cookies.txt detected")
else:
    print("ℹ️ cookies.txt not found - continuing without cookies")


ytdl = yt_dlp.YoutubeDL(ytdl_options)


# =========================================================
# FFMPEG
# =========================================================

FFMPEG_OPTIONS = {
    "before_options": (
        "-reconnect 1 "
        "-reconnect_streamed 1 "
        "-reconnect_delay_max 5 "
        "-nostdin"
    ),
    "options": (
        "-vn "
        "-loglevel warning"
    )
}


# =========================================================
# MUSIC DATA
# =========================================================

guild_queues = {}
guild_now_playing = {}
guild_text_channels = {}


def get_queue(guild_id):

    if guild_id not in guild_queues:
        guild_queues[guild_id] = []

    return guild_queues[guild_id]


# =========================================================
# YOUTUBE EXTRACTION
# =========================================================

async def extract_youtube(query):

    loop = asyncio.get_running_loop()

    def extract():

        try:

            if query.startswith(
                (
                    "https://youtube.com/",
                    "https://www.youtube.com/",
                    "http://youtube.com/",
                    "http://www.youtube.com/",
                    "https://youtu.be/",
                    "http://youtu.be/"
                )
            ):

                search_query = query

            else:

                search_query = f"ytsearch1:{query}"

            info = ytdl.extract_info(
                search_query,
                download=False
            )

            if not info:
                return None

            if "entries" in info:

                entries = info.get("entries")

                if not entries:
                    return None

                info = entries[0]

            if not info:
                return None

            webpage_url = info.get("webpage_url")

            if not webpage_url:

                video_id = info.get("id")

                if video_id:
                    webpage_url = (
                        f"https://www.youtube.com/watch?v={video_id}"
                    )

            return {
                "title": info.get(
                    "title",
                    "Unknown Title"
                ),
                "url": webpage_url,
                "duration": info.get(
                    "duration",
                    0
                ),
                "thumbnail": info.get(
                    "thumbnail"
                )
            }

        except Exception as e:

            print(
                f"❌ YouTube extraction error: {e}"
            )

            return None

    return await loop.run_in_executor(
        None,
        extract
    )


# =========================================================
# STREAM EXTRACTION
# =========================================================

async def get_audio_url(webpage_url):

    loop = asyncio.get_running_loop()

    def extract_stream():

        try:

            info = ytdl.extract_info(
                webpage_url,
                download=False
            )

            if not info:
                return None

            if "entries" in info:

                entries = info.get("entries")

                if not entries:
                    return None

                info = entries[0]

            stream_url = info.get("url")

            if not stream_url:
                return None

            return stream_url

        except Exception as e:

            print(
                f"❌ Stream extraction error: {e}"
            )

            return None

    return await loop.run_in_executor(
        None,
        extract_stream
    )


# =========================================================
# EMBED
# =========================================================

def make_now_playing_embed(song):

    embed = discord.Embed(
        title="🎵 Now Playing",
        description=f"**{song['title']}**",
        color=discord.Color.blurple()
    )

    if song.get("thumbnail"):
        embed.set_thumbnail(
            url=song["thumbnail"]
        )

    return embed


# =========================================================
# PLAY NEXT
# =========================================================

async def play_next(guild):

    guild_id = guild.id
    queue = get_queue(guild_id)

    voice = guild.voice_client

    if not voice:
        guild_now_playing.pop(
            guild_id,
            None
        )
        return

    if not queue:

        guild_now_playing.pop(
            guild_id,
            None
        )

        try:

            await voice.disconnect()

        except Exception:
            pass

        return

    song = queue.pop(0)

    guild_now_playing[guild_id] = song

    text_channel = guild_text_channels.get(
        guild_id
    )

    try:

        stream_url = await get_audio_url(
            song["url"]
        )

        if not stream_url:

            if text_channel:
                await text_channel.send(
                    "❌ He song stream URL ka hmuh thei lo."
                )

            await play_next(guild)
            return

        source = discord.FFmpegPCMAudio(
            stream_url,
            **FFMPEG_OPTIONS
        )

        def after_play(error):

            if error:
                print(
                    f"FFmpeg error: {error}"
                )

            future = asyncio.run_coroutine_threadsafe(
                play_next(guild),
                bot.loop
            )

            try:
                future.result()
            except Exception as e:
                print(
                    f"❌ Next song error: {e}"
                )

        voice.play(
            source,
            after=after_play
        )

        if text_channel:

            await text_channel.send(
                embed=make_now_playing_embed(song)
            )

    except Exception as e:

        print(
            f"❌ Playback error: {e}"
        )

        if text_channel:

            await text_channel.send(
                f"❌ Playback error: `{e}`"
            )

        await play_next(guild)


# =========================================================
# CONNECT VOICE
# =========================================================

async def connect_to_voice(ctx):

    if not ctx.author.voice:

        await ctx.send(
            "❌ Voice channel-ah lut lo.",
            ephemeral=True
        )

        return None

    channel = ctx.author.voice.channel

    voice = ctx.guild.voice_client

    try:

        if voice:

            if voice.channel != channel:

                await voice.move_to(channel)

        else:

            voice = await channel.connect()

        return voice

    except Exception as e:

        await ctx.send(
            f"❌ Voice connect error: `{e}`"
        )

        return None


# =========================================================
# PLAY COMMAND
# =========================================================

@bot.command(name="play")
async def play(ctx, *, query=None):

    if not query:

        await ctx.send(
            "❌ Example: `!play Alan Walker Faded`"
        )

        return

    voice = await connect_to_voice(ctx)

    if not voice:
        return

    guild_id = ctx.guild.id

    guild_text_channels[guild_id] = ctx.channel

    msg = await ctx.send(
        "🔎 YouTube-ah ka zawng mek..."
    )

    song = await extract_youtube(query)

    if not song:

        await msg.edit(
            content=(
                "❌ YouTube song hi ka hmuh thei lo.\n"
                "Link dik emaw song name dik zawk hmang rawh."
            )
        )

        return

    queue = get_queue(guild_id)

    queue.append(song)

    if voice.is_playing() or voice.is_paused():

        await msg.edit(
            content=(
                f"✅ Queue-ah dah tawh.\n"
                f"🎵 **{song['title']}**\n"
                f"📌 Queue: `{len(queue)}`"
            )
        )

    else:

        await msg.delete()

        await play_next(ctx.guild)


# =========================================================
# SKIP
# =========================================================

@bot.command(name="skip")
async def skip(ctx):

    voice = ctx.guild.voice_client

    if not voice:

        await ctx.send(
            "❌ Voice channel-ah ka awm lo."
        )

        return

    if not voice.is_playing():

        await ctx.send(
            "❌ Song play mek a awm lo."
        )

        return

    voice.stop()

    await ctx.send(
        "⏭️ Song skip a ni."
    )


# =========================================================
# PAUSE
# =========================================================

@bot.command(name="pause")
async def pause(ctx):

    voice = ctx.guild.voice_client

    if not voice:

        await ctx.send(
            "❌ Bot voice channel-ah a awm lo."
        )

        return

    if voice.is_playing():

        voice.pause()

        await ctx.send(
            "⏸️ Paused."
        )

    else:

        await ctx.send(
            "❌ Song play mek a awm lo."
        )


# =========================================================
# RESUME
# =========================================================

@bot.command(name="resume")
async def resume(ctx):

    voice = ctx.guild.voice_client

    if not voice:

        await ctx.send(
            "❌ Bot voice channel-ah a awm lo."
        )

        return

    if voice.is_paused():

        voice.resume()

        await ctx.send(
            "▶️ Resumed."
        )

    else:

        await ctx.send(
            "❌ Song pause a ni lo."
        )


# =========================================================
# STOP
# =========================================================

@bot.command(name="stop")
async def stop(ctx):

    voice = ctx.guild.voice_client

    if not voice:

        await ctx.send(
            "❌ Bot voice channel-ah a awm lo."
        )

        return

    queue = get_queue(
        ctx.guild.id
    )

    queue.clear()

    guild_now_playing.pop(
        ctx.guild.id,
        None
    )

    if voice.is_playing() or voice.is_paused():

        voice.stop()

    await ctx.send(
        "⏹️ Playback stopped leh queue clear."
    )


# =========================================================
# LEAVE
# =========================================================

@bot.command(name="leave")
async def leave(ctx):

    voice = ctx.guild.voice_client

    if not voice:

        await ctx.send(
            "❌ Bot voice channel-ah a awm lo."
        )

        return

    queue = get_queue(
        ctx.guild.id
    )

    queue.clear()

    guild_now_playing.pop(
        ctx.guild.id,
        None
    )

    await voice.disconnect()

    await ctx.send(
        "👋 Voice channel ka chhuak."
    )


# =========================================================
# QUEUE
# =========================================================

@bot.command(name="queue")
async def show_queue(ctx):

    queue = get_queue(
        ctx.guild.id
    )

    current = guild_now_playing.get(
        ctx.guild.id
    )

    embed = discord.Embed(
        title="🎶 Music Queue",
        color=discord.Color.blurple()
    )

    if current:

        embed.add_field(
            name="▶️ Now Playing",
            value=current["title"],
            inline=False
        )

    if queue:

        text = ""

        for index, song in enumerate(
            queue[:10],
            start=1
        ):

            text += (
                f"`{index}.` "
                f"{song['title']}\n"
            )

        embed.add_field(
            name="📋 Up Next",
            value=text,
            inline=False
        )

        if len(queue) > 10:

            embed.set_footer(
                text=(
                    f"+ {len(queue) - 10} more songs"
                )
            )

    else:

        embed.add_field(
            name="📋 Up Next",
            value="Queue empty.",
            inline=False
        )

    await ctx.send(
        embed=embed
    )


# =========================================================
# NOW PLAYING
# =========================================================

@bot.command(name="np")
async def now_playing(ctx):

    song = guild_now_playing.get(
        ctx.guild.id
    )

    if not song:

        await ctx.send(
            "❌ Song play mek a awm lo."
        )

        return

    await ctx.send(
        embed=make_now_playing_embed(song)
    )


# =========================================================
# CONTROL PANEL
# =========================================================

class MusicControlView(discord.ui.View):

    def __init__(self):

        super().__init__(
            timeout=None
        )


    @discord.ui.button(
        label="Pause",
        emoji="⏸️",
        style=discord.ButtonStyle.primary,
        custom_id="music_pause"
    )
    async def pause_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        voice = interaction.guild.voice_client

        if not voice:

            await interaction.response.send_message(
                "❌ Bot voice channel-ah a awm lo.",
                ephemeral=True
            )

            return

        if voice.is_playing():

            voice.pause()

            await interaction.response.send_message(
                "⏸️ Paused.",
                ephemeral=True
            )

        else:

            await interaction.response.send_message(
                "❌ Song play mek a awm lo.",
                ephemeral=True
            )


    @discord.ui.button(
        label="Resume",
        emoji="▶️",
        style=discord.ButtonStyle.success,
        custom_id="music_resume"
    )
    async def resume_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        voice = interaction.guild.voice_client

        if not voice
