#!/bin/bash
# Rate sweep: 0.25x / 0.5x / 0.75x / 1.0x × 3 arms × N=3 reps = 36 reps
#
# Output: runs/<TS>_layer2-{a,b,d}-rate{025,050,075,100}-rep{1,2,3}/
# Tracks how each arm degrades with bag rate; isolates host compute bottleneck
# from allocator behavior.

set -uo pipefail

REPO=/home/aga_pc1a/repo/claude_ws4/heaphook_experiments
cd "$REPO"

TS=$(date +%Y%m%d-%H%M)
LOG="$REPO/runs/${TS}_run_rate_sweep.log"

log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }

RATES=("0.25" "0.5" "0.75" "1.0")
RATE_TAGS=("025" "050" "075" "100")
ARMS=("A" "B" "D")
N_REPS=3

log "=== Rate sweep: ${#RATES[@]} rates × ${#ARMS[@]} arms × N=$N_REPS reps = $((${#RATES[@]} * ${#ARMS[@]} * N_REPS)) reps ==="
log "Estimated wall: $((${#RATES[@]} * ${#ARMS[@]} * N_REPS * 3)) min orch + caret_batch later"

for ri in "${!RATES[@]}"; do
  rate="${RATES[$ri]}"
  rtag="${RATE_TAGS[$ri]}"
  for arm in "${ARMS[@]}"; do
    for n in $(seq 1 $N_REPS); do
      RUN_DIR="$REPO/runs/${TS}_layer2-${arm,,}-rate${rtag}-rep${n}"
      mkdir -p "$RUN_DIR/scripts" "$RUN_DIR/raw/$arm"
      log "--- arm=$arm rate=${rate}x rep=$n: $RUN_DIR ---"

      # Copy reference scripts (any 0506 valid rep works since scripts identical across rates)
      REF_REP=$(ls -d "$REPO"/runs/20260506-08*_layer2-cv-${arm,,}-canonical-*-rss 2>/dev/null | head -1)
      if [ -z "$REF_REP" ]; then
        REF_REP=$(ls -d "$REPO"/runs/20260506-1159_layer2-${arm,,}-canonical-*-baseline 2>/dev/null | head -1)
      fi
      if [ -d "$REF_REP/scripts" ]; then
        cp -r "$REF_REP/scripts/." "$RUN_DIR/scripts/"
      else
        log "  [ERR] no reference scripts; skip"
        continue
      fi

      PROBE=0 timeout 420 bash "$REPO/tools/run_canonical_rep.sh" "$arm" "$RUN_DIR" "$rate" 2>&1 | tee -a "$LOG"
      rc=${PIPESTATUS[0]}
      log "  arm=$arm rate=${rate}x rep=$n exit=$rc"
      sleep 6
    done
  done
done

log "=== Rate sweep done ==="
log "Next: tools/run_caret_batch.sh on all rate-sweep traces; then aggregate"
