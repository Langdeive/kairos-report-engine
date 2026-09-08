from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont
from pypdf import PdfReader

from kairos_report.pdf import default_approved_assets, generate_approved_report
from kairos_report.pdf.layouts.generate_approved_constancy import (
    generate as generate_constancy,
)
from kairos_report.pdf.layouts.generate_approved_constancy import (
    report_values as constancy_report_values,
)
from kairos_report.pdf.layouts.generate_approved_cover import _erase_navy_text
from kairos_report.pdf.layouts.generate_approved_cover import generate as generate_cover
from kairos_report.pdf.layouts.generate_approved_panorama import generate as generate_panorama
from kairos_report.pdf.layouts.generate_approved_questions_overview import (
    generate as generate_questions_overview,
)
from kairos_report.pdf.layouts.generate_approved_questions_overview import (
    report_values as questions_report_values,
)
from kairos_report.pdf.layouts.generate_panorama_variants import DISPLAY_PATH


def test_priority_discipline_cards_use_original_blue_background():
    from PIL import ImageColor

    from kairos_report.pdf.layouts.generate_approved_question_priorities import priority_card
    from kairos_report.pdf.layouts.generate_panorama_variants import PANEL_NAVY_ALT

    for index in range(3):
        page = Image.new("RGB", (1240, 1754))
        priority_card(ImageDraw.Draw(page), (76, 290, 1164, 660), index, {
            "display_name": "Disciplina teste", "accuracy_percent": 50,
            "total": 20, "correct": 10, "wrong": 10, "topics": [],
        })
        assert page.getpixel((100, 450)) == ImageColor.getrgb(PANEL_NAVY_ALT)


def approved_mock_data(discipline_count: int = 9) -> dict[str, object]:
    disciplines = [
        {
            "name": f"Disciplina {index}",
            "total": 20 + index,
            "correct": 10 + index,
            "wrong": 10,
            "accuracy_percent": 50.0 + index * 4,
        }
        for index in range(1, discipline_count + 1)
    ]
    topics = [
        {
            "discipline": item["name"],
            "topic": f"Assunto principal da {item['name']}",
            "accuracy_percent": item["accuracy_percent"],
        }
        for item in disciplines
    ]
    weekly = [
        {"label": f"Semana {index}", "hours": float(index), "target_hours": 8.0}
        for index in range(1, 6)
    ]
    question_weekly = [
        {
            "label": f"Semana {index}",
            "correct": 20 * index,
            "wrong": 5 * index,
            "total": 25 * index,
            "accuracy_percent": 80.0,
        }
        for index in range(1, 6)
    ]
    return {
        "schema_version": "1.0",
        "identity": {
            "report_id": 1,
            "student_name": "Luiza",
            "course": "Curso de teste",
            "period_start": "2026-07-01",
            "period_end": "2026-07-31",
        },
        "summary": {
            "total_hours": 15.0,
            "study_days": 14,
            "inactive_days": 17,
            "average_hours_per_active_day": 1.07,
            "accuracy_percent": 80.0,
            "plan_progress_percent": 20.0,
            "remaining_progress_percent": 80.0,
        },
        "weekly_evolution": {
            "weeks": weekly,
            "total_target_hours": 40.0,
            "adherence_percent": 37.5,
            "first_to_last_hours_delta": 4.0,
            "trend": "improving",
        },
        "disciplines": {
            "most_studied": "Disciplina 9",
            "least_studied": "Disciplina 1",
            "ranking": [],
            "progress_percent": {},
        },
        "modalities": {
            "hours": {
                "Estudo": 8.0,
                "Resumo/Mapa Mental": 2.0,
                "Exercício": 2.0,
                "Revisão": 3.0,
            },
            "total_hours": 15.0,
            "shares_percent": {
                "Estudo": 53.33,
                "Resumo/Mapa Mental": 13.33,
                "Exercício": 13.33,
                "Revisão": 20.0,
            },
        },
        "performance_by_area": {},
        "unavailable_metrics": [],
        "questions": {
            "total": 375,
            "correct": 300,
            "wrong": 75,
            "accuracy_percent": 80.0,
            "weekly": question_weekly,
            "disciplines": disciplines,
            "topics": topics,
        },
        "student_activity": None,
    }


def test_generate_approved_report_creates_seven_consistent_pages(tmp_path: Path) -> None:
    output = tmp_path / "relatorio-aprovado.pdf"
    previews = tmp_path / "previews"

    result = generate_approved_report(
        approved_mock_data(),
        output,
        preview_dir=previews,
    )

    assert result == output
    assert output.stat().st_size > 100_000
    assert len(PdfReader(output).pages) == 7
    assert [path.name for path in sorted(previews.glob("*.png"))] == [
        "pagina-01.png",
        "pagina-02.png",
        "pagina-04.png",
        "pagina-05.png",
        "pagina-06.png",
        "pagina-07.png",
        "pagina-08.png",
    ]
    for preview in previews.glob("*.png"):
        with Image.open(preview) as image:
            assert image.size == (1240, 1754)
            assert image.mode == "RGB"


