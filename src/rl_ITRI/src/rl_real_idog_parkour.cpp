/*
 * Copyright (c) 2024-2025 Brian Lin
 * SPDX-License-Identifier: Apache-2.0
 */

#include "rl_real_idog_parkour.hpp"
#include <cmath>
#include <algorithm>

RL_Real::RL_Real(int argc, char **argv)
{
    bool wheel_mode = (argc > 2 && std::string(argv[2]) == "wheel");
#if defined(USE_ROS1) && defined(USE_ROS)
    ros::NodeHandle nh;
    this->cmd_vel_subscriber = nh.subscribe<geometry_msgs::Twist>("/cmd_vel", 10, &RL_Real::CmdvelCallback, this);
    this->depth_subscriber = nh.subscribe<std_msgs::Float32MultiArray>("/forward_depth_image", 1, &RL_Real::DepthCallback, this);
    this->action_dof_pos_publisher = 
        nh.advertise<std_msgs::Float32MultiArray>("/debug/action_dof_pos", 10);
    this->clamped_obs_publisher =
        nh.advertise<std_msgs::Float32MultiArray>("/debug/clamped_obs", 10); // not used in test
    
    // Replay clamped_obs support
    // Enable: rosparam set use_replay_clamped_obs true (before controller starts)
    nh.param("use_replay_clamped_obs", this->use_replay_clamped_obs, false);

    if (this->use_replay_clamped_obs)
    {
        this->replay_clamped_obs_subscriber =
            nh.subscribe<std_msgs::Float32MultiArray>(
                "/replay/clamped_obs",
                10,
                &RL_Real::ReplayClampedObsCallback,
                this);
        std::cout << LOGGER::INFO
                  << "[Replay] use_replay_clamped_obs = true, subscribing /replay/clamped_obs"
                  << std::endl;
    }

#elif defined(USE_ROS2) && defined(USE_ROS)
    ros2_node = std::make_shared<rclcpp::Node>("rl_real_node");
    ros2_node->declare_parameter("use_replay_clamped_obs", false);
    ros2_node->get_parameter("use_replay_clamped_obs", this->use_replay_clamped_obs);

    this->cmd_vel_subscriber = ros2_node->create_subscription<geometry_msgs::msg::Twist>(
        "/cmd_vel", rclcpp::SystemDefaultsQoS(),
        [this] (const geometry_msgs::msg::Twist::SharedPtr msg) {this->CmdvelCallback(msg);}
    );

    this->depth_subscriber = ros2_node->create_subscription<std_msgs::msg::Float32MultiArray>(
        "/forward_depth_image", rclcpp::SensorDataQoS(),
        [this] (const std_msgs::msg::Float32MultiArray::SharedPtr msg) {this->DepthCallback(msg);}
    );

    this->motor_status_subscriber = ros2_node->create_subscription<motor_msg::msg::LowState>(
        TOPIC_LOWSTATE, rclcpp::SensorDataQoS(),
        [this] (const motor_msg::msg::LowState::SharedPtr msg) {this->MotorStatusCallback(msg);}
    );
    this->imu_subscriber = ros2_node->create_subscription<sensor_msgs::msg::Imu>(
        "/imu/data", rclcpp::SensorDataQoS(),
        [this] (const sensor_msgs::msg::Imu::SharedPtr msg) {this->ImuCallback(msg);}
    );

    this->joy_subscriber = ros2_node->create_subscription<sensor_msgs::msg::Joy>(
        TOPIC_JOYSTICK, rclcpp::SystemDefaultsQoS(),
        [this] (const sensor_msgs::msg::Joy::SharedPtr msg) {this->JoyCallback(msg);}
    );

    if (this->use_replay_clamped_obs) {
        this->replay_clamped_obs_subscriber = ros2_node->create_subscription<std_msgs::msg::Float32MultiArray>(
            "/replay/clamped_obs", rclcpp::SystemDefaultsQoS(),
            [this] (const std_msgs::msg::Float32MultiArray::SharedPtr msg) {this->ReplayClampedObsCallback(msg);}
        );
        RCLCPP_INFO(ros2_node->get_logger(), "[Replay] use_replay_clamped_obs = true, subscribing /replay/clamped_obs");
    }

    this->action_dof_pos_publisher = ros2_node->create_publisher<std_msgs::msg::Float32MultiArray>("/debug/action_dof_pos", 10);
    this->clamped_obs_publisher = ros2_node->create_publisher<std_msgs::msg::Float32MultiArray>("/debug/clamped_obs", 10);
    
    this->motor_cmd_publisher = ros2_node->create_publisher<motor_msg::msg::LowCmd>(TOPIC_LOWCMD, rclcpp::SensorDataQoS());
#endif

    // read params from yaml
    this->ang_vel_axis = "body";
    this->robot_name = wheel_mode ? "idogw" : "idog";
    this->ReadYaml(this->robot_name, "base.yaml");

    // auto load FSM by robot_name
    if (FSMManager::GetInstance().IsTypeSupported(this->robot_name))
    {
        auto fsm_ptr = FSMManager::GetInstance().CreateFSM(this->robot_name, this);
        if (fsm_ptr)
        {
            this->fsm = *fsm_ptr;
        }
    }
    else
    {
        std::cout << LOGGER::ERROR << "[FSM] No FSM registered for robot: " << this->robot_name << std::endl;
    }

    // init robot
    this->InitJointNum(this->params.Get<int>("num_of_dofs"));
    this->InitOutputs();
    this->InitControl();
    #if defined(USE_ROS1)
        this->motor_cmd_publisher = nh.advertise<motor_msg::LowCmd>(TOPIC_LOWCMD, 1);
        this->motor_status_subscriber = nh.subscribe<motor_msg::LowState>(TOPIC_LOWSTATE, 1, &RL_Real::MotorStatusCallback, this);
        this->joy_subscriber = nh.subscribe<sensor_msgs::Joy>(TOPIC_JOYSTICK, 1, &RL_Real::JoyCallback, this);
        this->imu_subscriber = nh.subscribe<sensor_msgs::Imu>("/imu/data", 1, &RL_Real::ImuCallback, this);
    #endif
    // this->motor_servo_publisher = nh.advertise<std_msgs::Bool>("/motor_servo", 1);
    // this->motor_tolerance_publisher = nh.advertise<std_msgs::Bool>("/motor_tolerance", 1);

    // init rl
    for (size_t i = 0; i < joint_cmd_msg_last.motor_cmd.size(); ++i)
    {
        joint_cmd_msg_last.motor_cmd[i].kp = 0.0;
        joint_cmd_msg_last.motor_cmd[i].kd = 0.0;
    }

    // loop
    this->loop_keyboard = std::make_shared<LoopFunc>("loop_keyboard", 0.05, std::bind(&RL_Real::KeyboardInterface, this));
    this->loop_control = std::make_shared<LoopFunc>("loop_control", this->params.Get<float>("dt"), std::bind(&RL_Real::RobotControl, this));
    this->loop_rl = std::make_shared<LoopFunc>("loop_rl", this->params.Get<float>("dt") * this->params.Get<int>("decimation"), std::bind(&RL_Real::RunModel, this));
    this->loop_keyboard->start();
    this->loop_control->start();
    this->loop_rl->start();

#ifdef PLOT
    this->plot_t = std::vector<int>(this->plot_size, 0);
    this->plot_real_joint_pos.resize(this->params.Get<int>("num_of_dofs"));
    this->plot_target_joint_pos.resize(this->params.Get<int>("num_of_dofs"));
    for (auto &vector : this->plot_real_joint_pos) { vector = std::vector<float>(this->plot_size, 0); }
    for (auto &vector : this->plot_target_joint_pos) { vector = std::vector<float>(this->plot_size, 0); }
    this->loop_plot = std::make_shared<LoopFunc>("loop_plot", 0.002, std::bind(&RL_Real::Plot, this));
    this->loop_plot->start();
#endif
#ifdef CSV_LOGGER
    this->CSVInit(this->robot_name);
#endif
}

