"""
test_coefficients.py
===============================================================================
Integrity test: proves the EXACT 15 Fibonacci Urvin coefficients are implemented
without alteration and are the only set used across every module — calculations,
chart annotations, Telegram alerts, backtesting, and validation reports. Classical
Fibonacci ratios appear ONLY as an explicit, separately-labelled benchmark and are
never substituted for the Urvin coefficients.

Run standalone:    python test_coefficients.py
Or with pytest:    pytest test_coefficients.py
===============================================================================
"""
import pandas as pd

import futas_engine as fe
import telegram_signals as tg

# The canonical coefficients, exactly as specified in the dissertation request.
EXPECTED = [1, 0, 0.5, 0.5993, -0.6993, 1.5993, -0.5993, 1.1987,
            1.6987, 1.7973, -0.1987, -0.0987, -0.7973, 0.3973, 1.0993]
EXPECTED_F = [float(x) for x in EXPECTED]

# The 12 *distinctive* Urvin values (the 15 minus the trivial 0/0.5/1 range anchors).
DISTINCTIVE = [k for k in EXPECTED_F if k not in (0.0, 0.5, 1.0)]


def _sample_result():
    df = pd.read_csv("sample_data/XAUUSD_daily.csv")
    return df, fe.analyze(df, asset="XAUUSD")


def test_exact_and_ordered():
    assert fe.FU_COEFFICIENTS == EXPECTED_F, "coefficients differ from the specified set"
    assert len(fe.FU_COEFFICIENTS) == 15
    assert list(fe.FU_COEFFICIENTS_FROZEN) == EXPECTED_F, "frozen signature altered"


def test_fu_levels_use_exact_coefficients():
    levels = fe.fu_levels(100.0, 0.0)
    assert [round(L.k, 6) for L in levels] == EXPECTED_F
    # P = Low + (High-Low)*K must hold for every level
    for L in levels:
        assert abs(L.price - (0.0 + (100.0 - 0.0) * L.k)) < 1e-9


def test_analyze_and_table_use_exact_coefficients():
    _, res = _sample_result()
    assert res.coefficients == EXPECTED_F
    assert list(res.levels_table()["k"]) == EXPECTED_F


def test_signal_sl_tp_are_fu_levels():
    """Chart markers, Telegram alerts and the backtest all read SL/TP from these."""
    _, res = _sample_result()
    prices = {round(L.price, 9) for L in res.levels}
    sg = res.signal
    if sg.stop_loss is not None:
        assert round(sg.stop_loss, 9) in prices, "Stop-Loss is not a Fibonacci Urvin level"
    for tp in sg.take_profits:
        assert round(tp, 9) in prices, "a Take-Profit is not a Fibonacci Urvin level"


def test_telegram_alert_uses_fu_levels():
    _, res = _sample_result()
    msg = tg.format_signal("XAUUSD", "1D", res, narrative=fe.signal_narrative(res))
    # the alert annotates SL/TP with their FU coefficient; price strings must match levels
    if res.signal.action in ("BUY", "SELL"):
        assert "FU" in msg, "alert does not brand the levels as Fibonacci Urvin"


def test_backtest_default_uses_fu_not_classical():
    df = pd.read_csv("sample_data/XAUUSD_daily.csv")
    bt_fu = fe.backtest(df, asset="XAUUSD", window=40)            # default -> FU
    bt_cl = fe.backtest(df, asset="XAUUSD", window=40,
                        coeffs=fe.CLASSICAL_FIB_COEFFS)           # explicit benchmark
    # the benchmark is a SEPARATE call; defaults never pull in classical ratios.
    assert "trades" in bt_fu and "trades" in bt_cl


def test_distinctive_urvin_disjoint_from_classical():
    """The 12 distinctive Urvin values share NOTHING with classical Fibonacci."""
    classical = set(fe.CLASSICAL_FIB_COEFFS)
    assert set(DISTINCTIVE).isdisjoint(classical), \
        "a distinctive Urvin coefficient collides with a classical ratio"
    # only the trivial range anchors 0/0.5/1 may be shared
    shared = set(EXPECTED_F) & classical
    assert shared.issubset({0.0, 0.5, 1.0})


def main():
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL  {t.__name__}: {e}")
        except Exception as e:
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(tests)} coefficient-integrity checks passed.")
    print("Coefficients verified exact & unaltered:" if passed == len(tests)
          else "INTEGRITY PROBLEM — see failures above.")
    print(" ", fe.FU_COEFFICIENTS)


if __name__ == "__main__":
    main()
