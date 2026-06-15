#!/bin/bash
# One-command refresh of all derived artefacts.
#
# Runs compute_summary for each run directory, then the cross-config
# aggregate. Idempotent — safe to re-run after editing configs.tsv.
#
# Usage:
#   tools/make-all.sh                    # process every runs/*/ dir
#   tools/make-all.sh runs/<id> ...      # specific run dirs only
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"

runs=("$@")
if [[ ${#runs[@]} -eq 0 ]]; then
  mapfile -t runs < <(find runs -maxdepth 1 -mindepth 1 -type d | sort)
fi

echo "==> compute_summary.sh for ${#runs[@]} run(s)"
for r in "${runs[@]}"; do
  if [[ ! -d "$r/raw" ]]; then
    echo "  skip $r (no raw/)"
    continue
  fi
  echo "  $r"
  tools/compute_summary.sh "$r"
done

echo "==> aggregate_configs.py (cross-config csv + xlsx)"
tools/aggregate_configs.py

echo
echo "Done. Outputs:"
echo "  runs/<id>/derived/summary.{txt,tsv}"
echo "  derived_cross/aggregate.{csv,xlsx}"
echo "  derived_cross/definitions.md"
