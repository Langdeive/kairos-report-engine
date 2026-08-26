import pytest
from cryptography.fernet import Fernet, InvalidToken

from kairos_report.crypto import PhoneCipher, mask_phone


def test_phone_cipher_round_trip_does_not_store_plaintext() -> None:
    cipher = PhoneCipher(Fernet.generate_key().decode())

    encrypted = cipher.encrypt("+55 11 99999-1234")

    assert encrypted != "+55 11 99999-1234"
    assert "+55" not in encrypted
    assert cipher.decrypt(encrypted) == "+55 11 99999-1234"


def test_phone_cipher_rejects_another_key() -> None:
    encrypted = PhoneCipher(Fernet.generate_key().decode()).encrypt("5511999991234")

    with pytest.raises(InvalidToken):
        PhoneCipher(Fernet.generate_key().decode()).decrypt(encrypted)


@pytest.mark.parametrize(
    ("phone", "expected"),
    [
        ("5511999991234", "*********1234"),
        ("1234", "1234"),
        ("", ""),
    ],
)
def test_mask_phone_keeps_only_the_last_four_digits(phone: str, expected: str) -> None:
    assert mask_phone(phone) == expected
