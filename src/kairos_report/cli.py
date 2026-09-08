from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from calendar import monthrange
from datetime import date
from pathlib import Path
from typing import Annotated

import typer

from kairos_report.config import Settings
from kairos_report.data.service import ReportDataService
from kairos_report.db import upgrade_database
from kairos_report.errors import KairosReportError
from kairos_report.pdf import (
    ApprovedReportAssets,
    default_approved_assets,
    generate_approved_report,
)
from kairos_report.report_data import ReportDataPackage, build_report_data
from kairos_report.runs.service import RunService
from kairos_report.tutory.client import TutoryClient
from kairos_report.tutory.parser import (
    parse_question_report,
    parse_report,
    parse_student_activity_report,
)

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)
run_app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)
data_app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)
report_app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)
app.add_typer(run_app, name="run")
app.add_typer(data_app, name="data")
app.add_typer(report_app, name="report")


@app.command()
def version() -> None:
    """Print the installed application version."""
    from kairos_report import __version__

    typer.echo(__version__)


def _is_writable(directory: Path) -> bool:
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=directory):
            pass
    except OSError:
        return False
    return True


def _chromium_available() -> bool:
    try:
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "--list"],
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and "chromium" in result.stdout.lower()


def _approved_pdf_assets_ready() -> bool:
    try:
        default_approved_assets().validate()
    except (FileNotFoundError, OSError):
        return False
    return True


@app.command()
def doctor() -> None:
    """Report local readiness without exposing credentials."""
    settings = Settings.load()
    payload = {
        "data_directory_writable": _is_writable(settings.data_dir),
        "database_path": str(settings.data_dir / "database" / "kairos.sqlite3"),
        "approved_pdf_assets_ready": _approved_pdf_assets_ready(),
        "chromium_required": False,
        "chromium_available": _chromium_available(),
        "approval_mode": settings.approval_mode,
        "retention_months": settings.retention_months,
    }
    typer.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _run_service() -> RunService:
    settings = Settings.load()
    upgrade_database(settings)
    return RunService(settings, TutoryClient(settings))


def _data_service() -> ReportDataService:
    settings = Settings.load()
    upgrade_database(settings)
    return ReportDataService(settings)


@run_app.command("create")
def run_create(month: str = typer.Option(..., "--month")) -> None:
    """Create a frozen monthly report run."""
    try:
        year, month_number = (int(part) for part in month.split("-", maxsplit=1))
        period_start = date(year, month_number, 1)
    except (TypeError, ValueError) as exc:
        raise typer.BadParameter("month must use YYYY-MM") from exc
    period_end = date(year, month_number, monthrange(year, month_number)[1])
    run = _run_service().create(
        period_start,
        period_end,
        os.getenv("KAIROS_CODE_VERSION", "dev"),
        os.getenv("KAIROS_TEMPLATE_VERSION", "v1"),
    )
    typer.echo(json.dumps({"run_id": run.id, "status": run.status.value}, sort_keys=True))


@run_app.command("extract")
def run_extract(
    run_id: int = typer.Option(..., "--run"),
    student_ids: Annotated[list[str] | None, typer.Option("--student")] = None,
) -> None:
    """Extract every active student, safely resuming existing work."""
    try:
        summary = _run_service().extract(run_id, student_ids)
    except (KairosReportError, ValueError) as exc:
        typer.echo(f"Error: {exc}")
        raise typer.Exit(code=1) from None
    typer.echo(summary.model_dump_json())


@run_app.command("status")
def run_status(run_id: int = typer.Option(..., "--run")) -> None:
    """Return the persisted counters for one monthly run."""
    summary = _run_service().status(run_id)
    typer.echo(summary.model_dump_json())


@data_app.command("export")
def data_export(
    run_id: int = typer.Option(..., "--run"),
    output: Annotated[Path | None, typer.Option("--output")] = None,
) -> None:
    """Export one complete, layout-independent data record per student."""
    result = _data_service().export(run_id, output)
    typer.echo(result.model_dump_json())


