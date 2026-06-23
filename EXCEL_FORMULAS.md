# FUTAS — Excel Formulas (Deliverable #5)

This document lists every spreadsheet formula used in **`FUTAS_Excel_Template.xlsx`**.
The workbook is the spreadsheet companion to `futas_engine.py`: you supply four
inputs (High, Low, Current Price, Direction) and pure Excel formulas reproduce —
cell for cell — what the Python function `generate_signal()` does, so a reviewer
can audit the risk arithmetic by hand with no code.

> **Scientific guarantee.** No Entry, Stop‑Loss or Take‑Profit number is ever
> typed in or copied from an old analysis. **Entry** is the live price; the
> **Stop‑Loss** and every **Take‑Profit** are *selected only* from the 15
> calculated Fibonacci Urvin levels, through the single formula
> **`P = Low + (High − Low) × K`**.
>
> This is a scientific research / algorithm‑testing instrument. It does **not**
> provide financial advice.

Generate or regenerate the file with:

```bash
python make_excel_template.py
```

Requirements: `MAXIFS` / `MINIFS` need **Excel 2019, Microsoft 365, or
LibreOffice Calc 5.2+**. `openpyxl` writes the formulas but does not pre‑compute
them — open the file once so the workbook recalculates.

---

## 1. Sheet map

| Sheet | Purpose |
|-------|---------|
| **Calculator** | Live formulas — type 4 inputs, read SL / TP / RR / Signal |
| **Coefficients** | The 15 fixed Fibonacci Urvin coefficients (the scientific constant) |
| **Worked_Example** | Static reference computed by `futas_engine.analyze()` on the XAUUSD sample — the Calculator must reproduce these numbers |
| **How_to_use** | Step‑by‑step instructions and scope |

---

## 2. Inputs (Calculator sheet)

| Cell | Meaning | Example | Notes |
|------|---------|---------|-------|
| `B5` | **High** of the analysed range | `2549.97` | The FUTAS app detects it automatically |
| `B6` | **Low** of the analysed range | `2341.74` | |
| `B7` | **Current Price** = Entry | `2496.63` | The live price |
| `B8` | **Range** | `=B5-B6` | High − Low |
| `B9` | **Direction** | `BUY` | `BUY` / `SELL` / `WAIT`, from the app verdict (drop‑down) |
| `B10` | **Minimum Risk/Reward** | `1.00` | TP1 gate — below this the signal downgrades to WAIT |
| `B11` | Tolerance % of range | `0.060` | Informational only (used by the engine for confidence) |

Only `B5`, `B6`, `B7`, `B9` are typed. Everything below is computed.

---

## 3. The 15 Fibonacci Urvin levels  (`P = Low + (High − Low) × K`)

The coefficients live in `B14:B28`; the level prices are built in `C14:C28`.

**Price of each level — the core scientific formula** (row 14 shown; fill down to row 28):

```excel
C14 = $B$6 + ($B$5 - $B$6) * B14
```

* `$B$6` = Low, `$B$5` = High, `B14` = the coefficient *K*.
* This is exactly `P = Low + (High − Low) × K`.

Supporting columns:

```excel
D14 = B14 * 100                                              ' % of range (K × 100)
E14 = IF(B14>1,"extension_up",IF(B14<0,"extension_down","inside"))   ' zone
F14 = IF(ABS(C14-$B$7)<0.000001,"at-price",
         IF(C14<$B$7,"support","resistance"))                ' role vs current price
```

The 15 coefficients (fixed research result, order preserved):

```
1.0, 0.0, 0.5, 0.5993, -0.6993, 1.5993, -0.5993, 1.1987,
1.6987, 1.7973, -0.1987, -0.0987, -0.7973, 0.3973, 1.0993
```

`K = 0` → the level equals **Low**; `K = 1` → equals **High**; `K = 0.5` → the
mid‑point; `K > 1` are upward extensions; `K < 0` are downward extensions.

The named range used by every signal formula below is the level column:

```
levels  =  $C$14:$C$28
```

---

## 4. Signal & Risk Management (Calculator sheet)

All of these are pure formulas — they **select** values from `levels`, never
invent them. Cell addresses assume the layout written by
`make_excel_template.py` (Entry on `B31`, Anchor `B32`, SL `B33`,
TP1‑3 `B34:B36`, Risk `B37`, RR1‑3 `B38:B40`, Final `B41`).

### 4.1 Entry

```excel
B31 = IF($B$9="WAIT", "—", $B$7)
```

Entry is simply the live **Current Price**.

### 4.2 Anchor — the FU level the price sits on

* **BUY** → the highest level **at or below** price (support).
* **SELL** → the lowest level **at or above** price (resistance).

```excel
B32 = IF($B$9="BUY",  MAXIFS(levels, levels, "<="&$B$7),
      IF($B$9="SELL", MINIFS(levels, levels, ">="&$B$7), "—"))
```

### 4.3 Stop‑Loss — the next FU level **beyond** the anchor

* **BUY** → the next level **below** the support anchor.
* **SELL** → the next level **above** the resistance anchor.
* `COUNTIFS` first checks such a level exists; otherwise `"n/a"` (→ WAIT).

```excel
B33 = IF($B$9="BUY",
        IF(COUNTIFS(levels,"<"&$B$32)>0, MAXIFS(levels,levels,"<"&$B$32), "n/a"),
      IF($B$9="SELL",
        IF(COUNTIFS(levels,">"&$B$32)>0, MINIFS(levels,levels,">"&$B$32), "n/a"), "—"))
```

### 4.4 Take‑Profit 1 / 2 / 3 — the next FU levels in the trade direction

