"""
Market context: Nifty trend, expiry day detection, ASM/GSM list, daily trading gate.
Run before any screening or trade execution.
"""
import logging
from datetime import datetime, date
import calendar
import pytz
import yfinance as yf

from research.nse_client import get_nse_client

logger = logging.getLogger(__name__)
IST = pytz.timezone("Asia/Kolkata")

_asmgsm_cache: set[str] = set()
_cache_date: date | None = None


# ── Nifty trend ──────────────────────────────────────────────────────────────

def get_nifty_trend() -> str:
    """Returns 'bullish', 'neutral', or 'bearish' based on Nifty 50 vs its SMAs."""
    try:
        nifty = yf.Ticker("^NSEI")
        hist = nifty.history(period="60d")
        if hist.empty or len(hist) < 50:
            logger.warning("Insufficient Nifty data — defaulting to neutral")
            return "neutral"

        price = hist["Close"].iloc[-1]
        sma20 = hist["Close"].tail(20).mean()
        sma50 = hist["Close"].tail(50).mean()

        if price > sma20 and price > sma50:
            trend = "bullish"
        elif price < sma20 and price < sma50:
            trend = "bearish"
        else:
            trend = "neutral"

        logger.info(
            f"Nifty trend: {trend} | price={price:.0f} SMA20={sma20:.0f} SMA50={sma50:.0f}"
        )
        return trend
    except Exception as e:
        logger.error(f"Nifty trend check failed: {e}")
        return "neutral"


# ── Expiry day detection ──────────────────────────────────────────────────────

def is_thursday() -> bool:
    return datetime.now(IST).weekday() == 3  # 0=Mon … 3=Thu


def is_monthly_expiry() -> bool:
    """True if today is the last Thursday of the current month."""
    today = datetime.now(IST).date()
    if today.weekday() != 3:
        return False
    # Next Thursday would be in next month → this is the last Thursday
    next_thu = today.day + 7
    _, month_days = calendar.monthrange(today.year, today.month)
    return next_thu > month_days


def expiry_context() -> dict:
    thu = is_thursday()
    monthly = is_monthly_expiry() if thu else False
    return {
        "is_expiry_day": thu,
        "is_monthly_expiry": monthly,
        "expiry_type": ("monthly" if monthly else "weekly") if thu else "none",
    }


# ── ASM / GSM surveillance list ───────────────────────────────────────────────

def get_asmgsm_symbols() -> set[str]:
    """Returns combined set of ASM + GSM symbols. Cached once per day."""
    global _asmgsm_cache, _cache_date
    today = datetime.now(IST).date()
    if _cache_date == today and _asmgsm_cache is not None:
        return _asmgsm_cache

    client = get_nse_client()
    asm = client.get_asm_symbols()
    gsm = client.get_gsm_symbols()
    _asmgsm_cache = asm | gsm
    _cache_date = today
    logger.info(f"ASM/GSM list loaded: {len(asm)} ASM + {len(gsm)} GSM = {len(_asmgsm_cache)} total")
    return _asmgsm_cache


def is_under_surveillance(symbol: str) -> bool:
    return symbol.upper() in get_asmgsm_symbols()


# ── Delivery % fetch ──────────────────────────────────────────────────────────

def get_delivery_pct(symbol: str) -> float | None:
    return get_nse_client().get_delivery_pct(symbol)


# ── Master trading gate ───────────────────────────────────────────────────────

def should_trade_today() -> tuple[bool, str]:
    """
    Master gate that must return True before any trade is executed.
    Returns (can_trade, reason_string).
    """
    trend = get_nifty_trend()
    expiry = expiry_context()

    if trend == "bearish":
        return False, f"SKIP: Nifty in bearish trend (below SMA20 and SMA50) — no longs today"

    reasons = []
    if trend == "neutral":
        reasons.append("Nifty trend neutral — trade with reduced conviction")
    if expiry["is_monthly_expiry"]:
        reasons.append("Monthly F&O expiry — extreme volatility, reduced size recommended")
    elif expiry["is_expiry_day"]:
        reasons.append("Weekly F&O expiry Thursday — elevated volatility")

    reason = " | ".join(reasons) if reasons else "Market conditions OK"
    logger.info(f"Trading gate: OPEN | {reason}")
    return True, reason


def get_full_context() -> dict:
    trend = get_nifty_trend()
    expiry = expiry_context()
    can_trade, gate_reason = should_trade_today()
    return {
        "nifty_trend": trend,
        **expiry,
        "can_trade": can_trade,
        "gate_reason": gate_reason,
    }
