from typing import Literal


class KairosReportError(Exception):
    """Base error for failures that should be shown safely by the CLI."""


class TutoryContractChanged(KairosReportError):
    """The Tutory response no longer matches the verified contract."""


class TutoryTemporaryError(KairosReportError):
    """Tutory was temporarily unavailable after bounded retries."""


class TutoryGenerationUncertain(TutoryTemporaryError):
    """Report generation may have succeeded and cannot safely be repeated."""

    def __init__(
        self,
        message: str,
        *,
        retry_after_seconds: float | None = None,
        stop_reason: Literal["upstream", "auth", "retry_paused"] = "upstream",
    ) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds
        self.stop_reason = stop_reason


class TutoryRetryPaused(TutoryTemporaryError):
    """An upstream Retry-After delay must be preserved before further requests."""

    def __init__(self, message: str, *, retry_after_seconds: float) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class ExtractionInProgressError(KairosReportError):
    """Another process holds the extraction lock for this account and data directory."""


class ExtractionCooldownError(KairosReportError):
    """A durable upstream cooldown prevents an extraction from resuming early."""


class TutoryAuthenticationError(KairosReportError):
    """The configured Tutory credential is no longer accepted."""


class InvalidPhone(KairosReportError):
    """A phone number cannot be safely normalized for WhatsApp."""
