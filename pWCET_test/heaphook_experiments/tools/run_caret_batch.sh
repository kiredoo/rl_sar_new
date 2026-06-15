#!/usr/bin/env bash
# run_caret_batch.sh — wrapper around caret_report/sample_autoware/batch_run.sh.
#
# Idempotent setup + trace_data_list lifecycle + new-output detection.
#
# Usage:
#   tools/run_caret_batch.sh <trace_path1> [<trace_path2> ...]
#
# Outputs (stdout, last lines):
#   NEW_OUTPUT_STORAGE_DIR=<absolute path under caret_report/sample_autoware/output_storage/>
#   ... one line per new dir produced.
#
# See: docs/MEASUREMENT_PROTOCOL.md and reports/caret_jitter_gate.md.

set -euo pipefail

CARET_REPO="${CARET_REPO:-${HOME}/repo/caret_report}"
CARET_INSTALL="${CARET_INSTALL:-${HOME}/caret-v0.6.2/install/setup.bash}"
SAMPLE_DIR="${CARET_REPO}/sample_autoware"
TS="$(date +%Y%m%d_%H%M00)"
LOG="/tmp/caret_batch_${TS}.log"

TARGET_PATH_JSON=""
while [[ "${1:-}" == --* ]]; do
  case "$1" in
    --target) TARGET_PATH_JSON="$2"; shift 2 ;;
    --) shift; break ;;
    *) echo "[ERR] unknown flag: $1" >&2; exit 2 ;;
  esac
done

if (( $# < 1 )); then
  echo "[ERR] usage: $0 [--target <target_path.json>] <trace_path1> [<trace_path2> ...]" >&2
  exit 2
fi

# Absolute-ify trace paths NOW, before any `cd`. batch_run.sh later resolves
# the trace_data_list.txt entries relative to sample_autoware/, which would
# break any caller-relative input.
ABS_TRACES=()
for tp in "$@"; do
  ABS_TRACES+=( "$(realpath -m -- "$tp")" )
done

# --- Step 1: idempotent setup check -----------------------------------------
# `caret_analyze` is exposed via PYTHONPATH from sourcing `~/caret-v0.6.2/install/setup.bash`
# (it does NOT live in the venv). We test importability AFTER sourcing both venv + setup.bash.
# `bt2` (babeltrace2) is the venv's responsibility — that's what setup.sh actually installs.
need_setup=0
if [[ ! -d "${CARET_REPO}/venv" ]]; then
  need_setup=1
else
  # shellcheck disable=SC1091
  if ! ( set +u; source "${CARET_REPO}/venv/bin/activate"; \
         python3 -c 'import bt2' ) >/dev/null 2>&1; then
    need_setup=1
  fi
fi
if (( need_setup )); then
  echo "[INFO] caret_report venv missing or bt2 not importable → running setup.sh"
  ( cd "${CARET_REPO}" && ./setup.sh )
fi

# --- Step 2: source env (analysis-only — no LD_PRELOAD libcaret) ------------
# install/setup.bash exposes ros2 + python ament packages used by report scripts.
# setenv_caret.bash additionally enables LD_PRELOAD libcaret + lttng daemon for
# TRACE CAPTURE — which is dead weight (and can perturb timing) for analysis-only.
# Disable -u while sourcing: ROS / colcon setup scripts reference COLCON_TRACE etc.
# unconditionally and trip on `set -u`.
set +u
# shellcheck disable=SC1091
source "${CARET_REPO}/venv/bin/activate"
# shellcheck disable=SC1090
source "${CARET_INSTALL}" >/dev/null
set -u

# --- Step 3: trace_data_list lifecycle --------------------------------------
cd "${SAMPLE_DIR}"
mkdir -p trace_data_list_legacy

# Move any prior dated list out of the way (skip current session's, skip generic).
shopt -s nullglob
for prev in trace_data_list_*.txt; do
  case "${prev}" in
    "trace_data_list_${TS}.txt") ;;
    *) git mv -- "${prev}" "trace_data_list_legacy/${prev}" 2>/dev/null \
         || mv -- "${prev}" "trace_data_list_legacy/${prev}" ;;
  esac
done
shopt -u nullglob

NEW_LIST="trace_data_list_${TS}.txt"
: > "${NEW_LIST}"
for abs_path in "${ABS_TRACES[@]}"; do
  printf '%s\n' "${abs_path}" >> "${NEW_LIST}"
done
cp -f "${NEW_LIST}" trace_data_list.txt

echo "[INFO] active trace_data_list.txt:"
sed 's/^/  /' trace_data_list.txt

# --- Step 4: snapshot output_storage/ before run ----------------------------
SNAP_BEFORE="$(mktemp)"
find output_storage -mindepth 1 -maxdepth 1 -type d -printf '%f\n' \
  | sort > "${SNAP_BEFORE}"

# --- Step 5: run analysis ---------------------------------------------------
# If --target is given, bypass batch_run.sh (which doesn't accept --target)
# and call run.sh directly per trace, matching batch_run.sh's "snapshot output/
# before+after, mv new dirs into output_storage/" behaviour.
echo "[INFO] running analysis — log: ${LOG}"
rc=0
if [[ -n "${TARGET_PATH_JSON}" ]]; then
  echo "[INFO] custom target: ${TARGET_PATH_JSON}" | tee -a "${LOG}"
  for tp in "${ABS_TRACES[@]}"; do
    snap_before="$(mktemp)"
    find output -mindepth 1 -maxdepth 1 -type d -printf '%f\n' 2>/dev/null \
      | sort > "$snap_before"
    ./run.sh --target "${TARGET_PATH_JSON}" "$tp" 2>&1 | tee -a "${LOG}"
    rc_step="${PIPESTATUS[0]}"
    (( rc_step != 0 )) && rc="$rc_step"
    snap_after="$(mktemp)"
    find output -mindepth 1 -maxdepth 1 -type d -printf '%f\n' 2>/dev/null \
      | sort > "$snap_after"
    while IFS= read -r d; do
      [[ -z "$d" ]] && continue
      mv "output/$d" "output_storage/" 2>&1 | tee -a "${LOG}"
    done < <(comm -13 "$snap_before" "$snap_after")
    rm -f "$snap_before" "$snap_after"
  done
else
  ./batch_run.sh 2>&1 | tee "${LOG}"
  rc="${PIPESTATUS[0]}"
fi

# --- Step 6: detect new tags via after-vs-before diff -----------------------
SNAP_AFTER="$(mktemp)"
find output_storage -mindepth 1 -maxdepth 1 -type d -printf '%f\n' \
  | sort > "${SNAP_AFTER}"

NEW_TAGS="$(comm -13 "${SNAP_BEFORE}" "${SNAP_AFTER}")"
rm -f "${SNAP_BEFORE}" "${SNAP_AFTER}"

# --- Step 7: emit machine-readable result -----------------------------------
if [[ -z "${NEW_TAGS}" ]]; then
  echo "[WARN] no new output_storage/ entries detected"
else
  while IFS= read -r tag; do
    [[ -z "${tag}" ]] && continue
    echo "NEW_OUTPUT_STORAGE_DIR=${SAMPLE_DIR}/output_storage/${tag}"
  done <<< "${NEW_TAGS}"
fi

exit "${rc}"
