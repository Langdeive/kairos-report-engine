from __future__ import annotations

import re

from kairos_report.errors import InvalidPhone


def normalize_brazil_phone(raw: str) -> str:
    """Normalize a Brazilian landline or mobile number to WhatsApp digits."""
    digits = re.sub(r"\D", "", raw)
    if len(digits) in {10, 11}:
        digits = f"55{digits}"
    if len(digits) not in {12, 13} or not digits.startswith("55"):
        raise InvalidPhone("Phone must be a Brazilian number with area code")

    national_number = digits[2:]
    area_code = national_number[:2]
    subscriber = national_number[2:]
    if area_code.startswith("0") or subscriber.startswith("0"):
        raise InvalidPhone("Phone has an invalid area or subscriber code")
    if len(subscriber) == 9 and not subscriber.startswith("9"):
        raise InvalidPhone("Brazilian mobile numbers must start with 9")
    return digits
