#!/bin/bash
# Sequential N=3 D-arm reps with PROBE=1 (frag instrumentation).
# Post-processes each rep's frag tsvs into per-rep frag_summary.tsv.
#
# Output: runs/20260506-HHMM_layer2-d-probe-rep{1,2,3}/

set -uo pipefail

REPO=/home/aga_pc1a/repo/claude_ws4/heaphook_experiments
cd "$REPO"

TS=$(date +%Y%m%d-%H%M)
LOG="$REPO/runs/${TS}_run_n3_d_probe.log"
mkdir -p "$(dirname "$LOG")"

log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }

log "=== N=3 D PROBE=1 reps starting ==="

for i in 1 2 3; do
  RUN_DIR="$REPO/runs/${TS}_layer2-d-probe-rep${i}"
  mkdir -p "$RUN_DIR/scripts" "$RUN_DIR/raw/D"
  log "--- rep $i: $RUN_DIR ---"

  # Copy launcher and sampler scripts from a known-good prior rep
  REF_REP=$(ls -d "$REPO"/runs/20260506-08*_layer2-cv-d-canonical-*-rss 2>/dev/null | head -1)
  if [ -d "$REF_REP/scripts" ]; then
    cp -r "$REF_REP/scripts/." "$RUN_DIR/scripts/"
  else
    log "[ERR] no reference rep scripts found; abort"
    exit 4
  fi

  PROBE=1 timeout 360 bash "$REPO/tools/run_canonical_rep.sh" D "$RUN_DIR" 0.5 2>&1 | tee -a "$LOG"
  rc=${PIPESTATUS[0]}
  log "rep $i canonical orch exit=$rc"

  # Post-process frag if data present
  if ls "$RUN_DIR/raw/D/frag/"*.tsv >/dev/null 2>&1; then
    log "rep $i post-processing frag"
    python3 "$REPO/tools/post_process_frag.py" --run-dir "$RUN_DIR" 2>&1 | tee -a "$LOG"
  else
    log "rep $i NO frag tsvs found — sampler did not run; skipping post-process"
  fi

  log "rep $i complete"
  sleep 10  # give system time to settle between reps
done

log "=== N=3 done ==="
