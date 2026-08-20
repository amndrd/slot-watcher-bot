"""Telegram and desktop notifications."""

from __future__ import annotations

import json
import platform
import subprocess
import time
import urllib.parse
import urllib.request

API = "https://api.telegram.org/bot{token}/{method}"


class TelegramError(Exception):
    pass


def _call(token, method, params=None, timeout=15):
    url = API.format(token=token, method=method)
    data = urllib.parse.urlencode(params or {}).encode()
    request = urllib.request.Request(url, data=data)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode()).get("description", str(exc))
        except Exception:
            detail = str(exc)
        raise TelegramError(detail) from exc
    except Exception as exc:
        raise TelegramError(str(exc)) from exc
    if not payload.get("ok"):
        raise TelegramError(payload.get("description", "unknown error"))
    return payload.get("result", {})


def check_bot(token):
    """Return the bot's username, confirming the token works."""
    return _call(token, "getMe").get("username")


def check_chat(token, chat_id):
    """Return a human-readable name for the chat, confirming it is reachable."""
    result = _call(token, "getChat", {"chat_id": chat_id})
    return result.get("title") or result.get("first_name") or str(chat_id)


def recent_chat_ids(token):
    """
    List chats that have recently messaged the bot.

    This is how a new user finds their chat id: send the bot a message, then
    run `slotwatcher setup`.
    """
    found = {}
    for update in _call(token, "getUpdates", {"timeout": 0, "limit": 20}) or []:
        message = update.get("message") or update.get("channel_post") or {}
        chat = message.get("chat") or {}
        if chat.get("id") is not None:
            name = chat.get("title") or " ".join(
                filter(None, [chat.get("first_name"), chat.get("last_name")])
            )
            found[str(chat["id"])] = name or chat.get("type", "chat")
    return found


class Notifier:
    def __init__(self, token, chat_id, log, desktop=True):
        self.token = token
        self.chat_id = chat_id
        self.log = log
        self.desktop = desktop and platform.system() == "Darwin"

    def send(self, message):
        """Send an HTML-formatted Telegram message. Never raises."""
        if not (self.token and self.chat_id):
            self.log("  (Telegram not configured — message not sent)")
            return False
        try:
            _call(self.token, "sendMessage", {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": "true",
            })
            self.log("  Telegram message sent")
            return True
        except TelegramError as exc:
            self.log(f"  Telegram error: {exc}")
            return False

    def alarm(self, title, message):
        """macOS banner plus a repeated sound, to wake someone up."""
        if not self.desktop:
            return
        safe = message.replace('"', "'")
        try:
            subprocess.run(
                ["osascript", "-e",
                 f'display notification "{safe}" with title "{title}" sound name "Glass"'],
                check=False, timeout=10,
            )
            for _ in range(6):
                subprocess.run(["afplay", "/System/Library/Sounds/Glass.aiff"],
                               check=False, timeout=5)
                time.sleep(0.3)
        except Exception:
            pass