def test_approved_report_keeps_cover_light_and_uses_dark_internal_pages(tmp_path: Path) -> None:
    output = tmp_path / "relatorio-tema-escuro.pdf"
    previews = tmp_path / "previews"

    generate_approved_report(approved_mock_data(), output, preview_dir=previews)

    pages = sorted(previews.glob("*.png"))
    with Image.open(pages[0]) as cover:
        assert cover.convert("RGB").getpixel((10, 10)) != (7, 20, 72)
    for internal_page in pages[1:]:
        with Image.open(internal_page) as page:
            assert page.convert("RGB").getpixel((10, 10)) == (7, 20, 72)


def test_generate_approved_report_paginates_additional_disciplines(tmp_path: Path) -> None:
    output = tmp_path / "relatorio-com-doze-disciplinas.pdf"

    generate_approved_report(approved_mock_data(discipline_count=12), output)

    assert len(PdfReader(output).pages) == 8


def test_panorama_uses_dark_canvas_shared_accents_and_white_card_text() -> None:
    page = generate_panorama(approved_mock_data()).convert("RGB")

    assert page.getpixel((10, 10)) == (7, 20, 72)
    assert page.getpixel((200, 350)) == page.getpixel((540, 1130))
    assert page.getpixel((1000, 350)) == page.getpixel((828, 619))
    for left in (76, 354, 632, 910):
        card = page.crop((left, 306, left + 254, 474))
        white_pixels = sum(pixel == (255, 255, 255) for pixel in card.getdata())
        assert white_pixels > 200


def test_panorama_finishing_uses_one_column_white_labels_and_blue_week_bars() -> None:
    page = generate_panorama(approved_mock_data()).convert("RGB")

    panel_fill = page.getpixel((130, 700))
    assert page.getpixel((130, 1100)) == panel_fill
    assert page.getpixel((130, 1400)) == panel_fill

    assert all(
        page.getpixel((left + 32, 336)) == (255, 255, 255)
        for left in (76, 354, 632, 910)
    )

    for label_box in ((340, 890, 485, 925), (750, 890, 905, 925)):
        label = page.crop(label_box)
        assert sum(pixel == (255, 255, 255) for pixel in label.getdata()) > 30

    week_bar_colors = [page.getpixel((center, 1458)) for center in (320, 520, 720, 920)]
    assert week_bar_colors == [(23, 104, 215)] * 4


def test_panorama_makes_weekly_study_copy_large_white_and_legible() -> None:
    page = generate_panorama(approved_mock_data()).convert("RGB")

    for box, minimum_white_pixels in (
        ((208, 1004, 470, 1046), 100),
        ((208, 1110, 520, 1154), 120),
        ((208, 1150, 500, 1198), 100),
        ((208, 1290, 590, 1338), 160),
    ):
        area = page.crop(box)
        white_pixels = sum(pixel == (255, 255, 255) for pixel in area.getdata())
        assert white_pixels > minimum_white_pixels

    copy_area = page.crop((208, 1100, 500, 1198))
    yellow_pixels = sum(pixel == (255, 181, 27) for pixel in copy_area.getdata())
    assert yellow_pixels == 0


def test_panorama_places_performance_detail_below_the_donut() -> None:
    page = generate_panorama(approved_mock_data()).convert("RGB")

    detail_area = page.crop((690, 852, 966, 892))
    white_pixels = sum(pixel == (255, 255, 255) for pixel in detail_area.getdata())

    assert white_pixels > 80


def test_questions_overview_uses_white_values_on_dark_metric_cards() -> None:
    page = generate_questions_overview(approved_mock_data()).convert("RGB")

    for left in (76, 352, 628, 904):
        value_area = page.crop((left + 20, 340, left + 230, 420))
        white_pixels = sum(pixel == (255, 255, 255) for pixel in value_area.getdata())
        assert white_pixels > 100


def test_questions_overview_uses_four_full_color_metric_cards() -> None:
    page = generate_questions_overview(approved_mock_data()).convert("RGB")

    fills = [page.getpixel((left + 12, 300)) for left in (76, 352, 628, 904)]
    assert fills == [
        (23, 104, 215),
        (118, 87, 215),
        (255, 80, 88),
        (255, 181, 27),
    ]


