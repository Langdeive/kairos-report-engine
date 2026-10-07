"""Runtime delivery client. Extraction and PDF generation remain independent."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from kairos_report.analysis_provenance import AnalysisClaim, ProvenanceError, validate_analysis
from kairos_report.config import Settings
from kairos_report.data.service import ReportDataService
from kairos_report.errors import KairosReportError


class RuntimeDeliveryError(KairosReportError):
    """Only sanitized error codes cross the CLI boundary."""


def digest(value: object) -> str:
    content = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(content.encode()).hexdigest()


def render_preview(body: str, slots: dict[str, str]) -> str:
    return re.sub(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", lambda m: slots[m[1]], body)


def write_private(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False
    ) as temporary:
        json.dump(value, temporary, ensure_ascii=False, indent=2)
        temporary_path = Path(temporary.name)
    temporary_path.replace(path)


class RuntimeClient:
    def __init__(self, url: str, token: str, *, transport: httpx.BaseTransport | None = None):
        parsed = urlsplit(url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
            or len(token) < 32
        ):
            raise RuntimeDeliveryError("runtime_configuration_invalid")
        self.url = url.rstrip("/")
        self._client = httpx.Client(
            base_url=f"{self.url}/integrations/deliveries/v1/",
            headers={"Authorization": f"Bearer {token}"},
            timeout=60,
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        )

    @classmethod
    def from_env(cls) -> RuntimeClient:
        return cls(os.getenv("KAIROS_RUNTIME_URL", ""), os.getenv("KAIROS_RUNTIME_TOKEN", ""))

    def close(self) -> None:
        self._client.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.HTTPError:
            raise RuntimeDeliveryError("runtime_unreachable_retry_same_plan") from None
        if not response.is_success:
            code = f"runtime_http_{response.status_code}"
            try:
                detail = response.json().get("detail")
                if isinstance(detail, str) and re.fullmatch(r"[a-z_]{1,100}", detail):
                    code = detail
            except (ValueError, AttributeError):
                pass
            raise RuntimeDeliveryError(code)
        try:
            value = response.json()
        except ValueError:
            raise RuntimeDeliveryError("runtime_invalid_response") from None
        if not isinstance(value, dict):
            raise RuntimeDeliveryError("runtime_invalid_response")
        return value

    def catalog(self) -> list[dict[str, Any]]:
        items = self._request("GET", "templates").get("items")
        if not isinstance(items, list) or not all(isinstance(i, dict) for i in items):
            raise RuntimeDeliveryError("runtime_invalid_catalog")
        return items

    def upload(self, data: bytes) -> dict[str, Any]:
        return self._request(
            "POST", "documents", content=data, headers={"Content-Type": "application/pdf"}
        )

    def submit(self, request: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "requests", json=request)

    def status(self, request_id: str) -> dict[str, Any]:
        if not re.fullmatch(r"[a-f0-9]{64}", request_id):
            raise RuntimeDeliveryError("invalid_request_id")
        return self._request("GET", f"requests/{quote(request_id, safe='')}")


class TemplateDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    report_id: int = Field(gt=0)
    channel_id: str = Field(min_length=1)
    template_id: int = Field(gt=0)
    template_version: str = Field(pattern=r"^[a-f0-9]{64}$")
    parameters: dict[str, str]
    analysis_claims: list[AnalysisClaim] = Field(default_factory=list)


def validate_decision_analysis(
    decision: TemplateDecision,
    report: dict[str, Any],
    preview: str,
) -> None:
    """Public seam for draft/review; never accept evidence from decision authors."""
    try:
        validate_analysis(preview, report.get("report_data") or {}, claims=decision.analysis_claims)
    except ProvenanceError as exc:
        raise RuntimeDeliveryError(str(exc)) from None


def read_decisions(path: Path) -> list[TemplateDecision]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        decisions = [TemplateDecision.model_validate(item) for item in raw]
    except (OSError, ValueError, TypeError, ValidationError):
        raise RuntimeDeliveryError("invalid_decisions_file") from None
    if not decisions or len({d.report_id for d in decisions}) != len(decisions):
        raise RuntimeDeliveryError("empty_or_duplicate_decisions")
    return decisions


def current_manifest(settings: Settings, run_id: int) -> dict[int, dict[str, Any]]:
    manifest = ReportDataService(settings).export_delivery(run_id, write_manifest=False)
    items = manifest["items"]
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        raise RuntimeDeliveryError("invalid_manifest")
    return {item["report_id"]: item for item in items}


def validate_test_destination(value: str) -> str:
    if not re.fullmatch(r"\d{10,15}", value):
        raise RuntimeDeliveryError("invalid_test_destination")
    return value


def choose_template(decision: TemplateDecision, catalog: list[dict[str, Any]]) -> dict[str, Any]:
    template = next(
        (
            t
            for t in catalog
            if t["template_id"] == decision.template_id and t["channel_id"] == decision.channel_id
        ),
        None,
    )
    if not template or template["version"] != decision.template_version:
        raise RuntimeDeliveryError("template_unavailable_or_changed")
    if not template["document_required"]:
        raise RuntimeDeliveryError("report_requires_document_template")
    expected = {p["name"] for p in template["parameters"]}
    if set(decision.parameters) != expected:
        raise RuntimeDeliveryError("template_parameters_mismatch")
    if any(
        not v.strip() or len(v) > 1024 or any(c in v for c in "\r\n\t")
        for v in decision.parameters.values()
    ):
        raise RuntimeDeliveryError("invalid_template_parameter_value")
    return template


def prepare(
    settings: Settings,
    client: RuntimeClient,
    run_id: int,
    decisions: list[TemplateDecision],
    output: Path,
    *,
    test_destination: str | None = None,
) -> dict[str, Any]:
    if test_destination is not None:
        test_destination = validate_test_destination(test_destination)
        if len(decisions) != 1:
            raise RuntimeDeliveryError("test_destination_requires_single_report")
    manifest, catalog = current_manifest(settings, run_id), client.catalog()
    if not decisions or len({d.report_id for d in decisions}) != len(decisions):
        raise RuntimeDeliveryError("empty_or_duplicate_decisions")
    items = []
    for decision in decisions:
        report = manifest.get(decision.report_id)
        if not report or not report["ready_for_hermes"]:
            raise RuntimeDeliveryError("report_not_ready")
        template = choose_template(decision, catalog)
        identity = [report[k] for k in ("student_id", "period_start", "period_end", "revision")]
        test_request_identity = {
            "report": identity,
            "destination": test_destination,
            "template_id": decision.template_id,
            "template_version": decision.template_version,
            "parameters": decision.parameters,
            "pdf_sha256": report["pdf_sha256"],
        }
        request_key = (
            f"test:{digest(test_request_identity)}"
            if test_destination is not None
            else f"report:{digest(identity)}"
        )
        slots = {p["slot"]: decision.parameters[p["name"]] for p in template["parameters"]}
        preview = render_preview(template["body"], slots)
        validate_decision_analysis(decision, report, preview)
        items.append(
            {
                "decision": decision.model_dump(),
                "report": report,
                "request_key": request_key,
                "preview": preview,
            }
        )
    plan = {
        "schema_version": "1.0",
        "runtime_url": client.url,
        "run_id": run_id,
        "items": items,
        "test_destination": test_destination,
    }
    plan_hash = digest(plan)
    write_private(output, {"plan": plan, "plan_hash": plan_hash})
    return {
        "output_path": str(output.resolve()),
        "plan_hash": plan_hash,
        "prepared": len(items),
        "unselected": len(manifest) - len(items),
        "submitted": 0,
    }


def submit_plan(
    settings: Settings, client: RuntimeClient, path: Path, approved_hash: str | None = None
) -> dict[str, Any]:
    try:
        envelope = json.loads(path.read_text(encoding="utf-8"))
        plan, plan_hash = envelope["plan"], envelope["plan_hash"]
        if digest(plan) != plan_hash or plan["runtime_url"] != client.url:
            raise RuntimeDeliveryError("plan_changed_or_wrong_runtime")
        if settings.approval_mode == "required" and approved_hash != plan_hash:
            raise RuntimeDeliveryError("approval_required_for_exact_plan_hash")
        items = plan["items"]
        test_destination = plan.get("test_destination")
        if test_destination is not None:
            test_destination = validate_test_destination(test_destination)
            if len(items) != 1:
                raise RuntimeDeliveryError("test_destination_requires_single_report")
        manifest = current_manifest(settings, plan["run_id"])
        catalog = client.catalog()
        # Validate the whole selection before the first network mutation.
        for item in items:
            decision = TemplateDecision.model_validate(item["decision"])
            template = choose_template(decision, catalog)
            actual = manifest.get(decision.report_id)
            frozen = item["report"]
            if not actual or not actual["ready_for_hermes"]:
                raise RuntimeDeliveryError("report_not_ready")
            slots = {p["slot"]: decision.parameters[p["name"]] for p in template["parameters"]}
            preview = render_preview(template["body"], slots)
            validate_decision_analysis(decision, actual, preview)
            validate_decision_analysis(decision, actual, item["preview"])
            for field in (
                "student_id",
                "phone",
                "period_start",
                "period_end",
                "revision",
                "pdf_path",
                "pdf_sha256",
                "report_data",
            ):
                if actual[field] != frozen[field]:
                    raise RuntimeDeliveryError("report_changed_since_preparation")
    except (KeyError, TypeError, ValueError, OSError):
        raise RuntimeDeliveryError("invalid_plan") from None

    receipts_path = path.with_suffix(".receipts.json")
    receipts: dict[str, Any] = {"plan_hash": plan_hash, "items": []}
    if receipts_path.exists():
        receipts = json.loads(receipts_path.read_text(encoding="utf-8"))
        if receipts.get("plan_hash") != plan_hash:
            raise RuntimeDeliveryError("receipts_plan_conflict")
    known = {item["request_key"]: item for item in receipts["items"]}
    for item in items:
        key, report = item["request_key"], item["report"]
        if key in known:
            continue
        data = Path(report["pdf_path"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != report["pdf_sha256"]:
            raise RuntimeDeliveryError("pdf_changed_before_upload")
        uploaded = client.upload(data)
        if uploaded.get("sha256") != report["pdf_sha256"]:
            raise RuntimeDeliveryError("uploaded_pdf_hash_mismatch")
        decision = item["decision"]
        request = {
            "request_key": key,
            "batch_id": f"reports:{report['period_start']}:{report['period_end']}",
            "channel_id": decision["channel_id"],
            "phone": test_destination or report["phone"],
            "recipient_name": report["student_name"],
            "template_id": decision["template_id"],
            "template_version": decision["template_version"],
            "parameters": decision["parameters"],
            "document_id": uploaded["document_id"],
        }
        result = client.submit(request)
        if not re.fullmatch(r"[a-f0-9]{64}", str(result.get("request_id", ""))):
            raise RuntimeDeliveryError("runtime_invalid_receipt_retry_same_plan")
        receipt = {
            "request_key": key,
            "request_id": result["request_id"],
            "report_id": report["report_id"],
            "status": result["status"],
        }
        receipts["items"].append(receipt)
        write_private(receipts_path, receipts)
    return {
        "receipts_path": str(receipts_path.resolve()),
        "registered": len(receipts["items"]),
        "plan_hash": plan_hash,
    }


def refresh_status(client: RuntimeClient, path: Path) -> dict[str, Any]:
    receipts = json.loads(path.read_text(encoding="utf-8"))
    totals: dict[str, int] = {}
    for item in receipts["items"]:
        result = client.status(item["request_id"])
        item["status"] = result["status"]
        item["error"] = result.get("error")
        totals[item["status"]] = totals.get(item["status"], 0) + 1
    write_private(path, receipts)
    return {"total": len(receipts["items"]), "statuses": totals}
