from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from kairos_report.report_data import ReportDataPackage


@dataclass(frozen=True)
class ApprovedReportAssets:
    """Ativos que pertencem à identidade visual, não aos dados do aluno."""

    logo_path: Path
    cover_template_path: Path
    font_dir: Path
    cover_template_student: str = "LUIZA"
    cover_template_period: str = "2026-07"

    def validate(self) -> None:
        required = [
            self.logo_path,
            self.cover_template_path,
            self.font_dir / "InstrumentSans-Regular.ttf",
            self.font_dir / "InstrumentSans-Bold.ttf",
            self.font_dir / "BigShoulders-Bold.ttf",
        ]
        missing = [path for path in required if not path.is_file()]
        if missing:
            joined = ", ".join(str(path) for path in missing)
            raise FileNotFoundError(f"Ativos visuais ausentes: {joined}")


def default_approved_assets() -> ApprovedReportAssets:
    asset_dir = Path(__file__).with_name("assets")
    return ApprovedReportAssets(
        logo_path=asset_dir / "logo.png",
        cover_template_path=asset_dir / "cover-template-shark-natane-v2.png",
        font_dir=asset_dir / "fonts",
    )


def _payload(data: ReportDataPackage | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(data, ReportDataPackage):
        return data.model_dump(mode="json")
    return dict(data)


def _page_name(index: int) -> str:
    approved_numbers = [1, 2, 4, 5, 6]
    visual_number = approved_numbers[index] if index < len(approved_numbers) else index + 2
    return f"pagina-{visual_number:02d}.png"


def generate_approved_report(
    data: ReportDataPackage | Mapping[str, Any],
    output_path: Path,
    *,
    assets: ApprovedReportAssets | None = None,
    preview_dir: Path | None = None,
) -> Path:
    """Renderiza o relatório com os layouts aprovados e cria um único PDF."""
    assets = assets or default_approved_assets()
    assets.validate()
    payload = _payload(data)
    from kairos_report.pdf.layouts import empty_states
    from kairos_report.pdf.layouts import generate_panorama_variants as base
    from kairos_report.pdf.layouts.generate_approved_constancy import (
        generate as constancy_page,
    )
    from kairos_report.pdf.layouts.generate_approved_cover import generate as cover_page
    from kairos_report.pdf.layouts.generate_approved_discipline_map import (
        generate_pages as map_pages,
    )
    from kairos_report.pdf.layouts.generate_approved_panorama import (
        generate as panorama_page,
    )
    from kairos_report.pdf.layouts.generate_approved_question_priorities import (
        generate as priorities_page,
    )
    from kairos_report.pdf.layouts.generate_approved_questions_overview import (
        generate as questions_page,
    )

    base.configure_assets(logo_path=assets.logo_path, font_dir=assets.font_dir)
    pages = [
        cover_page(
            payload,
            template_path=assets.cover_template_path,
            template_student=assets.cover_template_student,
            template_period=assets.cover_template_period,
        ),
        panorama_page(payload),
        (
            constancy_page(payload)
            if payload["summary"]["total_hours"] > 0
            else empty_states.page(payload, "CONSTÂNCIA E TEMPO", empty_states.NO_STUDY)
        ),
    ]
    questions = payload.get("questions")
    if questions is None or questions["total"] == 0:
        pages.append(
            empty_states.page(
                payload,
                "PANORAMA DE QUESTÕES",
                empty_states.MISSING_QUESTIONS if questions is None else empty_states.NO_QUESTIONS,
            )
        )
    else:
        pages.append(questions_page(payload))
        if any(item["total"] >= 10 for item in questions["disciplines"]):
            pages.extend([priorities_page(payload), *map_pages(payload)])
        else:
            pages.append(
                empty_states.page(
                    payload,
                    "ANÁLISE POR DISCIPLINA",
                    "Sem disciplinas com 10 ou mais questões para classificar o desempenho.",
                )
            )

    rgb_pages: list[Image.Image] = []
    for page in pages:
        if page.size != (base.WIDTH, base.HEIGHT):
            raise ValueError(f"Página fora do tamanho aprovado: {page.size}")
        rgb_pages.append(page.convert("RGB"))

    if preview_dir is not None:
        preview_dir.mkdir(parents=True, exist_ok=True)
        for index, page in enumerate(rgb_pages):
            page.save(preview_dir / _page_name(index), quality=96, optimize=True)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(f".{output_path.name}.building")
    rgb_pages[0].save(
        temporary_path,
        format="PDF",
        resolution=150.0,
        save_all=True,
        append_images=rgb_pages[1:],
        title=f"Relatório mensal - {payload['identity']['student_name']}",
        author="Kairós Mentorias",
    )
    temporary_path.replace(output_path)
    return output_path
