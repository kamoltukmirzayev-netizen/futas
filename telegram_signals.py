"""
telegram_signals.py
===============================================================================
FUTAS — Telegram Signal Center (real-time alert delivery).

Sends FUTAS BUY / SELL set-ups to a user's Telegram chat through the official
Telegram Bot API. Only the Python standard library is used (urllib + json), so
**no extra dependency** is added to requirements.txt — the same approach as
`live_data.py`.

IMPORTANT — scope & safety
--------------------------
* This module only DELIVERS NOTIFICATIONS. It never places an order, executes a
  trade, or moves money. Every signal message carries the standing FUTAS notice
  that the system is a scientific-research instrument and does **not** provide
  financial advice.
* The Bot Token is a secret. The application keeps it in per-session memory only
  (never written to disk or logs) and shows it masked after saving. This module
  receives the token as an argument and does not persist it anywhere.

Telegram set-up (the wizard mirrors this):
    1. Open Telegram, search @BotFather.
    2. /newbot  ->  choose a name  ->  receive the Bot Token.
    3. Open your new bot and press /start  (required before it can message you).
    4. Find your numeric Chat ID (this module's get_chat_id_hint() helps, or use
       @userinfobot).
    5. Paste the token + chat id into FUTAS, Connect, Send Test Signal.
===============================================================================
"""

from __future__ import annotations

import html
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

_API = "https://api.telegram.org/bot{token}/{method}"
_UA = {"User-Agent": "FUTAS scientific research"}

# Timeframes the FUTAS dashboard exposes (kept in sync with futas_engine.TIMEFRAMES)
TIMEFRAMES: List[str] = ["1M", "5M", "15M", "30M", "1H", "4H", "1D", "1W"]


# ---------------------------------------------------------------------------
# Low-level Bot API call
# ---------------------------------------------------------------------------
def _call(token: str, method: str, params: Optional[Dict[str, Any]] = None,
          timeout: int = 15) -> Dict[str, Any]:
    """Call a Bot API method. Returns the parsed JSON dict (may have ok=False)."""
    url = _API.format(token=(token or "").strip(), method=method)
    data = urlencode(params).encode("utf-8") if params else None
    req = Request(url, data=data, headers=_UA)            # POST if data else GET
    with urlopen(req, timeout=timeout) as r:              # noqa: S310 (fixed host)
        return json.loads(r.read().decode("utf-8"))


def _friendly_http(e: HTTPError) -> str:
    """Map a Telegram HTTPError to an actionable message."""
    detail = ""
    try:
        body = json.loads(e.read().decode("utf-8"))
        detail = body.get("description", "")
    except Exception:
        pass
    base = {
        400: "Bad request — check the Chat ID is correct.",
        401: "Unauthorized — the Bot Token is invalid.",
        403: "Forbidden — open the bot in Telegram and press /start first.",
        404: "Not found — the Bot Token looks malformed.",
        429: "Rate limited by Telegram — wait a moment and try again.",
    }.get(e.code, f"Telegram HTTP {e.code}: {e.reason}")
    return f"{base} {('(' + detail + ')') if detail else ''}".strip()


# ---------------------------------------------------------------------------
# Validation / connection
# ---------------------------------------------------------------------------
def validate_token(token: str) -> Dict[str, Any]:
    """
    Verify a Bot Token via getMe. Returns
    {ok, bot_username, bot_name} or {ok: False, error}.
    """
    if not token or ":" not in token:
        return {"ok": False, "error": "Token looks malformed (expected '<id>:<hash>')."}
    try:
        res = _call(token, "getMe")
        if res.get("ok"):
            u = res.get("result", {})
            return {"ok": True,
                    "bot_username": u.get("username", ""),
                    "bot_name": u.get("first_name", "")}
        return {"ok": False, "error": res.get("description", "Invalid token.")}
    except HTTPError as e:
        return {"ok": False, "error": _friendly_http(e)}
    except URLError as e:
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:                                  # pragma: no cover
        return {"ok": False, "error": str(e)}


