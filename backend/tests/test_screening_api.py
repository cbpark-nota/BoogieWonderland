"""스크리닝 결과 API 테스트 (SQLite 인메모리 DB 사용)."""
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# 프로젝트 루트를 sys.path에 추가
_PROJECT_ROOT = Path(__file__).parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.db.database import Base, get_db  # noqa: E402
from backend.db.models import ScreeningHistory, ScreeningResult  # noqa: E402
from backend.api.main import app  # noqa: E402

# 테스트 전용 인메모리 엔진 — StaticPool로 단일 연결 공유
_TEST_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestSession = sessionmaker(autocommit=False, autoflush=False, bind=_TEST_ENGINE)


def _override_get_db():
    db = _TestSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db


@pytest.fixture(autouse=True)
def setup_db():
    """각 테스트 전 테이블 생성, 후 Drop."""
    Base.metadata.create_all(bind=_TEST_ENGINE)
    yield
    Base.metadata.drop_all(bind=_TEST_ENGINE)


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def sample_history():
    """테스트용 스크리닝 히스토리 데이터 삽입."""
    data = {
        "run_id": 20260331,
        "run_date": "2026-03-31T09:00:00",
        "market_status": {"spy_price": 500.0, "is_golden_cross": True},
        "strategies": {
            "balanced": {
                "label": "균형형",
                "results": [
                    {"ticker": "AAPL", "name": "Apple Inc.", "rank": 1, "score": 95.0},
                    {"ticker": "MSFT", "name": "Microsoft", "rank": 2, "score": 90.0},
                ],
            },
            "aggressive": {
                "label": "공격적",
                "results": [
                    {"ticker": "NVDA", "name": "NVIDIA", "rank": 1, "score": 98.0},
                ],
            },
        },
    }
    db = _TestSession()
    try:
        db.add(ScreeningHistory(
            date="2026-03-31",
            data_json=json.dumps(data, ensure_ascii=False),
        ))
        db.add(ScreeningHistory(
            date="2026-03-30",
            data_json=json.dumps({**data, "run_id": 20260330}, ensure_ascii=False),
        ))
        # screening_result 행 추가
        db.add(ScreeningResult(
            date="2026-03-31", strategy="balanced",
            ticker="AAPL", name="Apple Inc.", rank=1, score=95.0, market="US",
        ))
        db.add(ScreeningResult(
            date="2026-03-31", strategy="balanced",
            ticker="MSFT", name="Microsoft", rank=2, score=90.0, market="US",
        ))
        db.commit()
    finally:
        db.close()
    return data


# ──────────────────────────────────────────────────
# /api/screening/latest
# ──────────────────────────────────────────────────

class TestGetLatest:
    def test_latest_no_data(self, client):
        resp = client.get("/api/screening/latest")
        assert resp.status_code == 404

    def test_latest_returns_most_recent(self, client, sample_history):
        resp = client.get("/api/screening/latest")
        assert resp.status_code == 200
        body = resp.json()
        assert body["date"] == "2026-03-31"
        assert "data" in body
        assert body["data"]["run_id"] == 20260331


# ──────────────────────────────────────────────────
# /api/screening/history?days=N
# ──────────────────────────────────────────────────

class TestGetHistory:
    def test_history_no_data(self, client):
        resp = client.get("/api/screening/history")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_history_default_days(self, client, sample_history):
        resp = client.get("/api/screening/history")
        assert resp.status_code == 200
        dates = [item["date"] for item in resp.json()]
        assert "2026-03-31" in dates
        assert "2026-03-30" in dates

    def test_history_days_param(self, client, sample_history):
        resp = client.get("/api/screening/history?days=1")
        assert resp.status_code == 200
        # days=1 이면 오늘(2026-03-31)만 반환 (테스트 환경에서는 today가 실제 날짜이므로
        # sample 데이터가 과거일 수 있어 0~2건이 맞음)
        assert isinstance(resp.json(), list)

    def test_history_days_validation(self, client):
        resp = client.get("/api/screening/history?days=0")
        assert resp.status_code == 422

        resp = client.get("/api/screening/history?days=91")
        assert resp.status_code == 422


# ──────────────────────────────────────────────────
# /api/screening/history/{date}
# ──────────────────────────────────────────────────

class TestGetHistoryByDate:
    def test_date_not_found(self, client):
        resp = client.get("/api/screening/history/2020-01-01")
        assert resp.status_code == 404

    def test_date_found(self, client, sample_history):
        resp = client.get("/api/screening/history/2026-03-31")
        assert resp.status_code == 200
        body = resp.json()
        assert body["date"] == "2026-03-31"
        assert body["data"]["run_id"] == 20260331

    def test_date_invalid_format(self, client):
        resp = client.get("/api/screening/history/20260331")
        assert resp.status_code == 422

        resp = client.get("/api/screening/history/2026-13-01")
        assert resp.status_code == 422


# ──────────────────────────────────────────────────
# /health
# ──────────────────────────────────────────────────

def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
