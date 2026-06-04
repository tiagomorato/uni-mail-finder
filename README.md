# uni-mail-finder

Telegram notifier for new University of Hildesheim emails over IMAP.

Polls the university IMAP mailbox (`imap.uni-hildesheim.de:993`, SSL) and, for
each newly arrived email, sends a Telegram summary followed by the full email as
a file and any attachments. "New" is determined by the tool's own persistent
state (the highest processed IMAP UID), **not** by the mailbox's read/unread
flags — so reading mail in another client causes neither missed nor duplicate
notifications. It runs unattended via system cron on an always-on server, only
acting within the configured working-hours window.

## Features

- Per-email Telegram **summary** (from / to / cc / subject / time / attachment
  names / body preview), plus the **full email as an `.html` file** (formatting
  preserved) and each **attachment forwarded** as its own file.
- A single compact **digest** (summaries only, no files) when a run finds more
  than `DIGEST_THRESHOLD` new emails at once (e.g. after downtime).
- UID-watermark deduplication with a UIDVALIDITY guard — no replays, no
  duplicates across retries, restarts, or DST transitions.
- Acts only within an inclusive `SCHEDULE_START`–`SCHEDULE_END` window in the
  configured timezone (in-app guard backs up the cron schedule).
- Connection/auth and delivery failures never produce false notifications; the
  watermark advances only for emails whose summary message was delivered.
- Reading is non-destructive (`mark_seen=False`) — notifying never marks mail
  read on the server.
- Secrets (`IMAP_PASSWORD`, `TELEGRAM_BOT_TOKEN`) are never logged or included
  in notifications.

## Requirements

- Python ≥ 3.10 and [`uv`](https://docs.astral.sh/uv/).
- University of Hildesheim IMAP credentials.
- A Telegram bot token (from `@BotFather`) and your chat ID.
- Network access to `imap.uni-hildesheim.de:993` (VPN if required).

## Setup

```bash
git clone <repo-url> uni-mail-finder && cd uni-mail-finder
uv sync                      # installs imap-tools, requests, python-dotenv (+ dev)
cp .env.example .env
# edit .env: set IMAP_PASSWORD, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
```

Run a manual once-cycle (verifies config + connectivity):

```bash
uv run python -m src.main
```

The first run establishes the baseline watermark and sends **no** notifications
for existing mail. Send yourself a test email and run again to confirm a
Telegram message with the sender and subject.

## Configuration

All settings come from environment variables (loaded from `.env`). Required
secrets must be set; everything else has a sensible default. A bad value fails
fast with a message naming the variable (never echoing secrets).

| Variable | Required | Default | Notes |
|----------|----------|---------|-------|
| `IMAP_HOST` | no | `imap.uni-hildesheim.de` | non-empty string |
| `IMAP_PORT` | no | `993` | integer 1–65535 |
| `IMAP_SSL` | no | `true` | `true`/`false` |
| `IMAP_USER` | **yes** | `jdoe` | account login |
| `IMAP_PASSWORD` | **yes** | — | **secret**, never logged |
| `IMAP_FOLDER` | no | `INBOX` | monitored folder |
| `TELEGRAM_BOT_TOKEN` | **yes** | — | **secret**, never logged |
| `TELEGRAM_CHAT_ID` | **yes** | — | destination chat/channel |
| `TIMEZONE` | no | `Europe/Berlin` | IANA name for the window guard |
| `SCHEDULE_START` | no | `08:00` | `HH:MM`, inclusive window start |
| `SCHEDULE_END` | no | `17:00` | `HH:MM`, ≥ `SCHEDULE_START` |
| `DIGEST_THRESHOLD` | no | `10` | batch→digest cutoff (≥ 1) |
| `RUN_MODE` | no | `once` | only `once` is supported |
| `DATA_DIR` | no | `data` | state-file location |

## What you receive in Telegram

For each new email (when fewer than `DIGEST_THRESHOLD` arrive in one run):

1. A **summary message** — sender, recipients (to/cc, when present), subject,
   received time (in `TIMEZONE`), attachment names, and a body preview (up to
   300 chars).
2. The **full email as a file** — the HTML part as a `.html` document (opens with
   formatting in a browser), or a `.txt` document if the email is plain-text only.
3. Each **attachment** forwarded as its own document (the real `.pdf`, `.docx`, …).

```text
📧 New university email
From:    prof@uni-hildesheim.de
Subject: Klausur/Anmeldung
📎 1 attachment(s): Klausur.pdf

Bitte beachten Sie die Anmeldefrist...

[ Klausur_Anmeldung.html ]   ← the full, formatted email
[ Klausur.pdf ]              ← the real attachment
```

File uploads are **best-effort**: the watermark advances once the summary
message is delivered, so a failed file upload (e.g. an attachment over Telegram's
50 MB bot limit) is logged as a warning but never causes the email to be
re-notified. When more than `DIGEST_THRESHOLD` emails arrive at once, a single
compact digest of summaries is sent instead (no files), to avoid flooding.

## Scheduling (cron)

Deployment is driven by **system cron** on the always-on server (`my-server`),
invoking the tool in `RUN_MODE=once`. See
[`deploy/crontab.example`](deploy/crontab.example) for the reference line.

1. **Confirm the host clock is Europe/Berlin** — cron uses the host timezone,
   and this is what keeps the 08:00–17:00 window DST-correct:

   ```bash
   timedatectl    # Time zone should be Europe/Berlin (CET/CEST)
   ```

2. **Install the schedule** with `crontab -e`:

   ```cron
   # Every 30 min, 08:00–17:00 inclusive, Europe/Berlin (host TZ)
   */30 8-17 * * * cd /home/user/uni-mail-finder && /home/user/.local/bin/uv run python -m src.main >> data/cron.log 2>&1
   ```

   `*/30 8-17` fires at `:00` and `:30` for hours 08–17 (final check at 17:00).

The application **also** guards the window internally (`within_window`, using
`zoneinfo`), so even a misconfigured cron or a manual out-of-window invocation
safely does nothing and records `last_status=skipped`. The in-app guard backstops
cron — it does not replace the need for a correct host clock.

## Operations

State lives in `data/state.json` (gitignored): the watermark, the folder's
`UIDVALIDITY`, plus `last_run_at` and `last_status` (`ok` / `error` / `skipped`)
for observability. cron output is appended to `data/cron.log`. Connection or
delivery failures are written to stderr (captured in the log) and exit non-zero
without notifying.

## Development & quality gates

All three MUST pass before any change:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest tests/
```

Tests are split into fully-mocked `tests/unit/` (no network; file I/O via
`tmp_path`) and `tests/e2e/` (the full connect → fetch → diff → notify flow with
the IMAP client faked in-process and the Telegram call mocked via `responses`).
