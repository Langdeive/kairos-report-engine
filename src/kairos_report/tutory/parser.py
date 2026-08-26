from __future__ import annotations

import json
import re
from typing import Any

from selectolax.parser import HTMLParser, Node

from kairos_report.errors import TutoryContractChanged
from kairos_report.schemas import RankedSubject, StudentMetrics, WeeklyMetric


def parse_report(html: str) -> StudentMetrics:
    tree = HTMLParser(html)
    student_name = _required_text(tree.css_first(".aluno-details h4"), "student name")
    course_text = _required_text(tree.css_first(".aluno-details p"), "course")
    course = re.sub(r"^Curso:\s*", "", course_text, flags=re.IGNORECASE)

    metrics = _label_value_map(tree, ".metric-card", ".metric-label", ".metric-value")
    required_metrics = {
        "Total de Horas": "total de horas",
        "% de acertos": "% de acertos",
        "Progresso Geral": "progresso geral",
        "Dias de Estudo": "dias de estudo",
    }
    for public_label, normalized_label in required_metrics.items():
        if normalized_label not in metrics:
            raise TutoryContractChanged(f"Tutory report is missing metric: {public_label}")

    insights = _label_value_map(tree, ".insight-card", "h4", "p")
    for label in ("média de tempo", "matéria mais estudada", "matéria menos estudada"):
        if label not in insights:
            raise TutoryContractChanged(f"Tutory report is missing insight: {label}")

    chart_data = _parse_chart_data(tree)
    weekly = _weekly_metrics(chart_data)

    return StudentMetrics(
        student_name=student_name,
        course=course,
        total_hours=_parse_hours(metrics["total de horas"], "Total de Horas"),
        accuracy_percent=_parse_number(metrics["% de acertos"], "% de acertos"),
        plan_progress_percent=_parse_number(metrics["progresso geral"], "Progresso Geral"),
        study_days=int(_parse_number(metrics["dias de estudo"], "Dias de Estudo")),
        average_study_hours=_parse_hours(insights["média de tempo"], "Média de tempo"),
        most_studied_subject=insights["matéria mais estudada"],
        least_studied_subject=insights["matéria menos estudada"],
        ranking=_parse_ranking(tree),
        weekly=weekly,
        modality_hours=_number_mapping(chart_data.get("modalidades"), "modalidades"),
        subject_progress=_paired_mapping(
            _mapping(chart_data, "progressoDisciplina"),
            "disciplinas",
            "percentuais",
            "progressoDisciplina",
        ),
        performance_by_area=_paired_mapping(
            _mapping(chart_data, "performance"),
            "disciplinas",
            "valores",
            "performance",
        ),
    )


def _required_text(node: Node | None, field: str) -> str:
    value = node.text(strip=True) if node is not None else ""
    if not value:
        raise TutoryContractChanged(f"Tutory report is missing {field}")
    return value


def _normalize_label(value: str) -> str:
    return " ".join(value.casefold().split())


def _label_value_map(
    tree: HTMLParser, card_selector: str, label_selector: str, value_selector: str
) -> dict[str, str]:
    result: dict[str, str] = {}
    for card in tree.css(card_selector):
        label_node = card.css_first(label_selector)
        value_node = card.css_first(value_selector)
        if label_node is None or value_node is None:
            continue
        label = _normalize_label(label_node.text(strip=True))
        value = value_node.text(strip=True)
        if label and value:
            result[label] = value
    return result


def _parse_number(value: str, field: str) -> float:
    match = re.search(r"-?\d+(?:[.,]\d+)?", value)
    if match is None:
        raise TutoryContractChanged(f"Tutory report has an invalid numeric value for {field}")
    return float(match.group(0).replace(",", "."))


def _parse_hours(value: str, field: str) -> float:
    hours_match = re.search(r"(\d+(?:[.,]\d+)?)\s*h", value, flags=re.IGNORECASE)
    minutes_match = re.search(r"(\d+)\s*(?:m|min)", value, flags=re.IGNORECASE)
    if hours_match is None and minutes_match is None:
        return _parse_number(value, field)
    hours = float(hours_match.group(1).replace(",", ".")) if hours_match else 0.0
    minutes = int(minutes_match.group(1)) if minutes_match else 0
    return round(hours + minutes / 60, 4)


