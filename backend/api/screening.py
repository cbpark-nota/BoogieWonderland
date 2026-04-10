"""스크리닝 결과 API 라우터 (SQLite 기반)."""
import json
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from backend.db.database import get_db
from backend.db.models import ScreeningHistory, ScreeningResult

router = APIRouter(prefix="/api/screening", tags=["screening"])


# ──────────────────────────── 응답 헬퍼 ────────────────────────────

def _history_to_dict(row: ScreeningHistory) -> dict[str, Any]:
    return {
        "date": row.date,
        "data": json.loads(row.data_json),
        "created_at": row.created_at,
    }


def _results_for_date(date_str: str, db: Session) -> list[dict[str, Any]]:
    stmt = (
        select(ScreeningResult)
        .where(ScreeningResult.date == date_str)
        .order_by(ScreeningResult.strategy, ScreeningResult.rank)
    )
    rows = db.execute(stmt).scalars().all()
    out = []
    for r in rows:
        item: dict[str, Any] = {
            "date": r.date,
            "strategy": r.strategy,
            "ticker": r.ticker,
            "name": r.name,
            "rank": r.rank,
            "score": r.score,
            "market": r.market,
        }
        if r.data_json:
            item["data"] = json.loads(r.data_json)
        out.append(item)
    return out


# ──────────────────────────── 엔드포인트 ────────────────────────────

@router.get("/latest")
def get_latest(db: Session = Depends(get_db)) -> dict[str, Any]:
    """최신 스크리닝 결과 반환."""
    stmt = select(ScreeningHistory).order_by(desc(ScreeningHistory.date)).limit(1)
    row = db.execute(stmt).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="스크리닝 결과 없음")
    return _history_to_dict(row)


@router.get("/history")
def get_history(
    days: int = Query(default=5, ge=1, le=90),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """최근 N일 스크리닝 히스토리 반환."""
    since = (date.today() - timedelta(days=days - 1)).isoformat()
    stmt = (
        select(ScreeningHistory)
        .where(ScreeningHistory.date >= since)
        .order_by(desc(ScreeningHistory.date))
    )
    rows = db.execute(stmt).scalars().all()
    return [_history_to_dict(r) for r in rows]


@router.get("/history/{target_date}")
def get_history_by_date(target_date: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """특정 날짜(YYYY-MM-DD) 스크리닝 결과 반환."""
    # 날짜 형식 검증
    try:
        datetime.strptime(target_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=422, detail="날짜 형식은 YYYY-MM-DD 이어야 합니다")

    stmt = select(ScreeningHistory).where(ScreeningHistory.date == target_date)
    row = db.execute(stmt).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"{target_date} 스크리닝 결과 없음")
    return _history_to_dict(row)


@router.post("/run")
def trigger_run(db: Session = Depends(get_db)) -> dict[str, Any]:
    """export_json.py를 실행하여 스크리닝 결과를 DB에 저장."""
    export_script = Path(__file__).parents[2] / "scripts" / "export_json.py"
    if not export_script.exists():
        raise HTTPException(status_code=500, detail="export_json.py 스크립트를 찾을 수 없습니다")

    try:
        result = subprocess.run(
            [sys.executable, str(export_script), "--db"],
            capture_output=True,
            text=True,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="스크리닝 실행 타임아웃 (10분 초과)")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"스크리닝 실행 실패: {exc}")

    if result.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=f"스크리닝 실패: {result.stderr[-500:] if result.stderr else '(오류 없음)'}",
        )

    # 방금 저장된 최신 결과 반환
    stmt = select(ScreeningHistory).order_by(desc(ScreeningHistory.date)).limit(1)
    row = db.execute(stmt).scalar_one_or_none()
    if row is None:
        return {"status": "ok", "message": "스크리닝 완료 (DB 저장 결과 없음)", "stdout": result.stdout[-500:]}

    return {
        "status": "ok",
        "date": row.date,
        "created_at": row.created_at,
        "stdout": result.stdout[-500:],
    }
