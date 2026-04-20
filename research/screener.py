import logging
import pandas as pd
import yfinance as yf

from research.market_context import is_under_surveillance, get_delivery_pct, should_trade_today

logger = logging.getLogger(__name__)

SCREENING_CRITERIA = {
    "min_price": 10,
    "max_price": 500,
    "min_volume_10d_avg": 500_000,
    "min_delivery_pct": 30,
    "rsi_min": 45,
    "rsi_max": 75,
    "volume_ratio_min": 1.5,
}

NSE500_URL = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"


def fetch_nse500_symbols() -> list[str]:
    try:
        df = pd.read_csv(NSE500_URL)
        symbols = df["Symbol"].tolist()
        logger.info(f"Fetched {len(symbols)} NSE500 symbols")
        return symbols
    except Exception as e:
        logger.error(f"Failed to fetch NSE500 list: {e}")
        return _fallback_symbols()


def _fallback_symbols() -> list[str]:
    return [
        "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK",
        "HINDUNILVR", "SBIN", "BHARTIARTL", "ITC", "KOTAKBANK",
        "LT", "AXISBANK", "ASIANPAINT", "MARUTI", "SUNPHARMA",
        "TITAN", "BAJFINANCE", "WIPRO", "ULTRACEMCO", "NESTLEIND",
    ]


def get_stock_data(symbol: str) -> dict | None:
    # Hard gate: skip ASM/GSM stocks
    if is_under_surveillance(symbol):
        logger.debug(f"SKIP {symbol}: under ASM/GSM surveillance")
        return None

    try:
        ticker = yf.Ticker(f"{symbol}.NS")
        hist = ticker.history(period="30d")
        if hist.empty or len(hist) < 10:
            return None

        current_price = hist["Close"].iloc[-1]
        if not (SCREENING_CRITERIA["min_price"] <= current_price <= SCREENING_CRITERIA["max_price"]):
            return None

        avg_volume_10d = hist["Volume"].tail(10).mean()
        today_volume = hist["Volume"].iloc[-1]

        if avg_volume_10d < SCREENING_CRITERIA["min_volume_10d_avg"]:
            return None

        volume_ratio = today_volume / avg_volume_10d if avg_volume_10d > 0 else 0
        if volume_ratio < SCREENING_CRITERIA["volume_ratio_min"]:
            return None

        sma_20 = hist["Close"].tail(20).mean()
        if current_price < sma_20:
            return None

        # Delivery % check via NSE API (soft gate — skip stock if data available and below threshold)
        delivery_pct = get_delivery_pct(symbol)
        if delivery_pct is not None and delivery_pct < SCREENING_CRITERIA["min_delivery_pct"]:
            logger.debug(f"SKIP {symbol}: delivery {delivery_pct:.1f}% < {SCREENING_CRITERIA['min_delivery_pct']}%")
            return None

        return {
            "symbol": symbol,
            "price": round(current_price, 2),
            "avg_volume_10d": int(avg_volume_10d),
            "today_volume": int(today_volume),
            "volume_ratio": round(volume_ratio, 2),
            "sma_20": round(sma_20, 2),
            "delivery_pct": delivery_pct,
            "hist": hist,
        }
    except Exception as e:
        logger.debug(f"Skipping {symbol}: {e}")
        return None


def run_screening() -> list[dict]:
    # Master market gate — abort if conditions are unfavourable
    can_trade, reason = should_trade_today()
    if not can_trade:
        logger.warning(f"Screening aborted: {reason}")
        return []

    logger.info(f"Starting universe screening... ({reason})")
    symbols = fetch_nse500_symbols()
    candidates = []

    for symbol in symbols:
        data = get_stock_data(symbol)
        if data:
            candidates.append(data)
            logger.info(
                f"PASS: {symbol} @ ₹{data['price']} "
                f"vol_ratio={data['volume_ratio']:.1f}x "
                f"delivery={data['delivery_pct']:.1f}%" if data['delivery_pct'] else
                f"PASS: {symbol} @ ₹{data['price']} vol_ratio={data['volume_ratio']:.1f}x"
            )

    logger.info(f"Screening complete: {len(candidates)}/{len(symbols)} stocks passed")
    return candidates
