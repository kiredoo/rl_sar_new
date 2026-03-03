/*
 * Copyright (c) 2024-2025 Ziqi Fan
 * SPDX-License-Identifier: Apache-2.0
 */

#include "rl_sdk.hpp"

void RL::StateController(const RobotState<float>* state, RobotCommand<float>* command)
{
    auto updateState = [&](std::shared_ptr<FSMState> statePtr)
    {
        if (auto rl_fsm_state = std::dynamic_pointer_cast<RLFSMState>(statePtr))
        {
            rl_fsm_state->fsm_state = state;
            rl_fsm_state->fsm_command = command;
        }
    };
    for (auto& pair : fsm.states_)
    {
        updateState(pair.second);
    }

    fsm.Run();

    this->motiontime++;

    if (this->control.current_keyboard == Input::Keyboard::W)
    {
        this->control.x += 0.1f;
    }
    if (this->control.current_keyboard == Input::Keyboard::S)
    {
        this->control.x -= 0.1f;
    }
    if (this->control.current_keyboard == Input::Keyboard::A)
    {
        this->control.y += 0.1f;
    }
    if (this->control.current_keyboard == Input::Keyboard::D)
    {
        this->control.y -= 0.1f;
    }
    if (this->control.current_keyboard == Input::Keyboard::Q)
    {
        this->control.yaw += 0.1f;
    }
    if (this->control.current_keyboard == Input::Keyboard::E)
    {
        this->control.yaw -= 0.1f;
    }
    if (this->control.current_keyboard == Input::Keyboard::Space)
    {
        this->control.x = 0.0f;
        this->control.y = 0.0f;
        this->control.yaw = 0.0f;
    }
    if (this->control.current_keyboard == Input::Keyboard::N || this->control.current_gamepad == Input::Gamepad::X)
    {
        this->control.navigation_mode = !this->control.navigation_mode;
        std::cout << std::endl << LOGGER::INFO << "Navigation mode: " << (this->control.navigation_mode ? "ON" : "OFF") << std::endl;
    }
}

