from kairos_report.pdf.layouts.week_dates import interval_label


def test_four_and_five_calendar_weeks_preserve_totals():
    from kairos_report.pdf.layouts.week_dates import group_four

    for start, end, numbers, expected in [
        ("2021-02-01", "2021-02-28", range(5, 9), [1, 1, 1, 1]),
        ("2024-02-01", "2024-02-29", range(5, 10), [2, 1, 1, 1]),
        ("2026-04-01", "2026-04-30", range(14, 19), [1, 1, 1, 2]),
        ("2026-07-01", "2026-07-31", range(27, 32), [2, 1, 1, 1]),
    ]:
        identity = {"period_start": start, "period_end": end}
        rows = [{"label": f"Semana {n}/{start[:4]}", "hours": 1} for n in numbers]
        grouped = group_four(rows, identity, ("hours",))
        assert len(grouped) == 4
        assert [w["hours"] for w in grouped] == expected
        assert sum(w["hours"] for w in grouped) == sum(w["hours"] for w in rows)
        assert group_four([], identity, ("hours",)) == []


def test_august_partial_weeks_are_clipped_to_month():
    identity = {"period_start": "2026-08-01", "period_end": "2026-08-31"}
    assert [interval_label(f"Semana {n}/2026", identity) for n in range(31, 37)] == [
        "01–02/08",
        "03–09/08",
        "10–16/08",
        "17–23/08",
        "24–30/08",
        "31/08",
    ]


def test_other_months_and_unknown_labels():
    assert (
        interval_label("Semana 5/2021", {"period_start": "2021-02-01", "period_end": "2021-02-28"})
        == "01–07/02"
    )
    assert (
        interval_label("Semana 1/2026", {"period_start": "2026-01-01", "period_end": "2026-01-31"})
        == "01–04/01"
    )
    assert (
        interval_label("Semana 3", {"period_start": "2026-08-01", "period_end": "2026-08-31"})
        == "Semana 3"
    )


def test_render_values_group_six_source_intervals_into_four():
    from kairos_report.pdf.layouts.generate_approved_panorama import report_values
    from kairos_report.pdf.layouts.generate_approved_questions_overview import (
        report_values as questions,
    )
    from tests.unit.test_approved_generator import approved_mock_data

    data = approved_mock_data()
    data["identity"].update(period_start="2026-08-01", period_end="2026-08-31")
    data["weekly_evolution"]["weeks"] = [
        {"label": f"Semana {n}/2026", "hours": n - 30, "target_hours": 10} for n in range(31, 37)
    ]
    data["questions"]["weekly"] = [
        {"label": w["label"], "total": 10, "correct": 8, "wrong": 2}
        for w in data["weekly_evolution"]["weeks"]
    ]
    assert report_values(data)["week_hours"] == [3, 3, 4, 11]
    assert report_values(data)["study_labels"] == ["01–09/08", "10–16/08", "17–23/08", "24–31/08"]
    assert [w["total"] for w in questions(data)["weeks"]] == [20, 10, 10, 20]
    from kairos_report.pdf.layouts.generate_approved_constancy import report_values as constancy

    assert constancy(data)["week_target"] == [20, 10, 10, 20]
    data["questions"]["weekly"] = data["questions"]["weekly"][-3:]
    assert [w["total"] for w in questions(data)["weeks"]] == [0, 0, 10, 20]
