from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field

NonNegativeNumber = Annotated[float, Field(ge=0)]
Percentage = Annotated[float, Field(ge=0, le=100)]


class RunSummary(BaseModel):
    run_id: int
    expected: int = Field(ge=0)
    extracted: int = Field(ge=0)
    valid: int = Field(ge=0)
    blocked: int = Field(ge=0)
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


class QuestionTopicMetric(BaseModel):
    discipline: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    accuracy_percent: Percentage


class QuestionMetrics(BaseModel):
    total: int = Field(ge=0)
    correct: int = Field(ge=0)
    wrong: int = Field(ge=0)
    accuracy_percent: Percentage
    weekly: list[QuestionWeekMetric]
    disciplines: list[QuestionDisciplineMetric]
    topics: list[QuestionTopicMetric]


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
