# Measure Hz for callback functions

Using eBPF to measure callback frequency is more efficient than using `ros2 topic hz <topic>`.
The scripts `measure_hz.py` and `measure_hzs.py` perform this measurement. Their usage is similar to `measure_et.py` and `measure_ets.py`.

### Example usage:

Open a terminal and run the Autoware rosbag simulation. When everything is loaded, open another terminal and run the following command:

```
sudo python3 measure_hzs.py -i cb_names/callbacks_all_202502_part1.txt --ignore-cache
...
WARNING:root:Attach uprobes for autoware::lidar_centerpoint::LidarCenterPointNode::pointCloudCallback, mangled_name: _ZN8autoware17lidar_centerpoint20LidarCenterPointNode18pointCloudCallbackESt10shared_ptrIKN11sensor_msgs3msg12PointCloud2_ISaIvEEEE, elf: /home/chtseng/repo/autoware/build/autoware_lidar_centerpoint/libautoware_lidar_centerpoint_component.so
```

Next, open a third terminal to play the rosbag.
When the bag replay finishes, return to the second terminal, press Ctrl+C, and you will see output similar to:

```
...
autoware::lidar_centerpoint::LidarCenterPointNode::pointCloudCallback -- #probings: 244, first_probing_time_ns: 784779514357475, last_probing_time_ns: 784809090993108, hz: 8.22
```

This indicates that `pointCloudCallback` runs at 8.22 Hz.
