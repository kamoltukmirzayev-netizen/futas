"""
app_streamlit.py
===============================================================================
FUTAS — Fibonacci Urvin Adaptive Trading Analysis System
Scientific web application (Streamlit).

Run locally:
    pip install -r requirements.txt
    streamlit run app_streamlit.py

This is a scientific-research and algorithmic-testing instrument.
It does NOT provide financial advice.
===============================================================================
"""

from __future__ import annotations

import io
import json
from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st

import plotly.graph_objects as go

import futas_engine as fe
from futas_engine import (
    FU_COEFFICIENTS,
    analyze,
    backtest,
    worked_example,
    normalize_ohlc,
    fu_levels,
)

# Local feature modules are imported PLAINLY (not in try/except) so Streamlit's
# file-watcher hot-reloads them when they change. Conditionally-imported modules
# are NOT reliably reloaded, which caused the recurring "stale module" errors
# (e.g. live_data.LIVE_CENTER_ASSETS, format_signal session). All of these import
# cleanly with the project's declared dependencies; optional deps (MetaTrader5,
# pytesseract) are handled inside the respective modules.
import chart_ingest
import live_data
import telegram_signals as tg
import screenshot_ta
import mt5_feed
import sessions as fsessions
import tv_chart
import i18n
import streamlit.components.v1 as components

_CHART_IMPORTED = True
_LIVE_IMPORTED = True
_TG_IMPORTED = True
_SSTA_IMPORTED = True
_MT5_MODULE = True
_SESS_IMPORTED = True
_TV_IMPORTED = True


