#!/bin/bash

set -euo pipefail

WS_PATH="${WS_PATH:-$HOME/catkin_ws}"
AGENT_ENV="$WS_PATH/agent_env.sh"
SUITE_NAME="default"
LEVEL_NAME="l1"
RUN_LABEL="baseline"
PX4_GUI="${PX4_GUI:-false}"
KEEP_STACK=0
START_STACK=1
RESET_PARAMS=0
PARAM_ARGS=()

if [ ! -f "$AGENT_ENV" ]; then
  echo "[ERROR] Missing environment bootstrap: $AGENT_ENV"
  exit 1
fi

while [ $# -gt 0 ]; do
  case "$1" in
    --suite)
      SUITE_NAME="$2"
      shift
      ;;
    --label)
      RUN_LABEL="$2"
      shift
      ;;
    --level)
      LEVEL_NAME="$2"
      shift
      ;;
    --param)
      PARAM_ARGS+=("--param" "$2")
      shift
      ;;
    --param-file)
      PARAM_ARGS+=("--param-file" "$2")
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

RESULT_ROOT="$WS_PATH/records/tracking_eval"
mkdir -p "$RESULT_ROOT"
RUN_STAMP="$(date +%Y-%m-%d_%H-%M-%S)"
RUN_DIR="$RESULT_ROOT/${RUN_STAMP}_${RUN_LABEL}"

mkdir -p "$RUN_DIR"

if [ "$START_STACK" -eq 1 ]; then
  START_ARGS=()
  if [ "$RESET_PARAMS" -eq 1 ]; then
    START_ARGS+=("--reset-params")
  fi
  PX4_GUI="$PX4_GUI" "$WS_PATH/start_tracking_stack.sh" "${START_ARGS[@]}"
fi

python3 "$WS_PATH/tracking_test_runner.py" --suite "$SUITE_NAME" --level "$LEVEL_NAME" --output-dir "$RUN_DIR" "${PARAM_ARGS[@]}"
python3 "$WS_PATH/tracking_analysis.py" --run-dir "$RUN_DIR"

if [ "$KEEP_STACK" -ne 1 ]; then
  "$WS_PATH/stop_sim.sh"
fi

echo "$RUN_DIR"
