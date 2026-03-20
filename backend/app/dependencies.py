from typing import Generator

from app.database import SessionLocal


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user():
    # TODO: implement in Phase 1
    raise NotImplementedError("get_current_user will be implemented in Phase 1")
