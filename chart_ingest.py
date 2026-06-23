"""
chart_ingest.py
===============================================================================
Approximate OHLC extraction from a candlestick **chart** picture (digitizer).

SCIENTIFIC HONESTY NOTE
-----------------------
Reading per-bar OHLC out of a *rendered candlestick chart* is an APPROXIMATION,
not a measurement:

  * pixels quantise price (sub-pixel highs/lows are lost);
  * adjacent candles merge in dense consolidation zones;
  * the hollow/filled (bull/bear) guess is unreliable at low resolution.

This module is therefore a *drafting aid*. It proposes an OHLC table that the
user must **review and correct** before analysis. Its robust outputs are the
range **High**, the range **Low** and the **last price** — which are exactly the
three inputs the FUTAS level grid (P = Low + (High − Low)·K) actually depends on;
the per-bar body/direction in between is approximate.

Implementation is pure Pillow + numpy (no OpenCV, no Tesseract), so it adds no
new dependency beyond what the app already requires.

This is a scientific-research and algorithmic-testing instrument.
It does NOT provide financial advice.
===============================================================================
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import List, Tuple

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw

__all__ = ["Candle", "DigitizeResult", "detect_candles", "render_overlay", "calibrate"]

# default plot-area crop as fractions of the image (drop toolbar / axis / panels)
DEFAULT_CROP: Tuple[float, float, float, float] = (0.02, 0.06, 0.93, 0.92)

# a candle column is a "horizontal line" (gridline / S-R line / box edge) and is
# discarded when its ink covers more than this fraction of the crop width
HORIZON_FRAC = 0.45


@dataclass
class Candle:
    """One detected candle, in PIXEL coordinates (y grows downward)."""
    cx: int          # centre x
    x0: int          # left x
    x1: int          # right x
    top_y: int       # highest ink row  -> maps to the candle HIGH
    bot_y: int       # lowest ink row   -> maps to the candle LOW
    body_top_y: int  # top of the filled body
    body_bot_y: int  # bottom of the filled body
    bull: bool       # approximate direction guess (hollow / green -> bullish)


@dataclass
class DigitizeResult:
    candles: List[Candle]
    crop: Tuple[int, int, int, int]          # pixel crop (l, t, r, b)
    image_size: Tuple[int, int]              # (W, H)
    pixel_top: int                           # min top_y  -> range HIGH in pixels
    pixel_bot: int                           # max bot_y  -> range LOW  in pixels
    horizon_rows_removed: int = 0
    theme: str = "dark"
    pitch: float = 0.0                       # detected candle spacing in pixels
    segmentation: str = "cluster"            # "cluster" | "pitch" | "hint"
    note: str = field(default=(
        "Approximate digitization — review every bar before trusting the levels."))


# =============================================================================
# Pixel detection
# =============================================================================
def _ink_mask(arr: np.ndarray, theme: str) -> np.ndarray:
    """Boolean mask of candle ink under the chosen candle style."""
    R, G, Bl = arr[..., 0], arr[..., 1], arr[..., 2]
    mx = np.maximum(np.maximum(R, G), Bl)
    mn = np.minimum(np.minimum(R, G), Bl)
    red = (R > 110) & (G < 90) & (Bl < 90)        # red annotations / zigzag

    if theme == "light":
        # light candles on a dark background; red annotations excluded
        return (mn > 150) & (~red)
    if theme == "color":
        # green/red candles -> saturated pixels; gray grid/background excluded
        return (mx - mn) > 60
    # default "dark": dark candles on a light background; red excluded
    return (mx < 110) & (~red)


def _cluster_columns(xs: np.ndarray, gap: int = 1) -> List[Tuple[int, int]]:
    """Group contiguous ink columns (allowing a small gap) into candle spans."""
    clusters: List[Tuple[int, int]] = []
    if len(xs):
        start = prev = int(xs[0])
        for x in xs[1:]:
            x = int(x)
            if x - prev <= gap:
                prev = x
            else:
                clusters.append((start, prev))
                start = prev = x
        clusters.append((start, prev))
    return clusters


def _estimate_pitch(profile: np.ndarray) -> int | None:
    """
    Estimate the candle-to-candle spacing (pitch) in pixels from the per-column
    ink-count profile, by autocorrelation.

    On a *dense* chart adjacent candles touch, so `_cluster_columns` merges many
    candles into one run and data is lost. The chart is still (approximately)
    periodic: bodies and wicks recur at a fixed pitch. The first strong
    autocorrelation peak recovers that pitch so each merged run can be sliced
    back into individual candles.
    """
    p = np.asarray(profile, dtype=float)
    n = p.size
    if n < 10:
        return None
    # First difference high-passes the signal: it cancels the slow random-walk
    # envelope of the body heights (which otherwise swamps the period) and keeps
    # the sharp body-edge / wick steps that recur once per candle.
    s = np.diff(p)
    s -= s.mean()
    if not np.any(s):
        return None
    ac = np.correlate(s, s, mode="full")[s.size - 1:]
    if ac[0] <= 0:
        return None
    ac = ac / ac[0]

    min_lag = 2
    max_lag = min(max(min_lag + 1, n // 3), ac.size - 1)
    if max_lag <= min_lag:
        return None
    peaks = [(lag, float(ac[lag]))
             for lag in range(min_lag, max_lag)
             if ac[lag] >= ac[lag - 1] and ac[lag] >= ac[lag + 1] and ac[lag] > 0.25]
    if not peaks:
        return None
    strongest = max(v for _, v in peaks)
    # the fundamental candle pitch is the *smallest* lag whose peak is strong;
    # its harmonics (2x, 3x, ...) are of comparable height and would over-merge
    strong = [lag for lag, v in peaks if v >= 0.5 * strongest]
    return int(min(strong))


def _slice_window(x0: int, x1: int, n: int) -> List[Tuple[int, int]]:
    """Split the pixel span [x0, x1] into n contiguous equal-width sub-windows."""
    edges = np.linspace(x0, x1 + 1, int(n) + 1)
    out: List[Tuple[int, int]] = []
    for i in range(int(n)):
        sx0, sx1 = int(round(edges[i])), int(round(edges[i + 1])) - 1
        if sx1 >= sx0:
            out.append((sx0, sx1))
    return out


def _extract_candle(mask: np.ndarray, arr: np.ndarray, theme: str,
                    x0: int, x1: int) -> "Candle | None":
    """Read one candle (high/low/body/direction) from a single column window."""
    w = x1 - x0 + 1
    sub = mask[:, x0:x1 + 1]
    ys = np.where(sub.any(axis=1))[0]
    if len(ys) == 0:
        return None
    wpr = sub.sum(axis=1)                       # ink width per row
    if int(wpr.sum()) < 2:                      # single-pixel speck -> noise
        return None
    hi, lo = int(ys.min()), int(ys.max())
    body_rows = np.where(wpr >= max(2, 0.6 * w))[0]
    bt, bb = (int(body_rows.min()), int(body_rows.max())) if len(body_rows) else (hi, lo)
    interior = mask[bt:bb + 1, x0:x1 + 1]
    bull = _direction(arr, interior, theme, x0, x1, bt, bb)
    return Candle(cx=(x0 + x1) // 2, x0=x0, x1=x1,
                  top_y=hi, bot_y=lo, body_top_y=bt, body_bot_y=bb, bull=bull)


def _direction(arr: np.ndarray, interior_mask: np.ndarray, theme: str,
               x0: int, x1: int, bt: int, bb: int) -> bool:
    """Approximate bull/bear: green vs red (color theme) or hollow vs filled."""
    if interior_mask.size == 0 or interior_mask.sum() == 0:
        return True
    if theme == "color":
        region = arr[bt:bb + 1, x0:x1 + 1]
        sel = interior_mask
        r_mean = region[..., 0][sel].mean()
        g_mean = region[..., 1][sel].mean()
        return bool(g_mean >= r_mean)           # greener body -> bullish
    # monochrome: a hollow (mostly empty) body is conventionally bullish
    fill = float(interior_mask.mean())
    return bool(fill < 0.5)


def detect_candles(image_bytes: bytes,
                   crop_fracs: Tuple[float, float, float, float] = DEFAULT_CROP,
                   theme: str = "dark",
                   n_candles_hint: "int | None" = None) -> DigitizeResult:
    """
    Detect candles in a chart screenshot and return them in pixel space.

    crop_fracs     : (left, top, right, bottom) as fractions of the image,
                     isolating the plot area (drop toolbar, price axis, tabs).
    theme          : "dark" | "light" | "color" — what the candles look like.
    n_candles_hint : if you can read the candle count off the chart, pass it; the
                     inked span is then sliced into exactly that many bars (the
                     most faithful mode for dense charts where candles touch).

    Without a hint, the candle pitch is estimated by autocorrelation and every
    merged run is sliced back into its individual candles, so dense charts no
    longer collapse to a handful of bars.
    """
    im = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    W, H = im.size
    arr = np.asarray(im).astype(int)

    lf, tf, rf, bf = crop_fracs
    l, t, r, b = int(W * lf), int(H * tf), int(W * rf), int(H * bf)
    l, r = max(0, min(l, W - 1)), max(1, min(r, W))
    t, b = max(0, min(t, H - 1)), max(1, min(b, H))

    ink = _ink_mask(arr, theme)
    mask = np.zeros((H, W), bool)
    mask[t:b, l:r] = ink[t:b, l:r]

    # drop full-width horizontal lines (gridlines / support-resistance / box edges)
    width = max(1, r - l)
    row_frac = mask[:, l:r].sum(axis=1) / width
    horizon_rows = np.where(row_frac > HORIZON_FRAC)[0]
    mask[horizon_rows, :] = False

    col = mask.sum(axis=0)
    profile = col[l:r].astype(float)           # ink-count per column over the crop
    xs = np.where(profile > 0)[0] + l
    clusters = _cluster_columns(xs, gap=1)

    # ---- decide how to cut the inked span into individual candle windows ------
    windows: List[Tuple[int, int]] = []
    pitch_used = 0.0
    segmentation = "cluster"

    if n_candles_hint and int(n_candles_hint) >= 2 and len(xs):
        # user-supplied count: slice the whole inked span into equal bars
        x_lo, x_hi = int(xs.min()), int(xs.max())
        windows = _slice_window(x_lo, x_hi, int(n_candles_hint))
        segmentation = "hint"
        if windows:
            pitch_used = (x_hi - x_lo + 1) / float(int(n_candles_hint))
    else:
        pitch = _estimate_pitch(profile)
        # Trust the pitch (and slice merged runs) only when it is justified:
        #   * candles TOUCH  -> the inked span is almost fully filled, so
        #     clustering collapses many candles into one run; OR
        #   * the pitch is at least as wide as a single candle, so it cannot be
        #     a spurious within-candle period (e.g. hollow-body edges).
        # Otherwise the clusters already separate the candles — trust them.
        cluster_widths = [c1 - c0 + 1 for (c0, c1) in clusters]
        med_w = float(np.median(cluster_widths)) if cluster_widths else 0.0
        if len(xs):
            span = int(xs.max()) - int(xs.min()) + 1
            fill = len(xs) / float(max(1, span))
        else:
            fill = 0.0
        trust = bool(pitch) and (fill >= 0.85 or pitch >= 0.8 * med_w)

        if trust:
            pitch_used = float(pitch)
            for (cx0, cx1) in clusters:
                w = cx1 - cx0 + 1
                if w >= 1.5 * pitch:           # a merged run -> slice by pitch
                    nsub = max(1, int(round(w / pitch)))
                    windows.extend(_slice_window(cx0, cx1, nsub))
                    segmentation = "pitch"
                else:
                    windows.append((cx0, cx1))
        else:
            windows = list(clusters)           # clusters already separate candles

    candles: List[Candle] = []
    for (x0, x1) in windows:
        c = _extract_candle(mask, arr, theme, x0, x1)
        if c is not None:
            candles.append(c)

    pixel_top = min((c.top_y for c in candles), default=t)
    pixel_bot = max((c.bot_y for c in candles), default=b)

    return DigitizeResult(
        candles=candles, crop=(l, t, r, b), image_size=(W, H),
        pixel_top=pixel_top, pixel_bot=pixel_bot,
        horizon_rows_removed=int(len(horizon_rows)), theme=theme,
        pitch=round(pitch_used, 2), segmentation=segmentation,
    )


# =============================================================================
# Preview overlay
# =============================================================================
def render_overlay(image_bytes: bytes, result: DigitizeResult) -> Image.Image:
    """Draw what was detected back onto the image, so the user can judge it."""
    im = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    draw = ImageDraw.Draw(im)
    l, t, r, b = result.crop
    draw.rectangle([l, t, r, b], outline=(255, 140, 0), width=1)         # crop guide
    for c in result.candles:
        draw.line([(c.cx, c.top_y), (c.cx, c.bot_y)], fill=(0, 200, 255), width=1)  # wick
        color = (0, 170, 0) if c.bull else (220, 0, 160)
        draw.rectangle([c.x0, c.body_top_y, c.x1, c.body_bot_y], outline=color, width=1)
    return im


# =============================================================================
# Calibration  (pixels -> price)
# =============================================================================
def calibrate(result: DigitizeResult, price_high: float, price_low: float) -> pd.DataFrame:
    """
    Map detected pixels to prices with a linear 2-point calibration, where the
    detected pixel envelope (top wick .. bottom wick) corresponds to the two
    reference prices the user reads off the chart's price axis.

      price(y) = price_high + (y - pixel_top) * (price_low - price_high)
                                              / (pixel_bot - pixel_top)

    Returns a draft OHLC DataFrame (time, open, high, low, close) for review.
    """
    if not result.candles:
        raise ValueError("No candles detected — adjust the crop or candle style first.")
    if not (price_high > price_low):
        raise ValueError("Highest price must be greater than the lowest price.")

    ptop, pbot = result.pixel_top, result.pixel_bot
    span = pbot - ptop
    if span <= 0:
        raise ValueError("Degenerate pixel range — re-detect the candles.")

    def price(y: float) -> float:
        return price_high + (y - ptop) * (price_low - price_high) / span

    rows = []
    for i, c in enumerate(result.candles, start=1):
        high = price(c.top_y)
        low = price(c.bot_y)
        if c.bull:                          # hollow/green: open low, close high
            open_, close = price(c.body_bot_y), price(c.body_top_y)
        else:                               # filled/red: open high, close low
            open_, close = price(c.body_top_y), price(c.body_bot_y)
        rows.append({
            "time": i,
            "open": round(open_, 5),
            "high": round(high, 5),
            "low": round(low, 5),
            "close": round(close, 5),
        })
    return pd.DataFrame(rows)
