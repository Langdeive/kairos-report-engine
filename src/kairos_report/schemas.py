from __future__ import annotations

from pydantic import BaseModel, Field


class RunSummary(BaseModel):
    run_id: int
    expected: int = Field(ge=0)
    extracted: int = Field(ge=0)
    valid: int = Field(ge=0)
    blocked: int = Field(ge=0)
    approved: int = Field(ge=0)
    sent: int = Field(ge=0)
    failed: int = Field(ge=0)


class DeliveryItem(BaseModel):
    delivery_id: int
    report_id: int
    student_name: str
    masked_phone: str
    pdf_path: str


class RankedSubject(BaseModel):
    rank: int
    name: str
    accuracy_percent: float
    study_hours: float


class WeeklyMetric(BaseModel):
    label: str
    hours: float
    target_hours: float
    peer_average_hours: float | None = None


class StudentMetrics(BaseModel):
    student_name: str
    course: str
    total_hours: float
    accuracy_percent: float
    plan_progress_percent: float
    study_days: int
    average_study_hours: float
    most_studied_subject: str
    least_studied_subject: str
    ranking: list[RankedSubject]
    weekly: list[WeeklyMetric]
    modality_hours: dict[str, float]
    subject_progress: dict[str, float]
    performance_by_area: dict[str, float]
