#!/bin/bash
cd ~/repo/autoware
source install/setup.bash
cd ~/repo/itriadv_aga/scripts/wcet
set -x
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
#"$PYTHON_BIN" measure_aw_wcet.py -i 1 --callback-names-txt callbacks_all_part3.txt --ld-preload /home/chtseng18/repo/mimalloc/out/libmimalloc.so.1.8

for sn in 2 3 1; do
  if [[ -f .measure_ets_cache.json ]]; then
    sudo rm .measure_ets_cache.json
  fi
  "$PYTHON_BIN" measure_aw_wcet.py -i 120 --callback-names-txt callbacks_all_part${sn}.txt --cool-down-seconds 5 --ld-preload /home/chtseng18/repo/mimalloc/out/libmimalloc.so.1.8
done
