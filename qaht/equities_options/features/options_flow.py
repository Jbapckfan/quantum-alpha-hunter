"""
Options flow analysis from Yahoo Finance.

Completely FREE - uses yfinance library to extract options data.

Options activity predicts stock moves:
- Unusual call volume = bullish
- High put/call ratio = bearish (or squeeze setup)
- IV spikes = big move coming
- Large block trades = whales entering
"""

import logging
from datetime import datetime
from typing import Dict, Optional

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


def compute_options_signals(symbol: str, ticker_obj=None) -> Dict:
    """
    Compute options flow signals from Yahoo Finance.

    Args:
        symbol: Stock ticker symbol
        ticker_obj: yfinance Ticker object (optional, will create if not provided)

    Returns:
        Dict with:
            - options_score: 0-100 (100 = very bullish options activity)
            - put_call_ratio: Put volume / Call volume
            - put_call_oi_ratio: Put OI / Call OI
            - iv_rank: Implied volatility rank (0-100)
            - unusual_activity: True if unusual options volume
            - whale_activity: True if large block trades detected
            - iv_percentile: Current IV vs 52-week range
            - days_to_nearest_expiry: Days until nearest options expiration
    """
    try:
        # Import here to avoid circular dependency
        try:
            import yfinance as yf
        except ImportError:
            logger.warning(f"yfinance not installed, cannot compute options signals for {symbol}")
            return _empty_options_score()

        if ticker_obj is None:
            ticker_obj = yf.Ticker(symbol)

        # Get options expiration dates
        expirations = ticker_obj.options

        if not expirations or len(expirations) == 0:
            logger.debug(f"No options data available for {symbol}")
            return _empty_options_score()

        # Get nearest expiration (typically most liquid)
        nearest_expiry = expirations[0]

        # Fetch options chain
        try:
            opt_chain = ticker_obj.option_chain(nearest_expiry)
        except Exception as e:
            logger.warning(f"Could not fetch options chain for {symbol}: {e}")
            return _empty_options_score()

        calls = opt_chain.calls
        puts = opt_chain.puts

        if calls.empty or puts.empty:
            logger.debug(f"Empty options chain for {symbol}")
            return _empty_options_score()

        # Compute signals
        signals = {}

        # 1. Put/Call Ratio (volume and open interest)
        total_call_volume = calls['volume'].sum()
        total_put_volume = puts['volume'].sum()
        total_call_oi = calls['openInterest'].sum()
        total_put_oi = puts['openInterest'].sum()

        put_call_ratio = total_put_volume / total_call_volume if total_call_volume > 0 else 1.0
        put_call_oi_ratio = total_put_oi / total_call_oi if total_call_oi > 0 else 1.0

        signals['put_call_ratio'] = round(put_call_ratio, 3)
        signals['put_call_oi_ratio'] = round(put_call_oi_ratio, 3)

        # 2. Implied Volatility Analysis
        try:
            # Get historical data for IV context
            hist = ticker_obj.history(period="1y")
            if not hist.empty:
                current_iv = calls['impliedVolatility'].median()

                # IV rank: where is current IV in 52-week range?
                # (we approximate from ATM options)
                if not pd.isna(current_iv) and current_iv > 0:
                    # Simple IV percentile (in real system, would track historical IV)
                    signals['current_iv'] = round(float(current_iv), 4)
                    # For now, use a heuristic: high IV is good for explosive moves
                    iv_rank = min(100, current_iv * 100)  # Normalize to 0-100
                    signals['iv_rank'] = round(iv_rank, 1)
                else:
                    signals['current_iv'] = 0
                    signals['iv_rank'] = 50  # Neutral
            else:
                signals['current_iv'] = 0
                signals['iv_rank'] = 50

        except Exception as e:
            logger.debug(f"Could not compute IV rank for {symbol}: {e}")
            signals['current_iv'] = 0
            signals['iv_rank'] = 50

        # 3. Unusual Activity Detection
        # Large volume relative to open interest = unusual activity
        call_volume_to_oi = total_call_volume / total_call_oi if total_call_oi > 0 else 0
        put_volume_to_oi = total_put_volume / total_put_oi if total_put_oi > 0 else 0

        # If volume > 50% of OI, that's unusual
        unusual_call_activity = call_volume_to_oi > 0.5
        unusual_put_activity = put_volume_to_oi > 0.5
        unusual_activity = unusual_call_activity or unusual_put_activity

        signals['unusual_activity'] = unusual_activity

        # 4. Whale Activity (Large Block Trades)
        # Detect options with very high volume relative to avg
        call_avg_volume = calls['volume'].mean()
        put_avg_volume = puts['volume'].mean()

        # Any single contract with 3x avg volume = whale trade
        whale_calls = (calls['volume'] > call_avg_volume * 3).any()
        whale_puts = (puts['volume'] > put_avg_volume * 3).any()
        whale_activity = whale_calls or whale_puts

        signals['whale_activity'] = whale_activity

        # 5. Days to Expiration
        try:
            expiry_date = datetime.strptime(nearest_expiry, '%Y-%m-%d')
            days_to_expiry = (expiry_date - datetime.now()).days
            signals['days_to_nearest_expiry'] = days_to_expiry
        except:
            signals['days_to_nearest_expiry'] = 0

        # 6. Compute Overall Options Score (0-100)
        score = 50  # Neutral baseline

        # Put/Call ratio signals
        # Low P/C ratio (< 0.7) = bullish, High P/C (> 1.3) = bearish or squeeze setup
        if put_call_ratio < 0.7:
            score += 20  # Very bullish
        elif put_call_ratio < 0.85:
            score += 10  # Moderately bullish
        elif put_call_ratio > 1.3:
            score -= 10  # Bearish (or potential squeeze)

        # High IV = potential for big move
        if signals['iv_rank'] > 70:
            score += 15  # High IV = explosive move likely

        # Unusual activity
        if unusual_activity:
            score += 15  # Smart money moving in

        # Whale activity
        if whale_activity:
            score += 10  # Big players entering

        # Call volume dominance
        if total_call_volume > total_put_volume * 1.5:
            score += 10  # Strong call buying

        score = max(0, min(100, score))
        signals['options_score'] = round(score, 1)

        logger.info(f"{symbol} options score: {score:.0f} (P/C={put_call_ratio:.2f}, IV_rank={signals['iv_rank']:.0f}, unusual={unusual_activity}, whale={whale_activity})")

        return signals

    except Exception as e:
        logger.error(f"Error computing options signals for {symbol}: {e}")
        return _empty_options_score()


