#!/bin/bash

# =============================================================================
# Daily Scholar - Setup Script
# =============================================================================
# This script checks prerequisites, sets up the environment, and gets
# Daily Scholar ready to run.
#
# Usage:
#   chmod +x setup.sh
#   ./setup.sh
# =============================================================================

set -e  # Exit on any error (we'll handle errors ourselves where needed)

# =============================================================================
# Colors and formatting
# =============================================================================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'  # No Color

# =============================================================================
# Helper functions
# =============================================================================
print_header() {
    echo ""
    echo -e "${BOLD}============================================${NC}"
    echo -e "${BOLD}  $1${NC}"
    echo -e "${BOLD}============================================${NC}"
    echo ""
}

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
    print_header "Checking Project Directory"

    if [[ -f "requirements.txt" && -d "backend" && -d "frontend" && -d "config" ]]; then
        print_pass "Running from Daily Scholar project root"
    else
        print_fail "Not in the Daily Scholar project directory"
        echo ""
        echo "  Please run this script from the project root:"
        echo ""
        echo "    cd /path/to/daily-scholar"
        echo "    ./setup.sh"
        echo ""
        exit 1
    fi
}

# =============================================================================
# Step 2: Detect platform
# =============================================================================
detect_platform() {
    case "$(uname -s)" in
        Darwin*)  PLATFORM="macos" ;;
        Linux*)   PLATFORM="linux" ;;
        MINGW*|MSYS*|CYGWIN*)  PLATFORM="windows" ;;
        *)        PLATFORM="unknown" ;;
    esac
}

# Returns a platform-specific install suggestion for a given tool
install_hint() {
    local tool="$1"

    case "$tool" in
        python)
            case "$PLATFORM" in
                macos)   echo "brew install python@3.11" ;;
                linux)   echo "sudo apt install python3 python3-venv python3-pip" ;;
                *)       echo "Download from https://www.python.org/downloads/" ;;
            esac
            ;;
        node)
            case "$PLATFORM" in
                macos)   echo "brew install node@18" ;;
                linux)   echo "See https://nodejs.org/ or use: curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash - && sudo apt install -y nodejs" ;;
                *)       echo "Download from https://nodejs.org/" ;;
            esac
            ;;
        git)
            case "$PLATFORM" in
                macos)   echo "brew install git  (or install Xcode Command Line Tools: xcode-select --install)" ;;
                linux)   echo "sudo apt install git" ;;
                *)       echo "Download from https://git-scm.com/" ;;
            esac
            ;;
    esac
}

# =============================================================================
# Step 3: Check prerequisites
# =============================================================================
check_prerequisites() {
    print_header "Checking Prerequisites"

    local errors=0

    # --- Python ---
    PYTHON_CMD=""
    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
    elif command -v python &> /dev/null; then
        # Make sure it's Python 3, not Python 2
        if python --version 2>&1 | grep -q "Python 3"; then
            PYTHON_CMD="python"
        fi
    fi

    if [[ -n "$PYTHON_CMD" ]]; then
        PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | awk '{print $2}')
        PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
        PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

        if [[ "$PYTHON_MAJOR" -ge 3 && "$PYTHON_MINOR" -ge 9 ]]; then
            print_pass "Python $PYTHON_VERSION (using: $PYTHON_CMD)"
        else
            print_fail "Python $PYTHON_VERSION found, but 3.9+ is required"
            print_info "Upgrade: $(install_hint python)"
            errors=$((errors + 1))
        fi
    else
        print_fail "Python 3 not found"
        print_info "Install: $(install_hint python)"
        errors=$((errors + 1))
    fi

    # --- Node.js ---
    if command -v node &> /dev/null; then
        NODE_VERSION=$(node --version | sed 's/v//')
        NODE_MAJOR=$(echo "$NODE_VERSION" | cut -d. -f1)

        if [[ "$NODE_MAJOR" -ge 18 ]]; then
            print_pass "Node.js v$NODE_VERSION"
        else
            print_fail "Node.js v$NODE_VERSION found, but v18+ is required"
            print_info "Upgrade: $(install_hint node)"
            errors=$((errors + 1))
        fi
    else
        print_fail "Node.js not found"
        print_info "Install: $(install_hint node)"
        errors=$((errors + 1))
    fi

    # --- npm (comes with Node, but verify) ---
    if command -v npm &> /dev/null; then
        NPM_VERSION=$(npm --version)
        print_pass "npm v$NPM_VERSION"
    else
        print_fail "npm not found"
        print_info "npm is included with Node.js — install Node.js first"
        errors=$((errors + 1))
    fi

    # --- git ---
    if command -v git &> /dev/null; then
        GIT_VERSION=$(git --version | awk '{print $3}')
        print_pass "git $GIT_VERSION"
    else
        print_fail "git not found"
        print_info "Install: $(install_hint git)"
        errors=$((errors + 1))
    fi

    # --- Summary ---
    echo ""
    if [[ $errors -gt 0 ]]; then
        echo -e "  ${RED}${BOLD}$errors prerequisite(s) missing or outdated.${NC}"
        echo "  Please install/upgrade the tools above and re-run this script."
        exit 1
    else
        print_pass "${BOLD}All prerequisites met!${NC}"
    fi
}

# =============================================================================
# Main
# =============================================================================
main() {
    echo ""
    echo -e "${BOLD}🎓 Daily Scholar Setup${NC}"
    echo ""

    detect_platform
    check_project_directory
    check_prerequisites

    # Future steps will go here:
    # - Python virtual environment setup
    # - Interactive .env configuration
    # - Install Python dependencies
    # - Install frontend dependencies
    # - Initialize database

    print_header "Setup Complete"
    echo -e "  ${GREEN}${BOLD}Prerequisites check passed!${NC}"
    echo ""
    echo "  Next steps (coming soon in setup automation):"
    echo "    1. Set up Python virtual environment"
    echo "    2. Configure API keys"
    echo "    3. Install dependencies"
    echo "    4. Initialize database"
    echo ""
}

main "$@"
