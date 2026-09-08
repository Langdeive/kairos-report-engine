from datetime import date
from pathlib import Path

from pypdf import PdfReader

from kairos_report.pdf.generator import generate_validation_pdf
from kairos_report.report_data import (
    DisciplineOverview,
    ModalityOverview,
    MonthlySummary,
    ReportDataPackage,
    ReportIdentity,
    ReportWeek,
    WeeklyEvolution,
)
from kairos_report.schemas import (
    QuestionDisciplineMetric,
    QuestionMetrics,
    QuestionWeekMetric,
    RankedSubject,
    RevisionMetric,
    StudentActivityMetrics,
    StudyActivityMetric,
)


def validation_data() -> ReportDataPackage:
    return ReportDataPackage(
        identity=ReportIdentity(
            report_id=1,
            student_name="Natane",
            course="Curso não informado na captura",
            period_start=date(2026, 7, 1),
            period_end=date(2026, 7, 31),
        ),
        summary=MonthlySummary(
            total_hours=35.25,
            study_days=7,
            inactive_days=24,
            average_hours_per_active_day=1.5,
            accuracy_percent=75,
            plan_progress_percent=0,
            remaining_progress_percent=100,
        ),
        weekly_evolution=WeeklyEvolution(
            weeks=[ReportWeek(label="Dados semanais recuperados", hours=1.5, target_hours=62)],
            total_target_hours=62,
            adherence_percent=2.42,
            first_to_last_hours_delta=None,
            trend="unavailable",
        ),
        disciplines=DisciplineOverview(
            most_studied="Não disponível na captura",
            least_studied="Não disponível na captura",
            ranking=[],
            progress_percent={},
        ),
        modalities=ModalityOverview(
            hours={"Modalidade registrada": 1.5},
            total_hours=1.5,
            shares_percent={"Modalidade registrada": 100},
        ),
        performance_by_area={},
        unavailable_metrics=[
            "active_days_by_week",
            "accuracy_by_week",
            "weekly_total_reconciliation",
        ],
    )


def zero_activity_data() -> ReportDataPackage:
    data = validation_data()
    data.summary.total_hours = 0
    data.summary.study_days = 0
    data.summary.inactive_days = 31
    data.summary.average_hours_per_active_day = 0
    data.summary.accuracy_percent = 0
    data.summary.plan_progress_percent = 0
    data.summary.remaining_progress_percent = 100
    data.weekly_evolution.weeks = [
        ReportWeek(label=f"Semana {number}/2026", hours=0, target_hours=10)
        for number in range(27, 32)
    ]
    data.disciplines.ranking = []
    data.disciplines.progress_percent = {
        "Direito Penal": 0,
        "Língua Portuguesa": 0,
    }
    data.modalities = ModalityOverview(hours={}, total_hours=0, shares_percent={})
    data.performance_by_area = {}
    return data


def test_generate_validation_pdf_writes_readable_three_page_report(tmp_path: Path) -> None:
    output = tmp_path / "relatorio-validacao.pdf"

    result = generate_validation_pdf(validation_data(), output)

    assert result == output
    assert output.stat().st_size > 5_000
    reader = PdfReader(output)
    assert len(reader.pages) == 3
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "Natane" in text
    assert "01/07/2026 a 31/07/2026" in text
    assert "35h 15min" in text
    assert "75%" in text
    assert "Dados indisponíveis" in text


def test_generate_validation_pdf_includes_every_subject_progress_entry(tmp_path: Path) -> None:
    data = validation_data()
    data.disciplines.progress_percent = {
        "Direito Penal": 58,
        "Língua Portuguesa": 37.5,
        "Arquivologia": 12,
    }
    output = tmp_path / "relatorio-completo.pdf"

    generate_validation_pdf(data, output)

    reader = PdfReader(output)
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert len(reader.pages) == 4
    assert "Progresso por disciplina" in text
    assert "Direito Penal" in text
    assert "Língua Portuguesa" in text
    assert "37,5%" in text
    assert "Arquivologia" in text


