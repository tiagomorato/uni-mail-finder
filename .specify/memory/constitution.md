<!--
SYNC IMPACT REPORT
==================
Version change: (template, unversioned) → 1.0.0
Bump rationale: Initial ratification of a concrete constitution from the template.
                MAJOR baseline since this establishes the governing principles.

Modified principles:
  [PRINCIPLE_1_NAME] → I. Code Quality & Consistency
  [PRINCIPLE_2_NAME] → II. Test-First & Comprehensive Coverage
  [PRINCIPLE_3_NAME] → III. User Experience Consistency
  [PRINCIPLE_4_NAME] → IV. Performance & Resource Efficiency
  [PRINCIPLE_5_NAME] → (removed; project scoped to four core principles per request)

Added sections:
  - Technology & Architecture Constraints (was [SECTION_2_NAME])
  - Development Workflow & Quality Gates (was [SECTION_3_NAME])

Removed sections:
  - None (template placeholder slots fully populated)

Templates requiring updates:
  ✅ .specify/templates/plan-template.md      (Constitution Check gate is generic; aligns)
  ✅ .specify/templates/spec-template.md      (no constitution-specific edits required)
  ✅ .specify/templates/tasks-template.md     (test + performance + polish phases align)
  ✅ .specify/templates/checklist-template.md (no changes required)

Follow-up TODOs:
  - None. RATIFICATION_DATE set to first adoption date (2026-06-04).
-->

# Uni Mail Finder Constitution

## Core Principles

### I. Code Quality & Consistency

Code MUST be clean, readable, and uniform across the codebase before it is merged.

- Ruff is the single source of truth for linting AND formatting. The enabled rule set is
  `E`, `F`, `I`, `W` with a line length of `88`, configured in `pyproject.toml`.
- `uv run ruff check .` and `uv run ruff format --check .` MUST both pass with zero findings
  before any commit. CI MUST fail on violations.
- `uv` is the ONLY package manager. `pip` MUST NOT be invoked directly. Dependencies and dev
  dependencies are declared in `pyproject.toml` and locked in `uv.lock`.
- The source layout MUST follow the established sibling-project structure: `src/config.py`
  (env loading + validation), `src/scraper.py` (network + parsing), `src/storage.py`
  (persistence + diff detection), `src/notifier.py` (notifications), `src/main.py` (entry
  point). Modules MUST stay single-responsibility; do not merge concerns across these files.
- Python 3.10+ is the minimum supported runtime.

**Rationale**: Two predecessor tools (`lsf-grade-finder`, `learnweb-content-finder`) already
share this exact structure and toolchain. Consistency across the family lowers the cost of
context-switching, review, and reuse, and keeps every project's mental model identical.

### II. Test-First & Comprehensive Coverage

Behavior MUST be protected by automated tests, and tests MUST NOT touch the network.

- Tests are split into `tests/unit/` (fast, fully mocked, no network, file I/O via `tmp_path`)
  and `tests/e2e/` (full flow against mocked HTTP using the `responses` library).
- Every `src/` module with logic MUST have a corresponding unit test module
  (`test_config.py`, `test_scraper.py`, `test_storage.py`, `test_notifier.py`).
- The complete end-to-end flow (login → fetch → parse → diff → notify) MUST be covered by at
  least one e2e test driven entirely by mocked HTTP — no live credentials, no live endpoints.
- Shared fixtures (sample HTML, mock data) live in `tests/conftest.py` and MUST be reused
  rather than duplicated per test.
- New behavior or bug fixes MUST add or update tests in the same change. `uv run pytest tests/`
  MUST pass before merge.

**Rationale**: These tools run unattended (cron / loop) against an external university portal.
Mocked, deterministic tests are the only safe way to verify scraping and diff logic without
hammering the live site or leaking credentials, and they make regressions immediately visible.

### III. User Experience Consistency

The end-user experience MUST be predictable and identical in shape across the project family.

- Notifications are delivered via the Telegram Bot API. Message formatting MUST be clear,
  self-contained, and actionable (state what changed and where), consistent with sibling tools.
