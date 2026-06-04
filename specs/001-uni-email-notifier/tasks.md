---
description: "Task list for Uni Hildesheim Email Notifier implementation"
---

# Tasks: Uni Hildesheim Email Notifier

**Input**: Design documents from `/specs/001-uni-email-notifier/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Included. Constitution Principle II (Test-First & Comprehensive Coverage) and plan.md
mandate unit tests per module plus one full e2e flow. Tests for a story are written before that
story's implementation and MUST fail first.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story the task belongs to (US1, US2, US3)
- Exact file paths are included in each description

## Path Conventions

Single-project Python CLI (per plan.md): `src/` and `tests/` at repository root.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization, dependencies, and tooling

- [ ] T001 Create the project directory structure at the repo root: `src/`, `tests/unit/`, `tests/e2e/`, `deploy/`, and `data/` with a `data/.gitkeep`
- [ ] T002 Create `pyproject.toml` as a `uv` project (Python ≥ 3.10) with runtime deps `imap-tools`, `requests`, `python-dotenv` and dev deps `pytest`, `responses`, `ruff`; run `uv sync` to generate `uv.lock`
- [ ] T003 [P] Configure Ruff lint + format in `pyproject.toml` (`select = ["E","F","I","W"]`, `line-length = 88`)
- [ ] T004 [P] Create `.gitignore` ignoring `.env`, `data/` (except `.gitkeep`), `__pycache__/`, `.venv/`, and `*.pyc`
- [ ] T005 [P] Create `.env.example` with every variable from `contracts/config.md` (non-secret defaults filled, secrets left blank with comments)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Configuration, persistent state, and shared test fixtures that every user story depends on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T006 Implement `src/config.py`: load `.env` via `python-dotenv`, parse and validate all variables per `contracts/config.md`, return a frozen/immutable config object, fail fast with `Configuration error: <VAR> ...` to stderr naming the offending variable, and never echo `IMAP_PASSWORD` or `TELEGRAM_BOT_TOKEN`
- [ ] T007 [P] Unit test config in `tests/unit/test_config.py`: defaults applied, missing required vars rejected, invalid `IMAP_PORT`/`SCHEDULE_*`/`TIMEZONE`/`DIGEST_THRESHOLD` rejected, `SCHEDULE_END ≥ SCHEDULE_START`, and secret values never appear in error messages
- [ ] T008 Implement `src/storage.py`: `ProcessedState` schema per `contracts/state.md`, load (default when file absent), atomic save (temp file + `os.replace`) into `DATA_DIR`, diff helper returning UIDs `> last_processed_uid`, and helpers to update `last_run_at`/`last_status` without touching the watermark
- [ ] T009 [P] Unit test storage in `tests/unit/test_storage.py` (use `tmp_path`): first-run baseline (no replay), normal diff (`uid > watermark`), atomic write survives, and `skipped`/`error` runs leave `last_processed_uid` unchanged
- [ ] T010 Create `tests/conftest.py` shared fixtures: a tmp `DATA_DIR`/state path, sample message data (incl. missing subject and umlaut/encoded sender), and an in-process fake IMAP client exposing `uid`/`from_`/`subject`/`date` and `UIDVALIDITY`

**Checkpoint**: Config + state + fixtures ready — user stories can now begin

---

## Phase 3: User Story 1 - Get notified of new university emails (Priority: P1) 🎯 MVP

**Goal**: On a manual `RUN_MODE=once` invocation, fetch newly arrived INBOX mail (UID above the stored watermark), send one Telegram message per new email (sender + subject + time), and advance the watermark only after delivery — with a digest fallback for large batches.

**Independent Test**: Set the watermark, feed the fake IMAP client one new message, run the flow, and confirm exactly one Telegram `sendMessage` POST with the sender and subject; a second run with no new mail sends nothing.

### Tests for User Story 1 ⚠️ (write first, ensure they FAIL)

- [ ] T011 [P] [US1] Unit test mailbox in `tests/unit/test_mailbox.py` (fake IMAP client): fetches only `UID > watermark`, parses in ascending UID order, sender fallback `(unknown sender)`, subject fallback `(no subject)`, and reports the current mailbox max UID + UIDVALIDITY
- [ ] T012 [P] [US1] Unit test notifier in `tests/unit/test_notifier.py` (`responses`): single-email format and `> DIGEST_THRESHOLD` digest format per `contracts/notification.md`, `delivered` true only on 2xx and false on non-2xx, umlauts render, and no secrets in payload
- [ ] T013 [US1] e2e happy-path test in `tests/e2e/test_flow.py`: connect → fetch → diff → notify → watermark advance, with the IMAP client faked in-process and the Telegram call mocked via `responses`

### Implementation for User Story 1

- [ ] T014 [P] [US1] Implement `src/mailbox.py`: `EmailMessage` dataclass (uid, sender, subject, received_at), connect via `imap-tools` (SSL per config), fetch `UID > watermark` with header-only parsing and FR-010 fallbacks, and expose mailbox max UID + UIDVALIDITY
- [ ] T015 [P] [US1] Implement `src/notifier.py`: `Notification` model, single-email and digest renderers per `contracts/notification.md`, POST to `https://api.telegram.org/bot<token>/sendMessage` via `requests`, mark delivered only on 2xx, escape text, and never include secrets
- [ ] T016 [US1] Implement `src/main.py` core flow (`RUN_MODE=once`): load config → load state → first-run baseline (set watermark to mailbox max, no replay) → fetch new → render single messages or a digest by `DIGEST_THRESHOLD` → deliver → advance watermark per delivered UID → persist state with `last_status=ok`

