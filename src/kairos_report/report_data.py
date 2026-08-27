from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from kairos_report.schemas import RankedSubject, StudentMetrics


class ReportIdentity(BaseModel):
    report_id: int = Field(gt=0)
    student_name: str = Field(min_length=1)
    course: str = Field(min_length=1)
    period_start: date
    period_end: date


class MonthlySummary(BaseModel):
    total_hours: float = Field(ge=0)
    study_days: int = Field(ge=0)
    inactive_days: int = Field(ge=0)
    average_hours_per_active_day: float = Field(ge=0)
    accuracy_percent: float = Field(ge=0, le=100)
    plan_progress_percent: float = Field(ge=0, le=100)
    remaining_progress_percent: float = Field(ge=0, le=100)


class ReportWeek(BaseModel):
    label: str = Field(min_length=1)
    hours: float = Field(ge=0)
    target_hours: float = Field(ge=0)


class WeeklyEvolution(BaseModel):
    weeks: list[ReportWeek]
    total_target_hours: float = Field(ge=0)
    adherence_percent: float | None = Field(default=None, ge=0)
    first_to_last_hours_delta: float | None = None
    trend: Literal["improving", "stable", "declining", "unavailable"]


class DisciplineOverview(BaseModel):
    most_studied: str = Field(min_length=1)
    least_studied: str = Field(min_length=1)
    ranking: list[RankedSubject]
    progress_percent: dict[str, float]


class ModalityOverview(BaseModel):
    hours: dict[str, float]
    total_hours: float = Field(ge=0)
    shares_percent: dict[str, float]


class ReportDataPackage(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    identity: ReportIdentity
    summary: MonthlySummary
    weekly_evolution: WeeklyEvolution
    disciplines: DisciplineOverview
    modalities: ModalityOverview
    performance_by_area: dict[str, float]
    unavailable_metrics: list[str]


class ReportIssues(BaseModel):
    data: list[str]
    delivery: list[str]


class ReportDataEnvelope(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    report_id: int = Field(gt=0)
    data_status: Literal["ready", "blocked", "pending"]
    delivery_status: Literal["ready", "blocked"]
    issues: ReportIssues
    data: ReportDataPackage | None


def build_report_data(
    *,
    report_id: int,
    period_start: date,
    period_end: date,
    metrics: StudentMetrics,
    student_name: str | None = None,
) -> ReportDataPackage:
    period_days = (period_end - period_start).days + 1
    if period_days <= 0:
        raise ValueError("period_end must not precede period_start")
    if metrics.study_days > period_days:
        raise ValueError("study_days cannot exceed the report period")

    weeks = [
        ReportWeek(label=week.label, hours=week.hours, target_hours=week.target_hours)
        for week in metrics.weekly
    ]
    total_weekly_hours = sum(week.hours for week in weeks)
    total_target_hours = sum(week.target_hours for week in weeks)
    adherence = (
        round(total_weekly_hours / total_target_hours * 100, 2)
        if total_target_hours > 0
        else None
    )

    delta: float | None = None
    trend: Literal["improving", "stable", "declining", "unavailable"] = "unavailable"
    if len(weeks) >= 2:
        delta = round(weeks[-1].hours - weeks[0].hours, 2)
        if delta > 0:
            trend = "improving"
        elif delta < 0:
            trend = "declining"
        else:
            trend = "stable"

    modality_total = round(sum(metrics.modality_hours.values()), 2)
    modality_shares = (
        {
            name: round(hours / modality_total * 100, 2)
            for name, hours in metrics.modality_hours.items()
        }
        if modality_total > 0
        else {}
    )

    return ReportDataPackage(
        identity=ReportIdentity(
            report_id=report_id,
            student_name=student_name or metrics.student_name,
            course=metrics.course,
            period_start=period_start,
            period_end=period_end,
        ),
        summary=MonthlySummary(
            total_hours=metrics.total_hours,
            study_days=metrics.study_days,
            inactive_days=period_days - metrics.study_days,
            average_hours_per_active_day=metrics.average_study_hours,
            accuracy_percent=metrics.accuracy_percent,
            plan_progress_percent=metrics.plan_progress_percent,
            remaining_progress_percent=round(100 - metrics.plan_progress_percent, 2),
        ),
        weekly_evolution=WeeklyEvolution(
            weeks=weeks,
            total_target_hours=round(total_target_hours, 2),
            adherence_percent=adherence,
            first_to_last_hours_delta=delta,
            trend=trend,
        ),
        disciplines=DisciplineOverview(
            most_studied=metrics.most_studied_subject,
            least_studied=metrics.least_studied_subject,
            ranking=metrics.ranking,
            progress_percent=metrics.subject_progress,
        ),
        modalities=ModalityOverview(
            hours=metrics.modality_hours,
            total_hours=modality_total,
            shares_percent=modality_shares,
        ),
        performance_by_area=metrics.performance_by_area,
        unavailable_metrics=[
            "active_days_by_week",
            "accuracy_by_week",
            "most_improved_subject",
        ],
    )
