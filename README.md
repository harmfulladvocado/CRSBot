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

## Notes on this refactor

This is a reorganized version of the original single-file `bot.py`.
Behavior is unchanged — every command, event listener, modal, and view
works exactly as before. The only differences:

- IDs and constants moved to `config.py`
- Shared helpers moved to `utils/helpers.py`
- `send_log` / `send_ticket_transcript` moved to `utils/logging.py` and now take
  `bot` as an explicit argument instead of relying on a global `bot` variable
- Event handlers, the ticket system, and the warn command are now separate cogs
- `on_ready` stayed on `bot.py` instead of becoming a cog listener since
  it has no dependencies and isn't worth moving

You'll still want a real `requirements.txt` lock once you've run the bot
and confirmed everything works — `venv/bin/pip freeze > requirements.txt`
will capture exact installed versions.