**Checkpoint**: User Story 1 is fully functional and independently testable — this is the MVP

---

## Phase 4: User Story 2 - Run automatically on a schedule during working hours (Priority: P2)

**Goal**: The tool only acts within the inclusive 08:00–17:00 Europe/Berlin window, and a cron schedule drives it every 30 minutes on `my-server`.

**Independent Test**: Invoke at 07:59, 08:00, 17:00, and 17:30 (mocked clock); confirm action runs at 08:00/17:00 and is skipped (no fetch, no notify, `last_status=skipped`) at 07:59/17:30, including across a DST boundary.

### Tests for User Story 2 ⚠️

- [ ] T017 [P] [US2] Unit test the window guard in `tests/unit/test_main.py`: inside vs. outside the window including the 08:00 and 17:00 boundaries, and correct behavior across a CET/CEST transition using `zoneinfo`

### Implementation for User Story 2

- [ ] T018 [US2] Add the timezone-aware window guard to `src/main.py` using `zoneinfo`: when the current `TIMEZONE` time is outside `SCHEDULE_START`–`SCHEDULE_END`, exit early with `last_status=skipped` and no fetch/notify (FR-005)
- [ ] T019 [P] [US2] Create `deploy/crontab.example` with the `*/30 8-17 * * *` line for `my-server` (Europe/Berlin host TZ) invoking `uv run python -m src.main`, logging to `data/cron.log`
- [ ] T020 [US2] Document scheduling in `README.md`: cron install steps, host-clock/`timedatectl` Europe/Berlin requirement, and how the in-app guard backstops cron

**Checkpoint**: Stories 1 AND 2 both work independently

---

## Phase 5: User Story 3 - Trust that the notifier is working and recoverable (Priority: P3)

**Goal**: Connection/auth and delivery failures never produce false notifications, are recorded to stderr, and never cause misses or duplicates across retries/restarts/UIDVALIDITY changes; overlapping runs are prevented.

**Independent Test**: Break connectivity or use wrong credentials and run — confirm no notification, `last_status=error`, non-zero exit, and unchanged watermark; restore service and confirm only genuinely new mail is notified.

### Tests for User Story 3 ⚠️

- [ ] T021 [P] [US3] Failure-handling unit tests in `tests/unit/test_main.py`: IMAP connect/auth failure → no notify, `last_status=error`, non-zero exit; partial delivery advances only to the highest contiguous delivered UID; second concurrent run skips on held lock
- [ ] T022 [P] [US3] UIDVALIDITY-guard unit test in `tests/unit/test_storage.py`: changed `UIDVALIDITY` resets the watermark to the current mailbox max and updates `uidvalidity` without replaying the mailbox
- [ ] T023 [US3] e2e failure/recovery test in `tests/e2e/test_flow.py`: unreachable/auth-failed run sends nothing and leaves state unchanged; the next successful run notifies only new mail (no re-notify of old)

