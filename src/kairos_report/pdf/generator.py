from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (
    Flowable,
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from kairos_report.report_data import ReportDataPackage, ReportWeek
from kairos_report.schemas import QuestionTopicMetric, StudentActivityMetrics

NAVY = colors.HexColor("#111743")
BLUE = colors.HexColor("#263B8F")
LIGHT_BLUE = colors.HexColor("#E9EEFF")
CYAN = colors.HexColor("#5CC8E8")
GREEN = colors.HexColor("#54B689")
ORANGE = colors.HexColor("#F2A65A")
INK = colors.HexColor("#20243A")
MUTED = colors.HexColor("#68708A")
LINE = colors.HexColor("#DCE1EE")
PAPER = colors.HexColor("#F7F8FC")


def generate_validation_pdf(
    data: ReportDataPackage,
    output_path: Path,
    *,
    logo_path: Path | None = None,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=17 * mm,
        bottomMargin=17 * mm,
        title=f"Relatório mensal - {data.identity.student_name}",
        author="Kairós Mentorias",
    )
    styles = _styles()
    story: list[Flowable] = []
    if data.questions is not None or data.student_activity is not None:
        story.extend(_enriched_story(data, styles, logo_path))
        document.build(story, onFirstPage=_decorate_page, onLaterPages=_decorate_page)
        return output_path

    has_study_activity = _has_study_activity(data)
    has_question_activity = _has_question_activity(data)
    has_weekly_detail = any(week.hours > 0 for week in data.weekly_evolution.weeks)
    has_ranking_detail = any(item.study_hours > 0 for item in data.disciplines.ranking)

    if logo_path is not None and logo_path.is_file():
        story.append(Image(str(logo_path), width=52 * mm, height=13 * mm))
    else:
        story.append(Paragraph("KAIRÓS MENTORIAS", styles["brand"]))
    story.extend(
        [
            Spacer(1, 8 * mm),
            Paragraph("RELATÓRIO MENSAL DE EVOLUÇÃO", styles["eyebrow"]),
            Paragraph(data.identity.student_name, styles["hero"]),
            Paragraph(
                (
                    f"{data.identity.period_start:%d/%m/%Y} a "
                    f"{data.identity.period_end:%d/%m/%Y}  |  {data.identity.course}"
                ),
                styles["subtitle"],
            ),
        ]
    )
    if has_study_activity:
        story.extend(
            [
                Spacer(1, 9 * mm),
                _summary_cards(data, styles),
                Spacer(1, 9 * mm),
                Paragraph("Leitura rápida", styles["section"]),
                Paragraph(
                    (
                        f"Foram registrados <b>{data.summary.study_days} dias de estudo</b> "
                        "no período, com média de "
                        f"<b>{_format_hours(data.summary.average_hours_per_active_day)}</b> "
                        f"por dia ativo. O progresso informado do plano é "
                        f"<b>{_format_percent(data.summary.plan_progress_percent)}</b>."
                    ),
                    styles["body"],
                ),
                Spacer(1, 5 * mm),
                _reconciliation_notice(data, styles),
                Spacer(1, 7 * mm),
                Paragraph(
                    "PRÉVIA TÉCNICA - CONTEÚDO E CÁLCULOS EM VALIDAÇÃO",
                    styles["stamp"],
                ),
                PageBreak(),
                Paragraph("Evolução semanal", styles["page_title"]),
                Paragraph(
                    "Comparação entre o tempo registrado e a meta disponível na Tutory.",
                    styles["subtitle"],
                ),
                Spacer(1, 6 * mm),
            ]
        )
        if has_weekly_detail:
            story.extend(
                [
                    _weekly_chart(data.weekly_evolution.weeks),
                    Spacer(1, 5 * mm),
                    _weekly_table(data, styles),
                ]
            )
        else:
            story.append(
                Paragraph(
                    (
                        "<b>Detalhamento semanal das horas não disponível.</b><br/>"
                        "A Tutory informou o total do período, mas não distribuiu as horas "
                        "entre as semanas."
                    ),
                    styles["note"],
                )
            )
        story.extend(
            [
                Spacer(1, 5 * mm),
                Paragraph("Disciplinas", styles["section"]),
                Spacer(1, 2 * mm),
            ]
        )
        if has_ranking_detail:
            story.extend(
                [
                    _discipline_summary(data, styles),
                    Spacer(1, 1 * mm),
                    _ranking_table(data, styles),
                ]
            )
        else:
            story.append(
                Paragraph(
                    (
                        "<b>Detalhamento por disciplina não disponível.</b><br/>"
                        "Nenhuma distribuição das horas por disciplina foi fornecida."
                    ),
                    styles["note"],
                )
            )
        if data.disciplines.progress_percent:
            story.extend(
                [
                    PageBreak(),
                    Paragraph("Progresso por disciplina", styles["page_title"]),
                    Paragraph(
                        "Percentual de avanço informado pela Tutory para cada disciplina.",
                        styles["subtitle"],
                    ),
                    Spacer(1, 7 * mm),
                    _subject_progress_table(data, styles),
                ]
            )
    else:
        story.extend(
            [
                Spacer(1, 18 * mm),
                Paragraph(
                    "Sem horas de estudo registradas no período",
                    styles["page_title"],
                ),
                Paragraph(
                    (
                        "A Tutory não registrou horas, dias ou modalidades de estudo para "
                        "este aluno neste mês. Por isso, os gráficos de evolução e as tabelas "
                        "de estudo não são exibidos."
                    ),
                    styles["body"],
                ),
                Spacer(1, 10 * mm),
                Paragraph(
                    "PRÉVIA TÉCNICA - CONTEÚDO E CÁLCULOS EM VALIDAÇÃO",
                    styles["stamp"],
                ),
            ]
        )

    story.extend(
        [
            PageBreak(),
            Paragraph("Detalhamento do período", styles["page_title"]),
            Paragraph(
                "Cada bloco abaixo aparece somente quando a Tutory fornece dados reais.",
                styles["subtitle"],
            ),
            Spacer(1, 7 * mm),
        ]
    )
    if has_study_activity:
        story.extend(
            [
                Paragraph("Modalidades de estudo", styles["section"]),
                Spacer(1, 2 * mm),
                (
                    _modality_table(data, styles)
                    if data.modalities.hours
                    else Paragraph(
                        "A distribuição das horas por modalidade não está disponível.",
                        styles["note"],
                    )
                ),
                Spacer(1, 8 * mm),
            ]
        )
    if has_question_activity:
        story.extend(
            [
                Paragraph("Desempenho em questões", styles["section"]),
                Spacer(1, 2 * mm),
                _question_summary(data, styles),
                Spacer(1, 6 * mm),
            ]
        )
        if data.performance_by_area:
            story.extend(
                [
                    Paragraph("Desempenho por área", styles["section"]),
                    _performance_table(data, styles),
                    Spacer(1, 7 * mm),
                ]
            )
        question_ranking = [
            item for item in data.disciplines.ranking if item.accuracy_percent is not None
        ]
        if question_ranking and not data.performance_by_area:
            story.extend(
                [
                    Paragraph("Acertos por disciplina", styles["section"]),
                    _question_ranking_table(data, styles),
                    Spacer(1, 7 * mm),
                ]
            )
    else:
        story.extend(
            [
                Paragraph("Questões", styles["section"]),
                Spacer(1, 2 * mm),
                Paragraph(
                    (
                        "<b>Nenhuma questão respondida no período.</b><br/>"
                        "A Tutory não forneceu acertos ou desempenho por área para este mês."
                    ),
                    styles["note"],
                ),
                Spacer(1, 8 * mm),
            ]
        )
    if has_study_activity or has_question_activity:
        story.extend(
            [
                Paragraph("Dados indisponíveis", styles["section"]),
                _unavailable_list(data, styles),
            ]
        )
    document.build(story, onFirstPage=_decorate_page, onLaterPages=_decorate_page)
    return output_path


def _enriched_story(
    data: ReportDataPackage,
    styles: dict[str, ParagraphStyle],
    logo_path: Path | None,
) -> list[Flowable]:
    questions = data.questions
    activity = data.student_activity
    period_days = data.summary.study_days + data.summary.inactive_days
    constancy = data.summary.study_days / period_days * 100 if period_days > 0 else 0
    localized_study_weeks = [
        week.model_copy(update={"label": _month_week_label(data, index)})
        for index, week in enumerate(data.weekly_evolution.weeks)
    ]
    story: list[Flowable] = []
    if logo_path is not None and logo_path.is_file():
        story.append(Image(str(logo_path), width=52 * mm, height=13 * mm))
    else:
        story.append(Paragraph("KAIRÓS MENTORIAS", styles["brand"]))
    story.extend(
        [
            Spacer(1, 7 * mm),
            Paragraph("RELATÓRIO MENSAL DE EVOLUÇÃO", styles["eyebrow"]),
            Paragraph(data.identity.student_name, styles["hero"]),
            Paragraph(
                (
                    f"{data.identity.period_start:%d/%m/%Y} a "
                    f"{data.identity.period_end:%d/%m/%Y}  |  {data.identity.course}"
                ),
                styles["subtitle"],
            ),
            Spacer(1, 8 * mm),
            _overview_grid(data, constancy, styles),
            Spacer(1, 8 * mm),
            Paragraph("Seu mês em uma frase", styles["section"]),
            Paragraph(
                _monthly_story(data, constancy),
                styles["body"],
            ),
            Spacer(1, 6 * mm),
            _reconciliation_notice(data, styles),
            Spacer(1, 7 * mm),
            Paragraph(
                "PRÉVIA TÉCNICA - CONTEÚDO E CÁLCULOS EM VALIDAÇÃO",
                styles["stamp"],
            ),
            PageBreak(),
            Paragraph("Constância e horas de estudo", styles["page_title"]),
            Paragraph(
                (
                    f"A aluna esteve ativa em {data.summary.study_days} de {period_days} dias "
                    f"({_format_percent(constancy)} de constância)."
                ),
                styles["subtitle"],
            ),
            Spacer(1, 6 * mm),
            _weekly_chart(localized_study_weeks),
            Spacer(1, 4 * mm),
            _weekly_table_for_weeks(localized_study_weeks, styles),
            Spacer(1, 6 * mm),
            Paragraph("Tempo por modalidade", styles["section"]),
            _modality_table(data, styles),
            PageBreak(),
            Paragraph("Questões do mês", styles["page_title"]),
        ]
    )
    if questions is None or questions.total == 0:
        story.append(Paragraph("Nenhuma questão respondida no período.", styles["note"]))
    else:
        story.extend(
            [
                Paragraph(
                    (
                        f"<b>{questions.total} questões</b> respondidas: "
                        f"<b>{questions.correct} acertos</b> e "
                        f"<b>{questions.wrong} erros</b>, com "
                        f"<b>{_format_percent(questions.accuracy_percent)}</b> de aproveitamento."
                    ),
                    styles["body"],
                ),
                Spacer(1, 6 * mm),
                Paragraph("Questões por semana", styles["section"]),
                _question_weekly_table(data, styles),
                Spacer(1, 7 * mm),
                Paragraph("Volume e acerto por disciplina", styles["section"]),
                _question_discipline_table(data, styles),
            ]
        )
    story.extend(
        [
            PageBreak(),
            Paragraph("Evolução por disciplina", styles["page_title"]),
            Paragraph(
                "Destaques e pontos de atenção a partir das questões respondidas no mês.",
                styles["subtitle"],
            ),
            Spacer(1, 6 * mm),
        ]
    )
    if questions is not None and questions.topics:
        story.extend(
            [
                _topic_highlights_table(questions.topics, styles),
                Spacer(1, 7 * mm),
            ]
        )
    if data.disciplines.ranking:
        story.extend(
            [
                Paragraph("Disciplinas com tempo registrado", styles["section"]),
                _ranking_table(data, styles),
            ]
        )
    story.extend(
        [
            PageBreak(),
            Paragraph("Plano e revisões", styles["page_title"]),
            Paragraph(
                "Acompanhamento do avanço do plano e do conteúdo revisado no período.",
                styles["subtitle"],
            ),
            Spacer(1, 6 * mm),
            _plan_cards(data, styles),
            Spacer(1, 7 * mm),
            Paragraph("Revisões realizadas", styles["section"]),
            _revision_table(activity, styles),
            Spacer(1, 7 * mm),
            Paragraph("Como interpretar", styles["section"]),
            Paragraph(
                (
                    "A aderência compara as horas registradas nas semanas com as metas "
                    "planejadas. O progresso geral é o percentual informado pela própria "
                    "Tutory para o plano completo; por isso, os dois indicadores medem "
                    "coisas diferentes."
                ),
                styles["note"],
            ),
        ]
    )
    return story


def _overview_grid(
    data: ReportDataPackage,
    constancy: float,
    styles: dict[str, ParagraphStyle],
) -> Table:
    questions = data.questions
    items = [
        ("TEMPO TOTAL", _format_hours(data.summary.total_hours), CYAN),
        (
            "DIAS ATIVOS",
            f"{data.summary.study_days}/{data.summary.study_days + data.summary.inactive_days}",
            GREEN,
        ),
        ("CONSTÂNCIA", _format_percent(constancy), ORANGE),
        ("QUESTÕES", str(questions.total) if questions else "—", BLUE),
        (
            "TAXA DE ACERTO",
            _format_percent(questions.accuracy_percent) if questions else "—",
            GREEN,
        ),
        ("PROGRESSO DO PLANO", _format_percent(data.summary.plan_progress_percent), BLUE),
    ]
    rows: list[list[object]] = []
    for offset in (0, 3):
        labels: list[object] = [
            Paragraph(items[index][0], styles["small"]) for index in range(offset, offset + 3)
        ]
        values: list[object] = [
            Paragraph(
                items[index][1],
                ParagraphStyle(
                    f"overview-{index}",
                    parent=styles["body"],
                    fontName="Helvetica-Bold",
                    fontSize=22,
                    leading=26,
                    textColor=items[index][2],
                    alignment=TA_CENTER,
                ),
            )
            for index in range(offset, offset + 3)
        ]
        rows.extend([labels, values])
    table = Table(rows, colWidths=[54.7 * mm] * 3, rowHeights=[8 * mm, 16 * mm] * 2)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PAPER),
                ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ]
        )
    )
    return table


