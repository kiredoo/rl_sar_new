#!/usr/bin/env bash
set -euo pipefail

PWCET_ROOT="${PWCET_ROOT:-$HOME/rl_sar_new/rl_sar/pWCET_test}"
SLUG="${1:-rlsim}"

RUN="$PWCET_ROOT/runs/${SLUG}_$(date +%Y%m%d-%H%M%S)"

mkdir -p "$RUN/raw/A" "$RUN/raw/D" "$RUN/derived"

echo "$RUN" | tee /tmp/rlsim_current_run

echo "[new-run] RUN=$RUN"
echo "[new-run] raw/A=$RUN/raw/A"
echo "[new-run] raw/D=$RUN/raw/D"
