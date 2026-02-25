#!/usr/bin/env python3
import rospy, numpy as np, threading
from collections import deque
from std_msgs.msg import Float32MultiArray

TOPIC = "/debug/clamped_obs"
HIST  = 300  # points kept in buffer
PRINT_EVERY = 1

lock = threading.Lock()
tbuf = deque(maxlen=HIST)
obuf = deque(maxlen=HIST)
tick = 0

def cb(msg: Float32MultiArray):
    global tick
    data = np.asarray(msg.data, dtype=np.float32)
    print("shape:", data.shape)
    print("first 10:", data[:10])
    with lock:
        tick += 1
        tbuf.append(tick)
        obuf.append(data)
        if PRINT_EVERY > 0 and (tick % PRINT_EVERY == 0):
            print(data)

def main():
    rospy.init_node("print_clamped_obs")
    rospy.Subscriber(TOPIC, Float32MultiArray, cb, queue_size=50)

    rate = rospy.Rate(50)
    while not rospy.is_shutdown():
        rate.sleep()

if __name__ == "__main__":
    main()