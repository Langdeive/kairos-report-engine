import pytest
import respx

from kairos_report.config import Settings
from kairos_report.errors import TutoryContractChanged
from kairos_report.tutory.client import TutoryClient
from tests.unit.test_tutory_client import coaching_html, dashboard_html, search_html


@pytest.mark.parametrize("active_match", [True, False])
@respx.mock
def test_saturated_substring_search_reconciles_missing_roster_identity(
    test_settings: Settings, monkeypatch: pytest.MonkeyPatch, active_match: bool
) -> None:
    monkeypatch.setattr(TutoryClient, "RESULT_LIMIT", 2)
    respx.post("https://admin.tutory.com.br/intent/login").respond(200)
    respx.get("https://admin.tutory.com.br/index").respond(200, text=dashboard_html(3))
    respx.get("https://admin.tutory.com.br/alunos/consulta?status=ativos").respond(
        200, text=search_html(["c1"], [])
    )
    respx.get("https://admin.tutory.com.br/alunos/consulta?status=ativos&curso=c1").respond(
        200, text=search_html([], [("s1", "Ana"), ("s2", "Bruno")])
    )
    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        respx.get(
            f"https://admin.tutory.com.br/alunos/consulta?status=ativos&curso=c1&nome={letter}"
        ).respond(200, text=search_html([], [("s1", "Ana"), ("s2", "Bruno")]))
    respx.get("https://admin.tutory.com.br/alunos/coaching").respond(
        200, text=coaching_html(1, 1, ["s1", "s2", "s3"])
    )
    respx.get("https://admin.tutory.com.br/alunos/index?aid=s3").respond(
        200, text='<input name="nome" value="Carla Silva">'
    )
    respx.get("https://admin.tutory.com.br/alunos/consulta?status=ativos&nome=Carla+Silva").respond(
        200, text=search_html([], [("s3", "Carla Silva")] if active_match else [])
    )
    if active_match:
        assert [s.id for s in TutoryClient(test_settings).list_active_students()] == [
            "s1",
            "s2",
            "s3",
        ]
    else:
        with pytest.raises(TutoryContractChanged):
            TutoryClient(test_settings).list_active_students()
