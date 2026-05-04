#!/usr/bin/env bash
set -e

echo "[*] Installing Payload Manager..."

# Copy app
mkdir -p ~/.local/bin
cp payload-manager.py ~/.local/bin/payload-manager
chmod +x ~/.local/bin/payload-manager

# Copy desktop entry
mkdir -p ~/.local/share/applications
cp payload-manager.desktop ~/.local/share/applications/payload-manager.desktop

# Create payloads directory
mkdir -p ~/payloads

echo "[+] Done. Run with: payload-manager"
echo "[+] Payloads stored in: ~/payloads/"
