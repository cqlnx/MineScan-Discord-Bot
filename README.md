# MineScan Discord Bot

Discord bot for searching and getting info about Minecraft servers using the mcapi.shit.vc API.

**[Join the Discord](https://discord.gg/AYbDNEWgHE)**

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Add your bot token to `bot.run()` in `main.py`

3. Run:
```bash
python main.py
```

## Commands

- `/help` - Show all commands
- `/random` - Get 5 random servers
- `/server` - Search servers with filters
- `/mcinfo <ip>` - Get live server info
- `/whois <ip>` - Find players on a server
- `/whereis <username/uuid>` - Find servers a player has been on
- `/stats` - Show database statistics
