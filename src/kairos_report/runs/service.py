from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from kairos_report.config import Settings
from kairos_report.crypto import PhoneCipher
from kairos_report.db import session_factory_for
from kairos_report.errors import InvalidPhone, TutoryContractChanged, TutoryTemporaryError
from kairos_report.models import (
    AuditEvent,
    ReportRun,
    ReportStatus,
    RunStatus,
    Student,
    StudentReport,
)
from kairos_report.schemas import RunSummary
from kairos_report.tutory.client import ReportDocument, TutoryStudent
from kairos_report.tutory.parser import parse_report
from kairos_report.tutory.phone import normalize_brazil_phone


class TutoryGateway(Protocol):
    def list_active_students(self, *, include_phones: bool = False) -> list[TutoryStudent]: ...

    def generate_report(
        self, student_id: str, period_start: date, period_end: date
    ) -> ReportDocument: ...


class RunService:
    def __init__(
        self,
        settings: Settings,
        tutory_client: TutoryGateway,
        *,
        session_factory: sessionmaker[Session] | None = None,
    ) -> None:
        self._tutory = tutory_client
        self._sessions = session_factory or session_factory_for(settings)
        self._phone_cipher = PhoneCipher(settings.data_key)

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
        requested_ids = set(student_ids) if student_ids is not None else None
        active_students = self._tutory.list_active_students(include_phones=True)
        selected = (
            active_students
            if requested_ids is None
            else [student for student in active_students if student.id in requested_ids]
        )
        self._prepare_reports(run_id, selected)

        with self._sessions() as session:
            report_ids = list(
                session.scalars(
                    select(StudentReport.id).where(
                        StudentReport.run_id == run_id,
                        StudentReport.status == ReportStatus.PENDING,
                    )
                )
            )

        for report_id in report_ids:
            self._extract_one(report_id)
        return self._finish_extract(run_id)

    def status(self, run_id: int) -> RunSummary:
        with self._sessions() as session:
            run = session.get(ReportRun, run_id)
            if run is None:
                raise ValueError(f"Report run {run_id} does not exist")
            return self._summary(session, run)

    def _prepare_reports(self, run_id: int, students: list[TutoryStudent]) -> None:
        with self._sessions.begin() as session:
            run = session.get(ReportRun, run_id)
            if run is None:
                raise ValueError(f"Report run {run_id} does not exist")
            run.status = RunStatus.EXTRACTING
            run.expected_count = len(students)
            session.add(
                AuditEvent(
                    run_id=run.id,
                    event_type="run.extracting",
                    actor="system",
                    details={"expected_count": len(students)},
                )
            )

            for external in students:
                student = session.scalar(
                    select(Student).where(Student.tutory_id == external.id)
                )
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
                    revision=1,
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

    def _extract_one(self, report_id: int) -> None:
        with self._sessions() as session:
            report = session.get(StudentReport, report_id)
            if report is None or report.status != ReportStatus.PENDING:
                return
            run = report.run
            tutory_id = report.student.tutory_id
            period_start = report.period_start
            period_end = report.period_end
            run_id = run.id

        try:
            document = self._tutory.generate_report(tutory_id, period_start, period_end)
            metrics = parse_report(document.html)
        except TutoryTemporaryError:
            with self._sessions.begin() as session:
                self._audit_report(session, run_id, report_id, "report.retryable")
            return
        except TutoryContractChanged:
            with self._sessions.begin() as session:
                stored = session.get(StudentReport, report_id)
                if stored is not None:
                    stored.status = ReportStatus.BLOCKED
                    stored.validation_errors = list(
                        dict.fromkeys(
                            [*stored.validation_errors, "tutory_contract_changed"]
                        )
                    )
                    self._audit_report(session, run_id, report_id, "report.blocked")
            return

        with self._sessions.begin() as session:
            stored = session.get(StudentReport, report_id)
            if stored is None or stored.status != ReportStatus.PENDING:
                return
            stored.metrics = metrics.model_dump(mode="json")
            stored.status = ReportStatus.VALID
            self._audit_report(session, run_id, report_id, "report.valid")

    def _finish_extract(self, run_id: int) -> RunSummary:
        with self._sessions.begin() as session:
            run = session.get(ReportRun, run_id)
            if run is None:
                raise ValueError(f"Report run {run_id} does not exist")
            summary = self._summary(session, run)
            run.extracted_count = summary.valid
            run.valid_count = summary.valid
            run.blocked_count = summary.blocked
            if summary.valid:
                run.status = RunStatus.AWAITING_COMMENTS
                event_type = "run.awaiting_comments"
            elif summary.blocked == summary.expected:
                run.status = RunStatus.COMPLETED_WITH_FAILURES
                event_type = "run.completed_with_failures"
            else:
                run.status = RunStatus.EXTRACTING
                event_type = "run.extracting_incomplete"
            session.add(
                AuditEvent(run_id=run.id, event_type=event_type, actor="system", details={})
            )
            return summary

    @staticmethod
    def _audit_report(
        session: Session, run_id: int, report_id: int, event_type: str
    ) -> None:
        session.add(
            AuditEvent(
                run_id=run_id,
                event_type=event_type,
                actor="system",
                details={"student_report_id": report_id},
            )
        )

    @staticmethod
    def _summary(session: Session, run: ReportRun) -> RunSummary:
        def count(status: ReportStatus) -> int:
            value = session.scalar(
                select(func.count())
                .select_from(StudentReport)
                .where(StudentReport.run_id == run.id, StudentReport.status == status)
            )
            return int(value or 0)

        valid = count(ReportStatus.VALID)
        blocked = count(ReportStatus.BLOCKED)
        approved = count(ReportStatus.APPROVED)
        sent = count(ReportStatus.SENT)
        return RunSummary(
            run_id=run.id,
            expected=run.expected_count,
            extracted=valid,
            valid=valid,
            blocked=blocked,
            approved=approved,
            sent=sent,
            failed=run.failed_count,
        )
