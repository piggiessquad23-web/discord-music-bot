import discord
from discord.ext import commands
from discord.ui import View, button, Button, Modal, TextInput
import yt_dlp
import asyncio
import json
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# 1. Render Web Service health-check bypass
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is online and healthy!")

    def log_message(self, format, *args):
        pass

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

threading.Thread(target=run_web_server, daemon=True).start()

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# 2. Cloud Server (Render IP) block pumpelhna iOS/TV client settings
ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': 'song_cache.%(ext)s',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch1',
    'source_address': '0.0.0.0',
    'extractor_args': {
        'youtube': {
            'player_client': ['ios', 'tvhtml5'],
            'skip': ['dash', 'hls']
        }
    }
}

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

song_queues = {}
current_songs = {}
PLAYLIST_FILE = "playlists.json"

def load_saved_playlists():
    if os.path.exists(PLAYLIST_FILE):
        try:
            with open(PLAYLIST_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_playlists_to_file(data):
    with open(PLAYLIST_FILE, "w") as f:
        json.dump(data, f, indent=4)

def get_queue(guild_id):
    if guild_id not in song_queues:
        song_queues[guild_id] = []
    return song_queues[guild_id]

def add_song_to_pl(guild_id, pl_name, song_title):
    playlists = load_saved_playlists()
    gid = str(guild_id)
    if gid not in playlists:
        playlists[gid] = {}
    p_name = pl_name.lower().strip()
    if p_name not in playlists[gid]:
        playlists[gid][p_name] = []

    if song_title not in playlists[gid][p_name]:
        playlists[gid][p_name].append(song_title)
        save_playlists_to_file(playlists)
        return True
    return False

class AddToPlaylistModal(Modal, title="Playlist-ah Dahna"):
    pl_input = TextInput(
        label="Playlist Hming",
        placeholder="Entirnan: myfav, zofolk",
        required=True,
        max_length=30
    )

    def __init__(self, current_song_title):
        super().__init__()
        self.song_title = current_song_title

    async def on_submit(self, interaction: discord.Interaction):
        p_name = self.pl_input.value.strip()
        added = add_song_to_pl(interaction.guild.id, p_name, self.song_title)
        if added:
            await interaction.response.send_message(f"✅ **{self.song_title}** chu Playlist **{p_name}**-ah dah a ni e!", ephemeral=True)
        else:
            await interaction.response.send_message(f"ℹ️ Chu hla chu Playlist **{p_name}**-ah a awm sa tawh reng mai.", ephemeral=True)

def cleanup_cache():
    for f in os.listdir("."):
        if f.startswith("song_cache."):
            try:
                os.remove(f)
            except Exception:
                pass

def play_next(ctx):
    queue = get_queue(ctx.guild.id)
    if queue and ctx.voice_client:
        next_song = queue.pop(0)
        current_songs[ctx.guild.id] = next_song['title']
        try:
            cleanup_cache()
            info = ytdl.extract_info(next_song['search_url'], download=True)
            if 'entries' in info and info['entries']:
                info = info['entries'][0]
            filename = ytdl.prepare_filename(info)

            source = discord.FFmpegPCMAudio(filename, **ffmpeg_options)
            ctx.voice_client.play(source, after=lambda e: play_next(ctx))

            panel_view = MusicControlPanel(ctx)
            asyncio.run_coroutine_threadsafe(
                ctx.send(f"🎵 **Tunah ka play mek:** {next_song['title']}", view=panel_view),
                bot.loop
            )
        except Exception as e:
            print(f"Error in play_next: {e}")
            play_next(ctx)
    else:
        current_songs.pop(ctx.guild.id, None)
        cleanup_cache()

class MusicControlPanel(View):
    def __init__(self, ctx):
        super().__init__(timeout=None)
        self.ctx = ctx

    @button(label="Pause", style=discord.ButtonStyle.secondary, emoji="⏸️", row=0)
    async def pause_button(self, interaction: discord.Interaction, btn: Button):
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.pause()
            await interaction.response.send_message("⏸️ Hla pause a ni e.", ephemeral=True)
        else:
            await interaction.response.send_message("Hla play mek a awm lo.", ephemeral=True)

    @button(label="Resume", style=discord.ButtonStyle.success, emoji="▶️", row=0)
    async def resume_button(self, interaction: discord.Interaction, btn: Button):
        vc = interaction.guild.voice_client
        if vc and vc.is_paused():
            vc.resume()
            await interaction.response.send_message("▶️ Hla play chhunzawm a ni e.", ephemeral=True)
        else:
            await interaction.response.send_message("Hla pause lai a awm lo.", ephemeral=True)

    @button(label="Skip", style=discord.ButtonStyle.primary, emoji="⏭️", row=0)
    async def skip_button(self, interaction: discord.Interaction, btn: Button):
        vc = interaction.guild.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()
            await interaction.response.send_message("⏭️ A dawt ami kan play ang e!", ephemeral=True)
        else:
            await interaction.response.send_message("Hla skip tur a awm lo.", ephemeral=True)

    @button(label="Stop", style=discord.ButtonStyle.danger, emoji="⏹️", row=0)
    async def stop_button(self, interaction: discord.Interaction, btn: Button):
        vc = interaction.guild.voice_client
        get_queue(interaction.guild.id).clear()
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()
            await interaction.response.send_message("⏹️ Hla leh queue tih tawp a ni e.", ephemeral=True)
        else:
            await interaction.response.send_message("Hla play mek a awm lo.", ephemeral=True)

    @button(label="Save to Playlist", style=discord.ButtonStyle.green, emoji="💾", row=1)
    async def save_to_playlist_button(self, interaction: discord.Interaction, btn: Button):
        song = current_songs.get(interaction.guild.id)
        if not song:
            await interaction.response.send_message("Hla play mek a awm lo.", ephemeral=True)
            return
        await interaction.response.send_modal(AddToPlaylistModal(song))

    @button(label="Queue", style=discord.ButtonStyle.secondary, emoji="📋", row=1)
    async def queue_button(self, interaction: discord.Interaction, btn: Button):
        q = get_queue(interaction.guild.id)
        curr = current_songs.get(interaction.guild.id, "Awm lo")
        msg = f"🎶 **Play mek:** {curr}\n\n**📋 Queue:**\n"
        if not q:
            msg += "Hla dang dah a la awm lo."
        else:
            for i, s in enumerate(q[:10], start=1):
                msg += f"{i}. {s['title']}\n"
        await interaction.response.send_message(msg, ephemeral=True)

    @button(label="Leave", style=discord.ButtonStyle.gray, emoji="👋", row=1)
    async def leave_button(self, interaction: discord.Interaction, btn: Button):
        vc = interaction.guild.voice_client
        get_queue(interaction.guild.id).clear()
        if vc:
            await vc.disconnect()
            await interaction.response.send_message("👋 Ka chhuak ta e!", ephemeral=True)
        else:
            await interaction.response.send_message("Voice channel-ah ka awm lo.", ephemeral=True)

@bot.event
async def on_ready():
    print(f"✅ Bot a inpeih fel ta e: {bot.user}")

@bot.command()
async def join(ctx):
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        if ctx.voice_client:
            await ctx.voice_client.move_to(channel)
        else:
            await channel.connect()
        await ctx.send(f"🔊 **{channel.name}**-ah ka lo lut e!")
    else:
        await ctx.send("Voice channel-ah lut hmasa phawt rawh!")

@bot.command()
async def leave(ctx):
    get_queue(ctx.guild.id).clear()
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("👋 Ka chhuak ta e!")
    else:
        await ctx.send("Voice channel-ah ka awm lo.")

@bot.command()
async def play(ctx, *, search):
    if not ctx.author.voice:
        await ctx.send("Voice channel-ah lut hmasa phawt rawh!")
        return

    if not ctx.voice_client:
        await ctx.author.voice.channel.connect()

    async with ctx.typing():
        loop = asyncio.get_event_loop()
        try:
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(search, download=False))
            queue = get_queue(ctx.guild.id)

            entry = data['entries'][0] if 'entries' in data and data['entries'] else data
            title = entry.get('title', 'Hla')
            url = entry.get('webpage_url') or entry.get('url', search)
            queue.append({'title': title, 'search_url': url})

            if ctx.voice_client.is_playing() or ctx.voice_client.is_paused():
                await ctx.send(f"📋 Queue-ah dah a ni e: **{title}**")

            vc = ctx.voice_client
            if vc and not vc.is_playing() and not vc.is_paused():
                play_next(ctx)

        except Exception as e:
            await ctx.send("Hla lak chhuah theih a ni lo. Link dang emaw hla hming dang han tum chhin teh.")
            print(f"Error in play: {e}")

