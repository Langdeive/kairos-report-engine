"""Synthetic provenance fixtures; no operational student records."""

import pytest
from pydantic import ValidationError

from kairos_report.schemas import QuestionTopicMetric


def test_counts_never_confirm_execution_and_review_cannot_strengthen() -> None:
    from kairos_report.analysis_provenance import ProvenanceError, validate_analysis

    report = {"questions": {"total": 7, "correct": 7, "accuracy_percent": 100}}
    validate_analysis("O relatório registra 7 questões e 100% de acertos.", report)
    for text in (
        "Você acertou questões",
        "você resolveu 7 questões",
        "Parabéns por ter praticado",
        "Você estudou Biologia",
        "Você domina Citologia",
        "Sua prática foi consistente",
    ):
        with pytest.raises(ProvenanceError, match="execution_evidence_required"):
            validate_analysis(text, report)
    with pytest.raises(ProvenanceError, match="execution_evidence_required"):
        validate_analysis("Revisão fortalecida", report, claims=[{"kind": "practice"}])


def test_verified_evidence_is_period_and_claim_bound() -> None:
    from kairos_report.analysis_provenance import ProvenanceError, validate_analysis

    report = {
        "identity": {
            "report_id": 1,
            "student_name": "Synthetic Student",
            "period_start": "2026-09-01",
            "period_end": "2026-09-30",
        }
    }
    evidence = {
        "kind": "execution",
        "scope": "overall",
        "execution_status": "confirmed",
        "report_id": 1,
        "student_name": "Synthetic Student",
        "period_start": "2026-09-01",
        "period_end": "2026-09-30",
        "source_reference": "synthetic-log",
        "verified_by": "synthetic-verifier",
    }
    validate_analysis("Você resolveu questões", report, verified_evidence=[evidence])
    for change in (
        {"execution_status": "recorded"},
        {"period_start": "2026-08-01"},
        {"source_reference": ""},
        {"report_id": 2},
        {"student_name": "Another Student"},
        {"scope": "topic", "topic": "Citologia"},
    ):
        with pytest.raises(ProvenanceError, match="execution_evidence_required"):
            validate_analysis(
                "Você resolveu questões", report, verified_evidence=[evidence | change]
            )
    with pytest.raises(ProvenanceError, match="execution_evidence_required"):
        validate_analysis("Você domina Citologia", report, verified_evidence=[evidence])


@pytest.mark.parametrize(
    "total,status",
    [(None, "recorded"), (1, "recorded"), (1, "placeholder"), (7, "placeholder"), (7, "unknown")],
)
def test_topic_highlights_never_borrow_parent_sample(total: int | None, status: str) -> None:
    from kairos_report.analysis_provenance import ProvenanceError, validate_analysis

    topic = {
        "discipline": "Biologia",
        "topic": "Citologia",
        "accuracy_percent": 100,
        "total": total,
        "correct": total,
        "wrong": 0 if total is not None else None,
        "execution_status": status,
    }
    report = {"questions": {"total": 7, "topics": [topic]}}
    with pytest.raises(ProvenanceError, match="topic_highlight_insufficient_evidence"):
        validate_analysis("Citologia foi um ponto forte", report)
    with pytest.raises(ProvenanceError, match="topic_highlight_insufficient_evidence"):
        validate_analysis(
            "Destaque",
            report,
            claims=[
                {
                    "kind": "topic_positive",
                    "scope": "topic",
                    "discipline": "Biologia",
                    "topic": "Citologia",
                }
            ],
        )
    if status == "recorded":
        validate_analysis("O relatório registra 100% em Citologia; amostra insuficiente.", report)