### Implementation for User Story 3

- [ ] T024 [US3] Add the UIDVALIDITY guard to `src/storage.py`/`src/mailbox.py`: when the server's `UIDVALIDITY` differs from the stored value (non-null), reset the watermark to the current mailbox max, update `uidvalidity`, and record the reset to stderr (research §2)
- [ ] T025 [US3] Add a non-blocking skip-if-locked file lock under `DATA_DIR` in `src/main.py`: if a prior run holds the lock, exit immediately with `last_status=skipped` (Edge Case "Overlapping runs")
- [ ] T026 [US3] Add error handling to `src/main.py`: catch IMAP connect/auth and Telegram delivery failures, log to stderr without secrets, exit non-zero with `last_status=error`, and advance the watermark only to the highest contiguous delivered UID so undelivered mail stays new (FR-008, FR-009, Story 3 §3)

**Checkpoint**: All user stories independently functional

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, gates, and end-to-end validation

- [ ] T027 [P] Complete `README.md`: feature overview, full configuration table (all `contracts/config.md` variables), `uv` setup, and the quickstart/quality-gate commands
- [ ] T028 Run the quality gates from `quickstart.md`: `uv run ruff check .`, `uv run ruff format --check .`, and `uv run pytest tests/` — all MUST pass
- [ ] T029 Execute the `quickstart.md` manual validation: a real `RUN_MODE=once` baseline run sends no notifications, then a test email produces one Telegram message with sender + subject

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories
- **User Stories (Phase 3–5)**: All depend on Foundational; then proceed in priority order (P1 → P2 → P3) or in parallel if staffed
- **Polish (Phase 6)**: Depends on all targeted user stories being complete

### User Story Dependencies

- **US1 (P1)**: Depends only on Foundational — the standalone MVP
- **US2 (P2)**: Depends on Foundational; extends `main.py` from US1 but the window guard is independently testable
- **US3 (P3)**: Depends on Foundational; hardens `main.py`/`storage.py`/`mailbox.py` from US1 but its failure paths are independently testable

### Within Each User Story

- Tests are written first and MUST fail before implementation
- `mailbox.py` and `notifier.py` (different files) precede `main.py` orchestration
- Story complete before moving to the next priority

### Parallel Opportunities

- Setup: T003, T004, T005 in parallel after T001/T002
- Foundational: T007 and T009 in parallel (after their modules); T010 alongside
- US1: T011 ∥ T012 (tests); then T014 ∥ T015 (different modules) before T016
- US2: T017 and T019 in parallel
- US3: T021 ∥ T022 (different test files)
- Across stories: with multiple developers, US1/US2/US3 can proceed in parallel once Foundational is done

---

## Parallel Example: User Story 1

```bash
# Tests first (different files, run together):
Task: "Unit test mailbox in tests/unit/test_mailbox.py"
Task: "Unit test notifier in tests/unit/test_notifier.py"

# Then implement the two independent modules together:
Task: "Implement src/mailbox.py (EmailMessage + imap-tools fetch)"
Task: "Implement src/notifier.py (Telegram single + digest send)"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: run the flow against the fake IMAP client + mocked Telegram
5. Deploy/demo the manual once-run if ready

### Incremental Delivery

1. Setup + Foundational → foundation ready
2. US1 → test → manual once-run is the MVP
3. US2 → test → automated on the 08:00–17:00 cron cadence
4. US3 → test → trustworthy and recoverable
5. Polish → docs + gates + real-mailbox validation

---

## Notes

- [P] = different files, no dependencies on incomplete tasks
- [Story] label maps each task to its user story for traceability
- Secrets (`IMAP_PASSWORD`, `TELEGRAM_BOT_TOKEN`) never appear in logs, errors, or notifications
- Verify tests fail before implementing; commit after each task or logical group
- Stop at any checkpoint to validate a story independently
