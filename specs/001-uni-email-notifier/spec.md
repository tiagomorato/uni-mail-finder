# Feature Specification: Uni Hildesheim Email Notifier

**Feature Branch**: `001-uni-email-notifier`

**Created**: 2026-06-04

**Status**: Draft

**Input**: User description: "I want to build something similar to the above mentioned repos but for the uni email of the university of hildesheim. I want to use IMAP, see the screenshot. What: a cron job that runs on my local ubuntu server accessible through 'ssh user@my-server' that checks for new emails and notifies me on a dedicated telegram bot. this way i dont have to check manually for emails. In the timezone of germany/berlin it should run between 8am and 5pm, every 30min."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Get notified of new university emails (Priority: P1)

As a University of Hildesheim student/staff member, I want to automatically receive a Telegram message whenever a new email arrives in my university mailbox, so that I no longer have to manually log in and check for new mail throughout the day.

**Why this priority**: This is the core value of the entire feature. Without automatic notification of new mail, the system delivers nothing. Everything else is supporting infrastructure.

**Independent Test**: Send a test email to the university mailbox during operating hours, wait for the next scheduled check, and confirm that a Telegram message describing that email arrives. This alone delivers the complete primary value.

**Acceptance Scenarios**:

1. **Given** the mailbox has one previously unseen email, **When** the scheduled check runs, **Then** the user receives exactly one Telegram notification containing the email's sender and subject.
2. **Given** the mailbox has three previously unseen emails, **When** the scheduled check runs, **Then** the user receives notifications covering all three emails and none are omitted.
3. **Given** the mailbox has no new emails since the previous check, **When** the scheduled check runs, **Then** the user receives no Telegram notification.
4. **Given** an email was already notified in a prior check, **When** a later check runs, **Then** that same email does not trigger a duplicate notification.

---

### User Story 2 - Run automatically on a schedule during working hours (Priority: P2)

As the user, I want the check to run by itself every 30 minutes between 08:00 and 17:00 Europe/Berlin time on my always-on home server, so that I get timely notifications during the hours I care about without keeping any app open.

**Why this priority**: The notification capability (P1) is only useful if it runs unattended on the intended cadence. This makes the feature "hands-off," but it builds on the core notification capability rather than replacing it.

**Independent Test**: Observe the system over a full day and confirm checks occur on the half-hour within the 08:00–17:00 Europe/Berlin window and do not occur outside it, including correct behavior across a daylight-saving transition.

**Acceptance Scenarios**:

1. **Given** the current local time is 08:00 Europe/Berlin, **When** the scheduler triggers, **Then** a mailbox check runs.
2. **Given** the current local time is 17:00 Europe/Berlin, **When** the scheduler triggers, **Then** a mailbox check runs (final check of the day).
3. **Given** the current local time is 17:30 or later, or earlier than 08:00, **When** the scheduler would otherwise trigger, **Then** no mailbox check runs.
4. **Given** checks run within the window, **When** measuring the interval between consecutive checks, **Then** they occur approximately every 30 minutes.

---

### User Story 3 - Trust that the notifier is working and recoverable (Priority: P3)

As the user, I want failed checks (e.g., the mail server is unreachable or credentials are rejected) to be visible and to not cause missed or duplicated notifications once service is restored, so that I can trust the system and fix it when it breaks.

**Why this priority**: Reliability and observability increase long-term trust but are not required to demonstrate the core value. A first usable version can exist without rich error reporting.

**Independent Test**: Temporarily break connectivity or use wrong credentials, run a check, confirm the failure is recorded/surfaced and no false notification is sent; restore service and confirm normal operation resumes without re-notifying old mail.

**Acceptance Scenarios**:

1. **Given** the mail server is unreachable, **When** a check runs, **Then** no notification about new mail is sent and the failure is recorded for the user to see.
2. **Given** a check failed and then connectivity is restored, **When** the next check runs, **Then** only genuinely new emails are notified and previously seen emails are not re-sent.
3. **Given** the Telegram delivery fails for a found email, **When** the next check runs, **Then** the system still attempts to deliver notification for that not-yet-notified email rather than silently dropping it.

---

### Edge Cases

