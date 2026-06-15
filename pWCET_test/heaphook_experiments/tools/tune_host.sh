#!/bin/bash
# Active host tuning for measurement runs.
# Usage:
#   tools/tune_host.sh apply [--state-file PATH]
#   tools/tune_host.sh restore [--state-file PATH]
#   tools/tune_host.sh status [--state-file PATH]
#   tools/tune_host.sh write-state-into <run_dir>   # snapshot achieved state into env/tune_state.txt
#
# Convention: --state-file defaults to /tmp/aga_tune_state.<USER>.txt.
# Two-line key=value text format, deliberately not JSON, so a hand-edit
# during a stuck run is a one-grep operation.
#
# Sudo: governor + swappiness + drop_caches require root. The script
# tries `sudo -n` first (no prompt); if that fails it records what
# couldn't be applied and exits non-zero. Caller (the gate) decides
# whether a partial-tune run still counts.
set -euo pipefail

state_file_default="/tmp/aga_tune_state.${USER:-anon}.txt"
state_file="$state_file_default"

cmd="${1:-}"; shift || true
while [[ $# -gt 0 ]]; do
  case "$1" in
    --state-file) state_file="$2"; shift 2 ;;
    --) shift; break ;;
    *) break ;;
  esac
done

# --- helpers ---------------------------------------------------------

log() { printf '[tune_host] %s\n' "$*" >&2; }

# Run a privileged command. Returns 0 on success, 1 on failure.
# Prints the actual command before running so a reader can audit.
priv() {
  if sudo -n true 2>/dev/null; then
    log "sudo: $*"
    sudo "$@"
  else
    log "no sudo (no -n): $*  -- skipping"
    return 1
  fi
}

current_governor() {
  cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor 2>/dev/null \
    | sort -u | paste -sd, - || echo "N/A"
}

current_swappiness() {
  sysctl -n vm.swappiness 2>/dev/null || echo "N/A"
}

# --- apply -----------------------------------------------------------

apply_tuning() {
  if [[ -f "$state_file" ]]; then
    log "state file already exists at $state_file — refusing to overwrite"
    log "  (run 'restore' first, or pass --state-file to a fresh path)"
    exit 2
  fi

  local prior_gov prior_swappiness partial=false
  prior_gov="$(current_governor)"
  prior_swappiness="$(current_swappiness)"
  log "snapshot: governor=$prior_gov swappiness=$prior_swappiness"

  {
    echo "# tune_host.sh state — DO NOT HAND-EDIT unless you know what you're doing"
    echo "applied_at_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "user=${USER:-anon}"
    echo "host=$(hostname)"
    echo "prior_governor=$prior_gov"
    echo "prior_swappiness=$prior_swappiness"
  } > "$state_file"

  # Governor → performance on every online CPU.
  for f in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
    [[ -w "$f" ]] || { priv tee "$f" <<<"performance" >/dev/null || partial=true; continue; }
    echo "performance" > "$f" 2>/dev/null || { priv tee "$f" <<<"performance" >/dev/null || partial=true; }
  done

  # Swappiness → 1 (effectively no swap; kernel will only swap to avoid OOM).
  priv sysctl -q -w vm.swappiness=1 || partial=true

  # Drop page caches. Non-restorable by design; reflected as a drop event.
  sync
  priv tee /proc/sys/vm/drop_caches <<<"3" >/dev/null || partial=true

  {
    echo "achieved_governor=$(current_governor)"
    echo "achieved_swappiness=$(current_swappiness)"
    echo "drop_caches_attempted=true"
    echo "partial=$partial"
  } >> "$state_file"

  if $partial; then
    log "WARNING: tuning partial — governor or swappiness or drop_caches not fully applied"
    log "see $state_file for what was actually set"
    return 1
  fi
  log "applied; state saved to $state_file"
}

# --- restore ---------------------------------------------------------

restore_tuning() {
  if [[ ! -f "$state_file" ]]; then
    log "no state file at $state_file — nothing to restore"
    exit 0
  fi

  # Source-style read of the snapshot into local vars.
  local prior_gov prior_swappiness
  prior_gov=$(grep -E '^prior_governor=' "$state_file" | cut -d= -f2-)
  prior_swappiness=$(grep -E '^prior_swappiness=' "$state_file" | cut -d= -f2-)

  if [[ -z "$prior_gov" ]]; then
    log "state file at $state_file is malformed — refusing"
    exit 2
  fi

  # Restore governor. If the snapshot recorded multiple governors (comma-separated),
  # pick the first; that case shouldn't happen on a homogeneous box but is logged.
  local restore_gov="${prior_gov%%,*}"
  if [[ "$prior_gov" != "$restore_gov" ]]; then
    log "snapshot saw mixed governors ($prior_gov); restoring all CPUs to $restore_gov"
  fi
  for f in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
    echo "$restore_gov" > "$f" 2>/dev/null || priv tee "$f" <<<"$restore_gov" >/dev/null || true
  done

  if [[ -n "$prior_swappiness" && "$prior_swappiness" != "N/A" ]]; then
    priv sysctl -q -w "vm.swappiness=$prior_swappiness" || true
  fi

  rm -f "$state_file"
  log "restored from snapshot; state file removed"
}

# --- status ----------------------------------------------------------

status_tuning() {
  echo "current:"
  echo "  governor:     $(current_governor)"
  echo "  swappiness:   $(current_swappiness)"
  if [[ -f "$state_file" ]]; then
    echo
    echo "state file:   $state_file"
    sed 's/^/  /' "$state_file"
  else
    echo
    echo "state file:   absent (no apply in flight)"
  fi
}

# --- write-state-into (per-run snapshot) -----------------------------
# Copy the active state file into a run's env/, so the run is
# self-contained even if /tmp is wiped after the run.

write_state_into() {
  local run_dir="${1:-}"
  if [[ -z "$run_dir" || ! -d "$run_dir" ]]; then
    log "usage: tune_host.sh write-state-into <run_dir>"
    exit 2
  fi
  mkdir -p "$run_dir/env"
  if [[ -f "$state_file" ]]; then
    cp "$state_file" "$run_dir/env/tune_state.txt"
    {
      echo "# captured live values at write-state-into time"
      echo "live_governor=$(current_governor)"
      echo "live_swappiness=$(current_swappiness)"
    } >> "$run_dir/env/tune_state.txt"
    log "wrote $run_dir/env/tune_state.txt"
  else
    {
      echo "# tune_host.sh state file was absent at write-state-into time"
      echo "# this run was either grandfathered or tuned outside the harness"
      echo "live_governor=$(current_governor)"
      echo "live_swappiness=$(current_swappiness)"
      echo "partial=unknown"
    } > "$run_dir/env/tune_state.txt"
    log "wrote partial $run_dir/env/tune_state.txt (no live snapshot)"
  fi
}

# --- dispatch --------------------------------------------------------

case "$cmd" in
  apply)            apply_tuning ;;
  restore)          restore_tuning ;;
  status)           status_tuning ;;
  write-state-into) write_state_into "${1:-}" ;;
  ""|-h|--help)
    sed -n '1,15p' "$0"
    exit 0
    ;;
  *)
    log "unknown command: $cmd"
    exit 2
    ;;
esac
