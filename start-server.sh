#!/usr/bin/env bash
# Start the web server (backend API + the web app) from a source checkout.
#
# Needs uv (https://docs.astral.sh/uv/) and Node 20+. For a no-install
# start, use Docker instead: docker compose up -d
#
# Usage:            ./start-server.sh
# Then open:        http://localhost:8000
# Stop it with:     Ctrl+C
#
# The web app is always rebuilt first (a few seconds), so the server
# never serves an out-of-date build. If the build fails, the server
# does not start.

set -euo pipefail
cd "$(dirname "$0")"

echo "Building the web app..."
(cd web && npm install --no-audit --no-fund --silent && npm run build --silent)

echo "Starting the server..."
uv run server.py
