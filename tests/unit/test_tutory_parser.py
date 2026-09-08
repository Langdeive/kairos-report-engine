from pathlib import Path

import pytest

from kairos_report.errors import TutoryContractChanged
from kairos_report.tutory.parser import (
    parse_question_report,
    parse_report,
    parse_student_activity_report,
)

FIXTURE = Path(__file__).parents[1] / "fixtures" / "tutory" / "report_page.html"
QUESTION_FIXTURE = Path(__file__).parents[1] / "fixtures" / "tutory" / "question_report_page.html"
ACTIVITY_FIXTURE = Path(__file__).parents[1] / "fixtures" / "tutory" / "student_report_page.html"


def test_parse_question_report_extracts_totals_weekly_and_disciplines() -> None:
    metrics = parse_question_report(QUESTION_FIXTURE.read_text(encoding="utf-8"))

    assert metrics.total == 541
    assert metrics.correct == 442
    assert metrics.wrong == 99
    assert metrics.accuracy_percent == 81.7
    assert metrics.weekly[1].label == "Semana 28/2026"
    assert metrics.weekly[1].correct == 83
    assert metrics.weekly[1].wrong == 24
    assert metrics.weekly[1].total == 107
    assert metrics.disciplines[0].name == "Direito Constitucional"
    assert metrics.disciplines[0].total == 51
    assert metrics.disciplines[0].correct == 42
    assert metrics.disciplines[0].accuracy_percent == 82.35
    assert metrics.topics[0].topic == "Direitos políticos"
    assert metrics.topics[0].accuracy_percent == 100


def test_parse_student_activity_report_extracts_revisions_and_study_history() -> None:
    details = parse_student_activity_report(ACTIVITY_FIXTURE.read_text(encoding="utf-8"))

    assert details.revisions[0].discipline == "Contabilidade Geral"
    assert details.revisions[0].count == 2
    assert details.total_revisions == 3
    assert details.activities[0].modality == "Estudo"
    assert details.activities[0].hours == 1.5
    assert details.activities[1].hours == 0.5


def test_parse_report_extracts_every_confirmed_field() -> None:
    metrics = parse_report(FIXTURE.read_text(encoding="utf-8"))

    assert metrics.student_name == "Aluno Exemplo"
    assert metrics.course == "Curso Preparatório Exemplo"
    assert metrics.total_hours == 18.5
    assert metrics.accuracy_percent == 76.5
    assert metrics.plan_progress_percent == 42
    assert metrics.study_days == 16
    assert metrics.average_study_hours == 1.15
    assert metrics.most_studied_subject == "Direito Penal"
    assert metrics.least_studied_subject == "Arquivologia"
    assert metrics.ranking[0].name == "Direito Penal"
    assert metrics.ranking[0].accuracy_percent == 82
    assert metrics.ranking[0].study_hours == 5.5
    assert metrics.weekly[1].label == "Semana 32/2026"
    assert metrics.weekly[1].hours == 10.5
    assert metrics.weekly[1].target_hours == 10
    assert metrics.weekly[1].peer_average_hours == 12
    assert metrics.modality_hours == {"Teoria": 9.5, "Questões": 7, "Revisão": 2}
    assert metrics.subject_progress == {"Direito Penal": 58, "Português": 37}
    assert metrics.performance_by_area == {"Direito": 79, "Língua Portuguesa": 71.5}


def test_parse_report_accepts_current_h5_insight_headings() -> None:
    html = FIXTURE.read_text(encoding="utf-8")
    for label in (
        "Média de tempo",
        "Matéria mais estudada",
        "Matéria menos estudada",
    ):
        html = html.replace(f"<h4>{label}</h4>", f"<h5>{label}</h5>")

    metrics = parse_report(html)

    assert metrics.average_study_hours == 1.15
    assert metrics.most_studied_subject == "Direito Penal"
    assert metrics.least_studied_subject == "Arquivologia"


def test_parse_report_preserves_missing_ranking_accuracy_as_unavailable() -> None:
    html = FIXTURE.read_text(encoding="utf-8").replace(
        "<td>82%</td>", '<td class="score-cell"></td>', 1
    )

    metrics = parse_report(html)

    assert metrics.ranking[0].accuracy_percent is None
    assert metrics.ranking[1].accuracy_percent == 71.5


def test_parse_report_converts_current_colon_time_format_to_decimal_hours() -> None:
    html = (
        FIXTURE.read_text(encoding="utf-8")
        .replace("18h 30m", "18:30", 1)
        .replace("1h 09m", "01:09 por dia de estudo", 1)
    )

    metrics = parse_report(html)

    assert metrics.total_hours == 18.5
    assert metrics.average_study_hours == 1.15


@pytest.mark.parametrize(
    "label",
    ["Total de Horas", "% de acertos", "Progresso Geral", "Dias de Estudo"],
)
def test_parse_report_names_a_missing_required_metric(label: str) -> None:
    html = FIXTURE.read_text(encoding="utf-8").replace(label, "Campo removido", 1)

    with pytest.raises(TutoryContractChanged, match=label):
        parse_report(html)


def test_parse_report_rejects_missing_chart_data_without_echoing_html() -> None:
    html = FIXTURE.read_text(encoding="utf-8").replace("chartData", "removedData", 1)

    with pytest.raises(TutoryContractChanged) as captured:
        parse_report(html)

    assert "Aluno Exemplo" not in str(captured.value)


@pytest.mark.parametrize(
    ("original", "invalid"),
    [
        ("76,5%", "176,5%"),
        ("horas: [8, 10.5]", "horas: [-8, 10.5]"),
        ("percentuais: [58, 37]", "percentuais: [158, 37]"),
    ],
)
def test_parse_report_rejects_out_of_range_metrics_without_exposing_student(
    original: str,
    invalid: str,
) -> None:
    html = FIXTURE.read_text(encoding="utf-8").replace(original, invalid, 1)

    with pytest.raises(TutoryContractChanged) as captured:
        parse_report(html)

    assert "Aluno Exemplo" not in str(captured.value)
