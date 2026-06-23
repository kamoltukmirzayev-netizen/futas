"""
screenshot_ta.py
===============================================================================
FUTAS — Screenshot Technical Analysis.

Turns a *picture* of a chart (live or historical) into a full FUTAS technical
analysis: direction, BUY/SELL scenario, entry zone, Stop-Loss, TP1-3, R/R,
support/resistance, trend, Fibonacci Urvin interpretation, market structure,
invalidation and a final conclusion.

SCIENTIFIC HONESTY (hard requirement)
-------------------------------------
Everything produced here is **ESTIMATED FROM THE IMAGE**, not calculated from raw
market data. A rendered chart only yields approximate candles (pixels quantise
price, dense candles merge), so:
  * direction / trend / structure / R-R / Fibonacci-Urvin *percentages* are
    scale-invariant and reasonably robust;
  * absolute Entry / SL / TP prices are only meaningful once the chart's price
    axis is known (read two axis prices, or let the user type them);
  * indicator values (RSI/MACD/volume) derived from digitised candles are
    estimates of estimates and are labelled as such.
This module NEVER presents an image-estimated value as an exact raw-data figure.

Digitisation: chart_ingest (pure Pillow+numpy).   Text reading: ocr_ingest
(Tesseract, optional). The engine: futas_engine.analyze().
===============================================================================
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import pandas as pd

import futas_engine as fe

try:
    import chart_ingest
    _CHART_OK = True
except Exception:
    _CHART_OK = False

try:
    import ocr_ingest
    _OCR_OK = True
except Exception:
    _OCR_OK = False


# Common symbols / timeframes to look for in the chart's own text.
_ASSET_PATTERNS = [
    r"XAU\s*/?\s*USD", r"XAG\s*/?\s*USD", r"BTC\s*/?\s*USD[T]?", r"ETH\s*/?\s*USD[T]?",
    r"EUR\s*/?\s*USD", r"GBP\s*/?\s*USD", r"USD\s*/?\s*JPY", r"USD\s*/?\s*CHF",
    r"\bGOLD\b", r"\bSILVER\b", r"\bBITCOIN\b", r"\bETHEREUM\b",
    r"\b[A-Z]{3}/?[A-Z]{3}\b",
]
_TF_PATTERN = re.compile(
    r"\b(M1|M5|M15|M30|H1|H2|H4|D1|W1|MN|1m|5m|15m|30m|1h|2h|4h|1d|1w|"
    r"Daily|Weekly|Monthly|1 min|5 min|15 min|30 min|1 hour|4 hour)\b", re.I)
_NUM_PATTERN = re.compile(r"\d{1,3}(?:[ ,]\d{3})*(?:\.\d+)?|\d+\.\d+")

_TF_CANON = {
    "M1": "1M", "1M": "1M", "1MIN": "1M", "1 MIN": "1M",
    "M5": "5M", "5M": "5M", "5MIN": "5M", "5 MIN": "5M",
    "M15": "15M", "15M": "15M", "15MIN": "15M",
    "M30": "30M", "30M": "30M",
    "H1": "1H", "1H": "1H", "1HOUR": "1H", "1 HOUR": "1H",
    "H4": "4H", "4H": "4H", "4HOUR": "4H",
    "D1": "1D", "1D": "1D", "DAILY": "1D",
    "W1": "1W", "1W": "1W", "WEEKLY": "1W",
}


def detect_asset_timeframe(text: str) -> Dict[str, Optional[str]]:
    """Best-effort read of the asset symbol + timeframe from the chart's own text."""
    asset = None
    if text:
        for pat in _ASSET_PATTERNS:
            m = re.search(pat, text, re.I)
            if m:
                asset = re.sub(r"\s+", "", m.group(0)).upper()
                break
    tf = None
    if text:
        m = _TF_PATTERN.search(text)
        if m:
            tf = _TF_CANON.get(re.sub(r"\s+", "", m.group(1)).upper())
    return {"asset": asset, "timeframe": tf}


def _price_candidates(text: str) -> List[float]:
    out: List[float] = []
    for tok in _NUM_PATTERN.findall(text or ""):
        try:
            out.append(float(tok.replace(" ", "").replace(",", "")))
        except ValueError:
            continue
    return sorted(set(out))


