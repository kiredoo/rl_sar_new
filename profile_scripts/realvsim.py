import rosbag
import numpy as np
import matplotlib.pyplot as plt
import matplotlib

# ----------------------------------------------------------
# Helper: Move window safely across backends
# ----------------------------------------------------------
def move_figure(fig, x, y, w, h):
    backend = matplotlib.get_backend()

    # ---- TkAgg ----
    if backend == "TkAgg":
        fig.canvas.manager.window.wm_geometry(f"{w}x{h}+{x}+{y}")

    # ---- Qt (Qt5Agg / QtAgg) ----
    elif backend in ["Qt5Agg", "QtAgg"]:
        try:
            fig.canvas.manager.window.setGeometry(x, y, w, h)
        except:
            fig.canvas.manager.window.move(x, y)
            fig.canvas.manager.window.resize(w, h)

    # ---- WXAgg ----
    elif backend == "WXAgg":
        fig.canvas.manager.window.SetPosition((x, y))
        fig.canvas.manager.window.SetSize((w, h))

    else:
        print(f"[WARN] Can't move window for backend: {backend}")

# ----------------------------------------------------------
# Load bags
# ----------------------------------------------------------
bag1 = rosbag.Bag('real_data.bag')
bag2 = rosbag.Bag('replay_real_data.bag')

data1 = []
data2 = []

for _, msg, _ in bag1.read_messages('/debug/action_dof_pos'):
    data1.append(msg.data)

for _, msg, _ in bag2.read_messages('/debug/action_dof_pos'):
    data2.append(msg.data)

data1 = np.array(data1)
data2 = np.array(data2)

# Split
actions1 = data1[:, :12]
jointpos1 = data1[:, 12:]

actions2 = data2[:, :12]
jointpos2 = data2[:, 12:]

# ----------------------------------------------------------
# SHIFT function
# ----------------------------------------------------------
SHIFT = 12  # adjust manually

def apply_shift(arr, shift):
    if shift <= 0:
        return arr
    pad = np.full((shift, arr.shape[1]), np.nan)
    shifted = np.vstack([pad, arr])
    return shifted[:arr.shape[0], :]

actions2_shifted = apply_shift(actions2, SHIFT)
jointpos2_shifted = apply_shift(jointpos2, SHIFT)

# ----------------------------------------------------------
# Window layout for a single monitor (divide into 4 areas)
# ----------------------------------------------------------
WIN_W = 900
WIN_H = 700

positions = [
    (0, 0),                 # top-left
    (WIN_W, 0),             # top-right
    (0, WIN_H),             # bottom-left
    (WIN_W, WIN_H)          # bottom-right
]

# ----------------------------------------------------------
# Plot 4 windows, each containing 3 joints
# ----------------------------------------------------------
groups = [
    (0, 1, 2),
    (3, 4, 5),
    (6, 7, 8),
    (9, 10, 11)
]

for window_index, joint_group in enumerate(groups):

    fig = plt.figure(figsize=(12, 8))
    fig.suptitle(f"Joint Group {window_index+1}: {joint_group}", fontsize=16)

    for subplot_index, j in enumerate(joint_group):
        plt.subplot(3, 1, subplot_index+1)

        plt.plot(actions1[:, j], label=f'real action j{j}')
        plt.plot(jointpos1[:, j], label=f'real joint j{j}')

        plt.plot(actions2_shifted[:, j], '--', label=f'replay action j{j} (shift={SHIFT})')
        plt.plot(jointpos2_shifted[:, j], '--', label=f'replay joint j{j} (shift={SHIFT})')

        plt.legend(loc='upper right')
        plt.xlabel("Time step")
        plt.ylabel("Value")

    plt.tight_layout(rect=[0, 0, 1, 0.95])

    # Move window to screen corner
    x, y = positions[window_index]
    move_figure(fig, x, y, WIN_W, WIN_H)

    plt.show(block=False)

# Keeps all windows open
plt.show()
