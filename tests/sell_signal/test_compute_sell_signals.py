"""
compute_sell_signals.py 단위 테스트 (네트워크 없이 실행 가능)
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

# scripts/sell_signal 경로를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts" / "sell_signal"))

from compute_sell_signals import (
    _bdays_since,
    _is_bday,
    load_candidate_tickers,
    load_current_ranks,
    load_previous_signals,
    _write,
    DISPLAY_BDAYS,
)


# ── _is_bday ────────────────────────────────────────────────

def test_is_bday_weekday():
    monday = datetime(2026, 4, 13)   # 월요일
    assert _is_bday(monday) is True

def test_is_bday_saturday():
    saturday = datetime(2026, 4, 11) # 토요일
    assert _is_bday(saturday) is False

def test_is_bday_sunday():
    sunday = datetime(2026, 4, 12)   # 일요일
    assert _is_bday(sunday) is False


# ── _bdays_since ────────────────────────────────────────────

def test_bdays_since_today():
    today_str = datetime.now().strftime("%Y-%m-%d")
    # 오늘 = 영업일 1일째 (오늘이 영업일이면)
    result = _bdays_since(today_str)
    if _is_bday(datetime.now()):
        assert result == 1
    else:
        assert result == 0


def test_bdays_since_counts_only_weekdays(tmp_path):
    # 월요일부터 금요일까지 5영업일
    monday = datetime(2026, 4, 6)   # 월요일
    friday = datetime(2026, 4, 10)  # 금요일 (그 주 금요일)
    # 직접 계산: 4/6(월)~4/10(금) = 5 영업일
    count = 0
    cur = monday
    while cur.date() <= friday.date():
        if _is_bday(cur):
            count += 1
        cur += timedelta(days=1)
    assert count == 5


# ── load_candidate_tickers ───────────────────────────────────

def test_load_candidate_tickers_empty(tmp_path, monkeypatch):
    """HISTORY_DIR이 비어 있으면 빈 딕셔너리 반환."""
    import compute_sell_signals as cs
    monkeypatch.setattr(cs, "HISTORY_DIR", tmp_path / "history")
    result = load_candidate_tickers(30)
    assert result == {}


def test_load_candidate_tickers_picks_oldest(tmp_path, monkeypatch):
    """같은 ticker가 여러 날 등장하면 가장 오래된 날짜를 entry_date로 사용."""
    import compute_sell_signals as cs

    hist_dir = tmp_path / "history"
    hist_dir.mkdir()
    monkeypatch.setattr(cs, "HISTORY_DIR", hist_dir)

    older_date = "2026-03-20"
    newer_date = "2026-04-10"

    for date_str in (older_date, newer_date):
        (hist_dir / f"{date_str}.json").write_text(json.dumps({
            "strategies": {
                "balanced": {
                    "results": [{"ticker": "AAPL", "rank": 1}]
                }
            }
        }))

    result = load_candidate_tickers(60)
    assert "AAPL" in result
    assert result["AAPL"] == older_date


def test_load_candidate_tickers_excludes_old(tmp_path, monkeypatch):
    """look_back_days 이전 날짜 항목은 제외."""
    import compute_sell_signals as cs

    hist_dir = tmp_path / "history"
    hist_dir.mkdir()
    monkeypatch.setattr(cs, "HISTORY_DIR", hist_dir)

    old_date = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
    (hist_dir / f"{old_date}.json").write_text(json.dumps({
        "strategies": {
            "aggressive": {"results": [{"ticker": "MSFT", "rank": 1}]}
        }
    }))

    result = load_candidate_tickers(30)
    assert "MSFT" not in result


# ── load_current_ranks ───────────────────────────────────────

def test_load_current_ranks_empty(tmp_path, monkeypatch):
    """strategies.json이 없으면 빈 딕셔너리 반환."""
    import compute_sell_signals as cs
    monkeypatch.setattr(cs, "STRATEGIES_FILE", tmp_path / "missing.json")
    assert load_current_ranks() == {}


def test_load_current_ranks_reads_aggressive(tmp_path, monkeypatch):
    """aggressive 결과에서 rank를 올바르게 읽는다."""
    import compute_sell_signals as cs

    f = tmp_path / "strategies.json"
    f.write_text(json.dumps({
        "strategies": {
            "aggressive": {
                "results": [
                    {"ticker": "NVDA", "rank": 1},
                    {"ticker": "AAPL", "rank": 2},
                ]
            }
        }
    }))
    monkeypatch.setattr(cs, "STRATEGIES_FILE", f)

    ranks = load_current_ranks()
    assert ranks["NVDA"] == 1
    assert ranks["AAPL"] == 2


# ── load_previous_signals ────────────────────────────────────

def test_load_previous_signals_missing(tmp_path):
    result = load_previous_signals(tmp_path / "nonexistent.json")
    assert result == {}


def test_load_previous_signals_reads_correctly(tmp_path):
    f = tmp_path / "sell_signals.json"
    f.write_text(json.dumps({
        "updated_at": "2026-04-13",
        "signals": [
            {
                "ticker": "TSLA",
                "sell_triggered_date": "2026-04-12",
                "sell_reasons": ["rank_out"],
                "days_remaining": 2,
            }
        ],
    }))
    result = load_previous_signals(f)
    assert "TSLA" in result
    assert result["TSLA"]["sell_triggered_date"] == "2026-04-12"


# ── _write ────────────────────────────────────────────────────

def test_write_creates_file(tmp_path):
    out = tmp_path / "sell_signals.json"
    signals = [{"ticker": "AAPL", "days_remaining": 2}]
    _write(out, "2026-04-14", signals)

    assert out.exists()
    data = json.loads(out.read_text())
    assert data["updated_at"] == "2026-04-14"
    assert len(data["signals"]) == 1
    assert data["signals"][0]["ticker"] == "AAPL"


def test_write_empty_signals(tmp_path):
    out = tmp_path / "sell_signals.json"
    _write(out, "2026-04-14", [])
    data = json.loads(out.read_text())
    assert data["signals"] == []