def _monthly_story(data: ReportDataPackage, constancy: float) -> str:
    question_text = ""
    if data.questions is not None:
        question_text = (
            f" e respondeu <b>{data.questions.total} questões</b> com "
            f"<b>{_format_percent(data.questions.accuracy_percent)}</b> de acerto"
        )
    return (
        f"Foram <b>{_format_hours(data.summary.total_hours)}</b> registradas em "
        f"<b>{data.summary.study_days} dias ativos</b>, alcançando "
        f"<b>{_format_percent(constancy)}</b> de constância{question_text}."
    )


def _month_week_label(data: ReportDataPackage, index: int) -> str:
    start = data.identity.period_start
    end = data.identity.period_end
    raw_weeks = data.weekly_evolution.weeks
    if not raw_weeks:
        return f"{index + 1}ª semana"
    boundaries = []
    cursor = start
    while cursor <= end:
        days_until_sunday = 6 - cursor.weekday()
        boundary_end = min(end, cursor + timedelta(days=days_until_sunday))
        boundaries.append((cursor, boundary_end))
        cursor = boundary_end + timedelta(days=1)
    if index >= len(boundaries):
        return f"{index + 1}ª semana"
    week_start, week_end = boundaries[index]
    return f"{index + 1}ª semana ({week_start:%d/%m} a {week_end:%d/%m})"


