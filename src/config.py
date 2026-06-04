"""Configuration loading and validation.

All settings come from environment variables (loaded from ``.env`` via
``python-dotenv``). :func:`load_config` validates every variable per
``specs/001-uni-email-notifier/contracts/config.md`` and fails fast with a
human-readable error that names the offending variable and never echoes the
value of a secret (``IMAP_PASSWORD`` / ``TELEGRAM_BOT_TOKEN``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

# Variables whose values must never appear in an error message or log line.
_SECRET_VARS = frozenset({"IMAP_PASSWORD", "TELEGRAM_BOT_TOKEN"})

# Non-secret defaults (from the user's existing mail client; see research §7).
_DEFAULTS = {
    "IMAP_HOST": "imap.uni-hildesheim.de",
    "IMAP_PORT": "993",
    "IMAP_SSL": "true",
    "IMAP_USER": "jdoe",
    "IMAP_FOLDER": "INBOX",
    "TIMEZONE": "Europe/Berlin",
    "SCHEDULE_START": "08:00",
    "SCHEDULE_END": "17:00",
    "DIGEST_THRESHOLD": "10",
    "RUN_MODE": "once",
    "DATA_DIR": "data",
}

_REQUIRED = ("IMAP_USER", "IMAP_PASSWORD", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")


class ConfigError(Exception):
    """Raised when configuration is missing or invalid.

    The message follows the contract format and never contains secret values.
    """


@dataclass(frozen=True)
class Config:
    """Immutable, validated runtime configuration."""

    imap_host: str
    imap_port: int
    imap_ssl: bool
    imap_user: str
    imap_password: str
    imap_folder: str
    telegram_bot_token: str
    telegram_chat_id: str
    timezone: ZoneInfo
    schedule_start: time
    schedule_end: time
    digest_threshold: int
    run_mode: str
    data_dir: str


def _required_error(var: str) -> ConfigError:
    return ConfigError(f"Configuration error: {var} is required")


def _invalid_error(var: str, reason: str) -> ConfigError:
    return ConfigError(f"Configuration error: {var} is invalid ({reason})")


def _get(env: dict, var: str) -> str | None:
    value = env.get(var, _DEFAULTS.get(var))
    if value is not None:
        value = value.strip()
    return value


def _parse_bool(var: str, value: str) -> bool:
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    raise _invalid_error(var, "must be 'true' or 'false'")


def _parse_int(var: str, value: str) -> int:
    try:
        return int(value)
    except ValueError:
        raise _invalid_error(var, "must be an integer") from None


def _parse_time(var: str, value: str) -> time:
    parts = value.split(":")
    if len(parts) != 2:
        raise _invalid_error(var, "must be HH:MM")
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except ValueError:
        raise _invalid_error(var, "must be HH:MM") from None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise _invalid_error(var, "must be HH:MM, 00:00-23:59")
    return time(hour, minute)


def load_config(env: dict | None = None) -> Config:
    """Load and validate configuration.

    Args:
        env: Optional mapping to read from (defaults to ``os.environ`` after
            loading ``.env``). Injectable for tests.

    Returns:
        A frozen :class:`Config`.

    Raises:
        ConfigError: On any missing or invalid variable. The message names the
            variable and never includes a secret value.
    """
    if env is None:
        load_dotenv()
        env = dict(os.environ)

    # Required variables must be present and non-empty (after defaults).
    for var in _REQUIRED:
        value = _get(env, var)
        if not value:
            raise _required_error(var)

    imap_host = _get(env, "IMAP_HOST")
    if not imap_host:
        raise _required_error("IMAP_HOST")

    imap_port = _parse_int("IMAP_PORT", _get(env, "IMAP_PORT"))
    if not (1 <= imap_port <= 65535):
        raise _invalid_error("IMAP_PORT", "must be between 1 and 65535")

    imap_ssl = _parse_bool("IMAP_SSL", _get(env, "IMAP_SSL"))

    imap_folder = _get(env, "IMAP_FOLDER")
    if not imap_folder:
        raise _required_error("IMAP_FOLDER")

    tz_name = _get(env, "TIMEZONE")
    try:
        timezone = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        raise _invalid_error("TIMEZONE", "must be a valid IANA timezone") from None

    schedule_start = _parse_time("SCHEDULE_START", _get(env, "SCHEDULE_START"))
    schedule_end = _parse_time("SCHEDULE_END", _get(env, "SCHEDULE_END"))
    if schedule_end < schedule_start:
        raise _invalid_error("SCHEDULE_END", "must be >= SCHEDULE_START")

    digest_threshold = _parse_int("DIGEST_THRESHOLD", _get(env, "DIGEST_THRESHOLD"))
    if digest_threshold < 1:
        raise _invalid_error("DIGEST_THRESHOLD", "must be >= 1")

    run_mode = _get(env, "RUN_MODE")
    if run_mode != "once":
        raise _invalid_error("RUN_MODE", "must be 'once'")

    data_dir = _get(env, "DATA_DIR")
    if not data_dir:
        raise _required_error("DATA_DIR")

    return Config(
        imap_host=imap_host,
        imap_port=imap_port,
        imap_ssl=imap_ssl,
        imap_user=_get(env, "IMAP_USER"),
        imap_password=_get(env, "IMAP_PASSWORD"),
        imap_folder=imap_folder,
        telegram_bot_token=_get(env, "TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=_get(env, "TELEGRAM_CHAT_ID"),
        timezone=timezone,
        schedule_start=schedule_start,
        schedule_end=schedule_end,
        digest_threshold=digest_threshold,
        run_mode=run_mode,
        data_dir=data_dir,
    )
