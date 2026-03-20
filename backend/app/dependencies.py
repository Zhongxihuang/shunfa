from typing import Generator

from fastapi import HTTPException

from app.database import SessionLocal


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user():
    # TODO: implement in Phase 1
    raise HTTPException(status_code=401, detail="Authentication not yet implemented")