# =============================================================================
# Page config + light styling
# =============================================================================
st.set_page_config(
    page_title="FUTAS — Fibonacci Urvin Adaptive Trading Analysis System",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

ACTION_COLORS = {"BUY": "#1a9850", "SELL": "#d73027", "WAIT": "#737373"}

st.markdown(
    """
    <style>
      .futas-title { font-size: 1.9rem; font-weight: 800; margin-bottom: 0; }
      .futas-sub   { color: #666; margin-top: 0; }
      .signal-badge{ padding: 14px 18px; border-radius: 10px; color: #fff;
                     font-size: 1.6rem; font-weight: 800; text-align:center; }
      .disclaimer  { background:#fff8e1; border:1px solid #ffe082; padding:8px 12px;
                     border-radius:8px; font-size:0.85rem; color:#5d4037; }
    </style>
    """,
    unsafe_allow_html=True,
)


# =============================================================================
# Session state
# =============================================================================
def _init_state():
    st.session_state.setdefault("df", None)          # normalized OHLC DataFrame (effective / shown)
    st.session_state.setdefault("df_base", None)     # as-loaded frame (source of truth for resampling)
    st.session_state.setdefault("tf_active", None)   # currently selected timeframe label, None = native
    st.session_state.setdefault("is_live", False)    # was the data fetched live (re-fetchable)?
    st.session_state.setdefault("live_args", None)   # fetch args, so the TF selector can re-fetch
    st.session_state.setdefault("source", "")
    st.session_state.setdefault("result", None)
    st.session_state.setdefault("backtest", None)
    st.session_state.setdefault("validation", None)
    st.session_state.setdefault("worked", None)
    st.session_state.setdefault("ss_result", None)   # screenshot-analysis result
    # Live Center state
    st.session_state.setdefault("lc_assets", ["XAUUSD", "BTCUSD", "ETHUSD",
                                              "EURUSD", "GBPUSD", "USDJPY"])
    st.session_state.setdefault("lc_quotes", None)   # last fetched quote rows
    st.session_state.setdefault("lc_updated", "")    # last update timestamp
    st.session_state.setdefault("mt5_connected", False)
    st.session_state.setdefault("mt5_account", {})
    # Telegram Signal Center state (token kept in memory ONLY, never persisted)
    st.session_state.setdefault("tg_token", "")
    st.session_state.setdefault("tg_chat_id", "")
    st.session_state.setdefault("tg_username", "")
    st.session_state.setdefault("tg_bot_username", "")
    st.session_state.setdefault("tg_status", "Not Connected")   # Connected / Not Connected / Testing
    st.session_state.setdefault("tg_auto", True)
    st.session_state.setdefault("tg_side", "Both")              # Both / BUY only / SELL only
    st.session_state.setdefault("tg_conf", "All confirmed")     # band: All / Medium+high / High-only
    st.session_state.setdefault("tg_min_rr", 0.0)               # minimum R/R (TP1) to alert
    st.session_state.setdefault("tg_min_conf", 0)               # minimum confidence % to alert
    st.session_state.setdefault("tg_require_htf", False)        # require higher-timeframe alignment
    st.session_state.setdefault("tg_require_vol", False)        # require volume confirmation
    st.session_state.setdefault("tg_valid_bars", 12)            # signal validity window (bars)
    st.session_state.setdefault("tg_last_sig", "")              # dedupe last auto-SENT setup
    st.session_state.setdefault("tg_last_eval_sig", "")         # dedupe last EVALUATED setup (logging)
    st.session_state.setdefault("tg_log", [])                   # recent send log (newest first)
    st.session_state.setdefault("tg_trades", [])                # open trades being monitored
    st.session_state.setdefault("tg_last_health", 0.0)          # last health-check epoch


_init_state()


# =============================================================================
# Data-loading helpers
# =============================================================================
def _set_data(df: pd.DataFrame, source: str, is_live: bool = False, live_args=None):
    norm = normalize_ohlc(df)
    st.session_state.df = norm
    st.session_state.df_base = norm          # the as-loaded base for up-aggregation
    st.session_state.tf_active = None        # show native timeframe on a fresh load
    st.session_state.is_live = bool(is_live)
    st.session_state.live_args = dict(live_args) if live_args else None
    st.session_state.source = source
    st.session_state.result = None
    st.session_state.backtest = None
    st.session_state.validation = None
    st.session_state.worked = None


# ---- timeframe selector plumbing (multi-timeframe; recomputes everything) ----
# TIMEFRAMES labels (1M = 1 minute … 1W = 1 week) -> source-native intervals.
_BINANCE_TF = {"1M": "1m", "5M": "5m", "15M": "15m", "30M": "30m",
               "1H": "1h", "4H": "4h", "1D": "1d", "1W": "1w"}
_YAHOO_TF = {"1M": "1m", "5M": "5m", "15M": "15m", "30M": "30m", "1H": "1h",
             "1D": "1d", "1W": "1wk"}   # 4H built by resampling 1h; ranges auto-clamped
# Yahoo only serves intraday over short ranges (else HTTP 422). Cap the range to
# each interval's limit IN THE APP so a timeframe switch works regardless of the
# live_data module state. All values below are accepted by Yahoo's chart endpoint.
_YF_SAFE_RANGE = {"1m": "5d", "5m": "1mo", "15m": "1mo", "30m": "1mo",
                  "1h": "2y", "1d": "5y", "1wk": "max"}


def _interval_to_tf(interval: str) -> str:
    """Best-guess TIMEFRAMES label for a live source interval (for highlighting)."""
    rev = {v: k for k, v in _BINANCE_TF.items()}
    rev.update({"1wk": "1W", "1mo": "1W"})
    return rev.get(str(interval).lower(), "")


def _live_timeframe_availability(live_args) -> dict:
    """Per-TF (enabled, reason) for the active live source."""
    market = (live_args or {}).get("market", "")
    out = {}
    for tf in fe.TIMEFRAMES:
        if market.startswith("Crypto"):
            out[tf] = (True, "")                      # Binance serves all eight
        else:
            ok = tf in _YAHOO_TF or tf == "4H"        # 4H via 1h resample
            out[tf] = (ok, "" if ok else "Yahoo does not serve 1-minute reliably.")
    return out


def _apply_timeframe(tf: str):
    """Switch the analysed timeframe: re-fetch (live) or aggregate up (static)."""
    if st.session_state.is_live and _LIVE_IMPORTED and st.session_state.live_args:
        args = dict(st.session_state.live_args)
        market = args.get("market", "")
        if market.startswith("Crypto"):
            iv = _BINANCE_TF.get(tf)
            if not iv:
                return
            args["interval"] = iv
            raw = live_data.fetch_live(**args)
            new_df = normalize_ohlc(raw)
        else:
            if tf == "4H":                            # Yahoo has no 4h -> 1h then aggregate
                a = dict(args); a["interval"] = "1h"; a["range_"] = "2y"
                raw = live_data.fetch_live(**a)
                new_df = fe.resample_ohlc(raw, "4H")
                args["interval"] = "1h"; args["range_"] = "2y"
            else:
                iv = _YAHOO_TF.get(tf)
                if not iv:
                    return
                args["interval"] = iv
                # cap range to the interval's Yahoo limit (prevents HTTP 422)
                args["range_"] = _YF_SAFE_RANGE.get(iv, args.get("range_", "1y"))
                raw = live_data.fetch_live(**args)
                new_df = normalize_ohlc(raw)
        st.session_state.df_base = new_df
        st.session_state.df = new_df
        st.session_state.live_args = args
    else:
        # static data: aggregate UP from the as-loaded base (never fabricate finer)
        st.session_state.df = fe.resample_ohlc(st.session_state.df_base, tf)
    st.session_state.tf_active = tf
    st.session_state.result = None
    st.session_state.backtest = None
    st.session_state.validation = None
    st.session_state.worked = None


# ---- Telegram Signal Center plumbing ----------------------------------------
def _current_tf_label() -> str:
    """The timeframe label currently driving the analysis (for the signal)."""
    if st.session_state.is_live:
        return (st.session_state.tf_active
                or _interval_to_tf((st.session_state.live_args or {}).get("interval", ""))
                or "—")
    base = st.session_state.df_base
    return (st.session_state.tf_active
            or (fe.native_timeframe(base) if base is not None else None) or "—")
#nkjnsdakjfnkdsafna

def _tg_log(text: str, ok: bool, **fields):
    entry = {"time": datetime.now().strftime("%H:%M:%S"), "ok": bool(ok), "text": text}
    entry.update(fields)
    st.session_state.tg_log = ([entry] + st.session_state.tg_log)[:30]


def _tg_log_signal(res, tf: str, kind: str, out: dict):
    """Structured log row for a sent/attempted alert (dashboard §11)."""
    sg = res.signal
    _tg_log(f"{kind} {sg.action} {res.asset} {tf}", out.get("ok", False),
            asset=res.asset, timeframe=tf, signal=sg.action,
            entry=f"{sg.entry:.6g}", sl=(f"{sg.stop_loss:.6g}" if sg.stop_loss else "—"),
            tps=", ".join(f"{t:.6g}" for t in (sg.take_profits or [])) or "—",
            status=("sent" if out.get("ok") else "failed"),
            error=("" if out.get("ok") else str(out.get("error", ""))))


def _tg_mask(token: str) -> str:
    """Masked token for display — only the last 4 chars are shown."""
    t = token or ""
    return ("•" * 8 + t[-4:]) if len(t) >= 4 else "••••••••"


def _fmt_signal(res, tf: str) -> str:
    """
    Build the alert text, tolerant of a stale in-memory `telegram_signals` whose
    `format_signal` predates the `session` (or `narrative`/`valid_bars`) keyword —
    so a hot-reload that didn't refresh the module degrades gracefully instead of
    crashing. A full server restart restores the complete message.
    """
    nar = fe.signal_narrative(res)
    sess = fsessions.telegram_session() if _SESS_IMPORTED else None
    vb = int(st.session_state.tg_valid_bars)
    labels = i18n.alert_labels(st.session_state.get("lang", "en"))
    for kwargs in (dict(narrative=nar, valid_bars=vb, session=sess, labels=labels),
                   dict(narrative=nar, valid_bars=vb, session=sess),
                   dict(narrative=nar, valid_bars=vb),
                   dict(narrative=nar),
                   {}):
        try:
            return tg.format_signal(res.asset, tf, res, **kwargs)
        except TypeError:
            continue
    return tg.format_signal(res.asset, tf, res)      # last resort


def _tg_plaintext(html_msg: str) -> str:
    """Strip HTML tags so the message preview reads cleanly on screen."""
    import re
    return re.sub(r"<[^>]+>", "", html_msg)


def _tg_validate_signal(res) -> tuple:
    """
    Final validation layer (requirement #9) BEFORE any Telegram send. Returns
    (ok, reasons). `reasons` explains the decision either way, for the log (#10).
    Checks: confirmed BUY/SELL · valid numeric entry/SL/TP · SL & TP on the
    correct side · positive R/R · confidence ≥ threshold · direction agrees with
    trend · structure confirmed · last candle confirms (no strong opposite close).
    """
    import math
    sg = getattr(res, "signal", None)
    if sg is None or sg.action not in ("BUY", "SELL"):
        return False, ["no confirmed BUY/SELL set-up (WAIT)"]
    d = 1 if sg.action == "BUY" else -1
    nums = [sg.entry, sg.stop_loss] + list(sg.take_profits or [])
    if (not sg.take_profits) or any(
            v is None or not isinstance(v, (int, float)) or not math.isfinite(float(v))
            for v in nums):
        return False, ["entry / stop-loss / take-profit missing or non-numeric"]
    if (d == 1 and not sg.stop_loss < sg.entry) or (d == -1 and not sg.stop_loss > sg.entry):
        return False, ["stop-loss is on the wrong side of entry"]
    if any((d == 1 and tp <= sg.entry) or (d == -1 and tp >= sg.entry) for tp in sg.take_profits):
        return False, ["a take-profit is on the wrong side of entry"]
    rr = sg.rr[0] if getattr(sg, "rr", None) else 0.0
    if rr <= 0:
        return False, ["non-positive risk/reward"]
    thr = float(st.session_state.tg_min_conf) / 100.0
    if sg.confidence_score < thr:
        return False, [f"confidence {sg.confidence_score:.0%} below minimum {st.session_state.tg_min_conf}%"]
    if sg.action == "BUY" and res.trend == "DOWNTREND":
        return False, ["BUY conflicts with a DOWNTREND"]
    if sg.action == "SELL" and res.trend == "UPTREND":
        return False, ["SELL conflicts with an UPTREND"]
    sc = res.struct_conf or {}
    if sg.action == "BUY" and not (res.trend == "UPTREND" or sc.get("bull")):
        return False, ["bullish market structure not confirmed"]
    if sg.action == "SELL" and not (res.trend == "DOWNTREND" or sc.get("bear")):
        return False, ["bearish market structure not confirmed"]
    # candle confirmation: the last closed candle must not be a strong opposite candle
    df = st.session_state.df
    if df is not None and len(df) >= 1:
        b = df.iloc[-1]
        o, h, l, c = float(b["open"]), float(b["high"]), float(b["low"]), float(b["close"])
        rng = (h - l) or 1e-9
        confirm = ((c >= o) or ((c - l) / rng >= 0.5)) if d == 1 \
            else ((c <= o) or ((h - c) / rng >= 0.5))
        if not confirm:
            return False, ["last candle does not confirm the direction"]
    return True, [f"{sg.action} confirmed", f"R/R 1:{rr:.2f}",
                  f"confidence {sg.confidence_score:.0%}",
                  "structure " + ("bullish" if d == 1 else "bearish"), "candle confirms"]


def _tg_auto_send(res):
    """
    Send a confirmed, VALIDATED BUY/SELL once. Order: confirmed set-up → final
    validation (#9) → user filters → de-dup → send. Every decision is logged (#10).
    Telegram always uses the SAME res.signal the app shows, so BUY≠SELL mismatch
    is impossible (#4–#6).
    """
    if not (_TG_IMPORTED and st.session_state.tg_status == "Connected"
            and st.session_state.tg_auto):
        return
    sg = getattr(res, "signal", None)
    tf = _current_tf_label()
    sig = tg.signal_signature(res.asset, tf, res)
    if sig and sig == st.session_state.get("tg_last_eval_sig"):
        return                              # evaluate/log each unique set-up once
    st.session_state.tg_last_eval_sig = sig
    if sg is None or sg.action not in ("BUY", "SELL"):
        return                              # WAIT → send nothing (#7)
    ok, reasons = _tg_validate_signal(res)
    if not ok:
        _tg_log(f"REJECTED {sg.action} {res.asset} {tf}: " + "; ".join(reasons), False,
                asset=res.asset, timeframe=tf, signal=sg.action, status="rejected",
                error="; ".join(reasons))
        return
    if not _tg_signal_passes(res, sg):
        _tg_log(f"FILTERED {sg.action} {res.asset} {tf} (user alert filters)", False,
                asset=res.asset, timeframe=tf, signal=sg.action, status="filtered",
                error="below your direction/confidence/RR/HTF/volume filters")
        return
    if sig == st.session_state.tg_last_sig:
        return                              # this set-up already delivered
    msg = _fmt_signal(res, tf)
    out = tg.send_message(st.session_state.tg_token, st.session_state.tg_chat_id, msg)
    st.session_state.tg_last_sig = sig
    _tg_log(f"SENT {sg.action} {res.asset} {tf}: " + "; ".join(reasons),
            out.get("ok", False), asset=res.asset, timeframe=tf, signal=sg.action,
            entry=f"{sg.entry:.6g}", sl=(f"{sg.stop_loss:.6g}" if sg.stop_loss else "—"),
            tps=", ".join(f"{t:.6g}" for t in (sg.take_profits or [])),
            status=("sent" if out.get("ok") else "failed"),
            error=("" if out.get("ok") else str(out.get("error", ""))))
    if out.get("ok"):
        _tg_register_trade(res, tf)         # begin lifecycle monitoring


def _tg_register_trade(res, tf: str):
    """Begin tracking a sent signal so TP/SL milestones can be reported."""
    sg = res.signal
    if sg.action not in ("BUY", "SELL") or sg.stop_loss is None:
        return
    sig = tg.signal_signature(res.asset, tf, res)
    if any(t.get("sig") == sig for t in st.session_state.tg_trades):
        return
    st.session_state.tg_trades.append({
        "sig": sig, "asset": res.asset, "timeframe": tf, "action": sg.action,
        "dir": 1 if sg.action == "BUY" else -1, "entry": float(sg.entry),
        "sl": float(sg.stop_loss), "tps": [float(t) for t in (sg.take_profits or [])][:3],
        "hit": [], "status": "open",
    })


def _tg_send_lifecycle(event: str, trade: dict, level: float):
    out = tg.send_message(
        st.session_state.tg_token, st.session_state.tg_chat_id,
        tg.lifecycle_message(event, trade["asset"], trade["timeframe"], level,
                             trade["entry"], trade["action"]))
    _tg_log(f"{event} {trade['asset']} {trade['timeframe']}", out.get("ok", False),
            asset=trade["asset"], timeframe=trade["timeframe"], signal=event,
            status=("sent" if out.get("ok") else "failed"),
            error=("" if out.get("ok") else str(out.get("error", ""))))


def _tg_monitor_trades():
    """Check open trades against the latest bar and push TP/SL lifecycle updates."""
    if not (_TG_IMPORTED and st.session_state.tg_status == "Connected"):
        return
    df = st.session_state.df
    if df is None or len(df) == 0 or not st.session_state.tg_trades:
        return
    bar = df.iloc[-1]
    hi, lo = float(bar["high"]), float(bar["low"])
    for t in st.session_state.tg_trades:
        if t.get("status") != "open":
            continue
        d = t["dir"]
        # stop-loss first (conservative)
        if t["sl"] is not None and "SL" not in t["hit"] and \
           ((d == 1 and lo <= t["sl"]) or (d == -1 and hi >= t["sl"])):
            _tg_send_lifecycle("SL", t, t["sl"])
            t["hit"].append("SL"); t["status"] = "closed"
            continue
        for i, tp in enumerate(t["tps"]):
            key = ["TP1", "TP2", "TP3"][i]
            if key in t["hit"]:
                continue
            if (d == 1 and hi >= tp) or (d == -1 and lo <= tp):
                _tg_send_lifecycle(key, t, tp)
                t["hit"].append(key)
                if i == len(t["tps"]) - 1 or key == "TP3":
                    t["status"] = "closed"


def _tg_health_check():
    """Re-validate the connection at most every 2 minutes; keep status accurate."""
    import time
    if not (_TG_IMPORTED and st.session_state.tg_token):
        return
    now = time.time()
    if now - float(st.session_state.tg_last_health) < 120:
        return
    st.session_state.tg_last_health = now
    v = tg.validate_token(st.session_state.tg_token)
    if v.get("ok"):
        st.session_state.tg_status = "Connected"
    else:
        st.session_state.tg_status = "Reconnecting"
        v2 = tg.validate_token(st.session_state.tg_token)   # one auto-reconnect attempt
        st.session_state.tg_status = "Connected" if v2.get("ok") else "Error"


def _tg_signal_passes(res, sg) -> bool:
    """Apply all configured Telegram alert filters to a confirmed signal."""
    htf = getattr(res, "htf", {}) or {}
    htf_aligned = ((sg.action == "BUY" and htf.get("aligned_bull")) or
                   (sg.action == "SELL" and htf.get("aligned_bear")))
    vol_ok = bool((getattr(res, "volume_conf", {}) or {}).get("confirms"))
    rr0 = sg.rr[0] if getattr(sg, "rr", None) else None
    try:
        return tg.passes_filter(
            sg.action, sg.confidence_score, rr=rr0,
            side=st.session_state.tg_side, confidence=st.session_state.tg_conf,
            min_rr=float(st.session_state.tg_min_rr),
            min_confidence=float(st.session_state.tg_min_conf) / 100.0,
            htf_aligned=htf_aligned, require_htf=bool(st.session_state.tg_require_htf),
            volume_ok=vol_ok, require_volume=bool(st.session_state.tg_require_vol))
    except TypeError:
        # stale in-memory telegram_signals (older passes_filter signature) — fall
        # back to the basic direction/confidence filter so nothing crashes.
        return tg.passes_filter(sg.action, sg.confidence_score,
                                side=st.session_state.tg_side,
                                confidence=st.session_state.tg_conf)


def _seed_manual_frame(n: int = 8) -> pd.DataFrame:
    base = 4550.0
    rows = []
    for i in range(n):
        o = base + i * 6
        c = o + (8 if i % 2 == 0 else -5)
        h = max(o, c) + 6
        l = min(o, c) - 6
        rows.append({"time": f"2026-01-{i+1:02d}", "open": o, "high": h, "low": l, "close": c, "volume": 1000 + i * 50})
    return pd.DataFrame(rows)


def _synthetic_sample(asset: str = "XAUUSD") -> pd.DataFrame:
    return fe._demo_frame(n=200, seed=11)


# =============================================================================
# Charting
# =============================================================================
def build_chart(df: pd.DataFrame, res: "fe.FUTASResult", chart_type: str = "Candlestick",
                show_classical: bool = False, price_action_mode: bool = False) -> go.Figure:
    """
    Price-action-first chart. The candles own the vertical space (the Y-axis is
    framed to the candle range + the active trade levels, NOT the far Fibonacci
    Urvin extensions, which would otherwise squash the candles). FU levels are
    drawn BELOW the candles so price action is never covered.
    """
    fig = go.Figure()
    x = df["time"]
    o = df["open"].astype(float); h = df["high"].astype(float)
    lo_ = df["low"].astype(float); c = df["close"].astype(float)
    vol = df["volume"].astype(float) if "volume" in df.columns else pd.Series([0.0] * len(df))

    up_col, dn_col = "#00c853", "#ff1744"          # bright green / bright red
    cw = 2.2 if price_action_mode else 1.5
    if chart_type == "Candlestick":
        fig.add_trace(go.Candlestick(
            x=x, open=o, high=h, low=lo_, close=c, name="Price",
            increasing=dict(line=dict(color=up_col, width=cw), fillcolor=up_col),
            decreasing=dict(line=dict(color=dn_col, width=cw), fillcolor=dn_col),
            whiskerwidth=0.5, hoverinfo="skip"))
    else:
        fig.add_trace(go.Scatter(x=x, y=c, mode="lines", name="Close",
                                 line=dict(color="#1565c0", width=1.9), hoverinfo="skip"))

    # rich per-candle hover (Date/O/H/L/C/Volume/Range/Status) via invisible overlay
    status = ["Bullish ▲" if cc >= oo else "Bearish ▼" for oo, cc in zip(o, c)]
    cd = np.column_stack([o, h, lo_, c, vol, (h - lo_)]).astype(float)
    fig.add_trace(go.Scatter(
        x=x, y=c, mode="markers", name="", showlegend=False,
        marker=dict(size=6, opacity=0), customdata=cd, text=status,
        hovertemplate=("<b>%{x}</b><br>"
                       "Open %{customdata[0]:.4f}   High %{customdata[1]:.4f}<br>"
                       "Low %{customdata[2]:.4f}   Close %{customdata[3]:.4f}<br>"
                       "Volume %{customdata[4]:,.0f}   Range %{customdata[5]:.4f}<br>"
                       "<b>%{text}</b><extra></extra>")))

    # ---- frame the Y-axis to the CANDLES (+ active trade levels) --------------
    sg = res.signal
    extra = []
    if sg.action in ("BUY", "SELL"):
        extra = [sg.entry] + ([sg.stop_loss] if sg.stop_loss is not None else []) \
            + list(sg.take_profits)
    y_lo = min([float(lo_.min())] + [float(v) for v in extra])
    y_hi = max([float(h.max())] + [float(v) for v in extra])
    pad = (y_hi - y_lo) * (0.06 if price_action_mode else 0.10) or 1.0
    y_range = [y_lo - pad, y_hi + pad]

    # ---- OPTIONAL classical-Fibonacci overlay (comparison ONLY, below candles) -
    if show_classical:
        rng = res.high - res.low
        for r in [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0, 1.272, 1.618]:
            yv = res.low + rng * r
            if y_range[0] <= yv <= y_range[1]:
                fig.add_hline(y=yv, line=dict(color="#9e9e9e", width=0.8, dash="dashdot"),
                              layer="below", annotation_text=f"fib {r:.3f}",
                              annotation_position="left", annotation_font_size=8,
                              annotation_font_color="#9e9e9e")

    # ---- Fibonacci Urvin levels: BELOW the candles; fainter in price-action mode
    band_a = 0.018 if price_action_mode else 0.055
    line_w = (0.8 if price_action_mode else 1.2)
    for L in res.levels:
        if not (y_range[0] <= L.price <= y_range[1]):
            continue                                # off-screen levels add no value
        if L.zone == "inside":
            color, dash = "#2962ff", "solid"
            fill = f"rgba(41,98,255,{band_a})"
        elif L.zone == "extension_up":
            color, dash = "#00897b", "dash"
            fill = f"rgba(0,137,123,{band_a})"
        else:
            color, dash = "#8e24aa", "dash"
            fill = f"rgba(142,36,170,{band_a})"
        w = (line_w + 0.7) if L.k in (0.0, 0.5, 1.0) else line_w
        if L.zone_high > L.zone_low:
            fig.add_hrect(y0=L.zone_low, y1=L.zone_high, line_width=0,
                          fillcolor=fill, layer="below")
        fig.add_hline(
            y=L.price, layer="below",
            line=dict(color=color, width=w, dash=dash),
            annotation_text=f"FU {L.k:g} ({L.percent:.0f}%) = {L.price:.4f}",
            annotation_position="right", annotation_font_size=9,
            annotation_font_color=color,
            opacity=(0.45 if price_action_mode else 0.9))

    # ---- entry / SL / TP markers (kept above bands, within frame) -------------
    if sg.action in ("BUY", "SELL"):
        fig.add_hline(y=sg.entry, line=dict(color="#111", width=1.6),
                      annotation_text=f"ENTRY {sg.entry:.4f}", annotation_position="left",
                      annotation_font_color="#111", annotation_font_size=10)
        if sg.stop_loss is not None:
            fig.add_hline(y=sg.stop_loss, line=dict(color="#b71c1c", width=1.8),
                          annotation_text=f"SL {sg.stop_loss:.4f}", annotation_position="left",
                          annotation_font_color="#b71c1c", annotation_font_size=10)
        for i, tp in enumerate(sg.take_profits):
            fig.add_hline(y=tp, line=dict(color="#1b5e20", width=1.5, dash="dot"),
                          annotation_text=f"TP{i+1} {tp:.4f}", annotation_position="left",
                          annotation_font_color="#1b5e20", annotation_font_size=10)

    # ---- swing markers + HH/HL/LH/LL structure labels (offset, no overlap) ----
    sh = [s for s in res.swings if s.kind == "high"]
    sl = [s for s in res.swings if s.kind == "low"]
    if sh:
        fig.add_trace(go.Scatter(x=[s.time for s in sh], y=[s.price for s in sh],
                                 mode="markers", name="Swing High", hoverinfo="skip",
                                 marker=dict(color="#c62828", size=8, symbol="triangle-down")))
    if sl:
        fig.add_trace(go.Scatter(x=[s.time for s in sl], y=[s.price for s in sl],
                                 mode="markers", name="Swing Low", hoverinfo="skip",
                                 marker=dict(color="#2e7d32", size=8, symbol="triangle-up")))
    _min_gap = max(1, len(df) // 28)        # thin labels so they never crowd
    _last_idx = -10 ** 9
    for e in res.structure[-16:]:
        if e.label not in ("HH", "HL", "LH", "LL"):
            continue
        if not (y_range[0] <= e.price <= y_range[1]):
            continue
        if getattr(e, "index", 0) - _last_idx < _min_gap:
            continue                         # too close to the previous label — skip
        _last_idx = getattr(e, "index", 0)
        above = e.label in ("HH", "LH")
        col = "#1b5e20" if e.label in ("HH", "HL") else "#b71c1c"
        fig.add_annotation(x=e.time, y=e.price, text=f"<b>{e.label}</b>",
                           showarrow=False, yshift=(15 if above else -15),
                           font=dict(size=(12 if price_action_mode else 10), color=col),
                           bgcolor="rgba(255,255,255,0.7)")

    fig.update_layout(
        height=(720 if price_action_mode else 640),
        margin=dict(l=10, r=170, t=30, b=10),
        xaxis_rangeslider_visible=False, legend=dict(orientation="h", y=1.04),
        template="plotly_white", hovermode="x unified",
        dragmode="pan",
    )
    fig.update_yaxes(range=y_range, fixedrange=False)
    return fig


def equity_chart(bt: dict) -> go.Figure:
    ec = pd.DataFrame(bt["equity_curve"])
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=ec["index"], y=ec["balance"], mode="lines",
                             name="Balance", line=dict(color="#1565c0", width=2)))
    fig.add_hline(y=bt["initial_balance"], line=dict(color="#999", dash="dot"),
                  annotation_text="Start")
    fig.update_layout(height=340, template="plotly_white",
                      margin=dict(l=10, r=10, t=30, b=10),
                      xaxis_title="Bar index", yaxis_title="Balance")
    return fig


