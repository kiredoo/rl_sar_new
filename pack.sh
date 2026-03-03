#!/bin/bash

# 載入共通工具
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
if [ -f "${SCRIPT_DIR}/scripts/common.sh" ]; then
    source "${SCRIPT_DIR}/scripts/common.sh"
else
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
BUILD_ARTIFACTS=("build") # 共通目錄

if [[ "$ROS_DISTRO" != "noetic" ]]; then
    IS_ROS2=true
    BUILD_ARTIFACTS+=("install")
    print_info "偵測到 ROS 2 ($ROS_DISTRO) 環境"
else
    IS_ROS2=false
    BUILD_ARTIFACTS+=("devel")
    print_info "偵測到 ROS 1 ($ROS_DISTRO) 環境"
fi

# ========================
# 配置預設值
# ========================
PROJECT_NAME="idog_rl_walking"
TEMP_DIR="legged_ws_binary"

while [[ "$#" -gt 0 ]]; do
    case $1 in
        -n|--name) 
            PROJECT_NAME="$2"
            shift 2
            ;;
        -t|--temp) 
            TEMP_DIR="$2"
            shift 2
            ;;
        -h|--help)
            echo "用法: $0 [選項]"
            echo "選項:"
            echo "  -n, --name     設定打包後的專案名稱 (預設: idog_rl_walking)"
            echo "  -t, --temp     設定暫存資料夾名稱 (預設: legged_ws_binary)"
            echo "  -h, --help     顯示此幫助訊息"
            exit 0
            ;;
        *) 
            print_error "未知的參數: $1"
            echo "請使用 $0 --help 查看可用參數"
            exit 1 
            ;;
    esac
done

ZIP_NAME="${PROJECT_NAME}.zip"

# ========================
# 執行打包
# ========================

print_header "開始打包流程"

print_info "正在清理舊的建置環境..."
printf "y\n" | ./build.sh -c > /dev/null 2>&1

print_info "正在重新編譯專案 (這可能需要一點時間)..."
./build.sh > /dev/null 2>&1
if [ $? -ne 0 ]; then
    print_error "編譯失敗，請檢查建置狀態。"
    exit 1
fi
print_success "編譯完成。"

print_info "正在準備打包檔案..."
rm -rf "$TEMP_DIR"
mkdir -p "$TEMP_DIR/src/rl_ITRI"
mkdir -p "$TEMP_DIR/src/rl_ITRI_zoo"
mkdir -p "$TEMP_DIR/src/robot_joint_controller"

for dir in "${BUILD_ARTIFACTS[@]}"; do
    if [ -d "$dir" ]; then
        cp -ra "$dir/" "$TEMP_DIR/"
    fi
done

[ -d "library" ] && cp -ra library/ "$TEMP_DIR/"
[ -d "policy" ] && cp -ra policy/ "$TEMP_DIR/"

if [ -d "src/rl_ITRI/launch" ]; then
    cp -ra src/rl_ITRI/launch "$TEMP_DIR/src/rl_ITRI/"
fi
if [ -d "src/rl_ITRI/worlds" ]; then
    cp -ra src/rl_ITRI/worlds "$TEMP_DIR/src/rl_ITRI/"
fi

[ -d "src/rl_ITRI_zoo" ] && cp -ra src/rl_ITRI_zoo "$TEMP_DIR/src/"
[ -d "src/robot_joint_controller" ] && cp -ra src/robot_joint_controller "$TEMP_DIR/src/"

cp -a run.sh "$TEMP_DIR/"

print_info "正在產生壓縮檔: $ZIP_NAME ..."
rm -f "$ZIP_NAME"
zip -q -r "$ZIP_NAME" "$TEMP_DIR"

rm -rf "$TEMP_DIR"

print_header "打包完成"
print_success "壓縮檔已儲存至: $ZIP_NAME"
