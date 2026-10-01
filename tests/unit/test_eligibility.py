from datetime import UTC, date, datetime, timedelta
from unittest.mock import Mock

import httpx
import pytest
import respx

from kairos_report.config import Settings
from kairos_report.eligibility import EligibilityEvidence, EligibilityGuard
from kairos_report.errors import TutoryContractChanged, TutoryRetryPaused
from kairos_report.tutory.client import TutoryClient

ON = date(2026, 10, 1)


@pytest.mark.parametrize("age,expected", [(0, True), (14, True), (15, False), (16, False)])
def test_minimum_days_boundary(age: int, expected: bool) -> None:
    reasons = EligibilityEvidence(ON - timedelta(days=age), ()).reasons(ON, 15)
    assert ("mentorship_too_recent" in reasons) == expected


@pytest.mark.parametrize("start,end,paused", [
    (-10, -1, False), (1, 5, False), (0, 5, True), (-5, 0, True), (-5, 5, True),
])
def test_only_current_pause_blocks(start: int, end: int, paused: bool) -> None:
    evidence = EligibilityEvidence(ON - timedelta(days=60), (
        (ON + timedelta(days=start), ON + timedelta(days=end)),
    ))
    assert ("study_plan_paused" in evidence.reasons(ON, 15)) == paused


def test_invalid_evidence_is_not_eligible() -> None:
    assert EligibilityEvidence(ON + timedelta(days=1), ()).reasons(ON, 15) == [
        "eligibility_unverified"
    ]
    assert EligibilityEvidence(ON, ((ON, ON - timedelta(days=1)),)).reasons(ON, 0) == [
        "eligibility_unverified"
    ]


def test_local_day_and_configurable_threshold(test_settings: Settings) -> None:
    settings = test_settings.model_copy(update={
        "report_eligibility_enabled": True, "mentorship_minimum_days": 10,
    })
    source = Mock()
    source.report_eligibility.return_value = EligibilityEvidence(date(2026, 9, 21), ())
    guard = EligibilityGuard(settings, source, clock=lambda: datetime(2026, 10, 1, 1, tzinfo=UTC))
    # UTC is October 1, but Sao Paulo is still September 30 (nine days).
    assert guard.check("s1") == ["mentorship_too_recent"]


def test_explicitly_disabled_policy_does_not_consult_provider(test_settings: Settings) -> None:
    source = Mock()
    assert EligibilityGuard(test_settings, source).check("s1") == []
    source.report_eligibility.assert_not_called()


def test_provider_failure_blocks_and_retry_after_is_preserved(test_settings: Settings) -> None:
    settings = test_settings.model_copy(update={"report_eligibility_enabled": True})
    source = Mock()
    source.report_eligibility.side_effect = TutoryContractChanged("private upstream data")
    assert EligibilityGuard(settings, source).check("s1") == ["eligibility_unverified"]
    source.report_eligibility.side_effect = TutoryRetryPaused("wait", retry_after_seconds=90)
    with pytest.raises(TutoryRetryPaused):
        EligibilityGuard(settings, source).check("s1")


def pause_html(start: str, end: str) -> str:
    return ('<table><thead><tr><th>Data</th><th>Motivo</th><th></th></tr></thead>'
            f'<tbody><tr><td>{start} até {end}</td><td>Privado</td><td></td></tr></tbody></table>')


def test_pause_history_requires_verified_empty_marker() -> None:
    assert TutoryClient._parse_pause_history(
        '<div>Nenhuma pausa de plano cadastrada ainda</div>'
    ) == ()
    assert TutoryClient._parse_pause_history(pause_html('18/08/2026', '31/12/2026')) == (
        (date(2026, 8, 18), date(2026, 12, 31)),
    )


@pytest.mark.parametrize("html", [
    '<html>login</html>', pause_html('31/02/2026', '31/12/2026'),
    pause_html('18/08/2026', '17/08/2026'), pause_html('18/08/2026', ''),
    '<table><th>Data</th><th>Motivo</th><th></th><tbody></tbody></table>',
])
def test_changed_or_malformed_history_fails_closed(html: str) -> None:
    with pytest.raises(TutoryContractChanged):
        TutoryClient._parse_pause_history(html)


@pytest.mark.parametrize('problem', ['none', 'wrong_student', 'missing_date', 'bad_redirect'])
@respx.mock
def test_verified_panel_access_is_scoped_and_never_changes_pause(
    test_settings: Settings, problem: str,
) -> None:
    respx.post(TutoryClient.BASE_URL + '/intent/login').respond(200)
    student = 'other' if problem == 'wrong_student' else 's1'
    date_field = (
        '' if problem == 'missing_date' else '<input name="data_inicio" value="01/08/2026">'
    )
    detail = (date_field + f'<form action="{TutoryClient.STUDENT_PANEL_ACCESS}">'
              f'<input name="id" value="{student}"><input name="cpf" value="test-cpf">'
              '<input name="adm_id" value="admin"><input name="token" value="private">'
              '</form>')
    respx.get(TutoryClient.BASE_URL + '/alunos/index?aid=s1').respond(200, text=detail)
    access = respx.post(TutoryClient.STUDENT_PANEL_ACCESS).mock(return_value=httpx.Response(
        302, headers={'location': 'https://untrusted.invalid/' if problem == 'bad_redirect'
                     else '/painel/'},
    ))
    panel = respx.get(TutoryClient.STUDENT_PANEL_PATH).respond(200)
    history = respx.get(TutoryClient.PAUSE_HISTORY_PATH).respond(
        200, text=pause_html('18/08/2026', '31/12/2026'),
    )
    if problem == 'none':
        evidence = TutoryClient(test_settings).report_eligibility('s1')
        assert evidence.reasons(ON, 15) == ['study_plan_paused']
        assert panel.called and history.called
        assert all(call.request.url.path in {
            '/intent/login', '/alunos/index', '/intent/ver-painel',
            '/painel/', '/painel/config/pausar-plano',
        } for call in respx.calls)
        assert 'Authorization' not in access.calls[0].request.headers
    else:
        with pytest.raises(TutoryContractChanged):
            TutoryClient(test_settings).report_eligibility('s1')
        assert not history.called
        if problem != 'bad_redirect':
            assert not access.called
