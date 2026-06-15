#!/bin/bash
# Run one layer-2 CV rep: CARET record (parallel) + launcher + orchestrator.
#
# Usage:
#   tools/run_layer2_rep.sh <arm> <run_dir>
#     arm      A | B | D
#     run_dir  absolute path to runs/<id>
#
# The launcher is selected by arm:
#   A -> sim_play_bag_mp_baseline.sh        (pure glibc)
#   B -> sim_play_bag_mp_v2.sh              (libpreloaded_stockpile.so)
#   D -> sim_play_bag_mp_hybrid_fixed.sh    (libpreloaded_hybrid_o1heap_tlsf.so)
#
# Output: runs/<id>/raw/<arm>/{caret/heaphook-<arm>-XXX/ust/, aw_<arm>_t1.log.gz, aw_<arm>_phase.log, aw_<arm>_done}
#
# NOTE: caller is responsible for `lttng destroy --all` BEFORE invoking this
# (the current host occasionally has stale sessions that block create).

set -uo pipefail

arm="${1:?usage: $0 <arm> <run_dir>}"
run_dir="${2:?usage: $0 <arm> <run_dir>}"
case "$arm" in
  A) launcher="sim_play_bag_mp_baseline.sh" ;;
  B) launcher="sim_play_bag_mp_v2.sh" ;;
  D) launcher="sim_play_bag_mp_hybrid_fixed.sh" ;;
  *) echo "[ERR] arm must be A/B/D, got: $arm" >&2; exit 2 ;;
esac

REPO=/home/aga_pc1a/repo/claude_ws4/heaphook_experiments
SAMPLER=/home/aga_pc1a/repo/claude_ws4/heaphook_ws/build/heaphook/libheaphook_sampler.so

mkdir -p "$run_dir/raw/$arm"

# Zombie cleanup. Two failure modes observed 2026-05-04:
#   (a) bash launcher SIGINT'd but the python `ros2 launch` parent + its
#       Autoware-node children survived (run_ab_phase.sh SIGINT goes to bash
#       launcher PID, doesn't propagate to grandchildren). Result: nprocs=267
#       on D-rep2 instead of 89.
#   (b) Surviving `ros2 launch` python auto-respawns rviz2 when killed alone,
#       so killing rviz2 is insufficient — must kill the parent first.
# Pattern catches: python ros2 launch, logging_simulator references, rviz2,
# and any process with --ros-args.
for pat in 'logging_simulator' 'ros2 launch' 'rviz2' 'ros-args'; do
  PIDS="$(pgrep -f "$pat" 2>/dev/null | tr '\n' ' ')"
  [[ -z "${PIDS// }" ]] && continue
  echo "[run_layer2_rep $arm] cleanup: killing $(echo $PIDS | wc -w) procs matching '$pat'"
  # shellcheck disable=SC2086
  kill -9 $PIDS 2>/dev/null || true
done
sleep 5
# Final residue check (informational only)
RESIDUE="$(pgrep -caf 'logging_simulator|rviz2|ros-args' 2>/dev/null || echo 0)"
echo "[run_layer2_rep $arm] cleanup: residue $RESIDUE procs (rosdaemon-only is fine)"
# Also clear any stale lttng session
( set +u
  source "$HOME/caret-v0.6.2/setenv_caret.bash" >/dev/null 2>&1
  lttng destroy --all 2>&1 | head -2
) || true

# Phase 1: start CARET record wrapper in background; wait for "All process started recording".
bash "$REPO/tools/run_caret_trace.sh" "$arm" "$run_dir/raw/$arm" \
  > "$run_dir/raw/$arm/caret_trace_wrapper.log" 2>&1 &
TRACE_PID=$!
echo "$TRACE_PID" > "$run_dir/raw/$arm/caret_trace_wrapper.pid"
echo "[run_layer2_rep $arm] TRACE wrapper PID=$TRACE_PID"

