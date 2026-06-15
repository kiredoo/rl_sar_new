#!/bin/bash
# Compute derived/summary.txt from a run's raw/<arm>/aw_<arm>_{pre,post}.txt.
# Usage:  compute_summary.sh <run_dir>
#
# Walks $run_dir/raw/*/aw_*_pre.txt, matches each with its aw_*_post.txt,
# parses the "# totals" footer from snapshot_rss.sh, and writes:
#   $run_dir/derived/summary.txt       human-readable per-arm + delta table
#   $run_dir/derived/summary.tsv       tab-separated for cross-run diffing
set -u

run_dir="${1:-}"
if [[ -z "$run_dir" || ! -d "$run_dir" ]]; then
  echo "usage: $0 <run_dir>" >&2
  exit 1
fi
derived="$run_dir/derived"
mkdir -p "$derived"

out="$derived/summary.txt"
tsv="$derived/summary.tsv"

# Extract a value from the "# totals ..." footer line.
field() { awk -v k="$1" '/^# totals/ {for(i=1;i<=NF;i++) if($i~"^"k"="){split($i,a,"="); print a[2]; exit}}' "$2"; }

# Count SIGABRT-style crashes across the arm's runtime logs.
# A bringup component that exits on SIGABRT shows up as
# "exit code -6" in launch output; we grep both the gzipped
# phase-1 log and the plain phase-2 log. Absence of either log
# contributes 0.
count_aborts() {
  local tag_dir="$1" tag="$2"
  local total=0 c p
  for p in "$tag_dir/aw_${tag}"*.log.gz; do
    [[ -f "$p" ]] || continue
    c=$(zgrep -c 'exit code -6' "$p" 2>/dev/null)
    total=$(( total + ${c:-0} ))
  done
  for p in "$tag_dir/aw_${tag}"*.log; do
    [[ -f "$p" ]] || continue
    c=$(grep -c 'exit code -6' "$p" 2>/dev/null)
    total=$(( total + ${c:-0} ))
  done
  echo "$total"
}

# Collect every arm tag that has a pre file.
arms=()
for pre in "$run_dir"/raw/*/aw_*_pre.txt; do
  [[ -f "$pre" ]] || continue
  tag=$(basename "$pre" | sed -E 's/^aw_(.+)_pre\.txt$/\1/')
  arms+=("$tag")
done

if [[ ${#arms[@]} -eq 0 ]]; then
  echo "no aw_*_pre.txt found under $run_dir/raw/*/" >&2
  exit 1
fi

{
  echo "# schema=1"
  echo "# Run summary — $(basename "$run_dir")"
  echo "# Generated $(date -u +%Y-%m-%dT%H:%M:%SZ) by tools/compute_summary.sh"
  echo
  echo "## Raw totals (from snapshot_rss.sh '# totals' footer)"
  for tag in "${arms[@]}"; do
    pre="$run_dir/raw/$tag/aw_${tag}_pre.txt"
    post="$run_dir/raw/$tag/aw_${tag}_post.txt"
    echo "arm $tag"
    echo "  pre : $(tail -1 "$pre")"
    echo "  post: $(tail -1 "$post")"
  done
  echo
  echo "## Bag-phase delta (post - pre)"
  printf "%-6s %12s %12s %12s %12s %12s %8s %8s\n" arm minflt majflt rss_kb vol_ctx invol_ctx nprocs aborts
  for tag in "${arms[@]}"; do
    pre="$run_dir/raw/$tag/aw_${tag}_pre.txt"
    post="$run_dir/raw/$tag/aw_${tag}_post.txt"
    mi1=$(field minflt "$pre"); mi2=$(field minflt "$post")
    ma1=$(field majflt "$pre"); ma2=$(field majflt "$post")
    r1=$(field rss_kb "$pre");  r2=$(field rss_kb "$post")
    v1=$(field vol_ctx "$pre"); v2=$(field vol_ctx "$post")
    iv1=$(field invol_ctx "$pre"); iv2=$(field invol_ctx "$post")
    n=$(field num "$pre")
    a=$(count_aborts "$run_dir/raw/$tag" "$tag")
    printf "%-6s %12d %12d %12d %12d %12d %8d %8d\n" \
      "$tag" $((mi2-mi1)) $((ma2-ma1)) $((r2-r1)) $((v2-v1)) $((iv2-iv1)) "$n" "$a"
  done
  echo
  echo "## Steady-state RSS at pre-bag (kB)"
  for tag in "${arms[@]}"; do
    pre="$run_dir/raw/$tag/aw_${tag}_pre.txt"
    printf "  %-6s %d\n" "$tag" "$(field rss_kb "$pre")"
  done
} > "$out"