@report_app.command("generate")
def report_generate(
    input_path: Annotated[Path, typer.Option("--input", exists=True, file_okay=True)],
    output: Annotated[Path, typer.Option("--output", dir_okay=False)],
    logo: Annotated[Path | None, typer.Option("--logo")] = None,
    cover_template: Annotated[Path | None, typer.Option("--cover-template")] = None,
    font_dir: Annotated[Path | None, typer.Option("--font-dir")] = None,
    cover_template_student: str = typer.Option("LUIZA", "--cover-template-student"),
    cover_template_period: str = typer.Option("2026-07", "--cover-template-period"),
    previews: Annotated[Path | None, typer.Option("--previews")] = None,
) -> None:
    """Generate one PDF using the approved Kairós layouts."""
    data = ReportDataPackage.model_validate_json(input_path.read_text(encoding="utf-8"))
    bundled = default_approved_assets()
    result = generate_approved_report(
        data,
        output,
        assets=ApprovedReportAssets(
            logo_path=logo or bundled.logo_path,
            cover_template_path=cover_template or bundled.cover_template_path,
            font_dir=font_dir or bundled.font_dir,
            cover_template_student=cover_template_student,
            cover_template_period=cover_template_period,
        ),
        preview_dir=previews,
    )
    typer.echo(str(result))


@data_app.command("export-delivery")
def data_export_delivery(
    run_id: int = typer.Option(..., "--run"),
    output: Annotated[Path | None, typer.Option("--output")] = None,
) -> None:
    """Write the private phone/PDF manifest for Hermes; stdout contains counts only."""
    result = _data_service().export_delivery(run_id, output)
    typer.echo(json.dumps(result, ensure_ascii=False, sort_keys=True))


@report_app.command("generate-batch")
def report_generate_batch(
    run_id: int = typer.Option(..., "--run"),
    output_dir: Annotated[Path | None, typer.Option("--output-dir")] = None,
) -> None:
    """Generate approved-layout review PDFs for the persisted batch."""
    result = _data_service().generate(run_id, output_dir)
    typer.echo(json.dumps(result, ensure_ascii=False, sort_keys=True))


@report_app.command("generate-live")
def report_generate_live(
    output: Annotated[Path, typer.Option("--output", dir_okay=False)],
    data_output: Annotated[Path, typer.Option("--data-output", dir_okay=False)],
    month: str = typer.Option(..., "--month"),
    student_id: str = typer.Option(..., "--student-id"),
    previews: Annotated[Path | None, typer.Option("--previews")] = None,
) -> None:
    """Fetch one real student and generate the approved report in one flow."""
    try:
        year, month_number = (int(part) for part in month.split("-", maxsplit=1))
        period_start = date(year, month_number, 1)
    except (TypeError, ValueError) as exc:
        raise typer.BadParameter("month must use YYYY-MM") from exc
    period_end = date(year, month_number, monthrange(year, month_number)[1])

    settings = Settings.load()
    bundle = TutoryClient(settings).generate_report_bundle(
        student_id,
        period_start,
        period_end,
        models=("desempenho", "questoes", "aluno"),
        grouping="dia",
    )
    metrics = parse_report(bundle.documents["desempenho"],
                           period_start=period_start, period_end=period_end)
    package = build_report_data(
        report_id=1,
        period_start=period_start,
        period_end=period_end,
        metrics=metrics,
        questions=parse_question_report(bundle.documents["questoes"],
                                         period_start=period_start, period_end=period_end),
        student_activity=parse_student_activity_report(bundle.documents["aluno"]),
        require_monthly_source=True,
    )

    data_output.parent.mkdir(parents=True, exist_ok=True)
    data_output.write_text(package.model_dump_json(indent=2), encoding="utf-8")
    result = generate_approved_report(
        package,
        output,
        assets=default_approved_assets(),
        preview_dir=previews,
    )
    typer.echo(
        json.dumps(
            {"data_path": str(data_output), "pdf_path": str(result)},
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    app()
