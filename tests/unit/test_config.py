from pathlib import Path

import pytest

from kairos_report.config import Settings


def test_settings_allow_tutory_token_to_be_discovered_after_login(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TUTORY_API_TOKEN", raising=False)
    monkeypatch.setenv("TUTORY_ACCOUNT", "test-account")
    monkeypatch.setenv("TUTORY_PASSWORD", "test-password")
    monkeypatch.setenv("KAIROS_DATA_KEY", "test-only-data-key")
    monkeypatch.setenv("KAIROS_DATA_DIR", str(tmp_path))

    settings = Settings.load()

    assert settings.tutory_api_token is None


def test_settings_require_data_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TUTORY_API_TOKEN", "test-token")
    monkeypatch.setenv("TUTORY_ACCOUNT", "test-account")
    monkeypatch.setenv("TUTORY_PASSWORD", "test-password")
    monkeypatch.delenv("KAIROS_DATA_KEY", raising=False)
    monkeypatch.setenv("KAIROS_DATA_DIR", str(tmp_path))

    with pytest.raises(ValueError, match="KAIROS_DATA_KEY"):
        Settings.load()


def test_settings_require_tutory_login(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TUTORY_API_TOKEN", "test-token")
    monkeypatch.delenv("TUTORY_ACCOUNT", raising=False)
    monkeypatch.delenv("TUTORY_PASSWORD", raising=False)
    monkeypatch.setenv("KAIROS_DATA_KEY", "test-only-data-key")
    monkeypatch.setenv("KAIROS_DATA_DIR", str(tmp_path))

    with pytest.raises(ValueError, match="TUTORY_ACCOUNT"):
        Settings.load()


def test_settings_load_safe_http_and_batch_controls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TUTORY_API_TOKEN", "test-token")
    monkeypatch.setenv("TUTORY_ACCOUNT", "test-account")
    monkeypatch.setenv("TUTORY_PASSWORD", "test-password")
    monkeypatch.setenv("KAIROS_DATA_KEY", "test-only-data-key")
    monkeypatch.setenv("KAIROS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TUTORY_HTTP_MAX_ATTEMPTS", "4")
    monkeypatch.setenv("TUTORY_REQUEST_SPACING_SECONDS", "0.25")
    monkeypatch.setenv("TUTORY_RETRY_BASE_SECONDS", "2")
    monkeypatch.setenv("TUTORY_RETRY_MAX_SECONDS", "15")
    monkeypatch.setenv("KAIROS_BATCH_SIZE", "7")
    monkeypatch.setenv("KAIROS_BATCH_PAUSE_SECONDS", "12")
    monkeypatch.setenv("KAIROS_MAX_CONSECUTIVE_UPSTREAM_FAILURES", "2")

    settings = Settings.load()

    assert settings.tutory_http_max_attempts == 4
    assert settings.tutory_request_spacing_seconds == 0.25
    assert settings.tutory_retry_base_seconds == 2
    assert settings.tutory_retry_max_seconds == 15
    assert settings.batch_size == 7
    assert settings.batch_pause_seconds == 12
    assert settings.max_consecutive_upstream_failures == 2
