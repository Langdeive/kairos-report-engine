from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from threading import Event, Thread
from unittest.mock import Mock

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from kairos_report.config import Settings
from kairos_report.db import create_engine_for
from kairos_report.errors import (
    KairosReportError,
    TutoryAuthenticationError,
    TutoryContractChanged,
    TutoryGenerationUncertain,
    TutoryRetryPaused,
    TutoryTemporaryError,
)
from kairos_report.models import (
    AuditEvent,
    Base,
    ReportRun,
    ReportStatus,
    RunStatus,
    Student,
    StudentReport,
)
from kairos_report.runs.service import RunService
from kairos_report.tutory.client import ReportBundle, TutoryStudent

FIXTURE = Path(__file__).parents[1] / "fixtures" / "tutory" / "report_page.html"


def build_service(settings: Settings, students: list[TutoryStudent]) -> tuple[RunService, Mock]:
    client = Mock()
    def list_active_students(
        *, student_ids: list[str] | tuple[str, ...] | None = None, include_phones: bool = False
    ) -> list[TutoryStudent]:
        del include_phones
        if student_ids is None:
            return list(students)
        selected_ids = set(student_ids)
        return [student for student in students if student.id in selected_ids]

    client.list_active_students.side_effect = list_active_students
    client.generate_report_bundle.return_value = ReportBundle(
        key="report-key",
        documents={
            "desempenho": FIXTURE.read_text(encoding="utf-8"),
            "questoes": FIXTURE.with_name("question_report_page.html").read_text(encoding="utf-8"),
            "aluno": FIXTURE.with_name("student_report_page.html").read_text(encoding="utf-8"),
        },
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

    assert client.generate_report_bundle.call_count == 2


def test_invalid_phone_does_not_prevent_report_data_extraction(
    test_settings: Settings,
) -> None:
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
    assert summary.valid == 2
    assert summary.blocked == 0
    assert client.generate_report_bundle.call_count == 2
    engine = create_engine_for(test_settings)
    with Session(engine) as session:
        report = session.scalar(select(StudentReport).join(Student).where(Student.name == "Bia"))
        assert report is not None
        assert report.status == ReportStatus.VALID
        assert report.validation_errors == ["invalid_phone"]
        assert report.student.phone_ciphertext is None
    engine.dispose()


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
    assert client.generate_report_bundle.call_count == 500
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


def test_extract_validates_run_before_calling_tutory(test_settings: Settings) -> None:
    service, client = build_service(test_settings, [])

    with pytest.raises(ValueError, match="does not exist"):
        service.extract(999, ["s1"])

    client.list_active_students.assert_not_called()


def test_extract_freezes_first_selected_membership_on_resume(test_settings: Settings) -> None:
    service, client = build_service(
        test_settings,
        [
            TutoryStudent(id="s1", name="Ana", raw_phone="11999991111"),
            TutoryStudent(id="s2", name="Bia", raw_phone="11999992222"),
        ],
    )
    run = service.create(date(2026, 8, 1), date(2026, 8, 31), "abc123", "v1")

    first = service.extract(run.id, ["s1"])
    # The source list changes, as the live Tutory roster could change between cycles.
    new_student = TutoryStudent(id="s3", name="Caio", raw_phone="11999993333")
    client.list_active_students.side_effect = lambda **kwargs: [new_student]
    resumed = service.extract(run.id)

    assert first.expected == resumed.expected == 1
    engine = create_engine_for(test_settings)
    with Session(engine) as session:
        ids = list(
            session.scalars(
                select(Student.tutory_id).join(StudentReport).where(StudentReport.run_id == run.id)
            )
        )
    engine.dispose()
    assert ids == ["s1"]
    assert client.list_active_students.call_count == 1


def test_extract_rejects_changed_explicit_selection_before_network(
    test_settings: Settings,
) -> None:
    service, client = build_service(
        test_settings,
        [
            TutoryStudent(id="s1", name="Ana", raw_phone="11999991111"),
            TutoryStudent(id="s2", name="Bia", raw_phone="11999992222"),
        ],
    )
    run = service.create(date(2026, 8, 1), date(2026, 8, 31), "abc123", "v1")
    service.extract(run.id, ["s1"])

    with pytest.raises(ValueError, match="selection is already frozen"):
        service.extract(run.id, ["s2"])

    assert client.list_active_students.call_count == 1


def test_legacy_run_freezes_membership_from_existing_records(test_settings: Settings) -> None:
    service, client = build_service(
        test_settings,
        [
            TutoryStudent(id="s1", name="Ana", raw_phone="11999991111"),
            TutoryStudent(id="s2", name="Bia", raw_phone="11999992222"),
        ],
    )
    engine = create_engine_for(test_settings)
    with Session(engine) as session:
        student = Student(tutory_id="s1", name="Ana")
        run = ReportRun(
            period_start=date(2026, 8, 1),
            period_end=date(2026, 8, 31),
            status=RunStatus.EXTRACTING,
            code_version="abc123",
            template_version="v1",
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
                status=ReportStatus.PENDING,
            )
        )
        session.commit()
        run_id = run.id

    summary = service.extract(run_id)

    assert summary.expected == summary.valid == 1
    client.list_active_students.assert_not_called()
    with Session(engine) as session:
        frozen = session.scalar(
            select(AuditEvent).where(
                AuditEvent.run_id == run_id,
                AuditEvent.event_type == "run.selection_frozen",
            )
        )
        assert frozen is not None
        assert frozen.details["student_ids"] == ["s1"]
    engine.dispose()