def validate_chat_id(chat_id: str) -> bool:
    """
    A Telegram chat id is a (possibly negative) integer, or an @channel handle.
    Accept both; reject obviously wrong input.
    """
    s = str(chat_id or "").strip()
    if not s:
        return False
    if s.startswith("@"):
        return len(s) >= 4
    if s.startswith("-"):
        s = s[1:]
    return s.isdigit() and len(s) >= 5


def get_chat_id_hint(token: str) -> Dict[str, Any]:
    """
    Read recent updates (getUpdates) and surface the chat ids that have messaged
    the bot — a convenience so the user can find their Chat ID after /start.
    """
    try:
        res = _call(token, "getUpdates", {"limit": 20})
        if not res.get("ok"):
            return {"ok": False, "error": res.get("description", "getUpdates failed.")}
        chats: List[Dict[str, Any]] = []
        seen = set()
        for upd in res.get("result", []):
            msg = upd.get("message") or upd.get("edited_message") or upd.get("channel_post") or {}
            chat = msg.get("chat") or {}
            cid = chat.get("id")
            if cid is not None and cid not in seen:
                seen.add(cid)
                chats.append({
                    "id": cid,
                    "type": chat.get("type", ""),
                    "name": (chat.get("username") or chat.get("title")
                             or chat.get("first_name") or ""),
                })
        return {"ok": True, "chats": chats}
    except HTTPError as e:
        return {"ok": False, "error": _friendly_http(e)}
    except URLError as e:
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:                                  # pragma: no cover
        return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Sending
# ---------------------------------------------------------------------------
def send_message(token: str, chat_id: str, text: str,
                 parse_mode: str = "HTML") -> Dict[str, Any]:
    """
    Send a message. Returns {ok, message_id} or {ok: False, error} — never raises,
    so the dashboard can show a clean status instead of crashing.
    """
    if not token:
        return {"ok": False, "error": "Not connected (no Bot Token)."}
    if not validate_chat_id(chat_id):
        return {"ok": False, "error": "Invalid Chat ID."}
    try:
        res = _call(token, "sendMessage", {
            "chat_id": str(chat_id).strip(),
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": "true",
        })
        if res.get("ok"):
            return {"ok": True, "message_id": res.get("result", {}).get("message_id")}
        return {"ok": False, "error": res.get("description", "Send failed.")}
    except HTTPError as e:
        return {"ok": False, "error": _friendly_http(e)}
    except URLError as e:
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:                                  # pragma: no cover
        return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Message formatting
# ---------------------------------------------------------------------------
_DISCLAIMER = ("⚠️ FUTAS is a scientific-research instrument and does "
               "<b>not</b> provide financial advice.")
_NOTICE = "This is an analytical alert only and not financial advice."

# nominal seconds per timeframe (for the signal validity window)
TIMEFRAME_SECONDS: Dict[str, int] = {
    "1M": 60, "5M": 300, "15M": 900, "30M": 1800,
    "1H": 3600, "4H": 14400, "1D": 86400, "1W": 604800,
}


def _valid_until(timeframe: str, valid_bars: int, start: Optional[datetime] = None) -> str:
    start = start or datetime.now(timezone.utc)
    secs = TIMEFRAME_SECONDS.get(timeframe, 3600) * max(1, int(valid_bars))
    return (start + timedelta(seconds=secs)).strftime("%Y-%m-%d %H:%M:%S")


def _fmt_price(v: Optional[float]) -> str:
    if v is None:
        return "—"
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "—"
    a = abs(v)
    if a >= 100:
        return f"{v:,.2f}"
    if a >= 1:
        return f"{v:.4f}"
    return f"{v:.6f}"


def _lvl_tag(level: Any) -> str:
    """A short Fibonacci Urvin level annotation, e.g. ' (FU 159.9%)'."""
    if level is None:
        return ""
    pct = getattr(level, "percent", None)
    return f"  ·  FU {pct:.1f}%" if pct is not None else ""


