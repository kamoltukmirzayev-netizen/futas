# FUTAS — Fibonacci Urvin Adaptive Trading Analysis System

A scientific‑research and algorithm‑testing **web application** for technical
analysis of international‑trade and digital‑economy assets (cryptocurrency and
gold). FUTAS detects market structure and projects an adaptive grid of price
levels from a single linear formula, then derives a fully‑auditable
**BUY / SELL / WAIT** signal with Entry, Stop‑Loss, Take‑Profit and
Risk/Reward — every one of which is selected only from the calculated levels.

> **Dissertation:** *“Technical analysis methods of international trade and
> trading strategies of the digital economy and cryptocurrency (based on
> cryptocurrency and gold assets).”*
> **Specialization:** 08.00.16 — Digital economy and international digital integration.

> ⚠️ **FUTAS is a scientific instrument. It does NOT provide financial advice**
> and must not be used as the sole basis for any trading decision.

---

## 1. Scientific basis

Classical technical analysis uses fixed Fibonacci retracement ratios (0.236,
0.382, 0.618, …). FUTAS instead uses the **Fibonacci Urvin adaptive coefficient
system** — a fixed research result of **exactly 15 coefficients**. Every price
level in the entire system is produced from these coefficients through one
linear projection:

```
P = Low + (High − Low) × K
```

| Symbol | Meaning |
|--------|---------|
| `P`    | the calculated price level |
| `High` | the high of the analysed range |
| `Low`  | the low of the analysed range |
| `K`    | a Fibonacci Urvin adaptive coefficient |

**The 15 coefficients (fixed, order preserved):**

```
1.0, 0.0, 0.5, 0.5993, -0.6993, 1.5993, -0.5993, 1.1987,
1.6987, 1.7973, -0.1987, -0.0987, -0.7973, 0.3973, 1.0993
```

`K = 0` → the level equals **Low**; `K = 1` → equals **High**; `K = 0.5` → the
mid‑point; `K > 1` are upward extensions; `K < 0` are downward extensions.

**Scientific guarantee.** No Entry, Stop‑Loss or Take‑Profit value is ever
taken from an external source, an old analysis, or a hard‑coded number.
The Entry is the live price; the Stop‑Loss and every Take‑Profit are *selected
only* from the 15 computed Fibonacci Urvin levels.

---

## 2. What it does (functional capabilities)

1. Load OHLC data from **CSV**, a **live data fetch** (Binance for crypto, Yahoo
   Finance for gold / FX / stocks), a **screenshot / photo of a data table**
   (OCR), or an approximate digitization of a **candlestick chart image**
   (the *Chart image (digitizer)* source).
2. Auto‑detect the dominant **High** and **Low** of the range.
3. Compute the **15 Fibonacci Urvin levels** with `P = Low + (High − Low) × K`.
4. Classify the **trend**: UPTREND / DOWNTREND / SIDEWAY.
5. Detect **swing highs / lows** (fractal pivots).
6. Label **market structure**: HH / HL / LH / LL.
7. Mark **structural turning points** (BOS — Break of Structure, CHoCH —
   Change of Character).
8. Distinguish **impulse vs correction** phases.
9. **Integrate** market structure with the Fibonacci Urvin levels.
10. Generate a **BUY / SELL / WAIT** signal.
11. Take the **Entry** from the current price.
12. Select the **Stop‑Loss** only from the FU levels.
13. Select **TP1 / TP2 / TP3** only from the FU levels.
14. Compute **Risk/Reward** for every target.
15. Produce a **scientific explanation** for each signal.
16. Render **tables, charts and reports** (Excel / text / CSV).
17. Provide **technical conclusions** suitable for the dissertation.

A walk‑forward **backtest** (equity curve, win rate, profit factor, max
drawdown) is included to test the method without look‑ahead bias.

### 2a. Dissertation methodology (integrated, additive — the 15 coefficients are unchanged)

The third chapter of the dissertation is implemented on top of the level grid.
None of it alters `P = Low + (High − Low) × K` or the 15 coefficients; it only
*interprets* and *gates*:

* **Per‑coefficient structural roles (Table 3.2.2).** Each coefficient carries a
  documented structural meaning (e.g. `0.5` = equilibrium / structural‑memory
  zone, `1.5993` = structural reversal zone, `-0.7973` = extreme‑volatility
  zone). Shown in the levels table as `structural_role`.
