from datetime import date

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from kairos_report.config import Settings
from kairos_report.db import create_engine_for, upgrade_database
from kairos_report.models import ReportRun, RunStatus, Student, StudentReport


def test_report_run_round_trip(db_session: Session) -> None:
    run = ReportRun(
        period_start=date(2026, 8, 1),
        period_end=date(2026, 8, 31),
        status=RunStatus.CREATED,
        code_version="dev",
        template_version="v1",
    )
    db_session.add(run)
    db_session.commit()

    stored = db_session.scalar(select(ReportRun))
    assert stored is not None
    assert stored.status is RunStatus.CREATED


def test_student_report_identity_is_unique_per_revision(db_session: Session) -> None:
    student = Student(tutory_id="student-1", name="Student", phone_ciphertext="encrypted")
    run = ReportRun(
        period_start=date(2026, 8, 1),
        period_end=date(2026, 8, 31),
        status=RunStatus.CREATED,
        code_version="dev",
        template_version="v1",
    )
    db_session.add_all([student, run])
    db_session.flush()
    db_session.add(
        StudentReport(
            run_id=run.id,
            student_id=student.id,
            period_start=run.period_start,
            period_end=run.period_end,
            revision=1,
        )
    )
    db_session.commit()

    assert db_session.scalar(select(StudentReport)) is not None


def test_migration_creates_schema_from_empty_database(test_settings: Settings) -> None:
    upgrade_database(test_settings)

    engine = create_engine_for(test_settings)
    table_names = set(inspect(engine).get_table_names())
    engine.dispose()

    assert {
        "students",
        "report_runs",
        "student_reports",
        "approvals",
        "deliveries",
        "audit_events",
    }.issubset(table_names)
