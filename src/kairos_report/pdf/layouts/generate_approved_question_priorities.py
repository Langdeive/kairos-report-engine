from __future__ import annotations

import json
import re
import textwrap
from pathlib import Path
from typing import Any, cast

from PIL import Image, ImageDraw

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
    font,
    paste_light_logo,
    rounded,
    text,
    wave_footer,
)

OUTPUT_DIR = Path(__file__).resolve().parents[2] / "output" / "layouts" / "aprovados"
OUTPUT_FILE = OUTPUT_DIR / "pagina-06-prioridades-de-evolucao.png"
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
ACCENTS = [CORAL, "#FFB51B", BLUE]
MIN_QUESTIONS = 10


def load_report() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(DATA_FILE.read_text(encoding="utf-8")))


def normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def display_discipline(value: str) -> str:
    name = re.sub(r"\s*\(Mentoria\)\s*", "", value, flags=re.IGNORECASE)
    name = re.sub(r"\s*\(COMPLETO\)\s*", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s*-\s*Área Policial(?:\s*-\s*PC BA)?\s*", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s+", " ", name).strip()
    return name.replace(" - Parte", " — Parte")


def topic_lines(value: str, *, width: int = 57) -> list[str]:
    cleaned = re.sub(r"\s+", " ", value).strip()
    lines = textwrap.wrap(cleaned, width=width, break_long_words=False, break_on_hyphens=False)
    if len(lines) <= 2:
        return lines
    second = lines[1]
    if len(second) > width - 1:
        second = second[: width - 1]
    return [lines[0], second.rstrip(" ,;:.") + "…"]


