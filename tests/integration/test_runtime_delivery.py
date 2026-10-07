import hashlib
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from kairos_report.cli import app
from kairos_report.config import Settings
from kairos_report.data.service import ReportDataService
from kairos_report.runtime_delivery import (
    RuntimeClient,
    RuntimeDeliveryError,
    TemplateDecision,
    digest,
    prepare,
    read_decisions,
    refresh_status,
    submit_plan,
)
from tests.integration.test_delivery_manifest import prepared_run


class FakeRuntime:
    def __init__(self) -> None:
        self.templates: list[dict[str, Any]] = []
        self.calls: list[httpx.Request] = []
        self.requests: dict[str, dict[str, Any]] = {}
        self.fail_after_accept = False
        self.add_template(1)
        self.client = RuntimeClient(
            "http://runtime:8000", "t" * 32, transport=httpx.MockTransport(self.handle)
        )

    def add_template(self, template_id: int) -> None:
        self.templates.append(
            {
                "template_id": template_id,
                "channel_id": "channel",
                "version": "a" * 64,
                "document_required": True,
                "body": "Ola {{1}}, o relatorio registra {{2}} questoes!",
                "parameters": [
                    {"slot": "1", "name": "nome", "description": "Nome"},
                    {"slot": "2", "name": "questoes", "description": "Questoes"},
                ],
            }
        )

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        assert request.headers["Authorization"] == f"Bearer {'t' * 32}"
        if request.url.path.endswith("/templates"):
            return httpx.Response(200, json={"items": self.templates})
        if request.url.path.endswith("/documents"):
            assert request.headers["Content-Type"] == "application/pdf"
            return httpx.Response(
                201,
                json={
                    "document_id": "d" * 64,
                    "sha256": hashlib.sha256(request.content).hexdigest(),
                },
            )
        if request.method == "POST":
            body = json.loads(request.content)
            key = body["request_key"]
            if key in self.requests and self.requests[key] != body:
                return httpx.Response(409, json={"detail": "request_key_conflict"})
            self.requests[key] = body
            if self.fail_after_accept:
                self.fail_after_accept = False
                raise httpx.ReadTimeout("secret phone and token must not escape")
            return httpx.Response(202, json={"request_id": digest(key), "status": "pending"})
        return httpx.Response(200, json={"status": "delivered", "error": None})


def decision(template_id: int = 1) -> TemplateDecision:
    return TemplateDecision(
        report_id=1,
        channel_id="channel",
        template_id=template_id,
        template_version="a" * 64,
        parameters={"nome": "Ana", "questoes": "420"},
    )


def test_prepare_blocks_unverified_execution_before_plan_write(
    test_settings: Settings,
    tmp_path: Path,
) -> None:
    run_id = prepared_run(test_settings, tmp_path)
    runtime = FakeRuntime()
    runtime.templates[0]["body"] = "Você resolveu {{2}} questões, {{1}}!"
    plan = tmp_path / "blocked.json"
    exported = ReportDataService(test_settings).export_delivery(run_id)
    manifest_path = Path(str(exported["output_path"]))
    import os

    os.utime(manifest_path, ns=(1, 1))
    original_mtime = manifest_path.stat().st_mtime_ns
    with pytest.raises(RuntimeDeliveryError, match="execution_evidence_required"):
        prepare(test_settings, runtime.client, run_id, [decision()], plan)
    assert not plan.exists()
    assert manifest_path.stat().st_mtime_ns == original_mtime
    assert all(request.method == "GET" for request in runtime.calls)


def test_submit_revalidates_legacy_plan_before_upload(
    test_settings: Settings,
    tmp_path: Path,
) -> None:
    run_id = prepared_run(test_settings, tmp_path)
    runtime = FakeRuntime()
    plan = tmp_path / "legacy.json"
    prepare(test_settings, runtime.client, run_id, [decision()], plan)
    envelope = json.loads(plan.read_text())
    # Synthetic formerly approved plan; not an operational frozen artifact.
    runtime.templates[0]["body"] = "Você resolveu {{2}} questões, {{1}}!"
    envelope["plan"]["items"][0]["preview"] = "Você resolveu 420 questões, Ana!"
    envelope["plan_hash"] = digest(envelope["plan"])
    plan.write_text(json.dumps(envelope))
    before = plan.read_bytes()
    with pytest.raises(RuntimeDeliveryError, match="execution_evidence_required"):
        submit_plan(test_settings, runtime.client, plan, envelope["plan_hash"])
    assert plan.read_bytes() == before
    assert all(request.method == "GET" for request in runtime.calls)


