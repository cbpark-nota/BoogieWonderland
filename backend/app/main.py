"""FastAPI 앱 엔트리포인트"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import engine, Base, async_session
from app.routers import screening, portfolio, market
from app.routers.portfolio import portfolio_router
from app.scheduler import scheduler, setup_scheduler, seed_rebalance_dates
from app.services.screener import ALL_UNIVERSE, US_UNIVERSE, KR_UNIVERSE

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def seed_stocks():
    """종목 유니버스 시드 데이터 삽입."""
    from sqlalchemy import select
    from app.models.stock import Stock

    async with async_session() as db:
        result = await db.execute(select(Stock).limit(1))
        if result.scalar_one_or_none():
            return  # 이미 시드됨

        for ticker, sector in ALL_UNIVERSE.items():
            market = "KR" if ticker.endswith(".KS") else "US"
            db.add(Stock(ticker=ticker, market=market, sector=sector))
        await db.commit()
        logger.info(f"종목 시드 완료: {len(ALL_UNIVERSE)}개")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 시작
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await seed_stocks()
    await seed_rebalance_dates()

    if settings.scheduler_enabled:
        setup_scheduler()
        scheduler.start()
        logger.info("스케줄러 시작")

    yield

    # 종료
    if scheduler.running:
        scheduler.shutdown()
    await engine.dispose()


app = FastAPI(
    title="모멘텀 주식 스크리너 API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(screening.router)
app.include_router(portfolio.router)
app.include_router(portfolio_router)
app.include_router(market.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
