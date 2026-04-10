"""FE-BE 연동 통합 테스트 — SQLite 인메모리 DB 사용.

테스트 커버리지:
- GET /api/health  : 헬스체크 (DB 연결 상태 + timestamp)
- Portfolio CRUD → 조회 흐름
- 스크리닝 결과 저장 → 조회 흐름
- API 응답 스키마 검증
"""
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

_PROJECT_ROOT = Path(__file__).parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.db.database import Base, get_db  # noqa: E402
from backend.db.models import Portfolio, ScreeningHistory, ScreeningResult  # noqa: F401
from backend.api.main import app  # noqa: E402

# ─── 테스트 전용 인메모리 엔진 ─────────────────────────────────────────────────

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


@pytest.fixture(autouse=True)
def setup_db():
    """각 테스트 전 테이블 생성, 후 Drop. 기존 override는 복원한다."""
    Base.metadata.create_all(bind=_TEST_ENGINE)
    prev_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _override_get_db
    yield
    if prev_override is not None:
        app.dependency_overrides[get_db] = prev_override
    else:
        app.dependency_overrides.pop(get_db, None)
    Base.metadata.drop_all(bind=_TEST_ENGINE)


@pytest.fixture()
def client():
    return TestClient(app)


# ─── 헬퍼 ─────────────────────────────────────────────────────────────────────

def _insert_screening_history(date: str, run_id: int = None):
    """테스트용 screening_history + screening_result 행 삽입."""
    data = {
        "run_id": run_id or int(date.replace("-", "")),
        "run_date": f"{date}T09:00:00",
        "market_status": {"spy_price": 510.0, "is_golden_cross": True},
        "total_screened": 867,
        "total_passed": 5,
        "strategies": {
            "balanced": {
                "label": "균형형",
                "results": [
                    {"ticker": "AAPL", "name": "Apple Inc.", "rank": 1, "score": 92.5, "market": "US"},
                    {"ticker": "MSFT", "name": "Microsoft", "rank": 2, "score": 88.0, "market": "US"},
                ],
            },
        },
    }
    db = _TestSession()
    try:
        db.add(ScreeningHistory(
            date=date,
            data_json=json.dumps(data, ensure_ascii=False),
        ))
        db.add(ScreeningResult(
            date=date, strategy="balanced",
            ticker="AAPL", name="Apple Inc.", rank=1, score=92.5, market="US",
            data_json=json.dumps({"adx": 28.3, "rsi": 62.1, "atr": 3.2}),
        ))
        db.add(ScreeningResult(
            date=date, strategy="balanced",
            ticker="MSFT", name="Microsoft", rank=2, score=88.0, market="US",
            data_json=json.dumps({"adx": 25.1, "rsi": 58.4, "atr": 4.1}),
        ))
        db.commit()
    finally:
        db.close()
    return data


_PORTFOLIO_PAYLOAD = {
    "ticker": "AAPL",
    "name": "Apple Inc.",
    "entry_price": 180.0,
    "quantity": 10,
    "entry_date": "2026-01-15",
    "stop_loss": 162.0,
    "market": "US",
}


# ─── 1. 헬스체크 API ──────────────────────────────────────────────────────────

