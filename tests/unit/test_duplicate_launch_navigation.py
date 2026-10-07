"""Desktop/mobile menu aliases must not be mistaken for ambiguous navigation."""

import pytest
import respx

from kairos_report.config import Settings
from kairos_report.errors import TutoryContractChanged
from kairos_report.tutory.client import TutoryClient
from tests.unit.test_topic_extraction import APP, LAUNCH_PATH, launch_page, mock_panel


@respx.mock
def test_duplicate_panel_menu_links_to_same_destination_are_accepted(
    test_settings: Settings,
) -> None:
    mock_panel()
    respx.get(f"{APP}/painel/").respond(
        200,
        text=(
            f'<nav><a href="{LAUNCH_PATH}">Lançamentos de Questões</a></nav>'
            f'<aside><a href="{APP}{LAUNCH_PATH}">Lançamentos de Questões</a></aside>'
        ),
    )
    respx.get(f"{APP}{LAUNCH_PATH}").respond(200, text=launch_page(""))
    result = TutoryClient(test_settings).read_question_launches("s1")
    assert result == "<table><tbody></tbody></table>"


@respx.mock
def test_duplicate_menu_label_with_hostile_destination_is_rejected(test_settings: Settings) -> None:
    mock_panel()
    respx.get(f"{APP}/painel/").respond(
        200,
        text=(
            f'<a href="{LAUNCH_PATH}">Lançamentos de Questões</a>'
            '<a href="https://hostile.invalid/painel/questoes/lancamento">'
            'Lançamentos de Questões</a>'
        ),
    )
    with pytest.raises(TutoryContractChanged, match="topic_launch_navigation_unverified"):
        TutoryClient(test_settings).read_question_launches("s1")
    assert not any(c.request.url.path == LAUNCH_PATH for c in respx.calls)
    assert all(c.request.url.host != "hostile.invalid" for c in respx.calls)
