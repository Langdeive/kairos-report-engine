from __future__ import annotations

import math
import os
from collections.abc import Iterable
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps

WIDTH = 1240
HEIGHT = 1754
MARGIN = 76

NAVY = "#071448"
BLUE = "#1768D7"
CYAN = "#14C4E5"
MINT = "#5ED9B1"
CORAL = "#FF5058"
YELLOW = "#FFB51B"
INK = "#101A3A"
MUTED = "#66708B"
PALE = "#EEF7FC"
PALE_BLUE = "#DFF5FA"
LINE = "#D8E5EF"
WHITE = "#FFFFFF"
BG = "#F7FAFD"
PANEL_NAVY = "#0D225E"
PANEL_NAVY_ALT = "#132B6D"
PANEL_LINE = "#30457E"
LIGHT_MUTED = "#BFD3FF"
DARK_TRACK = "#34467E"

FONT_DIR = Path(
    os.environ.get(
        "KAIROS_FONT_DIR",
        str(Path(__file__).resolve().parents[1] / "assets" / "fonts"),
    )
)
REGULAR_PATH = FONT_DIR / "InstrumentSans-Regular.ttf"
BOLD_PATH = FONT_DIR / "InstrumentSans-Bold.ttf"
DISPLAY_PATH = FONT_DIR / "BigShoulders-Bold.ttf"
LOGO_PATH = Path(
    os.environ.get(
        "KAIROS_LOGO_PATH",
        str(Path(__file__).resolve().parents[1] / "assets" / "logo.png"),
    )
)
OUTPUT_DIR = Path(__file__).resolve().parents[2] / "output" / "layouts" / "panorama-dashboard"

WEEK_HOURS = [2.0, 4.5, 3.0, 0.5, 0.0]
WEEK_TARGETS = [6.5, 11.0, 11.0, 11.0, 9.0]
WEEK_QUESTIONS = [38, 107, 98, 146, 152]
WEEK_ACCURACY = [71.05, 77.57, 85.71, 85.62, 80.92]


def configure_assets(*, logo_path: Path, font_dir: Path) -> None:
    """Configura os ativos visuais sem fixá-los a uma máquina específica."""
    global BOLD_PATH, DISPLAY_PATH, FONT_DIR, LOGO_PATH, REGULAR_PATH
    FONT_DIR = font_dir
    REGULAR_PATH = FONT_DIR / "InstrumentSans-Regular.ttf"
    BOLD_PATH = FONT_DIR / "InstrumentSans-Bold.ttf"
    DISPLAY_PATH = FONT_DIR / "BigShoulders-Bold.ttf"
    LOGO_PATH = logo_path


def font(size: int, *, bold: bool = False, display: bool = False) -> ImageFont.FreeTypeFont:
    path = DISPLAY_PATH if display else (BOLD_PATH if bold else REGULAR_PATH)
    return ImageFont.truetype(str(path), size=size)


def rounded(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    radius: int,
    fill: str,
    outline: str | None = None,
    width: int = 1,
) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def paste_logo(image: Image.Image, x: int, y: int, width: int) -> None:
    logo = Image.open(LOGO_PATH).convert("RGBA")
    ratio = width / logo.width
    logo = logo.resize((width, round(logo.height * ratio)), Image.Resampling.LANCZOS)
    pixels = logo.load()
    assert pixels is not None
    for py in range(logo.height):
        for px in range(logo.width):
            r, g, b, _ = pixels[px, py]  # type: ignore[misc]
            alpha = 0 if r > 247 and g > 247 and b > 247 else 255
            pixels[px, py] = (r, g, b, alpha)
    image.alpha_composite(logo, (x, y))


def paste_light_logo(image: Image.Image, x: int, y: int, width: int) -> None:
    logo = Image.open(LOGO_PATH).convert("RGBA")
    darkness = ImageOps.invert(logo.convert("L"))
    opacity = ImageChops.multiply(logo.getchannel("A"), darkness)
    light_logo = Image.new("RGBA", logo.size, WHITE)
    light_logo.putalpha(opacity)
    ratio = width / light_logo.width
    light_logo = light_logo.resize(
        (width, round(light_logo.height * ratio)),
        Image.Resampling.LANCZOS,
    )
    image.alpha_composite(light_logo, (x, y))