def report_values(data: dict[str, Any]) -> dict[str, Any]:
    period = data["identity"]["period_start"].split("-")
    topics = data["questions"]["topics"]
    disciplines = [
        item for item in data["questions"]["disciplines"] if int(item["total"]) >= MIN_QUESTIONS
    ]
    priorities = sorted(
        disciplines, key=lambda item: (float(item["accuracy_percent"]), -int(item["total"]))
    )[:3]
    enriched = []
    for discipline in priorities:
        matching_topics = [
            topic
            for topic in topics
            if normalized(topic["discipline"]) == normalized(discipline["name"])
        ]
        enriched.append(
            {
                **discipline,
                "display_name": display_discipline(discipline["name"]),
                "topics": sorted(matching_topics, key=lambda item: float(item["accuracy_percent"]))[
                    :3
                ],
            }
        )
    return {
        "student": data["identity"]["student_name"].upper(),
        "period": f"{MONTHS[int(period[1])]} {period[0]}",
        "priorities": enriched,
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
    text(
        draw,
        (MARGIN, 174),
        "AS TRÊS DISCIPLINAS COM PIOR DESEMPENHO",
        43,
        WHITE,
        display=True,
    )
    title_font = font(43, display=True)
    for prefix, word in [("AS ", "TRÊS"), ("AS TRÊS DISCIPLINAS COM ", "PIOR")]:
        left = MARGIN + draw.textlength(prefix, font=title_font)
        right = MARGIN + draw.textlength(prefix + word, font=title_font)
        draw.line((left, 218, right, 218), fill=YELLOW, width=4)
    text(draw, (MARGIN, 228), "Disciplinas e assuntos que merecem mais atenção", 20, LIGHT_MUTED)
    rounded(draw, (WIDTH - 177, 172, WIDTH - MARGIN, 216), 22, YELLOW)
    text(draw, (WIDTH - 126, 194), "06", 16, NAVY, bold=True, anchor="mm")


def multiline(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    lines: list[str],
    size: int,
    fill: str,
    *,
    bold: bool = False,
    spacing: int = 7,
) -> None:
    draw.multiline_text(
        xy, "\n".join(lines), font=font(size, bold=bold), fill=fill, spacing=spacing
    )


def topic_row(
    draw: ImageDraw.ImageDraw,
    x1: int,
    y: int,
    x2: int,
    topic: dict[str, Any],
    accent: str,
) -> None:
    percentage = float(topic["accuracy_percent"])
    lines = topic_lines(topic["topic"])
    multiline(draw, (x1, y), lines, 16, WHITE, bold=True, spacing=4)
    text(
        draw,
        (x2, y + 10),
        f"{percentage:.1f}%".replace(".", ","),
        18,
        WHITE,
        bold=True,
        anchor="ra",
    )
    bar_y = y + 52 if len(lines) == 1 else y + 67
    rounded(draw, (x1, bar_y, x2, bar_y + 13), 7, DARK_TRACK)
    if percentage > 0:
        rounded(draw, (x1, bar_y, x1 + round((x2 - x1) * percentage / 100), bar_y + 13), 7, accent)


def priority_card(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    index: int,
    priority: dict[str, Any],
) -> None:
    x1, y1, x2, y2 = box
    accent = ACCENTS[index]
    rounded(draw, box, 34, PANEL_NAVY, PANEL_LINE, 2)

    panel_box = (x1 + 12, y1 + 12, x1 + 350, y2 - 12)
    rounded(draw, panel_box, 28, PANEL_NAVY_ALT, PANEL_LINE, 2)
    label_color = CYAN
    body_color = WHITE
    muted_color = LIGHT_MUTED

    rounded(draw, (x1 + 38, y1 + 36, x1 + 188, y1 + 72), 18, accent)
    text(
        draw,
        (x1 + 113, y1 + 54),
        f"PRIORIDADE {index + 1:02d}",
        12,
        NAVY if index == 1 else WHITE,
        bold=True,
        anchor="mm",
    )
    name_lines = textwrap.wrap(priority["display_name"], width=26, break_long_words=False)
    multiline(draw, (x1 + 38, y1 + 96), name_lines[:2], 23, body_color, bold=True, spacing=4)
    text(
        draw,
        (x1 + 38, y1 + 188),
        f"{float(priority['accuracy_percent']):.1f}%".replace(".", ","),
        49,
        body_color,
        display=True,
    )
    text(draw, (x1 + 40, y1 + 246), "TAXA DE ACERTO", 13, label_color, bold=True)
    text(draw, (x1 + 38, y1 + 296), f"{priority['total']} QUESTÕES", 14, body_color, bold=True)
    text(
        draw,
        (x1 + 38, y1 + 326),
        f"{priority['correct']} ACERTOS  •  {priority['wrong']} ERROS",
        14,
        muted_color,
        bold=True,
    )

    content_x1 = x1 + 388
    content_x2 = x2 - 34
    text(draw, (content_x1, y1 + 38), "ASSUNTOS PRIORITÁRIOS", 17, WHITE, bold=True)
    text(draw, (content_x2, y1 + 38), "DESEMPENHO", 12, LIGHT_MUTED, bold=True, anchor="ra")
    if not priority["topics"]:
        text(
            draw,
            (content_x1, y1 + 120),
            "Nenhum assunto disponível neste período.",
            17,
            LIGHT_MUTED,
            bold=True,
        )
        return
    for topic_index, topic in enumerate(priority["topics"]):
        topic_row(draw, content_x1, y1 + 82 + topic_index * 86, content_x2, topic, accent)


def generate(data: dict[str, Any] | None = None) -> Image.Image:
    values = report_values(data or load_report())
    image = Image.new("RGBA", (WIDTH, HEIGHT), NAVY)
    draw = ImageDraw.Draw(image)
    header(image, draw, values)

    card_height = 372
    card_gap = 24
    for index, priority in enumerate(values["priorities"]):
        y1 = 292 + index * (card_height + card_gap)
        priority_card(draw, (MARGIN, y1, WIDTH - MARGIN, y1 + card_height), index, priority)

    rounded(draw, (MARGIN, 1484, WIDTH - MARGIN, 1538), 27, PANEL_NAVY, PANEL_LINE, 2)
    text(
        draw,
        (WIDTH // 2, 1511),
        "CRITÉRIO: 3 MENORES TAXAS ENTRE DISCIPLINAS COM 10 OU MAIS QUESTÕES",
        13,
        WHITE,
        bold=True,
        anchor="mm",
    )
    wave_footer(draw, top=1582)
    return image


if __name__ == "__main__":
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    result = generate()
    result.convert("RGB").save(OUTPUT_FILE, quality=96, optimize=True)
    print(OUTPUT_FILE)
