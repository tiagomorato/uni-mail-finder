# Contract: Telegram Notification Format

Defines the message(s) the tool sends to the user via the Telegram Bot API. Delivery is a direct
HTTP `POST` to `https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/sendMessage` with
`chat_id=<TELEGRAM_CHAT_ID>`. One-directional (system → user); no inline commands.

## Single-email message (default: ≤ `DIGEST_THRESHOLD` new emails)

One message per new email. Required content: **sender** and **subject** (FR-003); received time
included for context.

```text
📧 New university email

From:    <sender>
Subject: <subject>
Time:    <received_at, Europe/Berlin, e.g. 2026-06-04 14:32>
```

- `<sender>` falls back to `(unknown sender)` when missing/undecodable (FR-010).
- `<subject>` falls back to `(no subject)` when empty/missing (FR-010).
- German/English characters (umlauts, etc.) MUST render correctly; text is escaped per the
  chosen `parse_mode` (or sent as plain text) so special characters never break delivery.

## Digest message (> `DIGEST_THRESHOLD` new emails in one run)

A single summarizing message instead of flooding (Edge Case "Many emails at once", FR-011).

```text
📬 <N> new university emails

1. <sender> — <subject>
2. <sender> — <subject>
...
<N>. <sender> — <subject>
```

- Lists every new email's sender + subject; none omitted (FR-011). May truncate overly long
  subjects with an ellipsis for readability.

## Delivery contract

- A notification is **delivered** only on a Telegram 2xx response.
- On non-2xx or network error: log the failure to stderr (without secrets), do NOT mark
  delivered, and do NOT advance the UID watermark past the undelivered email — it remains new
  for the next run (FR-009, Story 3 §3).
- Notification text MUST NEVER contain `IMAP_PASSWORD` or `TELEGRAM_BOT_TOKEN` (FR-007).
- No notification is ever sent outside the 08:00–17:00 Europe/Berlin window (FR-005) or when no
  new emails exist (Story 1 §3).