def signal_signature(asset: str, timeframe: str, res: Any) -> str:
    """
    Stable id of a signal so the dashboard sends each set-up only once. Built from
    asset, timeframe, signal type, entry, stop-loss, take-profit levels and the
    structural phase — a constantly-changing wall-clock time is deliberately NOT
    included, otherwise nothing would ever deduplicate.
    """
    s = getattr(res, "signal", None)
    if s is None:
        return ""
    # Identity = the SET-UP (direction + FU stop/targets + phase) on this timeframe.
    # The raw entry (live price) is deliberately excluded so the same set-up in the
    # same price zone is not re-sent every candle (dedup by candle + price zone).
    tps = "/".join(f"{t:.6g}" for t in (s.take_profits or []))
    phase = getattr(res, "market_phase", "") or getattr(res, "phase", "")
    return f"{asset}|{timeframe}|{s.action}|{(s.stop_loss or 0):.6g}|{tps}|{phase}"


def passes_filter(action: str, confidence_score: float, rr: Optional[float] = None,
                  side: str = "Both", confidence: str = "All confirmed",
                  min_rr: float = 0.0, min_confidence: float = 0.0,
                  htf_aligned: Optional[bool] = None, require_htf: bool = False,
                  volume_ok: Optional[bool] = None, require_volume: bool = False,
                  high_threshold: float = 0.70, medium_threshold: float = 0.45) -> bool:
    """
    Apply the user's alert filters to a confirmed signal:
    direction · confidence band · minimum R/R · minimum confidence ·
    optional higher-timeframe alignment · optional volume confirmation.
    """
    if action not in ("BUY", "SELL"):
        return False
    if side == "BUY only" and action != "BUY":
        return False
    if side == "SELL only" and action != "SELL":
        return False
    cs = float(confidence_score)
    if confidence == "High-confidence only" and cs < high_threshold:
        return False
    if confidence == "Medium and high-confidence" and cs < medium_threshold:
        return False
    if min_confidence and cs < float(min_confidence):
        return False
    if min_rr and rr is not None and float(rr) < float(min_rr):
        return False
    if require_htf and not bool(htf_aligned):
        return False
    if require_volume and not bool(volume_ok):
        return False
    return True


def _nearest_fu(res: Any) -> str:
    """The Fibonacci Urvin level the entry price is reacting to (percent + role)."""
    try:
        e = float(res.signal.entry)
        lv = min(res.levels, key=lambda L: abs(L.price - e))
        role = getattr(lv, "role", "") or getattr(lv, "zone", "")
        return f"{lv.percent:.1f}%" + (f" ({role})" if role else "")
    except Exception:
        return "—"


