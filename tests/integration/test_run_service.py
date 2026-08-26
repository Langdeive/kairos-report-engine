from datetime import date
from pathlib import Path
from unittest.mock import Mock

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from kairos_report.config import Settings
from kairos_report.db import create_engine_for
from kairos_report.models import Base, ReportStatus, StudentReport
from kairos_report.runs.service import RunService
from kairos_report.tutory.client import ReportDocument, TutoryStudent

FIXTURE = Path(__file__).parents[1] / "fixtures" / "tutory" / "report_page.html"


def build_service(settings: Settings, students: list[TutoryStudent]) -> tuple[RunService, Mock]:
    client = Mock()
    client.list_active_students.return_value = students
    client.generate_report.return_value = ReportDocument(
        key="report-key", html=FIXTURE.read_text(encoding="utf-8")
    )
    engine = create_engine_for(settings)
    Base.metadata.create_all(engine)
    return RunService(settings, client), client


def test_extract_resume_skips_completed_students(test_settings: Settings) -> None:
    service, client = build_service(
        test_settings,
        [
            TutoryStudent(id="s1", name="Ana", raw_phone="(11) 99999-1111"),
            TutoryStudent(id="s2", name="Bia", raw_phone="(11) 99999-2222"),
        ],
    )
    run = service.create(date(2026, 8, 1), date(2026, 8, 31), "abc123", "v1")

    service.extract(run.id, ["s1", "s2"])
    service.extract(run.id, ["s1", "s2"])

    assert client.generate_report.call_count == 2


def test_invalid_phone_blocks_only_that_student(test_settings: Settings) -> None:
    service, client = build_service(
        test_settings,
        [
            TutoryStudent(id="s1", name="Ana", raw_phone="(11) 99999-1111"),
            TutoryStudent(id="s2", name="Bia", raw_phone="invalid"),
        ],
    )
    run = service.create(date(2026, 8, 1), date(2026, 8, 31), "abc123", "v1")

    summary = service.extract(run.id, ["s1", "s2"])

    assert summary.expected == 2
    assert summary.valid == 1
    assert summary.blocked == 1
    assert client.generate_report.call_count == 1


def test_500_students_are_processed_once_and_resume_without_duplicates(
    test_settings: Settings,
) -> None:
    students = [
        TutoryStudent(id=f"s{index:03}", name=f"Student {index}", raw_phone="11999991234")
        for index in range(500)
    ]
    service, client = build_service(test_settings, students)
    run = service.create(date(2026, 8, 1), date(2026, 8, 31), "abc123", "v1")

    first = service.extract(run.id, [student.id for student in students])
    second = service.extract(run.id, [student.id for student in students])

    assert first.expected == first.valid == 500
    assert second.expected == second.valid == 500
    assert client.generate_report.call_count == 500
    engine = create_engine_for(test_settings)
    with Session(engine) as session:
        report_count = session.scalar(select(func.count()).select_from(StudentReport))
        valid_count = session.scalar(
            select(func.count())
            .select_from(StudentReport)
            .where(StudentReport.status == ReportStatus.VALID)
        )
    engine.dispose()
    assert report_count == valid_count == 500