* **Dynamic liquidity zones (§3.3).** Each level is drawn as a reaction **band**
  around the exact price, not as an infinitely thin line — reflecting that price
  reacts to a zone.
* **Momentum as confirmation only (§3.2).** RSI(14) and MACD are computed but may
  only *raise or lower confidence* — they never create or veto a signal.
* **Structural‑confirmation gate (§3.2).** A single swing is not a confirmation:
  a bias‑only context needs consecutive **HH + HL** (bull) or **LH + LL** (bear).
* **Seven‑phase structural model (Table 3.3.1).** The market is placed on a
  lifecycle — *Impulse continuation → Volatility expansion → Liquidity
  concentration → Momentum weakening → Structural rejection → Reversal move →
  Corrective stabilization* — with the empirically‑expected next stage.
* **SFVT structural validation metrics (§3.1).** The backtest reports **CSR**
  (continuation success), **FSF** (false‑signal frequency), **SPR** (structural
  persistence) and **Δ** vs a plain RSI/MA baseline, next to the dissertation’s
  own reference figures.
* **Worked entry → exit example.** Reconstructs a real historical trade with **no
  look‑ahead** and reports the realized result: *“if you had entered here and
  closed there, you would have made this much.”*

---

## 3. Project structure

```
FUTAS/
├── futas_engine.py            # scientific core (levels, structure, signal, backtest)
├── live_data.py               # live OHLC + quote snapshots (Binance crypto + Yahoo gold/FX/stocks)
├── mt5_feed.py                # OPTIONAL MetaTrader 5 live feed (local Windows; auto-fallback to cloud)
├── sessions.py                # world trading clocks (live) + trading-session analysis
├── i18n.py                    # trilingual interface (English / Русский / Oʻzbek)
├── tv_chart.py                # TradingView-quality candles (Lightweight Charts)
├── telegram_signals.py        # Telegram Signal Center — real-time alerts + TP/SL lifecycle (stdlib)
├── screenshot_ta.py           # Screenshot Technical Analysis — chart image → full FUTAS read
├── ocr_ingest.py              # screenshot/photo of a data TABLE → OHLC (Tesseract)
├── chart_ingest.py            # candlestick CHART image → approximate OHLC (Pillow+numpy)
├── app_streamlit.py           # the web application (UI)
├── smoke_test.py              # headless end-to-end check of the app (AppTest)
├── test_coefficients.py       # integrity test: the exact 15 coefficients, used everywhere
├── make_excel_template.py     # builds FUTAS_Excel_Template.xlsx
├── FUTAS_Excel_Template.xlsx  # spreadsheet calculator (generated)
├── requirements.txt           # Python dependencies
├── packages.txt               # system packages for Streamlit Cloud (tesseract-ocr)
├── .streamlit/config.toml     # theme + server settings
├── sample_data/
│   ├── generate_samples.py    # rebuilds the demo CSVs (deterministic)
│   ├── XAUUSD_daily.csv        # gold demo (clean BUY set‑up)
│   └── BTCUSD_daily.csv        # bitcoin demo (clean SELL set‑up)
├── README.md                  # this file
├── EXCEL_FORMULAS.md          # every spreadsheet formula, documented
├── ALGORITHM.md               # the algorithm flow (START → … → END)
└── DISSERTATION_FUTAS.md      # 2–3 page scientific description (OAK style)
```

---

## 4. Setup

Requires **Python 3.10+** (tested on 3.13).

```bash
# 1. (optional) create an isolated environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# 2. install dependencies
pip install -r requirements.txt
```

Dependencies: `pandas`, `numpy`, `streamlit`, `plotly`, `matplotlib`,
`openpyxl` (all required by the brief), plus `pillow` + `pytesseract` for the
optional image ingest.

**Tesseract (only for screenshot/photo OCR).** The Python package
`pytesseract` calls the system Tesseract binary:

* **Windows:** install *Tesseract‑OCR* (e.g. the UB‑Mannheim build) and ensure
  `tesseract.exe` is on `PATH`.
* **macOS:** `brew install tesseract`
* **Linux:** `sudo apt install tesseract-ocr`
* **Streamlit Cloud:** handled automatically by `packages.txt`.

