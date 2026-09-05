#!/bin/sh
set -e

mkdir -p /app/data

if [ ! -f /app/data/recovery.db ]; then
  echo "[podium] No recovery.db found — generating synthetic dataset (seed=42)…"
  podium-generate --seed 42 --db /app/data/recovery.db
  echo "[podium] Dataset ready."
else
  echo "[podium] Using existing /app/data/recovery.db"
fi

exec "$@"
