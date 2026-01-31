"""
Minecraft Server Discord Bot
A Discord bot for searching, filtering, and getting info about Minecraft servers.
Uses the mcapi.shit.vc API to fetch server data and geolocation info.
"""

import discord
from discord.ext import commands, tasks
import requests
from mcstatus import JavaServer
from datetime import datetime,timezone
import asyncio

# Discord bot setup
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# API endpoints for server data
API_URL = "https://mcapi.shit.vc/servers"
API_URL_WHEREIS = "https://mcapi.shit.vc/whereis"
API_URL_WHO = "https://mcapi.shit.vc/who"

# ============================================================================
# API HELPER FUNCTIONS - Fetch data from the Minecraft server database API
# ============================================================================

def fetch_servers(page=1, **params):
    """Fetch a list of servers with optional filters (software, version, etc.)"""
    params["page"] = page
    response = requests.get(API_URL, params=params)
    if response.status_code != 200:
        return []
    return response.json().get("servers", [])


def fetch_random_servers():
    """Get 5 random servers from the API"""
    try:
        response = requests.get(f"{API_URL}/random")
        if response.status_code == 200:
            data = response.json()
            return data.get("servers", [])
        return []
    except:
        return []


def fetch_total_servers():
    """Get the total count of servers in the database"""
    try:
        response = requests.get(API_URL)
        if response.status_code == 200:
            data = response.json()
            return data.get("total", 0)
        return 0
    except:
        return 0


def fetch_whereis(identifier: str):
    """Find which servers a player has been seen on"""
    r = requests.get(f"{API_URL_WHEREIS}/{identifier}", timeout=10)
    if r.status_code != 200:
        return None
    data = r.json()
    # Try to find an exact match for the player
    if "players" not in data and data.get("name", "").lower() == identifier.lower():
        return data
    for p in data.get("players", []) or []:
        if p.get("name", "").lower() == identifier.lower():
            return p
    return None


def fetch_who(server_ip: str):
    """Get list of players seen on a specific server"""
    r = requests.get(f"{API_URL_WHO}/{server_ip}")
    if r.status_code != 200:
        return None
    return r.json()


# ============================================================================
# UTILITY FUNCTIONS - Helper functions for formatting and parsing data
# ============================================================================

def clean_motd(motd_obj):
    """Parse and clean the server's MOTD (message of the day)"""
    try:
        # Handle raw JSON format
        if hasattr(motd_obj, "raw") and isinstance(motd_obj.raw, dict):
            base = motd_obj.raw.get("text", "")
            extras = motd_obj.raw.get("extra", [])
            text = base + "".join(extras)
            return text.strip()

        # Handle parsed format
        if hasattr(motd_obj, "parsed"):
            clean = "".join([str(x) for x in motd_obj.parsed if isinstance(x, str)])
            return clean.strip()

        return str(motd_obj).strip()
    except:
        return "Unknown MOTD"


def map_authmode(authmode_str: str) -> dict:
    """Convert authentication mode string to emoji + readable text"""
    auth_map = {
        "online": {"icon": ":white_check_mark:", "text": "Online Mode"},
        "offline": {"icon": ":x:", "text": "Offline (Cracked)"},
        "whitelist": {"icon": ":lock:", "text": "Whitelisted"}
    }
    default = {"icon": ":question:", "text": "Unknown"}
    return auth_map.get((authmode_str or "").lower(), default)

# ============================================================================
# DISCORD UI COMPONENTS - Interactive buttons and embeds for Discord responses
# ============================================================================

class RandomServerButtons(discord.ui.View):
    """Creates clickable buttons for 5 random servers"""
    def __init__(self, servers):
        super().__init__(timeout=120)
        for index, server in enumerate(servers):
            self.add_item(ServerButton(label=f"Server {index + 1}", server=server))