def worked_chart(df: pd.DataFrame, wt: "fe.WorkedTrade") -> go.Figure:
    """Visualise one reconstructed entry→exit trade over the price series."""
    x = df["time"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=df["close"], mode="lines", name="Close",
                             line=dict(color="#455a64", width=1.4)))
    # shade the holding period
    try:
        x0 = df["time"].iloc[wt.entry_index]
        x1 = df["time"].iloc[wt.exit_index]
        fig.add_vrect(x0=x0, x1=x1, line_width=0,
                      fillcolor="rgba(21,101,192,0.07)", layer="below")
    except Exception:
        pass
    up = wt.direction == 1
    # Stop-Loss and TP1 reference lines (FU levels)
    fig.add_hline(y=wt.stop_loss, line=dict(color="#b71c1c", width=1.4, dash="dot"),
                  annotation_text=f"SL {wt.stop_loss:.4f}", annotation_position="right",
                  annotation_font_size=9, annotation_font_color="#b71c1c")
    if wt.take_profits:
        fig.add_hline(y=wt.take_profits[0], line=dict(color="#1b5e20", width=1.4, dash="dot"),
                      annotation_text=f"TP1 {wt.take_profits[0]:.4f}", annotation_position="right",
                      annotation_font_size=9, annotation_font_color="#1b5e20")
    fig.add_hline(y=wt.entry_price, line=dict(color="#000", width=1.2),
                  annotation_text=f"Entry {wt.entry_price:.4f}", annotation_position="right",
                  annotation_font_size=9)
    # entry / exit markers
    fig.add_trace(go.Scatter(
        x=[df["time"].iloc[wt.entry_index]], y=[wt.entry_price], mode="markers+text",
        name="Entry", text=[wt.action], textposition="top center",
        marker=dict(color="#000", size=12, symbol="triangle-up" if up else "triangle-down")))
    exit_color = "#1b5e20" if wt.outcome == "win" else ("#b71c1c" if wt.outcome == "loss" else "#777")
    fig.add_trace(go.Scatter(
        x=[df["time"].iloc[wt.exit_index]], y=[wt.exit_price], mode="markers+text",
        name="Exit", text=[wt.exit_kind], textposition="bottom center",
        marker=dict(color=exit_color, size=12, symbol="x")))
    fig.update_layout(height=420, template="plotly_white",
                      margin=dict(l=10, r=120, t=30, b=10),
                      legend=dict(orientation="h", y=1.05),
                      xaxis_rangeslider_visible=False)
    return fig


# =============================================================================
# Export helpers
# =============================================================================
def build_excel_bytes(res: "fe.FUTASResult", bt: dict | None) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xl:
        _m = res.momentum or {}
        summary = pd.DataFrame({
            "Field": ["Asset", "Bars", "High", "Low", "Range", "Current price",
                      "Trend", "Phase (3-state)", "Structural phase (7-model)",
                      "Expected next stage", "Momentum (RSI)", "Momentum confirms",
                      "Signal", "Confidence", "Generated"],
            "Value": [res.asset, res.n_bars, res.high, res.low, res.range_size,
                      res.current_price, res.trend, res.phase,
                      res.market_phase or "—", res.market_phase_next or "—",
                      f"{_m.get('rsi', float('nan')):.1f}" if _m else "—",
                      ("bullish" if _m.get("confirms_bull") else
                       "bearish" if _m.get("confirms_bear") else "neutral"),
                      res.signal.action,
                      f"{res.signal.confidence} ({res.signal.confidence_score:.0%})",
                      datetime.now().isoformat(timespec="seconds")],
        })
        summary.to_excel(xl, sheet_name="Summary", index=False)
        res.levels_table().to_excel(xl, sheet_name="FU_Levels", index=False)
        res.signal_table().to_excel(xl, sheet_name="Signal", index=False)
        pd.DataFrame({"FU_Coefficients": FU_COEFFICIENTS}).to_excel(
            xl, sheet_name="Coefficients", index=False)
        if bt and bt["trades"]:
            pd.DataFrame(bt["trades"]).to_excel(xl, sheet_name="Backtest_Trades", index=False)
            pd.DataFrame([bt["stats"]]).T.rename(columns={0: "Value"}).to_excel(
                xl, sheet_name="Backtest_Stats")
            sf = bt.get("sfvt")
            if sf:
                sf_flat = {k: v for k, v in sf.items() if k != "reference"}
                pd.DataFrame([sf_flat]).T.rename(columns={0: "Value"}).to_excel(
                    xl, sheet_name="SFVT_Metrics")
    return buf.getvalue()


def build_text_report(res: "fe.FUTASResult", bt: dict | None) -> str:
    out = []
    out.append("FUTAS — Fibonacci Urvin Adaptive Trading Analysis System")
    out.append("Scientific technical report")
    out.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    out.append("=" * 70)
    out.append("")
    out.append("FIBONACCI URVIN COEFFICIENTS (15):")
    out.append("  " + ", ".join(str(k) for k in FU_COEFFICIENTS))
    out.append("  Formula:  P = Low + (High - Low) * K")
    out.append("")
    out.append(res.levels_table().to_string(index=False))
    out.append("")
    out.append(res.explanation)
    if bt:
        out.append("")
        out.append("BACKTEST SUMMARY")
        out.append("-" * 70)
        for k, v in bt["stats"].items():
            out.append(f"  {k:16s}: {v}")
        sf = bt.get("sfvt")
        if sf:
            out.append("")
            out.append("SFVT STRUCTURAL VALIDATION METRICS (dissertation §3.1)")
            out.append("-" * 70)
            out.append(f"  CSR (continuation success) : {sf['CSR']:.1f}%")
            out.append(f"  FSF (false-signal freq.)   : {sf['FSF']:.1f}%")
            out.append(f"  NEU (indecisive/timeout)   : {sf.get('NEU', 0.0):.1f}%")
            out.append(f"  SPR (structural persistence): {sf['SPR']:.1f}%")
            out.append(f"  RSI/MA baseline CSR         : {sf['baseline_csr']:.1f}%")
            out.append(f"  Delta (CSR - baseline)      : {sf['delta']:+.1f} pts")
    return "\n".join(out)


def build_validation_report(asset: str, bt: dict | None, val: dict | None) -> str:
    """Tier-1 exportable validation report: stats + SFVT + benchmark + significance."""
    L: list[str] = []
    L.append("=" * 72)
    L.append("FUTAS — TIER 1 VALIDATION REPORT")
    L.append(f"Asset: {asset}")
    L.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    L.append("Method: Fibonacci Urvin adaptive coefficients · P = Low + (High-Low)*K")
    L.append("Note: scientific research tool — not financial advice.")
    L.append("=" * 72)
    if bt:
        s, sf = bt["stats"], bt.get("sfvt", {})
        L.append("\n[1] BACKTEST (walk-forward, no look-ahead)")
        L.append(f"  TP management : {bt.get('tp_management','single')}")
        L.append(f"  Round-trip cost: {bt.get('cost_bps_total',0):.1f} bps")
        for key in ("total_trades", "wins", "losses", "neutrals", "win_rate",
                    "profit_factor", "net_profit", "max_drawdown", "sharpe", "expectancy"):
            if key in s:
                L.append(f"  {key:14s}: {s[key]}")
        if sf:
            L.append("\n[2] SFVT STRUCTURAL VALIDATION (dissertation §3.1)")
            L.append(f"  CSR {sf['CSR']:.1f}%  FSF {sf['FSF']:.1f}%  "
                     f"NEU {sf.get('NEU',0):.1f}%  SPR {sf['SPR']:.1f}%")
            L.append(f"  Δ vs RSI/MA baseline ({sf['baseline_csr']:.1f}%): {sf['delta']:+.1f} pts")
    if val:
        bm = val.get("benchmark")
        if bm:
            L.append("\n[3] FUTAS vs CLASSICAL FIBONACCI vs BUY-AND-HOLD")
            f, c = bm["futas"], bm["classical_fib"]
            L.append(f"  FUTAS      : net {f['net_pct']:+.2f}%  win {f['win_rate']:.1f}%  "
                     f"PF {f['profit_factor']}  CSR {f['CSR']:.1f}%  ({f['trades']} trades)")
            L.append(f"  Classical  : net {c['net_pct']:+.2f}%  win {c['win_rate']:.1f}%  "
                     f"PF {c['profit_factor']}  CSR {c['CSR']:.1f}%  ({c['trades']} trades)")
            L.append(f"  Buy & hold : {bm['buy_hold_pct']:+.2f}%")
        mc = val.get("mc")
        if mc:
            L.append("\n[4] MONTE-CARLO PERMUTATION TEST")
            L.append(f"  metric={mc['metric']}  real={mc['real']}  "
                     f"random mean={mc['random_mean']}±{mc['random_std']}")
            L.append(f"  p-value={mc['p_value']}  ({mc['n_iter']} permutations)  "
                     f"-> {'SIGNIFICANT' if mc['significant'] else 'not significant'} at 5%")
        bs = val.get("bootstrap")
        if bs and not bs.get("insufficient"):
            L.append("\n[5] BOOTSTRAP CONFIDENCE INTERVALS (95%)")
            L.append(f"  win-rate  : {bs['win_rate_ci'][0]:.1f}–{bs['win_rate_ci'][1]:.1f}%")
            L.append(f"  expectancy: {bs['expectancy_ci'][0]:.3f}–{bs['expectancy_ci'][1]:.3f} per trade")
        sens = val.get("sensitivity")
        if sens and sens.get("rows"):
            L.append("\n[6] PARAMETER SENSITIVITY (sweep " + sens["param"] + ")")
            for r in sens["rows"]:
                L.append(f"  {sens['param']}={r['value']}: {sens['metric']}={r['metric']} "
                         f"win={r['win_rate']}% trades={r['trades']} CSR={r['CSR']}")
            L.append(f"  mean {sens['metric_mean']} ± {sens['metric_std']}; "
                     f"{sens['positive_share']:.0f}% of settings profitable")
        iso = val.get("isoos")
        if iso:
            L.append("\n[7] IN-SAMPLE vs OUT-OF-SAMPLE")
            L.append(f"  in-sample    : {iso['in_sample']}")
            L.append(f"  out-of-sample: {iso['out_of_sample']}")
    L.append("\n" + "=" * 72)
    L.append("Reproducible: deterministic engine; fixed seeds for Monte-Carlo / bootstrap.")
    return "\n".join(L)


