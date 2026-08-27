from datetime import date

import pytest

from kairos_report.report_data import build_report_data
from kairos_report.schemas import RankedSubject, StudentMetrics, WeeklyMetric


def complete_metrics() -> StudentMetrics:
    return StudentMetrics(
        student_name="Aluno Exemplo",
        course="Curso Preparatório Exemplo",
        total_hours=18.5,
        accuracy_percent=76.5,
        plan_progress_percent=42,
        study_days=16,
        average_study_hours=1.15,
        most_studied_subject="Direito Penal",
        least_studied_subject="Arquivologia",
        ranking=[
            RankedSubject(
                rank=1,
                name="Direito Penal",
                accuracy_percent=82,
                study_hours=5.5,
            ),
            RankedSubject(
                rank=2,
                name="Português",
                accuracy_percent=71.5,
                study_hours=3,
            ),
        ],
        weekly=[
            WeeklyMetric(label="Semana 1", hours=8, target_hours=10),
            WeeklyMetric(label="Semana 2", hours=10.5, target_hours=10),
        ],
        modality_hours={"Teoria": 9.5, "Questões": 7, "Revisão": 2},
        subject_progress={"Direito Penal": 58, "Português": 37},
        performance_by_area={"Direito": 79, "Língua Portuguesa": 71.5},
    )


def test_build_report_data_calculates_supported_monthly_insights() -> None:
    package = build_report_data(
        report_id=42,
        period_start=date(2026, 8, 1),
        period_end=date(2026, 8, 31),
        metrics=complete_metrics(),
    )

    assert package.schema_version == "1.0"
    assert package.identity.model_dump(mode="json") == {
        "report_id": 42,
        "student_name": "Aluno Exemplo",
        "course": "Curso Preparatório Exemplo",
        "period_start": "2026-08-01",
        "period_end": "2026-08-31",
    }
    assert package.summary.model_dump() == {
        "total_hours": 18.5,
        "study_days": 16,
        "inactive_days": 15,
        "average_hours_per_active_day": 1.15,
        "accuracy_percent": 76.5,
        "plan_progress_percent": 42.0,
        "remaining_progress_percent": 58.0,
    }
    assert package.weekly_evolution.total_target_hours == 20
    assert package.weekly_evolution.adherence_percent == 92.5
    assert package.weekly_evolution.first_to_last_hours_delta == 2.5
    assert package.weekly_evolution.trend == "improving"
    assert package.modalities.total_hours == 18.5
    assert package.modalities.shares_percent == {
        "Teoria": 51.35,
        "Questões": 37.84,
        "Revisão": 10.81,
    }
    assert package.unavailable_metrics == [
        "active_days_by_week",
        "accuracy_by_week",
        "most_improved_subject",
    ]
    serialized = package.model_dump(mode="json")
    assert "peer_average_hours" not in serialized["weekly_evolution"]["weeks"][0]


def test_build_report_data_does_not_invent_trends_or_percentages() -> None:
    metrics = complete_metrics().model_copy(
        update={
            "weekly": [WeeklyMetric(label="Semana única", hours=4, target_hours=0)],
            "modality_hours": {},
        }
    )

    package = build_report_data(
        report_id=7,
        period_start=date(2026, 2, 1),
        period_end=date(2026, 2, 28),
        metrics=metrics,
    )

    assert package.summary.inactive_days == 12
    assert package.weekly_evolution.total_target_hours == 0
    assert package.weekly_evolution.adherence_percent is None
    assert package.weekly_evolution.first_to_last_hours_delta is None
    assert package.weekly_evolution.trend == "unavailable"
    assert package.modalities.total_hours == 0
    assert package.modalities.shares_percent == {}


def test_build_report_data_rejects_an_inverted_period() -> None:
    with pytest.raises(ValueError, match="period_end"):
        build_report_data(
            report_id=7,
            period_start=date(2026, 8, 31),
            period_end=date(2026, 8, 1),
            metrics=complete_metrics(),
        )


def test_build_report_data_rejects_more_study_days_than_the_period() -> None:
    metrics = complete_metrics().model_copy(update={"study_days": 32})

    with pytest.raises(ValueError, match="study_days"):
        build_report_data(
            report_id=7,
            period_start=date(2026, 8, 1),
            period_end=date(2026, 8, 31),
            metrics=metrics,
        )


@pytest.mark.parametrize(
    ("last_week_hours", "expected_delta", "expected_trend"),
    [(8, 0, "stable"), (4, -4, "declining")],
)
def test_build_report_data_classifies_non_improving_weekly_trends(
    last_week_hours: float,
    expected_delta: float,
    expected_trend: str,
) -> None:
    metrics = complete_metrics().model_copy(
        update={
            "weekly": [
                WeeklyMetric(label="Semana 1", hours=8, target_hours=10),
                WeeklyMetric(label="Semana 2", hours=last_week_hours, target_hours=10),
            ]
        }
    )

    package = build_report_data(
        report_id=7,
        period_start=date(2026, 8, 1),
        period_end=date(2026, 8, 31),
        metrics=metrics,
    )

    assert package.weekly_evolution.first_to_last_hours_delta == expected_delta
    assert package.weekly_evolution.trend == expected_trend
