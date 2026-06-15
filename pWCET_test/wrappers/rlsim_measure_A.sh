#!/usr/bin/env bash
set -euo pipefail

PWCET_ROOT="${PWCET_ROOT:-$HOME/rl_sar_new/rl_sar/pWCET_test}"
RUN="${RUN:-$(cat /tmp/rlsim_current_run)}"
DURATION_S="${1:-60}"

SNAP="$PWCET_ROOT/wrappers/snapshot_rlsim.sh"

test -x "$SNAP" || {
  echo "missing snapshot script: $SNAP" >&2
  exit 1
}

mkdir -p "$RUN/raw/A"

echo "[A-measure] RUN=$RUN"
echo "[A-measure] duration=${DURATION_S}s"

echo "[A-measure] pre snapshot"
env -u LD_PRELOAD "$SNAP" "$RUN/raw/A/aw_A_pre.txt"

echo "[A-measure] sleep ${DURATION_S}s"
sleep "$DURATION_S"

echo "[A-measure] post snapshot"
env -u LD_PRELOAD "$SNAP" "$RUN/raw/A/aw_A_post.txt"

touch "$RUN/raw/A/aw_A_done"

echo "[A-measure] done"
echo "=== A pre ==="
tail -1 "$RUN/raw/A/aw_A_pre.txt"
echo "=== A post ==="
tail -1 "$RUN/raw/A/aw_A_post.txt"
