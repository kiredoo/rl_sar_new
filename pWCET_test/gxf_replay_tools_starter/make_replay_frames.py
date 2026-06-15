#!/usr/bin/env python3
"""Create aligned replay frames using baseline command timestamps.

For every /robot_joint_controller/command timestamp, this script selects the latest
state, imu, and cmd_vel message at or before that timestamp. The output is a
JSONL file that is easy for a ReplayInputCodelet / Operator to consume.
"""

import argparse
import bisect
import json
from pathlib import Path


def load_jsonl(path: Path):
    records = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                records.append(json.loads(line))
    records.sort(key=lambda r: int(r["timestamp_ns"]))
    return records


def latest_at(records, timestamps, t_ns):
    if not records:
        return None
    idx = bisect.bisect_right(timestamps, t_ns) - 1
    if idx < 0:
        return None
    return records[idx]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jsonl-dir", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--max-frames", type=int, default=0, help="0 means all frames")
    args = parser.parse_args()

    d = Path(args.jsonl_dir).expanduser().resolve()
    paths = {
        "state": d / "robot_joint_controller__state.jsonl",
        "command": d / "robot_joint_controller__command.jsonl",
        "imu": d / "imu.jsonl",
        "cmd_vel": d / "cmd_vel.jsonl",
    }
    for name, path in paths.items():
        if not path.exists():
            raise FileNotFoundError(f"Missing {name}: {path}")

    state = load_jsonl(paths["state"])
    command = load_jsonl(paths["command"])
    imu = load_jsonl(paths["imu"])
    cmd_vel = load_jsonl(paths["cmd_vel"])

    state_ts = [int(r["timestamp_ns"]) for r in state]
    imu_ts = [int(r["timestamp_ns"]) for r in imu]
    cmd_vel_ts = [int(r["timestamp_ns"]) for r in cmd_vel]

    out_path = Path(args.out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    written = 0
    missing = {"state": 0, "imu": 0, "cmd_vel": 0}
    with open(out_path, "w", encoding="utf-8") as out:
        for i, cmd in enumerate(command):
            if args.max_frames and written >= args.max_frames:
                break
            t_ns = int(cmd["timestamp_ns"])
            st = latest_at(state, state_ts, t_ns)
            im = latest_at(imu, imu_ts, t_ns)
            cv = latest_at(cmd_vel, cmd_vel_ts, t_ns)

            if st is None:
                missing["state"] += 1
            if im is None:
                missing["imu"] += 1
            if cv is None:
                missing["cmd_vel"] += 1

            frame = {
                "frame_id": written,
                "timestamp_ns": t_ns,
                "state": st,
                "imu": im,
                "cmd_vel": cv,
                "baseline_command": cmd,
            }
            out.write(json.dumps(frame, ensure_ascii=False) + "\n")
            written += 1

    print(f"[DONE] wrote {written} frames -> {out_path}")
    print(f"[INFO] missing latest samples before command timestamp: {missing}")


if __name__ == "__main__":
    main()
