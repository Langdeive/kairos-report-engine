from datetime import date

import httpx
import pytest
import respx

from kairos_report.config import Settings
from kairos_report.errors import TutoryAuthenticationError, TutoryContractChanged
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
        return_value=httpx.Response(
            200, text=search_html([], [("s1", "Ana"), ("s2", "Bruno")])
        )
    )
    respx.get("https://admin.tutory.com.br/alunos/consulta?status=ativos&curso=c2").mock(
        return_value=httpx.Response(
            200, text=search_html([], [("s2", "Bruno"), ("s3", "Carla")])
        )
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
    respx.get(
        "https://admin.tutory.com.br/alunos/consulta?status=ativos&curso=large&nome=A"
    ).mock(
        return_value=httpx.Response(200, text=search_html([], [("s1", "Ana"), ("s2", "Bia")]))
    )
    respx.get(
        "https://admin.tutory.com.br/alunos/consulta?status=ativos&curso=large&nome=B"
    ).mock(return_value=httpx.Response(200, text=search_html([], [("s3", "Bruna")])))

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
def test_generate_report_uses_bearer_and_fetches_html(test_settings: Settings) -> None:
    generate = respx.post(
        "https://admin.tutory.com.br/intent/cadastrar-relatorio-coach"
    ).mock(
        return_value=httpx.Response(
            200,
            json={"result": True, "data": [{"id": "s1", "token": "k1"}]},
        )
    )
    respx.get(
        "https://admin.tutory.com.br/documentos/relatorios/desempenho?key=k1"
    ).mock(return_value=httpx.Response(200, text="<h1>Relatório de Desempenho</h1>"))

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
def test_generate_report_retries_server_error_at_most_three_times(
    test_settings: Settings,
) -> None:
    generate = respx.post(
        "https://admin.tutory.com.br/intent/cadastrar-relatorio-coach"
    ).mock(side_effect=[httpx.Response(503), httpx.Response(503), httpx.Response(200, json={})])

    with pytest.raises(TutoryContractChanged):
        TutoryClient(test_settings, sleep=lambda _: None).generate_report(
            "s1", date(2026, 8, 1), date(2026, 8, 31)
        )

    assert generate.call_count == 3


@respx.mock
def test_authentication_error_does_not_log_token(
    test_settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    respx.post("https://admin.tutory.com.br/intent/cadastrar-relatorio-coach").mock(
        return_value=httpx.Response(401)
    )

    with pytest.raises(TutoryAuthenticationError), caplog.at_level("WARNING"):
        TutoryClient(test_settings).generate_report(
            "s1", date(2026, 8, 1), date(2026, 8, 31)
        )

    assert "test-token" not in caplog.text
    assert "authentication" in caplog.text.lower()