- All configuration is supplied through environment variables loaded from `.env` via
  `python-dotenv`. Every variable MUST be documented in `.env.example` with required/optional
  status and defaults, and mirrored in the README configuration table.
- `config.py` MUST validate configuration on startup and fail fast with a human-readable error
  naming the missing or invalid variable — never a raw stack trace for a config mistake.
- The tool MUST support the two standard run modes: `once` (for GitHub Actions cron) and `loop`
  (for Docker with an interval), selected via `RUN_MODE`, defaulting to `once`.
- Errors written for operators go to stderr; normal status output goes to stdout.

**Rationale**: Users of these tools expect the same setup ritual and the same notification
behavior across every "finder." A consistent config contract and notification style make the
whole family learnable once and trustworthy everywhere.

### IV. Performance & Resource Efficiency

The tool MUST stay lightweight enough to run free on GitHub Actions and small containers.

- Scraping MUST use `requests` + `BeautifulSoup4`. Selenium or any headless-browser dependency
  is PROHIBITED unless server-rendered HTML is proven insufficient and the exception is recorded
  in the Complexity Tracking section of the plan.
- A single check cycle MUST be efficient: reuse one `requests.Session`, avoid redundant fetches,
  and fetch only the pages required to detect changes.
- Persistent state MUST be a compact JSON file under `data/` (gitignored), with change detection
  done by diffing against stored state — never by re-notifying unchanged items.
- The runtime footprint MUST remain small enough to complete well within a GitHub Actions
  free-tier job and to run in a minimal Docker image without a browser runtime.

**Rationale**: The deployment model (free GitHub Actions cron or a tiny always-on container)
only works if the tool is cheap to run. Avoiding the ~400MB browser dependency and minimizing
network work keeps it fast, free, and maintenance-light.

## Technology & Architecture Constraints

- **Language/runtime**: Python ≥ 3.10.
- **Core dependencies**: `requests`, `beautifulsoup4`, `python-dotenv`. Dev: `pytest`,
  `responses`, `ruff`. Additions MUST be justified and added via `uv`.
- **No browser automation** (see Principle IV).
- **Persistence**: JSON file in `data/` (gitignored); diff-based change detection.
- **Notifications**: Telegram Bot API via direct HTTP (no heavyweight wrapper library).
- **Deployment targets**: GitHub Actions (cron, `RUN_MODE=once`) and Docker
  (`docker compose`, `RUN_MODE=loop`) with a mounted `./data` volume.
- **Secrets**: never committed. Provided via repository secrets (Actions) or `.env` (Docker /
  local). `.env` and `data/` MUST be gitignored.

## Development Workflow & Quality Gates

The following gates MUST pass, in order, before a change is considered done:

1. `uv run ruff check .` — zero lint findings.
2. `uv run ruff format --check .` — formatting clean.
3. `uv run pytest tests/` — all unit and e2e tests pass.

Additional rules:

- New or changed behavior ships with tests in the same change (Principle II).
- New env vars are reflected in `config.py` validation, `.env.example`, and the README table
  in the same change (Principle III).
- The `## Constitution Check` gate in `plan-template.md` MUST be evaluated against these
  principles before Phase 0 research and re-checked after Phase 1 design. Any deviation MUST be
  recorded in the plan's Complexity Tracking table with justification and the rejected simpler
  alternative.

## Governance

This constitution supersedes other practices for this project. When guidance conflicts, the
constitution wins.

- **Amendments**: proposed via pull request that edits this file, states the rationale, and
  updates the Sync Impact Report. Dependent templates and docs MUST be brought back into
  alignment in the same change.
- **Versioning policy** (semantic versioning of this document):
  - **MAJOR**: backward-incompatible governance changes or removal/redefinition of a principle.
  - **MINOR**: a new principle or section, or materially expanded guidance.
  - **PATCH**: clarifications, wording, and non-semantic refinements.
- **Compliance review**: every PR and review MUST verify adherence to the principles above. The
  three quality gates are mandatory and non-negotiable. Unjustified complexity MUST be rejected.

**Version**: 1.0.0 | **Ratified**: 2026-06-04 | **Last Amended**: 2026-06-04