RL_Real::~RL_Real()
{
    this->loop_keyboard->shutdown();
    this->loop_control->shutdown();
    this->loop_rl->shutdown();
#ifdef PLOT
    this->loop_plot->shutdown();
#endif
    std::cout << LOGGER::INFO << "RL_Real exit" << std::endl;
}

void RL_Real::GetState(RobotState<float> *state)
{
    state->imu.quaternion[0] = this->imu.orientation.w; // w
    state->imu.quaternion[1] = this->imu.orientation.x; // x
    state->imu.quaternion[2] = this->imu.orientation.y; // y
    state->imu.quaternion[3] = this->imu.orientation.z; // z

    state->imu.gyroscope[0] = this->imu.angular_velocity.x;
    state->imu.gyroscope[1] = this->imu.angular_velocity.y;
    state->imu.gyroscope[2] = this->imu.angular_velocity.z;

    // std::cout << "IMU Quaternion:" << state->imu.quaternion[0] <<", " << state->imu.quaternion[1] <<", " << state->imu.quaternion[2] <<", " << state->imu.quaternion[3] << std::endl;
    // std::cout << "IMU Gyroscope:" << state->imu.gyroscope[0] <<", " << state->imu.gyroscope[1] <<", " << state->imu.gyroscope[2] << std::endl;
    for (int i = 0; i < this->params.Get<int>("num_of_dofs"); ++i)
    {
        state->motor_state.q[i] = this->motor_state.motor_state[this->params.Get<std::vector<int>>("joint_mapping")[i]].q;
        state->motor_state.dq[i] = this->motor_state.motor_state[this->params.Get<std::vector<int>>("joint_mapping")[i]].dq;
        state->motor_state.tau_est[i] = this->motor_state.motor_state[this->params.Get<std::vector<int>>("joint_mapping")[i]].tau_est;
    }
}

