from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from calendar import monthrange
from datetime import date
from pathlib import Path

import typer

from kairos_report.config import Settings
from kairos_report.db import upgrade_database
from kairos_report.runs.service import RunService
from kairos_report.tutory.client import TutoryClient

app = typer.Typer(no_args_is_help=True)
run_app = typer.Typer(no_args_is_help=True)
app.add_typer(run_app, name="run")


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


@app.command()
def doctor() -> None:
    """Report local readiness without exposing credentials."""
    settings = Settings.load()
    payload = {
        "data_directory_writable": _is_writable(settings.data_dir),
        "database_path": str(settings.data_dir / "database" / "kairos.sqlite3"),
        "chromium_available": _chromium_available(),
        "approval_mode": settings.approval_mode,
        "retention_months": settings.retention_months,
    }
    typer.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _run_service() -> RunService:
    settings = Settings.load()
    upgrade_database(settings)
    return RunService(settings, TutoryClient(settings))


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
def run_extract(run_id: int = typer.Option(..., "--run")) -> None:
    """Extract every active student, safely resuming existing work."""
    summary = _run_service().extract(run_id)
    typer.echo(summary.model_dump_json())


@run_app.command("status")
def run_status(run_id: int = typer.Option(..., "--run")) -> None:
    """Return the persisted counters for one monthly run."""
    summary = _run_service().status(run_id)
    typer.echo(summary.model_dump_json())


if __name__ == "__main__":
    app()
