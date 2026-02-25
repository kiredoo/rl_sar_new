#!/usr/bin/env python3
import math
import rospy

from std_msgs.msg import Float32MultiArray
from sensor_msgs.msg import Image, CameraInfo

# from unitree_ros2_real import UnitreeRos2Real  # 若不需要可移除
# ROS1 沒有 rclpy.qos，直接拿掉
import os, sys
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
import ros_numpy as rnp
import random

from collections import deque
import matplotlib.pyplot as plt
import threading

if os.uname().machine in ["x86_64", "amd64"]:
    sys.path.append(os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "x86",
    ))
elif os.uname().machine == "aarch64":
    sys.path.append(os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "aarch64",
    ))


@torch.no_grad()
def resize2d(img, size):
    return (F.adaptive_avg_pool2d(Variable(img), size)).data


class VisualHandlerNode(object):
    """ A wrapper class for the realsense camera """
    def __init__(self,
            cfg: dict,
            cropping: list = [0, 0, 0, 0], # top, bottom, left, right (origin repo 106x60, H_fov 87)
            rs_resolution: tuple = (640, 480), # width, height for the realsense camera
            rs_fps: int= 30,
            depth_input_topic= "/camera/forward_depth",
            camera_info_topic= "/camera/camera_info",
            forward_depth_image_topic= "/forward_depth_image",
            use_sim=False,
            vision_delay_ms: int = 0
        ):
        
        self.cfg = cfg
        self.cropping = cropping
        self.rs_resolution = rs_resolution
        self.rs_fps = rs_fps
        self.depth_input_topic = depth_input_topic
        self.camera_info_topic = camera_info_topic
        self.forward_depth_image_topic = forward_depth_image_topic
        self.use_sim = use_sim
        self.vision_delay_ms = int(max(0, vision_delay_ms))

        self.parse_args()
        if not self.use_sim: self.start_pipeline() 
        self.start_ros_handlers()
        
        # 以 fps 決定發佈頻率；若 fps 無效就 30Hz
        pub_hz = int(self.rs_fps) if int(self.rs_fps) > 0 else 30
        if self.vision_delay_ms <= 0: # 只有在有設定延遲時，才需要 Buffer 和 Timer
            self._delay_buffer = None
            self._buf_lock = None
            self._pub_timer = None
        else:
             # 佇列容量：可涵蓋 delay + 0.5s buffer，避免長延遲時取不到幀
            buf_secs = (self.vision_delay_ms / 1000.0) + 0.5
            cap = max(int(math.ceil(pub_hz * buf_secs)), pub_hz, 1)
            self._delay_buffer = deque(maxlen=cap)
            self._buf_lock = threading.Lock()
            # 固定頻率定時回調：決定要發佈哪一幀（最接近 now-delay）
            self._pub_timer = rospy.Timer(rospy.Duration(1.0 / pub_hz), self._delay_publish_timer_cb)

        # debug
        # depth_data_sim = np.load('/home/unitree/Desktop/extreme_parkour_onboard/depth_image_random.npy')
        # depth_data_sim = np.load('/home/unitree/Desktop/extreme_parkour_onboard/depth_image_sim_336-11_flat.npy')
        # self.depth_data_sim = torch.from_numpy(depth_data_sim.astype(np.float32)).unsqueeze(0).unsqueeze(0)

    def parse_args(self):
        # self.output_resolution = self.cfg["depth"]["resized"]
        self.output_resolution = [58, 87]
        depth_range = [0.0, 2.0]
        self.depth_range = (depth_range[0], depth_range[1] * 1000)  # [m] -> [mm]

    def start_pipeline(self):
        self.rs_pipeline = rs.pipeline()
        self.rs_config = rs.config()
        self.rs_config.enable_stream(
            rs.stream.depth,
            self.rs_resolution[0],
            self.rs_resolution[1],
            rs.format.z16,
            self.rs_fps,
        )
        self.rs_profile = self.rs_pipeline.start(self.rs_config)

        self.rs_align = rs.align(rs.stream.depth)

        # RealSense filters
        # self.rs_decimation_filter = rs.decimation_filter()
        # self.rs_decimation_filter.set_option(rs.option.filter_magnitude, 6)
        self.rs_hole_filling_filter = rs.hole_filling_filter()
        self.rs_spatial_filter = rs.spatial_filter()
        self.rs_spatial_filter.set_option(rs.option.filter_magnitude, 5)
        self.rs_spatial_filter.set_option(rs.option.filter_smooth_alpha, 0.75)
        self.rs_spatial_filter.set_option(rs.option.filter_smooth_delta, 1)
        self.rs_spatial_filter.set_option(rs.option.holes_fill, 4)
        self.rs_temporal_filter = rs.temporal_filter()
        self.rs_temporal_filter.set_option(rs.option.filter_smooth_alpha, 0.75)
        self.rs_temporal_filter.set_option(rs.option.filter_smooth_delta, 1)
        # using a list of filters to define the filtering order
        self.rs_filters = [
            # self.rs_decimation_filter,
            self.rs_hole_filling_filter,
            self.rs_spatial_filter,
            self.rs_temporal_filter,
        ]

    def start_ros_handlers(self):
        if not self.use_sim:
            # RealSense 模式 : publish depth Image
            self.depth_input_pub = rospy.Publisher(
                self.depth_input_topic,
                Image,
                queue_size=1,
            )
        else:
            # Sim 模式: subscribe depth Image from Gazebo
            self.depth_sub = rospy.Subscriber(
                self.depth_input_topic,
                Image,
                self.depth_image_callback,
                queue_size=1,
            )

        self.forward_depth_image_pub = rospy.Publisher(
            self.forward_depth_image_topic,
            Float32MultiArray,
            queue_size=1,
        )
        
        rospy.loginfo("ros handlers started")
        
    def depth_image_callback(self, msg):
        # depth Image from Gazebo Sim (32FC1/16UC1) # m
        depth_np = rnp.numpify(msg).astype(np.float32)*1000.0  # m -> mm
        depth_np = np.nan_to_num(depth_np, nan=self.depth_range[0]) # mm
        # print(depth_np)
        # nan_count = np.isnan(depth_np).sum()
        # rospy.logwarn_throttle(1.0,
        #     f"[RAW] nan={nan_count}, "
        #     f"min={np.nanmin(depth_np):.3f}, max={np.nanmax(depth_np):.3f}"
        # )
        depth_image_pyt = torch.from_numpy(depth_np).unsqueeze(0)

        depth_image_pyt = self.process_depth_tensor(depth_image_pyt)
        # publish the depth image input to ros topic
        rospy.loginfo_once("depth range: {}-{}".format(*self.depth_range))

        depth_image_pyt -= 0.5 # [-0.5, 0.5])
        
        # debug
        # self.plot_depth_data(depth_image_pyt)
        self.publish_depth_data(depth_image_pyt)

            
    def plot_depth_data(self, depth_data_flat):
        """Show normalized depth and save when SPACE is pressed."""
        h, w = self.output_resolution 
        # 將一維陣列 reshape 回二維 (H, W)
        depth_norm = depth_data_flat.reshape(h, w) # [-0.5, 0.5]
        depth_show = depth_norm + 0.5 # Restore to [0, 1] for visualization

        # zoom（same as extreme-parkour-onboard）
        scale_factor = 6
        depth_resized = cv2.resize(
            depth_show,
            (w * scale_factor, h * scale_factor),
            interpolation=cv2.INTER_NEAREST,
        )

        cv2.imshow(f"Depth Data (Delay {self.vision_delay_ms}ms)", depth_resized)
        key = cv2.waitKey(1) & 0xFF

        if key == ord(' '):   # SPACE pressed
            import time, os
            save_dir = os.path.join(os.getcwd(), "depth_debug")
            os.makedirs(save_dir, exist_ok=True)

            ts = time.strftime("%Y%m%d_%H%M%S")
            base_name = f"depth_{ts}"

            # 1) 存原始 normalized 值（-0.5 ~ 0.5），方便之後用 matplotlib 分析
            npy_path = os.path.join(save_dir, base_name + ".npy")
            np.save(npy_path, depth_norm)

            # 2) 存視覺化影像（0~1 → 0~255 灰階）
            depth_u8 = (np.clip(depth_show, 0.0, 1.0) * 255).astype(np.uint8)
            depth_u8_resized = cv2.resize(
                depth_u8,
                (w * scale_factor, h * scale_factor),
                interpolation=cv2.INTER_NEAREST,
            )
            png_path = os.path.join(save_dir, base_name + ".png")
            cv2.imwrite(png_path, depth_u8_resized)

            rospy.loginfo(f"Saved depth frame: {npy_path} and {png_path}")



    def publish_camera_info_callback(self):
        self.camera_info_msg.header.stamp = rospy.Time.now()
        rospy.loginfo_once("camera info published")
        self.camera_info_pub.publish(self.camera_info_msg)

    def get_depth_frame(self):
        if self.use_sim: return None # sim mode, the depth is obtained from the subscriber
        # read from pyrealsense2, preprocess and write the model embedding to the buffer
        latency_range  = [0.08, 0.142]
        rs_frame = self.rs_pipeline.wait_for_frames(int( latency_range[1] * 1000 )) # ms
        
        depth_frame = rs_frame.get_depth_frame()
        if not depth_frame:
            rospy.logerr_throttle(1.0, "No depth frame")
            return
        
        for rs_filter in self.rs_filters:
            depth_frame = rs_filter.process(depth_frame)
        
        depth_image_pyt = torch.from_numpy(np.asanyarray(depth_frame.get_data()).astype(np.float32)).unsqueeze(0)
        # depth_image_np = np.rot90(depth_image_np, k= 2) # k = 2 for rotate 90 degree twice   
        
        # apply torch filters
        # if self.cropping != [0, 0, 0, 0]:
        #     top, bottom, left, right = self.cropping
        #     h, w = depth_image_pyt.shape[1:]
        #     row_end = h - bottom   # crop bottom
        #     col_end = w - right    # crop right
        #     depth_image_pyt = depth_image_pyt[:, top:row_end, left:col_end]

        # depth_image_pyt = torch.clip(depth_image_pyt, self.depth_range[0], self.depth_range[1]) / (self.depth_range[1] - self.depth_range[0])
        # depth_image_pyt = resize2d(depth_image_pyt, self.output_resolution)
        depth_image_pyt = self.process_depth_tensor(depth_image_pyt)

        # publish the depth image input to ros topic
        rospy.loginfo_once("depth range: {}-{}".format(*self.depth_range))
        depth_input_data = (
            depth_image_pyt.detach().cpu().numpy() * (self.depth_range[1] - self.depth_range[0]) + self.depth_range[0]).astype(np.uint16)[0] # (h, w) unit [mm]
        # print('depth input data: ', depth_input_data.min(), depth_input_data.max())
        
        depth_image_pyt -= 0.5 # [-0.5, 0.5])

        depth_input_msg = rnp.msgify(Image, depth_input_data.astype(np.float32), encoding= "32FC1")
        depth_input_msg.header.stamp = rospy.Time.now()
        depth_input_msg.header.frame_id = "d435_sim_depth_link"
        self.depth_input_pub.publish(depth_input_msg)
        rospy.loginfo_once("depth input published")

        return depth_image_pyt
    
    def process_depth_tensor(self, depth_image_pyt): # depth_image_pyt: torch (1, H, W), 單位 mm
        if torch.isnan(depth_image_pyt).any(): rospy.logwarn_throttle(1.0, "NaN detected !!")
        # cropping
        if self.cropping != [0, 0, 0, 0]:
            top, bottom, left, right = self.cropping
            h, w = depth_image_pyt.shape[1:]
            row_end = h - bottom   # crop bottom
            col_end = w - right    # crop right
            depth_image_pyt = depth_image_pyt[:, top:row_end, left:col_end]

        # clip + normalize + resize
        depth_image_pyt = torch.clip(depth_image_pyt, self.depth_range[0], self.depth_range[1]) / (self.depth_range[1] - self.depth_range[0])
        depth_image_pyt = resize2d(depth_image_pyt, self.output_resolution)

        return depth_image_pyt


    def publish_depth_data(self, depth_data):
        flat = depth_data.flatten().detach().cpu().numpy()  # (H*W,)
        if self.vision_delay_ms <= 0:
            self._publish_array_now(flat)
        else:
            ts = time.monotonic()
            with self._buf_lock:
                self._delay_buffer.append((ts, flat))
    
    def _delay_publish_timer_cb(self, event):
        # 有延遲：找最接近 now - delay 的幀
        delay_s = self.vision_delay_ms / 1000.0
        now_mono = time.monotonic()
        candidate = None

        with self._buf_lock:
            # 不斷 pop 左側直到超過目標延遲（保留最後一個 <= delay 的）
            while self._delay_buffer and (now_mono - self._delay_buffer[0][0]) >= delay_s:
                candidate = self._delay_buffer.popleft()
            # 若沒有剛好達標，就用目前隊首作為最接近的
            if candidate is None and self._delay_buffer:
                candidate = self._delay_buffer[0]

        if candidate is not None:
            self._publish_array_now(candidate[1])

    def _publish_array_now(self, flat_arr):
        # publish delayed frame
        msg = Float32MultiArray()
        msg.data = flat_arr.tolist()

        self.forward_depth_image_pub.publish(msg)
        rospy.loginfo_once("depth data published")

        # visualize the DELAYED frame for debug
        try:
            self.plot_depth_data(flat_arr)
        except Exception as e:
            rospy.logerr("Failed to visualize depth data: %s", e)

    def main_loop(self, event=None):
        depth_image_pyt = self.get_depth_frame()
        if depth_image_pyt is not None:
            # depth_image_pyt = torch.zeros_like(depth_image_pyt) + 0.5
            # depth_image_pyt = self.depth_data_sim
            self.publish_depth_data(depth_image_pyt)
        else:
            rospy.logwarn_throttle(1.0, "One frame of depth latent is not acquired")

