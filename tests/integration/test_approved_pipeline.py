from datetime import date
from pathlib import Path

import pytest
from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.orm import Session

from kairos_report.config import Settings
from kairos_report.data.service import ReportDataService
from kairos_report.db import create_engine_for
from kairos_report.errors import TutoryContractChanged
from kairos_report.models import ReportStatus, StudentReport
from kairos_report.pdf import generate_approved_report
from kairos_report.tutory.client import TutoryStudent
from kairos_report.tutory.parser import parse_student_activity_report
from tests.integration.test_run_service import build_service
from tests.unit.test_approved_generator import approved_mock_data


def scenario(study: bool, questions: bool | None) -> dict:
    data = approved_mock_data()
    if not study:
        data["summary"].update(total_hours=0, study_days=0, inactive_days=31)
        data["weekly_evolution"].update(weeks=[], adherence_percent=None)
        data["modalities"].update(hours={}, total_hours=0, shares_percent={})
    if questions is None:
        data["questions"] = None
    elif not questions:
        data["questions"].update(
            total=0, correct=0, wrong=0, accuracy_percent=0, weekly=[], disciplines=[], topics=[]
        )
    return data


@pytest.mark.parametrize(
    ("study", "questions", "pages"),
    [
        (True, True, 7),
        (True, False, 4),
        (False, True, 7),
        (False, False, 4),
        (True, None, 4),
    ],
)
def test_independent_empty_sections_render_without_losing_other_data(
    tmp_path: Path,
    study: bool,
    questions: bool | None,
    pages: int,
) -> None:
    output = generate_approved_report(scenario(study, questions), tmp_path / "report.pdf")
    assert len(PdfReader(output).pages) == pages


def test_missing_targets_and_weekly_breakdown_are_renderable(tmp_path: Path) -> None:
    data = approved_mock_data()
    for week in data["weekly_evolution"]["weeks"]:
        week["target_hours"] = 0
    data["weekly_evolution"]["adherence_percent"] = None
    data["questions"]["weekly"] = []
    output = generate_approved_report(data, tmp_path / "report.pdf")
    assert len(PdfReader(output).pages) == 7


def test_zero_accuracy_with_answered_questions_keeps_question_analysis(tmp_path: Path) -> None:
    data = approved_mock_data()
    data["questions"].update(correct=0, wrong=375, accuracy_percent=0)
    for week in data["questions"]["weekly"]:
        week.update(correct=0, wrong=week["total"], accuracy_percent=0)
    output = generate_approved_report(data, tmp_path / "report.pdf")
    assert len(PdfReader(output).pages) == 7


def test_changed_activity_page_is_not_silently_treated_as_no_activity() -> None:
    with pytest.raises(TutoryContractChanged):
        parse_student_activity_report("<html>Login</html>")


def test_many_topics_continue_on_extra_pages_instead_of_overflowing(tmp_path: Path) -> None:
    data = approved_mock_data()
    data["questions"]["topics"] = [
        {"discipline": "Disciplina 1", "topic": f"Assunto {index}", "accuracy_percent": 50}
        for index in range(24)
    ]
    output = generate_approved_report(data, tmp_path / "report.pdf")
    # First three topics on the priorities page; 21 others on three continuation cards.
    assert len(PdfReader(output).pages) == 8


def test_batch_extract_export_and_pdf_preserve_questions_and_activity(
    test_settings: Settings,
    tmp_path: Path,
) -> None:
    service, _ = build_service(test_settings, [TutoryStudent(id="s1", name="Exemplo")])
    run = service.create(date(2026, 8, 1), date(2026, 8, 31), "test", "approved")
    service.extract(run.id)
    data_service = ReportDataService(test_settings)
    result = data_service.generate(run.id, tmp_path / "reports")
    assert result["generated"] == 1
    assert result["complete"] is True
    engine = create_engine_for(test_settings)
    with Session(engine) as session:
        report = session.scalar(select(StudentReport).where(StudentReport.run_id == run.id))
        assert report is not None
        envelope = data_service._envelope(report)
        assert envelope.data is not None
        assert envelope.data.questions.total == 541
        assert envelope.data.student_activity.total_revisions == 3
        assert report.pdf_hash and report.pdf_path
        assert len(PdfReader(report.pdf_path).pages) == 5
        assert report.status.value == "valid"
    engine.dispose()


def test_same_month_new_run_creates_revision_without_unique_constraint_failure(
    test_settings: Settings,
) -> None:
    service, _ = build_service(test_settings, [TutoryStudent(id="s1", name="Exemplo")])
    for _ in range(2):
        run = service.create(date(2026, 8, 1), date(2026, 8, 31), "test", "approved")
        assert service.extract(run.id).valid == 1
    engine = create_engine_for(test_settings)
    with Session(engine) as session:
        revisions = list(session.scalars(select(StudentReport.revision).order_by(StudentReport.id)))
        assert revisions == [1, 2]
    engine.dispose()


def test_batch_does_not_rewrite_previously_approved_reports(test_settings: Settings) -> None:
    service, _ = build_service(test_settings, [TutoryStudent(id="s1", name="Exemplo")])
    run = service.create(date(2026, 8, 1), date(2026, 8, 31), "test", "approved")
    service.extract(run.id)
    engine = create_engine_for(test_settings)
    with Session(engine) as session:
        report = session.scalar(select(StudentReport))
        assert report is not None
        report.status = ReportStatus.APPROVED
        report.pdf_hash = "already-approved"
        report_id = report.id
        session.commit()
    result = ReportDataService(test_settings).generate(run.id)
    assert result["generated"] == 0
    assert result["skipped_report_ids"] == [report_id]
    with Session(engine) as session:
        assert session.get(StudentReport, report_id).pdf_hash == "already-approved"
    engine.dispose()


def test_resuming_with_changed_subset_is_rejected_and_preserves_original_batch(
    test_settings: Settings,
) -> None:
    service, _ = build_service(
        test_settings,
        [
            TutoryStudent(id="s1", name="Um"),
            TutoryStudent(id="s2", name="Dois"),
        ],
    )
    run = service.create(date(2026, 8, 1), date(2026, 8, 31), "test", "approved")
    service.extract(run.id)
    with pytest.raises(ValueError, match="selection is already frozen"):
        service.extract(run.id, ["s1"])
    summary = service.status(run.id)
    assert summary.expected == summary.valid == 2
