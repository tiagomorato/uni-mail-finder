"""Unit tests for src.storage."""

import json

from src.storage import (
    ProcessedState,
    apply_uidvalidity,
    load_state,
    mark_run,
    new_uids,
    save_state,
)


def test_first_run_baseline_when_file_absent(tmp_path):
    state = load_state(str(tmp_path))
    assert state.is_first_run
    assert state.last_processed_uid == 0
    assert state.uidvalidity is None
    # First run must not treat the existing mailbox as new: diff against 0 only
    # returns genuinely higher UIDs, but the flow sets the baseline instead.
    assert new_uids(state, [1, 2, 3]) == [1, 2, 3]


def test_normal_diff_returns_only_above_watermark():
    state = ProcessedState(last_processed_uid=100)
    assert new_uids(state, [98, 100, 101, 105]) == [101, 105]


def test_diff_is_sorted_ascending():
    state = ProcessedState(last_processed_uid=0)
    assert new_uids(state, [5, 1, 3, 2, 4]) == [1, 2, 3, 4, 5]


def test_save_then_load_roundtrip(tmp_path):
    state = ProcessedState(
        last_processed_uid=42,
        uidvalidity=999,
        folder="INBOX",
        last_run_at="2026-06-04T10:00:00+00:00",
        last_status="ok",
    )
    save_state(str(tmp_path), state)
    loaded = load_state(str(tmp_path))
    assert loaded == state


def test_atomic_write_leaves_no_temp_file(tmp_path):
    save_state(str(tmp_path), ProcessedState(last_processed_uid=7))
    files = {p.name for p in tmp_path.iterdir()}
    assert files == {"state.json"}
    # File is valid JSON.
    data = json.loads((tmp_path / "state.json").read_text())
    assert data["last_processed_uid"] == 7


def test_save_creates_missing_data_dir(tmp_path):
    nested = tmp_path / "deep" / "data"
    save_state(str(nested), ProcessedState(last_processed_uid=1))
    assert (nested / "state.json").exists()


def test_skipped_run_leaves_watermark_unchanged():
    state = ProcessedState(last_processed_uid=50, uidvalidity=1)
    mark_run(state, "skipped")
    assert state.last_processed_uid == 50
    assert state.uidvalidity == 1
    assert state.last_status == "skipped"
    assert state.last_run_at is not None


def test_error_run_leaves_watermark_unchanged():
    state = ProcessedState(last_processed_uid=50)
    mark_run(state, "error")
    assert state.last_processed_uid == 50
    assert state.last_status == "error"


def test_uidvalidity_first_run_records_without_reset():
    state = ProcessedState(last_processed_uid=0, uidvalidity=None)
    reset = apply_uidvalidity(state, server_uidvalidity=123, mailbox_max_uid=900)
    assert reset is False
    assert state.uidvalidity == 123
    assert state.last_processed_uid == 0


def test_uidvalidity_unchanged_no_reset():
    state = ProcessedState(last_processed_uid=50, uidvalidity=123)
    reset = apply_uidvalidity(state, server_uidvalidity=123, mailbox_max_uid=900)
    assert reset is False
    assert state.last_processed_uid == 50


def test_uidvalidity_changed_resets_to_mailbox_max():
    # Stored epoch differs from server -> reset watermark to current max,
    # adopt the new uidvalidity, and do NOT replay the mailbox.
    state = ProcessedState(last_processed_uid=50, uidvalidity=123)
    reset = apply_uidvalidity(state, server_uidvalidity=456, mailbox_max_uid=900)
    assert reset is True
    assert state.last_processed_uid == 900
    assert state.uidvalidity == 456