def text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    value: str,
    size: int,
    fill: str = INK,
    *,
    bold: bool = False,
    display: bool = False,
    anchor: str | None = None,
) -> None:
    draw.text(xy, value, font=font(size, bold=bold, display=display), fill=fill, anchor=anchor)


def header(image: Image.Image, draw: ImageDraw.ImageDraw, version: str, subtitle: str) -> None:
    paste_logo(image, MARGIN, 52, 300)
    text(draw, (WIDTH - MARGIN, 72), "LUIZA  •  JULHO 2026", 22, NAVY, bold=True, anchor="ra")
    text(draw, (MARGIN, 178), "PANORAMA DO MÊS", 58, NAVY, display=True)
    text(draw, (MARGIN, 238), subtitle, 20, MUTED)
    rounded(draw, (WIDTH - 177, 172, WIDTH - MARGIN, 216), 22, WHITE, LINE, 2)
    text(draw, (WIDTH - 126, 194), version, 16, BLUE, bold=True, anchor="mm")


def wave_footer(draw: ImageDraw.ImageDraw, top: int = 1585) -> None:
    layers = [(top, CYAN, 42), (top + 44, BLUE, 38), (top + 92, NAVY, 34)]
    for base_y, color, amplitude in layers:
        points = [(0, HEIGHT)]
        for x in range(0, WIDTH + 21, 20):
            y = base_y + math.sin((x / WIDTH) * math.pi * 2.1) * amplitude
            points.append((x, round(y)))
        points.extend([(WIDTH, HEIGHT), (0, HEIGHT)])
        draw.polygon(points, fill=color)


def metric_card(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    value: str,
    label: str,
    accent: str,
    *,
    dark: bool = False,
) -> None:
    fill = NAVY if dark else WHITE
    rounded(draw, box, 28, fill, None if dark else LINE, 2)
    x1, y1, x2, y2 = box
    draw.ellipse((x1 + 24, y1 + 24, x1 + 40, y1 + 40), fill=accent)
    text(draw, (x1 + 24, y1 + 63), value, 54, WHITE if dark else NAVY, bold=True)
    text(draw, (x1 + 25, y2 - 38), label, 17, "#BFD3FF" if dark else MUTED, bold=True)