ready=0
# Time scales with #recordable-procs (~5s for 3 procs, ~15s for 12 procs).
# 30s gives margin for cold cache + 20+ procs.
for i in {1..30}; do
  sleep 1
  if grep -qE "All process started recording|press ctrl-c to stop" \
       "$run_dir/raw/$arm/caret/record.log" 2>/dev/null; then
    ready=1
    echo "[run_layer2_rep $arm] CARET record READY at $(date +%H:%M:%S) (after ${i}s)"
    break
  fi
done
if (( ready == 0 )); then
  echo "[run_layer2_rep $arm] CARET record did NOT report READY in 30s; aborting"
  kill -INT "$TRACE_PID" 2>/dev/null || true
  exit 3
fi

# Lane 1.1 H1 fix (2026-05-04 v2): wait 5 s AFTER ready signal so all
# event channels are fully enabled in lttng before Autoware nodes register
# their `caret_init` events. Hypothesis: previous Phase 2.5c reps had
# stats_path.yaml all '---' because some chain nodes' caret_init events
# were dropped during the brief window between "All process started
# recording" and channels-actually-flowing. 5 s is empirical safety margin.
echo "[run_layer2_rep $arm] CARET settle 5s before launcher start"
sleep 5

# Phase 2: T1 launcher + T2 orchestrator (env propagates THREAD_LOCAL_POOL_SIZE etc.)
_SAMPLER_LD="${SKIP_SAMPLER:-0}"
if [ "$_SAMPLER_LD" = "1" ]; then
  echo "[run_layer2_rep $arm] SKIP_SAMPLER=1 — heaphook_sampler.so NOT loaded"
  _LDPRE=""
else
  _LDPRE="$SAMPLER"
fi
HEAPHOOK_FRAG_PROVIDER="${HEAPHOOK_FRAG_PROVIDER:-hybrid}" \
LD_PRELOAD="$_LDPRE" \
CARET_RECORD_ACTIVE=on \
bash "$run_dir/scripts/$launcher" > "$run_dir/raw/$arm/aw_${arm}_t1.log" 2>&1 &
T1_PID=$!
echo "$T1_PID" > "$run_dir/raw/$arm/aw_${arm}_t1.pid"
echo "[run_layer2_rep $arm] T1 launcher PID=$T1_PID"

HEAPHOOK_FRAG_PROVIDER="${HEAPHOOK_FRAG_PROVIDER:-hybrid}" \
CARET_RECORD_ACTIVE=on \
SMAPS_TOP_K="${SMAPS_TOP_K:-20}" \
SMAPS_PERIOD_MS="${SMAPS_PERIOD_MS:-10000}" \
BAG_FLOW_S="${BAG_FLOW_S:-6}" \
BAG_BURNIN_S="${BAG_BURNIN_S:-10}" \
WAIT_LOC="${WAIT_LOC:-1}" \
WAIT_LOC_MIN_HZ="${WAIT_LOC_MIN_HZ:-0.5}" \
WAIT_LOC_MAX_S="${WAIT_LOC_MAX_S:-120}" \
PLAY_RATE="${PLAY_RATE:-1.0}" \
bash "$run_dir/scripts/run_ab_phase.sh" "$arm" "$run_dir/raw/$arm" \
  > "$run_dir/raw/$arm/aw_${arm}_phase.log" 2>&1
phase_rc=$?
echo "[run_layer2_rep $arm] phase rc=$phase_rc"

# Phase 3: stop trace cleanly. Try SIGINT first (fires run_caret_trace.sh
# cleanup trap), wait briefly, then ALWAYS do manual fallback (SIGINT trap
# unreliable when wrapper is in `wait $record_pid` builtin — observed on
# 2026-05-04 A rep1 where trace stayed in ~/.ros/tracing/ after wrapper exit).
SESSION="$(cat "$run_dir/raw/$arm/caret/trace_session_name.txt" 2>/dev/null || echo)"
kill -INT "$TRACE_PID" 2>/dev/null || true
for i in {1..6}; do
  sleep 1
  if ! kill -0 "$TRACE_PID" 2>/dev/null; then break; fi