std::vector<float> RL::ComputeObservation()
{
    std::vector<std::vector<float>> obs_list;
    std::vector<std::vector<float>> proprio_list;

    for (const std::string &observation : this->params.Get<std::vector<std::string>>("observations"))
    {
        // ============= Base Observations =============
        if (observation == "lin_vel")
        {
            obs_list.push_back(this->obs.lin_vel * this->params.Get<float>("lin_vel_scale"));
        }
        else if (observation == "ang_vel")
        {
            // In ROS1 Gazebo, the coordinate system for angular velocity is in the world coordinate system.
            // In ROS2 Gazebo, mujoco and real robot, the coordinate system for angular velocity is in the body coordinate system.
            if (this->ang_vel_axis == "body")
            {
                obs_list.push_back(this->obs.ang_vel * this->params.Get<float>("ang_vel_scale"));
            }
            else if (this->ang_vel_axis == "world")
            {
                obs_list.push_back(QuatRotateInverse(this->obs.base_quat, this->obs.ang_vel) * this->params.Get<float>("ang_vel_scale"));
            }
        }
        else if (observation == "gravity_vec")
        {
            // obs_list.push_back(QuatRotateInverse(this->obs.base_quat, this->obs.gravity_vec));

            std::vector<float> fixed_quat = this->obs.base_quat;
            

            obs_list.push_back(QuatRotateInverse(fixed_quat, this->obs.gravity_vec));
        }
        else if (observation == "commands")
        {
            obs_list.push_back(this->obs.commands * this->params.Get<std::vector<float>>("commands_scale"));
        }
        else if (observation == "dof_pos")
        {
            std::vector<float> dof_pos_rel = this->obs.dof_pos - this->params.Get<std::vector<float>>("default_dof_pos");
            for (int i : this->params.Get<std::vector<int>>("wheel_indices"))
            {
                dof_pos_rel[i] = 0.0f;
            }

            auto action_scale = this->params.Get<std::vector<float>>("action_scale");
            for (size_t i = 0; i < dof_pos_rel.size(); ++i)
            {
                float sign = (action_scale[i] >= 0) ? 1.0f : -1.0f;
                dof_pos_rel[i] *= sign;
            }

            obs_list.push_back(dof_pos_rel * this->params.Get<float>("dof_pos_scale"));
        }
        else if (observation == "dof_vel")
        {
            std::vector<float> dof_vel_obs = this->obs.dof_vel;

            auto action_scale = this->params.Get<std::vector<float>>("action_scale");
            for (size_t i = 0; i < dof_vel_obs.size(); ++i)
            {
                float sign = (action_scale[i] >= 0) ? 1.0f : -1.0f;
                dof_vel_obs[i] *= sign;
            }

            obs_list.push_back(this->obs.dof_vel * this->params.Get<float>("dof_vel_scale"));
        }
        else if (observation == "actions")
        {
            obs_list.push_back(this->obs.actions);
        }
        // ============= Other Observations =============
        else if (observation == "whole_body_tracking/motion_command")
        {
            std::vector<float> motion_cmd;
            if (this->motion_loader)
            {
                auto joint_pos_sdk = this->motion_loader->GetJointPos();
                auto joint_vel_sdk = this->motion_loader->GetJointVel();
                auto joint_mapping = this->params.Get<std::vector<int>>("joint_mapping");
                std::vector<float> joint_pos_training(joint_mapping.size());
                std::vector<float> joint_vel_training(joint_mapping.size());
                for (size_t i = 0; i < joint_mapping.size(); ++i)
                {
                    joint_pos_training[i] = joint_pos_sdk[joint_mapping[i]];
                    joint_vel_training[i] = joint_vel_sdk[joint_mapping[i]];
                }
                motion_cmd.insert(motion_cmd.end(), joint_pos_training.begin(), joint_pos_training.end());
                motion_cmd.insert(motion_cmd.end(), joint_vel_training.begin(), joint_vel_training.end());
            }
            else
            {
                motion_cmd.resize(this->params.Get<int>("num_of_dofs") * 2, 0.0f);
            }
            obs_list.push_back(motion_cmd);
        }
        else if (observation == "whole_body_tracking/motion_anchor_ori_b")
        {
            std::vector<float> anchor_ori(6, 0.0f);
            if (this->motion_loader)
            {
                auto waist_sdk_indices = this->params.Get<std::vector<int>>("waist_joint_indices");
                std::vector<float> waist_angles = {
                    this->obs.dof_pos[InverseJointMapping(waist_sdk_indices[0])],
                    this->obs.dof_pos[InverseJointMapping(waist_sdk_indices[1])],
                    this->obs.dof_pos[InverseJointMapping(waist_sdk_indices[2])]
                };
                std::vector<float> robot_torso_quat_w = MotionLoader::ComputeTorsoQuat(this->obs.base_quat, waist_angles);
                std::vector<float> ref_torso_quat_w = this->motion_loader->GetAnchorQuat();
                std::vector<float> init_quat = this->motion_loader->GetInitQuat();
                std::vector<float> motion_anchor_quat_w = QuaternionMultiply(init_quat, ref_torso_quat_w);
                std::vector<float> robot_quat_inv = QuaternionConjugate(robot_torso_quat_w);
                std::vector<float> relative_quat = QuaternionMultiply(robot_quat_inv, motion_anchor_quat_w);
                std::vector<float> rot_matrix = QuaternionToRotationMatrix(relative_quat);
                anchor_ori = MatrixFirstTwoColumns(rot_matrix);
            }
            obs_list.push_back(anchor_ori);
        }
        else if (observation == "RoboMimic_Deploy/phase")
        {
            float motion_time = this->episode_length_buf * this->params.Get<float>("dt") * this->params.Get<int>("decimation");
            float count = motion_time;
            float phase = count / this->motion_length;
            std::vector<float> phase_vec = {phase};
            obs_list.push_back(phase_vec);
        }
        // ============= Parkour Observations =============
        else if (observation == "commands_vx")
        {
            auto scale = this->params.Get<std::vector<float>>("commands_scale");
            std::vector<float> cmd_vx(3, 0.0f);
            // cmd_vx[2] = this->obs.commands[0] * this->params.Get<std::vector<float>>("commands_scale")[0];   // [0, 0, x*scale_x]
            cmd_vx[0] = this->obs.commands[1] * scale[1];
            cmd_vx[1] = 0.0f;
            cmd_vx[2] = this->obs.commands[0] * scale[0];
            obs_list.push_back(cmd_vx);
        }
        else if (observation == "imu_rp") // should get [roll, pitch] from imu
        {
            std::vector<float> imu_rpy = QuaternionToEuler(this->obs.base_quat);
            obs_list.push_back({imu_rpy[0], imu_rpy[1]});
        }
        else if (observation == "delta_yaw")
        {
            // It is good now, the value would be inserted at depth_latent output
            obs_list.push_back({0.0f, 0.0f, 0.0f});
            // proprio[:, 6:8] = yaw (get from depth encoder output (depth_latent))
            // [0, delta_yaw, delta_next_yaw] -> [5 ,6 ,7] in proprio
        }
        else if (observation == "parkour_mode")
        {
            // Use parkour mode for now
            std::vector<float> walk = {0.0f, 1.0f};
            std::vector<float> parkour = {1.0f, 0.0f};
            obs_list.push_back(parkour);
        }
        else if (observation == "contact")
        {
            // should get from feet contact sensor but we trained a student model that set foot contact as zero
            obs_list.push_back({0.0f, 0.0f, 0.0f, 0.0f});
        }
        else if (observation == "depth_latent") // should get from image encoder
        {
            auto image = this->obs.depth_data;
            
            std::vector<float> proprio;
            for (const auto& vec : obs_list) {
                proprio.insert(proprio.end(), vec.begin(), vec.end());
            }

            // depth_latent_yaw first 32: depth_latent, last 2: yaw
            std::vector<float> depth_latent_yaw;
            if (this->episode_length_buf % 5 == 0 || this->last_depth_latent_yaw.empty()) {
                depth_latent_yaw = this->depth_model->depth_forward(image, proprio);
            }else {
                depth_latent_yaw = this->last_depth_latent_yaw;
            }
            this->last_depth_latent_yaw = depth_latent_yaw;

            // depth encoder output
            std::vector<float> depth_latent(depth_latent_yaw.begin(), depth_latent_yaw.begin() + 32);
            std::vector<float> yaw(depth_latent_yaw.begin() + 32, depth_latent_yaw.end());
            if (yaw.size() != 2) {
                throw std::runtime_error(
                    "RL::ComputeObservation(): expected yaw size 2, got "
                    + std::to_string(yaw.size()));
            }

            // Yaw from command instead of depth encoder output (controllable purpose)
            if (this->obs.commands[2] > 0.2) {
                yaw[0] = this->obs.commands[2] * this->params.Get<std::vector<float>>("commands_scale")[2]; // delta_yaw
                yaw[1] = this->obs.commands[2] * this->params.Get<std::vector<float>>("commands_scale")[2] * 1.2; // delta_yaw_next
            }
            // insert yaw into obs_list
            obs_list[2][1] = yaw[0] * 1.5; // delta_yaw
            obs_list[2][2] = yaw[1] * 1.5; // delta_yaw_next

            // Save current obs_list to proprio_list for estimator and history encoder use
            proprio_list.clear();
            proprio_list = obs_list;

            // push only 32-dim depth_latent into obs_list
            obs_list.push_back(depth_latent);

            // std::cout << "\n"<< "[depth_latent_yaw] size = " << depth_latent_yaw.size() << "\n";
            // std::cout << "[depth_latent_yaw] values: [";
            // for (size_t i = 0; i < depth_latent_yaw.size(); ++i) {
            //     std::cout << depth_latent_yaw[i];
            //     if (i + 1 < depth_latent_yaw.size()) {
            //         std::cout << ", ";
            //     }
            // }
            // std::cout << "]" << std::endl;
        }
        else if (observation == "lin_vel_latent") // should get from estimator
        {
            std::vector<float> proprio(53, 0.0f);
            proprio.clear();
            for (const auto& vec : proprio_list) { // Flatten proprio_list into proprio
                proprio.insert(proprio.end(), vec.begin(), vec.end());
            }

            std::vector<float> lin_vel_latent = this->model->estimator(proprio);
            obs_list.push_back(lin_vel_latent);

            // std::cout << "[lin_vel_latent] size = " << lin_vel_latent.size() << "\n";
            // std::cout << "[lin_vel_latent] values: [";
            // for (size_t i = 0; i < lin_vel_latent.size(); ++i) {
            //     std::cout << lin_vel_latent[i];
            //     if (i + 1 < lin_vel_latent.size()) {
            //         std::cout << ", ";
            //     }
            // }
            // std::cout << "]" << std::endl;
        }
        else if (observation == "priv_latent") //should get from history encoder
        {   
            std::vector<float> proprio(53, 0.0f);
            proprio.clear();
            for (const auto& vec : proprio_list) {
                proprio.insert(proprio.end(), vec.begin(), vec.end());
            }

            // 判斷是否 episode reset
            bool episode_reset = (this->episode_length_buf <= 1);
            this->push_proprio(proprio, episode_reset);

            auto priv_latent = this->model->history_encoder(hist_proprio);
            obs_list.push_back(priv_latent); 

            // std::cout << "[priv_latent] size = " << priv_latent.size() << "\n";
            // std::cout << "[priv_latent] values: [";
            // for (size_t i = 0; i < priv_latent.size(); ++i) {
            //     std::cout << priv_latent[i];
            //     if (i + 1 < priv_latent.size()) {
            //         std::cout << ", ";
            //     }
            // }
            // std::cout << "]" << std::endl;
        }
    }

    this->obs_dims.clear();
    for (const auto& obs : obs_list)
    {
       this->obs_dims.push_back(obs.size());
    }

    std::vector<float> obs;
    for (const auto& obs_vec : obs_list)
    {
        obs.insert(obs.end(), obs_vec.begin(), obs_vec.end());
    }
    std::vector<float> clamped_obs = clamp(obs, -this->params.Get<float>("clip_obs"), this->params.Get<float>("clip_obs"));
    return clamped_obs;
}

