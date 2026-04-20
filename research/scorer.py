import logging
from research.technical import generate_signals

logger = logging.getLogger(__name__)

SENTIMENT_SCORE_MAP = {"positive": 100, "neutral": 60, "negative": 0}


def compute_technical_score(signals: dict) -> float:
    score = 0.0
    weights = 0.0

    # RSI: ideal 50–65
    rsi = signals.get("rsi_14", 50)
    if 50 <= rsi <= 65:
        score += 100 * 0.15
    elif 45 <= rsi < 50 or 65 < rsi <= 75:
        score += 60 * 0.15
    else:
        score += 20 * 0.15
    weights += 0.15

    # MACD
    macd = signals.get("macd_signal", "neutral")
    score += (100 if macd == "buy" else 40 if macd == "neutral" else 0) * 0.20
    weights += 0.20

    # EMA cross
    score += (100 if signals.get("ema_9_cross_ema_21") else 30) * 0.15
    weights += 0.15

    # ADX (trend strength)
    adx = signals.get("adx_14", 20)
    score += (min(100, adx * 3) if adx >= 25 else adx * 2) * 0.15
    weights += 0.15

    # Price vs VWAP
    score += (80 if signals.get("price_vs_vwap") == "above" else 30) * 0.10
    weights += 0.10

    # Bollinger Band position (0.3–0.7 is ideal)
    bb = signals.get("bb_position", 0.5)
    score += (100 if 0.3 <= bb <= 0.7 else 50) * 0.10
    weights += 0.10

    # OBV trend
    score += (80 if signals.get("obv_trend") == "up" else 20) * 0.15
    weights += 0.15

    base_score = round(score / weights, 1) if weights > 0 else 50.0

    # Candlestick pattern bonus (up to +10 points, not weighted into the base)
    candle_score = signals.get("candlestick_score", 0)
    bonus = round(candle_score * 0.10, 1)  # max +10 points

    return min(100.0, base_score + bonus)


def compute_volume_score(data: dict) -> float:
    ratio = data.get("volume_ratio", 1.0)
    if ratio >= 3.0:
        return 100.0
    elif ratio >= 2.0:
        return 80.0
    elif ratio >= 1.5:
        return 60.0
    return 30.0


def compute_momentum_score(signals: dict) -> float:
    stoch = signals.get("stochastic_k", 50)
    rsi = signals.get("rsi_14", 50)
    macd = signals.get("macd_signal", "neutral")

    score = 0
    score += min(100, stoch) * 0.40
    score += min(100, rsi) * 0.30
    score += (100 if macd == "buy" else 50 if macd == "neutral" else 0) * 0.30
    return round(score, 1)


def score_candidate(data: dict, sentiment: str) -> dict:
    signals = generate_signals(data)
    data["signals"] = signals

    tech_score = compute_technical_score(signals)
    vol_score = compute_volume_score(data)
    mom_score = compute_momentum_score(signals)
    sent_score = float(SENTIMENT_SCORE_MAP.get(sentiment, 60))

    composite = (
        0.40 * tech_score +
        0.30 * vol_score +
        0.20 * mom_score +
        0.10 * sent_score
    )

    result = {
        **data,
        "signals": signals,
        "tech_score": tech_score,
        "vol_score": vol_score,
        "mom_score": mom_score,
        "sent_score": sent_score,
        "composite_score": round(composite, 1),
        "sentiment": sentiment,
    }

    pattern = signals.get("candlestick_pattern", "none")
    logger.info(
        f"{data['symbol']}: composite={composite:.1f} "
        f"(tech={tech_score:.0f} vol={vol_score:.0f} mom={mom_score:.0f} "
        f"sent={sent_score:.0f} candle={pattern})"
    )
    return result


def generate_candidates(screened: list[dict], sentiments: dict[str, str]) -> list[dict]:
    scored = []
    for data in screened:
        symbol = data["symbol"]
        if sentiments.get(symbol) == "negative":
            logger.info(f"SKIP {symbol}: negative sentiment")
            continue
        sentiment = sentiments.get(symbol, "neutral")
        result = score_candidate(data, sentiment)
        if result["composite_score"] >= 65:
            scored.append(result)
        else:
            logger.info(f"SKIP {symbol}: score {result['composite_score']:.1f} < 65")

    scored.sort(key=lambda x: x["composite_score"], reverse=True)
    top2 = scored[:2]
    logger.info(f"Final candidates: {[c['symbol'] for c in top2]}")
    return top2
