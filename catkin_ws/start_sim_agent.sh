#!/bin/bash

set -euo pipefail

WS_PATH="${WS_PATH:-$HOME/catkin_ws}"
AGENT_ENV="$WS_PATH/agent_env.sh"
RUN_LOG_DIR="$WS_PATH/run_logs"
PX4_GUI="${PX4_GUI:-false}"

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
    if source "$AGENT_ENV" >/dev/null 2>&1 && rostopic list 2>/dev/null | grep -qx "$topic"; then
      return 0
    fi
    if [ $(( $(date +%s) - start_ts )) -ge "$timeout_s" ]; then
      echo "[WARN] Timeout waiting for topic: $topic"
      return 1
    fi
    sleep 1
  done
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

nohup python3 "$WS_PATH/obstacle_manager.py" >"$RUN_LOG_DIR/obstacles.log" 2>&1 &
nohup python3 "$WS_PATH/px4_bridge.py" >"$RUN_LOG_DIR/bridge.log" 2>&1 &
nohup python3 "$WS_PATH/fix_cloud.py" >"$RUN_LOG_DIR/fix_cloud.log" 2>&1 &
nohup roslaunch ego_planner px4_single.launch enable_rviz:=false >"$RUN_LOG_DIR/ego.log" 2>&1 &

wait_for_topic "/cloud_corrected" 90 || true
wait_for_topic "/planning/pos_cmd" 90 || true
wait_for_topic "/waypoint_generator/waypoints" 90 || true

nohup python3 "$WS_PATH/mission_manager.py" >"$RUN_LOG_DIR/mission.log" 2>&1 &

echo "start_sim_agent.sh completed startup for PX4_PATH=$PX4_PATH"
