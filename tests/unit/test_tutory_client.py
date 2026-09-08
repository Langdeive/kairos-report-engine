from datetime import UTC, date, datetime, timedelta
from email.utils import format_datetime

import httpx
import pytest
import respx

from kairos_report.config import Settings
from kairos_report.errors import (
    TutoryAuthenticationError,
    TutoryContractChanged,
    TutoryGenerationUncertain,
    TutoryRetryPaused,
    TutoryTemporaryError,
)
from kairos_report.tutory.client import TutoryClient


def dashboard_html(active_count: int) -> str:
    return f'<div role="progressbar">{active_count} (1%)</div>'


def search_html(courses: list[str], students: list[tuple[str, str]]) -> str:
    options = "".join(f'<option value="{course}">Course</option>' for course in courses)
    cards = "".join(
        (
            '<div class="pesquisa-aluno-container">'
            f'<div class="pesquisa-aluno-nome">{name}</div>'
            '<form class="form_visualizar_aluno" action="/intent/ver-painel">'
            f'<input name="id" value="{student_id}">'
            "</form></div>"
        )
        for student_id, name in students
    )
    return f'<select name="curso"><option value="">All</option>{options}</select>{cards}'


def test_extract_api_token_accepts_current_unquoted_javascript_key() -> None:
    html = """
    <script type="text/javascript">
        window.adminUser = { id: 123, token: 'live-session-token', role: 'admin' };
    </script>
    """

    assert TutoryClient._extract_api_token(html) == "live-session-token"


@respx.mock
def test_expired_discovered_token_is_refreshed_once(test_settings: Settings) -> None:
    settings = test_settings.model_copy(update={"tutory_api_token": None})
    client = TutoryClient(settings)
    client._token = "expired-session"
    login = respx.post("https://admin.tutory.com.br/intent/login").respond(200)
    respx.get("https://admin.tutory.com.br/index").respond(
        200, text='<script>window.adminUser = {token: "fresh-session"};</script>'
    )
    generation = respx.post("https://admin.tutory.com.br/intent/cadastrar-relatorio-coach").mock(
        side_effect=[
            httpx.Response(401),
            httpx.Response(200, json={"result": True, "data": [{"token": "document-key"}]}),
        ]
    )
    respx.get("https://admin.tutory.com.br/documentos/relatorios/desempenho").respond(
        200, text="<html>Relatório</html>"
    )
    result = client.generate_report("s1", date(2026, 8, 1), date(2026, 8, 31))
    assert result.key == "document-key"
    assert login.call_count == 1
    assert generation.call_count == 2
    assert generation.calls[-1].request.headers["Authorization"] == "Bearer fresh-session"


@respx.mock
def test_list_active_students_logs_in_partitions_courses_and_deduplicates(
    test_settings: Settings,
) -> None:
    login = respx.post("https://admin.tutory.com.br/intent/login").mock(
        return_value=httpx.Response(200, text='<script>document.location.href = "/index"</script>')
    )
    respx.get("https://admin.tutory.com.br/index").mock(
        return_value=httpx.Response(200, text=dashboard_html(3))
    )
    respx.get("https://admin.tutory.com.br/alunos/consulta?status=ativos").mock(
        return_value=httpx.Response(200, text=search_html(["c1", "c2"], []))
    )
    respx.get("https://admin.tutory.com.br/alunos/consulta?status=ativos&curso=c1").mock(
        return_value=httpx.Response(200, text=search_html([], [("s1", "Ana"), ("s2", "Bruno")]))
    )
    respx.get("https://admin.tutory.com.br/alunos/consulta?status=ativos&curso=c2").mock(
        return_value=httpx.Response(200, text=search_html([], [("s2", "Bruno"), ("s3", "Carla")]))
    )

    students = TutoryClient(test_settings).list_active_students()

    assert [(student.id, student.name, student.status) for student in students] == [
        ("s1", "Ana", "active"),
        ("s2", "Bruno", "active"),
        ("s3", "Carla", "active"),
    ]
    assert login.calls[0].request.content.decode() == (
        "account=test-account&password=test-password"
    )