def _parse_ranking(tree: HTMLParser) -> list[RankedSubject]:
    ranking: list[RankedSubject] = []
    for row in tree.css(".ranking-table tbody tr"):
        cells = row.css("td")
        if len(cells) == 1:
            continue
        if len(cells) != 4:
            raise TutoryContractChanged("Tutory report ranking has an unexpected column count")
        ranking.append(
            RankedSubject(
                rank=int(_parse_number(cells[0].text(strip=True), "ranking position")),
                name=_required_text(cells[1], "ranking subject"),
                accuracy_percent=_parse_number(cells[2].text(strip=True), "ranking accuracy"),
                study_hours=_parse_hours(cells[3].text(strip=True), "ranking study time"),
            )
        )
    return ranking


def _parse_chart_data(tree: HTMLParser) -> dict[str, Any]:
    script = next((node.text() for node in tree.css("script") if "chartData" in node.text()), None)
    if script is None:
        raise TutoryContractChanged("Tutory report is missing chartData")
    assignment = script.find("chartData")
    start = script.find("{", assignment)
    if start < 0:
        raise TutoryContractChanged("Tutory report chartData has no object")
    block = _balanced_object(script, start)
    json_text = re.sub(
        r"([,{]\s*)([A-Za-z_$][\w$]*)\s*:",
        r'\1"\2":',
        block,
    )
    json_text = re.sub(r",\s*([}\]])", r"\1", json_text)
    try:
        payload: object = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise TutoryContractChanged("Tutory report chartData is not parseable") from exc
    if not isinstance(payload, dict):
        raise TutoryContractChanged("Tutory report chartData is not an object")
    return {str(key): value for key, value in payload.items()}


def _balanced_object(text: str, start: int) -> str:
    depth = 0
    quote: str | None = None
    escaped = False
    for index in range(start, len(text)):
        character = text[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in {'"', "'"}:
            quote = character
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    raise TutoryContractChanged("Tutory report chartData object is incomplete")


def _mapping(container: dict[str, Any], key: str) -> dict[str, Any]:
    value = container.get(key)
    if not isinstance(value, dict):
        raise TutoryContractChanged(f"Tutory report chartData.{key} is not an object")
    return {str(item_key): item_value for item_key, item_value in value.items()}


def _string_list(value: object, field: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TutoryContractChanged(f"Tutory report {field} is not a string list")
    return value


def _number_list(value: object, field: str) -> list[float]:
    if not isinstance(value, list) or not all(
        isinstance(item, int | float) and not isinstance(item, bool) for item in value
    ):
        raise TutoryContractChanged(f"Tutory report {field} is not a numeric list")
    return [float(item) for item in value]


def _number_mapping(value: object, field: str) -> dict[str, float]:
    if value == []:
        return {}
    if not isinstance(value, dict) or not all(
        isinstance(item, int | float) and not isinstance(item, bool) for item in value.values()
    ):
        raise TutoryContractChanged(f"Tutory report {field} is not a numeric object")
    return {str(key): float(item) for key, item in value.items()}


def _paired_mapping(
    container: dict[str, Any], labels_key: str, values_key: str, field: str
) -> dict[str, float]:
    labels = _string_list(container.get(labels_key), f"{field}.{labels_key}")
    values = _number_list(container.get(values_key), f"{field}.{values_key}")
    if len(labels) != len(values):
        raise TutoryContractChanged(f"Tutory report {field} series lengths differ")
    return dict(zip(labels, values, strict=True))


def _weekly_metrics(chart_data: dict[str, Any]) -> list[WeeklyMetric]:
    progress = _mapping(chart_data, "progressoMensal")
    labels = _string_list(progress.get("labels"), "progressoMensal.labels")
    hours = _number_list(progress.get("horas"), "progressoMensal.horas")
    targets = _number_list(progress.get("meta"), "progressoMensal.meta")
    if not (len(labels) == len(hours) == len(targets)):
        raise TutoryContractChanged("Tutory report weekly series lengths differ")

    study_hours = _mapping(chart_data, "horasEstudo")
    peers = _number_mapping(study_hours.get("mediaTopAlunos"), "horasEstudo.mediaTopAlunos")
    return [
        WeeklyMetric(
            label=label,
            hours=hours[index],
            target_hours=targets[index],
            peer_average_hours=peers.get(label),
        )
        for index, label in enumerate(labels)
    ]
