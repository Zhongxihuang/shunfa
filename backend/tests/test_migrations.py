import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect

from alembic import command
from alembic.config import Config
from app.config import settings

ALEMBIC_INI = str(Path(__file__).resolve().parents[1] / "alembic.ini")


def _alembic_config(database_url: str) -> Config:
    cfg = Config(ALEMBIC_INI)
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


def _assert_head_schema(database_url: str) -> None:
    engine = create_engine(database_url)
    inspector = inspect(engine)
    checkin_columns = {column["name"] for column in inspector.get_columns("checkins")}

    assert "hot_topics" in inspector.get_table_names()
    assert "reminder_deliveries" in inspector.get_table_names()
    assert {"topic_source", "topic_url", "topic_summary", "topic_published_at"} <= checkin_columns


def test_alembic_upgrade_head_on_fresh_sqlite(tmp_path):
    db_path = tmp_path / "migration_smoke.db"
    database_url = f"sqlite:///{db_path}"
    original_database_url = settings.database_url
    settings.database_url = database_url

    try:
        command.upgrade(_alembic_config(database_url), "head")
        _assert_head_schema(database_url)
    finally:
        settings.database_url = original_database_url


def test_alembic_downgrade_one_revision_and_upgrade_back_on_sqlite(tmp_path):
    db_path = tmp_path / "migration_downgrade_smoke.db"
    database_url = f"sqlite:///{db_path}"
    cfg = _alembic_config(database_url)
    original_database_url = settings.database_url

    try:
        settings.database_url = database_url
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "-1")
        command.upgrade(cfg, "head")
    finally:
        settings.database_url = original_database_url

    _assert_head_schema(database_url)


@pytest.mark.skipif(
    not os.getenv("POSTGRES_TEST_DATABASE_URL"),
    reason="POSTGRES_TEST_DATABASE_URL is required for production-like migration verification",
)
def test_alembic_upgrade_head_on_postgresql():
    database_url = os.environ["POSTGRES_TEST_DATABASE_URL"]
    original_database_url = settings.database_url

    try:
        settings.database_url = database_url
        command.upgrade(_alembic_config(database_url), "head")
        _assert_head_schema(database_url)
    finally:
        settings.database_url = original_database_url
