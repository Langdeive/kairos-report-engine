from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from PIL import Image, ImageDraw

from . import empty_states
from .generate_panorama_variants import (
    BLUE,
    CORAL,
    CYAN,
    HEIGHT,
    LINE,
    MARGIN,
    MUTED,
    NAVY,
    PANEL_LINE,
    PANEL_NAVY,
    WHITE,
    WIDTH,
    paste_light_logo,
    rounded,
    text,
    wave_footer,
)
from .week_dates import group_four, interval_label

OUTPUT_DIR = Path(__file__).resolve().parents[2] / "output" / "layouts" / "aprovados"
OUTPUT_FILE = OUTPUT_DIR / "pagina-02-panorama-do-mes.png"
DATA_FILE = (
    Path(__file__).resolve().parents[2]
    / "output"
    / "data"
    / "aluno-05-relatorio-enriquecido-julho-2026.json"
)

MONTHS = [
    "",
    "JANEIRO",
    "FEVEREIRO",
    "MARÇO",
    "ABRIL",
    "MAIO",
    "JUNHO",
    "JULHO",
    "AGOSTO",
    "SETEMBRO",
    "OUTUBRO",
    "NOVEMBRO",
    "DEZEMBRO",
]
WEEK_LABELS = ["1ª", "2ª", "3ª", "4ª"]
PURPLE = "#7657D7"
YELLOW = "#FFB51B"
WEEK_COLORS = [BLUE] * 4


def load_report() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(DATA_FILE.read_text(encoding="utf-8")))


def format_hours(value: float) -> str:
    hours = int(value)
    minutes = round((value - hours) * 60)
    if hours and minutes:
        return f"{hours}h{minutes:02d}"
    if hours:
        return f"{hours}h"
    return f"{minutes}min" if minutes else "0h"


def consolidate_four(values: list[float]) -> list[float]:
    if len(values) <= 4:
        return values + [0.0] * (4 - len(values))
    return values[:3] + [sum(values[3:])]


def report_values(data: dict[str, Any]) -> dict[str, Any]:
    period = data["identity"]["period_start"].split("-")
    study_weeks = group_four(data["weekly_evolution"]["weeks"], data["identity"], ("hours",))
    questions = data.get("questions") or {
        "weekly": [],
        "total": 0,
        "correct": 0,
        "accuracy_percent": 0,
    }
    question_weeks = group_four(
        questions["weekly"], data["identity"], ("total", "correct", "wrong")
    )
    question_totals = [float(week["total"]) for week in question_weeks]
    question_correct = [float(week["correct"]) for week in question_weeks]
    question_wrong = [float(week["wrong"]) for week in question_weeks]
    return {
        "student": data["identity"]["student_name"].upper(),
        "period": f"{MONTHS[int(period[1])]} {period[0]}",
        "total_hours": float(data["summary"]["total_hours"]),
        "study_days": int(data["summary"]["study_days"]),
        "total_days": int(data["summary"]["study_days"]) + int(data["summary"]["inactive_days"]),
        "constancy": float(data["summary"]["study_days"])
        / (int(data["summary"]["study_days"]) + int(data["summary"]["inactive_days"]))
        * 100,
        "accuracy": float(questions["accuracy_percent"]),
        "question_total": int(questions["total"]),
        "question_correct": int(questions["correct"]),
        "questions_available": data.get("questions") is not None,
        "plan_progress": float(data["summary"]["plan_progress_percent"]),
        "week_hours": [float(week["hours"]) for week in study_weeks],
        "study_labels": [interval_label(w["label"], data["identity"]) for w in study_weeks],
        "question_labels": [interval_label(w["label"], data["identity"]) for w in question_weeks],
        "week_questions": [int(value) for value in question_totals],
        "week_correct": [int(value) for value in question_correct],
        "week_wrong": [int(value) for value in question_wrong],
    }


def metric_card(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    value: str,
    label: str,
    accent: str,
    *,
    dark: bool = False,
    fill: str = WHITE,
    value_color: str = NAVY,
) -> None:
    x1, y1, x2, y2 = box
    rounded(draw, box, 26, fill, None if dark else LINE, 2)
    draw.ellipse((x1 + 24, y1 + 22, x1 + 40, y1 + 38), fill=accent)
    text(draw, (x1 + 24, y1 + 55), value, 48, value_color, bold=True)
    text(
        draw,
        (x1 + 25, y2 - 31),
        label,
        15,
        value_color if dark else MUTED,
        bold=True,
    )


