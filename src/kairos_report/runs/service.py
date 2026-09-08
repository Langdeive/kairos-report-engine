from __future__ import annotations

import hashlib
import importlib
import os
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import BinaryIO, Literal, Protocol

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from kairos_report.config import Settings
from kairos_report.crypto import PhoneCipher
from kairos_report.db import session_factory_for
from kairos_report.errors import (
    ExtractionCooldownError,
    ExtractionInProgressError,
    InvalidPhone,
    TutoryAuthenticationError,
    TutoryContractChanged,
    TutoryGenerationUncertain,
    TutoryRetryPaused,
    TutoryTemporaryError,
)
from kairos_report.models import (
    AuditEvent,
    ReportRun,
    ReportStatus,
    RunStatus,
    Student,
    StudentReport,
)
from kairos_report.schemas import RunSummary
from kairos_report.tutory.client import ReportBundle, TutoryStudent
from kairos_report.tutory.parser import (
    parse_question_report,
    parse_report,
    parse_student_activity_report,
)
from kairos_report.tutory.phone import normalize_brazil_phone


class TutoryGateway(Protocol):
    def list_active_students(
        self,
        *,
        student_ids: Sequence[str] | None = None,
        include_phones: bool = False,
    ) -> list[TutoryStudent]: ...

    def generate_report_bundle(
        self, student_id: str, period_start: date, period_end: date,
        *, grouping: Literal["mes", "semana", "dia"] = "semana",
    ) -> ReportBundle: ...


@dataclass(frozen=True)
class _ExtractionResult:
    outcome: Literal[
        "valid",
        "blocked",
        "upstream_failure",
        "ambiguous_failure",
        "ambiguous_auth",
        "ambiguous_paused",
        "auth_failure",
        "contract_failure",
        "skipped",
    ]
    retry_after_seconds: float | None = None