done
# Manual fallback: stop+destroy+mv whether or not cleanup ran.
if [[ -n "$SESSION" ]]; then
  ( set +u
    source "$HOME/caret-v0.6.2/setenv_caret.bash" >/dev/null 2>&1
    lttng stop "$SESSION" 2>&1 | head -2
    lttng destroy "$SESSION" 2>&1 | head -2
  ) >> "$run_dir/raw/$arm/caret/record.log" 2>&1
  if [[ -d "$HOME/.ros/tracing/$SESSION" ]]; then
    mv "$HOME/.ros/tracing/$SESSION" "$run_dir/raw/$arm/caret/" 2>/dev/null \
      || cp -r "$HOME/.ros/tracing/$SESSION" "$run_dir/raw/$arm/caret/"
    echo "[run_layer2_rep $arm] manual fallback moved trace to $run_dir/raw/$arm/caret/$SESSION"
  fi
fi
echo "[run_layer2_rep $arm] trace wrapper exited"

# Phase 4a: operational-state gate (added 2026-05-04 evening, post-Layer-3 fix).
# Catches the silent-broken-Autoware failure mode that masked the reallocarray
# bug for ~6 weeks. If any of these signals fires, the rep is operationally
# degraded and should not be used for cross-arm comparison without re-running.
log="$run_dir/raw/$arm/aw_${arm}_t1.log"
gate_pass=1
# `grep -c` on no-match exits rc=1 (still prints 0) — wrap with `|| true`
# so the count is captured cleanly without an extra `0` from `|| echo 0`.
gate_oom=$({ grep -c 'memory exhausted' "$log" 2>/dev/null; true; } | head -1)
gate_xacro=$({ grep -cE 'xacro:.*error|xacro:.*Error' "$log" 2>/dev/null; true; } | head -1)
gate_maphash=$({ grep -cE 'map_hash_generator.*memory|map_hash_generator.*Aborted' "$log" 2>/dev/null; true; } | head -1)
# Pre/post snapshot nprocs (from `# totals num=N` line of phase log)
gate_npre=$(grep -oE 'num=[0-9]+' "$run_dir/raw/$arm/aw_${arm}_pre.txt" 2>/dev/null | head -1 | cut -d= -f2)
gate_npost=$(grep -oE 'num=[0-9]+' "$run_dir/raw/$arm/aw_${arm}_post.txt" 2>/dev/null | head -1 | cut -d= -f2)
echo "[gate $arm] memory_exhausted=$gate_oom xacro_err=$gate_xacro maphash_err=$gate_maphash nprocs_pre=$gate_npre nprocs_post=$gate_npost"
[[ $gate_oom -gt 0    ]] && { echo "[gate $arm] FAIL: 'memory exhausted' in log"; gate_pass=0; }
[[ $gate_xacro -gt 0  ]] && { echo "[gate $arm] FAIL: xacro error in log";          gate_pass=0; }
[[ $gate_maphash -gt 0 ]] && { echo "[gate $arm] FAIL: map_hash_generator error";   gate_pass=0; }
[[ -z "$gate_npre"  || "$gate_npre"  -lt 80 ]] && { echo "[gate $arm] WARN: pre-bag nprocs=$gate_npre  < 80 (expected ~89)"; }
[[ -z "$gate_npost" || "$gate_npost" -lt 80 ]] && { echo "[gate $arm] WARN: post-bag nprocs=$gate_npost < 80 (expected ~89)"; }
if [[ $gate_pass -eq 1 ]]; then
  echo "[gate $arm] PASS — operational state gate cleared"
else
  echo "[gate $arm] FAIL — operationally degraded; do not use for cross-arm comparison"
fi
echo "$gate_pass" > "$run_dir/raw/$arm/aw_${arm}_gate.txt"

# Phase 4b: post-process (capture_env, gzip log, compute_summary)
"$REPO/tools/capture_env.sh" "$run_dir" >/dev/null 2>&1 || true
gzip -f "$run_dir/raw/$arm/aw_${arm}_t1.log" 2>/dev/null || true
"$REPO/tools/compute_summary.sh" "$run_dir" >/dev/null 2>&1 || true
echo "[run_layer2_rep $arm] DONE"