def test_empty_run_is_frozen_once_and_completed_without_reenumeration(
    test_settings: Settings,
) -> None:
    service, client = build_service(test_settings, [])
    run = service.create(date(2026, 8, 1), date(2026, 8, 31), "abc123", "v1")

    first = service.extract(run.id)
    resumed = service.extract(run.id)

    assert first.expected == resumed.expected == 0
    assert client.list_active_students.call_count == 1
    engine = create_engine_for(test_settings)
    with Session(engine) as session:
        stored = session.get(ReportRun, run.id)
        assert stored is not None
        assert stored.status == RunStatus.COMPLETED
        frozen = session.scalar(
            select(AuditEvent).where(
                AuditEvent.run_id == run.id,
                AuditEvent.event_type == "run.selection_frozen",
            )
        )
        assert frozen is not None
        assert frozen.details["student_ids"] == []
    engine.dispose()


def test_extract_blocks_ambiguous_generation_for_manual_reconciliation(
    test_settings: Settings,
) -> None:
    service, client = build_service(
        test_settings,
        [TutoryStudent(id="s1", name="Ana", raw_phone="11999991111")],
    )
    client.generate_report_bundle.side_effect = TutoryGenerationUncertain("uncertain")
    run = service.create(date(2026, 8, 1), date(2026, 8, 31), "abc123", "v1")

    summary = service.extract(run.id, ["s1"])

    assert summary.blocked == 1
    assert summary.pending == 0
    engine = create_engine_for(test_settings)
    with Session(engine) as session:
        report = session.scalar(select(StudentReport).where(StudentReport.run_id == run.id))
        assert report is not None
        assert "tutory_generation_uncertain" in report.validation_errors
    engine.dispose()
    client.generate_report_bundle.reset_mock()
    client.generate_report_bundle.side_effect = None
    resumed = service.extract(run.id)
    assert resumed.blocked == 1
    client.generate_report_bundle.assert_not_called()


def test_ambiguous_failures_block_students_and_open_upstream_circuit(
    test_settings: Settings,
) -> None:
    students = [
        TutoryStudent(id=f"s{index}", name=f"Student {index}", raw_phone="11999991111")
        for index in range(4)
    ]
    service, client = build_service(test_settings, students)
    client.generate_report_bundle.side_effect = TutoryGenerationUncertain("uncertain")
    run = service.create(date(2026, 8, 1), date(2026, 8, 31), "abc123", "v1")

    summary = service.extract(run.id)

    assert summary.blocked == 3
    assert summary.pending == 1
    assert summary.upstream_failures == 3
    assert summary.circuit_stopped is True
    assert client.generate_report_bundle.call_count == 3


def test_repeated_contract_failures_block_students_and_open_upstream_circuit(
    test_settings: Settings,
) -> None:
    students = [
        TutoryStudent(id=f"s{index}", name=f"Student {index}", raw_phone="11999991111")
        for index in range(4)
    ]
    service, client = build_service(test_settings, students)
    client.generate_report_bundle.side_effect = TutoryContractChanged("changed")
    run = service.create(date(2026, 8, 1), date(2026, 8, 31), "abc123", "v1")

    summary = service.extract(run.id)

    assert summary.blocked == 3
    assert summary.pending == 1
    assert summary.upstream_failures == 3
    assert summary.circuit_stopped is True
    assert client.generate_report_bundle.call_count == 3


def test_post_generation_auth_blocks_current_and_stops_before_next_student(
    test_settings: Settings,
) -> None:
    students = [
        TutoryStudent(id="s1", name="Ana", raw_phone="11999991111"),
        TutoryStudent(id="s2", name="Bia", raw_phone="11999992222"),
    ]
    service, client = build_service(test_settings, students)
    client.generate_report_bundle.side_effect = TutoryGenerationUncertain(
        "post-generation auth failure", stop_reason="auth"
    )
    run = service.create(date(2026, 8, 1), date(2026, 8, 31), "abc123", "v1")

    summary = service.extract(run.id)

    assert summary.blocked == 1
    assert summary.pending == 1
    assert summary.auth_stopped is True
    assert client.generate_report_bundle.call_count == 1


