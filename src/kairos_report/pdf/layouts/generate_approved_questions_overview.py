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

PURPLE = "#7657D7"

OUTPUT_DIR = Path(__file__).resolve().parents[2] / "output" / "layouts" / "aprovados"
OUTPUT_FILE = OUTPUT_DIR / "pagina-05-panorama-de-questoes.png"
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


def load_report() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(DATA_FILE.read_text(encoding="utf-8")))


def consolidate_four(values: list[int]) -> list[int]:
    if len(values) <= 4:
        return values + [0] * (4 - len(values))
    return values[:3] + [sum(values[3:])]


def report_values(data: dict[str, Any]) -> dict[str, Any]:
    period = data["identity"]["period_start"].split("-")
    from .week_dates import group_four, interval_label

    weeks = group_four(data["questions"]["weekly"], data["identity"], ("total", "correct", "wrong"))

    totals = [int(week["total"]) for week in weeks]
    correct = [int(week["correct"]) for week in weeks]
    wrong = [int(week["wrong"]) for week in weeks]
    accuracy = [
        round(hits / total * 100, 1) if total else 0.0
        for hits, total in zip(correct, totals, strict=True)
    ]
    eligible_weeks = [index for index, total in enumerate(totals) if total > 0]
    return {
        "student": data["identity"]["student_name"].upper(),
        "period": f"{MONTHS[int(period[1])]} {period[0]}",
        "total": int(data["questions"]["total"]),
        "correct": int(data["questions"]["correct"]),
        "wrong": int(data["questions"]["wrong"]),
        "accuracy": float(data["questions"]["accuracy_percent"]),
        "weeks": [
            {
                "total": total,
                "correct": hits,
                "wrong": misses,
                "accuracy": rate,
                "label": interval_label(week["label"], data["identity"]),
            }
            for total, hits, misses, rate, week in zip(
                totals, correct, wrong, accuracy, weeks, strict=True
            )
        ],
        "best_week": (
            max(eligible_weeks, key=lambda index: accuracy[index])
            if eligible_weeks
            else None
        ),
    }


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
    text(draw, (MARGIN, 174), "PANORAMA DE QUESTÕES", 58, WHITE, display=True)
    text(draw, (MARGIN, 236), "Volume, precisão e evolução ao longo do mês", 20, LIGHT_MUTED)
    rounded(draw, (WIDTH - 177, 172, WIDTH - MARGIN, 216), 22, YELLOW)
    text(draw, (WIDTH - 126, 194), "05", 16, NAVY, bold=True, anchor="mm")


def accuracy_ring(
    draw: ImageDraw.ImageDraw,
    center: tuple[int, int],
    accuracy: float,
    *,
    dark: bool,
    radius: int = 82,
) -> None:
    cx, cy = center
    width = 22
    box = (cx - radius, cy - radius, cx + radius, cy + radius)
    draw.arc(box, 0, 360, fill=DARK_TRACK, width=width)
    draw.arc(box, -90, -90 + 360 * accuracy / 100, fill=CORAL, width=width)
    text(draw, (cx, cy), f"{accuracy:.0f}%", 31, WHITE, bold=True, anchor="mm")


def colorful_metric_card(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    value: str,
    label: str,
    fill: str,
) -> None:
    x1, y1, x2, y2 = box
    rounded(draw, box, 28, fill)
    draw.ellipse((x1 + 24, y1 + 23, x1 + 42, y1 + 41), fill=WHITE)
    text(draw, (x1 + 24, y1 + 66), value, 54, WHITE, bold=True)
    text(draw, (x1 + 24, y2 - 31), label, 15, WHITE, bold=True)


