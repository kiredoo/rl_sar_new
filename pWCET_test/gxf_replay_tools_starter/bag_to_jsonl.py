#!/usr/bin/env python3
"""Convert selected ROS 2 bag topics to JSONL.

Usage:
  source /opt/ros/humble/setup.bash
  source ~/rl_sar_new/rl_sar/install/setup.bash
  python3 bag_to_jsonl.py --bag /path/to/bag_dir --out /path/to/out_dir

This script requires the workspace that defines custom message types to be sourced.
"""

import argparse
import json
from pathlib import Path

import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
from rosidl_runtime_py.convert import message_to_ordereddict

DEFAULT_TOPICS = [
    "/imu",
    "/cmd_vel",
    "/robot_joint_controller/state",
    "/robot_joint_controller/command",
]


def safe_name(topic: str) -> str:
    name = topic.strip("/") or "root"
    return name.replace("/", "__")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bag", required=True, help="Path to rosbag directory")
    parser.add_argument("--out", required=True, help="Output directory")
    parser.add_argument("--topics", nargs="*", default=DEFAULT_TOPICS)
    args = parser.parse_args()

    bag_path = Path(args.bag).expanduser().resolve()
    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    reader = rosbag2_py.SequentialReader()
    storage_options = rosbag2_py.StorageOptions(uri=str(bag_path), storage_id="sqlite3")
    converter_options = rosbag2_py.ConverterOptions(
        input_serialization_format="cdr",
        output_serialization_format="cdr",
    )
    reader.open(storage_options, converter_options)

    topic_types = {meta.name: meta.type for meta in reader.get_all_topics_and_types()}
    selected = set(args.topics)
    writers = {}
    counts = {topic: 0 for topic in selected if topic in topic_types}

    try:
        for topic in selected:
            if topic not in topic_types:
                print(f"[WARN] topic not found in bag: {topic}")
                continue
            out_file = out_dir / f"{safe_name(topic)}.jsonl"
            writers[topic] = open(out_file, "w", encoding="utf-8")
            print(f"[INFO] {topic} ({topic_types[topic]}) -> {out_file}")

        while reader.has_next():
            topic, data, timestamp = reader.read_next()
            if topic not in writers:
                continue
            msg_type = get_message(topic_types[topic])
            msg = deserialize_message(data, msg_type)
            record = {
                "timestamp_ns": int(timestamp),
                "topic": topic,
                "type": topic_types[topic],
                "msg": message_to_ordereddict(msg),
            }
            writers[topic].write(json.dumps(record, ensure_ascii=False) + "\n")
            counts[topic] += 1
    finally:
        for fh in writers.values():
            fh.close()

    print("[DONE] counts:")
    for topic, count in sorted(counts.items()):
        print(f"  {topic}: {count}")


if __name__ == "__main__":
    main()
