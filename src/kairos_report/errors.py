class KairosReportError(Exception):
    """Base error for failures that should be shown safely by the CLI."""


class TutoryContractChanged(KairosReportError):
    """The Tutory response no longer matches the verified contract."""


class TutoryTemporaryError(KairosReportError):
    """Tutory was temporarily unavailable after bounded retries."""


class TutoryAuthenticationError(KairosReportError):
    """The configured Tutory credential is no longer accepted."""


class InvalidPhone(KairosReportError):
    """A phone number cannot be safely normalized for WhatsApp."""
