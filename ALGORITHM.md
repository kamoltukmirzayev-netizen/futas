# FUTAS — Algorithm Description

The complete processing flow of the Fibonacci Urvin Adaptive Trading Analysis
System, from raw data to exported report. Each stage names the engine function
that implements it (`futas_engine.py`) and states the exact rule applied.

---

## Flowchart

```
              ┌───────────┐
              │   START   │
              └─────┬─────┘
                    │
        ┌───────────▼────────────┐
        │  1. DATA INPUT         │   CSV · live fetch · table OCR · chart digitizer · manual · paste · synthetic
        │     normalize_ohlc()   │   → canonical time, open, high, low, close, volume
        └───────────┬────────────┘
                    │
        ┌───────────▼────────────┐
        │  2. HIGH / LOW DETECT   │   detect_range(mode, lookback)
        │     auto · full · LB    │   → High, Low, High_time, Low_time
        └───────────┬────────────┘
                    │
        ┌───────────▼────────────┐
        │  3. RANGE CALCULATION   │   Range = High − Low   (must be > 0)
        └───────────┬────────────┘
                    │
        ┌───────────▼────────────┐
        │  4. FIBONACCI URVIN     │   fu_levels(High, Low) → 15 levels · structural roles · liquidity bands
        │     ADAPTIVE LEVELS     │   P = Low + (High − Low) × K  for all 15 K
        └───────────┬────────────┘
                    │
        ┌───────────▼────────────┐
        │  5. TREND DETECTION     │   detect_swings() → detect_trend()
        │     UP / DOWN / SIDEWAY │   structure verdict ⊕ regression-slope verdict
        └───────────┬────────────┘
                    │
        ┌───────────▼────────────┐
        │  6. MARKET STRUCTURE    │   market_structure() → HH/HL/LH/LL, BOS, CHoCH
        │     + PHASE + MOMENTUM   │   detect_phase() · market_phase() 7-stage · momentum_state() (confirm only)
        └───────────┬────────────┘
                    │
        ┌───────────▼────────────┐
        │  7. SIGNAL GENERATION   │   generate_signal()  +  structure_confirmed() gate
        │     BUY / SELL / WAIT   │   integrate trend + structure + phase + FU levels
        └───────────┬────────────┘
                    │
        ┌───────────▼────────────┐
        │  8. RISK MANAGEMENT     │   Entry = price · SL & TP1-3 from FU levels · R/R
        │                         │   validity gate → WAIT if no SL/TP or R/R < min
        └───────────┬────────────┘
                    │
        ┌───────────▼────────────┐
        │  9. SCIENTIFIC EXPLAIN  │   scientific_explanation()
        └───────────┬────────────┘
                    │
        ┌───────────▼────────────┐
        │ 10. REPORT EXPORT       │   tables · charts · Excel · text · CSV
        └───────────┬────────────┘
                    │
              ┌─────▼─────┐
              │    END    │
              └───────────┘
```

---

## Stage 1 — Data Input  →  `normalize_ohlc()`

* Accepts OHLC from seven sources: **CSV**, a **live fetch**
  (`live_data.py` — Binance klines for crypto, Yahoo Finance chart JSON for
  gold / FX / stocks; `urllib` only, no API key, no extra dependency),
  **screenshot/photo of a data table** (OCR via `ocr_ingest.py`),
  **candlestick‑chart image** (approximate digitization via `chart_ingest.py`,
  reviewed before use), **manual** grid, **pasted text**, or a **synthetic
  sample**.
* Header names from TradingView / MT5 / Binance / Yahoo are auto‑mapped to the
  canonical `time, open, high, low, close, volume`.
* Separate `Date` + `Time` columns are merged; thousands‑separators are
  stripped; OHLC are coerced to numbers; empty/degenerate rows are rejected.

> **Chart digitizer (Stage 1 detail).** `chart_ingest.py` recovers the candles
> from a *picture* of a chart. It first tries column‑clustering, then — because
> dense/touching candles merge into a few clusters — falls back to a **fixed
> pitch** recovered from the median column spacing (and honours an optional
> *candle‑count hint*), so a chart of ~100 touching candles yields ~100 bars
> instead of collapsing to a handful. The result is always shown for review
> before analysis (see §7b of the README for the scientific‑honesty caveat).

> **Timeframe selection (Stage 1 detail).** A switch among
> `1M·5M·15M·30M·1H·4H·1D·1W` re‑runs the whole pipeline at the chosen horizon.
> `resample_ohlc()` aggregates **upward only** (open=first, high=max, low=min,
> close=last, volume=sum); finer‑than‑native timeframes are **disabled** for
> static data rather than fabricated (`available_timeframes()` /
> `native_timeframe()`), while live sources **re‑fetch** at the requested
> interval. `analyze(..., with_htf=True)` additionally computes a
> **higher‑timeframe** structural read (`htf_bias()`, two steps coarser) as a
> multi‑timeframe filter — exposed in `res.htf`, never altering the formula or
> the 15 coefficients.

