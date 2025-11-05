"""
Input Validation Utilities

Validates user inputs to prevent injection attacks and ensure data integrity.
"""

import re
import logging
from typing import Optional, List

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Raised when input validation fails"""
    pass


def validate_ticker(ticker: str, allow_crypto: bool = True) -> str:
    """
    Validate ticker symbol format.

    Args:
        ticker: Ticker symbol to validate
        allow_crypto: Allow crypto tickers with .X suffix (e.g., BTC.X)

    Returns:
        Validated uppercase ticker

    Raises:
        ValidationError: If ticker format is invalid

    Examples:
        >>> validate_ticker("AAPL")
        'AAPL'
        >>> validate_ticker("BTC.X")
        'BTC.X'
        >>> validate_ticker("ABC123")
        ValidationError: Invalid ticker format
    """
    if not ticker or not isinstance(ticker, str):
        raise ValidationError("Ticker must be a non-empty string")

    ticker = ticker.strip().upper()

    # Stock ticker pattern: 1-5 uppercase letters
    stock_pattern = r'^[A-Z]{1,5}$'

    # Crypto ticker pattern: 1-10 letters/numbers, optional .X suffix
    crypto_pattern = r'^[A-Z0-9]{1,10}(\.X)?$'

    pattern = crypto_pattern if allow_crypto else stock_pattern

    if not re.match(pattern, ticker):
        raise ValidationError(
            f"Invalid ticker format: '{ticker}'. "
            f"Expected 1-5 uppercase letters" +
            (" or crypto format (e.g., BTC.X)" if allow_crypto else "")
        )

    # Additional security: check for common injection attempts
    dangerous_chars = ['<', '>', '"', "'", ';', '&', '|', '`', '$', '(', ')']
    if any(char in ticker for char in dangerous_chars):
        raise ValidationError(f"Ticker contains dangerous characters: '{ticker}'")

    return ticker


def validate_tickers(tickers: List[str], allow_crypto: bool = True) -> List[str]:
    """
    Validate multiple ticker symbols.

    Args:
        tickers: List of ticker symbols
        allow_crypto: Allow crypto tickers

    Returns:
        List of validated tickers

    Raises:
        ValidationError: If any ticker is invalid
    """
    if not isinstance(tickers, list):
        raise ValidationError("Tickers must be a list")

    validated = []
    for ticker in tickers:
        try:
            validated.append(validate_ticker(ticker, allow_crypto))
        except ValidationError as e:
            logger.warning(f"Invalid ticker skipped: {ticker} - {e}")
            # Continue validation, skip invalid ones
            continue

    if not validated:
        raise ValidationError("No valid tickers provided")

    return validated


def validate_api_key(api_key: str, name: str, min_length: int = 10) -> str:
    """
    Validate API key format.

    Args:
        api_key: API key to validate
        name: Name of the API (for error messages)
        min_length: Minimum key length

    Returns:
        Validated API key

    Raises:
        ValidationError: If API key is invalid
    """
    if not api_key or not isinstance(api_key, str):
        raise ValidationError(f"{name} API key must be a non-empty string")

    api_key = api_key.strip()

    # Check for placeholder values
    placeholder_values = [
        'your_key_here',
        'your_api_key',
        'replace_me',
        'your_token',
        'your_secret',
        'xxx',
        'yyy',
        'zzz'
    ]

    if api_key.lower() in placeholder_values:
        raise ValidationError(
            f"{name} API key not configured. "
            f"Please set a valid key in .env file."
        )

    # Check minimum length
    if len(api_key) < min_length:
        raise ValidationError(
            f"{name} API key too short (minimum {min_length} characters)"
        )

    # Check for suspicious patterns
    if api_key.count(' ') > 2:
        raise ValidationError(f"{name} API key format appears invalid (too many spaces)")

    return api_key


def mask_secret(secret: str, visible_chars: int = 4) -> str:
    """
    Mask secret for logging.

    Args:
        secret: Secret string to mask
        visible_chars: Number of characters to show at start/end

    Returns:
        Masked string

    Examples:
        >>> mask_secret("abcdefghijklmnop")
        'abcd****mnop'
        >>> mask_secret("short")
        '****'
    """
    if not secret or not isinstance(secret, str):
        return "****"

    if len(secret) <= visible_chars * 2:
        return "****"

    return (
        secret[:visible_chars] +
        "****" +
        secret[-visible_chars:]
    )


def validate_email(email: str) -> str:
    """
    Validate email address format.

    Args:
        email: Email address

    Returns:
        Validated email

    Raises:
        ValidationError: If email format is invalid
    """
    if not email or not isinstance(email, str):
        raise ValidationError("Email must be a non-empty string")

    email = email.strip().lower()

    # Simple email pattern
    pattern = r'^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$'

    if not re.match(pattern, email):
        raise ValidationError(f"Invalid email format: '{email}'")

    return email


def sanitize_query(query: str, max_length: int = 200) -> str:
    """
    Sanitize search query to prevent injection.

    Args:
        query: Search query string
        max_length: Maximum query length

    Returns:
        Sanitized query

    Raises:
        ValidationError: If query is invalid
    """
    if not query or not isinstance(query, str):
        raise ValidationError("Query must be a non-empty string")

    query = query.strip()

    # Check length
    if len(query) > max_length:
        raise ValidationError(f"Query too long (max {max_length} characters)")

    # Remove potentially dangerous characters
    # Allow: letters, numbers, spaces, basic punctuation
    allowed_pattern = r'[^a-zA-Z0-9\s\-_.,!?@#$%]'
    sanitized = re.sub(allowed_pattern, '', query)

    # Remove multiple consecutive spaces
    sanitized = re.sub(r'\s+', ' ', sanitized).strip()

    if not sanitized:
        raise ValidationError("Query contains no valid characters")

    return sanitized


if __name__ == '__main__':
    # Test validation functions
    print("="*80)
    print("🔒 Input Validation Tests")
    print("="*80)
    print()

    # Test ticker validation
    print("Testing ticker validation:")
    test_tickers = ['AAPL', 'TSLA', 'BTC.X', 'invalid!', '  NVDA  ', 'abc']
    for ticker in test_tickers:
        try:
            result = validate_ticker(ticker)
            print(f"  ✓ '{ticker}' -> '{result}'")
        except ValidationError as e:
            print(f"  ✗ '{ticker}' -> {e}")

    print()

    # Test API key validation
    print("Testing API key validation:")
    test_keys = ['valid_api_key_123', 'your_key_here', 'short', 'a' * 50]
    for key in test_keys:
        try:
            validate_api_key(key, 'Test')
            print(f"  ✓ '{mask_secret(key)}' -> Valid")
        except ValidationError as e:
            print(f"  ✗ '{mask_secret(key)}' -> {e}")

    print()

    # Test secret masking
    print("Testing secret masking:")
    secrets = ['abcdefghijklmnop', 'short', 'my_long_api_key_12345']
    for secret in secrets:
        masked = mask_secret(secret)
        print(f"  '{secret}' -> '{masked}'")

    print()
    print("="*80)