void RL::push_proprio(const std::vector<float>& proprio, bool episode_reset)
{
    static constexpr size_t N_HIST  = 10;  // history 長度
    static constexpr size_t N_PROP  = 53;  // proprio 維度
    static constexpr size_t HIST_DIM = N_HIST * N_PROP;
    // 要求 proprio 維度必須是 53
    if (proprio.size() != N_PROP) return;

    // 確保 buffer 大小正確
    if (hist_proprio.size() != HIST_DIM) hist_proprio.assign(HIST_DIM, 0.0f);

    if (episode_reset) {
        // torch.stack([proprio]*n_hist_len, dim=1) => 每一個時間步都填同一個 proprio
        for (size_t t = 0; t < N_HIST; ++t) {
            float* dst = hist_proprio.data() + t * N_PROP;
            std::copy(proprio.begin(), proprio.end(), dst);
        }
    } else {
        // torch.cat([history[:,1:], proprio.unsqueeze(1)], dim=1)
        // 對單一 env 來說: 時間往前平移一格 (丟掉最老的 t=0, 其他 t-1)
        // shift left by 1 step: [t0, t1, ..., t8, t9] -> [t1, t2, ..., t9, ?]
        // flatten 表示就是整個 vector 從 index 53 開始 copy 到 index 0
        std::copy(
            hist_proprio.begin() + N_PROP,  // 來源起點: 原本 t=1
            hist_proprio.end(),             // 來源終點: 原本 t=9
            hist_proprio.begin()            // 目標: t=0
        );
        // 把新的 proprio 填進最後一個 block (t = N_HIST-1)
        float* last_block = hist_proprio.data() + (N_HIST - 1) * N_PROP;
        std::copy(proprio.begin(), proprio.end(), last_block);
    }
}