## Stage 2 — High / Low Detection  →  `detect_range()`

* `mode="auto"` or `"lookback"` with a positive `lookback` uses the last *N*
  bars; otherwise the whole sample (`mode="full"`).
* `High = max(high)` and `Low = min(low)` of the selected window; their
  timestamps are recorded for the chart anchor.

## Stage 3 — Range Calculation

* `Range = High − Low`. If `Range ≤ 0` the pipeline stops with an error
  (levels cannot be computed from a degenerate range).

## Stage 4 — Fibonacci Urvin Adaptive Levels  →  `fu_levels()`

* For each of the **15 fixed coefficients** `K`, compute the level price with
  the single scientific formula:

  ```
  P = Low + (High − Low) × K
  ```

* Each level is tagged by **zone**: `inside` (0 ≤ K ≤ 1),
  `extension_up` (K > 1), `extension_down` (K < 0); and by **percent** = K × 100.
* Relative to the current price each level is later marked `support`,
  `resistance` or `at-price`.
* **Structural role (dissertation Table 3.2.2).** Each coefficient additionally
  carries a documented structural *meaning* (e.g. `0.5` = equilibrium /
  structural‑memory zone, `1.5993` = structural reversal zone, `-0.7973` =
  extreme‑volatility zone). This is a *label* attached to the level, never a
  change to its price.
* **Dynamic liquidity band (dissertation §3.3).** Each level also gets a
  `zone_low … zone_high` reaction band of half‑width `|Range| ×
  zone_halfwidth_pct` around the exact price, reflecting that price reacts to a
  *zone*, not an infinitely thin line. The band is drawn on the chart; the exact
  level price is still what SL/TP selection uses.

The 15 coefficients (order preserved):
`1.0, 0.0, 0.5, 0.5993, -0.6993, 1.5993, -0.5993, 1.1987, 1.6987, 1.7973, -0.1987, -0.0987, -0.7973, 0.3973, 1.0993`.

## Stage 5 — Trend Detection  →  `detect_swings()` → `detect_trend()`

* **Swings (fractals):** bar *i* is a swing high if its high is the maximum of
  the window `[i−left, i+right]` (mirror for swing low). Default `left=right=2`.
* **Structure verdict** (Smart‑Money style) from the last two swing highs/lows:
  * `HH and HL` → UPTREND
  * `LH and LL` → DOWNTREND
  * otherwise → MIXED
* **Slope verdict** from a linear regression on closes, normalised by range:
  `slope_norm > 0.30` → UPTREND, `< −0.30` → DOWNTREND, else SIDEWAY.
* **Reconciliation** (reduces false trends at inflections):
  * decisive structure **and** slope agrees‑or‑flat → use the structure;
  * structure and slope **conflict** → SIDEWAY (genuine inflection);
  * structure MIXED → fall back to the slope verdict.

## Stage 6 — Market Structure + Phase + Momentum  →  `market_structure()`, `structure_bias()`, `detect_phase()`, `market_phase()`, `momentum_state()`

* Every swing is labelled **HH / HL / LH / LL** (first of each kind as `H`/`L`).
* **Turning points:** a higher‑high after a bearish bias is a **CHoCH‑bull**
  (Change of Character), otherwise **BOS‑up** (Break of Structure); mirror logic
  produces **CHoCH‑bear / BOS‑down** on a lower‑low. The running bias flips on
  each break.
* `structure_bias()` returns the most recent decisive bias (`bull` / `bear` /
  `neutral`).
* **Phase (leg):** the current leg is **IMPULSE** when it moves with the trend,
  or **CORRECTION** when it retraces against it (RANGE when there is no trend).
* **Seven‑phase lifecycle (dissertation Table 3.3.1)** → `market_phase()`. On top
  of the impulse/correction leg, the market is placed on a structural lifecycle —
  *Impulse continuation → Volatility expansion → Liquidity concentration →
  Momentum weakening → Structural rejection → Reversal move → Corrective
  stabilization* — using the trend, structure labels, ATR‑based volatility
  expansion and the momentum read. The engine reports the current stage **and**
  the empirically‑expected next stage (`market_phase`, `market_phase_next`).
* **Momentum (dissertation §3.2, confirmation only)** → `momentum_state()`.
  RSI(14, Wilder), MACD(12/26/9) and ATR(14) are computed and summarised
  (`confirms_bull`, `confirms_bear`, `weakening`, `overbought`, `oversold`).
  These may only **raise or lower confidence** at Stage 7 — they can never create
  a signal and never veto one. Momentum is a *witness*, not a trigger.