def _weekly_table_for_weeks(weeks: list[ReportWeek], styles: dict[str, ParagraphStyle]) -> Table:
    rows: list[list[object]] = [["Semana do mês", "Estudado", "Meta", "Aderência"]]
    for week in weeks:
        adherence = week.hours / week.target_hours * 100 if week.target_hours else None
        rows.append(
            [
                Paragraph(week.label, styles["table"]),
                _format_hours(week.hours),
                _format_hours(week.target_hours),
                _format_percent(adherence) if adherence is not None else "—",
            ]
        )
    table = Table(rows, colWidths=[72 * mm, 30 * mm, 30 * mm, 32 * mm])
    table.setStyle(_table_style())
    return table


def _question_weekly_table(data: ReportDataPackage, styles: dict[str, ParagraphStyle]) -> Table:
    rows: list[list[object]] = [["Semana do mês", "Questões", "Acertos", "Erros", "Taxa"]]
    if data.questions is not None:
        for index, week in enumerate(data.questions.weekly):
            rows.append(
                [
                    Paragraph(_month_week_label(data, index), styles["table"]),
                    str(week.total),
                    str(week.correct),
                    str(week.wrong),
                    _format_percent(week.accuracy_percent),
                ]
            )
    table = Table(rows, colWidths=[64 * mm, 25 * mm, 25 * mm, 22 * mm, 28 * mm])
    table.setStyle(_table_style())
    return table


