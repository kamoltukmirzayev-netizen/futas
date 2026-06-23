"""
live_data.py
===============================================================================
FUTAS — live OHLC fetch (honest TradingView alternative).

TradingView does NOT publish an official public market-data API, so this module
pulls equivalent candles from sources that DO allow programmatic access:

    * Crypto                 -> Binance public REST (klines)  — no API key
    * Gold / FX / stocks     -> Yahoo Finance chart endpoint  — no API key

The returned frame uses the same raw OHLC column convention that
`futas_engine.normalize_ohlc()` already understands, so the rest of the FUTAS
pipeline is unchanged. CSV / image / manual input remain fully available; this
is just one more way to load data.

Only the Python standard library is used (urllib + json) so no extra dependency
is added to requirements.txt.

NOTE: data is provided for scientific back-testing/analysis. FUTAS does not give
financial advice and does not place orders.
===============================================================================
"""

from __future__ import annotations

import json
from typing import List, Dict, Any, Optional
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

import pandas as pd

_UA = {"User-Agent": "Mozilla/5.0 (FUTAS scientific research)"}

# ----------------------------------------------------------------------------
# Crypto — Binance
# ----------------------------------------------------------------------------
BINANCE_INTERVALS: List[str] = [
    "1m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d", "1w",
]
# `data-api.binance.vision` is the market-data mirror, reachable where the main
# api host is geo-blocked; we try both.
_BINANCE_HOSTS = ["https://api.binance.com", "https://data-api.binance.vision"]
BINANCE_PRESETS: Dict[str, str] = {
    "Bitcoin (BTCUSDT)": "BTCUSDT",
    "Ethereum (ETHUSDT)": "ETHUSDT",
    "BNB (BNBUSDT)": "BNBUSDT",
    "Solana (SOLUSDT)": "SOLUSDT",
    "XRP (XRPUSDT)": "XRPUSDT",
    "Gold-backed PAXG (PAXGUSDT)": "PAXGUSDT",
}

