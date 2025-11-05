"""
Command-line interface for Quantum Alpha Hunter
"""
import click
import sys
from pathlib import Path

from .db import init_db, drop_all
from .config import get_config
from .logging_conf import setup_logging


@click.group()
@click.version_option(version="0.1.0")
def main():
    """
    Quantum Alpha Hunter - AI-Powered Multi-Bagger Detection System

    A self-learning market intelligence system for identifying explosive moves
    before they happen.
    """
    pass


@main.command()
@click.option('--drop', is_flag=True, help='Drop existing tables first (DESTRUCTIVE)')
def init(drop):
    """Initialize the database and create all tables"""
    logger = setup_logging()

    if drop:
        click.confirm(
            '⚠️  This will DELETE all existing data. Continue?',
            abort=True
        )
        drop_all()
        logger.info("Dropped all tables")

    init_db()
    click.echo("✅ Database initialized successfully")
    click.echo(f"   Location: {get_config().db_url}")


@main.command()
@click.option('--universe', default=None, help='Path to universe CSV file')
@click.option('--symbols', default=None, help='Comma-separated symbols to process')
def run_pipeline(universe, symbols):
    """
    Run the complete data pipeline

    Fetches data, computes features, labels events, trains models, and generates scores.
    """
    try:
        # Dynamic import to avoid loading heavy dependencies at CLI startup
        from .equities_options.pipeline.daily_job import run as run_equities
        from .crypto.pipeline.daily_job import run as run_crypto
    except ImportError as e:
        click.echo(f"❌ Pipeline not yet implemented: {e}", err=True)
        click.echo("   This will be available in Phase 2 of development")
        sys.exit(1)

    logger = setup_logging()
    click.echo("🚀 Starting Quantum Alpha Hunter pipeline...")

    try:
        # Run both verticals
        click.echo("\n📊 Processing equities/options...")
        equities_summary = run_equities(universe_csv=universe)

        click.echo("\n₿  Processing crypto...")
        crypto_summary = run_crypto(universe_csv=universe)

        click.echo("\n✅ Pipeline completed successfully!")
        click.echo(f"   Equities: {equities_summary['total_duration']:.2f}s")
        click.echo(f"   Crypto: {crypto_summary['total_duration']:.2f}s")

    except Exception as e:
        logger.error(f"Pipeline failed: {str(e)}")
        click.echo(f"\n❌ Pipeline failed: {str(e)}", err=True)
        sys.exit(1)


@main.command()
@click.option('--start', default='2022-01-01', help='Start date (YYYY-MM-DD)')
@click.option('--end', default='2024-01-01', help='End date (YYYY-MM-DD)')
@click.option('--capital', default=100000, type=float, help='Initial capital')
def backtest(start, end, capital):
    """
    Run historical backtest

    Simulates trading based on historical quantum scores.
    """
    try:
        from .backtest.simulator import simulate
        from .backtest.metrics import calculate_performance
    except ImportError as e:
        click.echo(f"❌ Backtest not yet implemented: {e}", err=True)
        sys.exit(1)

    click.echo(f"🔬 Running backtest: {start} to {end}")
    click.echo(f"   Initial capital: ${capital:,.2f}")

    # Run simulation
    results = simulate(start_date=start, end_date=end, initial_capital=capital)

    # Calculate metrics
    metrics = calculate_performance(results)

    # Display results
    click.echo("\n📈 Backtest Results:")
    click.echo(f"   Total Trades: {metrics['total_trades']}")
    click.echo(f"   Hit Rate: {metrics['hit_rate']:.2%}")
    click.echo(f"   Sharpe Ratio: {metrics['sharpe']:.2f}")
    click.echo(f"   Max Drawdown: {metrics['max_drawdown']:.2%}")
    click.echo(f"   Final Capital: ${metrics['final_capital']:,.2f}")
    click.echo(f"   Total Return: {metrics['total_return']:.2%}")


