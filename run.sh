#!/bin/bash

# 載入共通工具
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
if [ -f "${SCRIPT_DIR}/scripts/common.sh" ]; then
    source "${SCRIPT_DIR}/scripts/common.sh"
else
    # 如果沒找到 common.sh，定義基本顏色
    COLOR_INFO='\033[0;34m'
    COLOR_SUCCESS='\033[0;32m'
    COLOR_WARNING='\033[1;33m'
    COLOR_ERROR='\033[0;31m'
    COLOR_RESET='\033[0m'
    print_info() { echo -e "${COLOR_INFO}[INFO]${COLOR_RESET} $1"; }
    print_success() { echo -e "${COLOR_SUCCESS}[SUCCESS]${COLOR_RESET} $1"; }
    print_warning() { echo -e "${COLOR_WARNING}[WARNING]${COLOR_RESET} $1"; }
    print_error() { echo -e "${COLOR_ERROR}[ERROR]${COLOR_RESET} $1"; }
    print_header() { echo -e "${COLOR_INFO}=== $1 ===${COLOR_RESET}"; }
fi

# ========================
# ROS 版本偵測
# ========================
if [ -z "$ROS_DISTRO" ]; then
    print_error "未偵測到 ROS 環境，請先 source 您的 setup.bash"
    exit 1
fi

IS_ROS2=false
if [[ "$ROS_DISTRO" != "noetic" ]]; then
    IS_ROS2=true
    ROS_CMD="ros2"
    DEFAULT_LAUNCH="gazebo.launch.py"
else
    IS_ROS2=false
    ROS_CMD="ros"
    DEFAULT_LAUNCH="gazebo_idog.launch"
fi

# ========================
# 配置預設值
# ========================
PKG_NAME="rl_ITRI"
LAUNCH_FILE=$DEFAULT_LAUNCH
CONFIG="ITRI_lab"
SIM_NODE="rl_sim"
RNAME="idog"
WNAME="stairs"
GUI_ENABLED="false"

# ========================
# 解析命令列參數 (Flags)
# ========================
while [[ "$#" -gt 0 ]]; do
    case $1 in
        -gui|--gui) 
            GUI_ENABLED="true"
            shift 
            ;;
        -p|--pkg) 
            PKG_NAME="$2"
            shift 2 
            ;;
        -l|--launch) 
            LAUNCH_FILE="$2"
            shift 2
            ;;
        -c|--config) 
            CONFIG="$2"
            shift 2
            ;;
        -n|--node) 
            SIM_NODE="$2"
            shift 2
            ;;
        -r|--rname) 
            RNAME="$2"
            shift 2
            ;;
        -w|--world) 
            WNAME="$2"
            shift 2
            ;;
        -h|--help)
            echo "用法: $0 [選項]"
            echo "選項:"
            echo "  -gui, --gui      啟用 GUI"
            echo "  -p, --pkg        設定 Package Name (預設: rl_ITRI)"
            echo "  -l, --launch     設定 Launch file (預設: $DEFAULT_LAUNCH)"
            echo "  -c, --config     設定 Configuration (預設: ITRI_lab)"
            echo "  -n, --node       設定 Simulation Node (預設: rl_sim)"
            echo "  -r, --rname      設定 Robot Name (預設: idog)"
            echo "  -w, --world      設定 World Name (預設: stairs)"
            echo "  -h, --help       顯示此幫助訊息"
            exit 0
            ;;
        *) 
            print_error "未知的參數: $1"
            echo "請使用 $0 --help 查看可用參數"
            exit 1 
            ;;
    esac
done

# ========================
# 清理函數
# ========================
cleanup() {
    echo ""
    print_info "正在關閉所有程序..."
    
    if [ ! -z "$GAZEBO_PID" ]; then
        kill -SIGINT $GAZEBO_PID 2>/dev/null
    fi

    pkill -9 -f "gzserver"
    pkill -9 -f "gzclient"
    pkill -9 -f "robot_state_publisher"
    pkill -9 -f "joy_node"
    pkill -9 -f "parameter_blackboard"
    pkill -9 -f "$SIM_NODE"
    
    sleep 1
    print_success "系統已安全關閉。"
    exit
}

trap cleanup SIGINT

print_info "目前環境: ROS $ROS_DISTRO"

# ========================
# 執行
# ========================

print_header "啟動 Gazebo"
print_info "Package: $PKG_NAME, Launch: $LAUNCH_FILE, World: $WNAME, Rname: $RNAME"

if [ "$IS_ROS2" = true ]; then
    ros2 launch "$PKG_NAME" "$LAUNCH_FILE" rname:="$RNAME" wname:="$WNAME" cfg:="$CONFIG" gui:="$GUI_ENABLED" > /dev/null 2>&1 &
else
    roslaunch "$PKG_NAME" "$LAUNCH_FILE" rname:="$RNAME" wname:="$WNAME" cfg:="$CONFIG" gui:="$GUI_ENABLED" > /dev/null 2>&1 &
fi

GAZEBO_PID=$!
print_info "等待初始化..."
sleep 10

print_header "啟動 RL 控制器"
print_warning "鍵盤操作提示 (請切換英文輸入):"
echo "  0/9: 站立/坐下 | 1: 啟動AI | w/a/s/d: 前後左右 | q/e: 旋轉 | space: reset command"

if [ "$IS_ROS2" = true ]; then
    ros2 run "$PKG_NAME" "$SIM_NODE"
else
    rosrun "$PKG_NAME" "$SIM_NODE"
fi

cleanup
