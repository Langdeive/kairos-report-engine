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
    DARK_TRACK,
    HEIGHT,
    LIGHT_MUTED,
    MARGIN,
    NAVY,
    PANEL_LINE,
    PANEL_NAVY,
    PANEL_NAVY_ALT,
    WHITE,
    WIDTH,
    YELLOW,
    paste_light_logo,
    rounded,
    text,
    wave_footer,
)

OUTPUT_DIR = Path(__file__).resolve().parents[2] / "output" / "layouts" / "aprovados"
OUTPUT_FILE = OUTPUT_DIR / "pagina-04-constancia-e-tempo.png"
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
PURPLE = "#7657D7"
INACTIVE_DAY = "#6F8CC8"
MODALITY_COLORS = [PURPLE, CYAN, BLUE, YELLOW]
MODALITY_ALIASES = {
    "ESTUDO": ("Estudo", "Estudo (coach)", "Estudo(coach)", "Teoria"),
    "RESUMO": ("Resumo/Mapa Mental", "Resumo"),
    "EXERCÍCIO": ("Exercício", "Questões"),
    "REVISÃO": ("Revisão",),
}


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


def report_values(data: dict[str, Any]) -> dict[str, Any]:
    period = data["identity"]["period_start"].split("-")
    raw_modalities = data["modalities"]["hours"]
    modalities: list[tuple[str, float]] = [
        (label, sum(float(raw_modalities.get(alias, 0)) for alias in aliases))
        for label, aliases in MODALITY_ALIASES.items()
    ]
    known_modalities = {alias for aliases in MODALITY_ALIASES.values() for alias in aliases}
    uncategorized_modalities_total = sum(
        float(value) for label, value in raw_modalities.items() if label not in known_modalities
    )
    categorized_modalities_total = sum(value for _, value in modalities)
    formatted_modalities = [
        (*item, format_hours(item[1]).upper(), MODALITY_COLORS[index])
        for index, item in enumerate(modalities)
    ]
    from .week_dates import group_four, interval_label

    weeks = group_four(
        data["weekly_evolution"]["weeks"], data["identity"], ("hours", "target_hours")
    )
    return {
        "student": data["identity"]["student_name"].upper(),
        "period": f"{MONTHS[int(period[1])]} {period[0]}",
        "total_hours": float(data["summary"]["total_hours"]),
        "study_days": int(data["summary"]["study_days"]),
        "inactive_days": int(data["summary"]["inactive_days"]),
        "constancy": float(data["summary"]["study_days"])
        / (int(data["summary"]["study_days"]) + int(data["summary"]["inactive_days"]))
        * 100,
        "modalities": formatted_modalities,
        "modalities_total": categorized_modalities_total,
        "reported_modalities_total": float(data["modalities"]["total_hours"]),
        "uncategorized_modalities_total": uncategorized_modalities_total,
        "week_actual": [float(week["hours"]) for week in weeks],
        "week_labels": [interval_label(week["label"], data["identity"]) for week in weeks],
        "week_target": [float(week["target_hours"]) for week in weeks],
        "adherence": data["weekly_evolution"]["adherence_percent"],
        "best_week": (
            max(range(len(weeks)), key=lambda index: float(weeks[index]["hours"])) + 1
            if weeks and any(float(week["hours"]) > 0 for week in weeks)
            else None
        ),
    }


def ring(
    draw: ImageDraw.ImageDraw,
    center: tuple[int, int],
    radius: int,
    percent: float,
    color: str,
    *,
    background: str,
    width: int,
) -> None:
    cx, cy = center
    box = (cx - radius, cy - radius, cx + radius, cy + radius)
    draw.arc(box, 0, 360, fill=background, width=width)
    if percent > 0:
        draw.arc(box, -90, -90 + 360 * percent / 100, fill=color, width=width)


def segmented_ring(
    draw: ImageDraw.ImageDraw,
    center: tuple[int, int],
    radius: int,
    modalities: list[tuple[str, float, str, str]],
) -> None:
    cx, cy = center
    box = (cx - radius, cy - radius, cx + radius, cy + radius)
    draw.arc(box, 0, 360, fill=PURPLE, width=24)
    start = -90.0
    total = sum(value for _, value, _, _ in modalities)
    if total <= 0:
        return
    gap = 3.0
    for _, value, _, color in modalities:
        if value <= 0:
            continue
        sweep = 360 * value / total
        draw.arc(box, start + gap / 2, start + sweep - gap / 2, fill=color, width=24)
        start += sweep