# TSV for easy cross-run diffing.
# Schema=1: leading `#` lines are comments / metadata; readers must
# skip them before consuming the header row. aggregate_configs.py
# enforces a matching schema=1; bumping this line requires bumping
# the consumer in lockstep.
{
  echo "# schema=1"
  echo -e "arm\tminflt_delta\tmajflt_delta\trss_kb_delta\tvol_ctx_delta\tinvol_ctx_delta\trss_kb_pre\tnprocs\taborts"
  for tag in "${arms[@]}"; do
    pre="$run_dir/raw/$tag/aw_${tag}_pre.txt"
    post="$run_dir/raw/$tag/aw_${tag}_post.txt"
    mi1=$(field minflt "$pre"); mi2=$(field minflt "$post")
    ma1=$(field majflt "$pre"); ma2=$(field majflt "$post")
    r1=$(field rss_kb "$pre");  r2=$(field rss_kb "$post")
    v1=$(field vol_ctx "$pre"); v2=$(field vol_ctx "$post")
    iv1=$(field invol_ctx "$pre"); iv2=$(field invol_ctx "$post")
    n=$(field num "$pre")
    a=$(count_aborts "$run_dir/raw/$tag" "$tag")
    printf "%s\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\n" \
      "$tag" $((mi2-mi1)) $((ma2-ma1)) $((r2-r1)) $((v2-v1)) $((iv2-iv1)) "$r1" "$n" "$a"
  done
} > "$tsv"

echo "wrote $out"
echo "wrote $tsv"

# ---- Auto-generate per-run figures (Session 7 automation) -----------
# 1) 1 Hz time-series PNG per arm (via tools/plot_timeseries.py).
# 2) Tier 0 PNG triplet per arm (via tools/plot_tier0.py) when a
#    raw/<arm>/tier0/ directory is present.
# Failures here do not abort the summary — figures are additive evidence
# and a missing matplotlib / pandas should not break the headline numbers.
tools_dir="$(cd "$(dirname "$0")" && pwd)"
fig_dir="$run_dir/derived/figures"
mkdir -p "$fig_dir"
for tag in "${arms[@]}"; do
  ts="$run_dir/raw/$tag/aw_${tag}_timeseries.tsv"
  if [[ -f "$ts" && -x "$tools_dir/plot_timeseries.py" ]]; then
    out_png="$fig_dir/timeseries_${tag}.png"
    if python3 "$tools_dir/plot_timeseries.py" "$ts" "$out_png" >/dev/null 2>&1; then
      echo "wrote $out_png"
    else
      echo "(skipped $out_png — plot_timeseries.py failed; check matplotlib/pandas)" >&2
    fi
  fi
  tier0_in="$run_dir/raw/$tag/tier0"
  if [[ -d "$tier0_in" && -x "$tools_dir/plot_tier0.py" ]]; then
    if python3 "$tools_dir/plot_tier0.py" "$tier0_in" >/dev/null 2>&1; then
      echo "wrote $tier0_in/figures/{psi_memory,smaps_pss_aggregate,cgroup_memory_pre_post}.png"
    else
      echo "(skipped $tier0_in/figures/ — plot_tier0.py failed)" >&2
    fi
  fi
done

