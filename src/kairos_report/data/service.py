from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Literal

from cryptography.fernet import InvalidToken
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select

from kairos_report.config import Settings
from kairos_report.crypto import PhoneCipher
from kairos_report.db import session_factory_for
from kairos_report.errors import InvalidPhone
from kairos_report.models import ReportRun, ReportStatus, StudentReport
from kairos_report.pdf import generate_approved_report
from kairos_report.report_data import (
    ReportDataEnvelope,
    ReportIssues,
    build_report_data,
)
from kairos_report.schemas import QuestionMetrics, StudentActivityMetrics, StudentMetrics
from kairos_report.tutory.phone import normalize_brazil_phone


class DataExportResult(BaseModel):
    run_id: int = Field(gt=0)
    output_path: Path
    expected: int = Field(ge=0)
    exported: int = Field(ge=0)
    complete: bool
    ready: int = Field(ge=0)
    blocked: int = Field(ge=0)
    pending: int = Field(ge=0)
    delivery_blocked: int = Field(ge=0)


class ReportDataService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._sessions = session_factory_for(settings)

    def generate(self, run_id: int, output_dir: Path | None = None) -> dict[str, object]:
        """Generate review PDFs from persisted data, without changing approval state."""
        with self._sessions() as session:
            run = session.get(ReportRun, run_id)
            if run is None:
                raise ValueError(f"Report run {run_id} does not exist")
            expected = run.expected_count
            reports = list(
                session.scalars(
                    select(StudentReport)
                    .where(StudentReport.run_id == run_id)
                    .order_by(StudentReport.id)
                )
            )
            envelopes = [self._envelope(report) for report in reports]
            protected_ids = {
                report.id
                for report in reports
                if report.status in {ReportStatus.APPROVED, ReportStatus.SENT}
            }
            destination = output_dir or (
                self._settings.data_dir
                / "review"
                / run.period_start.strftime("%Y-%m")
                / f"run-{run_id}"
                / "pdf"
            )
        generated: list[str] = []
        skipped: list[int] = []
        for envelope in envelopes:
            if (
                envelope.data_status != "ready"
                or envelope.data is None
                or envelope.report_id in protected_ids
            ):
                skipped.append(envelope.report_id)
                continue
            output = destination / f"relatorio-{envelope.report_id}.pdf"
            generate_approved_report(envelope.data, output)
            digest = hashlib.sha256(output.read_bytes()).hexdigest()
            with self._sessions.begin() as session:
                report = session.get(StudentReport, envelope.report_id)
                if report is not None:
                    report.pdf_path = str(output.resolve())
                    report.pdf_hash = digest
            generated.append(str(output.resolve()))
        return {
            "run_id": run_id,
            "expected": expected,
            "generated": len(generated),
            "complete": len(generated) == expected and not skipped,
            "skipped_report_ids": skipped,
            "pdf_paths": generated,
            "delivery_manifest": self.export_delivery(run_id),
        }

    def export_delivery(self, run_id: int, output_path: Path | None = None) -> dict[str, object]:
        """Local recipient-to-PDF manifest for Hermes; never sends or approves messages."""
        cipher = PhoneCipher(self._settings.data_key)
        items: list[dict[str, object]] = []
        with self._sessions() as session:
            run = session.get(ReportRun, run_id)
            if run is None:
                raise ValueError(f"Report run {run_id} does not exist")
            expected = run.expected_count
            destination = output_path or (
                self._settings.data_dir
                / "review"
                / run.period_start.strftime("%Y-%m")
                / f"run-{run_id}"
                / "delivery-manifest.json"
            )
            for report in session.scalars(
                select(StudentReport)
                .where(StudentReport.run_id == run_id)
                .order_by(StudentReport.id)
            ):
                issues: list[str] = []
                phone: str | None = None
                if report.student.phone_ciphertext is None:
                    issues.append("missing_or_invalid_phone")
                else:
                    try:
                        phone = normalize_brazil_phone(
                            cipher.decrypt(report.student.phone_ciphertext)
                        )
                    except (InvalidToken, InvalidPhone, UnicodeDecodeError):
                        issues.append("invalid_or_unreadable_phone")
                if report.status == ReportStatus.SENT:
                    issues.append("already_sent")
                elif report.status not in {ReportStatus.VALID, ReportStatus.APPROVED}:
                    issues.append("report_not_valid")
                path = Path(report.pdf_path) if report.pdf_path else None
                try:
                    if path is None or not path.is_file():
                        issues.append("missing_pdf")
                    elif hashlib.sha256(path.read_bytes()).hexdigest() != report.pdf_hash:
                        issues.append("pdf_changed")
                except OSError:
                    issues.append("unreadable_pdf")
                items.append(
                    {
                        "report_id": report.id,
                        "student_id": report.student.tutory_id,
                        "student_name": report.student.name,
                        "period_start": report.period_start.isoformat(),
                        "period_end": report.period_end.isoformat(),
                        "revision": report.revision,
                        "phone": phone,
                        "pdf_path": str(path.resolve()) if path else None,
                        "pdf_sha256": report.pdf_hash,
                        "ready_for_hermes": not issues,
                        "issues": issues,
                    }
                )
        ready = sum(item["ready_for_hermes"] is True for item in items)
        payload = {"schema_version": "1.0", "run_id": run_id, "items": items}
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            json.dump(payload, temporary, ensure_ascii=False, indent=2)
            temporary_path = Path(temporary.name)
        temporary_path.replace(destination)
        return {
            "output_path": str(destination.resolve()),
            "expected": expected,
            "exported": len(items),
            "ready": ready,
            "blocked": len(items) - ready,
            "complete": len(items) == expected and ready == expected,
        }

    def export(self, run_id: int, output_path: Path | None = None) -> DataExportResult:
        with self._sessions() as session:
            run = session.get(ReportRun, run_id)
            if run is None:
                raise ValueError(f"Report run {run_id} does not exist")
            reports = list(
                session.scalars(
                    select(StudentReport)
                    .where(StudentReport.run_id == run_id)
                    .order_by(StudentReport.id)
                )
            )
            envelopes = [self._envelope(report) for report in reports]
            period_key = run.period_start.strftime("%Y-%m")
            expected = run.expected_count

        destination = output_path or (
            self._settings.data_dir
            / "review"
            / period_key
            / f"run-{run_id}"
            / "report-data.jsonl"
        )
        self._write_jsonl(destination, envelopes)
        statuses = [envelope.data_status for envelope in envelopes]
        ready = statuses.count("ready")
        blocked = statuses.count("blocked")
        pending = statuses.count("pending")
        return DataExportResult(
            run_id=run_id,
            output_path=destination,
            expected=expected,
            exported=len(envelopes),
            complete=(len(envelopes) == expected and blocked == 0 and pending == 0),
            ready=ready,
            blocked=blocked,
            pending=pending,
            delivery_blocked=sum(envelope.delivery_status == "blocked" for envelope in envelopes),
        )

    @staticmethod
    def _envelope(report: StudentReport) -> ReportDataEnvelope:
        delivery_issues = [issue for issue in report.validation_errors if issue == "invalid_phone"]
        if report.student.phone_ciphertext is None and not delivery_issues:
            delivery_issues = ["missing_phone"]

        data_issues = [issue for issue in report.validation_errors if issue != "invalid_phone"]
        data_status: Literal["ready", "blocked", "pending"]
        data = None
        if report.status in {ReportStatus.VALID, ReportStatus.APPROVED, ReportStatus.SENT}:
            try:
                metrics = StudentMetrics.model_validate(report.metrics)
                data = build_report_data(
                    report_id=report.id,
                    period_start=report.period_start,
                    period_end=report.period_end,
                    metrics=metrics,
                    student_name=report.student.name,
                    questions=(
                        QuestionMetrics.model_validate(report.metrics["questions"])
                        if report.metrics.get("questions") is not None
                        else None
                    ),
                    student_activity=(
                        StudentActivityMetrics.model_validate(report.metrics["student_activity"])
                        if report.metrics.get("student_activity") is not None
                        else None
                    ),
                )
            except (ValidationError, ValueError):
                data_status = "blocked"
                data_issues.append("stored_metrics_invalid")
            else:
                data_status = "ready"
        elif report.status == ReportStatus.BLOCKED:
            data_status = "blocked"
            if not data_issues:
                data_issues.append("report_blocked")
        else:
            data_status = "pending"

        return ReportDataEnvelope(
            report_id=report.id,
            data_status=data_status,
            delivery_status=("ready" if report.student.phone_ciphertext is not None else "blocked"),
            issues=ReportIssues(data=data_issues, delivery=delivery_issues),
            data=data,
        )

    @staticmethod
    def _write_jsonl(path: Path, envelopes: list[ReportDataEnvelope]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        content = "".join(
            json.dumps(
                envelope.model_dump(mode="json"),
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
            for envelope in envelopes
        )
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary_path = Path(temporary.name)
        temporary_path.replace(path)
