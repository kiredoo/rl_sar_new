We use callback function latency to align with the node latency reported by CARET.  
The file `node_to_callback_latency.csv` serves as the mapping table between them.

The script `summarize_exec_by_cb_topic.py` uses the subscribed topic’s wall time and the callback function’s start time, and matches these two to analyze:

> “Callback-function latency (same function, different node names) → node latency”

For **normally executed** nodes and callback functions (one node → one or two callback), the table is filled directly using the results measured by **AGA.Time**.  
Only when **multiple nodes share the same callback function** do we need to run the scripts below to derive the per-node latency.

### How to run

```
sudo -E bash -lc 'source /opt/ros/humble/setup.bash && \
python3 ebpf_perf_callback_nine_one_shot_et_prio.py \
  --callback-list-file data1.txt \
  --topic-spec /sensing/lidar/top/velodyne_packets:velodyne_msgs/msg/VelodyneScan \
  --topic-spec /sensing/lidar/left/velodyne_packets:velodyne_msgs/msg/VelodyneScan \
  --topic-spec /sensing/lidar/right/velodyne_packets:velodyne_msgs/msg/VelodyneScan \
  --priority-by-input'
```

After --topic-spec, specify the `topic name` and the topic’s `message_type`.

In data1.txt, list the callback functions you want to measure.
You can rename this file as needed.

Important: put the top lidar callback first in the list, otherwise the search results will be mixed together.

After the run, you still need to analyze the data with this script. The final result will be the file `stats_exec_cb-topic_exec.csv`. Use the P95 values in that file as a replacement for the pWCET values.

Run:
```
python3 summarize_exec_by_cb_topic.py --matched out_matched.csv --out stats_exec
```