# ---- Auto-append "## Figures" section to MANIFEST.md (Session 7) -----
# Idempotent: re-runs replace the existing block. Reader-friendly captions
# so the human reader can interpret each figure without reading the code.
manifest="$run_dir/MANIFEST.md"
if [[ -f "$manifest" ]]; then
  # Strip any prior auto-generated block so re-runs stay clean.
  awk '/^<!-- BEGIN compute_summary auto-figures -->/{skip=1; next}
       /^<!-- END compute_summary auto-figures -->/{skip=0; next}
       !skip' "$manifest" > "$manifest.tmp" && mv "$manifest.tmp" "$manifest"
  {
    echo
    echo "<!-- BEGIN compute_summary auto-figures -->"
    echo "## Figures (auto-generated by tools/compute_summary.sh)"
    echo
    for tag in "${arms[@]}"; do
      ts_png="derived/figures/timeseries_${tag}.png"
      if [[ -f "$run_dir/$ts_png" ]]; then
        echo "### Arm $tag — 1 Hz RSS time-series"
        echo
        echo "![timeseries arm $tag]($ts_png)"
        echo
        echo "*Three panels: (1) sum RSS over Autoware procs in MiB; (2) minflt rate (faults/sec); (3) live nprocs at each sample. The bag-replay window is the busy middle stretch; pre-bag bringup tail is on the left, teardown on the right.*"
        echo
      fi
      psi_png="raw/$tag/tier0/figures/psi_memory.png"
      smaps_png="raw/$tag/tier0/figures/smaps_pss_aggregate.png"
      cgroup_png="raw/$tag/tier0/figures/cgroup_memory_pre_post.png"
      if [[ -f "$run_dir/$psi_png" ]]; then
        echo "### Arm $tag — Tier 0 PSI memory"
        echo
        echo "![PSI memory arm $tag]($psi_png)"
        echo
        echo "*Top: PSI \`some\` and \`full\` avg10 / avg60 over time. Bottom: cumulative \`total_us\` delta. PSI = 0 throughout means the host was not pressured into reclaim during the bag-replay window — saturation absent. See \`feedback_psi_metric_semantics.md\` memo for why this is the correct claim, not a bug.*"
        echo
      fi
      if [[ -f "$run_dir/$smaps_png" ]]; then
        echo "### Arm $tag — Tier 0 smaps_rollup PSS aggregate"
        echo
        echo "![smaps PSS arm $tag]($smaps_png)"
        echo
        echo "*Top: sum RSS / sum PSS / sum Pss_Anon across sampled procs (PIDs in pgrep filter; with \`SMAPS_TOP_K\` set, only top-K by VmRSS). Middle: PSS / RSS share — closer to 100 % means less shared-memory double-counting in RSS. Bottom: AnonHugePages share + distinct PID count.*"
        echo
      fi
      if [[ -f "$run_dir/$cgroup_png" ]]; then
        echo "### Arm $tag — Tier 0 cgroup memory.stat pre vs post"
        echo
        echo "![cgroup arm $tag]($cgroup_png)"
        echo
        echo "*Pre and post snapshots of cgroup memory.stat for top keys (rss / cache / anon / shmem / mapped_file / active+inactive_anon / active+inactive_file). Δpre→post quantifies the cgroup-level memory change across the bag-replay window. Pre-only label appears if the orchestrator SIGTERM'd the sampler before the post hook (older runs pre commit \`869efe6\`).*"
        echo
      fi
    done
    echo "<!-- END compute_summary auto-figures -->"
  } >> "$manifest"
  echo "appended auto-figures section to $manifest"

  # ---- Auto-append "## Experiment settings" section to MANIFEST.md ----
  # Same idempotent BEGIN/END pattern. Source: env/exp_settings_<arm>.tsv
  # written by run_ab_phase.sh at phase start. Records the protocol /
  # sampler / CARET / heaphook .so identity active for the run, with a
  # sha256 over the file content as the audit-chain cryptographic anchor.
  awk '/^<!-- BEGIN compute_summary auto-exp-settings -->/{skip=1; next}
       /^<!-- END compute_summary auto-exp-settings -->/{skip=0; next}
       !skip' "$manifest" > "$manifest.tmp" && mv "$manifest.tmp" "$manifest"
  {
    echo
    echo "<!-- BEGIN compute_summary auto-exp-settings -->"
    echo "## Experiment settings (auto-generated by tools/compute_summary.sh)"
    echo
    echo "Each \`exp_settings_<arm>.tsv\` is the canonical record of every protocol / sampler / CARET / binary knob active when the phase ran. Reports cite this run via \`run_id\`; from there, this section is the one-step path back to the recipe."
    echo
    found_any=0
    for tag in "${arms[@]}"; do
      tsv="env/exp_settings_${tag}.tsv"
      if [[ -f "$run_dir/$tsv" ]]; then
        found_any=1
        sha=$(sha256sum "$run_dir/$tsv" 2>/dev/null | awk '{print $1}')
        echo "### Arm $tag — settings"
        echo
        echo "Source: \`$tsv\` (sha256 \`$sha\`)"
        echo
        echo "| key | value |"
        echo "|---|---|"
        # Skip header + comment lines; render data rows as table.
        awk -F'\t' '!/^#/ && !/^key\tvalue/ {gsub(/\|/,"\\|",$1); gsub(/\|/,"\\|",$2); print "| `" $1 "` | `" $2 "` |"}' "$run_dir/$tsv"
        echo
      fi
    done
    if [[ $found_any -eq 0 ]]; then
      echo "(no \`env/exp_settings_*.tsv\` file found; this run pre-dates the audit-chain logging in tools/run_ab_phase.sh, or the phase ran before that wiring landed.)"
      echo
    fi
    echo "<!-- END compute_summary auto-exp-settings -->"
  } >> "$manifest"
  echo "appended exp-settings section to $manifest"
fi

# Seal raw/ with a checksum file. Listed paths are relative to $run_dir
# (so `cd $run_dir && sha256sum -c raw/CHECKSUMS.sha256` verifies).
# Sorted for determinism; self-excluded to avoid a recursion trap.
checksums="$run_dir/raw/CHECKSUMS.sha256"
(
  cd "$run_dir"
  find raw -type f ! -name CHECKSUMS.sha256 -print0 \
    | LC_ALL=C sort -z \
    | xargs -0 sha256sum
) > "$checksums"
echo "wrote $checksums"
