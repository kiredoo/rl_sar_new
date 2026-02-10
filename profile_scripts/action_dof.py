#!/usr/bin/env python3
import rospy, numpy as np, threading
from collections import deque
from std_msgs.msg import Float32MultiArray
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation


TOPIC = "/debug/action_dof_pos"
KDOF  = 12
HIST  = 300

lock = threading.Lock()
tbuf = deque(maxlen=HIST)                       # seconds
abuf = [deque(maxlen=HIST) for _ in range(KDOF)]
qbuf = [deque(maxlen=HIST) for _ in range(KDOF)]

t0 = None  # time origin (rospy.Time)

def cb(msg: Float32MultiArray):
    global t0
    data = np.asarray(msg.data, dtype=np.float32)
    if data.size < 2 * KDOF:
        return

    a = data[:KDOF]
    q = data[KDOF:2*KDOF]

    now = rospy.Time.now()
    with lock:
        if t0 is None:
            t0 = now
        t_sec = (now - t0).to_sec()
        tbuf.append(t_sec)
        for i in range(KDOF):
            abuf[i].append(float(a[i]))
            qbuf[i].append(float(q[i]))

def main():
    import matplotlib
    matplotlib.rcParams['figure.raise_window'] = False

    rospy.init_node("plot_action_vs_q")
    rospy.Subscriber(TOPIC, Float32MultiArray, cb, queue_size=50)

    fig, axs = plt.subplots(4, 3, figsize=(12, 8), sharex=True)
    import matplotlib as mpl
    backend = mpl.get_backend()

    if backend.startswith('TkAgg'):
        fig.canvas.manager.window.wm_attributes("-topmost", 0)
    elif backend.startswith('Qt5Agg') or backend.startswith('QtAgg'):
        from PyQt5 import QtCore
        w = fig.canvas.manager.window
        w.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, False)
        w.show()
    elif backend.startswith('WXAgg'):
        w = fig.canvas.manager.window
        w.Raise(False)

    axs = axs.ravel()
    lines = []
    for i, ax in enumerate(axs[:KDOF]):
        la, = ax.plot([], [], label="action")
        lq, = ax.plot([], [], label="q")
        ax.set_title(f"Joint {i}")
        ax.grid(True)
        lines.append((la, lq))
    axs[0].legend(loc="upper right")

    y_lim = [
        [-0.5, 0.5],
        [0.0, 2.0],
        [-3.0, 0.0],
    ]

    def update(_):
        with lock:
            if not tbuf:
                return []
            tt = list(tbuf)
            for i, (la, lq) in enumerate(lines):
                ya = list(abuf[i])
                yq = list(qbuf[i])
                la.set_data(tt, ya)
                lq.set_data(tt, yq)

                y_min, y_max = tuple(y_lim[i % 3])
                pad = 0.05 * max(1e-6, (y_max - y_min))
                axs[i].set_xlim(tt[0], tt[-1])
                axs[i].set_ylim(y_min - pad, y_max + pad)

        return [a for pair in lines for a in pair]

    ani = FuncAnimation(fig, update, interval=50, blit=False)
    plt.tight_layout()
    plt.show(block=False)

    rate = rospy.Rate(50)
    while not rospy.is_shutdown():
        plt.pause(0.02)
        rate.sleep()

if __name__ == "__main__":
    main()
