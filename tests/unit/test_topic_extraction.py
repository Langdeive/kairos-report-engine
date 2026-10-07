"""Synthetic HTTP fixtures: automatic topic-launch extraction, never live credentials."""

from datetime import date
from urllib.parse import parse_qs

import httpx
import pytest
import respx

from kairos_report.config import Settings
from kairos_report.errors import TutoryContractChanged, TutoryTemporaryError
from kairos_report.tutory.client import TutoryClient
from kairos_report.tutory.parser import parse_question_report
from tests.daily_fixtures import question_html

ADMIN = "https://admin.tutory.com.br"
APP = "https://app.tutory.com.br"
LAUNCH_PATH = "/painel/questoes/lancamento"


def launch_row(discipline: str, topic: str, day: str, total: int, correct: int) -> str:
    return (
        f"<tr><td>{discipline}</td><td>{topic}</td><td>{total}</td><td>{correct}</td>"
        f'<td></td><td><a data-data="{day}" data-questoes="{total}" '
        f'data-acertos="{correct}"></a></td></tr>'
    )


def launch_page(rows: str, *, page: int = 1, last: int = 1) -> str:
    pagination = (
        '<ul class="pagination">'
        f'<li><a href="?">{page}</a></li>'
        + (f'<li><a href="?p={page + 1}">{page + 1}</a></li>' if page < last else "")
        + f'<li><a href="?p={last}">Última</a></li></ul>'
    )
    return (
        "<table><thead><tr><td>Disciplina</td><td>Assunto</td><td>Questões</td>"
        "<td>Acertos</td><td>%</td><td></td></tr></thead>"
        f"<tbody>{rows}</tbody></table>{pagination}"
    )


def mock_panel(router=respx) -> None:
    router.post(f"{ADMIN}/intent/login").respond(200, text="ok")
    router.get(f"{ADMIN}/alunos/index", params={"aid": "s1"}).respond(
        200,
        text=(
            f'<form action="{APP}/intent/ver-painel">'
            '<input name="id" value="s1"><input name="cpf" value="synthetic-cpf">'
            '<input name="adm_id" value="synthetic-admin">'
            '<input name="token" value="synthetic-panel-token"></form>'
        ),
    )
    router.post(f"{APP}/intent/ver-painel").respond(
        302, headers={"location": "/painel/", "set-cookie": "panel=synthetic; Path=/"}
    )
    router.get(f"{APP}/painel/").respond(
        200, text=f'<a href="{LAUNCH_PATH}">Lançamentos de Questões</a>'
    )


@respx.mock
def test_question_bundle_automatically_fetches_all_launch_pages_before_generation(
    test_settings: Settings,
) -> None:
    mock_panel()
    first = launch_row("Disciplina fictícia", "Assunto fictício", "2026-08-03", 4, 3)
    second = launch_row("Disciplina fictícia", "Assunto fictício", "2026-07-31", 5, 1)
    respx.get(f"{APP}{LAUNCH_PATH}", params__eq={}).respond(200, text=launch_page(first, last=2))
    respx.get(f"{APP}{LAUNCH_PATH}", params={"p": "2"}).respond(
        200, text=launch_page(second, page=2, last=2)
    )
    respx.post(f"{ADMIN}/intent/cadastrar-relatorio-coach").respond(
        200, json={"result": True, "data": [{"id": "s1", "token": "synthetic-key"}]}
    )
    for model in ("desempenho", "questoes", "aluno"):
        respx.get(
            f"{ADMIN}/documentos/relatorios/{model}", params={"key": "synthetic-key"}
        ).respond(200, text=f"<h1>Relatório {model}</h1>")
    bundle = TutoryClient(test_settings).generate_report_bundle(
        "s1", date(2026, 8, 1), date(2026, 8, 31), grouping="dia"
    )
    assert "lancamentos-questoes" in bundle.documents
    assert first in bundle.documents["lancamentos-questoes"]
    assert second in bundle.documents["lancamentos-questoes"]
    paths = [call.request.url.path for call in respx.calls]
    assert max(i for i, path in enumerate(paths) if path == LAUNCH_PATH) < paths.index(
        "/intent/cadastrar-relatorio-coach"
    )
    assert all(
        "authorization" not in call.request.headers
        for call in respx.calls
        if call.request.url.host == "app.tutory.com.br"
    )


def scoped_question_html() -> str:
    html = question_html(labels=["2026/08/03"], total=4, headline_correct=3, correct=[3], wrong=[1])
    html = html.replace(
        "<tbody></tbody>",
        "<tbody><tr><td>Disciplina fictícia</td><td>Assunto fictício</td><td>75%</td></tr></tbody>",
    )
    return html.replace(
        "datasets: []",
        "datasets: [{label: 'Disciplina fictícia', data: [{x: 4, y: 3, r: 1}]}]",
    )


