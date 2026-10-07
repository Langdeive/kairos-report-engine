import json
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from typer.testing import CliRunner

from kairos_report.cli import app
from kairos_report.tutory.client import ReportBundle
from tests.unit.test_cli import FixtureLiveTutoryClient
from tests.unit.test_topic_extraction import launch_row, scoped_question_html


def test_single_report_command_includes_automatic_topic_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class TopicClient(FixtureLiveTutoryClient):
        def generate_report_bundle(self, *args, **kwargs) -> ReportBundle:
            bundle = super().generate_report_bundle(*args, **kwargs)
            return ReportBundle(
                key=bundle.key,
                documents={
                    **bundle.documents,
                    "questoes": scoped_question_html(),
                    "lancamentos-questoes": "<table><tbody>"
                    + launch_row("Disciplina fictícia", "Assunto fictício", "2026-08-03", 4, 3)
                    + "</tbody></table>",
                },
            )

    monkeypatch.setenv("TUTORY_ACCOUNT", "synthetic")
    monkeypatch.setenv("TUTORY_PASSWORD", "synthetic")
    monkeypatch.setenv("KAIROS_DATA_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("KAIROS_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("kairos_report.cli.TutoryClient", TopicClient)
    monkeypatch.setattr(
        "kairos_report.cli.generate_approved_report", lambda data, output, **kw: output
    )
    output = tmp_path / "synthetic.json"
    result = CliRunner().invoke(
        app,
        [
            "report",
            "generate-live",
            "--month",
            "2026-08",
            "--student-id",
            "s1",
            "--output",
            str(tmp_path / "synthetic.pdf"),
            "--data-output",
            str(output),
        ],
    )
    assert result.exit_code == 0, result.exception
    topic = json.loads(output.read_text())["questions"]["topics"][0]
    assert (topic["total"], topic["correct"], topic["wrong"]) == (4, 3, 1)