# =============================================================================
# SIDEBAR — data input & parameters
# =============================================================================
with st.sidebar:
    # Use ASCII language CODES as the widget value (with a format_func for the
    # native display name). Using the non-ASCII names ("Русский", "Oʻzbek") as
    # the value can get mangled on round-trip and reset the selection.
    _codes = i18n.CODES                       # ["en", "ru", "uz"]
    _names = {c: n for n, c in i18n.LANGUAGES.items()}
    _cur = st.session_state.get("lang", "en")
    if _cur not in _codes:
        _cur = "en"
    _lang = st.selectbox("🌐 Language / Язык / Til", _codes, index=_codes.index(_cur),
                         format_func=lambda c: _names.get(c, c), key="lang_select")
    st.session_state.lang = _lang

    def T(_k):                       # module-level helper (with-block has no own scope)
        return i18n.t(_k, _lang)

    st.markdown("### ⚙️ " + T("data_params"))

    src = st.radio(T("data_source"), ["CSV upload", "Live data fetch", "Manual input",
                                      "Synthetic sample"], index=0)
    st.caption("To analyse a *chart image*, use the **📷 Screenshot TA** tab.")

    asset = st.text_input(T("asset_symbol"), value="XAUUSD",
                          help="Free text. Presets are only labels, not data.")
    preset = st.selectbox("Asset preset (label only)",
                          ["XAUUSD (Gold)", "BTCUSD", "ETHUSD", "Custom"], index=0)

    if src == "CSV upload":
        up = st.file_uploader("OHLC CSV", type=["csv", "txt"])
        if up is not None:
            try:
                raw = pd.read_csv(up, sep=None, engine="python")
                _set_data(raw, f"CSV: {up.name}")
                st.success(f"Loaded {len(st.session_state.df)} rows.")
            except Exception as e:
                st.error(f"Could not read CSV: {e}")

    elif src == "Live data fetch":
        if not _LIVE_IMPORTED:
            st.error("live_data module not available.")
        else:
            st.caption("Fetch real candles directly. TradingView has **no official "
                       "public data API**, so FUTAS uses equivalent free sources: "
                       "**Binance** for crypto and **Yahoo Finance** for gold / FX / "
                       "stocks. CSV, image and manual input stay available too.")
            market = st.selectbox("Market / source",
                                  ["Crypto (Binance)", "Gold / FX / stocks (Yahoo)"], index=0)
            if market.startswith("Crypto"):
                presets = live_data.BINANCE_PRESETS
                pcol = st.selectbox("Symbol preset", list(presets.keys()) + ["Custom"], index=0)
                sym = (st.text_input("Binance symbol", value="BTCUSDT", key="live_sym_b")
                       if pcol == "Custom" else presets[pcol])
                fcol = st.columns(2)
                interval = fcol[0].selectbox("Interval", live_data.BINANCE_INTERVALS,
                                             index=live_data.BINANCE_INTERVALS.index("1h"))
                limit = fcol[1].number_input("Candles", 50, 1000, 400, 50)
                fetch_args = dict(market=market, symbol=sym, interval=interval, limit=int(limit))
                shown_sym = sym
            else:
                presets = live_data.YAHOO_PRESETS
                pcol = st.selectbox("Symbol preset", list(presets.keys()) + ["Custom"], index=0)
                sym = (st.text_input("Yahoo symbol", value="GC=F", key="live_sym_y",
                                     help="e.g. GC=F (gold), SI=F (silver), EURUSD=X, BTC-USD, ^GSPC")
                       if pcol == "Custom" else presets[pcol])
                fcol = st.columns(2)
                interval = fcol[0].selectbox("Interval", live_data.YAHOO_INTERVALS, index=0)
                rng = fcol[1].selectbox("History range", live_data.YAHOO_RANGES,
                                        index=live_data.YAHOO_RANGES.index("1y"))
                fetch_args = dict(market=market, symbol=sym, interval=interval, range_=rng)
                shown_sym = sym
            if st.button("⬇️ Fetch live data", type="primary"):
                with st.spinner(f"Fetching {shown_sym}…"):
                    try:
                        raw = live_data.fetch_live(**fetch_args)
                        _set_data(raw, f"Live: {shown_sym} {interval}",
                                  is_live=True, live_args=fetch_args)
                        st.success(f"Loaded {len(st.session_state.df)} candles for {shown_sym}.")
                    except Exception as e:
                        st.error(str(e))
            st.caption("⚠️ Data is for scientific back-testing/analysis only — FUTAS "
                       "does not provide financial advice and never places orders.")

    elif src == "Manual input":
        st.caption("Edit the table directly, then click **Use table**.")
        seed = st.session_state.df if st.session_state.df is not None else _seed_manual_frame()
        edited = st.data_editor(seed, num_rows="dynamic", width="stretch", key="manual_editor")
        if st.button("Use table", type="primary"):
            try:
                _set_data(pd.DataFrame(edited), "Manual input")
                st.success(f"Loaded {len(st.session_state.df)} rows.")
            except Exception as e:
                st.error(str(e))

    else:  # Synthetic sample
        if st.button("Generate synthetic sample", type="primary"):
            _set_data(_synthetic_sample(asset), "Synthetic sample")
            st.success(f"Generated {len(st.session_state.df)} rows.")

    st.markdown("---")
    st.markdown("### 🎛️ " + T("analysis_settings"))
    chart_type = st.selectbox("Chart type", ["Candlestick", "Line"], index=0)
    range_mode = st.selectbox("Range (High/Low) detection", ["auto", "full", "lookback"], index=1)
    lookback = st.number_input("Lookback bars (0 = all)", min_value=0, value=0, step=5)
    c1, c2 = st.columns(2)
    swing_left = c1.number_input("Swing left", min_value=1, value=2, step=1)
    swing_right = c2.number_input("Swing right", min_value=1, value=2, step=1)
    tol_pct = st.slider("Level tolerance (% of range)", 1, 20, 6) / 100.0
    min_rr = st.slider("Minimum Risk/Reward for a signal", 0.0, 3.0, 1.0, 0.1)
    price_override = st.text_input("Current price override (optional)", value="")

    st.markdown("---")
    st.markdown(
        '<div class="disclaimer">⚠️ ' + T("not_advice") + "</div>",
        unsafe_allow_html=True)


# =============================================================================
# HEADER
# =============================================================================
st.markdown('<p class="futas-title">📈 FUTAS — Fibonacci Urvin Adaptive Trading Analysis System</p>',
            unsafe_allow_html=True)
st.markdown('<p class="futas-sub">' + T("subtitle")
            + " &nbsp;•&nbsp; P = Low + (High − Low) × K</p>", unsafe_allow_html=True)


def _run_analysis():
    df = st.session_state.df
    cp = None
    if price_override.strip():
        try:
            cp = float(price_override.replace(",", ""))
        except ValueError:
            st.warning("Ignoring invalid current-price override.")
    st.session_state.result = analyze(
        df, asset=asset or "ASSET", current_price=cp, lookback=int(lookback),
        swing_left=int(swing_left), swing_right=int(swing_right),
        tol_pct=float(tol_pct), min_rr=float(min_rr), range_mode=range_mode,
    )


# =============================================================================
# MAIN
# =============================================================================
if st.session_state.df is None:
    st.info("⬅️ " + T("load_data_info"))
    with st.expander("📐 The scientific method (coefficients & formula)", expanded=True):
        st.write("**Fibonacci Urvin adaptive coefficients (exactly 15):**")
        st.code(", ".join(str(k) for k in FU_COEFFICIENTS), language="text")
        st.latex(r"P = \text{Low} + (\text{High} - \text{Low}) \times K")
        st.write("Every Entry / Stop-Loss / Take-Profit in FUTAS is derived **only** from these "
                 "coefficients — no pre-set or externally supplied numbers are ever used.")
    st.stop()

# data is loaded -> show preview + run
top_l, top_m, top_r = st.columns([3, 1.4, 1])
with top_l:
    st.caption(f"Source: **{st.session_state.source}** &nbsp;|&nbsp; rows: **{len(st.session_state.df)}**")
with top_m:
    _tg_emoji = {"Connected": "🟢", "Testing": "🟡", "Reconnecting": "🟠",
                 "Error": "🔴"}.get(st.session_state.tg_status, "⚪")
    st.caption(f"📡 Telegram {_tg_emoji} **{st.session_state.tg_status}** "
               "&nbsp;·&nbsp; open the **📡 Telegram** tab")
with top_r:
    run = st.button("🔬 " + T("run_analysis"), type="primary", width="stretch")

# self-heal a stale result left in session_state across a code hot-reload
# (e.g. an older FUTASResult that predates a newly-added field)
_stale = st.session_state.result is not None and not hasattr(st.session_state.result, "htf")
if run or st.session_state.result is None or _stale:
    try:
        _run_analysis()
    except Exception as e:
        st.error(f"Analysis error: {e}")
        st.stop()

res = st.session_state.result

# real-time alert: keep the connection healthy, push a newly-confirmed BUY/SELL,
# then advance any open trades' TP/SL lifecycle.
try:
    _tg_health_check()
    _tg_auto_send(res)
    _tg_monitor_trades()
except Exception:
    pass

(tab_live, tab_an, tab_sig, tab_bt, tab_wex, tab_ss, tab_tg, tab_data, tab_exp, tab_about) = st.tabs(
    ["🛰️ " + T("tab_live"), "📊 " + T("tab_analysis"), "🎯 " + T("tab_signal"),
     "🧪 " + T("tab_backtest"), "🎬 " + T("tab_worked"), "📷 " + T("tab_screenshot"),
     "📡 " + T("tab_telegram"), "🗂️ " + T("tab_data"), "📝 " + T("tab_explanation"),
     "📐 " + T("tab_science")])

