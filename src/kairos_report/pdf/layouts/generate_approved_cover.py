from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import generate_panorama_variants as base

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


def _fit_font(
    draw: ImageDraw.ImageDraw,
    value: str,
    *,
    maximum_width: int,
    initial_size: int,
    minimum_size: int,
) -> ImageFont.FreeTypeFont:
    for size in range(initial_size, minimum_size - 1, -2):
        candidate = ImageFont.truetype(str(base.DISPLAY_PATH), size=size)
        if draw.textbbox((0, 0), value, font=candidate)[2] <= maximum_width:
            return candidate
    return ImageFont.truetype(str(base.DISPLAY_PATH), size=minimum_size)


def _wrap_name(
    draw: ImageDraw.ImageDraw,
    value: str,
    font: ImageFont.FreeTypeFont,
    maximum_width: int,
) -> str:
    lines: list[str] = []
    for word in value.split():
        candidate = f"{lines[-1]} {word}" if lines else word
        if lines and draw.textbbox((0, 0), candidate, font=font)[2] > maximum_width:
            lines.append(word)
        elif lines:
            lines[-1] = candidate
        else:
            lines.append(word)
    return "\n".join(lines) if lines else value


def _name_layout(
    draw: ImageDraw.ImageDraw,
    value: str,
    box: tuple[int, int, int, int],
) -> tuple[str, ImageFont.FreeTypeFont]:
    x1, y1, x2, y2 = box
    maximum_width = x2 - x1

    # Keep the approved one-line treatment unchanged whenever it already fits.
    single_line_font = _fit_font(
        draw,
        value,
        maximum_width=maximum_width,
        initial_size=132,
        minimum_size=50,
    )
    single_line_box = draw.textbbox((x1, y1), value, font=single_line_font)
    if single_line_box[2] <= x2 and single_line_box[3] <= y2:
        return value, single_line_font

    for size in range(132, 3, -2):
        candidate_font = ImageFont.truetype(str(base.DISPLAY_PATH), size=size)
        wrapped = _wrap_name(draw, value, candidate_font, maximum_width)
        candidate_box = draw.multiline_textbbox(
            (x1, y1), wrapped, font=candidate_font, spacing=0
        )
        if candidate_box[2] <= x2 and candidate_box[3] <= y2:
            return wrapped, candidate_font

    return value, ImageFont.truetype(str(base.DISPLAY_PATH), size=4)


def _erase_navy_text(
    image: Image.Image,
    box: tuple[int, int, int, int],
) -> None:
    region = image.crop(box).convert("RGB")
    mask = Image.new("L", region.size, 0)
    mask_pixels = mask.load()
    region_pixels = region.load()
    assert mask_pixels is not None
    assert region_pixels is not None
    for y in range(region.height):
        for x in range(region.width):
            red, green, blue = region_pixels[x, y]  # type: ignore[misc]
            if red < 135 and green < 145 and blue < 180 and blue > red:
                mask_pixels[x, y] = 255
    mask = mask.filter(ImageFilter.MaxFilter(15)).filter(ImageFilter.GaussianBlur(1.2))
    background = Image.new("RGBA", region.size, base.WHITE)
    image.paste(background, box[:2], mask)


def generate(
    data: dict[str, Any],
    *,
    template_path: Path,
    template_student: str = "LUIZA",
    template_period: str = "2026-07",
) -> Image.Image:
    """Personaliza a capa aprovada sem alterar sua composição visual."""
    image = Image.open(template_path).convert("RGBA")
    draw = ImageDraw.Draw(image)
    identity = data["identity"]
    year, month, _ = identity["period_start"].split("-")
    student = str(identity["student_name"]).upper()
    period = f"{year}-{month}"

    # Altera somente os campos que realmente mudaram para preservar a arte-base.
    if student != template_student.upper():
        _erase_navy_text(image, (62, 607, 594, 774))
        rendered_student, student_font = _name_layout(draw, student, (72, 604, 550, 772))
        if "\n" in rendered_student:
            draw.multiline_text(
                (72, 604),
                rendered_student,
                font=student_font,
                fill=base.NAVY,
                spacing=0,
            )
        else:
            draw.text((72, 604), rendered_student, font=student_font, fill=base.NAVY)

    if period != template_period:
        _erase_navy_text(image, (145, 789, 566, 905))
        detail_font = ImageFont.truetype(str(base.BOLD_PATH), size=38)
        draw.text(
            (162, 798),
            f"{MONTHS[int(month)]} {year}",
            font=detail_font,
            fill=base.NAVY,
        )
        draw.text((162, 848), "MENTORIA KAIRÓS", font=detail_font, fill=base.NAVY)
    return image.resize((base.WIDTH, base.HEIGHT), Image.Resampling.LANCZOS)