def test_declared_claims_cannot_supply_their_own_evidence(
    test_settings: Settings,
    tmp_path: Path,
) -> None:
    run_id = prepared_run(test_settings, tmp_path)
    runtime = FakeRuntime()
    declared = TemplateDecision.model_validate(
        decision().model_dump()
        | {
            "analysis_claims": [{"kind": "practice"}],
        }
    )
    with pytest.raises(RuntimeDeliveryError, match="execution_evidence_required"):
        prepare(test_settings, runtime.client, run_id, [declared], tmp_path / "blocked.json")
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TemplateDecision.model_validate(declared.model_dump() | {"verified_evidence": []})


def test_prepare_and_submit_with_explicit_test_destination_uses_override(
    test_settings: Settings,
    tmp_path: Path,
) -> None:
    run_id = prepared_run(test_settings, tmp_path)
    runtime = FakeRuntime()
    plan = tmp_path / "test-plan.json"
    destination = "5511888888888"

    result = prepare(
        test_settings,
        runtime.client,
        run_id,
        [decision()],
        plan,
        test_destination=destination,
    )

    frozen = json.loads(plan.read_text())["plan"]
    assert frozen["test_destination"] == destination
    assert frozen["items"][0]["request_key"].startswith("test:")

    submit_plan(test_settings, runtime.client, plan, result["plan_hash"])
    request = next(iter(runtime.requests.values()))
    assert request["phone"] == destination


def test_test_destination_request_key_changes_with_template_content(
    test_settings: Settings,
    tmp_path: Path,
) -> None:
    run_id = prepared_run(test_settings, tmp_path)
    runtime = FakeRuntime()
    destination = "5511888888888"
    first = prepare(
        test_settings,
        runtime.client,
        run_id,
        [decision()],
        tmp_path / "first.json",
        test_destination=destination,
    )
    changed = decision()
    changed.parameters["questoes"] = "421"
    second = prepare(
        test_settings,
        runtime.client,
        run_id,
        [changed],
        tmp_path / "second.json",
        test_destination=destination,
    )
    first_plan = json.loads((tmp_path / "first.json").read_text())["plan"]
    second_plan = json.loads((tmp_path / "second.json").read_text())["plan"]
    first_key = first_plan["items"][0]["request_key"]
    second_key = second_plan["items"][0]["request_key"]

    assert first["plan_hash"] != second["plan_hash"]
    assert first_key != second_key


def test_prepare_and_submit_uses_existing_identity_and_requires_exact_approval(
    test_settings: Settings,
    tmp_path: Path,
) -> None:
    run_id = prepared_run(test_settings, tmp_path)
    runtime = FakeRuntime()
    plan = tmp_path / "plan.json"
    result = prepare(test_settings, runtime.client, run_id, [decision()], plan)
    assert result["prepared"] == 1 and result["submitted"] == 0 and result["unselected"] == 1
    assert all(request.method == "GET" for request in runtime.calls)
    frozen = json.loads(plan.read_text())["plan"]["items"][0]
    assert "Ana" in frozen["preview"] and "420" in frozen["preview"]
    assert frozen["report"]["report_data"]["summary"]
    with pytest.raises(RuntimeDeliveryError, match="approval_required_for_exact_plan_hash"):
        submit_plan(test_settings, runtime.client, plan)
    response = submit_plan(test_settings, runtime.client, plan, result["plan_hash"])
    assert response["registered"] == 1
    request = next(iter(runtime.requests.values()))
    assert request["phone"] == "5511999991234"
    assert request["parameters"] == {"nome": "Ana", "questoes": "420"}
    assert request["document_id"] == "d" * 64
    submit_plan(test_settings, runtime.client, plan, result["plan_hash"])
    assert (
        len([r for r in runtime.calls if r.method == "POST" and r.url.path.endswith("/requests")])
        == 1
    )
    status = refresh_status(runtime.client, Path(response["receipts_path"]))
    assert status == {"total": 1, "statuses": {"delivered": 1}}
    # Report generation state is not incorrectly counted as a WhatsApp send.
    assert ReportDataService(test_settings).export_delivery(run_id)["ready"] == 1


