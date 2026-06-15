#!/usr/bin/env bash
set -euo pipefail

PWCET_ROOT="${PWCET_ROOT:-$HOME/rl_sar_new/rl_sar/pWCET_test}"
RUN="${RUN:-$(cat /tmp/rlsim_current_run)}"

POOL_ARG="${1:-${THREAD_LOCAL_POOL_SIZE:-}}"

case "$POOL_ARG" in
  "")
    POOL_LABEL="default"
    unset THREAD_LOCAL_POOL_SIZE || true
    ;;
  4M|4m)
    export THREAD_LOCAL_POOL_SIZE=$((4*1024*1024))
    POOL_LABEL="4M"
    ;;
  2M|2m)
    export THREAD_LOCAL_POOL_SIZE=$((2*1024*1024))
    POOL_LABEL="2M"
    ;;
  1M|1m)
    export THREAD_LOCAL_POOL_SIZE=$((1*1024*1024))
    POOL_LABEL="1M"
    ;;
  512K|512k)
    export THREAD_LOCAL_POOL_SIZE=$((512*1024))
    POOL_LABEL="512K"
    ;;
  *)
    export THREAD_LOCAL_POOL_SIZE="$POOL_ARG"
    POOL_LABEL="${POOL_ARG}_bytes"
    ;;
esac

mkdir -p "$RUN/raw/D"

echo "[D-start] RUN=$RUN"
echo "[D-start] log=$RUN/raw/D/aw_D_t1.log"
echo "[D-start] pool_label=$POOL_LABEL"
echo "[D-start] THREAD_LOCAL_POOL_SIZE=${THREAD_LOCAL_POOL_SIZE:-default}"

{
  echo "# arm=D"
  echo "# started_at=$(date -Iseconds)"
  echo "# allocator=heaphook O1heap+TLSF hybrid"
  echo "# pool_label=$POOL_LABEL"
  echo "# THREAD_LOCAL_POOL_SIZE=${THREAD_LOCAL_POOL_SIZE:-default}"
  echo "# command=run_rl_sim_D.sh"
} > "$RUN/raw/D/launch_meta_D.txt"

~/rl_sar_new/rl_sar/pWCET_test/wrappers/run_rl_sim_D.sh \
  2>&1 | tee "$RUN/raw/D/aw_D_t1.log"