def test_generate_validation_pdf_keeps_five_ranking_rows_on_the_weekly_page(
    tmp_path: Path,
) -> None:
    data = validation_data()
    data.weekly_evolution.weeks = [
        ReportWeek(label=f"Semana {number}/2026", hours=number / 2, target_hours=11)
        for number in range(27, 32)
    ]
    data.disciplines.ranking = [
        RankedSubject(
            rank=rank,
            name=name,
            study_hours=rank / 2,
            accuracy_percent=None,
        )
        for rank, name in enumerate(
            [
                "Contabilidade Geral - Área Policial (Mentoria)",
                "Leitura de Lei Seca",
                "Direito administrativo - Área Policial (Mentoria)",
                "Medicina Legal - Meta Fixa",
                "DISCURSIVAS /REDAÇÃO",
            ],
            start=1,
        )
    ]
    data.disciplines.progress_percent = {"Direito Penal": 16}
    output = tmp_path / "relatorio-ranking-cinco-linhas.pdf"

    generate_validation_pdf(data, output)

    reader = PdfReader(output)
    page_texts = [page.extract_text() or "" for page in reader.pages]
    assert len(reader.pages) == 4
    assert "DISCURSIVAS /REDAÇÃO" in page_texts[1]
    assert "Progresso por disciplina" in page_texts[2]


def test_zero_study_with_questions_replaces_study_charts_with_message(
    tmp_path: Path,
) -> None:
    data = zero_activity_data()
    data.summary.accuracy_percent = 89
    data.performance_by_area = {"Direito Penal": 82}
    output = tmp_path / "somente-questoes.pdf"

    generate_validation_pdf(data, output)

    pages = [page.extract_text() or "" for page in PdfReader(output).pages]
    full_text = "\n".join(pages)
    first_page_text = " ".join(pages[0].split())
    assert len(pages) == 2
    assert "Sem horas de estudo registradas no período" in first_page_text
    assert "Evolução semanal" not in full_text
    assert "Progresso por disciplina" not in full_text
    assert "Desempenho em questões" in pages[1]
    assert "89%" in pages[1]
    assert "Direito Penal" in pages[1]


def test_study_without_questions_keeps_study_and_shows_question_message(
    tmp_path: Path,
) -> None:
    data = validation_data()
    data.summary.accuracy_percent = 0
    data.performance_by_area = {}
    output = tmp_path / "somente-estudo.pdf"

    generate_validation_pdf(data, output)

    full_text = "\n".join(page.extract_text() or "" for page in PdfReader(output).pages)
    assert "Evolução semanal" in full_text
    assert "35h 15min" in full_text
    assert "Nenhuma questão respondida no período" in full_text
    assert "Desempenho por área não disponível na captura" not in full_text


def test_no_study_and_no_questions_uses_only_absence_messages(tmp_path: Path) -> None:
    output = tmp_path / "sem-atividade.pdf"

    generate_validation_pdf(zero_activity_data(), output)

    pages = [page.extract_text() or "" for page in PdfReader(output).pages]
    full_text = "\n".join(pages)
    first_page_text = " ".join(pages[0].split())
    assert len(pages) == 2
    assert "Sem horas de estudo registradas no período" in first_page_text
    assert "Nenhuma questão respondida no período" in pages[1]
    assert "Evolução semanal" not in full_text
    assert "Progresso por disciplina" not in full_text
    assert "0h" not in full_text
    assert "0%" not in full_text


def test_study_and_questions_keep_both_information_blocks(tmp_path: Path) -> None:
    data = validation_data()
    data.performance_by_area = {"Direito Penal": 82}
    output = tmp_path / "estudo-e-questoes.pdf"

    generate_validation_pdf(data, output)

    full_text = "\n".join(page.extract_text() or "" for page in PdfReader(output).pages)
    assert "Evolução semanal" in full_text
    assert "Desempenho em questões" in full_text
    assert "75%" in full_text
    assert "Direito Penal" in full_text
    assert "Sem horas de estudo registradas no período" not in full_text
    assert "Nenhuma questão respondida no período" not in full_text


