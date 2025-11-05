#!/usr/bin/env python
"""
Daily scoring and alert generation script
Run this after the daily pipeline to get immediate signals

Usage:
    python scripts/daily_score_and_alert.py --min-score 80 --email
    python scripts/daily_score_and_alert.py --slack-webhook <url>
"""
import argparse
import sys
import logging
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from qaht.db import session_scope
from qaht.schemas import Predictions
from sqlalchemy import select, desc
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_todays_signals(min_score: int = 80, max_results: int = 20) -> pd.DataFrame:
    """
    Get today's top signals

    Args:
        min_score: Minimum quantum score threshold
        max_results: Maximum number of results to return

    Returns:
        DataFrame of top signals
    """
    today = datetime.now().strftime("%Y-%m-%d")

    with session_scope() as session:
        query = select(Predictions).where(
            Predictions.date == today,
            Predictions.quantum_score >= min_score
        ).order_by(
            desc(Predictions.quantum_score)
        ).limit(max_results)

        predictions = session.execute(query).scalars().all()

        if not predictions:
            logger.info(f"No signals found for {today} with score >= {min_score}")
            return pd.DataFrame()

        data = [{
            'symbol': p.symbol,
            'date': p.date,
            'quantum_score': p.quantum_score,
            'conviction_level': p.conviction_level,
            'prob_hit_10d': p.prob_hit_10d,
            'components': p.components
        } for p in predictions]

        return pd.DataFrame(data)


def format_alert_message(signals_df: pd.DataFrame) -> str:
    """
    Format signals into readable alert message

    Args:
        signals_df: DataFrame of signals

    Returns:
        Formatted alert message
    """
    if signals_df.empty:
        return "No high-conviction signals today."

    msg = f"🎯 QUANTUM ALPHA HUNTER - Daily Signals\n"
    msg += f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
    msg += f"🔥 Found {len(signals_df)} high-conviction opportunities\n\n"

    # Group by conviction level
    for level in ['MAX', 'HIGH', 'MED']:
        level_signals = signals_df[signals_df['conviction_level'] == level]
        if len(level_signals) > 0:
            emoji = {'MAX': '🚀', 'HIGH': '⭐', 'MED': '📊'}[level]
            msg += f"{emoji} {level} CONVICTION ({len(level_signals)})\n"
            msg += "-" * 50 + "\n"

            for _, signal in level_signals.iterrows():
                msg += f"  {signal['symbol']:8s} | Score: {signal['quantum_score']:3d} | "
                msg += f"Prob: {signal['prob_hit_10d']*100:5.1f}%\n"

            msg += "\n"

    msg += "\n💡 Review these signals in the dashboard:\n"
    msg += "   qaht dashboard\n"

    return msg


def send_console_alert(signals_df: pd.DataFrame):
    """Print alert to console"""
    message = format_alert_message(signals_df)
    print("\n" + "="*60)
    print(message)
    print("="*60 + "\n")


def send_email_alert(signals_df: pd.DataFrame, recipient: str):
    """
    Send email alert (requires SMTP configuration)

    Args:
        signals_df: DataFrame of signals
        recipient: Email address to send to
    """
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        import os

        # Get SMTP credentials from environment
        smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        smtp_port = int(os.getenv('SMTP_PORT', '587'))
        smtp_user = os.getenv('SMTP_USER')
        smtp_password = os.getenv('SMTP_PASSWORD')

        if not smtp_user or not smtp_password:
            logger.error("SMTP credentials not configured. Set SMTP_USER and SMTP_PASSWORD env vars.")
            return

        message = format_alert_message(signals_df)

        # Create email
        msg = MIMEMultipart()
        msg['From'] = smtp_user
        msg['To'] = recipient
        msg['Subject'] = f"🎯 Quantum Alpha Hunter - {len(signals_df)} Signals - {datetime.now().strftime('%Y-%m-%d')}"

        msg.attach(MIMEText(message, 'plain'))

        # Send
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.send_message(msg)
        server.quit()

        logger.info(f"Email alert sent to {recipient}")

    except Exception as e:
        logger.error(f"Failed to send email: {e}")


