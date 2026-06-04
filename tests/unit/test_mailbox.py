"""Unit tests for src.mailbox (against the in-process fake IMAP client)."""

from datetime import datetime, timezone

from src.mailbox import EmailMessage, fetch_new, get_uidvalidity, mailbox_max_uid
from tests.conftest import FakeMailBox, FakeMessage


def test_fetches_only_uids_above_watermark(fake_mailbox):
    result = fetch_new(fake_mailbox, since_uid=101)
    assert [m.uid for m in result] == [102, 103]


def test_no_new_when_watermark_at_max(fake_mailbox):
    assert fetch_new(fake_mailbox, since_uid=103) == []


def test_results_sorted_ascending_by_uid():
    msgs = [
        FakeMessage("5", "a@x", "s5", datetime(2026, 1, 1, tzinfo=timezone.utc)),
        FakeMessage("2", "b@x", "s2", datetime(2026, 1, 1, tzinfo=timezone.utc)),
        FakeMessage("9", "c@x", "s9", datetime(2026, 1, 1, tzinfo=timezone.utc)),
    ]
    result = fetch_new(FakeMailBox(msgs), since_uid=0)
    assert [m.uid for m in result] == [2, 5, 9]


def test_sender_fallback_when_missing(fake_mailbox):
    result = fetch_new(fake_mailbox, since_uid=102)
    assert result[0].uid == 103
    assert result[0].sender == "(unknown sender)"


def test_subject_fallback_when_missing(fake_mailbox):
    result = fetch_new(fake_mailbox, since_uid=101)
    msg_102 = next(m for m in result if m.uid == 102)
    assert msg_102.subject == "(no subject)"


def test_umlaut_sender_preserved(fake_mailbox):
    result = fetch_new(fake_mailbox, since_uid=0)
    msg_101 = next(m for m in result if m.uid == 101)
    assert "ü" in msg_101.sender


def test_returns_email_message_instances(fake_mailbox):
    result = fetch_new(fake_mailbox, since_uid=0)
    assert all(isinstance(m, EmailMessage) for m in result)
    assert all(isinstance(m.uid, int) for m in result)


def test_mailbox_max_uid(fake_mailbox):
    assert mailbox_max_uid(fake_mailbox) == 103


def test_mailbox_max_uid_empty():
    assert mailbox_max_uid(FakeMailBox([])) == 0


def test_get_uidvalidity(fake_mailbox):
    assert get_uidvalidity(fake_mailbox) == 1


class _RichMessage:
    """A fuller fake message exposing body, attachments, to and cc."""

    class _Att:
        def __init__(self, filename):
            self.filename = filename

    def __init__(self, uid, text="", html="", attachments=(), to=(), cc=()):
        self.uid = str(uid)
        self.from_ = "prof@uni-hildesheim.de"
        self.subject = "Subject"
        self.date = datetime(2026, 6, 4, 12, 0, tzinfo=timezone.utc)
        self.text = text
        self.html = html
        self.attachments = [self._Att(n) for n in attachments]
        self.to = to
        self.cc = cc


def test_parses_to_cc_attachments_and_body_preview():
    msg = _RichMessage(
        uid=10,
        text="Line one\n\nLine two   with   spaces",
        attachments=["a.pdf", "b.docx"],
        to=("me@uni-hildesheim.de",),
        cc=("other@uni-hildesheim.de",),
    )
    result = fetch_new(FakeMailBox([msg]), since_uid=0)[0]
    assert result.to == ["me@uni-hildesheim.de"]
    assert result.cc == ["other@uni-hildesheim.de"]
    assert result.attachments == ["a.pdf", "b.docx"]
    # Whitespace/newlines collapsed to single spaces.
    assert result.body_preview == "Line one Line two with spaces"


def test_body_preview_truncated_to_300_chars():
    long_text = "x " * 400  # ~800 chars
    msg = _RichMessage(uid=11, text=long_text)
    result = fetch_new(FakeMailBox([msg]), since_uid=0)[0]
    assert len(result.body_preview) <= 300
    assert result.body_preview.endswith("…")


def test_body_preview_falls_back_to_html_when_no_text():
    msg = _RichMessage(uid=12, text="", html="<p>Hallo <b>Welt</b></p>")
    result = fetch_new(FakeMailBox([msg]), since_uid=0)[0]
    assert result.body_preview == "Hallo Welt"