@bot.command()
async def loadplaylist(ctx, name: str):
    if not ctx.author.voice:
        await ctx.send("Voice channel-ah lut hmasa phawt rawh!")
        return

    playlists = load_saved_playlists()
    guild_id = str(ctx.guild.id)

    if guild_id not in playlists or name.lower() not in playlists[guild_id]:
        await ctx.send(f"Playlist **{name}** a awm lo. `!myplaylists` hmangin i playlist-te i en thei.")
        return

    song_list = playlists[guild_id][name.lower()]
    await ctx.send(f"🚀 Playlist **{name}** ({len(song_list)} songs) play mek a ni...")

    for song in song_list:
        await play(ctx, search=song)

@bot.command()
async def myplaylists(ctx):
    playlists = load_saved_playlists()
    guild_id = str(ctx.guild.id)

    if guild_id not in playlists or not playlists[guild_id]:
        await ctx.send("Playlist a la awm lo. Hla i play laiin **[💾 Save to Playlist]** button hmet rawh.")
        return

    msg = "**📂 I Playlist-te:**\n"
    for pl_name, songs in playlists[guild_id].items():
        msg += f"• **{pl_name}** ({len(songs)} songs)\n"
    await ctx.send(msg)

@bot.command()
async def viewplaylist(ctx, name: str):
    playlists = load_saved_playlists()
    guild_id = str(ctx.guild.id)
    p_name = name.lower()

    if guild_id not in playlists or p_name not in playlists[guild_id]:
        await ctx.send(f"Playlist **{name}** a awm lo.")
        return

    songs = playlists[guild_id][p_name]
    msg = f"🎶 **Playlist: {name.upper()} ({len(songs)} songs)**\n"
    for i, s in enumerate(songs, start=1):
        msg += f"{i}. {s}\n"
    await ctx.send(msg)

@bot.command()
async def queue(ctx):
    q = get_queue(ctx.guild.id)
    curr = current_songs.get(ctx.guild.id, "Awm lo")
    msg = f"🎶 **Play mek:** {curr}\n\n**📋 Queue:**\n"
    if not q:
        msg += "Queue-ah hla dah a awm lo."
    else:
        for i, s in enumerate(q[:10], start=1):
            msg += f"{i}. {s['title']}\n"
    await ctx.send(msg)

@bot.command()
async def skip(ctx):
    vc = ctx.voice_client
    if vc and (vc.is_playing() or vc.is_paused()):
        vc.stop()
        await ctx.send("⏭️ Hla skip a ni e!")

token = os.environ.get("DISCORD_TOKEN")
if token:
    bot.run(token)
else:
    print("Error: DISCORD_TOKEN environment variable a awm lo!")
    
