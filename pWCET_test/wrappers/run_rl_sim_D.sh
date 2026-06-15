#!/usr/bin/env bash
set -euo pipefail

cd "$HOME/rl_sar_new/rl_sar"


PWCET_ROOT="$HOME/rl_sar_new/rl_sar/pWCET_test"
HYBRID_SO="$PWCET_ROOT/heaphook_ws/install/heaphook/lib/libpreloaded_hybrid_o1heap_tlsf.so"
RL_SIM_BIN="$(ros2 pkg prefix rl_ITRI)/lib/rl_ITRI/rl_sim"
LOADER="/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2"

test -f "$HYBRID_SO" || {
  echo "missing HYBRID_SO: $HYBRID_SO" >&2
  exit 1
}

test -x "$RL_SIM_BIN" || {
  echo "missing rl_sim binary: $RL_SIM_BIN" >&2
  exit 1
}

test -x "$LOADER" || {
  echo "missing loader: $LOADER" >&2
  exit 1
}

exec env -u LD_PRELOAD "$LOADER" --preload "$HYBRID_SO" "$RL_SIM_BIN" "$@"
