import json
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from kairos_report.cli import app
from kairos_report.config import Settings
from kairos_report.data.service import ReportDataService
from kairos_report.db import create_engine_for
from kairos_report.eligibility import EligibilityEvidence
from kairos_report.errors import KairosReportError, TutoryContractChanged
from kairos_report.models import AuditEvent, ReportStatus, StudentReport
from kairos_report.runtime_delivery import RuntimeDeliveryError, prepare, submit_plan
from kairos_report.tutory.client import TutoryClient, TutoryStudent
from tests.integration.test_delivery_manifest import prepared_run
from tests.integration.test_run_service import build_service
from tests.integration.test_runtime_delivery import FakeRuntime, decision


@pytest.mark.parametrize("case,reason", [
    ('recent', 'mentorship_too_recent'), ('paused', 'study_plan_paused'),
    ('unknown', 'eligibility_unverified'),
])
def test_exclusion_prevents_upstream_generation(
    test_settings: Settings, case: str, reason: str,
) -> None:
    settings = test_settings.model_copy(update={"report_eligibility_enabled": True})
    service, client = build_service(settings, [TutoryStudent('s1', 'Exemplo')])
    service._eligibility._clock = lambda: datetime(2026, 10, 1, 12, tzinfo=UTC)
    if case == 'unknown':
        client.report_eligibility.side_effect = TutoryContractChanged('changed')
    else:
        client.report_eligibility.return_value = EligibilityEvidence(
            date(2026, 9, 28) if case == 'recent' else date(2026, 8, 1),
            ((date(2026, 9, 1), date(2026, 12, 1)),) if case == 'paused' else (),
        )
    run = service.create(date(2026, 9, 1), date(2026, 9, 30), 'test', 'v1')
    summary = service.extract(run.id)
    assert summary.blocked == 1 and summary.valid == 0
    assert summary.excluded == (0 if case == 'unknown' else 1)
    client.generate_report_bundle.assert_not_called()
    with Session(create_engine_for(settings)) as session:
        report = session.scalar(select(StudentReport))
        assert report is not None and report.status == ReportStatus.BLOCKED
        assert reason in report.validation_errors
        assert report.pdf_path is None
        assert session.scalar(select(AuditEvent).where(
            AuditEvent.event_type == 'report.eligibility_blocked'
        )) is not None
    exported = ReportDataService(settings).export(run.id)
    assert exported.complete == (case != 'unknown')
    generated = ReportDataService(settings).generate(run.id)
    assert generated['generated'] == 0
    assert generated['complete'] == (case != 'unknown')


def test_exactly_fifteen_days_and_past_pause_allow_extraction(test_settings: Settings) -> None:
    settings = test_settings.model_copy(update={"report_eligibility_enabled": True})
    service, client = build_service(settings, [TutoryStudent('s1', 'Aluno Exemplo')])
    service._eligibility._clock = lambda: datetime(2026, 10, 1, 12, tzinfo=UTC)
    client.report_eligibility.return_value = EligibilityEvidence(
        date(2026, 9, 16), ((date(2026, 9, 20), date(2026, 9, 30)),),
    )
    run = service.create(date(2026, 8, 1), date(2026, 8, 31), 'test', 'v1')
    summary = service.extract(run.id)
    assert summary.valid == 1
    client.generate_report_bundle.assert_called_once()


def test_old_data_cannot_generate_pdf_when_currently_paused(
    test_settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = prepared_run(test_settings, tmp_path)
    settings = test_settings.model_copy(update={"report_eligibility_enabled": True})
    source = Mock()
    source.report_eligibility.return_value = EligibilityEvidence(
        date(2020, 1, 1), ((date(2020, 1, 1), date(2100, 1, 1)),),
    )
    render = Mock()
    monkeypatch.setattr('kairos_report.data.service.generate_approved_report', render)
    result = ReportDataService(settings, eligibility_source=source).generate(run_id)
    assert result['generated'] == 0
    assert result['eligibility_exclusions'] == {1: ['study_plan_paused'], 2: ['study_plan_paused']}
    render.assert_not_called()
    manifest = json.loads(Path(result['delivery_manifest']['output_path']).read_text())
    assert all(not item['ready_for_hermes'] for item in manifest['items'])


def test_pause_after_approval_blocks_upload_and_submission(
    test_settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = prepared_run(test_settings, tmp_path)
    runtime = FakeRuntime()
    plan_path = tmp_path / 'plan.json'
    result = prepare(test_settings, runtime.client, run_id, [decision()], plan_path)
    settings = test_settings.model_copy(update={"report_eligibility_enabled": True})
    monkeypatch.setattr(TutoryClient, 'report_eligibility', lambda self, student_id:
        EligibilityEvidence(date(2020, 1, 1), ((date(2020, 1, 1), date(2100, 1, 1)),)))
    with pytest.raises(RuntimeDeliveryError, match='report_not_ready'):
        submit_plan(settings, runtime.client, plan_path, result['plan_hash'])
    assert not any(request.method == 'POST' for request in runtime.calls)


def test_single_file_generation_uses_persisted_identity_and_current_policy(
    test_settings: Settings, tmp_path: Path,
) -> None:
    run_id = prepared_run(test_settings, tmp_path)
    exported = ReportDataService(test_settings).export(run_id)
    from kairos_report.report_data import ReportDataEnvelope
    envelope = ReportDataEnvelope.model_validate_json(
        exported.output_path.read_text().splitlines()[0]
    )
    assert envelope.data is not None
    settings = test_settings.model_copy(update={'report_eligibility_enabled': True})
    source = Mock()
    source.report_eligibility.return_value = EligibilityEvidence(
        date(2020, 1, 1), ((date(2020, 1, 1), date(2100, 1, 1)),),
    )
    guarded = ReportDataService(settings, eligibility_source=source)
    with pytest.raises(KairosReportError, match='study_plan_paused'):
        guarded.require_eligible_package(envelope.data)
    source.report_eligibility.assert_called_once_with('s1')
    changed = envelope.data.model_copy(deep=True)
    changed.identity.student_name = 'Different student'
    with pytest.raises(KairosReportError, match='eligibility_identity_unverified'):
        guarded.require_eligible_package(changed)


def test_live_diagnostic_cli_cannot_bypass_pause(
    test_settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = test_settings.model_copy(update={'report_eligibility_enabled': True})
    monkeypatch.setattr(Settings, 'load', lambda: settings)
    source = Mock()
    source.report_eligibility.return_value = EligibilityEvidence(
        date(2020, 1, 1), ((date(2020, 1, 1), date(2100, 1, 1)),),
    )
    monkeypatch.setattr('kairos_report.cli.TutoryClient', lambda settings: source)
    pdf = tmp_path / 'blocked.pdf'
    data = tmp_path / 'blocked.json'
    result = CliRunner().invoke(app, [
        'report', 'generate-live', '--student-id', 's1', '--month', '2026-09',
        '--output', str(pdf), '--data-output', str(data),
    ])
    assert result.exit_code != 0
    assert 'study_plan_paused' in result.output
    source.generate_report_bundle.assert_not_called()
    assert not pdf.exists() and not data.exists()
