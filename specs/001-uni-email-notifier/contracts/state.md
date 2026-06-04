# Contract: Persistent State File (`data/state.json`)

The single persisted artifact. Holds the deduplication watermark and run metadata. Lives under
the gitignored `DATA_DIR` (default `data/`). Written atomically (temp file + `os.replace`) so a
crash mid-write cannot corrupt it. Managed exclusively by `storage.py`.

## Schema

```json
{
  "last_processed_uid": 0,
  "uidvalidity": null,
  "folder": "INBOX",
  "last_run_at": null,
  "last_status": null
}
```

| Field | Type | Meaning |
|-------|------|---------|
| `last_processed_uid` | integer ≥ 0 | Highest IMAP UID whose notification was delivered. `0` = nothing processed yet. |
| `uidvalidity` | integer \| null | The folder's `UIDVALIDITY` when the watermark was recorded. `null` before first run. |
| `folder` | string | Monitored folder the watermark applies to (default `INBOX`). |
| `last_run_at` | string (ISO 8601) \| null | When the last run completed. |
| `last_status` | `"ok"` \| `"error"` \| `"skipped"` \| null | Outcome of the last run. |

## Behavioral contract

- **First run** (file absent or `last_processed_uid == 0`, `uidvalidity == null`): establish the
  baseline by setting the watermark to the current mailbox max UID and recording `uidvalidity`.
  Do NOT notify the entire existing mailbox as "new".
- **Normal run**: new = messages with `uid > last_processed_uid` in the current epoch. After each
  successful delivery, advance `last_processed_uid` to that email's UID. Persist after the run.
- **Partial delivery**: advance only to the highest contiguously delivered UID; undelivered
  emails stay new (FR-009).
- **UIDVALIDITY change** (server `UIDVALIDITY` ≠ stored, stored non-null): reset
  `last_processed_uid` to the current mailbox max UID, update `uidvalidity`, record to stderr.
  Never replay the whole mailbox (research §2).
- **Read elsewhere**: state is independent of `\Seen`; reading mail in another client does not
  change `last_processed_uid` (Edge Case "Read on another device").
- **Atomic write**: serialize to a temp file in `DATA_DIR`, then `os.replace` onto `state.json`.
- **`skipped`/`error` runs**: update `last_run_at`/`last_status` for observability but leave
  `last_processed_uid` unchanged.
