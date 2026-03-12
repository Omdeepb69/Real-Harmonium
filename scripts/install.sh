#!/usr/bin/env bash
# install.sh — Quick install for realharmonium (without building .deb)
# Usage: curl -fsSL https://realharmonium.dev/install.sh | bash
#    OR: bash install.sh

set -e

BOLD="\033[1m"
GOLD="\033[33m"
DIM="\033[2m"
RESET="\033[0m"

echo -e "${GOLD}${BOLD}"
cat << 'EOF'
  ╔══════════════════════════════════════╗
  ║      r e a l h a r m o n i u m      ║
  ║    tilt-controlled terminal音楽     ║
  ╚══════════════════════════════════════╝
EOF
echo -e "${RESET}"

# ── Detect Python ────────────────────────────────────────────────────────────
PYTHON=$(command -v python3 || command -v python || "")
if [ -z "$PYTHON" ]; then
    echo "Python 3.10+ is required. Install with: sudo apt install python3"
    exit 1
fi

PY_VER=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo -e "${DIM}Using Python $PY_VER${RESET}"

# ── Install system deps ───────────────────────────────────────────────────────
echo -e "\n${BOLD}Installing system packages…${RESET}"
if command -v apt-get &>/dev/null; then
    sudo apt-get install -y python3-numpy python3-pygame libsdl2-mixer-2.0-0 2>/dev/null || true
fi

# ── pip install ───────────────────────────────────────────────────────────────
echo -e "\n${BOLD}Installing realharmonium…${RESET}"
pip3 install --user realharmonium 2>/dev/null || \
    $PYTHON -m pip install --user realharmonium

# ── PATH check ───────────────────────────────────────────────────────────────
USERBIN="$HOME/.local/bin"
if [[ ":$PATH:" != *":$USERBIN:"* ]]; then
    echo -e "\n${GOLD}Add to your ~/.bashrc or ~/.zshrc:${RESET}"
    echo -e "  export PATH=\"\$HOME/.local/bin:\$PATH\""
    echo ""
    echo "  Then restart your terminal or run: source ~/.bashrc"
else
    echo -e "\n${GOLD}${BOLD}Done! Run:  realhm${RESET}\n"
fi
