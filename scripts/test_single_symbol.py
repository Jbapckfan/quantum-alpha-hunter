"""
Quick test - run pipeline on single symbol to validate everything works
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from qaht.db import init_db
from qaht.equities_options.adapters.prices_yahoo import fetch_and_upsert
from qaht.equities_options.features.tech import upsert_factors_for_symbol
from qaht.backtest.labeler import label_explosions
from qaht.logging_conf import setup_logging

logger = setup_logging()

def main():
    print("🧪 Testing pipeline with single symbol...")

    # Initialize database
    init_db()
    print("✅ Database initialized")

    # Test symbol
    symbol = "AAPL"

    # Step 1: Fetch price data
    print(f"\n1️⃣ Fetching price data for {symbol}...")
    try:
        rows = fetch_and_upsert([symbol], period="1y")
        print(f"   ✅ Fetched {rows} rows")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return 1

    # Step 2: Compute technical features
    print(f"\n2️⃣ Computing technical features...")
    try:
        upsert_factors_for_symbol(symbol)
        print(f"   ✅ Features computed")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # Step 3: Label explosions
    print(f"\n3️⃣ Labeling explosive moves...")
    try:
        label_explosions(symbol, horizon=10)
        print(f"   ✅ Labels created")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # Step 4: Check database
    print(f"\n4️⃣ Verifying database...")
    from qaht.db import session_scope
    from qaht.schemas import PriceOHLC, Factors, Labels
    from sqlalchemy import select

    with session_scope() as session:
        price_count = session.execute(
            select(PriceOHLC).where(PriceOHLC.symbol == symbol)
        ).all()

        factor_count = session.execute(
            select(Factors).where(Factors.symbol == symbol)
        ).all()

        label_count = session.execute(
            select(Labels).where(Labels.symbol == symbol)
        ).all()

        print(f"   Prices: {len(price_count)} rows")
        print(f"   Factors: {len(factor_count)} rows")
        print(f"   Labels: {len(label_count)} rows")

        if label_count:
            # Show some labels
            labels = [l[0] for l in label_count[:5]]
            print(f"\n   Sample labels:")
            for label in labels:
                print(f"     {label.date}: fwd_ret={label.fwd_ret_10d:.2%}, "
                      f"explosive={label.explosive_10d}")

    print("\n✅ Pipeline test completed successfully!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