def _question_discipline_table(data: ReportDataPackage, styles: dict[str, ParagraphStyle]) -> Table:
    rows: list[list[object]] = [["Disciplina", "Questões", "Acertos", "Erros", "Taxa"]]
    disciplines = sorted(
        data.questions.disciplines if data.questions else [],
        key=lambda item: item.total,
        reverse=True,
    )[:9]
    for item in disciplines:
        rows.append(
            [
                Paragraph(item.name, styles["table"]),
                str(item.total),
                str(item.correct),
                str(item.wrong),
                _format_percent(item.accuracy_percent),
            ]
        )
    table = Table(rows, colWidths=[84 * mm, 21 * mm, 21 * mm, 18 * mm, 20 * mm])
    table.setStyle(_table_style())
    return table


def _topic_highlights_table(
    topics: list[QuestionTopicMetric], styles: dict[str, ParagraphStyle]
) -> Table:
    ordered = sorted(topics, key=lambda item: item.accuracy_percent, reverse=True)
    selected = ordered[:4] + list(reversed(ordered[-4:]))
    unique: list[QuestionTopicMetric] = []
    seen: set[tuple[str, str]] = set()
    for item in selected:
        key = (item.discipline, item.topic)
        if key not in seen:
            seen.add(key)
            unique.append(item)
    rows: list[list[object]] = [["Leitura", "Disciplina e assunto", "Taxa"]]
    for index, item in enumerate(unique):
        label = "Destaque" if index < min(4, len(ordered)) else "Atenção"
        rows.append(
            [
                label,
                Paragraph(f"<b>{item.discipline}</b><br/>{item.topic}", styles["table"]),
                _format_percent(item.accuracy_percent),
            ]
        )
    table = Table(rows, colWidths=[25 * mm, 114 * mm, 25 * mm], repeatRows=1)
    table.setStyle(_table_style())
    return table


