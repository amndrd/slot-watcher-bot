"""The watch loop: check, compare against what was already seen, notify."""

from __future__ import annotations

import asyncio
from datetime import datetime

from .flow import Flow
from .notifier import Notifier
from .parser import Parser, select
from .state import State

RETRY_DELAY = 20  # seconds between immediate retries after a failed check


def log(message):
    print(f"[{datetime.now():%H:%M:%S}] {message}", flush=True)


class Watcher:
    def __init__(self, config, dry_run=False):
        self.config = config
        self.dry_run = dry_run
        self.parser = Parser(config.parse)
        self.state = State(config.state_path)
        self.notifier = Notifier(
            config.telegram_token, config.telegram_chat_id, log,
            desktop=config.watch.desktop_notifications,
        )
        self.flow = Flow(config, log, debug_dir=config.path.parent / ".debug")

    # ── one check ────────────────────────────────────────────────────
    async def check_once(self):
        """Return (status, current_keys). Status is FOUND, NONE or ERROR."""
        try:
            text = await self.flow.fetch_text()
        except Exception as exc:
            log(f"  check failed: {str(exc).splitlines()[0]}")
            return "ERROR", None

        available = select(self.parser.parse(text), self.config.watch)
        if not available:
            log("  nothing available")
            return "NONE", set()

        keys = set().union(*(slot.keys() for slot in available))
        log("  available: " + " | ".join(slot.describe() for slot in available))

        new = self.state.new_among(keys)
        if not new:
            log("  already reported — staying quiet")
            return "NONE", keys

        log(f"  {len(new)} new slot(s)")
        if not self.dry_run:
            self._announce(available, new)
        return "FOUND", keys

    def _announce(self, available, new):
        lines = []
        for slot in available:
            fresh = sorted(t for t in slot.times if f"{slot.label}|{t}" in new)
            if fresh:
                lines.append(f"📅 <b>{slot.label}</b> — {', '.join(fresh)}")
            elif slot.label in new:
                lines.append(f"📅 <b>{slot.label}</b>")
        self.notifier.send(
            "🚨 <b>SLOT AVAILABLE</b>\n\n"
            f"📍 {self.config.name}\n\n"
            + "\n".join(lines)
            + f"\n\n👉 Book now: {self.config.url}"
        )
        dates = ", ".join(sorted({key.split("|")[0] for key in new}))
        self.notifier.alarm("🚨 Slot available!", f"{dates} — go!")

    async def check_with_retry(self):
        attempts = self.config.watch.retries + 1
        for attempt in range(1, attempts + 1):
            status, keys = await self.check_once()
            if status != "ERROR":
                return status, keys
            if attempt < attempts:
                log(f"  retrying ({attempt + 1}/{attempts}) in {RETRY_DELAY}s")
                await asyncio.sleep(RETRY_DELAY)
        return "ERROR", None

    # ── the loop ─────────────────────────────────────────────────────
    async def run(self):
        watch = self.config.watch
        log("=" * 60)
        log(f"Watching  : {self.config.name}")
        log(f"Looking for: {watch.describe()}")
        log(f"Every     : {watch.interval}s")
        log("=" * 60)
        if self.state.reported:
            log(f"{len(self.state.reported)} slot(s) already reported previously")
        log("Press Ctrl+C to stop.\n")

        self.notifier.send(
            "✅ <b>Watcher started</b>\n\n"
            f"📍 {self.config.name}\n"
            f"🔎 {watch.describe()}\n"
            f"⏱ every {watch.interval}s\n\n"
            "You'll get a message as soon as a slot opens up."
        )

        count = 0
        failures = 0
        alerted = False
        while True:
            count += 1
            log(f"── check #{count} " + "─" * 34)
            status, keys = await self.check_with_retry()

            if status == "ERROR":
                failures += 1
                log(f"  {failures} consecutive failure(s)")
                # Without this, an outage is invisible unless someone is
                # watching the terminal.
                if failures >= watch.alert_after_errors and not alerted:
                    self.notifier.send(
                        "⚠️ <b>Watcher is failing</b>\n\n"
                        f"{failures} checks in a row failed for {self.config.name}.\n"
                        "The site may be down, or its layout may have changed."
                    )
                    alerted = True
            else:
                if failures and alerted:
                    self.notifier.send("✅ <b>Watcher recovered</b> — back to normal.")
                failures = 0
                alerted = False
                if keys is not None:
                    self.state.sync(keys)

            log(f"  next check in {watch.interval}s\n")
            await asyncio.sleep(watch.interval)