def test_scoped_percentages_and_missing_questions_fail_closed() -> None:
    from kairos_report.analysis_provenance import ProvenanceError, validate_analysis

    report = {
        "questions": {
            "total": 7,
            "accuracy_percent": 85.71,
            "disciplines": [{"name": "Biologia", "accuracy_percent": 50}],
        }
    }
    for text, claims in (
        ("Biologia registra 85,71% de acertos", []),
        (
            "Percentual",
            [
                {
                    "kind": "percentage",
                    "scope": "discipline",
                    "discipline": "Biologia",
                    "value": 85.71,
                }
            ],
        ),
        ("Geral", [{"kind": "percentage", "value": 50}]),
    ):
        with pytest.raises(ProvenanceError, match="percentage_scope_mismatch"):
            validate_analysis(text, report, claims=claims)
    validate_analysis("Biologia registra 50% de acertos", report)
    validate_analysis(
        "O relatório registra 85,71% geral", report, claims=[{"kind": "percentage", "value": 85.71}]
    )
    for questions in (None, {"total": 0, "accuracy_percent": 0}):
        with pytest.raises(ProvenanceError, match="percentage_scope_mismatch"):
            validate_analysis(
                "Percentual",
                {"questions": questions},
                claims=[{"kind": "percentage", "value": 100}],
            )


def test_legacy_percentage_aliases_are_unambiguous_and_overall_bound() -> None:
    from kairos_report.analysis_provenance import ProvenanceError, validate_analysis

    report = {
        "questions": {
            "accuracy_percent": 46.9,
            "disciplines": [
                {"name": "BIOLOGIA (Completo) - Perito Criminal", "accuracy_percent": 0},
                {"name": "Direito Penal (Parte Geral)", "accuracy_percent": 25},
                {"name": "Direito Penal (Parte Especial)", "accuracy_percent": 75},
            ],
        }
    }
    for text in ("Biologia: 46,9% de acertos", "Geral: 100% de acertos"):
        with pytest.raises(ProvenanceError, match="percentage_scope_mismatch"):
            validate_analysis(text, report)
    validate_analysis("Biologia: 0% de acertos", report)
    validate_analysis("Geral: 46,9% de acertos", report)
    with pytest.raises(ProvenanceError, match="percentage_scope_ambiguous"):
        validate_analysis("Direito Penal: 25% de acertos", report)


def test_pedagogical_future_and_negated_caveats_are_not_execution_claims() -> None:
    from kairos_report.analysis_provenance import ProvenanceError, validate_analysis

    for text in (
        "Resolve novas questões e refaz os erros.",
        "Como está sua prática?",
        "Esse recorte não confirma domínio.",
        "Não dá para afirmar que você estudou.",
    ):
        validate_analysis(text, {})
    with pytest.raises(ProvenanceError, match="execution_evidence_required"):
        validate_analysis("Esse recorte não confirma domínio. Mas você resolveu questões.", {})


def test_topic_positive_requires_consistent_counts_bound_to_requested_period() -> None:
    from kairos_report.analysis_provenance import ProvenanceError, validate_analysis

    period = {"period_start": "2026-09-01", "period_end": "2026-09-30"}
    topic = {
        "discipline": "Biologia",
        "topic": "Citologia",
        "accuracy_percent": 100,
        "total": 7,
        "correct": 7,
        "wrong": 0,
        "source_period": period,
    }
    report = {"identity": period, "questions": {"topics": [topic]}}
    validate_analysis("Citologia: resultado positivo nos registros", report)
    for change in (
        {"source_period": None},
        {"source_period": period | {"period_end": "2026-08-31"}},
        {"correct": 6},
        {"wrong": -1},
        {"total": 1, "correct": 1},
    ):
        altered = report | {"questions": {"topics": [topic | change]}}
        for text in (
            "Citologia: ponto forte",
            "Resultado positivo em Citologia",
            "Acertos registrados em Citologia",
        ):
            with pytest.raises(ProvenanceError, match="topic_highlight_insufficient_evidence"):
                validate_analysis(text, altered)
    validate_analysis("O relatório registra 7 questões em Citologia.", report)
    with pytest.raises(ProvenanceError, match="execution_evidence_required"):
        validate_analysis("Você praticou Citologia", report)


