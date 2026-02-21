#!/bin/bash

# =============================================================================
# Daily Scholar - Start Script
# =============================================================================
# Launches both the backend API and frontend in a single command.
# Press Ctrl+C to stop both services.
#
# Usage:
#   ./start.sh
# =============================================================================

# TODO: Add auto-open browser on startup (platform-aware: open on macOS,
#       xdg-open on Linux). For now, the URL is printed to the terminal.

# =============================================================================
# Colors and formatting
# =============================================================================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

print_pass() {
    echo -e "  ${GREEN}✓${NC} $1"
}

print_fail() {
    echo -e "  ${RED}✗${NC} $1"
}

print_warn() {
    echo -e "  ${YELLOW}!${NC} $1"
}

print_info() {
    echo -e "  ${BLUE}→${NC} $1"
}

# =============================================================================
# Step 1: Verify we're in the right directory
# =============================================================================
check_project_directory() {
    if [[ ! -f "requirements.txt" || ! -d "backend" || ! -d "frontend" ]]; then
        print_fail "Not in the Daily Scholar project directory"
        echo ""
        echo "  Please run this script from the project root:"
        echo "    cd /path/to/daily-scholar"
        echo "    ./start.sh"
        echo ""
        exit 1
    fi
}

# =============================================================================
# Step 2: Verify setup has been completed
# =============================================================================
check_setup_complete() {
    local missing=0

    if [[ ! -d "venv" ]]; then
        print_fail "Python virtual environment not found"
        missing=1
    fi

    if [[ ! -d "frontend/node_modules" ]]; then
        print_fail "Frontend dependencies not installed"
        missing=1
    fi

    if [[ ! -f ".env" ]]; then
        print_fail ".env file not found"
        missing=1
    fi

    if [[ $missing -eq 1 ]]; then
        echo ""
        print_info "Please run setup first:"
        echo ""
        echo "    ./setup.sh"
        echo ""
        exit 1
    fi
}

# =============================================================================
# Step 3: Check for port conflicts
# =============================================================================
check_ports() {
    local conflict=0

    if lsof -i :8000 &> /dev/null; then
        print_warn "Port 8000 is already in use (backend)"
        conflict=1
    fi

    if lsof -i :3000 &> /dev/null; then
        print_warn "Port 3000 is already in use (frontend)"
        conflict=1
    fi

    if [[ $conflict -eq 1 ]]; then
        echo ""
        print_info "Daily Scholar may already be running, or another service is using these ports"
        read -p "  Continue anyway? (y/n): " continue_anyway
        echo ""

        if [[ "$continue_anyway" != "y" && "$continue_anyway" != "Y" ]]; then
            print_info "To find what's using a port: lsof -i :8000"
            print_info "To kill a process on a port: kill \$(lsof -t -i :8000)"
            exit 0
        fi
    fi
}

# =============================================================================
# Step 4: Cleanup handler — runs when user hits Ctrl+C
# =============================================================================
BACKEND_PID=""

cleanup() {
    echo ""
    echo ""
    print_info "Shutting down Daily Scholar..."

    # Kill the backend process if it's running
    if [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" 2>/dev/null; then
        kill "$BACKEND_PID" 2>/dev/null
        wait "$BACKEND_PID" 2>/dev/null
        print_pass "Backend stopped"
    fi

    print_pass "Frontend stopped"
    echo ""
    print_info "Daily Scholar has been shut down. See you next time! 👋"
    echo ""
    exit 0
}

# Register the cleanup function to run on Ctrl+C (SIGINT) and terminal close (SIGTERM)
trap cleanup SIGINT SIGTERM

# =============================================================================
# Step 5: Start the backend
# =============================================================================
start_backend() {
    print_info "Starting backend API server..."

    # Activate venv and start uvicorn in the background
    source venv/bin/activate
    uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000 &
    BACKEND_PID=$!

    # Wait for backend to be ready (poll the health endpoint)
    local retries=0
    local max_retries=30

    while [[ $retries -lt $max_retries ]]; do
        if curl -s http://127.0.0.1:8000/health &> /dev/null; then
            print_pass "Backend running on http://127.0.0.1:8000"
            return 0
        fi
        sleep 1
        retries=$((retries + 1))
    done

    print_fail "Backend failed to start within ${max_retries} seconds"
    print_info "Check for errors above or try running manually:"
    echo "    source venv/bin/activate && uvicorn backend.main:app --reload"
    cleanup
    exit 1
}

# =============================================================================
# Step 6: Start the frontend
# =============================================================================
start_frontend() {
    print_info "Starting frontend dev server..."
    echo ""

    cd frontend
    npm run dev &
    FRONTEND_PID=$!
    cd ..

    # Give the frontend a moment to compile
    sleep 3

    print_pass "Frontend running on http://localhost:3000"
}

# =============================================================================
# Main
# =============================================================================
main() {
    echo ""
    echo -e "${BOLD}🎓 Daily Scholar${NC}"
    echo ""

    check_project_directory
    check_setup_complete
    check_ports
    start_backend
    start_frontend

    echo ""
    echo -e "  ${GREEN}${BOLD}============================================${NC}"
    echo -e "  ${GREEN}${BOLD}  Daily Scholar is running!${NC}"
    echo -e "  ${GREEN}${BOLD}============================================${NC}"
    echo ""
    echo "  Open in your browser:"
    echo ""
    echo -e "    ${BOLD}http://localhost:3000${NC}"
    echo ""
    echo "  API docs available at:"
    echo ""
    echo -e "    ${BOLD}http://localhost:8000/docs${NC}"
    echo ""
    echo -e "  Press ${BOLD}Ctrl+C${NC} to stop"
    echo ""

    # Wait for the background processes — this keeps the script alive
    # so the trap can catch Ctrl+C
    wait
}

main "$@"
