from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.config import settings


def test_alembic_upgrade_head_on_fresh_sqlite(tmp_path):
    db_path = tmp_path / "migration_smoke.db"
    database_url = f"sqlite:///{db_path}"
    original_database_url = settings.database_url
    settings.database_url = database_url

    try:
        alembic_cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        command.upgrade(alembic_cfg, "head")

        engine = create_engine(database_url)
        inspector = inspect(engine)
        checkin_columns = {column["name"] for column in inspector.get_columns("checkins")}

        assert "hot_topics" in inspector.get_table_names()
        assert "reminder_deliveries" in inspector.get_table_names()
        assert {"topic_source", "topic_url", "topic_summary", "topic_published_at"} <= checkin_columns
    finally:
        settings.database_url = original_database_url
