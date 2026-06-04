"""Unit tests for src.config."""

from datetime import time

import pytest

from src.config import ConfigError, load_config


def _valid_env(**overrides):
    env = {
        "IMAP_PASSWORD": "secret-pass",
        "TELEGRAM_BOT_TOKEN": "secret-token",
        "TELEGRAM_CHAT_ID": "12345",
    }
    env.update(overrides)
    return env


def test_defaults_applied():
    cfg = load_config(_valid_env())
    assert cfg.imap_host == "imap.uni-hildesheim.de"
    assert cfg.imap_port == 993
    assert cfg.imap_ssl is True
    assert cfg.imap_user == "jdoe"
    assert cfg.imap_folder == "INBOX"
    assert str(cfg.timezone) == "Europe/Berlin"
    assert cfg.schedule_start == time(8, 0)
    assert cfg.schedule_end == time(17, 0)
    assert cfg.digest_threshold == 10
    assert cfg.run_mode == "once"
    assert cfg.data_dir == "data"


@pytest.mark.parametrize(
    "missing", ["IMAP_PASSWORD", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]
)
def test_missing_required_rejected(missing):
    env = _valid_env()
    del env[missing]
    with pytest.raises(ConfigError) as exc:
        load_config(env)
    assert missing in str(exc.value)
    assert "required" in str(exc.value)


def test_empty_required_rejected():
    with pytest.raises(ConfigError) as exc:
        load_config(_valid_env(IMAP_PASSWORD="   "))
    assert "IMAP_PASSWORD is required" in str(exc.value)


@pytest.mark.parametrize("port", ["0", "70000", "abc"])
def test_invalid_imap_port_rejected(port):
    with pytest.raises(ConfigError) as exc:
        load_config(_valid_env(IMAP_PORT=port))
    assert "IMAP_PORT" in str(exc.value)


@pytest.mark.parametrize("value", ["25:00", "08", "8:99", "noon"])
def test_invalid_schedule_rejected(value):
    with pytest.raises(ConfigError) as exc:
        load_config(_valid_env(SCHEDULE_START=value))
    assert "SCHEDULE_START" in str(exc.value)


def test_invalid_timezone_rejected():
    with pytest.raises(ConfigError) as exc:
        load_config(_valid_env(TIMEZONE="Mars/Phobos"))
    assert "TIMEZONE" in str(exc.value)


@pytest.mark.parametrize("value", ["0", "-1", "x"])
def test_invalid_digest_threshold_rejected(value):
    with pytest.raises(ConfigError) as exc:
        load_config(_valid_env(DIGEST_THRESHOLD=value))
    assert "DIGEST_THRESHOLD" in str(exc.value)


def test_schedule_end_before_start_rejected():
    with pytest.raises(ConfigError) as exc:
        load_config(_valid_env(SCHEDULE_START="17:00", SCHEDULE_END="08:00"))
    assert "SCHEDULE_END" in str(exc.value)


def test_schedule_end_equal_start_allowed():
    cfg = load_config(_valid_env(SCHEDULE_START="09:00", SCHEDULE_END="09:00"))
    assert cfg.schedule_start == cfg.schedule_end


def test_run_mode_must_be_once():
    with pytest.raises(ConfigError) as exc:
        load_config(_valid_env(RUN_MODE="loop"))
    assert "RUN_MODE" in str(exc.value)


def test_secret_values_never_in_error_messages():
    secret_pw = "SUPERSECRETPW123"
    secret_tok = "SUPERSECRETTOKEN456"
    # Force an unrelated invalid value while secrets are present and valid.
    env = _valid_env(
        IMAP_PASSWORD=secret_pw,
        TELEGRAM_BOT_TOKEN=secret_tok,
        IMAP_PORT="not-a-number",
    )
    with pytest.raises(ConfigError) as exc:
        load_config(env)
    assert secret_pw not in str(exc.value)
    assert secret_tok not in str(exc.value)
