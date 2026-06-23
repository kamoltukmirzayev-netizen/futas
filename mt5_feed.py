"""
mt5_feed.py
===============================================================================
FUTAS — optional MetaTrader 5 live feed.

The official `MetaTrader5` Python package is **Windows-only** and needs the MT5
terminal installed and running on the same machine. It therefore works only when
FUTAS is run locally on Windows — it is NOT available on Streamlit Community
Cloud (Linux). The Live Center uses this when available and automatically falls
back to the cloud feeds (Binance / Yahoo) otherwise.

SECURITY
--------
Credentials (login / password / server) are passed in as arguments by the caller
and are never stored, printed, or logged by this module. The app keeps them in
per-session memory only and shows them masked. Nothing is hard-coded here.
===============================================================================
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    import MetaTrader5 as _mt5          # noqa: N813
    _MT5_AVAILABLE = True
except Exception:
    _mt5 = None
    _MT5_AVAILABLE = False


def available() -> bool:
    """True only where the MetaTrader5 package imported (local Windows + MT5)."""
    return _MT5_AVAILABLE


def connect(login: Optional[int] = None, password: Optional[str] = None,
            server: Optional[str] = None) -> Dict[str, Any]:
    """
    Initialise/log in to the local MT5 terminal. Returns {ok, account?, error?}.
    Credentials are used transiently and never persisted by this module.
    """
    if not _MT5_AVAILABLE:
        return {"ok": False, "error": "MetaTrader5 package not installed (local Windows only)."}
    try:
        if login and password and server:
            ok = _mt5.initialize(login=int(login), password=str(password), server=str(server))
        else:
            ok = _mt5.initialize()
        if not ok:
            return {"ok": False, "error": f"MT5 initialize failed: {_mt5.last_error()}"}
        info = _mt5.account_info()
        acct = {}
        if info is not None:
            d = info._asdict()
            # expose only non-sensitive fields
            acct = {"login": d.get("login"), "name": d.get("name"),
                    "server": d.get("server"), "currency": d.get("currency"),
                    "balance": d.get("balance"), "equity": d.get("equity"),
                    "leverage": d.get("leverage"), "company": d.get("company")}
        term = _mt5.terminal_info()
        return {"ok": True, "account": acct,
                "terminal": (term._asdict().get("name") if term else "")}
    except Exception as e:                                  # pragma: no cover
        return {"ok": False, "error": str(e)}


def quote(symbol: str) -> Dict[str, Any]:
    """One MT5 tick snapshot for `symbol` (bid/ask/spread)."""
    if not _MT5_AVAILABLE:
        return {"ok": False, "error": "MT5 not available", "symbol": symbol}
    try:
        if not _mt5.symbol_select(symbol, True):
            return {"ok": False, "error": f"Symbol {symbol} not in Market Watch", "symbol": symbol}
        t = _mt5.symbol_info_tick(symbol)
        if t is None:
            return {"ok": False, "error": f"No tick for {symbol}", "symbol": symbol}
        bid, ask = float(t.bid), float(t.ask)
        last = float(getattr(t, "last", 0.0)) or bid
        return {"ok": True, "symbol": symbol, "bid": bid, "ask": ask,
                "last": last, "spread": round(ask - bid, 8), "source": "MT5"}
    except Exception as e:                                  # pragma: no cover
        return {"ok": False, "error": str(e), "symbol": symbol}


def quotes(symbols: List[str]) -> Dict[str, Dict[str, Any]]:
    return {s: quote(s) for s in symbols}


def shutdown() -> None:
    if _MT5_AVAILABLE:
        try:
            _mt5.shutdown()
        except Exception:
            pass


if __name__ == "__main__":
    print("MetaTrader5 available:", available())
    if available():
        print(connect())
        print(quote("XAUUSD"))
        shutdown()
