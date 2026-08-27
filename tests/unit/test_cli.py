import json
from datetime import date
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from kairos_report.cli import app
from kairos_report.config import Settings
from kairos_report.db import create_engine_for, upgrade_database
from kairos_report.models import ReportRun, ReportStatus, RunStatus, Student, StudentReport
from kairos_report.tutory.parser import parse_report

REPORT_FIXTURE = Path(__file__).parents[1] / "fixtures" / "tutory" / "report_page.html"


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


def test_data_export_command_writes_the_canonical_student_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TUTORY_API_TOKEN", "test-token")
    monkeypatch.setenv("TUTORY_ACCOUNT", "test-account")
    monkeypatch.setenv("TUTORY_PASSWORD", "test-password")
    monkeypatch.setenv("KAIROS_DATA_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("KAIROS_DATA_DIR", str(tmp_path))
    settings = Settings.load()
    upgrade_database(settings)
    engine = create_engine_for(settings)
    with Session(engine) as session:
        student = Student(tutory_id="s1", name="Aluno Exemplo", phone_ciphertext="encrypted")
        run = ReportRun(
            period_start=date(2026, 8, 1),
            period_end=date(2026, 8, 31),
            status=RunStatus.AWAITING_COMMENTS,
            code_version="abc123",
            template_version="data-v1",
            expected_count=1,
        )
        session.add_all([student, run])
        session.flush()
        session.add(
            StudentReport(
                run_id=run.id,
                student_id=student.id,
                period_start=run.period_start,
                period_end=run.period_end,
                revision=1,
                status=ReportStatus.VALID,
                metrics=parse_report(REPORT_FIXTURE.read_text(encoding="utf-8")).model_dump(
                    mode="json"
                ),
            )
        )
        session.commit()
        run_id = run.id
    engine.dispose()
    output = tmp_path / "exports" / "august.jsonl"

    result = CliRunner().invoke(
        app,
        ["data", "export", "--run", str(run_id), "--output", str(output)],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ready"] == 1
    assert payload["blocked"] == 0
    assert payload["output_path"] == str(output)
    assert output.exists()
