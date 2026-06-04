# Phase 0 Research: Uni Hildesheim Email Notifier

All Technical Context unknowns are resolved below. Decisions favor consistency with the sibling
tools (`lsf-grade-finder`, `learnweb-content-finder`) and the constitution, deviating only where
the IMAP protocol or the local-server deployment makes the family default inapplicable.

## 1. IMAP access library

- **Decision**: Use the `imap-tools` package for connecting, searching, and fetching messages;
  use its parsed-message API for sender/subject/UID/date and encoding handling.
- **Rationale**: IMAP UID semantics and MIME header decoding are easy to get subtly wrong with
  raw `imaplib`+`email`. `imap-tools` exposes UIDs directly, supports `UID > N` style fetching,
  and returns already-decoded `from_`, `subject`, `uid`, and `date` fields, directly serving
  FR-002 (UID-based dedup), FR-009 (no duplicates), and FR-010 (malformed/encoded fields).
- **Alternatives considered**:
  - Stdlib `imaplib` + `email`: zero dependency, but forces hand-rolled UID parsing and
    RFC 2047 header decoding — fragile and bug-prone for exactly the cases FR-010 calls out.
  - `imapclient`: capable, but `imap-tools` has a higher-level parsed-message API with less
    boilerplate for this read-only use case.

## 2. Determining "new" emails (deduplication)

- **Decision**: Persist the highest IMAP **UID** successfully processed in INBOX. On each run,
  fetch only messages with `UID > last_processed_uid`, notify them in ascending UID order, and
  advance the watermark only after a message's notification is delivered.
- **Rationale**: IMAP UIDs are monotonically increasing and stable within a `UIDVALIDITY` epoch,
  making them the canonical "what's new" cursor independent of read/unread flags (Assumptions;
  FR-002). Advancing the watermark only after successful delivery satisfies FR-009 and the
  Story 3 requirement that a Telegram failure leaves the email pending for the next run.
- **UIDVALIDITY guard**: Store `UIDVALIDITY` alongside the UID. If the server reports a different
  `UIDVALIDITY` than stored, treat UIDs as a new epoch: reset the watermark to the current
  mailbox max (do **not** replay the whole mailbox as "new") and record the event to stderr.
- **Alternatives considered**:
  - Relying on the `\Seen` flag: rejected — reading mail in webmail/another client would mark
    messages seen and cause missed notifications (Edge Case "Read on another device").
  - Tracking a set of all notified Message-IDs: rejected — unbounded growth and slower diffs vs.
    a single integer watermark; UID watermark is O(1) state.

## 3. Scheduling and the 08:00–17:00 Europe/Berlin window

- **Decision**: System cron on `my-server` (host TZ Europe/Berlin) with the line
  `*/30 8-17 * * * <runner>`, invoking the tool in `RUN_MODE=once`. The program additionally
  performs a defensive window check on startup and exits without notifying if invoked outside
  08:00–17:00 Europe/Berlin.
- **Rationale**: cron with a Europe/Berlin host clock honors local time including CET/CEST DST
  transitions automatically (SC-004, Edge Case "Daylight Saving Time"). `*/30 8-17` fires at
  :00 and :30 for hours 08–17 inclusive, giving the final check at 17:00 (FR-004, Story 2
  scenarios 1–2). The in-app guard makes FR-005 hold even if cron is misconfigured and uses
  `zoneinfo` (stdlib) for a timezone-correct comparison.
- **Alternatives considered**:
  - A long-running `loop` daemon that self-schedules: rejected — duplicates cron, adds idle
    process + sleep-drift/signal complexity with no consuming deployment (Complexity Tracking).
  - Cron in UTC with offset math: rejected — breaks across DST; relying on the OS TZ database is
    simpler and correct.

## 4. Overlapping / long runs

- **Decision**: Guard each run with a non-blocking lock on a file under `data/` (e.g.
  `flock`-style or an OS-level file lock). If a previous run still holds the lock, the new run
  exits immediately without action.