* **Volume (Tier 2, confirmation only)** → `volume_confirmation()`. The latest
  bar's volume vs its recent average (`ratio`, `status`, `confirms`). Like
  momentum it only nudges confidence — above-average participation makes a set-up
  more trustworthy, but thin volume never vetoes it.
* **Higher-timeframe (Tier 2, confirmation only)** → `htf_bias()` in `res.htf`.
  Alignment with the coarser-timeframe structure nudges confidence up; opposition
  nudges it down.

## Stage 7 — Signal Generation  →  `generate_signal()`

Integrates trend + structure + phase with the FU levels:

* Context is **bullish** if `trend = UPTREND` or (`bias = bull` **and** the
  structural‑confirmation gate passes); **bearish** is the mirror.
* **Structural‑confirmation gate (dissertation §3.2)** → `structure_confirmed()`.
  A single swing is *not* a confirmation: when the context rests on bias alone
  (not a full trend), the engine requires the last two structure labels to be
  consecutive **HH + HL** (bull) or **LH + LL** (bear) before it will act. A
  confirmed trend bypasses the gate; an unconfirmed bias is downgraded to WAIT.
* **BUY** when the context is bullish **and** price is on / pulling back to a FU
  support (within a tolerance band, or `phase = CORRECTION`).
* **SELL** is the mirror image into a FU resistance.
* Otherwise **WAIT** (structure and levels do not agree on a side).
* **Confidence modifier (momentum, confirmation only).** After the side is
  decided, the confidence score is nudged **up** when momentum confirms the side
  and **down** when momentum is weakening — but momentum never changes the
  BUY/SELL/WAIT verdict itself.

## Stage 8 — Risk Management  (tasks 11–14, inside `generate_signal()`)

* **Entry** = the current price (never a stored number).
* **Anchor** = the FU level the price sits on
  (highest level ≤ price for BUY; lowest level ≥ price for SELL).
* **Stop‑Loss** = the next FU level *beyond* the anchor
  (one level below for BUY; one above for SELL).
* **TP1 / TP2 / TP3** = the next three FU levels in the trade direction.
* **Risk/Reward** for each target = reward ÷ risk
  (`(TP − Entry)/(Entry − SL)` for BUY; mirror for SELL).
* **Validity gate → WAIT** if there is no FU Stop‑Loss, no FU Take‑Profit, or
  the TP1 Risk/Reward is below the configured minimum.
* A **confidence** score (LOW / MEDIUM / HIGH) is accumulated from trend
  strength, structure agreement, phase and Risk/Reward.

> Every Stop‑Loss and Take‑Profit is therefore guaranteed to be one of the 15
> Fibonacci Urvin levels — the core scientific constraint.

## Stage 9 — Scientific Explanation  →  `scientific_explanation()`

Produces a structured, human‑readable justification: the detected range and
formula, the trend/structure/phase reasoning, why the chosen FU levels were
selected for SL/TP, the Risk/Reward, and the confidence — with the standing
note that the system does not provide financial advice.

## Stage 10 — Report Export

The web app renders the candlestick chart with the 15 levels, the swing markers
and the diagonal Low→High anchor, plus the signal panel and the backtest equity
curve. Results export to **Excel** (`openpyxl`: Summary, FU_Levels, Signal,
Coefficients, Backtest_Trades, Backtest_Stats), **text report**, and **CSV**.

> **Real-time alert delivery (`telegram_signals.py`).** When Stage 7 produces a
> **confirmed BUY/SELL** that passes the user's direction + confidence filters,
> the **📡 Telegram Signal Center** pushes it to the user's chat via the Telegram
> Bot API — once per unique set-up (deduplicated by an asset/timeframe/action/
> entry/SL/TP signature). The message (`format_signal()`) carries the entry, the
> FU-derived SL and TP1–3 with their level annotations, RSI, the seven-phase
> stage, bias, confidence and timeframe, plus the standing *not financial advice*
> notice. It delivers **alerts only** — it never places an order.

---

## Backtest (validation, no look‑ahead)  →  `backtest()`

A walk‑forward loop recomputes the FU levels and the signal from the **rolling
window only**. A trade opens when a BUY/SELL appears with no open position and
closes on the first later bar that touches **TP1** (win) or the **Stop‑Loss**
(loss). It returns the trade list, the equity curve, and statistics
(total trades, win rate, net profit, profit factor, max drawdown).

Two parameters make it defensible for the dissertation:

