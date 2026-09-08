"""Synthetic daily provider documents; no captured student data."""

import calendar
import json
import re
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "tutory" / "report_page.html"


def performance_html(
    year: int = 2026,
    month: int = 8,
    *,
    hours: list[float] | None = None,
    labels: list[str] | None = None,
    targets: list[float] | None = None,
    lifetime_days: int = 401,
    modalities: dict[str, float] | None = None,
) -> str:
    count = calendar.monthrange(year, month)[1]
    labels = (
        labels
        if labels is not None
        else [f"{year}/{month:02}/{day:02}" for day in range(1, count + 1)]
    )
    hours = hours if hours is not None else [1.0] * 8 + [7.0] + [0.0] * (count - 9)
    targets = targets if targets is not None else [1.0] * len(labels)
    payload = {
        "progressoMensal": {"labels": labels, "horas": hours, "meta": targets},
        "horasEstudo": {
            "labels": labels[:9],
            "horas": hours[:9],
            "mediaTopAlunos": dict.fromkeys(labels, 2.0),
        },
        "modalidades": modalities if modalities is not None else {"Estudo (coach)": sum(hours)},
        "progressoDisciplina": {"disciplinas": ["Português"], "percentuais": [30]},
        "performance": {"disciplinas": ["Português"], "valores": [70]},
    }
    html = FIXTURE.read_text(encoding="utf-8")
    html = html.replace("18h 30m", "1283:30").replace(
        '<p class="metric-value">16</p>', f'<p class="metric-value">{lifetime_days}</p>'
    )
    return re.sub(
        r"const chartData = .*?;",
        lambda _: "const chartData = " + json.dumps(payload) + ";",
        html,
        flags=re.DOTALL,
    )


def question_html(
    *,
    labels: list[str] | None = None,
    correct: list[float] | None = None,
    wrong: list[float] | None = None,
    total: float = 670,
    headline_correct: float = 550,
) -> str:
    labels = labels if labels is not None else ["2026/08/01", "2026/08/31"]
    correct = correct if correct is not None else [500, 50]
    wrong = wrong if wrong is not None else [100, 20]
    return f"""<h1>Relatório de Questões</h1>
    <div class="main-numbers"><h3>{total}</h3></div>
    <div class="main-numbers"><h3>{headline_correct}</h3></div>
    <div class="main-numbers"><h3>{headline_correct / total * 100 if total else 0}</h3></div>
    <table id="tabela_questoes"><tbody></tbody></table>
    <script>
    var chartQuestoesDia = {{data: {{labels: {json.dumps(labels).replace("/", chr(92) + "/")},
      datasets: [{{label: 'questões corretas', data: {json.dumps(correct)}}},
                 {{label: 'questões erradas', data: {json.dumps(wrong)}}}]}}}};
    var chartBolhaQuestoes = {{data: {{datasets: []}}}};
    </script>"""
