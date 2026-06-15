### Measure malloc/free patterns of a callback function

We use eBPF programs to monitor dynamic memory allocation by tracing `malloc` and `free` calls. Its purpose is to determine how frequently and how much memory a callback function requests. Since memory allocation involves system calls, context switches may occur, making execution time less deterministic. Ideally, callback functions should avoid `malloc`/`free` operations entirely.

### Example 1: Show explicit malloc/free calls

Let us use the callback function `autoware::ndt_scan_matcher::NDTScanMatcher::callback_sensor_points` as an example.

Open a terminal and run the Autoware rosbag simulation. When everything is loaded, open another terminal and run the following command:

```
sudo python3 measure_malloc_free_pattern.py -i autoware::ndt_scan_matcher::NDTScanMatcher::callback_sensor_points
...
WARNING:root:Find autoware::ndt_scan_matcher::NDTScanMatcher::callback_sensor_points in /home/chtseng/repo/autoware/build/autoware_ndt_scan_matcher/libautoware_ndt_scan_matcher.so
...
```

Next, open a third terminal to play the rosbag. The previous terminal will show logs like

```
malloc,512,0x74ecb0003f60  # allocate 512 bytes at address 0x74ecb0003f60
malloc,27,0x74ecd4001860
free,0x74ecd40015b0
free,0x74ecbc003350
...
```

### Example 2: Show allocated size in histogram

This example is similar to Example 1, except that it prints the histogram of allocated sizes for every invocation of a callback function.
Like Example 1, run the Autoware rosbag simulation first, and then in the second terminal, run

```
sudo python3 measure_malloc_as_histogram.py -i autoware::ndt_scan_matcher::NDTScanMatcher::callback_sensor_points
...
```

Play the rosbag in the third terminal. The second terminal will show logs like

```
----------------------------------------
Allocate 49,117 bytes
[2^4, 2^5):  59
[2^5, 2^6):  11
[2^6, 2^7):  3
[2^7, 2^8):  5
[2^8, 2^9):  3
[2^9, 2^10):  2
[2^14, 2^15):  2
```

This indicates that during an invocation of the callback function, 49,117
bytes are dynamically allocated. There are 59 malloc calls that request 16 to 31 bytes. Other rows are interpreted in the same way.

### Example 3: Show allocated size in histogram for multiple callback functions

Let's show the total number of malloc calls, grouped by the requested size, for multiple callback functions.

Like Example 1, run the Autoware rosbag simulation in the first terminal, and then in the second terminal, run

```
sudo python3 measure_malloc_as_histogram_multi_cb.py -i cb_names/callbacks_all_202502_part1.txt --no-print-cb-malloc
```
where `cb_names/callbacks_all_202502_part1.txt` contains a list of callback function names, one per line.
The option `--no-print-cb-malloc` reduces the printed logs by not showing the histogram for each invocation of a callback.

In the third terminal, play the rosbag. When bag replaying finishes, returns to the second terminal and
press Ctrl+C. The output would like the following:

```
----------------------------------------
Sampled for 51.832 seconds
Total number of malloc calls for each size bucket:
[2^0, 2^1):  4
[2^2, 2^3):  3429
[2^3, 2^4):  204305
[2^4, 2^5):  407608
[2^5, 2^6):  176205
[2^6, 2^7):  153060
[2^7, 2^8):  73087
[2^8, 2^9):  63359
[2^9, 2^10):  9459
[2^10, 2^11):  6907
[2^11, 2^12):  5671
[2^12, 2^13):  7340
[2^13, 2^14):  3514
[2^14, 2^15):  32308
[2^15, 2^16):  112
[2^16, 2^17):  57
[2^17, 2^18):  10
[2^18, 2^19):  14
[2^19, 2^20):  2234
[2^20, 2^21):  2
----------------------------------------
Max number of malloc calls for each size bucket
[2^0, 2^1):  4 - claimed by b'autoware::ekf_localizer::EKFLocalizer::timer_callback'
[2^2, 2^3):  606 - claimed by b'autoware::lidar_centerpoint::LidarCenterPointNode::pointCloudCallback'
[2^3, 2^4):  41441 - claimed by b'autoware::euclidean_cluster::VoxelGridBasedEuclideanClusterNode::onPointCloud'
[2^4, 2^5):  29852 - claimed by b'autoware::euclidean_cluster::VoxelGridBasedEuclideanClusterNode::onPointCloud'
[2^5, 2^6):  6360 - claimed by b'autoware::euclidean_cluster::VoxelGridBasedEuclideanClusterNode::onPointCloud'
[2^6, 2^7):  6246 - claimed by b'autoware::euclidean_cluster::VoxelGridBasedEuclideanClusterNode::onPointCloud'
[2^7, 2^8):  1778 - claimed by b'autoware::euclidean_cluster::VoxelGridBasedEuclideanClusterNode::onPointCloud'
[2^8, 2^9):  774 - claimed by b'autoware::euclidean_cluster::VoxelGridBasedEuclideanClusterNode::onPointCloud'
[2^9, 2^10):  158 - claimed by b'autoware::euclidean_cluster::VoxelGridBasedEuclideanClusterNode::onPointCloud'
[2^10, 2^11):  101 - claimed by b'autoware::euclidean_cluster::VoxelGridBasedEuclideanClusterNode::onPointCloud'
[2^11, 2^12):  63 - claimed by b'autoware::euclidean_cluster::VoxelGridBasedEuclideanClusterNode::onPointCloud'
[2^12, 2^13):  57 - claimed by b'autoware::euclidean_cluster::VoxelGridBasedEuclideanClusterNode::onPointCloud'
[2^13, 2^14):  50 - claimed by b'autoware::euclidean_cluster::VoxelGridBasedEuclideanClusterNode::onPointCloud'
[2^14, 2^15):  8079 - claimed by b'autoware::euclidean_cluster::VoxelGridBasedEuclideanClusterNode::onPointCloud'
[2^15, 2^16):  22 - claimed by b'autoware::lidar_centerpoint::LidarCenterPointNode::pointCloudCallback'
[2^16, 2^17):  8 - claimed by b'autoware::euclidean_cluster::VoxelGridBasedEuclideanClusterNode::onPointCloud'
[2^17, 2^18):  2 - claimed by b'autoware::lidar_centerpoint::LidarCenterPointNode::pointCloudCallback'
[2^18, 2^19):  3 - claimed by b'autoware::euclidean_cluster::VoxelGridBasedEuclideanClusterNode::onPointCloud'
[2^19, 2^20):  4 - claimed by b'autoware::ekf_localizer::EKFLocalizer::timer_callback'
[2^20, 2^21):  1 - claimed by b'autoware::freespace_planner::FreespacePlannerNode::onTimer'
```

The first histogram shows the number of malloc calls grouped by the requested sizes. The second histogram indicates which callback function contributes the most to each group.
