#!/bin/bash
# Merge derived/summary.tsv from multiple runs into one markdown table.
#
# Usage:
#   compare_runs.sh [--baseline <run_id:arm>] <run_dir> [run_dir ...]
#
# Examples:
#   # All arms of all runs, no delta column
#   tools/compare_runs.sh runs/2026-04-14T12-48_stockpile-ab
#
#   # Compare everything against arm A of the stockpile run
#   tools/compare_runs.sh \
#     --baseline 2026-04-14T12-48_stockpile-ab:A \
#     runs/2026-04-14T12-48_stockpile-ab \
#     runs/2026-04-20T09-30_hybrid-unfixed   \
#     runs/2026-04-21T10-15_hybrid-fixed-v1
#
# Output: markdown table on stdout. Paste into reports/*.md.
# Reads derived/summary.tsv from each run (must exist — run compute_summary.sh first).
set -u

baseline=""
runs=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --baseline) baseline="$2"; shift 2 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *)          runs+=("$1"); shift ;;
  esac
done
[[ ${#runs[@]} -gt 0 ]] || { echo "usage: $0 [--baseline <run_id:arm>] <run_dir>..." >&2; exit 1; }

base_mi= base_ma= base_r= base_v= base_iv=
if [[ -n "$baseline" ]]; then
  b_run="${baseline%%:*}"
  b_arm="${baseline##*:}"
  # find matching run dir
  b_dir=""
  for d in "${runs[@]}"; do
    if [[ "$(basename "$d")" == "$b_run" ]]; then b_dir="$d"; break; fi
  done
  if [[ -z "$b_dir" || ! -f "$b_dir/derived/summary.tsv" ]]; then
    echo "baseline $baseline not found among supplied runs (need its summary.tsv)" >&2
    exit 1
  fi
  read -r base_mi base_ma base_r base_v base_iv < <(
    awk -v a="$b_arm" -F'\t' 'NR>1 && $1==a {print $2,$3,$4,$5,$6}' "$b_dir/derived/summary.tsv"
  )
  if [[ -z "$base_mi" ]]; then
    echo "arm '$b_arm' not found in $b_dir/derived/summary.tsv" >&2
    exit 1
  fi
fi

pct() {   # $1=value  $2=baseline
  awk -v v="$1" -v b="$2" 'BEGIN {
    if (b+0 == 0) { printf "    --"; exit }
    printf "%+6.1f%%", (v-b)*100.0/b
  }'
}

# Header
{
  echo "# Cross-run comparison"
  echo
  [[ -n "$baseline" ]] && echo "Baseline: \`$baseline\` (column Δ = (this − baseline) / baseline)" && echo
  if [[ -n "$baseline" ]]; then
    echo "| run | arm | minflt | Δ | majflt | rss_kb Δ | Δ | vol_ctx | invol_ctx | rss_pre | n |"
    echo "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
  else
    echo "| run | arm | minflt Δ | majflt Δ | rss_kb Δ | vol_ctx Δ | invol_ctx Δ | rss_pre | n |"
    echo "|---|---|---:|---:|---:|---:|---:|---:|---:|"
  fi

  for d in "${runs[@]}"; do
    tsv="$d/derived/summary.tsv"
    if [[ ! -f "$tsv" ]]; then
      echo "| $(basename "$d") | _(no summary.tsv — run compute_summary.sh)_ | | | | | | | |"
      continue
    fi
    run_id=$(basename "$d")
    awk -F'\t' -v run="$run_id" -v bmi="$base_mi" -v bma="$base_ma" -v br="$base_r" \
               -v bv="$base_v" -v biv="$base_iv" -v use_base="$([[ -n "$baseline" ]] && echo 1 || echo 0)" '
      NR>1 {
        arm=$1; mi=$2; ma=$3; r=$4; v=$5; iv=$6; rpre=$7; n=$8
        if (use_base=="1") {
          printf "| %s | %s | %s | ", run, arm, mi
          printf "%s", (bmi+0==0 ? "  --" : sprintf("%+.1f%%", (mi-bmi)*100.0/bmi))
          printf " | %s | %s | ", ma, r
          printf "%s", (br+0==0 ? "  --" : sprintf("%+.1f%%", (r-br)*100.0/br))
          printf " | %s | %s | %s | %s |\n", v, iv, rpre, n
        } else {
          printf "| %s | %s | %s | %s | %s | %s | %s | %s | %s |\n", run, arm, mi, ma, r, v, iv, rpre, n
        }
      }' "$tsv"
  done

  echo
  echo "_Generated $(date -u +%Y-%m-%dT%H:%MZ) by tools/compare_runs.sh_"
  echo
  echo "Columns are bag-phase deltas (post − pre) unless marked \`rss_pre\` (steady-state)."
  echo "\`n\` = processes captured. All numeric values from derived/summary.tsv."
}
