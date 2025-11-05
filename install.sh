#!/bin/bash
# Installation Script for Quantum Alpha Hunter
# Sets up everything you need in ONE command

set -e  # Exit on error

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "════════════════════════════════════════════════════════════════════════════════"
echo "🚀 Quantum Alpha Hunter - Quick Install"
echo "════════════════════════════════════════════════════════════════════════════════"
echo ""

# Check Python version
echo -e "${BLUE}[1/6]${NC} Checking Python version..."
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python 3 not found. Please install Python 3.8+${NC}"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
echo -e "${GREEN}✓${NC} Python $PYTHON_VERSION found"
echo ""

# Install dependencies
echo -e "${BLUE}[2/6]${NC} Installing Python dependencies..."
if [ -f "requirements.txt" ]; then
    pip3 install -r requirements.txt --quiet
    echo -e "${GREEN}✓${NC} Dependencies installed"
else
    echo -e "${YELLOW}⚠${NC}  No requirements.txt found, skipping..."
fi
echo ""

# Create necessary directories
echo -e "${BLUE}[3/6]${NC} Creating directories..."
mkdir -p data/cache
mkdir -p logs
mkdir -p results
echo -e "${GREEN}✓${NC} Directories created"
echo ""

# Make scripts executable
echo -e "${BLUE}[4/6]${NC} Making scripts executable..."
chmod +x qaht-cli.py
chmod +x run.sh
chmod +x install.sh
echo -e "${GREEN}✓${NC} Scripts are executable"
echo ""

# Create symbolic link for easy CLI access
echo -e "${BLUE}[5/6]${NC} Setting up CLI command..."
if command -v sudo &> /dev/null; then
    read -p "Install 'qaht' command globally? (requires sudo) [y/N]: " install_global
    if [[ $install_global =~ ^[Yy]$ ]]; then
        sudo ln -sf "$PROJECT_DIR/qaht-cli.py" /usr/local/bin/qaht
        echo -e "${GREEN}✓${NC} 'qaht' command installed globally"
        echo "   You can now run: qaht scan crypto"
    else
        echo -e "${YELLOW}⚠${NC}  Skipped global install"
        echo "   Use: python3 qaht-cli.py scan crypto"
    fi
else
    echo -e "${YELLOW}⚠${NC}  sudo not available, skipping global install"
    echo "   Use: python3 qaht-cli.py scan crypto"
fi
echo ""

# Setup API keys
echo -e "${BLUE}[6/6]${NC} API Configuration..."
if [ ! -f ".env" ]; then
    echo "Creating .env file for API keys..."
    cat > .env << 'EOF'
# FREE API Keys (Sign up at links below)

# Alpha Vantage (500 calls/day FREE)
# Sign up: https://www.alphavantage.co/support/#api-key
ALPHA_VANTAGE_API_KEY=your_key_here

# NewsAPI (100 calls/day FREE)
# Sign up: https://newsapi.org/register
NEWS_API_KEY=your_key_here

# Finnhub (60 calls/min FREE)
# Sign up: https://finnhub.io/register
FINNHUB_API_KEY=your_key_here

# Reddit (optional, for social sentiment)
# Create app: https://www.reddit.com/prefs/apps
REDDIT_CLIENT_ID=your_client_id
REDDIT_CLIENT_SECRET=your_secret
REDDIT_USER_AGENT=QuantumAlphaHunter/1.0
EOF
    echo -e "${GREEN}✓${NC} .env file created"
    echo -e "${YELLOW}⚠${NC}  Edit .env and add your FREE API keys"
else
    echo -e "${GREEN}✓${NC} .env file already exists"
fi
echo ""

# Summary
echo "════════════════════════════════════════════════════════════════════════════════"
echo -e "${GREEN}✅ Installation Complete!${NC}"
echo "════════════════════════════════════════════════════════════════════════════════"
echo ""
echo "🎯 Quick Start:"
echo ""
echo "  # Easy way (interactive menu)"
echo "  ./run.sh"
echo ""
echo "  # CLI commands"
if [ -L "/usr/local/bin/qaht" ]; then
    echo "  qaht scan crypto              # Scan cryptocurrencies"
    echo "  qaht scan stocks              # Scan stocks"
    echo "  qaht dashboard                # Start web UI"
    echo "  qaht automate --interval 1h   # Setup automation"
else
    echo "  python3 qaht-cli.py scan crypto              # Scan cryptocurrencies"
    echo "  python3 qaht-cli.py scan stocks              # Scan stocks"
    echo "  python3 qaht-cli.py dashboard                # Start web UI"
    echo "  python3 qaht-cli.py automate --interval 1h   # Setup automation"
fi
echo ""
echo "📚 Next Steps:"
echo ""
echo "  1. Edit .env and add your FREE API keys"
echo "  2. Run: ./run.sh (or use CLI commands above)"
echo "  3. Check docs/PRODUCTION_OPTIMIZATIONS.md for features"
echo ""
echo "════════════════════════════════════════════════════════════════════════════════"
