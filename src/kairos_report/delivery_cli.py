"""Explicit prepare / approve / submit steps operated by Hermes."""

import json
from pathlib import Path
from typing import Annotated

import typer

from kairos_report.config import Settings
from kairos_report.runtime_delivery import (
    RuntimeClient,
    RuntimeDeliveryError,
    prepare,
    read_decisions,
    refresh_status,
    submit_plan,
    write_private,
)

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)


@app.command("catalog")
def catalog(output: Annotated[Path, typer.Option("--output")]) -> None:
    """Save the current template choices, field meanings and versions locally."""
    client = RuntimeClient.from_env()
    try:
        items = client.catalog()
        write_private(output, {"items": items})
        typer.echo(json.dumps({"output_path": str(output.resolve()), "templates": len(items)}))
    except RuntimeDeliveryError as exc:
        raise typer.BadParameter(str(exc)) from None
    finally:
        client.close()


@app.command("prepare")
def prepare_command(
    run_id: Annotated[int, typer.Option("--run")],
    decisions: Annotated[Path, typer.Option("--decisions")],
    output: Annotated[Path, typer.Option("--output")],
) -> None:
    """Validate Hermes' choices and freeze a private reviewable plan; does not send."""
    client = RuntimeClient.from_env()
    try:
        result = prepare(Settings.load(), client, run_id, read_decisions(decisions), output)
        typer.echo(json.dumps(result))
    except RuntimeDeliveryError as exc:
        raise typer.BadParameter(str(exc)) from None
    finally:
        client.close()


@app.command("submit")
def submit_command(
    plan: Annotated[Path, typer.Option("--plan")],
    approved_hash: Annotated[str | None, typer.Option("--approved-hash")] = None,
) -> None:
    """Register the exact reviewed plan in Runtime; registration is not delivery."""
    client = RuntimeClient.from_env()
    try:
        result = submit_plan(Settings.load(), client, plan, approved_hash)
        typer.echo(json.dumps(result))
    except RuntimeDeliveryError as exc:
        raise typer.BadParameter(str(exc)) from None
    finally:
        client.close()


@app.command("status")
def status(receipts: Annotated[Path, typer.Option("--receipts")]) -> None:
    """Refresh Runtime statuses; stdout contains aggregate counts only."""
    client = RuntimeClient.from_env()
    try:
        typer.echo(json.dumps(refresh_status(client, receipts)))
    except RuntimeDeliveryError as exc:
        raise typer.BadParameter(str(exc)) from None
    finally:
        client.close()