def _empty_options_score() -> Dict:
    """Return empty options score when data unavailable."""
    return {
        'options_score': 50,  # Neutral
        'put_call_ratio': 1.0,
        'put_call_oi_ratio': 1.0,
        'iv_rank': 50,
        'unusual_activity': False,
        'whale_activity': False,
        'current_iv': 0,
        'days_to_nearest_expiry': 0
    }


def compute_options_features(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """
    Add options-based features to a dataframe of prices.

    This fetches current options data and adds it as static features.
    For time-series backtesting, you would need historical options data.

    Args:
        df: DataFrame with OHLCV data
        symbol: Stock ticker

    Returns:
        DataFrame with added options features columns
    """
    try:
        # Fetch current options signals
        signals = compute_options_signals(symbol)

        # Add as constant columns (for real-time scoring)
        df['options_score'] = signals['options_score']
        df['put_call_ratio'] = signals['put_call_ratio']
        df['put_call_oi_ratio'] = signals['put_call_oi_ratio']
        df['iv_rank'] = signals['iv_rank']
        df['unusual_options_activity'] = int(signals['unusual_activity'])
        df['whale_options_activity'] = int(signals['whale_activity'])

        logger.info(f"Added options features for {symbol}")

    except Exception as e:
        logger.warning(f"Could not add options features for {symbol}: {e}")
        # Add empty columns
        df['options_score'] = 50
        df['put_call_ratio'] = 1.0
        df['put_call_oi_ratio'] = 1.0
        df['iv_rank'] = 50
        df['unusual_options_activity'] = 0
        df['whale_options_activity'] = 0

    return df


def analyze_options_chain_detail(symbol: str, ticker_obj=None) -> Dict:
    """
    Deep analysis of options chain for advanced users.

    Returns detailed breakdown of:
    - ATM (at-the-money) options activity
    - OTM (out-of-the-money) call walls
    - ITM (in-the-money) put support
    - Gamma exposure
    - Max pain calculation
    """
    try:
        try:
            import yfinance as yf
        except ImportError:
            return {}

        if ticker_obj is None:
            ticker_obj = yf.Ticker(symbol)

        info = ticker_obj.info
        current_price = info.get('currentPrice') or info.get('regularMarketPrice')

        if not current_price:
            return {}

        expirations = ticker_obj.options
        if not expirations:
            return {}

        # Get nearest monthly expiration (most liquid)
        nearest_expiry = expirations[0]
        opt_chain = ticker_obj.option_chain(nearest_expiry)

        calls = opt_chain.calls
        puts = opt_chain.puts

        # Find ATM strike (closest to current price)
        calls['distance'] = abs(calls['strike'] - current_price)
        atm_call = calls.loc[calls['distance'].idxmin()]

        puts['distance'] = abs(puts['strike'] - current_price)
        atm_put = puts.loc[puts['distance'].idxmin()]

        # Find max pain (strike with most OI)
        all_strikes = pd.concat([
            calls[['strike', 'openInterest']].rename(columns={'openInterest': 'call_oi'}),
            puts[['strike', 'openInterest']].rename(columns={'openInterest': 'put_oi'})
        ], axis=1)

        # Max pain = strike with highest total OI
        total_oi = all_strikes.groupby('strike').sum()
        max_pain_strike = total_oi.sum(axis=1).idxmax()

        return {
            'current_price': current_price,
            'atm_strike': atm_call['strike'],
            'atm_call_volume': atm_call['volume'],
            'atm_call_oi': atm_call['openInterest'],
            'atm_put_volume': atm_put['volume'],
            'atm_put_oi': atm_put['openInterest'],
            'max_pain': max_pain_strike,
            'distance_to_max_pain': current_price - max_pain_strike,
            'nearest_expiry': nearest_expiry
        }

    except Exception as e:
        logger.debug(f"Could not perform detailed options analysis for {symbol}: {e}")
        return {}