@respx.mock
def test_list_active_students_subdivides_a_course_that_reaches_the_limit(
    test_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(TutoryClient, "RESULT_LIMIT", 2)
    respx.post("https://admin.tutory.com.br/intent/login").mock(
        return_value=httpx.Response(200, text="ok")
    )
    respx.get("https://admin.tutory.com.br/index").mock(
        return_value=httpx.Response(200, text=dashboard_html(3))
    )
    respx.get("https://admin.tutory.com.br/alunos/consulta?status=ativos").mock(
        return_value=httpx.Response(200, text=search_html(["large"], []))
    )
    respx.get("https://admin.tutory.com.br/alunos/consulta?status=ativos&curso=large").mock(
        return_value=httpx.Response(200, text=search_html([], [("s1", "Ana"), ("s2", "Bia")]))
    )
    respx.get("https://admin.tutory.com.br/alunos/consulta?status=ativos&curso=large&nome=A").mock(
        return_value=httpx.Response(200, text=search_html([], [("s1", "Ana"), ("s2", "Bia")]))
    )
    respx.get("https://admin.tutory.com.br/alunos/consulta?status=ativos&curso=large&nome=B").mock(
        return_value=httpx.Response(200, text=search_html([], [("s3", "Bruna")]))
    )

    students = TutoryClient(test_settings).list_active_students()

    assert [student.id for student in students] == ["s1", "s2", "s3"]


@respx.mock
def test_list_active_students_fails_closed_when_total_does_not_match(
    test_settings: Settings,
) -> None:
    respx.post("https://admin.tutory.com.br/intent/login").mock(
        return_value=httpx.Response(200, text="ok")
    )
    respx.get("https://admin.tutory.com.br/index").mock(
        return_value=httpx.Response(200, text=dashboard_html(2))
    )
    respx.get("https://admin.tutory.com.br/alunos/consulta?status=ativos").mock(
        return_value=httpx.Response(200, text=search_html(["c1"], []))
    )
    respx.get("https://admin.tutory.com.br/alunos/consulta?status=ativos&curso=c1").mock(
        return_value=httpx.Response(200, text=search_html([], [("s1", "Ana")]))
    )

    with pytest.raises(TutoryContractChanged, match="expected 2, found 1"):
        TutoryClient(test_settings).list_active_students()


@respx.mock
def test_list_active_students_can_include_phone_in_the_same_session(
    test_settings: Settings,
) -> None:
    login = respx.post("https://admin.tutory.com.br/intent/login").mock(
        return_value=httpx.Response(200, text="ok")
    )
    respx.get("https://admin.tutory.com.br/index").mock(
        return_value=httpx.Response(200, text=dashboard_html(1))
    )
    respx.get("https://admin.tutory.com.br/alunos/consulta?status=ativos").mock(
        return_value=httpx.Response(200, text=search_html(["c1"], []))
    )
    respx.get("https://admin.tutory.com.br/alunos/consulta?status=ativos&curso=c1").mock(
        return_value=httpx.Response(200, text=search_html([], [("s1", "Ana")]))
    )
    respx.get("https://admin.tutory.com.br/alunos/index?aid=s1").mock(
        return_value=httpx.Response(
            200,
            text=(
                '<select name="ddd"><option value="11" selected>11</option></select>'
                '<input name="celular" value="99999-1234">'
            ),
        )
    )

    students = TutoryClient(test_settings).list_active_students(include_phones=True)

    assert students[0].raw_phone == "1199999-1234"
    assert login.call_count == 1


@respx.mock
def test_list_active_students_filters_only_after_full_count_validation(
    test_settings: Settings,
) -> None:
    respx.post("https://admin.tutory.com.br/intent/login").respond(200, text="ok")
    respx.get("https://admin.tutory.com.br/index").respond(200, text=dashboard_html(3))
    respx.get("https://admin.tutory.com.br/alunos/consulta?status=ativos").respond(
        200, text=search_html(["c1"], [])
    )
    respx.get("https://admin.tutory.com.br/alunos/consulta?status=ativos&curso=c1").respond(
        200, text=search_html([], [("s1", "Ana"), ("s2", "Bia")])
    )

    with pytest.raises(TutoryContractChanged, match="expected 3, found 2"):
        TutoryClient(test_settings).list_active_students(
            student_ids=["s1"], include_phones=True
        )


@respx.mock
def test_list_active_students_fetches_phones_only_for_selected_students(
    test_settings: Settings,
) -> None:
    respx.post("https://admin.tutory.com.br/intent/login").respond(200, text="ok")
    respx.get("https://admin.tutory.com.br/index").respond(200, text=dashboard_html(2))
    respx.get("https://admin.tutory.com.br/alunos/consulta?status=ativos").respond(
        200, text=search_html(["c1"], [])
    )
    respx.get("https://admin.tutory.com.br/alunos/consulta?status=ativos&curso=c1").respond(
        200, text=search_html([], [("s1", "Ana"), ("s2", "Bia")])
    )
    selected_phone = respx.get("https://admin.tutory.com.br/alunos/index?aid=s2").respond(
        200,
        text=(
            '<select name="ddd"><option value="11" selected>11</option></select>'
            '<input name="celular" value="99999-2222">'
        ),
    )

    students = TutoryClient(test_settings).list_active_students(
        student_ids=["s2"], include_phones=True
    )

    assert [(student.id, student.raw_phone) for student in students] == [
        ("s2", "1199999-2222")
    ]
    assert selected_phone.call_count == 1


@respx.mock
def test_list_active_students_rejects_unknown_selected_student(
    test_settings: Settings,
) -> None:
    respx.post("https://admin.tutory.com.br/intent/login").respond(200, text="ok")
    respx.get("https://admin.tutory.com.br/index").respond(200, text=dashboard_html(1))
    respx.get("https://admin.tutory.com.br/alunos/consulta?status=ativos").respond(
        200, text=search_html(["c1"], [])
    )
    respx.get("https://admin.tutory.com.br/alunos/consulta?status=ativos&curso=c1").respond(
        200, text=search_html([], [("s1", "Ana")])
    )

    with pytest.raises(ValueError, match="not in the active-student list"):
        TutoryClient(test_settings).list_active_students(student_ids=["missing"])


@pytest.mark.parametrize("student_ids", [[], [""]])
def test_list_active_students_rejects_empty_selection_before_network(
    test_settings: Settings, student_ids: list[str]
) -> None:
    with pytest.raises(ValueError, match="student IDs"):
        TutoryClient(test_settings).list_active_students(student_ids=student_ids)


@respx.mock
def test_generate_report_uses_bearer_and_fetches_html(test_settings: Settings) -> None:
    generate = respx.post("https://admin.tutory.com.br/intent/cadastrar-relatorio-coach").mock(
        return_value=httpx.Response(
            200,
            json={"result": True, "data": [{"id": "s1", "token": "k1"}]},
        )
    )
    respx.get("https://admin.tutory.com.br/documentos/relatorios/desempenho?key=k1").mock(
        return_value=httpx.Response(200, text="<h1>Relatório de Desempenho</h1>")
    )

    document = TutoryClient(test_settings).generate_report(
        "s1", date(2026, 8, 1), date(2026, 8, 31)
    )

    assert document.key == "k1"
    assert "Relatório" in document.html
    request = generate.calls[0].request
    assert request.headers["Authorization"] == "Bearer test-token"
    assert request.headers["Content-Type"].startswith("application/x-www-form-urlencoded")
    assert request.content.decode() == (
        "alunos%5B%5D=s1&dt_ini=01%2F08%2F2026&dt_fim=31%2F08%2F2026&agrupamento=semana"
    )


@respx.mock
def test_generate_report_bundle_fetches_requested_models_with_one_key(
    test_settings: Settings,
) -> None:
    respx.post("https://admin.tutory.com.br/intent/cadastrar-relatorio-coach").mock(
        return_value=httpx.Response(
            200,
            json={"result": True, "data": [{"id": "s1", "token": "k1"}]},
        )
    )
    for model in ("desempenho", "questoes", "aluno"):
        respx.get(f"https://admin.tutory.com.br/documentos/relatorios/{model}?key=k1").mock(
            return_value=httpx.Response(200, text=f"<h1>Relatório {model}</h1>")
        )

    bundle = TutoryClient(test_settings).generate_report_bundle(
        "s1",
        date(2026, 7, 1),
        date(2026, 7, 31),
        models=("desempenho", "questoes", "aluno"),
    )

    assert bundle.key == "k1"
    assert set(bundle.documents) == {"desempenho", "questoes", "aluno"}
    assert "Relatório questoes" in bundle.documents["questoes"]


@respx.mock
def test_generate_report_logs_in_and_uses_token_from_authenticated_page(
    test_settings: Settings,
) -> None:
    settings_without_static_token = test_settings.model_copy(update={"tutory_api_token": None})
    login = respx.post("https://admin.tutory.com.br/intent/login").mock(
        return_value=httpx.Response(200, text='<script>location.href = "/index"</script>')
    )
    respx.get("https://admin.tutory.com.br/index").mock(
        return_value=httpx.Response(
            200,
            text=(
                '<div role="progressbar">3 (100%)</div>'
                '<script>window.adminUser = {"id":"admin-1","token":"session-token"};</script>'
            ),
        )
    )
    generate = respx.post("https://admin.tutory.com.br/intent/cadastrar-relatorio-coach").mock(
        return_value=httpx.Response(
            200,
            json={"result": True, "data": [{"id": "s1", "token": "report-key"}]},
        )
    )
    respx.get("https://admin.tutory.com.br/documentos/relatorios/desempenho?key=report-key").mock(
        return_value=httpx.Response(200, text="<h1>Relatório de Desempenho</h1>")
    )

    document = TutoryClient(settings_without_static_token).generate_report(
        "s1", date(2026, 8, 1), date(2026, 8, 31)
    )

    assert document.key == "report-key"
    assert login.call_count == 1
    assert generate.calls[0].request.headers["Authorization"] == "Bearer session-token"


@respx.mock
def test_list_students_reuses_discovered_token_for_report_generation(
    test_settings: Settings,
) -> None:
    settings_without_static_token = test_settings.model_copy(update={"tutory_api_token": None})
    login = respx.post("https://admin.tutory.com.br/intent/login").mock(
        return_value=httpx.Response(200, text="ok")
    )
    respx.get("https://admin.tutory.com.br/index").mock(
        return_value=httpx.Response(
            200,
            text=(
                '<div role="progressbar">1 (100%)</div>'
                '<script>window.adminUser = {"token":"cycle-token"};</script>'
            ),
        )
    )
    respx.get("https://admin.tutory.com.br/alunos/consulta?status=ativos").mock(
        return_value=httpx.Response(200, text=search_html(["c1"], []))
    )
    respx.get("https://admin.tutory.com.br/alunos/consulta?status=ativos&curso=c1").mock(
        return_value=httpx.Response(200, text=search_html([], [("s1", "Ana")]))
    )
    generate = respx.post("https://admin.tutory.com.br/intent/cadastrar-relatorio-coach").mock(
        return_value=httpx.Response(
            200,
            json={"result": True, "data": [{"id": "s1", "token": "report-key"}]},
        )
    )
    respx.get("https://admin.tutory.com.br/documentos/relatorios/desempenho?key=report-key").mock(
        return_value=httpx.Response(200, text="<h1>Relatório de Desempenho</h1>")
    )

    client = TutoryClient(settings_without_static_token)
    students = client.list_active_students()
    client.generate_report("s1", date(2026, 8, 1), date(2026, 8, 31))

    assert len(students) == 1
    assert login.call_count == 1
    assert generate.calls[0].request.headers["Authorization"] == "Bearer cycle-token"


@respx.mock
def test_list_students_uses_coaching_page_when_dashboard_has_no_api_token(
    test_settings: Settings,
) -> None:
    settings_without_static_token = test_settings.model_copy(update={"tutory_api_token": None})
    respx.post("https://admin.tutory.com.br/intent/login").mock(
        return_value=httpx.Response(200, text="ok")
    )
    respx.get("https://admin.tutory.com.br/index").mock(
        return_value=httpx.Response(200, text=dashboard_html(1))
    )
    coaching = respx.get("https://admin.tutory.com.br/alunos/coaching").mock(
        return_value=httpx.Response(
            200,
            text='<script>window.adminUser = {"token":"coaching-token"};</script>',
        )
    )
    respx.get("https://admin.tutory.com.br/alunos/consulta?status=ativos").mock(
        return_value=httpx.Response(200, text=search_html(["c1"], []))
    )
    respx.get("https://admin.tutory.com.br/alunos/consulta?status=ativos&curso=c1").mock(
        return_value=httpx.Response(200, text=search_html([], [("s1", "Ana")]))
    )

    students = TutoryClient(settings_without_static_token).list_active_students()

    assert len(students) == 1
    assert coaching.call_count == 1


@respx.mock
def test_generate_report_does_not_repeat_ambiguous_server_error(
    test_settings: Settings,
) -> None:
    generate = respx.post("https://admin.tutory.com.br/intent/cadastrar-relatorio-coach").mock(
        return_value=httpx.Response(503)
    )

    with pytest.raises(TutoryTemporaryError, match="uncertain"):
        TutoryClient(test_settings, sleep=lambda _: None).generate_report(
            "s1", date(2026, 8, 1), date(2026, 8, 31)
        )

    assert generate.call_count == 1


@respx.mock
def test_generate_report_does_not_repeat_ambiguous_timeout(test_settings: Settings) -> None:
    generate = respx.post("https://admin.tutory.com.br/intent/cadastrar-relatorio-coach").mock(
        side_effect=httpx.ReadTimeout("timeout")
    )

    client = TutoryClient(test_settings, sleep=lambda _: None)
    with pytest.raises(TutoryTemporaryError, match="uncertain"):
        client.generate_report(
            "s1", date(2026, 8, 1), date(2026, 8, 31)
        )

    assert generate.call_count == 1
    assert client.stats["http_calls"] == 1
    assert client.stats["statuses"] == {"network_error": 1}


@respx.mock
def test_rate_limit_honors_retry_after_seconds(test_settings: Settings) -> None:
    settings = test_settings.model_copy(
        update={
            "tutory_request_spacing_seconds": 0,
            "tutory_retry_max_seconds": 10,
        }
    )
    sleeps: list[float] = []
    generation = respx.post(
        "https://admin.tutory.com.br/intent/cadastrar-relatorio-coach"
    ).mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "7"}),
            httpx.Response(200, json={"result": True, "data": [{"token": "key"}]}),
        ]
    )
    respx.get("https://admin.tutory.com.br/documentos/relatorios/desempenho?key=key").respond(
        200, text="<h1>Relatório</h1>"
    )

    TutoryClient(settings, sleep=sleeps.append).generate_report(
        "s1", date(2026, 8, 1), date(2026, 8, 31)
    )

    assert generation.call_count == 2
    assert sleeps == [7]


