#!/usr/bin/env bash
set -euo pipefail

PID="${1:-}"
OUT="${2:-$HOME/rl_sar_new/rl_sar/pWCET_test/wrappers/rlsim_tid_filter.bt}"

if [[ -z "$PID" ]]; then
  echo "usage: $0 <rl_sim_pid> [out.bt]" >&2
  echo "example: pid=\$(pgrep -n -f '/install/lib/rl_ITRI/rl_sim'); $0 \$pid" >&2
  exit 1
fi

if [[ ! -d "/proc/$PID/task" ]]; then
  echo "PID not found or has no task dir: $PID" >&2
  exit 1
fi

mapfile -t TIDS < <(ls "/proc/$PID/task" | sort -n)

if [[ "${#TIDS[@]}" -eq 0 ]]; then
  echo "no tids found under /proc/$PID/task" >&2
  exit 1
fi

join_or() {
  local field="$1"
  local out=""
  for tid in "${TIDS[@]}"; do
    if [[ -z "$out" ]]; then
      out="${field} == ${tid}"
    else
      out="${out} || ${field} == ${tid}"
    fi
  done
  printf '%s' "$out"
}

WAKE_FILTER="$(join_or 'args->pid')"
IN_FILTER="$(join_or 'args->next_pid')"
OUT_FILTER="$(join_or 'args->prev_pid')"

mkdir -p "$(dirname "$OUT")"

cat > "$OUT" <<BPF
#!/usr/bin/env bpftrace

BEGIN {
  printf("ts,event,tid,other\\n");
}

tracepoint:sched:sched_wakeup /${WAKE_FILTER}/ {
  printf("%llu,wakeup,%d,0\\n", nsecs, args->pid);
}

tracepoint:sched:sched_switch /${IN_FILTER}/ {
  printf("%llu,switch_in,%d,%d\\n", nsecs, args->next_pid, args->prev_pid);
}

tracepoint:sched:sched_switch /${OUT_FILTER}/ {
  printf("%llu,switch_out,%d,%d\\n", nsecs, args->prev_pid, args->next_pid);
}
BPF

chmod +x "$OUT"

echo "wrote $OUT"
echo "target PID: $PID"
echo "tracked TIDs (${#TIDS[@]}): ${TIDS[*]}"