def header(image: Image.Image, draw: ImageDraw.ImageDraw, values: dict[str, Any]) -> None:
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
    text(draw, (MARGIN, 174), "CONSTÂNCIA E TEMPO", 58, WHITE, display=True)
    text(draw, (MARGIN, 236), "Presença, ritmo e distribuição do estudo no mês", 20, LIGHT_MUTED)
    rounded(draw, (WIDTH - 177, 172, WIDTH - MARGIN, 216), 22, YELLOW)
    text(draw, (WIDTH - 126, 194), "04", 16, NAVY, bold=True, anchor="mm")


def presence_card(draw: ImageDraw.ImageDraw, values: dict[str, Any]) -> None:
    rounded(draw, (MARGIN, 292, 474, 1030), 38, PANEL_NAVY, PANEL_LINE, 2)
    text(draw, (112, 338), "PRESENÇA NO MÊS", 17, CYAN, bold=True)
    ring(draw, (275, 525), 128, values["constancy"], CYAN, background="#34467E", width=32)
    text(
        draw,
        (275, 505),
        f"{values['constancy']:.2f}%".replace(".", ","),
        46,
        WHITE,
        bold=True,
        anchor="mm",
    )
    text(draw, (275, 554), "CONSTÂNCIA", 15, "#C8D7FF", bold=True, anchor="mm")
    days_total = values["study_days"] + values["inactive_days"]
    text(
        draw,
        (275, 587),
        f"{values['study_days']} DE {days_total} DIAS ATIVOS",
        12,
        "#8EA4DC",
        bold=True,
        anchor="mm",
    )

    rounded(draw, (100, 704, 450, 1004), 28, PANEL_NAVY_ALT, PANEL_LINE, 2)
    text(draw, (124, 738), "HORAS POR MODALIDADE", 17, WHITE, bold=True)
    if values["modalities_total"] <= 0:
        message = (
            f"{format_hours(values['uncategorized_modalities_total']).upper()} em "
            "modalidades não categorizadas."
            if values["uncategorized_modalities_total"] > 0
            else "Sem detalhamento por modalidade."
        )
        empty_states.message(draw, (100, 780, 450, 990), message)
        return
    segmented_ring(draw, (206, 842), 70, values["modalities"])
    text(
        draw,
        (206, 842),
        format_hours(values["modalities_total"]).upper(),
        35,
        WHITE,
        bold=True,
        anchor="mm",
    )
    text(draw, (206, 929), "DETALHADAS", 13, WHITE, bold=True, anchor="mm")

    legend_y = 782
    for index, (label, _, shown, color) in enumerate(values["modalities"]):
        y = legend_y + index * 42
        draw.ellipse((294, y - 6, 306, y + 6), fill=color)
        text(
            draw,
            (316, y),
            label,
            12,
            WHITE,
            bold=True,
            anchor="lm",
        )
        text(draw, (430, y), shown, 15, WHITE, bold=True, anchor="rm")
    uncategorized = values["uncategorized_modalities_total"]
    without_modality = max(0.0, values["total_hours"] - values["reported_modalities_total"])
    detail = (
        f"{format_hours(uncategorized)} NÃO CATEGORIZADAS"
        if uncategorized > 0
        else f"{format_hours(without_modality)} SEM MODALIDADE"
    )
    text(
        draw,
        (124, 976),
        f"{format_hours(values['total_hours'])} TOTAIS  •  {detail}".upper(),
        14,
        WHITE,
        bold=True,
    )