void RL_Real::SetCommand(const RobotCommand<float> *command)
{
    bool publish_gain = false;
    for (int i = 0; i < this->params.Get<int>("num_of_dofs"); ++i)
    {
        // std::cout << std::fixed << std::setprecision(3)
        //     << "[cmd] j" << i
        //     << " q="  << command->motor_command.q[i]
        //     << " dq=" << command->motor_command.dq[i]
        //     << std::endl;
        this->joint_cmd_msg.motor_cmd[i].q = command->motor_command.q[this->params.Get<std::vector<int>>("joint_mapping")[i]];
        // this->joint_publishers_commands[i].dq = command->motor_command.dq[i];
        this->joint_cmd_msg.motor_cmd[i].kp = command->motor_command.kp[this->params.Get<std::vector<int>>("joint_mapping")[i]];
        this->joint_cmd_msg.motor_cmd[i].kd = command->motor_command.kd[this->params.Get<std::vector<int>>("joint_mapping")[i]];
        // this->joint_publishers_commands[i].tau = command->motor_command.tau[i];
        if(joint_cmd_msg.motor_cmd[i].kp != joint_cmd_msg_last.motor_cmd[i].kp || joint_cmd_msg.motor_cmd[i].kd != joint_cmd_msg_last.motor_cmd[i].kd)
        {
            publish_gain = true;
        }
    }
    if (publish_gain)
    {
        this->joint_cmd_msg.cmd = "gain";
        #if defined(USE_ROS1)
            motor_cmd_publisher.publish(joint_cmd_msg);
        #elif defined(USE_ROS2)
            motor_cmd_publisher->publish(joint_cmd_msg);
        #endif
    }
    this->joint_cmd_msg.cmd = "position";
    #if defined(USE_ROS1)
        motor_cmd_publisher.publish(joint_cmd_msg);
    #elif defined(USE_ROS2)
        motor_cmd_publisher->publish(joint_cmd_msg);
    #endif
    joint_cmd_msg_last = joint_cmd_msg;
}

void RL_Real::RobotControl()
{
    this->GetState(&this->robot_state);

    this->StateController(&this->robot_state, &this->robot_command);

    this->control.ClearInput();

    this->SetCommand(&this->robot_command);
}

