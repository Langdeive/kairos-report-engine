import json
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from typer.testing import CliRunner

from kairos_report.cli import app


def test_doctor_reports_local_readiness_without_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = "secret-tutory-token"
    data_key = Fernet.generate_key().decode()
    monkeypatch.setenv("TUTORY_API_TOKEN", token)
    monkeypatch.setenv("TUTORY_ACCOUNT", "test-account")
    monkeypatch.setenv("TUTORY_PASSWORD", "test-password")
    monkeypatch.setenv("KAIROS_DATA_KEY", data_key)
    monkeypatch.setenv("KAIROS_DATA_DIR", str(tmp_path))

    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["data_directory_writable"] is True
    assert payload["database_path"] == str(tmp_path / "database" / "kairos.sqlite3")
    assert isinstance(payload["chromium_available"], bool)
    assert payload["approval_mode"] == "required"
    assert payload["retention_months"] == 12
    assert token not in result.stdout
    assert data_key not in result.stdout


def test_run_create_and_status_return_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TUTORY_API_TOKEN", "test-token")
    monkeypatch.setenv("TUTORY_ACCOUNT", "test-account")
    monkeypatch.setenv("TUTORY_PASSWORD", "test-password")
    monkeypatch.setenv("KAIROS_DATA_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("KAIROS_DATA_DIR", str(tmp_path))

    created = CliRunner().invoke(app, ["run", "create", "--month", "2026-08"])

    assert created.exit_code == 0
    run_id = json.loads(created.stdout)["run_id"]
    status = CliRunner().invoke(app, ["run", "status", "--run", str(run_id)])
    assert status.exit_code == 0
    assert json.loads(status.stdout)["expected"] == 0