def send_slack_alert(signals_df: pd.DataFrame, webhook_url: str):
    """
    Send Slack alert via webhook

    Args:
        signals_df: DataFrame of signals
        webhook_url: Slack webhook URL
    """
    try:
        import requests
        import json

        message = format_alert_message(signals_df)

        payload = {
            "text": message,
            "username": "Quantum Alpha Hunter",
            "icon_emoji": ":chart_with_upwards_trend:"
        }

        response = requests.post(
            webhook_url,
            data=json.dumps(payload),
            headers={'Content-Type': 'application/json'},
            timeout=10
        )

        if response.status_code == 200:
            logger.info("Slack alert sent successfully")
        else:
            logger.error(f"Slack alert failed: {response.status_code} - {response.text}")

    except Exception as e:
        logger.error(f"Failed to send Slack alert: {e}")


def send_telegram_alert(signals_df: pd.DataFrame, bot_token: str, chat_id: str):
    """
    Send Telegram alert

    Args:
        signals_df: DataFrame of signals
        bot_token: Telegram bot token
        chat_id: Telegram chat ID
    """
    try:
        import requests

        message = format_alert_message(signals_df)

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }

        response = requests.post(url, json=payload, timeout=10)

        if response.status_code == 200:
            logger.info("Telegram alert sent successfully")
        else:
            logger.error(f"Telegram alert failed: {response.status_code}")

    except Exception as e:
        logger.error(f"Failed to send Telegram alert: {e}")


def save_alerts_to_file(signals_df: pd.DataFrame, output_dir: str = "data/alerts"):
    """
    Save alerts to dated file

    Args:
        signals_df: DataFrame of signals
        output_dir: Directory to save alerts
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    today = datetime.now().strftime("%Y-%m-%d")
    filename = f"{output_dir}/alerts_{today}.csv"

    signals_df.to_csv(filename, index=False)
    logger.info(f"Alerts saved to {filename}")

    # Also save as JSON for easy parsing
    json_filename = f"{output_dir}/alerts_{today}.json"
    signals_df.to_json(json_filename, orient='records', indent=2)
    logger.info(f"Alerts saved to {json_filename}")


def main():
    parser = argparse.ArgumentParser(description='Generate daily trading signals and alerts')
    parser.add_argument('--min-score', type=int, default=80, help='Minimum quantum score (default: 80)')
    parser.add_argument('--max-results', type=int, default=20, help='Maximum results (default: 20)')
    parser.add_argument('--email', type=str, help='Email recipient for alerts')
    parser.add_argument('--slack-webhook', type=str, help='Slack webhook URL')
    parser.add_argument('--telegram-bot-token', type=str, help='Telegram bot token')
    parser.add_argument('--telegram-chat-id', type=str, help='Telegram chat ID')
    parser.add_argument('--save-file', action='store_true', help='Save alerts to file')
    parser.add_argument('--quiet', action='store_true', help='Suppress console output')

    args = parser.parse_args()

    # Get signals
    logger.info(f"Fetching signals with min_score={args.min_score}")
    signals_df = get_todays_signals(args.min_score, args.max_results)

    if signals_df.empty:
        logger.info("No signals to alert on")
        if not args.quiet:
            print("No high-conviction signals today.")
        return

    # Send alerts
    if not args.quiet:
        send_console_alert(signals_df)

    if args.email:
        send_email_alert(signals_df, args.email)

    if args.slack_webhook:
        send_slack_alert(signals_df, args.slack_webhook)

    if args.telegram_bot_token and args.telegram_chat_id:
        send_telegram_alert(signals_df, args.telegram_bot_token, args.telegram_chat_id)

    if args.save_file:
        save_alerts_to_file(signals_df)

    logger.info("Alert generation complete")


if __name__ == "__main__":
    main()