# ----------------------------------------------------------- Live Center -----
with tab_live:
    st.markdown("### 🛰️ Live MT5 Center")
    _mt5_ok = _MT5_MODULE and mt5_feed.available()
    _mode = "MT5 (local terminal)" if st.session_state.mt5_connected else "Cloud feed (Binance / Yahoo)"
    hc = st.columns([2, 1, 1])
    hc[0].caption(f"Active data source: **{_mode}**  ·  auto-switches to cloud when MT5 is "
                  "unavailable. Dedicated to live market data — separate from the analysis modules.")
    if st.session_state.mt5_connected:
        hc[1].success("MT5 🟢 Connected")
    elif _mt5_ok:
        hc[1].info("MT5 available (not connected)")
    else:
        hc[2].warning("MT5 not available here")

    # ---- 🕒 World trading clocks (live) + session analysis -----------------
    if _SESS_IMPORTED:
        st.markdown("#### 🕒 World trading clocks")
        components.html(fsessions.clock_html(), height=320, scrolling=False)
        _sb = fsessions.session_brief()
        sgc = st.columns(4)
        sgc[0].metric("Active session", _sb["label"])
        sgc[1].metric("Volatility", _sb["volatility"].split("—")[0].strip())
        sgc[2].metric("Best window", "London–NY overlap")
        sgc[3].metric("Trade now?", "Recommended ✅" if _sb["recommended"] else "Selective ⚠️")
        (st.success if _sb["recommended"] else st.warning)(
            f"**{_sb['label']}** — {_sb['volatility']}. {_sb['advice']}")
        st.caption("Session impact by asset:  "
                   + "   ·   ".join(f"**{k}** — {v}" for k, v in _sb["assets"].items()))
        with st.expander("All sessions / cities (snapshot table)"):
            st.dataframe(pd.DataFrame(fsessions.city_rows()), width="stretch", hide_index=True)
        st.divider()

    # ---- optional MT5 connection (secure; local Windows only) --------------
    with st.expander("🔌 Optional: connect MetaTrader 5 (local Windows only — secure)", expanded=False):
        if not _MT5_MODULE:
            st.info("`mt5_feed` module missing.")
        elif not mt5_feed.available():
            st.info("The **MetaTrader5** package is not installed in this environment "
                    "(it is Windows-only and needs the MT5 terminal). The Live Center "
                    "runs on the cloud feeds instead. To use MT5, run FUTAS locally on "
                    "Windows with MT5 installed: `pip install MetaTrader5`.")
        else:
            st.caption("Credentials are kept in this session's memory only — never saved, "
                       "logged, or shown. Leave blank to use the terminal's current login.")
            mc = st.columns(3)
            _mlogin = mc[0].text_input("MT5 login", value="", key="mt5_login")
            _mpass = mc[1].text_input("MT5 password", type="password", value="", key="mt5_pass")
            _mserver = mc[2].text_input("MT5 server", value="", key="mt5_server")
            bc = st.columns(2)
            if bc[0].button("Connect MT5", type="primary"):
                with st.spinner("Connecting to local MT5 terminal…"):
                    r = mt5_feed.connect(login=(int(_mlogin) if _mlogin.strip().isdigit() else None),
                                         password=(_mpass or None), server=(_mserver or None))
                if r.get("ok"):
                    st.session_state.mt5_connected = True
                    st.session_state.mt5_account = r.get("account", {})
                    st.session_state.pop("mt5_pass", None)   # clear secret from state
                    st.success("MT5 connected.")
                    st.rerun()
                else:
                    st.error(r.get("error", "MT5 connection failed."))
            if st.session_state.mt5_connected and bc[1].button("Disconnect MT5"):
                mt5_feed.shutdown()
                st.session_state.mt5_connected = False
                st.session_state.mt5_account = {}
                st.rerun()
            if st.session_state.mt5_connected and st.session_state.mt5_account:
                a = st.session_state.mt5_account
                st.success(f"Account {a.get('login','—')} · {a.get('server','—')} · "
                           f"{a.get('currency','')} {a.get('balance','—')} ({a.get('company','')})")

    # ---- asset selection + refresh ----------------------------------------
    _lc_ready = (_LIVE_IMPORTED and hasattr(live_data, "LIVE_CENTER_ASSETS")
                 and hasattr(live_data, "fetch_quote"))
    if _LIVE_IMPORTED and not _lc_ready:
        st.warning("⚠️ The Live Center was updated, but Streamlit is still running the "
                   "**previous** `live_data` module (its hot-reload didn't pick up the new "
                   "code). Please **restart the server** — stop it (Ctrl+C) and run "
                   "`python -m streamlit run app_streamlit.py` again — to enable live quotes.")
    _all_assets = list(live_data.LIVE_CENTER_ASSETS.keys()) if _lc_ready else []
    sc = st.columns([3, 1, 1])
    st.session_state.lc_assets = sc[0].multiselect(
        "Watchlist", _all_assets, default=st.session_state.lc_assets or _all_assets[:6])
    _auto = sc[1].toggle("Auto-refresh 10s", value=False,
                         help="Re-fetches quotes about every 10 seconds while this tab is open.")
    _refresh = sc[2].button("🔄 Refresh now", type="primary", width="stretch")

    def _refresh_quotes():
        rows = []
        for a in st.session_state.lc_assets:
            q = None
            if st.session_state.mt5_connected and _MT5_MODULE:
                src, sym = live_data.LIVE_CENTER_ASSETS.get(a, ("yahoo", a))
                mq = mt5_feed.quote(a if src != "crypto" else sym)
                if mq.get("ok"):
                    q = {"asset": a, "source": "MT5", "last": mq["last"], "bid": mq["bid"],
                         "ask": mq["ask"], "spread": mq["spread"], "high": None, "low": None,
                         "change_pct": None, "ok": True}
            if q is None and _LIVE_IMPORTED:           # cloud fallback / primary
                q = live_data.fetch_quote(a)
            if q and q.get("ok"):
                rows.append({
                    "Asset": a, "Bid": q.get("bid"), "Ask": q.get("ask"),
                    "Spread": q.get("spread"), "Last": q.get("last"),
                    "Day Change %": (round(q["change_pct"], 2) if q.get("change_pct") is not None else None),
                    "Day High": q.get("high"), "Day Low": q.get("low"),
                    "Market": ("Open" if live_data.market_is_open(a) else "Closed"),
                    "Source": q.get("source", "—"),
                })
            else:
                rows.append({"Asset": a, "Bid": None, "Ask": None, "Spread": None,
                             "Last": None, "Day Change %": None, "Day High": None,
                             "Day Low": None, "Market": "—",
                             "Source": (q or {}).get("error", "fetch failed")})
        st.session_state.lc_quotes = rows
        st.session_state.lc_updated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if _lc_ready and (_refresh or (_auto and st.session_state.lc_quotes is None)):
        with st.spinner("Fetching live quotes…"):
            _refresh_quotes()

    if not _LIVE_IMPORTED:
        st.error("live_data module not available.")
    elif st.session_state.lc_quotes:
        st.dataframe(pd.DataFrame(st.session_state.lc_quotes), width="stretch", hide_index=True)
        st.caption(f"Last update: **{st.session_state.lc_updated}**  ·  Bid/Ask are real for "
                   "Binance crypto; Yahoo provides last/high/low/change (no order-book "
                   "bid/ask).  ·  Not financial advice.")
        # one-click: pull an asset's history into the main analysis
        ac = st.columns([2, 1, 1])
        _pick = ac[0].selectbox("Load an asset's history into the analysis",
                                st.session_state.lc_assets or _all_assets)
        _iv = ac[1].selectbox("Interval", ["1h", "4h", "1d"], index=2, key="lc_iv")
        if ac[2].button("📥 Load & analyze", width="stretch"):
            try:
                src, sym = live_data.LIVE_CENTER_ASSETS.get(_pick, ("yahoo", _pick))
                with st.spinner(f"Fetching {_pick} history…"):
                    if src == "crypto":
                        raw = live_data.fetch_binance(sym, _iv, 400)
                        fa = dict(market="Crypto (Binance)", symbol=sym, interval=_iv, limit=400)
                    else:
                        _rng = {"1h": "3mo", "4h": "1y", "1d": "5y"}.get(_iv, "1y")
                        raw = live_data.fetch_yahoo(sym, _iv if _iv != "4h" else "1h", _rng)
                        if _iv == "4h":
                            raw = fe.resample_ohlc(raw, "4H")
                        fa = dict(market="Gold / FX / stocks (Yahoo)", symbol=sym,
                                  interval=(_iv if _iv != "4h" else "1h"), range_=_rng)
                    _set_data(raw, f"Live: {_pick} {_iv}", is_live=True, live_args=fa)
                st.success(f"Loaded {len(st.session_state.df)} bars for {_pick}. Open 📊 Analysis.")
            except Exception as e:
                st.error(str(e))
    else:
        st.info("Pick a watchlist and press **Refresh now** to load live quotes.")

    if _auto:
        # lightweight client-side auto-refresh (no extra dependency)
        st.markdown("<meta http-equiv='refresh' content='10'>", unsafe_allow_html=True)

# ---------------------------------------------------------------- Analysis ---
with tab_an:
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric(T("high"), f"{res.high:.4f}")
    m2.metric(T("low"), f"{res.low:.4f}")
    m3.metric(T("range"), f"{res.range_size:.4f}")
    m4.metric(T("current"), f"{res.current_price:.4f}")
    badge = ACTION_COLORS[res.signal.action]
    m5.markdown(f'<div class="signal-badge" style="background:{badge}">{res.signal.action}</div>',
                unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)
    c1.metric(T("trend"), res.trend)
    c2.metric(T("phase"), res.phase)
    c3.metric(T("structure_bias"), res.trend_metrics.get("structure_bias", "—"))

    # confirmation read-outs (confirmation only — never gate the signal)
    p3, p4, p5 = st.columns(3)
    _m = res.momentum or {}
    _rsi = _m.get("rsi", float("nan"))
    _conf = ("bullish ✓" if _m.get("confirms_bull") else
             "bearish ✓" if _m.get("confirms_bear") else "neutral")
    p3.metric(T("momentum"),
              f"RSI {_rsi:.0f}" if isinstance(_rsi, (int, float)) and not pd.isna(_rsi) else "—",
              _conf)
    _v = res.volume_conf or {}
    p4.metric(T("volume"),
              f"×{_v.get('ratio')}" if _v.get("available") else "n/a",
              (_v.get("status", "") + (" ✓" if _v.get("confirms") else "")) if _v.get("available") else "")
    _h = res.htf or {}
    _ha = (res.signal.action == "BUY" and _h.get("aligned_bull")) or \
          (res.signal.action == "SELL" and _h.get("aligned_bear"))
    p5.metric(T("higher_tf"), f"{_h.get('timeframe','—')} {_h.get('trend','')}".strip(),
              ("aligned ✓" if _h.get("timeframe") and _ha else
               "mixed" if _h.get("timeframe") else ""))

    # ---- ⏱️ multi-timeframe selector: recomputes ALL analysis on switch ------
    if st.session_state.df_base is not None:
        if st.session_state.is_live:
            avail = _live_timeframe_availability(st.session_state.live_args)
            native_tf = None
            active_tf = (st.session_state.tf_active
                         or _interval_to_tf((st.session_state.live_args or {}).get("interval", "")))
        else:
            _items = fe.available_timeframes(st.session_state.df_base)
            avail = {it["tf"]: (it["enabled"], it["reason"]) for it in _items}
            native_tf = next((it["tf"] for it in _items if it["native"]), None)
            active_tf = st.session_state.tf_active or native_tf

        tf_cols = st.columns([1.6] + [1] * len(fe.TIMEFRAMES))
        tf_cols[0].markdown("**⏱️ Timeframe**")
        for i, tf in enumerate(fe.TIMEFRAMES):
            enabled, reason = avail.get(tf, (False, ""))
            is_active = (tf == active_tf)
            if tf_cols[i + 1].button(
                    tf, key=f"tfbtn_{tf}",
                    type=("primary" if is_active else "secondary"),
                    disabled=(not enabled and not is_active),
                    width="stretch",
                    help=(reason or ("Active timeframe" if is_active else f"Aggregate up to {tf}"))):
                try:
                    with st.spinner(f"Switching to {tf}…"):
                        _apply_timeframe(tf)
                    st.rerun()
                except Exception as e:
                    st.warning(f"Could not switch to {tf}: {e}")

        _bits = []
        if not st.session_state.is_live:
            _bits.append(f"native **{native_tf or '—'}**  ·  static data (switching aggregates upward only)")
        else:
            _bits.append("live source (switching re-fetches at that interval)")
        _htf = getattr(res, "htf", {}) or {}
        if _htf.get("timeframe"):
            _al = ("aligned ✓" if (_htf.get("aligned_bull") or _htf.get("aligned_bear"))
                   else "no clear bias")
            _bits.append(f"higher TF **{_htf['timeframe']}** {_htf.get('trend','—')} ({_al})")
        st.caption(f"Active **{active_tf or '—'}**  ·  " + "  ·  ".join(_bits)
                   + "  ·  a switch recomputes FU levels, structure, momentum and phases.")

    # ---- prominent ACTIVE TIMEFRAME banner (analysis TF + higher-TF) ---------
    _tf_now = _current_tf_label()
    _htf = res.htf or {}
    _htf_txt = (f"{_htf.get('timeframe')} {_htf.get('trend')}" if _htf.get("timeframe") else "n/a")
    _sigcol = ACTION_COLORS.get(res.signal.action, "#737373")
    st.markdown(
        f"<div style='background:#0f172a;color:#fff;border-radius:8px;padding:8px 14px;"
        f"font-size:0.95rem;margin-bottom:6px'>"
        f"⏱️ <b>{T('active_tf')}: <span style='color:#38bdf8'>{_tf_now}</span></b>"
        f" &nbsp;·&nbsp; {res.n_bars} {T('candles')} &nbsp;·&nbsp; "
        f"{T('high')} {res.high:.4f} / {T('low')} {res.low:.4f} &nbsp;·&nbsp; "
        f"{T('trend').lower()} <b>{res.trend}</b> &nbsp;·&nbsp; "
        f"{T('signal_word')} <b style='color:{_sigcol}'>{res.signal.action}</b>"
        f" &nbsp;|&nbsp; {T('htf_confirmation')}: <b style='color:#a78bfa'>{_htf_txt}</b>"
        f"</div>", unsafe_allow_html=True)
    st.caption(T("tf_note"))

    cca, ccb, ccc = st.columns(3)
    _tv = cca.toggle(
        "📈 TradingView-style chart", value=_TV_IMPORTED, disabled=not _TV_IMPORTED,
        help="Renders candles with TradingView's own Lightweight-Charts engine: crisp, "
             "high-DPI, smooth zoom/pan, crosshair OHLC. Turn off for the built-in chart.")
    _pa_mode = ccb.toggle(
        "🕯️ Price Action Priority Mode", value=True,
        help="Candles take priority: the view frames the price action (not the far FU "
             "extensions); FU levels fade behind the candles.")
    _show_classic = ccc.toggle(
        "Overlay classical Fibonacci", value=False,
        help="Standard Fibonacci ratios as thin grey lines for contrast — NEVER used in "
             "any FUTAS calculation.")

    _rendered = False
    if _tv and _TV_IMPORTED:
        try:
            _html = tv_chart.tv_chart_html(st.session_state.df, res, height=600,
                                           price_action_mode=_pa_mode)
            if _html:
                components.html(_html, height=660, scrolling=False)
                _rendered = True
        except Exception as e:
            st.warning(f"TradingView chart unavailable ({e}); using the built-in chart.")
    if not _rendered:
        st.plotly_chart(
            build_chart(st.session_state.df, res, chart_type,
                        show_classical=_show_classic, price_action_mode=_pa_mode),
            width="stretch", config={"scrollZoom": True, "displaylogo": False})
    st.caption("Candles are the primary object — the view is framed to the price action "
               "(+ entry/SL/TP). **FU** levels sit *behind* the candles; far extensions are "
               "off-frame until price approaches them. HH/HL/LH/LL mark the structure."
               + ("  ·  Classical **fib** overlay on." if _show_classic and not _rendered else ""))

    st.markdown("#### Fibonacci Urvin levels")
    st.caption("Each level is a P = Low + (High − Low) × K projection. "
               "`structural_role` is the dissertation's Table 3.2.2 meaning of the zone.")
    lv = res.levels_table().copy()
    lv["price"] = lv["price"].map(lambda v: f"{v:.5f}")
    st.dataframe(lv, width="stretch", height=560)

