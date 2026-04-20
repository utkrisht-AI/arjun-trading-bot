import logging
import numpy as np
import pandas as pd

try:
    import talib
    TALIB_AVAILABLE = True
except ImportError:
    TALIB_AVAILABLE = False
    logging.warning("TA-Lib not installed — using pandas fallback indicators")

logger = logging.getLogger(__name__)


# ── Core indicators ───────────────────────────────────────────────────────────

def compute_rsi(close: pd.Series, period: int = 14) -> float:
    if TALIB_AVAILABLE:
        rsi = talib.RSI(close.values, timeperiod=period)
        return float(rsi[-1]) if not np.isnan(rsi[-1]) else 50.0
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1]) if not np.isnan(rsi.iloc[-1]) else 50.0


def compute_macd_signal(close: pd.Series) -> str:
    if TALIB_AVAILABLE:
        macd, signal, _ = talib.MACD(close.values, fastperiod=12, slowperiod=26, signalperiod=9)
        if np.isnan(macd[-1]) or np.isnan(signal[-1]):
            return "neutral"
        if macd[-1] > signal[-1] and macd[-2] <= signal[-2]:
            return "buy"
        if macd[-1] < signal[-1] and macd[-2] >= signal[-2]:
            return "sell"
        return "buy" if macd[-1] > signal[-1] else "sell"
    ema12 = close.ewm(span=12).mean()
    ema26 = close.ewm(span=26).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9).mean()
    if macd.iloc[-1] > signal.iloc[-1] and macd.iloc[-2] <= signal.iloc[-2]:
        return "buy"
    if macd.iloc[-1] < signal.iloc[-1] and macd.iloc[-2] >= signal.iloc[-2]:
        return "sell"
    return "buy" if macd.iloc[-1] > signal.iloc[-1] else "sell"


def compute_ema_cross(close: pd.Series) -> bool:
    if TALIB_AVAILABLE:
        ema9 = talib.EMA(close.values, timeperiod=9)
        ema21 = talib.EMA(close.values, timeperiod=21)
        return bool(ema9[-1] > ema21[-1] and ema9[-2] <= ema21[-2])
    ema9 = close.ewm(span=9).mean()
    ema21 = close.ewm(span=21).mean()
    return bool(ema9.iloc[-1] > ema21.iloc[-1] and ema9.iloc[-2] <= ema21.iloc[-2])


def compute_adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> float:
    if TALIB_AVAILABLE:
        adx = talib.ADX(high.values, low.values, close.values, timeperiod=period)
        return float(adx[-1]) if not np.isnan(adx[-1]) else 20.0
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    return float(atr.iloc[-1]) if not np.isnan(atr.iloc[-1]) else 20.0


def compute_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> float:
    if TALIB_AVAILABLE:
        atr = talib.ATR(high.values, low.values, close.values, timeperiod=period)
        return float(atr[-1]) if not np.isnan(atr[-1]) else float(close.iloc[-1] * 0.02)
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    return float(tr.rolling(period).mean().iloc[-1])


def compute_vwap(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series) -> float:
    typical = (high + low + close) / 3
    vwap = (typical * volume).sum() / volume.sum()
    return float(vwap)


def compute_bb_position(close: pd.Series, period: int = 20) -> float:
    if TALIB_AVAILABLE:
        upper, mid, lower = talib.BBANDS(close.values, timeperiod=period)
        if np.isnan(upper[-1]) or np.isnan(lower[-1]):
            return 0.5
        rng = upper[-1] - lower[-1]
        return float((close.iloc[-1] - lower[-1]) / rng) if rng > 0 else 0.5
    sma = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = sma + 2 * std
    lower = sma - 2 * std
    rng = upper.iloc[-1] - lower.iloc[-1]
    return float((close.iloc[-1] - lower.iloc[-1]) / rng) if rng > 0 else 0.5


