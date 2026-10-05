"""End-to-end flow tests: connect -> fetch -> diff -> notify -> watermark.

The IMAP client is faked in-process; the Telegram HTTP call is mocked via
``responses``. No real network is used.
"""

from datetime import datetime, timezone

import responses

from src.config import load_config
from src.main import run
from src.storage import load_state
from tests.conftest import FakeMailBox, FakeMessage

API = "https://api.telegram.org/botsecret-token/sendMessage"


def _config(data_dir, **overrides):
    env = {
        "IMAP_USER": "jdoe",
        "IMAP_PASSWORD": "pw",
        "TELEGRAM_BOT_TOKEN": "secret-token",
        "TELEGRAM_CHAT_ID": "99",
        "DATA_DIR": data_dir,
        # Always inside the window for deterministic e2e.
        "SCHEDULE_START": "00:00",
        "SCHEDULE_END": "23:59",
    }
    env.update(overrides)
    return load_config(env)


def _msg(uid, subject="hello"):
    return FakeMessage(
        uid=str(uid),
        from_="prof@uni-hildesheim.de",
        subject=subject,
        date=datetime(2026, 6, 4, 12, 0, tzinfo=timezone.utc),
    )


@responses.activate
def test_happy_path_baseline_then_notify(data_dir):
    responses.add(responses.POST, API, json={"ok": True}, status=200)
    cfg = _config(data_dir)

    # First run: baseline established from existing mail, no notifications.
    box1 = FakeMailBox([_msg(1), _msg(2), _msg(3)], uidvalidity=5)
    rc = run(cfg, mailbox_factory=lambda: box1)
    assert rc == 0
    assert len(responses.calls) == 0

    state = load_state(data_dir)
    assert state.last_processed_uid == 3
    assert state.uidvalidity == 5
    assert state.last_status == "ok"

    # Second run: one genuinely new email -> exactly one Telegram message.
    box2 = FakeMailBox([_msg(1), _msg(2), _msg(3), _msg(4, "NEW")], uidvalidity=5)
    rc = run(cfg, mailbox_factory=lambda: box2)
    assert rc == 0
    assert len(responses.calls) == 1
    assert "NEW" in responses.calls[0].request.body.decode("utf-8")

    state = load_state(data_dir)
    assert state.last_processed_uid == 4

    # Third run: no new mail -> no notification, watermark unchanged.
    rc = run(cfg, mailbox_factory=lambda: box2)
    assert rc == 0
    assert len(responses.calls) == 1
    assert load_state(data_dir).last_processed_uid == 4


class _FailingFactory:
    """Mailbox factory that raises on connect, as if the server is unreachable."""

    def __call__(self):
        raise ConnectionError("connection refused")


@responses.activate
def test_failure_then_recovery(data_dir):
    responses.add(responses.POST, API, json={"ok": True}, status=200)
    cfg = _config(data_dir)

    # Baseline established from existing mail.
    box = FakeMailBox([_msg(1), _msg(2)], uidvalidity=5)
    assert run(cfg, mailbox_factory=lambda: box) == 0
    assert load_state(data_dir).last_processed_uid == 2
    assert len(responses.calls) == 0

    # New mail arrives, but the server is unreachable: no notify, state intact.
    rc = run(cfg, mailbox_factory=_FailingFactory())
    assert rc != 0
    assert len(responses.calls) == 0
    state = load_state(data_dir)
    assert state.last_status == "error"
    assert state.last_processed_uid == 2  # unchanged

    # Service recovers: only genuinely new mail (uid 3) is notified, not old.
    box2 = FakeMailBox([_msg(1), _msg(2), _msg(3, "NEW")], uidvalidity=5)
    rc = run(cfg, mailbox_factory=lambda: box2)
    assert rc == 0
    assert len(responses.calls) == 1
    assert "NEW" in responses.calls[0].request.body.decode("utf-8")
    assert load_state(data_dir).last_processed_uid == 3
