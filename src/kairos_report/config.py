from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, SecretStr


class Settings(BaseModel):
    tutory_api_token: SecretStr
    tutory_account: str
    tutory_password: SecretStr
    data_key: SecretStr
    data_dir: Path
    approval_mode: Literal["required", "automatic"] = "required"
    retention_months: int = Field(default=12, ge=1, le=120)
    timezone: str = "America/Sao_Paulo"
    run_time: str = "20:00"

    @classmethod
    def load(cls) -> Settings:
        token = os.getenv("TUTORY_API_TOKEN")
        if not token:
            raise ValueError("TUTORY_API_TOKEN is required")

        account = os.getenv("TUTORY_ACCOUNT")
        if not account:
            raise ValueError("TUTORY_ACCOUNT is required")

        password = os.getenv("TUTORY_PASSWORD")
        if not password:
            raise ValueError("TUTORY_PASSWORD is required")

        data_key = os.getenv("KAIROS_DATA_KEY")
        if not data_key:
            raise ValueError("KAIROS_DATA_KEY is required")

        return cls(
            tutory_api_token=SecretStr(token),
            tutory_account=account,
            tutory_password=SecretStr(password),
            data_key=SecretStr(data_key),
            data_dir=Path(os.getenv("KAIROS_DATA_DIR", "/opt/data/kairos-reports")),
            approval_mode=os.getenv("KAIROS_APPROVAL_MODE", "required"),  # type: ignore[arg-type]
            retention_months=int(os.getenv("KAIROS_RETENTION_MONTHS", "12")),
            timezone=os.getenv("KAIROS_TIMEZONE", "America/Sao_Paulo"),
            run_time=os.getenv("KAIROS_RUN_TIME", "20:00"),
        )
