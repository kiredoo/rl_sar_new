/*
 * Copyright (c) 2024-2025 ITRI
 * SPDX-License-Identifier: Apache-2.0
 */

#include "inference_runtime.hpp"
#include <stdexcept>
#include <iostream>
#include <numeric>

#ifdef USE_TORCH
#include <ATen/Parallel.h>
#endif

namespace InferenceRuntime
{

// ============================================================================
// TorchModel Implementation
// ============================================================================

TorchModel::TorchModel()
{
#ifdef USE_TORCH
    // Set threads before model load
    torch::set_num_threads(1);
#endif
}

TorchModel::~TorchModel()
{
}

bool TorchModel::load(const std::string& model_path)
{
    try
    {
#ifdef USE_TORCH
        // Load TorchScript model
        model_ = torch::jit::load(model_path);

        // For extreme_parkour actor model , try to get three submodules
        if (model_path.find("extreme_parkour/base_jit") != std::string::npos)
        {
            try
            {
                // estimator_ = model_.estimator.estimator
                estimator_ = model_.attr("estimator").toModule();
                // actor = model_.actor
                auto actor_model = model_.attr("actor").toModule();
                // hist_encoder_ = actor.history_encoder
                hist_encoder_ = actor_model.attr("history_encoder").toModule();
                // model_ = actor.actor_backbone (used as the main policy)
                model_ = actor_model.attr("actor_backbone").toModule();

                std::cout << LOGGER::INFO
                          << "Loaded parkour submodules (estimator, history_encoder, actor_backbone)"
                          << std::endl;
            }
            catch (const std::exception& e)
            {
                std::cout << LOGGER::WARNING
                          << "Failed to split extreme_parkour model into submodules, "
                          << "falling back to mono model. Reason: " << e.what()
                          << std::endl;
            }
        }

        model_path_ = model_path;
        loaded_ = true;
        std::cout << LOGGER::INFO << "Successfully loaded Torch model: " << model_path << std::endl;
        return true;
#else
        std::cout << LOGGER::WARNING << "Torch support not compiled. Please define USE_TORCH." << std::endl;
        loaded_ = false;
        return false;
#endif
    }
    catch (const std::exception& e)
    {
        std::cout << LOGGER::ERROR << "Failed to load Torch model: " << e.what() << std::endl;
        loaded_ = false;
        return false;
    }
}

std::vector<float> TorchModel::forward(const std::vector<std::vector<float>>& inputs)
{
    if (!loaded_)
    {
        throw std::runtime_error("Model not loaded");
    }

#ifdef USE_TORCH
    try
    {
        // Convert input vector to Torch tensor (use first input only)
        const auto& input = inputs[0];
        auto input_tensor = torch::tensor(input, torch::kFloat32).reshape({1, static_cast<int64_t>(input.size())});

        // Disable gradient computation before each forward pass
        torch::autograd::GradMode::set_enabled(false);

        // Ensure single-threaded execution (critical for performance!)
        torch::set_num_threads(1);

        // Execute forward inference
        auto output = model_.forward({input_tensor}).toTensor();

        // Convert output tensor to vector
        return torch_to_vector(output);
    }
    catch (const std::exception& e)
    {
        std::cout << LOGGER::ERROR << "Torch inference error: " << e.what() << std::endl;
        throw;
    }
#else
    throw std::runtime_error("Torch support not compiled");
#endif
}

void TorchModel::reset()
{
    if (!loaded_)
    {
        return;
    }

#ifdef USE_TORCH
    torch::InferenceMode guard(true);
    if (model_.find_method("reset"))
    {
        model_.run_method("reset");
    }
#endif
}

std::vector<float> TorchModel::estimator(const std::vector<float>& inputs)
{
    if (!loaded_)
    {
        throw std::runtime_error("Model not loaded");
    }

#ifdef USE_TORCH
    try
    {
        // Convert input vector to Torch tensor
        const auto& input = inputs;
        auto input_tensor = torch::tensor(input, torch::kFloat32).reshape({1, static_cast<int64_t>(input.size())});

        // Disable gradient computation before each forward pass
        torch::autograd::GradMode::set_enabled(false);

        // Ensure single-threaded execution (critical for performance!)
        torch::set_num_threads(1);

        // Execute forward inference
        auto output = estimator_.forward({input_tensor}).toTensor();

        // Convert output tensor to vector
        return torch_to_vector(output);
    }
    catch (const std::exception& e)
    {
        std::cout << LOGGER::ERROR << "Torch inference error: " << e.what() << std::endl;
        throw;
    }
#else
    throw std::runtime_error("Torch support not compiled");
#endif
}

std::vector<float> TorchModel::history_encoder(const std::vector<float>& inputs)
{
    if (!loaded_) {
        throw std::runtime_error("Model not loaded");
    }

#ifdef USE_TORCH
    try {
        const int64_t hist_len = 10;
        const int64_t n_propio = 53;

        // [1, hist_len, n_propio]
        auto input_tensor = torch::tensor(inputs, torch::kFloat32).reshape({1, hist_len, n_propio});

        torch::autograd::GradMode::set_enabled(false);
        torch::set_num_threads(1);

        // 關鍵：從 actor_backbone 拿到 index=1 的 ELU
        torch::jit::IValue activation_iv = model_.attr("1");

        // 準備 forward 的參數：[ELU, history_propio]
        std::vector<torch::jit::IValue> ivals;
        ivals.push_back(activation_iv);  // ELU
        ivals.push_back(input_tensor);   // history_propio

        // 呼叫 StateHistoryEncoder.forward(ELU, history_propio)
        auto output = hist_encoder_.forward(ivals).toTensor();

        return torch_to_vector(output);
    }
    catch (const std::exception& e) {
        std::cout << LOGGER::ERROR
                  << "Torch inference error (history_encoder): " << e.what()
                  << std::endl;
        throw;
    }
#else
    throw std::runtime_error("Torch support not compiled");
#endif
}

std::vector<float> TorchModel::depth_forward(const std::vector<float>& depth_vec,
                                             const std::vector<float>& proprio_vec)
{
    if (!loaded_) {
        throw std::runtime_error("Model not loaded");
    }

#ifdef USE_TORCH
    try {
        // Disable gradient computation and use pure inference mode
        torch::InferenceMode guard(true);

        // Ensure single-threaded execution (critical for performance!)
        torch::set_num_threads(1);

        // Hard-coded sizes for DepthOnlyFCBackbone58x87 + RecurrentDepthBackbone
        const int64_t H         = 58;
        const int64_t W         = 87;
        const int64_t N_PROPRIO = 53;

        if (static_cast<int64_t>(depth_vec.size()) != H * W) {
            throw std::runtime_error(
                "TorchModel::depth_forward(depth_vec): expected "
                + std::to_string(H * W) + " elements, got "
                + std::to_string(depth_vec.size()));
        }
        if (static_cast<int64_t>(proprio_vec.size()) != N_PROPRIO) {
            throw std::runtime_error(
                "TorchModel::depth_forward(proprio_vec): expected "
                + std::to_string(N_PROPRIO) + " elements, got "
                + std::to_string(proprio_vec.size()));
        }

        // depth_image: [1, 58, 87]
        auto depth_tensor = torch::tensor(depth_vec, torch::kFloat32).reshape({1, H, W});

        // proprio: [1, 53]
        auto proprio_tensor = torch::tensor(proprio_vec, torch::kFloat32).reshape({1, N_PROPRIO});

        std::vector<torch::jit::IValue> torch_inputs;
        torch_inputs.emplace_back(depth_tensor);
        torch_inputs.emplace_back(proprio_tensor);

        // Depth encoder forward
        torch::Tensor output = model_.forward(torch_inputs).toTensor();

        return torch_to_vector(output);
    }
    catch (const std::exception& e) {
        std::cout << LOGGER::ERROR
                  << "Torch inference error (depth_forward): "
                  << e.what() << std::endl;
        throw;
    }
#else
    throw std::runtime_error("Torch support not compiled");
#endif
}

#ifdef USE_TORCH
torch::Tensor TorchModel::vector_to_torch(const std::vector<float>& data, const std::vector<int64_t>& shape)
{
    // Use torch::tensor() + reshape() to match test program behavior
    auto tensor = torch::tensor(data, torch::kFloat32).reshape(shape);
    return tensor;
}

std::vector<float> TorchModel::torch_to_vector(const torch::Tensor& tensor)
{
    // Ensure tensor is contiguous and on CPU
    auto cpu_tensor = tensor.is_contiguous() ? tensor : tensor.contiguous();
    if (cpu_tensor.device().type() != torch::kCPU)
    {
        cpu_tensor = cpu_tensor.to(torch::kCPU);
    }

    // Get data pointer and size
    float* data_ptr = cpu_tensor.data_ptr<float>();
    int64_t num_elements = cpu_tensor.numel();

    // Copy data to vector
    return std::vector<float>(data_ptr, data_ptr + num_elements);
}
#endif

// ============================================================================
// ONNXModel Implementation
// ============================================================================

ONNXModel::ONNXModel()
#ifdef USE_ONNX
    : memory_info_(Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault))
