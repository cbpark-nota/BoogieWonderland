"""SQLite 기반 경량 FastAPI 앱 엔트리포인트.

PostgreSQL 없이 SQLite만으로 스크리닝 결과 API를 제공한다.
기존 backend/app/main.py(PostgreSQL 풀스택)와 별개로 운영 가능.

실행:
    uvicorn backend.api.main:app --reload --port 8001
"""
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.sql import text

from backend.api.portfolio import router as portfolio_router
from backend.api.screening import router as screening_router
from backend.db.database import get_db, init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="스크리닝 결과 API (SQLite)",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(screening_router)
app.include_router(portfolio_router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/health")
def api_health(db: Session = Depends(get_db)):
    """DB 연결 상태 포함 헬스체크."""
    db_status = "disconnected"
    try:
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except OperationalError:
        pass
    return {
        "status": "ok",
        "db": db_status,
        "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
    }
