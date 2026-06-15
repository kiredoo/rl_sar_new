# tools/

Reusable, authoritative scripts for running experiments. These are the
source of truth; `new_run.sh` seeds each run's `scripts/` directory from
here so that every run has a frozen snapshot of what was actually executed.

> Adding a **new allocator variant** (not just re-running an existing one)?
> Start with [docs/ADDING_A_NEW_VARIANT.md](../docs/ADDING_A_NEW_VARIANT.md) —
> it walks the full chain from branching `heaphook/` to a new row in
> `derived_cross/aggregate.csv`.

| File | Role |
|---|---|
| `new_run.sh`         | Scaffold a new run directory. Always the starting point. |
| `snapshot_rss.sh`    | One-shot per-process counter dump to `/proc/{stat,status}`. Authoritative copy; seeded into each run. |
| `run_ab_phase.sh`    | Orchestrates one arm: wait-for-bringup → pre-snapshot → bag play → post-snapshot → SIGINT. Authoritative copy; seeded into each run. |
| `capture_env.sh`     | Fingerprints host + heaphook/autoware/caret git state + bag metadata into `runs/<id>/env/`. |
| `compute_summary.sh` | Parses `raw/<arm>/aw_*_{pre,post}.txt` footers into `derived/summary.txt` and `summary.tsv`. |
| `compare_runs.sh`    | Merges `derived/summary.tsv` from several runs into one markdown table (optional `--baseline <run_id>:<arm>` for Δ%). |
| `aggregate_configs.py` | Reads `configs.tsv` (logical name → run_id:arm) and emits `derived_cross/aggregate.{csv,xlsx}` — the cross-config comparison workbook. |
| `make-all.sh`        | One-command refresh: `compute_summary.sh` for each run + `aggregate_configs.py`. Safe to re-run after editing configs.tsv. |
| `merge_frag_tsv.sh`  | Phase 2.5 — gather per-PID fragmentation TSVs written by `libheaphook_sampler.so` from `/tmp/` into `runs/<id>/raw/<arm>/frag/`. |
| `post_process_frag.py` | Phase 2.5 — summarise merged frag TSVs into `derived/frag_summary.tsv` (per-PID row + per-arm footer with mean/stddev frag_ratio). |

## Skill shortcut

For the full arm execution sequence (scaffold → launch → snapshot → derive → aggregate), the `/run-arm` skill at `.claude/skills/run-arm/SKILL.md` wraps steps 1–5 of the typical flow below. (Renamed from `/run-ab-arm` on 2026-04-30; the old name was a 2-arm-test legacy.)

## Typical run flow

```bash
# 1. Scaffold
tools/new_run.sh hybrid-unfixed
# → creates runs/2026-04-20T09-30_hybrid-unfixed/ with MANIFEST stub + seeded scripts

RUN=runs/2026-04-20T09-30_hybrid-unfixed

# 2. Execute arms (tag = arm label, e.g. C, D)
bash $RUN/scripts/sim_play_bag_mp_hybrid.sh > $RUN/raw/C/aw_C_t1.log 2>&1 &
bash $RUN/scripts/run_ab_phase.sh C $RUN/raw/C > $RUN/raw/C/aw_C_phase.log 2>&1
gzip $RUN/raw/C/aw_C_t1.log

# 3. Fingerprint env
tools/capture_env.sh $RUN

# 4. Derive summary
tools/compute_summary.sh $RUN

# 5. Fill MANIFEST.md, update INDEX.md, flip symlink
ln -sfn $(basename $RUN | xargs -I{} echo runs/{}) latest
```

## Invariants these scripts depend on

- Launch processes match the pgrep filter in `snapshot_rss.sh`. If a
  future Autoware release changes node binary names, update the filter
  in the authoritative copy — do **not** hand-edit frozen copies inside
  past runs.
- `/proc/$pid/stat` field 10 = minflt, field 12 = majflt. This is Linux
  kernel API and has been stable since 2.6.
- `kernel.perf_event_paranoid` is read-only from our scripts; we work
  around it via `/proc`, not by raising the limit.

## When to update these scripts

| Change | Action |
|---|---|
| Bug fix in filter / counter parsing | Edit in place; affects future runs only (old `runs/<id>/scripts/` still has the pre-fix bytes, which reflects what that run actually used). |
| New metric to capture | Edit `snapshot_rss.sh` and `compute_summary.sh` together; bump a `SCHEMA_VERSION` comment in both if you want cross-run compatibility checking. |
| Protocol change (e.g. different bringup wait) | Edit in place; note in the next run's MANIFEST "Deviations from protocol" if different from earlier runs. |
