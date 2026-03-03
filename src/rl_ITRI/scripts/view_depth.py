#!/usr/bin/env python3
import numpy as np
import matplotlib.pyplot as plt
import sys

# 用法: python view_depth.py depth_xxx.npy
path = sys.argv[1]

depth = np.load(path)      # shape: (H, W), values in [-0.5, 0.5]

plt.figure(figsize=(6, 4))

# 用灰階顯示，並固定範圍在 [-0.5, 0.5]
im = plt.imshow(
    depth,
    cmap="gray",
    vmin=-0.5,
    vmax=0.5,
)

plt.title("Depth Gazebo")
plt.xlabel("x (pixels)")
plt.ylabel("y (pixels)")

# 右邊加 value bar
cbar = plt.colorbar(im, fraction=0.03, pad=0.05)
cbar.set_label("Depth value normalized [-0.5, 0.5]")
cbar.set_ticks([-0.5, -0.25, 0.0, 0.25, 0.5])
plt.tight_layout()
plt.show()
