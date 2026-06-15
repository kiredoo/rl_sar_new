#!/bin/bash
# Gather per-PID fragmentation TSVs emitted by libheaphook_sampler.so.
#
# The sampler writes one /tmp/heaphook_frag_<pid>.tsv per Autoware process.
# After a run this script moves them under the run directory so they
# become part of the immutable raw/ payload.
#
# Usage:  merge_frag_tsv.sh <run_dir> <arm>
#   run_dir  absolute or relative path to runs/<id>/
#   arm      A / B / C / D  (matches snapshot_rss.sh tag)
#
# Files are copied then removed from /tmp; a failed copy aborts before
# any /tmp file is deleted. Safe to re-run: existing dest files are
# overwritten (cp -f).

set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 <run_dir> <arm>" >&2
  exit 2
fi

run_dir="$1"
arm="$2"

if [[ ! -d "$run_dir" ]]; then
  echo "merge_frag_tsv: run_dir does not exist: $run_dir" >&2
  exit 1
fi

dest="$run_dir/raw/$arm/frag"
mkdir -p "$dest"

shopt -s nullglob
sources=(/tmp/heaphook_frag_*.tsv)

if [[ ${#sources[@]} -eq 0 ]]; then
  echo "merge_frag_tsv: no /tmp/heaphook_frag_*.tsv found; nothing to merge" >&2
  exit 0
fi

# Phase 1: copy everything. If any cp fails, exit before deleting /tmp.
for src in "${sources[@]}"; do
  cp -f -p "$src" "$dest/"
done

# Phase 2: cp succeeded for all — now safe to remove originals.
rm -f "${sources[@]}"

echo "merge_frag_tsv: moved ${#sources[@]} file(s) to $dest"
