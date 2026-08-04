#!/usr/bin/env python3
import math
import os
import sys
import os.path as osp
import json
import time
from collections import OrderedDict

import numpy as np
import torch
import torch.nn.functional as F
from torch.autograd import Variable
import pyrealsense2 as rs
import cv2

# --- ROS 2 Imports ---
import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32MultiArray
from sensor_msgs.msg import Image
from cv_bridge import CvBridge

if os.uname().machine in ["x86_64", "amd64"]:
    sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "x86"))
elif os.uname().machine == "aarch64":
    sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "aarch64"))

@torch.no_grad()
def resize2d(img, size):
    return (F.adaptive_avg_pool2d(Variable(img), size)).data

class VisionExtremeParkourNode(Node):
    def __init__(self, cfg, args):
        super().__init__('vision_extreme_parkour')
        
        self.cfg = cfg
        self.args = args
        self.rs_resolution = (args.width, args.height)
        self.rs_fps = args.fps
        self.use_sim = args.sim
        self.show_display = bool(args.display and os.environ.get("DISPLAY"))
        
        self.depth_input_topic = args.depth_topic
        self.forward_depth_image_topic = "/forward_depth_image"
        self._last_frame_warn_time = 0.0
        self._latest_raw_depth_m = None
        
        self.bridge = CvBridge()
        self.parse_args()
        
        # 啟動硬體或設定模擬
        if not self.use_sim: 
            self.start_pipeline() 
        self.start_ros_handlers()
        
        # ROS 2 Timer (100Hz 檢查相機畫面)
        if not self.use_sim:
            loop_duration = 0.01 
            self.main_timer = self.create_timer(loop_duration, self.main_loop)

    def parse_args(self):
        # 影像縮放目標解析度：[Height, Width] -> 54 高, 96 寬
        self.output_resolution = [54, 96]
        
        # Policy preprocessing must match training:
        # valid depth: 0.3 ~ 3.0 m; invalid/out-of-range depth: 0.0
        self.depth_range = [0.0, 3.0]
        self.min_valid_depth = 0.3

    def start_pipeline(self):
        self.rs_pipeline = rs.pipeline()
        self.rs_config = rs.config()
        self.rs_config.enable_stream(
            rs.stream.depth,
            self.rs_resolution[0], self.rs_resolution[1],
            rs.format.z16, self.rs_fps
        )
        self.rs_profile = self.rs_pipeline.start(self.rs_config)
        self.rs_align = rs.align(rs.stream.depth)

        # RealSense Filters
        self.rs_hole_filling_filter = rs.hole_filling_filter()
        self.rs_spatial_filter = rs.spatial_filter()
        self.rs_spatial_filter.set_option(rs.option.filter_magnitude, 2)
        self.rs_spatial_filter.set_option(rs.option.filter_smooth_alpha, 0.75)
        self.rs_spatial_filter.set_option(rs.option.filter_smooth_delta, 1)
        self.rs_spatial_filter.set_option(rs.option.holes_fill, 4)
        self.rs_temporal_filter = rs.temporal_filter()
        self.rs_temporal_filter.set_option(rs.option.filter_smooth_alpha, 0.75)
        self.rs_temporal_filter.set_option(rs.option.filter_smooth_delta, 1)
        self.rs_filters = [
            self.rs_hole_filling_filter,
            self.rs_spatial_filter,
            self.rs_temporal_filter,
        ]

    def start_ros_handlers(self):
        qos_profile = 1
        if not self.use_sim:
            self.depth_input_pub = self.create_publisher(Image, self.depth_input_topic, qos_profile)
        else:
            self.depth_sub = self.create_subscription(Image, self.depth_input_topic, self.depth_image_callback, qos_profile)

        self.forward_depth_image_pub = self.create_publisher(Float32MultiArray, self.forward_depth_image_topic, qos_profile)
        self.get_logger().info(
            "ROS 2 handlers started (Unit: meters, valid range: 0.3-3.0m, "
            "invalid -> 0, valid scaled by /3, no cropping)"
        )
        
    def depth_image_callback(self, msg):
        try:
            # 模擬環境傳入的深度圖標準單位即為公尺 (m)
            depth_m = self.bridge.imgmsg_to_cv2(msg, desired_encoding="passthrough").astype(np.float32)
        except Exception as e:
            self.get_logger().error(f"CV Bridge Error: {e}")
            return
            
        self._latest_raw_depth_m = depth_m.copy()
        
        depth_image_pyt = torch.from_numpy(depth_m).unsqueeze(0)
        depth_image_pyt = self.process_depth_tensor(depth_image_pyt)
        
        self.publish_depth_data(depth_image_pyt)

    def plot_depth_data(self, depth_data_flat):
        h, w = self.output_resolution 
        depth_scaled = depth_data_flat.reshape(h, w) # 數值已經是 0~1
        
        scale_factor = 6
        processed_u8 = (np.clip(depth_scaled, 0.0, 1.0) * 255).astype(np.uint8)
        processed_resized = cv2.resize(
            processed_u8, (w * scale_factor, h * scale_factor), interpolation=cv2.INTER_NEAREST
        )

        if self._latest_raw_depth_m is not None:
            # 將原始公尺數值歸一化以供顯示
            raw_norm = np.clip(
                self._latest_raw_depth_m,
                self.depth_range[0],
                self.depth_range[1],
            ) / self.depth_range[1]
            raw_u8 = (raw_norm * 255).astype(np.uint8)
            raw_resized = cv2.resize(
                raw_u8,
                (processed_resized.shape[1], processed_resized.shape[0]),
                interpolation=cv2.INTER_NEAREST,
            )
        else:
            raw_resized = np.zeros_like(processed_resized)

        raw_bgr = cv2.cvtColor(raw_resized, cv2.COLOR_GRAY2BGR)
        processed_bgr = cv2.cvtColor(processed_resized, cv2.COLOR_GRAY2BGR)

        label_color = (255, 255, 255)
        cv2.putText(raw_bgr, "raw depth (m)", (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, label_color, 2)
        cv2.putText(processed_bgr, f"scaled 0-1 {w}x{h}", (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, label_color, 2)

        preview = np.hstack([raw_bgr, processed_bgr])

        cv2.imshow("Depth Data (Scaled 0-1)", preview)
        key = cv2.waitKey(1) & 0xFF

        if key == ord(' '):  
            save_dir = os.path.join(os.getcwd(), "depth_debug")
            os.makedirs(save_dir, exist_ok=True)
            ts = time.strftime("%Y%m%d_%H%M%S")
            base_name = f"depth_{ts}"

            npy_path = os.path.join(save_dir, base_name + ".npy")
            np.save(npy_path, depth_scaled)

            png_path = os.path.join(save_dir, base_name + ".png")
            cv2.imwrite(png_path, preview)
            self.get_logger().info(f"Saved depth frame: {npy_path} and {png_path}")

    def get_depth_frame(self):
        if self.use_sim: return None 
        
        timeout_ms = max(1000, int((1000.0 / max(float(self.rs_fps), 1.0)) * 5.0))
        try:
            rs_frame = self.rs_pipeline.wait_for_frames(timeout_ms)
        except RuntimeError as e:
            now = time.monotonic()
            if now - self._last_frame_warn_time > 1.0:
                self.get_logger().warning(f"RealSense frame timeout: {e}")
                self._last_frame_warn_time = now
            return None

        depth_frame = rs_frame.get_depth_frame()
        
        if not depth_frame:
            now = time.monotonic()
            if now - self._last_frame_warn_time > 1.0:
                self.get_logger().warning("No RealSense depth frame")
                self._last_frame_warn_time = now
            return None
        
        for rs_filter in self.rs_filters:
            depth_frame = rs_filter.process(depth_frame)
        
        raw_depth_mm = np.asanyarray(depth_frame.get_data()).astype(np.float32)
            
        # RealSense 原始資料為 mm，除以 1000 轉換為公尺 (m)
        raw_depth_m = raw_depth_mm / 1000.0
        self._latest_raw_depth_m = raw_depth_m.copy()
        
        depth_image_pyt = torch.from_numpy(raw_depth_m).unsqueeze(0)
        depth_image_pyt = self.process_depth_tensor(depth_image_pyt)

        # 還原為原始公尺資料發佈給本地的 depth_input_pub (不影響 0~1 的前向輸出)
        depth_input_data = (depth_image_pyt.detach().cpu().numpy() * self.depth_range[1]).astype(np.float32)[0] 
        
        depth_input_msg = self.bridge.cv2_to_imgmsg(depth_input_data, encoding="32FC1")
        depth_input_msg.header.stamp = self.get_clock().now().to_msg()
        depth_input_msg.header.frame_id = "d435_sim_depth_link"
        self.depth_input_pub.publish(depth_input_msg)

        return depth_image_pyt
    
    def process_depth_tensor(self, depth_image_pyt):
        # 1. Mark only finite depths in [0.3, 3.0] m as usable.
        valid_mask = (
            torch.isfinite(depth_image_pyt)
            & (depth_image_pyt >= self.min_valid_depth)
            & (depth_image_pyt <= self.depth_range[1])
        )

        # 2. Match training representation:
        #    invalid/out-of-range -> 0.0; valid depth remains in meters.
        depth_image_pyt = torch.where(
            valid_mask,
            depth_image_pyt,
            torch.zeros_like(depth_image_pyt),
        )

        # 3. Scale valid depth by 1/3.0.
        depth_image_pyt = depth_image_pyt / self.depth_range[1]

        # 4. Resize to 54x96 using the same average pooling as training.
        depth_image_pyt = resize2d(depth_image_pyt, self.output_resolution)

        return depth_image_pyt

    def publish_depth_data(self, depth_data):
        flat = depth_data.flatten().detach().cpu().numpy()  
        
        msg = Float32MultiArray()
        msg.data = flat.tolist()
        self.forward_depth_image_pub.publish(msg)

        if self.show_display:
            try:
                self.plot_depth_data(flat)
            except Exception as e:
                self.get_logger().error(f"Failed to visualize depth data: {e}")

    def main_loop(self):
        depth_image_pyt = self.get_depth_frame()
        if depth_image_pyt is not None:
            self.publish_depth_data(depth_image_pyt)


def main(args=None):
    rclpy.init(args=sys.argv)
    
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--logdir", type=str, default=None)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--sim", action="store_true")
    parser.add_argument("--display", action="store_true")
    parser.add_argument("--depth-topic", type=str, default="/depth_cam/depth/image_raw")

    parsed_args, unknown = parser.parse_known_args()

    config_dict = {}
    if parsed_args.logdir is not None:
        config_path = osp.join(parsed_args.logdir, "config.json")
        if osp.exists(config_path):
            with open(config_path, "r") as f:
                config_dict = json.load(f, object_pairs_hook=OrderedDict)

    vision_node = VisionExtremeParkourNode(config_dict, parsed_args)

    try:
        rclpy.spin(vision_node)
    except KeyboardInterrupt:
        pass
    finally:
        if hasattr(vision_node, 'rs_pipeline'):
            vision_node.rs_pipeline.stop()
        vision_node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()

if __name__ == "__main__":
    main()
