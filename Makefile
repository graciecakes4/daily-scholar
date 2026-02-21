# =============================================================================
# Daily Scholar - Makefile
# =============================================================================
# Simple commands for setting up and running Daily Scholar.
#
# Usage:
#   make help     - Show available commands
#   make setup    - Run first-time setup
#   make start    - Start the application
#   make stop     - Stop all running services
# =============================================================================

.PHONY: help setup start stop

# Default target — runs when user types just `make`
help:
	@echo ""
	@echo "🎓 Daily Scholar"
	@echo ""
	@echo "Available commands:"
	@echo ""
	@echo "  make setup    First-time setup (prerequisites, API keys, dependencies)"
	@echo "  make start    Start the application (backend + frontend)"
	@echo "  make stop     Stop all running services"
	@echo "  make help     Show this help message"
	@echo ""

setup:
	@chmod +x setup.sh
	@./setup.sh

start:
	@chmod +x start.sh
	@./start.sh

stop:
	@echo ""
	@echo "Stopping Daily Scholar..."
	@echo ""
	@if lsof -t -i :8000 > /dev/null 2>&1; then \
		kill $$(lsof -t -i :8000) 2>/dev/null; \
		echo "  ✓ Backend stopped (port 8000)"; \
	else \
		echo "  - Backend not running"; \
	fi
	@if lsof -t -i :3000 > /dev/null 2>&1; then \
		kill $$(lsof -t -i :3000) 2>/dev/null; \
		echo "  ✓ Frontend stopped (port 3000)"; \
	else \
		echo "  - Frontend not running"; \
	fi
	@echo ""
	@echo "  Done!"
	@echo ""
