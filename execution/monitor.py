import logging
import time
from datetime import datetime
import pytz
from broker.base import BrokerBase
from execution.order_manager import get_open_trades, update_trailing_sl, execute_exit, check_daily_loss_limit, force_close_all
from logs.logger import read_corpus

logger = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")

EOD_EXIT_TIME = (15, 15)
POLL_INTERVAL_SECONDS = 300  # 5 minutes


def _ist_now():
    return datetime.now(IST)


def _past_eod() -> bool:
    now = _ist_now()
    return (now.hour, now.minute) >= EOD_EXIT_TIME


def monitor_positions(broker: BrokerBase):
    trades = get_open_trades()
    if not trades:
        return

    for symbol, trade in list(trades.items()):
        try:
            price = broker.get_live_price(symbol)
        except Exception as e:
            logger.error(f"Price fetch failed for {symbol}: {e}")
            continue

        entry = trade["entry_price"]
        pnl_pct = (price - entry) / entry

        logger.info(f"Monitor: {symbol} @ ₹{price:.1f} | P&L={pnl_pct:+.1%}")

        if _past_eod():
            execute_exit(broker, symbol, "EOD_MANDATORY")
            continue

        update_trailing_sl(broker, symbol, price)

        if pnl_pct >= 0.10:
            logger.info(f"TARGET HIT: {symbol} +{pnl_pct:.1%}")
            execute_exit(broker, symbol, "TARGET_HIT")


def run_monitor_loop(broker: BrokerBase):
    logger.info("Monitor loop started")
    while True:
        if _past_eod():
            force_close_all(broker)
            logger.info("EOD exit complete — monitor loop ending")
            break

        # Daily loss limit check — halt new monitoring if limit hit
        corpus = read_corpus()
        if check_daily_loss_limit(corpus):
            logger.warning("Daily loss limit active — closing all positions and stopping")
            force_close_all(broker)
            break

        if get_open_trades():
            monitor_positions(broker)
        else:
            logger.debug("No open positions — sleeping")

        time.sleep(POLL_INTERVAL_SECONDS)