void RL_Real::RunModel()
{
    if (this->rl_init_done)
    {
        // TODO: Add depth image input here ex: this->obs.depth=??
        this->episode_length_buf += 1;
        this->obs.ang_vel = this->robot_state.imu.gyroscope;
        this->obs.commands = {this->control.x, this->control.y, this->control.yaw};
#if !defined(USE_CMAKE) && defined(USE_ROS)
        if (this->control.navigation_mode)
        {
            this->obs.commands = {(float)this->cmd_vel.linear.x, (float)this->cmd_vel.linear.y, (float)this->cmd_vel.angular.z};

        }
#endif
        this->obs.base_quat = this->robot_state.imu.quaternion;
        this->obs.dof_pos = this->robot_state.motor_state.q;
        this->obs.dof_vel = this->robot_state.motor_state.dq;
        this->obs.depth_data.assign(this->depth_data.data.begin(), this->depth_data.data.end());

        this->obs.actions = this->Forward();
        
        if (this->params.Has("test_motion") && this->params.Has("test_motion_duration")) 
        {
            // static state (per process). If you run multiple instances, turn these into class members.
            static bool tm_armed = false;
            static int  tm_stage = 0;     // 0=idle/arm, 1=ramp-to-start, 2=hold-start-delay, 3=hold-target
            static int  tm_frame = 0;
            static int  tm_delay_frame = 0;
            static std::vector<float> tm_from_actions;

            static const void* tm_last_model_ptr = nullptr;
            const void* tm_cur_model_ptr = (this->model ? (const void*)this->model.get() : nullptr);
            if (tm_cur_model_ptr != tm_last_model_ptr)
            {
                tm_last_model_ptr = tm_cur_model_ptr;
                tm_armed = false;
                tm_stage = 0;
                tm_frame = 0;
                tm_delay_frame = 0;
                tm_from_actions.clear();
            }

            const bool tm_enabled = this->params.Has("test_motion") && (this->params.Get<int>("test_motion") == 1);

            if (!tm_enabled)
            {
                tm_armed = false;
                tm_stage = 0;
                tm_frame = 0;
                tm_delay_frame = 0;
            }
            else
            {
                const int ndof = this->params.Get<int>("num_of_dofs");
                const auto start_actions  = this->params.Get<std::vector<float>>("test_motion_start");
                const auto target_actions = this->params.Get<std::vector<float>>("test_motion_target");

                // RL tick = dt * decimation (defaults to 0.005*4=0.02 if not present)
                const float base_dt = this->params.Has("dt") ? this->params.Get<float>("dt") : 0.005f;
                const int decimation = this->params.Has("decimation") ? this->params.Get<int>("decimation") : 4;
                const float rl_dt = base_dt * (float)decimation;

                // Stage A duration (seconds): use your test_motion_duration as "ramp-to-start time"
                const float ramp_s = this->params.Has("test_motion_duration") ? this->params.Get<float>("test_motion_duration") : 1.0f;
                const int ramp_frames = std::max(1, (int)std::ceil(std::max(0.0f, ramp_s) / std::max(1e-6f, rl_dt)));

                // NEW: 1 second delay between Stage A and Stage B (hold start)
                const float delay_s = 1.0f;
                const int delay_frames = std::max(1, (int)std::ceil(delay_s / std::max(1e-6f, rl_dt)));

                // Arm once when enabled
                if (!tm_armed)
                {
                    tm_armed = true;
                    tm_stage = 1;
                    tm_frame = 0;
                    tm_delay_frame = 0;

                    // start ramp from whatever action is currently in effect (policy output on this tick)
                    tm_from_actions.assign(this->obs.actions.begin(), this->obs.actions.begin() + ndof);
                }

                if (tm_stage == 1)
                {
                    // Ramp current -> start_actions over ramp_frames RL ticks
                    const float alpha = std::min(1.0f, (float)(tm_frame + 1) / (float)ramp_frames);
                    for (int i = 0; i < ndof; ++i)
                    {
                        const float a0 = (i < (int)tm_from_actions.size()) ? tm_from_actions[i] : 0.0f;
                        const float a1 = (i < (int)start_actions.size()) ? start_actions[i] : 0.0f;
                        this->obs.actions[i] = (1.0f - alpha) * a0 + alpha * a1;
                    }

                    tm_frame++;
                    if (tm_frame >= ramp_frames)
                    {
                        tm_stage = 2;          // go to hold-start-delay
                        tm_delay_frame = 0;
                    }
                }
                else if (tm_stage == 2)
                {
                    // Hold start_actions for 1 second
                    for (int i = 0; i < ndof; ++i)
                    {
                        this->obs.actions[i] = (i < (int)start_actions.size()) ? start_actions[i] : 0.0f;
                    }

                    tm_delay_frame++;
                    if (tm_delay_frame >= delay_frames)
                    {
                        tm_stage = 3;          // then enter hold-target
                    }
                }
                else // tm_stage == 3
                {
                    // Step/hold at target_actions indefinitely
                    for (int i = 0; i < ndof; ++i)
                    {
                        this->obs.actions[i] = (i < (int)target_actions.size()) ? target_actions[i] : 0.0f;
                    }
                }
            }
        }

        this->ComputeOutput(this->obs.actions, this->output_dof_pos, this->output_dof_vel, this->output_dof_tau);

        // publish actions and robot's pos here
        #if defined(USE_ROS1) && defined(USE_ROS)
            std_msgs::Float32MultiArray msg;
        #elif defined(USE_ROS2) && defined(USE_ROS)
            std_msgs::msg::Float32MultiArray msg;
        #endif

        msg.data.resize(24);

        // [0..11] in actions
        std::copy(this->output_dof_pos.begin(), this->output_dof_pos.end(), msg.data.begin());
        // [12..23] in joint positions
        std::copy(this->obs.dof_pos.begin(), this->obs.dof_pos.end(), msg.data.begin() + 12);
        #if defined(USE_ROS1) && defined(USE_ROS)
            this->action_dof_pos_publisher.publish(msg);
        #elif defined(USE_ROS2) && defined(USE_ROS)
            this->action_dof_pos_publisher->publish(msg);
        #endif
        

        if (!this->output_dof_pos.empty())
        {
            output_dof_pos_queue.push(this->output_dof_pos);
        }
        if (!this->output_dof_vel.empty())
        {
            output_dof_vel_queue.push(this->output_dof_vel);
        }
        if (!this->output_dof_tau.empty())
        {
            output_dof_tau_queue.push(this->output_dof_tau);
        }

        // this->TorqueProtect(this->output_dof_tau);
        // this->AttitudeProtect(this->robot_state.imu.quaternion, 75.0f, 75.0f);

#ifdef CSV_LOGGER
        std::vector<float> tau_est = this->robot_state.motor_state.tau_est;
        this->CSVLogger(this->output_dof_tau, tau_est, this->obs.dof_pos, this->output_dof_pos, this->obs.dof_vel);
#endif
    }
}

