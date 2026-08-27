import json
from datetime import date
from pathlib import Path
from unittest.mock import Mock

from sqlalchemy import select
from sqlalchemy.orm import Session

from kairos_report.config import Settings
from kairos_report.data.service import ReportDataService
from kairos_report.db import create_engine_for
from kairos_report.models import Base, ReportStatus, StudentReport
from kairos_report.runs.service import RunService
from kairos_report.tutory.client import ReportDocument, TutoryStudent

FIXTURE = Path(__file__).parents[1] / "fixtures" / "tutory" / "report_page.html"


def extracted_run(settings: Settings, *, malformed_second: bool = False) -> int:
    students = [
        TutoryStudent(id="s1", name="Ana Exemplo", raw_phone="(11) 99999-1111"),
        TutoryStudent(id="s2", name="Bia Exemplo", raw_phone="invalid"),
    ]
    names = {student.id: student.name for student in students}
    html = FIXTURE.read_text(encoding="utf-8")
    client = Mock()
    client.list_active_students.return_value = students

    def document_for(student_id: str, _start: date, _end: date) -> ReportDocument:
        if malformed_second and student_id == "s2":
            return ReportDocument(key="s2-key", html="<html>contrato alterado</html>")
        student_html = html.replace("Aluno Exemplo", names[student_id])
        return ReportDocument(key=f"{student_id}-key", html=student_html)

    client.generate_report.side_effect = document_for
    engine = create_engine_for(settings)
    Base.metadata.create_all(engine)
    engine.dispose()
    runs = RunService(settings, client)
    run = runs.create(date(2026, 8, 1), date(2026, 8, 31), "abc123", "data-v1")
    runs.extract(run.id, ["s1", "s2"])
    return run.id


def read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_export_contains_every_ready_student_without_phone_data(
    test_settings: Settings,
) -> None:
    run_id = extracted_run(test_settings)

    result = ReportDataService(test_settings).export(run_id)

    assert result.ready == 2
    assert result.expected == 2
    assert result.exported == 2
    assert result.complete is True
    assert result.blocked == 0
    assert result.pending == 0
    assert result.delivery_blocked == 1
    assert result.output_path == (
        test_settings.data_dir / "review" / "2026-08" / "report-data.jsonl"
    )
    records = read_jsonl(result.output_path)
    assert len(records) == 2
    assert [record["data_status"] for record in records] == ["ready", "ready"]
    assert [record["delivery_status"] for record in records] == ["ready", "blocked"]
    assert records[1]["issues"] == {"data": [], "delivery": ["invalid_phone"]}
    assert records[1]["data"]["identity"]["student_name"] == "Bia Exemplo"  # type: ignore[index]
    serialized = result.output_path.read_text(encoding="utf-8")
    assert "99999-1111" not in serialized
    assert "phone_ciphertext" not in serialized


def test_export_keeps_blocked_students_visible_in_the_batch(
    test_settings: Settings,
) -> None:
    run_id = extracted_run(test_settings, malformed_second=True)

    result = ReportDataService(test_settings).export(run_id)

    assert result.ready == 1
    assert result.blocked == 1
    assert result.complete is False
    records = read_jsonl(result.output_path)
    blocked = records[1]
    assert blocked["data_status"] == "blocked"
    assert blocked["data"] is None
    assert blocked["issues"] == {
        "data": ["tutory_contract_changed"],
        "delivery": ["invalid_phone"],
    }


def test_export_reports_an_incomplete_batch_instead_of_hiding_the_gap(
    test_settings: Settings,
) -> None:
    run_id = extracted_run(test_settings)
    engine = create_engine_for(test_settings)
    with Session(engine) as session:
        missing = session.scalar(
            select(StudentReport)
            .where(StudentReport.run_id == run_id)
            .order_by(StudentReport.id.desc())
        )
        assert missing is not None
        session.delete(missing)
        session.commit()
    engine.dispose()

    result = ReportDataService(test_settings).export(run_id)

    assert result.expected == 2
    assert result.exported == 1
    assert result.complete is False


def test_export_preserves_pending_students_for_safe_resume(test_settings: Settings) -> None:
    run_id = extracted_run(test_settings)
    engine = create_engine_for(test_settings)
    with Session(engine) as session:
        pending = session.scalar(
            select(StudentReport)
            .where(StudentReport.run_id == run_id)
            .order_by(StudentReport.id.desc())
        )
        assert pending is not None
        pending.status = ReportStatus.PENDING
        pending.metrics = {}
        session.commit()
    engine.dispose()

    result = ReportDataService(test_settings).export(run_id)

    assert result.ready == 1
    assert result.pending == 1
    assert result.complete is False
    records = read_jsonl(result.output_path)
    assert records[1]["data_status"] == "pending"
    assert records[1]["data"] is None
