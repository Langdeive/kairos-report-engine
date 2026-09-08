"""Messages for absent measurements; zero performance is not absent activity."""

from __future__ import annotations

from typing import Any

from PIL import Image, ImageDraw

from . import generate_panorama_variants as base

NO_STUDY = "Sem horas de estudo registradas neste período."
NO_QUESTIONS = "Sem questões respondidas neste período."
MISSING_QUESTIONS = "Dados de questões não disponíveis nesta extração."


def message(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], value: str) -> None:
    x1, y1, x2, y2 = box
    # Fit to the available card width, keeping a readable baseline size.
    size = 22
    while size > 14 and draw.textlength(value, font=base.font(size, bold=True)) > x2 - x1 - 32:
        size -= 1
    base.text(
        draw, ((x1 + x2) // 2, (y1 + y2) // 2), value, size, base.WHITE, bold=True, anchor="mm"
    )


def page(data: dict[str, Any], title: str, value: str) -> Image.Image:
    from .generate_approved_constancy import MONTHS

    image = Image.new("RGBA", (base.WIDTH, base.HEIGHT), base.NAVY)
    draw = ImageDraw.Draw(image)
    base.paste_light_logo(image, base.MARGIN, 54, 300)
    period = data["identity"]["period_start"].split("-")
    label = f"{data['identity']['student_name'].upper()} • {MONTHS[int(period[1])]} {period[0]}"
    base.text(draw, (base.WIDTH - base.MARGIN, 72), label, 22, base.WHITE, bold=True, anchor="ra")
    base.text(draw, (base.MARGIN, 174), title, 48, base.WHITE, display=True)
    base.rounded(
        draw,
        (base.MARGIN, 340, base.WIDTH - base.MARGIN, 1180),
        34,
        base.PANEL_NAVY,
        base.PANEL_LINE,
        2,
    )
    message(draw, (base.MARGIN, 580, base.WIDTH - base.MARGIN, 900), value)
    base.wave_footer(draw, top=1582)
    return image
