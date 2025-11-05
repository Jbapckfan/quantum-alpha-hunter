"""
Validation script to check critical fixes are working
Run this after initial setup to ensure everything is configured properly
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_imports():
    """Verify all critical imports work"""
    print("1️⃣  Testing imports...")

    try:
        import pandas as pd
        import numpy as np
        import yfinance as yf
        from qaht.db import session_scope, init_db
        from qaht.schemas import Factors, PriceOHLC, Labels
        from qaht.config import get_config
        from qaht.scoring.registry import FEATURES, validate_features
        from qaht.utils.retry import retry_with_backoff
        from qaht.utils.parallel import process_concurrently

        print("   ✅ All imports successful")
        return True
    except ImportError as e:
        print(f"   ❌ Import failed: {e}")
        return False


def test_database():
    """Verify database initialization and primary key access"""
    print("\n2️⃣  Testing database...")

    try:
        from qaht.db import init_db, session_scope
        from qaht.schemas import Factors, PriceOHLC

        # Initialize database
        init_db()
        print("   ✅ Database initialized")

        # Test composite primary key access (CRITICAL FIX)
        with session_scope() as session:
            # This should not raise an error
            result = session.get(Factors, ("TEST", "2024-01-01"))

        print("   ✅ Composite primary key access working")

        # Test write and read
        with session_scope() as session:
            test_price = PriceOHLC(
                symbol="TEST",
                date="2024-01-01",
                open=100.0,
                high=105.0,
                low=99.0,
                close=104.0,
                volume=1000000,
                asset_type="stock"
            )
            session.add(test_price)

        print("   ✅ Write operations working")

        # Read back
        with session_scope() as session:
            from sqlalchemy import select
            result = session.execute(
                select(PriceOHLC).where(PriceOHLC.symbol == "TEST")
            ).scalar_one_or_none()

            if result:
                print("   ✅ Read operations working")
            else:
                print("   ❌ Read operation failed")
                return False

        return True

    except Exception as e:
        print(f"   ❌ Database test failed: {e}")
        return False


def test_feature_registry():
    """Verify feature registry is consistent"""
    print("\n3️⃣  Testing feature registry...")

    try:
        from qaht.scoring.registry import FEATURES, validate_features, get_features_for_asset_type
        import pandas as pd

        print(f"   ✅ Feature registry loaded: {len(FEATURES)} features")
        print(f"      Equities: {len(get_features_for_asset_type('stock'))} features")
        print(f"      Crypto: {len(get_features_for_asset_type('crypto'))} features")

        # Test validation with missing features
        test_df = pd.DataFrame({
            'bb_width_pct': [0.05],
            'ma_spread_pct': [0.03],
            'missing_feature': [1.0]
        })

        try:
            validated = validate_features(test_df, raise_on_missing=False)
            print(f"   ✅ Feature validation working")
            return True
        except Exception as e:
            print(f"   ❌ Feature validation failed: {e}")
            return False

    except Exception as e:
        print(f"   ❌ Feature registry test failed: {e}")
        return False


def test_configuration():
    """Verify configuration is loaded"""
    print("\n4️⃣  Testing configuration...")

    try:
        from qaht.config import get_config

        config = get_config()

        print(f"   Database URL: {config.db_url}")
        print(f"   Log level: {config.log_level}")
        print(f"   Lookback days: {config.pipeline.lookback_days}")
        print(f"   BB window: {config.features.bb_window}")
        print(f"   MA windows: {config.features.ma_windows}")

        print("   ✅ Configuration loaded successfully")

        # Check Reddit credentials
        if config.reddit_client_id:
            print("   ✅ Reddit API credentials found")
        else:
            print("   ⚠️  Reddit API credentials not configured (optional for testing)")

        return True

    except Exception as e:
        print(f"   ❌ Configuration test failed: {e}")
        return False


def test_retry_logic():
    """Test retry decorator"""
    print("\n5️⃣  Testing retry logic...")

    try:
        from qaht.utils.retry import retry_with_backoff

        @retry_with_backoff(max_retries=2, initial_delay=0.1)
        def flaky_function(attempt_count=[0]):
            attempt_count[0] += 1
            if attempt_count[0] < 2:
                raise ValueError("Simulated failure")
            return "success"

        result = flaky_function()
        if result == "success":
            print("   ✅ Retry logic working (recovered from failure)")
            return True
        else:
            print("   ❌ Retry logic didn't return expected result")
            return False

    except Exception as e:
        print(f"   ❌ Retry test failed: {e}")
        return False


def test_basic_data_fetch():
    """Test fetching data from Yahoo Finance"""
    print("\n6️⃣  Testing data fetch...")

    try:
        import yfinance as yf
        import pandas as pd

        ticker = yf.Ticker("AAPL")
        hist = ticker.history(period="5d")

        if len(hist) > 0:
            print(f"   ✅ Fetched {len(hist)} days of data for AAPL")
            print(f"      Latest close: ${hist['Close'].iloc[-1]:.2f}")
            return True
        else:
            print("   ❌ No data returned from Yahoo Finance")
            return False

    except Exception as e:
        print(f"   ❌ Data fetch failed: {e}")
        return False


def main():
    """Run all validation tests"""
    print("🔍 Quantum Alpha Hunter - System Validation")
    print("=" * 60)

    tests = [
        test_imports,
        test_database,
        test_feature_registry,
        test_configuration,
        test_retry_logic,
        test_basic_data_fetch,
    ]

    results = []
    for test in tests:
        results.append(test())

    print("\n" + "=" * 60)
    print("📊 Validation Summary")
    print("=" * 60)

    passed = sum(results)
    total = len(results)

    print(f"Tests passed: {passed}/{total}")

    if all(results):
        print("\n🎉 All tests passed! System is ready.")
        print("\nNext steps:")
        print("  1. Copy .env.example to .env and add Reddit credentials")
        print("  2. Run: qaht run-pipeline")
        print("  3. Check results: qaht validate")
        return 0
    else:
        print("\n⚠️  Some tests failed. Please fix the issues above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
