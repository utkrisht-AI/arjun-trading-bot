import logging
import threading
import pytz
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

load_dotenv()

from logs.logger import setup_logging, get_daily_logger, read_corpus, generate_eod_report, write_state
from research.screener import run_screening
from research.sentiment import run_sentiment_scan
from research.scorer import generate_candidates
from research.market_context import get_full_context
from broker import get_broker
from execution.order_manager import execute_entry, force_close_all
from execution.monitor import run_monitor_loop

setup_logging()
logger = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")

_candidates: list[dict] = []
_screened: list[dict] = []
_broker = None
_market_context: dict = {}


def job_screening():
    global _screened, _market_context
    logger.info("JOB: Universe screening")
    _market_context = get_full_context()
    write_state({"market_context": _market_context})
    dl = get_daily_logger()
    dl.info(
        f"Market context: nifty={_market_context['nifty_trend']} | "
        f"expiry={_market_context['expiry_type']} | "
        f"gate={_market_context['gate_reason']}"
    )
    if not _market_context["can_trade"]:
        logger.warning(f"Trading gate CLOSED: {_market_context['gate_reason']}")
        _screened = []
        write_state({"today": {"screened_count": 0, "screening_done": True}})
        return
    _screened = run_screening()
    write_state({"today": {"screened_count": len(_screened), "screening_done": True}})


def job_sentiment():
    global _candidates
    logger.info("JOB: Sentiment scan + candidate generation")
    if not _screened:
        logger.warning("No screened stocks — skipping sentiment")
        _candidates = []
        return
    sentiments = run_sentiment_scan(_screened)
    _candidates = generate_candidates(_screened, sentiments)
    _safe_candidates = [
        {k: v for k, v in c.items() if k != "hist"}
        for c in _candidates
    ]
    write_state({"today": {"candidates": _safe_candidates, "candidates_done": True}})


def job_daily_brief():
    logger.info("JOB: Daily brief")
    corpus = read_corpus()
    dl = get_daily_logger()
    dl.info(f"Corpus: ₹{corpus:,.0f}")

    expiry_type = _market_context.get("expiry_type", "none")
    if expiry_type != "none":
        dl.info(f"WARNING: {expiry_type.upper()} expiry day — elevated volatility")

    for c in _candidates:
        dl.info(
            f"CANDIDATE: {c['symbol']} score={c['composite_score']} "
            f"@ ₹{c['price']} | RSI={c['signals']['rsi_14']} "
            f"MACD={c['signals']['macd_signal']} "
            f"candle={c['signals']['candlestick_pattern']}"
        )
    if not _candidates:
        dl.info("No candidates today — will sit out")


def job_market_open():
    global _broker
    logger.info("JOB: Market open — initializing broker")
    if not _market_context.get("can_trade", True):
        logger.warning("Trading gate closed — skipping broker init")
        return
    try:
        _broker = get_broker()
    except Exception as e:
        logger.error(f"Broker init failed: {e}")
        _broker = None


def job_execute_entries():
    if not _broker:
        logger.error("No broker — skipping entries")
        return
    if not _candidates:
        logger.info("No candidates today — no trades")
        return

    # On expiry days, warn and halve position sizing via corpus cap
    expiry_type = _market_context.get("expiry_type", "none")
    corpus = read_corpus()
    if expiry_type == "monthly_expiry":
        logger.warning("Monthly expiry — skipping entries (too risky)")
        return

    for candidate in _candidates:
        result = execute_entry(_broker, candidate["symbol"], corpus)
        if result:
            corpus -= result["shares"] * result["entry_price"]


def job_start_monitor():
    if not _broker:
        return
    thread = threading.Thread(target=run_monitor_loop, args=(_broker,), daemon=True)
    thread.start()
    logger.info("Monitor loop started in background thread")


def job_force_close():
    if _broker:
        force_close_all(_broker)


def job_eod_report():
    skipped = [
        s for s in _screened
        if not any(c["symbol"] == s["symbol"] for c in _candidates)
    ]
    generate_eod_report(_candidates, skipped)


def create_scheduler() -> BlockingScheduler:
    scheduler = BlockingScheduler(timezone=IST)

    def cron(**kwargs):
        return CronTrigger(timezone=IST, **kwargs)

    scheduler.add_job(job_screening,       cron(hour=7,  minute=0))
    scheduler.add_job(job_sentiment,       cron(hour=7,  minute=30))
    scheduler.add_job(job_daily_brief,     cron(hour=9,  minute=0))
    scheduler.add_job(job_market_open,     cron(hour=9,  minute=10))
    scheduler.add_job(job_execute_entries, cron(hour=9,  minute=20))
    scheduler.add_job(job_start_monitor,   cron(hour=9,  minute=25))
    scheduler.add_job(job_force_close,     cron(hour=15, minute=15))
    scheduler.add_job(job_eod_report,      cron(hour=15, minute=35))

    return scheduler
