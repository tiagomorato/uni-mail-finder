# Phase 1 Data Model: Uni Hildesheim Email Notifier

Derived from the spec's Key Entities and Functional Requirements. This is a small, file-based
system: there is no database. Entities are in-memory dataclasses plus one persisted JSON state
file.

## Entity: EmailMessage (in-memory)

A message fetched from INBOX that is a candidate for notification.

| Field | Type | Source / Rules |
|-------|------|----------------|
| `uid` | int | IMAP UID within the current UIDVALIDITY epoch. Primary dedup key (FR-002). |
| `sender` | str | Decoded `From`. Fallback `(unknown sender)` if missing/undecodable (FR-010). |
| `subject` | str | Decoded `Subject`. Fallback `(no subject)` if empty/missing (FR-010). |
| `received_at` | datetime | IMAP `Date` (INTERNALDATE/header). Used in notification text. |

- **Validation**: `uid` MUST be a positive integer. `sender`/`subject` are always coerced to a
  non-empty display string via fallbacks — parsing MUST NOT raise on malformed headers.
- **Ordering**: Messages are processed in ascending `uid` order so the watermark advances
  monotonically (FR-002, FR-009, FR-011).
- **Lifecycle**: Transient — built per run from the fetch, never persisted.

## Entity: Notification (in-memory)

A Telegram message describing one new email (or a digest of many).

| Field | Type | Rules |
|-------|------|-------|
| `text` | str | Rendered from one EmailMessage (sender, subject, time) or a digest summary. MUST NOT contain secrets (FR-007). |
| `covers_uids` | list[int] | The UID(s) this notification reports; the watermark may advance to `max(covers_uids)` only after delivery succeeds. |
| `delivered` | bool | Set true only on a 2xx Telegram response (FR-009, Story 3 §3). |

- **Single vs digest**: ≤ threshold new emails → one Notification per email. > threshold →
  one digest Notification covering the batch (Edge Case "Many emails at once", FR-011).

## Entity: ProcessedState (persisted — `data/state.json`)

The single source of truth for "what is new." One JSON object.

| Field | Type | Rules |
|-------|------|-------|
| `last_processed_uid` | int | Highest UID whose notification was delivered. `0` before first successful run. Advances only on delivery. |
| `uidvalidity` | int \| null | IMAP `UIDVALIDITY` of the folder when `last_processed_uid` was recorded. `null` before first run. |
| `folder` | str | Monitored folder, default `INBOX`. Scopes the watermark. |
| `last_run_at` | str (ISO 8601) | Timestamp of the last completed run (observability). |
| `last_status` | str | `ok` \| `error` \| `skipped` — last run outcome (observability, FR-008). |

- **UIDVALIDITY epoch rule**: If the server's current `UIDVALIDITY` ≠ stored `uidvalidity`
  (and stored is non-null), reset `last_processed_uid` to the current mailbox max UID, set
  `uidvalidity` to the new value, and record the reset — do NOT replay all mail as new
  (research §2).
- **Persistence**: Compact JSON under gitignored `data/` (Principle IV). Written atomically
  (temp file + rename) so a crash mid-write cannot corrupt state.
- **Diff**: "new" = messages with `uid > last_processed_uid` in the matching epoch.

## Entity: Configuration (in-memory, from env)

Loaded and validated by `config.py` at startup; fail-fast on missing/invalid (FR-012, Principle III).

| Variable | Type | Required | Default | Notes |
|----------|------|----------|---------|-------|
| `IMAP_HOST` | str | no | `mailf1.rz.uni-hildesheim.de` | |
| `IMAP_PORT` | int | no | `993` | |
| `IMAP_SSL` | bool | no | `true` | |
| `IMAP_USER` | str | yes | `jdoe` | account login |
| `IMAP_PASSWORD` | str (secret) | yes | — | never logged (FR-007) |
| `IMAP_FOLDER` | str | no | `INBOX` | |
| `TELEGRAM_BOT_TOKEN` | str (secret) | yes | — | never logged (FR-007) |
| `TELEGRAM_CHAT_ID` | str | yes | — | destination chat/channel |
| `TIMEZONE` | str | no | `Europe/Berlin` | IANA name for window guard |
| `SCHEDULE_START` | str `HH:MM` | no | `08:00` | inclusive window start |
| `SCHEDULE_END` | str `HH:MM` | no | `17:00` | inclusive window end |
| `DIGEST_THRESHOLD` | int | no | `10` | batch→digest cutoff |
| `RUN_MODE` | str | no | `once` | only `once` supported |
| `DATA_DIR` | str | no | `data` | state location |

- **Validation rules**: required secrets present and non-empty; `IMAP_PORT`/`DIGEST_THRESHOLD`
  parse as int; `TIMEZONE` resolvable via `zoneinfo`; `SCHEDULE_START`/`SCHEDULE_END` parse as
  `HH:MM` and start ≤ end. Any failure → human-readable stderr message naming the variable,
  non-zero exit (Principle III). Validation MUST NOT echo secret values.

## Relationships

```text
Configuration ──drives──> mailbox fetch ──produces──> EmailMessage[]
EmailMessage[] ──diff against──> ProcessedState.last_processed_uid ──> new EmailMessage[]
new EmailMessage[] ──render──> Notification[] ──deliver──> Telegram
delivered Notification ──advances──> ProcessedState.last_processed_uid (persisted)
```

## State transitions (per run)

1. `skipped` — outside window OR lock held → exit, write `last_status=skipped`, no fetch.
2. `error` — IMAP connect/auth fails OR all deliveries fail → no watermark advance,
   `last_status=error`, non-zero exit (FR-008, SC-005).
3. `ok` — fetched, every found new email delivered (or none found) → watermark advanced to the
   highest delivered UID, `last_status=ok`.
4. **Partial delivery** — some emails delivered, a later one fails → watermark advances only to
   the highest contiguous *delivered* UID; undelivered emails remain new for the next run
   (FR-009, Story 3 §3).