def format_signal(asset: str, timeframe: str, res: Any,
                  narrative: Optional[Dict[str, str]] = None,
                  valid_bars: int = 12, signal_time: Optional[str] = None,
                  session: Optional[Dict[str, str]] = None,
                  labels: Optional[Dict[str, str]] = None) -> str:
    """
    Build the rich FUTAS TRADING ALERT for a confirmed signal: entry / SL / TP1-3
    (each with its Fibonacci Urvin level), R/R, RSI, volume status, market
    structure, the FU level in play, higher-timeframe confirmation, confidence,
    the signal time and validity window, and the scenario / reason / invalidation
    (from `futas_engine.signal_narrative`, passed in as `narrative`).
    """
    s = res.signal
    mom = getattr(res, "momentum", {}) or {}
    vol = getattr(res, "volume_conf", {}) or {}
    htf = getattr(res, "htf", {}) or {}
    rsi = mom.get("rsi")
    rsi_txt = f"{rsi:.1f}" if isinstance(rsi, (int, float)) and rsi == rsi else "—"
    bias = (getattr(res, "trend_metrics", {}) or {}).get("structure_bias", "—")
    struct = getattr(res, "struct_conf", {}) or {}
    if s.action == "BUY":
        struct_txt = "bullish confirmed (HH + HL)" if struct.get("bull") else f"bullish bias ({bias})"
    else:
        struct_txt = "bearish confirmed (LH + LL)" if struct.get("bear") else f"bearish bias ({bias})"
    rr_txt = f"1:{s.rr[0]:.2f}" if getattr(s, "rr", None) else "—"
    vol_txt = (f"{vol.get('status')} (×{vol.get('ratio')})"
               + (" ✓" if vol.get("confirms") else "")) if vol.get("available") else "n/a"
    if htf.get("timeframe"):
        aligned = ((s.action == "BUY" and htf.get("aligned_bull")) or
                   (s.action == "SELL" and htf.get("aligned_bear")))
        htf_txt = f"{htf['timeframe']} {htf.get('trend', '—')} " + ("✓ aligned" if aligned else "✗ mixed")
    else:
        htf_txt = "n/a"
    nar = narrative or {}
    tps = list(s.take_profits or [])
    tp_levels = list(getattr(s, "tp_levels", []) or [])
    ts = signal_time or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    emoji = "🟢" if s.action == "BUY" else "🔴"

    def tp(i: int) -> str:
        if i < len(tps):
            tag = _lvl_tag(tp_levels[i]) if i < len(tp_levels) else ""
            return _fmt_price(tps[i]) + tag
        return "—"

    _L = labels or {}

    def lab(key: str, default: str) -> str:
        return html.escape(str(_L.get(key, default)))

    sess = session or {}
    sess_lines: List[str] = []
    if sess:
        sess_lines = [
            "",
            f"<b>{lab('f_session', 'World Session')}:</b> {html.escape(str(sess.get('session', '—')))}",
            f"<b>{lab('f_condition', 'Market Condition')}:</b> {html.escape(str(sess.get('condition', '—')))}",
            (f"<b>Tashkent:</b> {sess.get('tashkent', '—')}  ·  "
             f"<b>London:</b> {sess.get('london', '—')}  ·  "
             f"<b>New York:</b> {sess.get('newyork', '—')}"),
        ]

    a = html.escape(str(asset))
    notice = str(_L.get("notice_text", _NOTICE))
    lines = [
        f"📊 <b>{lab('alert_title', 'FUTAS TRADING ALERT')}</b>",
        "",
        f"<b>{lab('f_asset', 'Asset')}:</b> {a}",
        f"<b>{lab('f_timeframe', 'Timeframe')}:</b> {html.escape(str(timeframe))}",
        f"<b>{lab('f_signal_type', 'Signal Type')}:</b> {emoji} <b>{s.action}</b>",
        f"<b>{lab('f_entry', 'Entry Price')}:</b> {_fmt_price(s.entry)}",
        f"<b>{lab('f_sl', 'Stop Loss')}:</b> {_fmt_price(s.stop_loss)}{_lvl_tag(getattr(s, 'sl_level', None))}",
        f"<b>{lab('f_tp1', 'Take Profit 1')}:</b> {tp(0)}",
        f"<b>{lab('f_tp2', 'Take Profit 2')}:</b> {tp(1)}",
        f"<b>{lab('f_tp3', 'Take Profit 3')}:</b> {tp(2)}",
        "",
        f"<b>{lab('f_rr', 'Risk/Reward Ratio')}:</b> {rr_txt}",
        f"<b>{lab('f_rsi', 'RSI')}:</b> {rsi_txt}",
        f"<b>{lab('f_volume', 'Volume Status')}:</b> {html.escape(str(vol_txt))}",
        f"<b>{lab('f_structure', 'Market Structure')}:</b> {html.escape(struct_txt)}",
        f"<b>{lab('f_fu_level', 'Fibonacci Urvin Level')}:</b> {html.escape(_nearest_fu(res))}",
        f"<b>{lab('f_htf', 'Higher Timeframe Confirmation')}:</b> {html.escape(htf_txt)}",
        f"<b>{lab('f_confidence', 'Confidence Score')}:</b> {s.confidence_score*100:.0f}% ({s.confidence})",
    ] + sess_lines + [
        "",
        f"<b>{lab('f_time', 'Signal Time')}:</b> {ts} UTC",
        f"<b>{lab('f_valid', 'Signal Valid Until')}:</b> {_valid_until(str(timeframe), valid_bars)} UTC",
        f"<b>{lab('f_status', 'Status')}:</b> 🟢 {lab('f_status_active', 'ACTIVE (monitoring TP / SL)')}",
        "",
        f"<b>{lab('f_scenario', 'Scenario')}:</b> {html.escape(nar.get('scenario', '—'))}",
        f"<b>{lab('f_reason', 'Reason for Entry')}:</b> {html.escape(nar.get('reason', '—'))}",
        f"<b>{lab('f_invalidation', 'Invalidation Condition')}:</b> {html.escape(nar.get('invalidation', '—'))}",
        "",
        f"<b>{lab('f_notice', 'Notice')}:</b> {html.escape(notice)}",
    ]
    return "\n".join(lines)


