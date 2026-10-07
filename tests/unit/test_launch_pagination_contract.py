import pytest

from kairos_report.errors import TutoryContractChanged
from kairos_report.tutory.client import TutoryClient
from tests.unit.test_topic_extraction import launch_page, launch_row


def test_real_style_current_page_anchor_is_inert_not_a_navigation_target() -> None:
    html = launch_page(launch_row("Synthetic", "Synthetic", "2026-08-01", 2, 1), last=2)
    html = html.replace('href="?">1', 'href="#!">1')
    rows, last, next_url = TutoryClient._launch_page(
        html, "https://app.tutory.com.br/painel/questoes/lancamento", 1
    )
    assert len(rows) == 1
    assert last == 2
    assert next_url == "https://app.tutory.com.br/painel/questoes/lancamento?p=2"


def test_inert_marker_with_wrong_current_page_label_is_rejected() -> None:
    html = launch_page(launch_row("Synthetic", "Synthetic", "2026-08-01", 2, 1), last=2)
    html = html.replace('href="?">1', 'href="#!">99')
    with pytest.raises(TutoryContractChanged, match="topic_launch_navigation_unverified"):
        TutoryClient._launch_page(
            html, "https://app.tutory.com.br/painel/questoes/lancamento", 1
        )
