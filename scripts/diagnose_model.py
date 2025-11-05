"""
Diagnose model performance and feature correlations
Understand why scores are low and what features matter
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np

from qaht.db import session_scope
from sqlalchemy import text

def main():
    print("=" * 80)
    print("🔍 MODEL PERFORMANCE DIAGNOSTICS")
    print("=" * 80)

    with session_scope() as session:
        # Load full training data with features and labels
        query = text("""
            SELECT
                f.symbol,
                f.date,
                f.bb_width_pct,
                f.bb_position,
                f.ma_spread_pct,
                f.ma_alignment_score,
                f.atr_pct,
                f.volatility_20d,
                f.volume_ratio_20d,
                f.obv_trend_5d,
                f.social_delta_7d,
                f.author_entropy_7d,
                f.engagement_ratio_7d,
                f.rsi_14,
                f.macd,
                f.macd_signal,
                l.fwd_ret_10d,
                l.explosive_10d,
                l.lead_time_days
            FROM factors f
            JOIN labels l ON f.symbol = l.symbol AND f.date = l.date
            WHERE l.fwd_ret_10d IS NOT NULL
        """)

        df = pd.read_sql(query, session.bind)

    if df.empty:
        print("❌ No training data found!")
        return 1

    print(f"\n📊 Dataset Overview:")
    print(f"  Total samples: {len(df)}")
    print(f"  Symbols: {df['symbol'].nunique()}")
    print(f"  Date range: {df['date'].min()} to {df['date'].max()}")

    # Explosion analysis
    explosions = df[df['explosive_10d'] == True]
    print(f"\n🚀 Explosion Analysis:")
    print(f"  Total explosions: {len(explosions)} ({len(explosions)/len(df):.1%} of samples)")
    print(f"  Avg forward return (explosions): {explosions['fwd_ret_10d'].mean():.1%}")
    print(f"  Avg forward return (non-explosions): {df[df['explosive_10d'] == False]['fwd_ret_10d'].mean():.1%}")

    # Feature correlation with explosions
    print(f"\n📈 Feature Correlations with Explosions:")

    features = [
        'bb_width_pct', 'bb_position', 'ma_spread_pct', 'ma_alignment_score',
        'atr_pct', 'volatility_20d', 'volume_ratio_20d', 'obv_trend_5d',
        'social_delta_7d', 'author_entropy_7d', 'engagement_ratio_7d',
        'rsi_14', 'macd', 'macd_signal'
    ]

    correlations = []
    for feat in features:
        if feat in df.columns and df[feat].notna().sum() > 0:
            # Fill NaN with 0 for correlation calculation
            corr = df[feat].fillna(0).corr(df['fwd_ret_10d'])
            correlations.append({'feature': feat, 'correlation': corr})

    corr_df = pd.DataFrame(correlations).sort_values('correlation', key=abs, ascending=False)

    for _, row in corr_df.head(10).iterrows():
        direction = "📈" if row['correlation'] > 0 else "📉"
        print(f"  {direction} {row['feature']:25s}: {row['correlation']:+.3f}")

    # Check feature distributions for explosions vs non-explosions
    print(f"\n🔬 Feature Distributions:")
    print(f"\n{'Feature':<25s} {'Explosion Mean':>15s} {'Normal Mean':>15s} {'Difference':>12s}")
    print("-" * 70)

    for feat in features[:8]:  # Top 8 features
        if feat in df.columns:
            exp_mean = explosions[feat].fillna(0).mean()
            normal_mean = df[df['explosive_10d'] == False][feat].fillna(0).mean()
            diff = exp_mean - normal_mean

            print(f"{feat:<25s} {exp_mean:>15.4f} {normal_mean:>15.4f} {diff:>+12.4f}")

    # Check if we have compression signals
    print(f"\n🗜️  Compression Signal Analysis:")

    # Low BB width = compression
    compressed = df[df['bb_width_pct'] < df['bb_width_pct'].quantile(0.2)]
    print(f"  Samples with compressed BB (< 20th percentile): {len(compressed)}")
    print(f"  Explosion rate in compressed samples: {compressed['explosive_10d'].mean():.1%}")
    print(f"  Explosion rate overall: {df['explosive_10d'].mean():.1%}")

    # Check social delta
    high_social = df[df['social_delta_7d'] > 1.0]  # 100%+ increase
    if len(high_social) > 0:
        print(f"\n📱 High Social Delta Analysis:")
        print(f"  Samples with social delta > 1.0: {len(high_social)}")
        print(f"  Explosion rate with high social: {high_social['explosive_10d'].mean():.1%}")

    # Check feature coverage
    print(f"\n📋 Feature Coverage (non-null %):")
    for feat in features:
        if feat in df.columns:
            coverage = (df[feat].notna().sum() / len(df)) * 100
            print(f"  {feat:<25s}: {coverage:>5.1f}%")

    # Sample some explosion examples
    print(f"\n🎯 Sample Explosion Examples:")
    print(f"\nShowing 5 random explosions with their feature values:")

    sample_explosions = explosions.sample(min(5, len(explosions)))

    for idx, row in sample_explosions.iterrows():
        print(f"\n  {row['symbol']} on {row['date']}:")
        print(f"    Forward return: {row['fwd_ret_10d']:.1%}")
        print(f"    BB width: {row['bb_width_pct']:.4f}")
        print(f"    Social delta: {row['social_delta_7d']:.2f}")
        print(f"    Volume ratio: {row['volume_ratio_20d']:.2f}")
        print(f"    RSI: {row['rsi_14']:.1f}")

    print("\n" + "=" * 80)
    print("💡 Insights:")
    print("=" * 80)

    # Provide actionable insights
    if corr_df.iloc[0]['correlation'] < 0.1:
        print("⚠️  WARNING: Weak feature correlations detected!")
        print("   → Features may not be predictive of explosions")
        print("   → Consider adding more discriminative features")

    if len(explosions) / len(df) < 0.05:
        print(f"⚠️  Class imbalance: Only {len(explosions)/len(df):.1%} explosions")
        print("   → Model may struggle to learn explosion patterns")
        print("   → Consider adjusting explosion threshold or adding more data")

    compression_boost = compressed['explosive_10d'].mean() / df['explosive_10d'].mean()
    if compression_boost > 1.5:
        print(f"✅ Compression signal works! {compression_boost:.1f}x more explosions")
    else:
        print(f"⚠️  Compression not strongly predictive (only {compression_boost:.1f}x)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
