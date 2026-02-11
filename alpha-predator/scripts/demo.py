"""Demo: Run Alpha Predator on a small universe to show the system working."""
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from apredator.db import init_db
from apredator.logging_conf import setup_logging
from apredator.adapters.yahoo import fetch_prices, fetch_and_upsert
from apredator.features.technical import compute_all_technical
from apredator.features.explosive import compute_all_explosive
from apredator.scoring.combo_matcher import match_combos
from apredator.scoring.tier_system import compute_setup_score
from apredator.scoring.position_sizer import kelly_position_size

DEMO_SYMBOLS = ["AMC", "GME", "SOFI", "RIOT", "HOOD"]


def main():
    setup_logging(log_level="INFO", name="apredator")
    print("=" * 60)
    print("ALPHA PREDATOR — Demo Scan")
    print("=" * 60)

    # Initialize DB
    init_db()

    # Fetch prices
    print(f"\nFetching prices for {DEMO_SYMBOLS}...")
    df = fetch_prices(DEMO_SYMBOLS, period="6mo")
    if df.empty:
        print("Failed to fetch prices. Check network connection.")
        return
    print(f"Got {len(df)} price rows")

    # Analyze each symbol
    results = []
    for symbol in DEMO_SYMBOLS:
        sym_df = df[df["symbol"] == symbol].sort_values("date")
        if len(sym_df) < 30:
            print(f"  {symbol}: insufficient data")
            continue

        # Compute features
        tech = compute_all_technical(sym_df)
        explosive = compute_all_explosive(sym_df)
        combos = match_combos(explosive)

        best_combo = max(combos, key=lambda c: c["hit_rate"]) if combos else None

        result = {
            "symbol": symbol,
            "price": sym_df["close"].iloc[-1],
            "rsi": tech.get("rsi_14", 0),
            "vol_zscore": explosive.get("vol_zscore", 0),
            "range_20d": explosive.get("range_20d", 0),
            "combo": best_combo["name"] if best_combo else "None",
            "hit_rate": best_combo["hit_rate"] if best_combo else 0,
        }
        results.append(result)

        # Kelly sizing if combo matched
        if best_combo:
            kelly = kelly_position_size(best_combo["hit_rate"])
            result["kelly_pct"] = kelly * 100
        else:
            result["kelly_pct"] = 0

    # Display results
    print(
        f"\n{'Symbol':8s} {'Price':>8s} {'RSI':>6s} {'VolZ':>6s} {'Range':>6s} "
        f"{'Combo':>25s} {'Hit%':>6s} {'Kelly':>6s}"
    )
    print("-" * 80)
    for r in sorted(results, key=lambda x: x["hit_rate"], reverse=True):
        print(
            f"{r['symbol']:8s} ${r['price']:7.2f} {r['rsi']:5.1f} "
            f"{r['vol_zscore']:5.2f} {r['range_20d']:5.1f}% "
            f"{r['combo']:>25s} {r['hit_rate']*100:5.1f}% {r['kelly_pct']:5.1f}%"
        )

    print("\nDemo complete.")


if __name__ == "__main__":
    main()
