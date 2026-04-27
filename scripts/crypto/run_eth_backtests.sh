#!/usr/bin/env bash
# ETH 4h 백테스트 일괄 실행: A안(ETH 단독) + B안(BTC 신호 기반) 각 v1~v10
#
# 사용:
#   bash scripts/crypto/run_eth_backtests.sh
#
# 출력은 /tmp/eth_*.log 로 리다이렉트하고 마지막 요약만 콘솔에 표시.

set -e

ROOT=$(git rev-parse --show-toplevel)
cd "$ROOT"

# venv 활성화
if [ -f .venv/bin/activate ]; then
    source .venv/bin/activate
elif [ -f /Users/cheol-binpark/workspace/_s_test/.venv/bin/activate ]; then
    source /Users/cheol-binpark/workspace/_s_test/.venv/bin/activate
fi

LOG_A=/tmp/eth_a_backtest.log
LOG_B=/tmp/eth_b_backtest.log
: > "$LOG_A"; : > "$LOG_B"

echo "[A안 ETH 단독 신호] v1~v10 실행 중 → $LOG_A"
for v in v1 v2 v3 v4 v5 v6 v7 v8 v9 v10; do
    python scripts/crypto/eth_daytrading_4h.py --version $v --cache-only \
        >> "$LOG_A" 2>&1
done
python scripts/crypto/eth_daytrading_4h.py --aggregate >> "$LOG_A" 2>&1

echo "[B안 BTC 신호 기반] v1~v10 실행 중 → $LOG_B"
for v in v1 v2 v3 v4 v5 v6 v7 v8 v9 v10; do
    python scripts/crypto/eth_btc_driven_4h.py --version $v --cache-only \
        >> "$LOG_B" 2>&1
done
python scripts/crypto/eth_btc_driven_4h.py --aggregate >> "$LOG_B" 2>&1

echo "── A안 요약 ──"
grep -E "^\[ETH-A" "$LOG_A" || tail -20 "$LOG_A"
echo "── B안 요약 ──"
grep -E "^\[ETH-B" "$LOG_B" || tail -20 "$LOG_B"
