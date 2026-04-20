"""
Simple backtest runner. Tests the scoring strategy on historical data.
Usage: python scripts/backtest.py --symbol RELIANCE --days 30
"""
import argparse
import pandas as pd
import yfinance as yf
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from research.technical import generate_signals
from research.scorer import compute_technical_score, compute_volume_score, compute_momentum_score
from execution.position_sizer import calculate_position

STOP_LOSS_PCT = 0.05
TARGET_PCT = 0.10
BROKERAGE = 40  # ₹20 × 2


def backtest_symbol(symbol: str, days: int = 60, corpus: float = 2000.0):
    ticker = yf.Ticker(f"{symbol}.NS")
    hist = ticker.history(period=f"{days + 30}d")

    if len(hist) < 30:
        print(f"Not enough data for {symbol}")
        return

    results = []
    corpus_track = corpus

    for i in range(30, len(hist) - 1):
        window = hist.iloc[:i]
        today = hist.iloc[i]
        tomorrow = hist.iloc[i + 1]

        price = today["Close"]
        avg_vol_10d = window["Volume"].tail(10).mean()
        vol_ratio = today["Volume"] / avg_vol_10d if avg_vol_10d > 0 else 0

        if not (10 <= price <= 500 and avg_vol_10d >= 500_000 and vol_ratio >= 1.5):
            continue

        data = {
            "symbol": symbol,
            "price": price,
            "avg_volume_10d": avg_vol_10d,
            "today_volume": today["Volume"],
            "volume_ratio": vol_ratio,
            "hist": window,
        }

        signals = generate_signals(data)
        tech_score = compute_technical_score(signals)
        vol_score = compute_volume_score(data)
        mom_score = compute_momentum_score(signals)
        composite = 0.40 * tech_score + 0.30 * vol_score + 0.20 * mom_score + 0.10 * 60

        if composite < 65:
            continue

        sizing = calculate_position(corpus_track, price)
        if not sizing:
            continue

        shares = sizing["shares"]
        entry = price
        sl = sizing["stop_loss_price"]
        target = sizing["target_price"]

        # Simulate next-day outcome
        high = tomorrow["High"]
        low = tomorrow["Low"]

        if low <= sl:
            exit_price = sl
            outcome = "STOP_LOSS"
        elif high >= target:
            exit_price = target
            outcome = "TARGET_HIT"
        else:
            exit_price = tomorrow["Close"]
            outcome = "HELD"

        pnl = (exit_price - entry) * shares - BROKERAGE
        corpus_track += pnl
        pnl_pct = (exit_price - entry) / entry

        results.append({
            "date": hist.index[i].strftime("%Y-%m-%d"),
            "score": round(composite, 1),
            "entry": round(entry, 2),
            "exit": round(exit_price, 2),
            "shares": shares,
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct * 100, 1),
            "outcome": outcome,
            "corpus": round(corpus_track, 2),
        })

    if not results:
        print(f"No qualifying trades found for {symbol}")
        return

    df = pd.DataFrame(results)
    wins = (df["pnl"] > 0).sum()
    total = len(df)
    total_pnl = df["pnl"].sum()
    win_rate = wins / total * 100

    print(f"\n{'='*50}")
    print(f"BACKTEST: {symbol} | {days} days")
    print(f"{'='*50}")
    print(f"Trades:      {total}")
    print(f"Win rate:    {win_rate:.1f}%")
    print(f"Total P&L:   ₹{total_pnl:,.0f}")
    print(f"Final corpus: ₹{corpus_track:,.0f} (started ₹{corpus:,.0f})")
    print(f"\nTrade log:")
    print(df[["date", "score", "entry", "exit", "pnl_pct", "outcome", "corpus"]].to_string(index=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="RELIANCE", help="NSE symbol")
    parser.add_argument("--days", type=int, default=60, help="Lookback days")
    parser.add_argument("--corpus", type=float, default=2000.0, help="Starting corpus")
    args = parser.parse_args()
    backtest_symbol(args.symbol, args.days, args.corpus)
