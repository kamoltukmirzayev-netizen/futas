"""
sessions.py
===============================================================================
FUTAS — World trading clocks + trading-session analysis.

Two parts:
  * Python session analysis (`session_brief`, `city_rows`, `telegram_session`):
    which FX/metal session is active now (Asian / London / New York / overlap),
    the volatility expectation, and a per-asset read for XAUUSD / BTCUSD / ETHUSD
    / Forex — computed from the current UTC time.
  * A self-contained live clock (`clock_html`): an HTML/JS panel that ticks every
    second in the browser (no Streamlit reruns) and shows, for each city, the
    local time and an Open / Pre-market / Closed / High-volatility badge.

Times use the standard-library `zoneinfo`. No third-party dependency is added.
===============================================================================
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    from zoneinfo import ZoneInfo
    _ZI = True
except Exception:                       # pragma: no cover
    _ZI = False

# (display name, IANA timezone, session-key for status)
CITIES: List[tuple] = [
    ("Tashkent",  "Asia/Tashkent",     "local"),
    ("UTC",       "UTC",               "ref"),
    ("New York",  "America/New_York",  "newyork"),
    ("London",    "Europe/London",     "london"),
    ("Frankfurt", "Europe/Berlin",     "london"),
    ("Tokyo",     "Asia/Tokyo",        "asian"),
    ("Hong Kong", "Asia/Hong_Kong",    "asian"),
    ("Singapore", "Asia/Singapore",    "asian"),
    ("Dubai",     "Asia/Dubai",        "asian"),
    ("Sydney",    "Australia/Sydney",  "sydney"),
]

# session windows in UTC hours [start, end) — may wrap past midnight
SESSIONS: Dict[str, tuple] = {
    "sydney":  (22, 7),
    "asian":   (0, 9),     # Tokyo open
    "london":  (8, 17),
    "newyork": (13, 22),
}
_SESSION_NAME = {"sydney": "Sydney", "asian": "Asian", "london": "London",
                 "newyork": "New York", "local": "Local (UTC+5)", "ref": "Reference"}


def _active(window: tuple, hour: float) -> bool:
    s, e = window
    return (s <= hour < e) if s <= e else (hour >= s or hour < e)


def active_sessions(now: Optional[datetime] = None) -> List[str]:
    now = now or datetime.now(timezone.utc)
    h = now.hour + now.minute / 60.0
    return [k for k, w in SESSIONS.items() if _active(w, h)]


def _asset_advice(asset: str, act: List[str], overlap: bool) -> str:
    if asset in ("BTCUSD", "ETHUSD"):
        return "24/7 — most active now (US hours)" if "newyork" in act else \
               "24/7 — calmer outside US hours"
    if asset == "XAUUSD":
        if overlap:
            return "Most active (London–NY overlap)"
        return "Active" if ("london" in act or "newyork" in act) else "Quiet (Asian hours)"
    # Forex majors
    if overlap:
        return "Most active (overlap)"
    if "london" in act or "newyork" in act:
        return "Active"
    if "asian" in act:
        return "JPY/AUD pairs active; EUR/GBP quiet"
    return "Quiet"


def session_brief(now: Optional[datetime] = None) -> Dict[str, Any]:
    """Active session, volatility expectation, per-asset read and a recommendation."""
    now = now or datetime.now(timezone.utc)
    act = active_sessions(now)
    overlap = ("london" in act and "newyork" in act)
    if overlap:
        label, vol = "Overlap (London + New York)", "High — London–New York overlap"
    elif "newyork" in act:
        label, vol = "New York session", "Elevated — New York session"
    elif "london" in act:
        label, vol = "London session", "Elevated — London session"
    elif "asian" in act or "sydney" in act:
        label, vol = "Asian session", "Moderate to low — Asian session"
    else:
        label, vol = "Between sessions", "Low — between sessions"
    recommended = overlap or ("london" in act) or ("newyork" in act)
    return {
        "active": [_SESSION_NAME[a] for a in act],
        "label": label,
        "overlap": overlap,
        "volatility": vol,
        "best_session": "London–New York overlap (13:00–17:00 UTC)",
        "recommended": recommended,
        "advice": ("Favourable trading window — liquidity and volatility are higher."
                   if recommended else
                   "Quieter window — thinner liquidity and ranges; trade selectively."),
        "assets": {
            "XAUUSD": _asset_advice("XAUUSD", act, overlap),
            "BTCUSD": _asset_advice("BTCUSD", act, overlap),
            "ETHUSD": _asset_advice("ETHUSD", act, overlap),
            "Forex (majors)": _asset_advice("FX", act, overlap),
        },
    }


def _local_time(tz: str, now: datetime) -> str:
    if _ZI:
        try:
            return now.astimezone(ZoneInfo(tz)).strftime("%H:%M:%S")
        except Exception:
            pass
    return now.strftime("%H:%M:%S") + " UTC"


def city_rows(now: Optional[datetime] = None) -> List[Dict[str, str]]:
    """City / local time / session / status snapshot (server-side)."""
    now = now or datetime.now(timezone.utc)
    h = now.hour + now.minute / 60.0
    overlap = _active(SESSIONS["london"], h) and _active(SESSIONS["newyork"], h)
    rows = []
    for name, tz, key in CITIES:
        if key in SESSIONS:
            if overlap and key in ("london", "newyork"):
                status = "High volatility"
            elif _active(SESSIONS[key], h):
                status = "Open"
            elif _active(SESSIONS[key], (h + 1) % 24):     # opens within the next hour
                status = "Pre-market"
            else:
                status = "Closed"
        else:
            status = "—"
        rows.append({"City": name, "Local time": _local_time(tz, now),
                     "Session": _SESSION_NAME.get(key, key), "Status": status})
    return rows


def telegram_session(now: Optional[datetime] = None) -> Dict[str, str]:
    """Compact session + key-city times for inclusion in a Telegram alert."""
    now = now or datetime.now(timezone.utc)
    b = session_brief(now)
    return {
        "session": b["label"],
        "condition": b["volatility"],
        "tashkent": _local_time("Asia/Tashkent", now),
        "newyork": _local_time("America/New_York", now),
        "london": _local_time("Europe/London", now),
    }


def clock_html(height: int = 300) -> str:
    """A self-contained live (ticking) world-clock panel — pure HTML/JS."""
    cities = [{"name": n, "tz": tz, "key": k} for n, tz, k in CITIES]
    data = json.dumps(cities)
    sessions = json.dumps(SESSIONS)
    return f"""
