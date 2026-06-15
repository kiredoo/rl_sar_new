#!/bin/bash
# Sequential N=3 reps per arm WITHOUT sampler (PROBE=0) — for deadline miss data refresh.
# Output: runs/20260506-HHMM_layer2-{a,b,d}-canonical-rep{1,2,3}/

set -uo pipefail

REPO=/home/aga_pc1a/repo/claude_ws4/heaphook_experiments
cd "$REPO"

TS=$(date +%Y%m%d-%H%M)
LOG="$REPO/runs/${TS}_run_n3_baseline.log"
mkdir -p "$(dirname "$LOG")"

log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }

log "=== N=3 baseline (PROBE=0) reps starting: 3 arms × 3 reps ==="

for arm in A B D; do
  for i in 1 2 3; do
    RUN_DIR="$REPO/runs/${TS}_layer2-${arm,,}-canonical-rep${i}-baseline"
    mkdir -p "$RUN_DIR/scripts" "$RUN_DIR/raw/$arm"
    log "--- arm=$arm rep=$i: $RUN_DIR ---"

    REF_REP=$(ls -d "$REPO"/runs/20260506-08*_layer2-cv-${arm,,}-canonical-*-rss 2>/dev/null | head -1)
    if [ -z "$REF_REP" ]; then
      REF_REP=$(ls -d "$REPO"/runs/20260505-17*_layer2-cv-${arm,,}-canonical-rep* 2>/dev/null | head -1)
    fi
    if [ -d "$REF_REP/scripts" ]; then
      cp -r "$REF_REP/scripts/." "$RUN_DIR/scripts/"
      log "  copied scripts from $REF_REP"
    else
      log "  [ERR] no reference rep scripts for arm=$arm; skip"
      continue
    fi

    PROBE=0 timeout 360 bash "$REPO/tools/run_canonical_rep.sh" "$arm" "$RUN_DIR" 0.5 2>&1 | tee -a "$LOG"
    rc=${PIPESTATUS[0]}
    log "  arm=$arm rep=$i exit=$rc"
    sleep 8
  done
done

log "=== N=3 baseline done ==="
