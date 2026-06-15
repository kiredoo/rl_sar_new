## 00_Overview & Objectives

### Background & Motivation

We need a WCET measurement tool because all deterministic methods we adopt rely on trustworthy WCET data. Having an in-house tool lets us customize the workflow and obtain the required numbers faster.

### Objectives

- Measure each callback function pWCET with EVT/GEV.  
- Deliver the full AGA.Time pipeline:
  - from launch  
  - to measurement  
  - to report generation.

### Experimental Environment

| Item                 | Value                     |
| -------------------- | ------------------------- |
| x86-CPU              | Intel i7-6800K            |
| x86-GPU              | NVIDIA 2080 Ti            |
| Ubuntu               | 22.04                     |
| ROS 2                | humble                    |
| Autoware.Universe    | 2025.02                   |
| rosbag play rate     | 1×                        |
| simulator            | logging simulation        |
| Loop count           | 100                       |
| CPU frequency locked | 3.4 GHz                   |

---

## 01_System_Architecture

### High-level Diagram (eBPF sampling → preprocessing → EVT/pWCET → report)

AGA.Time inserts eBPF probes into selected callback functions. Using the probe timestamps, we:

1. Compute execution times per callback invocation.  
2. Aggregate samples into blocks.  
3. Estimate pWCET (via EVT/GEV) and CV.  
4. Generate a complete report.

![probe.png](image/probe.png)

### Operational Flow (runtime overview)

1. Launch Autoware and wait until it is fully ready.  
2. Attach eBPF probes.  
3. Replay rosbag.  
4. After replay completes, collect the execution-time samples.  
5. Shutdown Autoware and detach eBPF.  
6. Depending on configuration:
   - either proceed to the next run, or  
   - generate a report from the collected data.

![measure_aw_wcet_diagram.png](image/measure_aw_wcet_diagram.png)

### Module Responsibilities

- **measure_aw_wcet.py** – launcher / sampler (orchestrates runs, attaches probes, collects samples).  
- **wcet_utils.py** – report generation (EVT fitting, pWCET, tables/plots).  
- **cv_manager.py** – CV calculation and related metrics.

---

## 02_Methodology

### Sampling Approach

We measure callback execution time with eBPF by placing:

- an **uprobes/uretprobes** pair at the callback’s entry/return, and  
- a **kprobes/kretprobes** pair as system-call timing markers.

For each callback invocation, we conceptually compute:

- `runtime = (t_uretprobe - t_uprobe) - (t_kretprobe - t_kprobe)`

Practical notes:

- If multiple kprobe intervals exist inside one callback, we subtract their **total** duration.  
- If your pipeline guarantees a single kprobe pair, we subtract just that single interval.

### Experiment Design

To support EVT-based pWCET, we:

- repeat the experiment for multiple runs (≥ 100 as a rule of thumb), and
- fix system conditions for stability, e.g.:
  - CPU frequency locked at ~90% of max  
  - fix simulation / rosbag configuration.

### Statistical Assumptions

We use the **Block Maxima (BM)** strategy for EVT-based pWCET:

- We repeat rosbag replays across runs.
- **Per rosbag replay**, we split the per-invocation execution-time samples into **15 equal segments** and take one maximum per segment.
  - This yields **15 block maxima per rosbag**, instead of a single maximum per rosbag.
  - Motivation: using only one BM per rosbag can overreact to a single outlier and inflate the final pWCET. A 15-maxima-per-rosbag approach reduces this sensitivity while preserving a maxima-based tail signal.
- The choice of **15** is empirical for our current workload:
  - Using **10** segments still produced overly large pWCET in some callbacks.
  - Using **20** segments increased KS-test failure rate (insufficient/unstable tail fit on the BM series).
  - Therefore we default to **15** as a practical trade-off for this setup.

### Practical Workflow Summary

1. **Burn-in removal**: discard initial samples per callback to avoid warm-up artifacts.
2. **BM extraction per rosbag**: split each rosbag run into 15 segments and take one maximum per segment (15 BM values per rosbag).
3. **Tail estimation & fallback**:
   - Use EVT (BM + GEV) when KS validation passes and ξ is within the configured threshold.
   - Otherwise, publish the **inequality-based P95 bound** (ATAN) as the fallback pWCET.

---

## 03_Estimation_and_Validation

### EVT Modeling

AGA.Time uses **BM + GEV** for tail modeling:

1. Aggregate block maxima across runs.  
2. Fit a GEV distribution to the block-maxima series.  
3. From the fitted GEV model, compute tail quantiles and report pWCET.

### pWCET Metrics

- We report **pWCET** as the **95th percentile** (α = 0.05) of the fitted GEV distribution.  

(Other metrics such as p95 and CV are also reported where applicable.)

### Model Validation (with fallback)

We validate the GEV fit on the BM series using the KS test. When the parametric tail model is considered unreliable, we **do not** publish the EVT/GEV-based pWCET. Instead, we apply an inequality-based fallback that is robust to heavy tails.

We trigger the fallback under either condition:
- **KS test failure** (Type II / Type III in our report), or
- **Heavy-tail indicator**: fitted shape parameter **ξ > 0.2**.

#### Fallback: Markov-inequality bound for P95 (ATAN)

Given per-invocation execution-time samples X, we use the generalized Markov inequality:

    P(X >= b) <= E[f(X)] / f(b)

For P95, the tail probability is p = 0.05 (i.e., only 5% of executions exceed b).
We choose b as the smallest value such that:

    E[f(X)] / f(b) <= 0.05

We use the saturating function (based on [1]):

    f(x) = (atan(x / d))^k

This fallback provides a conservative, model-free pWCET-style bound when EVT assumptions/fit checks fail.

Practical implementation notes:
We use a coarse grid search for (𝑑, 𝑘) with 𝑘 ∈ {1, 2, 3, 4} to balance tightness and estimator stability under finite samples.
The threshold 𝑏 is selected from the empirical sample set (sorted samples) for reproducibility and debuggability.
If no 𝑏 satisfies the target tail bound under the searched (𝑑, 𝑘) pairs, we conservatively fall back to the observed maximum sample.

---

![CB_report.png](image/CB_report.png)

## 04_Benchmarking

### Benchmark Tooling

We use **MBBench** (WCET micro-benchmarks) to compare **AGA.Time** with **RapiTime** across a set of kernels/programs.

![MBbench.png](image/MBbench.png)

### Summary

Overall, results are similar except in **“burn-in” periods** where differences appear;our numbers tend to better reflect stabilized steady-state.

### Detailed results are summarized below


| Run | miller RapiTime (ms) | miller AGA.Time (ms) | rsa RapiTime (ms) | rsa AGA.Time (ms) |
| --- | -------------------- | -------------------- | ----------------- | ----------------- |
| 1   | 2028.14              | 2206.495             | 8193.729          | 7431.125          |
| 2   | 0.002                | 0.002                | 0.004             | 0.004             |
| …   | …                    | …                    | …                 | …                 |
| N   | 0.002                | 0.002                | 0.004             | 0.004             |

### MBBench: Summary Table

| Benchmark          | RapiTime (ms) | AGA.Time (ms) |
| ----------------   | ------------- | ------------- |
| cesar              | 0.003         | 0.001         |
| knapsack           | 0.003         | 0.001         |
| bucket             | 0.004         | 0.002         |
| gcd                | 0.008         | 0.002         |
| rabinkart          | 0.009         | 0.002         |
| radix              | 0.010         | 0.002         |
| merge              | 0.005         | 0.002         |
| huffman            | 0.065         | 0.003         |
| standard_deviation | 0.033         | 0.016         |
| pollard            | 0.270         | 0.064         |
| counting           | 0.005         | 0.066         |
| booth              | 1.197         | 1.343         |
| miller             | 2028.1        | 0.002         |
| rsa                | 8193.7        | 0.004         |

---

![benchmark_rapitime_agatime.png](image/benchmark_rapitime_agatime.png)

## 05_Conclusion_and_Roadmap

### Overall Conclusion

AGA.Time delivers a **reproducible, end-to-end timing pipeline**:

- from eBPF sampling and preprocessing  
- to EVT fitting and report generation  

with clear **traceability**:

> Data → Script → Commit → Environment

Across multiple runs, tail metrics (p95, p99, CV, pWCET):

- are **consistent** and **interpretable**,  
- supporting **predictable** and **defensible** timing behavior.

---

## References

[1] H. Toba, A. Yano, and T. Azumi, “Generalized Inequality-based Approach for Probabilistic WCET Estimation,” arXiv:2511.11682, 2025. Available: https://arxiv.org/abs/2511.11682


## Appendix: Example Callback final_result Table