def test_question_parser_enriches_own_topic_counts_for_requested_period() -> None:
    rows = launch_row("Disciplina fictícia", "Assunto fictício", "2026-08-03", 4, 3)
    rows += launch_row("Disciplina fictícia", "Assunto fictício", "2026-07-31", 5, 1)
    questions = parse_question_report(
        scoped_question_html(),
        period_start=date(2026, 8, 1),
        period_end=date(2026, 8, 31),
        topic_launches_html=f"<table><tbody>{rows}</tbody></table>",
    )
    topic = questions.topics[0]
    assert (topic.total, topic.correct, topic.wrong) == (4, 3, 1)
    assert topic.execution_status == "recorded"
    assert topic.source_period.period_start == date(2026, 8, 1)
    assert questions.model_dump(mode="json")["topics"][0]["total"] == 4


def test_question_parser_rejects_launch_snapshot_missing_monthly_questions() -> None:
    with pytest.raises(TutoryContractChanged, match="topic_launch_totals_mismatch"):
        parse_question_report(
            scoped_question_html(),
            period_start=date(2026, 8, 1),
            period_end=date(2026, 8, 31),
            topic_launches_html="<table><tbody></tbody></table>",
        )


@pytest.fixture
def synthetic_http():
    """Strict mocked transport; unused failure-path routes are permitted."""
    with respx.mock(assert_all_called=False) as router:
        yield router


def assert_collection_stopped_before_generation(synthetic_http: respx.MockRouter) -> None:
    assert not any(
        call.request.url.path == TutoryClient.GENERATE_PATH for call in synthetic_http.calls
    )
    assert all(
        call.request.url.host in {"admin.tutory.com.br", "app.tutory.com.br"}
        for call in synthetic_http.calls
    )
    assert all(
        "authorization" not in call.request.headers
        for call in synthetic_http.calls
        if call.request.url.host == "app.tutory.com.br"
    )


def generate_questions(client: TutoryClient):
    return client.generate_report_bundle(
        "s1", date(2026, 8, 1), date(2026, 8, 31), models=("questoes",)
    )


@pytest.mark.parametrize(
    "location",
    [
        "https://hostile.invalid/painel/",
        "//hostile.invalid/painel/",
        "http://app.tutory.com.br/painel/",
        "https://***@hostile.invalid/painel/",
        "/painel/?token=synthetic-panel-token",
        "/painel/#fragment",
        "/intent/ver-painel",
    ],
)
def test_hostile_panel_redirect_is_not_followed_or_given_credentials(
    test_settings: Settings,
    synthetic_http: respx.MockRouter,
    location: str,
) -> None:
    mock_panel(synthetic_http)
    synthetic_http.post(f"{APP}/intent/ver-painel").respond(307, headers={"location": location})
    with pytest.raises(TutoryContractChanged, match="topic_launch_redirect_unverified"):
        generate_questions(TutoryClient(test_settings))
    assert_collection_stopped_before_generation(synthetic_http)
    assert [call.request.url.path for call in synthetic_http.calls] == [
        "/intent/login",
        "/alunos/index",
        "/intent/ver-painel",
    ]
    access = synthetic_http.calls[-1].request
    assert parse_qs(access.content.decode())["token"] == ["synthetic-panel-token"]
    assert "test-password" not in access.content.decode()
    assert "test-token" not in access.content.decode()


@pytest.mark.parametrize(
    "target",
    [
        "https://hostile.invalid/painel/questoes/lancamento",
        "//hostile.invalid/painel/questoes/lancamento",
        "http://app.tutory.com.br/painel/questoes/lancamento",
        "https://***@hostile.invalid/painel/questoes/lancamento",
        "/painel/questoes/lancamento?token=synthetic-panel-token",
        "/painel/questoes/lancamento?p=2",
        "/painel/questoes/lancamento#fragment",
        "/painel/config/pausar-plano",
    ],
)
def test_hostile_launch_navigation_is_rejected_before_request(
    test_settings: Settings,
    synthetic_http: respx.MockRouter,
    target: str,
) -> None:
    mock_panel(synthetic_http)
    synthetic_http.get(f"{APP}/painel/").respond(
        200, text=f'<a href="{target}">Lançamentos de Questões</a>'
    )
    with pytest.raises(TutoryContractChanged, match="topic_launch_.*unverified"):
        generate_questions(TutoryClient(test_settings))
    assert_collection_stopped_before_generation(synthetic_http)
    assert synthetic_http.calls[-1].request.url == f"{APP}/painel/"
    assert not any(call.request.url.path == LAUNCH_PATH for call in synthetic_http.calls)


