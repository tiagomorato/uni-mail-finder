"""Persistent deduplication state.

Manages ``<DATA_DIR>/state.json`` per
``specs/001-uni-email-notifier/contracts/state.md``: the highest processed IMAP
UID watermark plus run metadata. Writes are atomic (temp file + ``os.replace``)
so a crash mid-write cannot corrupt the file. This module is the sole owner of
the state file.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

STATE_FILENAME = "state.json"

_VALID_STATUSES = frozenset({"ok", "error", "skipped"})


@dataclass
class ProcessedState:
    """The persisted deduplication watermark and last-run metadata."""

    last_processed_uid: int = 0
    uidvalidity: int | None = None
    folder: str = "INBOX"
    last_run_at: str | None = None
    last_status: str | None = None

    @property
    def is_first_run(self) -> bool:
        """True before any baseline has been established."""
        return self.last_processed_uid == 0 and self.uidvalidity is None


def _state_path(data_dir: str) -> str:
    return os.path.join(data_dir, STATE_FILENAME)


def load_state(data_dir: str, folder: str = "INBOX") -> ProcessedState:
    """Load state from ``<data_dir>/state.json``.

    Returns a default :class:`ProcessedState` (first-run baseline) when the file
    is absent.
    """
    path = _state_path(data_dir)
    if not os.path.exists(path):
        return ProcessedState(folder=folder)
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    return ProcessedState(
        last_processed_uid=int(raw.get("last_processed_uid", 0)),
        uidvalidity=raw.get("uidvalidity"),
        folder=raw.get("folder", folder),
        last_run_at=raw.get("last_run_at"),
        last_status=raw.get("last_status"),
    )


def save_state(data_dir: str, state: ProcessedState) -> None:
    """Atomically persist ``state`` to ``<data_dir>/state.json``."""
    os.makedirs(data_dir, exist_ok=True)
    path = _state_path(data_dir)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(asdict(state), fh, separators=(",", ":"))
    os.replace(tmp_path, path)


def new_uids(state: ProcessedState, uids) -> list[int]:
    """Return UIDs strictly greater than the watermark, ascending."""
    return sorted(uid for uid in uids if uid > state.last_processed_uid)


def mark_run(state: ProcessedState, status: str) -> None:
    """Record run outcome without touching the watermark.

    Sets ``last_run_at`` to now (UTC, ISO 8601) and ``last_status``. Used for
    ``skipped``/``error`` runs and as the final stamp on ``ok`` runs.
    """
    if status not in _VALID_STATUSES:
        raise ValueError(f"invalid status: {status}")
    state.last_run_at = datetime.now(timezone.utc).isoformat()
    state.last_status = status


def apply_uidvalidity(
    state: ProcessedState, server_uidvalidity: int, mailbox_max_uid: int
) -> bool:
    """Reconcile the stored UIDVALIDITY with the server's.

    First run (``uidvalidity is None``): record the server value without
    resetting (the caller establishes the baseline watermark separately).

    Changed epoch (stored non-null and differs): reset the watermark to the
    current mailbox max UID and adopt the new ``uidvalidity`` so the mailbox is
    not replayed as new (research §2).

    Returns:
        True if a UIDVALIDITY-change reset occurred, else False.
    """
    if state.uidvalidity is None:
        state.uidvalidity = server_uidvalidity
        return False
    if state.uidvalidity != server_uidvalidity:
        state.last_processed_uid = mailbox_max_uid
        state.uidvalidity = server_uidvalidity
        return True
    return False