def test_questions_overview_ignores_empty_week_when_zero_accuracy_is_tied() -> None:
    payload = approved_mock_data()
    questions = payload["questions"]
    assert isinstance(questions, dict)
    questions["weekly"] = [
        {"label": "Semana 1", "correct": 0, "wrong": 0, "total": 0},
        {"label": "Semana 2", "correct": 0, "wrong": 8, "total": 8},
    ]

    values = questions_report_values(payload)

    assert values["best_week"] == 1
    assert values["weeks"][values["best_week"]]["accuracy"] == 0.0


def test_questions_overview_has_no_best_week_when_every_week_is_empty() -> None:
    payload = approved_mock_data()
    questions = payload["questions"]
    assert isinstance(questions, dict)
    questions["weekly"] = [
        {"label": "Semana 1", "correct": 0, "wrong": 0, "total": 0},
        {"label": "Semana 2", "correct": 0, "wrong": 0, "total": 0},
    ]

    values = questions_report_values(payload)

    assert values["best_week"] is None


def test_constancy_uses_white_days_card_and_high_contrast_progress_colors() -> None:
    page = generate_constancy(approved_mock_data()).convert("RGB")

    assert page.getpixel((92, 1086)) == (255, 255, 255)
    assert page.getpixel((126, 1228)) == (20, 196, 229)
    assert page.getpixel((994, 1228)) == (111, 140, 200)
    assert page.getpixel((680, 440)) == (255, 80, 88)
    assert page.getpixel((548, 914)) == (255, 181, 27)
    assert page.getpixel((206, 772)) == (118, 87, 215)


def test_constancy_keeps_the_four_approved_modalities_colors_and_order() -> None:
    payload = approved_mock_data()
    modalities = payload["modalities"]
    assert isinstance(modalities, dict)
    modalities["hours"] = {"Estudo": 8.0}
    modalities["total_hours"] = 8.0

    values = constancy_report_values(payload)

    assert values["modalities"] == [
        ("ESTUDO", 8.0, "8H", "#7657D7"),
        ("RESUMO", 0, "0H", "#14C4E5"),
        ("EXERCÍCIO", 0, "0H", "#1768D7"),
        ("REVISÃO", 0, "0H", "#FFB51B"),
    ]


def test_constancy_maps_legacy_modalities_into_the_approved_categories() -> None:
    payload = approved_mock_data()
    modalities = payload["modalities"]
    assert isinstance(modalities, dict)
    modalities["hours"] = {"Teoria": 9.5, "Questões": 7.0, "Revisão": 2.0}
    modalities["total_hours"] = 18.5
    summary = payload["summary"]
    assert isinstance(summary, dict)
    summary["total_hours"] = 18.5

    values = constancy_report_values(payload)

    assert values["modalities"] == [
        ("ESTUDO", 9.5, "9H30", "#7657D7"),
        ("RESUMO", 0, "0H", "#14C4E5"),
        ("EXERCÍCIO", 7.0, "7H", "#1768D7"),
        ("REVISÃO", 2.0, "2H", "#FFB51B"),
    ]
    assert values["modalities_total"] == 18.5
    assert values["uncategorized_modalities_total"] == 0


def test_constancy_counts_unknown_modalities_as_uncategorized() -> None:
    payload = approved_mock_data()
    modalities = payload["modalities"]
    assert isinstance(modalities, dict)
    modalities["hours"] = {"Estudo": 5.0, "Simulado": 3.0}
    modalities["total_hours"] = 8.0

    values = constancy_report_values(payload)

    assert values["modalities_total"] == 5.0
    assert values["uncategorized_modalities_total"] == 3.0


def test_constancy_emphasizes_modality_totals_and_details_in_white() -> None:
    page = generate_constancy(approved_mock_data()).convert("RGB")

    for box, minimum_white_pixels in (
        ((145, 808, 266, 879), 100),
        ((112, 954, 440, 996), 160),
    ):
        area = page.crop(box)
        white_pixels = sum(pixel == (255, 255, 255) for pixel in area.getdata())
        assert white_pixels > minimum_white_pixels


def test_constancy_places_modality_detail_below_the_segmented_ring() -> None:
    page = generate_constancy(approved_mock_data()).convert("RGB")

    detail_area = page.crop((145, 912, 267, 950))
    white_pixels = sum(pixel == (255, 255, 255) for pixel in detail_area.getdata())

    assert white_pixels > 40


def test_constancy_does_not_draw_false_progress_when_adherence_is_zero() -> None:
    payload = approved_mock_data()
    weekly = payload["weekly_evolution"]
    assert isinstance(weekly, dict)
    weekly["adherence_percent"] = 0.0

    page = generate_constancy(payload).convert("RGB")

    assert page.getpixel((566, 970)) == (248, 216, 121)


