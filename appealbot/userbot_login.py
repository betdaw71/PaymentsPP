"""Interactive login: prints TELEGRAM_SESSION_STRING for the appeal userbot.

Run once on a machine where you can receive the Telegram SMS/code:

  docker compose --profile userbot run --rm -it --no-deps appeal-userbot python userbot_login.py

Or locally:

  TELEGRAM_API_ID=... TELEGRAM_API_HASH=... python userbot_login.py
"""

from __future__ import annotations

import asyncio
import os
import sys

from telethon import TelegramClient
from telethon.sessions import StringSession


def _require_api() -> tuple[int, str]:
    raw_id = (os.getenv("TELEGRAM_API_ID") or "").strip()
    api_hash = (os.getenv("TELEGRAM_API_HASH") or "").strip()
    if not raw_id or not api_hash:
        raise SystemExit("Set TELEGRAM_API_ID and TELEGRAM_API_HASH (https://my.telegram.org → API development tools)")
    try:
        return int(raw_id), api_hash
    except ValueError as exc:
        raise SystemExit("TELEGRAM_API_ID must be an integer") from exc


async def main() -> None:
    api_id, api_hash = _require_api()
    two_fa = (os.getenv("TELEGRAM_2FA_PASSWORD") or "").strip()
    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.start(
        phone=lambda: input("Phone number (+7… / +1…): ").strip(),
        password=lambda: two_fa or input("Cloud password (2FA), empty if none: "),
    )
    me = await client.get_me()
    session = client.session.save()
    print()
    print(f"Logged in as id={me.id} username={getattr(me, 'username', None) or ''} first_name={me.first_name or ''}")
    print()
    print("Put this in server .env (do not commit, do not paste into provider chats):")
    print(f"TELEGRAM_SESSION_STRING={session}")
    print()
    await client.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(1)
