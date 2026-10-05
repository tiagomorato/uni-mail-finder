"""Unit tests for src.main (window guard, locking, failure handling)."""

import fcntl
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import responses

from src.config import load_config
from src.main import LOCK_FILENAME, run, within_window
from src.storage import ProcessedState, load_state, save_state
from tests.conftest import FakeMailBox, FakeMessage

API = "https://api.telegram.org/botsecret-token/sendMessage"


def _config(**overrides):
    env = {
        "IMAP_USER": "jdoe",
        "IMAP_PASSWORD": "pw",
        "TELEGRAM_BOT_TOKEN": "secret-token",
        "TELEGRAM_CHAT_ID": "99",
    }
    env.update(overrides)
    return load_config(env)


def _berlin(year, month, day, hour, minute):
    return datetime(year, month, day, hour, minute, tzinfo=ZoneInfo("Europe/Berlin"))


def test_inside_window_at_start_boundary():
    cfg = _config(SCHEDULE_START="08:00", SCHEDULE_END="17:00")
    assert within_window(_berlin(2026, 6, 4, 8, 0), cfg) is True


def test_inside_window_at_end_boundary():
    cfg = _config(SCHEDULE_START="08:00", SCHEDULE_END="17:00")
    assert within_window(_berlin(2026, 6, 4, 17, 0), cfg) is True


def test_inside_window_midday():
    cfg = _config()
    assert within_window(_berlin(2026, 6, 4, 12, 30), cfg) is True


def test_outside_window_before_start():
    cfg = _config(SCHEDULE_START="08:00", SCHEDULE_END="17:00")
    assert within_window(_berlin(2026, 6, 4, 7, 59), cfg) is False


def test_outside_window_after_end():
    cfg = _config(SCHEDULE_START="08:00", SCHEDULE_END="17:00")
    assert within_window(_berlin(2026, 6, 4, 17, 30), cfg) is False


def test_window_uses_configured_timezone_for_naive_now():
    # A naive `now` is interpreted in the configured timezone.
    cfg = _config(TIMEZONE="Europe/Berlin")
    assert within_window(datetime(2026, 6, 4, 12, 0), cfg) is True
    assert within_window(datetime(2026, 6, 4, 6, 0), cfg) is False


def test_window_correct_across_dst_summer():
    # June -> CEST (UTC+2). 08:30 Berlin local is inside.
    cfg = _config(SCHEDULE_START="08:00", SCHEDULE_END="17:00")
    assert within_window(_berlin(2026, 6, 4, 8, 30), cfg) is True


def test_window_correct_across_dst_winter():
    # January -> CET (UTC+1). 16:30 Berlin local is inside.
    cfg = _config(SCHEDULE_START="08:00", SCHEDULE_END="17:00")
    assert within_window(_berlin(2026, 1, 15, 16, 30), cfg) is True


def _run_config(data_dir, **overrides):
    env = {
        "IMAP_USER": "jdoe",
        "IMAP_PASSWORD": "pw",
        "TELEGRAM_BOT_TOKEN": "secret-token",
        "TELEGRAM_CHAT_ID": "99",
        "DATA_DIR": data_dir,
        "SCHEDULE_START": "00:00",
        "SCHEDULE_END": "23:59",
    }
    env.update(overrides)
    return load_config(env)


def _msg(uid, subject="hi"):
    return FakeMessage(
        uid=str(uid),
        from_="prof@uni-hildesheim.de",
        subject=subject,
        date=datetime(2026, 6, 4, 12, 0, tzinfo=timezone.utc),
    )


def _seed_state(data_dir, last_uid, uidvalidity=5):
    save_state(
        data_dir,
        ProcessedState(last_processed_uid=last_uid, uidvalidity=uidvalidity),
    )


def test_imap_connect_failure_no_notify_error_status(data_dir):
    _seed_state(data_dir, last_uid=10)
    cfg = _run_config(data_dir)

    def boom():
        raise ConnectionError("cannot reach server")

    rc = run(cfg, mailbox_factory=boom)
    assert rc != 0
    state = load_state(data_dir)
    assert state.last_status == "error"
    assert state.last_processed_uid == 10  # watermark unchanged


@responses.activate
def test_partial_delivery_advances_to_highest_contiguous(data_dir):
    # First send succeeds, second fails -> watermark advances only to the first.
    responses.add(responses.POST, API, json={"ok": True}, status=200)
    responses.add(responses.POST, API, json={"ok": False}, status=500)
    _seed_state(data_dir, last_uid=10)
    cfg = _run_config(data_dir, DIGEST_THRESHOLD="10")
    box = FakeMailBox([_msg(11), _msg(12)], uidvalidity=5)

    rc = run(cfg, mailbox_factory=lambda: box)
    assert rc != 0  # a delivery failed
    state = load_state(data_dir)
    assert state.last_processed_uid == 11
    assert state.last_status == "error"


def test_second_run_skips_on_held_lock(data_dir):
    _seed_state(data_dir, last_uid=10)
    cfg = _run_config(data_dir)
    box = FakeMailBox([_msg(11)], uidvalidity=5)

    # Hold the lock as if another run were in progress.
    lock_path = os.path.join(data_dir, LOCK_FILENAME)
    held = open(lock_path, "w")
    fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        rc = run(cfg, mailbox_factory=lambda: box)
    finally:
        fcntl.flock(held.fileno(), fcntl.LOCK_UN)
        held.close()

    assert rc == 0
    state = load_state(data_dir)
    assert state.last_status == "skipped"
    assert state.last_processed_uid == 10  # untouched
