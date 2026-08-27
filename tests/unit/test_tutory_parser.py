from pathlib import Path

import pytest

from kairos_report.errors import TutoryContractChanged
from kairos_report.tutory.parser import parse_report

FIXTURE = Path(__file__).parents[1] / "fixtures" / "tutory" / "report_page.html"


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