def test_live_launch_enrichment_filters_dates_and_matches_exact_topic() -> None:
    from datetime import date

    from kairos_report.analysis_provenance import enrich_topic_metrics

    html = """<table><tr><td>Biologia</td><td>Citologia</td><td>999</td><td>999</td>
    <td>100%</td><td>
    <a data-data='2026-08-31' data-questoes='99' data-acertos='99'></a>
    <a data-data='2026-09-01' data-questoes='1' data-acertos='1'></a>
    <a data-data='2026-09-30' data-questoes='3' data-acertos='2'></a>
    <a data-data='2026-10-01' data-questoes='99' data-acertos='99'></a>
    </td></tr><tr><td>Química</td><td>Citologia</td><td>100</td><td>100</td><td>100%</td>
    <td><a data-data='2026-09-15' data-questoes='100' data-acertos='100'></a></td>
    </tr></table>"""
    topics = [
        QuestionTopicMetric(discipline="Biologia", topic="Citologia", accuracy_percent=75),
        QuestionTopicMetric(discipline="Biologia", topic="Genética", accuracy_percent=100),
    ]
    result = enrich_topic_metrics(
        html, topics, period_start=date(2026, 9, 1), period_end=date(2026, 9, 30)
    )
    assert (result[0].total, result[0].correct, result[0].wrong) == (4, 3, 1)
    assert result[0].accuracy_percent == 75
    assert result[0].execution_status == "recorded"
    assert result[0].source_period.period_start == date(2026, 9, 1)
    assert "basis" not in result[0].source_period.model_dump()
    assert result[1].total is None
    assert result[1].execution_status == "unknown"
    assert topics[0].total is None  # Pure: no mutation of input.


@pytest.mark.parametrize(
    "launch",
    [
        "<a data-data='2026-09-01' data-questoes='1' data-acertos='2'></a>",
        "<a data-data='2026-09-01' data-questoes='-1' data-acertos='0'></a>",
        "<a data-data='2026-09-01' data-questoes='1'></a>",
        "<a data-data='not-a-date' data-questoes='1' data-acertos='1'></a>",
    ],
)
def test_launch_enrichment_rejects_malformed_records(launch: str) -> None:
    from datetime import date

    from kairos_report.analysis_provenance import ProvenanceError, enrich_topic_metrics

    topic = QuestionTopicMetric(discipline="Biologia", topic="Citologia", accuracy_percent=100)
    html = (
        "<table><tr><td>Biologia</td><td>Citologia</td><td>7</td><td>7</td><td>100</td><td>"
        "<a data-data='2026-09-01' data-questoes='1' data-acertos='1'></a>"
        + launch
        + "</td></tr></table>"
    )
    with pytest.raises(ProvenanceError, match="topic_launch_invalid"):
        enrich_topic_metrics(
            html, [topic], period_start=date(2026, 9, 1), period_end=date(2026, 9, 30)
        )


def test_launch_enrichment_legacy_and_ambiguous_sources_fail_closed() -> None:
    from datetime import date

    from kairos_report.analysis_provenance import ProvenanceError, enrich_topic_metrics

    topic = QuestionTopicMetric(discipline="Biologia", topic="Citologia", accuracy_percent=100)
    legacy = "<table><tr><td>Biologia</td><td>Citologia</td><td>100%</td></tr></table>"
    result = enrich_topic_metrics(
        legacy, [topic], period_start=date(2026, 9, 1), period_end=date(2026, 9, 30)
    )
    assert result[0].total is None and result[0].execution_status == "unknown"
    with pytest.raises(ProvenanceError, match="topic_launch_invalid"):
        enrich_topic_metrics(
            legacy, [topic], period_start=date(2026, 9, 30), period_end=date(2026, 9, 1)
        )
    row = (
        "<tr><td>Biologia</td><td>Citologia</td><td>1</td><td>1</td><td>100%</td>"
        "<td><a data-data='2026-09-01' data-questoes='1' data-acertos='1'></a></td></tr>"
    )
    with pytest.raises(ProvenanceError, match="topic_launch_invalid"):
        enrich_topic_metrics(
            "<table>" + row * 2 + "</table>",
            [topic],
            period_start=date(2026, 9, 1),
            period_end=date(2026, 9, 30),
        )


