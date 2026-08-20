"""Configuration loading, validation and interval handling."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

# The four presets offered by `slotwatcher setup`. Any integer number of
# seconds also works, as long as it respects MIN_INTERVAL.
INTERVAL_PRESETS = {"30sec": 30, "1min": 60, "2min": 120, "5min": 300}

# Polling faster than this hammers the target site for no practical gain.
MIN_INTERVAL = 30

VALID_ACTIONS = {"goto", "click", "click_in", "fill", "check", "select", "press", "wait"}
VALID_SCOPES = {"all", "month", "days"}
VALID_DATE_ORDERS = {"dmy", "mdy", "ymd"}


class ConfigError(Exception):
    """Raised when a configuration file is missing something or is malformed."""


def _resolve_secret(value, where):
    """
    Resolve an "env:NAME" indirection.

    Keeping tokens in environment variables rather than in the config file is
    what makes it safe to commit a config to a public repository.
    """
    if not isinstance(value, str):
        raise ConfigError(f"{where} must be a string, got {type(value).__name__}")
    if value.startswith("env:"):
        name = value[4:].strip()
        if not name:
            raise ConfigError(f"{where}: 'env:' must be followed by a variable name")
        got = os.environ.get(name)
        if not got:
            raise ConfigError(
                f"{where} refers to environment variable {name!r}, which is not set.\n"
                f"  Set it with:  export {name}='...'"
            )
        return got
    return value


@dataclass
class Step:
    """One action performed on the way to the availability page."""

    action: str
    selector: str | None = None
    value: str | None = None
    url: str | None = None
    container: str = "form"
    contains: str | None = None
    key: str | None = None
    state: str = "visible"
    timeout: int | None = None
    navigates: bool = False
    optional: bool = False
    force: bool = False

    @classmethod
    def from_dict(cls, raw, index):
        where = f"[[site.steps]] #{index + 1}"
        if not isinstance(raw, dict):
            raise ConfigError(f"{where} must be a table")
        action = raw.get("action")
        if action not in VALID_ACTIONS:
            raise ConfigError(
                f"{where}: unknown action {action!r}. "
                f"Valid actions: {', '.join(sorted(VALID_ACTIONS))}"
            )

        known = {f.name for f in cls.__dataclass_fields__.values()}
        unknown = set(raw) - known
        if unknown:
            raise ConfigError(f"{where}: unknown key(s) {', '.join(sorted(unknown))}")

        step = cls(**{k: v for k, v in raw.items() if k in known})

        # Step values can hold personal data (an ID number, a date of birth).
        # "env:NAME" keeps it out of a config file that might get committed.
        if isinstance(step.value, str) and step.value.startswith("env:"):
            step.value = _resolve_secret(step.value, f"{where} value")

        if action == "goto" and not step.url:
            raise ConfigError(f"{where}: action 'goto' requires 'url'")
        if action in {"click", "fill", "check", "select", "press", "wait"} and not step.selector:
            raise ConfigError(f"{where}: action {action!r} requires 'selector'")
        if action in {"fill", "select"} and step.value is None:
            raise ConfigError(f"{where}: action {action!r} requires 'value'")
        if action == "press" and not step.key:
            raise ConfigError(f"{where}: action 'press' requires 'key'")
        if action == "click_in" and not (step.contains and step.selector):
            raise ConfigError(f"{where}: action 'click_in' requires 'contains' and 'selector'")
        return step

    def describe(self):
        if self.action == "click_in":
            return f"click {self.selector} inside {self.container} containing {self.contains!r}"
        if self.action == "fill":
            return f"fill {self.selector}"
        if self.action == "goto":
            return f"go to {self.url}"
        return f"{self.action} {self.selector or ''}".strip()


@dataclass
class ParseRules:
    """How to read availability out of the page text."""

    start_marker: str | None = None
    end_marker: str | None = None
    full_markers: list[str] = field(default_factory=list)
    free_markers: list[str] = field(default_factory=list)
    require_times: bool = True
    date_order: str = "dmy"
    date_regex: str | None = None
    time_regex: str | None = None
    ignore_past: bool = True

    @classmethod
    def from_dict(cls, raw):
        known = {f.name for f in cls.__dataclass_fields__.values()}
        unknown = set(raw) - known
        if unknown:
            raise ConfigError(f"[parse]: unknown key(s) {', '.join(sorted(unknown))}")
        rules = cls(**raw)
        if rules.date_order not in VALID_DATE_ORDERS:
            raise ConfigError(
                f"[parse] date_order must be one of {', '.join(sorted(VALID_DATE_ORDERS))}"
            )
        if not rules.require_times and not rules.free_markers:
            raise ConfigError(
                "[parse]: with require_times = false you must set free_markers, "
                "otherwise nothing can ever count as available"
            )
        return rules


@dataclass
class WatchRules:
    """Which dates matter, and how often to look."""

    interval: int = 120
    scope: str = "all"
    year: int | None = None
    month: int | None = None
    days: list[int] = field(default_factory=list)
    desktop_notifications: bool = True
    alert_after_errors: int = 3
    retries: int = 2

    @classmethod
    def from_dict(cls, raw):
        raw = dict(raw)
        raw["interval"] = parse_interval(raw.get("interval", "2min"))
        known = {f.name for f in cls.__dataclass_fields__.values()}
        unknown = set(raw) - known
        if unknown:
            raise ConfigError(f"[watch]: unknown key(s) {', '.join(sorted(unknown))}")
        rules = cls(**raw)
        if rules.scope not in VALID_SCOPES:
            raise ConfigError(
                f"[watch] scope must be one of {', '.join(sorted(VALID_SCOPES))}"
            )
        if rules.scope in {"month", "days"} and not (rules.year and rules.month):
            raise ConfigError(f"[watch] scope = {rules.scope!r} requires 'year' and 'month'")
        if rules.scope == "days" and not rules.days:
            raise ConfigError("[watch] scope = 'days' requires a non-empty 'days' list")
        return rules

    def describe(self):
        if self.scope == "all":
            return "any available date"
        month_name = f"{self.month:02d}/{self.year}"
        if self.scope == "month":
            return f"any date in {month_name}"
        return f"{', '.join(str(d) for d in sorted(self.days))} {month_name}"


def parse_interval(value):
    """Accept '30sec' / '1min' / '2min' / '5min', or a raw number of seconds."""
    if isinstance(value, bool):
        raise ConfigError("[watch] interval must be a preset or a number of seconds")
    if isinstance(value, int):
        seconds = value
    elif isinstance(value, str):
        key = value.strip().lower()
        if key in INTERVAL_PRESETS:
            seconds = INTERVAL_PRESETS[key]
        elif key.isdigit():
            seconds = int(key)
        else:
            raise ConfigError(
                f"[watch] interval {value!r} is not valid. Use one of "
                f"{', '.join(INTERVAL_PRESETS)} or a number of seconds."
            )
    else:
        raise ConfigError("[watch] interval must be a string or an integer")

    if seconds < MIN_INTERVAL:
        raise ConfigError(
            f"[watch] interval of {seconds}s is too aggressive; "
            f"the minimum is {MIN_INTERVAL}s so the target site is not hammered."
        )
    return seconds


@dataclass
class Config:
    path: Path
    name: str
    url: str
    telegram_token: str | None
    telegram_chat_id: str | None
    steps: list[Step]
    parse: ParseRules
    watch: WatchRules

    @property
    def state_path(self):
        return self.path.parent / ".state" / f"{self.path.stem}.json"

    @property
    def has_telegram(self):
        return bool(self.telegram_token and self.telegram_chat_id)


def load(path):
    """Read a TOML config file and return a validated Config."""
    path = Path(path).expanduser()
    if not path.is_file():
        raise ConfigError(f"Config file not found: {path}")
    try:
        with open(path, "rb") as fh:
            raw = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path} is not valid TOML: {exc}") from exc

    site = raw.get("site")
    if not site:
        raise ConfigError("Missing [site] section")
    url = site.get("url")
    if not url:
        raise ConfigError("[site] requires a 'url'")

    steps = [Step.from_dict(s, i) for i, s in enumerate(site.get("steps", []))]

    telegram = raw.get("telegram", {})
    token = telegram.get("token")
    chat_id = telegram.get("chat_id")
    if token:
        token = _resolve_secret(token, "[telegram] token")
    if chat_id:
        chat_id = str(_resolve_secret(str(chat_id), "[telegram] chat_id"))

    return Config(
        path=path,
        name=site.get("name", url),
        url=url,
        telegram_token=token,
        telegram_chat_id=chat_id,
        steps=steps,
        parse=ParseRules.from_dict(raw.get("parse", {})),
        watch=WatchRules.from_dict(raw.get("watch", {})),
    )
