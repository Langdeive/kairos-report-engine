from __future__ import annotations

from cryptography.fernet import Fernet
from pydantic import SecretStr


class PhoneCipher:
    """Encrypt phone numbers before they are persisted."""

    def __init__(self, key: str | SecretStr) -> None:
        raw_key = key.get_secret_value() if isinstance(key, SecretStr) else key
        self._fernet = Fernet(raw_key.encode())

    def encrypt(self, phone: str) -> str:
        return self._fernet.encrypt(phone.encode()).decode()

    def decrypt(self, encrypted_phone: str) -> str:
        return self._fernet.decrypt(encrypted_phone.encode()).decode()


def mask_phone(phone: str) -> str:
    """Hide all but the last four characters for logs and diagnostics."""
    if len(phone) <= 4:
        return phone
    return f"{'*' * (len(phone) - 4)}{phone[-4:]}"