void RL::InitObservations()
{
    this->hist_proprio.clear();
    this->last_depth_latent_yaw.clear();
    this->obs.lin_vel = {0.0f, 0.0f, 0.0f};
    this->obs.ang_vel = {0.0f, 0.0f, 0.0f};
    this->obs.gravity_vec = {0.0f, 0.0f, -1.0f};
    this->obs.commands = {0.0f, 0.0f, 0.0f};
    this->obs.base_quat = {0.0f, 0.0f, 0.0f, 1.0f};
    this->obs.dof_pos = this->params.Get<std::vector<float>>("default_dof_pos");
    this->obs.dof_vel.clear();
    this->obs.dof_vel.resize(this->params.Get<int>("num_of_dofs"), 0.0f);
    this->obs.actions.clear();
    this->obs.actions.resize(this->params.Get<int>("num_of_dofs"), 0.0f);
    this->obs.depth_data.clear();
    this->obs.depth_data.resize(this->params.Get<int>("depth_width")*this->params.Get<int>("depth_height"), 0.0f);
    this->obs.depth_latent.clear();
    this->obs.depth_latent.resize(32, 0.0f);
    this->obs.lin_vel_latent.clear();
    this->obs.lin_vel_latent.resize(9, 0.0f);
    this->obs.priv_latent.clear();
    this->obs.priv_latent.resize(20, 0.0f);
    this->ComputeObservation();
}


void RL::InitOutputs()
{
    int num_of_dofs = this->params.Get<int>("num_of_dofs");
    this->output_dof_tau.clear();
    this->output_dof_tau.resize(num_of_dofs, 0.0f);
    this->output_dof_pos = this->params.Get<std::vector<float>>("default_dof_pos");
    this->output_dof_vel.clear();
    this->output_dof_vel.resize(num_of_dofs, 0.0f);
}

void RL::InitControl()
{
    this->control.x = 0.0f;
    this->control.y = 0.0f;
    this->control.yaw = 0.0f;
}

void RL::InitJointNum(size_t num_joints)
{
    this->robot_state.motor_state.resize(num_joints);
    this->start_state.motor_state.resize(num_joints);
    this->now_state.motor_state.resize(num_joints);
    this->robot_command.motor_command.resize(num_joints);
}