def weekly_card(draw: ImageDraw.ImageDraw, values: dict[str, Any]) -> None:
    rounded(draw, (500, 292, WIDTH - MARGIN, 1030), 38, PANEL_NAVY, PANEL_LINE, 2)
    text(draw, (544, 340), "PLANEJADO × EXECUTADO", 27, WHITE, bold=True)
    text(draw, (544, 380), "Comparação direta com a meta semanal", 16, LIGHT_MUTED)

    if not values["week_actual"] or not any(values["week_actual"]):
        empty_states.message(
            draw, (500, 400, WIDTH - MARGIN, 1030), "Sem horas com detalhamento semanal."
        )
        return

    row_top = 440
    row_gap = min(104, 400 // max(1, len(values["week_actual"]) - 1))
    track_x1, track_x2 = 674, 1020
    for index, (actual, target) in enumerate(
        zip(values["week_actual"], values["week_target"], strict=True)
    ):
        y = row_top + index * row_gap
        text(draw, (544, y), values["week_labels"][index], 16, WHITE, bold=True, anchor="lm")
        rounded(draw, (track_x1, y - 11, track_x2, y + 11), 11, DARK_TRACK)
        fill_width = round((track_x2 - track_x1) * min(1, actual / target)) if target > 0 else 0
        if fill_width:
            rounded(draw, (track_x1, y - 11, track_x1 + fill_width, y + 11), 11, CORAL)
        text(
            draw,
            (1120, y),
            (
                f"{format_hours(actual)} / {format_hours(target)}"
                if target > 0
                else f"{format_hours(actual)} / SEM META"
            ),
            15,
            WHITE,
            bold=True,
            anchor="rm",
        )

    if values["adherence"] is None:
        empty_states.message(draw, (536, 902, 1128, 1000), "Sem meta para calcular aderência.")
        return
    rounded(draw, (536, 902, 1128, 1000), 24, YELLOW)
    text(draw, (566, 932), "ADERÊNCIA ÀS METAS", 14, WHITE, bold=True)
    text(
        draw,
        (1096, 932),
        f"{values['adherence']:.2f}%".replace(".", ","),
        24,
        WHITE,
        bold=True,
        anchor="ra",
    )
    rounded(draw, (566, 960, 1096, 980), 10, "#F8D879")
    adherence = max(0.0, min(100.0, values["adherence"]))
    fill_end = 566 + round((1096 - 566) * adherence / 100)
    if fill_end > 566:
        rounded(draw, (566, 960, fill_end, 980), 10, CORAL)


def days_card(draw: ImageDraw.ImageDraw, values: dict[str, Any]) -> None:
    rounded(draw, (MARGIN, 1064, WIDTH - MARGIN, 1518), 38, WHITE, PANEL_LINE, 2)
    days_total = values["study_days"] + values["inactive_days"]
    text(draw, (112, 1110), f"CONSTÂNCIA EM {days_total} DIAS", 24, NAVY, bold=True)
    text(draw, (112, 1148), "Uma visão simples da frequência registrada no mês", 16, "#66708B")

    active_days = values["study_days"]
    start_x, start_y = 126, 1228
    gap_x, gap_y = 62, 66
    for index in range(days_total):
        row = 0 if index < 16 else 1
        col = index if row == 0 else index - 16
        x = start_x + col * gap_x
        y = start_y + row * gap_y
        fill = CYAN if index < active_days else INACTIVE_DAY
        draw.ellipse((x - 14, y - 14, x + 14, y + 14), fill=fill)

    text(
        draw,
        (112, 1390),
        f"{values['study_days']} dias com estudo registrado",
        20,
        NAVY,
        bold=True,
    )
    text(
        draw,
        (112, 1427),
        f"{values['inactive_days']} dias sem registro",
        16,
        "#66708B",
        bold=True,
    )
    rounded(draw, (838, 1374, 1128, 1448), 24, BLUE)
    text(
        draw,
        (983, 1411),
        (
            f"DESTAQUE: {values['week_labels'][values['best_week'] - 1]}"
            if values["best_week"]
            else "SEM DETALHAMENTO SEMANAL"
        ),
        16,
        WHITE,
        bold=True,
        anchor="mm",
    )
    text(
        draw,
        (112, 1484),
        "As bolinhas representam a quantidade de dias, não datas específicas.",
        13,
        "#66708B",
        bold=True,
    )


def generate(data: dict[str, Any] | None = None) -> Image.Image:
    values = report_values(data or load_report())
    image = Image.new("RGBA", (WIDTH, HEIGHT), NAVY)
    draw = ImageDraw.Draw(image)
    header(image, draw, values)
    presence_card(draw, values)
    weekly_card(draw, values)
    days_card(draw, values)
    wave_footer(draw, top=1578)
    return image


if __name__ == "__main__":
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    result = generate()
    result.convert("RGB").save(OUTPUT_FILE, quality=96, optimize=True)
    print(OUTPUT_FILE)