@pytest.mark.parametrize("template_id", [1, 2, 3])
def test_new_catalog_templates_need_no_code_change(
    test_settings: Settings,
    tmp_path: Path,
    template_id: int,
) -> None:
    run_id = prepared_run(test_settings, tmp_path)
    runtime = FakeRuntime()
    runtime.add_template(2)
    runtime.add_template(3)
    result = prepare(
        test_settings, runtime.client, run_id, [decision(template_id)], tmp_path / "plan.json"
    )
    assert result["prepared"] == 1


@pytest.mark.parametrize("problem", ["pdf_changed", "template_changed", "plan_changed"])
@pytest.mark.parametrize("approval_mode", ["required", "automatic"])
def test_changes_block_before_any_upload(
    test_settings: Settings,
    tmp_path: Path,
    problem: str,
    approval_mode: str,
) -> None:
    test_settings = test_settings.model_copy(update={"approval_mode": approval_mode})
    run_id = prepared_run(test_settings, tmp_path)
    runtime = FakeRuntime()
    plan = tmp_path / "plan.json"
    result = prepare(test_settings, runtime.client, run_id, [decision()], plan)
    if problem == "pdf_changed":
        (tmp_path / "report-1.pdf").write_bytes(b"wrong")
    elif problem == "template_changed":
        runtime.templates[0]["version"] = "b" * 64
    else:
        value = json.loads(plan.read_text())
        value["plan"]["items"][0]["decision"]["parameters"]["nome"] = "Another student"
        plan.write_text(json.dumps(value))
    with pytest.raises(RuntimeDeliveryError):
        submit_plan(test_settings, runtime.client, plan, result["plan_hash"])
    assert all(request.method == "GET" for request in runtime.calls)


@pytest.mark.parametrize("approval_mode", ["required", "automatic"])
def test_uncertain_registration_reuses_same_request_and_pdf(
    test_settings: Settings,
    tmp_path: Path,
    approval_mode: str,
) -> None:
    test_settings = test_settings.model_copy(update={"approval_mode": approval_mode})
    run_id = prepared_run(test_settings, tmp_path)
    runtime = FakeRuntime()
    plan = tmp_path / "plan.json"
    result = prepare(test_settings, runtime.client, run_id, [decision()], plan)
    runtime.fail_after_accept = True
    with pytest.raises(RuntimeDeliveryError, match="runtime_unreachable_retry_same_plan"):
        submit_plan(test_settings, runtime.client, plan, result["plan_hash"])
    submit_plan(test_settings, runtime.client, plan, result["plan_hash"])
    assert len(runtime.requests) == 1


def test_automatic_mode_is_explicit_configuration(test_settings: Settings, tmp_path: Path) -> None:
    run_id = prepared_run(test_settings, tmp_path)
    runtime = FakeRuntime()
    plan = tmp_path / "plan.json"
    prepare(test_settings, runtime.client, run_id, [decision()], plan)
    assert (
        submit_plan(
            test_settings.model_copy(update={"approval_mode": "automatic"}), runtime.client, plan
        )["registered"]
        == 1
    )


def test_catalog_cli_has_only_counts_in_stdout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = FakeRuntime()
    monkeypatch.setattr(RuntimeClient, "from_env", lambda: runtime.client)
    result = CliRunner().invoke(app, ["delivery", "catalog", "--output", str(tmp_path / "c.json")])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["templates"] == 1
    assert "Authorization" not in result.stdout and "questoes" not in result.stdout


def test_invalid_choices_and_duplicate_reports_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "decisions.json"
    for content in [[], [decision().model_dump()] * 2, [{"report_id": "invalid"}]]:
        path.write_text(json.dumps(content))
        with pytest.raises(RuntimeDeliveryError):
            read_decisions(path)


def test_remote_error_does_not_expose_personal_data_or_tokens() -> None:
    client = RuntimeClient(
        "http://runtime:8000",
        "t" * 32,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(422, json={"detail": [{"input": "SECRET"}]})
        ),
    )
    with pytest.raises(RuntimeDeliveryError, match="^runtime_http_422$"):
        client.catalog()


@pytest.mark.parametrize(
    "url",
    [
        "https://user:secret@runtime",
        "https://runtime/?token=secret",
        "file:///data",
        "https://runtime/#token",
    ],
)
def test_credentials_cannot_be_embedded_in_url(url: str) -> None:
    with pytest.raises(RuntimeDeliveryError, match="runtime_configuration_invalid"):
        RuntimeClient(url, "t" * 32)