- **Rationale**: Satisfies Edge Case "Overlapping runs": a slow check cannot collide with or
  duplicate the next scheduled invocation. A 30-minute cadence makes contention rare, so a
  simple skip-if-locked policy is sufficient.
- **Alternatives considered**: queueing the second run (unnecessary complexity); relying on runs
  always finishing in time (unsafe if the mail server is slow).

## 5. Notification format & batching

- **Decision**: One Telegram message per new email by default, containing sender and subject
  (and received time). When a single run finds more than a threshold (default 10) new emails
  (e.g. after server downtime), send a compact digest summarizing them instead of flooding.
- **Rationale**: Meets FR-003 (sender + subject per email) and the Edge Case "Many emails at
  once"/FR-011 (process all, stay readable). Threshold is configurable.
- **Encoding/fallbacks**: Missing subject → `(no subject)`; undecodable sender → raw address or
  `(unknown sender)`. Render via Telegram with text escaping so German umlauts and special
  characters display correctly (FR-010, Assumptions: English + German).
- **Alternatives considered**: always-digest (loses per-email immediacy); always one-per-email
  (floods after downtime). The threshold hybrid covers both.

## 6. Telegram delivery

- **Decision**: Direct HTTP `POST` to `https://api.telegram.org/bot<token>/sendMessage` via
  `requests` (constitution: no heavyweight wrapper). Treat non-2xx / network errors as delivery
  failure: do **not** advance the UID watermark past an undelivered message; log to stderr.
- **Rationale**: Matches Principle III and the sibling tools; keeps the failure-retry guarantee
  of Story 3 scenario 3 (FR-009).
- **Alternatives considered**: `python-telegram-bot` wrapper — rejected per constitution
  (heavyweight, async machinery unnecessary for one-directional sends).

## 7. Configuration & secrets

- **Decision**: All settings via environment variables loaded from `.env` (`python-dotenv`),
  validated in `config.py` with fail-fast human-readable errors. Secrets (mailbox password,
  bot token) are read from env only, never logged, never placed in notification content
  (FR-007, FR-012). `.env` and `data/` are gitignored.
- **Known non-secret defaults** (from the user's mail client): `IMAP_HOST=mailf1.rz.uni-hildesheim.de`,
  `IMAP_PORT=993`, `IMAP_SSL=true`, `IMAP_USER=jdoe`, `IMAP_FOLDER=INBOX`,
  `SCHEDULE_START=08:00`, `SCHEDULE_END=17:00`, `TIMEZONE=Europe/Berlin`.
- **Rationale**: Identical config ritual to the family (Principle III); SC-006 (setup < 30 min).
- **Alternatives considered**: a config file format (YAML/TOML) — rejected for family
  consistency with `.env`.

## 8. Failure handling & observability

- **Decision**: Connection/auth failures and Telegram failures are caught, logged to stderr with
  a non-zero exit, and never produce a "new email" notification. The UID watermark only advances
  for emails whose notification succeeded, so recovery resumes cleanly.
- **Rationale**: FR-008, Story 3 scenarios 1–3, SC-005. Operator can read cron mail / journald
  for stderr output.
- **Alternatives considered**: sending a Telegram alert on failure — out of scope for v1 (could
  re-notify storms during an outage); stderr logging is the minimal observable surface.

## Resolved unknowns summary

| Unknown | Resolution |
|---------|-----------|
| IMAP library | `imap-tools` |
| Dedup mechanism | Highest processed UID watermark + UIDVALIDITY guard, in JSON state |
| Scheduling | System cron `*/30 8-17` @ Europe/Berlin + in-app window guard (`zoneinfo`) |
| Overlap protection | Skip-if-locked file lock under `data/` |
| Batching | One message/email; digest above configurable threshold (default 10) |
| Telegram | Direct `requests` POST to Bot API `sendMessage` |
| Config/secrets | `.env` + `python-dotenv`, validated in `config.py`, gitignored |
| Failure model | Log to stderr, no false notify, advance watermark only on delivered |