class TestApiHealth:
    def test_health_status_ok(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200

    def test_health_schema(self, client):
        body = client.get("/api/health").json()
        assert body["status"] == "ok"
        assert body["db"] in ("connected", "disconnected")
        assert "timestamp" in body

    def test_health_db_connected(self, client):
        """인메모리 DB이므로 connected 반환."""
        body = client.get("/api/health").json()
        assert body["db"] == "connected"

    def test_health_timestamp_format(self, client):
        """timestamp가 ISO-8601 형식인지 확인."""
        from datetime import datetime
        body = client.get("/api/health").json()
        # 파싱 가능하면 OK
        datetime.fromisoformat(body["timestamp"])

    def test_legacy_health_still_works(self, client):
        """/health (레거시) 엔드포인트도 정상."""
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


# ─── 2. 포트폴리오 CRUD → 조회 흐름 ─────────────────────────────────────────

class TestPortfolioCrudFlow:
    def test_empty_list(self, client):
        resp = client.get("/api/portfolio")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_returns_201(self, client):
        resp = client.post("/api/portfolio", json=_PORTFOLIO_PAYLOAD)
        assert resp.status_code == 201

    def test_create_response_schema(self, client):
        body = client.post("/api/portfolio", json=_PORTFOLIO_PAYLOAD).json()
        for field in ("id", "ticker", "name", "entry_price", "quantity",
                      "entry_date", "stop_loss", "market", "created_at", "updated_at"):
            assert field in body, f"응답에 '{field}' 필드 없음"

    def test_create_and_list(self, client):
        client.post("/api/portfolio", json=_PORTFOLIO_PAYLOAD)
        resp = client.get("/api/portfolio")
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["ticker"] == "AAPL"

    def test_create_multiple_and_count(self, client):
        client.post("/api/portfolio", json=_PORTFOLIO_PAYLOAD)
        client.post("/api/portfolio", json={**_PORTFOLIO_PAYLOAD, "ticker": "MSFT"})
        items = client.get("/api/portfolio").json()
        assert len(items) == 2

    def test_update_entry_price(self, client):
        created = client.post("/api/portfolio", json=_PORTFOLIO_PAYLOAD).json()
        item_id = created["id"]
        resp = client.put(f"/api/portfolio/{item_id}", json={"entry_price": 200.0})
        assert resp.status_code == 200
        assert resp.json()["entry_price"] == 200.0

    def test_delete_by_ticker(self, client):
        client.post("/api/portfolio", json=_PORTFOLIO_PAYLOAD)
        resp = client.delete("/api/portfolio/ticker/AAPL")
        assert resp.status_code == 204
        items = client.get("/api/portfolio").json()
        assert len(items) == 0

    def test_delete_by_id(self, client):
        created = client.post("/api/portfolio", json=_PORTFOLIO_PAYLOAD).json()
        resp = client.delete(f"/api/portfolio/{created['id']}")
        assert resp.status_code == 204
        assert client.get("/api/portfolio").json() == []

    def test_delete_nonexistent_returns_404(self, client):
        resp = client.delete("/api/portfolio/9999")
        assert resp.status_code == 404

    def test_summary_empty(self, client):
        resp = client.get("/api/portfolio/summary")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_items"] == 0
        assert body["total_invested"] == 0.0

    def test_summary_after_create(self, client):
        client.post("/api/portfolio", json=_PORTFOLIO_PAYLOAD)
        body = client.get("/api/portfolio/summary").json()
        assert body["total_items"] == 1
        # entry_price=180, quantity=10
        assert body["total_invested"] == pytest.approx(1800.0)


# ─── 3. 스크리닝 결과 저장 → 조회 흐름 ─────────────────────────────────────

class TestScreeningFlow:
    def test_latest_no_data_returns_404(self, client):
        resp = client.get("/api/screening/latest")
        assert resp.status_code == 404

    def test_latest_returns_most_recent(self, client):
        _insert_screening_history("2026-04-01")
        _insert_screening_history("2026-04-02")
        resp = client.get("/api/screening/latest")
        assert resp.status_code == 200
        assert resp.json()["date"] == "2026-04-02"

    def test_latest_schema(self, client):
        _insert_screening_history("2026-04-02")
        body = client.get("/api/screening/latest").json()
        assert "date" in body
        assert "data" in body
        assert "created_at" in body

    def test_latest_data_contains_strategies(self, client):
        _insert_screening_history("2026-04-02")
        body = client.get("/api/screening/latest").json()
        data = body["data"]
        assert "strategies" in data
        assert "balanced" in data["strategies"]

    def test_history_empty(self, client):
        resp = client.get("/api/screening/history")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_history_returns_list(self, client):
        _insert_screening_history("2026-04-01")
        _insert_screening_history("2026-04-02")
        resp = client.get("/api/screening/history?days=90")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_history_by_date_found(self, client):
        _insert_screening_history("2026-04-02")
        resp = client.get("/api/screening/history/2026-04-02")
        assert resp.status_code == 200
        assert resp.json()["date"] == "2026-04-02"

    def test_history_by_date_not_found(self, client):
        resp = client.get("/api/screening/history/2020-01-01")
        assert resp.status_code == 404

    def test_history_invalid_date_format(self, client):
        resp = client.get("/api/screening/history/20260402")
        assert resp.status_code == 422

    def test_history_days_validation_min(self, client):
        resp = client.get("/api/screening/history?days=0")
        assert resp.status_code == 422

    def test_history_days_validation_max(self, client):
        resp = client.get("/api/screening/history?days=91")
        assert resp.status_code == 422


# ─── 4. API 응답 스키마 검증 ─────────────────────────────────────────────────

class TestApiSchemaValidation:
    def test_portfolio_create_missing_ticker(self, client):
        payload = {k: v for k, v in _PORTFOLIO_PAYLOAD.items() if k != "ticker"}
        resp = client.post("/api/portfolio", json=payload)
        assert resp.status_code == 422

    def test_portfolio_create_missing_entry_price(self, client):
        payload = {k: v for k, v in _PORTFOLIO_PAYLOAD.items() if k != "entry_price"}
        resp = client.post("/api/portfolio", json=payload)
        assert resp.status_code == 422

    def test_portfolio_create_invalid_quantity_type(self, client):
        resp = client.post("/api/portfolio", json={**_PORTFOLIO_PAYLOAD, "quantity": "열"})
        assert resp.status_code == 422

    def test_portfolio_out_has_all_fields(self, client):
        body = client.post("/api/portfolio", json=_PORTFOLIO_PAYLOAD).json()
        required = {"id", "ticker", "name", "entry_price", "quantity",
                    "entry_date", "stop_loss", "market", "created_at", "updated_at"}
        assert required.issubset(body.keys())

    def test_screening_latest_response_has_run_id(self, client):
        _insert_screening_history("2026-04-02", run_id=20260402)
        body = client.get("/api/screening/latest").json()
        assert body["data"]["run_id"] == 20260402

    def test_screening_latest_has_market_status(self, client):
        _insert_screening_history("2026-04-02")
        body = client.get("/api/screening/latest").json()
        assert "market_status" in body["data"]
        assert "spy_price" in body["data"]["market_status"]

    def test_health_response_has_required_keys(self, client):
        body = client.get("/api/health").json()
        assert {"status", "db", "timestamp"}.issubset(body.keys())
