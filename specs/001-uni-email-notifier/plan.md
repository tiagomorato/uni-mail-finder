# Implementation Plan: Uni Hildesheim Email Notifier

**Branch**: `001-uni-email-notifier` | **Date**: 2026-06-04 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-uni-email-notifier/spec.md`

## Summary

Poll the University of Hildesheim IMAP mailbox (`mailf1.rz.uni-hildesheim.de:993`, SSL) every
30 minutes between 08:00–17:00 Europe/Berlin and send one Telegram message per newly arrived
email (sender + subject). "New" is determined by the system's own persistent state (highest
processed IMAP UID stored in a JSON file under `data/`), never by the mailbox's read/unread
flags, so reading mail elsewhere causes neither misses nor duplicates. The tool runs unattended
on the always-on local Ubuntu server `my-server` via system cron invoking `RUN_MODE=once`.
Connection/auth failures are recorded to stderr and produce no false notifications; recovery
resumes from the stored UID without re-notifying old mail.

The codebase mirrors the sibling tools (`lsf-grade-finder`, `learnweb-content-finder`):
`uv`-managed Python ≥ 3.10, Ruff for lint+format, the `src/config.py` / `src/storage.py` /
`src/notifier.py` / `src/main.py` module layout, JSON state under `data/`, Telegram Bot API
notifications, and split unit/e2e tests. The HTTP-scraping module is replaced by an IMAP
mailbox module appropriate to this feature (see Complexity Tracking).

## Technical Context

**Language/Version**: Python ≥ 3.10 (constitution minimum)

**Primary Dependencies**: `imap-tools` (IMAP access + UID handling + parsed messages),
`requests` (Telegram Bot API HTTP), `python-dotenv` (env loading).
Dev: `pytest`, `responses` (mock Telegram HTTP), `ruff`.

**Storage**: Compact JSON file under `data/` (gitignored). Tracks the highest processed IMAP
UID and last-run metadata. Diff-based: nothing is re-notified.

**Testing**: `pytest`. `tests/unit/` fully mocked (no network; file I/O via `tmp_path`).
`tests/e2e/` drives the full flow (connect → fetch → diff → notify) with the IMAP client faked
in-process and the Telegram HTTP call mocked via `responses`.

**Target Platform**: Local Ubuntu server `my-server` (reachable via `ssh user@my-server`),
system cron, host timezone Europe/Berlin.

**Project Type**: Single-project Python CLI (one entry point, `RUN_MODE=once`).

**Performance Goals**: One check cycle completes in well under a minute; a single IMAP
connection per run; fetch only headers of UIDs greater than the stored watermark. No browser
runtime; minimal memory footprint.

**Constraints**: Must not notify outside the 08:00–17:00 Europe/Berlin window (FR-005); zero
duplicate notifications across retries/restarts/DST (SC-002, SC-004); secrets never logged or
included in notifications (FR-007). Notifications must render English and German content and
handle missing/malformed fields with fallbacks (FR-010).

**Scale/Scope**: Single mailbox (INBOX), single user, ~tens of emails per day at most; one
notification per email (digest fallback for large catch-up batches).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Code Quality & Consistency | PASS (with deviations) | `uv` only, Ruff `E,F,I,W` @ 88, Python ≥ 3.10, `config.py`/`storage.py`/`notifier.py`/`main.py` retained. Deviations: `scraper.py` → `mailbox.py`; IMAP, not HTTP. See Complexity Tracking. |
| II. Test-First & Comprehensive Coverage | PASS (with deviation) | Unit tests per module; one full e2e flow; shared fixtures in `tests/conftest.py`; tests touch no real network. Deviation: e2e mocks IMAP in-process (the `responses` HTTP mock applies only to the Telegram call, not IMAP). See Complexity Tracking. |
| III. User Experience Consistency | PASS (with deviation) | Telegram Bot API notifications; all config via `.env` + `python-dotenv`, documented in `.env.example` and README; `config.py` validates and fails fast; stderr for operator errors, stdout for status. Deviation: only `RUN_MODE=once` is provided (no `loop`), per the local-cron deployment decision. See Complexity Tracking. |
| IV. Performance & Resource Efficiency | PASS (with deviation) | No browser runtime; single connection per run; fetch only UIDs above the stored watermark; compact JSON state under gitignored `data/`, diff-based. Deviation: network library is `imap-tools`, not `requests`+`BeautifulSoup4`, because the source is IMAP not HTML. See Complexity Tracking. |

All deviations are driven by the protocol change (IMAP vs. HTTP scraping) and the explicit
deployment target (local cron on `my-server`), and are recorded with justification in the
Complexity Tracking table. No unjustified complexity is introduced. **Gate: PASS.**

## Project Structure

### Documentation (this feature)

```text
specs/001-uni-email-notifier/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── config.md        # Environment-variable configuration contract
│   ├── notification.md  # Telegram message format contract
│   └── state.md         # Persistent JSON state-file schema
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
src/
├── config.py        # Load + validate env (.env via python-dotenv); fail fast
├── mailbox.py       # IMAP connect/fetch/parse via imap-tools (network + parsing)
├── storage.py       # JSON state under data/: load/save highest processed UID + diff
├── notifier.py      # Telegram Bot API delivery (requests); message formatting
└── main.py          # Entry point: window guard → check cycle → notify (RUN_MODE=once)