OCR is optional — if Tesseract is absent, every other feature still works and
the app shows a clear status message.

---

## 5. Running the web application

```bash
python -m streamlit run app_streamlit.py
```

Then open the URL Streamlit prints (default `http://localhost:8501`).
(`python -m streamlit …` is used because the `streamlit` command may not be on
`PATH`.)

### Using the app

0. **Pick a language** at the top of the sidebar — **English / Русский / Oʻzbek**.
   The interface chrome (tabs, labels, the active‑timeframe banner) and the
   **Telegram alerts** are translated; analysis values stay universal (`i18n.py`).
1. **Choose a data source** in the sidebar:
   * **CSV upload** — your own OHLC file.
   * **Live data fetch** — pull candles directly from **Binance** (crypto) or
     **Yahoo Finance** (gold / FX / stocks); see §7c.
   * **Manual input** — paste/edit rows in a grid.
   * **Chart image (digitizer)** — approximate OHLC from a candlestick *chart*
     screenshot (§7b).
   * **Image / screenshot (OCR)** — upload a screenshot or photo of an OHLC
     *table* (§7).
   * **Synthetic sample** — generate deterministic demo data.

   (To analyse a *picture of a chart*, use the **📷 Screenshot TA** tab — §7d.)
2. Set the **asset name** and, if you wish, tune the analysis controls
   (range mode, look‑back window, swing sensitivity, tolerance, minimum
   Risk/Reward, manual price override).
3. Read the results across the tabs:
   * **🛰️ Live Center** — dedicated live‑market dashboard (Bid/Ask/spread/day‑change/
     high/low/market‑status) for **XAUUSD, BTCUSD, ETHUSD and major FX**, powered by
     Binance + Yahoo (cloud‑compatible) with an **optional local MetaTrader 5** feed
     that auto‑activates on Windows and auto‑falls‑back to the cloud otherwise (§12b).
   * **📊 Analysis** — candlestick chart with the 15 FU levels drawn as
     **dynamic liquidity bands**, swings, the diagonal Low→High anchor, plus the
     **seven‑phase** market‑lifecycle stage and the **momentum** (RSI / MACD)
     confirmation read‑out. A **⏱️ timeframe selector**
     (`1M·5M·15M·30M·1H·4H·1D·1W`) recomputes the entire analysis at the chosen
     horizon — it **re‑fetches** for live data and **aggregates upward** for
     static data (timeframes finer than the loaded data are disabled rather than
     fabricated). A **higher‑timeframe bias** read is shown beside it as a
     multi‑timeframe filter.
   * **🎯 Signal & Risk** — Entry / SL / TP1‑3 / Risk‑Reward.
   * **🧪 Backtest report** — equity curve, statistics and the **SFVT** structural
     validation panel (CSR / FSF / **NEU** / SPR / Δ vs an RSI‑MA baseline, next to
     the dissertation’s reference figures). Supports a **holding horizon** (so a
     signal can also expire *neutral* — CSR + FSF need not sum to 100%), a split
     **spread / commission / slippage** cost model, and **Tier‑2 trade
     management** (single, or *scaled* partial exits at TP1/TP2/TP3 with
     break‑even and optional trailing). An optional **🔬 statistical‑validation**
     run adds a **Monte‑Carlo permutation p‑value**, **bootstrap CIs**, a
     **parameter‑sensitivity** sweep, an **in/out‑of‑sample** split, a head‑to‑head
     **FUTAS vs classical‑Fibonacci vs buy‑and‑hold** comparison, and a
     downloadable **validation report**.
   * **🎬 Worked example** — reconstructs a real historical trade with **no
     look‑ahead**: “if you had entered here and closed there, you would have made
     this much.”
   * **📷 Screenshot TA** — upload any chart image (live or historical) and get a
     full, clearly *image‑estimated* technical read (§7d).
   * **📡 Telegram** — the **Telegram Signal Center**: connect a bot and receive
     each confirmed BUY / SELL set‑up in your chat in real time (see the
     *Telegram Signal Center* section).
   * **🗂️ Data** — the parsed OHLC table.
   * **📝 Explanation** — the scientific reasoning, plus Excel / text / CSV
     download buttons.
   * **📐 Science** — the formula and the 15 coefficients.

