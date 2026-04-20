"""
ARJUN — Autonomous Rupee-Jacking Ultra Nimble Trader
Entry point. Run: python main.py [--dry-run] [--now]
"""
import argparse
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from logs.logger import setup_logging, read_corpus
setup_logging()

import logging
logger = logging.getLogger("arjun")


def print_banner():
    corpus = read_corpus()
    mode = "DRY RUN" if os.getenv("DRY_RUN", "true").lower() == "true" else "LIVE"
    broker = os.getenv("BROKER", "zerodha").upper()
    print(f"""
╔══════════════════════════════════════════╗
║   ARJUN — Autonomous Trading System      ║
║   Mode:   {mode:<30} ║
║   Broker: {broker:<30} ║
║   Corpus: ₹{corpus:<29,.0f} ║
╚══════════════════════════════════════════╝
""")


def run_now():
    """Run all pipeline steps immediately (for testing / manual trigger)."""
    from research.screener import run_screening
    from research.sentiment import run_sentiment_scan
    from research.scorer import generate_candidates
    from broker import get_broker
    from execution.order_manager import execute_entry, force_close_all
    from execution.monitor import run_monitor_loop
    from logs.logger import read_corpus, generate_eod_report

    logger.info("Manual run triggered")

    screened = run_screening()
    if not screened:
        logger.warning("No stocks passed screening today")
        return

    sentiments = run_sentiment_scan(screened)
    candidates = generate_candidates(screened, sentiments)

    if not candidates:
        logger.info("No candidates scored ≥ 65 today — no trades")
        generate_eod_report([], screened)
        return

    corpus = read_corpus()
    broker = get_broker()

    for candidate in candidates:
        result = execute_entry(broker, candidate["symbol"], corpus)
        if result:
            corpus -= result["shares"] * result["entry_price"]

    run_monitor_loop(broker)

    skipped = [s for s in screened if not any(c["symbol"] == s["symbol"] for c in candidates)]
    generate_eod_report(candidates, skipped)


def run_scheduled():
    """Run on the automated daily schedule (production mode)."""
    from scheduler import create_scheduler
    scheduler = create_scheduler()
    logger.info("Scheduler started — waiting for market hours (IST)")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ARJUN Trading System")
    parser.add_argument("--dry-run", action="store_true", help="Override DRY_RUN=true")
    parser.add_argument("--live", action="store_true", help="Enable live trading (DRY_RUN=false)")
    parser.add_argument("--now", action="store_true", help="Run pipeline immediately (skip scheduler)")
    args = parser.parse_args()

    if args.dry_run:
        os.environ["DRY_RUN"] = "true"
    if args.live:
        confirm = input("WARNING: Live trading enabled. Type 'CONFIRM' to proceed: ")
        if confirm != "CONFIRM":
            print("Aborted.")
            sys.exit(0)
        os.environ["DRY_RUN"] = "false"

    print_banner()

    if args.now:
        run_now()
    else:
        run_scheduled()
