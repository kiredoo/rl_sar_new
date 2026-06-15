#!/bin/bash
# Periodic per-process sampler. Runs in the background during bag play
# and writes a TSV time series of minflt / majflt / rss_kb / vol_ctx /
# invol_ctx / comm per pid per sampling epoch.
#
# Usage:
#   sample_rss.sh start <out_tsv>     start sampler, write pidfile <out_tsv>.pid
#   sample_rss.sh stop  <out_tsv>     stop sampler (noop if no pidfile)
#
# Env knobs:
#   SAMPLE_INTERVAL   seconds between samples (default 1)
#   SAMPLE_PATTERN    pgrep -f pattern for the target process set
#                     (default: same Autoware filter as snapshot_rss.sh)
#
# Output schema: first line is a banner comment, second line is the
# tab-separated column header, remaining lines are data rows.

cmd="${1:-}"
out="${2:-}"
if [[ -z "$cmd" || -z "$out" ]]; then
  echo "usage: $0 {start|stop} <out_tsv>" >&2
  exit 1
fi

pidfile="${out}.pid"
interval="${SAMPLE_INTERVAL:-1}"
pattern="${SAMPLE_PATTERN:-ros-args|rviz2|ros2 launch autoware|robot_state_publisher|web_server\\.py|logging_simulator}"

case "$cmd" in
  start)
    if [[ -f "$pidfile" ]]; then
      old_pid=$(cat "$pidfile" 2>/dev/null || true)
      if [[ -n "$old_pid" ]] && kill -0 "$old_pid" 2>/dev/null; then
        echo "sample_rss: already running pid=$old_pid (pidfile=$pidfile)" >&2
        exit 1
      fi
    fi

    {
      date +"# started %F %T epoch=%s interval=${interval}s pattern=$pattern"
      printf 'epoch\tpid\tminflt\tmajflt\trss_kb\tvol_ctx\tinvol_ctx\tcomm\n'
    } > "$out"

    # Background sampler. Detach from stdin, keep stdout appending to $out,
    # swallow stderr (transient /proc races are expected and noisy).
    (
      trap 'exit 0' TERM INT
      while true; do
        epoch=$(date +%s)
        while IFS= read -r pid; do
          [[ -r /proc/$pid/stat ]] || continue
          # /proc/<pid>/stat field 10=minflt, field 12=majflt (0-indexed 9/11).
          read -r -a sf < /proc/$pid/stat 2>/dev/null || continue
          minflt=${sf[9]:-0}
          majflt=${sf[11]:-0}
          rss=$(awk '/^VmRSS:/ {print $2}' /proc/$pid/status 2>/dev/null)
          [[ -z "$rss" ]] && continue
          vol=$(awk '/^voluntary_ctxt_switches:/ {print $2}' /proc/$pid/status 2>/dev/null)
          invol=$(awk '/^nonvoluntary_ctxt_switches:/ {print $2}' /proc/$pid/status 2>/dev/null)
          comm=$(cat /proc/$pid/comm 2>/dev/null)
          [[ -z "$comm" ]] && comm="?"
          printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
            "$epoch" "$pid" "$minflt" "$majflt" "$rss" "${vol:-0}" "${invol:-0}" "$comm"
        done < <(pgrep -f "$pattern" 2>/dev/null)
        sleep "$interval"
      done
    ) </dev/null >>"$out" 2>/dev/null &

    sampler_pid=$!
    echo "$sampler_pid" > "$pidfile"
    exit 0
    ;;

  stop)
    if [[ ! -f "$pidfile" ]]; then
      exit 0
    fi
    pid=$(cat "$pidfile" 2>/dev/null || true)
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill -TERM "$pid" 2>/dev/null
      # Up to ~5s for clean exit.
      for _ in $(seq 1 10); do
        kill -0 "$pid" 2>/dev/null || break
        sleep 0.5
      done
      kill -0 "$pid" 2>/dev/null && kill -KILL "$pid" 2>/dev/null
    fi
    rm -f "$pidfile"
    exit 0
    ;;

  *)
    echo "usage: $0 {start|stop} <out_tsv>" >&2
    exit 1
    ;;
esac