void RL::InitRL(std::string robot_config_path)
{
    std::lock_guard<std::mutex> lock(this->model_mutex);

    this->ReadYaml(robot_config_path, "config.yaml");

    // init joint num first
    this->InitJointNum(this->params.Get<int>("num_of_dofs"));

    // init model
    std::string model_path = std::string(POLICY_DIR) + "/" + robot_config_path + "/" + this->params.Get<std::string>("model_name");
    this->model = InferenceRuntime::ModelFactory::load_model(model_path);
    if (!this->model)
    {
        throw std::runtime_error("Failed to load model from: " + model_path);
    }
    //  init depth model
    if (this->config_name == "extreme_parkour")
    {
        std::string depth_model_path = std::string(POLICY_DIR) + "/" + robot_config_path + "/" + this->params.Get<std::string>("depth_model_name");
        std::cout << LOGGER::INFO << "Loading Depth model: " << depth_model_path << std::endl;
        this->depth_model = InferenceRuntime::ModelFactory::load_model(depth_model_path);
        if (!this->depth_model)
        {
            throw std::runtime_error("Failed to load depth model from: " + depth_model_path);
        }
    }
    
    // init rl
    this->InitObservations();
    this->InitOutputs();
    this->InitControl();

    // init obs history
    const auto& observations_history = this->params.Get<std::vector<int>>("observations_history");  // avoid dangling reference
    if (!observations_history.empty())
    {
        int history_length = *std::max_element(observations_history.begin(), observations_history.end()) + 1;
        this->history_obs_buf = ObservationBuffer(1, this->obs_dims, history_length, this->params.Get<std::string>("observations_history_priority"));
    }
}

void RL::ComputeOutput(const std::vector<float> &actions, std::vector<float> &output_dof_pos, std::vector<float> &output_dof_vel, std::vector<float> &output_dof_tau)
{
    std::vector<float> actions_scaled = actions * this->params.Get<std::vector<float>>("action_scale");
    auto default_dof_pos = this->params.Get<std::vector<float>>("default_dof_pos");
    std::vector<float> pos_actions_scaled = actions_scaled;
    std::vector<float> vel_actions_scaled(actions.size(), 0.0f);
    for (int i : this->params.Get<std::vector<int>>("wheel_indices"))
    {
        pos_actions_scaled[i] = 0.0f;
        vel_actions_scaled[i] = actions_scaled[i];
    }
    std::vector<float> all_actions_scaled = pos_actions_scaled + vel_actions_scaled;
    output_dof_pos = pos_actions_scaled + this->params.Get<std::vector<float>>("default_dof_pos");
    output_dof_vel = vel_actions_scaled;
    output_dof_tau = this->params.Get<std::vector<float>>("rl_kp") * (all_actions_scaled + this->params.Get<std::vector<float>>("default_dof_pos") - this->obs.dof_pos) - this->params.Get<std::vector<float>>("rl_kd") * this->obs.dof_vel;
    output_dof_tau = clamp(output_dof_tau, -this->params.Get<std::vector<float>>("torque_limits"), this->params.Get<std::vector<float>>("torque_limits"));

    // static int debug_print_counter = 0;
    // if (debug_print_counter++ % 50 == 0) 
    // {
    //     auto mapping = this->params.Get<std::vector<int>>("joint_mapping");
    //     auto default_dof_pos = this->params.Get<std::vector<float>>("default_dof_pos");
    //     int num_dofs = this->params.Get<int>("num_of_dofs");

    //     std::cout << "\n" << "\033[1;36m" << "--- [DEBUG] 所有馬達對齊狀態 (每50次輸出一回) ---" << "\033[0m" << std::endl;
    //     std::cout << "模型索引(M) -> 機器人索引(R) | 目標(Target) | 實際(Obs) | 誤差(Err)" << std::endl;
    //     std::cout << "---------------------------------------------------------------" << std::endl;

    //     for (int i = 0; i < num_dofs; ++i) 
    //     {
    //         int robot_idx = mapping[i];
            
    //         // 注意：這裡計算 Target 的方式必須跟你的程式碼邏輯一致
    //         // 如果你的程式碼還沒改，這裡顯示的就是「如果映射成功後」該有的數值
    //         float target = all_actions_scaled[i] + default_dof_pos[robot_idx];
    //         float obs_val = this->obs.dof_pos[robot_idx];
    //         float error = target - obs_val;

    //         // 格式化輸出，讓數字對齊好讀
    //         printf("M[%2d] -> R[%2d] | Target: %6.3f | Obs: %6.3f | Err: %6.3f", 
    //                 i, robot_idx, target, obs_val, error);
            
    //         // 如果誤差太大（例如大於 0.5），印出一個警告符號
    //         if (std::abs(error) > 0.5f) printf("  \033[1;31m[!] 嚴重偏差\033[0m");
            
    //         printf("\n");
    //     }
    //     std::cout << "---------------------------------------------------------------" << std::endl;
    // }
}

int RL::InverseJointMapping(int idx) const
{
    auto joint_mapping = this->params.Get<std::vector<int>>("joint_mapping");
    for (size_t i = 0; i < joint_mapping.size(); ++i) {
        if (joint_mapping[i] == idx) return (int)i;
    }
    return -1;
}

