"""PDF generation for validated report data."""

from kairos_report.pdf.approved_generator import (
    ApprovedReportAssets,
    default_approved_assets,
    generate_approved_report,
)

__all__ = [
    "ApprovedReportAssets",
    "default_approved_assets",
    "generate_approved_report",
]
