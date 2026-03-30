"""
공용 유니버스 상수 모듈
══════════════════════════════════════════════════════════════
screener_v2/v3 및 관련 백테스트 스크립트가 공유하는 하드코딩 유니버스.
(S&P500 + NASDAQ-100 전체 동적 수집은 data_cache.py 참조)

이 유니버스는 v2/v3 로컬 스크리닝 및 역사적 백테스트 재현용으로만 사용한다.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
사용 예:
    from scripts.core.constants import US_UNIVERSE, KR_UNIVERSE, ALL_UNIVERSE, SECTOR_ETF

    # 또는 scripts/ 를 sys.path에 추가한 경우
    from core.constants import US_UNIVERSE, KR_UNIVERSE, ALL_UNIVERSE, SECTOR_ETF
══════════════════════════════════════════════════════════════
"""

US_UNIVERSE = {
    "NVDA": "Technology", "AAPL": "Technology", "MSFT": "Technology", "AVGO": "Technology",
    "AMD": "Technology",  "QCOM": "Technology", "AMAT": "Technology", "LRCX": "Technology",
    "MU":  "Technology",  "KLAC": "Technology", "ORCL": "Technology", "ADBE": "Technology",
    "CRM": "Technology",  "NOW":  "Technology", "PANW": "Technology", "SNPS": "Technology",
    "META": "Communication", "GOOGL": "Communication", "NFLX": "Communication", "TMUS": "Communication",
    "AMZN": "Consumer Disc", "TSLA": "Consumer Disc", "HD": "Consumer Disc", "LULU": "Consumer Disc",
    "LLY":  "Health Care", "UNH": "Health Care", "ABBV": "Health Care",
    "ISRG": "Health Care", "VRTX": "Health Care",
    "V": "Financials", "MA": "Financials", "JPM": "Financials", "GS": "Financials",
    "XOM": "Energy", "CVX": "Energy", "SLB": "Energy",
    "CAT": "Industrials", "GE": "Industrials", "ETN": "Industrials", "LMT": "Industrials",
    "FCX": "Materials", "NEM": "Materials",
}

KR_UNIVERSE = {
    "005930.KS": "Technology",    # 삼성전자
    "000660.KS": "Technology",    # SK하이닉스
    "009150.KS": "Technology",    # 삼성전기
    "006400.KS": "Technology",    # 삼성SDI
    "373220.KS": "Technology",    # LG에너지솔루션
    "207940.KS": "Health Care",   # 삼성바이오로직스
    "068270.KS": "Health Care",   # 셀트리온
    "051910.KS": "Materials",     # LG화학
    "247540.KS": "Materials",     # 에코프로비엠
    "005380.KS": "Consumer Disc", # 현대차
    "000270.KS": "Consumer Disc", # 기아
    "035420.KS": "Communication", # NAVER
    "035720.KS": "Communication", # 카카오
    "105560.KS": "Financials",    # KB금융
    "055550.KS": "Financials",    # 신한지주
    "096770.KS": "Energy",        # SK이노베이션
    "011200.KS": "Industrials",   # HMM
}

ALL_UNIVERSE = {**US_UNIVERSE, **KR_UNIVERSE}

SECTOR_ETF = {
    "Technology":    "XLK",
    "Health Care":   "XLV",
    "Financials":    "XLF",
    "Consumer Disc": "XLY",
    "Industrials":   "XLI",
    "Energy":        "XLE",
    "Materials":     "XLB",
    "Communication": "XLC",
}
