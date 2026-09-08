from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, SecretStr


class Settings(BaseModel):
    tutory_api_token: SecretStr | None = None
    tutory_account: str
    tutory_password: SecretStr
    data_key: SecretStr
    data_dir: Path
    approval_mode: Literal["required", "automatic"] = "required"
    retention_months: int = Field(default=12, ge=1, le=120)
    timezone: str = "America/Sao_Paulo"
    run_time: str = "20:00"
    tutory_http_max_attempts: int = Field(default=3, ge=1, le=10)
    tutory_request_spacing_seconds: float = Field(default=1.0, ge=0, le=60)
    tutory_retry_base_seconds: float = Field(default=1.0, ge=0, le=60)
    tutory_retry_max_seconds: float = Field(default=30.0, ge=0, le=3600)
    batch_size: int = Field(default=10, ge=1, le=1000)
    batch_pause_seconds: float = Field(default=30.0, ge=0, le=3600)
    max_consecutive_upstream_failures: int = Field(default=3, ge=1, le=100)

    @classmethod
    def load(cls) -> Settings:
        token = os.getenv("TUTORY_API_TOKEN")
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
            tutory_api_token=SecretStr(token) if token else None,
            tutory_account=account,
            tutory_password=SecretStr(password),
            data_key=SecretStr(data_key),
            data_dir=Path(os.getenv("KAIROS_DATA_DIR", "/opt/data/kairos-reports")),
            approval_mode=os.getenv("KAIROS_APPROVAL_MODE", "required"),  # type: ignore[arg-type]
            retention_months=int(os.getenv("KAIROS_RETENTION_MONTHS", "12")),
            timezone=os.getenv("KAIROS_TIMEZONE", "America/Sao_Paulo"),
            run_time=os.getenv("KAIROS_RUN_TIME", "20:00"),
            tutory_http_max_attempts=int(os.getenv("TUTORY_HTTP_MAX_ATTEMPTS", "3")),
            tutory_request_spacing_seconds=float(
                os.getenv("TUTORY_REQUEST_SPACING_SECONDS", "1")
            ),
            tutory_retry_base_seconds=float(os.getenv("TUTORY_RETRY_BASE_SECONDS", "1")),
            tutory_retry_max_seconds=float(os.getenv("TUTORY_RETRY_MAX_SECONDS", "30")),
            batch_size=int(os.getenv("KAIROS_BATCH_SIZE", "10")),
            batch_pause_seconds=float(os.getenv("KAIROS_BATCH_PAUSE_SECONDS", "30")),
            max_consecutive_upstream_failures=int(
                os.getenv("KAIROS_MAX_CONSECUTIVE_UPSTREAM_FAILURES", "3")
            ),
        )
