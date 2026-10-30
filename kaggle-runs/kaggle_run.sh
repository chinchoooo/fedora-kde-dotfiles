#!/bin/bash
# Push a Kaggle kernel folder, poll until it finishes, fetch output.
# usage: kaggle_run.sh <folder with kernel-metadata.json> [--accelerator NvidiaTeslaT4] [-t seconds]
# Needs Kaggle credentials (kaggle auth login, or ~/.kaggle/access_token). Never commit credentials.
set -euo pipefail
DIR="$1"; shift
ID=$(python3 -c "import json,sys;print(json.load(open('$DIR/kernel-metadata.json'))['id'])")
kaggle kernels push -p "$DIR" "$@"
while :; do
  S=$(kaggle kernels status "$ID" 2>&1 || true)
  echo "$(date +%T) $S"
  case "$S" in
    *COMPLETE*|*complete*) break ;;
    *ERROR*|*CANCEL*|*error*|*cancel*) kaggle kernels logs "$ID" | tail -40; exit 1 ;;
  esac
  sleep 30
done
mkdir -p "$DIR/output" && kaggle kernels output "$ID" -p "$DIR/output"