---

## 6. CSV format

Provide a header row and at least the four OHLC columns. A `time` and a
`volume` column are recommended but optional.

```csv
time,open,high,low,close,volume
2025-09-01,2350.00,2358.40,2345.10,2356.20,18342
2025-09-02,2356.20,2369.90,2353.70,2367.10,20551
2025-09-03,2367.10,2372.30,2358.00,2360.40,17760
```

**Header auto‑detection.** Many conventions are accepted automatically
(TradingView, MT5, Binance, Yahoo). Recognised aliases include:

| Canonical | Accepted headers |
|-----------|------------------|
| `time`   | time, date, datetime, timestamp, date/time, `<DATE>`, `<TIME>` |
| `open`   | open, o, `<OPEN>`, open price |
| `high`   | high, h, `<HIGH>`, high price, max |
| `low`    | low, l, `<LOW>`, low price, min |
| `close`  | close, c, `<CLOSE>`, close price, price, adj close |
| `volume` | volume, vol, v, `<VOL>`, `<TICKVOL>`, tickvol |

Separate `Date` and `Time` columns are merged automatically; numbers with
thousands‑separators (`92,000.50`) are parsed correctly.

---

## 7. Screenshot / photo ingest (OCR)

Select **Image OCR**, upload a picture of an OHLC table (e.g. a TradingView or
MT5 panel), and FUTAS will read the numbers with Tesseract and rebuild a clean
OHLC table (enforcing `high = max`, `low = min` per row). Verify the parsed
table in the **🗂️ Data** tab before relying on it — OCR quality depends on the
image. If a column order is ambiguous you can hint it; if Tesseract is not
installed the app says so and the other input modes remain available.

> **OCR reads numeric *tables*, not charts.** To read a picture of a
> candlestick *chart*, use the digitizer described next.

---

## 7b. Chart‑image digitizer (`chart_ingest.py`)

Select **Chart image (digitizer)** to obtain an *approximate* OHLC table from a
picture of a candlestick **chart** (no Tesseract needed — pure Pillow + numpy).
The workflow is deliberately review‑driven:

1. **Upload** the chart screenshot.
2. **Pick the candle style** (dark‑on‑light, light‑on‑dark, or green‑red) and,
   if needed, **crop** the plot area to drop the toolbar, price axis and tabs.
3. **Detect candles** — an overlay shows exactly what was found (cyan wick,
   coloured body box) so you can re‑crop / restyle until it tracks the chart.
4. **Calibrate** by reading **two prices off the axis** — the price at the top
   of the highest wick and at the bottom of the lowest wick. A single linear map
   `price(y) = High + (y − y_top)·(Low − High)/(y_bot − y_top)` converts every
   pixel row to a price.
5. **Review & correct** the draft table in the editable grid, then
   **Use digitized table** to feed it into the normal analysis.

**Scientific honesty.** Digitizing a rendered chart is an *approximation*, not a
measurement: pixels quantise price, dense candles merge, and the bull/bear guess
is unreliable at low resolution. The **robust** outputs are exactly the three
the FUTAS level grid depends on — range **High**, range **Low**, and the **last
price** — so the levels, the BUY/SELL decision and TP1–TP3 are well‑grounded
even when individual mid‑range bars need a manual fix. The draft is always shown
for correction before it is analysed.

---

## 7c. Live data fetch (`live_data.py`)

Select **Live data fetch** to pull candles programmatically — no file, no
screenshot. Two public, key‑less sources are used (only the Python standard
library `urllib`, so **no extra dependency**):

