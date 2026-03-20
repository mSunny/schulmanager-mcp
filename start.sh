#!/usr/bin/env bash
# Load .env and start the Schulmanager MCP server
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SCRIPT_DIR/.env" ]; then
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
fi
exec "$SCRIPT_DIR/.venv/bin/python" -m schulmanager_mcp.server "$@"