@respx.mock
def test_rate_limit_pauses_when_retry_after_exceeds_allowed_wait(
    test_settings: Settings,
) -> None:
    settings = test_settings.model_copy(
        update={
            "tutory_request_spacing_seconds": 0,
            "tutory_retry_max_seconds": 5,
        }
    )
    sleeps: list[float] = []
    generation = respx.post(
        "https://admin.tutory.com.br/intent/cadastrar-relatorio-coach"
    ).mock(return_value=httpx.Response(429, headers={"Retry-After": "12"}))

    with pytest.raises(TutoryRetryPaused, match="must be preserved") as raised:
        TutoryClient(settings, sleep=sleeps.append).generate_report(
            "s1", date(2026, 8, 1), date(2026, 8, 31)
        )

    assert raised.value.retry_after_seconds == 12
    assert generation.call_count == 1
    assert sleeps == []


@respx.mock
def test_get_auth_error_after_generation_never_creates_a_second_report(
    test_settings: Settings,
) -> None:
    settings = test_settings.model_copy(update={"tutory_api_token": None})
    respx.post("https://admin.tutory.com.br/intent/login").respond(200, text="ok")
    respx.get("https://admin.tutory.com.br/index").respond(
        200, text='<script>window.adminUser = {token: "session"};</script>'
    )
    generation = respx.post(
        "https://admin.tutory.com.br/intent/cadastrar-relatorio-coach"
    ).respond(200, json={"result": True, "data": [{"token": "key"}]})
    respx.get("https://admin.tutory.com.br/documentos/relatorios/desempenho?key=key").respond(
        401
    )

    with pytest.raises(TutoryGenerationUncertain) as raised:
        TutoryClient(settings).generate_report("s1", date(2026, 8, 1), date(2026, 8, 31))

    assert generation.call_count == 1
    assert isinstance(raised.value.__cause__, TutoryAuthenticationError)
    assert getattr(raised.value, "stop_reason", None) == "auth"