# ----------------------------------------------------------- Signal & Risk ---
with tab_sig:
    sg = res.signal
    st.markdown(f'<div class="signal-badge" style="background:{ACTION_COLORS[sg.action]}; '
                f'max-width:420px">{sg.action}  •  {sg.confidence} ({sg.confidence_score:.0%})</div>',
                unsafe_allow_html=True)
    st.write("")
    if sg.action in ("BUY", "SELL"):
        verb = "BUY" if sg.action == "BUY" else "SELL"
        tp_str = " &nbsp;·&nbsp; ".join(
            f"TP{i+1} <b>{tp:.4f}</b>" for i, tp in enumerate(sg.take_profits))
        st.markdown(
            f'<div style="background:#f1f8e9;border-left:5px solid '
            f'{ACTION_COLORS[sg.action]};padding:10px 14px;border-radius:6px;'
            f'font-size:1.02rem">📍 <b>{verb} now</b> at <b>{sg.entry:.4f}</b> '
            f'&nbsp;→&nbsp; {tp_str} &nbsp;|&nbsp; '
            f'🛑 Stop <b>{sg.stop_loss:.4f}</b></div>',
            unsafe_allow_html=True)
        st.write("")
        cc = st.columns(5)
        cc[0].metric("Entry", f"{sg.entry:.4f}")
        cc[1].metric("Stop Loss", f"{sg.stop_loss:.4f}")
        for i, tp in enumerate(sg.take_profits):
            cc[2 + i].metric(f"TP{i+1}", f"{tp:.4f}", f"R/R {sg.rr[i]:.2f}")
        st.markdown("##### Risk / Reward")
        rr_tbl = pd.DataFrame({
            "Target": [f"TP{i+1}" for i in range(len(sg.take_profits))],
            "Price (FU level)": [f"{tp:.5f}" for tp in sg.take_profits],
            "FU level": [t.label for t in sg.tp_levels],
            "Reward": [abs(tp - sg.entry) for tp in sg.take_profits],
            "Risk": [abs(sg.entry - sg.stop_loss)] * len(sg.take_profits),
            "R/R": [f"{r:.2f} : 1" for r in sg.rr],
        })
        st.dataframe(rr_tbl, width="stretch")
    else:
        st.info("No position: the FUTAS confluence filters (trend + structure + FU level + R/R) "
                "are not simultaneously satisfied.")
    st.markdown("##### Signal summary")
    st.dataframe(res.signal_table(), width="stretch", hide_index=True)
    st.markdown("##### Reasoning")
    for r in sg.reasons:
        st.markdown(f"- {r}")

# ------------------------------------------------------------- Backtest ------
with tab_bt:
    st.caption("Walk-forward test of the FUTAS rules over the loaded history "
               "(reproduces a MetaTrader-style strategy report).")
    bcol = st.columns(4)
    bt_window = bcol[0].number_input("Rolling window", min_value=20, value=60, step=10)
    bt_step = bcol[1].number_input("Re-evaluate every N bars", min_value=1, value=1, step=1)
    bt_balance = bcol[2].number_input("Initial balance", min_value=100.0, value=1000.0, step=100.0)
    bt_risk = bcol[3].slider("Risk per trade (%)", 0.5, 5.0, 1.0, 0.5) / 100.0
    bcol2 = st.columns(4)
    bt_maxhold = bcol2[0].number_input(
        "Holding horizon (bars, 0 = off)", min_value=0, value=24, step=2,
        help="If > 0, a trade reaching neither TP1 nor the Stop-Loss within this many "
             "bars closes as a NEUTRAL outcome — so CSR + FSF need not sum to 100% "
             "(dissertation §3.1).")
    bt_tpm = bcol2[1].selectbox(
        "TP management (Tier 2)", ["single", "scaled"], index=0,
        help="single = whole position exits at TP1. scaled = partial exits at "
             "TP1/TP2/TP3 with break-even and optional trailing.")
    bt_mc = bcol2[2].number_input(
        "Monte-Carlo iterations", min_value=0, value=100, step=25,
        help="Permutation test: re-runs the backtest on random re-orderings of the "
             "same bars. 0 = skip. Higher = more precise p-value but slower.")
    run_val = bcol2[3].checkbox(
        "Run statistical validation", value=False,
        help="Adds the Monte-Carlo significance p-value and the classical-Fibonacci / "
             "buy-and-hold benchmark. Slower (runs many backtests).")
    _scaled = (bt_tpm == "scaled")
    with st.expander("⚙️ Tier 2 — trade management & split cost model", expanded=_scaled):
        m1 = st.columns(3)
        bt_spread = m1[0].number_input("Spread (bps)", min_value=0.0, value=3.0, step=0.5)
        bt_comm = m1[1].number_input("Commission (bps)", min_value=0.0, value=1.0, step=0.5)
        bt_slip = m1[2].number_input("Slippage (bps)", min_value=0.0, value=1.0, step=0.5)
        m2 = st.columns(3)
        bt_be = m2[0].toggle("Break-even after TP1", value=True, disabled=not _scaled)
        bt_trail = m2[1].toggle("Trail to TP1 after TP2", value=False, disabled=not _scaled)
        bt_w = m2[2].text_input("TP1/TP2/TP3 exit weights", value="0.5, 0.3, 0.2",
                                disabled=not _scaled)
        st.caption(f"Round-trip cost = spread + commission + slippage = "
                   f"**{bt_spread + bt_comm + bt_slip:.1f} bps**."
                   + ("  Scaled mode takes partial profit at each TP and (optionally) "
                      "moves the stop to break-even / trails it." if _scaled else
                      "  Switch TP management to *scaled* to enable partials/break-even/trailing."))
    try:
        _w = tuple(float(x) for x in str(bt_w).replace(" ", "").split(",") if x)
        if not _w:
            _w = (0.5, 0.3, 0.2)
    except Exception:
        _w = (0.5, 0.3, 0.2)
    if st.button("Run backtest", type="primary"):
        _bt_kwargs = dict(
            window=int(bt_window), step=int(bt_step),
            tol_pct=float(tol_pct), min_rr=float(min_rr),
            initial_balance=float(bt_balance), risk_per_trade=float(bt_risk),
            max_hold=int(bt_maxhold), cost_bps=0.0,
            spread_bps=float(bt_spread), commission_bps=float(bt_comm),
            slippage_bps=float(bt_slip), tp_management=bt_tpm, tp_weights=_w,
            breakeven=bool(bt_be), trailing=bool(bt_trail))
        with st.spinner("Running walk-forward backtest…"):
            st.session_state.backtest = backtest(
                st.session_state.df, asset=asset or "ASSET", **_bt_kwargs)
        if run_val:
            with st.spinner("Running statistical validation (Monte-Carlo + benchmarks)…"):
                val = {}
                try:
                    val["benchmark"] = fe.benchmark_compare(
                        st.session_state.df, asset=asset or "ASSET", **_bt_kwargs)
                    val["sensitivity"] = fe.parameter_sensitivity(
                        st.session_state.df, asset=asset or "ASSET",
                        param="tol_pct", metric="net_profit", **_bt_kwargs)
                    val["isoos"] = fe.in_out_of_sample(
                        st.session_state.df, asset=asset or "ASSET",
                        train_frac=0.6, **_bt_kwargs)
                    if int(bt_mc) > 0:
                        val["mc"] = fe.monte_carlo_significance(
                            st.session_state.df, asset=asset or "ASSET",
                            metric="net_profit", n_iter=int(bt_mc), **_bt_kwargs)
                    if st.session_state.backtest and st.session_state.backtest.get("trades"):
                        val["bootstrap"] = fe.bootstrap_metrics(
                            st.session_state.backtest["trades"])
                except Exception as e:
                    val["error"] = str(e)
                st.session_state.validation = val
        else:
            st.session_state.validation = None
    bt = st.session_state.backtest
    if bt:
        s = bt["stats"]
        k = st.columns(6)
        k[0].metric("Trades", s["total_trades"])
        k[1].metric("Win rate", f"{s['win_rate']*100:.1f}%")
        pf = s["profit_factor"]
        k[2].metric("Profit factor", "∞" if pf == float("inf") else f"{pf:.2f}")
        k[3].metric("Net profit", f"{s['net_profit']:.2f}")
        k[4].metric("Max DD", f"{s['max_drawdown']:.2f}")
        k[5].metric("Sharpe", f"{s['sharpe']:.2f}")
        st.plotly_chart(equity_chart(bt), width="stretch")

        st.caption(f"Outcome split — **{s['wins']}** win · **{s['losses']}** loss"
                   + (f" · **{s.get('neutrals', 0)}** neutral (reached neither TP nor SL "
                      "within the holding horizon)" if s.get("neutrals") else ""))

        # ---- SFVT structural validation metrics (dissertation §3.1) ----
        sf = bt.get("sfvt")
        if sf:
            st.markdown("##### SFVT — structural validation metrics (dissertation §3.1)")
            g = st.columns(5)
            g[0].metric("CSR — continuation success", f"{sf['CSR']:.1f}%",
                        help="Share of signals that reached the target (TP before SL). Higher is better.")
            g[1].metric("FSF — false-signal frequency", f"{sf['FSF']:.1f}%",
                        help="Share of signals that failed (SL first). Lower is better.")
            g[2].metric("NEU — indecisive", f"{sf.get('NEU', 0.0):.1f}%",
                        help="Share of signals that expired at the holding horizon (neither "
                             "TP nor SL). With this third bucket, CSR + FSF need not sum to 100%.")
            g[3].metric("SPR — structural persistence", f"{sf['SPR']:.1f}%",
                        help="Share of structural transitions that kept the prevailing bias.")
            g[4].metric("Δ vs RSI/MA baseline", f"{sf['delta']:+.1f} pts",
                        help=f"CSR − naive RSI/MA momentum baseline ({sf['baseline_csr']:.1f}%). "
                             "Positive means the structural method beats raw momentum.")
            ref = sf.get("reference", {})
            if ref:
                ref_rows = [{"Source": k, **v} for k, v in ref.items()]
                cur_row = {"Source": f"This run ({bt.get('asset','ASSET')})",
                           "CSR": sf["CSR"], "FSF": sf["FSF"],
                           "SPR": sf["SPR"], "delta": sf["delta"]}
                st.caption("Dissertation reference results (for orientation — computed on the "
                           "author's XAUUSD / BTCUSD samples), shown next to this run:")
                st.dataframe(pd.DataFrame([cur_row] + ref_rows), width="stretch", hide_index=True)

        # ---- statistical validation: significance + benchmarks ----
        val = st.session_state.get("validation")
        if val:
            st.markdown("##### 🔬 Statistical validation (dissertation defence)")
            if val.get("error"):
                st.warning("Validation error: " + val["error"])
            bm = val.get("benchmark")
            if bm:
                st.caption("Head-to-head on the **same data and rules** — FUTAS (the 15 "
                           "Fibonacci Urvin coefficients) vs the textbook Fibonacci ratios "
                           "(baseline only — never used inside FUTAS):")
                rows = [{"Method": "FUTAS (15 Urvin coeffs)", **bm["futas"]},
                        {"Method": "Classical Fibonacci", **bm["classical_fib"]}]
                st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
                cc = st.columns(3)
                cc[0].metric("FUTAS net", f"{bm['futas']['net_pct']:+.2f}%")
                cc[1].metric("Classical Fib net", f"{bm['classical_fib']['net_pct']:+.2f}%")
                cc[2].metric("Buy & hold (same period)", f"{bm['buy_hold_pct']:+.2f}%")
            mc = val.get("mc")
            if mc:
                sig = "significant ✓ (p < 0.05)" if mc["significant"] else "not significant"
                st.metric(f"Monte-Carlo p-value ({mc['n_iter']} permutations)",
                          f"{mc['p_value']:.3f}", sig)
                st.caption(
                    f"Real net profit **{mc['real']:.2f}** sits at the **{mc['percentile']:.0f}th "
                    f"percentile** of random re-orderings of the same bars "
                    f"(random mean {mc['random_mean']:.2f} ± {mc['random_std']:.2f}). A low "
                    "p-value means the edge comes from market **structure**, not chance.")

            sens = val.get("sensitivity")
            if sens and sens.get("rows"):
                st.caption(
                    f"**Parameter robustness** — sweeping `{sens['param']}` "
                    f"({sens['metric']} mean {sens['metric_mean']} ± {sens['metric_std']}; "
                    f"{sens['positive_share']:.0f}% of settings profitable). Stable across a "
                    "region argues the result is not curve-fit to one setting:")
                st.dataframe(pd.DataFrame(sens["rows"]), width="stretch", hide_index=True)

            iso = val.get("isoos")
            if iso:
                st.caption("**In-sample vs out-of-sample** stability (FUTAS fits no "
                           "parameters — similar halves argue the edge is not a one-period "
                           "artefact):")
                st.dataframe(pd.DataFrame([{"Segment": "In-sample", **iso["in_sample"]},
                                           {"Segment": "Out-of-sample", **iso["out_of_sample"]}]),
                             width="stretch", hide_index=True)

            bs = val.get("bootstrap")
            if bs and not bs.get("insufficient"):
                st.caption(
                    f"**Bootstrap {int(bs['ci']*100)}% CIs** ({bs['n']} trades resampled): "
                    f"win-rate **{bs['win_rate_ci'][0]:.0f}–{bs['win_rate_ci'][1]:.0f}%**, "
                    f"expectancy **{bs['expectancy_ci'][0]:.2f}–{bs['expectancy_ci'][1]:.2f}** "
                    "per trade — how far the headline numbers could move on another draw.")

            st.download_button(
                "⬇️ Download validation report (.txt)",
                build_validation_report(bt.get("asset", asset or "ASSET"), bt, val).encode("utf-8"),
                file_name=f"{asset or 'ASSET'}_FUTAS_validation_report.txt",
                mime="text/plain")

        if bt["trades"]:
            st.markdown("##### Trades")
            st.dataframe(pd.DataFrame(bt["trades"]), width="stretch", height=320)
        else:
            st.info("No trades were triggered for these settings.")

