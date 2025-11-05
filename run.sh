#!/bin/bash
# Quick Start Script for Quantum Alpha Hunter
# Makes running the system SUPER EASY

set -e  # Exit on error

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "════════════════════════════════════════════════════════════════════════════════"
echo "🚀 Quantum Alpha Hunter - Quick Start"
echo "════════════════════════════════════════════════════════════════════════════════"
echo ""

# Show menu
echo "What do you want to run?"
echo ""
echo "  1) Scan Cryptocurrencies (fast)"
echo "  2) Scan Stocks for Agile Movers"
echo "  3) Scan Everything (crypto + stocks)"
echo "  4) Start Dashboard (web UI)"
echo "  5) Setup Automation (cron jobs)"
echo "  6) Run Tests"
echo ""
echo "  q) Quit"
echo ""
read -p "Enter choice [1-6 or q]: " choice

case $choice in
    1)
        echo -e "${GREEN}🪙 Scanning Cryptocurrencies...${NC}"
        echo ""
        python3 qaht-cli.py scan crypto
        ;;
    2)
        echo -e "${GREEN}📈 Scanning Stocks...${NC}"
        echo ""
        python3 qaht-cli.py scan stocks
        ;;
    3)
        echo -e "${GREEN}🚀 Scanning Everything...${NC}"
        echo ""
        python3 qaht-cli.py scan all
        ;;
    4)
        echo -e "${GREEN}🌐 Starting Dashboard...${NC}"
        echo ""
        echo "Dashboard will be available at: http://localhost:8000"
        echo "Press CTRL+C to stop"
        echo ""
        python3 qaht-cli.py dashboard
        ;;
    5)
        echo -e "${GREEN}⚙️  Setting up Automation...${NC}"
        echo ""
        python3 qaht-cli.py automate
        ;;
    6)
        echo -e "${GREEN}🧪 Running Tests...${NC}"
        echo ""
        python3 -m pytest tests/ -v
        ;;
    q|Q)
        echo "Goodbye!"
        exit 0
        ;;
    *)
        echo -e "${YELLOW}Invalid choice${NC}"
        exit 1
        ;;
esac

echo ""
echo "════════════════════════════════════════════════════════════════════════════════"
echo "✅ Done!"
echo "════════════════════════════════════════════════════════════════════════════════"