#endif
{
#ifdef USE_ONNX
    // Initialize ONNX Runtime environment
    env_ = std::make_unique<Ort::Env>(ORT_LOGGING_LEVEL_WARNING, "ONNXModel");
#endif
}

ONNXModel::~ONNXModel()
{
#ifdef USE_ONNX
    session_.reset();
    env_.reset();
#endif
}

bool ONNXModel::load(const std::string& model_path)
{
    try
    {
#ifdef USE_ONNX
        // Configure session options
        Ort::SessionOptions session_options;
        session_options.SetIntraOpNumThreads(1);
        session_options.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_EXTENDED);

        // Create inference session
        session_ = std::make_unique<Ort::Session>(*env_, model_path.c_str(), session_options);

        // Setup input/output information
        setup_input_output_info();

        model_path_ = model_path;
        loaded_ = true;
        std::cout << LOGGER::INFO << "Successfully loaded ONNX model: " << model_path << std::endl;
        return true;
#else
        std::cout << LOGGER::WARNING << "ONNX support not compiled. Please define USE_ONNX." << std::endl;
        loaded_ = false;
        return false;
#endif
    }
    catch (const std::exception& e)
    {
        std::cout << LOGGER::ERROR << "Failed to load ONNX model: " << e.what() << std::endl;
        loaded_ = false;
        return false;
    }
}