def test_topic_attention_has_same_sample_and_period_guard() -> None:
    from kairos_report.analysis_provenance import ProvenanceError, validate_analysis

    period = {"period_start": "2026-09-01", "period_end": "2026-09-30"}
    claim = {
        "kind": "topic_attention",
        "scope": "topic",
        "discipline": "Biologia",
        "topic": "Citologia",
    }
    topic = {
        "discipline": "Biologia",
        "topic": "Citologia",
        "accuracy_percent": 0,
        "total": 4,
        "correct": 0,
        "wrong": 4,
        "source_period": period,
    }
    report = {"identity": period, "questions": {"topics": [topic]}}
    validate_analysis("Citologia pede atenção nos registros", report, claims=[claim])
    for change in (
        {"total": None, "correct": None, "wrong": None},
        {"total": 1, "wrong": 1},
        {"source_period": None},
        {"execution_status": "placeholder"},
    ):
        with pytest.raises(ProvenanceError, match="topic_highlight_insufficient_evidence"):
            validate_analysis(
                "Citologia pede atenção",
                report | {"questions": {"topics": [topic | change]}},
                claims=[claim],
            )
    validate_analysis("Revise Citologia e resolve novas questões.", {})


def test_nonfinite_percentage_claim_cannot_bypass_comparison() -> None:
    from kairos_report.analysis_provenance import ProvenanceError, validate_analysis

    with pytest.raises(ProvenanceError, match="percentage_scope_mismatch"):
        validate_analysis(
            "Percentual",
            {"questions": {"accuracy_percent": 50}},
            claims=[{"kind": "percentage", "value": float("nan")}],
        )


def test_launch_enrichment_preserves_canonical_percent_contract() -> None:
    from datetime import date

    from kairos_report.analysis_provenance import ProvenanceError, enrich_topic_metrics

    html = (
        "<table><tr><td>Biologia</td><td>Citologia</td><td>15</td><td>7</td><td>46.7</td>"
        "<td><a data-data='2026-09-01' data-questoes='15' data-acertos='7'></a>"
        "</td></tr></table>"
    )
    topic = QuestionTopicMetric(discipline="Biologia", topic="Citologia", accuracy_percent=100)
    with pytest.raises(ProvenanceError, match="topic_launch_percent_mismatch"):
        enrich_topic_metrics(
            html, [topic], period_start=date(2026, 9, 1), period_end=date(2026, 9, 30)
        )
    rounded = topic.model_copy(update={"accuracy_percent": 46.7})
    result = enrich_topic_metrics(
        html, [rounded], period_start=date(2026, 9, 1), period_end=date(2026, 9, 30)
    )
    assert result[0].accuracy_percent == 46.67
    outside = enrich_topic_metrics(
        html, [topic], period_start=date(2026, 10, 1), period_end=date(2026, 10, 31)
    )
    assert outside[0].total is None
    assert outside[0].execution_status == "unknown"
    assert outside[0].accuracy_percent == 100


@pytest.mark.parametrize("extra_cell", ["", "<td>unexpected</td>"])
def test_matching_malformed_launch_row_cannot_authorize_partial_highlight(extra_cell: str) -> None:
    from datetime import date

    from kairos_report.analysis_provenance import ProvenanceError, enrich_topic_metrics

    topic = QuestionTopicMetric(discipline="Biologia", topic="Citologia", accuracy_percent=100)
    valid = (
        "<tr><td>Biologia</td><td>Citologia</td><td>2</td><td>2</td><td>100%</td>"
        "<td><a data-data='2026-09-01' data-questoes='2' data-acertos='2'></a></td></tr>"
    )
    # Five cells without extra_cell; seven cells otherwise.
    summary = "<td>8</td><td>0</td>" + ("<td>0%</td>" if extra_cell else "")
    malformed = (
        "<tr><td>Biologia</td><td>Citologia</td>"
        + summary
        + "<td><a data-data='2026-09-02' data-questoes='8' data-acertos='0'></a></td>"
        + extra_cell
        + "</tr>"
    )
    with pytest.raises(ProvenanceError, match="^topic_launch_invalid$"):
        enrich_topic_metrics(
            "<table>" + valid + malformed + "</table>",
            [topic],
            period_start=date(2026, 9, 1),
            period_end=date(2026, 9, 30),
        )