# -------------------------------------------------------- Worked example -----
with tab_wex:
    st.caption("Reconstruct a real entry **earlier in the chart** (never the present "
               "bar) using only the data available up to that moment — no look-ahead — "
               "then walk the chart forward to the exit and measure the result: "
               "*“if you had entered there and closed here, you would have made this much.”*")
    wcol = st.columns(4)
    w_side = wcol[0].selectbox("Trade side", ["Any", "BUY", "SELL"], index=0)
    w_window = wcol[1].number_input("Rolling window", min_value=20, value=60, step=10,
                                    key="wex_window")
    w_region = wcol[2].slider("Search entries within first … % of chart", 30, 90, 70, 5,
                              key="wex_region",
                              help="The entry is taken from this earlier part so the trade "
                                   "has room to reach a target or stop afterwards.")
    if wcol[3].button("🎬 Reconstruct a trade", type="primary"):
        with st.spinner("Searching for the best historical FUTAS set-up…"):
            st.session_state["worked"] = worked_example(
                st.session_state.df, asset=asset or "ASSET", window=int(w_window),
                tol_pct=float(tol_pct), min_rr=float(min_rr),
                entry_search_end_frac=float(w_region) / 100.0,
                target_action=w_side.lower() if w_side != "Any" else "any")
    wt = st.session_state.get("worked")
    if wt is None:
        st.info("Choose the side and search region, then click **Reconstruct a trade**.")
    elif not wt.found:
        st.warning(wt.reason)
    else:
        sign = "profit" if wt.profit_pct >= 0 else "loss"
        box_color = "#1b5e20" if wt.outcome == "win" else ("#b71c1c" if wt.outcome == "loss" else "#777")
        verb = "bought" if wt.direction == 1 else "sold"
        back = "sold" if wt.direction == 1 else "bought back"
        st.markdown(
            f'<div style="background:#f4f6f8;border-left:6px solid {box_color};'
            f'padding:12px 16px;border-radius:6px;font-size:1.05rem">'
            f'🎬 If you had <b>{verb}</b> at <b>{wt.entry_price:.4f}</b> and <b>{back}</b> at '
            f'<b>{wt.exit_price:.4f}</b>, the trade would have returned '
            f'<b style="color:{box_color}">{wt.profit_pct:+.2f}%</b> '
            f'({wt.r_multiple:+.2f}R) — outcome <b>{wt.outcome.upper()}</b>, '
            f'held {wt.bars_held} bars.</div>',
            unsafe_allow_html=True)
        st.write("")
        wk = st.columns(6)
        wk[0].metric("Side", wt.action)
        wk[1].metric("Entry", f"{wt.entry_price:.4f}")
        wk[2].metric("Exit", f"{wt.exit_price:.4f}", wt.exit_kind)
        wk[3].metric("Result", f"{wt.profit_pct:+.2f}%", f"{wt.r_multiple:+.2f}R")
        wk[4].metric("Bars held", wt.bars_held)
        wk[5].metric("Confidence at entry", f"{wt.confidence_score:.0%}")
        st.plotly_chart(worked_chart(st.session_state.df, wt), width="stretch")
        st.markdown("##### Full reconstruction (no look-ahead)")
        st.code(wt.narrative, language="text")

# --------------------------------------------------- Screenshot TA -----------
with tab_ss:
    st.markdown("### 📷 Screenshot Technical Analysis")
    st.caption("Upload any chart image — live or historical — and FUTAS returns a full "
               "technical read: direction, BUY/SELL, entry/SL/TP, support/resistance, "
               "trend, Fibonacci Urvin interpretation, structure and a conclusion.")
    st.warning("⚠️ **Everything below is ESTIMATED FROM THE IMAGE**, not calculated from "
               "raw market data. Digitised candles are approximate and indicator values are "
               "estimates. Absolute Entry/SL/TP require the chart's price axis (enter its "
               "top & bottom prices). This is analytical only — not financial advice.")
    if not _SSTA_IMPORTED:
        st.error("screenshot_ta module not available.")
    else:
        up = st.file_uploader("Chart image / screenshot",
                              type=["png", "jpg", "jpeg", "bmp", "webp"], key="ss_uploader")
        cc = st.columns(4)
        ss_theme = cc[0].selectbox("Candle style", ["dark", "light", "color"], index=0,
                    help="dark = dark candles on light bg · light = light on dark · color = green/red")
        ss_asset = cc[1].text_input("Asset (optional)", value="", placeholder="auto-detect")
        ss_tf = cc[2].selectbox("Timeframe (optional)", ["auto"] + fe.TIMEFRAMES, index=0)
        ss_hint = cc[3].number_input("Candle count hint (0 = auto)", min_value=0, value=0, step=10)
        pc = st.columns([1, 1, 1.4])
        ss_high = pc[0].text_input("Axis TOP price (optional)", value="",
                                   help="The highest price shown on the chart's price axis.")
        ss_low = pc[1].text_input("Axis BOTTOM price (optional)", value="",
                                  help="The lowest price shown on the chart's price axis.")
        with st.expander("✂️ Crop the plot area (drop toolbar / price axis / tabs)", expanded=False):
            cr = st.columns(4)
            _cl = cr[0].slider("crop left %", 0, 40, 0) / 100.0
            _ct = cr[1].slider("crop top %", 0, 40, 0) / 100.0
            _crr = 1 - cr[2].slider("crop right %", 0, 40, 0) / 100.0
            _cb = 1 - cr[3].slider("crop bottom %", 0, 40, 0) / 100.0
        go_ss = pc[2].button("🔍 Analyze screenshot", type="primary", disabled=up is None,
                             width="stretch")

        if go_ss and up is not None:
            img_bytes = up.getvalue()

            def _pf(s):
                try:
                    return float(s.replace(",", "").strip()) if s.strip() else None
                except ValueError:
                    return None
            with st.spinner("Reading the chart and running FUTAS…"):
                out = screenshot_ta.analyze_screenshot(
                    img_bytes, asset=(ss_asset.strip() or None),
                    timeframe=(None if ss_tf == "auto" else ss_tf), theme=ss_theme,
                    crop_fracs=(_cl, _ct, _crr, _cb),
                    n_candles_hint=(int(ss_hint) or None),
                    price_high=_pf(ss_high), price_low=_pf(ss_low))
            if out.get("ok") and out.get("digit") is not None and _CHART_IMPORTED:
                try:
                    ov = chart_ingest.render_overlay(img_bytes, out["digit"])
                    _b = io.BytesIO(); ov.save(_b, format="PNG")
                    out["overlay_png"] = _b.getvalue()
                except Exception:
                    out["overlay_png"] = None
            st.session_state.ss_result = out

        out = st.session_state.get("ss_result")
        if out and not out.get("ok"):
            st.error(out.get("error", "Could not analyze the image."))
        elif out and out.get("ok"):
            r = out["report"]
            det = out.get("detected", {})
            st.success(f"Detected **{out['n_candles']}** candles · asset **{r['asset']}** · "
                       f"timeframe **{r['timeframe']}** · "
                       + ("absolute prices (axis given)" if out["scaled"]
                          else "RELATIVE scale — enter axis prices for exact levels"))
            top = st.columns(2)
            with top[0]:
                if out.get("overlay_png"):
                    st.image(out["overlay_png"], caption="Detected candles (cyan wick, coloured body)",
                             width="stretch")
                elif up is not None:
                    st.image(up, caption="Uploaded chart", width="stretch")
            with top[1]:
                badge = ACTION_COLORS.get(r["scenario"], "#737373")
                st.markdown(f'<div class="signal-badge" style="background:{badge}">'
                            f'{r["scenario"]}</div>', unsafe_allow_html=True)
                kk = st.columns(2)
                kk[0].metric("Direction", r["market_direction"])
                kk[1].metric("Trend", r["trend"])
                kk2 = st.columns(2)
                kk2[0].metric("R/R (TP1)", r["risk_reward"])
                kk2[1].metric("Confidence", r["confidence"])

            st.markdown("#### Estimated trade plan (from image)")
            tcols = st.columns(5)
            tcols[0].metric("Entry zone", r["entry_zone"])
            tcols[1].metric("Stop Loss", r["stop_loss"])
            tcols[2].metric("TP1", r["tp1"])
            tcols[3].metric("TP2", r["tp2"])
            tcols[4].metric("TP3", r["tp3"])

            ec = st.columns(2)
            with ec[0]:
                st.markdown("**Support zones (Fibonacci Urvin)**")
                for s in r["support_zones"]:
                    st.write("• " + s)
                st.markdown("**RSI / MACD / Volume** *(estimated)*")
                st.write(f"• RSI {r['rsi']}  ·  MACD {r['macd']}  ·  Volume {r['volume']}")
            with ec[1]:
                st.markdown("**Resistance zones (Fibonacci Urvin)**")
                for s in r["resistance_zones"]:
                    st.write("• " + s)
                st.markdown("**Market structure / Higher timeframe**")
                st.write(f"• Structure bias {r['market_structure']}  ·  HTF {r['htf']}")

            st.markdown("**Invalidation:** " + r["invalidation"])
            st.info("**Final conclusion:** " + r["conclusion"])
            with st.expander("Fibonacci Urvin levels (estimated) + detected chart text"):
                st.write("  ·  ".join(r["fu_levels"]))
                if det.get("price_candidates"):
                    st.caption("OCR price candidates: "
                               + ", ".join(str(x) for x in det["price_candidates"][:12]))
                if out.get("ocr_text"):
                    st.caption("Raw OCR text (first 300 chars): " + out["ocr_text"][:300])
            if st.button("➡️ Load this reconstructed data into the main analysis"):
                _set_data(out["ohlc"], f"Screenshot: {r['asset']} {r['timeframe']}")
                st.success("Loaded — open the 📊 Analysis tab. (Values remain image-estimated.)")