def _plan_cards(data: ReportDataPackage, styles: dict[str, ParagraphStyle]) -> Table:
    adherence = data.weekly_evolution.adherence_percent
    values = [
        ("PROGRESSO GERAL", _format_percent(data.summary.plan_progress_percent)),
        ("ADERÊNCIA ÀS METAS", _format_percent(adherence) if adherence is not None else "—"),
        ("META TOTAL", _format_hours(data.weekly_evolution.total_target_hours)),
    ]
    table = Table(
        [
            [Paragraph(label, styles["small"]) for label, _ in values],
            [
                Paragraph(
                    value,
                    ParagraphStyle(
                        f"plan-{index}",
                        parent=styles["body"],
                        fontName="Helvetica-Bold",
                        fontSize=20,
                        leading=24,
                        textColor=(BLUE, GREEN, ORANGE)[index],
                        alignment=TA_CENTER,
                    ),
                )
                for index, (_, value) in enumerate(values)
            ],
        ],
        colWidths=[54.7 * mm] * 3,
        rowHeights=[9 * mm, 17 * mm],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PAPER),
                ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    return table


def _revision_table(
    activity: StudentActivityMetrics | None,
    styles: dict[str, ParagraphStyle],
) -> Table | Paragraph:
    if activity is None or not activity.revisions:
        return Paragraph("Nenhuma revisão registrada no período.", styles["note"])
    rows: list[list[object]] = [["Disciplina", "Assunto", "Revisões"]]
    for item in activity.revisions:
        rows.append(
            [
                Paragraph(item.discipline, styles["table"]),
                Paragraph(item.subject, styles["table"]),
                str(item.count),
            ]
        )
    table = Table(rows, colWidths=[55 * mm, 89 * mm, 20 * mm], repeatRows=1)
    table.setStyle(_table_style())
    return table


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "brand": ParagraphStyle(
            "brand", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=14, textColor=NAVY
        ),
        "eyebrow": ParagraphStyle(
            "eyebrow",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=12,
            tracking=1.5,
            textColor=BLUE,
        ),
        "hero": ParagraphStyle(
            "hero",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=30,
            leading=34,
            textColor=NAVY,
            spaceBefore=5,
            spaceAfter=4,
        ),
        "page_title": ParagraphStyle(
            "page_title",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=23,
            leading=28,
            textColor=NAVY,
            spaceAfter=5,
        ),
        "subtitle": ParagraphStyle(
            "subtitle", parent=base["Normal"], fontSize=9.5, leading=14, textColor=MUTED
        ),
        "section": ParagraphStyle(
            "section",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=18,
            textColor=NAVY,
            spaceAfter=5,
        ),
        "body": ParagraphStyle(
            "body", parent=base["BodyText"], fontSize=10, leading=15, textColor=INK
        ),
        "note": ParagraphStyle(
            "note",
            parent=base["BodyText"],
            fontSize=9,
            leading=14,
            textColor=INK,
            backColor=LIGHT_BLUE,
            borderColor=BLUE,
            borderWidth=0.7,
            borderPadding=9,
        ),
        "warning": ParagraphStyle(
            "warning",
            parent=base["BodyText"],
            fontSize=9,
            leading=14,
            textColor=INK,
            backColor=colors.HexColor("#FFF4E8"),
            borderColor=ORANGE,
            borderWidth=0.7,
            borderPadding=9,
        ),
        "stamp": ParagraphStyle(
            "stamp",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=11,
            alignment=TA_CENTER,
            textColor=BLUE,
            borderColor=BLUE,
            borderWidth=0.7,
            borderPadding=6,
        ),
        "table": ParagraphStyle(
            "table", parent=base["Normal"], fontSize=8.5, leading=11, textColor=INK
        ),
        "small": ParagraphStyle(
            "small", parent=base["Normal"], fontSize=8, leading=11, textColor=MUTED
        ),
    }