void RL::TorqueProtect(const std::vector<float>& origin_output_dof_tau)
{
    std::vector<int> out_of_range_indices;
    std::vector<float> out_of_range_values;
    for (size_t i = 0; i < origin_output_dof_tau.size(); ++i)
    {
        float torque_value = origin_output_dof_tau[i];
        float limit_lower = -this->params.Get<std::vector<float>>("torque_limits")[i];
        float limit_upper = this->params.Get<std::vector<float>>("torque_limits")[i];

        if (torque_value < limit_lower || torque_value > limit_upper)
        {
            out_of_range_indices.push_back(i);
            out_of_range_values.push_back(torque_value);
        }
    }
    if (!out_of_range_indices.empty())
    {
        for (size_t i = 0; i < out_of_range_indices.size(); ++i)
        {
            int index = out_of_range_indices[i];
            float value = out_of_range_values[i];
            float limit_lower = -this->params.Get<std::vector<float>>("torque_limits")[index];
            float limit_upper = this->params.Get<std::vector<float>>("torque_limits")[index];

            std::cout << LOGGER::WARNING << "Torque(" << index + 1 << ")=" << value << " out of range(" << limit_lower << ", " << limit_upper << ")" << std::endl;
        }
        // Just a reminder, no protection
        // this->control.SetKeyboard(Input::Keyboard::P);
        std::cout << LOGGER::INFO << "Switching to STATE_POS_GETDOWN"<< std::endl;
    }
}

void RL::AttitudeProtect(const std::vector<float> &quaternion, float pitch_threshold, float roll_threshold)
{
    // Use QuaternionToEuler from vector_math.hpp
    std::vector<float> euler = QuaternionToEuler(quaternion);
    float roll = euler[0] * 57.2958f;   // Convert to degrees
    float pitch = euler[1] * 57.2958f;

    if (std::fabs(roll) > roll_threshold)
    {
        this->control.SetKeyboard(Input::Keyboard::P);
        std::cout << LOGGER::WARNING << "Roll exceeds " << roll_threshold << " degrees. Current: " << roll << " degrees." << std::endl;
    }
    if (std::fabs(pitch) > pitch_threshold)
    {
        this->control.SetKeyboard(Input::Keyboard::P);
        std::cout << LOGGER::WARNING << "Pitch exceeds " << pitch_threshold << " degrees. Current: " << pitch << " degrees." << std::endl;
    }
}

#include <termios.h>
#include <sys/ioctl.h>
#include <fcntl.h>
#include <unistd.h>

static int kbhit()
{
    static bool initialized = false;
    static termios original_term;

    // Initialize terminal to non-canonical mode on first call
    if (!initialized)
    {
        tcgetattr(STDIN_FILENO, &original_term);

        termios new_term = original_term;
        new_term.c_lflag &= ~(ICANON | ECHO);  // Disable canonical mode and echo
        new_term.c_cc[VMIN] = 0;   // Non-blocking read
        new_term.c_cc[VTIME] = 0;  // No timeout

        tcsetattr(STDIN_FILENO, TCSANOW, &new_term);

        // Register cleanup function to restore terminal on exit
        static bool cleanup_registered = false;
        if (!cleanup_registered)
        {
            std::atexit([]() {
                tcsetattr(STDIN_FILENO, TCSANOW, &original_term);
            });
            cleanup_registered = true;
        }

        initialized = true;
    }

    // Non-blocking read of a single character
    char c;
    int result = read(STDIN_FILENO, &c, 1);

    return (result == 1) ? (unsigned char)c : -1;
}

