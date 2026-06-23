"""
Simple JSON-backed storage for moderation warnings.

Each warning gets an incrementing integer ID (per-guild) so it can be
referenced later by /unwarn. Data is stored at utils/data/warnings.json
relative to the bot's working directory.

Structure on disk:
{
  "<guild_id>": {
    "next_id": 4,
    "warnings": [
      {
        "id": 1,
        "member_id": 123456789012345678,
        "moderator_id": 987654321098765432,
        "reason": "Spamming",
        "timestamp": "2026-06-23T10:15:00+00:00"
      },
      ...
    ]
  }
}
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DATA_PATH = Path(__file__).with_name("data") / "warnings.json"


@dataclass
class Warning:
    id: int
    member_id: int
    moderator_id: int
    reason: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "member_id": self.member_id,
            "moderator_id": self.moderator_id,
            "reason": self.reason,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Warning":
        return cls(
            id=data["id"],
            member_id=data["member_id"],
            moderator_id=data["moderator_id"],
            reason=data["reason"],
            timestamp=data.get("timestamp", ""),
        )


def _load() -> dict:
    if not DATA_PATH.exists():
        return {}
    try:
        with DATA_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save(data: dict) -> None:
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = DATA_PATH.with_suffix(".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    tmp_path.replace(DATA_PATH)


def add_warning(guild_id: int, member_id: int, moderator_id: int, reason: str) -> Warning:
    """Create and persist a new warning, returning it with its assigned ID."""
    data = _load()
    guild_key = str(guild_id)
    guild_data = data.setdefault(guild_key, {"next_id": 1, "warnings": []})

    new_id = guild_data["next_id"]
    warning = Warning(
        id=new_id,
        member_id=member_id,
        moderator_id=moderator_id,
        reason=reason,
    )
    guild_data["warnings"].append(warning.to_dict())
    guild_data["next_id"] = new_id + 1

    _save(data)
    return warning


def remove_warning(guild_id: int, warning_id: int) -> Optional[Warning]:
    """Remove a warning by ID. Returns the removed Warning, or None if not found."""
    data = _load()
    guild_key = str(guild_id)
    guild_data = data.get(guild_key)
    if not guild_data:
        return None

    warnings = guild_data.get("warnings", [])
    for i, entry in enumerate(warnings):
        if entry["id"] == warning_id:
            removed = warnings.pop(i)
            _save(data)
            return Warning.from_dict(removed)
    return None


def get_warnings(guild_id: int, member_id: int) -> list[Warning]:
    """Return all active warnings for a member in a guild, oldest first."""
    data = _load()
    guild_data = data.get(str(guild_id))
    if not guild_data:
        return []
    return [
        Warning.from_dict(entry)
        for entry in guild_data.get("warnings", [])
        if entry["member_id"] == member_id
    ]


def get_warning(guild_id: int, warning_id: int) -> Optional[Warning]:
    """Look up a single warning by ID without removing it."""
    data = _load()
    guild_data = data.get(str(guild_id))
    if not guild_data:
        return None
    for entry in guild_data.get("warnings", []):
        if entry["id"] == warning_id:
            return Warning.from_dict(entry)
    return None
