from logging import getLogger

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

logger = getLogger(__name__)

_is_sqlite = settings.database_url.startswith("sqlite")

# Engine creation — SQLite gets WAL mode; PostgreSQL gets connection pooling
_engine = create_engine(
    settings.database_url,
    **(
        {"connect_args": {"check_same_thread": False}}
        if _is_sqlite
        else {
            "pool_size": 5,
            "max_overflow": 10,
            "pool_pre_ping": True,
        }
    ),
)

# WAL mode is SQLite-only
if _is_sqlite:

    @event.listens_for(_engine, "connect")
    def set_wal_mode(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

else:
    logger.info(
        "PostgreSQL detected (DATABASE_URL=%r). "
        "Using connection pool (pool_size=5, max_overflow=10).",
        settings.database_url[:30],
    )

engine = _engine

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()
