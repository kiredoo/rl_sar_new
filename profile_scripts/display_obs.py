import rosbag
import numpy as np

# ----------------------------
# 1. DEFINE OBSERVATION ORDER
# ----------------------------
obs_order = [
    "ang_vel",
    "imu_rp",
    "delta_yaw",
    "commands_vx",
    "parkour_mode",
    "dof_pos",
    "dof_vel",
    "actions",
    "contact",
    "depth_latent",
    "lin_vel_latent",
    "priv_latent"
]

# ----------------------------
# 2. DEFINE DIMENSIONS
# ----------------------------
# Adjust these numbers if your dog uses different dims
obs_dim = {
    "ang_vel": 3,
    "imu_rp": 2,
    "delta_yaw": 1,
    "commands_vx": 3,      # vx, vy, yaw_rate
    "parkour_mode": 1,
    "dof_pos": 12,
    "dof_vel": 12,
    "actions": 12,
    "contact": 4,           # check if your bag uses 4, 6, or 8
    "depth_latent": 32,
    "lin_vel_latent": 9,
    "priv_latent": 20
}

# Build index map automatically
index_map = {}
start = 0
for key in obs_order:
    end = start + obs_dim[key]
    index_map[key] = (start, end)
    start = end

print("\n=== Observation Index Map ===")
for k, (i,j) in index_map.items():
    print(f"{k:15s} : [{i:3d} → {j:3d}]  (dim={obs_dim[k]})")


# ----------------------------
# 3. READ BAG FILE
# ----------------------------
bag = rosbag.Bag("real_data.bag")

print("\nReading /debug/clamped_obs ...")

count = 0
for _, msg, _ in bag.read_messages("/debug/clamped_obs"):

    obs = np.array(msg.data)

    print("\n==============================")
    print(f"Observation sample #{count}")
    print("==============================")

    # ----------------------------
    # 4. PRINT EACH SLICE
    # ----------------------------
    for key in obs_order:
        i, j = index_map[key]
        print(f"\n--- {key} ({i}:{j}) ---")
        print(obs[i:j])

    count += 1

    # Stop after first sample for debugging
    if count == 1:
        break

bag.close()