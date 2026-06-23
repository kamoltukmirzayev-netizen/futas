"""
futas_engine.py
===============================================================================
FUTAS — Fibonacci Urvin Adaptive Trading Analysis System
Scientific algorithmic core.

Dissertation:  "Technical analysis methods of international trade and trading
strategies of the digital economy and cryptocurrency (based on cryptocurrency
and gold assets)".
Specialization: 08.00.16 — Digital economy and international digital integration.

-------------------------------------------------------------------------------
SCIENTIFIC INNOVATION
-------------------------------------------------------------------------------
FUTAS does NOT use the classical Fibonacci retracement ratios. It uses the
transformed *Fibonacci Urvin adaptive coefficient system* — a fixed research
result of exactly 15 coefficients. Every price level in the whole system is
derived ONLY from these coefficients through the single linear projection:

        P = Low + (High - Low) * K

    P     — calculated price level
    High  — the high point of the selected range
    Low   — the low point of the selected range
    K     — a Fibonacci Urvin adaptive coefficient

No Entry / Stop-Loss / Take-Profit value is ever taken from an external source,
an old analysis, or a hard-coded number. Entries are taken from the live price,
and Stop-Loss / Take-Profit values are *selected only* from the 15 computed
Fibonacci Urvin levels.

This module is a scientific-research and algorithmic-testing instrument.
It does NOT provide financial advice.
===============================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any, Tuple

import math
import sys
import numpy as np
import pandas as pd

# =============================================================================
# 1. FIBONACCI URVIN ADAPTIVE COEFFICIENTS  (the scientific constant)
# -----------------------------------------------------------------------------
# Order is preserved exactly as derived in the dissertation research. These are
# the ONLY coefficients the entire system is allowed to use.
# =============================================================================
FU_COEFFICIENTS: List[float] = [
    1.0, 0.0, 0.5, 0.5993, -0.6993, 1.5993, -0.5993, 1.1987,
    1.6987, 1.7973, -0.1987, -0.0987, -0.7973, 0.3973, 1.0993,
]

# Immutable signature used for integrity checks (so a publication can prove that
# the deployed software used the unmodified research coefficients).
FU_COEFFICIENTS_FROZEN: Tuple[float, ...] = tuple(FU_COEFFICIENTS)
N_COEFFICIENTS: int = len(FU_COEFFICIENTS)  # == 15

# Canonical OHLC column names this engine works with internally.
CANONICAL_COLS = ["time", "open", "high", "low", "close", "volume"]

# =============================================================================
# 1b. PER-COEFFICIENT STRUCTURAL ROLES  (dissertation §3.2, Table 3.2.2)
# -----------------------------------------------------------------------------
# Each Fibonacci Urvin coefficient is not a geometric retracement ratio but a
# *structural reaction zone*. The roles below are taken verbatim from the
# dissertation's empirical classification (Jadval 3.2.2) plus the range anchors
# {0.0, 0.5, 1.0} described in the surrounding text. They label what each level
# MEANS structurally; they never change the price (P = Low + (High-Low)*K).
# =============================================================================
COEFFICIENT_ROLES: Dict[float, Tuple[str, str]] = {
    1.0:     ("Range high / supply cap",
              "Upper boundary of the selected range — structural supply ceiling "
              "where the measured impulse completes."),
    0.0:     ("Range low / demand base",
              "Lower boundary of the selected range — structural demand floor "
              "from which the impulse is measured."),
    0.5:     ("Equilibrium / structural-memory zone",
              "Not a classic 50% retracement but a structural-memory and "
              "liquidity-redistribution zone where continuation can be cancelled "
              "and a reversal prepared."),
    0.3973:  ("Intermediate impulse zone",
              "Temporary accumulation that forms a base for the next move."),
    0.5993:  ("Rising impulse zone",
              "Buyer activity increases and a sustained up-move forms."),
    1.0993:  ("Resistance zone",
              "Up-pace slows and selling pressure starts to build."),
    1.1987:  ("Strong resistance",
              "The up-move weakens and sellers become active."),
    1.5993:  ("Structural reversal zone",
              "High-impulse stage; probability of a trend change rises."),
    1.6987:  ("Expansion zone",
              "Over-extended rise with elevated market pressure."),
    1.7973:  ("Extreme resistance",
              "Sharp rejection; a downward correction tends to begin."),
    -0.0987: ("Short-term support",
              "Temporary stabilisation of price."),
    -0.1987: ("Support zone",
              "The downward move slows."),
    -0.5993: ("Strong recovery zone",
              "Selling pressure eases and recovery probability rises."),
    -0.6993: ("Structural support",
              "Lower impulse boundary of the structure."),
    -0.7973: ("Extreme volatility zone",
              "High-risk band with sharp price swings."),
}


def _role_for(k: float) -> Tuple[str, str]:
    """Return (role, technical description) for a coefficient (robust to float)."""
    for kk, rd in COEFFICIENT_ROLES.items():
        if abs(kk - k) < 1e-6:
            return rd
    return ("Structural zone", "Adaptive Fibonacci Urvin reaction zone.")


# =============================================================================
# 2. DATA STRUCTURES (returned as dataclasses -> easily serialised to dict)
# =============================================================================
@dataclass
class FULevel:
    """A single Fibonacci Urvin price level."""
    order: int          # original index 0..14 in FU_COEFFICIENTS
    k: float            # the coefficient
    price: float        # P = Low + (High - Low) * K
    percent: float      # K * 100  (the "depth/extension" in %)
    label: str          # human label, e.g. "FU 0.5993 (59.93%)"
    zone: str           # 'inside' | 'extension_up' | 'extension_down'
    role: str = ""      # filled relative to current price: support/resistance/at
    structural_role: str = ""   # dissertation Table 3.2.2 structural meaning
    role_desc: str = ""         # technical description of that structural role
    zone_low: float = 0.0       # lower bound of the dynamic liquidity band
    zone_high: float = 0.0      # upper bound of the dynamic liquidity band

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Swing:
    """A confirmed swing (fractal) point."""
    index: int
    time: Any
    price: float
    kind: str           # 'high' | 'low'


@dataclass
class StructureEvent:
    """One market-structure label attached to a swing."""
    index: int
    time: Any
    price: float
    label: str          # HH | HL | LH | LL | H | L
    event: str = "—"    # BOS-up | BOS-down | CHoCH-bull | CHoCH-bear | HL | LH


@dataclass
class Signal:
    """A trading/analytical signal fully derived from FU levels."""
    action: str                 # BUY | SELL | WAIT
    entry: Optional[float]
    stop_loss: Optional[float]
    take_profits: List[float]   # TP1, TP2, TP3 (FU levels only)
    rr: List[float]             # RR for each TP
    sl_level: Optional[FULevel] = None
    tp_levels: List[FULevel] = field(default_factory=list)
    confidence: str = "LOW"     # LOW | MEDIUM | HIGH
    confidence_score: float = 0.0
    reasons: List[str] = field(default_factory=list)


@dataclass
class FUTASResult:
    """Complete result of one FUTAS analysis pass."""
    asset: str
    n_bars: int
    high: float
    low: float
    range_size: float
    high_time: Any
    low_time: Any
    current_price: float
    levels: List[FULevel]
    swings: List[Swing]
    structure: List[StructureEvent]
    trend: str
    trend_metrics: Dict[str, Any]
    phase: str                  # IMPULSE | CORRECTION | RANGE
    signal: Signal
    explanation: str
    momentum: Dict[str, Any] = field(default_factory=dict)      # RSI/MACD (confirmation only)
    struct_conf: Dict[str, bool] = field(default_factory=dict)  # consecutive-structure flags
    market_phase: str = ""          # seven-phase model (Table 3.3.1)
    market_phase_next: str = ""     # empirically-expected next stage
    market_phase_note: str = ""     # plain-language description
    htf: Dict[str, Any] = field(default_factory=dict)  # higher-timeframe context (MTF filter)
    volume_conf: Dict[str, Any] = field(default_factory=dict)  # volume participation (confirmation only)
    coefficients: List[float] = field(default_factory=lambda: list(FU_COEFFICIENTS))

    # ---- serialisation helpers (for export / JSON / tables) ----
    def levels_table(self) -> pd.DataFrame:
        rows = [L.as_dict() for L in self.levels]
        df = pd.DataFrame(rows)
        return df[["order", "k", "percent", "price", "zone", "role",
                   "structural_role", "label"]]

    def signal_table(self) -> pd.DataFrame:
        s = self.signal
        data = {
            "Field": ["Action", "Entry", "Stop Loss",
                      "Take Profit 1", "Take Profit 2", "Take Profit 3",
                      "R/R (TP1)", "R/R (TP2)", "R/R (TP3)",
                      "Confidence"],
            "Value": [
                s.action,
                _fmt(s.entry), _fmt(s.stop_loss),
                _fmt(_get(s.take_profits, 0)), _fmt(_get(s.take_profits, 1)),
                _fmt(_get(s.take_profits, 2)),
                _fmt(_get(s.rr, 0), 2), _fmt(_get(s.rr, 1), 2),
                _fmt(_get(s.rr, 2), 2),
                f"{s.confidence} ({s.confidence_score:.0%})",
            ],
        }
        return pd.DataFrame(data)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # dataclasses inside lists are already converted by asdict
        return d


# =============================================================================
# 3. SMALL HELPERS
# =============================================================================
def _get(seq, i, default=None):
    return seq[i] if seq is not None and i < len(seq) else default


def _fmt(v, nd: int = 5) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    return f"{v:.{nd}f}"


def _label_for(k: float) -> str:
    return f"FU {k:+.4f} ({k*100:.2f}%)"


# =============================================================================
# 4. DATA INGEST / VALIDATION  (task 1: receive OHLC via CSV / manual / OCR)
# =============================================================================
_COLUMN_ALIASES = {
    "time": ["time", "date", "datetime", "timestamp", "date/time", "<date>", "<time>"],
    "open": ["open", "o", "<open>", "open price"],
    "high": ["high", "h", "<high>", "high price", "max"],
    "low": ["low", "l", "<low>", "low price", "min"],
    "close": ["close", "c", "<close>", "close price", "price", "adj close"],
    "volume": ["volume", "vol", "v", "<vol>", "<tickvol>", "tickvol"],
}


def normalize_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalise an arbitrary OHLC table to the canonical column names and types.
    Accepts many header conventions (TradingView, MT5, Binance, Yahoo, ...).
    """
    if df is None or len(df) == 0:
        raise ValueError("Empty data: no rows found.")

    lower_map = {str(c).strip().lower(): c for c in df.columns}
    rename = {}
    for canon, aliases in _COLUMN_ALIASES.items():
        for a in aliases:
            if a in lower_map:
                rename[lower_map[a]] = canon
                break
    out = df.rename(columns=rename).copy()

    # If a single Date and Time column exist separately, merge them.
    cols_lower = [str(c).strip().lower() for c in df.columns]
    if "time" not in out.columns and "date" in cols_lower and "time" in cols_lower:
        d = df[[c for c in df.columns if str(c).strip().lower() == "date"][0]].astype(str)
        t = df[[c for c in df.columns if str(c).strip().lower() == "time"][0]].astype(str)
        out["time"] = d + " " + t

    missing = [c for c in ["open", "high", "low", "close"] if c not in out.columns]
    if missing:
        raise ValueError(
            "OHLC columns not found: missing "
            + ", ".join(missing)
            + f". Detected columns: {list(df.columns)}"
        )

    for c in ["open", "high", "low", "close", "volume"]:
        if c in out.columns:
            out[c] = pd.to_numeric(
                out[c].astype(str).str.replace(",", "", regex=False),
                errors="coerce",
            )

    if "time" not in out.columns:
        out["time"] = np.arange(len(out))

    keep = [c for c in CANONICAL_COLS if c in out.columns]
    out = out[keep].dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)

    # Enforce OHLC validity: high>=max(open,close), low<=min(open,close)
    out["high"] = out[["high", "open", "close"]].max(axis=1)
    out["low"] = out[["low", "open", "close"]].min(axis=1)

    if len(out) == 0:
        raise ValueError("No valid OHLC rows after cleaning.")
    return out


