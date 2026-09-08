"""Display source ISO weeks as actual dates, without redistributing totals."""

import re
from collections.abc import Mapping
from datetime import date, timedelta
from typing import Any


def group_four(
    weeks: list[dict[str, Any]], identity: Mapping[str, str], fields: tuple[str, ...]
) -> list[dict[str, Any]]:
    """Merge calendar edges into four shared periods, preserving additive totals."""
    if not weeks:
        return []
    start = date.fromisoformat(identity["period_start"])
    end = date.fromisoformat(identity["period_end"])
    if start > end or (start.year, start.month) != (end.year, end.month):
        raise ValueError("Four-period charts require a single monthly period")
    groups: list[list[date]] = []
    cursor = start
    while cursor <= end:
        last = min(end, cursor + timedelta(days=6 - cursor.weekday()))
        groups.append([cursor, last])
        cursor = last + timedelta(days=1)
    while len(groups) > 4:
        if groups[0][1] - groups[0][0] <= groups[-1][1] - groups[-1][0]:
            first = groups.pop(0)
            groups[0][0] = first[0]
        else:
            last_group = groups.pop()
            groups[-1][1] = last_group[1]
    dated = [re.fullmatch(r"Semana\s+(\d{1,2})/(\d{4})", w["label"].strip(), re.I) for w in weeks]
    if any(dated) and not all(dated):
        raise ValueError("Mixed dated and legacy weekly labels")
    if all(dated):
        output = [{"label": format_interval(a, b), **dict.fromkeys(fields, 0)} for a, b in groups]
        for week, match in zip(weeks, dated, strict=True):
            assert match is not None
            monday = date.fromisocalendar(int(match[2]), int(match[1]), 1)
            interval_label(week["label"], identity)  # Reject out-of-period source records.
            day = max(start, monday)
            index = next(i for i, (a, b) in enumerate(groups) if a <= day <= b)
            for field in fields:
                output[index][field] += week[field]
        return output
    # Legacy/mock series have no calendar contract: preserve chronological totals.
    output = [{"label": f"{i + 1}ª semana", **dict.fromkeys(fields, 0)} for i in range(4)]
    for i, week in enumerate(weeks):
        for field in fields:
            output[min(i, 3)][field] += week[field]
    return output


def format_interval(start: date, end: date) -> str:
    if start == end:
        return start.strftime("%d/%m")
    if start.month == end.month:
        return f"{start:%d}–{end:%d/%m}"
    return f"{start:%d/%m}–{end:%d/%m}"


def interval_label(label: str, identity: Mapping[str, str]) -> str:
    match = re.fullmatch(r"Semana\s+(\d{1,2})/(\d{4})", label.strip(), re.IGNORECASE)
    if not match:
        return label  # Do not invent dates for legacy/mock labels.
    monday = date.fromisocalendar(int(match[2]), int(match[1]), 1)
    start = max(monday, date.fromisoformat(identity["period_start"]))
    end = min(monday + timedelta(days=6), date.fromisoformat(identity["period_end"]))
    if start > end:
        raise ValueError("Source week is outside the report period")
    return format_interval(start, end)
