#!/bin/bash
# Authoritative copy — new_run.sh seeds each run's scripts/ with this.
#
# Snapshot per-process counters for all Autoware-related processes.
# For each pid we record:
#   minflt  (/proc/pid/stat field 10)  — minor page faults
#   majflt  (/proc/pid/stat field 12)  — major page faults
#   VmRSS   (/proc/pid/status)         — resident memory (kB)
#   vol_ctx, invol_ctx (/proc/pid/status)
# Output: per-line "pid minflt majflt rss_kb vol_ctx invol_ctx tag"
# Footer: "# totals minflt=... majflt=... rss_kb=... vol_ctx=... invol_ctx=... num=..."
#
# Usage:  snapshot_rss.sh [output_path]

out="${1:-/tmp/aw_snapshot.txt}"
{
  date +"# snapshot %F %T epoch=%s"
  for pid in $(pgrep -f "ros-args|rviz2|ros2 launch autoware|robot_state_publisher|web_server\.py|logging_simulator"); do
    [[ -r /proc/$pid/stat ]] || continue
    read -r -a sf < /proc/$pid/stat 2>/dev/null || continue
    minflt=${sf[9]}
    majflt=${sf[11]}
    rss=$(awk '/^VmRSS:/ {print $2}' /proc/$pid/status 2>/dev/null)
    vol=$(awk '/^voluntary_ctxt_switches:/ {print $2}' /proc/$pid/status 2>/dev/null)
    invol=$(awk '/^nonvoluntary_ctxt_switches:/ {print $2}' /proc/$pid/status 2>/dev/null)
    [[ -z "$rss" ]] && continue
    tag=$(tr '\0' ' ' < /proc/$pid/cmdline 2>/dev/null | grep -oE '__node:=[^ ]+' | head -1 | sed 's/^__node:=//')
    [[ -z "$tag" ]] && tag=$(basename "$(readlink /proc/$pid/exe 2>/dev/null)")
    [[ -z "$tag" ]] && tag="?"
    printf "%s %s %s %s %s %s %s\n" "$pid" "$minflt" "$majflt" "$rss" "$vol" "$invol" "$tag"
  done
} > "$out"
awk '/^[0-9]/ {mi+=$2; ma+=$3; r+=$4; v+=$5; iv+=$6; n++} END {
  printf "# totals minflt=%d majflt=%d rss_kb=%d vol_ctx=%d invol_ctx=%d num=%d\n", mi, ma, r, v, iv, n
}' "$out" >> "$out"
tail -1 "$out"
