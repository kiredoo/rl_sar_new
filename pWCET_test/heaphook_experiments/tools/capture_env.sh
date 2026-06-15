#!/bin/bash
# Fingerprint the host and source repos at experiment time.
# Usage:  capture_env.sh <run_dir>   (writes files into <run_dir>/env/)
#
# Files produced:
#   heaphook_git.txt   heaphook remote, branches, HEAD, short log
#   autoware_git.txt   autoware baseline repo state (if present as git)
#   caret_git.txt      caret repo state (if present as git; else version)
#   heaphook_build.txt built .so list under heaphook_ws build/ and install/
#   host_env.txt       kernel / CPU / mem / ROS / perf_event_paranoid
#   bag_metadata.txt   full metadata.yaml of the bag used
set -u

run_dir="${1:-}"
if [[ -z "$run_dir" || ! -d "$run_dir" ]]; then
  echo "usage: $0 <run_dir>   (e.g. runs/2026-04-20T09-30_stockpile-ab-repro2)" >&2
  exit 1
fi
env_dir="$run_dir/env"
mkdir -p "$env_dir"

HEAPHOOK_REPO="${HEAPHOOK_REPO:-$HOME/repo/claude_ws4/heaphook}"
HEAPHOOK_WS="${HEAPHOOK_WS:-$HOME/repo/claude_ws4/heaphook_ws}"
AUTOWARE_WS="${AUTOWARE_WS:-$HOME/repo/claude_ws4/autoware-2025.02_baseline_caret}"
CARET_DIR="${CARET_DIR:-$HOME/caret-v0.6.2}"
BAG_DIR="${BAG_DIR:-$HOME/autoware_map/sample-rosbag}"

capture_git() {
  local repo="$1" out="$2" label="$3"
  # Clear any stale file from a prior run.
  rm -f "$out" "${out}.MISSING"
  if [[ -d "$repo/.git" ]]; then
    {
      echo "# $label ($repo)"
      echo "## remote"
      git -C "$repo" remote -v
      echo
      echo "## current branch"
      git -C "$repo" branch --show-current
      echo
      echo "## HEAD"
      git -C "$repo" rev-parse HEAD
      echo
      echo "## status (short)"
      git -C "$repo" status --short | head -40
      echo
      echo "## last 5 commits"
      git -C "$repo" log --oneline -5
    } > "$out"
  else
    {
      echo "label:  $label"
      echo "repo:   ${repo:-<unset>}"
      if [[ -z "$repo" ]]; then
        echo "reason: env var pointing at the repo was unset (default also unresolved)"
      elif [[ ! -d "$repo" ]]; then
        echo "reason: directory does not exist"
      else
        echo "reason: directory exists but is not a git repo (no .git/)"
      fi
    } > "${out}.MISSING"
  fi
}

capture_git "$HEAPHOOK_REPO" "$env_dir/heaphook_git.txt" "heaphook"
capture_git "$AUTOWARE_WS"   "$env_dir/autoware_git.txt" "autoware baseline"
capture_git "$CARET_DIR"     "$env_dir/caret_git.txt"    "CARET"

rm -f "$env_dir/heaphook_build.txt" "$env_dir/heaphook_build.txt.MISSING"
if [[ -d "$HEAPHOOK_WS" ]]; then
  {
    echo "# heaphook build artefacts"
    echo "## build/"
    ls -la "$HEAPHOOK_WS/build/heaphook/"*.so 2>&1
    echo
    echo "## install/"
    ls -la "$HEAPHOOK_WS/install/heaphook/lib/"*.so 2>&1
  } > "$env_dir/heaphook_build.txt"
else
  {
    echo "HEAPHOOK_WS:  ${HEAPHOOK_WS:-<unset>}"
    echo "reason:       workspace directory does not exist"
    echo
    echo "This is a best-effort artefact. The only required input to"
    echo "capture_env.sh is HEAPHOOK_SO_PATH (or a HEAPHOOK_SO= line in"
    echo "one of the run's scripts/*.sh). See docs/HEAPHOOK_SEAM.md."
  } > "$env_dir/heaphook_build.txt.MISSING"
fi

{
  uname -a
  echo
  echo "# kernel.perf_event_paranoid"
  cat /proc/sys/kernel/perf_event_paranoid
  echo
  echo "# CPU"
  lscpu | grep -E "^(Model name|CPU\(s\)|Thread|Architecture|NUMA)"
  echo
  echo "# Mem"
  free -h
  echo
  echo "# ROS"
  echo "ROS_DISTRO=${ROS_DISTRO:-unset}"
  dpkg -l ros-humble-ros-core 2>/dev/null | tail -1
  echo
  echo "# ulimit"
  ulimit -a
} > "$env_dir/host_env.txt"

if [[ -f "$BAG_DIR/metadata.yaml" ]]; then
  cp "$BAG_DIR/metadata.yaml" "$env_dir/bag_metadata.txt"
else
  echo "bag metadata missing at $BAG_DIR/metadata.yaml" > "$env_dir/bag_metadata.txt"
fi

