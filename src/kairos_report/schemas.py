from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

NonNegativeNumber = Annotated[float, Field(ge=0)]
Percentage = Annotated[float, Field(ge=0, le=100)]


class RunSummary(BaseModel):
    run_id: int
    expected: int = Field(ge=0)
    extracted: int = Field(ge=0)
    valid: int = Field(ge=0)
    blocked: int = Field(ge=0)
    excluded: int = Field(default=0, ge=0)
    approved: int = Field(ge=0)
    sent: int = Field(ge=0)
    failed: int = Field(ge=0)
    pending: int = Field(default=0, ge=0)
    processed: int = Field(default=0, ge=0)
    upstream_failures: int = Field(default=0, ge=0)
    auth_stopped: bool = False
    circuit_stopped: bool = False
    retry_paused: bool = False
    resume_not_before: str | None = None
    batch_pauses: int = Field(default=0, ge=0)
    http_calls: int = Field(default=0, ge=0)
    http_retries: int = Field(default=0, ge=0)
    wait_seconds: float = Field(default=0, ge=0)
    elapsed_seconds: float = Field(default=0, ge=0)
    http_statuses: dict[str, int] = Field(default_factory=dict)


class DeliveryItem(BaseModel):
    delivery_id: int
    report_id: int
    student_name: str
    masked_phone: str
    pdf_path: str


class RankedSubject(BaseModel):
    rank: int = Field(ge=1)
    name: str = Field(min_length=1)
    accuracy_percent: Percentage | None = None
    study_hours: NonNegativeNumber


class WeeklyMetric(BaseModel):
    label: str = Field(min_length=1)
    hours: NonNegativeNumber
    target_hours: NonNegativeNumber
    peer_average_hours: NonNegativeNumber | None = None


class MonthlySource(BaseModel):
    basis: Literal["verified_daily_v1"] = "verified_daily_v1"
    period_start: date
    period_end: date


class PerformanceMonthlySource(MonthlySource):
    daily: list[WeeklyMetric]


class StudentMetrics(BaseModel):
    student_name: str = Field(min_length=1)
    course: str = Field(min_length=1)
    total_hours: NonNegativeNumber
    accuracy_percent: Percentage
    plan_progress_percent: Percentage
    study_days: int = Field(ge=0)
    average_study_hours: NonNegativeNumber
    most_studied_subject: str = Field(min_length=1)
    least_studied_subject: str = Field(min_length=1)
    ranking: list[RankedSubject]
    weekly: list[WeeklyMetric]
    modality_hours: dict[str, NonNegativeNumber]
    subject_progress: dict[str, Percentage]
    performance_by_area: dict[str, Percentage]
    monthly_source: PerformanceMonthlySource | None = None


class QuestionWeekMetric(BaseModel):
    label: str = Field(min_length=1)
    correct: int = Field(ge=0)
    wrong: int = Field(ge=0)
    total: int = Field(ge=0)
    accuracy_percent: Percentage


class QuestionDisciplineMetric(BaseModel):
    name: str = Field(min_length=1)
    total: int = Field(ge=0)
    correct: int = Field(ge=0)
    wrong: int = Field(ge=0)
    accuracy_percent: Percentage


class TopicSourcePeriod(BaseModel):
    """Period binding for records; does not attest actual execution."""

    period_start: date
    period_end: date


class QuestionTopicMetric(BaseModel):
    discipline: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    accuracy_percent: Percentage
    total: int | None = Field(default=None, ge=0, strict=True)
    correct: int | None = Field(default=None, ge=0, strict=True)
    wrong: int | None = Field(default=None, ge=0, strict=True)
    execution_status: Literal["recorded", "confirmed", "placeholder", "unknown"] = "recorded"
    source_period: TopicSourcePeriod | None = None

    @model_validator(mode="after")
    def consistent_counts(self) -> QuestionTopicMetric:
        counts = (self.total, self.correct, self.wrong)
        if any(value is not None for value in counts):
            if self.total is None or self.correct is None or self.wrong is None:
                raise ValueError("topic_counts_incomplete")
            if self.correct + self.wrong != self.total:
                raise ValueError("topic_counts_inconsistent")
            expected = round(100 * self.correct / self.total, 2) if self.total else 0
            if abs(self.accuracy_percent - expected) > 0.01:
                raise ValueError("topic_accuracy_inconsistent")
        if self.source_period and self.source_period.period_start > self.source_period.period_end:
            raise ValueError("topic_period_inverted")
        return self


class QuestionMonthlySource(MonthlySource):
    daily: list[QuestionWeekMetric]


class QuestionMetrics(BaseModel):
    total: int = Field(ge=0)
    correct: int = Field(ge=0)
    wrong: int = Field(ge=0)
    accuracy_percent: Percentage
    weekly: list[QuestionWeekMetric]
    disciplines: list[QuestionDisciplineMetric]
    topics: list[QuestionTopicMetric]
    monthly_source: QuestionMonthlySource | None = None


class RevisionMetric(BaseModel):
    discipline: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    count: int = Field(ge=0)


class StudyActivityMetric(BaseModel):
    discipline: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    modality: str = Field(min_length=1)
    hours: NonNegativeNumber


class StudentActivityMetrics(BaseModel):
    revisions: list[RevisionMetric]
    activities: list[StudyActivityMetric]
    total_revisions: int = Field(ge=0)
