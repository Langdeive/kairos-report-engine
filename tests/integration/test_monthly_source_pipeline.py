import hashlib
import json
from datetime import date
from pathlib import Path

import pytest
from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.orm import Session

from kairos_report.config import Settings
from kairos_report.data.service import ReportDataService
from kairos_report.db import create_engine_for
from kairos_report.models import ReportStatus, StudentReport
from kairos_report.pdf import generate_approved_report
from kairos_report.report_data import build_report_data
from kairos_report.tutory.client import TutoryStudent
from kairos_report.tutory.parser import parse_report
from tests.daily_fixtures import FIXTURE, performance_html, question_html
from tests.integration.test_run_service import build_service

START, END = date(2026, 8, 1), date(2026, 8, 31)


def test_protected_cycle_persists_daily_monthly_totals_through_pdf_and_delivery(
    test_settings: Settings,
) -> None:
    service, client = build_service(
        test_settings, [TutoryStudent(id="s1", name="Exemplo", raw_phone="11999991111")]
    )
    docs = client.generate_report_bundle.return_value.documents
    docs["desempenho"] = performance_html()
    docs["questoes"] = question_html()
    run = service.create(START, END, "test", "monthly")
    assert service.extract(run.id).valid == 1
    client.generate_report_bundle.assert_called_once_with("s1", START, END, grouping="dia")
    data_service = ReportDataService(test_settings)
    export = data_service.export(run.id)
    assert export.ready == 1
    record = json.loads(export.output_path.read_text())
    assert record["data"]["summary"]["total_hours"] == 15
    assert record["data"]["summary"]["study_days"] == 9
    result = data_service.generate(run.id)
    assert result["generated"] == 1
    assert result["delivery_manifest"]["ready"] == 1
    engine = create_engine_for(test_settings)
    with Session(engine) as session:
        stored = session.scalar(select(StudentReport))
        assert stored.metrics["total_hours"] == 15
        assert stored.metrics["study_days"] == 9
        assert stored.metrics["monthly_source"]["period_start"] == "2026-08-01"
        assert len(stored.metrics["monthly_source"]["daily"]) == 31
        assert stored.metrics["questions"]["total"] == 670
        assert all("date" not in row for row in stored.metrics["student_activity"]["activities"])
        assert len(PdfReader(stored.pdf_path).pages) >= 4
    engine.dispose()


@pytest.mark.parametrize("status", [ReportStatus.VALID, ReportStatus.APPROVED, ReportStatus.SENT])
def test_legacy_snapshot_is_readable_but_cannot_be_automatically_ready(
    test_settings: Settings,
    tmp_path: Path,
    status: ReportStatus,
) -> None:
    service, _ = build_service(
        test_settings, [TutoryStudent(id="s1", name="Exemplo", raw_phone="11999991111")]
    )
    run = service.create(START, END, "test", "monthly")
    service.extract(run.id)
    legacy = parse_report(FIXTURE.read_text(encoding="utf-8"))
    offline = build_report_data(report_id=1, period_start=START, period_end=END, metrics=legacy)
    pdf = generate_approved_report(offline, tmp_path / "legacy-preview.pdf")
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    engine = create_engine_for(test_settings)
    with Session(engine) as session:
        report = session.scalar(select(StudentReport))
        report.metrics = legacy.model_dump(mode="json")
        report.status = status
        report.pdf_path, report.pdf_hash = str(pdf), digest
        session.commit()
    data_service = ReportDataService(test_settings)
    exported = data_service.export(run.id)
    assert exported.ready == 0
    record = json.loads(exported.output_path.read_text())
    assert "monthly_source_unverified" in record["issues"]["data"]
    assert data_service.generate(run.id)["generated"] == 0
    manifest = data_service.export_delivery(run.id)
    assert manifest["ready"] == 0
    item = json.loads(Path(manifest["output_path"]).read_text())["items"][0]
    assert "monthly_source_unverified" in item["issues"]
    if status == ReportStatus.SENT:
        assert "already_sent" in item["issues"]
    assert hashlib.sha256(pdf.read_bytes()).hexdigest() == digest
    with Session(engine) as session:
        report = session.scalar(select(StudentReport))
        assert report.status == status
        assert report.metrics == legacy.model_dump(mode="json")
    engine.dispose()