# --- host tunables ------------------------------------------------------
# Kernel + allocator knobs that change what the allocator actually does.
# THP settings change RSS accounting; vm.overcommit_* changes brk/mmap
# path; CPU governor changes context-switch cost; glibc version changes
# malloc heuristics. Always emit section headers so a reader knows we
# looked — record "N/A" or the failure reason when a source is missing.

read_or_na() {
  local path="$1"
  if [[ -r "$path" ]]; then
    cat "$path"
  else
    echo "N/A (unreadable: $path)"
  fi
}

{
  echo "# transparent hugepage"
  for f in /sys/kernel/mm/transparent_hugepage/enabled \
           /sys/kernel/mm/transparent_hugepage/defrag; do
    printf '%s: ' "$f"
    read_or_na "$f"
  done
  echo

  echo "# vm sysctls"
  for k in vm.swappiness vm.overcommit_memory vm.overcommit_ratio \
           vm.min_free_kbytes vm.max_map_count vm.dirty_ratio \
           vm.dirty_background_ratio; do
    v=$(sysctl -n "$k" 2>/dev/null || echo "N/A")
    echo "$k = $v"
  done
  echo

  echo "# cpu governor"
  govs=$(cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor 2>/dev/null | sort -u)
  if [[ -n "$govs" ]]; then
    echo "unique governors across CPUs:"
    echo "$govs"
  else
    echo "N/A (no cpufreq scaling_governor files)"
  fi
  echo

  echo "# glibc"
  ldd --version 2>&1 | head -2
  echo

  echo "# ASLR"
  echo "kernel.randomize_va_space = $(sysctl -n kernel.randomize_va_space 2>/dev/null || echo N/A)"
  echo

  echo "# meminfo (selected)"
  if [[ -r /proc/meminfo ]]; then
    grep -E '^(MemTotal|MemFree|MemAvailable|Buffers|Cached|SwapTotal|SwapFree|AnonPages|Slab|HugePages_Total|Hugepagesize):' /proc/meminfo
  else
    echo "N/A (unreadable /proc/meminfo)"
  fi
  echo

  echo "# MALLOC_* env (at capture time)"
  env | grep -E '^MALLOC_' || echo "(none set)"
  echo

  echo "# CPU mitigations (summary)"
  if compgen -G '/sys/devices/system/cpu/vulnerabilities/*' > /dev/null; then
    for f in /sys/devices/system/cpu/vulnerabilities/*; do
      printf '%s: ' "$(basename "$f")"
      head -1 "$f" 2>/dev/null || echo "N/A"
    done
  else
    echo "N/A (no vulnerabilities/ entries)"
  fi
} > "$env_dir/host_tunables.txt"

# --- binary fingerprints -------------------------------------------------
# Binary artefacts (the preloaded .so, the bag file) don't live in this
# repo and aren't covered by git. A sha256 committed into env/ extends
# the evidence chain to them. A `.MISSING` marker replaces a hash when
# the resource isn't locatable — silent failure is forbidden per
# METHODOLOGY §3.4.

# Resolve the path to the preloaded .so. Priority:
#   1. $HEAPHOOK_SO_PATH (explicit env var)
#   2. A line like `HEAPHOOK_SO="..."` in any launcher under
#      $run_dir/scripts/*.sh (expanded via bash so $HOME etc. resolve).
resolve_so_path() {
  if [[ -n "${HEAPHOOK_SO_PATH:-}" ]]; then
    echo "$HEAPHOOK_SO_PATH"
    return
  fi
  for s in "$run_dir/scripts"/*.sh; do
    [[ -f "$s" ]] || continue
    local raw
    raw=$(grep -m1 '^[[:space:]]*HEAPHOOK_SO=' "$s" 2>/dev/null || true)
    [[ -n "$raw" ]] || continue
    raw="${raw#*=}"
    raw="${raw%\"}"
    raw="${raw#\"}"
    # Expand embedded vars like $HOME.
    local expanded
    eval "expanded=\"$raw\""
    echo "$expanded"
    return
  done
}

rm -f "$env_dir/heaphook_so.sha256" "$env_dir/heaphook_so.sha256.MISSING"
so_path=$(resolve_so_path)
if [[ -n "$so_path" && -f "$so_path" ]]; then
  sha256sum "$so_path" > "$env_dir/heaphook_so.sha256"
else
  {
    echo "HEAPHOOK_SO_PATH (env):  ${HEAPHOOK_SO_PATH:-<unset>}"
    echo "resolved path:           ${so_path:-<unresolved>}"
    echo "reason:                  file does not exist"
  } > "$env_dir/heaphook_so.sha256.MISSING"
fi

rm -f "$env_dir/bag.sha256" "$env_dir/bag.sha256.MISSING"
if [[ -f "$BAG_DIR/metadata.yaml" ]]; then
  sha256sum "$BAG_DIR/metadata.yaml" > "$env_dir/bag.sha256"
else
  {
    echo "BAG_DIR: $BAG_DIR"
    echo "reason:  $BAG_DIR/metadata.yaml does not exist"
  } > "$env_dir/bag.sha256.MISSING"
fi

echo "captured env fingerprints into $env_dir/"
ls -la "$env_dir"
