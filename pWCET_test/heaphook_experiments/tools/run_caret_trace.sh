#!/bin/bash
# Wrap a heaphook_experiments arm rep with CARET tracing (`ros2 caret record`)
# parallel to the standard launch + run_ab_phase orchestrator.
#
# Why this exists: the historical heaphook reps source `setenv_caret.bash`
# (which LD_PRELOADs libcaret.so) but never started an `ros2 caret record`
# session, so trace events went nowhere. This wrapper closes that gap by
# starting `record.sh` (= `ros2 caret record -f 10000 --light`) BEFORE the
# launch and tearing it down AFTER the bag completes.
#
# Reference: reports/caret_jitter_gate.md § 4; user note 2026-04-30 evening
# pointed at ~/repo/caret_report/ + ~/repo/claude_ws4/autoware-2025.02_baseline_caret/scripts/record.sh
#
# Usage:
#   tools/run_caret_trace.sh <arm> <run_dir>
#     arm      A | B | D | D-v4 — same labels as run_ab_phase.sh
#     run_dir  destination for trace artefacts (typically runs/<id>/raw/<arm>)
#
# Outputs into $run_dir/caret/:
#   session-<id>/                 raw CTF trace dir (moved from ~/.ros/tracing)
#   record.log                    record.sh stdout/stderr
#   trace_session_name.txt        the lttng session name for downstream analysis
#
# Caveats:
#   - Caller is responsible for spawning the actual launch (e.g.
#     sim_play_bag_mp_v2.sh) AFTER this script has reported "RECORD_READY".
#   - Caller must NOT exit the script before `lttng stop` runs; this wrapper
#     traps EXIT and stops/destroys the session cleanly.
#   - record.sh uses `--light` (UST only, no kernel tracing). Override
#     CARET_RECORD_FLAGS to add e.g. ` --lttng-output-format ctf2`.
#
# Pre-conditions (caret_jitter_gate.md § 4):
#   - ~/caret-v0.6.2/setenv_caret.bash is sourceable
#   - lttng-sessiond is daemonised (setenv_caret.bash auto-starts it)
#   - ~/.ros/tracing/ writable

set -uo pipefail

arm="${1:?usage: $0 <arm> <run_dir>}"
run_dir="${2:?usage: $0 <arm> <run_dir>}"
caret_record_flags="${CARET_RECORD_FLAGS:--f 10000 --immediate}"

caret_out="$run_dir/caret"
mkdir -p "$caret_out"

# Resolve canonical record.sh — use the autoware workspace's copy (the one
# tested on this host); fall back to inline `ros2 caret record` if absent.
record_sh="${RECORD_SH:-$HOME/repo/claude_ws4/autoware-2025.02_baseline_caret/scripts/record.sh}"

# Session naming: heaphook<arm>-<wallclock>
session_name="heaphook-$arm-$(date +%Y%m%d-%H%M%S)"
echo "$session_name" > "$caret_out/trace_session_name.txt"
trace_dir_pattern="$HOME/.ros/tracing/$session_name"

# Cleanup trap — stop + destroy the session, then move the captured trace
# dir into the run dir for immutability.
cleanup() {
  local rc=$?
  echo "[caret_trace] cleanup (rc=$rc)" >&2
  bash -c "source $HOME/caret-v0.6.2/setenv_caret.bash >/dev/null 2>&1; \
    lttng stop $session_name 2>&1 | head -2; \
    lttng destroy $session_name 2>&1 | head -2" >> "$caret_out/record.log" 2>&1
  # Best-effort move; preserves trace if move fails for any reason.
  if [[ -d "$trace_dir_pattern" ]]; then
    mv "$trace_dir_pattern" "$caret_out/" 2>/dev/null || cp -r "$trace_dir_pattern" "$caret_out/"
    echo "[caret_trace] trace moved to $caret_out/$session_name" >&2
  else
    echo "[caret_trace] WARN: trace dir $trace_dir_pattern not found at cleanup" >&2
  fi
  exit "$rc"
}
trap cleanup EXIT INT TERM

# Start record.sh in background.
# We call `ros2 caret record` directly with a named session for predictable
# trace-dir resolution at cleanup time.
echo "[caret_trace] starting record session '$session_name'" >&2
bash -c "
  source $HOME/caret-v0.6.2/setenv_caret.bash >/dev/null 2>&1
  ros2 caret record $caret_record_flags --session-name $session_name --path $HOME/.ros/tracing
" > "$caret_out/record.log" 2>&1 &
record_pid=$!
echo "$record_pid" > "$caret_out/record.pid"

# Wait for the session to be ready (~3 s on this host typically).
for i in 1 2 3 4 5 6 7 8 9 10; do
  sleep 1
  if grep -q 'started\|recording' "$caret_out/record.log" 2>/dev/null; then
    echo "RECORD_READY" >&2
    break
  fi
done

# Block until the caller signals via wait. Caller does:
#   bash tools/run_caret_trace.sh A "$RUN/raw/A" &
#   trace_pid=$!
#   bash launcher.sh & launch_pid=$!
#   bash run_ab_phase.sh A "$RUN/raw/A"
#   kill -INT $launch_pid; wait $launch_pid
#   kill -INT $trace_pid; wait $trace_pid     # triggers cleanup() above
wait "$record_pid" 2>/dev/null
