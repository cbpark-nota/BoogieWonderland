"""APScheduler 기반 스케줄러 — 스크리닝, 스톱 체크, 리밸런싱 알림"""
import logging
from datetime import date, datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.market import RebalanceSchedule, DeviceToken, NotificationLog
from app.models.portfolio import Holding
from app.models.stock import ScreeningRun, ScreeningResult
from app.services.screener import run_screening
from app.services.monitor import check_stop_loss
from app.services.notification import send_push

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


async def job_daily_screening():
    """일간 스크리닝 실행 + DB 저장."""
    logger.info("스케줄: 일간 스크리닝 시작")
    try:
        data = run_screening()
        async with async_session() as db:
            mkt = data["market"]
            run = ScreeningRun(
                run_at=datetime.utcnow(),
                market_spy_price=mkt["price"] if mkt else None,
                market_is_golden=mkt["is_golden"] if mkt else None,
                market_ma50=mkt["ma50"] if mkt else None,
                market_ma200=mkt["ma200"] if mkt else None,
                total_screened=data["total_screened"],
                total_passed=data["total_passed"],
            )
            db.add(run)
            await db.flush()
            for r in data["results"]:
                db.add(ScreeningResult(
                    run_id=run.id, rank=r["rank"], ticker=r["ticker"],
                    score=r["score"], weight_pct=r["weight_pct"], price=r["price"],
                    adx=r["adx"], rsi=r["rsi"], ret_3m=r["ret_3m"],
                    stop_price=r["stop_price"], stop_dist_pct=r["stop_dist_pct"],
                    atr=r["atr"],
                ))
            await db.commit()
        logger.info(f"스케줄: 스크리닝 완료 — {data['total_passed']}개 통과")
    except Exception as e:
        logger.error(f"스케줄: 스크리닝 실패 — {e}")


async def job_stop_check():
    """보유 종목 스톱로스 체크 + 알림 발송."""
    logger.info("스케줄: 스톱 체크 시작")
    try:
        async with async_session() as db:
            stmt = select(Holding).where(Holding.is_active == True)
            result = await db.execute(stmt)
            holdings = result.scalars().all()

            if not holdings:
                return

            tokens_stmt = select(DeviceToken)
            tokens_result = await db.execute(tokens_stmt)
            tokens = [t.token for t in tokens_result.scalars().all()]

            for h in holdings:
                stop_result = check_stop_loss(h.ticker, h.entry_price, h.peak_price)
                event_type = stop_result["event_type"]

                if event_type == "BREACH":
                    title = "스톱로스 이탈"
                    body = (f"{h.ticker} ${stop_result['current_price']:.2f} — "
                            f"스톱가 ${stop_result['stop_price']:.2f} 이탈. 매도 검토 필요.")
                    s, f = await send_push(tokens, title, body)
                    db.add(NotificationLog(
                        type="STOP_BREACH", title=title, body=body,
                        success_count=s, fail_count=f,
                    ))
                elif event_type == "WARNING":
                    title = "스톱 근접 경고"
                    body = (f"{h.ticker} ${stop_result['current_price']:.2f} — "
                            f"스톱가 ${stop_result['stop_price']:.2f}까지 "
                            f"{stop_result['margin_pct']:.1f}% 여유.")
                    s, f = await send_push(tokens, title, body)
                    db.add(NotificationLog(
                        type="STOP_WARNING", title=title, body=body,
                        success_count=s, fail_count=f,
                    ))

            await db.commit()
        logger.info("스케줄: 스톱 체크 완료")
    except Exception as e:
        logger.error(f"스케줄: 스톱 체크 실패 — {e}")


async def job_rebalance_reminder():
    """리밸런싱 2일 전 알림."""
    target_date = date.today() + timedelta(days=2)
    try:
        async with async_session() as db:
            stmt = select(RebalanceSchedule).where(
                RebalanceSchedule.scheduled_date == target_date,
                RebalanceSchedule.status == "PENDING",
            )
            result = await db.execute(stmt)
            rebal = result.scalar_one_or_none()
            if not rebal:
                return

            tokens_stmt = select(DeviceToken)
            tokens_result = await db.execute(tokens_stmt)
            tokens = [t.token for t in tokens_result.scalars().all()]

            title = "리밸런싱 예정"
            body = f"{target_date.strftime('%m월 %d일')} 리밸런싱 예정입니다. 스크리닝 결과를 확인하세요."
            s, f = await send_push(tokens, title, body)

            db.add(NotificationLog(
                type="REBALANCE", title=title, body=body,
                success_count=s, fail_count=f,
            ))
            await db.commit()
            logger.info(f"스케줄: 리밸런싱 리마인더 발송 ({target_date})")
    except Exception as e:
        logger.error(f"스케줄: 리밸런싱 리마인더 실패 — {e}")


async def seed_rebalance_dates():
    """향후 6개월 격주 금요일 리밸런싱 일정 시드."""
    import pandas as pd
    today = date.today()
    end = today + timedelta(days=180)
    fridays = pd.date_range(today, end, freq="W-FRI")[::2]  # 격주

    async with async_session() as db:
        for fri in fridays:
            d = fri.date()
            stmt = select(RebalanceSchedule).where(RebalanceSchedule.scheduled_date == d)
            result = await db.execute(stmt)
            if not result.scalar_one_or_none():
                db.add(RebalanceSchedule(scheduled_date=d))
        await db.commit()


def setup_scheduler():
    """스케줄러에 작업 등록."""
    # 일간 스크리닝 (미국장 마감 후, KST 06:30)
    scheduler.add_job(job_daily_screening, "cron", hour=6, minute=30,
                      day_of_week="tue-sat", id="daily_screening",
                      replace_existing=True)

    # 스톱 체크 (미국장 마감 후)
    scheduler.add_job(job_stop_check, "cron", hour=6, minute=45,
                      day_of_week="tue-sat", id="stop_check_us",
                      replace_existing=True)

    # 스톱 체크 (한국장 마감 후)
    scheduler.add_job(job_stop_check, "cron", hour=15, minute=45,
                      day_of_week="mon-fri", id="stop_check_kr",
                      replace_existing=True)

    # 리밸런싱 리마인더 (매일 09:00 체크)
    scheduler.add_job(job_rebalance_reminder, "cron", hour=9, minute=0,
                      day_of_week="mon-fri", id="rebalance_reminder",
                      replace_existing=True)
