"""모니터 서비스 단위 테스트 — 외부 API 호출을 mock 처리"""
from unittest.mock import patch

import pytest

from app.services.monitor import check_stop_loss


def _mock_atr_stop(current_price: float, stop_price: float, margin_pct: float):
    """calc_atr_stop_for_ticker를 대체할 반환값을 만든다."""
    return {
        "current_price": current_price,
        "stop_price": stop_price,
        "margin_pct": margin_pct,
        "atr": 2.0,
        "peak_20": 110.0,
    }


@patch("app.services.monitor.calc_atr_stop_for_ticker")
def test_check_stop_loss_breach(mock_atr):
    """현재가 <= 스톱가일 때 BREACH 이벤트를 반환해야 한다."""
    mock_atr.return_value = _mock_atr_stop(
        current_price=95.0, stop_price=100.0, margin_pct=-5.26,
    )
    result = check_stop_loss("AAPL", entry_price=105.0, peak_price=110.0)
    assert result["event_type"] == "BREACH"
    assert result["current_price"] == 95.0
    assert result["stop_price"] == 100.0


@patch("app.services.monitor.calc_atr_stop_for_ticker")
def test_check_stop_loss_warning(mock_atr):
    """마진 < 5%일 때 WARNING 이벤트를 반환해야 한다."""
    mock_atr.return_value = _mock_atr_stop(
        current_price=102.0, stop_price=100.0, margin_pct=1.96,
    )
    result = check_stop_loss("AAPL", entry_price=105.0, peak_price=110.0)
    assert result["event_type"] == "WARNING"
    assert result["margin_pct"] == pytest.approx(1.96)


@patch("app.services.monitor.calc_atr_stop_for_ticker")
def test_check_stop_loss_ok(mock_atr):
    """정상 상태(마진 >= 5%, 현재가 > 스톱가)일 때 event_type이 None이어야 한다."""
    mock_atr.return_value = _mock_atr_stop(
        current_price=120.0, stop_price=100.0, margin_pct=16.67,
    )
    result = check_stop_loss("AAPL", entry_price=105.0, peak_price=110.0)
    assert result["event_type"] is None
    assert result["ticker"] == "AAPL"
