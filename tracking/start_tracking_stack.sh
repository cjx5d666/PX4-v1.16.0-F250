#!/bin/bash

set -euo pipefail

WS_PATH="${WS_PATH:-$HOME/catkin_ws}"
AGENT_ENV="$WS_PATH/agent_env.sh"
RUN_LOG_DIR="$WS_PATH/run_logs"
PX4_GUI="${PX4_GUI:-false}"
DO_STOP=1
RESET_PARAMS=0

if [ ! -f "$AGENT_ENV" ]; then
  echo "[ERROR] Missing environment bootstrap: $AGENT_ENV"
  exit 1
fi

while [ $# -gt 0 ]; do
  case "$1" in
    --gui)
      PX4_GUI=true
      ;;
    --headless)
      PX4_GUI=false
      ;;
    --no-stop)
      DO_STOP=0
      ;;
    --reset-params)
      RESET_PARAMS=1
      ;;
    *)
      echo "[ERROR] Unknown argument: $1"
      exit 1
      ;;
  esac
  shift
done

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

if [ "$DO_STOP" -eq 1 ]; then
  "$WS_PATH/stop_sim.sh"
fi

if [ "$RESET_PARAMS" -eq 1 ]; then
  mkdir -p "$HOME/.ros/eeprom"
  rm -f "$HOME/.ros/parameters.bson" "$HOME/.ros/parameters_backup.bson"
  rm -f "$HOME/.ros/eeprom"/parameters_*
  echo "start_tracking_stack.sh reset persisted SITL params"
fi

nohup roslaunch px4 mavros_posix_sitl.launch vehicle:=iris_depth_camera sdf:="$SDF_PATH" gui:="$PX4_GUI" interactive:=false >"$RUN_LOG_DIR/tracking_stack_px4.log" 2>&1 &

wait_for_topic "/mavros/state" 90 || exit 1
wait_for_topic "/mavros/local_position/pose" 90 || exit 1
wait_for_topic "/mavros/local_position/velocity_local" 90 || true

echo "start_tracking_stack.sh ready for PX4_PATH=$PX4_PATH gui=$PX4_GUI"
