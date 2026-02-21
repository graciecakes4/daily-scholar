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
# Step 4: Configure environment variables
# =============================================================================
# TODO: Add support for alternative LLM providers (OpenAI, Google Gemini, local
#       models via Ollama, etc.) so users can choose their preferred provider
#       during setup. This would involve:
#       - Prompting the user to select an LLM provider
#       - Accepting the appropriate API key for that provider
#       - Writing the correct env vars (e.g., OPENAI_API_KEY, GOOGLE_API_KEY)
#       - Backend changes to support multiple providers
#       See GitHub Issue #XX for discussion.
# =============================================================================
configure_env() {
    print_header "Configuring Environment"

    # --- Check if .env already exists ---
    if [[ -f ".env" ]]; then
        print_warn ".env file already exists"
        echo ""
        read -p "  Do you want to reconfigure it? (y/n): " reconfigure
        echo ""

        if [[ "$reconfigure" != "y" && "$reconfigure" != "Y" ]]; then
            print_info "Keeping existing .env configuration"
            return 0
        fi
    fi

    # --- Copy template ---
    if [[ -f ".env.example" ]]; then
        cp .env.example .env
        print_pass "Created .env from template"
    else
        print_fail ".env.example not found — cannot create .env"
        exit 1
    fi

    # --- Anthropic API Key (required) ---
    echo ""
    echo -e "  ${BOLD}Anthropic API Key (required)${NC}"
    echo "  This is needed for AI-powered content generation."
    echo "  Get your key at: https://console.anthropic.com/"
    echo ""

    while true; do
        read -s -p "  Paste your Anthropic API key: " api_key
        echo ""

        # Check not empty
        if [[ -z "$api_key" ]]; then
            print_fail "API key cannot be empty"
            continue
        fi

        # Check format (Anthropic keys start with sk-ant-)
        if [[ ! "$api_key" =~ ^sk-ant- ]]; then
            print_warn "Key doesn't start with 'sk-ant-' — this may not be a valid Anthropic key"
            read -p "  Use it anyway? (y/n): " use_anyway
            if [[ "$use_anyway" != "y" && "$use_anyway" != "Y" ]]; then
                continue
            fi
        fi

        # Show masked version for confirmation
        local masked="${api_key:0:7}****${api_key: -4}"
        echo ""
        print_info "Key: $masked"
        read -p "  Does this look correct? (y/n): " confirm

        if [[ "$confirm" == "y" || "$confirm" == "Y" ]]; then
            break
        fi
    done

    # Write to .env (replace the placeholder line)
    if [[ "$PLATFORM" == "macos" ]]; then
        sed -i '' "s|ANTHROPIC_API_KEY=.*|ANTHROPIC_API_KEY=$api_key|" .env
    else
        sed -i "s|ANTHROPIC_API_KEY=.*|ANTHROPIC_API_KEY=$api_key|" .env
    fi
    print_pass "Anthropic API key saved"

    # --- Semantic Scholar API Key (optional) ---
    echo ""
    echo -e "  ${BOLD}Semantic Scholar API Key (optional)${NC}"
    echo "  Enhances paper discovery. Free tier works without a key."
    echo "  Get one at: https://www.semanticscholar.org/product/api"
    echo ""
    read -p "  Do you have a Semantic Scholar API key? (y/n): " has_ss_key

    if [[ "$has_ss_key" == "y" || "$has_ss_key" == "Y" ]]; then
        read -s -p "  Paste your Semantic Scholar API key: " ss_key
        echo ""

        if [[ -n "$ss_key" ]]; then
            if [[ "$PLATFORM" == "macos" ]]; then
                sed -i '' "s|SEMANTIC_SCHOLAR_API_KEY=.*|SEMANTIC_SCHOLAR_API_KEY=$ss_key|" .env
            else
                sed -i "s|SEMANTIC_SCHOLAR_API_KEY=.*|SEMANTIC_SCHOLAR_API_KEY=$ss_key|" .env
            fi
            print_pass "Semantic Scholar API key saved"
        fi
    else
        print_info "Skipped — you can add this later in .env"
    fi

    # --- CORE API Key (optional) ---
    echo ""
    echo -e "  ${BOLD}CORE API Key (optional)${NC}"
    echo "  Provides access to a broader range of research papers."
    echo "  Get one at: https://core.ac.uk/services/api"
    echo ""
    read -p "  Do you have a CORE API key? (y/n): " has_core_key

    if [[ "$has_core_key" == "y" || "$has_core_key" == "Y" ]]; then
        read -s -p "  Paste your CORE API key: " core_key
        echo ""

        if [[ -n "$core_key" ]]; then
            if [[ "$PLATFORM" == "macos" ]]; then
                sed -i '' "s|CORE_API_KEY=.*|CORE_API_KEY=$core_key|" .env
            else
                sed -i "s|CORE_API_KEY=.*|CORE_API_KEY=$core_key|" .env
            fi
            print_pass "CORE API key saved"
        fi
    else
        print_info "Skipped — you can add this later in .env"
    fi

    echo ""
    print_pass "${BOLD}Environment configured!${NC}"
    print_info "You can edit .env manually at any time to change these settings"
}