@respx.mock
def test_exhausted_get_after_generation_is_uncertain_without_second_post(
    test_settings: Settings,
) -> None:
    settings = test_settings.model_copy(update={"tutory_http_max_attempts": 2})
    generation = respx.post(
        "https://admin.tutory.com.br/intent/cadastrar-relatorio-coach"
    ).respond(200, json={"result": True, "data": [{"token": "key"}]})
    document = respx.get(
        "https://admin.tutory.com.br/documentos/relatorios/desempenho?key=key"
    ).respond(503)

    with pytest.raises(TutoryGenerationUncertain) as raised:
        TutoryClient(settings, sleep=lambda _: None).generate_report(
            "s1", date(2026, 8, 1), date(2026, 8, 31)
        )

    assert generation.call_count == 1
    assert document.call_count == 2
    assert isinstance(raised.value.__cause__, TutoryTemporaryError)


@respx.mock
def test_retry_pause_after_generation_remains_uncertain_and_keeps_delay(
    test_settings: Settings,
) -> None:
    settings = test_settings.model_copy(update={"tutory_retry_max_seconds": 5})
    generation = respx.post(
        "https://admin.tutory.com.br/intent/cadastrar-relatorio-coach"
    ).respond(200, json={"result": True, "data": [{"token": "key"}]})
    document = respx.get(
        "https://admin.tutory.com.br/documentos/relatorios/desempenho?key=key"
    ).respond(429, headers={"Retry-After": "12"})

    with pytest.raises(TutoryGenerationUncertain) as raised:
        TutoryClient(settings).generate_report(
            "s1", date(2026, 8, 1), date(2026, 8, 31)
        )

    assert generation.call_count == 1
    assert document.call_count == 1
    assert getattr(raised.value, "retry_after_seconds", None) == 12
    assert isinstance(raised.value.__cause__, TutoryRetryPaused)