@pytest.mark.parametrize(
    ("failure", "expect_cooldown"),
    [
        (
            TutoryGenerationUncertain(
                "post-generation auth failure", stop_reason="auth"
            ),
            False,
        ),
        (TutoryGenerationUncertain("post-generation exhausted GET"), False),
            (
                TutoryGenerationUncertain(
                    "post-generation retry pause",
                    retry_after_seconds=12,
                    stop_reason="retry_paused",
                ),
            True,
        ),
    ],
    ids=["get-auth", "get-exhausted", "get-retry-paused"],
)
def test_new_service_instance_never_reposts_after_post_generation_failure(
    test_settings: Settings,
    failure: TutoryGenerationUncertain,
    expect_cooldown: bool,
) -> None:
    students = [TutoryStudent(id="s1", name="Ana", raw_phone="11999991111")]
    _, first_client = build_service(test_settings, students)
    first_client.generate_report_bundle.side_effect = failure
    current = [datetime(2026, 9, 8, 12, 0, tzinfo=UTC)]
    first_service = RunService(test_settings, first_client, clock=lambda: current[0])
    run = first_service.create(date(2026, 8, 1), date(2026, 8, 31), "abc123", "v1")

    stopped = first_service.extract(run.id)

    assert stopped.blocked == 1
    next_client = Mock()
    next_service = RunService(test_settings, next_client, clock=lambda: current[0])
    if expect_cooldown:
        with pytest.raises(KairosReportError, match="paused until"):
            next_service.extract(run.id)
        current[0] += timedelta(seconds=13)

    resumed = next_service.extract(run.id)

    assert resumed.blocked == 1
    assert resumed.pending == 0
    next_client.generate_report_bundle.assert_not_called()


def test_resume_blocks_unfinished_generation_marker_without_another_post(
    test_settings: Settings,
) -> None:
    service, client = build_service(
        test_settings,
        [TutoryStudent(id="s1", name="Ana", raw_phone="11999991111")],
    )
    client.generate_report_bundle.side_effect = TutoryTemporaryError("temporary")
    run = service.create(date(2026, 8, 1), date(2026, 8, 31), "abc123", "v1")
    service.extract(run.id, ["s1"])
    engine = create_engine_for(test_settings)
    with Session(engine) as session:
        report = session.scalar(select(StudentReport).where(StudentReport.run_id == run.id))
        assert report is not None
        session.add(
            AuditEvent(
                run_id=run.id,
                event_type="report.generation_started",
                actor="system",
                details={"student_report_id": report.id},
            )
        )
        session.commit()
    client.generate_report_bundle.reset_mock()
    client.generate_report_bundle.side_effect = None

    summary = service.extract(run.id)

    assert summary.blocked == 1
    assert summary.pending == 0
    client.generate_report_bundle.assert_not_called()
    engine.dispose()


def test_auth_failure_stops_cycle_and_leaves_pending_for_resume(test_settings: Settings) -> None:
    service, client = build_service(
        test_settings,
        [
            TutoryStudent(id="s1", name="Ana", raw_phone="11999991111"),
            TutoryStudent(id="s2", name="Bia", raw_phone="11999992222"),
        ],
    )
    client.generate_report_bundle.side_effect = TutoryAuthenticationError("rejected")
    run = service.create(date(2026, 8, 1), date(2026, 8, 31), "abc123", "v1")

    summary = service.extract(run.id)

    assert summary.auth_stopped is True
    assert summary.pending == 2
    assert client.generate_report_bundle.call_count == 1

    client.generate_report_bundle.side_effect = None
    resumed = service.extract(run.id)
    assert resumed.valid == 2
    assert resumed.pending == 0


def test_consecutive_upstream_failures_open_circuit_and_resume_pending(
    test_settings: Settings,
) -> None:
    students = [
        TutoryStudent(id=f"s{index}", name=f"Student {index}", raw_phone="11999991111")
        for index in range(4)
    ]
    service, client = build_service(test_settings, students)
    client.generate_report_bundle.side_effect = TutoryTemporaryError("temporary")
    run = service.create(date(2026, 8, 1), date(2026, 8, 31), "abc123", "v1")

    stopped = service.extract(run.id)

    assert stopped.circuit_stopped is True
    assert stopped.upstream_failures == 3
    assert stopped.pending == 4
    assert client.generate_report_bundle.call_count == 3

    client.generate_report_bundle.side_effect = None
    resumed = service.extract(run.id)
    assert resumed.valid == 4
    assert resumed.pending == 0