# =============================================================================
# Step 5: Set up Python virtual environment
# =============================================================================
setup_python_env() {
    print_header "Setting Up Python Environment"

    # --- Check if venv already exists ---
    if [[ -d "venv" ]]; then
        print_warn "Virtual environment already exists"
        echo ""
        read -p "  Do you want to recreate it? (y/n): " recreate
        echo ""

        if [[ "$recreate" != "y" && "$recreate" != "Y" ]]; then
            print_info "Keeping existing virtual environment"
        else
            print_info "Removing old virtual environment..."
            rm -rf venv
            print_info "Creating new virtual environment (this may take a moment)..."
            $PYTHON_CMD -m venv venv
            print_pass "Virtual environment created"
        fi
    else
        print_info "Creating virtual environment (this may take a moment)..."
        $PYTHON_CMD -m venv venv
        print_pass "Virtual environment created"
    fi

    # --- Activate the venv ---
    source venv/bin/activate
    print_pass "Virtual environment activated"

    # --- Upgrade pip (avoids warnings during dependency install) ---
    print_info "Upgrading pip..."
    pip install --upgrade pip --quiet
    print_pass "pip upgraded to $(pip --version | awk '{print $2}')"
}

# =============================================================================
# Step 6: Install Python dependencies
# =============================================================================
install_python_deps() {
    print_header "Installing Python Dependencies"

    print_info "Installing packages from requirements.txt..."
    print_info "This may take 1-2 minutes on first run"
    echo ""

    # Run pip install — show output so users can see progress
    if pip install -r requirements.txt; then
        echo ""
        print_pass "Python dependencies installed"
    else
        echo ""
        print_fail "Failed to install Python dependencies"
        print_info "Try running manually: source venv/bin/activate && pip install -r requirements.txt"
        exit 1
    fi
}

# =============================================================================
# Step 7: Install frontend dependencies
# =============================================================================
install_frontend_deps() {
    print_header "Installing Frontend Dependencies"

    print_info "Installing Node.js packages..."
    print_info "This may take 1-2 minutes on first run"
    echo ""

    cd frontend

    if npm install; then
        echo ""
        print_pass "Frontend dependencies installed"
    else
        echo ""
        print_fail "Failed to install frontend dependencies"
        print_info "Try running manually: cd frontend && npm install"
        cd ..
        exit 1
    fi

    cd ..
}

# =============================================================================
# Step 8: Initialize the database
# =============================================================================
initialize_database() {
    print_header "Initializing Database"

    # --- Create required directories ---
    mkdir -p data
    print_pass "Data directory ready"

    mkdir -p uploads/course_materials
    print_pass "Uploads directory ready"

    # --- Run database setup ---
    print_info "Creating database tables..."
    echo ""

    if $PYTHON_CMD scripts/setup_db.py; then
        echo ""
        print_pass "Database initialized"
    else
        echo ""
        print_fail "Database initialization failed"
        print_info "Try running manually: python scripts/setup_db.py"
        exit 1
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
    configure_env
    setup_python_env
    install_python_deps
    install_frontend_deps
    initialize_database

    print_header "🎉 Setup Complete!"
    echo -e "  ${GREEN}${BOLD}Daily Scholar is ready to go!${NC}"
    echo ""
    echo "  To start the application, run:"
    echo ""
    echo "    ./start.sh"
    echo ""
    echo "  Or start manually:"
    echo ""
    echo "    Terminal 1:  source venv/bin/activate && uvicorn backend.main:app --reload"
    echo "    Terminal 2:  cd frontend && npm run dev"
    echo ""
    echo "  Then open http://localhost:3000 in your browser"
    echo ""
}

main "$@"
