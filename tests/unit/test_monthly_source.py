from datetime import date

import pytest

from kairos_report.errors import TutoryContractChanged
from kairos_report.pdf.layouts.week_dates import group_four
from kairos_report.report_data import build_report_data
from kairos_report.tutory.parser import parse_question_report, parse_report
from tests.daily_fixtures import performance_html, question_html

START, END = date(2026, 8, 1), date(2026, 8, 31)


@pytest.mark.parametrize("lifetime_days", [401, 12])
def test_monthly_totals_use_daily_evidence_even_when_lifetime_days_look_plausible(
    lifetime_days: int,
) -> None:
    metrics = parse_report(
        performance_html(lifetime_days=lifetime_days), period_start=START, period_end=END
    )
    assert metrics.total_hours == 15
    assert metrics.study_days == 9
    assert metrics.average_study_hours == pytest.approx(15 / 9)
    assert sum(item.study_hours for item in metrics.ranking) == 8.5
    assert metrics.monthly_source.period_start == START
    assert len(metrics.monthly_source.daily) == 31
    assert metrics.monthly_source.daily[0].label == "2026/08/01"


@pytest.mark.parametrize(
    ("year", "month", "days"), [(2026, 2, 28), (2024, 2, 29), (2026, 4, 30), (2026, 8, 31)]
)
def test_all_month_lengths_preserve_calendar_edges_in_four_shared_groups(
    year: int,
    month: int,
    days: int,
) -> None:
    start, end = date(year, month, 1), date(year, month, days)
    metrics = parse_report(
        performance_html(year, month, hours=[1.0] * days), period_start=start, period_end=end
    )
    questions = parse_question_report(
        question_html(labels=[f"{year}/{month:02}/01", f"{year}/{month:02}/{days}"]),
        period_start=start,
        period_end=end,
    )
    identity = {"period_start": start.isoformat(), "period_end": end.isoformat()}
    study_groups = group_four(
        [week.model_dump() for week in metrics.weekly], identity, ("hours", "target_hours")
    )
    question_groups = group_four(
        [week.model_dump() for week in questions.weekly], identity, ("total", "correct", "wrong")
    )
    assert len(study_groups) == len(question_groups) == 4
    assert [g["label"] for g in study_groups] == [g["label"] for g in question_groups]
    assert sum(g["hours"] for g in study_groups) == days
    assert sum(g["target_hours"] for g in study_groups) == days
    assert sum(g["total"] for g in question_groups) == 670
    assert question_groups[0]["total"] == 600
    assert question_groups[-1]["total"] == 70


@pytest.mark.parametrize("questions_present", [False, True])
def test_complete_zero_study_axis_keeps_questions_independent(questions_present: bool) -> None:
    metrics = parse_report(performance_html(hours=[0.0] * 31), period_start=START, period_end=END)
    html = (
        question_html()
        if questions_present
        else question_html(labels=[], correct=[], wrong=[], total=0, headline_correct=0)
    )
    questions = parse_question_report(html, period_start=START, period_end=END)
    data = build_report_data(
        report_id=1, period_start=START, period_end=END, metrics=metrics, questions=questions
    )
    assert data.summary.total_hours == data.summary.study_days == 0
    assert data.summary.average_hours_per_active_day == 0
    assert data.questions.total == (670 if questions_present else 0)


@pytest.mark.parametrize(
    "bad_label", ["2026/08/01", "2026/07/31", "2026/08/32", "2026/8/02", "Semana 32/2026"]
)
def test_daily_performance_rejects_duplicate_outside_and_malformed_dates(bad_label: str) -> None:
    labels = [f"2026/08/{day:02}" for day in range(1, 32)]
    labels[1] = bad_label
    with pytest.raises(TutoryContractChanged):
        parse_report(performance_html(labels=labels), period_start=START, period_end=END)


@pytest.mark.parametrize(
    "change", ["missing_day", "empty", "alignment", "negative", "nan", "modality_sum"]
)
def test_daily_performance_fails_closed_for_incomplete_or_invalid_series(change: str) -> None:
    kwargs = {
        "missing_day": {
            "labels": [f"2026/08/{day:02}" for day in range(1, 31)],
            "hours": [1.0] * 30,
        },
        "empty": {"labels": [], "hours": []},
        "alignment": {"targets": [1.0]},
        "negative": {"hours": [-1.0] + [1.0] * 30},
        "nan": {"hours": [float("nan")] + [1.0] * 30},
        "modality_sum": {"modalities": {"Estudo": 14.0}},
    }[change]
    with pytest.raises(TutoryContractChanged):
        parse_report(performance_html(**kwargs), period_start=START, period_end=END)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"labels": ["2026/08/01", "2026/08/01"]},
        {"labels": ["2026/08/01", "2026/09/01"]},
        {"labels": ["2026/08/01", "Semana 32/2026"]},
        {"labels": [], "correct": [], "wrong": []},
        {"correct": [500]},
        {"correct": [500, 49]},
        {"wrong": [100, 19]},
        {"correct": [500.5, 49.5]},
        {"total": 670.5},
    ],
)
def test_daily_questions_reject_invalid_evidence_and_headline_mismatches(kwargs: dict) -> None:
    with pytest.raises(TutoryContractChanged):
        parse_question_report(question_html(**kwargs), period_start=START, period_end=END)


@pytest.mark.parametrize("source", ["performance", "questions"])
def test_normalized_sources_cannot_be_relabelled_to_another_month(source: str) -> None:
    metrics = parse_report(performance_html(), period_start=START, period_end=END)
    questions = parse_question_report(question_html(), period_start=START, period_end=END)
    if source == "questions":
        metrics = parse_report(
            performance_html(2026, 7), period_start=date(2026, 7, 1), period_end=date(2026, 7, 31)
        )
    with pytest.raises(ValueError, match="source period"):
        build_report_data(
            report_id=1,
            period_start=date(2026, 7, 1),
            period_end=date(2026, 7, 31),
            metrics=metrics,
            questions=questions,
        )


def test_daily_sources_are_sorted_before_weekly_aggregation() -> None:
    labels = [f"2026/08/{day:02}" for day in range(31, 0, -1)]
    metrics = parse_report(performance_html(labels=labels), period_start=START, period_end=END)
    assert metrics.weekly[0].label == "Semana 31/2026"
    assert metrics.weekly[-1].label == "Semana 36/2026"
    assert metrics.weekly[-1].hours == 1
