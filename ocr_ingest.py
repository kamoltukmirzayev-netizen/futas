"""
ocr_ingest.py
===============================================================================
FUTAS — optical ingest of OHLC data from a screenshot / photo.

Scope & scientific honesty
--------------------------
This module extracts OHLC data from an *image of a data table* (e.g. a
TradingView/MT5 data-window screenshot, an exported price table, a photographed
spreadsheet). For tabular numeric data this is reliable.

Reading OHLC values directly out of a *raw candlestick chart photo* (pixels of
candles) is NOT scientifically reliable — the exact open/high/low/close cannot
be recovered to the precision a quantitative method requires. FUTAS therefore
treats chart-photo extraction as best-effort only and always lets the analyst
review / correct the parsed table before it enters the engine.

OCR backend is optional and degrades gracefully:
    1. pytesseract  (needs the Tesseract binary; on Streamlit Cloud add
       `tesseract-ocr` to packages.txt)
    2. if unavailable -> a clear message + the universal "paste table text"
       fallback (parse_ohlc_text) which needs no OCR at all.
===============================================================================
"""

from __future__ import annotations

import io
import re
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

# ---- optional dependencies, imported defensively ---------------------------
try:
    from PIL import Image, ImageOps, ImageFilter  # type: ignore
    _HAS_PIL = True
except Exception:  # pragma: no cover
    _HAS_PIL = False

try:
    import pytesseract  # type: ignore
    _HAS_TESS = True
except Exception:  # pragma: no cover
    _HAS_TESS = False


# =============================================================================
# Capability probe
# =============================================================================
def ocr_status() -> dict:
    """Report which OCR capabilities are available in this environment."""
    tess_bin = False
    version = None
    if _HAS_TESS:
        try:
            version = str(pytesseract.get_tesseract_version())
            tess_bin = True
        except Exception:
            tess_bin = False
    return {
        "pillow": _HAS_PIL,
        "pytesseract_pkg": _HAS_TESS,
        "tesseract_binary": tess_bin,
        "tesseract_version": version,
        "ready": bool(_HAS_PIL and _HAS_TESS and tess_bin),
    }


# =============================================================================
# Image pre-processing (improves OCR on screenshots)
# =============================================================================
def _preprocess(img: "Image.Image", upscale: float = 2.0) -> "Image.Image":
    img = img.convert("L")                       # grayscale
    img = ImageOps.autocontrast(img)
    if upscale and upscale != 1.0:
        w, h = img.size
        img = img.resize((int(w * upscale), int(h * upscale)))
    img = img.filter(ImageFilter.SHARPEN)
    return img


def image_to_text(image: "bytes | str | Image.Image", psm: int = 6) -> str:
    """Run OCR over an image and return raw text. Raises if OCR is unavailable."""
    status = ocr_status()
    if not status["ready"]:
        raise RuntimeError(
            "OCR engine not available. "
            f"(pillow={status['pillow']}, pytesseract={status['pytesseract_pkg']}, "
            f"tesseract_binary={status['tesseract_binary']}). "
            "Install Tesseract and pytesseract, or use the 'paste table text' "
            "fallback instead."
        )
    if isinstance(image, bytes):
        img = Image.open(io.BytesIO(image))
    elif isinstance(image, str):
        img = Image.open(image)
    else:
        img = image
    img = _preprocess(img)
    config = f"--oem 3 --psm {psm}"
    return pytesseract.image_to_string(img, config=config)


# =============================================================================
# Text -> OHLC parsing (works for OCR output AND manual paste)
# =============================================================================
# Match comma-grouped numbers (1,234.5) first, then decimals, then integers.
_NUM_RE = re.compile(r"[-+]?\d{1,3}(?:,\d{3})+(?:\.\d+)?|[-+]?\d+\.\d+|[-+]?\d+")
# Date / time tokens are removed before numeric extraction so they cannot
# pollute the OHLC numbers (e.g. "2026-01-10" must not become 2026, -01, -10).
_DT_RE = re.compile(
    r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}(?:[ T]\d{1,2}:\d{2}(?::\d{2})?)?"
    r"|\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}"
    r"|\d{1,2}:\d{2}(?::\d{2})?"
)
_HEADER_TOKENS = {
    "open": ["open", "o"],
    "high": ["high", "h", "max"],
    "low": ["low", "l", "min"],
    "close": ["close", "c", "price", "last"],
    "time": ["date", "time", "datetime", "timestamp"],
    "volume": ["volume", "vol", "v"],
}