def test_wrong_student_panel_form_id_blocks_panel_access_and_generation(
    test_settings: Settings,
    synthetic_http: respx.MockRouter,
) -> None:
    mock_panel(synthetic_http)
    synthetic_http.get(f"{ADMIN}/alunos/index", params={"aid": "s1"}).respond(
        200,
        text=(
            f'<form action="{APP}/intent/ver-painel">'
            '<input name="id" value="s2"><input name="cpf" value="synthetic-cpf">'
            '<input name="adm_id" value="synthetic-admin">'
            '<input name="token" value="synthetic-panel-token"></form>'
        ),
    )
    with pytest.raises(TutoryContractChanged, match="topic_launch_identity_unverified"):
        generate_questions(TutoryClient(test_settings))
    assert_collection_stopped_before_generation(synthetic_http)
    assert not any(call.request.url.host == "app.tutory.com.br" for call in synthetic_http.calls)


@pytest.mark.parametrize(
    "scenario,error,expected_pages",
    [
        ("missing_next", "topic_launch_pagination_incomplete", 1),
        ("changing_last", "topic_launch_pagination_changed", 2),
        ("duplicate_page", "topic_launch_duplicate_page", 2),
        ("cap", "topic_launch_pagination_unverified", 1),
    ],
)
def test_incomplete_or_unstable_pagination_blocks_generation(
    test_settings: Settings,
    synthetic_http: respx.MockRouter,
    scenario: str,
    error: str,
    expected_pages: int,
) -> None:
    mock_panel(synthetic_http)
    row = launch_row("Synthetic discipline", "Synthetic topic", "2026-08-03", 4, 3)
    first = launch_page(row, last=3)
    second = launch_page(
        launch_row("Synthetic discipline", "Other topic", "2026-08-04", 5, 2),
        page=2,
        last=3,
    )
    if scenario == "missing_next":
        first = first.replace('<li><a href="?p=2">2</a></li>', "")
    elif scenario == "changing_last":
        second = launch_page(
            launch_row("Synthetic discipline", "Other topic", "2026-08-04", 5, 2),
            page=2,
            last=2,
        )
    elif scenario == "duplicate_page":
        second = launch_page(row, page=2, last=3)
    elif scenario == "cap":
        first = launch_page(row, last=TutoryClient.MAX_QUESTION_LAUNCH_PAGES + 1)
    synthetic_http.get(f"{APP}{LAUNCH_PATH}", params__eq={}).respond(200, text=first)
    synthetic_http.get(f"{APP}{LAUNCH_PATH}", params={"p": "2"}).respond(200, text=second)
    with pytest.raises(TutoryContractChanged, match=error):
        generate_questions(TutoryClient(test_settings))
    assert_collection_stopped_before_generation(synthetic_http)
    assert (
        sum(call.request.url.path == LAUNCH_PATH for call in synthetic_http.calls) == expected_pages
    )


def test_hostile_pagination_target_is_not_requested(
    test_settings: Settings,
    synthetic_http: respx.MockRouter,
) -> None:
    mock_panel(synthetic_http)
    row = launch_row("Synthetic discipline", "Synthetic topic", "2026-08-03", 4, 3)
    html = launch_page(row, last=3).replace(
        'href="?p=2"', 'href="https://hostile.invalid/steal?p=2"'
    )
    synthetic_http.get(f"{APP}{LAUNCH_PATH}", params__eq={}).respond(200, text=html)
    with pytest.raises(TutoryContractChanged, match="topic_launch_navigation_unverified"):
        generate_questions(TutoryClient(test_settings))
    assert_collection_stopped_before_generation(synthetic_http)
    assert sum(call.request.url.path == LAUNCH_PATH for call in synthetic_http.calls) == 1


def test_launch_network_failure_exhausts_retry_budget_before_generation(
    test_settings: Settings,
    synthetic_http: respx.MockRouter,
) -> None:
    mock_panel(synthetic_http)
    route = synthetic_http.get(f"{APP}{LAUNCH_PATH}").mock(
        side_effect=httpx.ConnectError("synthetic network failure")
    )
    waits = []
    client = TutoryClient(test_settings, sleep=waits.append)
    with pytest.raises(TutoryTemporaryError, match="configured attempts"):
        generate_questions(client)
    assert route.call_count == test_settings.tutory_http_max_attempts
    assert client.stats["http_retries"] == test_settings.tutory_http_max_attempts - 1
    assert_collection_stopped_before_generation(synthetic_http)