def donut(
    draw: ImageDraw.ImageDraw,
    center: tuple[int, int],
    radius: int,
    percent: float,
    color: str,
    value: str,
    detail: str,
    label: str,
    *,
    dark: bool = False,
) -> None:
    cx, cy = center
    box = (cx - radius, cy - radius, cx + radius, cy + radius)
    width = 28
    draw.arc(box, 0, 360, fill="#30457E" if dark else "#DCE7F0", width=width)
    draw.arc(box, -90, -90 + 360 * percent / 100, fill=color, width=width)
    text(draw, (cx, cy - 8), value, 34, WHITE if dark else NAVY, bold=True, anchor="mm")
    text(
        draw,
        (cx, cy + radius + 22),
        detail,
        13,
        WHITE if dark else MUTED,
        bold=True,
        anchor="mm",
    )
    text(
        draw,
        (cx, cy + radius + 56),
        label,
        16,
        WHITE if dark else BLUE,
        bold=True,
        anchor="mm",
    )


def study_line(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    values: list[float],
    labels: list[str] | None = None,
) -> None:
    x1, y1, x2, y2 = box
    chart_x1 = x1 + 430
    chart_x2 = x2 - 48
    chart_y1 = y1 + 58
    chart_y2 = y2 - 68
    points: list[tuple[int, int]] = []
    maximum = max(values) or 1
    draw.line((chart_x1, chart_y2, chart_x2, chart_y2), fill="#314076", width=2)
    for index, value in enumerate(values):
        x = round(chart_x1 + (chart_x2 - chart_x1) * index / max(1, len(values) - 1))
        y = round(chart_y2 - (chart_y2 - chart_y1) * value / maximum)
        points.append((x, y))
    if len(points) > 1:
        draw.line(points, fill=CYAN, width=7, joint="curve")
    for index, ((x, y), value) in enumerate(zip(points, values, strict=True)):
        draw.ellipse((x - 8, y - 8, x + 8, y + 8), fill=WHITE, outline=CYAN, width=4)
        label = format_hours(value)
        width = 72 if len(label) <= 3 else 92
        rounded(draw, (x - width // 2, y - 48, x + width // 2, y - 18), 15, YELLOW)
        text(draw, (x, y - 33), label, 13, NAVY, bold=True, anchor="mm")
        text(
            draw,
            (x, chart_y2 + 32),
            labels[index] if labels else f"Período {index + 1}",
            12,
            "#9FB2E8",
            bold=True,
            anchor="mm",
        )


def questions_bars(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    totals: list[int],
    *,
    dark: bool = False,
    labels: list[str] | None = None,
) -> None:
    x1, y1, x2, y2 = box
    baseline = y2 - 66
    top = y1 + 8
    maximum = max(totals) or 1
    slot = (x2 - x1) / max(1, len(totals))
    for index, volume in enumerate(totals):
        center = round(x1 + slot * (index + 0.5))
        height = round((baseline - top) * volume / maximum)
        bar_width = 84
        rounded(
            draw,
            (center - bar_width // 2, baseline - height, center + bar_width // 2, baseline),
            12,
            BLUE,
        )
        text(
            draw,
            (center, baseline + 24),
            labels[index] if labels else f"Período {index + 1}",
            13,
            "#BFD3FF" if dark else MUTED,
            bold=True,
            anchor="mm",
        )
        text(
            draw,
            (center, baseline + 54),
            f"{volume} QUESTÕES",
            15,
            WHITE if dark else NAVY,
            bold=True,
            anchor="mm",
        )


def generate(data: dict[str, Any] | None = None) -> Image.Image:
    values = report_values(data or load_report())
    image = Image.new("RGBA", (WIDTH, HEIGHT), NAVY)
    draw = ImageDraw.Draw(image)

    paste_light_logo(image, MARGIN, 54, 300)
    text(
        draw,
        (WIDTH - MARGIN, 72),
        f"{values['student']}  •  {values['period']}",
        22,
        WHITE,
        bold=True,
        anchor="ra",
    )
    text(draw, (MARGIN, 174), "PANORAMA DO MÊS", 58, WHITE, display=True)
    text(
        draw,
        (MARGIN, 236),
        "Indicadores, ritmo e questões em uma leitura direta",
        20,
        "#BFD3FF",
    )
    rounded(draw, (WIDTH - 177, 172, WIDTH - MARGIN, 216), 22, YELLOW)
    text(draw, (WIDTH - 126, 194), "02", 16, NAVY, bold=True, anchor="mm")

    card_y1, card_y2 = 306, 474
    card_width = 254
    cards = [
        (
            format_hours(values["total_hours"]) if values["total_hours"] > 0 else "-",
            "TEMPO TOTAL",
            WHITE,
            True,
            YELLOW,
            WHITE,
        ),
        (
            f"{values['study_days']}/{values['total_days']}" if values["total_hours"] > 0 else "-",
            "DIAS ATIVOS",
            WHITE,
            True,
            PURPLE,
            WHITE,
        ),
        (
            str(values["question_total"]) if values["question_total"] > 0 else "-",
            "QUESTÕES",
            WHITE,
            True,
            BLUE,
            WHITE,
        ),
        (
            f"{values['accuracy']:.1f}%".replace(".", ",") if values["question_total"] > 0 else "-",
            "TAXA DE ACERTO",
            WHITE,
            True,
            CORAL,
            WHITE,
        ),
    ]
    for index, (value, label, accent, dark, card_fill, value_color) in enumerate(cards):
        x1 = MARGIN + index * (card_width + 24)
        metric_card(
            draw,
            (x1, card_y1, x1 + card_width, card_y2),
            value,
            label,
            accent,
            dark=dark,
            fill=card_fill,
            value_color=value_color,
        )

    rounded(draw, (116, 508, 1124, 948), 34, PANEL_NAVY, PANEL_LINE, 2)
    text(
        draw,
        (WIDTH // 2, 548),
        "SEU MÊS EM DOIS MOVIMENTOS",
        19,
        WHITE,
        bold=True,
        anchor="mm",
    )
    draw.line((WIDTH // 2, 620, WIDTH // 2, 850), fill="#30457E", width=2)
    if values["total_hours"] <= 0:
        empty_states.message(draw, (140, 620, 600, 850), "Sem horas de estudo registradas.")
    else:
        donut(
            draw,
            (412, 735),
            116,
            values["constancy"],
            CYAN,
            f"{values['constancy']:.1f}%".replace(".", ","),
            f"{values['study_days']} ATIVOS  •  {values['total_days']} DIAS",
            "CONSTÂNCIA",
            dark=True,
        )
    if values["question_total"] <= 0:
        empty_states.message(
            draw,
            (640, 620, 1100, 850),
            "Sem questões respondidas."
            if values["questions_available"]
            else "Dados de questões indisponíveis.",
        )
    else:
        donut(
            draw,
            (828, 735),
            116,
            values["accuracy"],
            CORAL,
            f"{values['accuracy']:.1f}%".replace(".", ","),
            f"{values['question_correct']} ACERTOS  •  {values['question_total']} TOTAL",
            "DESEMPENHO",
            dark=True,
        )

    rounded(draw, (116, 974, 1124, 1248), 30, PANEL_NAVY, PANEL_LINE, 2)
    text(draw, (216, 1018), "RITMO   DE   ESTUDO", 19, WHITE, bold=True)
    detailed_hours = sum(values["week_hours"])
    text(draw, (216, 1060), format_hours(detailed_hours), 58, WHITE, display=True)
    text(draw, (216, 1127), "COM   DISTRIBUIÇÃO   SEMANAL", 16, WHITE, bold=True)
    text(
        draw,
        (216, 1164),
        f"{format_hours(values['total_hours'] - detailed_hours)} sem detalhamento semanal",
        17,
        WHITE,
        bold=True,
    )
    if detailed_hours > 0:
        study_line(draw, (116, 974, 1124, 1248), values["week_hours"], values["study_labels"])
    else:
        rounded(draw, (117, 1048, 1123, 1240), 24, PANEL_NAVY)
        empty_states.message(
            draw,
            (116, 1048, 1124, 1240),
            empty_states.NO_STUDY
            if values["total_hours"] <= 0
            else "Horas registradas sem detalhamento semanal disponível.",
        )

    rounded(draw, (116, 1272, 1124, 1540), 30, PANEL_NAVY, PANEL_LINE, 2)
    text(draw, (216, 1308), "QUESTÕES   REALIZADAS   POR   SEMANA", 19, WHITE, bold=True)
    if sum(values["week_questions"]) > 0:
        questions_bars(
            draw,
            (220, 1340, 1020, 1530),
            values["week_questions"],
            dark=True,
            labels=values["question_labels"],
        )

    else:
        empty_states.message(
            draw,
            (116, 1340, 1124, 1540),
            empty_states.NO_QUESTIONS
            if values["question_total"] <= 0 and values["questions_available"]
            else "Detalhamento semanal de questões não disponível.",
        )

    wave_footer(draw, top=1582)
    return image


if __name__ == "__main__":
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    result = generate()
    result.convert("RGB").save(OUTPUT_FILE, quality=96, optimize=True)
    print(OUTPUT_FILE)
