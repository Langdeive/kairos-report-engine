from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class RunStatus(StrEnum):
    CREATED = "created"
    EXTRACTING = "extracting"
    AWAITING_COMMENTS = "awaiting_comments"
    VALIDATING = "validating"
    RENDERING = "rendering"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    DELIVERING = "delivering"
    COMPLETED = "completed"
    COMPLETED_WITH_FAILURES = "completed_with_failures"


class ReportStatus(StrEnum):
    PENDING = "pending"
    VALID = "valid"
    BLOCKED = "blocked"
    APPROVED = "approved"
    SENT = "sent"


class DeliveryStatus(StrEnum):
    PENDING = "pending"
    LEASED = "leased"
    SENT = "sent"
    FAILED = "failed"


def _enum_type(enum_class: type[StrEnum], name: str) -> SqlEnum:
    return SqlEnum(
        enum_class,
        name=name,
        native_enum=False,
        create_constraint=True,
        values_callable=lambda members: [member.value for member in members],
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Student(TimestampMixin, Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True)
    tutory_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    phone_ciphertext: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")

    reports: Mapped[list[StudentReport]] = relationship(back_populates="student")


class ReportRun(TimestampMixin, Base):
    __tablename__ = "report_runs"
    __table_args__ = (Index("ix_report_runs_status", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    status: Mapped[RunStatus] = mapped_column(
        _enum_type(RunStatus, "run_status"), default=RunStatus.CREATED
    )
    code_version: Mapped[str] = mapped_column(String(64))
    template_version: Mapped[str] = mapped_column(String(64))
    batch_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    expected_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    extracted_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    valid_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    blocked_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    approved_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    sent_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    failed_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    reports: Mapped[list[StudentReport]] = relationship(back_populates="run")
    approvals: Mapped[list[Approval]] = relationship(back_populates="run")
    audit_events: Mapped[list[AuditEvent]] = relationship(back_populates="run")


class StudentReport(TimestampMixin, Base):
    __tablename__ = "student_reports"
    __table_args__ = (
        UniqueConstraint(
            "student_id",
            "period_start",
            "period_end",
            "revision",
            name="uq_student_report_period_revision",
        ),
        Index("ix_student_reports_run_status", "run_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("report_runs.id", ondelete="CASCADE"))
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="RESTRICT"))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    status: Mapped[ReportStatus] = mapped_column(
        _enum_type(ReportStatus, "report_status"), default=ReportStatus.PENDING
    )
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    comments: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    validation_errors: Mapped[list[str]] = mapped_column(JSON, default=list)
    pdf_path: Mapped[str | None] = mapped_column(String, nullable=True)
    pdf_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    comment_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)

    run: Mapped[ReportRun] = relationship(back_populates="reports")
    student: Mapped[Student] = relationship(back_populates="reports")
    delivery: Mapped[Delivery | None] = relationship(back_populates="report", uselist=False)


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("report_runs.id", ondelete="CASCADE"), index=True
    )
    revision: Mapped[int] = mapped_column(Integer)
    batch_hash: Mapped[str] = mapped_column(String(128))
    approver: Mapped[str] = mapped_column(String(255))
    source: Mapped[str] = mapped_column(String(64))
    reference: Mapped[str] = mapped_column(String(255))
    approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    run: Mapped[ReportRun] = relationship(back_populates="approvals")


class Delivery(TimestampMixin, Base):
    __tablename__ = "deliveries"
    __table_args__ = (Index("ix_deliveries_status", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(
        ForeignKey("student_reports.id", ondelete="CASCADE"), unique=True
    )
    destination_ciphertext: Mapped[str] = mapped_column(String)
    status: Mapped[DeliveryStatus] = mapped_column(
        _enum_type(DeliveryStatus, "delivery_status"), default=DeliveryStatus.PENDING
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    provider_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    report: Mapped[StudentReport] = relationship(back_populates="delivery")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int | None] = mapped_column(
        ForeignKey("report_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(128), index=True)
    actor: Mapped[str] = mapped_column(String(255))
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    run: Mapped[ReportRun | None] = relationship(back_populates="audit_events")
