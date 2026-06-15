#!/usr/bin/env bash
set -euo pipefail

PWCET_ROOT="${PWCET_ROOT:-$HOME/rl_sar_new/rl_sar/pWCET_test}"
RUN="${RUN:-$(cat /tmp/rlsim_current_run)}"

mkdir -p "$RUN/raw/A"

echo "[A-start] RUN=$RUN"
echo "[A-start] log=$RUN/raw/A/aw_A_t1.log"
echo "[A-start] allocator=glibc baseline, LD_PRELOAD cleared"

{
  echo "# arm=A"
  echo "# started_at=$(date -Iseconds)"
  echo "# allocator=glibc baseline"
  echo "# command=run_rl_sim_A.sh"
} > "$RUN/raw/A/launch_meta_A.txt"

~/rl_sar_new/rl_sar/pWCET_test/wrappers/run_rl_sim_A.sh \
  2>&1 | tee "$RUN/raw/A/aw_A_t1.log"
