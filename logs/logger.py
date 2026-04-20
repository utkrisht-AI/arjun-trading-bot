import logging
import os
import csv
import json
from datetime import datetime
import pytz

IST = pytz.timezone("Asia/Kolkata")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DAILY_DIR = os.path.join(BASE_DIR, "daily")
PNL_FILE = os.path.join(BASE_DIR, "pnl_tracker.csv")
STATE_FILE = os.path.join(BASE_DIR, "state.json")

os.makedirs(DAILY_DIR, exist_ok=True)

_DEFAULT_STATE = {
    "open_trades": {},
    "trading_halted": False,
    "api_fail_count": 0,
    "market_context": {
        "nifty_trend": "unknown",
        "nifty_price": None,
        "is_expiry_day": False,
        "expiry_type": "none",
        "can_trade": True,
        "gate_reason": "Not checked yet",
    },
    "today": {
        "candidates": [],
        "screened_count": 0,
        "screening_done": False,
        "candidates_done": False,
    },
    "system": {
        "last_updated": None,
        "dry_run": True,
        "broker": "zerodha",
    },
}


def read_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return dict(_DEFAULT_STATE)
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return dict(_DEFAULT_STATE)


def write_state(patch: dict):
    state = read_state()
    _deep_update(state, patch)
    state["system"]["last_updated"] = datetime.now(IST).isoformat()
    state["system"]["dry_run"] = os.getenv("DRY_RUN", "true").lower() == "true"
    state["system"]["broker"] = os.getenv("BROKER", "zerodha")
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, default=str)


def _deep_update(base: dict, patch: dict):
    for k, v in patch.items():
        if isinstance(v, dict) and k in base and isinstance(base[k], dict):
            _deep_update(base[k], v)
        else:
            base[k] = v

_daily_logger = None


def setup_logging():
    level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def get_daily_logger() -> logging.Logger:
    global _daily_logger
    if _daily_logger:
        return _daily_logger

    today = datetime.now(IST).strftime("%Y-%m-%d")
    log_path = os.path.join(DAILY_DIR, f"{today}.log")

    _daily_logger = logging.getLogger("arjun.daily")
    _daily_logger.setLevel(logging.INFO)

    fh = logging.FileHandler(log_path)
    fh.setFormatter(logging.Formatter("%(asctime)s — %(message)s", "%H:%M:%S"))
    _daily_logger.addHandler(fh)
    return _daily_logger


def read_corpus() -> float:
    if not os.path.exists(PNL_FILE) or os.path.getsize(PNL_FILE) == 0:
        starting = float(os.getenv("STARTING_CORPUS", 2000))
        return starting

    with open(PNL_FILE, newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return float(os.getenv("STARTING_CORPUS", 2000))

    return float(rows[-1]["corpus_after"])


def append_pnl(symbol: str, entry: float, exit_price: float, qty: int, pnl: float, reason: str):
    today = datetime.now(IST).strftime("%Y-%m-%d")
    now = datetime.now(IST).strftime("%H:%M:%S")
    corpus_before = read_corpus()
    corpus_after = corpus_before + pnl

    write_header = not os.path.exists(PNL_FILE) or os.path.getsize(PNL_FILE) == 0
    with open(PNL_FILE, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "date", "time", "symbol", "entry", "exit", "qty", "pnl", "reason", "corpus_after"
        ])
        if write_header:
            writer.writeheader()
        writer.writerow({
            "date": today,
            "time": now,
            "symbol": symbol,
            "entry": round(entry, 2),
            "exit": round(exit_price, 2),
            "qty": qty,
            "pnl": round(pnl, 2),
            "reason": reason,
            "corpus_after": round(corpus_after, 2),
        })


def generate_eod_report(candidates: list[dict], skipped: list[dict]):
    today = datetime.now(IST).strftime("%Y-%m-%d")
    corpus_now = read_corpus()
    starting = float(os.getenv("STARTING_CORPUS", 2000))

    if not os.path.exists(PNL_FILE) or os.path.getsize(PNL_FILE) == 0:
        day_pnl = 0.0
        trades_today = []
    else:
        with open(PNL_FILE, newline="") as f:
            all_rows = list(csv.DictReader(f))
        trades_today = [r for r in all_rows if r["date"] == today]
        day_pnl = sum(float(r["pnl"]) for r in trades_today)

    cumulative_pct = (corpus_now - starting) / starting * 100

    lines = [
        "====================================",
        f"ARJUN DAILY REPORT — {today}",
        "====================================",
        f"Starting Corpus:    ₹{starting:,.0f}",
        f"Ending Corpus:      ₹{corpus_now:,.0f}",
        f"Day P&L:            {'+'if day_pnl>=0 else ''}₹{day_pnl:,.0f} ({day_pnl/starting*100:+.1f}%)",
        f"Cumulative Return:  {cumulative_pct:+.1f}% from Day 1",
        "",
        "TRADES TODAY:",
    ]

    for i, row in enumerate(trades_today, 1):
        pnl = float(row["pnl"])
        entry = float(row["entry"])
        exit_p = float(row["exit"])
        pnl_pct = (exit_p - entry) / entry * 100
        lines.append(
            f"[{i}] {row['symbol']} — BUY ₹{entry:.1f} × {row['qty']} shares\n"
            f"    Exit: {row['time']} ({row['reason']})\n"
            f"    Result: {pnl_pct:+.1f}% | P&L: {'+'if pnl>=0 else ''}₹{pnl:.0f}"
        )

    if skipped:
        lines.append("\nSKIPPED (screened but not entered):")
        for s in skipped:
            lines.append(f"  - {s['symbol']}: Score {s.get('composite_score', '?')} (below 65)")

    if candidates:
        lines.append("\nTOMORROW'S WATCHLIST:")
        for c in candidates[:3]:
            lines.append(f"  - {c['symbol']} (Score: {c.get('composite_score', '?')})")

    lines.append("\nLESSON OF THE DAY:")
    lines.append("  [Review trade log for patterns]")
    lines.append("====================================")

    report = "\n".join(lines)
    report_path = os.path.join(DAILY_DIR, f"{today}_report.txt")
    with open(report_path, "w") as f:
        f.write(report)

    print(report)
    get_daily_logger().info(f"EOD report written to {report_path}")
    return report