def test_study_without_weekly_or_ranking_detail_uses_messages_instead_of_zeros(
    tmp_path: Path,
) -> None:
    data = validation_data()
    data.summary.total_hours = 61.25
    data.summary.study_days = 30
    data.summary.average_hours_per_active_day = 0
    data.summary.accuracy_percent = 0
    data.weekly_evolution.weeks = [
        ReportWeek(label=f"Semana {number}/2026", hours=0, target_hours=14)
        for number in range(27, 32)
    ]
    data.disciplines.most_studied = "Nenhuma"
    data.disciplines.least_studied = "Nenhuma"
    data.disciplines.ranking = []
    data.modalities = ModalityOverview(hours={}, total_hours=0, shares_percent={})
    output = tmp_path / "estudo-sem-detalhamento.pdf"

    generate_validation_pdf(data, output)

    pages = [page.extract_text() or "" for page in PdfReader(output).pages]
    weekly_page = " ".join(pages[1].split())
    assert "Detalhamento semanal das horas não disponível" in weekly_page
    assert "Detalhamento por disciplina não disponível" in weekly_page
    assert "Semana 27/2026" not in weekly_page
    assert "Ranking não disponível na captura" not in weekly_page
    assert "Não disponível" in pages[0]


def test_full_report_does_not_create_a_note_only_page(tmp_path: Path) -> None:
    data = validation_data()
    data.weekly_evolution.weeks = [
        ReportWeek(label=f"Semana {number}/2026", hours=2, target_hours=10)
        for number in range(27, 32)
    ]
    data.disciplines.ranking = [
        RankedSubject(
            rank=rank,
            name=f"Disciplina {rank}",
            study_hours=1,
            accuracy_percent=70 + rank,
        )
        for rank in range(1, 6)
    ]
    data.disciplines.progress_percent = {
        f"Disciplina {number}": 10 if number == 1 else 0 for number in range(1, 17)
    }
    data.modalities = ModalityOverview(
        hours={f"Modalidade {number}": 2 for number in range(1, 6)},
        total_hours=10,
        shares_percent={f"Modalidade {number}": 20 for number in range(1, 6)},
    )
    data.performance_by_area = {f"Área {number}": 70 + number for number in range(1, 7)}
    output = tmp_path / "relatorio-sem-pagina-orfa.pdf"

    generate_validation_pdf(data, output)

    pages = [page.extract_text() or "" for page in PdfReader(output).pages]
    assert len(pages) == 4
    assert "Detalhamento do período" in pages[3]


def test_enriched_report_shows_month_weeks_question_totals_and_revisions(
    tmp_path: Path,
) -> None:
    data = validation_data()
    data.weekly_evolution.weeks = [
        ReportWeek(label=f"Semana {number}/2026", hours=hours, target_hours=target)
        for number, hours, target in [
            (27, 2, 6.5),
            (28, 4.5, 11),
            (29, 3, 11),
            (30, 0.5, 11),
            (31, 0, 9),
        ]
    ]
    data.questions = QuestionMetrics(
        total=541,
        correct=442,
        wrong=99,
        accuracy_percent=81.7,
        weekly=[
            QuestionWeekMetric(
                label=f"Semana {number}/2026",
                correct=correct,
                wrong=wrong,
                total=correct + wrong,
                accuracy_percent=round(correct / (correct + wrong) * 100, 2),
            )
            for number, correct, wrong in [
                (27, 27, 11),
                (28, 83, 24),
                (29, 84, 14),
                (30, 125, 21),
                (31, 123, 29),
            ]
        ],
        disciplines=[
            QuestionDisciplineMetric(
                name="Legislação Extravagante",
                total=144,
                correct=119,
                wrong=25,
                accuracy_percent=82.64,
            ),
            QuestionDisciplineMetric(
                name="Direito Processual Penal",
                total=11,
                correct=10,
                wrong=1,
                accuracy_percent=90.91,
            ),
        ],
        topics=[],
    )
    data.student_activity = StudentActivityMetrics(
        revisions=[
            RevisionMetric(
                discipline="Contabilidade Geral",
                subject="Patrimônio",
                count=2,
            )
        ],
        activities=[
            StudyActivityMetric(
                discipline="Contabilidade Geral",
                subject="Patrimônio",
                modality="Estudo",
                hours=1.5,
            )
        ],
        total_revisions=2,
    )
    output = tmp_path / "relatorio-enriquecido.pdf"

    generate_validation_pdf(data, output)

    pages = [page.extract_text() or "" for page in PdfReader(output).pages]
    full_text = "\n".join(pages)
    assert "541" in full_text
    assert "442 acertos" in full_text
    assert "99 erros" in full_text
    assert "1ª semana" in full_text
    assert "5ª semana" in full_text
    assert "Semana 27/2026" not in full_text
    assert "Questões por semana" in full_text
    assert "Revisões realizadas" in full_text
    assert "Patrimônio" in full_text
