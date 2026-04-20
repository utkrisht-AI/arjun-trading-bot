import logging

logger = logging.getLogger(__name__)

BROKERAGE_PER_ORDER = 20.0  # ₹20 flat fee (Zerodha/Upstox)
MAX_RISK_PCT = 0.20          # 20% of corpus per trade
STOP_LOSS_PCT = 0.05         # 5% hard stop
MAX_DEPLOY_PCT = 0.60        # Never deploy more than 60% of corpus in one trade


def calculate_position(corpus: float, price: float) -> dict | None:
    max_loss_rs = corpus * MAX_RISK_PCT
    stop_loss_price = round(price * (1 - STOP_LOSS_PCT), 2)
    risk_per_share = price - stop_loss_price

    if risk_per_share <= 0:
        logger.error("Risk per share is zero — skipping")
        return None

    shares = int(max_loss_rs / risk_per_share)

    # Cap at 60% corpus deployment
    max_shares_by_capital = int((corpus * MAX_DEPLOY_PCT) / price)
    shares = min(shares, max_shares_by_capital)

    if shares < 1:
        logger.warning(f"Cannot afford even 1 share: price=₹{price}, corpus=₹{corpus}")
        return None

    cost = shares * price
    brokerage = BROKERAGE_PER_ORDER * 2  # buy + sell
    total_cost = cost + brokerage
    target_price = round(price * 1.10, 2)
    max_loss = shares * (price - stop_loss_price) + brokerage

    logger.info(
        f"Position: {shares} shares @ ₹{price} | cost=₹{cost:.0f} | "
        f"SL=₹{stop_loss_price} | target=₹{target_price} | max_loss=₹{max_loss:.0f}"
    )

    return {
        "shares": shares,
        "cost": round(cost, 2),
        "total_cost_with_brokerage": round(total_cost, 2),
        "stop_loss_price": stop_loss_price,
        "target_price": target_price,
        "max_loss": round(max_loss, 2),
        "risk_pct_of_corpus": round(max_loss / corpus * 100, 1),
    }
