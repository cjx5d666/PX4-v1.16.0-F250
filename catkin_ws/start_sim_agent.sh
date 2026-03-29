#!/bin/bash

set -euo pipefail

WS_PATH="${WS_PATH:-$HOME/catkin_ws}"
AGENT_ENV="$WS_PATH/agent_env.sh"
RUN_LOG_DIR="$WS_PATH/run_logs"
PX4_GUI="${PX4_GUI:-false}"
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

if [ ! -f "$AGENT_ENV" ]; then
  echo "[ERROR] Missing environment bootstrap: $AGENT_ENV"
  exit 1
fi

source "$AGENT_ENV"

if [ -d "$PX4_PATH/Tools/simulation/gazebo-classic/sitl_gazebo-classic" ]; then
  SDF_PATH="$PX4_PATH/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris_depth_camera/iris_depth_camera.sdf"
else
  SDF_PATH="$PX4_PATH/Tools/sitl_gazebo/models/iris_depth_camera/iris_depth_camera.sdf"
fi

mkdir -p "$RUN_LOG_DIR"

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

arm_offboard() {
  python3 - <<'PY'
import rospy
from geometry_msgs.msg import PoseStamped
from mavros_msgs.msg import State
from mavros_msgs.srv import CommandBool, SetMode

state = State()

def state_cb(msg):
    global state
    state = msg

rospy.init_node('codex_agent_arm_offboard', anonymous=True)
rospy.Subscriber('/mavros/state', State, state_cb)
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
target.pose.position.z = 2.0

for _ in range(40):
    target.header.stamp = rospy.Time.now()
    pub.publish(target)
    rate.sleep()

stable = 0
for _ in range(600):
    target.header.stamp = rospy.Time.now()
    pub.publish(target)
    if not state.armed:
        arm(True)
    if state.mode != 'OFFBOARD':
        set_mode(0, 'OFFBOARD')

    if state.armed and state.mode == 'OFFBOARD':
        stable += 1
        if stable >= 20:
            break
    else:
        stable = 0

    rate.sleep()

print(f"connected={state.connected} armed={state.armed} mode={state.mode}", flush=True)
if not (state.connected and state.armed and state.mode == 'OFFBOARD'):
    raise SystemExit(1)
PY
}

case "${1:-}" in
  --only-arm|--arm-offboard)
    arm_offboard
    exit 0
    ;;
esac

"$WS_PATH/stop_sim.sh"

nohup roslaunch px4 mavros_posix_sitl.launch vehicle:=iris_depth_camera sdf:="$SDF_PATH" gui:="$PX4_GUI" interactive:=false >"$RUN_LOG_DIR/px4.log" 2>&1 &

wait_for_topic "/mavros/state" 90 || exit 1
wait_for_connected_state 90 || exit 1
wait_for_message "/mavros/local_position/pose" "geometry_msgs/PoseStamped" 90 || exit 1
wait_for_message "/mavros/local_position/odom" "nav_msgs/Odometry" 90 || exit 1

configure_runtime_params

nohup python3 "$WS_PATH/obstacle_manager.py" >"$RUN_LOG_DIR/obstacles.log" 2>&1 &
nohup python3 "$WS_PATH/px4_bridge.py" >"$RUN_LOG_DIR/bridge.log" 2>&1 &
nohup python3 "$WS_PATH/fix_cloud.py" >"$RUN_LOG_DIR/fix_cloud.log" 2>&1 &
nohup roslaunch ego_planner px4_single.launch \
  enable_rviz:=false \
  planner_max_vel:="$PLANNER_MAX_VEL" \
  planner_max_acc:="$PLANNER_MAX_ACC" \
  planner_horizon:="$PLANNER_HORIZON" \
  planner_lambda_collision:="$PLANNER_LAMBDA_COLLISION" \
  planner_dist0:="$PLANNER_DIST0" >"$RUN_LOG_DIR/ego.log" 2>&1 &

wait_for_topic "/cloud_corrected" 90 || exit 1
wait_for_topic "/planning/pos_cmd" 90 || exit 1

nohup python3 "$WS_PATH/mission_manager.py" >"$RUN_LOG_DIR/mission.log" 2>&1 &
wait_for_topic "/waypoint_generator/waypoints" 30 || exit 1

echo "start_sim_agent.sh completed startup for PX4_PATH=$PX4_PATH"