void RL::KeyboardInterface()
{
    int c = kbhit();
    if (c > 0)
    {
        switch (c)
        {
        case '0': this->control.SetKeyboard(Input::Keyboard::Num0); break;
        case '1': this->control.SetKeyboard(Input::Keyboard::Num1); break;
        case '2': this->control.SetKeyboard(Input::Keyboard::Num2); break;
        case '3': this->control.SetKeyboard(Input::Keyboard::Num3); break;
        case '4': this->control.SetKeyboard(Input::Keyboard::Num4); break;
        case '5': this->control.SetKeyboard(Input::Keyboard::Num5); break;
        case '6': this->control.SetKeyboard(Input::Keyboard::Num6); break;
        case '7': this->control.SetKeyboard(Input::Keyboard::Num7); break;
        case '8': this->control.SetKeyboard(Input::Keyboard::Num8); break;
        case '9': this->control.SetKeyboard(Input::Keyboard::Num9); break;
        case 'a': case 'A': this->control.SetKeyboard(Input::Keyboard::A); break;
        case 'b': case 'B': this->control.SetKeyboard(Input::Keyboard::B); break;
        case 'c': case 'C': this->control.SetKeyboard(Input::Keyboard::C); break;
        case 'd': case 'D': this->control.SetKeyboard(Input::Keyboard::D); break;
        case 'e': case 'E': this->control.SetKeyboard(Input::Keyboard::E); break;
        case 'f': case 'F': this->control.SetKeyboard(Input::Keyboard::F); break;
        case 'g': case 'G': this->control.SetKeyboard(Input::Keyboard::G); break;
        case 'h': case 'H': this->control.SetKeyboard(Input::Keyboard::H); break;
        case 'i': case 'I': this->control.SetKeyboard(Input::Keyboard::I); break;
        case 'j': case 'J': this->control.SetKeyboard(Input::Keyboard::J); break;
        case 'k': case 'K': this->control.SetKeyboard(Input::Keyboard::K); break;
        case 'l': case 'L': this->control.SetKeyboard(Input::Keyboard::L); break;
        case 'm': case 'M': this->control.SetKeyboard(Input::Keyboard::M); break;
        case 'n': case 'N': this->control.SetKeyboard(Input::Keyboard::N); break;
        case 'o': case 'O': this->control.SetKeyboard(Input::Keyboard::O); break;
        case 'p': case 'P': this->control.SetKeyboard(Input::Keyboard::P); break;
        case 'q': case 'Q': this->control.SetKeyboard(Input::Keyboard::Q); break;
        case 'r': case 'R': this->control.SetKeyboard(Input::Keyboard::R); break;
        case 's': case 'S': this->control.SetKeyboard(Input::Keyboard::S); break;
        case 't': case 'T': this->control.SetKeyboard(Input::Keyboard::T); break;
        case 'u': case 'U': this->control.SetKeyboard(Input::Keyboard::U); break;
        case 'v': case 'V': this->control.SetKeyboard(Input::Keyboard::V); break;
        case 'w': case 'W': this->control.SetKeyboard(Input::Keyboard::W); break;
        case 'x': case 'X': this->control.SetKeyboard(Input::Keyboard::X); break;
        case 'y': case 'Y': this->control.SetKeyboard(Input::Keyboard::Y); break;
        case 'z': case 'Z': this->control.SetKeyboard(Input::Keyboard::Z); break;
        case ' ': this->control.SetKeyboard(Input::Keyboard::Space); break;
        case '\n': case '\r': this->control.SetKeyboard(Input::Keyboard::Enter); break;
        case 27:  // Escape sequence (for arrow keys on Unix/Linux/macOS)
        {
            char seq[2];
            // Try to read escape sequence non-blockingly
            if (read(STDIN_FILENO, &seq[0], 1) == 1)
            {
                if (seq[0] == '[')
                {
                    if (read(STDIN_FILENO, &seq[1], 1) == 1)
                    {
                        switch (seq[1])
                        {
                        case 'A': this->control.SetKeyboard(Input::Keyboard::Up); break;
                        case 'B': this->control.SetKeyboard(Input::Keyboard::Down); break;
                        case 'C': this->control.SetKeyboard(Input::Keyboard::Right); break;
                        case 'D': this->control.SetKeyboard(Input::Keyboard::Left); break;
                        default: break;
                        }
                    }
                }
                else
                {
                    // Plain escape key
                    this->control.SetKeyboard(Input::Keyboard::Escape);
                }
            }
            else
            {
                // Plain escape key
                this->control.SetKeyboard(Input::Keyboard::Escape);
            }
        } break;
        default:  break;
        }
    }
}

template <typename T>
std::vector<T> ReadVectorFromYaml(const YAML::Node &node)
{
    std::vector<T> values;
    for (const auto &val : node)
    {
        values.push_back(val.as<T>());
    }
    return values;
}

void RL::ReadYaml(const std::string& file_path, const std::string& file_name)
{
    std::string config_path = std::string(POLICY_DIR) + "/" + file_path + "/" + file_name;
    YAML::Node config;
    try
    {
        config = YAML::LoadFile(config_path)[file_path];
    }
    catch (YAML::BadFile &e)
    {
        std::cout << LOGGER::ERROR << "The file '" << config_path << "' does not exist" << std::endl;
        return;
    }

    for (auto it = config.begin(); it != config.end(); ++it)
    {
        std::string key = it->first.as<std::string>();
        this->params.config_node[key] = it->second;
    }
}

