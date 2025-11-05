# Testing Guide

## Overview

The Quantum Alpha Hunter project now has a comprehensive test suite with **171 passing tests** and **11% code coverage**. This guide explains how to run tests, understand coverage, and add new tests.

## Quick Start

### Run All Tests
```bash
# Run all tests with coverage
pytest

# Run tests with verbose output
pytest -v

# Run specific test file
pytest tests/utils/test_validation.py

# Run tests with coverage report
pytest --cov=qaht --cov-report=html
```

### Test Organization

```
tests/
├── utils/
│   ├── test_validation.py      # Input validation tests (75 tests)
│   ├── test_error_handling.py  # Error handling tests (39 tests)
│   └── test_cache.py            # Caching system tests (17 tests)
├── data_sources/
│   ├── test_stocktwits_api.py  # StockTwits API tests
│   ├── test_youtube_api.py     # YouTube API tests
│   └── test_lunarcrush_api.py  # LunarCrush API tests
└── core/
    └── test_production_optimizations.py  # Circuit breaker & rate limiter
```

## Test Categories

### Unit Tests

Fast, isolated tests for individual functions:

```bash
# Run only unit tests
pytest -m unit
```

**Coverage Areas:**
- Input validation (tickers, API keys, emails, queries)
- Error handling decorators
- Safe dictionary access
- Timestamp parsing
- Caching utilities

### Integration Tests

Tests that verify component interactions:

```bash
# Run only integration tests
pytest -m integration
```

**Coverage Areas:**
- API client initialization
- Circuit breaker integration
- Rate limiter integration
- Validation in API workflows
- Cache integration patterns

### Slow Tests

Tests that take longer to run (e.g., with sleep/timeouts):

```bash
# Skip slow tests for quick feedback
pytest -m "not slow"
```

## Coverage Reports

### Terminal Report
```bash
pytest --cov=qaht --cov-report=term-missing
```

Shows coverage with line numbers of missing coverage.

### HTML Report
```bash
pytest --cov=qaht --cov-report=html
open htmlcov/index.html  # View in browser
```

Interactive HTML report with highlighted coverage.

## Current Coverage

### High Coverage Modules (70-100%)

| Module | Coverage | Tests |
|--------|----------|-------|
| `qaht/utils/validation.py` | 72% | 75 |
| `qaht/utils/error_handling.py` | 83% | 39 |
| `qaht/utils/cache.py` | 75% | 17 |
| `qaht/data_sources/lunarcrush_api.py` | 100% | ✓ |
| `qaht/data_sources/youtube_api.py` | 100% | ✓ |
| `qaht/data_sources/stocktwits_api.py` | 74% | ✓ |

### What's Tested

#### ✅ Input Validation
- Ticker format validation (stock & crypto)
- SQL injection prevention
- XSS attack prevention
- Command injection prevention
- API key validation
- Placeholder detection
- Email validation
- Query sanitization

#### ✅ Error Handling
- HTTP status codes (401, 403, 404, 429, 5xx)
- Timeout errors
- Connection errors
- Network failures
- Retry logic with exponential backoff
- Custom exception classes

#### ✅ Caching
- TTL-based expiration
- Cache hit/miss behavior
- Decorator functionality
- Cleanup of expired entries
- Multi-argument caching

#### ✅ API Integration
- Circuit breaker state management
- Rate limiter adaptation
- API response parsing
- Error recovery patterns

## Writing New Tests

### Test File Structure

```python
"""
Description of what this module tests
"""
import pytest
from qaht.module import function_to_test


class TestFeatureName:
    """Test suite for specific feature"""

    def setup_method(self):
        """Setup run before each test"""
        self.test_data = {}

    def teardown_method(self):
        """Cleanup run after each test"""
        pass

    def test_successful_case(self):
        """Test the happy path"""
        result = function_to_test("valid_input")
        assert result == expected_value

    def test_error_case(self):
        """Test error handling"""
        with pytest.raises(ExpectedException):
            function_to_test("invalid_input")
```

### Using Fixtures

```python
@pytest.fixture
def sample_data():
    """Reusable test data"""
    return {"key": "value"}


def test_with_fixture(sample_data):
    """Use fixture in test"""
    assert sample_data["key"] == "value"
```