std::vector<float> RL_Real::Forward()
{
    std::unique_lock<std::mutex> lock(this->model_mutex, std::try_to_lock);

    // If model is being reinitialized, return previous actions to avoid blocking
    if (!lock.owns_lock())
    {
        std::cout << LOGGER::WARNING << "Model is being reinitialized, using previous actions" << std::endl;
        return this->obs.actions;
    }

    // std::vector<float> clamped_obs = this->ComputeObservation();
    std::vector<float> clamped_obs;
    
    #if defined(USE_ROS1)
        if (this->use_replay_clamped_obs && this->has_replay_clamped_obs)
        {
            // Use clamped_obs from replay topic
            clamped_obs = this->replay_clamped_obs;
        }
        else
        {
            // Normal sim path
            clamped_obs = this->ComputeObservation();
        }
    #endif
    #if defined(USE_ROS1) && defined(USE_ROS)
        std_msgs::Float32MultiArray obs_msg;
    #elif defined(USE_ROS2) && defined(USE_ROS)
        std_msgs::msg::Float32MultiArray obs_msg;
    #endif

    obs_msg.data.resize(clamped_obs.size());
    std::copy(clamped_obs.begin(), clamped_obs.end(), obs_msg.data.begin());
    #if defined(USE_ROS1) && defined(USE_ROS)
        this->clamped_obs_publisher.publish(obs_msg);
    #elif defined(USE_ROS2) && defined(USE_ROS)
        this->clamped_obs_publisher->publish(obs_msg);
    #endif

    std::vector<float> actions;
    if (!this->params.Get<std::vector<int>>("observations_history").empty())
    {
        this->history_obs_buf.insert(clamped_obs);
        this->history_obs = this->history_obs_buf.get_obs_vec(this->params.Get<std::vector<int>>("observations_history"));
        actions = this->model->forward({this->history_obs});
    }
    else
    {
        actions = this->model->forward({clamped_obs});
    }

    if (!this->params.Get<std::vector<float>>("clip_actions_upper").empty() && !this->params.Get<std::vector<float>>("clip_actions_lower").empty())
    {
        return clamp(actions, this->params.Get<std::vector<float>>("clip_actions_lower"), this->params.Get<std::vector<float>>("clip_actions_upper"));
    }
    else
    {
        return actions;
    }
}