@main.command()
@click.option('--port', default=8501, type=int, help='Port to run dashboard on')
def dashboard(port):
    """
    Launch the Streamlit dashboard

    Opens the web interface for viewing watchlists, signals, and performance.
    """
    import subprocess
    import os

    dashboard_path = Path(__file__).parent / "dashboard" / "app.py"

    if not dashboard_path.exists():
        click.echo("❌ Dashboard not yet implemented", err=True)
        click.echo("   This will be available in Phase 4 of development")
        sys.exit(1)

    click.echo(f"🎨 Launching dashboard on port {port}...")
    click.echo(f"   Visit: http://localhost:{port}")

    try:
        subprocess.run([
            "streamlit", "run",
            str(dashboard_path),
            "--server.port", str(port)
        ])
    except KeyboardInterrupt:
        click.echo("\n👋 Dashboard stopped")
    except FileNotFoundError:
        click.echo("❌ Streamlit not installed. Install with: pip install streamlit")
        sys.exit(1)


@main.command()
def validate():
    """
    Validate system configuration and critical fixes

    Checks database, API credentials, and feature registry consistency.
    """
    from .scoring.registry import FEATURES
    import os

    click.echo("🔍 Validating Quantum Alpha Hunter setup...\n")

    # Check 1: Database
    click.echo("1️⃣  Database connection...")
    try:
        from .db import session_scope
        from .schemas import Factors

        with session_scope() as session:
            # Test composite primary key access
            result = session.get(Factors, ("TEST", "2024-01-01"))
        click.echo("   ✅ Database connection working")
        click.echo("   ✅ Composite primary key access working")
    except Exception as e:
        click.echo(f"   ❌ Database error: {e}")

    # Check 2: Feature registry
    click.echo("\n2️⃣  Feature registry...")
    click.echo(f"   ✅ {len(FEATURES)} features registered: {', '.join(FEATURES[:5])}...")

    # Check 3: Configuration
    click.echo("\n3️⃣  Configuration...")
    config = get_config()
    click.echo(f"   Database: {config.db_url}")
    click.echo(f"   Log level: {config.log_level}")

    # Check 4: API credentials
    click.echo("\n4️⃣  API Credentials...")
    if config.reddit_client_id:
        click.echo("   ✅ Reddit API credentials found")
    else:
        click.echo("   ⚠️  Reddit API credentials missing (set in .env)")

    # Check 5: Dependencies
    click.echo("\n5️⃣  Critical dependencies...")
    try:
        import pandas
        import numpy
        import sklearn
        import yfinance
        click.echo("   ✅ All critical packages installed")
    except ImportError as e:
        click.echo(f"   ❌ Missing package: {e}")

    click.echo("\n✨ Validation complete!")


@main.command()
@click.argument('symbol')
@click.option('--days', default=30, help='Number of days to analyze')
def analyze(symbol, days):
    """
    Analyze a single symbol

    Shows current quantum score, features, and recent predictions.
    """
    click.echo(f"🔍 Analyzing {symbol} (last {days} days)...")

    try:
        from .db import session_scope
        from .schemas import Predictions, Factors
        from sqlalchemy import select

        with session_scope() as session:
            # Get latest prediction
            pred = session.execute(
                select(Predictions)
                .where(Predictions.symbol == symbol)
                .order_by(Predictions.date.desc())
                .limit(1)
            ).scalar_one_or_none()

            if pred:
                click.echo(f"\n📊 Latest Score (as of {pred.date}):")
                click.echo(f"   Quantum Score: {pred.quantum_score}/100")
                click.echo(f"   Conviction: {pred.conviction_level}")
                click.echo(f"   Probability: {pred.prob_hit_10d:.1%}")
            else:
                click.echo(f"\n⚠️  No predictions found for {symbol}")
                click.echo("   Run pipeline first: qaht run-pipeline")

    except Exception as e:
        click.echo(f"❌ Error: {e}")


if __name__ == "__main__":
    main()