std::vector<float> ONNXModel::forward(const std::vector<std::vector<float>>& inputs)
{
    if (!loaded_)
    {
        throw std::runtime_error("Model not loaded");
    }

#ifdef USE_ONNX
    try
    {
        // Create memory info
        Ort::MemoryInfo memory_info = Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault);

        // Get input (use first input only)
        const auto& input = inputs[0];
        auto input_shape = session_->GetInputTypeInfo(0).GetTensorTypeAndShapeInfo().GetShape();

        // Create input tensor
        auto input_tensor = Ort::Value::CreateTensor<float>(
            memory_info,
            const_cast<float*>(input.data()),
            input.size(),
            input_shape.data(),
            input_shape.size()
        );

        // Prepare input/output names
        const char* input_names[] = {input_node_names_[0].c_str()};
        const char* output_names[] = {output_node_names_[0].c_str()};

        // Execute inference
        auto outputs = session_->Run(
            Ort::RunOptions{nullptr},
            input_names,
            &input_tensor,
            1,
            output_names,
            1
        );

        // Extract output data
        return extract_output_data(outputs);
    }
    catch (const std::exception& e)
    {
        std::cout << LOGGER::ERROR << "ONNX inference error: " << e.what() << std::endl;
        throw;
    }
#else
    throw std::runtime_error("ONNX support not compiled");
#endif
}

