import torch
import torch.nn as nn
from rsl_rl.modules.actor_critic import Actor, StateHistoryEncoder, get_activation, ActorCriticRMA
from rsl_rl.modules.estimator import Estimator
from rsl_rl.modules.depth_backbone import DepthOnlyFCBackbone58x87, RecurrentDepthBackbone
import os


vision_model_path = "/home/lidar/rl_sar_new/rl_sar/policy/go2/extreme_parkour/vision_weight.pt"
device = torch.device('cpu')

# 1) 建好 depth_encoder，跟你原來一樣
vision_model = torch.load(vision_model_path, map_location=device)

depth_backbone = DepthOnlyFCBackbone58x87(None, 32, 512)
depth_encoder = RecurrentDepthBackbone(depth_backbone, None).to(device)

depth_encoder.load_state_dict(vision_model['depth_encoder_state_dict'])
depth_encoder.eval()

# 2) 做一個假的 input，讓 TorchScript 能 trace / script
#    RecurrentDepthBackbone.forward(depth_image, proprioception)
dummy_depth  = torch.randn(1, 58, 87, device=device)   # 對應 images: [B, 58, 87]
dummy_prop   = torch.randn(1, 53,     device=device)   # 你的 proprio 維度

# 3A) 用 script（較穩，支援 control flow）
scripted = torch.jit.script(depth_encoder)

# 或 3B) 用 trace（若 forward 沒有 if/loop 依賴 data）
# scripted = torch.jit.trace(depth_encoder, (dummy_depth, dummy_prop))

# 4) 存成 TorchScript `.pt`
jit_path = "depth_encoder_jit.pt"
scripted.save(jit_path)
print("Saved TorchScript depth encoder to:", jit_path)

