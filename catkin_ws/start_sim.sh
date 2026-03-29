#!/bin/bash

set -euo pipefail

if [ -n "${PX4_PATH:-}" ]; then
  PX4_PATH="$PX4_PATH"
elif [ -d "$HOME/PX4-Autopilot-v1.16.0" ]; then
  PX4_PATH="$HOME/PX4-Autopilot-v1.16.0"
else
  PX4_PATH="$HOME/PX4-Autopilot"
fi

WS_PATH="${WS_PATH:-$HOME/catkin_ws}"
AGENT_ENV="$WS_PATH/agent_env.sh"
WINDOW_HELPER="$WS_PATH/guest_gnome_windowctl.py"
OBSTACLE_SEED="${OBSTACLE_SEED:-250}"
CLOUD_POINT_STRIDE="${CLOUD_POINT_STRIDE:-4}"
CLOUD_MAX_PUBLISH_HZ="${CLOUD_MAX_PUBLISH_HZ:-0}"
CLOUD_TARGET_FRAME="${CLOUD_TARGET_FRAME:-map}"
CLOUD_TF_TIMEOUT_S="${CLOUD_TF_TIMEOUT_S:-0.15}"
BRIDGE_ENABLE_SMOOTHING="${BRIDGE_ENABLE_SMOOTHING:-true}"
BRIDGE_SMOOTH_ALPHA="${BRIDGE_SMOOTH_ALPHA:-0.6}"
BRIDGE_ZERO_ACCEL_WHEN_SHAPING="${BRIDGE_ZERO_ACCEL_WHEN_SHAPING:-false}"
PLANNER_MAX_VEL="${PLANNER_MAX_VEL:-1.2}"
PLANNER_MAX_ACC="${PLANNER_MAX_ACC:-1.5}"
PLANNER_HORIZON="${PLANNER_HORIZON:-8}"
PLANNER_LAMBDA_COLLISION="${PLANNER_LAMBDA_COLLISION:-10.0}"
PLANNER_DIST0="${PLANNER_DIST0:-0.4}"

if [ -d "$PX4_PATH/Tools/simulation/gazebo-classic/sitl_gazebo-classic" ]; then
  SDF_PATH="$PX4_PATH/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris_depth_camera/iris_depth_camera.sdf"
else
  SDF_PATH="$PX4_PATH/Tools/sitl_gazebo/models/iris_depth_camera/iris_depth_camera.sdf"
fi
TERM_PID_DIR="$HOME/.cache/px4_sim_terminals"
AUTO_STATE_DIR="$HOME/.cache/px4_auto"
TARGET_TAKEOFF_Z="2.5"

AUTO_READY_FILE="$AUTO_STATE_DIR/hover_ready.flag"
AUTO_RELEASE_FILE="$AUTO_STATE_DIR/release_handover.flag"
AUTO_PID_FILE="$AUTO_STATE_DIR/auto_takeoff.pid"
WORKSPACE_LOG_DIR="$WS_PATH/workspace_logs"
AUTO_LOG_FILE="$WORKSPACE_LOG_DIR/auto_takeoff_latest.log"