@respx.mock
def test_retry_after_is_honored_on_only_allowed_attempt(test_settings: Settings) -> None:
    settings = test_settings.model_copy(
        update={"tutory_http_max_attempts": 1, "tutory_retry_max_seconds": 5}
    )
    respx.post("https://admin.tutory.com.br/intent/login").respond(200, text="ok")
    dashboard = respx.get("https://admin.tutory.com.br/index").respond(
        429, headers={"Retry-After": "12"}
    )

    with pytest.raises(TutoryRetryPaused) as raised:
        TutoryClient(settings).list_active_students()

    assert dashboard.call_count == 1
    assert raised.value.retry_after_seconds == 12


@respx.mock
def test_retry_after_is_honored_on_last_configured_attempt(test_settings: Settings) -> None:
    settings = test_settings.model_copy(update={"tutory_retry_max_seconds": 5})
    respx.post("https://admin.tutory.com.br/intent/login").respond(200, text="ok")
    dashboard = respx.get("https://admin.tutory.com.br/index").mock(
        side_effect=[
            httpx.Response(429),
            httpx.Response(429),
            httpx.Response(429, headers={"Retry-After": "12"}),
        ]
    )

    with pytest.raises(TutoryRetryPaused) as raised:
        TutoryClient(settings, sleep=lambda _: None).list_active_students()

    assert dashboard.call_count == 3
    assert raised.value.retry_after_seconds == 12


