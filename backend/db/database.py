"""SQLite DB 연결 및 세션 관리."""
import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# DB 파일 경로: 환경변수 SQLITE_DB_PATH 또는 기본값
_DEFAULT_DB_PATH = Path(__file__).parent.parent / "data" / "screening.db"
DB_PATH = os.environ.get("SQLITE_DB_PATH", str(_DEFAULT_DB_PATH))

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI Depends용 DB 세션 제공."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """테이블 생성 (없을 경우)."""
    # models 임포트 후 metadata 등록 위해 지연 임포트
    from backend.db import models  # noqa: F401

    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
