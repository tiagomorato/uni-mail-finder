# Contract: Configuration (Environment Variables)

The tool's external configuration interface. All values come from environment variables (loaded
from `.env` via `python-dotenv`). `config.py` MUST validate these at startup and fail fast with a
human-readable stderr error naming the offending variable, without echoing secret values.

## Variables

| Variable | Required | Default | Validation |
|----------|----------|---------|------------|
| `IMAP_HOST` | no | `mailf1.rz.uni-hildesheim.de` | non-empty string |
| `IMAP_PORT` | no | `993` | integer 1–65535 |
| `IMAP_SSL` | no | `true` | boolean (`true`/`false`) |
| `IMAP_USER` | **yes** | — | non-empty string |
| `IMAP_PASSWORD` | **yes** | — | non-empty; **secret**, never logged |
| `IMAP_FOLDER` | no | `INBOX` | non-empty string |
| `TELEGRAM_BOT_TOKEN` | **yes** | — | non-empty; **secret**, never logged |
| `TELEGRAM_CHAT_ID` | **yes** | — | non-empty string |
| `TIMEZONE` | no | `Europe/Berlin` | resolvable IANA name via `zoneinfo` |
| `SCHEDULE_START` | no | `08:00` | `HH:MM`, 00:00–23:59 |
| `SCHEDULE_END` | no | `17:00` | `HH:MM`, ≥ `SCHEDULE_START` |
| `DIGEST_THRESHOLD` | no | `10` | integer ≥ 1 |
| `RUN_MODE` | no | `once` | must equal `once` |
| `DATA_DIR` | no | `data` | writable directory path |

## Behavioral contract

- Missing/empty required variable → exit non-zero with `Configuration error: <VAR> is required`.
- Invalid value → `Configuration error: <VAR> is invalid (<reason>)`.
- Error messages MUST NOT include the values of `IMAP_PASSWORD` or `TELEGRAM_BOT_TOKEN`.
- On success, `config.py` returns a frozen/immutable config object consumed by all other modules.
- Every variable above MUST appear in `.env.example` and the README configuration table.

## `.env.example` (authoritative template)

```dotenv
# IMAP (University of Hildesheim)
IMAP_HOST=mailf1.rz.uni-hildesheim.de
IMAP_PORT=993
IMAP_SSL=true
IMAP_USER=              # required
IMAP_PASSWORD=            # required secret
IMAP_FOLDER=INBOX

# Telegram
TELEGRAM_BOT_TOKEN=       # required secret
TELEGRAM_CHAT_ID=         # required

# Schedule (Europe/Berlin, inclusive window)
TIMEZONE=Europe/Berlin
SCHEDULE_START=08:00
SCHEDULE_END=17:00

# Behavior
DIGEST_THRESHOLD=10
RUN_MODE=once
DATA_DIR=data
```
