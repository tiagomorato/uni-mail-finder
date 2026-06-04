# Quickstart: Uni Hildesheim Email Notifier

Get the notifier running on `my-server` in under 30 minutes (SC-006).

## Prerequisites

- Python ≥ 3.10 and [`uv`](https://docs.astral.sh/uv/) on `my-server`.
- University of Hildesheim IMAP credentials (account `jdoe`, mailbox password).
- A Telegram bot token (from `@BotFather`) and your chat ID.
- Network access from `my-server` to `mailf1.rz.uni-hildesheim.de:993` (VPN if required).

## 1. Install

```bash
ssh user@my-server
git clone <repo-url> uni-mail-finder && cd uni-mail-finder
uv sync                      # installs imap-tools, requests, python-dotenv (+ dev)
```

## 2. Configure

```bash
cp .env.example .env
# edit .env: set IMAP_PASSWORD, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
```

Non-secret defaults (host, port, user `jdoe`, window 08:00–17:00 Europe/Berlin) are already
filled in. See `contracts/config.md` for every variable.

## 3. Verify configuration & connectivity (manual once-run)

```bash
uv run python -m src.main          # RUN_MODE=once
```

- First run establishes the baseline watermark and sends **no** notifications for existing mail.
- A config mistake fails fast with a message naming the variable (no stack trace, no secrets).
- Send yourself a test email, run again, and confirm a Telegram message with sender + subject.

## 4. Confirm the host clock is Europe/Berlin

```bash
timedatectl    # Time zone should be Europe/Berlin (CET/CEST)
```

cron uses the host timezone, so this is what keeps the 08:00–17:00 window DST-correct (SC-004).

## 5. Install the cron schedule

Use `deploy/crontab.example` as the reference. Add to the user's crontab (`crontab -e`):

```cron
# Uni mail notifier: every 30 min, 08:00–17:00 inclusive, Europe/Berlin (host TZ)
*/30 8-17 * * * cd /home/user/uni-mail-finder && /home/user/.local/bin/uv run python -m src.main >> data/cron.log 2>&1
```

`*/30 8-17` fires at :00 and :30 for hours 08–17 (final check 17:00). The program also guards the
window internally, so an out-of-window invocation safely does nothing.

## 6. Validate

- Watch `data/cron.log` and `data/state.json` (`last_run_at`, `last_status`) over a day.
- Confirm: notifications only within the window (SC-004), one per new email, no duplicates across
  runs/restarts (SC-002), and no false "new email" alerts when the mail server is unreachable
  (SC-005 — test by temporarily breaking connectivity).

## Quality gates (before any change)

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest tests/
```

All three MUST pass (constitution Development Workflow & Quality Gates).