void RL::CSVInit(std::string robot_path)
{
    csv_filename = std::string(POLICY_DIR) + "/" + robot_path + "/motor";

    // Uncomment these lines if need timestamp for file name
    // auto now = std::chrono::system_clock::now();
    // std::time_t now_c = std::chrono::system_clock::to_time_t(now);
    // std::stringstream ss;
    // ss << std::put_time(std::localtime(&now_c), "%Y%m%d%H%M%S");
    // std::string timestamp = ss.str();
    // csv_filename += "_" + timestamp;

    csv_filename += ".csv";
    std::ofstream file(csv_filename.c_str());

    for(int i = 0; i < this->params.Get<int>("num_of_dofs"); ++i) { file << "tau_cal_" << i << ","; }
    for(int i = 0; i < this->params.Get<int>("num_of_dofs"); ++i) { file << "tau_est_" << i << ","; }
    for(int i = 0; i < this->params.Get<int>("num_of_dofs"); ++i) { file << "joint_pos_" << i << ","; }
    for(int i = 0; i < this->params.Get<int>("num_of_dofs"); ++i) { file << "joint_pos_target_" << i << ","; }
    for(int i = 0; i < this->params.Get<int>("num_of_dofs"); ++i) { file << "joint_vel_" << i << ","; }

    file << std::endl;

    file.close();
}

void RL::CSVLogger(const std::vector<float>& torque, const std::vector<float>& tau_est, const std::vector<float>& joint_pos, const std::vector<float>& joint_pos_target, const std::vector<float>& joint_vel)
{
    std::ofstream file(csv_filename.c_str(), std::ios_base::app);

    for(int i = 0; i < this->params.Get<int>("num_of_dofs"); ++i) { file << torque[i] << ","; }
    for(int i = 0; i < this->params.Get<int>("num_of_dofs"); ++i) { file << tau_est[i] << ","; }
    for(int i = 0; i < this->params.Get<int>("num_of_dofs"); ++i) { file << joint_pos[i] << ","; }
    for(int i = 0; i < this->params.Get<int>("num_of_dofs"); ++i) { file << joint_pos_target[i] << ","; }
    for(int i = 0; i < this->params.Get<int>("num_of_dofs"); ++i) { file << joint_vel[i] << ","; }

    file << std::endl;

    file.close();
}

bool RLFSMState::Interpolate(
    float& percent,
    const std::vector<float>& start_pos,
    const std::vector<float>& target_pos,
    float duration_seconds,
    const std::string& description,
    bool use_fixed_gains)
{
    if (percent >= 1.0f)
    {
        return false;
    }

    if (percent == 0.0f)
    {
        float max_diff = 0.0f;
        for (size_t i = 0; i < start_pos.size() && i < target_pos.size(); ++i)
        {
            max_diff = std::max(max_diff, std::abs(start_pos[i] - target_pos[i]));
        }

        if (max_diff < 0.1f)
        {
            percent = 1.0f;
        }
    }

    int required_frames = std::max(1, static_cast<int>(std::ceil(duration_seconds / rl.params.Get<float>("dt"))));
    float step = 1.0f / required_frames;

    percent += step;
    percent = std::min(percent, 1.0f);

    auto kp = use_fixed_gains ? rl.params.Get<std::vector<float>>("fixed_kp") : rl.params.Get<std::vector<float>>("rl_kp");
    auto kd = use_fixed_gains ? rl.params.Get<std::vector<float>>("fixed_kd") : rl.params.Get<std::vector<float>>("rl_kd");

    for (int i = 0; i < rl.params.Get<int>("num_of_dofs"); ++i)
    {
        fsm_command->motor_command.q[i] = (1 - percent) * start_pos[i] + percent * target_pos[i];
        fsm_command->motor_command.dq[i] = 0;
        fsm_command->motor_command.kp[i] = kp[i];
        fsm_command->motor_command.kd[i] = kd[i];
        fsm_command->motor_command.tau[i] = 0;
    }

    if (!description.empty())
    {
        LOGGER::PrintProgress(percent, description);
    }

    if (percent >= 1.0f)
    {
        return false;
    }

    return true;
}

void RLFSMState::RLControl()
{
    std::vector<float> _output_dof_pos, _output_dof_vel;
    if (rl.output_dof_pos_queue.try_pop(_output_dof_pos) && rl.output_dof_vel_queue.try_pop(_output_dof_vel))
    {
        for (int i = 0; i < rl.params.Get<int>("num_of_dofs"); ++i)
        {
            if (!_output_dof_pos.empty())
            {
                fsm_command->motor_command.q[i] = _output_dof_pos[i];
            }
            if (!_output_dof_vel.empty())
            {
                fsm_command->motor_command.dq[i] = _output_dof_vel[i];
            }
            fsm_command->motor_command.kp[i] = rl.params.Get<std::vector<float>>("rl_kp")[i];
            fsm_command->motor_command.kd[i] = rl.params.Get<std::vector<float>>("rl_kd")[i];
            fsm_command->motor_command.tau[i] = 0;
        }
    }
}
