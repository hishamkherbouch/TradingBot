#!/usr/bin/env bash
set -euo pipefail

ROOT="/root/.openclaw/workspace/TradingBot"
LOG_DIR="$ROOT/logs"
LOG_FILE="$LOG_DIR/live-cron.log"
LOCK_FILE="/tmp/tradingbot-live.lock"

mkdir -p "$LOG_DIR"
cd "$ROOT"

{
  echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] Starting TradingBot scheduled run"

  if ! flock -n 9; then
    echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] Another TradingBot run is already in progress; skipping"
    exit 0
  fi

  . .venv/bin/activate
  python live.py

  echo "[$(date -u +'%Y-%m-%d %H:%M:%S UTC')] TradingBot scheduled run finished"
} 9>"$LOCK_FILE" >> "$LOG_FILE" 2>&1