tests/
├── conftest.py      # Shared fixtures: sample messages, fake IMAP client, tmp state
├── unit/
│   ├── test_config.py
│   ├── test_mailbox.py
│   ├── test_storage.py
│   └── test_notifier.py
└── e2e/
    └── test_flow.py # connect → fetch → diff → notify, IMAP faked + Telegram via responses

data/                # gitignored; runtime JSON state (created on first run)
.env                 # gitignored; secrets + config
.env.example         # documented config template
pyproject.toml       # uv project, deps, ruff config (E,F,I,W @ 88)
uv.lock
README.md            # setup, config table, cron install instructions
deploy/
└── crontab.example  # */30 8-17 * * * cron line for my-server (Europe/Berlin)
```

**Structure Decision**: Single-project Python CLI following the established sibling-project
layout. The mandated `config.py`/`storage.py`/`notifier.py`/`main.py` modules are kept verbatim;
the network+parsing module is named `mailbox.py` instead of `scraper.py` to reflect that it
speaks IMAP rather than scraping HTML. Deployment artifacts (`deploy/crontab.example`) replace
the family's GitHub Actions workflow, since the private university IMAP host is only reachable
from `my-server`.

## Complexity Tracking

> Deviations from the constitution, each justified with the rejected simpler alternative.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| `imap-tools` dependency instead of `requests`+`BeautifulSoup4` for the data source | The feature reads mail over IMAP, a non-HTTP protocol; `requests`/`BeautifulSoup4` cannot speak IMAP. `imap-tools` gives robust UID handling and parsed messages. | Stdlib `imaplib`+`email` avoids a dependency but pushes fragile low-level UID/encoding handling into our code, raising the risk of dedup and decoding bugs against FR-009/FR-010. |
| Network/parsing module named `mailbox.py`, not `scraper.py` | There is no scraping; naming the IMAP client `scraper.py` would mislead every future reader in the project family. | Keeping the literal `scraper.py` name preserves a string match but actively misrepresents the module's responsibility. |
| Only `RUN_MODE=once` is implemented (no `loop` mode) | Deployment is system cron on `my-server`, which already provides the 30-min/08:00–17:00 scheduling; a `loop` daemon would duplicate cron and add an idle long-running process. | Shipping `loop` for family parity adds untested surface (signal handling, sleep drift, window math) with no deployment that uses it. |
| Deployment via local system cron, not GitHub Actions | The university IMAP host is private/possibly VPN-gated and unreachable from GitHub-hosted runners; the spec mandates the always-on local server `my-server`. | A GitHub Actions cron cannot connect to the mailbox at all, so it is not a viable deployment for this feature. |
| e2e test fakes the IMAP client in-process rather than using `responses` | `responses` mocks HTTP only; IMAP is not HTTP, so the IMAP leg must be faked another way. The Telegram leg still uses `responses`. | Using `responses` alone cannot intercept IMAP traffic, so it cannot cover the connect→fetch portion of the flow. |