* **BUY** → the next levels strictly **above** price (ascending).
* **SELL** → the next levels strictly **below** price (descending).
* TP2 steps off TP1, TP3 steps off TP2 — so they are always three *distinct*
  FU levels.

```excel
B34 = IF($B$9="BUY",
        IF(COUNTIFS(levels,">"&$B$7)>0, MINIFS(levels,levels,">"&$B$7), "n/a"),
      IF($B$9="SELL",
        IF(COUNTIFS(levels,"<"&$B$7)>0, MAXIFS(levels,levels,"<"&$B$7), "n/a"), "—"))

B35 = IF($B$9="BUY",
        IF(AND(ISNUMBER($B$34),COUNTIFS(levels,">"&$B$34)>0), MINIFS(levels,levels,">"&$B$34), "n/a"),
      IF($B$9="SELL",
        IF(AND(ISNUMBER($B$34),COUNTIFS(levels,"<"&$B$34)>0), MAXIFS(levels,levels,"<"&$B$34), "n/a"), "—"))

B36 = IF($B$9="BUY",
        IF(AND(ISNUMBER($B$35),COUNTIFS(levels,">"&$B$35)>0), MINIFS(levels,levels,">"&$B$35), "n/a"),
      IF($B$9="SELL",
        IF(AND(ISNUMBER($B$35),COUNTIFS(levels,"<"&$B$35)>0), MAXIFS(levels,levels,"<"&$B$35), "n/a"), "—"))
```

### 4.5 Risk and Risk/Reward

```excel
B37 = IF($B$9="BUY",  IF(ISNUMBER($B$33), $B$31-$B$33, "n/a"),
      IF($B$9="SELL", IF(ISNUMBER($B$33), $B$33-$B$31, "n/a"), "—"))        ' Risk = |Entry − SL|

B38 = IF(AND(ISNUMBER($B$34),ISNUMBER($B$37),$B$37>0),
         IF($B$9="BUY",($B$34-$B$31)/$B$37, IF($B$9="SELL",($B$31-$B$34)/$B$37,"—")), "n/a")   ' RR→TP1
B39 = … same with $B$35 …                                                  ' RR→TP2
B40 = … same with $B$36 …                                                  ' RR→TP3
```

`Risk/Reward = reward ÷ risk`, where reward is the distance from Entry to the
take‑profit and risk is the distance from Entry to the Stop‑Loss.

### 4.6 Final signal — the validity gate

Mirrors the engine's WAIT downgrade: if there is no Stop‑Loss, no TP1, or the
TP1 Risk/Reward is below the minimum (`B10`), the set‑up is **not** actionable.

```excel
B41 = IF($B$9="WAIT","WAIT",
        IF(OR(NOT(ISNUMBER($B$33)), NOT(ISNUMBER($B$34)),
              NOT(ISNUMBER($B$38)), $B$38<$B$10),
           "WAIT (downgraded)", $B$9))
```

A one‑line human reason is printed underneath (no SL, no TP, RR too low, or
“Valid set‑up: SL and TP1/2/3 are all members of the 15 FU levels.”).

---

## 5. Worked example (XAUUSD sample)

Computed by `futas_engine.analyze()` on `sample_data/XAUUSD_daily.csv`, and
reproduced exactly by the Calculator formulas when fed the same inputs:

| Field | Value |
|-------|-------|
| High | **2549.97** |
| Low | **2341.74** |
| Current Price (Entry) | **2496.63** |
| Direction | **BUY** |
| Anchor (support) | 2466.53 &nbsp;(FU level, K = 0.5993) |
| Stop‑Loss | **2445.85** &nbsp;(FU level, **K = 0.5** — the mid‑point) |
| Take‑Profit 1 | **2549.97** &nbsp;(FU level, **K = 1.0** — the High) &nbsp;RR ≈ **1.05** |
| Take‑Profit 2 | **2570.65** &nbsp;(FU level, K = 1.0993) &nbsp;RR ≈ **1.46** |
| Take‑Profit 3 | **2591.35** &nbsp;(FU level, K = 1.1987) &nbsp;RR ≈ **1.87** |
| Final signal | **BUY** |

Every SL/TP price is one of the 15 numbers on the **Coefficients** sheet
evaluated at this High/Low — the spreadsheet proof that Stop‑Loss and
Take‑Profit are selected only from the Fibonacci Urvin levels.

---

## 6. Formula summary table (for the dissertation)

| Quantity | Excel formula (essence) |
|----------|--------------------------|
| High | input |
| Low | input |
| Current Price | input |
| Range | `=High − Low` |
| K | the 15 fixed coefficients |
| **P (level price)** | `=Low + (High − Low) * K` |
| Anchor (BUY) | `=MAXIFS(levels, levels, "<="&Price)` |
| Anchor (SELL) | `=MINIFS(levels, levels, ">="&Price)` |
| **Stop‑Loss** (BUY) | `=MAXIFS(levels, levels, "<"&Anchor)` |
| **Stop‑Loss** (SELL) | `=MINIFS(levels, levels, ">"&Anchor)` |
| **TP1** (BUY) | `=MINIFS(levels, levels, ">"&Price)` |
| **TP1** (SELL) | `=MAXIFS(levels, levels, "<"&Price)` |
| TP2 / TP3 | same, stepping off the previous TP |
| **Risk** | `=ABS(Entry − StopLoss)` |
| **Risk/Reward** | `=ABS(TP − Entry) / Risk` |
| **Signal** | `=IF(no SL / no TP / RR<min, "WAIT", Direction)` |
