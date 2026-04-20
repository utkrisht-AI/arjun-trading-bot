import logging
import os
from broker.base import BrokerBase, Order
from execution.position_sizer import calculate_position
from logs.logger import get_daily_logger, append_pnl, write_state

logger = logging.getLogger(__name__)
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"

_open_trades: dict[str, dict] = {}  # symbol → trade state
_api_fail_count = 0
MAX_API_FAILURES = 3
_trading_halted = False
DAILY_LOSS_LIMIT_PCT = 0.10  # halt if day P&L hits -10% of corpus


def _safe_call(fn, *args, **kwargs):
    global _api_fail_count
    try:
        result = fn(*args, **kwargs)
        _api_fail_count = 0
        return result
    except Exception as e:
        _api_fail_count += 1
        logger.error(f"API call failed ({_api_fail_count}/{MAX_API_FAILURES}): {e}")
        if _api_fail_count >= MAX_API_FAILURES:
            logger.critical("3 consecutive API failures — HALTING trading")
            raise RuntimeError("Broker API unresponsive. Manual intervention required.") from e
        return None


def check_daily_loss_limit(corpus: float) -> bool:
    """Read today's realised P&L from the CSV and halt if it breaches -10% of corpus."""
    global _trading_halted
    if _trading_halted:
        return True

    from logs.logger import PNL_FILE
    import csv
    from datetime import datetime
    import pytz
    today = datetime.now(pytz.timezone("Asia/Kolkata")).strftime("%Y-%m-%d")

    try:
        if not os.path.exists(PNL_FILE) or os.path.getsize(PNL_FILE) == 0:
            return False
        with open(PNL_FILE, newline="") as f:
            rows = [r for r in csv.DictReader(f) if r.get("date") == today]
        day_pnl = sum(float(r["pnl"]) for r in rows)
        if day_pnl / corpus <= -DAILY_LOSS_LIMIT_PCT:
            _trading_halted = True
            logger.critical(
                f"DAILY LOSS LIMIT HIT: day P&L=₹{day_pnl:.0f} ({day_pnl/corpus:.1%}) "
                f"≤ -{DAILY_LOSS_LIMIT_PCT:.0%} — trading halted for today"
            )
            get_daily_logger().info(f"HALT: daily loss limit reached ({day_pnl/corpus:.1%})")
            return True
    except Exception as e:
        logger.error(f"Daily loss check failed: {e}")
    return False


def execute_entry(broker: BrokerBase, symbol: str, corpus: float) -> dict | None:
    if check_daily_loss_limit(corpus):
        logger.warning("Trading halted — daily loss limit reached")
        return None

    if len(_open_trades) >= 2:
        logger.warning("Max 2 positions already open — skipping entry")
        return None

    price = _safe_call(broker.get_live_price, symbol)
    if price is None:
        return None

    sizing = calculate_position(corpus, price)
    if sizing is None:
        return None

    limit_price = round(price * 1.001, 1)
    sl_price = sizing["stop_loss_price"]
    shares = sizing["shares"]

    if DRY_RUN:
        logger.info(f"[DRY RUN] ENTRY: BUY {shares} {symbol} @ ₹{limit_price} | SL=₹{sl_price}")
        entry_order = Order(order_id=f"DRY-E-{symbol}", symbol=symbol, qty=shares,
                            price=limit_price, transaction_type="BUY", status="COMPLETE")
        sl_order = Order(order_id=f"DRY-SL-{symbol}", symbol=symbol, qty=shares,
                         price=sl_price, transaction_type="SELL", status="TRIGGER_PENDING")
    else:
        entry_order = _safe_call(broker.place_limit_order, symbol, shares, limit_price, "BUY")
        if entry_order is None:
            return None

        sl_order = _safe_call(broker.place_sl_order, symbol, shares, sl_price, "SELL")
        if sl_order is None:
            # SL failed — cancel entry immediately
            logger.critical(f"SL order failed for {symbol} — cancelling entry order")
            _safe_call(broker.cancel_order, entry_order.order_id)
            return None

    trade = {
        "symbol": symbol,
        "shares": shares,
        "entry_price": limit_price,
        "stop_loss_price": sl_price,
        "target_price": sizing["target_price"],
        "entry_order_id": entry_order.order_id,
        "sl_order_id": sl_order.order_id,
        "trailing_sl_activated": False,
    }
    from datetime import datetime
    import pytz
    trade["entry_time"] = datetime.now(pytz.timezone("Asia/Kolkata")).isoformat()
    _open_trades[symbol] = trade
    write_state({"open_trades": _open_trades, "trading_halted": _trading_halted})

    get_daily_logger().info(
        f"ENTRY: {symbol} | {shares} shares @ ₹{limit_price} | "
        f"SL=₹{sl_price} | Target=₹{sizing['target_price']}"
    )
    return trade


def update_trailing_sl(broker: BrokerBase, symbol: str, current_price: float):
    trade = _open_trades.get(symbol)
    if trade is None or trade["trailing_sl_activated"]:
        return

    entry = trade["entry_price"]
    if current_price >= entry * 1.06:
        new_sl = round(entry * 1.02, 1)
        logger.info(f"Trailing SL activated for {symbol}: {trade['stop_loss_price']} → {new_sl}")
        if not DRY_RUN:
            _safe_call(broker.modify_sl_order, trade["sl_order_id"], new_sl)
        trade["stop_loss_price"] = new_sl
        trade["trailing_sl_activated"] = True
        write_state({"open_trades": _open_trades})
        get_daily_logger().info(f"TRAILING SL: {symbol} → ₹{new_sl}")


def execute_exit(broker: BrokerBase, symbol: str, reason: str) -> float | None:
    trade = _open_trades.get(symbol)
    if trade is None:
        return None

    if DRY_RUN:
        exit_price = trade["entry_price"] * 1.05  # simulate a 5% gain in dry run
        logger.info(f"[DRY RUN] EXIT: {symbol} @ ₹{exit_price:.1f} ({reason})")
    else:
        # Cancel SL order first to avoid double-sell
        _safe_call(broker.cancel_order, trade["sl_order_id"])
        exit_order = _safe_call(broker.place_market_order, symbol, trade["shares"], "SELL")
        if exit_order is None:
            return None
        exit_price = _safe_call(broker.get_live_price, symbol) or trade["entry_price"]

    pnl = (exit_price - trade["entry_price"]) * trade["shares"]
    pnl_pct = (exit_price - trade["entry_price"]) / trade["entry_price"]

    get_daily_logger().info(
        f"EXIT ({reason}): {symbol} @ ₹{exit_price:.1f} | "
        f"P&L: {'+'if pnl>=0 else ''}₹{pnl:.0f} ({pnl_pct:+.1%})"
    )
    append_pnl(symbol, trade["entry_price"], exit_price, trade["shares"], pnl, reason)
    del _open_trades[symbol]
    write_state({"open_trades": _open_trades, "trading_halted": _trading_halted})
    return pnl


def force_close_all(broker: BrokerBase):
    logger.info(f"EOD: Force closing {len(_open_trades)} open position(s)")
    for symbol in list(_open_trades.keys()):
        execute_exit(broker, symbol, "EOD_MANDATORY")


def get_open_trades() -> dict:
    return dict(_open_trades)