def _has_study_activity(data: ReportDataPackage) -> bool:
    return any(
        (
            data.summary.total_hours > 0,
            data.summary.study_days > 0,
            any(week.hours > 0 for week in data.weekly_evolution.weeks),
            any(hours > 0 for hours in data.modalities.hours.values()),
            any(item.study_hours > 0 for item in data.disciplines.ranking),
        )
    )


def _has_question_activity(data: ReportDataPackage) -> bool:
    return any(
        (
            data.summary.accuracy_percent > 0,
            bool(data.performance_by_area),
            any(item.accuracy_percent is not None for item in data.disciplines.ranking),
        )
    )


def _summary_cards(data: ReportDataPackage, styles: dict[str, ParagraphStyle]) -> Table:
    average_value = (
        _format_hours(data.summary.average_hours_per_active_day)
        if data.summary.average_hours_per_active_day > 0
        else "Não disponível"
    )
    values = [
        ("TEMPO TOTAL", _format_hours(data.summary.total_hours), CYAN),
        ("DIAS DE ESTUDO", str(data.summary.study_days), GREEN),
        ("MÉDIA POR DIA", average_value, ORANGE),
        ("PROGRESSO DO PLANO", _format_percent(data.summary.plan_progress_percent), BLUE),
    ]
    labels = []
    numbers = []
    for label, value, color in values:
        labels.append(Paragraph(label, styles["small"]))
        font_size = 11 if value == "Não disponível" else 18
        leading = 14 if value == "Não disponível" else 22
        numbers.append(
            Paragraph(
                value,
                ParagraphStyle(
                    f"value-{label}",
                    parent=styles["body"],
                    fontName="Helvetica-Bold",
                    fontSize=font_size,
                    leading=leading,
                    textColor=color,
                    alignment=TA_CENTER,
                ),
            )
        )
    table = Table([labels, numbers], colWidths=[41 * mm] * 4, rowHeights=[11 * mm, 16 * mm])
    table.setStyle(
        TableStyle(
            [
                ("SPAN", (0, 0), (0, 0)),
                ("BACKGROUND", (0, 0), (-1, -1), PAPER),
                ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _question_summary(data: ReportDataPackage, styles: dict[str, ParagraphStyle]) -> Table:
    label = Paragraph("ACERTOS GERAIS", styles["small"])
    value = Paragraph(
        _format_percent(data.summary.accuracy_percent),
        ParagraphStyle(
            "question-accuracy",
            parent=styles["body"],
            fontName="Helvetica-Bold",
            fontSize=24,
            leading=28,
            textColor=BLUE,
            alignment=TA_CENTER,
        ),
    )
    table = Table([[label], [value]], colWidths=[164 * mm], rowHeights=[9 * mm, 15 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PAPER),
                ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    return table


def _reconciliation_notice(data: ReportDataPackage, styles: dict[str, ParagraphStyle]) -> Paragraph:
    weekly_total = round(sum(week.hours for week in data.weekly_evolution.weeks), 2)
    difference = round(data.summary.total_hours - weekly_total, 2)
    if abs(difference) <= 0.1:
        return Paragraph(
            "<b>Conferência:</b> o total mensal coincide com a soma semanal recuperada.",
            styles["note"],
        )
    return Paragraph(
        (
            "<b>Atenção de validação:</b> o total exibido pela Tutory "
            f"({_format_hours(data.summary.total_hours)}) não coincide com a soma semanal "
            f"recuperada ({_format_hours(weekly_total)}). A diferença de "
            f"{_format_hours(abs(difference))} deve ser investigada antes do envio ao aluno."
        ),
        styles["warning"],
    )


def _weekly_chart(weeks: list[ReportWeek]) -> Drawing:
    width = 470
    height = max(95, 42 + len(weeks) * 34)
    drawing = Drawing(width, height)
    if not weeks:
        drawing.add(String(0, height - 20, "Sem dados semanais disponíveis", fillColor=MUTED))
        return drawing
    max_value = max(max(week.hours, week.target_hours) for week in weeks) or 1
    for index, week in enumerate(weeks):
        y = height - 30 - index * 34
        label = _truncate(week.label, 28)
        drawing.add(String(0, y + 9, label, fontName="Helvetica", fontSize=8, fillColor=INK))
        drawing.add(_bar_rect(150, y, 280, 8, colors.HexColor("#E4E7F0")))
        drawing.add(
            _bar_rect(
                150,
                y,
                280 * min(week.target_hours / max_value, 1),
                8,
                colors.HexColor("#C9D1F5"),
            )
        )
        drawing.add(
            _bar_rect(
                150,
                y,
                280 * min(week.hours / max_value, 1),
                8,
                BLUE,
            )
        )
        drawing.add(
            String(
                438,
                y,
                _format_hours(week.hours),
                fontName="Helvetica-Bold",
                fontSize=8,
                fillColor=NAVY,
            )
        )
    return drawing


def _bar_rect(x: float, y: float, width: float, height: float, color: colors.Color) -> Rect:
    rectangle = Rect(x, y, width, height)
    rectangle.fillColor = color
    rectangle.strokeColor = None
    return rectangle


def _weekly_table(data: ReportDataPackage, styles: dict[str, ParagraphStyle]) -> Table:
    rows: list[list[object]] = [["Período", "Estudado", "Meta", "Aderência"]]
    for week in data.weekly_evolution.weeks:
        adherence = week.hours / week.target_hours * 100 if week.target_hours > 0 else None
        rows.append(
            [
                Paragraph(week.label, styles["table"]),
                _format_hours(week.hours),
                _format_hours(week.target_hours),
                _format_percent(adherence) if adherence is not None else "Não disponível",
            ]
        )
    if len(rows) == 1:
        rows.append(["Sem dados", "-", "-", "-"])
    table = Table(rows, colWidths=[72 * mm, 30 * mm, 30 * mm, 32 * mm])
    table.setStyle(_table_style())
    return table


def _discipline_summary(data: ReportDataPackage, styles: dict[str, ParagraphStyle]) -> Table:
    rows = [
        [Paragraph("Mais estudada", styles["small"]), Paragraph("Menos estudada", styles["small"])],
        [
            Paragraph(data.disciplines.most_studied, styles["body"]),
            Paragraph(data.disciplines.least_studied, styles["body"]),
        ],
    ]
    table = Table(rows, colWidths=[82 * mm, 82 * mm], rowHeights=[8 * mm, 14 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PAPER),
                ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return table


def _ranking_table(data: ReportDataPackage, styles: dict[str, ParagraphStyle]) -> Table:
    rows: list[list[object]] = [["#", "Disciplina", "Tempo", "Acertos"]]
    for item in data.disciplines.ranking:
        rows.append(
            [
                str(item.rank),
                Paragraph(item.name, styles["table"]),
                _format_hours(item.study_hours),
                (
                    _format_percent(item.accuracy_percent)
                    if item.accuracy_percent is not None
                    else "Não disponível"
                ),
            ]
        )
    if len(rows) == 1:
        rows.append(["-", "Ranking não disponível na captura", "-", "-"])
    table = Table(rows, colWidths=[12 * mm, 88 * mm, 30 * mm, 34 * mm])
    table.setStyle(_table_style())
    return table


def _subject_progress_table(data: ReportDataPackage, styles: dict[str, ParagraphStyle]) -> Table:
    rows: list[list[object]] = [["Disciplina", "Progresso"]]
    for name, value in data.disciplines.progress_percent.items():
        rows.append([Paragraph(name, styles["table"]), _format_percent(value)])
    table = Table(rows, colWidths=[124 * mm, 40 * mm], repeatRows=1)
    table.setStyle(_table_style())
    return table


def _modality_table(data: ReportDataPackage, styles: dict[str, ParagraphStyle]) -> Table:
    rows: list[list[object]] = [["Modalidade", "Tempo", "Participação"]]
    for name, hours in data.modalities.hours.items():
        rows.append(
            [
                Paragraph(name, styles["table"]),
                _format_hours(hours),
                _format_percent(data.modalities.shares_percent.get(name, 0)),
            ]
        )
    if len(rows) == 1:
        rows.append(["Sem dados", "-", "-"])
    table = Table(rows, colWidths=[94 * mm, 34 * mm, 36 * mm])
    table.setStyle(_table_style())
    return table


def _performance_table(data: ReportDataPackage, styles: dict[str, ParagraphStyle]) -> Table:
    rows: list[list[object]] = [["Área", "Desempenho"]]
    for area, value in data.performance_by_area.items():
        rows.append([Paragraph(area, styles["table"]), _format_percent(value)])
    if len(rows) == 1:
        rows.append(["Desempenho por área não disponível na captura", "-"])
    table = Table(rows, colWidths=[124 * mm, 40 * mm])
    table.setStyle(_table_style())
    return table


def _question_ranking_table(data: ReportDataPackage, styles: dict[str, ParagraphStyle]) -> Table:
    rows: list[list[object]] = [["Disciplina", "Acertos"]]
    for item in data.disciplines.ranking:
        if item.accuracy_percent is None:
            continue
        rows.append(
            [
                Paragraph(item.name, styles["table"]),
                _format_percent(item.accuracy_percent),
            ]
        )
    table = Table(rows, colWidths=[124 * mm, 40 * mm], repeatRows=1)
    table.setStyle(_table_style())
    return table


def _unavailable_list(data: ReportDataPackage, styles: dict[str, ParagraphStyle]) -> Paragraph:
    labels = {
        "active_days_by_week": "dias ativos por semana",
        "accuracy_by_week": "percentual de acertos por semana",
        "most_improved_subject": "disciplina com maior evolução",
        "weekly_total_reconciliation": "conciliação entre total mensal e soma semanal",
        "course_name": "nome do curso",
        "ranking_subject_details": "nomes e valores das disciplinas do ranking",
        "subject_progress_details": "detalhamento do progresso das 18 disciplinas registradas",
        "modality_label": "nome da modalidade registrada",
        "performance_by_area": "desempenho por área",
    }
    items = [labels.get(metric, metric.replace("_", " ")) for metric in data.unavailable_metrics]
    if not items:
        return Paragraph("Nenhuma indisponibilidade registrada.", styles["body"])
    return Paragraph("<br/>".join(f"• {item}" for item in items), styles["body"])


def _table_style() -> TableStyle:
    return TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("BACKGROUND", (0, 1), (-1, -1), colors.white),
            ("TEXTCOLOR", (0, 1), (-1, -1), INK),
            ("BOX", (0, 0), (-1, -1), 0.5, LINE),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]
    )


def _decorate_page(canvas: object, document: object) -> None:
    page_width, page_height = A4
    canvas.saveState()  # type: ignore[attr-defined]
    canvas.setFillColor(NAVY)  # type: ignore[attr-defined]
    canvas.rect(0, page_height - 5 * mm, page_width, 5 * mm, stroke=0, fill=1)  # type: ignore[attr-defined]
    canvas.setStrokeColor(LINE)  # type: ignore[attr-defined]
    canvas.line(18 * mm, 12 * mm, page_width - 18 * mm, 12 * mm)  # type: ignore[attr-defined]
    footer = f"Kairós Mentorias  |  Prévia técnica  |  Página {document.page}"  # type: ignore[attr-defined]
    canvas.setFont("Helvetica", 7.5)  # type: ignore[attr-defined]
    canvas.setFillColor(MUTED)  # type: ignore[attr-defined]
    canvas.drawString(18 * mm, 7.5 * mm, footer)  # type: ignore[attr-defined]
    canvas.restoreState()  # type: ignore[attr-defined]


def _format_hours(value: float) -> str:
    total_minutes = round(value * 60)
    hours, minutes = divmod(total_minutes, 60)
    if minutes == 0:
        return f"{hours}h"
    return f"{hours}h {minutes:02d}min"


def _format_percent(value: float) -> str:
    if float(value).is_integer():
        return f"{int(value)}%"
    return f"{value:.2f}".rstrip("0").rstrip(".").replace(".", ",") + "%"


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    shortened = value[: limit - 1].rstrip() + "…"
    while stringWidth(shortened, "Helvetica", 8) > 145 and len(shortened) > 2:
        shortened = shortened[:-2].rstrip() + "…"
    return shortened
