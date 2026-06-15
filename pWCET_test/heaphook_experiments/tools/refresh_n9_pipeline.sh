#!/bin/bash
# Phase 3 pipeline — runs after caret_batch finishes on N=9 baseline reps.
#
# 1. Re-run observe_rep on each of 9 baseline reps (now stats_yaml exists)
# 2. Re-run extract_deadline_miss + aggregate (now N=24 reps)
# 3. Re-render f1 + f8 PNG with updated data
# 4. Print summary

set -uo pipefail

REPO=/home/aga_pc1a/repo/claude_ws4/heaphook_experiments
cd "$REPO"

LOG="/tmp/refresh_n9_pipeline_$(date +%H%M).log"
log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }

log "=== Step 1: re-run observe_rep on 9 baseline reps ==="
for d in runs/20260506-1*_layer2-*-canonical-rep*-baseline; do
  arm=$(ls $d/raw 2>/dev/null | head -1)
  if [ -z "$arm" ]; then continue; fi
  log "  observe $(basename $d) arm=$arm"
  python3 "$REPO/tools/observe_rep.py" "$d" "$arm" 2>&1 | tail -3 | tee -a "$LOG"
done

log "=== Step 2: re-extract deadline miss (24 reps) ==="
python3 "$REPO/tools/extract_deadline_miss.py" \
  --output "$REPO/reports/figures/deadline_miss_n24.tsv" 2>&1 | tee -a "$LOG"

log "=== Step 3: re-aggregate ==="
python3 "$REPO/tools/aggregate_deadline_miss.py" \
  --input "$REPO/reports/figures/deadline_miss_n24.tsv" \
  --output "$REPO/reports/figures/deadline_miss_summary_n24.tsv" \
  --png "$REPO/reports/figures/mckinsey/f8_deadline_miss_by_arm.png" 2>&1 | tee -a "$LOG"

log "=== Step 4: collect chain CV per rep for cross-arm summary ==="
python3 - <<'PY' 2>&1 | tee -a "$LOG"
import json, statistics
from pathlib import Path
import scipy.stats as st

REPO = Path("/home/aga_pc1a/repo/claude_ws4/heaphook_experiments")
groups = {"A": [], "B": [], "D": []}
for d in sorted(REPO.glob("runs/20260505-17*_layer2-cv-*-canonical-*")):
    nm = d.name.lower()
    if "1.0x" in nm or "rep1" in nm and "-cv-b-" in nm:  # skip controls / cold start
        continue
    arm = "A" if "-cv-a-" in nm else "B" if "-cv-b-" in nm else "D" if "-cv-d-" in nm else None
    if not arm: continue
    rj = list((d / "raw").rglob("result.json"))
    if not rj: continue
    data = json.loads(rj[0].read_text())
    cv = (data.get("trace") or {}).get("cv")
    verdict = data.get("verdict", "?")
    if cv is not None and verdict in ("RELAXED_PASS", "STRICT_PASS"):
        groups[arm].append(cv)

for d in sorted(REPO.glob("runs/20260506-0*_layer2-cv-*-canonical-*-rss")):
    nm = d.name.lower()
    arm = "A" if "-cv-a-" in nm else "B" if "-cv-b-" in nm else "D" if "-cv-d-" in nm else None
    if not arm: continue
    rj = list((d / "raw").rglob("result.json"))
    if not rj: continue
    data = json.loads(rj[0].read_text())
    cv = (data.get("trace") or {}).get("cv")
    verdict = data.get("verdict", "?")
    if cv is not None and verdict in ("RELAXED_PASS", "STRICT_PASS"):
        groups[arm].append(cv)

for d in sorted(REPO.glob("runs/20260506-1*_layer2-*-canonical-rep*-baseline")):
    nm = d.name.lower()
    arm = "A" if "layer2-a-" in nm else "B" if "layer2-b-" in nm else "D" if "layer2-d-" in nm else None
    if not arm: continue
    rj = list((d / "raw").rglob("result.json"))
    if not rj: continue
    data = json.loads(rj[0].read_text())
    cv = (data.get("trace") or {}).get("cv")
    verdict = data.get("verdict", "?")
    if cv is not None and verdict in ("RELAXED_PASS", "STRICT_PASS"):
        groups[arm].append(cv)

print("\nUpdated chain CV per arm:")
for a in ["A","B","D"]:
    cs = groups[a]
    print(f"  {a}: N={len(cs)} cv_list={[round(c,3) for c in cs]}")
    if cs:
        print(f"     mean={statistics.mean(cs):.4f} std={statistics.stdev(cs) if len(cs)>1 else 0:.4f}")

if groups["A"] and groups["B"]:
    t,p = st.ttest_ind(groups["A"], groups["B"], equal_var=False)
    print(f"\nWelch A vs B: t={t:.3f} p={p:.4f}")
if groups["A"] and groups["D"]:
    t,p = st.ttest_ind(groups["A"], groups["D"], equal_var=False)
    print(f"Welch A vs D: t={t:.3f} p={p:.4f}")
PY

log "=== Phase 3 refresh complete ==="
log "Log: $LOG"
