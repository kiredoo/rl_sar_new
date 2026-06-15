#!/usr/bin/env bash
set -euo pipefail

out="${1:-/tmp/rlsim_snapshot.txt}"

TARGET_PATTERN="${TARGET_PATTERN:-ld-linux.*rl_sim|rl_ITRI/rl_sim|/rl_sim}"

{
  date +"# snapshot %F %T epoch=%s"

  for pid in $(pgrep -f "$TARGET_PATTERN" || true); do
    [[ "$pid" == "$$" ]] && continue
    [[ -r /proc/$pid/stat ]] || continue
    [[ -r /proc/$pid/status ]] || continue

    read -r -a sf < /proc/$pid/stat 2>/dev/null || continue

    minflt=${sf[9]}
    majflt=${sf[11]}
    rss=$(awk '/^VmRSS:/ {print $2}' /proc/$pid/status 2>/dev/null)
    vol=$(awk '/^voluntary_ctxt_switches:/ {print $2}' /proc/$pid/status 2>/dev/null)
    invol=$(awk '/^nonvoluntary_ctxt_switches:/ {print $2}' /proc/$pid/status 2>/dev/null)

    [[ -z "${rss:-}" ]] && continue

    cmd=$(tr '\0' ' ' < /proc/$pid/cmdline 2>/dev/null | cut -c1-180)
    printf "%s %s %s %s %s %s %s\n" "$pid" "$minflt" "$majflt" "$rss" "$vol" "$invol" "$cmd"
  done
} > "$out"

awk '/^[0-9]/ {mi+=$2; ma+=$3; r+=$4; v+=$5; iv+=$6; n++} END {
  printf "# totals minflt=%d majflt=%d rss_kb=%d vol_ctx=%d invol_ctx=%d num=%d\n", mi, ma, r, v, iv, n
}' "$out" >> "$out"

tail -1 "$out"
