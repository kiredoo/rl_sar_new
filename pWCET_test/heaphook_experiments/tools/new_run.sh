#!/bin/bash
# Scaffold a fresh run directory under runs/.
# Usage:  tools/new_run.sh <slug>
# Example: tools/new_run.sh hybrid-unfixed
#
# After this scaffolds:
#   - drop raw artefacts into runs/<id>/raw/<arm>/aw_<arm>_{pre,post,t1.log.gz,t2.log,phase.log}
#   - run tools/capture_env.sh  runs/<id>
#   - run tools/compute_summary.sh runs/<id>
#   - fill runs/<id>/MANIFEST.md
#   - append a row to INDEX.md run catalogue
#   - ln -sfn runs/<id> latest
set -euo pipefail

slug="${1:-}"
if [[ -z "$slug" ]]; then
  echo "usage: $0 <slug>   (e.g. hybrid-unfixed, stockpile-ab-repro2, rate-stress-2x)" >&2
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# Run-id format: YYYYMMDD-HHMM_<slug>. Going-forward from 2026-04-29
# (see docs/DECISIONS.md and docs/CONVENTIONS.md). Pre-existing runs
# under the older `YYYY-MM-DDTHH-MM_<slug>` form are grandfathered as
# immutable; do not rename.
stamp="$(date +%Y%m%d-%H%M)"
run_id="${stamp}_${slug}"
run_dir="$ROOT/runs/$run_id"

if [[ -e "$run_dir" ]]; then
  suffix=b
  while [[ -e "${run_dir}-${suffix}" ]]; do
    suffix=$(printf "\\$(printf '%03o' $(( $(printf '%d' "'$suffix") + 1 )))")
  done
  run_dir="${run_dir}-${suffix}"
  run_id="${run_id}-${suffix}"
fi

mkdir -p "$run_dir"/{scripts,raw,derived,env}

# Seed the run's scripts/ with the authoritative copies from tools/.
# The live scripts in autoware-2025.02_baseline_caret/scripts/ may drift;
# these frozen copies are what we guarantee was run.
for f in run_ab_phase.sh snapshot_rss.sh sample_rss.sh tier0_sampler.sh; do
  [[ -f "$ROOT/tools/$f" ]] && cp "$ROOT/tools/$f" "$run_dir/scripts/"
done
# Launcher scripts + play_bag live in the autoware workspace — copy those too.
AW_SCRIPTS="${AW_SCRIPTS:-$HOME/repo/claude_ws4/autoware-2025.02_baseline_caret/scripts}"
for f in sim_play_bag_mp_baseline.sh sim_play_bag_mp_v2.sh play_bag.sh; do
  [[ -f "$AW_SCRIPTS/$f" ]] && cp "$AW_SCRIPTS/$f" "$run_dir/scripts/"
done
chmod +x "$run_dir/scripts/"*.sh 2>/dev/null || true

# MANIFEST skeleton — aligned with the one used for stockpile run.
cat > "$run_dir/MANIFEST.md" <<EOF
# Run manifest

| Field | Value |
|---|---|
| run_id        | \`$run_id\` |
| date          | $(date +%Y-%m-%d) |
| arm timestamps | <FILL IN, e.g. "arm A 09:30-09:35, arm B 09:36-09:41"> |
| experiment    | <FILL IN, e.g. "Hybrid vs glibc — hybrid as-is"> |
| arms present  | <FILL IN, e.g. "C (hybrid as-is)"> |
| arms missing  | <FILL IN or "none"> |
| bag           | \`~/autoware_map/sample-rosbag\`, rate 1.0, ~30s, 8262 msgs |
| heaphook branch | <FILL IN> |
| heaphook HEAD | <FILL IN short SHA> |
| heaphook .so  | <FILL IN path> |
| autoware ws   | \`~/repo/claude_ws4/autoware-2025.02_baseline_caret/\` |
| CARET         | v0.6.2 |
| host kernel   | $(uname -r) |
| kernel.perf_event_paranoid | $(cat /proc/sys/kernel/perf_event_paranoid 2>/dev/null || echo "?") |
| procs captured | <FILL IN after compute_summary.sh> |
| outcome       | <FILL IN, e.g. "both arms clean exit"> |
| report        | <FILL IN link to ../../reports/*.md> |

## Summary

<paste the relevant table from derived/summary.txt>

## Deviations from protocol

<FILL IN or "None">

## Known issues with this run

<FILL IN or "None">
EOF

echo "created: $run_dir"
echo "run_id:  $run_id"
echo
echo "next steps:"
echo "  1. run launcher + orchestrator; raw outputs go into $run_dir/raw/<arm>/"
echo "  2. $ROOT/tools/capture_env.sh $run_dir"
echo "  3. $ROOT/tools/compute_summary.sh $run_dir"
echo "  4. fill $run_dir/MANIFEST.md"
echo "  5. append run row to $ROOT/INDEX.md"
echo "  6. ln -sfn runs/$run_id $ROOT/latest"
