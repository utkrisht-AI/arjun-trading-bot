"""
ARJUN Trading Dashboard — Streamlit
Run:  streamlit run dashboard.py
Deploy: push to GitHub → connect to Streamlit Cloud
"""
import os
import json
import csv
from datetime import datetime, date
from pathlib import Path

import pytz
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
import yfinance as yf

# ── Config ────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ARJUN Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

IST = pytz.timezone("Asia/Kolkata")
BASE = Path(__file__).parent
LOGS = BASE / "logs"
STATE_FILE = LOGS / "state.json"
PNL_FILE = LOGS / "pnl_tracker.csv"
DAILY_DIR = LOGS / "daily"
KNOWLEDGE_FILE = BASE / "TRADING_KNOWLEDGE.md"

STARTING_CORPUS = float(os.getenv("STARTING_CORPUS", 2000))
TARGET_CORPUS = 20_000
TOTAL_DAYS = 7

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  .metric-card {
    background: #1e1e2e; border-radius: 12px;
    padding: 20px; margin: 6px 0;
    border-left: 4px solid #7c3aed;
  }
  .metric-label { color: #888; font-size: 12px; text-transform: uppercase; letter-spacing: 1px; }
  .metric-value { color: #fff; font-size: 28px; font-weight: 700; margin: 4px 0; }
  .metric-delta { font-size: 13px; }
  .win  { color: #22c55e; }
  .loss { color: #ef4444; }
  .neutral { color: #94a3b8; }
  .badge-bull { background:#166534; color:#4ade80; padding:3px 10px; border-radius:20px; font-size:12px; }
  .badge-bear { background:#7f1d1d; color:#f87171; padding:3px 10px; border-radius:20px; font-size:12px; }
  .badge-neutral { background:#1e3a5f; color:#60a5fa; padding:3px 10px; border-radius:20px; font-size:12px; }
  .badge-warn { background:#78350f; color:#fbbf24; padding:3px 10px; border-radius:20px; font-size:12px; }
  .position-card {
    background: #1e1e2e; border-radius: 12px;
    padding: 18px; margin: 8px 0;
  }
  .log-entry { font-family: monospace; font-size: 12px; padding: 2px 0; }
  .log-entry.entry  { color: #60a5fa; }
  .log-entry.exit-win  { color: #4ade80; }
  .log-entry.exit-loss { color: #f87171; }
  .log-entry.halt   { color: #fbbf24; }
  .log-entry.error  { color: #f87171; }
  .log-entry.info   { color: #94a3b8; }
  .section-title { font-size: 18px; font-weight: 600; color: #e2e8f0; margin: 16px 0 8px 0; }
  div[data-testid="stMetric"] { background: #1e1e2e; border-radius: 10px; padding: 14px 18px; }
</style>
""", unsafe_allow_html=True)


# ── Data loaders ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=30)
def load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


@st.cache_data(ttl=30)
def load_pnl() -> pd.DataFrame:
    if not PNL_FILE.exists() or PNL_FILE.stat().st_size == 0:
        return pd.DataFrame(columns=["date","time","symbol","entry","exit","qty","pnl","reason","corpus_after"])
    df = pd.read_csv(PNL_FILE)
    df["pnl"] = pd.to_numeric(df["pnl"], errors="coerce").fillna(0)
    df["corpus_after"] = pd.to_numeric(df["corpus_after"], errors="coerce")
    df["date"] = pd.to_datetime(df["date"])
    return df


@st.cache_data(ttl=60)
def get_live_price(symbol: str) -> float | None:
    try:
        ticker = yf.Ticker(f"{symbol}.NS")
        hist = ticker.history(period="1d", interval="5m")
        if hist.empty:
            return None
        return float(hist["Close"].iloc[-1])
    except Exception:
        return None


@st.cache_data(ttl=60)
def get_nifty_data() -> pd.DataFrame:
    try:
        return yf.Ticker("^NSEI").history(period="30d")
    except Exception:
        return pd.DataFrame()


def load_today_log() -> list[str]:
    today = datetime.now(IST).strftime("%Y-%m-%d")
    log_path = DAILY_DIR / f"{today}.log"
    if not log_path.exists():
        return []
    return log_path.read_text().splitlines()


def current_corpus() -> float:
    df = load_pnl()
    if df.empty:
        return STARTING_CORPUS
    return float(df["corpus_after"].iloc[-1])


def day_number() -> int:
    df = load_pnl()
    if df.empty:
        return 1
    first_trade_date = df["date"].min().date()
    return (date.today() - first_trade_date).days + 1


# ── Sidebar ───────────────────────────────────────────────────────────────────

def sidebar():
    st.sidebar.markdown("## 📈 ARJUN")
    state = load_state()
    sys = state.get("system", {})
    mode = "🟡 DRY RUN" if sys.get("dry_run", True) else "🟢 LIVE"
    broker = sys.get("broker", "zerodha").upper()
    last_upd = sys.get("last_updated")
    if last_upd:
        try:
            t = datetime.fromisoformat(last_upd)
            last_upd = t.strftime("%H:%M:%S")
        except Exception:
            pass

    st.sidebar.markdown(f"**Mode:** {mode}  \n**Broker:** {broker}")
    if last_upd:
        st.sidebar.caption(f"Bot last active: {last_upd} IST")

    halted = state.get("trading_halted", False)
    if halted:
        st.sidebar.error("⛔ Trading HALTED — daily loss limit hit")

    st.sidebar.divider()
    page = st.sidebar.radio(
        "Navigate",
        ["🏠 Overview", "🎯 Live Positions", "🔬 Research & Signals",
         "📈 Trade History", "📊 Analytics", "📋 System Logs", "📚 Knowledge Base"],
        label_visibility="collapsed",
    )
    st.sidebar.divider()
    if st.sidebar.button("🔄 Refresh Now"):
        st.cache_data.clear()
        st.rerun()
    st.sidebar.caption("Auto-refreshes every 30s via cache TTL")
    return page


# ── Page: Overview ────────────────────────────────────────────────────────────

def page_overview():
    st.title("🏠 Mission Control")

    corpus = current_corpus()
    df = load_pnl()
    today_str = date.today().isoformat()

    today_df = df[df["date"].dt.date == date.today()] if not df.empty else pd.DataFrame()
    day_pnl = float(today_df["pnl"].sum()) if not today_df.empty else 0.0
    cumulative_pct = (corpus - STARTING_CORPUS) / STARTING_CORPUS * 100
    days_elapsed = day_number()
    days_left = max(0, TOTAL_DAYS - days_elapsed + 1)

    # Required daily return to still hit target
    if corpus < TARGET_CORPUS and days_left > 0:
        required_daily = ((TARGET_CORPUS / corpus) ** (1 / days_left) - 1) * 100
    else:
        required_daily = 0.0

    # ── Top metrics row
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("💰 Corpus", f"₹{corpus:,.0f}", f"{cumulative_pct:+.1f}% from ₹{STARTING_CORPUS:,.0f}")
    c2.metric("📅 Day", f"{days_elapsed} / {TOTAL_DAYS}", f"{days_left} days left")
    c3.metric("Today P&L", f"₹{day_pnl:+,.0f}", f"{day_pnl/corpus*100:+.1f}%" if corpus else "")
    c4.metric("Cumulative Return", f"{cumulative_pct:+.1f}%", "from ₹2,000")
    c5.metric("Required Daily", f"{required_daily:.1f}%", "to hit ₹20,000")

    st.divider()

    # ── Progress bar
    st.markdown("### 🎯 Target Progress: ₹2,000 → ₹20,000")
    progress = min(1.0, (corpus - STARTING_CORPUS) / (TARGET_CORPUS - STARTING_CORPUS))
    pct_done = progress * 100

    # Milestone markers
    col_prog, col_info = st.columns([3, 1])
    with col_prog:
        st.progress(progress, text=f"₹{corpus:,.0f} / ₹{TARGET_CORPUS:,.0f}  —  {pct_done:.1f}% of journey complete")
        milestone_labels = ""
        milestones = [2000, 4000, 6000, 8000, 10000, 15000, 20000]
        for m in milestones:
            reached = "✅" if corpus >= m else "○"
            milestone_labels += f"{reached} ₹{m//1000}K  "
        st.caption(milestone_labels)
    with col_info:
        if corpus >= TARGET_CORPUS:
            st.success("🎉 TARGET ACHIEVED!")
        else:
            remaining = TARGET_CORPUS - corpus
            st.info(f"₹{remaining:,.0f} to go")

    st.divider()

    # ── Charts row
    chart_col, nifty_col = st.columns(2)

    with chart_col:
        st.markdown("### 💹 Corpus Growth")
        if not df.empty:
            chart_df = pd.concat([
                pd.DataFrame([{"date": pd.Timestamp("2020-01-01"), "corpus_after": STARTING_CORPUS}]),
                df[["date", "corpus_after"]].copy()
            ]).sort_values("date")
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=chart_df["date"], y=chart_df["corpus_after"],
                mode="lines+markers", name="Corpus",
                line=dict(color="#7c3aed", width=2),
                fill="tozeroy", fillcolor="rgba(124,58,237,0.1)",
            ))
            fig.add_hline(y=TARGET_CORPUS, line_dash="dash", line_color="#22c55e",
                          annotation_text="Target ₹20K")
            fig.add_hline(y=STARTING_CORPUS, line_dash="dot", line_color="#94a3b8",
                          annotation_text="Start ₹2K")
            fig.update_layout(
                paper_bgcolor="#0f0f1a", plot_bgcolor="#0f0f1a",
                font_color="#e2e8f0", margin=dict(t=20, b=20),
                xaxis=dict(gridcolor="#2a2a3e"), yaxis=dict(gridcolor="#2a2a3e"),
                showlegend=False, height=300,
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No trades yet — corpus chart will appear after first trade.")

    with nifty_col:
        st.markdown("### 📊 Nifty 50 (30 days)")
        nifty = get_nifty_data()
        if not nifty.empty:
            fig2 = go.Figure()
            colors = ["#22c55e" if c >= o else "#ef4444"
                      for c, o in zip(nifty["Close"], nifty["Open"])]
            fig2.add_trace(go.Candlestick(
                x=nifty.index,
                open=nifty["Open"], high=nifty["High"],
                low=nifty["Low"], close=nifty["Close"],
                increasing_line_color="#22c55e",
                decreasing_line_color="#ef4444",
                name="Nifty",
            ))
            sma20 = nifty["Close"].rolling(20).mean()
            fig2.add_trace(go.Scatter(x=nifty.index, y=sma20, name="SMA20",
                                      line=dict(color="#f59e0b", width=1.5)))
            fig2.update_layout(
                paper_bgcolor="#0f0f1a", plot_bgcolor="#0f0f1a",
                font_color="#e2e8f0", margin=dict(t=20, b=20),
                xaxis=dict(gridcolor="#2a2a3e", rangeslider_visible=False),
                yaxis=dict(gridcolor="#2a2a3e"),
                showlegend=False, height=300,
            )
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("Nifty data unavailable")

    # ── Today summary
    st.divider()
    st.markdown("### 📋 Today's Summary")
    if not today_df.empty:
        wins = (today_df["pnl"] > 0).sum()
        losses = (today_df["pnl"] <= 0).sum()
        best = today_df.loc[today_df["pnl"].idxmax()]
        worst = today_df.loc[today_df["pnl"].idxmin()]
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("Trades Today", len(today_df))
        s2.metric("Wins / Losses", f"{wins} / {losses}")
        s3.metric("Best Trade", f"₹{best['pnl']:+.0f}", best["symbol"])
        s4.metric("Worst Trade", f"₹{worst['pnl']:+.0f}", worst["symbol"])

        st.dataframe(
            today_df[["time","symbol","entry","exit","qty","pnl","reason"]].assign(
                pnl=today_df["pnl"].map(lambda x: f"₹{x:+.0f}")
            ).sort_values("time", ascending=False),
            use_container_width=True, hide_index=True,
        )
    else:
        st.info("No closed trades today yet.")


# ── Page: Live Positions ──────────────────────────────────────────────────────

def page_live_positions():
    st.title("🎯 Live Positions")

    state = load_state()
    open_trades = state.get("open_trades", {})
    halted = state.get("trading_halted", False)
    ctx = state.get("market_context", {})

    # Market status banner
    now_ist = datetime.now(IST)
    market_open = (9, 15) <= (now_ist.hour, now_ist.minute) <= (15, 30)
    status_color = "🟢" if market_open else "🔴"
    st.markdown(f"**Market:** {status_color} {'OPEN' if market_open else 'CLOSED'}  &nbsp;|&nbsp;  "
                f"**IST:** {now_ist.strftime('%H:%M:%S')}  &nbsp;|&nbsp;  "
                f"**Nifty Trend:** {ctx.get('nifty_trend','—').upper()}")

    if halted:
        st.error("⛔ **TRADING HALTED** — Daily loss limit reached. No new entries until tomorrow.")

    st.divider()

    if not open_trades:
        st.info("No open positions right now.")
        corpus = current_corpus()
        st.metric("Available Corpus", f"₹{corpus:,.0f}", "Ready to deploy")
        return

    corpus = current_corpus()
    total_live_pnl = 0.0

    for symbol, trade in open_trades.items():
        live_price = get_live_price(symbol)
        entry = trade["entry_price"]
        sl = trade["stop_loss_price"]
        target = trade["target_price"]
        shares = trade["shares"]
        trailing = trade.get("trailing_sl_activated", False)
        entry_time = trade.get("entry_time", "—")

        if live_price:
            pnl = (live_price - entry) * shares
            pnl_pct = (live_price - entry) / entry * 100
            dist_sl = (live_price - sl) / live_price * 100
            dist_target = (target - live_price) / live_price * 100
            total_live_pnl += pnl
            price_display = f"₹{live_price:.1f}"
            pnl_color = "win" if pnl >= 0 else "loss"
        else:
            pnl = pnl_pct = dist_sl = dist_target = None
            price_display = "—"
            pnl_color = "neutral"

        with st.container():
            st.markdown(f"### {symbol}")
            col1, col2, col3, col4, col5 = st.columns(5)
            col1.metric("Live Price", price_display)
            col2.metric("Entry", f"₹{entry:.1f}")
            col3.metric("P&L", f"₹{pnl:+.0f}" if pnl is not None else "—",
                        f"{pnl_pct:+.1f}%" if pnl_pct is not None else "")
            col4.metric("→ Stop Loss", f"₹{sl:.1f}",
                        f"{dist_sl:.1f}% away" if dist_sl is not None else "")
            col5.metric("→ Target", f"₹{target:.1f}",
                        f"{dist_target:.1f}% away" if dist_target is not None else "")

            # Visual price bar: SL ---- Entry ---- current ---- Target
            if live_price:
                bar_min, bar_max = sl * 0.998, target * 1.002
                bar_range = bar_max - bar_min
                pos_entry  = (entry - bar_min) / bar_range
                pos_sl     = (sl - bar_min) / bar_range
                pos_target = (target - bar_min) / bar_range
                pos_live   = min(1.0, max(0.0, (live_price - bar_min) / bar_range))

                fig = go.Figure()
                # Background zones
                fig.add_shape(type="rect", x0=0, x1=pos_entry, y0=0, y1=1,
                              fillcolor="rgba(239,68,68,0.15)", line_width=0)
                fig.add_shape(type="rect", x0=pos_entry, x1=1, y0=0, y1=1,
                              fillcolor="rgba(34,197,94,0.15)", line_width=0)
                # Lines
                for xval, color, label in [
                    (pos_sl, "#ef4444", f"SL ₹{sl:.0f}"),
                    (pos_entry, "#94a3b8", f"Entry ₹{entry:.0f}"),
                    (pos_target, "#22c55e", f"Target ₹{target:.0f}"),
                ]:
                    fig.add_vline(x=xval, line_color=color, line_dash="dash",
                                  annotation_text=label, annotation_position="top")
                # Live price marker
                marker_color = "#22c55e" if (live_price >= entry) else "#ef4444"
                fig.add_trace(go.Scatter(
                    x=[pos_live], y=[0.5],
                    mode="markers+text",
                    marker=dict(size=18, color=marker_color, symbol="diamond"),
                    text=[f"₹{live_price:.0f}"], textposition="top center",
                    name="Live"
                ))
                fig.update_layout(
                    height=120, margin=dict(t=40, b=10, l=10, r=10),
                    paper_bgcolor="#1e1e2e", plot_bgcolor="#1e1e2e",
                    xaxis=dict(visible=False, range=[0, 1]),
                    yaxis=dict(visible=False, range=[0, 1]),
                    showlegend=False,
                )
                st.plotly_chart(fig, use_container_width=True)

            badge = "🔁 Trailing SL Active" if trailing else "📍 Fixed SL"
            st.caption(f"{badge}  |  {shares} shares  |  Entry time: {entry_time}")
            st.divider()

    if total_live_pnl != 0:
        color = "win" if total_live_pnl >= 0 else "loss"
        st.markdown(f"**Total Unrealised P&L:** <span class='{color}'>₹{total_live_pnl:+,.0f}</span>",
                    unsafe_allow_html=True)


# ── Page: Research & Signals ──────────────────────────────────────────────────

def page_research():
    st.title("🔬 Research & Signals")

    state = load_state()
    ctx = state.get("market_context", {})
    today_data = state.get("today", {})
    candidates = today_data.get("candidates", [])
    screened_count = today_data.get("screened_count", 0)

    # ── Market Context card
    st.markdown("### 🌐 Market Context")
    trend = ctx.get("nifty_trend", "unknown")
    expiry = ctx.get("expiry_type", "none")
    can_trade = ctx.get("can_trade", True)
    gate = ctx.get("gate_reason", "—")

    trend_badge = {
        "bullish": "<span class='badge-bull'>▲ BULLISH</span>",
        "bearish": "<span class='badge-bear'>▼ BEARISH</span>",
        "neutral": "<span class='badge-neutral'>↔ NEUTRAL</span>",
    }.get(trend, "<span class='badge-neutral'>UNKNOWN</span>")

    expiry_badge = "" if expiry == "none" else (
        "<span class='badge-warn'>⚠ MONTHLY EXPIRY</span>" if "monthly" in expiry
        else "<span class='badge-warn'>⚠ WEEKLY EXPIRY</span>"
    )

    gate_badge = (
        "<span class='badge-bull'>✅ TRADING OPEN</span>" if can_trade
        else "<span class='badge-bear'>🚫 TRADING CLOSED</span>"
    )

    st.markdown(
        f"**Nifty Trend:** {trend_badge} &nbsp;&nbsp; "
        f"**Expiry:** {expiry_badge if expiry_badge else '✅ Normal day'} &nbsp;&nbsp; "
        f"**Gate:** {gate_badge}",
        unsafe_allow_html=True
    )
    st.caption(f"Reason: {gate}")

    mc1, mc2 = st.columns(2)
    mc1.metric("Stocks Screened (Passed)", screened_count, "from NSE500")
    mc2.metric("Candidates Selected", len(candidates), "score ≥ 65")

    st.divider()

    if not candidates:
        st.info("Screening hasn't run yet today, or no stocks met the criteria (score ≥ 65).")
        return

    st.markdown("### 🏆 Today's Candidates")

    for c in candidates:
        symbol = c.get("symbol", "?")
        price = c.get("price", 0)
        score = c.get("composite_score", 0)
        tech = c.get("tech_score", 0)
        vol = c.get("vol_score", 0)
        mom = c.get("mom_score", 0)
        sent = c.get("sent_score", 0)
        signals = c.get("signals", {})
        sentiment = c.get("sentiment", "neutral")
        delivery = c.get("delivery_pct")

        with st.expander(f"**{symbol}**  —  Score: {score:.1f} / 100  @  ₹{price:.1f}", expanded=True):
            left, right = st.columns([2, 1])

            with left:
                # Score breakdown radar
                categories = ["Technical", "Volume", "Momentum", "Sentiment", "Composite"]
                values = [tech, vol, mom, sent, score]
                fig = go.Figure(go.Scatterpolar(
                    r=values + [values[0]],
                    theta=categories + [categories[0]],
                    fill="toself",
                    fillcolor="rgba(124,58,237,0.2)",
                    line=dict(color="#7c3aed", width=2),
                    marker=dict(size=6, color="#7c3aed"),
                ))
                fig.update_layout(
                    polar=dict(
                        radialaxis=dict(visible=True, range=[0, 100],
                                        gridcolor="#2a2a3e", tickfont=dict(color="#888")),
                        angularaxis=dict(gridcolor="#2a2a3e"),
                        bgcolor="#1e1e2e",
                    ),
                    paper_bgcolor="#0f0f1a",
                    font_color="#e2e8f0",
                    margin=dict(t=30, b=30, l=30, r=30),
                    height=280,
                    showlegend=False,
                )
                st.plotly_chart(fig, use_container_width=True)

            with right:
                # Individual score bars
                for label, val, color in [
                    ("Technical", tech, "#7c3aed"),
                    ("Volume", vol, "#0ea5e9"),
                    ("Momentum", mom, "#f59e0b"),
                    ("Sentiment", sent, "#22c55e"),
                ]:
                    st.markdown(f"**{label}:** {val:.0f}/100")
                    st.progress(val / 100)

            # Signals table
            st.markdown("#### 📡 Signals")
            sig_col1, sig_col2 = st.columns(2)
            with sig_col1:
                rsi = signals.get("rsi_14", "—")
                macd = signals.get("macd_signal", "—")
                ema_cross = signals.get("ema_9_cross_ema_21", False)
                adx = signals.get("adx_14", "—")
                rsi_color = "win" if 50 <= float(rsi) <= 65 else "neutral" if float(rsi) < 50 else "loss"
                st.markdown(f"**RSI (14):** <span class='{rsi_color}'>{rsi}</span>", unsafe_allow_html=True)
                st.markdown(f"**MACD:** {'🟢 BUY' if macd=='buy' else '🔴 SELL' if macd=='sell' else '⚪ NEUTRAL'}")
                st.markdown(f"**EMA 9×21 Cross:** {'✅ YES' if ema_cross else '❌ No'}")
                st.markdown(f"**ADX (trend strength):** {adx} {'✅ Strong' if float(adx) >= 25 else '⚠ Weak'}")
            with sig_col2:
                stoch = signals.get("stochastic_k", "—")
                bb = signals.get("bb_position", "—")
                obv = signals.get("obv_trend", "—")
                pattern = signals.get("candlestick_pattern", "none")
                vwap = signals.get("price_vs_vwap", "—")
                st.markdown(f"**Stochastic %K:** {stoch}")
                st.markdown(f"**BB Position:** {bb} (0=bottom, 1=top)")
                st.markdown(f"**OBV Trend:** {'📈 Up' if obv=='up' else '📉 Down'}")
                st.markdown(f"**Price vs VWAP:** {'Above ✅' if vwap=='above' else 'Below ⚠'}")
                pattern_emoji = {
                    "morning_star": "🌟 Morning Star",
                    "bullish_engulfing": "🕯 Bullish Engulfing",
                    "hammer": "🔨 Hammer",
                    "doji": "⚖ Doji",
                    "none": "— None",
                }.get(pattern, pattern)
                st.markdown(f"**Candlestick:** {pattern_emoji}")

            # Extra info
            extra = st.columns(3)
            extra[0].metric("Sentiment", sentiment.upper())
            extra[1].metric("Delivery %", f"{delivery:.1f}%" if delivery else "N/A")
            extra[2].metric("Volume Ratio", f"{c.get('volume_ratio',0):.1f}× avg")

        st.markdown("")


# ── Page: Trade History ───────────────────────────────────────────────────────

def page_history():
    st.title("📈 Trade History")
    df = load_pnl()

    if df.empty:
        st.info("No trades recorded yet. Start with a dry run: `python3 main.py --now`")
        return

    # Summary stats
    total = len(df)
    wins = (df["pnl"] > 0).sum()
    losses = (df["pnl"] <= 0).sum()
    win_rate = wins / total * 100
    avg_win = df[df["pnl"] > 0]["pnl"].mean() if wins > 0 else 0
    avg_loss = df[df["pnl"] <= 0]["pnl"].mean() if losses > 0 else 0
    total_pnl = df["pnl"].sum()
    expectancy = (win_rate/100 * avg_win) + ((1-win_rate/100) * avg_loss)

    s1, s2, s3, s4, s5 = st.columns(5)
    s1.metric("Total Trades", total)
    s2.metric("Win Rate", f"{win_rate:.1f}%", f"{wins}W / {losses}L")
    s3.metric("Avg Win", f"₹{avg_win:+.0f}")
    s4.metric("Avg Loss", f"₹{avg_loss:+.0f}")
    s5.metric("Expectancy", f"₹{expectancy:+.0f}", "per trade")

    st.divider()

    # Charts row
    ch1, ch2 = st.columns(2)

    with ch1:
        st.markdown("### P&L per Trade")
        colors = ["#22c55e" if p > 0 else "#ef4444" for p in df["pnl"]]
        fig = go.Figure(go.Bar(
            x=[f"{r['symbol']} {r['date'].strftime('%m/%d')}" for _, r in df.iterrows()],
            y=df["pnl"],
            marker_color=colors,
            text=[f"₹{p:+.0f}" for p in df["pnl"]],
            textposition="outside",
        ))
        fig.update_layout(
            paper_bgcolor="#0f0f1a", plot_bgcolor="#0f0f1a",
            font_color="#e2e8f0", margin=dict(t=20, b=60),
            xaxis=dict(gridcolor="#2a2a3e", tickangle=-45),
            yaxis=dict(gridcolor="#2a2a3e", title="P&L (₹)"),
            height=320, showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)

    with ch2:
        st.markdown("### Win / Loss Breakdown")
        fig2 = go.Figure(go.Pie(
            labels=["Wins", "Losses"],
            values=[wins, losses],
            marker_colors=["#22c55e", "#ef4444"],
            hole=0.5,
            textinfo="label+percent+value",
        ))
        fig2.update_layout(
            paper_bgcolor="#0f0f1a", font_color="#e2e8f0",
            margin=dict(t=20, b=20), height=320,
        )
        st.plotly_chart(fig2, use_container_width=True)

    st.divider()
    st.markdown("### All Trades")

    display_df = df.copy()
    display_df["P&L"] = display_df["pnl"].map(lambda x: f"₹{x:+.0f}")
    display_df["date"] = display_df["date"].dt.strftime("%Y-%m-%d")
    display_df["Return %"] = ((display_df["exit"] - display_df["entry"]) / display_df["entry"] * 100).map(lambda x: f"{x:+.1f}%")
    st.dataframe(
        display_df[["date", "time", "symbol", "entry", "exit", "qty", "P&L", "Return %", "reason", "corpus_after"]],
        use_container_width=True, hide_index=True,
    )


# ── Page: Analytics ───────────────────────────────────────────────────────────

def page_analytics():
    st.title("📊 Analytics")
    df = load_pnl()

    if df.empty:
        st.info("No trades yet — analytics will appear after first trades.")
        return

    # R-multiples (risk = 5% of entry per share)
    df["risk"] = df["entry"] * 0.05 * df["qty"]
    df["r_multiple"] = df["pnl"] / df["risk"].replace(0, float("nan"))
    df["day_of_week"] = df["date"].dt.day_name()

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### R-Multiple Distribution")
        st.caption("R = P&L ÷ Risk. +2R means you made 2× what you risked.")
        fig = go.Figure(go.Histogram(
            x=df["r_multiple"].dropna(),
            nbinsx=20,
            marker_color="#7c3aed",
            opacity=0.8,
        ))
        fig.add_vline(x=0, line_color="#94a3b8", line_dash="dash")
        fig.add_vline(x=df["r_multiple"].mean(), line_color="#f59e0b",
                      annotation_text=f"Avg: {df['r_multiple'].mean():.2f}R")
        fig.update_layout(
            paper_bgcolor="#0f0f1a", plot_bgcolor="#0f0f1a",
            font_color="#e2e8f0", xaxis_title="R-Multiple",
            yaxis_title="Frequency", height=300,
            xaxis=dict(gridcolor="#2a2a3e"), yaxis=dict(gridcolor="#2a2a3e"),
            margin=dict(t=20, b=20),
        )
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.markdown("### P&L by Day of Week")
        dow_df = df.groupby("day_of_week")["pnl"].agg(["sum","count","mean"]).reset_index()
        dow_df.columns = ["Day", "Total P&L", "Trades", "Avg P&L"]
        order = ["Monday","Tuesday","Wednesday","Thursday","Friday"]
        dow_df["Day"] = pd.Categorical(dow_df["Day"], categories=order, ordered=True)
        dow_df = dow_df.sort_values("Day")
        fig2 = go.Figure(go.Bar(
            x=dow_df["Day"], y=dow_df["Total P&L"],
            marker_color=["#22c55e" if v >= 0 else "#ef4444" for v in dow_df["Total P&L"]],
            text=[f"₹{v:+.0f}" for v in dow_df["Total P&L"]],
            textposition="outside",
        ))
        fig2.update_layout(
            paper_bgcolor="#0f0f1a", plot_bgcolor="#0f0f1a",
            font_color="#e2e8f0", height=300,
            xaxis=dict(gridcolor="#2a2a3e"), yaxis=dict(gridcolor="#2a2a3e"),
            margin=dict(t=20, b=20),
        )
        st.plotly_chart(fig2, use_container_width=True)

    # Cumulative P&L by reason
    st.markdown("### P&L by Exit Reason")
    reason_df = df.groupby("reason")["pnl"].agg(["sum","count"]).reset_index()
    reason_df.columns = ["Reason", "Total P&L", "Count"]
    fig3 = px.bar(
        reason_df, x="Reason", y="Total P&L", text="Count",
        color="Total P&L",
        color_continuous_scale=["#ef4444","#1e1e2e","#22c55e"],
    )
    fig3.update_layout(
        paper_bgcolor="#0f0f1a", plot_bgcolor="#0f0f1a",
        font_color="#e2e8f0", height=300,
        xaxis=dict(gridcolor="#2a2a3e"), yaxis=dict(gridcolor="#2a2a3e"),
        margin=dict(t=20, b=20), coloraxis_showscale=False,
    )
    st.plotly_chart(fig3, use_container_width=True)

    # Running SQN
    if len(df) >= 5:
        st.markdown("### System Quality Number (SQN)")
        st.caption("SQN > 2.0 = Good | SQN > 3.0 = Excellent (Van Tharp)")
        r = df["r_multiple"].dropna()
        sqn = (r.mean() / r.std() * (len(r) ** 0.5)) if r.std() > 0 else 0
        col_sqn, col_exp = st.columns(2)
        col_sqn.metric("SQN", f"{sqn:.2f}", "good" if sqn >= 2 else "needs more trades")
        col_exp.metric("Expectancy", f"{r.mean():.2f}R", "per trade")


# ── Page: System Logs ─────────────────────────────────────────────────────────

def page_logs():
    st.title("📋 System Logs")

    today = datetime.now(IST).strftime("%Y-%m-%d")
    log_files = sorted(DAILY_DIR.glob("*.log"), reverse=True) if DAILY_DIR.exists() else []

    if not log_files:
        st.info("No log files found. Logs appear after the first run.")
        return

    selected = st.selectbox(
        "Select log date",
        [f.stem for f in log_files],
        index=0,
    )
    log_path = DAILY_DIR / f"{selected}.log"

    report_path = DAILY_DIR / f"{selected}_report.txt"
    if report_path.exists():
        with st.expander("📄 EOD Report", expanded=False):
            st.code(report_path.read_text(), language=None)

    st.markdown("### Log Entries")
    filter_col, _ = st.columns([1, 3])
    with filter_col:
        filter_type = st.selectbox("Filter", ["All", "ENTRY", "EXIT", "HALT", "ERROR", "TRAILING"])

    lines = log_path.read_text().splitlines() if log_path.exists() else []
    if filter_type != "All":
        lines = [l for l in lines if filter_type in l.upper()]

    if not lines:
        st.info("No matching log entries.")
        return

    log_html = ""
    for line in reversed(lines[-200:]):
        upper = line.upper()
        if "ENTRY" in upper:
            cls = "entry"
        elif "EXIT" in upper and ("+" in line or "PROFIT" in line.upper() or "TARGET" in upper):
            cls = "exit-win"
        elif "EXIT" in upper or "STOP" in upper:
            cls = "exit-loss"
        elif "HALT" in upper or "LIMIT" in upper:
            cls = "halt"
        elif "ERROR" in upper or "CRITICAL" in upper or "FAIL" in upper:
            cls = "error"
        else:
            cls = "info"
        escaped = line.replace("<","&lt;").replace(">","&gt;")
        log_html += f'<div class="log-entry {cls}">{escaped}</div>\n'

    st.markdown(
        f'<div style="background:#0f0f1a;padding:16px;border-radius:10px;'
        f'max-height:500px;overflow-y:auto;font-family:monospace;">'
        f'{log_html}</div>',
        unsafe_allow_html=True,
    )


# ── Page: Knowledge Base ──────────────────────────────────────────────────────

def page_knowledge():
    st.title("📚 Trading Knowledge Base")
    st.caption("Distilled from the world's best trading books — the intellectual foundation of ARJUN.")

    if not KNOWLEDGE_FILE.exists():
        st.error("TRADING_KNOWLEDGE.md not found.")
        return

    content = KNOWLEDGE_FILE.read_text()

    search = st.text_input("🔍 Search knowledge base", placeholder="e.g. stop loss, RSI, Kelly")

    if search:
        lines = content.splitlines()
        results = []
        for i, line in enumerate(lines):
            if search.lower() in line.lower():
                start = max(0, i - 2)
                end = min(len(lines), i + 3)
                results.append("\n".join(lines[start:end]))
        if results:
            st.success(f"Found {len(results)} matches for '{search}':")
            for r in results[:20]:
                st.markdown(f"```\n{r}\n```")
        else:
            st.warning(f"No results for '{search}'")
        return

    # Section nav
    sections = [l.strip("# ") for l in content.splitlines() if l.startswith("## ")]
    selected_sec = st.selectbox("Jump to section", ["(Full document)"] + sections)

    if selected_sec != "(Full document)":
        in_section = False
        section_lines = []
        for line in content.splitlines():
            if line.startswith("## ") and selected_sec in line:
                in_section = True
            elif line.startswith("## ") and in_section:
                break
            if in_section:
                section_lines.append(line)
        st.markdown("\n".join(section_lines))
    else:
        st.markdown(content)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    page = sidebar()

    if page == "🏠 Overview":
        page_overview()
    elif page == "🎯 Live Positions":
        page_live_positions()
    elif page == "🔬 Research & Signals":
        page_research()
    elif page == "📈 Trade History":
        page_history()
    elif page == "📊 Analytics":
        page_analytics()
    elif page == "📋 System Logs":
        page_logs()
    elif page == "📚 Knowledge Base":
        page_knowledge()


if __name__ == "__main__":
    main()