def week_card(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    index: int,
    week: dict[str, Any],
    *,
    highlighted: bool,
) -> None:
    x1, y1, x2, y2 = box
    center = (x1 + x2) // 2
    rounded(
        draw,
        box,
        32,
        PANEL_NAVY_ALT if highlighted else PANEL_NAVY,
        CYAN if highlighted else PANEL_LINE,
        3 if highlighted else 2,
    )
    text(
        draw,
        (center, y1 + 62),
        week["label"],
        25 if x2 - x1 < 200 else 32,
        CYAN if highlighted else BLUE,
        display=True,
        anchor="mm",
    )
    text(
        draw,
        (center, y1 + 105),
        "PERÍODO",
        14,
        LIGHT_MUTED,
        bold=True,
        anchor="mm",
    )
    if week["total"] == 0:
        empty_states.message(draw, (x1, y1 + 200, x2, y2 - 80), "Sem questões registradas.")
        return
    text(
        draw,
        (center, y1 + 190),
        str(week["total"]),
        63,
        WHITE,
        display=True,
        anchor="mm",
    )
    text(
        draw,
        (center, y1 + 239),
        "QUESTÕES",
        14,
        LIGHT_MUTED,
        bold=True,
        anchor="mm",
    )
    accuracy_ring(
        draw, (center, y1 + 357), week["accuracy"], dark=True, radius=min(82, (x2 - x1) // 2 - 12)
    )
    text(
        draw,
        (center, y1 + 468),
        f"{week['correct']} ACERTOS",
        17,
        WHITE,
        bold=True,
        anchor="mm",
    )
    text(
        draw,
        (center, y1 + 505),
        f"{week['wrong']} ERROS",
        15,
        LIGHT_MUTED,
        bold=True,
        anchor="mm",
    )
    if highlighted:
        rounded(draw, (x1 + 28, y2 - 66, x2 - 28, y2 - 24), 21, CYAN)
        text(draw, (center, y2 - 45), "DESTAQUE", 12, NAVY, bold=True, anchor="mm")


def generate(data: dict[str, Any] | None = None) -> Image.Image:
    values = report_values(data or load_report())
    image = Image.new("RGBA", (WIDTH, HEIGHT), NAVY)
    draw = ImageDraw.Draw(image)
    header(image, draw, values)

    metrics = [
        (str(values["total"]), "TOTAL DE QUESTÕES", BLUE),
        (str(values["correct"]), "ACERTOS", PURPLE),
        (str(values["wrong"]), "ERROS", CORAL),
        (f"{values['accuracy']:.1f}%".replace(".", ","), "TAXA DE ACERTO", YELLOW),
    ]
    card_width = 252
    for index, (value, label, accent) in enumerate(metrics):
        x = MARGIN + index * (card_width + 24)
        colorful_metric_card(draw, (x, 288, x + card_width, 460), value, label, accent)

    text(draw, (MARGIN, 516), "SUA JORNADA DE QUESTÕES", 23, WHITE, bold=True)
    text(draw, (MARGIN, 554), "Uma leitura semanal do volume e da precisão", 16, LIGHT_MUTED)
    if not any(week["total"] for week in values["weeks"]):
        empty_states.message(
            draw,
            (MARGIN, 592, WIDTH - MARGIN, 1518),
            "Detalhamento semanal de questões não disponível.",
        )
        wave_footer(draw, top=1582)
        return image
    gap = 16
    count = len(values["weeks"])
    week_width = (WIDTH - 2 * MARGIN - (count - 1) * gap) // count
    for index, week in enumerate(values["weeks"]):
        x1 = MARGIN + index * (week_width + gap)
        week_card(
            draw,
            (x1, 592, x1 + week_width, 1262),
            index,
            week,
            highlighted=index == values["best_week"],
        )

    best = values["weeks"][values["best_week"]]
    rounded(draw, (MARGIN, 1300, WIDTH - MARGIN, 1518), 36, PANEL_NAVY, PANEL_LINE, 2)
    text(draw, (116, 1346), "DESTAQUE DO MÊS", 17, CYAN, bold=True)
    text(draw, (116, 1401), best["label"], 40, WHITE, display=True)
    text(
        draw,
        (432, 1400),
        f"{best['accuracy']:.1f}% DE PRECISÃO".replace(".", ","),
        26,
        YELLOW,
        bold=True,
        anchor="lm",
    )
    text(
        draw,
        (432, 1442),
        f"{best['correct']} acertos em {best['total']} questões realizadas",
        17,
        LIGHT_MUTED,
        bold=True,
        anchor="lm",
    )

    wave_footer(draw, top=1582)
    return image


if __name__ == "__main__":
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    result = generate()
    result.convert("RGB").save(OUTPUT_FILE, quality=96, optimize=True)
    print(OUTPUT_FILE)