@pytest.mark.parametrize("cell_count", [3, 5, 7])
@pytest.mark.parametrize("malformed_first", [False, True])
def test_matching_row_without_launch_attrs_cannot_authorize_partial_counts(
    cell_count: int, malformed_first: bool
) -> None:
    from datetime import date

    from kairos_report.analysis_provenance import ProvenanceError, enrich_topic_metrics

    topic = QuestionTopicMetric(discipline="Biologia", topic="Citologia", accuracy_percent=100)
    valid = (
        "<tr><td>Biologia</td><td>Citologia</td><td>2</td><td>2</td><td>100%</td>"
        "<td><a data-data='2026-09-01' data-questoes='2' data-acertos='2'></a></td></tr>"
    )
    values = ["Biologia", "Citologia", "8", "0", "0%", "<a></a>", "unexpected"]
    malformed = "<tr>" + "".join(f"<td>{v}</td>" for v in values[:cell_count]) + "</tr>"
    rows = malformed + valid if malformed_first else valid + malformed
    with pytest.raises(ProvenanceError, match="^topic_launch_invalid$"):
        enrich_topic_metrics(
            "<table>" + rows + "</table>",
            [topic],
            period_start=date(2026, 9, 1),
            period_end=date(2026, 9, 30),
        )


@pytest.mark.parametrize("last_cell", ["", "<a></a>"])
@pytest.mark.parametrize("valid_position", ["before", "after", "absent"])
def test_matching_six_cell_row_requires_launch_metadata(
    last_cell: str, valid_position: str
) -> None:
    from datetime import date

    from kairos_report.analysis_provenance import ProvenanceError, enrich_topic_metrics

    topic = QuestionTopicMetric(discipline="Biologia", topic="Citologia", accuracy_percent=100)
    valid = (
        "<tr><td>Biologia</td><td>Citologia</td><td>2</td><td>2</td><td>100%</td>"
        "<td><a data-data='2026-09-01' data-questoes='2' data-acertos='2'></a></td></tr>"
    )
    malformed = (
        "<tr><td>Biologia</td><td>Citologia</td><td>8</td><td>0</td><td>0%</td>"
        f"<td>{last_cell}</td></tr>"
    )
    rows = {
        "before": valid + malformed,
        "after": malformed + valid,
        "absent": malformed,
    }[valid_position]
    with pytest.raises(ProvenanceError, match="^topic_launch_invalid$"):
        enrich_topic_metrics(
            "<table>" + rows + "</table>",
            [topic],
            period_start=date(2026, 9, 1),
            period_end=date(2026, 9, 30),
        )


@pytest.mark.parametrize("malformed_first", [False, True])
def test_six_cell_launch_row_cannot_ignore_anchor_without_metadata(malformed_first: bool) -> None:
    from datetime import date

    from kairos_report.analysis_provenance import ProvenanceError, enrich_topic_metrics

    topic = QuestionTopicMetric(discipline="Biologia", topic="Citologia", accuracy_percent=100)
    valid = "<a data-data='2026-09-01' data-questoes='2' data-acertos='2'></a>"
    anchors = "<a></a>" + valid if malformed_first else valid + "<a></a>"
    html = (
        "<table><tr><td>Biologia</td><td>Citologia</td><td>2</td><td>2</td><td>100%</td>"
        f"<td>{anchors}</td></tr></table>"
    )
    with pytest.raises(ProvenanceError, match="^topic_launch_invalid$"):
        enrich_topic_metrics(
            html, [topic], period_start=date(2026, 9, 1), period_end=date(2026, 9, 30)
        )