# ----------------------------------------------------------------------------
# Gold / FX / stocks — Yahoo Finance
# ----------------------------------------------------------------------------
YAHOO_INTERVALS: List[str] = ["1d", "1h", "30m", "15m", "5m", "1m", "1wk", "1mo"]
YAHOO_RANGES: List[str] = ["5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "max"]
_YAHOO_HOSTS = ["https://query1.finance.yahoo.com", "https://query2.finance.yahoo.com"]

# Yahoo only serves intraday intervals over short ranges. Requesting e.g. 30m
# over 5y returns HTTP 422, so we clamp the range to each interval's limit.
_YAHOO_RANGE_ORDER = ["5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "max"]
_YAHOO_INTRADAY_MAX = {"1m": "5d", "2m": "5d", "5m": "1mo", "15m": "1mo",
                       "30m": "1mo", "60m": "2y", "1h": "2y", "90m": "2y"}


def _clamp_yahoo_range(interval: str, range_: str) -> str:
    """Shrink `range_` to the largest Yahoo allows for an intraday `interval`."""
    cap = _YAHOO_INTRADAY_MAX.get(interval)
    if not cap:
        return range_
    order = _YAHOO_RANGE_ORDER
    try:
        return cap if order.index(range_) > order.index(cap) else range_
    except ValueError:
        return cap
YAHOO_PRESETS: Dict[str, str] = {
    "Gold futures (GC=F)": "GC=F",
    "Silver futures (SI=F)": "SI=F",
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "USD/JPY": "JPY=X",
    "Bitcoin (BTC-USD)": "BTC-USD",
    "Ethereum (ETH-USD)": "ETH-USD",
    "S&P 500 (^GSPC)": "^GSPC",
}


def _http_get(url: str, timeout: int = 20) -> bytes:
    req = Request(url, headers=_UA)
    with urlopen(req, timeout=timeout) as r:   # noqa: S310 (trusted hosts only)
        return r.read()


def fetch_binance(symbol: str = "BTCUSDT", interval: str = "1h",
                  limit: int = 300) -> pd.DataFrame:
    """
    Fetch OHLCV candles from the public Binance klines endpoint.

    Returns a DataFrame with columns time/open/high/low/close/volume.
    Raises RuntimeError with a readable message on failure.
    """
    symbol = symbol.upper().replace("/", "").replace(" ", "")
    if interval not in BINANCE_INTERVALS:
        interval = "1h"
    limit = max(10, min(int(limit), 1000))      # Binance hard cap is 1000
    params = urlencode({"symbol": symbol, "interval": interval, "limit": limit})

    last_err: Any = None
    for host in _BINANCE_HOSTS:
        url = f"{host}/api/v3/klines?{params}"
        try:
            raw = json.loads(_http_get(url))
            if isinstance(raw, dict) and raw.get("code"):
                raise RuntimeError(f"Binance: {raw.get('msg', raw)}")
            rows = [{
                "time": pd.to_datetime(k[0], unit="ms"),
                "open": float(k[1]), "high": float(k[2]),
                "low": float(k[3]), "close": float(k[4]),
                "volume": float(k[5]),
            } for k in raw]
            if not rows:
                raise RuntimeError(f"Binance returned no candles for {symbol} {interval}.")
            return pd.DataFrame(rows)
        except (HTTPError, URLError) as e:       # try the next host
            last_err = e
            continue
        except RuntimeError:
            raise
        except Exception as e:                   # parsing / unexpected
            last_err = e
            continue
    raise RuntimeError(
        f"Could not reach Binance for {symbol} {interval} "
        f"({type(last_err).__name__}: {last_err}). Check the symbol "
        f"(e.g. BTCUSDT, ETHUSDT) and your internet connection."
    )


def fetch_yahoo(symbol: str = "GC=F", interval: str = "1d",
                range_: str = "1y") -> pd.DataFrame:
    """
    Fetch OHLC candles from the public Yahoo Finance chart endpoint.

    Good for gold (GC=F), silver (SI=F), FX (EURUSD=X), indices (^GSPC) and even
    crypto (BTC-USD). Returns a DataFrame with time/open/high/low/close/volume.
    Note: intraday intervals (5m/15m/30m/1h) are only available over short
    ranges; Yahoo silently shortens the range if it is too long for the interval.
    """
    symbol = symbol.strip().replace(" ", "")
    if interval not in YAHOO_INTERVALS:
        interval = "1d"
    if range_ not in YAHOO_RANGES:
        range_ = "1y"
    range_ = _clamp_yahoo_range(interval, range_)   # avoid 422 on intraday+long range
    params = urlencode({"range": range_, "interval": interval, "includePrePost": "false"})

    last_err: Any = None
    for host in _YAHOO_HOSTS:
        url = f"{host}/v8/finance/chart/{quote(symbol)}?{params}"
        try:
            raw = json.loads(_http_get(url))
            chart = raw.get("chart", {}) if isinstance(raw, dict) else {}
            if chart.get("error"):
                err = chart["error"]
                raise RuntimeError(f"Yahoo: {err.get('description', err)}")
            res = chart.get("result")
            if not res:
                raise RuntimeError(f"Yahoo returned no data for '{symbol}'.")
            r0 = res[0]
            ts = r0.get("timestamp") or []
            quote_block = (r0.get("indicators", {}).get("quote") or [{}])[0]
            o = quote_block.get("open", [])
            h = quote_block.get("high", [])
            low = quote_block.get("low", [])
            c = quote_block.get("close", [])
            v = quote_block.get("volume", [])
            rows: List[Dict[str, Any]] = []
            for i, t in enumerate(ts):
                op, hi, lo, cl = o[i], h[i], low[i], c[i]
                if op is None or hi is None or lo is None or cl is None:
                    continue   # skip gap bars (holidays / missing prints)
                vol = v[i] if i < len(v) and v[i] is not None else 0.0
                rows.append({
                    "time": pd.to_datetime(int(t), unit="s"),
                    "open": float(op), "high": float(hi),
                    "low": float(lo), "close": float(cl),
                    "volume": float(vol),
                })
            if not rows:
                raise RuntimeError(
                    f"Yahoo returned an empty series for '{symbol}' "
                    f"({interval}/{range_})."
                )
            return pd.DataFrame(rows)
        except (HTTPError, URLError) as e:
            last_err = e
            continue
        except RuntimeError:
            raise
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(
        f"Could not reach Yahoo Finance for '{symbol}' "
        f"({type(last_err).__name__}: {last_err}). Check the symbol "
        f"(e.g. GC=F for gold, EURUSD=X, BTC-USD) and your connection."
    )


def fetch_live(market: str, symbol: str, interval: str,
               limit: int = 300, range_: str = "1y") -> pd.DataFrame:
    """
    Dispatch a live fetch by market.

    market starting with "Crypto" -> fetch_binance (uses `limit`)
    otherwise                      -> fetch_yahoo  (uses `range_`)
    """
    if market.startswith("Crypto"):
        return fetch_binance(symbol=symbol, interval=interval, limit=limit)
    return fetch_yahoo(symbol=symbol, interval=interval, range_=range_)


# ----------------------------------------------------------------------------
# Live QUOTE snapshots (Bid / Ask / Spread / Day change) for the Live Center
# ----------------------------------------------------------------------------
# Canonical asset -> (source, vendor-symbol). Binance gives true bid/ask;
# Yahoo gives last/high/low/change (no order-book bid/ask).
LIVE_CENTER_ASSETS: Dict[str, tuple] = {
    "BTCUSD":  ("crypto", "BTCUSDT"),
    "ETHUSD":  ("crypto", "ETHUSDT"),
    "XAUUSD":  ("yahoo",  "GC=F"),
    "XAGUSD":  ("yahoo",  "SI=F"),
    "EURUSD":  ("yahoo",  "EURUSD=X"),
    "GBPUSD":  ("yahoo",  "GBPUSD=X"),
    "USDJPY":  ("yahoo",  "JPY=X"),
    "USDCHF":  ("yahoo",  "CHF=X"),
    "AUDUSD":  ("yahoo",  "AUDUSD=X"),
    "S&P500":  ("yahoo",  "^GSPC"),
}


def _binance_quote(symbol: str) -> Dict[str, Any]:
    symbol = symbol.upper().replace("/", "").replace(" ", "")
    last_err: Any = None
    for host in _BINANCE_HOSTS:
        try:
            raw = json.loads(_http_get(f"{host}/api/v3/ticker/24hr?symbol={symbol}"))
            if isinstance(raw, dict) and raw.get("code"):
                raise RuntimeError(raw.get("msg", raw))
            bid, ask = float(raw["bidPrice"]), float(raw["askPrice"])
            return {"ok": True, "symbol": symbol, "last": float(raw["lastPrice"]),
                    "bid": bid, "ask": ask, "spread": round(ask - bid, 8),
                    "high": float(raw["highPrice"]), "low": float(raw["lowPrice"]),
                    "change_pct": float(raw["priceChangePercent"]), "source": "Binance"}
        except (HTTPError, URLError) as e:
            last_err = e; continue
        except Exception as e:
            last_err = e; continue
    return {"ok": False, "symbol": symbol, "error": f"Binance quote failed ({last_err})"}


def _yahoo_quote(symbol: str) -> Dict[str, Any]:
    symbol = symbol.strip().replace(" ", "")
    params = urlencode({"range": "5d", "interval": "1d"})
    last_err: Any = None
    for host in _YAHOO_HOSTS:
        try:
            raw = json.loads(_http_get(f"{host}/v8/finance/chart/{quote(symbol)}?{params}"))
            res = (raw.get("chart", {}) or {}).get("result")
            if not res:
                raise RuntimeError("no data")
            meta = res[0].get("meta", {}) or {}
            last = meta.get("regularMarketPrice")
            prev = meta.get("chartPreviousClose") or meta.get("previousClose")
            hi, lo = meta.get("regularMarketDayHigh"), meta.get("regularMarketDayLow")
            change = ((last / prev - 1.0) * 100.0) if (last and prev) else None
            return {"ok": True, "symbol": symbol,
                    "last": float(last) if last is not None else None,
                    "bid": None, "ask": None, "spread": None,
                    "high": float(hi) if hi is not None else None,
                    "low": float(lo) if lo is not None else None,
                    "change_pct": float(change) if change is not None else None,
                    "source": "Yahoo"}
        except (HTTPError, URLError) as e:
            last_err = e; continue
        except Exception as e:
            last_err = e; continue
    return {"ok": False, "symbol": symbol, "error": f"Yahoo quote failed ({last_err})"}


def fetch_quote(asset: str, source: Optional[str] = None,
                symbol: Optional[str] = None) -> Dict[str, Any]:
    """
    One live quote snapshot. If `asset` is a canonical key in LIVE_CENTER_ASSETS
    the source/symbol resolve automatically; otherwise pass source
    ('crypto'|'yahoo') and the vendor symbol, or let it guess from the suffix.
    """
    if asset in LIVE_CENTER_ASSETS and source is None:
        source, symbol = LIVE_CENTER_ASSETS[asset]
    symbol = symbol or asset
    if source is None:
        source = "crypto" if symbol.upper().endswith(("USDT", "BUSD")) else "yahoo"
    q = _binance_quote(symbol) if source == "crypto" else _yahoo_quote(symbol)
    q["asset"] = asset
    return q


def market_is_open(asset: str) -> bool:
    """
    Coarse session status: crypto is 24/7; FX/metals run ~Sun 22:00–Fri 22:00 UTC
    (closed at the weekend); indices approximated to weekdays.
    """
    src = LIVE_CENTER_ASSETS.get(asset, ("yahoo", asset))[0]
    if src == "crypto" or asset in ("BTCUSD", "ETHUSD"):
        return True
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    wd, hr = now.weekday(), now.hour            # Mon=0 .. Sun=6
    if wd == 5:
        return False
    if wd == 6:
        return hr >= 22
    if wd == 4:
        return hr < 22
    return True


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    for fn, args in [
        ("Binance BTCUSDT 1h", lambda: fetch_binance("BTCUSDT", "1h", 50)),
        ("Yahoo GC=F 1d", lambda: fetch_yahoo("GC=F", "1d", "6mo")),
        ("Yahoo EURUSD=X 1d", lambda: fetch_yahoo("EURUSD=X", "1d", "3mo")),
    ]:
        try:
            d = args()
            print(f"{fn}: {len(d)} rows; last close = {float(d['close'].iloc[-1])}")
        except Exception as e:
            print(f"{fn}: FAILED -> {e}")
