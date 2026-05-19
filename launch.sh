#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"

# Kill any stale wispr instance holding port 7842
lsof -ti :7842 | xargs kill -9 2>/dev/null

exec "$DIR/venv/bin/python" "$DIR/app.py"
