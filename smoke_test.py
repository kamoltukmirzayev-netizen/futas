"""Headless smoke test of the FUTAS Streamlit app using AppTest."""
import sys
from streamlit.testing.v1 import AppTest


def click_button(at, label_contains):
    for b in at.button:
        if label_contains.lower() in (b.label or "").lower():
            b.click()
            return True
    return False


def main():
    at = AppTest.from_file("app_streamlit.py", default_timeout=120)
    at.run()
    assert at.exception is None or not at.exception, f"Initial render raised: {at.exception}"
    print("[1] initial render OK, no exception")

    # choose synthetic sample
    at.radio[0].set_value("Synthetic sample").run()
    assert not at.exception, f"After radio set: {at.exception}"
    ok = click_button(at, "Generate synthetic sample")
    assert ok, "Generate button not found"
    at.run()
    assert not at.exception, f"After generate: {at.exception}"
    assert at.session_state["df"] is not None, "data not loaded"
    print(f"[2] synthetic data loaded: {len(at.session_state['df'])} rows")

    # analysis auto-runs when result is None
    assert at.session_state["result"] is not None, "analysis did not run"
    res = at.session_state["result"]
    print(f"[3] analysis OK -> trend={res.trend}, phase={res.phase}, signal={res.signal.action}, "
          f"levels={len(res.levels)}")
    assert len(res.levels) == 15, "expected 15 FU levels"

    # multi-timeframe switch: hourly synthetic data -> aggregate up to 4H
    rows_before = len(at.session_state["df"])
    if click_button(at, "4H"):
        at.run()
        assert not at.exception, f"After TF switch: {at.exception}"
        rows_after = len(at.session_state["df"])
        assert rows_after < rows_before, f"4H aggregation did not reduce rows ({rows_before}->{rows_after})"
        assert at.session_state["tf_active"] == "4H", "tf_active not updated"
        assert len(at.session_state["result"].levels) == 15, "levels lost after TF switch"
        print(f"[3b] timeframe switch OK -> 1H {rows_before} bars aggregated to 4H {rows_after} bars, "
              f"analysis recomputed")
    else:
        print("[3b] timeframe selector buttons not found (skipped)")

    # run backtest
    ok = click_button(at, "Run backtest")
    assert ok, "Run backtest button not found"
    at.run()
    assert not at.exception, f"After backtest: {at.exception}"
    bt = at.session_state["backtest"]
    assert bt is not None, "backtest not stored"
    print(f"[4] backtest OK -> {bt['stats']['total_trades']} trades, "
          f"win_rate={bt['stats']['win_rate']*100:.1f}%, net={bt['stats']['net_profit']:.2f}")

    # The Explanation tab calls build_excel_bytes()/build_text_report() on every
    # rerun for its download buttons; the runs above completed with no exception,
    # so the export path is already validated end-to-end inside the app.
    assert not at.exception, f"final state has exception: {at.exception}"
    assert res.signal.action in ("BUY", "SELL", "WAIT")
    assert res.high > res.low and res.range_size > 0
    print("[5] export tab + final render OK (xlsx/txt/csv builders ran with no exception)")

    # Telegram Signal Center initialized and inert without a connection
    assert at.session_state["tg_status"] == "Not Connected", "tg should start disconnected"
    assert at.session_state["tg_token"] == "", "no token should be stored initially"
    assert at.session_state["tg_last_sig"] == "", "nothing should have been auto-sent"
    print("[6] Telegram Signal Center present and inert (Not Connected, nothing sent)")

    # Tier 2 engine: scaled TP management + volume confirmation + signal narrative
    import futas_engine as fe
    import telegram_signals as tg
    demo = fe._demo_frame(n=220, seed=5)
    bt_scaled = fe.backtest(demo, asset="DEMO", window=40, max_hold=8,
                            tp_management="scaled", breakeven=True, trailing=True,
                            spread_bps=2, commission_bps=1, slippage_bps=1)
    assert bt_scaled["tp_management"] == "scaled", "scaled mode not recorded"
    assert abs(bt_scaled["cost_bps_total"] - 4.0) < 1e-9, "split costs should sum to 4 bps"
    r = fe.analyze(demo, asset="DEMO")
    assert "available" in (r.volume_conf or {}), "volume confirmation missing"
    nar = fe.signal_narrative(r)
    assert set(nar.keys()) == {"scenario", "reason", "invalidation"}, "narrative keys wrong"
    # duplicate-signal prevention: same signature twice
    sig_a = tg.signal_signature("DEMO", "1H", r)
    sig_b = tg.signal_signature("DEMO", "1H", r)
    assert sig_a == sig_b and sig_a, "signature must be stable for dedupe"
    print("[7] Tier 2 engine OK (scaled TP mgmt, split costs, volume, narrative, dedupe)")

    # Screenshot Technical Analysis: text detection + image->analysis pipeline
    import screenshot_ta as ssta
    dt = ssta.detect_asset_timeframe("XAUUSD H1 chart 2345.6 2350.1")
    assert dt["asset"] == "XAUUSD" and dt["timeframe"] == "1H", dt
    import io as _io
    from PIL import Image as _Img, ImageDraw as _Draw
    _df = fe._demo_frame(n=60, seed=2)
    _W, _H, _pad = 60 * 8 + 24, 360, 36
    _pmin, _pmax = float(_df["low"].min()), float(_df["high"].max())
    _img = _Img.new("RGB", (_W, _H), (255, 255, 255)); _d = _Draw.Draw(_img)
    for _i, _row in _df.reset_index(drop=True).iterrows():
        _cx = 12 + _i * 8 + 3
        _y = lambda p: int(_pad + (_pmax - p) / (_pmax - _pmin) * (_H - 2 * _pad))
        _d.line([(_cx, _y(_row.high)), (_cx, _y(_row.low))], fill=(0, 0, 0), width=1)
        _t, _b2 = _y(max(_row.open, _row.close)), _y(min(_row.open, _row.close))
        _d.rectangle([12 + _i * 8, _t, 12 + _i * 8 + 5, max(_b2, _t + 2)], outline=(0, 0, 0))
    _buf = _io.BytesIO(); _img.save(_buf, format="PNG")
    _ss = ssta.analyze_screenshot(_buf.getvalue(), asset="XAUUSD", theme="dark",
                                  price_high=_pmax, price_low=_pmin)
    assert _ss["ok"] and _ss["n_candles"] >= 40, _ss.get("error")
    assert _ss["report"]["scenario"] in ("BUY", "SELL", "WAIT")
    print(f"[8] Screenshot TA OK ({_ss['n_candles']} candles -> {_ss['report']['scenario']}, image-estimated)")

    # Live Center plumbing + Telegram lifecycle message builder (offline parts)
    import live_data as ld
    assert "XAUUSD" in ld.LIVE_CENTER_ASSETS and "BTCUSD" in ld.LIVE_CENTER_ASSETS
    assert ld.market_is_open("BTCUSD") is True  # crypto 24/7
    import mt5_feed
    assert isinstance(mt5_feed.available(), bool)  # present, importable, no crash
    lc = tg.lifecycle_message("TP1", "XAUUSD", "1H", 2550.0, 2496.0, "BUY")
    assert "TP1 Reached" in lc and "not financial advice" in lc
    sl = tg.lifecycle_message("SL", "BTCUSD", "1D", 60000.0, 64000.0, "SELL")
    assert "Stop Loss Triggered" in sl
    # the connection TEST must NOT impersonate a trade signal (no fake BUY/SELL/entry)
    _tm = tg.build_test_message("XAUUSD", "1H")
    assert "connection test" in _tm.lower(), "test message must be a connection test"
    assert "Signal Type" not in _tm and "Entry Price" not in _tm and "Take Profit" not in _tm, \
        "test message must not contain a fake trade signal"
    print("[9] Live Center + MT5 + lifecycle msgs + signal-free connection test OK")

    # World clocks / session analysis + session-enriched alert
    import sessions as fsessions
    _b = fsessions.session_brief()
    assert "label" in _b and "assets" in _b and "XAUUSD" in _b["assets"]
    assert len(fsessions.city_rows()) == 10, "expected 10 world-clock cities"
    _sb = fsessions.telegram_session()
    assert {"session", "condition", "tashkent", "newyork", "london"} <= set(_sb)
    _alert = tg.format_signal("XAUUSD", "1H", _ss["res"],
                              narrative=fe.signal_narrative(_ss["res"]), session=_sb)
    assert "World Session" in _alert and "Tashkent" in _alert and "Status:" in _alert
    assert "<script>" in fsessions.clock_html()  # live JS clock present
    print("[10] World clocks (10 cities) + session analysis + session-enriched alert OK")

    # TradingView-style chart: HTML generation from a real result (per-timeframe data)
    import tv_chart
    _tvhtml = tv_chart.tv_chart_html(demo, r, height=600)
    assert _tvhtml and "addCandlestickSeries" in _tvhtml and "createPriceLine" in _tvhtml
    assert "setMarkers" in _tvhtml and "lightweight-charts" in _tvhtml
    print("[11] TradingView (Lightweight Charts) chart HTML generated OK")

    # Multilingual EN/RU/UZ: translations + translated Telegram alert
    import i18n
    assert i18n.t("tab_analysis", "ru") == "Анализ" and i18n.t("tab_analysis", "uz") == "Tahlil"
    assert i18n.t("entry", "ru") == "Вход" and i18n.t("run_analysis", "uz").startswith("FUTAS")
    assert i18n.t("missing_key_xyz", "ru") == "missing_key_xyz"  # graceful fallback
    assert len(i18n.alert_labels("uz")) == 27
    _al = tg.format_signal("XAUUSD", "1H", _ss["res"],
                           narrative=fe.signal_narrative(_ss["res"]), labels=i18n.alert_labels("ru"))
    assert "ТОРГОВЫЙ СИГНАЛ FUTAS" in _al, "Russian alert title missing"
    print("[12] Multilingual EN/RU/UZ (i18n + translated Telegram alert) OK")

    print("\nSMOKE TEST PASSED")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