def analyze_screenshot(image_bytes: bytes,
                       asset: Optional[str] = None,
                       timeframe: Optional[str] = None,
                       theme: str = "dark",
                       crop_fracs=(0.0, 0.0, 1.0, 1.0),
                       n_candles_hint: Optional[int] = None,
                       price_high: Optional[float] = None,
                       price_low: Optional[float] = None) -> Dict[str, Any]:
    """
    Full screenshot → FUTAS analysis. Returns a dict:
      ok, error, scaled (bool), n_candles, ocr_text, detected{asset,timeframe,
      price_candidates}, res (FUTASResult), ohlc (DataFrame), report (dict of
      estimated fields), digit (DigitizeResult).
    `scaled` is True only when real axis prices were supplied — otherwise prices
    are on an arbitrary 0..100 scale and must NOT be read as absolute levels.
    """
    if not _CHART_OK:
        return {"ok": False, "error": "chart_ingest not available."}

    # 1) read any text the chart carries (asset / timeframe / axis numbers)
    ocr_text = ""
    if _OCR_OK:
        try:
            ocr_text = ocr_ingest.image_to_text(image_bytes) or ""
        except Exception:
            ocr_text = ""
    detected = detect_asset_timeframe(ocr_text)
    detected["price_candidates"] = _price_candidates(ocr_text)
    asset = asset or detected.get("asset") or "SCREENSHOT"
    timeframe = timeframe or detected.get("timeframe") or "—"

    # 2) digitise the candles
    try:
        digit = chart_ingest.detect_candles(
            image_bytes, crop_fracs=tuple(crop_fracs), theme=theme,
            n_candles_hint=n_candles_hint)
    except Exception as e:
        return {"ok": False, "error": f"Could not read candles from the image: {e}"}
    n_candles = len(getattr(digit, "candles", []) or [])
    if n_candles < 5:
        return {"ok": False, "error": f"Only {n_candles} candles detected — try a "
                "different candle theme or a tighter crop of the plot area.",
                "n_candles": n_candles, "digit": digit, "ocr_text": ocr_text,
                "detected": detected}

    # 3) calibrate pixels -> price. Real axis prices => absolute; else 0..100.
    scaled = price_high is not None and price_low is not None and price_high > price_low
    ph, pl = (float(price_high), float(price_low)) if scaled else (100.0, 0.0)
    try:
        ohlc = chart_ingest.calibrate(digit, price_high=ph, price_low=pl)
    except Exception as e:
        return {"ok": False, "error": f"Calibration failed: {e}", "digit": digit}

    # 4) run the full FUTAS engine on the reconstructed series
    try:
        res = fe.analyze(ohlc, asset=asset)
    except Exception as e:
        return {"ok": False, "error": f"Analysis failed on the reconstructed data: {e}"}
    nar = fe.signal_narrative(res)

    report = _build_report(res, nar, asset, timeframe, scaled)
    return {"ok": True, "scaled": scaled, "n_candles": n_candles, "ocr_text": ocr_text,
            "detected": detected, "res": res, "ohlc": ohlc, "digit": digit,
            "report": report, "asset": asset, "timeframe": timeframe}


def _fmt(v: Optional[float], scaled: bool) -> str:
    if v is None:
        return "—"
    if not scaled:
        return f"{v:.1f} (relative)"
    a = abs(v)
    return f"{v:,.2f}" if a >= 100 else (f"{v:.4f}" if a >= 1 else f"{v:.6f}")