# =============================================================================
# 4b. TIMEFRAME RESAMPLING  (multi-timeframe selector + higher-timeframe filter)
# -----------------------------------------------------------------------------
# A timeframe switch may only AGGREGATE UPWARD: a coarser candle is built from
# the finer candles inside it (open=first, high=max, low=min, close=last,
# volume=sum). Finer-than-native candles cannot be manufactured from coarser
# data without fabricating information, so the UI disables those timeframes for
# static data; live sources instead RE-FETCH at the requested interval.
#
# Note on labels: per the project spec the minute timeframes use an upper-case M
# (1M = 1 minute, 5M = 5 minutes, ...). They are NOT calendar months.
# =============================================================================
TIMEFRAMES: List[str] = ["1M", "5M", "15M", "30M", "1H", "4H", "1D", "1W"]
TIMEFRAME_RULES: Dict[str, str] = {
    "1M": "1min", "5M": "5min", "15M": "15min", "30M": "30min",
    "1H": "1h", "4H": "4h", "1D": "1D", "1W": "1W",
}
TIMEFRAME_SECONDS: Dict[str, float] = {
    "1M": 60.0, "5M": 300.0, "15M": 900.0, "30M": 1800.0,
    "1H": 3600.0, "4H": 14400.0, "1D": 86400.0, "1W": 604800.0,
}


def infer_interval_seconds(df: pd.DataFrame) -> Optional[float]:
    """Median spacing between bars in seconds, or None if `time` isn't datetime."""
    if "time" not in df.columns:
        return None
    t = pd.to_datetime(df["time"], errors="coerce").dropna()
    if t.size < 3:
        return None
    diffs = t.sort_values().diff().dropna().dt.total_seconds()
    diffs = diffs[diffs > 0]
    if diffs.empty:
        return None
    return float(diffs.median())


def native_timeframe(df: pd.DataFrame) -> Optional[str]:
    """Closest TIMEFRAMES label to the data's own bar spacing (None if unknown)."""
    sec = infer_interval_seconds(df)
    if sec is None:
        return None
    return min(TIMEFRAMES, key=lambda k: abs(TIMEFRAME_SECONDS[k] - sec))


