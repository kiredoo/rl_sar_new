#!/usr/bin/env bash
set -euo pipefail

PWCET_ROOT="${PWCET_ROOT:-$HOME/rl_sar_new/rl_sar/pWCET_test}"
EXP="$PWCET_ROOT/heaphook_experiments"
RUN="${RUN:-$(cat /tmp/rlsim_current_run)}"

COMPUTE="$EXP/tools/compute_summary.sh"

test -x "$COMPUTE" || {
  echo "missing compute_summary.sh: $COMPUTE" >&2
  exit 1
}

echo "[summary] RUN=$RUN"

env -u LD_PRELOAD bash "$COMPUTE" "$RUN"

echo
echo "=== summary.txt ==="
cat "$RUN/derived/summary.txt"

echo
echo "=== summary.tsv ==="
grep -v '^#' "$RUN/derived/summary.tsv" | column -t -s $'\t'
