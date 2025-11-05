# Makefile for Quantum Alpha Hunter
# Makes common tasks SUPER EASY with one command

.PHONY: help install scan-crypto scan-stocks scan-all dashboard automate test clean

# Default target
help:
	@echo "════════════════════════════════════════════════════════════════════════════════"
	@echo "🚀 Quantum Alpha Hunter - Quick Commands"
	@echo "════════════════════════════════════════════════════════════════════════════════"
	@echo ""
	@echo "📦 Setup:"
	@echo "  make install          Install dependencies and setup"
	@echo ""
	@echo "🔍 Scanning:"
	@echo "  make scan-crypto      Scan cryptocurrencies"
	@echo "  make scan-stocks      Scan stocks for agile movers"
	@echo "  make scan-all         Scan everything"
	@echo "  make scan-crypto-fresh  Force refresh crypto data"
	@echo ""
	@echo "🌐 Dashboard:"
	@echo "  make dashboard        Start web dashboard on :8000"
	@echo ""
	@echo "⚙️  Automation:"
	@echo "  make automate         Setup automated scanning"
	@echo "  make schedule         Show cron schedule"
	@echo ""
	@echo "🧪 Testing:"
	@echo "  make test             Run all tests"
	@echo "  make test-crypto      Test crypto APIs"
	@echo ""
	@echo "🧹 Maintenance:"
	@echo "  make clean            Clean cache and logs"
	@echo "  make clean-cache      Clean only cache"
	@echo ""
	@echo "════════════════════════════════════════════════════════════════════════════════"

# Installation
install:
	@echo "🚀 Installing Quantum Alpha Hunter..."
	@chmod +x install.sh
	@./install.sh

# Scanning
scan-crypto:
	@python3 qaht-cli.py scan crypto

scan-stocks:
	@python3 qaht-cli.py scan stocks

scan-all:
	@python3 qaht-cli.py scan all

scan-crypto-fresh:
	@python3 qaht-cli.py scan crypto --force-refresh

scan-stocks-fresh:
	@python3 qaht-cli.py scan stocks --force-refresh

# Dashboard
dashboard:
	@python3 qaht-cli.py dashboard

dashboard-custom:
	@python3 qaht-cli.py dashboard --port $(PORT)

# Automation
automate:
	@python3 qaht-cli.py automate --interval 1h

automate-15m:
	@python3 qaht-cli.py automate --interval 15m

automate-hourly:
	@python3 qaht-cli.py automate --interval 1h

automate-daily:
	@python3 qaht-cli.py automate --interval daily

schedule:
	@python3 qaht-cli.py schedule

# Testing
test:
	@echo "🧪 Running tests..."
	@python3 -m pytest tests/ -v

test-crypto:
	@echo "🧪 Testing crypto APIs..."
	@python3 qaht/data_sources/free_crypto_api.py

test-optimizations:
	@echo "🧪 Testing production optimizations..."
	@python3 -c "from qaht.core.production_optimizations import *; print('✅ All optimizations imported successfully')"

# Cleaning
clean:
	@echo "🧹 Cleaning cache and logs..."
	@rm -rf data/cache/*
	@rm -rf logs/*
	@rm -rf __pycache__
	@rm -rf */__pycache__
	@rm -rf */*/__pycache__
	@find . -name "*.pyc" -delete
	@echo "✅ Clean complete"

clean-cache:
	@echo "🧹 Cleaning cache..."
	@rm -rf data/cache/*
	@echo "✅ Cache cleaned"

clean-logs:
	@echo "🧹 Cleaning logs..."
	@rm -rf logs/*
	@echo "✅ Logs cleaned"

# Quick run (interactive)
run:
	@chmod +x run.sh
	@./run.sh

# Development
dev-install:
	@pip3 install -e .
	@pip3 install pytest pytest-cov black flake8

format:
	@echo "🎨 Formatting code..."
	@black qaht/ scripts/ dashboard/

lint:
	@echo "🔍 Linting code..."
	@flake8 qaht/ scripts/ dashboard/ --max-line-length=120

# Status
status:
	@echo "📊 System Status:"
	@echo ""
	@echo "Python: $(shell python3 --version)"
	@echo "Cache: $(shell du -sh data/cache 2>/dev/null || echo '0')"
	@echo "Logs: $(shell du -sh logs 2>/dev/null || echo '0')"
	@echo ""
	@python3 qaht-cli.py schedule