# ------------------------------------------------------------ Telegram -------
with tab_tg:
    st.markdown("### 📡 Telegram Signal Center")
    st.caption("Connect a Telegram bot and FUTAS will deliver each confirmed "
               "BUY / SELL set-up straight to your chat in real time. This sends "
               "**alerts only** — it never places orders or moves money.")

    if not _TG_IMPORTED:
        st.error("telegram_signals module not available.")
    else:
        # ---- status badge -------------------------------------------------
        _bc = {"Connected": ("#1a9850", "🟢 Connected"),
               "Testing": ("#f0ad4e", "🟡 Testing"),
               "Reconnecting": ("#fb8c00", "🟠 Reconnecting"),
               "Error": ("#d73027", "🔴 Error"),
               "Disconnected": ("#737373", "⚪ Disconnected"),
               "Not Connected": ("#737373", "⚪ Not Connected")}.get(
                   st.session_state.tg_status, ("#737373", "⚪ Not Connected"))
        sc1, sc2 = st.columns([1, 2])
        sc1.markdown(f'<div class="signal-badge" style="background:{_bc[0]};'
                     f'font-size:1.15rem">{_bc[1]}</div>', unsafe_allow_html=True)
        if st.session_state.tg_status == "Connected" and st.session_state.tg_bot_username:
            sc2.success(f"Bot @{st.session_state.tg_bot_username} → chat "
                        f"`{st.session_state.tg_chat_id}`"
                        + (f"  ({st.session_state.tg_username})"
                           if st.session_state.tg_username else ""))

        # ---- setup wizard -------------------------------------------------
        with st.expander("🧭 Telegram Setup Wizard (first time? start here)", expanded=False):
            st.markdown(
                "1. Open **Telegram** and search for **@BotFather**.\n"
                "2. Send **/newbot**, choose a name, and copy the **Bot Token** "
                "(looks like `123456789:AAE…`).\n"
                "3. Open **your new bot** and press **/start** "
                "(required before it can message you).\n"
                "4. Find your numeric **Chat ID** — use **🔎 Find my Chat ID** below "
                "after pressing /start, or message **@userinfobot**.\n"
                "5. Paste the **Bot Token** into FUTAS.\n"
                "6. Enter the **Chat ID**.\n"
                "7. Click **Connect**.\n"
                "8. Press **Send Test Signal** to verify.\n"
                "9. Keep this tab’s **Auto-send** on — confirmed signals now arrive automatically.")

        st.markdown("---")

        # ---- connection form ---------------------------------------------
        if st.session_state.tg_status != "Connected":
            st.markdown("#### 🔌 Connect")
            token_in = st.text_input(
                "Telegram Bot Token", type="password", key="tg_token_input",
                placeholder="123456789:AAE…",
                help="From @BotFather. Stored only in this browser session’s memory "
                     "(never written to disk) and shown masked once connected.")
            cc = st.columns(2)
            chat_in = cc[0].text_input("Telegram Chat ID", key="tg_chat_input",
                                       value=st.session_state.tg_chat_id,
                                       placeholder="e.g. 123456789")
            user_in = cc[1].text_input("Telegram Username (optional)", key="tg_user_input",
                                       value=st.session_state.tg_username,
                                       placeholder="@yourname")
            bcc = st.columns([1, 1, 3])
            if bcc[0].button("✅ Connect", type="primary"):
                if not token_in or ":" not in token_in:
                    st.warning("Enter a valid Bot Token (format `<id>:<hash>`).")
                elif not tg.validate_chat_id(chat_in):
                    st.warning("Enter a valid numeric Chat ID (e.g. 123456789).")
                else:
                    with st.spinner("Verifying the bot with Telegram…"):
                        v = tg.validate_token(token_in)
                    if v.get("ok"):
                        st.session_state.tg_token = token_in
                        st.session_state.tg_chat_id = chat_in.strip()
                        st.session_state.tg_username = user_in.strip()
                        st.session_state.tg_bot_username = v.get("bot_username", "")
                        st.session_state.tg_status = "Connected"
                        st.session_state.tg_last_sig = ""   # allow current live signal to send
                        import time as _t
                        st.session_state.tg_last_health = _t.time()
                        st.session_state.pop("tg_token_input", None)  # clear typed secret
                        _tg_log(f"Connected to @{v.get('bot_username','')}", True)
                        st.rerun()
                    else:
                        st.error(f"Could not connect: {v.get('error')}")

            with bcc[1]:
                if st.button("🔎 Find my Chat ID"):
                    if not token_in or ":" not in token_in:
                        st.warning("Enter the Bot Token first, then press /start in the bot.")
                    else:
                        with st.spinner("Reading recent bot messages…"):
                            h = tg.get_chat_id_hint(token_in)
                        if h.get("ok") and h.get("chats"):
                            st.write("Chats that have messaged this bot:")
                            for c in h["chats"]:
                                st.code(f"{c['id']}   ({c['type']} {c['name']})")
                            st.caption("Copy the numeric id into the Chat ID field above.")
                        elif h.get("ok"):
                            st.info("No messages yet — open the bot in Telegram, press "
                                    "**/start**, then try again.")
                        else:
                            st.error(h.get("error", "Could not read updates."))
        else:
            st.markdown("#### 🔐 Connection")
            ic = st.columns([2, 1, 1])
            ic[0].text_input("Bot Token (hidden)", value=_tg_mask(st.session_state.tg_token),
                             disabled=True)
            if ic[1].button("♻️ Replace token"):
                st.session_state.tg_status = "Not Connected"
                st.session_state.tg_token = ""
                st.session_state.pop("tg_token_input", None)
                _tg_log("Token cleared for replacement.", True)
                st.rerun()
            if ic[2].button("⛔ Disconnect"):
                st.session_state.tg_status = "Not Connected"
                st.session_state.tg_token = ""
                st.session_state.tg_bot_username = ""
                st.session_state.tg_trades = []
                st.session_state.pop("tg_token_input", None)
                _tg_log("Disconnected.", True)
                st.rerun()

        # ---- signal preferences / alert filters --------------------------
        st.markdown("#### ⚙️ Signal preferences & alert filters")
        pc = st.columns(3)
        _bands = ["All confirmed", "Medium and high-confidence", "High-confidence only"]
        st.session_state.tg_side = pc[0].selectbox(
            "Direction", ["Both", "BUY only", "SELL only"],
            index=["Both", "BUY only", "SELL only"].index(st.session_state.tg_side))
        st.session_state.tg_conf = pc[1].selectbox(
            "Confidence band", _bands,
            index=_bands.index(st.session_state.tg_conf) if st.session_state.tg_conf in _bands else 0,
            help="High ≥ 70%, Medium ≥ 45% (engine bands).")
        st.session_state.tg_auto = pc[2].toggle(
            "Auto-send confirmed signals", value=st.session_state.tg_auto,
            help="When on, each newly-confirmed BUY/SELL at the selected timeframe "
                 "is delivered automatically (once per set-up).")
        pc2 = st.columns(4)
        st.session_state.tg_min_rr = pc2[0].number_input(
            "Min R/R (TP1)", min_value=0.0, value=float(st.session_state.tg_min_rr), step=0.5,
            help="Only alert if the TP1 Risk/Reward is at least this (0 = off).")
        st.session_state.tg_min_conf = pc2[1].number_input(
            "Min confidence %", min_value=0, max_value=100, value=int(st.session_state.tg_min_conf),
            step=5, help="Only alert if the confidence score is at least this (0 = off).")
        st.session_state.tg_require_htf = pc2[2].toggle(
            "Require HTF align", value=bool(st.session_state.tg_require_htf),
            help="Only alert when the higher timeframe supports the direction.")
        st.session_state.tg_require_vol = pc2[3].toggle(
            "Require volume", value=bool(st.session_state.tg_require_vol),
            help="Only alert when volume confirms (above-average participation).")
        st.session_state.tg_valid_bars = st.slider(
            "Signal validity window (bars of the selected timeframe)",
            1, 48, int(st.session_state.tg_valid_bars),
            help="Used for the ‘Signal Valid Until’ time in the alert.")
        # live read-out: validation layer + filters for the CURRENT signal
        _v_ok, _v_reasons = _tg_validate_signal(res)
        if not _v_ok:
            st.info("🚫 **No confirmed set-up to send** — " + _v_reasons[0]
                    + ".  Telegram stays silent until a validated BUY/SELL appears.")
        else:
            _passes = _tg_signal_passes(res, res.signal)
            if _passes:
                st.success("✅ Validated **" + res.signal.action + "** set-up — "
                           + ", ".join(_v_reasons[:4]) + ". It will be auto-sent (matches the app).")
            else:
                st.warning("✅ Validated **" + res.signal.action + "**, but 🚫 below your alert "
                           "filters (direction/confidence/RR/HTF/volume) — not auto-sent.")

        # ---- test + manual send ------------------------------------------
        st.markdown("#### 🧪 Test & send")
        tcol = st.columns(3)
        _can_send = bool(st.session_state.tg_token) and tg.validate_chat_id(st.session_state.tg_chat_id)
        # Test = CONNECTION check only. It NEVER fabricates a BUY/SELL, so it can
        # never contradict the app. (If a validated signal exists, use "Send current
        # signal now" to push the real one.)
        if tcol[0].button("📨 Send Test Message", disabled=not _can_send,
                          help="Verifies the bot connection. Sends NO trade signal / no "
                               "entry/SL/TP — so it can never contradict the app."):
            with st.spinner("🟡 Testing the connection…"):
                out = tg.send_message(st.session_state.tg_token, st.session_state.tg_chat_id,
                                      tg.build_test_message(asset or "XAUUSD", _current_tf_label()))
            if out.get("ok"):
                st.success("✅ Connection test sent (no trade signal). Check your Telegram.")
                _tg_log("Connection test sent (no signal)", True, status="sent",
                        asset=asset or "XAUUSD", timeframe=_current_tf_label(), signal="TEST")
            else:
                st.error(f"Test failed: {out.get('error')}")
                _tg_log("Connection test failed", False, status="failed",
                        error=str(out.get("error", "")), asset=asset or "XAUUSD",
                        timeframe=_current_tf_label(), signal="TEST")
        # send the CURRENT signal on demand — only if it passes the validation layer
        _valid_ok, _valid_reasons = _tg_validate_signal(res)
        _cur_ok = _can_send and _valid_ok
        if tcol[1].button("📤 Send current signal now", disabled=not _cur_ok,
                          help="Pushes the current VALIDATED signal (bypasses only the alert "
                               "filters, never the validation). Disabled when no valid set-up."):
            tf = _current_tf_label()
            msg = _fmt_signal(res, tf)
            out = tg.send_message(st.session_state.tg_token, st.session_state.tg_chat_id, msg)
            if out.get("ok"):
                st.success("✅ Telegram alert sent successfully.")
                st.session_state.tg_last_sig = tg.signal_signature(res.asset, tf, res)
                _tg_register_trade(res, tf)      # monitor this trade's TP/SL too
            else:
                st.error(f"Send failed: {out.get('error')}")
            _tg_log(f"MANUAL {res.signal.action} {res.asset} {tf}: " + "; ".join(_valid_reasons),
                    out.get("ok", False), asset=res.asset, timeframe=tf, signal=res.signal.action,
                    entry=f"{res.signal.entry:.6g}",
                    sl=(f"{res.signal.stop_loss:.6g}" if res.signal.stop_loss else "—"),
                    tps=", ".join(f"{t:.6g}" for t in (res.signal.take_profits or [])),
                    status=("sent" if out.get("ok") else "failed"),
                    error=("" if out.get("ok") else str(out.get("error", ""))))
        if not _can_send:
            tcol[2].caption("Connect a bot + valid Chat ID to enable sending.")
        elif not _valid_ok:
            tcol[2].caption("🚫 No valid signal to send: " + _valid_reasons[0])

        # ---- live preview of what will be sent ---------------------------
        if getattr(res.signal, "action", "WAIT") in ("BUY", "SELL"):
            with st.expander("👁️ Preview of the message for the current signal", expanded=False):
                st.code(_tg_plaintext(_fmt_signal(res, _current_tf_label())),
                        language="text")
        else:
            st.info(f"Current signal is **WAIT** — nothing to send yet. Auto-send will "
                    f"trigger when a {st.session_state.tg_side} set-up is confirmed on "
                    f"**{_current_tf_label()}**.")

        # ---- monitored trades (lifecycle TP/SL tracking) ------------------
        if st.session_state.tg_trades:
            st.markdown("#### 🛰️ Monitored trades (TP/SL lifecycle)")
            st.caption("Each sent signal is tracked against new bars; TP1/TP2/TP3 and "
                       "Stop-Loss hits are pushed to Telegram automatically. Monitoring "
                       "advances as fresh data arrives (refresh live data / switch timeframe).")
            _tr_rows = [{
                "Asset": t["asset"], "TF": t["timeframe"], "Side": t["action"],
                "Entry": f"{t['entry']:.6g}", "Stop": f"{t['sl']:.6g}" if t["sl"] else "—",
                "TPs": ", ".join(f"{x:.6g}" for x in t["tps"]),
                "Hit": ", ".join(t["hit"]) or "—", "Status": t["status"],
            } for t in st.session_state.tg_trades]
            st.dataframe(pd.DataFrame(_tr_rows), width="stretch", hide_index=True, height=200)
            if st.button("🧹 Clear closed trades"):
                st.session_state.tg_trades = [t for t in st.session_state.tg_trades
                                              if t.get("status") == "open"]
                st.rerun()

        # ---- send log table (dashboard §11) -------------------------------
        if st.session_state.tg_log:
            st.markdown("#### 📜 Telegram alert log")
            _rows = []
            for e in st.session_state.tg_log:
                _rows.append({
                    "Time": e.get("time", ""),
                    "Asset": e.get("asset", "—"),
                    "Timeframe": e.get("timeframe", "—"),
                    "Signal": e.get("signal", "—"),
                    "Entry": e.get("entry", "—"),
                    "Stop Loss": e.get("sl", "—"),
                    "Take Profits": e.get("tps", "—"),
                    "Status": ("✅ " + e.get("status", "")) if e["ok"] else ("❌ " + e.get("status", "failed")),
                    "Error": e.get("error", ""),
                })
            st.dataframe(pd.DataFrame(_rows), width="stretch", hide_index=True, height=280)

# ---------------------------------------------------------------- Data -------
with tab_data:
    st.dataframe(st.session_state.df, width="stretch", height=480)
    st.download_button("⬇️ Download normalized OHLC (CSV)",
                       st.session_state.df.to_csv(index=False).encode("utf-8"),
                       file_name=f"{asset}_ohlc_normalized.csv", mime="text/csv")

# --------------------------------------------------------- Explanation -------
with tab_exp:
    st.markdown("#### Scientific explanation (auto-generated)")
    st.code(res.explanation, language="text")
    cexp = st.columns(3)
    cexp[0].download_button("⬇️ Excel workbook (.xlsx)",
                            build_excel_bytes(res, st.session_state.backtest),
                            file_name=f"FUTAS_{asset}_report.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    cexp[1].download_button("⬇️ Text report (.txt)",
                            build_text_report(res, st.session_state.backtest).encode("utf-8"),
                            file_name=f"FUTAS_{asset}_report.txt", mime="text/plain")
    cexp[2].download_button("⬇️ FU levels (.csv)",
                            res.levels_table().to_csv(index=False).encode("utf-8"),
                            file_name=f"FUTAS_{asset}_levels.csv", mime="text/csv")

# --------------------------------------------------------------- Science -----
with tab_about:
    st.markdown("#### Fibonacci Urvin adaptive coefficient system")
    st.code(", ".join(str(k) for k in FU_COEFFICIENTS), language="text")
    st.latex(r"P = \text{Low} + (\text{High} - \text{Low}) \times K")
    st.dataframe(pd.DataFrame({
        "order": range(len(FU_COEFFICIENTS)),
        "K": FU_COEFFICIENTS,
        "percent": [k * 100 for k in FU_COEFFICIENTS],
    }), width="stretch", height=420)
    st.markdown(
        "**Scientific essence.** FUTAS automatically detects the High/Low range, projects the "
        "15 Fibonacci Urvin levels, reads market trend and structure (HH/HL/LH/LL, BOS/CHoCH), "
        "distinguishes impulse vs. correction, and forms a BUY / SELL / WAIT decision whose "
        "Entry, Stop-Loss and Take-Profit are taken **only** from the computed FU levels. "
        "It is an instrument for scientific research and algorithmic testing — not financial advice.")
