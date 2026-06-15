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

mkdir -p "$RUN/raw/D"

echo "[D-measure] RUN=$RUN"
echo "[D-measure] duration=${DURATION_S}s"

echo "[D-measure] loaded check"
loaded_count=0

{
  for p in $(pgrep -f 'ld-linux.*rl_sim|rl_ITRI/rl_sim|/rl_sim|spawner.py|ros2 param|controller_manager' || true); do
    [[ -r /proc/$p/maps ]] || continue

    cmd=$(tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null | cut -c1-220)

    if grep -q 'libpreloaded_hybrid_o1heap_tlsf' /proc/$p/maps 2>/dev/null; then
      echo "LOADED     pid=$p $cmd"
      loaded_count=$((loaded_count + 1))
    else
      echo "not-loaded pid=$p $cmd"
    fi
  done

  echo "# loaded_count=$loaded_count"
} | tee "$RUN/raw/D/aw_D_loaded_check.txt"

loaded_count=$(grep -c '^LOADED' "$RUN/raw/D/aw_D_loaded_check.txt" || true)

if [[ "$loaded_count" -lt 1 ]]; then
  echo "[D-measure] ERROR: no process loaded libpreloaded_hybrid_o1heap_tlsf" >&2
  echo "[D-measure] This D run is invalid." >&2
  exit 2
fi

echo "[D-measure] pre snapshot"
env -u LD_PRELOAD "$SNAP" "$RUN/raw/D/aw_D_pre.txt"

echo "[D-measure] sleep ${DURATION_S}s"
sleep "$DURATION_S"

echo "[D-measure] post snapshot"
env -u LD_PRELOAD "$SNAP" "$RUN/raw/D/aw_D_post.txt"

touch "$RUN/raw/D/aw_D_done"

echo "[D-measure] done"
echo "=== D pre ==="
tail -1 "$RUN/raw/D/aw_D_pre.txt"
echo "=== D post ==="
tail -1 "$RUN/raw/D/aw_D_post.txt"
