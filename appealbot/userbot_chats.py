"""List dialogs for the appeal user account — find Melbet Support chat ids.

  docker compose --profile userbot run --rm --no-deps appeal-userbot python userbot_chats.py

Requires TELEGRAM_API_ID / TELEGRAM_API_HASH / TELEGRAM_SESSION_STRING.
"""

from __future__ import annotations

import asyncio
import os
import sys

from telethon import TelegramClient
from telethon.sessions import StringSession


def _require() -> tuple[int, str, str]:
    raw_id = (os.getenv("TELEGRAM_API_ID") or "").strip()
    api_hash = (os.getenv("TELEGRAM_API_HASH") or "").strip()
    session = (os.getenv("TELEGRAM_SESSION_STRING") or "").strip()
    if not raw_id or not api_hash or not session:
        raise SystemExit(
            "Set TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_SESSION_STRING "
            "(login first with userbot_login.py)"
        )
    try:
        return int(raw_id), api_hash, session
    except ValueError as exc:
        raise SystemExit("TELEGRAM_API_ID must be an integer") from exc


async def main() -> None:
    api_id, api_hash, session = _require()
    client = TelegramClient(StringSession(session), api_id, api_hash)
    await client.start()
    me = await client.get_me()
    print(
        f"Logged in as id={me.id} username={getattr(me, 'username', None) or ''} "
        f"name={me.first_name or ''}"
    )
    print()
    print("Dialogs (groups/channels first). Put matching Melbet Support id into USERBOT_WATCH_CHAT_IDS:")
    print("-" * 72)
    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        is_group = bool(getattr(entity, "megagroup", False) or getattr(entity, "gigagroup", False))
        is_channel = bool(getattr(entity, "broadcast", False))
        is_user = getattr(entity, "bot", None) is not None and not is_group and not is_channel
        kind = "user"
        if is_group:
            kind = "group"
        elif is_channel:
            kind = "channel"
        elif getattr(entity, "bot", False):
            kind = "bot"
        title = dialog.name or ""
        lowered = title.lower()
        mark = ""
        if any(x in lowered for x in ("melbet", "мелбет", "support", "avapay", "апелляц")):
            mark = "  <-- candidate"
        print(f"{dialog.id:>16}  {kind:<7}  {title}{mark}")
    print("-" * 72)
    print("Example: USERBOT_WATCH_CHAT_IDS=-1001234567890")
    await client.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(1)