def donut(
    draw: ImageDraw.ImageDraw,
    center: tuple[int, int],
    radius: int,
    percent: float,
    color: str,
    label: str,
    value: str,
    *,
    bg: str = "#DCE7F0",
) -> None:
    cx, cy = center
    width = max(16, radius // 6)
    box = (cx - radius, cy - radius, cx + radius, cy + radius)
    draw.arc(box, 0, 360, fill=bg, width=width)
    draw.arc(box, -90, -90 + 360 * percent / 100, fill=color, width=width)
    text(draw, (cx, cy - 8), value, 34, NAVY, bold=True, anchor="mm")
    text(draw, (cx, cy + 34), label, 15, MUTED, bold=True, anchor="mm")


def bar_chart(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    values: list[float],
    labels: list[str],
    color: str,
    *,
    targets: list[float] | None = None,
    title: str = "",
) -> None:
    x1, y1, x2, y2 = box
    if title:
        text(draw, (x1, y1), title, 22, NAVY, bold=True)
        y1 += 46
    baseline = y2 - 34
    draw.line((x1, baseline, x2, baseline), fill=LINE, width=2)
    slot = (x2 - x1) / len(values)
    maximum = max((targets or []) + values) or 1
    for index, value in enumerate(values):
        center_x = x1 + slot * (index + 0.5)
        width = min(54, slot * 0.44)
        max_height = baseline - y1 - 20
        if targets is not None:
            target_height = max_height * targets[index] / maximum
            rounded(
                draw,
                (
                    round(center_x - width / 2),
                    round(baseline - target_height),
                    round(center_x + width / 2),
                    baseline,
                ),
                10,
                "#DCE7F0",
            )
        height = max_height * value / maximum
        rounded(
            draw,
            (
                round(center_x - width / 2),
                round(baseline - height),
                round(center_x + width / 2),
                baseline,
            ),
            10,
            color,
        )
        text(
            draw, (round(center_x), baseline + 18), labels[index], 15, MUTED, bold=True, anchor="mm"
        )


def line_chart(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    values: list[float],
    labels: list[str],
    color: str,
    *,
    title: str = "",
) -> None:
    x1, y1, x2, y2 = box
    if title:
        text(draw, (x1, y1), title, 22, NAVY, bold=True)
        y1 += 50
    inner_y1 = y1 + 20
    inner_y2 = y2 - 38
    maximum = max(values) or 1
    points = []
    for index, value in enumerate(values):
        x = x1 + (x2 - x1) * index / max(1, len(values) - 1)
        y = inner_y2 - (inner_y2 - inner_y1) * value / maximum
        points.append((round(x), round(y)))
    draw.line(points, fill=color, width=7, joint="curve")
    for index, (x, y) in enumerate(points):
        draw.ellipse((x - 10, y - 10, x + 10, y + 10), fill=WHITE, outline=color, width=5)
        text(draw, (x, inner_y2 + 26), labels[index], 15, MUTED, bold=True, anchor="mm")


def progress(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    percent: float,
    color: str,
    label: str,
    value: str,
) -> None:
    x1, y1, x2, y2 = box
    text(draw, (x1, y1), label, 17, MUTED, bold=True)
    text(draw, (x2, y1), value, 19, NAVY, bold=True, anchor="ra")
    track_y = y2 - 22
    rounded(draw, (x1, track_y, x2, y2), 11, "#DFEAF2")
    fill_width = max(18, round((x2 - x1) * percent / 100))
    rounded(draw, (x1, track_y, x1 + fill_width, y2), 11, color)


def new_page(version: str, subtitle: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGBA", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)
    header(image, draw, version, subtitle)
    return image, draw


def variant_one() -> Image.Image:
    image, draw = new_page("01", "Indicadores centrais e evolução semanal")
    cards = [
        ("15h", "TEMPO TOTAL", CYAN),
        ("14/31", "DIAS ATIVOS", MINT),
        ("541", "QUESTÕES", BLUE),
        ("81,7%", "TAXA DE ACERTO", CORAL),
    ]
    card_width = 252
    for index, (value, label, accent) in enumerate(cards):
        x = MARGIN + index * (card_width + 24)
        metric_card(draw, (x, 300, x + card_width, 480), value, label, accent, dark=index == 2)
    rounded(draw, (MARGIN, 520, 760, 1100), 34, WHITE, LINE, 2)
    bar_chart(
        draw,
        (112, 566, 724, 1040),
        WEEK_HOURS,
        ["S1", "S2", "S3", "S4", "S5"],
        BLUE,
        targets=WEEK_TARGETS,
        title="TEMPO ESTUDADO × META",
    )
    rounded(draw, (792, 520, WIDTH - MARGIN, 1100), 34, WHITE, LINE, 2)
    text(draw, (828, 566), "CONSTÂNCIA E ACERTO", 22, NAVY, bold=True)
    donut(draw, (918, 760), 92, 45.16, CYAN, "CONSTÂNCIA", "45,2%")
    donut(draw, (1101, 760), 92, 81.7, CORAL, "ACERTO", "81,7%")
    progress(draw, (830, 958, 1124, 1026), 20.62, MINT, "ADERÊNCIA ÀS METAS", "20,62%")
    rounded(draw, (MARGIN, 1140, WIDTH - MARGIN, 1518), 34, NAVY)
    text(draw, (112, 1188), "QUESTÕES POR SEMANA", 22, WHITE, bold=True)
    bar_chart(
        draw,
        (112, 1240, 1118, 1474),
        [float(v) for v in WEEK_QUESTIONS],
        ["S1", "S2", "S3", "S4", "S5"],
        CYAN,
    )
    wave_footer(draw)
    return image


def variant_two() -> Image.Image:
    image, draw = new_page("02", "Um painel circular para leitura instantânea")
    rounded(draw, (MARGIN, 300, WIDTH - MARGIN, 1030), 42, WHITE, LINE, 2)
    text(draw, (WIDTH // 2, 355), "SEU MÊS EM DOIS MOVIMENTOS", 23, NAVY, bold=True, anchor="mm")
    donut(draw, (430, 655), 190, 45.16, CYAN, "14 DE 31 DIAS ATIVOS", "45,2%")
    donut(draw, (810, 655), 190, 81.7, CORAL, "442 DE 541 ACERTOS", "81,7%")
    draw.line((620, 460, 620, 866), fill=LINE, width=2)
    text(draw, (430, 925), "CONSTÂNCIA", 20, BLUE, bold=True, anchor="mm")
    text(draw, (810, 925), "DESEMPENHO", 20, BLUE, bold=True, anchor="mm")
    cards = [("15h", "ESTUDO", CYAN), ("541", "QUESTÕES", BLUE), ("1%", "PLANO", YELLOW)]
    for index, (value, label, accent) in enumerate(cards):
        x = MARGIN + index * 376
        metric_card(draw, (x, 1070, x + 344, 1248), value, label, accent, dark=index == 1)
    rounded(draw, (MARGIN, 1288, WIDTH - MARGIN, 1535), 34, WHITE, LINE, 2)
    line_chart(
        draw,
        (116, 1328, 1120, 1500),
        [float(v) for v in WEEK_QUESTIONS],
        ["S1", "S2", "S3", "S4", "S5"],
        BLUE,
        title="RITMO DE QUESTÕES",
    )
    wave_footer(draw)
    return image


def variant_three() -> Image.Image:
    image, draw = new_page("03", "A evolução como uma onda que atravessa o mês")
    rounded(draw, (MARGIN, 300, WIDTH - MARGIN, 660), 38, NAVY)
    text(draw, (112, 346), "RITMO DE ESTUDO", 22, CYAN, bold=True)
    text(draw, (112, 414), "15h", 88, WHITE, display=True)
    text(draw, (112, 518), "14 dias ativos  •  média de 1h por dia", 21, "#C9D9FF")
    line_chart(draw, (530, 350, 1112, 608), WEEK_HOURS, ["S1", "S2", "S3", "S4", "S5"], CYAN)
    rounded(draw, (MARGIN, 700, WIDTH - MARGIN, 1195), 38, WHITE, LINE, 2)
    text(draw, (112, 748), "UMA MARÉ DE 541 QUESTÕES", 28, NAVY, bold=True)
    bar_chart(
        draw,
        (116, 816, 1116, 1128),
        [float(v) for v in WEEK_QUESTIONS],
        ["S1", "S2", "S3", "S4", "S5"],
        BLUE,
    )
    for index, accuracy in enumerate(WEEK_ACCURACY):
        x = 182 + index * 214
        text(draw, (x, 1146), f"{accuracy:.0f}%", 16, CORAL, bold=True, anchor="mm")
    rounded(draw, (MARGIN, 1235, 568, 1515), 34, PALE_BLUE)
    text(draw, (112, 1276), "ACERTO", 18, MUTED, bold=True)
    text(draw, (112, 1320), "81,7%", 76, NAVY, display=True)
    progress(draw, (112, 1430, 526, 1488), 81.7, CORAL, "442 acertos", "99 erros")
    rounded(draw, (604, 1235, WIDTH - MARGIN, 1515), 34, WHITE, LINE, 2)
    text(draw, (642, 1276), "PLANO E META", 18, MUTED, bold=True)
    progress(draw, (642, 1350, 1124, 1410), 20.62, MINT, "ADERÊNCIA", "20,62%")
    progress(draw, (642, 1440, 1124, 1500), 1.0, YELLOW, "PROGRESSO DO PLANO", "1%")
    wave_footer(draw)
    return image


def variant_four() -> Image.Image:
    image, draw = new_page("04", "Números grandes com gráficos compactos")
    rounded(draw, (MARGIN, 300, 540, 820), 38, NAVY)
    text(draw, (116, 350), "TEMPO TOTAL", 18, CYAN, bold=True)
    text(draw, (116, 410), "15h", 112, WHITE, display=True)
    text(draw, (116, 555), "14", 72, MINT, display=True)
    text(draw, (278, 590), "dias ativos", 20, "#C6D5FF", bold=True)
    text(draw, (116, 720), "CONSTÂNCIA", 17, "#A9B7D9", bold=True)
    text(draw, (500, 720), "45,16%", 19, WHITE, bold=True, anchor="ra")
    rounded(draw, (116, 758, 500, 780), 11, "#DCE7F0")
    rounded(draw, (116, 758, 289, 780), 11, CYAN)
    rounded(draw, (576, 300, WIDTH - MARGIN, 820), 38, WHITE, LINE, 2)
    text(draw, (616, 350), "HORAS POR SEMANA", 22, NAVY, bold=True)
    bar_chart(
        draw,
        (616, 420, 1120, 760),
        WEEK_HOURS,
        ["S1", "S2", "S3", "S4", "S5"],
        BLUE,
        targets=WEEK_TARGETS,
    )
    rounded(draw, (MARGIN, 860, WIDTH - MARGIN, 1220), 38, WHITE, LINE, 2)
    text(draw, (116, 910), "QUESTÕES", 18, MUTED, bold=True)
    text(draw, (116, 960), "541", 84, NAVY, display=True)
    text(draw, (344, 1000), "442 acertos", 22, BLUE, bold=True)
    text(draw, (344, 1042), "99 erros", 20, CORAL, bold=True)
    donut(draw, (932, 1040), 118, 81.7, CORAL, "TAXA DE ACERTO", "81,7%")
    rounded(draw, (MARGIN, 1260, WIDTH - MARGIN, 1518), 34, PALE_BLUE)
    text(draw, (116, 1302), "ADERÊNCIA ÀS METAS", 20, NAVY, bold=True)
    progress(draw, (116, 1382, 1120, 1448), 20.62, MINT, "HORAS CUMPRIDAS × PLANEJADAS", "20,62%")
    text(draw, (116, 1482), "Progresso geral do plano: 1%", 18, MUTED, bold=True)
    wave_footer(draw)
    return image


def variant_five() -> Image.Image:
    image, draw = new_page("05", "Um dashboard em camadas, como marés")
    rounded(draw, (MARGIN, 300, WIDTH - MARGIN, 540), 38, NAVY)
    items = [("15h", "ESTUDO"), ("14/31", "DIAS ATIVOS"), ("541", "QUESTÕES"), ("81,7%", "ACERTO")]
    for index, (value, label) in enumerate(items):
        x = 118 + index * 272
        if index:
            draw.line((x - 30, 344, x - 30, 494), fill="#334379", width=2)
        text(draw, (x, 350), value, 54, WHITE, bold=True)
        text(draw, (x, 440), label, 16, "#BFD3FF", bold=True)
    rounded(draw, (MARGIN, 580, WIDTH - MARGIN, 1010), 38, WHITE, LINE, 2)
    text(draw, (116, 626), "MARÉ DE ESTUDO", 22, NAVY, bold=True)
    line_chart(draw, (116, 690, 1120, 952), WEEK_HOURS, ["S1", "S2", "S3", "S4", "S5"], CYAN)
    rounded(draw, (MARGIN, 1050, 758, 1518), 38, WHITE, LINE, 2)
    text(draw, (116, 1098), "VOLUME DE QUESTÕES", 22, NAVY, bold=True)
    bar_chart(
        draw,
        (116, 1168, 708, 1460),
        [float(v) for v in WEEK_QUESTIONS],
        ["S1", "S2", "S3", "S4", "S5"],
        BLUE,
    )
    rounded(draw, (794, 1050, WIDTH - MARGIN, 1518), 38, PALE_BLUE)
    text(draw, (832, 1098), "EQUILÍBRIO", 22, NAVY, bold=True)
    donut(draw, (978, 1260), 118, 81.7, CORAL, "ACERTO", "81,7%")
    progress(draw, (838, 1435, 1120, 1492), 20.62, MINT, "ADERÊNCIA", "20,62%")
    wave_footer(draw)
    return image


def save_all(pages: Iterable[tuple[str, Image.Image]]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, page in pages:
        output = OUTPUT_DIR / name
        page.convert("RGB").save(output, quality=96, optimize=True)
        print(output)


if __name__ == "__main__":
    save_all(
        [
            ("panorama-01-modular.png", variant_one()),
            ("panorama-02-circular.png", variant_two()),
            ("panorama-03-ritmo.png", variant_three()),
            ("panorama-04-numeros.png", variant_four()),
            ("panorama-05-mares.png", variant_five()),
        ]
    )