| Market | Source | Symbols (examples) |
|--------|--------|--------------------|
| **Crypto** | Binance public *klines* REST | `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, … |
| **Gold / FX / stocks** | Yahoo Finance *chart* endpoint | `GC=F` (gold), `SI=F` (silver), `EURUSD=X`, `BTC-USD`, `^GSPC`, … |

Pick a **market**, choose a preset symbol or type your own, set the **interval**
(and `limit` for Binance / `range` for Yahoo), then **Fetch** — the candles flow
straight into the normal pipeline (`normalize_ohlc` → `analyze`).

> **Why not TradingView directly?** TradingView does not publish an official
> public market‑data API, so FUTAS uses the equivalent, programmatically‑allowed
> sources above. CSV upload, the digitizer and image OCR all remain available.

> ⚠️ Live data is provided for scientific back‑testing and analysis only.
> **FUTAS does not give financial advice and does not place orders.**

---

## 7d. Screenshot Technical Analysis (`screenshot_ta.py`)

The **📷 Screenshot TA** tab turns a *picture of a chart* — live or historical —
into a full FUTAS read: market direction, BUY/SELL scenario, entry zone,
Stop‑Loss, TP1–TP3, Risk/Reward, support/resistance, trend, the Fibonacci Urvin
interpretation, market structure, an invalidation condition and a final
conclusion. It digitises the candles (`chart_ingest`), optionally reads the
asset/timeframe/axis numbers (`ocr_ingest`), then runs `futas_engine.analyze()`.

> **Scientific honesty.** Everything from a screenshot is **ESTIMATED FROM THE
> IMAGE**, never presented as a raw‑data calculation. Direction, trend, structure,
> R/R and the Fibonacci Urvin *percentages* are scale‑invariant and robust;
> absolute Entry/SL/TP need the chart's price axis, so you enter its **top and
> bottom prices** for exact levels (otherwise levels are shown on a relative
> scale). RSI/MACD/volume derived from digitised candles are labelled as
> estimates. One click can load the reconstructed series into the main analysis.

---

## 8. Using the engine without the UI (Python API)

```python
import pandas as pd
import futas_engine as fe

df  = pd.read_csv("sample_data/XAUUSD_daily.csv")
res = fe.analyze(df, asset="XAUUSD")          # full pipeline → FUTASResult

print(res.trend, res.phase, res.signal.action)
print("Entry :", res.signal.entry)
print("Stop  :", res.signal.stop_loss)
print("TPs   :", res.signal.take_profits, "RR:", res.signal.rr)

res.levels_table()       # the 15 FU levels as a DataFrame (incl. structural_role)
res.signal_table()       # the signal as a DataFrame
res.to_dict()            # everything as a plain dict (JSON‑friendly)

# dissertation methodology on the same result
print(res.market_phase, "→", res.market_phase_next)   # seven‑phase model
print(res.momentum)       # RSI / MACD confirmation read‑out (never gates)
print(res.struct_conf)    # {'bull': bool, 'bear': bool} structural‑confirmation gate

bt = fe.backtest(df, asset="XAUUSD")          # walk‑forward test
print(bt["stats"])
print(bt["sfvt"])         # CSR / FSF / SPR / Δ vs RSI‑MA baseline

# reconstruct a real historical trade with NO look‑ahead
wt = fe.worked_example(df, asset="XAUUSD")
if wt.found:
    print(wt.narrative)   # "if you had entered here and closed there …"
