# CRSBot

## Project layout

```
CRSBot/
├── bot.py                 # Entry point — loads cogs, starts the bot
├── config.py               # All server IDs and tunable constants
├── .env                    # DISCORD_BOT_TOKEN (gitignored, create from .env.example)
├── .env.example             # Template for .env
├── .gitignore
├── requirements.txt
├── cogs/
│   ├── tickets.py            # Ticket system: button, dropdown, modals, transcripts
│   ├── logging_events.py     # Server activity logging (channels, roles, members, messages)
│   └── moderation.py         # !warn command
└── utils/
    ├── helpers.py             # Shared small helper functions
    └── logging.py             # send_log() and send_ticket_transcript()
```

## Setup

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
cp .env.example .env
# edit .env and paste your real token
venv/bin/python bot.py
```

## Adding a new feature

1. Create a new file in `cogs/`, e.g. `cogs/fun.py`.
2. Give it a `class` extending `commands.Cog`, and an `async def setup(bot)` at the bottom that calls `bot.add_cog(...)`.
3. Add the module path (e.g. `"cogs.fun"`) to `INITIAL_COGS` in `bot.py`.

## Editing config

All channel/role/category IDs and tunables (max open tickets, excluded
channels, ticket type options) live in `config.py` — nothing else should
hardcode an ID.
