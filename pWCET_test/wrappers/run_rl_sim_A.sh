#!/usr/bin/env bash
set -euo pipefail

cd "$HOME/rl_sar_new/rl_sar"


RL_SIM_BIN="$(ros2 pkg prefix rl_ITRI)/lib/rl_ITRI/rl_sim"

test -x "$RL_SIM_BIN" || {
  echo "missing rl_sim binary: $RL_SIM_BIN" >&2
  exit 1
}

exec env -u LD_PRELOAD "$RL_SIM_BIN" "$@"
