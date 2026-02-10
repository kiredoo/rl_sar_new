/*
 * Copyright (c) 2024-2025 Ziqi Fan
 * SPDX-License-Identifier: Apache-2.0
 */

#ifndef RL_REAL_IDOG_HPP
#define RL_REAL_IDOG_HPP

// #define PLOT
// #define CSV_LOGGER
#define USE_ROS

#include "rl_sdk.hpp"
#include "observation_buffer.hpp"
#include "inference_runtime.hpp"
#include "loop.hpp"
#include "fsm_idog.hpp"

#include <csignal>

#if defined(USE_ROS1) && defined(USE_ROS)
#include <ros/ros.h>
#include <geometry_msgs/Twist.h>
#include <std_msgs/Float32MultiArray.h>
#include <sensor_msgs/PointCloud2.h>
#include <sensor_msgs/Joy.h>
#include <sensor_msgs/Imu.h>
#include <geometry_msgs/Twist.h>
#include "motor_msg/LowState.h"
#include "motor_msg/MotorState.h"
#include "motor_msg/LowCmd.h"
#include "motor_msg/MotorCmd.h"
#include "std_msgs/Bool.h"
#elif defined(USE_ROS2) && defined(USE_ROS)
#include <rclcpp/rclcpp.hpp>
#include <geometry_msgs/msg/twist.hpp>
#include <std_msgs/float32_multi_array.hpp>
#endif

#include "matplotlibcpp.h"
namespace plt = matplotlibcpp;


#define TOPIC_LOWCMD "/lowcmd"
#define TOPIC_LOWSTATE "/lowstate"
#define TOPIC_JOYSTICK "/joy"
constexpr double PosStopF = (2.146E+9f);
constexpr double VelStopF = (16000.0f);



class RL_Real : public RL
{
public:
    RL_Real(int argc, char **argv);
    ~RL_Real();

#if defined(USE_ROS2) && defined(USE_ROS)
    std::shared_ptr<rclcpp::Node> ros2_node;
#endif

private:
    // rl functions
    std::vector<float> Forward() override;
    void GetState(RobotState<float> *state) override;
    void SetCommand(const RobotCommand<float> *command) override;
    void RunModel();
    void RobotControl();

    // loop
    std::shared_ptr<LoopFunc> loop_keyboard;
    std::shared_ptr<LoopFunc> loop_control;
    std::shared_ptr<LoopFunc> loop_rl;
    std::shared_ptr<LoopFunc> loop_plot;

    // plot
    const int plot_size = 100;
    std::vector<int> plot_t;
    std::vector<std::vector<float>> plot_real_joint_pos, plot_target_joint_pos;
    void Plot();

    // unitree interface
    // void InitLowCmd();
    // int QueryMotionStatus();
    // std::string QueryServiceName(std::string form, std::string name);
    // uint32_t Crc32Core(uint32_t *ptr, uint32_t len);
    // void LowStateMessageHandler(const void *messages);
    // void JoystickHandler(const void *message);
    // MotionSwitcherClient msc;
    // unitree_go::msg::dds_::LowCmd_ unitree_low_command{};
    // unitree_go::msg::dds_::LowState_ unitree_low_state{};
    // unitree_go::msg::dds_::WirelessController_ joystick{};
    // ChannelPublisherPtr<unitree_go::msg::dds_::LowCmd_> lowcmd_publisher;
    // ChannelSubscriberPtr<unitree_go::msg::dds_::LowState_> lowstate_subscriber;
    // ChannelSubscriberPtr<unitree_go::msg::dds_::WirelessController_> joystick_subscriber;
    // xKeySwitchUnion unitree_joy;

    // others
    std::vector<float> mapped_joint_positions;
    std::vector<float> mapped_joint_velocities;

#if defined(USE_ROS1) && defined(USE_ROS)
    geometry_msgs::Twist cmd_vel;
    ros::Subscriber cmd_vel_subscriber;
    void CmdvelCallback(const geometry_msgs::Twist::ConstPtr &msg);
    // Depth data from Extreme Parkour Onboard's visual_extreme_parkour.py
    std_msgs::Float32MultiArray depth_data;
    ros::Subscriber depth_subscriber;
    void DepthCallback(const std_msgs::Float32MultiArray::ConstPtr &msg);
    motor_msg::LowState motor_state;
    ros::Subscriber motor_status_subscriber;
    void MotorStatusCallback(const motor_msg::LowState::ConstPtr &msg);
    sensor_msgs::Joy joy_msg;
    ros::Subscriber joy_subscriber;
    void JoyCallback(const sensor_msgs::Joy::ConstPtr &msg);
    sensor_msgs::Imu imu;
    ros::Subscriber imu_subscriber;
    void ImuCallback(const sensor_msgs::Imu::ConstPtr &msg);

    // Desired joint position and Actual joint position
    ros::Publisher action_dof_pos_publisher;
    // Clamped Observations
    ros::Publisher clamped_obs_publisher;
    
    // (Use for simulation, caution when use in real, might cause critical issues)
    // Replay Clamped Observations
    ros::Subscriber replay_clamped_obs_subscriber;
    std::vector<float> replay_clamped_obs;
    bool use_replay_clamped_obs = false;  // enable/disable via ROS param
    bool has_replay_clamped_obs = false;  // have we received anything yet?
    void ReplayClampedObsCallback(const std_msgs::Float32MultiArray::ConstPtr &msg);

    motor_msg::LowCmd joint_cmd_msg;
    motor_msg::LowCmd joint_cmd_msg_last;
    ros::Publisher motor_cmd_publisher;

#elif defined(USE_ROS2) && defined(USE_ROS)
    geometry_msgs::msg::Twist cmd_vel;
    rclcpp::Subscription<geometry_msgs::msg::Twist>::SharedPtr cmd_vel_subscriber;
    void CmdvelCallback(const geometry_msgs::msg::Twist::SharedPtr msg);
    // Depth data from Extreme Parkour Onboard's visual_extreme_parkour.py
    std_msgs::msg::Float32MultiArray depth_data;
    rclcpp::Subscription<std_msgs::msg::Float32MultiArray>::SharedPtr depth_subscriber;
    void DepthCallback(const std_msgs::msg::Float32MultiArray::SharedPtr msg);
#endif
};

#endif // RL_REAL_IDOG_HPP