### Mocking API Calls

```python
def test_api_call(mocker):
    """Test API interaction with mocking"""
    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"data": "test"}

    mocker.patch('requests.get', return_value=mock_response)

    result = api_function()
    assert result["data"] == "test"
```

### Parametrized Tests

```python
@pytest.mark.parametrize("input,expected", [
    ("AAPL", "AAPL"),
    ("aapl", "AAPL"),
    ("  MSFT  ", "MSFT"),
])
def test_multiple_cases(input, expected):
    """Test with multiple input/output pairs"""
    assert validate_ticker(input) == expected
```

## Test Markers

Mark tests for selective running:

```python
@pytest.mark.unit
def test_unit_function():
    """Fast unit test"""
    pass


@pytest.mark.integration
def test_api_integration():
    """Integration test"""
    pass


@pytest.mark.slow
def test_with_sleep():
    """Test that takes time"""
    time.sleep(2)
```

Run specific markers:
```bash
pytest -m unit           # Only unit tests
pytest -m integration    # Only integration tests
pytest -m "not slow"     # Skip slow tests
```

## Continuous Integration

### Pre-commit Checks

Before committing, run:

```bash
# Run tests
pytest

# Check coverage
pytest --cov=qaht --cov-report=term-missing

# Run linter
pylint qaht/

# Type checking
mypy qaht/
```

### CI Pipeline

Recommended CI workflow:

```yaml
- name: Run Tests
  run: pytest --cov=qaht --cov-report=xml

- name: Check Coverage
  run: |
    coverage report --fail-under=10

- name: Upload Coverage
  uses: codecov/codecov-action@v3
```

## Troubleshooting

### Common Issues

#### Tests fail with import errors
```bash
# Install project in editable mode
pip install -e ".[dev]"
```

#### Coverage report not generated
```bash
# Ensure pytest-cov is installed
pip install pytest-cov
```

#### Mocking doesn't work
```bash
# Install pytest-mock
pip install pytest-mock
```

### Debug Mode

Run tests with detailed output:

```bash
# Show print statements
pytest -s

# Show local variables on failure
pytest -l

# Drop into debugger on failure
pytest --pdb
```

## Best Practices

### ✅ Do's

- **Write tests first** (TDD) when possible
- **Test edge cases** (empty, None, invalid input)
- **Test error paths** (exceptions, timeouts)
- **Use descriptive test names** (`test_validates_stock_ticker_format`)
- **Keep tests isolated** (no shared state)
- **Mock external dependencies** (APIs, databases)
- **Assert specific exceptions** (`with pytest.raises(ValidationError)`)

### ❌ Don'ts

- **Don't test implementation details**
- **Don't share state between tests**
- **Don't make real API calls** (use mocks)
- **Don't ignore failing tests**
- **Don't skip writing tests** ("will add later")
- **Don't test third-party libraries**

## Test Coverage Goals

### Current Status
- **Overall Coverage**: 11%
- **Critical Modules**: 70-100%

### Target Coverage
- **Critical Modules** (utils, core): 80%+
- **API Clients**: 70%+
- **Overall Project**: 40%+

### Priority Areas

**High Priority** (target 80%):
- Input validation
- Error handling
- Security functions
- Caching logic
- Circuit breakers

**Medium Priority** (target 60%):
- API clients
- Data parsing
- Configuration

**Low Priority** (target 40%):
- CLI commands
- Dashboard UI
- Visualization

## Resources

- [pytest Documentation](https://docs.pytest.org/)
- [pytest-cov Plugin](https://pytest-cov.readthedocs.io/)
- [pytest-mock Plugin](https://pytest-mock.readthedocs.io/)
- [Python Testing Best Practices](https://docs.python-guide.org/writing/tests/)

## Questions?

If tests are failing or you need help:

1. Check this guide for common issues
2. Review test output carefully
3. Run with `-v` for verbose output
4. Use `--pdb` to debug interactively
5. Check existing tests for patterns

---

**Remember**: Tests are documentation, safety nets, and confidence builders. Write them!
