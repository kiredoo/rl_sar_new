#!/usr/bin/env python3
"""
Verify depth camera pipeline:
  - /depth_camera/depth/image_raw  : raw Gazebo depth (metres, inf = no hit)
  - /forward_depth_image           : preprocessed bridge output (54×96, scaled ÷3.0, range [0, 1])

Run:
  python3 src/rl_ITRI/scripts/test_depth.py
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import Image
from std_msgs.msg import Float32MultiArray
import numpy as np
from cv_bridge import CvBridge
import cv2

# Must match depth_bridge.py TARGET_H / TARGET_W
BRIDGE_H = 54
BRIDGE_W = 96
BRIDGE_MIN_DEPTH = 0.3
BRIDGE_MAX_DEPTH = 3.0  # metres; bridge scales ÷3.0 → output range [0, 1]


class DepthTester(Node):
    def __init__(self):
        super().__init__('depth_tester')
        self.bridge = CvBridge()

        # OpenCV windows for visualizing depth images
        cv2.namedWindow('Depth Raw', cv2.WINDOW_NORMAL)
        cv2.namedWindow('Depth Bridge', cv2.WINDOW_NORMAL)

        sensor_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
        )

        self.create_subscription(Image, '/depth_camera/depth/image_raw',
                                 self.raw_callback, sensor_qos)
        self.create_subscription(Float32MultiArray, '/forward_depth_image',
                                 self.bridge_callback, 1)

        self.get_logger().info('Listening on both topics — press Ctrl+C to stop')

    def raw_callback(self, msg: Image):
        try:
            depth = self.bridge.imgmsg_to_cv2(msg, desired_encoding='32FC1')
        except Exception as e:
            print(f'[RAW] CvBridge error: {e}')
            return

        total = depth.size
        finite_mask = np.isfinite(depth)
        finite_vals = depth[finite_mask]
        inf_count = total - finite_vals.size

        print(f'\n[RAW]  shape={depth.shape}  encoding={msg.encoding}')
        print(f'       total={total}  finite={finite_vals.size}  inf/nan={inf_count}')
        if finite_vals.size > 0:
            print(f'       depth range: {finite_vals.min():.3f} m  –  {finite_vals.max():.3f} m')
            print(f'       sample (first 8 finite): {[round(float(v), 3) for v in finite_vals.flat[:8]]}')
        else:
            print('       ALL pixels are infinity — camera sees empty space')

        # Prepare image for display: normalize finite values to 0-255 and apply colormap
        disp = depth.copy()
        finite_mask = np.isfinite(disp)
        # replace non-finite with 0 for visualization
        disp[~finite_mask] = 0.0

        norm = np.clip(disp, 0.0, BRIDGE_MAX_DEPTH) / BRIDGE_MAX_DEPTH
        img8 = (norm * 255.0).astype(np.uint8)
        img8[~finite_mask] = 0
        cv2.imshow('Depth Raw', img8)
        cv2.waitKey(1)

    def bridge_callback(self, msg: Float32MultiArray):
        data = np.array(msg.data, dtype=np.float32)
        nonzero = data[data > 0]
        expected = BRIDGE_H * BRIDGE_W

        print(f'\n[BRIDGE]  count={len(data)}  (expected {expected} = {BRIDGE_H}×{BRIDGE_W})')
        print(f'          zero={np.sum(data == 0)}  nonzero={len(nonzero)}')
        if len(nonzero) > 0:
            print(f'          value range: {nonzero.min():.3f}  –  {nonzero.max():.3f}'
                  f'  (valid depth [{BRIDGE_MIN_DEPTH}, {BRIDGE_MAX_DEPTH}] m, scaled ÷3.0)')
            print(f'          sample (first 8 nonzero): {[round(float(v), 3) for v in nonzero[:8]]}')
        else:
            print('          ALL zeros — bridge output is empty (inf input or bridge not running)')

        if len(data) != expected:
            print(f'          [WARN] unexpected count {len(data)}, cannot display')
            return

        grid = data.reshape(BRIDGE_H, BRIDGE_W)
        norm = np.clip(grid, 0.0, 1.0)  # already in [0, 1] after bridge ÷3.0 scaling
        img8 = (norm * 255.0).astype(np.uint8)  # invalid pixels (0) stay black naturally
        cv2.imshow('Depth Bridge', img8)
        cv2.waitKey(1)


def main():
    rclpy.init()
    node = DepthTester()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        # Close OpenCV windows
        try:
            cv2.destroyAllWindows()
        except Exception:
            pass
        rclpy.shutdown()


if __name__ == '__main__':
    main()
