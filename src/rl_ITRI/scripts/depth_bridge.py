#!/usr/bin/env python3
"""
Subscribes to /depth_camera/depth/image_raw (sensor_msgs/Image, 32FC1),
applies preprocessing matching Isaac Sim training, and publishes to
/forward_depth_image (std_msgs/Float32MultiArray) for rl_sim consumption.

Pre-processing:
  1. Resize to TARGET_H × TARGET_W (64×64)
  2. Replace inf/nan and out-of-range with 0
  3. Clip to [0, 10] m
  4. Scale ×0.1 → [0, 1]
  5. Flatten row-major to float32 vector
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import Image
from std_msgs.msg import Float32MultiArray
import numpy as np
from cv_bridge import CvBridge
import cv2

TARGET_H = 54
TARGET_W = 96
MAX_DEPTH = 3.0


class DepthBridge(Node):
    def __init__(self):
        super().__init__('depth_bridge')
        self.bridge = CvBridge()

        sensor_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
        )

        self.sub = self.create_subscription(
            Image,
            '/depth_camera/depth/image_raw',
            self.callback,
            sensor_qos,
        )
        self.pub = self.create_publisher(Float32MultiArray, '/forward_depth_image', 1)
        self.get_logger().info('depth_bridge ready')

    def callback(self, msg: Image):
        try:
            depth = self.bridge.imgmsg_to_cv2(msg, desired_encoding='32FC1')
        except Exception as e:
            self.get_logger().warn(f'imgmsg_to_cv2 failed: {e}', throttle_duration_sec=5.0)
            return

        if depth.shape == (1, TARGET_H * TARGET_W) or depth.shape == (TARGET_H * TARGET_W, 1):
            # Gazebo sometimes flattens 64×64 into 1×4096 — reshape preserves spatial layout
            depth = depth.reshape(TARGET_H, TARGET_W)
        elif depth.shape != (TARGET_H, TARGET_W):
            self.get_logger().warn(
                f'Unexpected depth shape {depth.shape}, resizing to {TARGET_H}×{TARGET_W}',
                throttle_duration_sec=5.0,
            )
            depth = cv2.resize(depth, (TARGET_W, TARGET_H), interpolation=cv2.INTER_LINEAR)

        depth = np.where(np.isfinite(depth), depth, 0.0)
        depth = np.where((depth >= 0.3) & (depth <= MAX_DEPTH), depth, 0.0)
        depth /= 3.0  # scale to [0, 1]

        out = Float32MultiArray()
        out.data = depth.flatten().tolist()
        self.pub.publish(out)


def main():
    rclpy.init()
    node = DepthBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
