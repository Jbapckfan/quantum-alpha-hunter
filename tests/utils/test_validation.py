"""
Unit tests for validation utilities
"""
import pytest
from qaht.utils.validation import (
    ValidationError,
    validate_ticker,
    validate_tickers,
    validate_api_key,
    mask_secret,
    validate_email,
    sanitize_query
)


class TestValidateTicker:
    """Tests for ticker validation"""

    def test_valid_stock_tickers(self):
        """Test valid stock ticker formats"""
        assert validate_ticker("AAPL") == "AAPL"
        assert validate_ticker("MSFT") == "MSFT"
        assert validate_ticker("GOOGL") == "GOOGL"
        assert validate_ticker("NVDA") == "NVDA"
        assert validate_ticker("A") == "A"  # Single letter
        assert validate_ticker("ABCDE") == "ABCDE"  # 5 letters

    def test_valid_crypto_tickers(self):
        """Test valid crypto ticker formats"""
        assert validate_ticker("BTC", allow_crypto=True) == "BTC"
        assert validate_ticker("ETH", allow_crypto=True) == "ETH"
        assert validate_ticker("BTC.X", allow_crypto=True) == "BTC.X"
        assert validate_ticker("ETH.X", allow_crypto=True) == "ETH.X"
        assert validate_ticker("DOGE", allow_crypto=True) == "DOGE"
        assert validate_ticker("BTC123", allow_crypto=True) == "BTC123"

    def test_case_normalization(self):
        """Test ticker case normalization"""
        assert validate_ticker("aapl") == "AAPL"
        assert validate_ticker("msft") == "MSFT"
        assert validate_ticker("  NVDA  ") == "NVDA"  # Whitespace stripped
        assert validate_ticker("btc.x", allow_crypto=True) == "BTC.X"

    def test_invalid_empty_ticker(self):
        """Test empty ticker validation"""
        with pytest.raises(ValidationError, match="non-empty string"):
            validate_ticker("")
        with pytest.raises(ValidationError, match="Invalid ticker format"):
            validate_ticker("   ")  # Strips to empty string, fails regex
        with pytest.raises(ValidationError, match="non-empty string"):
            validate_ticker(None)

    def test_invalid_type(self):
        """Test non-string ticker validation"""
        with pytest.raises(ValidationError, match="non-empty string"):
            validate_ticker(123)
        with pytest.raises(ValidationError, match="non-empty string"):
            validate_ticker([])
        with pytest.raises(ValidationError, match="non-empty string"):
            validate_ticker({})

    def test_invalid_format_stock(self):
        """Test invalid stock ticker formats"""
        with pytest.raises(ValidationError, match="Invalid ticker format"):
            validate_ticker("ABCDEF", allow_crypto=False)  # Too long
        with pytest.raises(ValidationError, match="Invalid ticker format"):
            validate_ticker("ABC123", allow_crypto=False)  # Numbers not allowed
        with pytest.raises(ValidationError, match="Invalid ticker format"):
            validate_ticker("ABC.X", allow_crypto=False)  # .X only for crypto

    def test_invalid_format_crypto(self):
        """Test invalid crypto ticker formats"""
        with pytest.raises(ValidationError, match="Invalid ticker format"):
            validate_ticker("ABCDEFGHIJK", allow_crypto=True)  # Too long (>10)
        with pytest.raises(ValidationError, match="Invalid ticker format"):
            validate_ticker("BTC.Y", allow_crypto=True)  # Only .X allowed

    def test_dangerous_characters(self):
        """Test injection attack prevention"""
        # These inputs contain dangerous characters but will fail regex first
        dangerous_inputs = [
            "'; DROP TABLE--",
            "<script>alert(1)</script>",
            "AAPL; rm -rf /",
            "AAPL | cat /etc/passwd",
            "AAPL & whoami",
            "AAPL`ls`",
            "AAPL$(whoami)",
            "AAPL'OR'1'='1",
        ]
        for dangerous in dangerous_inputs:
            # Will raise ValidationError (either "Invalid ticker format" or "dangerous characters")
            with pytest.raises(ValidationError):
                validate_ticker(dangerous)


