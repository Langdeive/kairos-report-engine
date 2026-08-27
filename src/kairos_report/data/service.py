from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select

from kairos_report.config import Settings
from kairos_report.db import session_factory_for
from kairos_report.models import ReportRun, ReportStatus, StudentReport
from kairos_report.report_data import (
    ReportDataEnvelope,
    ReportIssues,
    build_report_data,
)
from kairos_report.schemas import StudentMetrics


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
            self._settings.data_dir / "review" / period_key / "report-data.jsonl"
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
            delivery_blocked=sum(
                envelope.delivery_status == "blocked" for envelope in envelopes
            ),
        )

    @staticmethod
    def _envelope(report: StudentReport) -> ReportDataEnvelope:
        delivery_issues = [
            issue for issue in report.validation_errors if issue == "invalid_phone"
        ]
        if report.student.phone_ciphertext is None and not delivery_issues:
            delivery_issues = ["missing_phone"]

        data_issues = [
            issue for issue in report.validation_errors if issue != "invalid_phone"
        ]
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
            delivery_status=(
                "ready" if report.student.phone_ciphertext is not None else "blocked"
            ),
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