@respx.mock
def test_short_retry_after_is_persisted_on_only_allowed_attempt(
    test_settings: Settings,
) -> None:
    settings = test_settings.model_copy(update={"tutory_http_max_attempts": 1})
    respx.post("https://admin.tutory.com.br/intent/login").respond(200, text="ok")
    dashboard = respx.get("https://admin.tutory.com.br/index").respond(
        429, headers={"Retry-After": "3"}
    )

    with pytest.raises(TutoryRetryPaused) as raised:
        TutoryClient(settings).list_active_students()

    assert dashboard.call_count == 1
    assert raised.value.retry_after_seconds == 3


@respx.mock
def test_short_retry_after_is_persisted_on_last_configured_attempt(
    test_settings: Settings,
) -> None:
    respx.post("https://admin.tutory.com.br/intent/login").respond(200, text="ok")
    dashboard = respx.get("https://admin.tutory.com.br/index").mock(
        side_effect=[
            httpx.Response(429),
            httpx.Response(429),
            httpx.Response(429, headers={"Retry-After": "3"}),
        ]
    )

    with pytest.raises(TutoryRetryPaused) as raised:
        TutoryClient(test_settings, sleep=lambda _: None).list_active_students()

    assert dashboard.call_count == 3
    assert raised.value.retry_after_seconds == 3


