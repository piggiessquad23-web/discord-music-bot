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
import requests
import re

try:
    static_ffmpeg.add_paths()
except Exception:
    pass

# Render Web Service health-check bypass
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Music bot is online and healthy!")

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

# Multi-platform audio extractor options
ytdl_format_options = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'source_address': '0.0.0.0',
    'default_search': 'auto',
}

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

# Spotify metadata extraction (API key ngai miah lova embed oEmbed lakna)
def resolve_spotify_tracks(url):
    track_queries = []
    try:
        # Spotify track link
        if "open.spotify.com/track/" in url:
            res = requests.get(f"https://open.spotify.com/oembed?url={url}", timeout=5)
            if res.status_code == 200:
                data = res.json()
                title = data.get("title")
                if title:
                    track_queries.append(title)
        # Spotify album / playlist link (HTML scraping)
        elif "open.spotify.com/playlist/" in url or "open.spotify.com/album/" in url:
            res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=8)
            if res.status_code == 200:
                titles = re.findall(r'<meta property="music:song" content="([^"]+)"', res.text)
                for t_url in titles[:25]:  # Hla 25 thleng la rawh
                    t_res = requests.get(f"https://open.spotify.com/oembed?url={t_url}", timeout=5)
                    if t_res.status_code == 200:
                        t_data = t_res.json()
                        t_title = t_data.get("title")
                        if t_title:
                            track_queries.append(t_title)
    except Exception as e:
        print(f"Spotify resolve error: {e}")
    return track_queries

def extract_audio_info(query):
    # Multi-platform search fallback
    search_queries = []
    if query.startswith("http://") or query.startswith("https://"):
        search_queries.append(query)
    else:
        search_queries.append(f"scsearch1:{query}")
        search_queries.append(f"ytsearch1:{query}")

    for q in search_queries:
        try:
            data = ytdl.extract_info(q, download=False)
            if 'entries' in data and data['entries']:
                entry = data['entries'][0]
            else:
                entry = data

            if entry and 'url' in entry:
                return {
                    'title': entry.get('title', query),
                    'url': entry['url']
                }
        except Exception as e:
            print(f"Extraction error for {q}: {e}")
            continue

    return None

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
        placeholder="Entirnan: myfav, zofolk, chill",
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

def play_next(ctx):
    queue = get_queue(ctx.guild.id)
    if queue and ctx.voice_client:
        next_song = queue.pop(0)
        current_songs[ctx.guild.id] = next_song['title']
        try:
            source = discord.FFmpegPCMAudio(next_song['url'], **ffmpeg_options)
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

    @button(label="Save", style=discord.ButtonStyle.green, emoji="💾", row=1)
    async def save_to_playlist_button(self, interaction: discord.Interaction, btn: Button):
        song = current_songs.get(interaction.guild.id)
        if not song:
            await interaction.response.send_message("Hla play mek a awm lo.", ephemeral=True)
            return
        await interaction.response.send_modal(AddToPlaylistModal(song))

    @button(label="Playlists", style=discord.ButtonStyle.primary, emoji="📂", row=1)
    async def playlists_button(self, interaction: discord.Interaction, btn: Button):
        playlists = load_saved_playlists()
        gid = str(interaction.guild.id)
        if gid not in playlists or not playlists[gid]:
            await interaction.response.send_message("Playlist save a la awm lo. **[💾 Save]** button hmetin save rawh le!", ephemeral=True)
            return
        msg = "**📂 I Playlist Save-te:**\n"
        for pl_name, songs in playlists[gid].items():
            msg += f"• **{pl_name}** ({len(songs)} songs)\n"
        await interaction.response.send_message(msg, ephemeral=True)

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

        # 1. Spotify Link a nih chuan
        if "open.spotify.com" in search:
            spotify_tracks = await loop.run_in_executor(None, lambda: resolve_spotify_tracks(search))
            if not spotify_tracks:
                await ctx.send("Spotify atangin hla lak chhuah theih a ni lo.")
                return

            await ctx.send(f"🟢 Spotify atangin hla **{len(spotify_tracks)}** lak mek a ni...")
            for s_name in spotify_tracks:
                song_info = await loop.run_in_executor(None, lambda name=s_name: extract_audio_info(name))
                if song_info:
                    get_queue(ctx.guild.id).append(song_info)

            vc = ctx.voice_client
            if vc and not vc.is_playing() and not vc.is_paused():
                play_next(ctx)
            return

        # 2. Platform dang (YouTube, SoundCloud, Bandcamp, direct search)
        song_data = await loop.run_in_executor(None, lambda: extract_audio_info(search))

        if not song_data:
            await ctx.send("Hla a hmu zo lo tlat mai, hming dang han tum chhin teh.")
            return

        queue = get_queue(ctx.guild.id)
        queue.append(song_data)

        if ctx.voice_client.is_playing() or ctx.voice_client.is_paused():
            await ctx.send(f"📋 Queue-ah dah a ni e: **{song_data['title']}**")
        else:
            play_next(ctx)

@bot.command()
async def loadplaylist(ctx, name: str):
    if not ctx.author.voice:
        await ctx.send("Voice channel-ah lut hmasa phawt rawh!")
        return

    playlists = load_saved_playlists()
    guild_id = str(ctx.guild.id)

    if guild_id not in playlists or name.lower() not in playlists[guild_id]:
        await ctx.send(f"Playlist **{name}** a awm lo.")
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
        await ctx.send("Playlist a la awm lo. Hla i play laiin **[💾 Save]** button hmet rawh.")
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
        
