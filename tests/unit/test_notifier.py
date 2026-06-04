"""Unit tests for src.notifier (Telegram HTTP mocked via responses)."""

import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import responses

from src.config import load_config
from src.mailbox import EmailMessage
from src.notifier import build_notifications, send

API = "https://api.telegram.org/botsecret-token/sendMessage"


def _config(**overrides):
    env = {
        "IMAP_PASSWORD": "pw",
        "TELEGRAM_BOT_TOKEN": "secret-token",
        "TELEGRAM_CHAT_ID": "99",
    }
    env.update(overrides)
    return load_config(env)


def _email(uid, sender, subject):
    return EmailMessage(
        uid=uid,
        sender=sender,
        subject=subject,
        received_at=datetime(2026, 6, 4, 12, 32, tzinfo=ZoneInfo("Europe/Berlin")),
    )


def test_single_email_format():
    cfg = _config()
    emails = [_email(1, "studienbüro@uni-hildesheim.de", "Prüfung")]
    notes = build_notifications(emails, cfg)
    assert len(notes) == 1
    text = notes[0].text
    assert "📧 New university email" in text
    assert "studienbüro@uni-hildesheim.de" in text
    assert "Prüfung" in text
    assert "2026-06-04 12:32" in text
    assert notes[0].covers_uids == [1]


def test_one_notification_per_email_below_threshold():
    cfg = _config(DIGEST_THRESHOLD="10")
    emails = [_email(i, f"s{i}@x", f"sub{i}") for i in range(1, 6)]
    notes = build_notifications(emails, cfg)
    assert len(notes) == 5


def test_digest_format_above_threshold():
    cfg = _config(DIGEST_THRESHOLD="3")
    emails = [_email(i, f"s{i}@x", f"sub{i}") for i in range(1, 6)]
    notes = build_notifications(emails, cfg)
    assert len(notes) == 1
    text = notes[0].text
    assert "📬 5 new university emails" in text
    for i in range(1, 6):
        assert f"s{i}@x" in text
        assert f"sub{i}" in text
    assert notes[0].covers_uids == [1, 2, 3, 4, 5]


def test_time_rendered_in_configured_timezone():
    cfg = _config(TIMEZONE="Europe/Berlin")
    email = EmailMessage(
        uid=1,
        sender="a@x",
        subject="s",
        # 10:32 UTC == 12:32 Berlin (CEST, summer)
        received_at=datetime(2026, 6, 4, 10, 32, tzinfo=timezone.utc),
    )
    notes = build_notifications([email], cfg)
    assert "12:32" in notes[0].text


@responses.activate
def test_delivered_true_on_2xx():
    responses.add(responses.POST, API, json={"ok": True}, status=200)
    cfg = _config()
    note = build_notifications([_email(1, "a@x", "s")], cfg)[0]
    assert send(note, cfg) is True
    assert note.delivered is True


@responses.activate
def test_delivered_false_on_non_2xx():
    responses.add(responses.POST, API, json={"ok": False}, status=400)
    cfg = _config()
    note = build_notifications([_email(1, "a@x", "s")], cfg)[0]
    assert send(note, cfg) is False
    assert note.delivered is False


@responses.activate
def test_payload_contains_no_secrets():
    responses.add(responses.POST, API, json={"ok": True}, status=200)
    cfg = _config()
    note = build_notifications([_email(1, "a@x", "s")], cfg)[0]
    send(note, cfg)
    body = responses.calls[0].request.body
    if isinstance(body, bytes):
        body = body.decode()
    payload = json.loads(body)
    assert cfg.telegram_bot_token not in json.dumps(payload)
    assert cfg.imap_password not in json.dumps(payload)
    assert payload["chat_id"] == "99"


@responses.activate
def test_umlauts_render_in_payload():
    responses.add(responses.POST, API, json={"ok": True}, status=200)
    cfg = _config()
    note = build_notifications([_email(1, "müller@x", "Grüße")], cfg)[0]
    send(note, cfg)
    body = responses.calls[0].request.body
    if isinstance(body, bytes):
        body = body.decode("utf-8")
    assert "müller@x" in body
    assert "Grüße" in body