@pytest.mark.parametrize("retry_after", ["3", "120"])
@respx.mock
def test_ambiguous_post_503_preserves_retry_after_cooldown(
    test_settings: Settings, retry_after: str
) -> None:
    generation = respx.post(
        "https://admin.tutory.com.br/intent/cadastrar-relatorio-coach"
    ).respond(503, headers={"Retry-After": retry_after})

    with pytest.raises(TutoryGenerationUncertain) as raised:
        TutoryClient(test_settings).generate_report(
            "s1", date(2026, 8, 1), date(2026, 8, 31)
        )

    assert generation.call_count == 1
    assert raised.value.retry_after_seconds == float(retry_after)
    assert raised.value.stop_reason == "retry_paused"


@respx.mock
def test_rate_limit_honors_retry_after_http_date(test_settings: Settings) -> None:
    now = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
    settings = test_settings.model_copy(update={"tutory_retry_max_seconds": 10})
    sleeps: list[float] = []
    generation = respx.post(
        "https://admin.tutory.com.br/intent/cadastrar-relatorio-coach"
    ).mock(
        side_effect=[
            httpx.Response(
                429,
                headers={"Retry-After": format_datetime(now + timedelta(seconds=4))},
            ),
            httpx.Response(200, json={"result": True, "data": [{"token": "key"}]}),
        ]
    )
    respx.get("https://admin.tutory.com.br/documentos/relatorios/desempenho?key=key").respond(
        200, text="<h1>Relatório</h1>"
    )

    TutoryClient(settings, sleep=sleeps.append, clock=lambda: now).generate_report(
        "s1", date(2026, 8, 1), date(2026, 8, 31)
    )

    assert generation.call_count == 2
    assert sleeps == [4]


@respx.mock
def test_transient_get_retries_known_key_without_new_post(test_settings: Settings) -> None:
    generation = respx.post(
        "https://admin.tutory.com.br/intent/cadastrar-relatorio-coach"
    ).respond(200, json={"result": True, "data": [{"token": "key"}]})
    document = respx.get(
        "https://admin.tutory.com.br/documentos/relatorios/desempenho?key=key"
    ).mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(200, text="<h1>Relatório</h1>"),
        ]
    )

    TutoryClient(test_settings, sleep=lambda _: None).generate_report(
        "s1", date(2026, 8, 1), date(2026, 8, 31)
    )

    assert generation.call_count == 1
    assert document.call_count == 2


@respx.mock
def test_request_spacing_is_applied_between_http_calls(test_settings: Settings) -> None:
    settings = test_settings.model_copy(update={"tutory_request_spacing_seconds": 1})
    current = [datetime(2026, 9, 8, 12, 0, tzinfo=UTC)]
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        current[0] += timedelta(seconds=seconds)

    respx.post("https://admin.tutory.com.br/intent/cadastrar-relatorio-coach").respond(
        200, json={"result": True, "data": [{"token": "key"}]}
    )
    respx.get("https://admin.tutory.com.br/documentos/relatorios/desempenho?key=key").respond(
        200, text="<h1>Relatório</h1>"
    )

    client = TutoryClient(settings, sleep=sleep, clock=lambda: current[0])
    client.generate_report("s1", date(2026, 8, 1), date(2026, 8, 31))

    assert sleeps == [1]
    assert client.stats["http_calls"] == 2
    assert client.stats["wait_seconds"] == 1


@respx.mock
def test_authentication_error_does_not_log_token(
    test_settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    respx.post("https://admin.tutory.com.br/intent/cadastrar-relatorio-coach").mock(
        return_value=httpx.Response(401)
    )

    with pytest.raises(TutoryAuthenticationError), caplog.at_level("WARNING"):
        TutoryClient(test_settings).generate_report("s1", date(2026, 8, 1), date(2026, 8, 31))

    assert "test-token" not in caplog.text
    assert "authentication" in caplog.text.lower()
