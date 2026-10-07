"""Synthetic extraction-to-export tracer bullet, no operational database or network."""

import json
from datetime import date

import respx
from sqlalchemy import select

from kairos_report.config import Settings
from kairos_report.data.service import ReportDataService
from kairos_report.models import StudentReport
from kairos_report.tutory.client import ReportBundle, TutoryClient, TutoryStudent
from tests.integration.test_run_service import build_service
from tests.unit.test_topic_extraction import (
    ADMIN,
    APP,
    LAUNCH_PATH,
    launch_page,
    launch_row,
    mock_panel,
    scoped_question_html,
)


def test_normal_run_persists_and_exports_automatically_collected_topic_counts(
    test_settings: Settings,
) -> None:
    service, client = build_service(
        test_settings, [TutoryStudent(id="s1", name="Synthetic Example")]
    )
    old = client.generate_report_bundle.return_value
    client.generate_report_bundle.return_value = ReportBundle(
        key=old.key,
        documents={
            **old.documents,
            "questoes": scoped_question_html(),
            "lancamentos-questoes": "<table><tbody>"
            + launch_row("Disciplina fictícia", "Assunto fictício", "2026-08-03", 4, 3)
            + "</tbody></table>",
        },
    )
    run = service.create(date(2026, 8, 1), date(2026, 8, 31), "synthetic", "v1")
    service.extract(run.id, ["s1"])
    with service._sessions() as session:
        report = session.scalar(select(StudentReport).where(StudentReport.run_id == run.id))
        assert report is not None
        assert report.metrics["questions"]["topics"][0]["total"] == 4
        assert report.metrics["questions"]["topics"][0]["correct"] == 3
    result = ReportDataService(test_settings).export(run.id)
    record = json.loads(result.output_path.read_text())
    topic = record["data"]["questions"]["topics"][0]
    assert (topic["total"], topic["correct"], topic["wrong"]) == (4, 3, 1)
    assert topic["source_period"]["period_start"] == "2026-08-01"


@respx.mock
def test_http_pagination_to_run_database_and_export_without_manual_enrichment(
    test_settings: Settings,
) -> None:
    service, client = build_service(
        test_settings, [TutoryStudent(id="s1", name="Synthetic Example")]
    )
    documents = client.generate_report_bundle.return_value.documents
    mock_panel()
    row1 = launch_row("Disciplina fictícia", "Assunto fictício", "2026-08-03", 2, 2)
    row2 = launch_row("Disciplina fictícia", "Assunto fictício", "2026-08-04", 2, 1)
    respx.get(f"{APP}{LAUNCH_PATH}", params__eq={}).respond(200, text=launch_page(row1, last=2))
    respx.get(f"{APP}{LAUNCH_PATH}", params={"p": "2"}).respond(
        200, text=launch_page(row2, page=2, last=2)
    )
    respx.post(f"{ADMIN}/intent/cadastrar-relatorio-coach").respond(
        200, json={"result": True, "data": [{"id": "s1", "token": "synthetic-key"}]}
    )
    for model in ("desempenho", "questoes", "aluno"):
        respx.get(
            f"{ADMIN}/documentos/relatorios/{model}", params={"key": "synthetic-key"}
        ).respond(
            200,
            text=scoped_question_html()
            if model == "questoes"
            else "<h1>Relatório</h1>" + documents[model],
        )
    client.generate_report_bundle.side_effect = TutoryClient(test_settings).generate_report_bundle
    run = service.create(date(2026, 8, 1), date(2026, 8, 31), "synthetic", "v1")
    service.extract(run.id, ["s1"])
    result = ReportDataService(test_settings).export(run.id)
    assert result.ready == 1
    record = json.loads(result.output_path.read_text())
    topic = record["data"]["questions"]["topics"][0]
    assert (topic["total"], topic["correct"], topic["wrong"]) == (4, 3, 1)
    assert topic["execution_status"] == "recorded"
    assert len([c for c in respx.calls if c.request.url.path == LAUNCH_PATH]) == 2