class PlayerListButton(discord.ui.View):
    """Shows a button to reveal the list of online players on a server"""
    def __init__(self, players):
        super().__init__(timeout=30)
        self.players = players

    @discord.ui.button(label="Show Players", style=discord.ButtonStyle.blurple)
    async def show_players(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Display the list of players when button is clicked"""
        if not self.players:
            await interaction.response.send_message(
                "No players online or query is not enabled on server.", 
                ephemeral=True
            )
            return

        player_list = "\n".join(self.players)
        embed = discord.Embed(
            title="Online Players",
            description=player_list,
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

class ServerInfoButtons(discord.ui.View):
    """Handles pagination and displays servers in groups of 5"""
    def __init__(self, servers, page=1, params=None):
        super().__init__(timeout=120)
        self.servers = servers
        self.page = page
        self.params = params or {}
        self.start_index = 0
        self.update_buttons()

    def update_buttons(self):
        """Refresh the button layout based on current page"""
        self.clear_items()
        start = self.start_index % 20
        end = start + 5
        for index, server in enumerate(self.servers[start:end]):
            self.add_item(ServerButton(label=f"Server {self.start_index + index + 1}", server=server))
        self.add_item(PageButton(label="Previous", style=discord.ButtonStyle.secondary, direction=-1, view=self))
        self.add_item(PageButton(label="Next", style=discord.ButtonStyle.secondary, direction=1, view=self))

class ServerButton(discord.ui.Button):
    """A clickable button that shows detailed info about a server"""
    def __init__(self, label, server):
        super().__init__(label=label, style=discord.ButtonStyle.primary)
        self.server = server

    async def callback(self, interaction: discord.Interaction):
        """Show server details when clicked"""
        last_seen_raw = self.server.get("lastSeen")
        if last_seen_raw:
            dt = datetime.fromisoformat(last_seen_raw.replace("Z", "+00:00"))
            last_seen_ts = int(dt.replace(tzinfo=timezone.utc).timestamp())
            last_seen_display = f"<t:{last_seen_ts}:R>"
        else:
            last_seen_display = "Unknown"

        ip = self.server.get("serverip")
        geo = self.server.get("geolocation", {})
        embed = discord.Embed(title="Server Information", color=discord.Color.blue())
        embed.add_field(name="IP", value=ip, inline=False)
        embed.add_field(name="Version", value=str(self.server.get("version", "Unknown")), inline=True)
        embed.add_field(name="Country", value=f":flag_{geo.get('country', 'Unknown').lower()}: {geo.get('countryName', 'Unknown')}",inline=True)
        embed.add_field(name="City", value=geo.get("city", "Unknown"), inline=True)
        embed.add_field(name="Last Seen", value=last_seen_display, inline=True)

        auth_info = map_authmode(self.server.get("authmode"))
        embed.add_field(name="Authentication", value=f"{auth_info['icon']} {auth_info['text']}", inline=True)
        embed.add_field(name="Online Players", value=str(self.server.get("onlinePlayers", 0)), inline=True)
        embed.add_field(name="Max Players", value=str(self.server.get("maxPlayers", 0)), inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)

class PageButton(discord.ui.Button):
    """Navigation buttons for paginating through server lists"""
    def __init__(self, label, style, direction, view):
        super().__init__(label=label, style=style)
        self.direction = direction
        self.view_ref = view

    async def callback(self, interaction: discord.Interaction):
        """Handle next/previous page navigation"""
        self.view_ref.start_index += self.direction * 5

        # Move to next page if we've scrolled past the current one
        if self.view_ref.start_index >= 20:
            self.view_ref.page += 1
            self.view_ref.start_index = 0
            self.view_ref.servers = fetch_servers(
                page=self.view_ref.page, **self.view_ref.params
            )
        # Go back to previous page
        elif self.view_ref.start_index < 0:
            if self.view_ref.page == 1:
                self.view_ref.start_index = 0
            else:
                self.view_ref.page -= 1
                self.view_ref.start_index = 15
                self.view_ref.servers = fetch_servers(
                    page=self.view_ref.page, **self.view_ref.params
                )

        self.view_ref.update_buttons()

        start = self.view_ref.start_index
        end = start + 5

        embed = discord.Embed(
            title=f"Server Search Results - Page {self.view_ref.page}",
            color=discord.Color.blue()
        )

        for i, server in enumerate(self.view_ref.servers[start:end], start=start + 1):
            ip = server.get("serverip")
            geo = server.get("geolocation", {})
            auth_info = map_authmode(server.get("authmode"))

            embed.add_field(
                name=f"Server {i}",
                value=(
                    f"**IP:** {ip}\n"
                    f"**Version:** {server.get('version', 'Unknown')}\n"
                    f"**Location:** :flag_{geo.get('country', 'Unknown').lower()}: {geo.get('countryName', 'Unknown')}, {geo.get('city', 'Unknown')}\n"
                    f"**Authentication:** {auth_info['icon']} {auth_info['text']}"
                ),
                inline=False
            )

        await interaction.response.edit_message(embed=embed, view=self.view_ref)

# ============================================================================
# DISCORD COMMANDS - Slash commands that users can interact with
# ============================================================================

@bot.tree.command(name="help", description="Show help for commands.")
async def help_cmd(interaction: discord.Interaction):
    """Display the help menu with all available commands"""
    embed = discord.Embed(
        title="❓ Help Menu",
        description="List of available commands and how to use them.",
        color=discord.Color.blue()
    )

    server_help = (
        "**/server** — Search for Minecraft servers using the API.\n"
        "**Options:**\n"
        "• **page** — Starting page number (20 servers per page)\n"
        "• **software** — Filter by server software (e.g., Paper, Vanilla)\n"
        "• **version** — Filter by Minecraft version (e.g., 1.20.1)\n"
        "• **country** — Filter by server location (e.g., EE, Estonia)\n"
        "• **sort** — Sort by: Last Seen, Player Count, or Version\n"
        "• **authmode** — Authentication: online / offline / whitelist\n"
        "• **minplayers** — Minimum number of online players\n"
    )
    embed.add_field(name="🖥️ /server", value=server_help, inline=False)
    embed.add_field(name="🎲 /random", value="Gives a list of 5 random servers", inline=False)
    embed.add_field(name="📄 /mcinfo", value="Displays information about a server\nUsage: /mcinfo (IP of the server)", inline=False)
    embed.add_field(name="📈 /stats", value="Displays statistics about the bot.", inline=False)
    embed.add_field(name="👥 /whois", value="Find who has played on a server", inline=False)
    embed.add_field(name="🌍 /whereis", value="Find where a player has been", inline=False)
    embed.set_footer(text="Use the commands with / to start!")

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="random", description="Get 5 random Minecraft servers")
async def random_cmd(interaction: discord.Interaction):
    """Show 5 completely random servers from the database"""
    await interaction.response.defer()

    servers = fetch_random_servers()

    if not servers:
        await interaction.followup.send("No servers found (after privacy filtering).")
        return

    view = RandomServerButtons(servers)
    embed = discord.Embed(title="Random Server Selection", color=discord.Color.blue())

    for i, server in enumerate(servers, start=1):
        ip = server.get("serverip")
        geo = server.get("geolocation", {})
        auth_info = map_authmode(server.get("authmode"))

        embed.add_field(
            name=f"Server {i}",
            value=(
                f"**IP:** {ip}\n"
                f"**Version:** {server.get('version', 'Unknown')}\n"
                f"**Location:** :flag_{geo.get('country', 'Unknown').lower()}: {geo.get('countryName', 'Unknown')}, {geo.get('city', 'Unknown')}\n"
                f"**Authentication:** {auth_info['icon']} {auth_info['text']}"
            ),
            inline=False
        )

    await interaction.followup.send(embed=embed, view=view)

@bot.tree.command(name="server", description="Search Minecraft servers with filters")
@discord.app_commands.describe(
    page="Starting page number to fetch servers from (20 servers per page)",
    software="Filter by server software (e.g., Paper)",
    version="Filter by Minecraft version (e.g., 1.20.1)",
    country="Filter by server country (e.g., EE, Estonia)",
    sort="Sort servers by different criteria",
    authmode="Choose authentication mode: online/offline/whitelist",
    minplayers="Minimum number of online players"
)
@discord.app_commands.choices(
    authmode=[
        discord.app_commands.Choice(name="Online", value="online"),
        discord.app_commands.Choice(name="Offline", value="offline"),
        discord.app_commands.Choice(name="Whitelist", value="whitelist")
    ],
    sort=[
        discord.app_commands.Choice(name="Last Seen", value="lastseen"),
        discord.app_commands.Choice(name="Player Count", value="players"),
        discord.app_commands.Choice(name="Version", value="version")
    ]
)
async def server_cmd(
    interaction: discord.Interaction,
    page: int = 1,
    software: str | None = None,
    country: str | None = None,
    version: str | None = None,
    sort: discord.app_commands.Choice[str] | None = None,
    authmode: discord.app_commands.Choice[str] | None = None,
    minplayers: int | None = None
):
    """Search for servers with optional filters"""
    await interaction.response.defer()

    # Build query parameters from user input
    params = {}
    if software: 
        params["software"] = software
    if version: 
        params["version"] = version
    if sort: 
        params["sort"] = sort.value
    if authmode: 
        params["authmode"] = authmode.value
    if minplayers is not None: 
        params["minPlayers"] = minplayers
    if country: 
        params["country"] = country

    servers = fetch_servers(page=page, **params)

    if not servers:
        await interaction.followup.send("No servers found (after privacy filtering).")
        return

    view = ServerInfoButtons(servers, page=page, params=params)

    embed = discord.Embed(
        title=f"Server Search Results - Page {page}",
        color=discord.Color.blue()
    )

    for i, server in enumerate(servers[:5], start=1):
        ip = server.get("serverip")
        geo = server.get("geolocation", {})
        auth_info = map_authmode(server.get("authmode"))

        embed.add_field(
            name=f"Server {i}",
            value=(
                f"**IP:** {ip}\n"
                f"**Version:** {server.get('version', 'Unknown')}\n"
                f"**Location:** :flag_{geo.get('country', 'Unknown').lower()}: {geo.get('countryName', 'Unknown')}, {geo.get('city', 'Unknown')}\n"
                f"**Authentication:** {auth_info['icon']} {auth_info['text']}"
            ),
            inline=False
        )

    await interaction.followup.send(embed=embed, view=view)

@bot.tree.command(name="whereis", description="Find where a Minecraft player has been")
@discord.app_commands.describe(
    username="Minecraft username to search",
    uuid="Minecraft UUID to search"
)
async def whereis_cmd(interaction: discord.Interaction, username: str | None = None, uuid: str | None = None):
    """Find all servers where a player has played"""
    await interaction.response.defer()

    if not username and not uuid:
        await interaction.followup.send("Please provide either a username or a UUID.")
        return

    if username and uuid:
        await interaction.followup.send("Please only provide **one** of username or UUID.")
        return

    identifier = uuid if uuid else username
    search_type = "UUID" if uuid else "Username"

    data = fetch_whereis(identifier)
    if not data:
        await interaction.followup.send(f"No servers found for {identifier}.")
        return

    player = data
    servers = player.get("servers", [])
    if not servers:
        await interaction.followup.send(f"No servers found for {identifier}.")
        return

    embed = discord.Embed(
        title=f"{search_type} Search Results for {player.get('name', identifier)}",
        color=discord.Color.blue()
    )

    # Show up to 10 servers where the player has been
    for server in servers[:10]:
        first_seen_dt = datetime.fromisoformat(server['firstSeen'].replace("Z", "+00:00"))
        last_seen_dt = datetime.fromisoformat(server['lastSeen'].replace("Z", "+00:00"))

        first_seen_ts = int(first_seen_dt.timestamp())
        last_seen_ts = int(last_seen_dt.timestamp())

        first_seen = f"<t:{first_seen_ts}:R>"
        last_seen = f"<t:{last_seen_ts}:R>"

        embed.add_field(
            name=f"Server `{server['ip']}:{server['port']}`",
            value=f"**First Seen:** {first_seen}\n**Last Seen:** {last_seen}",
            inline=False
        )

    await interaction.followup.send(embed=embed)

@bot.tree.command(name="stats", description="Show statistics about the Minecraft server database.")
async def stats_cmd(interaction: discord.Interaction):
    """Display overall database statistics"""
    await interaction.response.defer()
    total = fetch_total_servers()

    embed = discord.Embed(title="Statistics", color=discord.Color.blue())
    embed.add_field(name="Bot author:", value="<@521371256763711489> (Reimopro)", inline=False)
    embed.add_field(name="API:", value="https://mcapi.shit.vc/", inline=False)
    embed.add_field(name="Total Servers:", value=f"**{total:,}**", inline=False)

    await interaction.followup.send(embed=embed)

@bot.tree.command(name="whois", description="Find who has played on a Minecraft server")
@discord.app_commands.describe(
    server_ip="The IP of the Minecraft server to search"
)
async def whois_cmd(interaction: discord.Interaction, server_ip: str):
    """Find all players who have played on a specific server"""
    await interaction.response.defer()

    data = fetch_who(server_ip)
    if not data:
        await interaction.followup.send(f"No players found for server `{server_ip}`.")
        return

    players = data.get("players", [])
    if not players:
        await interaction.followup.send(f"No players found for server `{server_ip}`.")
        return

    embed = discord.Embed(
        title=f"Players Seen on Server `{data['server']['ip']}:{data['server']['port']}`",
        color=discord.Color.blue()
    )

    # Show up to 20 players
    for player in players[:20]:
        first_seen_dt = datetime.fromisoformat(player['firstSeen'].replace("Z", "+00:00"))
        last_seen_dt = datetime.fromisoformat(player['lastSeen'].replace("Z", "+00:00"))

        first_seen = f"<t:{int(first_seen_dt.timestamp())}:R>"
        last_seen = f"<t:{int(last_seen_dt.timestamp())}:R>"

        embed.add_field(
            name=f"{player['name']} (`{player['uuid']}`)",
            value=f"**First Seen:** {first_seen}\n**Last Seen:** {last_seen}",
            inline=False
        )

    await interaction.followup.send(embed=embed)

@bot.tree.command(name="mcinfo", description="Get information about a Minecraft Java server.")
async def mcinfo(interaction: discord.Interaction, ip: str):
    """Get detailed info about a server (version, players, MOTD)"""
    await interaction.response.defer()

    try:
        # Try to connect to the server with a 5 second timeout
        try:
            server = await asyncio.wait_for(
                asyncio.to_thread(JavaServer.lookup, ip),
                timeout=5.0
            )
        except asyncio.TimeoutError:
            await interaction.followup.send(f"Could not reach `{ip}`.", ephemeral=True)
            return
        except Exception as e:
            await interaction.followup.send(f"Could not reach `{ip}`.", ephemeral=True)
            return

        # Get the server status (players, version, etc)
        try:
            status = await asyncio.wait_for(
                asyncio.to_thread(server.status),
                timeout=5.0
            )
        except asyncio.TimeoutError:
            await interaction.followup.send(f"Could not reach `{ip}`.", ephemeral=True)
            return
        except Exception as e:
            await interaction.followup.send(f"Could not reach `{ip}`.", ephemeral=True)
            return

        # Try to get list of online players (optional - not all servers support this)
        players = []
        try:
            query = await asyncio.wait_for(
                asyncio.to_thread(server.query),
                timeout=5.0
            )
            players = query.players.names
        except:
            pass

        # Create and send the embed with server info
        embed = discord.Embed(title=f"Server Info — {ip}", color=discord.Color.blue())
        embed.add_field(name="Status", value="Online", inline=True)
        embed.add_field(name="Version", value=status.version.name, inline=True)
        embed.add_field(name="Players", value=f"{status.players.online}/{status.players.max}", inline=True)
        embed.add_field(name="MOTD", value=clean_motd(status.motd) or "Unknown", inline=False)

        view = PlayerListButton(players)
        await interaction.followup.send(embed=embed, view=view)
    except Exception as e:
        await interaction.followup.send(f"Could not reach `{ip}`.", ephemeral=True)

# ============================================================================
# BOT LIFECYCLE - Activity updates and startup events
# ============================================================================

@tasks.loop(minutes=5)
async def update_activity():
    """Update the bot's status to show the total number of servers"""
    total = fetch_total_servers()
    activity_text = f"{total:,} Minecraft servers"
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=activity_text))


@bot.event
async def on_ready():
    """Run when the bot successfully connects to Discord"""
    print(f"Logged in as {bot.user}")
    try:
        await bot.tree.sync()
        print("Slash commands synced.")
    except Exception as e:
        print(e)
    update_activity.start()


# Start the bot with the token
bot.run("")
