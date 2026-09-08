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
OUTPUT_PAGE_7 = OUTPUT_DIR / "pagina-07-disciplinas-04-a-06.png"
OUTPUT_PAGE_8 = OUTPUT_DIR / "pagina-08-disciplinas-07-a-09.png"
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
MIN_QUESTIONS = 10
RANK_COLORS = [CORAL, YELLOW, BLUE, CYAN, "#5ED9B1", "#5667C9", "#7457D7", "#3689C9", NAVY]


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


def wrap_lines(value: str, width: int, maximum: int) -> list[str]:
    cleaned = re.sub(r"\s+", " ", value).strip()
    lines = textwrap.wrap(cleaned, width=width, break_long_words=False, break_on_hyphens=False)
    if len(lines) <= maximum:
        return lines
    result = lines[:maximum]
    result[-1] = result[-1].rstrip(" ,;:.") + "…"
    return result


def concise_topic(value: str, limit: int = 72) -> str:
    cleaned = re.sub(r"\s+", " ", value).strip()
    cleaned = re.sub(r"\s+e (?:suas )?alterações", "", cleaned, flags=re.IGNORECASE)
    law = re.search(r"Lei\s*n[º°]?\s*([\d.]+)\s*/\s*(\d{4})", cleaned, flags=re.IGNORECASE)
    if law:
        law_label = f"Lei nº {law.group(1)}/{law.group(2)}"
        quoted = re.findall(r"[“\"]([^”\"]+)[”\"]", cleaned)
        descriptions = [item.strip(" .") for item in re.findall(r"\(([^()]*)\)", cleaned)]
        descriptions = [item for item in descriptions if item and not item.startswith("1/")]
        tail = re.split(r"\s+-\s+", cleaned, maxsplit=1)
        description = (
            quoted[-1]
            if quoted
            else (descriptions[-1] if descriptions else (tail[1] if len(tail) == 2 else ""))
        )
        if description:
            cleaned = f"{law_label} — {description}"
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip(" ,;:.") + "…"


def multiline(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    lines: list[str],
    size: int,
    fill: str,
    *,
    bold: bool = False,
    spacing: int = 5,
) -> None:
    draw.multiline_text(
        xy, "\n".join(lines), font=font(size, bold=bold), fill=fill, spacing=spacing
    )


def report_values(data: dict[str, Any]) -> dict[str, Any]:
    period = data["identity"]["period_start"].split("-")
    topics = data["questions"]["topics"]
    disciplines = [
        item for item in data["questions"]["disciplines"] if int(item["total"]) >= MIN_QUESTIONS
    ]
    disciplines = sorted(
        disciplines, key=lambda item: (float(item["accuracy_percent"]), -int(item["total"]))
    )
    ranked: list[dict[str, Any]] = []
    for index, discipline in enumerate(disciplines):
        matching = [
            topic
            for topic in topics
            if normalized(topic["discipline"]) == normalized(discipline["name"])
        ]
        ranked.append(
            {
                **discipline,
                "rank": index + 1,
                "display_name": display_discipline(discipline["name"]),
                "topics": sorted(matching, key=lambda topic: float(topic["accuracy_percent"])),
            }
        )
    return {
        "student": data["identity"]["student_name"].upper(),
        "period": f"{MONTHS[int(period[1])]} {period[0]}",
        "disciplines": ranked,
    }


def header(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    values: dict[str, Any],
    page: int,
    range_label: str,
) -> None:
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
    text(draw, (MARGIN, 174), "MAPA COMPLETO DE QUESTÕES", 54, WHITE, display=True)
    text(
        draw,
        (MARGIN, 236),
        f"Disciplinas e assuntos em ordem de desempenho  •  {range_label}",
        19,
        LIGHT_MUTED,
    )
    rounded(draw, (WIDTH - 177, 172, WIDTH - MARGIN, 216), 22, YELLOW)
    text(draw, (WIDTH - 126, 194), f"{page:02d}", 16, NAVY, bold=True, anchor="mm")


