"""Turn the text of a booking page into a list of free slots."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

DEFAULT_DATE_REGEXES = {
    "dmy": r"(?<!\d)(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})(?!\d)",
    "mdy": r"(?<!\d)(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})(?!\d)",
    "ymd": r"(?<!\d)(\d{4})[/.-](\d{1,2})[/.-](\d{1,2})(?!\d)",
}

DEFAULT_TIME_REGEX = r"(?<!\d)([0-2]?\d[:h][0-5]\d)(?!\d)"


@dataclass(frozen=True)
class Slot:
    """One bookable day, with whatever times the page listed for it."""

    label: str          # the date exactly as printed on the page
    day: date
    times: tuple[str, ...]

    def keys(self):
        """Stable identifiers used to remember what was already reported."""
        if self.times:
            return {f"{self.label}|{t}" for t in self.times}
        return {self.label}

    def describe(self):
        return f"{self.label} ({', '.join(self.times)})" if self.times else self.label


class Parser:
    """
    Splits page text at each date, then classifies the block that follows it.

    Booking sites almost always print a date and then, underneath it, either a
    'fully booked' marker or a list of times. Reading blocks this way means a
    neighbouring date's status can never be mistaken for this one's.
    """

    def __init__(self, rules):
        self.rules = rules
        self.date_re = re.compile(rules.date_regex or DEFAULT_DATE_REGEXES[rules.date_order])
        self.time_re = re.compile(rules.time_regex or DEFAULT_TIME_REGEX)
        self.full = [m.lower() for m in rules.full_markers]
        self.free = [m.lower() for m in rules.free_markers]

    def _trim(self, text):
        """Drop the boilerplate around the calendar, which often holds dates too."""
        if self.rules.start_marker:
            i = text.find(self.rules.start_marker)
            if i != -1:
                text = text[i:]
        if self.rules.end_marker:
            i = text.find(self.rules.end_marker)
            if i != -1:
                text = text[:i]
        return text

    def _to_date(self, match):
        a, b, c = (int(g) for g in match.groups())
        order = self.rules.date_order
        if order == "dmy":
            day, month, year = a, b, c
        elif order == "mdy":
            month, day, year = a, b, c
        else:
            year, month, day = a, b, c
        try:
            return date(year, month, day)
        except ValueError:
            return None

    def parse(self, text, today=None):
        """Return the free Slots found in `text`, in page order."""
        today = today or date.today()
        text = self._trim(text)
        slots = []

        # Split *before* each date so every chunk starts with its own date.
        for block in re.split(f"(?={self.date_re.pattern})", text):
            match = self.date_re.match(block)
            if not match:
                continue
            day = self._to_date(match)
            if day is None:
                continue
            if self.rules.ignore_past and day < today:
                continue

            lowered = block.lower()
            if any(marker in lowered for marker in self.full):
                continue

            times = tuple(sorted(set(self.time_re.findall(block))))
            available = bool(times) if self.rules.require_times else False
            if self.free and any(marker in lowered for marker in self.free):
                available = True
            if not available:
                continue

            slots.append(Slot(label=match.group(0), day=day, times=times))
        return slots


def select(slots, watch):
    """Keep only the slots the user actually cares about."""
    if watch.scope == "all":
        return list(slots)
    wanted = []
    for slot in slots:
        if (slot.day.year, slot.day.month) != (watch.year, watch.month):
            continue
        if watch.scope == "days" and slot.day.day not in watch.days:
            continue
        wanted.append(slot)
    return wanted
