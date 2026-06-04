"""Entry point: the once-run check cycle (RUN_MODE=once).

Flow: load config -> load state -> window guard -> acquire run lock -> connect ->
reconcile UIDVALIDITY -> establish the first-run baseline (no replay) or fetch
new mail -> render and deliver notifications -> advance the watermark only for
delivered messages -> persist state. Connection/auth and delivery failures are
logged to stderr (without secrets), produce no false notifications, exit
non-zero, and leave the watermark at the highest contiguously delivered UID so
nothing is missed or duplicated. Designed for ``RUN_MODE=once`` under cron.
"""

from __future__ import annotations

import fcntl
import os
import sys
from contextlib import contextmanager
from datetime import datetime

from src import mailbox, notifier, storage

LOCK_FILENAME = ".lock"


def within_window(now: datetime, config) -> bool:
    """Whether ``now`` falls within the inclusive schedule window (FR-005).

    A naive ``now`` is interpreted in the configured timezone; an aware ``now``
    is converted to it, so the comparison is DST-correct via ``zoneinfo``.
    """
    if now.tzinfo is None:
        now = now.replace(tzinfo=config.timezone)
    else:
        now = now.astimezone(config.timezone)
    current = now.timetz().replace(tzinfo=None)
    return config.schedule_start <= current <= config.schedule_end


@contextmanager
def _run_lock(data_dir):
    """Non-blocking run lock under ``data_dir``.

    Yields True if the lock was acquired, False if another run already holds it
    (the new run should then skip). Prevents overlapping runs from colliding.
    """
    os.makedirs(data_dir, exist_ok=True)
    path = os.path.join(data_dir, LOCK_FILENAME)
    fh = open(path, "w")
    try:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            yield False
            return
        yield True
    finally:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        finally:
            fh.close()


def _deliver(notifications, config) -> tuple[int | None, bool]:
    """Deliver notifications in order, advancing only while they succeed.

    Returns ``(highest_delivered_uid, all_delivered)``. The watermark may only
    advance to the highest *contiguously* delivered UID so that an undelivered
    email stays new for the next run (FR-009).
    """
    highest = None
    all_delivered = True
    for note in notifications:
        if notifier.send(note, config):
            highest = max(note.covers_uids)
        else:
            all_delivered = False
            print(
                "Telegram delivery failed; leaving email(s) pending for retry",
                file=sys.stderr,
            )
            break
    return highest, all_delivered


def _check_cycle(config, factory, state) -> int:
    """The connect→fetch→notify body. Returns an exit code."""
    with factory() as client:
        server_uidvalidity = mailbox.get_uidvalidity(client)
        max_uid = mailbox.mailbox_max_uid(client)

        first_run = state.is_first_run
        reset = storage.apply_uidvalidity(state, server_uidvalidity, max_uid)
        if reset:
            print(
                "UIDVALIDITY changed; reset watermark to current mailbox max "
                f"({max_uid}) without replaying mail",
                file=sys.stderr,
            )

        if first_run:
            # Establish the baseline; do not notify existing mail as new.
            state.last_processed_uid = max_uid
            storage.mark_run(state, "ok")
            storage.save_state(config.data_dir, state)
            return 0

        emails = mailbox.fetch_new(client, state.last_processed_uid)

    notifications = notifier.build_notifications(emails, config)
    highest, all_delivered = _deliver(notifications, config)
    if highest is not None:
        state.last_processed_uid = highest

    storage.mark_run(state, "ok" if all_delivered else "error")
    storage.save_state(config.data_dir, state)
    return 0 if all_delivered else 1


def run(config, *, mailbox_factory=None, now=None) -> int:
    """Execute one check cycle. Returns a process exit code (0 ok)."""
    factory = mailbox_factory or (lambda: mailbox.open_mailbox(config))
    state = storage.load_state(config.data_dir, config.imap_folder)

    now = now or datetime.now(config.timezone)
    if not within_window(now, config):
        # Outside the window: do nothing, no fetch, no notify (FR-005).
        storage.mark_run(state, "skipped")
        storage.save_state(config.data_dir, state)
        return 0

    with _run_lock(config.data_dir) as acquired:
        if not acquired:
            # Another run is in progress; skip without touching the watermark.
            storage.mark_run(state, "skipped")
            storage.save_state(config.data_dir, state)
            return 0

        try:
            return _check_cycle(config, factory, state)
        except Exception as exc:  # connect/auth/fetch failure
            # Never echo secrets; report the error type and message only.
            print(f"Run failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            storage.mark_run(state, "error")
            storage.save_state(config.data_dir, state)
            return 1


def main() -> int:
    from src.config import ConfigError, load_config

    try:
        config = load_config()
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return run(config)


if __name__ == "__main__":
    sys.exit(main())
