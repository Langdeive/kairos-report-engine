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


class DeliveryItem(BaseModel):
    delivery_id: int
    report_id: int
    student_name: str
    masked_phone: str
    pdf_path: str


class RankedSubject(BaseModel):
    rank: int = Field(ge=1)
    name: str = Field(min_length=1)
    accuracy_percent: Percentage
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