def test_single_email_includes_to_cc_attachments_and_preview():
    cfg = _config()
    email = EmailMessage(
        uid=1,
        sender="prof@uni-hildesheim.de",
        subject="Klausur",
        received_at=datetime(2026, 6, 4, 12, 32, tzinfo=ZoneInfo("Europe/Berlin")),
        to=["jdoe@uni-hildesheim.de"],
        cc=["assistant@uni-hildesheim.de", "list@uni-hildesheim.de"],
        attachments=["Klausur.pdf", "Folien.pptx"],
        body_preview="Bitte beachten Sie die Anmeldefrist.",
    )
    text = build_notifications([email], cfg)[0].text
    assert "To:      jdoe@uni-hildesheim.de" in text
    assert "Cc:      assistant@uni-hildesheim.de, list@uni-hildesheim.de" in text
    assert "📎 2 attachment(s): Klausur.pdf, Folien.pptx" in text
    assert "Bitte beachten Sie die Anmeldefrist." in text


def test_single_email_omits_empty_optional_fields():
    cfg = _config()
    email = EmailMessage(
        uid=1,
        sender="a@x",
        subject="s",
        received_at=datetime(2026, 6, 4, 12, 32, tzinfo=ZoneInfo("Europe/Berlin")),
    )
    text = build_notifications([email], cfg)[0].text
    assert "To:" not in text
    assert "Cc:" not in text
    assert "📎" not in text


from src.mailbox import Attachment  # noqa: E402
from src.notifier import _email_documents  # noqa: E402

DOC_API = "https://api.telegram.org/botsecret-token/sendDocument"


def _rich_email(**overrides):
    base = dict(
        uid=1,
        sender="prof@uni-hildesheim.de",
        subject="Klausur/Anmeldung",
        received_at=datetime(2026, 6, 4, 12, 32, tzinfo=ZoneInfo("Europe/Berlin")),
    )
    base.update(overrides)
    return EmailMessage(**base)


def test_full_email_document_prefers_html():
    email = _rich_email(body_html="<p>Hallo</p>", body_text="Hallo")
    docs = _email_documents(email)
    assert len(docs) == 1
    assert docs[0].filename.endswith(".html")
    # Subject slash is sanitized out of the filename.
    assert "/" not in docs[0].filename
    assert docs[0].content == b"<p>Hallo</p>"


def test_full_email_document_txt_when_no_html():
    email = _rich_email(body_html="", body_text="Just text")
    docs = _email_documents(email)
    assert len(docs) == 1
    assert docs[0].filename.endswith(".txt")


def test_attachments_are_forwarded_as_documents():
    email = _rich_email(
        body_html="<p>x</p>",
        attachment_files=[
            Attachment("Klausur.pdf", b"%PDF-1.4 data", "application/pdf"),
            Attachment("Folien.pptx", b"pptx-bytes", None),
        ],
    )
    docs = _email_documents(email)
    # html doc + 2 attachments
    assert [d.filename for d in docs] == [
        "Klausur_Anmeldung.html",
        "Klausur.pdf",
        "Folien.pptx",
    ]
    assert docs[1].content == b"%PDF-1.4 data"


def test_empty_attachment_payload_skipped():
    email = _rich_email(body_text="x", attachment_files=[Attachment("empty.bin", b"")])
    docs = _email_documents(email)
    assert all(d.filename != "empty.bin" for d in docs)


@responses.activate
def test_send_uploads_text_then_documents():
    responses.add(responses.POST, API, json={"ok": True}, status=200)
    responses.add(responses.POST, DOC_API, json={"ok": True}, status=200)
    cfg = _config()
    email = _rich_email(
        body_html="<p>Hallo</p>",
        attachment_files=[Attachment("a.pdf", b"PDFDATA", "application/pdf")],
    )
    note = build_notifications([email], cfg)[0]
    assert send(note, cfg) is True
    # 1 sendMessage + 1 html doc + 1 attachment = 3 calls.
    urls = [c.request.url for c in responses.calls]
    assert urls.count(API) == 1
    assert urls.count(DOC_API) == 2


@responses.activate
def test_send_succeeds_even_if_document_upload_fails():
    responses.add(responses.POST, API, json={"ok": True}, status=200)
    responses.add(responses.POST, DOC_API, json={"ok": False}, status=413)  # too big
    cfg = _config()
    email = _rich_email(body_html="<p>Hallo</p>")
    note = build_notifications([email], cfg)[0]
    # Best-effort: a failed document upload must not fail the notification.
    assert send(note, cfg) is True
    assert note.delivered is True


@responses.activate
def test_no_documents_uploaded_when_text_fails():
    responses.add(responses.POST, API, json={"ok": False}, status=500)
    cfg = _config()
    email = _rich_email(body_html="<p>Hallo</p>")
    note = build_notifications([email], cfg)[0]
    assert send(note, cfg) is False
    # No sendDocument attempted because the text message failed.
    assert all(c.request.url == API for c in responses.calls)