@pytest.mark.parametrize(
    "models",
    [
        ("desempenho",),
        ("aluno",),
        ("desempenho", "aluno"),
        ("horas-liquidas", "progresso"),
    ],
)
def test_models_without_questions_never_collect_launches(
    test_settings: Settings,
    synthetic_http: respx.MockRouter,
    models: tuple[str, ...],
) -> None:
    generation = synthetic_http.post(f"{ADMIN}{TutoryClient.GENERATE_PATH}").respond(
        200, json={"result": True, "data": [{"token": "synthetic-key"}]}
    )
    for model in models:
        synthetic_http.get(f"{ADMIN}{TutoryClient.DOCUMENT_PATHS[model]}").respond(
            200, text=f"<h1>Relatório {model}</h1>"
        )
    bundle = TutoryClient(test_settings).generate_report_bundle(
        "s1",
        date(2026, 8, 1),
        date(2026, 8, 31),
        models=models,
    )
    assert set(bundle.documents) == set(models)
    assert generation.call_count == 1
    assert all(call.request.url.host == "admin.tutory.com.br" for call in synthetic_http.calls)
    assert not any(
        call.request.url.path
        in {
            "/intent/login",
            "/alunos/index",
            LAUNCH_PATH,
        }
        for call in synthetic_http.calls
    )


def test_two_student_bundles_use_fresh_sessions_and_separate_launches(
    test_settings: Settings,
    synthetic_http: respx.MockRouter,
) -> None:
    client = TutoryClient(test_settings)
    login = synthetic_http.post(f"{ADMIN}/intent/login").mock(
        side_effect=[
            httpx.Response(200, headers={"set-cookie": "admin_session=first; Path=/"}),
            httpx.Response(200, headers={"set-cookie": "admin_session=second; Path=/"}),
        ]
    )
    for student_id in ("s1", "s2"):
        synthetic_http.get(f"{ADMIN}/alunos/index", params={"aid": student_id}).respond(
            200,
            text=(
                f'<form action="{APP}/intent/ver-painel">'
                f'<input name="id" value="{student_id}">'
                '<input name="cpf" value="synthetic-cpf">'
                '<input name="adm_id" value="synthetic-admin">'
                f'<input name="token" value="synthetic-panel-{student_id}"></form>'
            ),
        )
    access = synthetic_http.post(f"{APP}/intent/ver-painel").mock(
        side_effect=[
            httpx.Response(302, headers={"location": "/painel/", "set-cookie": "panel=s1; Path=/"}),
            httpx.Response(302, headers={"location": "/painel/", "set-cookie": "panel=s2; Path=/"}),
        ]
    )
    synthetic_http.get(f"{APP}/painel/").respond(
        200, text=f'<a href="{LAUNCH_PATH}">Lançamentos de Questões</a>'
    )
    rows = [
        launch_row("Synthetic discipline", "Topic one", "2026-08-03", 4, 3),
        launch_row("Synthetic discipline", "Topic two", "2026-08-04", 7, 5),
    ]
    # A real single-page launch table may omit pagination entirely.
    launches = synthetic_http.get(f"{APP}{LAUNCH_PATH}").mock(
        side_effect=[
            httpx.Response(200, text=launch_page(row).split('<ul class="pagination">')[0])
            for row in rows
        ]
    )
    generation = synthetic_http.post(f"{ADMIN}{TutoryClient.GENERATE_PATH}").mock(
        side_effect=[
            httpx.Response(200, json={"result": True, "data": [{"token": "synthetic-key-s1"}]}),
            httpx.Response(200, json={"result": True, "data": [{"token": "synthetic-key-s2"}]}),
        ]
    )
    for student_id in ("s1", "s2"):
        synthetic_http.get(
            f"{ADMIN}/documentos/relatorios/questoes",
            params={
                "key": f"synthetic-key-{student_id}",
            },
        ).respond(200, text="<h1>Relatório sintético</h1>")
    bundles = [
        client.generate_report_bundle(
            student_id,
            date(2026, 8, 1),
            date(2026, 8, 31),
            models=("questoes",),
        )
        for student_id in ("s1", "s2")
    ]
    assert (
        login.call_count == access.call_count == launches.call_count == generation.call_count == 2
    )
    for index, student_id in enumerate(("s1", "s2")):
        assert "cookie" not in login.calls[index].request.headers
        assert "authorization" not in login.calls[index].request.headers
        assert "cookie" not in access.calls[index].request.headers
        assert parse_qs(access.calls[index].request.content.decode())["id"] == [student_id]
        assert parse_qs(access.calls[index].request.content.decode())["token"] == [
            f"synthetic-panel-{student_id}"
        ]
        assert launches.calls[index].request.headers["cookie"] == f"panel={student_id}"
        assert "authorization" not in launches.calls[index].request.headers
        assert parse_qs(generation.calls[index].request.content.decode())["alunos[]"] == [
            student_id
        ]
        assert generation.calls[index].request.headers["cookie"] == (
            "admin_session=first" if index == 0 else "admin_session=second"
        )
        assert bundles[index].key == f"synthetic-key-{student_id}"
        assert rows[index] in bundles[index].documents["lancamentos-questoes"]
        assert rows[1 - index] not in bundles[index].documents["lancamentos-questoes"]
