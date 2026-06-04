"""Shared pytest fixtures.

Provides a tmp ``DATA_DIR``/state path, representative sample message data
(including a missing subject and an umlaut/encoded sender), and an in-process
fake IMAP client matching the subset of the ``imap-tools`` ``MailBox`` API used
by ``src.mailbox`` (``uids()``, ``fetch()``, ``folder.status()``). No real
network is ever touched.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest


@dataclass
class FakeMessage:
    """Mimics ``imap_tools`` ``MailMessage`` (uid is a string, as upstream)."""

    uid: str
    from_: str
    subject: str
    date: datetime


class _FakeFolderManager:
    def __init__(self, uidvalidity: int):
        self._uidvalidity = uidvalidity

    def status(self, folder=None, options=None) -> dict:
        return {"UIDVALIDITY": self._uidvalidity}


class FakeMailBox:
    """In-process stand-in for ``imap_tools.MailBox``.

    Yields all stored messages on ``fetch`` regardless of criteria; ``mailbox``
    code is responsible for the UID diff, so the fake stays simple while still
    exercising the real filtering logic.
    """

    def __init__(self, messages: list[FakeMessage], uidvalidity: int = 1):
        self._messages = list(messages)
        self.folder = _FakeFolderManager(uidvalidity)

    def uids(self) -> list[str]:
        return [m.uid for m in self._messages]

    def fetch(self, *args, **kwargs):
        yield from self._messages

    # Context-manager support so it can be used like a logged-in MailBox.
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def data_dir(tmp_path):
    """A writable temporary DATA_DIR for state files."""
    d = tmp_path / "data"
    d.mkdir()
    return str(d)


@pytest.fixture
def sample_messages():
    """Representative messages incl. missing subject and umlaut sender."""
    return [
        FakeMessage(
            uid="101",
            from_="studienbüro@uni-hildesheim.de",
            subject="Anmeldung zur Prüfung",
            date=datetime(2026, 6, 4, 9, 15, tzinfo=timezone.utc),
        ),
        FakeMessage(
            uid="102",
            from_="prof.müller@uni-hildesheim.de",
            subject="",  # missing subject -> fallback
            date=datetime(2026, 6, 4, 10, 0, tzinfo=timezone.utc),
        ),
        FakeMessage(
            uid="103",
            from_="",  # missing sender -> fallback
            subject="Welcome / Willkommen",
            date=datetime(2026, 6, 4, 11, 30, tzinfo=timezone.utc),
        ),
    ]


@pytest.fixture
def fake_mailbox(sample_messages):
    return FakeMailBox(sample_messages, uidvalidity=1)