def test_cover_cleanup_removes_pale_antialiased_template_text() -> None:
    image = Image.new("RGBA", (700, 300), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(DISPLAY_PATH), size=132)
    circle_color = (235, 246, 255, 255)
    draw.rectangle((520, 0, 700, 300), fill=circle_color)
    draw.text(
        (72, 60),
        "LUIZA",
        font=font,
        fill=(8, 22, 79, 255),
        stroke_width=5,
        stroke_fill=(220, 225, 240, 255),
    )

    _erase_navy_text(image, (62, 50, 594, 220))

    cleaned = image.crop((62, 50, 500, 220)).convert("RGB")
    assert min(min(channel) for channel in cleaned.getextrema()) >= 250
    assert image.getpixel((560, 100)) == circle_color


def test_cover_preserves_template_name_when_only_period_changes() -> None:
    template = (
        Path(__file__).parents[2]
        / "src"
        / "kairos_report"
        / "pdf"
        / "assets"
        / "cover-template.png"
    )
    original = Image.open(template).convert("RGBA").resize((1240, 1754), Image.Resampling.LANCZOS)
    updated = generate_cover(
        {
            "identity": {
                "student_name": "Luiza",
                "period_start": "2026-08-01",
            }
        },
        template_path=template,
    )

    name_box = (62, 607, 594, 774)
    scale_x = 1240 / 1055
    scale_y = 1754 / 1491
    resized_box = tuple(
        round(value * (scale_x if index % 2 == 0 else scale_y))
        for index, value in enumerate(name_box)
    )
    difference = ImageChops.difference(
        original.crop(resized_box), updated.crop(resized_box)
    ).convert("RGB")
    assert difference.getbbox() is None


def test_default_cover_uses_approved_shark_template_without_extra_drawing() -> None:
    template = default_approved_assets().cover_template_path

    assert template.name == "cover-template-shark-natane-v2.png"

    original = Image.open(template).convert("RGBA").resize((1240, 1754), Image.Resampling.LANCZOS)
    generated = generate_cover(
        {
            "identity": {
                "student_name": "Luiza",
                "period_start": "2026-07-01",
            }
        },
        template_path=template,
    )
    difference = ImageChops.difference(original, generated).convert("RGB")

    assert difference.getbbox() is None


def test_cover_keeps_long_student_names_out_of_the_portrait_area() -> None:
    template = default_approved_assets().cover_template_path
    original = Image.open(template).convert("RGBA").resize((1240, 1754), Image.Resampling.LANCZOS)
    generated = generate_cover(
        {
            "identity": {
                "student_name": "Aluna Demonstração",
                "period_start": "2026-07-01",
            }
        },
        template_path=template,
    )

    portrait_guard = (700, 600, 1180, 900)
    difference = ImageChops.difference(
        original.crop(portrait_guard),
        generated.crop(portrait_guard),
    ).convert("RGB")

    assert difference.getbbox() is None


def _rendered_name_bbox(tmp_path: Path, student_name: str) -> tuple[int, int, int, int]:
    template = tmp_path / "blank-cover.png"
    blank = Image.new("RGBA", (1055, 1491), "white")
    blank.save(template)
    generated = generate_cover(
        {
            "identity": {
                "student_name": student_name,
                "period_start": "2026-07-01",
            }
        },
        template_path=template,
        template_student="TEMPLATE",
    ).convert("RGB")
    difference = ImageChops.difference(generated, Image.new("RGB", generated.size, "white"))
    bbox = difference.getbbox()
    assert bbox is not None
    return bbox


def _assert_name_bbox_is_reserved(bbox: tuple[int, int, int, int]) -> None:
    scale_x = 1240 / 1055
    scale_y = 1754 / 1491
    reserved = (
        round(72 * scale_x),
        round(604 * scale_y),
        round(552 * scale_x),
        round(774 * scale_y),
    )
    # LANCZOS may spread the first antialiased edge by one output pixel.
    assert bbox[0] >= reserved[0] - 2
    assert bbox[1] >= reserved[1]
    assert bbox[2] <= reserved[2]
    assert bbox[3] <= reserved[3]


def test_cover_wraps_long_common_name_inside_reserved_name_area(tmp_path: Path) -> None:
    bbox = _rendered_name_bbox(tmp_path, "Maria Eduarda de Almeida Santos")

    _assert_name_bbox_is_reserved(bbox)


def test_cover_shrinks_long_single_word_inside_reserved_name_area(tmp_path: Path) -> None:
    bbox = _rendered_name_bbox(tmp_path, "MariaEduardaDeAlmeidaSantos")

    _assert_name_bbox_is_reserved(bbox)
