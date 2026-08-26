from collections.abc import Iterator
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy.orm import Session

from kairos_report.config import Settings
from kairos_report.db import create_engine_for
from kairos_report.models import Base


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    return Settings(
        tutory_api_token=SecretStr("test-token"),
        tutory_account="test-account",
        tutory_password=SecretStr("test-password"),
        data_key=SecretStr(Fernet.generate_key().decode()),
        data_dir=tmp_path,
    )


@pytest.fixture
def db_session(test_settings: Settings) -> Iterator[Session]:
    engine = create_engine_for(test_settings)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()