| Callback function | final_result(ms) |
|---|---:|
| autoware::vehicle_cmd_gate::AdapiPauseInterface::on_pause | 0.013 |
| autoware::pose_initializer::GnssModule::on_pose | 0.019 |
| autoware::map_loader::DifferentialMapLoaderModule::on_service_get_differential_point_cloud_map | 0.022 |
| autoware::scenario_selector::ScenarioSelectorNode::onOdom | 0.028 |
| planning_diagnostics::PlanningEvaluatorNode::onTrajectory | 0.032 |
| autoware::operation_mode_transition_manager::Compatibility::on_selector_mode | 0.042 |
| ad_api_adaptors::RoutingAdaptor::on_timer | 0.062 |
| rviz_plugins::AutowareStatePanel::onRoute | 0.064 |
| autoware::traffic_light::TrafficLightClassifierNodelet::connectCb | 0.065 |
| rviz_plugins::AutowareStatePanel::onMotion | 0.101 |
| autoware::operation_mode_transition_manager::Compatibility::on_gate_mode | 0.114 |
| planning_diagnostics::PlanningEvaluatorNode::onModifiedGoal | 0.151 |
| autoware::remaining_distance_time_calculator::RemainingDistanceTimeCalculatorNode::on_timer | 0.218 |
| autoware::operation_mode_transition_manager::Compatibility::on_autoware_engage | 0.270 |
| rviz_plugins::AutowareStatePanel::onEmergencyStatus | 0.305 |
| autoware_overlay_rviz_plugin::SignalDisplay::updateSpeedData | 0.341 |
| autoware_overlay_rviz_plugin::SignalDisplay::updateSteeringData | 0.400 |
| autoware::vehicle_cmd_gate::VehicleCmdGate::checkExternalEmergencyStop | 0.401 |
| automatic_pose_initializer::AutomaticPoseInitializer::on_timer | 0.463 |
| autoware::pointcloud_preprocessor::RandomDownsampleFilterComponent::filter | 0.540 |
| autoware_overlay_rviz_plugin::SignalDisplay::updateGearData | 0.567 |
| autoware::twist2accel::Twist2Accel::callback_twist_with_covariance | 0.574 |
| autoware::vehicle_cmd_gate::VehicleCmdGate::onMrmState | 0.609 |
| autoware::pose_instability_detector::PoseInstabilityDetector::callback_twist | 0.626 |
| autoware::pose_instability_detector::PoseInstabilityDetector::callback_odometry | 0.702 |
| autoware::imu_corrector::GyroBiasEstimator::callback_odom | 0.705 |
| autoware::remaining_distance_time_calculator::RemainingDistanceTimeCalculatorNode::on_odometry | 0.708 |
| autoware::detection_by_tracker::TrackerHandler::onTrackedObjects | 0.718 |
| autoware::mission_planner::MissionPlanner::check_initialization | 0.794 |
| planning_diagnostics::PlanningEvaluatorNode::onObjects | 0.843 |
| autoware::component_interface_tools::ServiceLogChecker::on_service_log | 0.983 |
| autoware::mission_planner::RouteSelector::on_state | 1.196 |
| autoware::ekf_localizer::EKFLocalizer::callback_pose_with_covariance | 1.279 |
| MrmHandler::onOperationModeAvailability | 1.338 |
| autoware::motion_utils::VehicleStopChecker::onOdom | 1.406 |
| autoware::multi_object_tracker::TrackerDebugger::checkDelay | 1.474 |
| diagnostic_graph_aggregator::AggregatorNode::on_diag | 1.685 |
| RTCModule::autoModeCallback | 1.747 |
| autoware::gyro_odometer::GyroOdometerNode::concat_gyro_and_odometer | 1.879 |
| component_state_monitor::StateMonitor::on_diag | 2.148 |
| autoware::pointcloud_preprocessor::PointCloudConcatenateDataSynchronizerComponent::twist_callback | 2.162 |
| autoware::pointcloud_preprocessor::DistortionCorrectorComponent::imu_callback | 2.186 |
| autoware::stop_filter::StopFilter::callback_odometry | 2.400 |
| autoware::motion::control::trajectory_follower_node::Controller::callbackTimerControl | 2.525 |
| autoware::mission_planner::MissionPlanner::on_odometry | 2.587 |
| mrm_comfortable_stop_operator::MrmComfortableStopOperator::onTimer | 2.597 |
| autoware::imu_corrector::ImuCorrector::callback_imu | 2.806 |
| autoware::processing_time_checker::ProcessingTimeChecker::on_timer | 2.853 |
| autoware::scenario_selector::ScenarioSelectorNode::onTimer | 2.959 |
| autoware::gyro_odometer::GyroOdometerNode::callback_vehicle_twist | 3.086 |
| autoware::vehicle_cmd_gate::VehicleCmdGate::onEmergencyCtrlCmd | 3.149 |
| autoware::vehicle_velocity_converter::VehicleVelocityConverter::callback_velocity_report | 3.181 |
| autoware::default_adapi::OperationModeNode::on_timer | 3.317 |
| component_state_monitor::StateMonitor::on_timer | 3.504 |
| autoware::multi_object_tracker::MultiObjectTracker::onTimer | 3.619 |
| autoware::gnss_poser::GNSSPoser::callback_nav_sat_fix | 3.977 |
| autoware::rviz_plugins::object_detection::PredictedObjectsDisplay::messageProcessorThreadJob | 3.982 |
| control_diagnostics::ControlEvaluatorNode::onTimer | 4.110 |
| autoware::localization_error_monitor::LocalizationErrorMonitor::on_odom | 4.190 |
| autoware::imu_corrector::GyroBiasEstimator::timer_callback | 4.213 |
| autoware::detected_object_validation::lanelet_filter::ObjectLaneletFilterNode::objectCallback | 4.235 |
| autoware::default_adapi::PlanningNode::on_timer | 4.305 |
| autoware::ndt_scan_matcher::NDTScanMatcher::callback_initial_pose | 4.421 |
| autoware::default_adapi::VehicleNode::on_timer | 4.431 |
| autoware::costmap_generator::CostmapGenerator::onTimer | 4.436 |
| autoware::freespace_planner::FreespacePlannerNode::onTimer | 4.502 |
| autoware::imu_corrector::GyroBiasEstimator::callback_imu | 4.565 |
| hazard_status_converter::Converter::on_update | 4.706 |
| autoware::pose_instability_detector::PoseInstabilityDetector::callback_timer | 4.849 |
| diagnostic_graph_utils::DiagGraphSubscription::on_status | 4.870 |
| autoware::pointcloud_preprocessor::DistortionCorrectorComponent::twist_callback | 4.970 |
| external_api::RTCController::onAutoModeTimer | 5.276 |
| autoware::rtc_interface::RTCInterface::onTimer | 5.454 |
| autoware::twist2accel::Twist2Accel::callback_odometry | 5.549 |
| MrmHandler::onTimer | 5.672 |
| autoware::motion::control::autonomous_emergency_braking::AEB::onImu | 5.734 |
| planning_diagnostics::PlanningEvaluatorNode::onTimer | 5.895 |
| autoware::vehicle_cmd_gate::VehicleCmdGate::publishStatus | 5.907 |
| planning_diagnostics::PlanningEvaluatorNode::onOdometry | 5.948 |
| autoware::default_adapi::DiagnosticsNode::on_update | 6.154 |
| utoware::default_adapi::AutowareStateNode::on_timer | 6.181 |
| autoware::gyro_odometer::GyroOdometerNode::publish_data | 6.959 |
| autoware::twist2accel::Twist2Accel::estimate_accel | 7.200 |
| autoware::ekf_localizer::EKFLocalizer::callback_twist_with_covariance | 7.351 |
| planning_diagnostics::PlanningEvaluatorNode::onReferenceTrajectory | 7.444 |
| autoware::multi_object_tracker::InputStream::onMessage | 7.534 |
| autoware::behavior_path_planner::BehaviorPathPlannerNode::run | 7.888 |
| autoware::operation_mode_transition_manager::OperationModeTransitionManager::onTimer | 8.179 |
| topic_state_monitor::TopicStateMonitorNode::onTimer | 8.335 |
| autoware::pointcloud_preprocessor::PointCloudConcatenateDataSynchronizerComponent::timer_callback | 8.539 |
| autoware::default_adapi::MotionNode::on_timer | 8.614 |
| autoware::detected_object_validation::obstacle_pointcloud::ObstaclePointCloudBasedValidator::onObjectsAndObstaclePointCloud | 8.781 |
| autoware::pointcloud_preprocessor::CropBoxFilterComponent::faster_filter | 9.066 |
| autoware::external_cmd_selector::ExternalCmdSelector::onTimer | 9.074 |
| autoware::vehicle_cmd_gate::VehicleCmdGate::onTimer | 9.295 |
| autoware::traffic_light::TrafficLightFineDetectorNode::connectCb | 9.350 |
| autoware::lane_departure_checker::LaneDepartureCheckerNode::onTimer | 9.363 |
| diagnostic_graph_aggregator::AggregatorNode::on_timer | 9.378 |
| autoware::multi_object_tracker::InputManager::onTrigger | 9.523 |
| mrm_emergency_stop_operator::MrmEmergencyStopOperator::onTimer | 9.881 |
| duplicated_node_checker::DuplicatedNodeChecker::onTimer | 9.923 |
| utoware::shift_decider::ShiftDecider::onTimer | 10.283 |
| autoware::gyro_odometer::GyroOdometerNode::callback_imu | 10.387 |
| autoware::external_cmd_converter::ExternalCmdConverterNode::on_timer | 10.402 |
| autoware::multi_object_tracker::MultiObjectTracker::onTrigger | 11.148 |
| autoware::map_based_prediction::MapBasedPredictionNode::objectsCallback | 12.022 |
| nebula::ros::VelodyneRosWrapper::receive_scan_message_callback | 12.170 |
| autoware::ndt_scan_matcher::NDTScanMatcher::callback_timer | 12.185 |
| autoware::detected_object_feature_remover::DetectedObjectFeatureRemover::objectCallback | 13.438 |
| autoware::ekf_localizer::EKFLocalizer::timer_callback | 13.551 |
| autoware::detection_by_tracker::DetectionByTracker::onObjects | 14.468 |
| autoware::motion::control::autonomous_emergency_braking::AEB::onPointCloud | 18.918 |
| autoware::pointcloud_preprocessor::PickupBasedVoxelGridDownsampleFilterComponent::filter | 20.100 |
| autoware::motion::control::autonomous_emergency_braking::AEB::onTimer | 20.913 |
| autoware::shape_estimation::ShapeEstimationNode::callback | 21.417 |
| autoware::traffic_light::TrafficLightRoiVisualizerNode::connectCb | 21.847 |
| external_api::RTCController::onTimer | 23.184 |
| autoware::pointcloud_preprocessor::PointCloudConcatenateDataSynchronizerComponent::cloud_callback | 23.204 |
| autoware::object_merger::ObjectAssociationMergerNode::objectsCallback | 24.344 |
| autoware::compare_map_segmentation::VoxelBasedCompareMapFilterComponent::filter | 36.303 |
| autoware::ndt_scan_matcher::NDTScanMatcher::callback_sensor_points | 37.029 |
| autoware::lidar_centerpoint::LidarCenterPointNode::pointCloudCallback | 39.037 |
| autoware::euclidean_cluster::VoxelGridBasedEuclideanClusterNode::onPointCloud | 39.474 |
| autoware::occupancy_grid_map::PointcloudBasedOccupancyGridMapNode::onPointcloudWithObstacleAndRaw | 42.809 |
| autoware::pointcloud_preprocessor::DistortionCorrectorComponent::pointcloud_callback | 45.268 |
| autoware::pointcloud_preprocessor::RingOutlierFilterComponent::faster_filter | 46.034 |
| autoware::ground_segmentation::ScanGroundFilterComponent::faster_filter | 47.056 |
| autoware::pointcloud_preprocessor::VoxelGridDownsampleFilterComponent::faster_filter | 66.965 |
| autoware::occupancy_grid_map_outlier_filter::OccupancyGridMapOutlierFilterComponent::onOccupancyGridMapAndPointCloud2 | 93.874 |

# initial callback function
| Callback function | final_result(ms) |
|---|---:|
| autoware::ekf_localizer::EKFLocalizer::callback_initial_pose | 0.175 |
| rviz_plugins::AutowareStatePanel::onMRMState | 0.329 |
| autoware::ekf_localizer::EKFLocalizer::service_trigger_node | 0.509 |
| rviz_plugins::AutowareStatePanel::onOperationMode | 1.442 |
| autoware::mission_planner::MissionPlanner::on_operation_mode_state | 2.067 |
| autoware::ndt_scan_matcher::NDTScanMatcher::service_trigger_node | 5.724 |
| rviz_plugins::AutowareStatePanel::onLocalization | 8.021 |
| autoware::map_loader::PartialMapLoaderModule::on_service_get_partial_point_cloud_map | 20.347 |
| autoware::ndt_scan_matcher::NDTScanMatcher::service_ndt_align | 7422.167 |
