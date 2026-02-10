"""Swing trade scanner: Find bottomed reversals with strength."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from apredator.logging_conf import setup_logging
from apredator.adapters.yahoo import fetch_prices
from apredator.features.technical import compute_all_technical
from apredator.features.explosive import compute_all_explosive
from apredator.scoring.combo_matcher import match_combos
from apredator.scoring.tier_system import classify_tier
from apredator.scoring.position_sizer import kelly_position_size

# Broad universe: high-beta stocks most likely to show explosive reversals
UNIVERSE = [
    # Biotech
    "SAVA", "SRNE", "OCGN", "VXRT", "IBRX", "APLS", "CRSP", "BEAM", "NTLA",
    "EDIT", "FATE", "CDNA", "EXAS", "RXRX", "DNA",
    # EV / Clean energy
    "GOEV", "WKHS", "LCID", "RIVN", "NKLA", "QS", "CHPT", "BLNK", "PLUG",
    "FCEL", "BE", "ENPH", "SEDG", "RUN", "NOVA",
    # Crypto-adjacent
    "RIOT", "MARA", "COIN", "BITF", "HUT", "CIFR", "MSTR", "CLSK",
    # Cannabis
    "TLRY", "SNDL", "ACB", "CGC",
    # Chinese ADR
    "BABA", "JD", "PDD", "NIO", "XPEV", "LI", "BIDU", "FUTU", "TAL",
    # Meme / High-beta
    "AMC", "GME", "BBBY", "SOFI", "HOOD", "AFRM", "UPST", "DKNG", "PLTR",
    "CLOV", "WISH", "SKLZ", "OPEN", "RBLX", "U", "SNOW", "CRWD", "NET",
    "DDOG", "ZS", "MDB", "CFLT",
    # Tech growth / Semis
    "NVDA", "AMD", "TSLA", "SQ", "SHOP", "ROKU", "TTD", "PINS", "SNAP",
    "LYFT", "UBER", "ABNB", "DASH", "SE", "GRAB", "CPNG",
    # Misc high-beta
    "SMCI", "IONQ", "RGTI", "QBTS", "QUBT", "ARQQ", "LUNR", "RKLB",
    "ASTS", "ACHR", "JOBY", "LILM", "OKLO", "SMR", "NNE", "VST", "CEG",
    "CVNA", "HIMS", "DJT", "RDDT", "ARM", "CELH", "MNDY",
]


def compute_reversal_strength(tech, explosive, df):
    """Score how strongly a stock is bottoming and reversing."""
    score = 0
    reasons = []

    rsi = tech.get("rsi_14", 50)
    bb_pos = tech.get("bb_position", 0.5)
    ma_spread = tech.get("ma_spread_pct", 0)
    vol_ratio = tech.get("volume_ratio_20d", 1.0)
    momentum = explosive.get("momentum_10d", 0)
    drawdown = explosive.get("drawdown_60d", 0)
    vol_zscore = explosive.get("vol_zscore", 0)
    selling_pressure = explosive.get("selling_pressure", 0)
    rejection_wick = explosive.get("rejection_wick", 0)
    low_in_range = explosive.get("low_in_range", 0)

    close = df["close"].iloc[-1]
    close_5d = df["close"].iloc[-6] if len(df) > 5 else close
    close_20d = df["close"].iloc[-21] if len(df) > 20 else close
    ret_5d = (close - close_5d) / close_5d * 100
    ret_20d = (close - close_20d) / close_20d * 100

    # 1. Drawdown from highs (bottomed = significant prior drawdown)
    if drawdown >= 40:
        score += 25
        reasons.append(f"Deep drawdown {drawdown:.0f}%")
    elif drawdown >= 25:
        score += 18
        reasons.append(f"Drawdown {drawdown:.0f}%")
    elif drawdown >= 15:
        score += 10
        reasons.append(f"Pullback {drawdown:.0f}%")

    # 2. RSI recovering from oversold
    if 30 <= rsi <= 50:
        score += 15
        reasons.append(f"RSI setup {rsi:.0f}")
    elif rsi < 30:
        score += 10
        reasons.append(f"RSI oversold {rsi:.0f}")

    # 3. Short-term bounce (5d positive after being beaten down)
    if ret_5d > 3 and ret_20d < 0:
        score += 20
        reasons.append(f"Bounce +{ret_5d:.1f}% off -20d")
    elif ret_5d > 1 and ret_20d < -5:
        score += 15
        reasons.append(f"Early reversal +{ret_5d:.1f}%")

    # 4. Volume confirmation
    if vol_ratio >= 2.0:
        score += 15
        reasons.append(f"Vol surge {vol_ratio:.1f}x")
    elif vol_ratio >= 1.3:
        score += 8
        reasons.append(f"Vol rising {vol_ratio:.1f}x")

    # 5. Volume z-score (explosive vol)
    if vol_zscore >= 0.15:
        score += 10
        reasons.append(f"Vol z={vol_zscore:.2f}")

    # 6. Rejection wicks (buying at lows)
    if rejection_wick >= 1.0:
        score += 8
        reasons.append("Rejection wicks")

    # 7. Low in range (near bottom of range)
    if low_in_range:
        score += 5
        reasons.append("Low in range")

    # 8. BB squeeze (volatility compression before expansion)
    bb_width = tech.get("bb_width_pct", 10)
    if bb_width < 5:
        score += 8
        reasons.append(f"BB squeeze {bb_width:.1f}%")

    return score, reasons, {
        "ret_5d": ret_5d, "ret_20d": ret_20d, "rsi": rsi,
        "drawdown": drawdown, "vol_ratio": vol_ratio, "vol_zscore": vol_zscore,
    }


def main():
    setup_logging(log_level="WARNING", name="apredator")

    print("=" * 90)
    print("ALPHA PREDATOR — Swing Trade Reversal Scanner")
    print("Scanning for bottomed stocks reversing with strength...")
    print("=" * 90)

    # Fetch all prices in one batch
    print(f"\nFetching 1-year price data for {len(UNIVERSE)} symbols...")
    df_all = fetch_prices(UNIVERSE, period="1y")
    if df_all.empty:
        print("Failed to fetch prices.")
        return

    symbols_fetched = df_all["symbol"].nunique()
    print(f"Got data for {symbols_fetched} symbols ({len(df_all)} rows)")

    results = []
    for symbol in UNIVERSE:
        sym_df = df_all[df_all["symbol"] == symbol].sort_values("date").reset_index(drop=True)
        if len(sym_df) < 60:
            continue

        try:
            tech = compute_all_technical(sym_df)
            explosive = compute_all_explosive(sym_df)
            combos = match_combos(explosive)

            reversal_score, reasons, metrics = compute_reversal_strength(tech, explosive, sym_df)

            # Only interested in stocks with some reversal signal
            if reversal_score < 20:
                continue

            best_combo = max(combos, key=lambda c: c["hit_rate"]) if combos else None

            # Kelly sizing
            if best_combo:
                kelly = kelly_position_size(best_combo["hit_rate"]) * 100
            else:
                kelly = 0.0

            # Tier classification
            feat_dict = {**tech, **explosive, "close": sym_df["close"].iloc[-1]}
            tier_result = classify_tier(feat_dict)
            tier = tier_result.get("tier")

            results.append({
                "symbol": symbol,
                "price": sym_df["close"].iloc[-1],
                "reversal_score": reversal_score,
                "reasons": reasons,
                "combo": best_combo["name"] if best_combo else None,
                "combo_hit": best_combo["hit_rate"] if best_combo else 0,
                "n_combos": len(combos),
                "tier": tier,
                "kelly": kelly,
                **metrics,
            })
        except Exception as e:
            pass  # Skip errors silently

    # Sort by reversal score
    results.sort(key=lambda r: (r["n_combos"], r["reversal_score"]), reverse=True)

    # Display top results
    print(f"\n{'='*90}")
    print(f"TOP BOTTOMED REVERSALS ({len(results)} candidates found)")
    print(f"{'='*90}\n")

    for i, r in enumerate(results[:25], 1):
        combo_str = r["combo"] or "—"
        tier_str = f"T{r['tier']}" if r['tier'] else "—"
        kelly_str = f"{r['kelly']:.1f}%" if r['kelly'] > 0 else "—"

        print(f"#{i:2d}  {r['symbol']:6s}  ${r['price']:>8.2f}  "
              f"Rev={r['reversal_score']:3d}  RSI={r['rsi']:4.1f}  "
              f"DD={r['drawdown']:4.0f}%  5d={r['ret_5d']:+5.1f}%  20d={r['ret_20d']:+6.1f}%  "
              f"VolR={r['vol_ratio']:4.1f}x")
        if r["n_combos"] > 0:
            print(f"     COMBO: {combo_str} ({r['combo_hit']*100:.1f}% hit)  "
                  f"Combos={r['n_combos']}  {tier_str}  Kelly={kelly_str}")
        print(f"     Signals: {', '.join(r['reasons'])}")
        print()

    # Summary stats
    with_combos = [r for r in results if r["n_combos"] > 0]
    print(f"{'='*90}")
    print(f"SUMMARY: {len(results)} reversal candidates, "
          f"{len(with_combos)} with combo confirmation")
    if with_combos:
        print(f"\nCOMBO-CONFIRMED TRADES (highest conviction):")
        for r in with_combos[:10]:
            print(f"  {r['symbol']:6s} — {r['combo']} ({r['combo_hit']*100:.1f}% hit rate) "
                  f"| Kelly {r['kelly']:.1f}% | Rev score {r['reversal_score']}")


if __name__ == "__main__":
    main()