def test_retry_pause_stops_cycle_and_blocks_early_resume(test_settings: Settings) -> None:
    students = [
        TutoryStudent(id="s1", name="Ana", raw_phone="11999991111"),
        TutoryStudent(id="s2", name="Bia", raw_phone="11999992222"),
    ]
    _, client = build_service(test_settings, students)
    pause = TutoryRetryPaused("wait", retry_after_seconds=120)
    client.generate_report_bundle.side_effect = pause
    current = [datetime(2026, 9, 8, 12, 0, tzinfo=UTC)]
    service = RunService(test_settings, client, clock=lambda: current[0])
    run = service.create(date(2026, 8, 1), date(2026, 8, 31), "abc123", "v1")

    stopped = service.extract(run.id)

    assert stopped.retry_paused is True
    assert stopped.resume_not_before == "2026-09-08T12:02:00+00:00"
    assert stopped.pending == 2
    assert client.generate_report_bundle.call_count == 1

    with pytest.raises(KairosReportError, match="paused until"):
        service.extract(run.id)
    assert client.generate_report_bundle.call_count == 1

    current[0] += timedelta(seconds=121)
    client.generate_report_bundle.side_effect = None
    resumed = service.extract(run.id)
    assert resumed.valid == 2


def test_retry_pause_during_enumeration_is_persisted_before_membership_freeze(
    test_settings: Settings,
) -> None:
    _, client = build_service(test_settings, [])
    client.list_active_students.side_effect = TutoryRetryPaused(
        "wait", retry_after_seconds=120
    )
    current = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
    service = RunService(test_settings, client, clock=lambda: current)
    run = service.create(date(2026, 8, 1), date(2026, 8, 31), "abc123", "v1")

    stopped = service.extract(run.id)

    assert stopped.retry_paused is True
    assert stopped.resume_not_before == "2026-09-08T12:02:00+00:00"
    engine = create_engine_for(test_settings)
    with Session(engine) as session:
        stored = session.get(ReportRun, run.id)
        assert stored is not None
        assert stored.status == RunStatus.EXTRACTING
        frozen = session.scalar(
            select(AuditEvent).where(
                AuditEvent.run_id == run.id,
                AuditEvent.event_type == "run.selection_frozen",
            )
        )
        assert frozen is None
    engine.dispose()


def test_batch_pause_is_applied_between_configured_groups(test_settings: Settings) -> None:
    settings = test_settings.model_copy(update={"batch_size": 2, "batch_pause_seconds": 12})
    students = [
        TutoryStudent(id=f"s{index}", name=f"Student {index}", raw_phone="11999991111")
        for index in range(3)
    ]
    client = Mock()
    client.list_active_students.side_effect = lambda **kwargs: list(students)
    client.generate_report_bundle.return_value = ReportBundle(
        key="report-key",
        documents={
            "desempenho": FIXTURE.read_text(encoding="utf-8"),
            "questoes": FIXTURE.with_name("question_report_page.html").read_text(encoding="utf-8"),
            "aluno": FIXTURE.with_name("student_report_page.html").read_text(encoding="utf-8"),
        },
    )
    engine = create_engine_for(settings)
    Base.metadata.create_all(engine)
    sleeps: list[float] = []
    service = RunService(settings, client, sleep=sleeps.append)
    run = service.create(date(2026, 8, 1), date(2026, 8, 31), "abc123", "v1")

    summary = service.extract(run.id)

    assert summary.valid == 3
    assert summary.batch_pauses == 1
    assert sleeps == [12]


def test_competing_extract_fails_before_network_and_lock_releases(
    test_settings: Settings,
) -> None:
    entered = Event()
    release = Event()

    class BlockingClient:
        def list_active_students(self, **kwargs: object) -> list[TutoryStudent]:
            del kwargs
            entered.set()
            release.wait(timeout=5)
            return []

        def generate_report_bundle(self, *args: object, **kwargs: object) -> ReportBundle:
            raise AssertionError("empty run must not generate")

    first = RunService(test_settings, BlockingClient())
    second_client = Mock()
    second_client.list_active_students.return_value = []
    second = RunService(test_settings, second_client)
    engine = create_engine_for(test_settings)
    Base.metadata.create_all(engine)
    run = first.create(date(2026, 8, 1), date(2026, 8, 31), "abc123", "v1")
    failures: list[BaseException] = []

    thread = Thread(target=lambda: _capture_failure(lambda: first.extract(run.id), failures))
    thread.start()
    assert entered.wait(timeout=5)
    try:
        with pytest.raises(KairosReportError, match="already in progress"):
            second.extract(run.id)
        second_client.list_active_students.assert_not_called()
    finally:
        release.set()
        thread.join(timeout=5)

    assert not failures
    resumed = second.extract(run.id)
    assert resumed.expected == 0
    engine.dispose()


def _capture_failure(action: Callable[[], object], failures: list[BaseException]) -> None:
    try:
        action()
    except BaseException as exc:
        failures.append(exc)
