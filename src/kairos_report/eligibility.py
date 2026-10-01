"""Report eligibility, independent of the provider's page layout."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Protocol
from zoneinfo import ZoneInfo

from kairos_report.config import Settings
from kairos_report.errors import KairosReportError, TutoryRetryPaused

EXCLUSION_REASONS = frozenset({"mentorship_too_recent", "study_plan_paused"})


def is_policy_exclusion(reasons: list[str]) -> bool:
    return bool(EXCLUSION_REASONS.intersection(reasons)) and "eligibility_unverified" not in reasons


@dataclass(frozen=True)
class EligibilityEvidence:
    joined_on: date
    pause_periods: tuple[tuple[date, date], ...]

    def reasons(self, on: date, minimum_days: int) -> list[str]:
        if self.joined_on > on or any(start > end for start, end in self.pause_periods):
            return ["eligibility_unverified"]
        reasons = []
        if (on - self.joined_on).days < minimum_days:
            reasons.append("mentorship_too_recent")
        if any(start <= on <= end for start, end in self.pause_periods):
            reasons.append("study_plan_paused")
        return reasons


class EligibilitySource(Protocol):
    def report_eligibility(self, student_id: str) -> EligibilityEvidence: ...


class EligibilityGuard:
    def __init__(
        self, settings: Settings, source: EligibilitySource,
        *, clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._settings = settings
        self._source = source
        self._clock = clock or (lambda: datetime.now(UTC))

    def check(self, student_id: str) -> list[str]:
        if not self._settings.report_eligibility_enabled:
            return []
        on = self._clock().astimezone(ZoneInfo(self._settings.timezone)).date()
        try:
            evidence = self._source.report_eligibility(student_id)
        except TutoryRetryPaused:
            raise
        except KairosReportError:
            return ["eligibility_unverified"]
        if not isinstance(evidence, EligibilityEvidence):
            return ["eligibility_unverified"]
        return evidence.reasons(on, self._settings.mentorship_minimum_days)