def resample_ohlc(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """
    Aggregate a normalised OHLC frame UP to `timeframe` (a TIMEFRAMES label).

    Returns a new normalised frame. If the data has no usable timestamps, or the
    target is at/below the native interval, the input is returned unchanged — we
    never fabricate finer candles than the data actually contains.
    """
    d = normalize_ohlc(df)
    if timeframe not in TIMEFRAME_RULES:
        return d
    t = pd.to_datetime(d["time"], errors="coerce")
    if t.notna().sum() < 3:
        return d  # cannot time-resample without datetime stamps
    native_sec = infer_interval_seconds(d)
    if native_sec is not None and TIMEFRAME_SECONDS[timeframe] <= native_sec * 1.5:
        return d  # target is at/below native -> nothing to aggregate up to
    work = (d.assign(time=t).dropna(subset=["time"])
              .set_index("time").sort_index())
    agg: Dict[str, str] = {"open": "first", "high": "max", "low": "min", "close": "last"}
    if "volume" in work.columns:
        agg["volume"] = "sum"
    out = (work.resample(TIMEFRAME_RULES[timeframe], label="right", closed="right")
                .agg(agg).dropna(subset=["open", "high", "low", "close"]).reset_index())
    if len(out) < 2:
        return d
    return normalize_ohlc(out)


def available_timeframes(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    For a STATIC frame, report which timeframe buttons are valid. Each item is
    {tf, enabled, native, reason}. Only timeframes at/above the native bar
    spacing are enabled (you can aggregate up, never down).
    """
    native = native_timeframe(df)
    native_sec = infer_interval_seconds(df)
    items: List[Dict[str, Any]] = []
    for tf in TIMEFRAMES:
        if native_sec is None:
            enabled = (tf == "1D")  # unknown spacing: only the as-is view
            reason = "" if enabled else "Timestamps are not datetime; cannot resample by time."
            native_flag = enabled
        else:
            enabled = TIMEFRAME_SECONDS[tf] >= native_sec * 0.9
            reason = "" if enabled else f"Finer than the loaded data (~{native})."
            native_flag = (tf == native)
        items.append({"tf": tf, "enabled": bool(enabled),
                      "native": bool(native_flag), "reason": reason})
    return items


def htf_bias(df: pd.DataFrame, higher_tf: str,
             swing_left: int = 2, swing_right: int = 2) -> Dict[str, Any]:
    """
    Higher-timeframe structural context for a multi-timeframe filter (Tier 2).

    Resamples up to `higher_tf` and returns the HTF trend and structural bias so
    the base-timeframe signal can report alignment. This is *structural* context
    (not momentum), returned for the caller to apply as a filter / confidence
    note — it does not alter the FU formula or the 15 coefficients.
    """
    htf = resample_ohlc(df, higher_tf)
    if len(htf) < 6:
        return {"timeframe": higher_tf, "trend": "SIDEWAY", "bias": "neutral",
                "aligned_bull": False, "aligned_bear": False, "n_bars": len(htf)}
    sw = detect_swings(htf, left=swing_left, right=swing_right)
    structure = market_structure(sw)
    trend, _ = detect_trend(htf, sw)
    bias = structure_bias(structure)
    return {
        "timeframe": higher_tf,
        "trend": trend,
        "bias": bias,
        "aligned_bull": (trend == "UPTREND") or (bias == "bull"),
        "aligned_bear": (trend == "DOWNTREND") or (bias == "bear"),
        "n_bars": len(htf),
    }


def next_higher_timeframe(tf: str, steps: int = 2) -> str:
    """The timeframe `steps` positions coarser than `tf` (clamped to 1W)."""
    if tf not in TIMEFRAMES:
        return "1D"
    i = min(TIMEFRAMES.index(tf) + steps, len(TIMEFRAMES) - 1)
    return TIMEFRAMES[i]


# =============================================================================
# 5. RANGE DETECTION  (task 2: automatic High / Low)
# =============================================================================
def detect_range(
    df: pd.DataFrame, mode: str = "auto", lookback: int = 0
) -> Tuple[float, float, Any, Any]:
    """
    Determine the dominant High and Low of the selected range.

    mode='auto'      -> use the last `lookback` bars if given, else whole sample,
                        but anchored on the most recent significant swing window.
    mode='full'      -> whole dataset.
    mode='lookback'  -> strictly the last `lookback` bars.
    Returns (high, low, high_time, low_time).
    """
    if lookback and lookback > 0 and mode in ("auto", "lookback"):
        win = df.iloc[-lookback:]
    else:
        win = df

    hi_idx = win["high"].idxmax()
    lo_idx = win["low"].idxmin()
    high = float(win["high"].loc[hi_idx])
    low = float(win["low"].loc[lo_idx])
    return high, low, df["time"].loc[hi_idx], df["time"].loc[lo_idx]


# =============================================================================
# 6. FIBONACCI URVIN LEVELS  (task 3: the 15 adaptive levels)
# =============================================================================
def fu_levels(high: float, low: float, zone_halfwidth_pct: float = 0.0,
              coeffs: Optional[List[float]] = None) -> List[FULevel]:
    """
    Compute all 15 Fibonacci Urvin levels for the given range.

        P = Low + (High - Low) * K           for every K in FU_COEFFICIENTS

    `zone_halfwidth_pct` (dissertation §3.3 "dynamic liquidity zones"): each level
    is treated not as an infinitely thin line but as a reaction *band*
    [P - h, P + h] with h = |High-Low| * zone_halfwidth_pct. This reflects the
    empirical observation that price reacts to a zone around the level rather
    than to an exact tick. It NEVER changes the level price itself.

    `coeffs` is for BENCHMARKING ONLY (e.g. the classical-Fibonacci baseline used
    by `benchmark_compare`). It defaults to the frozen 15 Fibonacci Urvin
    coefficients, so the scientific guarantee — FUTAS uses only those 15 — is
    unchanged for every normal call. The frozen signature in
    `FU_COEFFICIENTS_FROZEN` still proves the default set is unmodified.
    """
    if not math.isfinite(high) or not math.isfinite(low):
        raise ValueError("High/Low must be finite numbers.")
    ks = list(coeffs) if coeffs is not None else FU_COEFFICIENTS
    rng = high - low
    half = abs(rng) * float(zone_halfwidth_pct)
    levels: List[FULevel] = []
    for order, k in enumerate(ks):
        price = low + rng * k
        if k > 1.0:
            zone = "extension_up"
        elif k < 0.0:
            zone = "extension_down"
        else:
            zone = "inside"
        srole, sdesc = _role_for(k)
        levels.append(
            FULevel(
                order=order,
                k=float(k),
                price=float(price),
                percent=float(k * 100.0),
                label=_label_for(k),
                zone=zone,
                structural_role=srole,
                role_desc=sdesc,
                zone_low=float(price - half),
                zone_high=float(price + half),
            )
        )
    return levels


def _assign_roles(levels: List[FULevel], current_price: float) -> None:
    """Tag each level as support / resistance / at-price relative to current."""
    for L in levels:
        if abs(L.price - current_price) < 1e-9:
            L.role = "at-price"
        elif L.price < current_price:
            L.role = "support"
        else:
            L.role = "resistance"


# =============================================================================
# 7. SWING DETECTION  (task 5: Swing High / Swing Low)
# =============================================================================
def detect_swings(df: pd.DataFrame, left: int = 2, right: int = 2) -> List[Swing]:
    """
    Fractal swing detection.

    A bar i is a Swing High if its high is the maximum of the window
    [i-left, i+right]; a Swing Low if its low is the minimum of that window.
    """
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    times = df["time"].to_numpy()
    n = len(df)
    swings: List[Swing] = []
    for i in range(left, n - right):
        wh = highs[i - left : i + right + 1]
        wl = lows[i - left : i + right + 1]
        if highs[i] == wh.max() and int(np.argmax(wh)) == left:
            swings.append(Swing(i, times[i], float(highs[i]), "high"))
        if lows[i] == wl.min() and int(np.argmin(wl)) == left:
            swings.append(Swing(i, times[i], float(lows[i]), "low"))
    swings.sort(key=lambda s: s.index)
    return swings


# =============================================================================
# 8. TREND DETECTION  (task 4: UPTREND / DOWNTREND / SIDEWAY)
# =============================================================================
def detect_trend(
    df: pd.DataFrame, swings: List[Swing]
) -> Tuple[str, Dict[str, Any]]:
    """
    Determine trend.

    Primary rule (market-structure based):
        UPTREND   if last 2 swing highs are higher AND last 2 swing lows higher
        DOWNTREND if last 2 swing highs lower  AND last 2 swing lows lower
        else      SIDEWAY
    Fallback / corroboration (when swings are insufficient): normalised slope of
    a linear regression on closes; |slope_norm| < SIDE_TH => SIDEWAY.
    """
    sh = [s for s in swings if s.kind == "high"]
    sl = [s for s in swings if s.kind == "low"]

    close = df["close"].to_numpy(dtype=float)
    n = len(close)
    x = np.arange(n)
    slope = float(np.polyfit(x, close, 1)[0]) if n >= 2 else 0.0
    rng = float(df["high"].max() - df["low"].min())
    slope_norm = (slope * n / rng) if rng > 0 else 0.0
    SIDE_TH = 0.30

    # ---- structure verdict (Smart-Money style: HH+HL / LH+LL) ----
    structure_verdict = "MIXED"
    if len(sh) >= 2 and len(sl) >= 2:
        hh = sh[-1].price > sh[-2].price
        hl = sl[-1].price > sl[-2].price
        lh = sh[-1].price < sh[-2].price
        ll = sl[-1].price < sl[-2].price
        if hh and hl:
            structure_verdict = "UPTREND"
        elif lh and ll:
            structure_verdict = "DOWNTREND"
        else:
            structure_verdict = "MIXED"

    # ---- slope verdict (linear regression on closes) ----
    if slope_norm > SIDE_TH:
        slope_verdict = "UPTREND"
    elif slope_norm < -SIDE_TH:
        slope_verdict = "DOWNTREND"
    else:
        slope_verdict = "SIDEWAY"

    # ---- reconcile the two filters ----
    if structure_verdict in ("UPTREND", "DOWNTREND"):
        if slope_verdict in (structure_verdict, "SIDEWAY"):
            trend, method = structure_verdict, "structure"
        else:
            # structure and slope disagree -> genuine inflection, no clear trend
            trend, method = "SIDEWAY", "structure/slope-conflict"
    else:
        trend = "UPTREND" if slope_verdict == "UPTREND" else \
                "DOWNTREND" if slope_verdict == "DOWNTREND" else "SIDEWAY"
        method = "slope"

    metrics = {
        "method": method,
        "structure_verdict": structure_verdict,
        "slope_verdict": slope_verdict,
        "slope": slope,
        "slope_norm": slope_norm,
        "n_swing_highs": len(sh),
        "n_swing_lows": len(sl),
        "side_threshold": SIDE_TH,
    }
    return trend, metrics


# =============================================================================
# 9. MARKET STRUCTURE  (tasks 6 & 7: HH/HL/LH/LL and turning points)
# =============================================================================
def market_structure(swings: List[Swing]) -> List[StructureEvent]:
    """
    Label every swing as HH / HL / LH / LL and detect structural turning points
    (Break Of Structure and Change Of Character).
    """
    events: List[StructureEvent] = []
    last_high: Optional[float] = None
    last_low: Optional[float] = None
    bias: Optional[str] = None  # 'bull' | 'bear'

    for s in swings:
        if s.kind == "high":
            if last_high is None:
                label = "H"
            elif s.price > last_high:
                label = "HH"
            else:
                label = "LH"
            last_high = s.price
        else:
            if last_low is None:
                label = "L"
            elif s.price > last_low:
                label = "HL"
            else:
                label = "LL"
            last_low = s.price

        event = "—"
        if label == "HH":
            event = "CHoCH-bull" if bias == "bear" else ("BOS-up" if bias == "bull" else "BOS-up")
            bias = "bull"
        elif label == "LL":
            event = "CHoCH-bear" if bias == "bull" else ("BOS-down" if bias == "bear" else "BOS-down")
            bias = "bear"
        elif label == "HL":
            event = "HL"
        elif label == "LH":
            event = "LH"

        events.append(StructureEvent(s.index, s.time, s.price, label, event))
    return events


def structure_bias(structure: List[StructureEvent]) -> str:
    """Most recent decisive bias from the structure sequence."""
    for e in reversed(structure):
        if e.event in ("BOS-up", "CHoCH-bull"):
            return "bull"
        if e.event in ("BOS-down", "CHoCH-bear"):
            return "bear"
    return "neutral"


# =============================================================================
# 10. IMPULSE / CORRECTION  (task 8)
# =============================================================================
def detect_phase(df: pd.DataFrame, swings: List[Swing], trend: str) -> str:
    """
    Classify the *current* leg as IMPULSE (aligned with trend) or CORRECTION
    (counter-trend retracement). In a non-trending market -> RANGE.
    """
    if not swings:
        return "RANGE"
    last = swings[-1]
    cur = float(df["close"].iloc[-1])
    leg_up = cur > last.price
    if trend == "UPTREND":
        return "IMPULSE" if leg_up else "CORRECTION"
    if trend == "DOWNTREND":
        return "IMPULSE" if not leg_up else "CORRECTION"
    return "RANGE"


# =============================================================================
# 10b. MOMENTUM — CONFIRMATION ONLY  (dissertation §3.2)
# -----------------------------------------------------------------------------
# IMPORTANT SCIENTIFIC RULE. In the dissertation the momentum oscillators
# (RSI, MACD) are explicitly *confirmation* instruments: they may strengthen or
# weaken the confidence of a structure-based decision, but they NEVER create a
# signal on their own and they NEVER override market structure or the Fibonacci
# Urvin levels. The functions below therefore only *report* momentum; the gate
# in generate_signal() is driven by structure, not by these values.
# =============================================================================
def compute_rsi(close: np.ndarray, period: int = 14) -> np.ndarray:
    """Wilder's RSI. Returns an array aligned to `close` (NaN until warmed up)."""
    close = np.asarray(close, dtype=float)
    n = close.size
    out = np.full(n, np.nan)
    if n < period + 1:
        return out
    delta = np.diff(close)
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    avg_gain = gain[:period].mean()
    avg_loss = loss[:period].mean()
    for i in range(period, n):
        g = gain[i - 1]
        l = loss[i - 1]
        avg_gain = (avg_gain * (period - 1) + g) / period
        avg_loss = (avg_loss * (period - 1) + l) / period
        rs = (avg_gain / avg_loss) if avg_loss > 0 else np.inf
        out[i] = 100.0 - 100.0 / (1.0 + rs)
    return out


def _ema(x: np.ndarray, span: int) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    if x.size == 0:
        return x
    alpha = 2.0 / (span + 1.0)
    out = np.empty_like(x)
    out[0] = x[0]
    for i in range(1, x.size):
        out[i] = alpha * x[i] + (1 - alpha) * out[i - 1]
    return out


def compute_macd(close: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9):
    """Return (macd_line, signal_line, histogram) aligned to `close`."""
    close = np.asarray(close, dtype=float)
    if close.size == 0:
        e = np.array([])
        return e, e, e
    macd_line = _ema(close, fast) - _ema(close, slow)
    signal_line = _ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def compute_atr(df: pd.DataFrame, period: int = 14) -> np.ndarray:
    """Average True Range (Wilder). Aligned to the frame, NaN until warmed up."""
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    close = df["close"].to_numpy(dtype=float)
    n = len(df)
    out = np.full(n, np.nan)
    if n < 2:
        return out
    prev_close = np.concatenate([[close[0]], close[:-1]])
    tr = np.maximum.reduce([
        high - low,
        np.abs(high - prev_close),
        np.abs(low - prev_close),
    ])
    if n <= period:
        out[-1] = float(np.mean(tr))
        return out
    atr = float(np.mean(tr[1:period + 1]))
    out[period] = atr
    for i in range(period + 1, n):
        atr = (atr * (period - 1) + tr[i]) / period
        out[i] = atr
    return out


def momentum_state(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Read RSI + MACD at the last bar and report whether momentum *confirms* a
    bullish or bearish structural reading. Confirmation only — never a trigger.
    """
    close = df["close"].to_numpy(dtype=float)
    rsi = compute_rsi(close)
    macd_line, signal_line, hist = compute_macd(close)

    rsi_last = float(rsi[-1]) if rsi.size and not math.isnan(rsi[-1]) else float("nan")
    macd_last = float(macd_line[-1]) if macd_line.size else float("nan")
    sig_last = float(signal_line[-1]) if signal_line.size else float("nan")
    hist_last = float(hist[-1]) if hist.size else float("nan")
    hist_prev = float(hist[-2]) if hist.size >= 2 else float("nan")

    # confirmation booleans (mild, symmetric thresholds)
    confirms_bull = bool(
        (not math.isnan(rsi_last) and rsi_last >= 50.0)
        and (not math.isnan(hist_last) and hist_last > 0.0)
    )
    confirms_bear = bool(
        (not math.isnan(rsi_last) and rsi_last <= 50.0)
        and (not math.isnan(hist_last) and hist_last < 0.0)
    )
    # is the histogram shrinking in magnitude -> momentum weakening?
    weakening = bool(
        not math.isnan(hist_last) and not math.isnan(hist_prev)
        and abs(hist_last) < abs(hist_prev)
    )
    overbought = bool(not math.isnan(rsi_last) and rsi_last >= 70.0)
    oversold = bool(not math.isnan(rsi_last) and rsi_last <= 30.0)

    return {
        "rsi": rsi_last,
        "macd": macd_last,
        "signal": sig_last,
        "hist": hist_last,
        "hist_prev": hist_prev,
        "confirms_bull": confirms_bull,
        "confirms_bear": confirms_bear,
        "weakening": weakening,
        "overbought": overbought,
        "oversold": oversold,
    }


# =============================================================================
# 10b-ii. VOLUME CONFIRMATION  (Tier 2 — liquidity participation layer)
# -----------------------------------------------------------------------------
# Volume is a confirmation, never a trigger: a set-up backed by above-average
# participation is more trustworthy than one on thin volume. Like momentum it
# only adjusts confidence; it does not create or veto a signal.
# =============================================================================
def volume_confirmation(df: pd.DataFrame, lookback: int = 20) -> Dict[str, Any]:
    """
    Compare the latest bar's volume to its recent average. Returns
    {available, confirms, ratio, status, last, avg}. If the data carries no
    usable volume, available=False and it simply does not contribute.
    """
    if "volume" not in df.columns:
        return {"available": False, "confirms": False, "ratio": 0.0, "status": "no volume"}
    vol = pd.to_numeric(df["volume"], errors="coerce").to_numpy(dtype=float)
    vol = vol[~np.isnan(vol)]
    if vol.size < 3 or float(np.nansum(vol)) <= 0:
        return {"available": False, "confirms": False, "ratio": 0.0, "status": "no volume"}
    last = float(vol[-1])
    ref = vol[-(lookback + 1):-1] if vol.size > lookback else vol[:-1]
    avg = float(np.nanmean(ref)) if ref.size else last
    ratio = (last / avg) if avg > 0 else 1.0
    if ratio >= 1.5:
        status = "high"
    elif ratio >= 1.2:
        status = "above-average"
    elif ratio >= 0.8:
        status = "average"
    else:
        status = "low"
    return {"available": True, "confirms": bool(ratio >= 1.2), "ratio": round(ratio, 2),
            "status": status, "last": last, "avg": round(avg, 2)}


# =============================================================================
# 10c. STRUCTURAL CONFIRMATION  (dissertation §3.2 — "single point is not enough")
# -----------------------------------------------------------------------------
# The dissertation insists that a single swing is not a confirmation: a bullish
# context needs at least two consecutive higher structural points (HH followed
# by HL, or vice-versa) and a bearish context needs two consecutive lower points
# (LH + LL). This gate is what makes generate_signal() open a position; momentum
# only adjusts the confidence afterwards.
# =============================================================================
def structure_confirmed(structure: List[StructureEvent]) -> Dict[str, bool]:
    """Return {'bull': bool, 'bear': bool} from the last few structure labels."""
    labels = [e.label for e in structure if e.label in ("HH", "HL", "LH", "LL")]
    bull = False
    bear = False
    if len(labels) >= 2:
        last2 = set(labels[-2:])
        bull = last2 == {"HH", "HL"} or labels[-2:] == ["HH", "HL"] or labels[-2:] == ["HL", "HH"]
        bear = last2 == {"LH", "LL"} or labels[-2:] == ["LH", "LL"] or labels[-2:] == ["LL", "LH"]
    # a longer run of same-direction labels also counts
    if len(labels) >= 2:
        if labels[-1] in ("HH", "HL") and labels[-2] in ("HH", "HL"):
            bull = True
        if labels[-1] in ("LH", "LL") and labels[-2] in ("LH", "LL"):
            bear = True
    return {"bull": bool(bull), "bear": bool(bear)}


# =============================================================================
# 10d. SEVEN-PHASE STRUCTURAL MODEL  (dissertation §3.3, Table 3.3.1)
# -----------------------------------------------------------------------------
# A richer, descriptive lifecycle than the 3-state IMPULSE/CORRECTION/RANGE used
# by the signal logic. It narrates *where in the structural cycle* the market is
# and what the empirically-expected next stage is. Purely descriptive — the
# trade gate still uses detect_phase()/structure.
# =============================================================================
SEVEN_PHASES: List[str] = [
    "Impulse continuation",     # trend extends with confirming momentum
    "Volatility expansion",     # range/ATR widens sharply
    "Liquidity concentration",  # compression / accumulation before a move
    "Momentum weakening",       # impulse intact but momentum fades (divergence)
    "Structural rejection",     # a level/zone rejects price (CHoCH risk)
    "Reversal move",            # structure flips (CHoCH confirmed)
    "Corrective stabilization", # counter-trend pullback settling before continuation
]


def market_phase(
    df: pd.DataFrame,
    swings: List[Swing],
    structure: List[StructureEvent],
    trend: str,
    momentum: Dict[str, Any],
) -> Tuple[str, str, str]:
    """
    Place the current state on the dissertation's seven-phase cycle.

    Returns (phase_name, expected_next_phase, note).
    """
    n = len(df)
    if n < 5 or not swings:
        return ("Liquidity concentration", "Impulse continuation",
                "Too few structural points yet; market is building liquidity.")

    phase3 = detect_phase(df, swings, trend)
    last_event = next((e.event for e in reversed(structure)
                       if e.event in ("BOS-up", "BOS-down", "CHoCH-bull", "CHoCH-bear")), "—")
    weakening = bool(momentum.get("weakening"))
    overbought = bool(momentum.get("overbought"))
    oversold = bool(momentum.get("oversold"))

    # volatility expansion: latest ATR well above its own median
    atr = compute_atr(df)
    vol_expansion = False
    finite_atr = atr[~np.isnan(atr)]
    if finite_atr.size >= 5:
        med = float(np.median(finite_atr))
        if med > 0 and float(finite_atr[-1]) >= 1.6 * med:
            vol_expansion = True

    # --- decision tree, ordered from most decisive to least ---
    if last_event in ("CHoCH-bull", "CHoCH-bear"):
        nxt = "Corrective stabilization"
        return ("Reversal move", nxt,
                f"Structure changed character ({last_event}); a new directional leg is forming.")

    if trend in ("UPTREND", "DOWNTREND") and phase3 == "IMPULSE":
        if weakening or (trend == "UPTREND" and overbought) or (trend == "DOWNTREND" and oversold):
            return ("Momentum weakening", "Structural rejection",
                    "Trend still intact but momentum is fading — watch for a rejection.")
        if vol_expansion:
            return ("Volatility expansion", "Liquidity concentration",
                    "Range is expanding sharply as the impulse accelerates.")
        return ("Impulse continuation", "Volatility expansion",
                "Trend and momentum agree; the dominant impulse is extending.")

    if phase3 == "CORRECTION":
        return ("Corrective stabilization", "Impulse continuation",
                "Counter-trend pullback is stabilising before the trend resumes.")

    # RANGE / sideways
    if vol_expansion:
        return ("Volatility expansion", "Liquidity concentration",
                "Sideways but volatile — wide swings without a directional structure.")
    return ("Liquidity concentration", "Impulse continuation",
            "Compression / accumulation; liquidity is building for the next impulse.")


# =============================================================================
# 11. SIGNAL GENERATION + RISK MANAGEMENT
#     (tasks 9-14: integrate structure with FU levels, BUY/SELL/WAIT,
#      entry from current price, SL & TP selected ONLY from FU levels, R/R)
# =============================================================================
def generate_signal(
    current_price: float,
    levels: List[FULevel],
    trend: str,
    bias: str,
    phase: str,
    range_size: float,
    tol_pct: float = 0.06,
    min_rr: float = 1.0,
    struct_conf: Optional[Dict[str, bool]] = None,
    momentum: Optional[Dict[str, Any]] = None,
    volume: Optional[Dict[str, Any]] = None,
    htf: Optional[Dict[str, Any]] = None,
) -> Signal:
    """
    Build a signal by integrating trend + market structure + the FU levels.

    Rules
    -----
    BUY  : bullish context (UPTREND, or bullish structure that is *confirmed* by
           consecutive HH+HL) AND price sitting on / pulling back to a Fibonacci
           Urvin support (correction into support).
           Entry = current price.
           Stop-Loss = the next FU level *below* that support.
           TP1/2/3   = the next three FU levels *above* the price.
    SELL : mirror image for a bearish context.
    WAIT : sideways market, no actionable FU level nearby, missing SL/TP, or
           Risk/Reward below `min_rr`.

    Scientific note (dissertation §3.2): a *single* structural point is not a
    confirmation — a bias-only context must be backed by consecutive structure
    (`struct_conf`). Momentum (`momentum`) is confirmation only: it tunes the
    confidence score and the narration but never creates or vetoes the trade.
    """
    sc = struct_conf or {}
    conf_bull = bool(sc.get("bull", False))
    conf_bear = bool(sc.get("bear", False))
    mom = momentum or {}
    vol = volume or {}
    htf_ctx = htf or {}

    prices = sorted(L.price for L in levels)
    by_price = {round(L.price, 10): L for L in levels}
    tol = tol_pct * range_size if range_size > 0 else 0.0

    below = [p for p in prices if p <= current_price + 1e-9]
    above = [p for p in prices if p >= current_price - 1e-9]
    support_p = below[-1] if below else None
    resistance_p = above[0] if above else None

    near_support = support_p is not None and abs(current_price - support_p) <= tol
    near_resistance = resistance_p is not None and abs(current_price - resistance_p) <= tol

    # A trend (UP/DOWN) already implies consecutive HH+HL / LH+LL inside
    # detect_trend(); a *bias-only* context must be confirmed by struct_conf.
    bull = (trend == "UPTREND") or (bias == "bull" and conf_bull)
    bear = (trend == "DOWNTREND") or (bias == "bear" and conf_bear)

    reasons: List[str] = []
    action = "WAIT"
    entry = float(current_price)
    sl: Optional[float] = None
    tps: List[float] = []

    if bull and not bear and (near_support or phase == "CORRECTION"):
        action = "BUY"
        if support_p is not None:
            i = prices.index(support_p)
            sl = prices[i - 1] if i - 1 >= 0 else None
        tps = [p for p in prices if p > current_price + 1e-9][:3]
        reasons.append(f"Bullish context (trend={trend}, structure={bias}).")
        if trend != "UPTREND" and conf_bull:
            reasons.append("Structural confirmation: consecutive higher structure "
                           "(HH + HL) validates the bullish bias — a single point is "
                           "not treated as confirmation.")
        reasons.append(
            f"Price is at/above Fibonacci Urvin support {support_p:.5f}"
            + (" (within tolerance band)." if near_support else " during a corrective pull-back.")
        )
        if mom.get("confirms_bull"):
            reasons.append(
                f"Momentum confirms the side (RSI={mom.get('rsi', float('nan')):.1f} ≥ 50, "
                "MACD histogram positive) — confirmation only, not the trigger."
            )
        elif mom.get("weakening"):
            reasons.append("Momentum is fading (histogram contracting); confirmation is "
                           "partial, so confidence is reduced rather than the trade vetoed.")

    elif bear and not bull and (near_resistance or phase == "CORRECTION"):
        action = "SELL"
        if resistance_p is not None:
            i = prices.index(resistance_p)
            sl = prices[i + 1] if i + 1 < len(prices) else None
        tps = [p for p in prices if p < current_price - 1e-9][::-1][:3]
        reasons.append(f"Bearish context (trend={trend}, structure={bias}).")
        if trend != "DOWNTREND" and conf_bear:
            reasons.append("Structural confirmation: consecutive lower structure "
                           "(LH + LL) validates the bearish bias — a single point is "
                           "not treated as confirmation.")
        reasons.append(
            f"Price is at/below Fibonacci Urvin resistance {resistance_p:.5f}"
            + (" (within tolerance band)." if near_resistance else " during a corrective bounce.")
        )
        if mom.get("confirms_bear"):
            reasons.append(
                f"Momentum confirms the side (RSI={mom.get('rsi', float('nan')):.1f} ≤ 50, "
                "MACD histogram negative) — confirmation only, not the trigger."
            )
        elif mom.get("weakening"):
            reasons.append("Momentum is fading (histogram contracting); confirmation is "
                           "partial, so confidence is reduced rather than the trade vetoed.")
    else:
        reasons.append(
            f"No aligned set-up: trend={trend}, structure={bias}, phase={phase}. "
            "Market structure and Fibonacci Urvin levels do not agree on a side."
        )

    # ---- Risk / Reward (task 14) ----
    rr: List[float] = []
    if action == "BUY" and sl is not None and sl < entry and tps:
        risk = entry - sl
        rr = [round((tp - entry) / risk, 4) for tp in tps] if risk > 0 else []
    elif action == "SELL" and sl is not None and sl > entry and tps:
        risk = sl - entry
        rr = [round((entry - tp) / risk, 4) for tp in tps] if risk > 0 else []

    # ---- validity gate -> downgrade to WAIT when risk management is impossible
    if action in ("BUY", "SELL"):
        if sl is None or not tps or not rr:
            reasons.append("Downgraded to WAIT: no valid FU Stop-Loss / Take-Profit available at this price.")
            action = "WAIT"
        elif rr[0] < min_rr:
            reasons.append(f"Downgraded to WAIT: Risk/Reward for TP1 ({rr[0]:.2f}) below minimum {min_rr:.2f}.")
            action = "WAIT"

    # ---- confidence score ----
    # Structure-driven base (trend + structure + phase + level reaction + R/R),
    # then momentum acts ONLY as a small confirmation modifier (dissertation §3.2).
    score = 0.0
    if action in ("BUY", "SELL"):
        score += 0.30 if (trend in ("UPTREND", "DOWNTREND")) else 0.0
        score += 0.20 if (bias in ("bull", "bear")) else 0.0
        # consecutive structural confirmation is worth more than a single point
        if (action == "BUY" and conf_bull) or (action == "SELL" and conf_bear):
            score += 0.12
        score += 0.18 if phase == "CORRECTION" else (0.05 if phase == "IMPULSE" else 0.0)
        if (action == "BUY" and near_support) or (action == "SELL" and near_resistance):
            score += 0.10
        if rr:
            score += min(0.10, 0.05 * rr[0])
        # momentum: confirmation only -> small bonus / small penalty, never a gate
        mom_confirms = (action == "BUY" and mom.get("confirms_bull")) or \
                       (action == "SELL" and mom.get("confirms_bear"))
        if mom_confirms:
            score += 0.08
        elif mom.get("weakening"):
            score -= 0.05
        # volume: confirmation only -> small bonus for above-average participation
        if vol.get("available") and vol.get("confirms"):
            score += 0.06
        # higher-timeframe alignment: confirmation only -> small bonus / penalty
        if htf_ctx.get("timeframe"):
            if (action == "BUY" and htf_ctx.get("aligned_bull")) or \
               (action == "SELL" and htf_ctx.get("aligned_bear")):
                score += 0.06
            elif (action == "BUY" and htf_ctx.get("aligned_bear")) or \
                 (action == "SELL" and htf_ctx.get("aligned_bull")):
                score -= 0.05
    score = round(min(max(score, 0.0), 1.0), 3)
    conf = "HIGH" if score >= 0.7 else ("MEDIUM" if score >= 0.45 else "LOW")

    sl_level = by_price.get(round(sl, 10)) if sl is not None else None
    tp_levels = [by_price.get(round(p, 10)) for p in tps]
    tp_levels = [t for t in tp_levels if t is not None]

    return Signal(
        action=action,
        entry=entry if action != "WAIT" else float(current_price),
        stop_loss=sl if action in ("BUY", "SELL") else None,
        take_profits=tps if action in ("BUY", "SELL") else [],
        rr=rr if action in ("BUY", "SELL") else [],
        sl_level=sl_level if action in ("BUY", "SELL") else None,
        tp_levels=tp_levels if action in ("BUY", "SELL") else [],
        confidence=conf,
        confidence_score=score,
        reasons=reasons,
    )


# =============================================================================
# 12. SCIENTIFIC EXPLANATION  (tasks 15 & 17)
# =============================================================================
def scientific_explanation(res: "FUTASResult") -> str:
    """Generate a structured, dissertation-grade textual justification."""
    s = res.signal
    lines: List[str] = []
    lines.append(f"FUTAS scientific interpretation — asset: {res.asset}")
    lines.append("=" * 64)
    lines.append(
        f"Selected range: High = {res.high:.5f}, Low = {res.low:.5f} "
        f"(range = {res.range_size:.5f}). Current price = {res.current_price:.5f}."
    )
    lines.append(
        f"The 15 Fibonacci Urvin adaptive levels were projected with "
        f"P = Low + (High - Low) * K. No external or pre-set price was used."
    )
    lines.append("")
    lines.append(f"1) TREND  →  {res.trend}")
    tm = res.trend_metrics
    lines.append(
        f"   Determined by {tm['method']} analysis "
        f"(swing highs={tm['n_swing_highs']}, swing lows={tm['n_swing_lows']}, "
        f"normalised slope={tm['slope_norm']:.3f})."
    )
    lines.append("")
    lines.append("2) MARKET STRUCTURE")
    if res.structure:
        tail = res.structure[-4:]
        seq = " → ".join(f"{e.label}" for e in tail)
        lines.append(f"   Latest structure sequence: {seq}")
        turns = [e for e in res.structure if e.event in ("BOS-up", "BOS-down", "CHoCH-bull", "CHoCH-bear")]
        if turns:
            last_turn = turns[-1]
            lines.append(
                f"   Last structural turning point: {last_turn.event} at "
                f"{last_turn.price:.5f}."
            )
    else:
        lines.append("   Not enough confirmed swings for a structural read.")
    sc = res.struct_conf or {}
    if sc.get("bull"):
        lines.append("   Structural confirmation: consecutive higher structure (HH + HL).")
    elif sc.get("bear"):
        lines.append("   Structural confirmation: consecutive lower structure (LH + LL).")
    else:
        lines.append("   Structural confirmation: none yet (a single swing is not a confirmation).")
    lines.append(f"   Current leg (3-state): {res.phase}.")
    if res.market_phase:
        lines.append(
            f"   Seven-phase model (Table 3.3.1): {res.market_phase} "
            f"→ expected next: {res.market_phase_next}."
        )
        lines.append(f"   {res.market_phase_note}")
    lines.append("")
    lines.append("2b) MOMENTUM (confirmation only — never a trigger)")
    m = res.momentum or {}
    if m:
        rsi = m.get("rsi", float("nan"))
        hist = m.get("hist", float("nan"))
        rsi_txt = f"{rsi:.1f}" if isinstance(rsi, (int, float)) and not math.isnan(rsi) else "—"
        hist_txt = f"{hist:+.5f}" if isinstance(hist, (int, float)) and not math.isnan(hist) else "—"
        confirm = ("bullish" if m.get("confirms_bull") else
                   "bearish" if m.get("confirms_bear") else "neutral")
        extra = []
        if m.get("overbought"):
            extra.append("overbought")
        if m.get("oversold"):
            extra.append("oversold")
        if m.get("weakening"):
            extra.append("weakening")
        extra_txt = (" [" + ", ".join(extra) + "]") if extra else ""
        lines.append(
            f"   RSI(14) = {rsi_txt}, MACD histogram = {hist_txt} → momentum is "
            f"{confirm}{extra_txt}. Per the methodology this only tunes the "
            f"confidence; the trade itself is decided by structure and FU levels."
        )
    else:
        lines.append("   Momentum unavailable (series too short).")
    lines.append("")
    lines.append(f"3) SIGNAL  →  {s.action}")
    for r in s.reasons:
        lines.append(f"   • {r}")

    if s.action in ("BUY", "SELL"):
        lines.append("")
        lines.append("4) RISK MANAGEMENT (values selected only from FU levels)")
        lines.append(f"   Entry (from current price): {s.entry:.5f}")
        if s.sl_level is not None:
            lines.append(f"   Stop-Loss : {s.stop_loss:.5f}  [{s.sl_level.label}]")
        for i, tpL in enumerate(s.tp_levels):
            rr = s.rr[i] if i < len(s.rr) else float("nan")
            lines.append(f"   Take-Profit {i+1}: {tpL.price:.5f}  [{tpL.label}]  R/R = {rr:.2f}")
        if s.rr:
            lines.append(
                f"   The set-up offers a primary Risk/Reward of {s.rr[0]:.2f} : 1."
            )
        lines.append(f"   Confidence: {s.confidence} ({s.confidence_score:.0%}).")
        why = "BUY" if s.action == "BUY" else "SELL"
        lines.append("")
        lines.append(f"   WHY {why}: The bullish/bearish trend, the supporting market"
                     if s.action == "BUY" else
                     f"   WHY {why}: The bearish trend, the supporting market")
        lines.append(
            "   structure and the price reaction at a Fibonacci Urvin level "
            "coincide, while the protective Stop-Loss and the profit targets are "
            "themselves Fibonacci Urvin levels, giving an internally consistent, "
            "self-similar risk geometry."
        )
    else:
        lines.append("")
        lines.append("4) WHY WAIT")
        lines.append(
            "   The three analytical filters (trend, market structure, Fibonacci "
            "Urvin level reaction) are not simultaneously aligned, or no valid "
            "FU-based Stop-Loss / Take-Profit with acceptable Risk/Reward exists. "
            "Under the FUTAS methodology a position is opened only on full "
            "confluence; therefore the scientifically correct action is to wait."
        )
    lines.append("")
    lines.append(
        "NOTE: FUTAS is a scientific-research and algorithmic-testing instrument. "
        "It does not constitute financial advice."
    )
    return "\n".join(lines)


# =============================================================================
# 13. ORCHESTRATION  (the full pipeline, task: return result dataclass/dict)
# =============================================================================
def analyze(
    data: pd.DataFrame,
    asset: str = "ASSET",
    current_price: Optional[float] = None,
    lookback: int = 0,
    swing_left: int = 2,
    swing_right: int = 2,
    tol_pct: float = 0.06,
    min_rr: float = 1.0,
    range_mode: str = "auto",
    with_htf: bool = True,
    higher_tf: Optional[str] = None,
    coeffs: Optional[List[float]] = None,
) -> FUTASResult:
    """
    Run the complete FUTAS pipeline:

        Data → High/Low → FU levels → Swings → Trend → Structure →
        Phase → Signal (+ SL/TP/RR) → Scientific explanation.
    """
    df = normalize_ohlc(data)

    high, low, hi_t, lo_t = detect_range(df, mode=range_mode, lookback=lookback)
    rng = high - low
    if rng <= 0:
        raise ValueError("Degenerate range (High <= Low); cannot compute levels.")

    cp = float(current_price) if current_price is not None else float(df["close"].iloc[-1])

    # dynamic liquidity bands: half a tolerance-width around each level
    levels = fu_levels(high, low, zone_halfwidth_pct=tol_pct * 0.5, coeffs=coeffs)
    _assign_roles(levels, cp)

    swings = detect_swings(df, left=swing_left, right=swing_right)
    trend, tmetrics = detect_trend(df, swings)
    structure = market_structure(swings)
    bias = structure_bias(structure)
    phase = detect_phase(df, swings, trend)

    momentum = momentum_state(df)
    volume_conf = volume_confirmation(df)
    struct_conf = structure_confirmed(structure)
    mphase, mphase_next, mphase_note = market_phase(df, swings, structure, trend, momentum)

    # higher-timeframe structural context (multi-timeframe filter, Tier 2).
    # Computed only when the data carries datetime stamps; never gates the signal
    # here — exposed for display and an optional UI alignment filter.
    htf_context: Dict[str, Any] = {}
    if with_htf:
        base_tf = native_timeframe(df)
        if base_tf is not None:
            tf_up = higher_tf or next_higher_timeframe(base_tf, steps=2)
            if tf_up != base_tf:
                try:
                    htf_context = htf_bias(df, tf_up,
                                           swing_left=swing_left, swing_right=swing_right)
                    htf_context["base_timeframe"] = base_tf
                except Exception:
                    htf_context = {}

    signal = generate_signal(
        current_price=cp,
        levels=levels,
        trend=trend,
        bias=bias,
        phase=phase,
        range_size=rng,
        tol_pct=tol_pct,
        min_rr=min_rr,
        struct_conf=struct_conf,
        momentum=momentum,
        volume=volume_conf,
        htf=htf_context,
    )

    result = FUTASResult(
        asset=asset,
        n_bars=len(df),
        high=high,
        low=low,
        range_size=rng,
        high_time=hi_t,
        low_time=lo_t,
        current_price=cp,
        levels=levels,
        swings=swings,
        structure=structure,
        trend=trend,
        trend_metrics={**tmetrics, "structure_bias": bias},
        phase=phase,
        signal=signal,
        explanation="",
        momentum=momentum,
        struct_conf=struct_conf,
        market_phase=mphase,
        market_phase_next=mphase_next,
        market_phase_note=mphase_note,
        htf=htf_context,
        volume_conf=volume_conf,
    )
    result.explanation = scientific_explanation(result)
    return result


def signal_narrative(res: "FUTASResult") -> Dict[str, str]:
    """
    Plain-language scenario / reason-for-entry / invalidation for a signal — used
    by the Telegram alert and the UI so a reader can decide quickly.
    """
    s = res.signal
    if s.action not in ("BUY", "SELL"):
        return {"scenario": "No confirmed set-up — structure and Fibonacci Urvin "
                            "levels do not currently agree on a side.",
                "reason": "—", "invalidation": "—"}
    mom = res.momentum or {}
    vol = res.volume_conf or {}
    htf = res.htf or {}
    bias = (res.trend_metrics or {}).get("structure_bias", "—")
    lvlword = "support" if s.action == "BUY" else "resistance"
    scenario = (f"{res.asset} is in a '{res.market_phase or res.phase}' phase with a {bias} "
                f"structure; price is reacting to a Fibonacci Urvin {lvlword} zone, "
                f"favouring a {s.action} continuation.")
    bits = [f"price at a Fibonacci Urvin {lvlword} level"]
    if (s.action == "BUY" and res.struct_conf.get("bull")) or \
       (s.action == "SELL" and res.struct_conf.get("bear")):
        bits.append("market structure confirmed ("
                    + ("HH+HL" if s.action == "BUY" else "LH+LL") + ")")
    rsi = mom.get("rsi")
    if isinstance(rsi, (int, float)) and rsi == rsi:
        bits.append(f"RSI {rsi:.0f}"
                    + (" weakening" if mom.get("weakening") else ""))
    if vol.get("available"):
        bits.append(f"volume {vol.get('status')}")
    if htf.get("timeframe"):
        aligned = ((s.action == "BUY" and htf.get("aligned_bull")) or
                   (s.action == "SELL" and htf.get("aligned_bear")))
        bits.append(f"higher timeframe {htf['timeframe']} "
                    + ("supports" if aligned else "is mixed vs") + " the direction")
    reason = "; ".join(bits) + "."
    sl = s.stop_loss
    if sl is not None:
        direction = "below" if s.action == "BUY" else "above"
        invalid = f"Signal becomes invalid if price closes {direction} the Stop-Loss {sl:.6g}."
    else:
        invalid = "—"
    return {"scenario": scenario, "reason": reason, "invalidation": invalid}


# =============================================================================
# 14. BACKTEST  (task 16/17 + reproduces the MT5-style report in the brief)
# -----------------------------------------------------------------------------
# A deterministic, event-driven test of the FUTAS rules over history so the app
# can output a trades table + summary statistics + equity curve, exactly like
# the MetaTrader strategy report supplied as the target output.
# =============================================================================
def _resolve_trade(df: pd.DataFrame, entry_i: int, sg: "Signal", max_hold: int,
                   total_cost_bps: float, tp_management: str,
                   tp_weights: Any, breakeven: bool, trailing: bool,
                   balance: float, risk_per_trade: float, asset: str) -> Optional[Dict[str, Any]]:
    """
    Simulate one trade forward from `entry_i` to its close and return the trade
    record. Looking forward here measures the OUTCOME only — the entry decision
    already used past bars exclusively, so there is no look-ahead in the signal.

    tp_management='single' -> the whole position exits at TP1 (or SL / timeout).
    tp_management='scaled' -> partial exits at TP1/TP2/TP3 by `tp_weights`, with
        optional break-even (SL→entry after TP1) and trailing (SL→TP1 after TP2).
    Conservative: a bar that straddles both SL and a TP is counted as SL first.
    """
    d = 1 if sg.action == "BUY" else -1
    entry = float(sg.entry)
    sl0 = float(sg.stop_loss)
    risk = abs(entry - sl0)
    tps = [float(t) for t in (sg.take_profits or [])][:3]
    if risk <= 0 or not tps:
        return None
    if tp_management == "scaled":
        w = list(tp_weights)[:len(tps)]
        if not w or sum(w) <= 0:
            w = [1.0] + [0.0] * (len(tps) - 1)
        be, tr = bool(breakeven), bool(trailing)
    else:                                   # single -> 100% at TP1
        w = [1.0] + [0.0] * (len(tps) - 1)
        be, tr = False, False
    sw = sum(w)
    w = [x / sw for x in w]                  # normalise over the available TPs

    n = len(df)
    sl = sl0
    filled: List[int] = []
    realized = 0.0
    remaining = 1.0
    last_exit_price = entry
    outcome: Optional[str] = None
    j = entry_i + 1
    while j < n:
        bar = df.iloc[j]
        hi, lo, cl = float(bar["high"]), float(bar["low"]), float(bar["close"])
        # 1) stop-loss (checked before TP on the same bar)
        if (d == 1 and lo <= sl) or (d == -1 and hi >= sl):
            realized += remaining * ((sl - entry) * d / risk)
            last_exit_price = sl
            remaining = 0.0
            outcome = "win" if filled else "loss"
            break
        # 2) take-profit fills, in order
        for ti, tp in enumerate(tps):
            if ti in filled:
                continue
            if (d == 1 and hi >= tp) or (d == -1 and lo <= tp):
                realized += w[ti] * ((tp - entry) * d / risk)
                remaining -= w[ti]
                filled.append(ti)
                last_exit_price = tp
                if ti == 0 and be:
                    sl = entry                  # break-even after TP1
                if ti == 1 and tr:
                    sl = tps[0]                 # trail to TP1 after TP2
        if remaining <= 1e-9:
            outcome = "win"
            break
        # 3) holding-horizon timeout
        if max_hold > 0 and (j - entry_i) >= max_hold:
            realized += remaining * ((cl - entry) * d / risk)
            last_exit_price = cl
            remaining = 0.0
            outcome = "win" if filled else "neutral"
            break
        j += 1
    if outcome is None:                          # ran out of data
        j = n - 1
        cl = float(df["close"].iloc[-1])
        realized += remaining * ((cl - entry) * d / risk)
        last_exit_price = cl
        outcome = "win" if filled else "neutral"

    cost_r = ((entry * total_cost_bps / 10000.0) / risk) if (risk > 0 and total_cost_bps) else 0.0
    net_r = realized - cost_r
    risk_cash = balance * risk_per_trade
    pnl = net_r * risk_cash
    return {
        "entry_index": entry_i, "entry_time": df["time"].iloc[entry_i], "asset": asset,
        "action": sg.action, "dir": d, "entry": entry, "sl": sl0, "tp": tps[0], "tps": tps,
        "rr": float(sg.rr[0]) if sg.rr else 0.0,
        "exit_index": int(j), "exit_time": df["time"].iloc[int(j)],
        "exit_price": float(last_exit_price), "outcome": outcome,
        "tps_filled": len(filled), "r_multiple": float(net_r),
        "bars_held": int(j - entry_i), "pnl": float(pnl),
    }


def backtest(
    data: pd.DataFrame,
    asset: str = "ASSET",
    window: int = 60,
    step: int = 1,
    lookback: int = 0,
    tol_pct: float = 0.06,
    min_rr: float = 1.0,
    initial_balance: float = 1000.0,
    risk_per_trade: float = 0.01,
    max_hold: int = 0,
    cost_bps: float = 0.0,
    coeffs: Optional[List[float]] = None,
    tp_management: str = "single",
    tp_weights: Any = (0.5, 0.3, 0.2),
    breakeven: bool = True,
    trailing: bool = False,
    spread_bps: float = 0.0,
    commission_bps: float = 0.0,
    slippage_bps: float = 0.0,
) -> Dict[str, Any]:
    """
    Walk forward bar-by-bar. On each evaluation the FU levels and the FUTAS
    signal are recomputed from the *rolling* window only (no look-ahead). When a
    BUY/SELL appears the trade is resolved forward by `_resolve_trade` and the
    scan resumes after its exit. Returns trades + statistics + equity curve.

    Tier-1 (validation):
      max_hold  : holding-horizon in bars -> a third "neutral" outcome so SFVT
                  CSR + FSF need not sum to 100%.
      cost_bps  : round-trip cost (bps). If 0, it is taken as the sum of the
                  split components below.
      coeffs    : BENCHMARKING ONLY — alternative coefficient set (default = the
                  frozen 15 Fibonacci Urvin coefficients).

    Tier-2 (methodological power):
      tp_management : 'single' (whole position at TP1) or 'scaled' (partial exits
                      at TP1/TP2/TP3 by tp_weights).
      tp_weights    : exit fractions for TP1/TP2/TP3 (scaled mode).
      breakeven     : move SL to entry after TP1 (scaled mode).
      trailing      : trail SL to TP1 after TP2 (scaled mode).
      spread_bps / commission_bps / slippage_bps : split cost model; their sum is
                      used when cost_bps == 0.
    """
    df = normalize_ohlc(data)
    n = len(df)
    if n < window + 5:
        window = max(20, n // 2)
    total_cost_bps = float(cost_bps) if cost_bps > 0 else float(spread_bps + commission_bps + slippage_bps)

    trades: List[Dict[str, Any]] = []
    balance = float(initial_balance)
    equity_curve: List[Dict[str, Any]] = [
        {"index": window - 1, "time": df["time"].iloc[window - 1], "balance": balance}]

    i = window
    while i < n:
        if i % step == 0:
            win = df.iloc[max(0, i - window): i + 1]
            try:
                res = analyze(win, asset=asset, lookback=lookback,
                              tol_pct=tol_pct, min_rr=min_rr, with_htf=False, coeffs=coeffs)
            except Exception:
                i += 1
                continue
            sg = res.signal
            if sg.action in ("BUY", "SELL") and sg.stop_loss is not None and sg.take_profits:
                tr = _resolve_trade(df, i, sg, max_hold, total_cost_bps, tp_management,
                                    tp_weights, breakeven, trailing, balance,
                                    risk_per_trade, asset)
                if tr is not None:
                    balance += tr["pnl"]
                    tr["balance"] = float(balance)
                    trades.append(tr)
                    equity_curve.append({"index": tr["exit_index"], "time": tr["exit_time"],
                                         "balance": balance})
                    i = tr["exit_index"] + 1
                    continue
        i += 1

    stats = _backtest_stats(trades, initial_balance, balance)
    full_structure = market_structure(detect_swings(df))
    sfvt = sfvt_metrics(df, full_structure, trades)
    return {
        "asset": asset,
        "trades": trades,
        "stats": stats,
        "sfvt": sfvt,
        "equity_curve": equity_curve,
        "initial_balance": initial_balance,
        "final_balance": balance,
        "tp_management": tp_management,
        "cost_bps_total": total_cost_bps,
    }


def _backtest_stats(trades, initial_balance, final_balance) -> Dict[str, Any]:
    n = len(trades)
    wins = [t for t in trades if t["outcome"] == "win"]
    losses = [t for t in trades if t["outcome"] == "loss"]
    neutrals = [t for t in trades if t["outcome"] == "neutral"]
    # sign-based so transaction costs are reflected (a post-cost "win" can be flat)
    gross_profit = sum(t["pnl"] for t in trades if t["pnl"] > 0)
    gross_loss = -sum(t["pnl"] for t in trades if t["pnl"] < 0)
    net = final_balance - initial_balance
    win_rate = (len(wins) / n) if n else 0.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)

    # consecutive streaks (a neutral breaks both)
    max_win_streak = max_loss_streak = cur_w = cur_l = 0
    for t in trades:
        if t["outcome"] == "win":
            cur_w += 1; cur_l = 0
        elif t["outcome"] == "loss":
            cur_l += 1; cur_w = 0
        else:
            cur_w = cur_l = 0
        max_win_streak = max(max_win_streak, cur_w)
        max_loss_streak = max(max_loss_streak, cur_l)

    # max drawdown on the running balance
    peak = initial_balance; max_dd = 0.0; bal = initial_balance
    for t in trades:
        bal = t["balance"]
        peak = max(peak, bal)
        max_dd = max(max_dd, peak - bal)

    pnls = [t["pnl"] for t in trades]
    expectancy = float(np.mean(pnls)) if pnls else 0.0
    sharpe = float(np.mean(pnls) / np.std(pnls)) if len(pnls) > 1 and np.std(pnls) > 0 else 0.0

    return {
        "total_trades": n,
        "wins": len(wins),
        "losses": len(losses),
        "neutrals": len(neutrals),
        "win_rate": win_rate,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "net_profit": net,
        "profit_factor": profit_factor,
        "max_win_streak": max_win_streak,
        "max_loss_streak": max_loss_streak,
        "max_drawdown": max_dd,
        "avg_win": float(np.mean([t["pnl"] for t in wins])) if wins else 0.0,
        "avg_loss": float(np.mean([t["pnl"] for t in losses])) if losses else 0.0,
        "expectancy": expectancy,
        "sharpe": sharpe,
    }


# =============================================================================
# 14b. SFVT STRUCTURAL VALIDATION METRICS  (dissertation §3.1)
# -----------------------------------------------------------------------------
# The dissertation validates the method with structural metrics, not only raw
# profit. SFVT = the structural-validation test reported there.
#   CSR  Continuation Success Rate   — share of signals that reached the target
#                                      (TP before SL).            higher better
#   FSF  False Signal Frequency      — share of signals that failed (SL first).
#                                                                  lower  better
#   SPR  Structural Persistence Rate — share of structural transitions that kept
#        the prevailing bias (HH/HL while bullish, LH/LL while bearish).
#   Δ    improvement of CSR over a plain RSI/MA momentum baseline on the SAME
#        data (CSR − baseline) — shows the structural method beats raw momentum.
# Reference values reported in the dissertation (orientation only):
#   XAUUSD: CSR 76.9, FSF 16.0, SPR 77.6, Δ +19.5
#   BTCUSD: CSR 69.6, FSF 22.8, SPR 70.2, Δ +19.8
# =============================================================================
DISSERTATION_SFVT_REFERENCE: Dict[str, Dict[str, float]] = {
    "XAUUSD": {"CSR": 76.9, "FSF": 16.0, "SPR": 77.6, "delta": 19.5},
    "BTCUSD": {"CSR": 69.6, "FSF": 22.8, "SPR": 70.2, "delta": 19.8},
}


def _structural_persistence(structure: List[StructureEvent]) -> float:
    """Share of labelled swings that *continued* the prevailing structural bias."""
    bias: Optional[str] = None
    total = 0
    persist = 0
    for e in structure:
        if bias in ("bull", "bear") and e.label in ("HH", "HL", "LH", "LL"):
            total += 1
            if bias == "bull" and e.label in ("HH", "HL"):
                persist += 1
            elif bias == "bear" and e.label in ("LH", "LL"):
                persist += 1
        if e.event in ("BOS-up", "CHoCH-bull"):
            bias = "bull"
        elif e.event in ("BOS-down", "CHoCH-bear"):
            bias = "bear"
        elif bias is None and e.label in ("HH", "HL"):
            bias = "bull"
        elif bias is None and e.label in ("LH", "LL"):
            bias = "bear"
    return (persist / total) if total else 0.0


def _rsi_ma_baseline(df: pd.DataFrame, period: int = 14, horizon: int = 5) -> float:
    """
    Plain momentum baseline: RSI crossing above its own moving average predicts an
    up-move over the next `horizon` bars (and below -> down). Returns the
    directional hit-rate. Used ONLY as the Δ comparison baseline (§3.1) so the
    structural method can be shown to beat a naive momentum rule.
    """
    close = df["close"].to_numpy(dtype=float)
    n = close.size
    rsi = compute_rsi(close, period)
    ma = np.full(n, np.nan)
    for i in range(n):
        seg = rsi[max(0, i - period + 1): i + 1]
        seg = seg[~np.isnan(seg)]
        if seg.size:
            ma[i] = seg.mean()
    hits = 0
    total = 0
    for i in range(1, n - horizon):
        if (math.isnan(rsi[i]) or math.isnan(rsi[i - 1])
                or math.isnan(ma[i]) or math.isnan(ma[i - 1])):
            continue
        crossed_up = rsi[i - 1] <= ma[i - 1] and rsi[i] > ma[i]
        crossed_dn = rsi[i - 1] >= ma[i - 1] and rsi[i] < ma[i]
        if not (crossed_up or crossed_dn):
            continue
        fwd = close[i + horizon] - close[i]
        total += 1
        if (crossed_up and fwd > 0) or (crossed_dn and fwd < 0):
            hits += 1
    return (hits / total) if total else 0.0


def sfvt_metrics(
    df: pd.DataFrame,
    structure: List[StructureEvent],
    trades: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Compute the dissertation's structural validation metrics (percentages).

    With a holding horizon (`backtest(max_hold>0)`) a signal can resolve three
    ways — reached TP (win), hit SL (loss), or expired (neutral) — so:
        CSR  = wins     / n   (continuation success)
        FSF  = losses   / n   (false signal)
        NEU  = neutrals / n   (structurally indecisive)
    and CSR + FSF + NEU = 100, i.e. CSR + FSF < 100 when neutrals exist — this is
    what makes the figures comparable to the dissertation's (e.g. 76.9 + 16.0).
    """
    n = len(trades)
    wins = sum(1 for t in trades if t.get("outcome") == "win")
    losses = sum(1 for t in trades if t.get("outcome") == "loss")
    neutrals = sum(1 for t in trades if t.get("outcome") == "neutral")
    csr = (wins / n * 100.0) if n else 0.0
    fsf = (losses / n * 100.0) if n else 0.0
    neu = (neutrals / n * 100.0) if n else 0.0
    spr = _structural_persistence(structure) * 100.0
    baseline = _rsi_ma_baseline(df) * 100.0
    delta = csr - baseline
    return {
        "CSR": round(csr, 1),
        "FSF": round(fsf, 1),
        "NEU": round(neu, 1),
        "SPR": round(spr, 1),
        "baseline_csr": round(baseline, 1),
        "delta": round(delta, 1),
        "n_signals": n,
        "reference": DISSERTATION_SFVT_REFERENCE,
    }


# =============================================================================
# 14b-ii. STATISTICAL SIGNIFICANCE + BENCHMARKS  (dissertation defence)
# -----------------------------------------------------------------------------
# Turns "it worked on this sample" into "the edge is unlikely to be chance, and
# it beats the obvious alternatives":
#   * Monte-Carlo permutation test — re-runs the backtest on many random
#     re-orderings of the SAME bars (identical High/Low/return distribution,
#     destroyed structure). If the real result sits in the tail, the edge comes
#     from market STRUCTURE, not luck.  -> p-value.
#   * Classical-Fibonacci baseline — the identical pipeline using the textbook
#     retracement ratios INSTEAD of the 15 Fibonacci Urvin coefficients. Used
#     ONLY as a comparison; it does not enter FUTAS. Shows the Urvin set adds value.
#   * Buy-and-hold — the naive benchmark every trading study must beat.
# =============================================================================
# Textbook retracement + extension ratios (baseline ONLY — never used inside FUTAS).
CLASSICAL_FIB_COEFFS: List[float] = [
    -0.618, -0.236, 0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0, 1.272, 1.618,
]


def _permute_bars(df: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """
    A null-hypothesis copy of the data: the SAME bars in random order. Max(high)
    and min(low) — hence the FU level grid — are unchanged, so only the temporal
    STRUCTURE (the HH/HL/LH/LL sequence) is destroyed. Time is re-stamped
    monotonically so resampling/labels stay valid.
    """
    idx = rng.permutation(len(df))
    p = df.iloc[idx].reset_index(drop=True).copy()
    p["time"] = pd.date_range("2000-01-01", periods=len(p), freq="h")
    return p


def monte_carlo_significance(data: pd.DataFrame, asset: str = "ASSET",
                             metric: str = "net_profit", n_iter: int = 150,
                             seed: int = 7, **bt_kwargs) -> Dict[str, Any]:
    """
    Permutation test for the backtest `metric` (e.g. 'net_profit', 'win_rate',
    'expectancy'). Returns the real value, the random distribution summary and a
    one-sided p-value = P(random >= real) with add-one smoothing.
    """
    df = normalize_ohlc(data)
    bt_kwargs.pop("coeffs", None)
    real = float(backtest(df, asset=asset, **bt_kwargs)["stats"].get(metric, 0.0))
    rng = np.random.default_rng(seed)
    vals: List[float] = []
    for _ in range(int(n_iter)):
        try:
            s = backtest(_permute_bars(df, rng), asset=asset, **bt_kwargs)["stats"]
            vals.append(float(s.get(metric, 0.0)))
        except Exception:
            continue
    rand = np.array(vals, dtype=float) if vals else np.array([0.0])
    ge = int(np.sum(rand >= real))
    p_value = (1 + ge) / (1 + rand.size)
    return {
        "metric": metric,
        "real": round(real, 4),
        "random_mean": round(float(rand.mean()), 4),
        "random_std": round(float(rand.std()), 4),
        "p_value": round(float(p_value), 4),
        "n_iter": int(rand.size),
        "percentile": round(float(np.sum(rand < real) / rand.size * 100.0), 1),
        "significant": bool(p_value < 0.05),
    }


def benchmark_compare(data: pd.DataFrame, asset: str = "ASSET",
                      **bt_kwargs) -> Dict[str, Any]:
    """
    Head-to-head: FUTAS (the 15 Fibonacci Urvin coefficients) vs the classical
    Fibonacci ratios vs buy-and-hold, all on the same data and rules.
    """
    df = normalize_ohlc(data)
    bt_kwargs.pop("coeffs", None)
    futas = backtest(df, asset=asset, **bt_kwargs)
    classical = backtest(df, asset=asset, coeffs=CLASSICAL_FIB_COEFFS, **bt_kwargs)
    close = df["close"].to_numpy(dtype=float)
    bh = ((close[-1] / close[0] - 1.0) * 100.0) if close.size > 1 and close[0] else 0.0

    def _summ(bt: Dict[str, Any]) -> Dict[str, Any]:
        s, v, ib = bt["stats"], bt["sfvt"], bt["initial_balance"]
        pf = s["profit_factor"]
        return {
            "net_pct": round(s["net_profit"] / ib * 100.0, 2),
            "win_rate": round(s["win_rate"] * 100.0, 1),
            "profit_factor": (round(pf, 2) if math.isfinite(pf) else float("inf")),
            "trades": s["total_trades"],
            "CSR": v["CSR"], "FSF": v["FSF"],
        }

    return {
        "asset": asset,
        "futas": _summ(futas),
        "classical_fib": _summ(classical),
        "buy_hold_pct": round(bh, 2),
        "rsi_ma_baseline_csr": futas["sfvt"]["baseline_csr"],
        "classical_coeffs": CLASSICAL_FIB_COEFFS,
    }


def parameter_sensitivity(data: pd.DataFrame, asset: str = "ASSET",
                          param: str = "tol_pct",
                          values: Optional[List[float]] = None,
                          metric: str = "net_profit", **bt_kwargs) -> Dict[str, Any]:
    """
    Sweep ONE backtest parameter over `values` and report the chosen `metric`,
    win-rate, trade count and CSR at each — robustness evidence that results hold
    across a *region*, not a single lucky setting.
    """
    df = normalize_ohlc(data)
    if values is None:
        values = {"tol_pct": [0.03, 0.04, 0.06, 0.08, 0.10],
                  "min_rr": [0.5, 1.0, 1.5, 2.0],
                  "window": [40, 50, 60, 80, 100]}.get(param, [0.04, 0.06, 0.08])
    rows: List[Dict[str, Any]] = []
    for v in values:
        kw = dict(bt_kwargs); kw[param] = (int(v) if param == "window" else float(v))
        try:
            bt = backtest(df, asset=asset, **kw)
            s, sf = bt["stats"], bt["sfvt"]
            rows.append({"value": v, "metric": round(float(s.get(metric, 0.0)), 3),
                         "win_rate": round(s["win_rate"] * 100, 1),
                         "trades": s["total_trades"], "CSR": sf["CSR"]})
        except Exception:
            rows.append({"value": v, "metric": float("nan"), "win_rate": float("nan"),
                         "trades": 0, "CSR": float("nan")})
    vals = [r["metric"] for r in rows if not math.isnan(r["metric"])]
    return {
        "param": param, "metric": metric, "rows": rows,
        "metric_mean": round(float(np.mean(vals)), 3) if vals else 0.0,
        "metric_std": round(float(np.std(vals)), 3) if vals else 0.0,
        "positive_share": round(sum(1 for x in vals if x > 0) / len(vals) * 100, 1) if vals else 0.0,
    }


def in_out_of_sample(data: pd.DataFrame, asset: str = "ASSET",
                     train_frac: float = 0.6, **bt_kwargs) -> Dict[str, Any]:
    """
    Split the history into an in-sample (first `train_frac`) and out-of-sample
    (the rest) segment and backtest each. FUTAS fits no parameters, so this is a
    *stability* check: similar performance in both halves argues the edge is not
    an artefact of one period.
    """
    df = normalize_ohlc(data)
    n = len(df)
    cut = max(2, int(n * float(train_frac)))
    cut = min(cut, n - 2)
    in_df = df.iloc[:cut].reset_index(drop=True)
    out_df = df.iloc[cut:].reset_index(drop=True)

    def _summ(frame: pd.DataFrame) -> Dict[str, Any]:
        try:
            bt = backtest(frame, asset=asset, **bt_kwargs)
            s, sf, ib = bt["stats"], bt["sfvt"], bt["initial_balance"]
            return {"bars": len(frame), "trades": s["total_trades"],
                    "win_rate": round(s["win_rate"] * 100, 1),
                    "net_pct": round(s["net_profit"] / ib * 100, 2), "CSR": sf["CSR"]}
        except Exception as e:
            return {"bars": len(frame), "error": str(e)}

    return {"asset": asset, "train_frac": train_frac,
            "in_sample": _summ(in_df), "out_of_sample": _summ(out_df)}


def bootstrap_metrics(trades: List[Dict[str, Any]], n_boot: int = 1000,
                      seed: int = 7, ci: float = 0.95) -> Dict[str, Any]:
    """
    Bootstrap confidence intervals for win-rate and per-trade expectancy by
    resampling the realized trades with replacement — quantifies how much the
    headline numbers could move on a different draw of the same process.
    """
    pnls = np.array([float(t.get("pnl", 0.0)) for t in trades], dtype=float)
    wins = np.array([1.0 if t.get("outcome") == "win" else 0.0 for t in trades], dtype=float)
    n = pnls.size
    if n < 3:
        return {"n": int(n), "insufficient": True}
    rng = np.random.default_rng(seed)
    lo_q, hi_q = (1 - ci) / 2 * 100, (1 + ci) / 2 * 100
    wr, ex = [], []
    for _ in range(int(n_boot)):
        idx = rng.integers(0, n, n)
        wr.append(float(wins[idx].mean() * 100.0))
        ex.append(float(pnls[idx].mean()))
    return {
        "n": int(n), "ci": ci, "insufficient": False,
        "win_rate_ci": [round(float(np.percentile(wr, lo_q)), 1),
                        round(float(np.percentile(wr, hi_q)), 1)],
        "expectancy_ci": [round(float(np.percentile(ex, lo_q)), 4),
                          round(float(np.percentile(ex, hi_q)), 4)],
        "win_rate_mean": round(float(np.mean(wr)), 1),
        "expectancy_mean": round(float(np.mean(ex)), 4),
    }


# =============================================================================
# 14c. WORKED ENTRY → EXIT EXAMPLE  (no look-ahead)
# -----------------------------------------------------------------------------
# "Assume the entry point earlier in the chart (not the present bar), then say:
#  if you had entered there and sold here, you would have made this much."
# The entry is selected from a HISTORICAL bar using ONLY the data available up to
# that bar (a rolling window — no future knowledge). The exit is then found by
# walking the chart forward to the first bar that touches TP1 (win) or the
# Stop-Loss (loss). Everything (entry/SL/TP) is FU-derived, exactly as the live
# engine would have produced it at that moment. Mirrors dissertation Table 3.2.3.
# =============================================================================
@dataclass
class WorkedTrade:
    """A fully reconstructed historical FUTAS trade, entry to exit."""
    found: bool
    reason: str = ""
    asset: str = "ASSET"
    n_bars: int = 0
    # entry (decided with no look-ahead)
    entry_index: int = -1
    entry_time: Any = None
    entry_price: float = 0.0
    action: str = "WAIT"
    direction: int = 0                       # +1 buy, -1 sell
    stop_loss: float = 0.0
    take_profits: List[float] = field(default_factory=list)
    rr_planned: List[float] = field(default_factory=list)
    sl_level_label: str = ""
    tp_level_labels: List[str] = field(default_factory=list)
    confidence: str = ""
    confidence_score: float = 0.0
    # exit (found by walking forward)
    exit_index: int = -1
    exit_time: Any = None
    exit_price: float = 0.0
    outcome: str = ""                        # win | loss | open
    exit_kind: str = ""                      # "Take-Profit 1" | "Stop-Loss" | "still open"
    bars_held: int = 0
    profit_pct: float = 0.0
    r_multiple: float = 0.0
    # context
    as_of_explanation: str = ""
    narrative: str = ""

    def as_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


def worked_example(
    data: pd.DataFrame,
    asset: str = "ASSET",
    window: int = 60,
    tol_pct: float = 0.06,
    min_rr: float = 1.0,
    entry_search_end_frac: float = 0.7,
    target_action: str = "any",
) -> WorkedTrade:
    """
    Reconstruct one historical entry→exit trade with no look-ahead.

    Parameters
    ----------
    window               : rolling history used for each as-of analysis.
    entry_search_end_frac: only look for the entry inside the first part of the
                           chart (default first 70%) so there is room left for the
                           trade to reach a target/stop afterwards.
    target_action        : "BUY", "SELL" or "any".

    The candidate entry chosen is the *highest-confidence* valid set-up inside the
    search region (earliest wins ties). Returns a WorkedTrade.
    """
    df = normalize_ohlc(data)
    n = len(df)
    if n < window + 6:
        window = max(15, n // 3)
    start = window
    end = max(start + 1, int(n * float(entry_search_end_frac)))
    end = min(end, n - 2)  # leave at least a couple of bars to resolve an exit

    want = target_action.upper()
    best: Optional[Dict[str, Any]] = None
    for i in range(start, end + 1):
        win = df.iloc[max(0, i - window): i + 1]
        try:
            res = analyze(win, asset=asset, tol_pct=tol_pct, min_rr=min_rr, with_htf=False)
        except Exception:
            continue
        sg = res.signal
        if sg.action not in ("BUY", "SELL"):
            continue
        if want in ("BUY", "SELL") and sg.action != want:
            continue
        if sg.stop_loss is None or not sg.take_profits:
            continue
        cand = {
            "i": i, "res": res, "sg": sg,
            "score": sg.confidence_score,
        }
        if best is None or cand["score"] > best["score"]:
            best = cand

    if best is None:
        return WorkedTrade(
            found=False, asset=asset, n_bars=n,
            reason=("No valid FUTAS entry (BUY/SELL with FU-based SL/TP and "
                    "acceptable R/R) was found in the searched region of the chart."),
        )

    i = best["i"]
    res = best["res"]
    sg = best["sg"]
    direction = 1 if sg.action == "BUY" else -1
    entry = float(sg.entry)               # entry = live price at that historical bar
    sl = float(sg.stop_loss)
    tp1 = float(sg.take_profits[0])

    # ---- walk forward to the exit (same conservative rule as the backtest) ----
    exit_index = -1
    exit_price = 0.0
    outcome = "open"
    exit_kind = "still open"
    for j in range(i + 1, n):
        bar = df.iloc[j]
        if direction == 1:
            if bar["low"] <= sl:
                exit_index, exit_price, outcome, exit_kind = j, sl, "loss", "Stop-Loss"
                break
            if bar["high"] >= tp1:
                exit_index, exit_price, outcome, exit_kind = j, tp1, "win", "Take-Profit 1"
                break
        else:
            if bar["high"] >= sl:
                exit_index, exit_price, outcome, exit_kind = j, sl, "loss", "Stop-Loss"
                break
            if bar["low"] <= tp1:
                exit_index, exit_price, outcome, exit_kind = j, tp1, "win", "Take-Profit 1"
                break

    if exit_index < 0:
        exit_index = n - 1
        exit_price = float(df["close"].iloc[-1])
        outcome = "open"
        exit_kind = "still open at last bar"

    bars_held = exit_index - i
    profit_pct = ((exit_price - entry) / entry * 100.0) * direction if entry else 0.0
    risk = abs(entry - sl)
    r_multiple = ((exit_price - entry) * direction / risk) if risk > 0 else 0.0

    sl_label = sg.sl_level.label if sg.sl_level is not None else "—"
    tp_labels = [t.label for t in sg.tp_levels]

    wt = WorkedTrade(
        found=True, asset=asset, n_bars=n,
        entry_index=i, entry_time=df["time"].iloc[i], entry_price=entry,
        action=sg.action, direction=direction,
        stop_loss=sl, take_profits=[float(x) for x in sg.take_profits],
        rr_planned=[float(x) for x in sg.rr],
        sl_level_label=sl_label, tp_level_labels=tp_labels,
        confidence=sg.confidence, confidence_score=sg.confidence_score,
        exit_index=exit_index, exit_time=df["time"].iloc[exit_index],
        exit_price=float(exit_price), outcome=outcome, exit_kind=exit_kind,
        bars_held=int(bars_held), profit_pct=float(profit_pct),
        r_multiple=float(r_multiple),
        as_of_explanation=res.explanation,
    )
    wt.narrative = _worked_narrative(wt, res)
    return wt


def _worked_narrative(wt: "WorkedTrade", res: "FUTASResult") -> str:
    """Plain, dissertation-grade story of the reconstructed trade."""
    L: List[str] = []
    side = "long (BUY)" if wt.direction == 1 else "short (SELL)"
    L.append("WORKED EXAMPLE — entry reconstructed earlier in the chart, "
             "with NO look-ahead (decided only from data up to the entry bar).")
    L.append("=" * 70)
    L.append(
        f"As of bar {wt.entry_index} of {wt.n_bars} (time {wt.entry_time}), FUTAS "
        f"projected the 15 Fibonacci Urvin levels from the range visible up to "
        f"that bar only (High={res.high:.5f}, Low={res.low:.5f}). It read the "
        f"market as trend={res.trend}, structure bias="
        f"{res.trend_metrics.get('structure_bias','—')}, phase={res.phase}, "
        f"seven-phase stage='{res.market_phase}'."
    )
    m = res.momentum or {}
    if m:
        conf = ("bullish" if m.get("confirms_bull") else
                "bearish" if m.get("confirms_bear") else "neutral")
        L.append(f"Momentum (confirmation only) was {conf} "
                 f"(RSI={m.get('rsi', float('nan')):.1f}).")
    L.append("")
    L.append(f"A {side} set-up formed. Every price below is a Fibonacci Urvin level:")
    L.append(f"   • Entry (live price at that bar) : {wt.entry_price:.5f}")
    L.append(f"   • Stop-Loss [{wt.sl_level_label}] : {wt.stop_loss:.5f}")
    for idx, tp in enumerate(wt.take_profits):
        lab = wt.tp_level_labels[idx] if idx < len(wt.tp_level_labels) else ""
        rr = wt.rr_planned[idx] if idx < len(wt.rr_planned) else float("nan")
        L.append(f"   • Take-Profit {idx+1} [{lab}] : {tp:.5f}   (planned R/R {rr:.2f} : 1)")
    L.append(f"   Confidence at entry: {wt.confidence} ({wt.confidence_score:.0%}).")
    L.append("")
    if wt.outcome == "open":
        L.append(
            f"Walking the chart forward with no future knowledge, the trade had "
            f"NOT yet reached TP1 or the Stop-Loss by the last bar "
            f"({wt.exit_time}). Unrealised result after {wt.bars_held} bars: "
            f"{wt.profit_pct:+.2f}% ({wt.r_multiple:+.2f}R)."
        )
    else:
        hit = "first profit target (TP1)" if wt.outcome == "win" else "protective Stop-Loss"
        L.append(
            f"Walking the chart forward with no future knowledge, price reached the "
            f"{hit} at bar {wt.exit_index} (time {wt.exit_time}), {wt.bars_held} "
            f"bars after entry, at {wt.exit_price:.5f}."
        )
        verb = "bought" if wt.direction == 1 else "sold"
        back = "sold" if wt.direction == 1 else "bought back"
        L.append("")
        L.append(
            f"RESULT: if you had {verb} at {wt.entry_price:.5f} and {back} at "
            f"{wt.exit_price:.5f}, the position would have returned "
            f"{wt.profit_pct:+.2f}%  ({wt.r_multiple:+.2f}R, outcome = {wt.outcome.upper()})."
        )
    L.append("")
    L.append(
        "This mirrors the dissertation's worked trade (Table 3.2.3): the entry, the "
        "Stop-Loss and the targets are all Fibonacci Urvin levels, and the result "
        "is measured purely from how the structure unfolded afterwards — no value "
        "was taken from the end of the chart or from any external source."
    )
    L.append("")
    L.append("NOTE: scientific reconstruction for back-testing only — not financial advice.")
    return "\n".join(L)


# =============================================================================
# 15. SELF-TEST  (run `python futas_engine.py`)
# =============================================================================
def _demo_frame(n: int = 180, seed: int = 7) -> pd.DataFrame:
    """Synthetic OHLC with a visible up-then-correction structure for testing."""
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    trend = np.linspace(0, 60, n)
    wave = 12 * np.sin(t / 9.0)
    noise = rng.normal(0, 2.2, n)
    close = 1800 + trend + wave + noise.cumsum() * 0.15
    open_ = np.concatenate([[close[0]], close[:-1]])
    high = np.maximum(open_, close) + rng.uniform(0.5, 3.5, n)
    low = np.minimum(open_, close) - rng.uniform(0.5, 3.5, n)
    return pd.DataFrame({
        "time": pd.date_range("2026-01-01", periods=n, freq="h"),
        "open": open_, "high": high, "low": low, "close": close,
        "volume": rng.integers(100, 1000, n),
    })


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1251
    except Exception:
        pass
    assert len(FU_COEFFICIENTS) == 15, "FU must have exactly 15 coefficients"
    print("Fibonacci Urvin coefficients (15):")
    print(" ", FU_COEFFICIENTS)

    df = _demo_frame()
    res = analyze(df, asset="XAUUSD-DEMO")
    print("\n--- FU LEVELS ---")
    print(res.levels_table().to_string(index=False))
    print("\n--- SIGNAL ---")
    print(res.signal_table().to_string(index=False))
    print("\n--- EXPLANATION ---")
    print(res.explanation)

    bt = backtest(df, asset="XAUUSD-DEMO", window=50)
    print("\n--- BACKTEST STATS ---")
    for k, v in bt["stats"].items():
        print(f"  {k:16s}: {v}")
    print("\n--- SFVT STRUCTURAL METRICS (dissertation §3.1) ---")
    for k, v in bt["sfvt"].items():
        if k == "reference":
            continue
        print(f"  {k:16s}: {v}")

    wt = worked_example(df, asset="XAUUSD-DEMO", window=50)
    print("\n--- WORKED ENTRY -> EXIT EXAMPLE ---")
    print(wt.narrative if wt.found else wt.reason)
