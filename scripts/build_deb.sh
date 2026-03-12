#!/usr/bin/env bash
# build_deb.sh — Builds the realharmonium .deb package
# Run from the project root: bash scripts/build_deb.sh

set -e

BOLD="\033[1m"; RESET="\033[0m"; GOLD="\033[33m"

echo -e "${GOLD}${BOLD}Building realharmonium .deb…${RESET}"

# ── Check build deps ──────────────────────────────────────────────────────────
MISSING=()
for pkg in debhelper dh-python python3-all python3-setuptools; do
    dpkg -s "$pkg" &>/dev/null || MISSING+=("$pkg")
done

if [ ${#MISSING[@]} -gt 0 ]; then
    echo "Installing build dependencies: ${MISSING[*]}"
    sudo apt-get install -y "${MISSING[@]}"
fi

# ── Build ─────────────────────────────────────────────────────────────────────
cd "$(dirname "$0")/.."
dpkg-buildpackage -us -uc -b

echo -e "\n${GOLD}${BOLD}Built! Find your .deb in the parent directory.${RESET}"
echo "Install with:  sudo dpkg -i ../realharmonium_*.deb"
echo "               sudo apt-get install -f  (fix any missing deps)"

# ── PPA instructions ──────────────────────────────────────────────────────────
cat << 'PPAEOF'

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  To publish on Launchpad PPA so users can
  sudo apt install realharmonium:

  1. Create account: https://launchpad.net
  2. Create PPA: https://launchpad.net/~YOU/+activate-ppa
  3. Sign source package:
       dpkg-buildpackage -S -sa
  4. Upload:
       dput ppa:YOU/realharmonium ../realharmonium_1.0.0-1_source.changes
  5. Users then run:
       sudo add-apt-repository ppa:YOU/realharmonium
       sudo apt update
       sudo apt install realharmonium
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PPAEOF