- **Many emails at once**: If a large batch of unseen emails accumulates (e.g., after downtime), the user is still notified about each without flooding being indistinguishable — notifications remain readable (e.g., one message per email or a clearly summarized digest).
- **Read on another device**: If the user reads an email in a webmail/desktop client before a check runs, the system should still rely on its own record of what was already notified so behavior is predictable.
- **Daylight Saving Time**: The 08:00–17:00 window follows Europe/Berlin local time and remains correct across CET/CEST transitions.
- **Server was off**: If the home server was powered down during part of the window, the next check after startup still notifies emails that arrived while it was off.
- **Email with no subject or unusual encoding**: Notifications are still delivered with a sensible placeholder rather than failing.
- **Overlapping runs**: A check that runs long does not collide with or duplicate the work of the next scheduled check.
- **Secrets exposure**: Mailbox and bot credentials are never included in notification content or logs.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST connect to the University of Hildesheim email mailbox over IMAP using the user's credentials and retrieve information about newly arrived emails.
- **FR-002**: System MUST identify emails that are "new" since the previous successful check, using a persistent record of what has already been processed, so that already-notified emails are never reported again.
- **FR-003**: System MUST send a notification to a dedicated Telegram bot/chat for each new email, including at minimum the sender and the subject.
- **FR-004**: System MUST run automatically on a recurring schedule of every 30 minutes, only during 08:00–17:00 inclusive, in the Europe/Berlin timezone.
- **FR-005**: System MUST NOT send notifications outside the configured operating window.
- **FR-006**: System MUST run unattended on the user's local Ubuntu server (reachable via `ssh user@my-server`) without requiring manual intervention for each check.
- **FR-007**: System MUST store mailbox and Telegram credentials securely and MUST NOT expose them in notifications or logs.
- **FR-008**: System MUST handle connection or authentication failures without sending false notifications, and MUST record such failures so the user can diagnose them.
- **FR-009**: System MUST avoid duplicate notifications when checks are retried, when the server restarts, or when emails are read elsewhere.
- **FR-010**: System MUST handle emails with missing or malformed fields (e.g., no subject, unusual character encodings) by producing a readable notification with sensible fallbacks.
- **FR-011**: System MUST process accumulated unseen emails (e.g., after downtime) so that none are skipped.
- **FR-012**: System MUST allow the user to configure the connection details, credentials, target Telegram destination, and schedule window without changing core logic.

### Key Entities *(include if feature involves data)*

- **Email Message**: A message in the university mailbox relevant to notification. Key attributes: unique identifier (for dedup tracking), sender, subject, received timestamp, seen/unseen status.
- **Notification**: A message delivered to the user via Telegram describing one (or a summarized set of) new email(s). Key attributes: content (sender, subject, time), delivery status.
- **Processed-State Record**: A persistent marker of which emails have already been notified (e.g., last processed message identifier), used to determine what is "new."
- **Configuration**: User-supplied settings: mailbox host/account/credentials, Telegram bot token and chat destination, and the operating schedule window/timezone. Known mailbox connection values for this account (from the user's mail client, see screenshot): IMAP server `mailf1.rz.uni-hildesheim.de`, port `993`, SSL encryption, username `jdoe`, full address `jdoe@uni-hildesheim.de`. The mailbox password and Telegram bot token are secrets to be supplied securely at setup, not stored in the spec. (Outgoing/SMTP settings are not relevant — this feature only reads mail.)

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of emails that arrive during the operating window are reported to the user within 30 minutes of arrival (by the next scheduled check).
- **SC-002**: Zero duplicate notifications for the same email across repeated checks, restarts, and recovery from failures over a one-week observation period.
- **SC-003**: The user spends zero manual effort checking the mailbox during operating hours once configured; all awareness of new mail comes from notifications.
- **SC-004**: 100% of scheduled checks occur within the 08:00–17:00 Europe/Berlin window and none occur outside it, verified across at least one daylight-saving transition.
- **SC-005**: When the mail service is unavailable, 0 false "new email" notifications are sent, and the failure is observable to the user.
- **SC-006**: Initial setup (configuring credentials, Telegram destination, and schedule) can be completed by the user in under 30 minutes.

## Assumptions

- The "above mentioned repos" and "screenshot" refer to similar mailbox-to-notifier tools; the concrete behavior is captured here as IMAP polling plus Telegram notification. No specific third-party repo is treated as a binding dependency.
- "New email" means an email not previously notified by this system, tracked via the system's own persistent state (e.g., highest processed IMAP UID), rather than relying solely on the mailbox's read/unread flags, so reading mail elsewhere does not cause misses or duplicates.
- The monitored scope is the primary inbox (INBOX) folder unless the user later configures additional folders.
- The University of Hildesheim provides standard IMAP access and the user has valid credentials. Per the user's mail client configuration (screenshot): IMAP host `mailf1.rz.uni-hildesheim.de`, port `993`, SSL encryption, username `jdoe`, address `jdoe@uni-hildesheim.de`. Any required VPN/network access from the home server is available.
- The home Ubuntu server (`my-server`) is normally powered on and connected to the internet during the operating window, and the existing system scheduler (cron) is available.
- A dedicated Telegram bot has been (or will be) created by the user, and the user has a chat/channel to receive messages.
- Notifications are personal and one-directional (system → user); interactive bot commands (replying, archiving, etc.) are out of scope for the first version.
- Operating window is inclusive of the 08:00 and 17:00 trigger times; checks occur at :00 and :30 of each hour in range.
- English and German email content are both expected and must render correctly.