def test_launch_enrichment_preserves_placeholder_with_valid_dated_launches() -> None:
    from datetime import date

    from kairos_report.analysis_provenance import (
        ProvenanceError,
        enrich_topic_metrics,
        validate_analysis,
    )

    topic = QuestionTopicMetric(
        discipline="Biologia",
        topic="Citologia",
        accuracy_percent=100,
        execution_status="placeholder",
    )
    html = (
        "<table><tr><td>Biologia</td><td>Citologia</td><td>2</td><td>2</td><td>100%</td>"
        "<td><a data-data='2026-09-01' data-questoes='2' data-acertos='2'></a></td></tr></table>"
    )
    result = enrich_topic_metrics(
        html, [topic], period_start=date(2026, 9, 1), period_end=date(2026, 9, 30)
    )
    assert result[0].execution_status == "placeholder"
    assert (result[0].total, result[0].correct, result[0].wrong) == (2, 2, 0)
    period = {"period_start": "2026-09-01", "period_end": "2026-09-30"}
    with pytest.raises(ProvenanceError, match="topic_highlight_insufficient_evidence"):
        validate_analysis(
            "Citologia: ponto forte",
            {"identity": period, "questions": {"topics": [result[0].model_dump(mode="json")]}},
        )
    assert topic.total is None


def test_launch_enrichment_aggregates_matching_rows_on_distinct_dates() -> None:
    from datetime import date

    from kairos_report.analysis_provenance import enrich_topic_metrics

    topic = QuestionTopicMetric(discipline="Biologia", topic="Citologia", accuracy_percent=75)
    rows = "".join(
        "<tr><td>Biologia</td><td>Citologia</td><td>999</td><td>999</td><td>100%</td>"
        f"<td><a data-data='{day}' data-questoes='{total}' data-acertos='{correct}'></a>"
        "</td></tr>"
        for day, total, correct in (
            ("2026-08-31", 8, 0),
            ("2026-09-01", 2, 2),
            ("2026-09-30", 2, 1),
            ("2026-10-01", 8, 0),
        )
    )
    result = enrich_topic_metrics(
        "<table>" + rows + "</table>",
        [topic],
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 30),
    )
    assert (result[0].total, result[0].correct, result[0].wrong) == (4, 3, 1)
    assert result[0].accuracy_percent == 75
    assert result[0].execution_status == "recorded"


def test_launch_enrichment_rejects_duplicate_topic_date_within_one_row() -> None:
    from datetime import date

    from kairos_report.analysis_provenance import ProvenanceError, enrich_topic_metrics

    topic = QuestionTopicMetric(discipline="Biologia", topic="Citologia", accuracy_percent=100)
    launch = "<a data-data='2026-09-01' data-questoes='2' data-acertos='2'></a>"
    html = (
        "<table><tr><td>Biologia</td><td>Citologia</td><td>4</td><td>4</td><td>100%</td><td>"
        + launch * 2
        + "</td></tr></table>"
    )
    with pytest.raises(ProvenanceError, match="^topic_launch_invalid$"):
        enrich_topic_metrics(
            html, [topic], period_start=date(2026, 9, 1), period_end=date(2026, 9, 30)
        )


def test_topic_counts_are_optional_and_consistent() -> None:
    topic = QuestionTopicMetric(discipline="Biologia", topic="Citologia", accuracy_percent=100)
    assert topic.total is None
    assert topic.execution_status == "recorded"
    for counts in (
        {"total": 2, "correct": 1},
        {"total": 2, "correct": 2, "wrong": 1},
        {"total": 2, "correct": 1, "wrong": 1},
    ):
        with pytest.raises(ValidationError):
            QuestionTopicMetric(
                discipline="Biologia", topic="Citologia", accuracy_percent=100, **counts
            )
    assert (
        QuestionTopicMetric(
            discipline="Biologia",
            topic="Citologia",
            accuracy_percent=100,
            total=2,
            correct=2,
            wrong=0,
        ).total
        == 2
    )