void RL_Real::Plot()
{
    this->plot_t.erase(this->plot_t.begin());
    this->plot_t.push_back(this->motiontime);
    plt::cla();
    plt::clf();
    for (int i = 0; i < this->params.Get<int>("num_of_dofs"); ++i)
    {
        this->plot_real_joint_pos[i].erase(this->plot_real_joint_pos[i].begin());
        this->plot_target_joint_pos[i].erase(this->plot_target_joint_pos[i].begin());
        this->plot_real_joint_pos[i].push_back(this->motor_state.motor_state[i].q);
        this->plot_target_joint_pos[i].push_back(this->joint_cmd_msg.motor_cmd[i].q);
        plt::subplot(this->params.Get<int>("num_of_dofs"), 1, i + 1);
        plt::named_plot("_real_joint_pos", this->plot_t, this->plot_real_joint_pos[i], "r");
        plt::named_plot("_target_joint_pos", this->plot_t, this->plot_target_joint_pos[i], "b");
        plt::xlim(this->plot_t.front(), this->plot_t.back());
    }
    // plt::legend();
    plt::pause(0.0001);
}

#if !defined(USE_CMAKE) && defined(USE_ROS)
void RL_Real::JoyCallback(
#if defined(USE_ROS1)
    const sensor_msgs::Joy::ConstPtr &msg
#elif defined(USE_ROS2)
    const sensor_msgs::msg::Joy::SharedPtr msg
#endif
)
{
    this->joy_msg = *msg;

    if (this->joy_msg.axes[5] < 0.5) // GETUP
    {
        this->control.SetGamepad(Input::Gamepad::A);
    }
    else if (this->joy_msg.axes[2] < 0.5) // GETDOWN
    {
        this->control.SetGamepad(Input::Gamepad::B);
    }
    else if (this->joy_msg.buttons[4]) // RL himloco
    {
        this->control.SetGamepad(Input::Gamepad::RB_DPadUp); //himloco
    }
    else if (this->joy_msg.buttons[5]) // RL himloco
    {
        this->control.SetGamepad(Input::Gamepad::RB_DPadLeft); //parkour
    }
    // else if (this->joy_msg.buttons[9]) // Servo On
    // {
    //     std_msgs::Bool msg;
    //     msg.data = false;
    //     motor_tolerance_publisher.publish(msg);
    //     msg.data = true;
    //     motor_servo_publisher.publish(msg);
    //     std::cout << LOGGER::INFO << "Start Servo On" << std::endl;
    //     usleep(1000000);
    //     for (int i = 0; i < this->params.Get<int>("num_of_dofs"); ++i)
    //     {
    //         this->joint_cmd_msg.motor_cmd[i].kp = this->robot_command.motor_command.kp[this->params.Get<std::vector<int>>("joint_mapping")[i]];
    //         this->joint_cmd_msg.motor_cmd[i].kd = this->robot_command.motor_command.kd[this->params.Get<std::vector<int>>("joint_mapping")[i]];
    //     }
    //     this->joint_cmd_msg.cmd = "gain";
    //     motor_cmd_publisher.publish(joint_cmd_msg);
    // }
    // else if (this->joy_msg.buttons[8]) // Servo off
    // {
    //     std_msgs::Bool msg;
    //     msg.data = false;
    //     motor_servo_publisher.publish(msg);
    //     std::cout << LOGGER::INFO << "Start Servo Off" << std::endl;
    // }

    this->control.x = this->joy_msg.axes[1]; // Ly
    this->control.y = this->joy_msg.axes[3]; // Lx
    this->control.yaw = this->joy_msg.axes[0]; // Rx
}