@torch.inference_mode()
def main(args):
    rospy.init_node("depth_image", anonymous=False)

    # assert args.logdir is not None, "Please provide a logdir"        
    config_dict = {}
    config_path = str()
    if args.logdir is not None:
        config_path = osp.join(args.logdir, "config.json")
        if osp.exists(config_path):
            with open(config_path, "r") as f:
                config_dict = json.load(f, object_pairs_hook=OrderedDict)
        else: print(f"Warning: logdir provided but config.json not found at {config_path}")
    else: print("No logdir provided, using default params")
    print(config_dict)
    if args.logdir is not None: print(f"Loaded config: {config_path}, BUT NOT USED") # TODO
        
    device = "cpu"
    # duration = config_dict["sensor"]["forward_camera"]["refresh_duration"] # in sec
    duration = 0.01 # duration

    visual_node = VisualHandlerNode(
        cfg= config_dict,
        cropping= [args.crop_top, args.crop_bottom, args.crop_left, args.crop_right],
        rs_resolution= (args.width, args.height),
        rs_fps= args.fps,
        use_sim=args.sim,
        vision_delay_ms=args.delay,
    )

    if args.loop_mode == "while" and not args.sim:
        while not rospy.is_shutdown():
            main_loop_time = time.monotonic()
            visual_node.main_loop()
            elapsed = time.monotonic() - main_loop_time
            if elapsed < duration: time.sleep(duration - elapsed)
    elif args.loop_mode == "timer" and not args.sim: 
        rospy.Timer(rospy.Duration(duration), visual_node.main_loop)
        rospy.spin()
    else: # sim mode: rely on subscriber callbacks
        rospy.spin()

    # 正常來說程式結束會自動釋放資源, 如果要確實關掉 pipeline：
    # visual_node.rs_pipeline.stop()
    

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()

    parser.add_argument("--logdir",
        type= str,
        default= None,
        help= "The directory which contains the config.json and model_*.pt files",
    )
    parser.add_argument("--height",
        type= int,
        default= 480,
        help= "The height of the realsense image",
    )
    parser.add_argument("--width",
        type= int,
        default= 640,
        help= "The width of the realsense image",
    )
    parser.add_argument("--fps",
        type= int,
        default= 30,
        help= "The fps request to the rs pipeline",
    )
    parser.add_argument("--crop_left",
        type= int,
        default= 80, # 28
        help= "num of pixel to crop in the original pyrealsense readings."
    )
    parser.add_argument("--crop_right",
        type= int,
        default= 36, # 36
        help= "num of pixel to crop in the original pyrealsense readings."
    )
    parser.add_argument("--crop_top",
        type= int,
        default= 60, # 48
        help= "num of pixel to crop in the original pyrealsense readings."
    )
    parser.add_argument("--crop_bottom",
        type= int,
        default= 100,
        help= "num of pixel to crop in the original pyrealsense readings."
    )
    parser.add_argument("--loop_mode", type= str, default= "timer",
        choices= ["while", "timer"],
        help= "Select which mode to run the main policy control iteration",
    )
    parser.add_argument("--sim",
        action="store_true",
        help="Use simulated depth from Gazebo (subscribe to /camera/forward_depth) instead of RealSense"
    )
    parser.add_argument("--delay", 
        type=int, default=0,
        help="Vision delay in milliseconds for /forward_depth_image. 0 = no delay."
    )

    args = parser.parse_args()
    main(args)
