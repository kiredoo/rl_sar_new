# ==========================================
# == Stage 1: Base (共用環境與相依套件) ==
# ==========================================
FROM osrf/ros:humble-desktop-full AS base

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    wget curl unzip python3-pip patchelf \
    libyaml-cpp-dev libyaml-cpp0.7 libeigen3-dev libboost-all-dev \
    libspdlog-dev libfmt-dev libtbb-dev liblcm-dev \
    libglfw3-dev libgl1-mesa-dev libglew-dev libosmesa6-dev xorg-dev \
    ros-humble-control-toolbox \
    ros-humble-realtime-tools \
    ros-humble-xacro \
    ros-humble-hardware-interface \
    ros-humble-controller-interface \
    ros-humble-pluginlib \
    ros-humble-angles \
    ros-humble-joint-state-broadcaster \
    ros-humble-ros2-control \
    ros-humble-ros2-controllers \
    ros-humble-teleop-twist-keyboard \
    ros-humble-robot-state-publisher \
    ros-humble-joint-state-publisher-gui \
    ros-humble-gazebo-ros2-control \
    ros-humble-gazebo-ros-pkgs \
    ros-humble-effort-controllers \
    ros-humble-joint-trajectory-controller \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# ==========================================
# == Stage 2: Dev (開發環境) ==
# ==========================================
FROM base AS dev

RUN apt-get update && apt-get install -y \
    git gdb bash-completion \
    && rm -rf /var/lib/apt/lists/*

RUN echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc && \
    echo "if [ -f /workspace/install/setup.bash ]; then source /workspace/install/setup.bash; fi" >> ~/.bashrc

CMD ["bash"]

# ==========================================
# == Stage 3: Builder (編譯環境) ==
# ==========================================
FROM dev AS builder

COPY . .

RUN /bin/bash -c "source /opt/ros/humble/setup.bash && \
    colcon build --merge-install --parallel-workers 2 --cmake-args -DCMAKE_BUILD_TYPE=Release"

# ==========================================
# == Stage 4: Prod (正式環境) ==
# ==========================================
FROM base AS prod

COPY --from=builder /workspace/install ./install
COPY --from=builder /workspace/library ./library
COPY policy/ ./policy/
COPY run.sh ./run.sh

COPY src/rl_ITRI/launch ./src/rl_ITRI/launch
COPY src/rl_ITRI/worlds ./src/rl_ITRI/worlds
COPY src/rl_ITRI_zoo ./src/rl_ITRI_zoo
COPY src/robot_joint_controller ./src/robot_joint_controller

RUN find . -type d -name ".git" -prune -exec rm -rf {} +

ENV LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/workspace/install/lib:/workspace/library/inference_runtime:/workspace/library/inference_runtime/lib
ENV PYTHONPATH=$PYTHONPATH:/workspace/install/lib/python3.10/site-packages

RUN echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc && \
    echo "source /workspace/install/setup.bash" >> ~/.bashrc

ENTRYPOINT ["/bin/bash", "-c", "source /opt/ros/humble/setup.bash && source /workspace/install/setup.bash && exec \"$@\"", "--"]
CMD ["bash"]