#ifdef USE_ONNX
void ONNXModel::setup_input_output_info()
{
    // Get input node information
    size_t num_input_nodes = session_->GetInputCount();
    input_node_names_.reserve(num_input_nodes);
    input_shapes_.reserve(num_input_nodes);

    for (size_t i = 0; i < num_input_nodes; ++i)
    {
        // Get input name
        auto input_name = session_->GetInputNameAllocated(i, Ort::AllocatorWithDefaultOptions());
        input_node_names_.push_back(std::string(input_name.get()));

        // Get input shape
        Ort::TypeInfo input_type_info = session_->GetInputTypeInfo(i);
        auto input_tensor_info = input_type_info.GetTensorTypeAndShapeInfo();
        auto input_dims = input_tensor_info.GetShape();

        std::vector<int64_t> shape;
        for (auto dim : input_dims)
        {
            // Handle dynamic dimensions
            if (dim == -1)
            {
                shape.push_back(1);
            }
            else
            {
                shape.push_back(dim);
            }
        }
        input_shapes_.push_back(shape);
    }

    // Get output node information
    size_t num_output_nodes = session_->GetOutputCount();
    output_node_names_.reserve(num_output_nodes);
    output_shapes_.reserve(num_output_nodes);

    for (size_t i = 0; i < num_output_nodes; ++i)
    {
        // Get output name
        auto output_name = session_->GetOutputNameAllocated(i, Ort::AllocatorWithDefaultOptions());
        output_node_names_.push_back(std::string(output_name.get()));

        // Get output shape
        Ort::TypeInfo output_type_info = session_->GetOutputTypeInfo(i);
        auto output_tensor_info = output_type_info.GetTensorTypeAndShapeInfo();
        auto output_dims = output_tensor_info.GetShape();

        std::vector<int64_t> shape;
        for (auto dim : output_dims)
        {
            // Handle dynamic dimensions
            if (dim == -1)
            {
                shape.push_back(1);
            }
            else
            {
                shape.push_back(dim);
            }
        }
        output_shapes_.push_back(shape);
    }
}

std::vector<float> ONNXModel::extract_output_data(const std::vector<Ort::Value>& outputs)
{
    if (outputs.empty())
    {
        throw std::runtime_error("No outputs from ONNX model");
    }

    // Get first output tensor
    auto& output = outputs[0];
    float* output_data = const_cast<float*>(output.GetTensorData<float>());

    // Calculate total number of output elements
    auto output_shape = output.GetTensorTypeAndShapeInfo().GetShape();

    int64_t num_elements = 1;
    for (auto dim : output_shape)
    {
        if (dim > 0)
        {
            num_elements *= dim;
        }
    }

    // Copy output data to vector
    std::vector<float> result(output_data, output_data + num_elements);

    return result;
}
#endif

// ============================================================================
// ModelFactory Implementation
// ============================================================================

std::unique_ptr<Model> ModelFactory::create_model(ModelType type)
{
    switch (type)
    {
        case ModelType::TORCH:
            return std::make_unique<TorchModel>();
        case ModelType::ONNX:
            return std::make_unique<ONNXModel>();
        default:
            return nullptr;
    }
}

ModelFactory::ModelType ModelFactory::detect_model_type(const std::string& model_path)
{
    // Extract file extension from path
    std::filesystem::path path(model_path);
    std::string extension = path.extension().string();

    // Convert to lowercase for case-insensitive comparison
    std::transform(extension.begin(), extension.end(), extension.begin(), ::tolower);

    // Determine model type based on extension
    if (extension == ".pt" || extension == ".pth")
    {
        return ModelType::TORCH;
    }
    else if (extension == ".onnx")
    {
        return ModelType::ONNX;
    }
    else
    {
        throw std::runtime_error("Unknown model file extension: " + extension + ". Supported: .pt, .pth, .onnx");
    }
}

std::unique_ptr<Model> ModelFactory::load_model(const std::string& model_path, ModelType type)
{
    // If type is AUTO, automatically detect model type
    if (type == ModelType::AUTO)
    {
        type = detect_model_type(model_path);
    }

    // Create and load model
    auto model = create_model(type);
    if (model && model->load(model_path))
    {
        return model;
    }
    return nullptr;
}

} // namespace InferenceRuntime
