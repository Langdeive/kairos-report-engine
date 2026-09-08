import hashlib
import json
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from kairos_report.cli import app
from kairos_report.config import Settings
from kairos_report.data.service import ReportDataService
from kairos_report.db import create_engine_for
from kairos_report.models import ReportStatus, StudentReport
from kairos_report.tutory.client import TutoryStudent
from tests.integration.test_run_service import build_service


def prepared_run(settings: Settings, tmp_path: Path) -> int:
    service, _ = build_service(
        settings,
        [
            TutoryStudent(id="s1", name="Ana", raw_phone="(11) 99999-1234"),
            TutoryStudent(id="s2", name="Bia", raw_phone="invalid"),
        ],
    )
    run = service.create(date(2026, 8, 1), date(2026, 8, 31), "test", "approved")
    service.extract(run.id)
    engine = create_engine_for(settings)
    with Session(engine) as session:
        for report in session.scalars(select(StudentReport)):
            pdf = tmp_path / f"report-{report.id}.pdf"
            pdf.write_bytes(b"%PDF-1.4 synthetic fixture")
            report.pdf_path = str(pdf)
            report.pdf_hash = hashlib.sha256(pdf.read_bytes()).hexdigest()
        session.commit()
    engine.dispose()
    return run.id


def test_manifest_links_pdf_to_extracted_phone_without_comments(
    test_settings: Settings,
    tmp_path: Path,
) -> None:
    run_id = prepared_run(test_settings, tmp_path)
    result = ReportDataService(test_settings).export_delivery(run_id)
    items = json.loads(Path(result["output_path"]).read_text(encoding="utf-8"))["items"]
    assert result["ready"] == 1
    assert result["blocked"] == 1
    assert items[0]["student_id"] == "s1"
    assert items[0]["phone"] == "5511999991234"
    assert items[0]["pdf_path"] == str((tmp_path / "report-1.pdf").resolve())
    assert items[0]["ready_for_hermes"] is True
    assert items[1]["phone"] is None
    assert items[1]["issues"] == ["missing_or_invalid_phone"]
    assert Path(items[1]["pdf_path"]).exists()
    assert "5511999991234" not in json.dumps(result)


@pytest.mark.parametrize("problem", ["missing_pdf", "pdf_changed", "already_sent"])
def test_manifest_blocks_unusable_or_sent_documents(
    test_settings: Settings,
    tmp_path: Path,
    problem: str,
) -> None:
    run_id = prepared_run(test_settings, tmp_path)
    engine = create_engine_for(test_settings)
    with Session(engine) as session:
        report = session.get(StudentReport, 1)
        if problem == "missing_pdf":
            report.pdf_path = str(tmp_path / "missing.pdf")
        elif problem == "pdf_changed":
            report.pdf_hash = "incorrect-hash"
        else:
            report.status = ReportStatus.SENT
        session.commit()
    result = ReportDataService(test_settings).export_delivery(run_id)
    items = json.loads(Path(result["output_path"]).read_text(encoding="utf-8"))["items"]
    assert items[0]["ready_for_hermes"] is False
    assert problem in items[0]["issues"]
    engine.dispose()


def test_export_delivery_cli_outputs_only_summary(
    test_settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = prepared_run(test_settings, tmp_path)
    monkeypatch.setattr("kairos_report.cli._data_service", lambda: ReportDataService(test_settings))
    result = CliRunner().invoke(app, ["data", "export-delivery", "--run", str(run_id)])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["ready"] == 1
    assert "5511999991234" not in result.stdout
