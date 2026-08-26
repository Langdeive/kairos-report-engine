from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, event
from sqlalchemy import create_engine as sqlalchemy_create_engine
from sqlalchemy.orm import Session, sessionmaker

from kairos_report.config import Settings


def database_path_for(settings: Settings) -> Path:
    return settings.data_dir / "database" / "kairos.sqlite3"


def create_engine_for(settings: Settings) -> Engine:
    database_path = database_path_for(settings)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    engine = sqlalchemy_create_engine(f"sqlite:///{database_path.as_posix()}")

    @event.listens_for(engine, "connect")
    def configure_sqlite(connection: object, _record: object) -> None:
        cursor = connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    return engine


def session_factory_for(settings: Settings) -> sessionmaker[Session]:
    return sessionmaker(create_engine_for(settings), expire_on_commit=False)


@contextmanager
def session_scope(settings: Settings) -> Iterator[Session]:
    factory = session_factory_for(settings)
    with factory() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


def upgrade_database(settings: Settings) -> None:
    project_root = Path(__file__).resolve().parents[2]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path_for(settings).as_posix()}")
    database_path_for(settings).parent.mkdir(parents=True, exist_ok=True)
    command.upgrade(config, "head")
