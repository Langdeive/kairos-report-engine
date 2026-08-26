from pathlib import Path

import pytest

from kairos_report.config import Settings


def test_settings_require_tutory_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TUTORY_API_TOKEN", raising=False)
    monkeypatch.setenv("TUTORY_ACCOUNT", "test-account")
    monkeypatch.setenv("TUTORY_PASSWORD", "test-password")
    monkeypatch.setenv("KAIROS_DATA_KEY", "test-only-data-key")
    monkeypatch.setenv("KAIROS_DATA_DIR", str(tmp_path))

    with pytest.raises(ValueError, match="TUTORY_API_TOKEN"):
        Settings.load()


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
