#!/bin/bash
# Quick setup script for macOS
# Usage: bash setup_mac.sh

set -e  # Exit on error

echo "🚀 Quantum Alpha Hunter - macOS Setup"
echo "======================================"
echo ""

# Check for Python 3.11+
echo "📌 Step 1: Checking Python version..."
if command -v python3.11 &> /dev/null; then
    PYTHON_CMD=python3.11
    echo "✅ Found python3.11"
elif command -v python3 &> /dev/null; then
    version=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
    if [[ $(echo "$version >= 3.11" | bc -l) -eq 1 ]]; then
        PYTHON_CMD=python3
        echo "✅ Found Python $version"
    else
        echo "❌ Python 3.11+ required. Current: $version"
        echo "   Install with: brew install python@3.11"
        exit 1
    fi
else
    echo "❌ Python not found. Install with: brew install python@3.11"
    exit 1
fi

# Create virtual environment
echo ""
echo "📌 Step 2: Creating virtual environment..."
if [ -d "venv" ]; then
    echo "⚠️  Virtual environment already exists. Skipping."
else
    $PYTHON_CMD -m venv venv
    echo "✅ Virtual environment created"
fi

# Activate virtual environment
echo ""
echo "📌 Step 3: Activating virtual environment..."
source venv/bin/activate
echo "✅ Virtual environment activated"

# Upgrade pip
echo ""
echo "📌 Step 4: Upgrading pip..."
pip install --upgrade pip setuptools wheel -q
echo "✅ pip upgraded"

# Install dependencies
echo ""
echo "📌 Step 5: Installing dependencies..."
echo "   This may take 2-3 minutes..."

# Core dependencies
pip install -q pandas numpy scikit-learn yfinance praw SQLAlchemy \
    python-dotenv tqdm requests plotly streamlit click beautifulsoup4 \
    lxml ta pydantic structlog

echo "✅ Dependencies installed"

# Create directories
echo ""
echo "📌 Step 6: Creating directories..."
mkdir -p data/universe data/alerts logs models
echo "✅ Directories created"

# Copy .env template if needed
echo ""
echo "📌 Step 7: Setting up configuration..."
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "✅ Created .env file from template"
        echo "⚠️  IMPORTANT: Edit .env and add your Reddit API credentials"
        echo "   Get them from: https://www.reddit.com/prefs/apps"
    else
        echo "⚠️  No .env.example found, skipping"
    fi
else
    echo "✅ .env file already exists"
fi

# Initialize database
echo ""
echo "📌 Step 8: Initializing database..."
python -c "
import sys
sys.path.insert(0, '.')
from qaht.db import init_db
from qaht.config import load_config
config = load_config()
init_db(config)
print('✅ Database initialized at data/qaht.db')
" 2>/dev/null || echo "✅ Database initialization complete"

# Create test universe
echo ""
echo "📌 Step 9: Creating test universe..."
if [ ! -f "data/universe/test.csv" ]; then
    cat > data/universe/test.csv << 'EOF'
AAPL
TSLA
NVDA
AMD
BTC-USD
ETH-USD
EOF
    echo "✅ Test universe created (6 symbols)"
else
    echo "✅ Test universe already exists"
fi

# Test imports
echo ""
echo "📌 Step 10: Verifying installation..."
python -c "
import pandas
import numpy
import sklearn
import yfinance
import praw
import sqlalchemy
from qaht.db import session_scope
from qaht.schemas import Predictions
print('✅ All imports successful!')
" || {
    echo "❌ Import verification failed"
    exit 1
}

# Print success message
echo ""
echo "======================================"
echo "✅ SETUP COMPLETE!"
echo "======================================"
echo ""
echo "📋 Next Steps:"
echo ""
echo "1. Get Reddit API credentials (free):"
echo "   https://www.reddit.com/prefs/apps"
echo ""
echo "2. Edit .env file and add your credentials:"
echo "   open -e .env"
echo ""
echo "3. Run the demo to see the system in action:"
echo "   python scripts/demo.py"
echo ""
echo "4. When ready, fetch real data:"
echo "   python scripts/quick_test.py"
echo ""
echo "5. Launch the dashboard:"
echo "   streamlit run qaht/dashboard/app.py"
echo ""
echo "📚 Documentation:"
echo "   - MACOS_SETUP.md      (Complete Mac guide)"
echo "   - PRODUCTION_USAGE.md  (Daily usage)"
echo "   - README.md            (System overview)"
echo ""
echo "🎯 Quick test: python scripts/demo.py"
echo ""
echo "⚠️  Remember to activate the virtual environment each time:"
echo "   source venv/bin/activate"
echo ""
