"""
tv_chart.py
===============================================================================
FUTAS — TradingView-quality candlestick chart via **Lightweight Charts**
(TradingView's own open-source charting library, loaded from a CDN).

This renders the SAME data the engine computed for the *selected timeframe*:
candles + Fibonacci Urvin price-lines + Entry/SL/TP lines + HH/HL/LH/LL markers.
The library gives crisp, anti-aliased, high-DPI candles with smooth zoom/pan and
a crosshair OHLC read-out — i.e. it looks and behaves like TradingView, while the
Fibonacci Urvin overlays are drawn on top of the same series.

Only NEAR-price FU levels are drawn so the candles always dominate the view
(far extensions stay off-frame), and structure markers auto-stack without
overlapping. Returns an HTML string for st.components.v1.html, or None when the
data has no usable datetime index (the app then falls back to the Plotly chart).
===============================================================================
"""

from __future__ import annotations

import json
from typing import Any, Optional

import pandas as pd


def _unix(t: Any) -> Optional[int]:
    try:
        ts = pd.Timestamp(t)
        if pd.isna(ts):
            return None
        return int(ts.timestamp())
    except Exception:
        return None


def tv_chart_html(df: pd.DataFrame, res: Any, height: int = 600,
                  price_action_mode: bool = True) -> Optional[str]:
    times = pd.to_datetime(df["time"], errors="coerce")
    if times.notna().sum() < 3:
        return None                       # no datetime -> caller uses Plotly

    rows, seen = [], set()
    for t, o, h, l, c in zip(times, df["open"], df["high"], df["low"], df["close"]):
        u = _unix(t)
        if u is None or u in seen:
            continue
        seen.add(u)
        rows.append({"time": u, "open": float(o), "high": float(h),
                     "low": float(l), "close": float(c)})
    rows.sort(key=lambda r: r["time"])
    if len(rows) < 3:
        return None

    pmin = min(r["low"] for r in rows)
    pmax = max(r["high"] for r in rows)
    span = (pmax - pmin) or 1.0
    lo_b, hi_b = pmin - 0.15 * span, pmax + 0.15 * span    # near-price band only

    levels = []
    for L in res.levels:
        if not (lo_b <= L.price <= hi_b):
            continue                       # keep candles dominant
        if L.zone == "inside":
            col, ls = "#2962ff", 0
        elif L.zone == "extension_up":
            col, ls = "#00897b", 2
        else:
            col, ls = "#8e24aa", 2
        levels.append({"price": round(float(L.price), 6), "color": col, "ls": ls,
                       "lw": 2 if L.k in (0.0, 0.5, 1.0) else 1,
                       "title": f"FU {L.k:g} ({L.percent:.0f}%)"})

    plan = []
    sg = res.signal
    if sg.action in ("BUY", "SELL"):
        plan.append({"price": round(float(sg.entry), 6), "color": "#111827", "title": "ENTRY"})
        if sg.stop_loss is not None:
            plan.append({"price": round(float(sg.stop_loss), 6), "color": "#b71c1c", "title": "SL"})
        for i, tp in enumerate(sg.take_profits):
            plan.append({"price": round(float(tp), 6), "color": "#1b5e20", "title": f"TP{i+1}"})

    marks = []
    for e in res.structure[-40:]:
        if e.label not in ("HH", "HL", "LH", "LL"):
            continue
        u = _unix(e.time)
        if u is None:
            continue
        high = e.label in ("HH", "LH")
        marks.append({"time": u, "position": "aboveBar" if high else "belowBar",
                      "color": "#1b5e20" if e.label in ("HH", "HL") else "#b71c1c",
                      "shape": "arrowDown" if high else "arrowUp", "text": e.label})
    marks.sort(key=lambda m: m["time"])

    data_j, lv_j, pl_j, mk_j = (json.dumps(rows), json.dumps(levels),
                                json.dumps(plan), json.dumps(marks))
    fu_w = 1 if price_action_mode else 1   # near levels stay readable
    return f"""
<div id="futas-tv" style="width:100%;height:{height}px;"></div>
<div id="futas-tv-msg" style="font:13px system-ui;color:#94a3b8"></div>
<script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
<script>
(function(){{
  var el=document.getElementById('futas-tv');
  if(!window.LightweightCharts){{
    document.getElementById('futas-tv-msg').textContent=
      'TradingView chart library could not load (offline?). Switch off the TradingView toggle to use the built-in chart.';
    return;
  }}
  var chart=LightweightCharts.createChart(el,{{
    height:{height},
    layout:{{background:{{color:'#ffffff'}},textColor:'#334155',fontSize:12}},
    grid:{{vertLines:{{color:'#f1f5f9'}},horzLines:{{color:'#f1f5f9'}}}},
    timeScale:{{timeVisible:true,secondsVisible:false,borderColor:'#cbd5e1'}},
    rightPriceScale:{{borderColor:'#cbd5e1'}},
    crosshair:{{mode:LightweightCharts.CrosshairMode.Normal}},
  }});
  var s=chart.addCandlestickSeries({{
    upColor:'#00c853',downColor:'#ff1744',borderUpColor:'#00c853',
    borderDownColor:'#ff1744',wickUpColor:'#00c853',wickDownColor:'#ff1744'}});
  s.setData({data_j});
  {lv_j}.forEach(function(l){{ s.createPriceLine({{price:l.price,color:l.color,
     lineWidth:l.lw,lineStyle:l.ls,axisLabelVisible:true,title:l.title}}); }});
  {pl_j}.forEach(function(p){{ s.createPriceLine({{price:p.price,color:p.color,
     lineWidth:2,lineStyle:0,axisLabelVisible:true,title:p.title}}); }});
  try {{ s.setMarkers({mk_j}); }} catch(e) {{}}
  chart.timeScale().fitContent();
  new ResizeObserver(function(){{ chart.applyOptions({{width:el.clientWidth}}); }}).observe(el);
}})();
</script>
"""


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    import futas_engine as fe
    d = fe._demo_frame(n=120, seed=4)
    r = fe.analyze(d, asset="XAUUSD")
    html = tv_chart_html(d, r)
    print("html generated:", bool(html), "| length:", len(html) if html else 0)
    for token in ("addCandlestickSeries", "createPriceLine", "setMarkers", "lightweight-charts"):
        print(f"  contains {token}:", token in (html or ""))
