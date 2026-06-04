"""IMAP mailbox access via ``imap-tools``.

Connects to the configured IMAP server, reads UIDVALIDITY, and fetches the
messages whose UID is above the stored watermark. Parsing applies the FR-010
fallbacks (``(unknown sender)`` / ``(no subject)``) and never raises on a
malformed header.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

UNKNOWN_SENDER = "(unknown sender)"
NO_SUBJECT = "(no subject)"
BODY_PREVIEW_MAX = 300


@dataclass
class Attachment:
    """A real email attachment, with its bytes for forwarding to Telegram."""

    filename: str
    payload: bytes
    content_type: str | None = None


@dataclass
class EmailMessage:
    """A fetched INBOX message that is a candidate for notification."""

    uid: int
    sender: str
    subject: str
    received_at: datetime
    to: list[str] = field(default_factory=list)
    cc: list[str] = field(default_factory=list)
    attachments: list[str] = field(default_factory=list)
    body_preview: str = ""
    body_html: str = ""
    body_text: str = ""
    attachment_files: list[Attachment] = field(default_factory=list)


def open_mailbox(config):
    """Open and log in to the configured IMAP folder.

    Returns a logged-in ``imap_tools`` ``MailBox`` usable as a context manager.
    """
    from imap_tools import MailBox, MailBoxUnencrypted

    if config.imap_ssl:
        box = MailBox(config.imap_host, port=config.imap_port)
    else:
        box = MailBoxUnencrypted(config.imap_host, port=config.imap_port)
    return box.login(
        config.imap_user, config.imap_password, initial_folder=config.imap_folder
    )


def get_uidvalidity(client, folder=None) -> int:
    """Return the current UIDVALIDITY of the (current) folder."""
    status = client.folder.status(folder, ["UIDVALIDITY"])
    return int(status["UIDVALIDITY"])


def mailbox_max_uid(client) -> int:
    """Return the highest UID present in the folder, or 0 if empty."""
    uids = [int(u) for u in client.uids()]
    return max(uids) if uids else 0


def _body_preview(msg) -> str:
    """A short, single-line preview of the message body (FR-010 safe)."""
    text = getattr(msg, "text", "") or ""
    if not text.strip():
        # Fall back to stripping tags out of the HTML part if there is no plain
        # text alternative.
        import re

        html = getattr(msg, "html", "") or ""
        text = re.sub(r"<[^>]+>", " ", html)
    collapsed = " ".join(text.split())
    if len(collapsed) > BODY_PREVIEW_MAX:
        return collapsed[: BODY_PREVIEW_MAX - 1].rstrip() + "…"
    return collapsed


def _attachments(msg) -> list[Attachment]:
    files = []
    for att in getattr(msg, "attachments", []) or []:
        name = getattr(att, "filename", None)
        files.append(
            Attachment(
                filename=name.strip() if name else "(unnamed)",
                payload=getattr(att, "payload", b"") or b"",
                content_type=getattr(att, "content_type", None),
            )
        )
    return files


def _to_email_message(msg) -> EmailMessage:
    sender = (msg.from_ or "").strip() or UNKNOWN_SENDER
    subject = (msg.subject or "").strip() or NO_SUBJECT
    attachment_files = _attachments(msg)
    return EmailMessage(
        uid=int(msg.uid),
        sender=sender,
        subject=subject,
        received_at=msg.date,
        to=[a for a in (getattr(msg, "to", ()) or ()) if a],
        cc=[a for a in (getattr(msg, "cc", ()) or ()) if a],
        attachments=[a.filename for a in attachment_files],
        body_preview=_body_preview(msg),
        body_html=getattr(msg, "html", "") or "",
        body_text=getattr(msg, "text", "") or "",
        attachment_files=attachment_files,
    )


def fetch_new(client, since_uid: int) -> list[EmailMessage]:
    """Fetch messages with ``UID > since_uid``, ascending.

    Returns an empty list when nothing is new. Limits the server fetch to the
    new UID range, then defensively filters again before returning. Fetches the
    full message (not headers only) so the body preview and attachment names are
    available; reading is non-destructive (``mark_seen=False``).
    """
    all_uids = sorted(int(u) for u in client.uids())
    new = [u for u in all_uids if u > since_uid]
    if not new:
        return []

    from imap_tools import AND

    criteria = AND(uid=",".join(str(u) for u in new))
    messages = [
        _to_email_message(m)
        for m in client.fetch(criteria, mark_seen=False, bulk=True)
        if int(m.uid) > since_uid
    ]
    messages.sort(key=lambda e: e.uid)
    return messages
