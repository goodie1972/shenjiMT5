# m15/m30_followave v1.0 (MT5 edition) — Strategy Notes (English)

- Ported: 2026-10-02 ｜ Lineage: legacy `20260927_m{15,30}_followave_v2.py` **v1.6** (line-level port, logic & params unchanged)
- Shared core: `strategies/followave_core.py` (6 interface adaptations in header); shells differ only in `TRAIL_ATR` (M30=3.0 / M15=4.0) and magic (661402 / 661401)

## Entry (all on closed bar1)

| Condition | Long | Short |
|-----------|------|-------|
| ±DI gate | \|+DI − −DI\| > 2 | same |
| Direction | +DI > −DI | −DI > +DI |
| Position | close > BBI | close < BBI |
| Stoch(5,3,3) | golden cross (K>D & K_prev≤D_prev) | death cross (K<D & K_prev≥D_prev) |
| Extreme filter | K < 80 | K > 20 |
| Mid band | close ≥ BB mid | close ≤ BB mid |

Tick-time re-verification (G15): price must be on the right side of BBI/mid; forming-bar body must not oppose direction.

## Exits (priority order, all on closed bars)

1. **Partial TP** (engine hook): bar1 close reaches entry ± 3.0×ATR (**frozen at entry**) → close 50%, once per trade
2. **Stoch cross TP**: touched BB upper (3-pt tolerance) + K>80 death cross (short: K<20 golden cross off lower)
3. **Trend reversal**: close beyond BBI with bb_mid_direction (SMA20 slope ±0.02%) aligned, **3 consecutive bars**
4. **BB hard stop**: close beyond opposite band
5. **Trailing stop**: TRAIL_ATR × ATR from closed-bar extreme

SL fallback: max(3×ATR, 30), no TP (exits fully managed). Exit attribution recorded in `_last_exit_detail`.

## Parameters & rationale (inherited from legacy changelog — do not touch)

80/20 (v1.3 reverted 70/30), bb_mid_direction over real BBI direction (v1.3 A/B: M15 +462.8 delta),
DI_GATE=2 (v1.4), partial 3.0×ATR@50% (v1.5), TRAIL 3.0/4.0 (v1.2). See legacy file header and
`followave_improvement_analysis.md`. **Any change must happen on the MT4 side first, then rebase.**

## MT5 validation record

- 21 port unit tests (`tests/test_followave.py`): entry/verify/exit priorities/partial/state freeze/SL
- Four-gate backtest on MT5 data: M30 full +2025 / M30 180d +346 / M15 full +2189 / M15 180d +524 — **PASS**
- Indicator parity vs legacy EA snapshots: bias ≈ 0 (feed-aggregation noise scale)
- Signal reconciliation: limited by legacy signals retention (7 days) — M15 window 10/15 (66.7%, ±2bar); M30 has no ground truth. Full acceptance deferred to **M3 forward shadow-run** (demo alongside MT4 live).