class TestValidateTickers:
    """Tests for batch ticker validation"""

    def test_valid_batch(self):
        """Test valid batch of tickers"""
        tickers = ["AAPL", "MSFT", "GOOGL"]
        result = validate_tickers(tickers)
        assert result == ["AAPL", "MSFT", "GOOGL"]

    def test_empty_list(self):
        """Test empty ticker list"""
        with pytest.raises(ValidationError, match="No valid tickers"):
            validate_tickers([])

    def test_invalid_type(self):
        """Test non-list input"""
        with pytest.raises(ValidationError, match="must be a list"):
            validate_tickers("AAPL")
        with pytest.raises(ValidationError, match="must be a list"):
            validate_tickers(None)

    def test_batch_with_invalid_ticker(self):
        """Test batch with one invalid ticker - it skips invalid ones"""
        result = validate_tickers(["AAPL", "'; DROP--", "MSFT"])
        assert result == ["AAPL", "MSFT"]  # Invalid ticker is skipped

    def test_case_normalization_batch(self):
        """Test batch case normalization"""
        result = validate_tickers(["aapl", "MSFT", "  nvda  "])
        assert result == ["AAPL", "MSFT", "NVDA"]


class TestValidateApiKey:
    """Tests for API key validation"""

    def test_valid_api_key(self):
        """Test valid API keys"""
        key = "AIzaSyD1234567890abcdefghijk"
        assert validate_api_key(key, "TestAPI") == key

    def test_minimum_length(self):
        """Test minimum length enforcement"""
        with pytest.raises(ValidationError, match="too short"):
            validate_api_key("short", "TestAPI", min_length=10)

        # Should pass with correct length
        assert validate_api_key("1234567890", "TestAPI", min_length=10) == "1234567890"

    def test_placeholder_detection(self):
        """Test placeholder API key detection"""
        placeholders = [
            "your_key_here",
            "YOUR_API_KEY",
            "replace_me",
            "your_token",
            "your_secret",
            "xxx",
            "yyy",
            "zzz",
            "Your_Key_Here",  # Case insensitive
        ]
        for placeholder in placeholders:
            with pytest.raises(ValidationError, match="not configured"):
                validate_api_key(placeholder, "TestAPI")

    def test_empty_api_key(self):
        """Test empty API key"""
        with pytest.raises(ValidationError, match="non-empty string"):
            validate_api_key("", "TestAPI")
        with pytest.raises(ValidationError, match="non-empty string"):
            validate_api_key(None, "TestAPI")

    def test_whitespace_stripping(self):
        """Test whitespace handling"""
        key = "  AIzaSyD1234567890abcdefghijk  "
        result = validate_api_key(key, "TestAPI")
        assert result == "AIzaSyD1234567890abcdefghijk"


class TestMaskSecret:
    """Tests for secret masking"""

    def test_mask_normal_secret(self):
        """Test masking normal length secrets"""
        assert mask_secret("AIzaSyD1234567890abcdefghijk") == "AIza****hijk"
        assert mask_secret("1234567890abcdef") == "1234****cdef"

    def test_mask_short_secret(self):
        """Test masking short secrets"""
        assert mask_secret("short") == "****"
        assert mask_secret("abc") == "****"
        assert mask_secret("12345678") == "****"

    def test_mask_custom_visible_chars(self):
        """Test custom visible characters"""
        assert mask_secret("1234567890", visible_chars=2) == "12****90"
        assert mask_secret("abcdefghij", visible_chars=3) == "abc****hij"

    def test_mask_empty_secret(self):
        """Test masking empty/None secrets"""
        assert mask_secret("") == "****"
        assert mask_secret(None) == "****"

    def test_mask_non_string(self):
        """Test non-string secrets"""
        assert mask_secret(12345) == "****"
        assert mask_secret([]) == "****"