<div id="futas-clocks" style="font-family:system-ui,Segoe UI,Arial,sans-serif;">
  <div id="futas-banner" style="padding:8px 12px;border-radius:8px;margin-bottom:8px;
       font-weight:600;background:#eef2ff;color:#1e293b;"></div>
  <div id="futas-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));
       gap:8px;"></div>
</div>
<script>
const CITIES = {data};
const SESS = {sessions};
function active(win, h){{ const [s,e]=win; return s<=e ? (h>=s&&h<e) : (h>=s||h<e); }}
function statusFor(key, h, overlap){{
  if(!(key in SESS)) return ["—","#9ca3af"];
  if(overlap && (key==="london"||key==="newyork")) return ["High volatility","#d97706"];
  if(active(SESS[key], h)) return ["Open","#16a34a"];
  if(active(SESS[key], (h+1)%24)) return ["Pre-market","#2563eb"];
  return ["Closed","#9ca3af"];
}}
function render(){{
  const now = new Date();
  const hUTC = now.getUTCHours() + now.getUTCMinutes()/60;
  const overlap = active(SESS["london"],hUTC) && active(SESS["newyork"],hUTC);
  let label = "Between sessions", color="#64748b";
  if(overlap){{ label="Overlap — London + New York (high volatility)"; color="#b45309"; }}
  else if(active(SESS["newyork"],hUTC)){{ label="New York session"; color="#7c3aed"; }}
  else if(active(SESS["london"],hUTC)){{ label="London session"; color="#2563eb"; }}
  else if(active(SESS["asian"],hUTC)||active(SESS["sydney"],hUTC)){{ label="Asian session"; color="#0891b2"; }}
  const ban = document.getElementById("futas-banner");
  ban.textContent = "Active session: " + label + "  ·  " + now.toUTCString().slice(17,25) + " UTC";
  ban.style.background = color+"22"; ban.style.color = color;
  const grid = document.getElementById("futas-grid");
  grid.innerHTML = "";
  for(const c of CITIES){{
    let t;
    try {{ t = new Intl.DateTimeFormat('en-GB',{{timeZone:c.tz,hour:'2-digit',minute:'2-digit',second:'2-digit'}}).format(now); }}
    catch(e) {{ t = now.toUTCString().slice(17,25); }}
    const [stx,scol] = statusFor(c.key, hUTC, overlap);
    const card = document.createElement("div");
    card.style = "border:1px solid #e2e8f0;border-radius:8px;padding:8px 10px;background:#fff;";
    card.innerHTML = "<div style='font-weight:700;font-size:0.95rem;color:#0f172a'>"+c.name+"</div>"+
      "<div style='font-variant-numeric:tabular-nums;font-size:1.35rem;color:#111'>"+t+"</div>"+
      "<div style='font-size:0.8rem;color:"+scol+";font-weight:600'>"+stx+"</div>";
    grid.appendChild(card);
  }}
}}
render(); setInterval(render, 1000);
</script>
"""


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    b = session_brief()
    print("Active:", b["active"], "| label:", b["label"], "| vol:", b["volatility"])
    print("Recommended:", b["recommended"], "-", b["advice"])
    for k, v in b["assets"].items():
        print(f"  {k:16s}: {v}")
    print("\nCity rows:")
    for r in city_rows():
        print(f'  {r["City"]:10s} {r["Local time"]:12s} {r["Session"]:14s} {r["Status"]}')
    print("\nTelegram session block:", telegram_session())
