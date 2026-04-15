#!/usr/bin/env bash
# BTC 4h v1~v10 순차 백테스트 러너
#   - 각 버전을 독립 프로세스로 실행 (세션 토큰 절감)
#   - 로그는 /tmp 로 리다이렉트
#   - 완료된 버전(vN.json 존재)은 건너뜀 (중단 복구 지원)
#   - 전체 완료 후 --aggregate 실행

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$SCRIPT_DIR"

RESULT_DIR="scripts/backtest/results/btc_4h"
mkdir -p "$RESULT_DIR"

echo "=== BTC 4h v1~v10 백테스트 시작 ==="
echo "    결과 저장 경로: $RESULT_DIR"
echo ""

for V in v1 v2 v3 v4 v5 v6 v7 v8 v9 v10; do
  if [[ -f "$RESULT_DIR/${V}.json" ]]; then
    echo "[$V] 이미 완료 → 건너뜀"
    continue
  fi
  echo "[$V] 실행 중... (log: /tmp/btc_4h_${V}.log)"
  python scripts/crypto/btc_daytrading_4h.py --version "$V" \
    > "/tmp/btc_4h_${V}.log" 2>&1
  # 1줄 요약 출력 (log 마지막 줄)
  tail -1 "/tmp/btc_4h_${V}.log"
done

echo ""
echo "=== 집계 실행 중... ==="
python scripts/crypto/btc_daytrading_4h.py --aggregate \
  > "/tmp/btc_4h_aggregate.log" 2>&1

tail -60 /tmp/btc_4h_aggregate.log

TODAY=$(date +%Y%m%d)
echo ""
echo "=== 완료 ==="
echo "    집계 보고서: docs/btc_4h_backtest_results_${TODAY}.md"
