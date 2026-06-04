"""Telegram notification rendering and delivery.

Renders one message per new email (or a single digest when a run finds more than
``DIGEST_THRESHOLD`` new emails) per
``specs/001-uni-email-notifier/contracts/notification.md`` and delivers each via
a direct HTTP POST to the Telegram Bot API. Messages are sent as plain text so
German umlauts and special characters render without escaping pitfalls. Secrets
never appear in the message body.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field

import requests

_TIME_FORMAT = "%Y-%m-%d %H:%M"
_REQUEST_TIMEOUT = 60
_FILENAME_MAX = 80


@dataclass
class Document:
    """A file to upload alongside a notification (full email body or attachment)."""

    filename: str
    content: bytes
    mime: str | None = None


@dataclass
class Notification:
    """A Telegram message describing one new email (or a digest of many).

    ``documents`` are uploaded after the text message on a successful send
    (best-effort): the full email body as a file plus any forwarded attachments.
    """

    text: str
    covers_uids: list[int]
    delivered: bool = field(default=False)
    documents: list[Document] = field(default_factory=list)


def _safe_filename(subject: str, fallback: str, ext: str) -> str:
    """Build a filesystem/Telegram-safe filename from an email subject."""
    base = re.sub(r"[^\w\s.-]", "_", subject or "").strip() or fallback
    base = re.sub(r"\s+", "_", base)[:_FILENAME_MAX]
    return f"{base}{ext}"


def _email_documents(email) -> list[Document]:
    """The full-email file (HTML preferred) plus any real attachments."""
    docs: list[Document] = []

    html = getattr(email, "body_html", "") or ""
    text = getattr(email, "body_text", "") or ""
    if html.strip():
        docs.append(
            Document(
                filename=_safe_filename(email.subject, "email", ".html"),
                content=html.encode("utf-8"),
                mime="text/html; charset=utf-8",
            )
        )
    elif text.strip():
        docs.append(
            Document(
                filename=_safe_filename(email.subject, "email", ".txt"),
                content=text.encode("utf-8"),
                mime="text/plain; charset=utf-8",
            )
        )

    for att in getattr(email, "attachment_files", []) or []:
        if att.payload:
            docs.append(
                Document(
                    filename=att.filename or "attachment",
                    content=att.payload,
                    mime=att.content_type,
                )
            )
    return docs


def _format_time(received_at, tz) -> str:
    if received_at is None:
        return "(unknown time)"
    if received_at.tzinfo is not None:
        received_at = received_at.astimezone(tz)
    return received_at.strftime(_TIME_FORMAT)


def render_single(email, tz) -> Notification:
    """Render a single-email notification.

    Includes To/Cc, attachment names, and a body preview when present; lines for
    empty fields are omitted to keep the message tidy.
    """
    lines = ["📧 New university email", "", f"From:    {email.sender}"]
    if getattr(email, "to", None):
        lines.append(f"To:      {', '.join(email.to)}")
    if getattr(email, "cc", None):
        lines.append(f"Cc:      {', '.join(email.cc)}")
    lines.append(f"Subject: {email.subject}")
    lines.append(f"Time:    {_format_time(email.received_at, tz)}")

    attachments = getattr(email, "attachments", None)
    if attachments:
        lines.append(f"📎 {len(attachments)} attachment(s): {', '.join(attachments)}")

    preview = getattr(email, "body_preview", "")
    if preview:
        lines.append("")
        lines.append(preview)

    return Notification(
        text="\n".join(lines),
        covers_uids=[email.uid],
        documents=_email_documents(email),
    )


def render_digest(emails, tz) -> Notification:
    """Render a digest notification summarizing many new emails."""
    lines = [f"📬 {len(emails)} new university emails", ""]
    for i, email in enumerate(emails, start=1):
        lines.append(f"{i}. {email.sender} — {email.subject}")
    return Notification(text="\n".join(lines), covers_uids=[e.uid for e in emails])


def build_notifications(emails, config) -> list[Notification]:
    """Build the notifications for a run's new emails.

    At most ``DIGEST_THRESHOLD`` emails -> one notification each. More than the
    threshold -> a single digest.
    """
    if not emails:
        return []
    if len(emails) > config.digest_threshold:
        return [render_digest(emails, config.timezone)]
    return [render_single(e, config.timezone) for e in emails]


def _send_document(doc: Document, config, poster) -> bool:
    """Upload one document via the Telegram Bot API. Returns delivery success."""
    url = f"https://api.telegram.org/bot{config.telegram_bot_token}/sendDocument"
    data = {"chat_id": config.telegram_chat_id}
    files = {"document": (doc.filename, doc.content, doc.mime)}
    try:
        response = poster(url, data=data, files=files, timeout=_REQUEST_TIMEOUT)
    except requests.RequestException:
        return False
    return 200 <= response.status_code < 300


def send(notification: Notification, config, session=None) -> bool:
    """Deliver a notification via the Telegram Bot API.

    Marks ``notification.delivered`` true only on a 2xx response to the text
    message. On a non-2xx response or a network error, returns False and leaves
    ``delivered`` false so the caller does not advance the watermark past the
    undelivered email.

    Attached documents (the full email body file and forwarded attachments) are
    uploaded after a successful text message on a **best-effort** basis: a failed
    upload is logged to stderr but does NOT fail the notification, so a single
    oversized attachment can never cause the email to be re-notified forever.
    """
    url = f"https://api.telegram.org/bot{config.telegram_bot_token}/sendMessage"
    payload = {"chat_id": config.telegram_chat_id, "text": notification.text}
    # Serialize with ensure_ascii=False so umlauts travel as real UTF-8 bytes.
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json; charset=utf-8"}
    poster = session.post if session is not None else requests.post
    try:
        response = poster(url, data=body, headers=headers, timeout=_REQUEST_TIMEOUT)
    except requests.RequestException:
        notification.delivered = False
        return False
    delivered = 200 <= response.status_code < 300
    notification.delivered = delivered
    if not delivered:
        return False

    for doc in notification.documents:
        if not _send_document(doc, config, poster):
            print(
                f"Warning: failed to upload '{doc.filename}' to Telegram "
                "(email still notified)",
                file=sys.stderr,
            )
    return True
