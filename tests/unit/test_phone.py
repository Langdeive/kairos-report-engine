import pytest

from kairos_report.errors import InvalidPhone
from kairos_report.tutory.phone import normalize_brazil_phone


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("(11) 99999-1234", "5511999991234"),
        ("+55 11 99999-1234", "5511999991234"),
        ("5511999991234", "5511999991234"),
        ("11 3333-1234", "551133331234"),
    ],
)
def test_normalize_brazil_phone(raw: str, expected: str) -> None:
    assert normalize_brazil_phone(raw) == expected


@pytest.mark.parametrize("raw", ["", "123", "+1 202 555 0199", "55 1 9999-1234"])
def test_normalize_brazil_phone_rejects_invalid_numbers(raw: str) -> None:
    with pytest.raises(InvalidPhone):
        normalize_brazil_phone(raw)