mkdir -p "$TERM_PID_DIR" "$AUTO_STATE_DIR" "$WORKSPACE_LOG_DIR"
rm -f "$TERM_PID_DIR"/*.pid 2>/dev/null
rm -f "$AUTO_READY_FILE" "$AUTO_RELEASE_FILE" "$AUTO_PID_FILE"

if [ ! -f "$AGENT_ENV" ]; then
  echo "[ERROR] Missing environment bootstrap: $AGENT_ENV"
  exit 1
fi

source "$AGENT_ENV"

wait_for_topic() {
  local topic="$1"
  local timeout_s="${2:-60}"
  local start_ts
  start_ts=$(date +%s)
  while true; do
    if rostopic list 2>/dev/null | grep -qx "$topic"; then
      return 0
    fi
    if [ $(( $(date +%s) - start_ts )) -ge "$timeout_s" ]; then
      echo "[WARN] Timeout waiting for topic: $topic"
      return 1
    fi
    sleep 1
  done
}

wait_for_message() {
  local topic="$1"
  local msg_type="$2"
  local timeout_s="${3:-60}"
  python3 - "$topic" "$msg_type" "$timeout_s" <<'PY'
import importlib
import sys

import rospy

topic, msg_type, timeout_s = sys.argv[1], sys.argv[2], float(sys.argv[3])
pkg, name = msg_type.split("/")
msg_module = importlib.import_module(f"{pkg}.msg")
msg_cls = getattr(msg_module, name)

rospy.init_node("codex_wait_for_message", anonymous=True, disable_signals=True)
rospy.wait_for_message(topic, msg_cls, timeout=timeout_s)
PY
}

wait_for_connected_state() {
  local timeout_s="${1:-60}"
  python3 - "$timeout_s" <<'PY'
import sys
import time

import rospy
from mavros_msgs.msg import State

timeout_s = float(sys.argv[1])
latest = None

def cb(msg):
    global latest
    latest = msg

rospy.init_node("codex_wait_for_connected_state", anonymous=True, disable_signals=True)
rospy.Subscriber("/mavros/state", State, cb, queue_size=1)

deadline = time.time() + timeout_s
rate = rospy.Rate(20)
while time.time() < deadline and not rospy.is_shutdown():
    if latest is not None and latest.connected:
        sys.exit(0)
    rate.sleep()

sys.exit(1)
PY
}

wait_for_file() {
  local file="$1"
  local timeout_s="${2:-60}"
  local start_ts
  start_ts=$(date +%s)
  while true; do
    [ -f "$file" ] && return 0
    if [ $(( $(date +%s) - start_ts )) -ge "$timeout_s" ]; then
      echo "[WARN] Timeout waiting for file: $file"
      return 1
    fi
    sleep 1
  done
}

configure_runtime_params() {
  rosparam set /obstacle_generator/seed "$OBSTACLE_SEED"
  rosparam set /cloud_fixer_node/point_stride "$CLOUD_POINT_STRIDE"
  rosparam set /cloud_fixer_node/max_publish_hz "$CLOUD_MAX_PUBLISH_HZ"
  rosparam set /cloud_fixer_node/target_frame "$CLOUD_TARGET_FRAME"
  rosparam set /cloud_fixer_node/tf_timeout_s "$CLOUD_TF_TIMEOUT_S"
  rosparam set /px4_bridge_machine/enable_smoothing "$BRIDGE_ENABLE_SMOOTHING"
  rosparam set /px4_bridge_machine/smooth_alpha "$BRIDGE_SMOOTH_ALPHA"
  rosparam set /px4_bridge_machine/zero_accel_when_shaping "$BRIDGE_ZERO_ACCEL_WHEN_SHAPING"

  echo "[INFO] obstacle_seed=$OBSTACLE_SEED cloud_stride=$CLOUD_POINT_STRIDE cloud_max_hz=$CLOUD_MAX_PUBLISH_HZ bridge_smooth=$BRIDGE_ENABLE_SMOOTHING bridge_alpha=$BRIDGE_SMOOTH_ALPHA bridge_zero_accel=$BRIDGE_ZERO_ACCEL_WHEN_SHAPING planner_max_vel=$PLANNER_MAX_VEL planner_max_acc=$PLANNER_MAX_ACC planner_horizon=$PLANNER_HORIZON planner_lambda_collision=$PLANNER_LAMBDA_COLLISION planner_dist0=$PLANNER_DIST0"
}

arrange_presentation_windows() {
  if [ ! -f "$WINDOW_HELPER" ]; then
    echo "[WARN] Missing window helper: $WINDOW_HELPER"
    return 0
  fi

  (
    export DISPLAY="${DISPLAY:-:0}"
    export XAUTHORITY="${XAUTHORITY:-$HOME/.Xauthority}"
    export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=/run/user/$(id -u)/bus}"

    python3 "$WINDOW_HELPER" wait "Gazebo" --timeout 180 >/dev/null 2>&1 || exit 0
    python3 "$WINDOW_HELPER" wait "rviz" --timeout 180 >/dev/null 2>&1 || exit 0

    # RViz may show an informational popup that blocks the final layout.
    sleep 2
    python3 "$WINDOW_HELPER" close "ROS 1 End-of-Life" >/dev/null 2>&1 || true
    sleep 1

    python3 "$WINDOW_HELPER" tile "Gazebo" --half left >/dev/null 2>&1 || true
    python3 "$WINDOW_HELPER" tile "rviz" --half right >/dev/null 2>&1 || true
  ) &
}

launch_auto_takeoff_hold() {
  echo "阶段 2/4: 自动起飞并保持到 ${TARGET_TAKEOFF_Z}m"
  mkdir -p "$AUTO_STATE_DIR"
  cat <<PY | nohup python3 - > "$AUTO_LOG_FILE" 2>&1 &
import os
import rospy
from geometry_msgs.msg import PoseStamped
from mavros_msgs.msg import State
from mavros_msgs.srv import CommandBool, SetMode

TARGET_Z = float(${TARGET_TAKEOFF_Z})
READY_FILE = os.path.expanduser('${AUTO_READY_FILE}')
RELEASE_FILE = os.path.expanduser('${AUTO_RELEASE_FILE}')
os.makedirs(os.path.dirname(READY_FILE), exist_ok=True)

state = State()
pose = None

def state_cb(msg):
    global state
    state = msg

def pose_cb(msg):
    global pose
    pose = msg

rospy.init_node('codex_auto_takeoff_hold', anonymous=True)
rospy.Subscriber('/mavros/state', State, state_cb)
rospy.Subscriber('/mavros/local_position/pose', PoseStamped, pose_cb)
pub = rospy.Publisher('/mavros/setpoint_position/local', PoseStamped, queue_size=10)
rospy.wait_for_service('/mavros/cmd/arming', timeout=30)
rospy.wait_for_service('/mavros/set_mode', timeout=30)
arm = rospy.ServiceProxy('/mavros/cmd/arming', CommandBool)
set_mode = rospy.ServiceProxy('/mavros/set_mode', SetMode)
rate = rospy.Rate(20)

target = PoseStamped()
target.header.frame_id = 'map'
target.pose.orientation.w = 1.0
target.pose.position.x = 0.0
target.pose.position.y = 0.0
target.pose.position.z = TARGET_Z

for _ in range(40):
    target.header.stamp = rospy.Time.now()
    pub.publish(target)
    rate.sleep()

stable = 0
release_seen = False
for i in range(3600):
    target.header.stamp = rospy.Time.now()
    pub.publish(target)

    if i % 20 == 0:
        try:
            if not state.armed:
                print('arming', arm(True), flush=True)
            if state.mode != 'OFFBOARD':
                print('set_mode', set_mode(0, 'OFFBOARD'), flush=True)
        except Exception as exc:
            print('service_error', exc, flush=True)

    if pose is not None:
        z = pose.pose.position.z
        if z >= TARGET_Z - 0.15:
            stable += 1
            if stable == 20 and not os.path.exists(READY_FILE):
                with open(READY_FILE, 'w') as f:
                    f.write('ready\n')
                print(f'hover_ready z={z}', flush=True)
        else:
            stable = 0
        if i % 20 == 0:
            print(f'mode={state.mode} armed={state.armed} z={z}', flush=True)

    if os.path.exists(RELEASE_FILE):
        if not release_seen:
            print('release_seen', flush=True)
            release_seen = True
        elif i % 40 == 0:
            print('handover_exit', flush=True)
            break

    rate.sleep()
PY
  echo $! > "$AUTO_PID_FILE"
}

echo "正在启动魔改自主导航仿真系统..."
echo "阶段 1/4: 启动 PX4 + Gazebo + MAVROS"

gnome-terminal --tab --title="PX4_SITL" -- bash -ic "
echo \$\$ > '$TERM_PID_DIR/px4_sitl.pid';
export PX4_PATH='$PX4_PATH';
source '$AGENT_ENV';
roslaunch px4 mavros_posix_sitl.launch vehicle:=iris_depth_camera sdf:=$SDF_PATH;
exit"

wait_for_topic "/mavros/state" 90 || exit 1
wait_for_connected_state 90 || exit 1
wait_for_message "/mavros/local_position/pose" "geometry_msgs/PoseStamped" 90 || exit 1
launch_auto_takeoff_hold
wait_for_file "$AUTO_READY_FILE" 90 || exit 1

echo "阶段 3/4: 高度稳定，启动障碍物/桥接/点云/规划器"
configure_runtime_params

gnome-terminal --tab --title="Obstacles" -- bash -ic "
echo \$\$ > '$TERM_PID_DIR/obstacles.pid';
export PX4_PATH='$PX4_PATH';
source '$AGENT_ENV';
python3 $WS_PATH/obstacle_manager.py;
rm -f '$TERM_PID_DIR/obstacles.pid';
echo '障碍物生成完毕，5秒后关闭此页...';
sleep 5;
exit"

gnome-terminal --tab --title="Bridge_Cloud" -- bash -ic "
echo \$\$ > '$TERM_PID_DIR/bridge_cloud.pid';
export PX4_PATH='$PX4_PATH';
source '$AGENT_ENV';
python3 $WS_PATH/px4_bridge.py &
python3 $WS_PATH/fix_cloud.py;
exit"

gnome-terminal --tab --title="Ego_Planner" -- bash -ic "
echo \$\$ > '$TERM_PID_DIR/ego_planner.pid';
export PX4_PATH='$PX4_PATH';
source '$AGENT_ENV';
sleep 2;
roslaunch ego_planner px4_single.launch \
  planner_max_vel:=$PLANNER_MAX_VEL \
  planner_max_acc:=$PLANNER_MAX_ACC \
  planner_horizon:=$PLANNER_HORIZON \
  planner_lambda_collision:=$PLANNER_LAMBDA_COLLISION \
  planner_dist0:=$PLANNER_DIST0;
exit"

arrange_presentation_windows

wait_for_topic "/cloud_corrected" 60 || exit 1
wait_for_topic "/planning/pos_cmd" 60 || exit 1

echo "阶段 4/4: 规划链路已就绪，启动任务管理器并交接控制"
gnome-terminal --tab --title="Mission_Manager" -- bash -ic "
echo \$\$ > '$TERM_PID_DIR/mission_manager.pid';
export PX4_PATH='$PX4_PATH';
source '$AGENT_ENV';
python3 $WS_PATH/mission_manager.py;
exit"

wait_for_topic "/waypoint_generator/waypoints" 30 || exit 1

mkdir -p "$AUTO_STATE_DIR"
touch "$AUTO_RELEASE_FILE"
echo "自动起飞保持器已释放，现由 bridge/planner 接管。"
