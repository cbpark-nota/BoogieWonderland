"""포트폴리오 CRUD API 테스트 — SQLite 인메모리 DB 사용."""
import sys
from pathlib import Path
from unittest.mock import patch

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
from backend.db.models import Portfolio  # noqa: F401 — 테이블 등록
from backend.api.main import app  # noqa: E402


@pytest.fixture()
def client():
    """테스트 전용 SQLite 인메모리 DB로 get_db 오버라이드. 이전 override를 복원한다."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def _override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    prev_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    # 이전 override 복원
    if prev_override is not None:
        app.dependency_overrides[get_db] = prev_override
    else:
        app.dependency_overrides.pop(get_db, None)
    Base.metadata.drop_all(bind=engine)


# ─── 헬퍼 ────────────────────────────────────────────────────────────────────

def _item_payload(**kwargs):
    base = {
        "ticker": "AAPL",
        "name": "Apple Inc.",
        "entry_price": 180.0,
        "quantity": 10,
        "entry_date": "2024-01-15",
        "stop_loss": 160.0,
        "market": "US",
    }
    base.update(kwargs)
    return base


# ─── GET /api/portfolio ───────────────────────────────────────────────────────

def test_list_portfolio_empty(client: TestClient):
    """초기 상태: 빈 리스트 반환."""
    resp = client.get("/api/portfolio")
    assert resp.status_code == 200
    assert resp.json() == []


# ─── POST /api/portfolio ──────────────────────────────────────────────────────

def test_create_portfolio(client: TestClient):
    """종목 추가 성공."""
    resp = client.post("/api/portfolio", json=_item_payload())
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"] == 1
    assert data["ticker"] == "AAPL"
    assert data["entry_price"] == 180.0
    assert data["quantity"] == 10
    assert data["market"] == "US"
    assert data["current_price"] is None


def test_create_portfolio_minimal(client: TestClient):
    """필수 필드만으로 종목 추가."""
    resp = client.post("/api/portfolio", json={
        "ticker": "TSLA",
        "entry_price": 250.0,
        "quantity": 5,
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["ticker"] == "TSLA"
    assert data["name"] is None
    assert data["stop_loss"] is None
    assert data["market"] == "US"


# ─── GET /api/portfolio (리스트) ──────────────────────────────────────────────

def test_list_portfolio_after_create(client: TestClient):
    """종목 추가 후 리스트 조회."""
    client.post("/api/portfolio", json=_item_payload())
    client.post("/api/portfolio", json=_item_payload(ticker="MSFT", name="Microsoft"))

    resp = client.get("/api/portfolio")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 2
    assert items[0]["ticker"] == "AAPL"
    assert items[1]["ticker"] == "MSFT"


# ─── PUT /api/portfolio/{id} ──────────────────────────────────────────────────

def test_update_portfolio(client: TestClient):
    """종목 수정 성공."""
    create = client.post("/api/portfolio", json=_item_payload())
    item_id = create.json()["id"]

    resp = client.put(f"/api/portfolio/{item_id}", json={
        "entry_price": 190.0,
        "quantity": 15,
        "stop_loss": 170.0,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["entry_price"] == 190.0
    assert data["quantity"] == 15
    assert data["stop_loss"] == 170.0
    assert data["ticker"] == "AAPL"  # 변경 안 된 필드 유지


def test_update_portfolio_not_found(client: TestClient):
    """존재하지 않는 id 수정 시 404."""
    resp = client.put("/api/portfolio/999", json={"entry_price": 200.0})
    assert resp.status_code == 404


# ─── DELETE /api/portfolio/{id} ───────────────────────────────────────────────

def test_delete_portfolio(client: TestClient):
    """종목 삭제 성공."""
    create = client.post("/api/portfolio", json=_item_payload())
    item_id = create.json()["id"]

    resp = client.delete(f"/api/portfolio/{item_id}")
    assert resp.status_code == 204

    list_resp = client.get("/api/portfolio")
    assert list_resp.json() == []


def test_delete_portfolio_not_found(client: TestClient):
    """존재하지 않는 id 삭제 시 404."""
    resp = client.delete("/api/portfolio/999")
    assert resp.status_code == 404


# ─── GET /api/portfolio/summary ───────────────────────────────────────────────

def test_summary_empty(client: TestClient):
    """빈 포트폴리오 요약: 모두 0."""
    resp = client.get("/api/portfolio/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_items"] == 0
    assert data["total_invested"] == 0.0


def test_summary_with_items(client: TestClient):
    """항목 있는 요약: yfinance mock 처리."""
    client.post("/api/portfolio", json=_item_payload(entry_price=180.0, quantity=10))
    client.post("/api/portfolio", json=_item_payload(ticker="MSFT", entry_price=400.0, quantity=5))

    with patch("backend.api.portfolio._fetch_prices", return_value={"AAPL": 200.0, "MSFT": 420.0}):
        resp = client.get("/api/portfolio/summary")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_items"] == 2
    # 총 투자금액: 180*10 + 400*5 = 3800
    assert data["total_invested"] == 3800.0
    # 현재 평가액: 200*10 + 420*5 = 4100
    assert data["total_current_value"] == 4100.0
    assert data["total_pnl"] == 300.0
    assert data["total_pnl_pct"] > 0


# ─── GET /api/portfolio/refresh ───────────────────────────────────────────────

def test_refresh_with_prices(client: TestClient):
    """현재가 조회 포함 리스트 반환."""
    client.post("/api/portfolio", json=_item_payload())
    client.post("/api/portfolio", json=_item_payload(ticker="TSLA", entry_price=250.0, quantity=3))

    with patch("backend.api.portfolio._fetch_prices", return_value={"AAPL": 195.5, "TSLA": 260.0}):
        resp = client.get("/api/portfolio/refresh")

    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 2

    aapl = next(i for i in items if i["ticker"] == "AAPL")
    tsla = next(i for i in items if i["ticker"] == "TSLA")
    assert aapl["current_price"] == 195.5
    assert tsla["current_price"] == 260.0


def test_refresh_price_fetch_failure(client: TestClient):
    """yfinance 조회 실패 시 current_price=None으로 응답."""
    client.post("/api/portfolio", json=_item_payload())

    with patch("backend.api.portfolio._fetch_prices", return_value={}):
        resp = client.get("/api/portfolio/refresh")

    assert resp.status_code == 200
    items = resp.json()
    assert items[0]["current_price"] is None
