# Measure page faults triggered by callback functions

Page faults can be observed by probing the kernel function `handle_mm_fault`.
Similar to measuring pWCET, the scripts `measure_page_fault.py` and `measure_page_faults.py` measure the page faults triggered by callback functions.

### Example Usage of measuring page faults triggered by multiple callbacks

Open a terminal and run the Autoware rosbag simulation. When everything is loaded, open another terminal and run the following command:

```
sudo python3 measure_page_faults.py -i cb_names/callbacks_all_202502_part1.txt --ignore-cache
...
Take 10.000 seconds to collect data
```

Note that `measure_page_faults.py` runs for only 10 seconds.
This duration is intentional, as we are interested in the callbacks' behavior when real data arrives.

Next, open a third terminal to play the rosbag before the 10-second collection period ends.
Then return to the second terminal, and you will see output similar to:

```
...
autoware::lidar_centerpoint::LidarCenterPointNode::pointCloudCallback -- major faults: 0, minor faults 41377, handle_mm_fault_time_ns: 50,369,534 ns, #samples: 68
Write page_faults.csv
```

It shows that `pointCloudCallback` triggers 0 major page faults and 41377 minor page faults.
In addition, there are 68 calls of `pointCloudCallback` and the total time for processing page faults is 50,369,534 nanoseconds.