class TestValidateEmail:
    """Tests for email validation"""

    def test_valid_emails(self):
        """Test valid email formats"""
        valid_emails = [
            "user@example.com",
            "test.user@example.com",
            "user+tag@example.co.uk",
            "user123@test-domain.com",
            "a@b.co",
        ]
        for email in valid_emails:
            assert validate_email(email) == email.lower()

    def test_invalid_emails(self):
        """Test invalid email formats"""
        invalid_emails = [
            "not-an-email",
            "@example.com",
            "user@",
            "user @example.com",
            "user@example",
            "",
            None,
        ]
        for email in invalid_emails:
            with pytest.raises(ValidationError):
                validate_email(email)

    def test_case_normalization(self):
        """Test email case normalization"""
        assert validate_email("USER@EXAMPLE.COM") == "user@example.com"
        assert validate_email("Test@Example.Com") == "test@example.com"


class TestSanitizeQuery:
    """Tests for query sanitization"""

    def test_valid_query(self):
        """Test valid queries"""
        assert sanitize_query("AAPL stock") == "AAPL stock"
        assert sanitize_query("Bitcoin price 2024") == "Bitcoin price 2024"
        assert sanitize_query("tech stocks analysis") == "tech stocks analysis"

    def test_dangerous_characters_removed(self):
        """Test dangerous character removal"""
        assert sanitize_query("<script>alert(1)</script>") == "scriptalert1script"
        assert sanitize_query("query; DROP TABLE") == "query DROP TABLE"
        assert sanitize_query("test | rm -rf /") == "test rm -rf"  # | and / removed, space normalized
        assert sanitize_query("test & whoami") == "test whoami"  # & removed, space normalized

    def test_allowed_special_chars(self):
        """Test allowed special characters"""
        query = "AAPL stock-market analysis, up 10%! What's next?"
        result = sanitize_query(query)
        assert "-" in result
        assert "," in result
        assert "%" in result
        assert "!" in result
        assert "?" in result

    def test_whitespace_normalization(self):
        """Test whitespace handling"""
        assert sanitize_query("test    multiple    spaces") == "test multiple spaces"
        assert sanitize_query("  leading spaces") == "leading spaces"
        assert sanitize_query("trailing spaces  ") == "trailing spaces"

    def test_max_length(self):
        """Test length limit"""
        long_query = "a" * 300
        with pytest.raises(ValidationError, match="too long"):
            sanitize_query(long_query, max_length=200)

    def test_empty_query(self):
        """Test empty query"""
        with pytest.raises(ValidationError, match="non-empty string"):
            sanitize_query("")
        with pytest.raises(ValidationError, match="no valid characters"):
            sanitize_query("   ")  # Strips to empty, fails after sanitization

    def test_query_with_only_invalid_chars(self):
        """Test query with only invalid characters"""
        with pytest.raises(ValidationError, match="no valid characters"):
            sanitize_query("<<<>>>")
        with pytest.raises(ValidationError, match="no valid characters"):
            sanitize_query("||||")


# Integration test
class TestValidationIntegration:
    """Integration tests for validation utilities"""

    def test_ticker_to_api_call(self):
        """Test ticker validation in API call scenario"""
        # Simulate API call flow
        user_input = "  aapl  "
        ticker = validate_ticker(user_input)
        assert ticker == "AAPL"

        # Should be safe to use in URL
        url = f"https://api.example.com/quote/{ticker}"
        assert "AAPL" in url

    def test_api_key_validation_flow(self):
        """Test API key validation flow"""
        # Valid key
        key = "AIzaSyD1234567890abcdefghijk"
        validated = validate_api_key(key, "TestAPI")
        masked = mask_secret(validated)
        assert masked == "AIza****hijk"

        # Invalid key (placeholder)
        with pytest.raises(ValidationError):
            validate_api_key("your_key_here", "TestAPI")

    def test_search_query_flow(self):
        """Test search query sanitization flow"""
        user_query = "<script>AAPL</script> stock analysis"
        sanitized = sanitize_query(user_query)
        assert "<script>" not in sanitized
        assert "AAPL" in sanitized
        assert "stock" in sanitized