void RL_Real::ImuCallback(
#if defined(USE_ROS1)
    const sensor_msgs::Imu::ConstPtr &msg
#elif defined(USE_ROS2)
    const sensor_msgs::msg::Imu::SharedPtr msg
#endif
)
{
    this->imu = *msg;
}

void RL_Real::MotorStatusCallback(
#if defined(USE_ROS1)
    const motor_msg::LowState::ConstPtr &msg
#elif defined(USE_ROS2)
    const motor_msg::msg::LowState::SharedPtr msg
#endif
)
{
    this->motor_state = *msg;
}

#endif

void RL_Real::ReplayClampedObsCallback(
#if defined(USE_ROS1)
    const std_msgs::Float32MultiArray::ConstPtr &msg
#elif defined(USE_ROS2)
    const std_msgs::msg::Float32MultiArray::SharedPtr msg
#endif
)
{
    this->replay_clamped_obs.assign(msg->data.begin(), msg->data.end());
    this->has_replay_clamped_obs = true;
}

#if !defined(USE_CMAKE) && defined(USE_ROS)
void RL_Real::CmdvelCallback(
#if defined(USE_ROS1) && defined(USE_ROS)
    const geometry_msgs::Twist::ConstPtr &msg
#elif defined(USE_ROS2) && defined(USE_ROS)
    const geometry_msgs::msg::Twist::SharedPtr msg
#endif
)
{
    this->cmd_vel = *msg;
}
#endif

#if !defined(USE_CMAKE) && defined(USE_ROS)
void RL_Real::DepthCallback(
#if defined(USE_ROS1) && defined(USE_ROS)
    const std_msgs::Float32MultiArray::ConstPtr &msg
#elif defined(USE_ROS2) && defined(USE_ROS)
    const std_msgs::msg::Float32MultiArray::SharedPtr msg
#endif
)
{
    this->depth_data = *msg;
    // std::cout << "Depth data size: " << msg->data.size() << std::endl;
}
#endif

#if defined(USE_ROS1) && defined(USE_ROS)
void signalHandler(int signum)
{
    ros::shutdown();
    exit(0);
}
#elif defined(USE_CMAKE) || !defined(USE_ROS)
// Signal handler for CMAKE mode
volatile sig_atomic_t g_shutdown_requested = 0;
void signalHandler(int signum)
{
    std::cout << LOGGER::INFO << "Received signal " << signum << ", shutting down..." << std::endl;
    g_shutdown_requested = 1;
}
#endif

int main(int argc, char **argv)
{
    // if (argc < 2)
    // {
    //     std::cout << LOGGER::ERROR << "Usage: " << argv[0] << " networkInterface [wheel]" << std::endl;
    //     throw std::runtime_error("Invalid arguments");
    // }
    // ChannelFactory::Instance()->Init(0, argv[1]);

#if defined(USE_ROS1) && defined(USE_ROS)
    signal(SIGINT, signalHandler);
    ros::init(argc, argv, "rl_ITRI");
    RL_Real rl_itri(argc, argv);
    ros::spin();
#elif defined(USE_ROS2) && defined(USE_ROS)
    rclcpp::init(argc, argv);
    auto rl_itri = std::make_shared<RL_Real>(argc, argv);
    rclcpp::spin(rl_itri->ros2_node);
    rclcpp::shutdown();
#elif defined(USE_CMAKE) || !defined(USE_ROS)
    signal(SIGINT, signalHandler);
    RL_Real rl_itri(argc, argv);
    while (!g_shutdown_requested) { sleep(1); }
    std::cout << LOGGER::INFO << "Exiting..." << std::endl;
#endif

    return 0;
}