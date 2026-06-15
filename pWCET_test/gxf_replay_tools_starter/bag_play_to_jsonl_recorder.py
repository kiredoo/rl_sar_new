#!/usr/bin/env python3

import argparse
import json
from pathlib import Path

import rclpy
from rclpy.node import Node
from rosidl_runtime_py.convert import message_to_ordereddict

from sensor_msgs.msg import Imu, Joy
from geometry_msgs.msg import Twist
from rosgraph_msgs.msg import Clock

from robot_msgs.msg import RobotState, RobotCommand


class JsonlRecorder(Node):
    def __init__(self, out_dir: Path):
        super().__init__("bag_play_to_jsonl_recorder")

        self.out_dir = out_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)

        self.files = {}
        self.counts = {}

        self.create_subscription(
            Imu,
            "/imu",
            lambda msg: self.write_msg("/imu", msg),
            100,
        )

        self.create_subscription(
            Twist,
            "/cmd_vel",
            lambda msg: self.write_msg("/cmd_vel", msg),
            100,
        )

        self.create_subscription(
            Joy,
            "/joy",
            lambda msg: self.write_msg("/joy", msg),
            100,
        )

        self.create_subscription(
            Clock,
            "/clock",
            lambda msg: self.write_msg("/clock", msg),
            100,
        )

        self.create_subscription(
            RobotState,
            "/robot_joint_controller/state",
            lambda msg: self.write_msg("/robot_joint_controller/state", msg),
            1000,
        )

        self.create_subscription(
            RobotCommand,
            "/robot_joint_controller/command",
            lambda msg: self.write_msg("/robot_joint_controller/command", msg),
            1000,
        )

        self.get_logger().info(f"Recording replay topics to: {self.out_dir}")

    def safe_name(self, topic: str) -> str:
        return topic.strip("/").replace("/", "__") or "root"

    def get_file(self, topic: str):
        if topic not in self.files:
            path = self.out_dir / f"{self.safe_name(topic)}.jsonl"
            self.files[topic] = open(path, "w", encoding="utf-8")
            self.counts[topic] = 0
            self.get_logger().info(f"Writing {topic} -> {path}")
        return self.files[topic]

    def write_msg(self, topic: str, msg):
        now_ns = self.get_clock().now().nanoseconds

        record = {
            "timestamp_ns": int(now_ns),
            "topic": topic,
            "type": msg.__class__.__module__ + "." + msg.__class__.__name__,
            "msg": message_to_ordereddict(msg),
        }

        f = self.get_file(topic)
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        self.counts[topic] += 1

    def close(self):
        for f in self.files.values():
            f.close()

        self.get_logger().info("Message counts:")
        for topic, count in sorted(self.counts.items()):
            self.get_logger().info(f"  {topic}: {count}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, help="Output JSONL directory")
    args = parser.parse_args()

    rclpy.init()
    node = JsonlRecorder(Path(args.out))

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.close()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