```

Optional live fetch (no file needed, no extra dependency):

```python
import live_data as ld
df = ld.fetch_live("Crypto (Binance)", "BTCUSDT", "1h", limit=300)   # crypto
df = ld.fetch_live("Gold / FX / stocks (Yahoo)", "GC=F", "1d", range_="1y")  # gold
res = fe.analyze(df, asset="BTCUSDT")
```

Key functions: `normalize_ohlc`, `detect_range`, `fu_levels`, `detect_swings`,
`detect_trend`, `market_structure`, `detect_phase`, `generate_signal`,
`scientific_explanation`, `analyze`, `backtest`. Dissertation‑methodology
additions: `momentum_state`, `structure_confirmed`, `market_phase`,
`sfvt_metrics`, `worked_example` (and `live_data.fetch_live` for live OHLC).
Multi‑timeframe: `resample_ohlc`, `native_timeframe`, `available_timeframes`,
`htf_bias` (and `analyze(..., with_htf=True)` carries the higher‑timeframe read
in `res.htf`). Statistical validation: `backtest(..., max_hold=, cost_bps=)`,
`monte_carlo_significance`, `benchmark_compare` (FUTAS vs classical Fibonacci vs
buy‑and‑hold; `fu_levels(..., coeffs=)` supplies the baseline coefficient set —
the default is always the frozen 15), `bootstrap_metrics`,
`parameter_sensitivity`, `in_out_of_sample`. Tier‑2 methodology:
`volume_confirmation`, `signal_narrative`, and `backtest(..., tp_management=,
tp_weights=, breakeven=, trailing=, spread_bps=, commission_bps=, slippage_bps=)`.

---

## 9. The Excel template

`FUTAS_Excel_Template.xlsx` is a spreadsheet calculator: type **High, Low,
Current Price, Direction** and pure Excel formulas reproduce the 15 levels, the
Stop‑Loss, TP1‑3, Risk/Reward and the validity‑gated signal — letting a
reviewer audit the risk arithmetic by hand. Regenerate it with
`python make_excel_template.py`. Every formula is documented in
[`EXCEL_FORMULAS.md`](EXCEL_FORMULAS.md). (`MAXIFS` / `MINIFS` need Excel 2019,
Microsoft 365, or LibreOffice Calc.)

---

## 10. Sample data

`sample_data/` ships two deterministic, synthetic series shaped to demonstrate
the full pipeline:

* **XAUUSD_daily.csv** — an uptrend with a corrective pull‑back → a clean **BUY**.
* **BTCUSD_daily.csv** — a downtrend with a corrective bounce → a clean **SELL**.

They are illustrative scientific test data, **not** real market quotes.
Rebuild them with `python sample_data/generate_samples.py`.

---

## 11. Using FUTAS in the dissertation

* **Methodology.** Cite the formula `P = Low + (High − Low) × K` and the 15
  fixed coefficients as the system’s scientific innovation. The
  [`DISSERTATION_FUTAS.md`](DISSERTATION_FUTAS.md) file provides a ready 2–3 page
  description in OAK style; [`ALGORITHM.md`](ALGORITHM.md) provides the full
  algorithm flow (START → Data Input → … → Report Export → END).
* **Reproducibility.** All results are deterministic. The coefficient signature
  is frozen in the engine (`FU_COEFFICIENTS_FROZEN`) so a published build can be
  proven to use the unmodified research coefficients.
* **Figures.** Export the candlestick‑with‑levels chart and the backtest equity
  curve directly from the app for inclusion as figures.
* **Tables.** Export the 15‑level table, the signal table and the backtest
  statistics to Excel for inclusion as tables.
* **Auditability.** The Excel template lets an examiner verify, by hand, that
  every Stop‑Loss and Take‑Profit is a member of the 15 FU levels.

---

## 12b. Live MT5 Center (`live_data.py` + `mt5_feed.py`)

The **🛰️ Live Center** tab is a dedicated live‑market dashboard, separate from the
analysis modules. It opens with **live world trading clocks** (Tashkent, New York,
London, Tokyo, Hong Kong, Singapore, Dubai, Frankfurt, Sydney, UTC — ticking every
second with Open / Pre‑market / Closed / High‑volatility status) and a
**trading‑session analysis** (active session, volatility expectation, per‑asset
read for XAUUSD/BTC/ETH/FX, and whether trading is recommended now). Below that it
shows **Bid / Ask / Spread / Last / Day‑Change% / Day‑High / Day‑Low /
Market‑Status / Source / Last‑update** for a watchlist of **XAUUSD, BTCUSD, ETHUSD,
EURUSD, GBPUSD, USDJPY** (and more / custom), and can load any asset's history
straight into the analysis (1H/4H/1D, up to 5 years). The session context (active
session + Tashkent/London/New‑York times + market condition) is also embedded in
every **Telegram alert**.

* **Primary, cloud‑compatible source:** Binance (true crypto bid/ask) + Yahoo
  (gold/FX/indices last/high/low/change) via `live_data.fetch_quote()`.
* **Optional local MT5:** if you run FUTAS on **Windows with MetaTrader 5** and
  `pip install MetaTrader5`, the Live Center can connect to your terminal through
  a **secure credential form** and use real MT5 ticks; it **auto‑falls‑back** to
  the cloud feed when MT5 is unavailable (e.g. on Streamlit Cloud), so the
  published app always works.
* **Security:** MT5 login/password/server are taken only through the form, kept in
  session memory, never hard‑coded, logged, or shown. `MetaTrader5` is **not** in
  `requirements.txt` (it is Windows‑only and would break the Linux cloud build);
  the optional import degrades gracefully.

> ⚠️ Live market data only — FUTAS does not place orders or move money.

---

## 📡 Telegram Signal Center (`telegram_signals.py`)

Open the **📡 Telegram** tab to push every confirmed FUTAS **BUY / SELL** set‑up
to your Telegram chat in real time. It uses the official Telegram **Bot API**
through the Python standard library only (`urllib`) — **no extra dependency**.

> **Alerts only.** This feature delivers *notifications*. It never places an
> order, executes a trade or moves money, and every message carries the standing
> FUTAS notice that the system does **not** provide financial advice.

**Setup wizard (in‑app):**

1. Open **Telegram**, search **@BotFather**.
2. **/newbot** → choose a name → copy the **Bot Token** (`123456789:AAE…`).
3. Open **your new bot** and press **/start** (required before it can message you).
4. Find your numeric **Chat ID** — the in‑app **🔎 Find my Chat ID** button reads
   the bot’s recent messages, or message **@userinfobot**.
5–8. Paste the **Bot Token** + **Chat ID** into FUTAS and click **Connect**.
9. Press **Send Test Signal** to verify, then leave **Auto‑send** on.

**What an alert contains** (the *FUTAS TRADING ALERT* — built by `format_signal()`
from the live `FUTASResult`): asset, timeframe, BUY/SELL, entry, stop‑loss and
TP1–TP3 (each annotated with its Fibonacci Urvin level), **Risk/Reward**, RSI,
**volume status**, **market‑structure confirmation**, the **Fibonacci Urvin level**
in play, **higher‑timeframe confirmation**, the confidence score, the signal time
and **validity window**, and a plain‑language **Scenario / Reason for Entry /
Invalidation Condition** (`signal_narrative()`), closing with the no‑advice notice.

**Filters:** direction (BUY only / SELL only / Both), confidence band (all
confirmed / medium+high / high‑only), **minimum R/R**, **minimum confidence %**,
and optional **require‑HTF‑alignment** / **require‑volume** gates. Auto‑send fires
once per confirmed set‑up (deduplicated by an asset/timeframe/action/entry/SL/TP/
phase signature) at the **selected timeframe** (`1M…1W`) for Gold, BTC, ETH, FX or
any custom symbol.

**Stability + trade lifecycle.** The connection is **health‑checked** (re‑validated
at most every 2 minutes) with an **auto‑reconnect** attempt and four status states
— **Connected / Reconnecting / Disconnected / Error**. After a signal is sent the
trade is **monitored**: as new bars arrive, FUTAS pushes **✅ TP1 Reached**,
**✅ TP2 Reached**, **✅ Trade Completed Successfully** (TP3), or **❌ Stop Loss
Triggered**, and shows the open trades in a monitored‑trades table. (Continuous
monitoring advances as fresh data arrives — refresh live data or keep the tab
open; Streamlit has no always‑on per‑session daemon.)

**Security:** the Bot Token is kept **only in the session’s memory** (never
written to disk or logs), shown **masked** after connecting, and can be
**replaced** or **disconnected** at any time. The Chat ID is validated and all
Telegram API errors are reported cleanly (e.g. “press /start first”).

> The token lives in `st.session_state`, so it is cleared when the app restarts —
> each user connects their own bot. Do **not** hard‑code a token in the repo.

---

## 12. Deployment / publishing

FUTAS is built as a web application and is ready to publish on
**Streamlit Community Cloud**:

1. Push this folder to a public GitHub repository.
2. On <https://share.streamlit.io>, create an app pointing at
   `app_streamlit.py` on your branch.
3. `requirements.txt` (Python deps) and `packages.txt` (the `tesseract-ocr`
   system package) are detected automatically; `.streamlit/config.toml`
   supplies the theme and server settings.
4. Deploy — the public URL can then be cited in the dissertation.

The same app also runs on any host that can run Streamlit (a VM, an internal
server, Hugging Face Spaces, etc.).

---

## 13. Scientific integrity & limitations

* The signal is a deterministic function of the data, the 15 coefficients and
  the documented rules — there is no hidden tuning or curve‑fitting.
* On unstructured (random) data the backtest honestly reports weak results;
  the method’s edge comes from genuine market structure, not from the tool.
* Past performance does not guarantee future results.

**FUTAS does not provide financial advice.** It is a scientific‑research and
algorithm‑testing instrument created for the dissertation named above.
