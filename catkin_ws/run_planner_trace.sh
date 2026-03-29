#!/bin/bash

set -euo pipefail

WS_PATH="${WS_PATH:-$HOME/catkin_ws}"
AGENT_ENV="$WS_PATH/agent_env.sh"
TRACE_SCRIPT="$WS_PATH/planner_trace_runner.py"
RESULT_ROOT="$WS_PATH/records/planner_eval"
PX4_GUI="${PX4_GUI:-true}"
DURATION_S=25
RUN_LABEL="baseline"
KEEP_STACK=0
START_STACK=1
POST_ARM_WARMUP_S=8

PLANNER_MAX_VEL="${PLANNER_MAX_VEL:-1.2}"
PLANNER_MAX_ACC="${PLANNER_MAX_ACC:-1.5}"
PLANNER_HORIZON="${PLANNER_HORIZON:-8}"
PLANNER_LAMBDA_COLLISION="${PLANNER_LAMBDA_COLLISION:-10.0}"
PLANNER_DIST0="${PLANNER_DIST0:-0.4}"

wait_for_message() {
  local topic="$1"
  local msg_type="$2"
  local timeout_s="${3:-30}"
  python3 - "$topic" "$msg_type" "$timeout_s" <<'PY'
import importlib
import sys

import rospy

topic, msg_type, timeout_s = sys.argv[1], sys.argv[2], float(sys.argv[3])
pkg, name = msg_type.split("/")
msg_module = importlib.import_module(f"{pkg}.msg")
msg_cls = getattr(msg_module, name)

rospy.init_node("planner_trace_wait_for_message", anonymous=True, disable_signals=True)
rospy.wait_for_message(topic, msg_cls, timeout=timeout_s)
PY
}

cleanup() {
  if [ "$KEEP_STACK" -ne 1 ]; then
    "$WS_PATH/stop_sim.sh" >/dev/null 2>&1 || true
  fi
}

trap cleanup EXIT

if [ ! -f "$AGENT_ENV" ]; then
  echo "[ERROR] Missing environment bootstrap: $AGENT_ENV"
  exit 1
fi

if [ ! -f "$TRACE_SCRIPT" ]; then
  echo "[ERROR] Missing planner trace script: $TRACE_SCRIPT"
  exit 1
fi

while [ $# -gt 0 ]; do
  case "$1" in
    --duration)
      DURATION_S="$2"
      shift
      ;;
    --label)
      RUN_LABEL="$2"
      shift
      ;;
    --planner-max-vel)
      PLANNER_MAX_VEL="$2"
      shift
      ;;
    --planner-max-acc)
      PLANNER_MAX_ACC="$2"
      shift
      ;;
    --planner-horizon)
      PLANNER_HORIZON="$2"
      shift
      ;;
    --planner-lambda-collision)
      PLANNER_LAMBDA_COLLISION="$2"
      shift
      ;;
    --planner-dist0)
      PLANNER_DIST0="$2"
      shift
      ;;
    --gui)
      PX4_GUI=true
      ;;
    --headless)
      PX4_GUI=false
      ;;
    --keep-stack)
      KEEP_STACK=1
      ;;
    --no-start)
      START_STACK=0
      ;;
    --post-arm-warmup)
      POST_ARM_WARMUP_S="$2"
      shift
      ;;
    *)
      echo "[ERROR] Unknown argument: $1"
      exit 1
      ;;
  esac
  shift
done

source "$AGENT_ENV"

if [ "$START_STACK" -eq 0 ]; then
  if [ "$PLANNER_MAX_VEL" != "1.2" ] || [ "$PLANNER_MAX_ACC" != "1.5" ] || [ "$PLANNER_HORIZON" != "8" ] || [ "$PLANNER_LAMBDA_COLLISION" != "10.0" ] || [ "$PLANNER_DIST0" != "0.4" ]; then
    echo "[ERROR] Planner overrides only take effect when the stack is freshly started."
    exit 1
  fi
fi

if [ "$PX4_GUI" = "true" ]; then
  export DISPLAY=:0
  export XAUTHORITY="$HOME/.Xauthority"
  export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
fi

mkdir -p "$RESULT_ROOT"
RUN_STAMP="$(date +%Y-%m-%d_%H-%M-%S)"
RUN_DIR="$RESULT_ROOT/${RUN_STAMP}_${RUN_LABEL}"
mkdir -p "$RUN_DIR"

python3 - "$RUN_DIR/run_manifest.json" "$DURATION_S" "$RUN_LABEL" "$PX4_GUI" "$START_STACK" "$PLANNER_MAX_VEL" "$PLANNER_MAX_ACC" "$PLANNER_HORIZON" "$PLANNER_LAMBDA_COLLISION" "$PLANNER_DIST0" <<'PY'
import json
import sys

path, duration_s, label, px4_gui, start_stack, max_vel, max_acc, horizon, lambda_collision, dist0 = sys.argv[1:]
payload = {
    "duration_s": float(duration_s),
    "label": label,
    "px4_gui": px4_gui,
    "start_stack": int(start_stack),
    "planner": {
        "max_vel": float(max_vel),
        "max_acc": float(max_acc),
        "horizon": float(horizon),
        "lambda_collision": float(lambda_collision),
        "dist0": float(dist0),
    },
}
with open(path, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2, sort_keys=True)
PY

if [ "$START_STACK" -eq 1 ]; then
  PLANNER_MAX_VEL="$PLANNER_MAX_VEL" \
  PLANNER_MAX_ACC="$PLANNER_MAX_ACC" \
  PLANNER_HORIZON="$PLANNER_HORIZON" \
  PLANNER_LAMBDA_COLLISION="$PLANNER_LAMBDA_COLLISION" \
  PLANNER_DIST0="$PLANNER_DIST0" \
  PX4_GUI="$PX4_GUI" \
    "$WS_PATH/start_sim_agent.sh"

  ARM_OK=0
  for attempt in 1 2 3; do
    if "$WS_PATH/start_sim_agent.sh" --only-arm; then
      ARM_OK=1
      break
    fi
    sleep 5
  done
  if [ "$ARM_OK" -ne 1 ]; then
    echo "[ERROR] Failed to arm and enter OFFBOARD after 3 attempts."
    exit 1
  fi
  sleep "$POST_ARM_WARMUP_S"
  wait_for_message "/mavros/local_position/pose" "geometry_msgs/PoseStamped" 30
  wait_for_message "/planning/pos_cmd" "quadrotor_msgs/PositionCommand" 30
  wait_for_message "/cloud_corrected" "sensor_msgs/PointCloud2" 30
fi

python3 "$TRACE_SCRIPT" --output-dir "$RUN_DIR" --duration-s "$DURATION_S"

if [ "$KEEP_STACK" -eq 1 ]; then
  trap - EXIT
fi

echo "$RUN_DIR"