def topic_bar(
    draw: ImageDraw.ImageDraw,
    x1: int,
    y: int,
    x2: int,
    topic: dict[str, Any],
    accent: str,
    *,
    compact: bool = False,
) -> int:
    percentage = float(topic["accuracy_percent"])
    lines = wrap_lines(topic["topic"], 78 if not compact else 62, 2)
    multiline(draw, (x1, y), lines, 14 if not compact else 13, WHITE, bold=True, spacing=3)
    text(
        draw, (x2, y + 8), f"{percentage:.1f}%".replace(".", ","), 16, WHITE, bold=True, anchor="ra"
    )
    bar_y = y + (49 if len(lines) == 1 else 62)
    rounded(draw, (x1, bar_y, x2, bar_y + 11), 6, DARK_TRACK)
    if percentage > 0:
        rounded(draw, (x1, bar_y, x1 + round((x2 - x1) * percentage / 100), bar_y + 11), 6, accent)
    return bar_y + 11


def left_panel(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    discipline: dict[str, Any],
    *,
    dark: bool = False,
) -> None:
    x1, y1, x2, y2 = box
    accent = RANK_COLORS[(discipline["rank"] - 1) % len(RANK_COLORS)]
    rounded(draw, box, 28, PANEL_NAVY_ALT, PANEL_LINE, 2)
    rounded(draw, (x1 + 26, y1 + 24, x1 + 178, y1 + 60), 18, accent)
    text(
        draw,
        (x1 + 102, y1 + 42),
        f"POSIÇÃO {discipline['rank']:02d}",
        12,
        NAVY if accent in (YELLOW, CYAN, "#5ED9B1") else WHITE,
        bold=True,
        anchor="mm",
    )
    name_lines = wrap_lines(discipline["display_name"], 26, 3)
    multiline(draw, (x1 + 26, y1 + 86), name_lines, 21, WHITE, bold=True, spacing=4)
    metric_y = y1 + 184 if len(name_lines) <= 2 else y1 + 210
    text(
        draw,
        (x1 + 26, metric_y),
        f"{float(discipline['accuracy_percent']):.1f}%".replace(".", ","),
        44,
        WHITE,
        display=True,
    )
    text(draw, (x1 + 28, metric_y + 52), "TAXA DE ACERTO", 12, CYAN, bold=True)
    text(
        draw,
        (x1 + 26, y2 - 60),
        f"{discipline['total']} QUESTÕES",
        13,
        WHITE,
        bold=True,
    )
    text(
        draw,
        (x1 + 26, y2 - 32),
        f"{discipline['correct']} ACERTOS  •  {discipline['wrong']} ERROS",
        13,
        LIGHT_MUTED,
        bold=True,
    )


def standard_card(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    discipline: dict[str, Any],
) -> None:
    x1, y1, x2, y2 = box
    accent = RANK_COLORS[(discipline["rank"] - 1) % len(RANK_COLORS)]
    rounded(draw, box, 34, PANEL_NAVY, PANEL_LINE, 2)
    left_panel(draw, (x1 + 12, y1 + 12, x1 + 342, y2 - 12), discipline)
    content_x1, content_x2 = x1 + 380, x2 - 34
    text(draw, (content_x1, y1 + 36), "ASSUNTOS", 17, WHITE, bold=True)
    text(draw, (content_x2, y1 + 36), "DESEMPENHO", 12, LIGHT_MUTED, bold=True, anchor="ra")
    if not discipline["topics"]:
        text(
            draw,
            (content_x1, y1 + 110),
            "Sem assuntos disponíveis nesta extração.",
            16,
            WHITE,
            bold=True,
        )
        return
    if len(discipline["topics"]) <= 3:
        for topic_index, topic in enumerate(discipline["topics"]):
            topic_bar(draw, content_x1, y1 + 76 + topic_index * 88, content_x2, topic, accent)
        return

    text(draw, (content_x1, y1 + 62), "Todos os assuntos disponíveis", 12, LIGHT_MUTED)
    column_gap = 24
    column_width = (content_x2 - content_x1 - column_gap) // 2
    split = (len(discipline["topics"]) + 1) // 2
    for topic_index, topic in enumerate(discipline["topics"]):
        column = 0 if topic_index < split else 1
        row = topic_index if column == 0 else topic_index - split
        topic_x1 = content_x1 + column * (column_width + column_gap)
        topic_x2 = topic_x1 + column_width
        topic_y = y1 + 92 + row * 66
        percentage = float(topic["accuracy_percent"])
        multiline(
            draw,
            (topic_x1, topic_y),
            wrap_lines(concise_topic(topic["topic"], 60), 36, 2),
            11,
            WHITE,
            bold=True,
            spacing=2,
        )
        bar_y = topic_y + 40
        bar_x2 = topic_x2 - 58
        rounded(draw, (topic_x1, bar_y, bar_x2, bar_y + 10), 5, DARK_TRACK)
        if percentage > 0:
            rounded(
                draw,
                (
                    topic_x1,
                    bar_y,
                    topic_x1 + round((bar_x2 - topic_x1) * percentage / 100),
                    bar_y + 10,
                ),
                5,
                accent,
            )
        text(
            draw,
            (topic_x2, bar_y + 5),
            f"{percentage:.1f}%".replace(".", ","),
            12,
            WHITE,
            bold=True,
            anchor="rm",
        )