class RunService:
    def __init__(
        self,
        settings: Settings,
        tutory_client: TutoryGateway,
        *,
        session_factory: sessionmaker[Session] | None = None,
        sleep: Callable[[float], object] = time.sleep,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._tutory = tutory_client
        self._sessions = session_factory or session_factory_for(settings)
        self._phone_cipher = PhoneCipher(settings.data_key)
        self._sleep = sleep
        self._clock = clock or (lambda: datetime.now(UTC))
        self._batch_size = settings.batch_size
        self._batch_pause = settings.batch_pause_seconds
        self._max_upstream_failures = settings.max_consecutive_upstream_failures
        account_scope = hashlib.sha256(settings.tutory_account.encode("utf-8")).hexdigest()[:16]
        self._lock_path = settings.data_dir / "locks" / f"extract-{account_scope}.lock"

    def create(
        self,
        period_start: date,
        period_end: date,
        code_version: str,
        template_version: str,
    ) -> ReportRun:
        if period_end < period_start:
            raise ValueError("period_end must not precede period_start")
        with self._sessions.begin() as session:
            run = ReportRun(
                period_start=period_start,
                period_end=period_end,
                status=RunStatus.CREATED,
                code_version=code_version,
                template_version=template_version,
            )
            session.add(run)
            session.flush()
            session.add(
                AuditEvent(run_id=run.id, event_type="run.created", actor="system", details={})
            )
        return run

    def extract(self, run_id: int, student_ids: Sequence[str] | None = None) -> RunSummary:
        requested_ids = self._normalize_requested_ids(student_ids)
        self._ensure_run_exists(run_id)
        with self._extraction_lock():
            self._enforce_retry_pause(run_id)
            frozen_ids = self._frozen_or_legacy_ids(run_id)
            if frozen_ids is not None:
                if requested_ids is not None and set(requested_ids) != set(frozen_ids):
                    raise ValueError("This run selection is already frozen and cannot be changed")
            else:
                try:
                    selected = self._tutory.list_active_students(
                        student_ids=requested_ids,
                        include_phones=True,
                    )
                except TutoryRetryPaused as exc:
                    selection_resume_not_before = self._record_retry_pause(
                        run_id, exc.retry_after_seconds
                    )
                    return self._finish_extract(
                        run_id,
                        upstream_failures=1,
                        retry_paused=True,
                        resume_not_before=selection_resume_not_before,
                    )
                self._prepare_reports(
                    run_id,
                    selected,
                    selection_mode="all" if requested_ids is None else "selected",
                )

            self._recover_uncertain_attempts(run_id)
            with self._sessions() as session:
                report_ids = list(
                    session.scalars(
                        select(StudentReport.id)
                        .where(
                            StudentReport.run_id == run_id,
                            StudentReport.status == ReportStatus.PENDING,
                        )
                        .order_by(StudentReport.id)
                    )
                )

            processed = 0
            upstream_failures = 0
            consecutive_upstream_failures = 0
            auth_stopped = False
            circuit_stopped = False
            retry_paused = False
            resume_not_before: str | None = None
            batch_pauses = 0
            for index, report_id in enumerate(report_ids):
                try:
                    result = self._extract_one(report_id)
                except TutoryRetryPaused as exc:
                    processed += 1
                    upstream_failures += 1
                    retry_paused = True
                    resume_not_before = self._record_retry_pause(
                        run_id, exc.retry_after_seconds, report_id=report_id
                    )
                    break
                processed += 1
                outcome = result.outcome
                if outcome == "auth_failure":
                    auth_stopped = True
                    break
                if outcome == "ambiguous_auth":
                    upstream_failures += 1
                    auth_stopped = True
                    break
                if outcome == "ambiguous_paused":
                    upstream_failures += 1
                    retry_paused = True
                    if result.retry_after_seconds is None:
                        raise AssertionError("ambiguous pause is missing its retry delay")
                    resume_not_before = self._record_retry_pause(
                        run_id, result.retry_after_seconds
                    )
                    break
                if outcome in {
                    "upstream_failure",
                    "ambiguous_failure",
                    "contract_failure",
                }:
                    upstream_failures += 1
                    consecutive_upstream_failures += 1
                    if consecutive_upstream_failures >= self._max_upstream_failures:
                        circuit_stopped = True
                        break
                else:
                    consecutive_upstream_failures = 0

                has_more = index + 1 < len(report_ids)
                if has_more and processed % self._batch_size == 0 and self._batch_pause > 0:
                    self._sleep(self._batch_pause)
                    batch_pauses += 1

            return self._finish_extract(
                run_id,
                processed=processed,
                upstream_failures=upstream_failures,
                auth_stopped=auth_stopped,
                circuit_stopped=circuit_stopped,
                retry_paused=retry_paused,
                resume_not_before=resume_not_before,
                batch_pauses=batch_pauses,
            )

    def _ensure_run_exists(self, run_id: int) -> None:
        with self._sessions() as session:
            if session.get(ReportRun, run_id) is None:
                raise ValueError(f"Report run {run_id} does not exist")

    def _enforce_retry_pause(self, run_id: int) -> None:
        with self._sessions() as session:
            pause = session.scalar(
                select(AuditEvent)
                .where(
                    AuditEvent.run_id == run_id,
                    AuditEvent.event_type == "run.retry_paused",
                )
                .order_by(AuditEvent.id.desc())
            )
            if pause is None:
                return
            raw_resume_at = pause.details.get("resume_not_before")
            if not isinstance(raw_resume_at, str):
                raise ValueError("The persisted extraction cooldown is invalid")
            try:
                resume_at = datetime.fromisoformat(raw_resume_at)
            except ValueError as exc:
                raise ValueError("The persisted extraction cooldown is invalid") from exc
            if resume_at.tzinfo is None:
                raise ValueError("The persisted extraction cooldown is invalid")
            if self._clock() < resume_at:
                raise ExtractionCooldownError(f"Extraction is paused until {raw_resume_at}")

    def _record_retry_pause(
        self,
        run_id: int,
        retry_after_seconds: float,
        *,
        report_id: int | None = None,
    ) -> str:
        resume_at = self._clock() + timedelta(seconds=retry_after_seconds)
        resume_not_before = resume_at.isoformat()
        with self._sessions.begin() as session:
            if report_id is not None:
                self._audit_report(session, run_id, report_id, "report.retryable")
            session.add(
                AuditEvent(
                    run_id=run_id,
                    event_type="run.retry_paused",
                    actor="system",
                    details={
                        "resume_not_before": resume_not_before,
                        "retry_after_seconds": retry_after_seconds,
                    },
                )
            )
        return resume_not_before

    @contextmanager
    def _extraction_lock(self) -> Iterator[None]:
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_file = self._lock_path.open("a+b")
        self._ensure_lock_byte(lock_file)
        try:
            self._lock_file(lock_file)
        except OSError as exc:
            lock_file.close()
            raise ExtractionInProgressError(
                "Extraction is already in progress for this account and data directory"
            ) from exc
        try:
            yield
        finally:
            self._unlock_file(lock_file)
            lock_file.close()

    @staticmethod
    def _ensure_lock_byte(lock_file: BinaryIO) -> None:
        lock_file.seek(0, os.SEEK_END)
        if lock_file.tell() == 0:
            lock_file.write(b"\0")
            lock_file.flush()
        lock_file.seek(0)

    @staticmethod
    def _lock_file(lock_file: BinaryIO) -> None:
        if os.name == "nt":
            msvcrt = importlib.import_module("msvcrt")
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            return
        fcntl = importlib.import_module("fcntl")
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    @staticmethod
    def _unlock_file(lock_file: BinaryIO) -> None:
        lock_file.seek(0)
        if os.name == "nt":
            msvcrt = importlib.import_module("msvcrt")
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            return
        fcntl = importlib.import_module("fcntl")
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _normalize_requested_ids(student_ids: Sequence[str] | None) -> tuple[str, ...] | None:
        if student_ids is None:
            return None
        if not student_ids or any(not student_id.strip() for student_id in student_ids):
            raise ValueError("Selected student IDs must not be empty")
        return tuple(dict.fromkeys(student_ids))

    def _frozen_or_legacy_ids(self, run_id: int) -> tuple[str, ...] | None:
        with self._sessions.begin() as session:
            run = session.get(ReportRun, run_id)
            if run is None:
                raise ValueError(f"Report run {run_id} does not exist")
            frozen = session.scalar(
                select(AuditEvent)
                .where(
                    AuditEvent.run_id == run_id,
                    AuditEvent.event_type == "run.selection_frozen",
                )
                .order_by(AuditEvent.id.desc())
            )
            if frozen is not None:
                stored_ids = frozen.details.get("student_ids", [])
                if not isinstance(stored_ids, list) or not all(
                    isinstance(student_id, str) for student_id in stored_ids
                ):
                    raise ValueError("The frozen run selection is invalid")
                return tuple(stored_ids)

            legacy_ids = tuple(
                session.scalars(
                    select(Student.tutory_id)
                    .join(StudentReport, StudentReport.student_id == Student.id)
                    .where(StudentReport.run_id == run_id)
                    .order_by(Student.tutory_id)
                )
            )
            if legacy_ids:
                session.add(
                    AuditEvent(
                        run_id=run_id,
                        event_type="run.selection_frozen",
                        actor="system",
                        details={"student_ids": list(legacy_ids), "selection_mode": "legacy"},
                    )
                )
                return legacy_ids
            return None

    def status(self, run_id: int) -> RunSummary:
        with self._sessions() as session:
            run = session.get(ReportRun, run_id)
            if run is None:
                raise ValueError(f"Report run {run_id} does not exist")
            return self._summary(session, run)

    def _prepare_reports(
        self,
        run_id: int,
        students: list[TutoryStudent],
        *,
        selection_mode: str,
    ) -> None:
        with self._sessions.begin() as session:
            run = session.get(ReportRun, run_id)
            if run is None:
                raise ValueError(f"Report run {run_id} does not exist")
            run.status = RunStatus.EXTRACTING
            session.add(
                AuditEvent(
                    run_id=run.id,
                    event_type="run.selection_frozen",
                    actor="system",
                    details={
                        "student_ids": sorted(student.id for student in students),
                        "selection_mode": selection_mode,
                    },
                )
            )
            session.add(
                AuditEvent(
                    run_id=run.id,
                    event_type="run.extracting",
                    actor="system",
                    details={"expected_count": len(students)},
                )
            )

            for external in students:
                student = session.scalar(select(Student).where(Student.tutory_id == external.id))
                if student is None:
                    student = Student(tutory_id=external.id, name=external.name)
                    session.add(student)
                    session.flush()

                existing = session.scalar(
                    select(StudentReport).where(
                        StudentReport.run_id == run.id,
                        StudentReport.student_id == student.id,
                    )
                )
                if existing is not None:
                    continue

                report = StudentReport(
                    run_id=run.id,
                    student_id=student.id,
                    period_start=run.period_start,
                    period_end=run.period_end,
                    revision=1
                    + int(
                        session.scalar(
                            select(func.max(StudentReport.revision)).where(
                                StudentReport.student_id == student.id,
                                StudentReport.period_start == run.period_start,
                                StudentReport.period_end == run.period_end,
                            )
                        )
                        or 0
                    ),
                    status=ReportStatus.PENDING,
                )
                session.add(report)
                session.flush()
                student.name = external.name
                try:
                    normalized_phone = normalize_brazil_phone(external.raw_phone or "")
                except InvalidPhone:
                    report.validation_errors = ["invalid_phone"]
                    student.phone_ciphertext = None
                    self._audit_report(session, run.id, report.id, "report.delivery_blocked")
                else:
                    student.phone_ciphertext = self._phone_cipher.encrypt(normalized_phone)
                self._audit_report(session, run.id, report.id, "report.pending")
            session.flush()
            run.expected_count = int(
                session.scalar(
                    select(func.count())
                    .select_from(StudentReport)
                    .where(StudentReport.run_id == run.id)
                )
                or 0
            )

    def _extract_one(self, report_id: int) -> _ExtractionResult:
        with self._sessions() as session:
            report = session.get(StudentReport, report_id)
            if report is None or report.status != ReportStatus.PENDING:
                return _ExtractionResult("skipped")
            run = report.run
            tutory_id = report.student.tutory_id
            period_start = report.period_start
            period_end = report.period_end
            run_id = run.id

        with self._sessions.begin() as session:
            self._audit_report(session, run_id, report_id, "report.generation_started")

        try:
            bundle = self._tutory.generate_report_bundle(
                tutory_id, period_start, period_end, grouping="dia"
            )
            metrics = parse_report(bundle.documents["desempenho"],
                                   period_start=period_start, period_end=period_end)
            questions = parse_question_report(bundle.documents["questoes"],
                                             period_start=period_start, period_end=period_end)
            activity = parse_student_activity_report(bundle.documents["aluno"])
        except TutoryRetryPaused:
            raise
        except TutoryGenerationUncertain as exc:
            with self._sessions.begin() as session:
                stored = session.get(StudentReport, report_id)
                if stored is not None and stored.status == ReportStatus.PENDING:
                    stored.status = ReportStatus.BLOCKED
                    stored.validation_errors = list(
                        dict.fromkeys(
                            [*stored.validation_errors, "tutory_generation_uncertain"]
                        )
                    )
                    self._audit_report(
                        session, run_id, report_id, "report.generation_uncertain"
                    )
            if exc.stop_reason == "auth":
                return _ExtractionResult("ambiguous_auth")
            if exc.stop_reason == "retry_paused" and exc.retry_after_seconds is not None:
                return _ExtractionResult("ambiguous_paused", exc.retry_after_seconds)
            return _ExtractionResult("ambiguous_failure")
        except TutoryAuthenticationError:
            with self._sessions.begin() as session:
                self._audit_report(session, run_id, report_id, "report.retryable")
            return _ExtractionResult("auth_failure")
        except TutoryTemporaryError:
            with self._sessions.begin() as session:
                self._audit_report(session, run_id, report_id, "report.retryable")
            return _ExtractionResult("upstream_failure")
        except (TutoryContractChanged, ValidationError, KeyError):
            with self._sessions.begin() as session:
                stored = session.get(StudentReport, report_id)
                if stored is not None:
                    stored.status = ReportStatus.BLOCKED
                    stored.validation_errors = list(
                        dict.fromkeys([*stored.validation_errors, "tutory_contract_changed"])
                    )
                    self._audit_report(session, run_id, report_id, "report.blocked")
            return _ExtractionResult("contract_failure")

        with self._sessions.begin() as session:
            stored = session.get(StudentReport, report_id)
            if stored is None or stored.status != ReportStatus.PENDING:
                return _ExtractionResult("skipped")
            stored.metrics = {
                **metrics.model_dump(mode="json"),
                "questions": questions.model_dump(mode="json"),
                "student_activity": activity.model_dump(mode="json"),
            }
            stored.status = ReportStatus.VALID
            self._audit_report(session, run_id, report_id, "report.valid")
        return _ExtractionResult("valid")

    def _recover_uncertain_attempts(self, run_id: int) -> None:
        terminal_events = {
            "report.retryable",
            "report.valid",
            "report.blocked",
            "report.generation_uncertain",
        }
        relevant_events = {"report.generation_started", *terminal_events}
        with self._sessions.begin() as session:
            pending_reports = {
                report.id: report
                for report in session.scalars(
                    select(StudentReport).where(
                        StudentReport.run_id == run_id,
                        StudentReport.status == ReportStatus.PENDING,
                    )
                )
            }
            unfinished: set[int] = set()
            events = session.scalars(
                select(AuditEvent)
                .where(
                    AuditEvent.run_id == run_id,
                    AuditEvent.event_type.in_(relevant_events),
                )
                .order_by(AuditEvent.id)
            )
            for event in events:
                report_id = event.details.get("student_report_id")
                if not isinstance(report_id, int):
                    continue
                if event.event_type == "report.generation_started":
                    unfinished.add(report_id)
                elif event.event_type in terminal_events:
                    unfinished.discard(report_id)
            for report_id in unfinished & pending_reports.keys():
                report = pending_reports[report_id]
                report.status = ReportStatus.BLOCKED
                report.validation_errors = list(
                    dict.fromkeys([*report.validation_errors, "tutory_generation_uncertain"])
                )
                self._audit_report(
                    session, run_id, report_id, "report.generation_uncertain"
                )

    def _finish_extract(
        self,
        run_id: int,
        *,
        processed: int = 0,
        upstream_failures: int = 0,
        auth_stopped: bool = False,
        circuit_stopped: bool = False,
        retry_paused: bool = False,
        resume_not_before: str | None = None,
        batch_pauses: int = 0,
    ) -> RunSummary:
        with self._sessions.begin() as session:
            run = session.get(ReportRun, run_id)
            if run is None:
                raise ValueError(f"Report run {run_id} does not exist")
            summary = self._summary(
                session,
                run,
                processed=processed,
                upstream_failures=upstream_failures,
                auth_stopped=auth_stopped,
                circuit_stopped=circuit_stopped,
                retry_paused=retry_paused,
                resume_not_before=resume_not_before,
                batch_pauses=batch_pauses,
            )
            run.extracted_count = summary.valid
            run.valid_count = summary.valid
            run.blocked_count = summary.blocked
            if summary.retry_paused:
                run.status = RunStatus.EXTRACTING
                event_type = "run.retry_paused"
            elif summary.pending:
                run.status = RunStatus.EXTRACTING
                event_type = "run.extracting_incomplete"
            elif summary.expected == 0:
                run.status = RunStatus.COMPLETED
                event_type = "run.completed_empty"
            elif summary.valid:
                run.status = RunStatus.RENDERING
                event_type = "run.ready_to_render"
            elif summary.blocked == summary.expected:
                run.status = RunStatus.COMPLETED_WITH_FAILURES
                event_type = "run.completed_with_failures"
            else:
                run.status = RunStatus.RENDERING
                event_type = "run.ready_to_render"
            session.add(
                AuditEvent(
                    run_id=run.id,
                    event_type=event_type,
                    actor="system",
                    details={
                        "processed": summary.processed,
                        "pending": summary.pending,
                        "upstream_failures": summary.upstream_failures,
                        "auth_stopped": summary.auth_stopped,
                        "circuit_stopped": summary.circuit_stopped,
                        "retry_paused": summary.retry_paused,
                        "resume_not_before": summary.resume_not_before,
                        "batch_pauses": summary.batch_pauses,
                        "http_calls": summary.http_calls,
                        "http_retries": summary.http_retries,
                        "http_statuses": summary.http_statuses,
                    },
                )
            )
            return summary

    @staticmethod
    def _audit_report(session: Session, run_id: int, report_id: int, event_type: str) -> None:
        session.add(
            AuditEvent(
                run_id=run_id,
                event_type=event_type,
                actor="system",
                details={"student_report_id": report_id},
            )
        )

    def _summary(
        self,
        session: Session,
        run: ReportRun,
        *,
        processed: int = 0,
        upstream_failures: int = 0,
        auth_stopped: bool = False,
        circuit_stopped: bool = False,
        retry_paused: bool = False,
        resume_not_before: str | None = None,
        batch_pauses: int = 0,
    ) -> RunSummary:
        def count(status: ReportStatus) -> int:
            value = session.scalar(
                select(func.count())
                .select_from(StudentReport)
                .where(StudentReport.run_id == run.id, StudentReport.status == status)
            )
            return int(value or 0)

        valid = count(ReportStatus.VALID)
        blocked = count(ReportStatus.BLOCKED)
        pending = count(ReportStatus.PENDING)
        approved = count(ReportStatus.APPROVED)
        sent = count(ReportStatus.SENT)
        client_stats = getattr(self._tutory, "stats", {})
        if not isinstance(client_stats, dict):
            client_stats = {}
        statuses = client_stats.get("statuses", {})
        if not isinstance(statuses, dict):
            statuses = {}
        return RunSummary(
            run_id=run.id,
            expected=run.expected_count,
            extracted=valid,
            valid=valid,
            blocked=blocked,
            approved=approved,
            sent=sent,
            failed=run.failed_count,
            pending=pending,
            processed=processed,
            upstream_failures=upstream_failures,
            auth_stopped=auth_stopped,
            circuit_stopped=circuit_stopped,
            retry_paused=retry_paused,
            resume_not_before=resume_not_before,
            batch_pauses=batch_pauses,
            http_calls=int(client_stats.get("http_calls", 0)),
            http_retries=int(client_stats.get("http_retries", 0)),
            wait_seconds=float(client_stats.get("wait_seconds", 0)),
            elapsed_seconds=float(client_stats.get("elapsed_seconds", 0)),
            http_statuses={str(key): int(value) for key, value in statuses.items()},
        )
