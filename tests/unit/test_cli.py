import json
from datetime import date
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from pypdf import PdfReader
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from kairos_report.cli import app
from kairos_report.config import Settings
from kairos_report.db import create_engine_for, upgrade_database
from kairos_report.errors import KairosReportError
from kairos_report.models import ReportRun, ReportStatus, RunStatus, Student, StudentReport
from kairos_report.tutory.client import ReportBundle
from kairos_report.tutory.parser import parse_question_report, parse_report
from tests.daily_fixtures import performance_html, question_html

REPORT_FIXTURE = Path(__file__).parents[1] / "fixtures" / "tutory" / "report_page.html"
QUESTION_FIXTURE = Path(__file__).parents[1] / "fixtures" / "tutory" / "question_report_page.html"
ACTIVITY_FIXTURE = Path(__file__).parents[1] / "fixtures" / "tutory" / "student_report_page.html"


class FixtureLiveTutoryClient:
    def __init__(self, _settings: Settings) -> None:
        pass

    def generate_report_bundle(
        self,
        _student_id: str,
        _period_start: date,
        _period_end: date,
        *,
        models: tuple[str, ...],
        grouping: str = "semana",
    ) -> ReportBundle:
        assert grouping == "dia"
        documents = {
            "desempenho": performance_html(_period_start.year, _period_start.month),
            "questoes": question_html(
                labels=[f"{_period_start:%Y/%m/%d}", f"{_period_end:%Y/%m/%d}"],
                total=541, headline_correct=442, correct=[400, 42], wrong=[90, 9],
            ),
            "aluno": ACTIVITY_FIXTURE.read_text(encoding="utf-8"),
        }
        return ReportBundle(
            key="fixture-key",
            documents={model: documents[model] for model in models},
        )


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
    monkeypatch.setattr("kairos_report.cli._chromium_available", lambda: False)

    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["data_directory_writable"] is True
    assert payload["database_path"] == str(tmp_path / "database" / "kairos.sqlite3")
    assert payload["approved_pdf_assets_ready"] is True
    assert payload["chromium_required"] is False
    assert payload["chromium_available"] is False
    assert payload["approval_mode"] == "required"
    assert payload["retention_months"] == 12
    assert token not in result.stdout
    assert data_key not in result.stdout


def test_doctor_reports_missing_pdf_assets_without_failing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class MissingAssets:
        def validate(self) -> None:
            raise FileNotFoundError("synthetic missing asset")

    monkeypatch.setenv("TUTORY_API_TOKEN", "test-token")
    monkeypatch.setenv("TUTORY_ACCOUNT", "test-account")
    monkeypatch.setenv("TUTORY_PASSWORD", "test-password")
    monkeypatch.setenv("KAIROS_DATA_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("KAIROS_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("kairos_report.cli.default_approved_assets", MissingAssets)
    monkeypatch.setattr("kairos_report.cli._chromium_available", lambda: False)

    result = CliRunner().invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["approved_pdf_assets_ready"] is False


def test_run_create_and_status_return_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_run_extract_accepts_repeated_student_options(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[object] = []

    class FakeRunService:
        def extract(self, run_id: int, student_ids: list[str] | None = None) -> object:
            captured.extend([run_id, student_ids])
            return type("Summary", (), {"model_dump_json": lambda self: "{}"})()

    monkeypatch.setattr("kairos_report.cli._run_service", lambda: FakeRunService())

    result = CliRunner().invoke(
        app, ["run", "extract", "--run", "7", "--student", "s2", "--student", "s1"]
    )

    assert result.exit_code == 0
    assert captured == [7, ["s2", "s1"]]


def test_run_extract_prints_sanitized_operational_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingRunService:
        def extract(self, run_id: int, student_ids: list[str] | None = None) -> object:
            del run_id, student_ids
            raise KairosReportError("Extraction is already in progress")

    monkeypatch.setattr("kairos_report.cli._run_service", lambda: FailingRunService())

    result = CliRunner().invoke(app, ["run", "extract", "--run", "7"])

    assert result.exit_code == 1
    assert "Extraction is already in progress" in result.stdout
    assert "Traceback" not in result.stdout


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
                metrics={
                    **parse_report(performance_html(), period_start=run.period_start,
                                   period_end=run.period_end).model_dump(mode="json"),
                    "questions": parse_question_report(
                        question_html(), period_start=run.period_start, period_end=run.period_end
                    ).model_dump(mode="json"),
                },
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


def test_report_generate_live_fetches_normalizes_and_renders_in_one_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TUTORY_API_TOKEN", "test-token")
    monkeypatch.setenv("TUTORY_ACCOUNT", "test-account")
    monkeypatch.setenv("TUTORY_PASSWORD", "test-password")
    monkeypatch.setenv("KAIROS_DATA_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("KAIROS_DATA_DIR", str(tmp_path / "runtime"))
    monkeypatch.setattr("kairos_report.cli.TutoryClient", FixtureLiveTutoryClient)
    output = tmp_path / "real-report.pdf"
    data_output = tmp_path / "real-report.json"
    previews = tmp_path / "previews"

    result = CliRunner().invoke(
        app,
        [
            "report",
            "generate-live",
            "--month",
            "2026-07",
            "--student-id",
            "student-1",
            "--output",
            str(output),
            "--data-output",
            str(data_output),
            "--previews",
            str(previews),
        ],
    )

    assert result.exit_code == 0
    assert output.exists()
    assert len(PdfReader(output).pages) == 5
    package = json.loads(data_output.read_text(encoding="utf-8"))
    assert package["questions"]["total"] == 541
    assert package["summary"]["total_hours"] == 15
    assert package["summary"]["study_days"] == 9
    assert package["student_activity"]["total_revisions"] == 3
    assert len(list(previews.glob("pagina-*.png"))) == len(PdfReader(output).pages)
