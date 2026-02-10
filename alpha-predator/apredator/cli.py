"""Alpha Predator CLI."""
import click
import logging

logger = logging.getLogger("apredator.cli")


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging")
def main(verbose):
    """Alpha Predator — Unified Trading Intelligence System"""
    from .logging_conf import setup_logging
    from .config import get_config
    config = get_config()
    level = "DEBUG" if verbose else config.log_level
    setup_logging(log_level=level, log_file=config.log_file, name="apredator")


@main.command()
@click.option("--drop", is_flag=True, help="Drop existing tables first")
def init(drop):
    """Initialize database tables."""
    from .db import init_db, drop_all
    if drop:
        click.confirm("Drop all existing data?", abort=True)
        drop_all()
    init_db()
    click.echo("Database initialized.")


@main.command()
@click.option("--asset-type", "-a", type=click.Choice(["stock", "crypto", "all"]), default="all")
@click.option("--symbols", "-s", default=None, help="Comma-separated symbols")
@click.option("--no-alerts", is_flag=True, help="Skip sending alerts")
def scan(asset_type, symbols, no_alerts):
    """Run daily scan pipeline."""
    from .pipeline.daily_scan import run_daily_scan
    asset_types = ["stock", "crypto"] if asset_type == "all" else [asset_type]
    sym_list = [s.strip().upper() for s in symbols.split(",")] if symbols else None
    results = run_daily_scan(asset_types=asset_types, symbols=sym_list, send_alerts=not no_alerts)
    click.echo(f"Scan complete: {results.get('n_signals', 0)} signals found")
    top = results.get("top_signals", [])
    for sig in top[:10]:
        click.echo(f"  {sig['symbol']:8s} Score={sig['score']:3d} Conviction={sig['conviction']}")


@main.command()
@click.option("--interval", "-i", default=60, help="Scan interval in minutes")
@click.option("--asset-type", "-a", type=click.Choice(["stock", "crypto", "all"]), default="all")
def monitor(interval, asset_type):
    """Start real-time monitoring loop."""
    from .pipeline.realtime import run_realtime_monitor
    asset_types = ["stock", "crypto"] if asset_type == "all" else [asset_type]
    click.echo(f"Starting real-time monitor (interval={interval}min)...")
    run_realtime_monitor(interval_minutes=interval, asset_types=asset_types)


@main.command()
@click.option("--start", required=True, help="Start date YYYY-MM-DD")
@click.option("--end", required=True, help="End date YYYY-MM-DD")
@click.option("--capital", default=100000, help="Initial capital")
@click.option("--min-score", default=70, help="Minimum quantum score")
@click.option("--symbols", "-s", default=None, help="Comma-separated symbols")
def backtest(start, end, capital, min_score, symbols):
    """Run backtest simulation."""
    from .backtest.simulator import simulate
    from .backtest.metrics import calculate_performance
    sym_list = [s.strip().upper() for s in symbols.split(",")] if symbols else None
    trades = simulate(start, end, initial_capital=capital, min_score=min_score, symbols=sym_list)
    if trades.empty:
        click.echo("No trades executed.")
        return
    metrics = calculate_performance(trades, initial_capital=capital)
    click.echo(f"Trades: {metrics['total_trades']} | Hit Rate: {metrics['hit_rate']*100:.1f}%")
    click.echo(f"Sharpe: {metrics['sharpe_ratio']:.2f} | Total Return: {metrics['total_return_pct']*100:.1f}%")
    click.echo(f"Max DD: {metrics['max_drawdown']*100:.1f}% | Profit Factor: {metrics['profit_factor']:.2f}")


@main.command()
@click.option("--port", default=8501, help="Streamlit port")
def dashboard(port):
    """Launch Streamlit dashboard."""
    import subprocess
    import sys
    dash_path = str(__import__("pathlib").Path(__file__).parent / "dashboard" / "app.py")
    subprocess.run([sys.executable, "-m", "streamlit", "run", dash_path, "--server.port", str(port)])


@main.command()
def validate():
    """Validate feature registry and database integrity."""
    from .db import session_scope
    from .schemas import Factors, Predictions
    from .features.registry import FEATURES_EQUITIES, FEATURES_CRYPTO
    from sqlalchemy import func, select
    with session_scope() as session:
        n_factors = session.execute(select(func.count()).select_from(Factors)).scalar()
        n_preds = session.execute(select(func.count()).select_from(Predictions)).scalar()
    click.echo(f"Factors rows: {n_factors}")
    click.echo(f"Predictions rows: {n_preds}")
    click.echo(f"Equity features registered: {len(FEATURES_EQUITIES)}")
    click.echo(f"Crypto features registered: {len(FEATURES_CRYPTO)}")
    click.echo("Validation complete.")


@main.command()
@click.argument("symbol")
def analyze(symbol):
    """Deep analysis of a single symbol."""
    from .adapters.yahoo import fetch_prices
    from .features.technical import compute_all_technical
    from .features.explosive import compute_all_explosive
    from .scoring.combo_matcher import match_combos
    from .scoring.tier_system import classify_tier
    symbol = symbol.upper()
    click.echo(f"Analyzing {symbol}...")
    df = fetch_prices([symbol], period="1y")
    if df.empty:
        click.echo("No price data found.")
        return
    sym_df = df[df["symbol"] == symbol].sort_values("date")
    tech = compute_all_technical(sym_df)
    explosive = compute_all_explosive(sym_df)
    combos = match_combos(explosive)
    click.echo(f"Technical: RSI={tech.get('rsi_14','N/A'):.1f}, BB Width={tech.get('bb_width_pct','N/A'):.1f}%")
    click.echo(f"Vol Z-Score: {explosive.get('vol_zscore','N/A'):.2f}")
    if combos:
        for c in combos:
            click.echo(f"  COMBO: {c['name']} (hit rate: {c['hit_rate']*100:.1f}%)")
    else:
        click.echo("  No combo matches.")
