"""Synthetic empty launch-card contract; no captured HTML or personal data."""

from datetime import date

import pytest
import respx

from kairos_report.config import Settings
from kairos_report.errors import TutoryContractChanged
from kairos_report.tutory.client import TutoryClient
from kairos_report.tutory.parser import parse_question_report
from tests.daily_fixtures import question_html
from tests.unit.test_topic_extraction import APP, LAUNCH_PATH, launch_page, launch_row, mock_panel

EMPTY_CARD = """<div class="card custom-card">
<h2>Questões</h2>
<p>Faça o lançamento de questões na sua plataforma de estudos</p>
<div><h6>Suas Questões</h6>
<p>Faça um novo lançamento de questões em sua plataforma de estudos, basta selecionar uma
 disciplina, um assunto e cadastrar os erros e acertos.</p></div>
</div>"""
LAUNCH_URL = "https://app.tutory.com.br/painel/questoes/lancamento"


@pytest.mark.parametrize(
    "other_card", ["", '<div class="card custom-card"><h2>Outro cartão</h2></div>']
)
def test_complete_scoped_empty_launch_card_is_one_empty_page(other_card: str) -> None:
    assert TutoryClient._launch_page(EMPTY_CARD + other_card, LAUNCH_URL, 1) == ([], 1, None)


def test_wrong_nested_heading_tag_is_not_the_confirmed_empty_card() -> None:
    html = EMPTY_CARD.replace("h6", "h4")
    with pytest.raises(TutoryContractChanged):
        TutoryClient._launch_page(html, LAUNCH_URL, 1)


@pytest.mark.parametrize(
    "html",
    [
        "",
        EMPTY_CARD.replace('<div class="card custom-card">', '<div class="card">'),
        EMPTY_CARD.replace("<h2>Questões</h2>", ""),
        EMPTY_CARD.replace("<h2>Questões</h2>", "<h3>Questões</h3>"),
        EMPTY_CARD.replace(
            "<p>Faça o lançamento de questões na sua plataforma de estudos</p>", ""
        ),
        EMPTY_CARD.replace("<h6>Suas Questões</h6>", ""),
        EMPTY_CARD.replace("cadastrar os erros e acertos.", "cadastrar questões."),
        # All words present, but the nested evidence is outside the card.
        EMPTY_CARD.replace("<div><h6>", "</div><div><h6>"),
        EMPTY_CARD + EMPTY_CARD,
        EMPTY_CARD + "<table><tbody></tbody></table>",
        EMPTY_CARD + '<ul class="pagination"></ul>',
        EMPTY_CARD + '<ul class="pagination"><a href="?p=2">2</a></ul>',
        EMPTY_CARD + "<form></form>",
    ],
    ids=[
        "missing-card", "wrong-class", "missing-heading", "wrong-heading-tag",
        "missing-intro", "missing-nested-title", "partial-instructions", "unscoped-evidence",
        "duplicate-card", "unexpected-table", "empty-pagination",
        "next-page", "form-conflict",
    ],
)
def test_incomplete_or_conflicting_empty_launch_evidence_is_rejected(html: str) -> None:
    with pytest.raises(TutoryContractChanged):
        TutoryClient._launch_page(html, LAUNCH_URL, 1)


def test_empty_launch_card_on_later_page_is_rejected() -> None:
    with pytest.raises(TutoryContractChanged):
        TutoryClient._launch_page(EMPTY_CARD, LAUNCH_URL + "?p=2", 2)


def instructed_table(rows: str, *, page: int = 1) -> str:
    return (
        EMPTY_CARD
        + '<div class="card custom-card"><form><input name="disciplina"></form></div>'
        + '<div class="card custom-card"><h6>Suas Questões</h6>'
        + launch_page(rows, page=page, last=2)
        + '</div>'
    )


@respx.mock
def test_instructions_and_entry_form_do_not_hide_paginated_launches(
    test_settings: Settings,
) -> None:
    mock_panel()
    first = ''.join(
        launch_row('Synthetic', f'Topic {n}', '2026-08-03', 2, 1) for n in range(50)
    )
    last = launch_row('Synthetic', 'Older topic', '2026-07-31', 3, 2)
    respx.get(LAUNCH_URL, params__eq={}).respond(200, text=instructed_table(first))
    second = respx.get(LAUNCH_URL, params={'p': '2'}).respond(
        200, text=instructed_table(last, page=2)
    )
    snapshot = TutoryClient(test_settings).read_question_launches('s1')
    assert snapshot.count('<tr>') == 51
    assert first in snapshot and last in snapshot
    assert second.call_count == 1


def test_instructions_do_not_hide_ambiguous_tables() -> None:
    with pytest.raises(TutoryContractChanged, match='topic_launch_table_unverified'):
        TutoryClient._launch_page(EMPTY_CARD + launch_page('') * 2, LAUNCH_URL, 1)


def test_valid_empty_table_takes_precedence_over_instructions() -> None:
    assert TutoryClient._launch_page(EMPTY_CARD + launch_page(''), LAUNCH_URL, 1) == (
        [], 1, None
    )


@pytest.mark.parametrize("total,correct", [(0, 0), (4, 0), (4, 3)])
@respx.mock
def test_collected_empty_launch_card_preserves_monthly_reconciliation(
    test_settings: Settings, total: int, correct: int,
) -> None:
    mock_panel()
    launch = respx.get(f"{APP}{LAUNCH_PATH}").respond(200, text=EMPTY_CARD)
    snapshot = TutoryClient(test_settings).read_question_launches("s1")
    assert snapshot == "<table><tbody></tbody></table>"
    assert launch.call_count == 1
    assert not any(
        call.request.url.path == TutoryClient.GENERATE_PATH for call in respx.calls
    )
    monthly = question_html(
        labels=["2026/08/03"] if total else [],
        total=total, headline_correct=correct,
        correct=[correct] if total else [], wrong=[total - correct] if total else [],
    )
    if total:
        with pytest.raises(TutoryContractChanged, match="^topic_launch_totals_mismatch$"):
            parse_question_report(
                monthly, period_start=date(2026, 8, 1), period_end=date(2026, 8, 31),
                topic_launches_html=snapshot,
            )
    else:
        questions = parse_question_report(
            monthly, period_start=date(2026, 8, 1), period_end=date(2026, 8, 31),
            topic_launches_html=snapshot,
        )
        assert (questions.total, questions.correct, questions.topics) == (0, 0, [])