def _to_float(tok: str) -> Optional[float]:
    t = tok.replace(" ", "").replace(",", "")
    try:
        return float(t)
    except ValueError:
        return None


def _detect_header(lines: List[str]) -> Optional[Tuple[int, List[str]]]:
    """Find a header row and return (line_index, column-order list)."""
    for i, ln in enumerate(lines[:5]):
        low = ln.lower()
        order: List[str] = []
        for canon, toks in _HEADER_TOKENS.items():
            for t in toks:
                if re.search(rf"\b{re.escape(t)}\b", low):
                    order.append(canon)
                    break
        if {"open", "high", "low", "close"}.issubset(set(order)):
            return i, order
    return None


def parse_ohlc_text(text: str, assume_order: Optional[str] = None) -> pd.DataFrame:
    """
    Parse free text (OCR output or pasted table) into an OHLC DataFrame.

    Strategy
    --------
    * If a header row is detected, numeric columns are mapped by header order.
    * Otherwise each line's numeric tokens are used; a row needs >= 4 numbers.
        - 5+ numbers  -> assume [..., O, H, L, C, (V)] taking O,H,L,C,V slots
        - exactly 4   -> assume O, H, L, C
    * `assume_order` (e.g. "ohlc", "hloc", "ohlcv") forces a column order.
    Each row is validated so that High = max and Low = min are consistent.
    """
    rows: List[dict] = []
    raw_lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    forced = list(assume_order.lower()) if assume_order else None
    header = _detect_header(raw_lines) if not forced else None
    col_order = header[1] if header else None
    start = (header[0] + 1) if header else 0

    for ln in raw_lines[start:]:
        clean = _DT_RE.sub(" ", ln)          # drop dates/times first
        nums = _NUM_RE.findall(clean)
        vals = [v for v in (_to_float(n) for n in nums) if v is not None]
        if len(vals) < 4:
            continue

        row = {}
        if col_order:
            numeric_targets = [c for c in col_order if c in ("open", "high", "low", "close", "volume")]
            for c, v in zip(numeric_targets, vals[-len(numeric_targets):]):
                row[c] = v
        elif forced:
            mapping = {"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"}
            seq = [mapping[ch] for ch in forced if ch in mapping]
            for c, v in zip(seq, vals[: len(seq)]):
                row[c] = v
        else:
            ohlc = vals[-5:] if len(vals) >= 5 else vals[-4:]
            keys = ["open", "high", "low", "close", "volume"][: len(ohlc)]
            for c, v in zip(keys, ohlc):
                row[c] = v

        if not {"open", "high", "low", "close"}.issubset(row):
            continue
        rows.append(row)

    if not rows:
        raise ValueError(
            "Could not parse any OHLC rows from the text. Make sure each line "
            "contains at least 4 numbers (Open, High, Low, Close)."
        )

    df = pd.DataFrame(rows)
    for c in ["open", "high", "low", "close", "volume"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)

    # enforce OHLC consistency
    df["high"] = df[["open", "high", "low", "close"]].max(axis=1)
    df["low"] = df[["open", "high", "low", "close"]].min(axis=1)
    df.insert(0, "time", np.arange(len(df)))
    return df


def image_to_ohlc(
    image: "bytes | str", assume_order: Optional[str] = None, psm: int = 6
) -> Tuple[pd.DataFrame, str]:
    """
    Full pipeline: image -> OCR text -> OHLC DataFrame.
    Returns (dataframe, raw_ocr_text). Raise on failure with a helpful message.
    """
    text = image_to_text(image, psm=psm)
    df = parse_ohlc_text(text, assume_order=assume_order)
    return df, text


# =============================================================================
# Self-test (no OCR needed — exercises the text parser)
# =============================================================================
if __name__ == "__main__":
    print("OCR status:", ocr_status())
    sample = """
    Date        Open     High     Low      Close    Volume
    2026-01-10  4559.97  4575.20  4551.10  4570.40  1200
    2026-01-11  4570.40  4602.00  4566.80  4596.46  1500
    2026-01-12  4596.46  4620.10  4588.30  4618.05  1800
    """
    out = parse_ohlc_text(sample)
    print(out.to_string(index=False))
