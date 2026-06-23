"""
generate_samples.py
Reproducibly build the demo OHLC CSVs shipped with FUTAS.

These are SYNTHETIC, deterministic series (fixed random seed) shaped to contain
clear market structure (trend + corrective pullback) so the FUTAS pipeline
demonstrates full BUY / SELL set-ups. They are illustrative data for scientific
testing, not real market quotes.
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def _ohlc_from_close(close, seed, wick=0.0035, start="2025-09-01", freq="D"):
    rng = np.random.default_rng(seed)
    close = np.asarray(close, dtype=float)
    open_ = np.concatenate([[close[0]], close[:-1]])
    span = np.maximum(np.abs(close - open_), close * 0.0015)
    high = np.maximum(open_, close) + rng.uniform(0.2, 1.0, len(close)) * span + close * wick * rng.uniform(0.2, 1.0, len(close))
    low = np.minimum(open_, close) - rng.uniform(0.2, 1.0, len(close)) * span - close * wick * rng.uniform(0.2, 1.0, len(close))
    vol = rng.integers(8_000, 40_000, len(close))
    t = pd.date_range(start, periods=len(close), freq=freq)
    return pd.DataFrame({
        "time": t.strftime("%Y-%m-%d"),
        "open": np.round(open_, 2), "high": np.round(high, 2),
        "low": np.round(low, 2), "close": np.round(close, 2), "volume": vol,
    })


def make_gold(n=140, seed=21):
    """Uptrend with higher highs / higher lows, ending in a corrective pull-back."""
    rng = np.random.default_rng(seed)
    base = 2350.0
    t = np.arange(n)
    up = np.linspace(0, 230, n)                 # primary uptrend
    swing = 28 * np.sin(t / 11.0)               # impulse/correction waves
    noise = np.cumsum(rng.normal(0, 1.0, n)) * 0.8
    close = base + up + swing + noise
    # final corrective pull-back into support (last ~12 bars drift down)
    close[-12:] = close[-13] - np.linspace(0, 42, 12) + rng.normal(0, 2.0, 12)
    return _ohlc_from_close(close, seed + 1, start="2025-09-01")


def make_btc(n=140, seed=33):
    """Downtrend (lower highs / lower lows) ending in a ~50% corrective bounce
    back UP into a mid-range Fibonacci Urvin resistance — a clean SELL set-up."""
    rng = np.random.default_rng(seed)
    nb = 12                                      # length of the final bounce
    n1 = n - nb
    t1 = np.arange(n1)
    down = np.linspace(92000.0, 74000.0, n1)     # primary downtrend
    swing = 1600 * np.sin(t1 / 10.0)             # LH/LL waves
    noise = np.cumsum(rng.normal(0, 1.0, n1)) * 55
    seg1 = down + swing + noise
    # smooth, low-noise corrective bounce up to just under the ~40% FU
    # resistance (keeps bias bearish, gives a clean high-R/R SELL toward the lows)
    seg2 = np.linspace(seg1[-1], 80800.0, nb) + rng.normal(0, 35, nb)
    close = np.concatenate([seg1, seg2])
    return _ohlc_from_close(close, seed + 1, start="2025-09-01")


if __name__ == "__main__":
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    g = make_gold(); g.to_csv(os.path.join(here, "XAUUSD_daily.csv"), index=False)
    b = make_btc(); b.to_csv(os.path.join(here, "BTCUSD_daily.csv"), index=False)
    print("wrote XAUUSD_daily.csv", g.shape, "and BTCUSD_daily.csv", b.shape)
