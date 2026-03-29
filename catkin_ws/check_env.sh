#!/bin/bash

WS_PATH="${WS_PATH:-$HOME/catkin_ws}"
AGENT_ENV="$WS_PATH/agent_env.sh"

if [ -f "$AGENT_ENV" ]; then
    source "$AGENT_ENV" >/dev/null 2>&1 || true
else
    source /opt/ros/noetic/setup.bash >/dev/null 2>&1 || true
    source "$WS_PATH/devel/setup.bash" >/dev/null 2>&1 || true
fi

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # 无颜色

echo -e "${YELLOW}=== 正在检查魔改导航仿真环境配置 ===${NC}\n"

# 1. 检查 ROS Noetic
if [ -d "/opt/ros/noetic" ]; then
    echo -e "[ OK ] ROS Noetic 已安装"
else
    echo -e "[ FAIL ] 未发现 ROS Noetic，请检查第二步"
fi

# 2. 检查 MAVROS 与 GeographicLib
if rosnode list 2>/dev/null | grep -q "/mavros" || [ -d "/opt/ros/noetic/share/mavros" ]; then
    echo -e "[ OK ] MAVROS 已安装"
    if [ -d "/usr/share/GeographicLib/geoids" ]; then
        echo -e "[ OK ] GeographicLib 数据集已存在"
    else
        echo -e "[ FAIL ] GeographicLib 数据缺失，无人机将无法起飞"
    fi
else
    echo -e "[ FAIL ] MAVROS 未安装"
fi

if [ -d "$PX4_PATH/Tools/simulation/gazebo-classic/sitl_gazebo-classic" ]; then
    SITL_GAZEBO_PATH="$PX4_PATH/Tools/simulation/gazebo-classic/sitl_gazebo-classic"
else
    SITL_GAZEBO_PATH="$PX4_PATH/Tools/sitl_gazebo"
fi

if [ -d "$PX4_PATH" ]; then
    echo -e "[ OK ] PX4 目录存在: $PX4_PATH"
    if [ -d "$PX4_PATH/build/px4_sitl_default" ]; then
        echo -e "[ OK ] PX4 SITL 已编译"
    else
        echo -e "[ WARN ] PX4 尚未编译，请执行 make px4_sitl gazebo-classic_iris_depth_camera"
    fi
else
    echo -e "[ FAIL ] PX4 路径错误，请检查第四步"
fi

# 4. 检查 Ego-Planner
EGO_PATH="$WS_PATH/src/ego-planner"
if [ -d "$EGO_PATH" ]; then
    echo -e "[ OK ] Ego-Planner 源码存在"
    if [ -f "$WS_PATH/devel/setup.bash" ]; then
        echo -e "[ OK ] 工作空间 catkin_ws 已编译"
    else
        echo -e "[ FAIL ] 工作空间尚未编译，请在 catkin_ws 运行 catkin_make"
    fi
else
    echo -e "[ FAIL ] 未发现 Ego-Planner 源码"
fi

# 5. 检查环境变量冲突 (核心检查)
echo -e "\n${YELLOW}--- 环境变量检查 ---${NC}"
if [[ "$ROS_PACKAGE_PATH" == *"$PX4_PATH"* ]]; then
    echo -e "[ OK ] ROS_PACKAGE_PATH 已包含 PX4"
else
    echo -e "[ FAIL ] ROS 找不到 PX4，请检查 .bashrc 中的 export 逻辑"
fi

if [[ "$GAZEBO_MODEL_PATH" == *"$PX4_PATH"* ]]; then
    echo -e "[ OK ] Gazebo 已关联 PX4 模型库"
else
    echo -e "[ FAIL ] Gazebo 找不到 PX4 模型"
fi

# 6. 检查魔改文件位置
echo -e "\n${YELLOW}--- 魔改文件检查 ---${NC}"
FILES=(
    "$SITL_GAZEBO_PATH/models/iris_depth_camera/iris_depth_camera.sdf"
    "$WS_PATH/px4_bridge.py"
    "$WS_PATH/fix_cloud.py"
    "$WS_PATH/src/ego-planner/src/planner/plan_manage/launch/advanced_param_px4.xml"
)

for file in "${FILES[@]}"; do
    if [ -f "$file" ]; then
        echo -e "[ OK ] 发现文件: $(basename $file)"
    else
        echo -e "[ FAIL ] 缺失文件: $file"
    fi
done

echo -e "\n${YELLOW}=== 检查完成 ===${NC}"