* **Holding horizon** (`max_hold`). A trade that reaches neither TP1 nor the
  Stop‑Loss within `max_hold` bars closes at that bar's close as a third
  **NEUTRAL** outcome. This breaks the CSR/FSF tautology — with a third bucket,
  CSR + FSF + NEU = 100, so CSR + FSF < 100 (as in the dissertation's figures).
* **Transaction cost** (`cost_bps`, or a split **`spread_bps` + `commission_bps`
  + `slippage_bps`**). A round‑trip cost in basis points of entry is charged to
  every trade, expressed in R units of that trade's own stop distance — realistic
  for gold and crypto.
* **Trade management** (`tp_management`, Tier 2). `single` exits the whole
  position at TP1. `scaled` takes **partial profit** at TP1/TP2/TP3 by
  `tp_weights`, moves the stop to **break‑even** after TP1, and optionally
  **trails** it to TP1 after TP2 — resolved forward by `_resolve_trade()` with no
  look‑ahead in the entry decision.

### Statistical significance + benchmarks  →  `monte_carlo_significance()`, `benchmark_compare()`

* **Monte‑Carlo permutation test.** The backtest is re‑run on many random
  re‑orderings of the *same* bars (`_permute_bars()` keeps max‑High / min‑Low —
  hence the level grid — fixed and destroys only the temporal structure). The
  one‑sided **p‑value** = P(random ≥ real) shows whether the edge comes from
  market **structure** or chance.
* **Classical‑Fibonacci baseline.** The identical pipeline is run with the
  textbook retracement/extension ratios via `fu_levels(..., coeffs=…)` —
  **baseline only, never inside FUTAS** — to demonstrate the Urvin set adds value.
* **Buy‑and‑hold.** The naive benchmark every trading study must beat.

### SFVT structural‑validation metrics (dissertation §3.1)  →  `sfvt_metrics()`

Alongside the equity statistics the backtest reports the dissertation’s
**Structural‑Filter Validation Test** metrics so the method can be judged on
*structural* terms, not just P/L:

* **CSR — Continuation Success Rate:** share of signals whose structure
  continued as projected (≈ the TP1‑before‑SL win rate).
* **FSF — False‑Signal Frequency:** share of signals invalidated by an immediate
  opposite structural break.
* **NEU — Indecisive rate:** share of signals that expired at the holding horizon
  (reached neither TP nor SL). Present only when `max_hold > 0`; it is what lets
  CSR + FSF sum to less than 100%.
* **SPR — Structural Persistence Rate:** how long the post‑signal structure held
  its HH/HL (or LH/LL) sequence (`_structural_persistence()`).
* **Δ vs baseline:** CSR minus a plain **RSI/MA** baseline (`_rsi_ma_baseline()`),
  i.e. the structural edge over a conventional indicator.

These are shown next to the dissertation’s own reference figures
(`DISSERTATION_SFVT_REFERENCE`: XAUUSD 76.9 / 16.0 / 77.6 / +19.5;
BTCUSD 69.6 / 22.8 / 70.2 / +19.8) for direct comparison.

---

## Worked entry → exit example (no look‑ahead)  →  `worked_example()`

Reconstructs one *real* historical trade to answer “**if you had entered here and
closed there, you would have made this much**”, in technical terms and without
peeking at the future:

1. Scan candidate bars in the **first part of the series** (`[window …
   n × entry_search_end_frac]`, default the first 70 %) and, at each bar, run the
   full analysis **on the rolling window up to that bar only** — no look‑ahead.
2. Pick the **highest‑confidence valid** BUY/SELL set‑up (respecting `min_rr`).
   Entry = the live price at that bar; SL and TP1‑3 are FU levels, exactly as in
   live analysis.
3. **Walk forward** bar by bar to the first touch of **TP1** (win) or the
   **Stop‑Loss** (loss); on a bar that straddles both, the **SL is taken first**
   (conservative).
4. Report `entry/exit` price & time, `profit_pct`, `r_multiple`, bars held, the
   FU‑level labels used, and a plain‑language `narrative`.

It is surfaced in the app’s **🎬 Worked example** tab and is purely illustrative —
**not** advice.

---

## End‑to‑end (one call)  →  `analyze()`

```
analyze(data) =
    normalize_ohlc → detect_range → fu_levels(+roles,+zones) → detect_swings →
    detect_trend → market_structure → structure_bias → detect_phase →
    momentum_state → structure_confirmed → market_phase(7-stage) →
    generate_signal → scientific_explanation → FUTASResult
```

`FUTASResult` carries the asset, bar count, High/Low/Range, the 15 levels (with
structural roles and liquidity bands), the swings and structure events, the trend
(+ metrics), the phase, the **seven‑phase** stage and expected next stage, the
**momentum** read, the **structural‑confirmation** flags, the signal
(Entry/SL/TP/RR/confidence), the explanation, and the frozen coefficient list —
everything needed for the tables, charts and reports above.
