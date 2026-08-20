# slot-watcher-bot

Watch any booking site for free slots and get a Telegram alert the moment one opens up.

Driving-test centres, consulates, doctors, DMV appointments — anywhere availability is
gone in minutes and refreshing by hand is not realistic. You describe the site once in a
config file; the bot walks through it on a schedule and messages you when something frees up.

```
🚨 SLOT AVAILABLE

📍 Name — Description

📅 21/08/2026 — 10:00, 12:00
📅 08/09/2026 — 07:00, 09:00

👉 Book now: https://website
```

## Why a config file

There is no honest way to make one scraper understand every booking site. Instead, you
describe your site's path to the calendar as a short list of steps, and the engine runs
them. Adding a new site means writing config, not code.

## Install

Requires Python 3.11+.

```bash
git clone https://github.com/amndrd/slot-watcher-bot.git
cd slot-watcher-bot
pip install -r requirements.txt
playwright install chromium
```

## Set up

```bash
python -m slotwatcher setup
```

The wizard creates your Telegram bot connection, finds your chat id, asks how often to
check, and writes a `config.toml`. Then:

```bash
python -m slotwatcher check   # validate the config
python -m slotwatcher dump    # see exactly what the bot reads
python -m slotwatcher once    # one check, no notifications
python -m slotwatcher run     # start watching
```

### Getting a Telegram bot

1. Message [@BotFather](https://t.me/BotFather) and send `/newbot`.
2. Copy the token it gives you.
3. Send any message to your new bot so it can see your chat.
4. Run `python -m slotwatcher setup` and paste the token.

## Configuration

```toml
[telegram]
token = "env:TELEGRAM_TOKEN"      # "env:NAME" reads an environment variable
chat_id = "env:TELEGRAM_CHAT_ID"

[watch]
interval = "2min"                 # 30sec | 1min | 2min | 5min
scope = "all"                     # all | month | days
desktop_notifications = true

[site]
name = "My booking site"
url = "https://example.com/booking"

[[site.steps]]
action = "click"
selector = "button#start"
navigates = true

[parse]
full_markers = ["Fully booked", "Sold out"]
require_times = true
date_order = "dmy"
```

### `[watch]`

| Key | Meaning |
| --- | --- |
| `interval` | `30sec`, `1min`, `2min`, `5min`, or a number of seconds (minimum 30) |
| `scope` | `all` = any date; `month` = one month; `days` = specific days |
| `year`, `month`, `days` | required for `month` / `days` scope |
| `desktop_notifications` | macOS banner + sound alongside Telegram |
| `alert_after_errors` | Telegram warning after N consecutive failures (default 3) |
| `retries` | immediate retries before a check counts as failed (default 2) |

### `[[site.steps]]`

Actions run in order, starting from `site.url`.

| Action | Keys | Does |
| --- | --- | --- |
| `click` | `selector`, `navigates`, `force` | click an element |
| `click_in` | `container`, `contains`, `selector` | click inside the container holding given text |
| `fill` | `selector`, `value` | type into a field |
| `check` | `selector` | tick a checkbox, including styled ones whose input is hidden |
| `select` | `selector`, `value` | pick a dropdown option |
| `press` | `selector`, `key` | send a keypress |
| `wait` | `selector`, `state` | wait for an element |
| `goto` | `url` | navigate somewhere else |

Every step also accepts `optional = true` (skip on failure) and `timeout` in milliseconds.
Set `navigates = true` on a step that triggers a page load, so the bot waits for it.

`click_in` exists because category pickers are often several identical `<form>`s that
differ only by their text — you select by label rather than by position.

### `[parse]`

The page is split at each date, and the block underneath is classified.

| Key | Meaning |
| --- | --- |
| `full_markers` | text meaning "unavailable" (`Volzet`, `Complet`, `Sold out`…) |
| `free_markers` | text meaning "available", if the site uses words instead of times |
| `require_times` | treat times like `09:00` under a date as availability (default true) |
| `date_order` | `dmy` (31/12/2026), `mdy`, or `ymd` |
| `start_marker` / `end_marker` | crop the page, to skip legal text containing other dates |
| `date_regex` / `time_regex` | override the built-in patterns |
| `ignore_past` | drop dates already in the past (default true) |

Use `python -m slotwatcher dump` to see the text the bot reads and what it detects — that
is the fastest way to get `[parse]` right.

## No repeated alerts

Slots already reported are remembered in `.state/`, so a slot that stays open does not
message you every couple of minutes. If it disappears and comes back, you are told again —
which is the point when you are waiting for a cancellation.

## Secrets

`token = "env:TELEGRAM_TOKEN"` reads from the environment, so a config file stays safe to
commit. `config.toml` and `.state/` are gitignored by default.

If a token ever does reach a public repo, revoke it with `/revoke` in @BotFather —
deleting the commit is not enough, since the history keeps it.

## Please be reasonable

Polling below 30 seconds is refused. Check whether a site's terms permit automated access,
and prefer the gentlest interval that still gets you a slot. This tool watches for
availability and tells you about it — it does not book anything on your behalf.

## Worked example

[`examples/act-schaerbeek.toml`](examples/act-schaerbeek.toml) is the real site this was
built against: a Belgian driving-theory exam centre, with a modal ID form, a checkbox whose
input is invisible, and a category chooser made of identical forms. It is a good model for
anything similarly awkward.

## License

MIT