def compute_stochastic_k(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> float:
    if TALIB_AVAILABLE:
        k, _ = talib.STOCH(high.values, low.values, close.values,
                           fastk_period=period, slowk_period=3, slowd_period=3)
        return float(k[-1]) if not np.isnan(k[-1]) else 50.0
    low_min = low.rolling(period).min()
    high_max = high.rolling(period).max()
    rng = high_max - low_min
    k = 100 * (close - low_min) / rng.replace(0, np.nan)
    return float(k.iloc[-1]) if not np.isnan(k.iloc[-1]) else 50.0


def compute_obv_trend(close: pd.Series, volume: pd.Series) -> str:
    obv = (np.sign(close.diff()) * volume).fillna(0).cumsum()
    return "up" if obv.iloc[-1] > obv.iloc[-5] else "down"


# ── Candlestick pattern detection ─────────────────────────────────────────────

def _body(o, c) -> float:
    return abs(c - o)


def _upper_shadow(o, h, c) -> float:
    return h - max(o, c)


def _lower_shadow(o, l, c) -> float:
    return min(o, c) - l


def detect_hammer(open_s: pd.Series, high: pd.Series, low: pd.Series, close: pd.Series) -> bool:
    """Bullish hammer on the last candle: small body at top, long lower shadow."""
    if TALIB_AVAILABLE:
        result = talib.CDLHAMMER(open_s.values, high.values, low.values, close.values)
        return int(result[-1]) != 0

    o, h, l, c = open_s.iloc[-1], high.iloc[-1], low.iloc[-1], close.iloc[-1]
    body = _body(o, c)
    lower = _lower_shadow(o, l, c)
    upper = _upper_shadow(o, h, c)
    if body == 0:
        return False
    return (lower >= 2.0 * body) and (upper <= 0.3 * body)


def detect_bullish_engulfing(open_s: pd.Series, high: pd.Series, low: pd.Series, close: pd.Series) -> bool:
    """Bullish engulfing: prior candle bearish, current candle bullish and fully engulfs prior body."""
    if len(close) < 2:
        return False
    if TALIB_AVAILABLE:
        result = talib.CDLENGULFING(open_s.values, high.values, low.values, close.values)
        return int(result[-1]) > 0  # positive = bullish engulfing

    o1, c1 = open_s.iloc[-2], close.iloc[-2]
    o2, c2 = open_s.iloc[-1], close.iloc[-1]

    prior_bearish = c1 < o1
    current_bullish = c2 > o2
    engulfs = o2 <= c1 and c2 >= o1
    return prior_bearish and current_bullish and engulfs


def detect_morning_star(open_s: pd.Series, high: pd.Series, low: pd.Series, close: pd.Series) -> bool:
    """Morning star: bearish candle → small doji/indecision → bullish candle closing above midpoint of first."""
    if len(close) < 3:
        return False
    if TALIB_AVAILABLE:
        result = talib.CDLMORNINGSTAR(open_s.values, high.values, low.values, close.values)
        return int(result[-1]) != 0

    o1, c1 = open_s.iloc[-3], close.iloc[-3]  # bearish
    o2, c2 = open_s.iloc[-2], close.iloc[-2]  # small body
    o3, c3 = open_s.iloc[-1], close.iloc[-1]  # bullish

    first_bearish = c1 < o1 and _body(o1, c1) > 0
    middle_small = _body(o2, c2) < 0.3 * _body(o1, c1)
    last_bullish = c3 > o3
    closes_above_midpoint = c3 > (o1 + c1) / 2

    return first_bearish and middle_small and last_bullish and closes_above_midpoint


def detect_doji(open_s: pd.Series, high: pd.Series, low: pd.Series, close: pd.Series) -> bool:
    """Doji: open ≈ close (body < 10% of total range)."""
    if TALIB_AVAILABLE:
        result = talib.CDLDOJI(open_s.values, high.values, low.values, close.values)
        return int(result[-1]) != 0

    o, h, l, c = open_s.iloc[-1], high.iloc[-1], low.iloc[-1], close.iloc[-1]
    total_range = h - l
    if total_range == 0:
        return False
    return _body(o, c) / total_range < 0.10


def detect_candlestick_pattern(
    open_s: pd.Series, high: pd.Series, low: pd.Series, close: pd.Series
) -> str:
    """
    Returns the strongest bullish pattern detected on the last candles.
    Priority: morning_star > bullish_engulfing > hammer > doji > none
    """
    try:
        if detect_morning_star(open_s, high, low, close):
            return "morning_star"
        if detect_bullish_engulfing(open_s, high, low, close):
            return "bullish_engulfing"
        if detect_hammer(open_s, high, low, close):
            return "hammer"
        if detect_doji(open_s, high, low, close):
            return "doji"
    except Exception as e:
        logger.debug(f"Candlestick detection error: {e}")
    return "none"


CANDLESTICK_SCORE = {
    "morning_star": 100,
    "bullish_engulfing": 90,
    "hammer": 80,
    "doji": 50,
    "none": 0,
}


# ── Master signal generator ───────────────────────────────────────────────────

def generate_signals(data: dict) -> dict:
    hist = data["hist"]
    close = hist["Close"]
    high = hist["High"]
    low = hist["Low"]
    open_s = hist["Open"]
    volume = hist["Volume"]

    rsi = compute_rsi(close)
    macd_signal = compute_macd_signal(close)
    ema_cross = compute_ema_cross(close)
    adx = compute_adx(high, low, close)
    atr = compute_atr(high, low, close)
    vwap = compute_vwap(high, low, close, volume)
    bb_pos = compute_bb_position(close)
    stoch_k = compute_stochastic_k(high, low, close)
    obv_trend = compute_obv_trend(close, volume)
    pattern = detect_candlestick_pattern(open_s, high, low, close)
    price = data["price"]

    return {
        "rsi_14": round(rsi, 1),
        "macd_signal": macd_signal,
        "ema_9_cross_ema_21": ema_cross,
        "adx_14": round(adx, 1),
        "atr_14": round(atr, 2),
        "price_vs_vwap": "above" if price > vwap else "below",
        "bb_position": round(bb_pos, 2),
        "stochastic_k": round(stoch_k, 1),
        "obv_trend": obv_trend,
        "volume_spike": data["volume_ratio"],
        "candlestick_pattern": pattern,
        "candlestick_score": CANDLESTICK_SCORE[pattern],
    }