def _build_report(res: "fe.FUTASResult", nar: Dict[str, str], asset: str,
                  timeframe: str, scaled: bool) -> Dict[str, Any]:
    """Assemble the requested screenshot-analysis fields, all image-estimated."""
    sg = res.signal
    mom = res.momentum or {}
    vol = res.volume_conf or {}
    htf = res.htf or {}
    levels = sorted(res.levels, key=lambda L: L.price)
    cp = res.current_price
    supports = [L for L in levels if L.price < cp][-3:]
    resists = [L for L in levels if L.price > cp][:3]
    rsi = mom.get("rsi")

    direction = ("Bullish / upward" if res.trend == "UPTREND" else
                 "Bearish / downward" if res.trend == "DOWNTREND" else "Sideways / ranging")
    if sg.action == "BUY":
        entry_zone = f"{_fmt(sg.entry, scaled)}"
    elif sg.action == "SELL":
        entry_zone = f"{_fmt(sg.entry, scaled)}"
    else:
        entry_zone = "no confirmed entry"

    return {
        "asset": asset,
        "timeframe": timeframe,
        "current_price": _fmt(cp, scaled),
        "market_direction": direction,
        "scenario": sg.action,
        "entry_zone": entry_zone,
        "stop_loss": _fmt(sg.stop_loss, scaled) if sg.action in ("BUY", "SELL") else "—",
        "tp1": _fmt(sg.take_profits[0], scaled) if len(sg.take_profits) > 0 else "—",
        "tp2": _fmt(sg.take_profits[1], scaled) if len(sg.take_profits) > 1 else "—",
        "tp3": _fmt(sg.take_profits[2], scaled) if len(sg.take_profits) > 2 else "—",
        "risk_reward": f"1:{sg.rr[0]:.2f}" if getattr(sg, "rr", None) else "—",
        "support_zones": [f"FU {L.k:g} ({L.percent:.0f}%) {_fmt(L.price, scaled)}" for L in supports] or ["—"],
        "resistance_zones": [f"FU {L.k:g} ({L.percent:.0f}%) {_fmt(L.price, scaled)}" for L in resists] or ["—"],
        "trend": res.trend,
        "market_structure": res.trend_metrics.get("structure_bias", "—"),
        "fu_levels": [f"FU {L.k:g} ({L.percent:.1f}%) = {_fmt(L.price, scaled)}" for L in res.levels],
        "rsi": f"{rsi:.0f}" if isinstance(rsi, (int, float)) and rsi == rsi else "—",
        "macd": ("rising" if mom.get("hist", 0) and mom.get("hist", 0) > mom.get("hist_prev", 0)
                 else "falling"),
        "volume": (f"{vol.get('status')} (×{vol.get('ratio')})" if vol.get("available")
                   else "not visible / not estimable"),
        "htf": (f"{htf.get('timeframe')} {htf.get('trend')}" if htf.get("timeframe") else "—"),
        "confidence": f"{sg.confidence_score*100:.0f}% ({sg.confidence})",
        "invalidation": nar.get("invalidation", "—"),
        "conclusion": _conclusion(res, nar, scaled),
    }


def _conclusion(res: "fe.FUTASResult", nar: Dict[str, str], scaled: bool) -> str:
    sg = res.signal
    if sg.action == "WAIT":
        return ("No confirmed FUTAS set-up is visible in this chart — structure and "
                "Fibonacci Urvin levels do not agree on a side. Wait for confirmation.")
    base = nar.get("scenario", "")
    price_note = ("" if scaled else " Absolute Entry/SL/TP cannot be given without the "
                  "chart's price axis — provide the top and bottom axis prices for exact levels.")
    return (f"{sg.action} bias estimated from the image. {base}"
            f" Planned R/R {('1:%.2f' % sg.rr[0]) if sg.rr else 'n/a'}, "
            f"confidence {sg.confidence_score*100:.0f}%.{price_note}")


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    # offline self-test: render a synthetic chart, then analyse the image
    import io
    import numpy as np
    from PIL import Image, ImageDraw
    df = fe._demo_frame(n=80, seed=4)
    W, H, pad = 80 * 8 + 24, 420, 40
    pmin, pmax = float(df["low"].min()), float(df["high"].max())

    def y(p):
        return int(pad + (pmax - p) / (pmax - pmin) * (H - 2 * pad))
    img = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(img)
    for i, row in df.reset_index(drop=True).iterrows():
        cx = 12 + i * 8 + 3
        d.line([(cx, y(row.high)), (cx, y(row.low))], fill=(0, 0, 0), width=1)
        top, bot = y(max(row.open, row.close)), y(min(row.open, row.close))
        if bot - top < 2:
            bot = top + 2
        d.rectangle([12 + i * 8, top, 12 + i * 8 + 5, bot],
                    fill=(0, 0, 0) if row.close < row.open else None,
                    outline=(0, 0, 0))
    buf = io.BytesIO(); img.save(buf, format="PNG")
    out = analyze_screenshot(buf.getvalue(), asset="XAUUSD", timeframe="1H",
                             theme="dark", price_high=pmax, price_low=pmin)
    print("ok:", out["ok"], "| candles:", out.get("n_candles"), "| scaled:", out.get("scaled"))
    if out["ok"]:
        r = out["report"]
        for k in ("asset", "timeframe", "market_direction", "scenario", "entry_zone",
                  "stop_loss", "tp1", "risk_reward", "trend", "rsi", "conclusion"):
            print(f"  {k:16s}: {r[k]}")