def criterion(draw: ImageDraw.ImageDraw) -> None:
    rounded(draw, (MARGIN, 1482, WIDTH - MARGIN, 1538), 28, PANEL_NAVY, PANEL_LINE, 2)
    text(
        draw,
        (WIDTH // 2, 1510),
        "ORDEM: MENOR PARA MAIOR TAXA DE ACERTO  •  MÍNIMO DE 10 QUESTÕES",
        13,
        WHITE,
        bold=True,
        anchor="mm",
    )


def discipline_page(
    values: dict[str, Any],
    disciplines: list[dict[str, Any]],
    *,
    page_number: int,
) -> Image.Image:
    image = Image.new("RGBA", (WIDTH, HEIGHT), NAVY)
    draw = ImageDraw.Draw(image)
    first_rank = disciplines[0]["rank"]
    last_rank = disciplines[-1]["rank"]
    header(
        image,
        draw,
        values,
        page_number,
        f"POSIÇÕES {first_rank:02d}-{last_rank:02d}",
    )
    for offset, discipline in enumerate(disciplines):
        y1 = 292 + offset * 396
        standard_card(draw, (MARGIN, y1, WIDTH - MARGIN, y1 + 372), discipline)
    criterion(draw)
    wave_footer(draw, top=1582)
    return image


def generate_pages(data: dict[str, Any] | None = None) -> list[Image.Image]:
    values = report_values(data or load_report())
    remaining = []
    for index, discipline in enumerate(values["disciplines"]):
        topics = discipline["topics"][3:] if index < 3 else discipline["topics"]
        if index < 3 and not topics:
            continue
        chunks = [topics[offset : offset + 8] for offset in range(0, len(topics), 8)] or [[]]
        for chunk_index, chunk in enumerate(chunks):
            continued = index < 3 or chunk_index > 0
            remaining.append(
                {
                    **discipline,
                    "topics": chunk,
                    "display_name": discipline["display_name"]
                    + (" (continuação)" if continued else ""),
                }
            )
    return [
        discipline_page(
            values,
            remaining[offset : offset + 3],
            page_number=7 + offset // 3,
        )
        for offset in range(0, len(remaining), 3)
    ]


def page_seven(values: dict[str, Any]) -> Image.Image:
    return discipline_page(values, values["disciplines"][3:6], page_number=7)


def page_eight(values: dict[str, Any]) -> Image.Image:
    return discipline_page(values, values["disciplines"][6:9], page_number=8)


if __name__ == "__main__":
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pages = generate_pages()
    for output, page in zip((OUTPUT_PAGE_7, OUTPUT_PAGE_8), pages, strict=False):
        page.convert("RGB").save(output, quality=96, optimize=True)
        print(output)