_LIFECYCLE = {
    "TP1": ("✅", "TP1 Reached"),
    "TP2": ("✅", "TP2 Reached"),
    "TP3": ("✅", "Trade Completed Successfully"),
    "SL":  ("❌", "Stop Loss Triggered"),
}


def lifecycle_message(event: str, asset: str, timeframe: str, level_price: float,
                      entry: float, action: str) -> str:
    """
    Trade-lifecycle update sent after a signal: TP1/TP2/TP3 reached, trade
    completed, or stop-loss triggered.
    """
    emoji, title = _LIFECYCLE.get(event, ("ℹ️", event))
    lines = [
        f"{emoji} <b>{title}</b>",
        "",
        f"<b>Asset:</b> {html.escape(str(asset))}",
        f"<b>Timeframe:</b> {html.escape(str(timeframe))}",
        f"<b>Direction:</b> {html.escape(str(action))}",
        f"<b>Level hit:</b> {_fmt_price(level_price)}",
        f"<b>Original entry:</b> {_fmt_price(entry)}",
        f"<b>Time:</b> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC",
        "",
        f"<b>Notice:</b> {_NOTICE}",
    ]
    return "\n".join(lines)


def build_test_message(asset: str = "XAUUSD", timeframe: str = "1H") -> str:
    """
    Connection test ONLY — deliberately contains NO BUY/SELL, entry, stop-loss or
    take-profit, so it can never be mistaken for (or contradict) a real signal.
    Real alerts are sent only when the engine confirms and validates a set-up.
    """
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "🔌 <b>FUTAS — Telegram connection test</b>",
        "",
        f"<b>Context:</b> {html.escape(asset)} · {html.escape(timeframe)}",
        f"<b>Time:</b> {ts} UTC",
        "",
        "✅ Your bot is <b>connected</b>.",
        "",
        "This is a <b>connection test, not a trading signal</b> — it carries no "
        "entry, stop-loss or take-profit. A real <b>FUTAS TRADING ALERT</b> is sent "
        "only when the engine confirms <b>and validates</b> a BUY or SELL set-up "
        "(valid entry/SL/TP, acceptable R/R, structure + candle confirmation, and "
        "your confidence/HTF/volume filters). It will always match the app.",
        "",
        f"<b>Notice:</b> {_NOTICE}",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    # offline checks (no network)
    print("validate_chat_id('123456789') :", validate_chat_id("123456789"))
    print("validate_chat_id('-1001234567'):", validate_chat_id("-1001234567"))
    print("validate_chat_id('@channel')   :", validate_chat_id("@channel"))
    print("validate_chat_id('abc')        :", validate_chat_id("abc"))
    print("validate_token('bad')          :", validate_token("bad"))
    print("\n--- TEST MESSAGE ---")
    print(build_test_message())
