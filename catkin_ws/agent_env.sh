#!/bin/bash

WS_PATH="${WS_PATH:-$HOME/catkin_ws}"

if [ -n "${PX4_PATH:-}" ]; then
  PX4_PATH="$PX4_PATH"
elif [ -d "$HOME/PX4-Autopilot-v1.16.0" ]; then
  PX4_PATH="$HOME/PX4-Autopilot-v1.16.0"
else
  PX4_PATH="$HOME/PX4-Autopilot"
fi

PX4_DIR="$PX4_PATH"
PX4_BUILD_DIR="${PX4_BUILD_DIR:-$PX4_PATH/build/px4_sitl_default}"
GAZEBO_CLASSIC_DIR="$PX4_PATH/Tools/simulation/gazebo-classic"
GAZEBO_CLASSIC_PKG_DIR="$GAZEBO_CLASSIC_DIR/sitl_gazebo-classic"
LEGACY_GAZEBO_PKG_DIR="$PX4_PATH/Tools/sitl_gazebo"
GAZEBO_SYSTEM_PLUGIN_DIR="/usr/lib/x86_64-linux-gnu/gazebo-11/plugins"
ROS_GAZEBO_PLUGIN_DIR="/opt/ros/noetic/lib"

append_unique_path() {
  local var_name="$1"
  local new_path="$2"
  local current_value="${!var_name:-}"

  case ":$current_value:" in
    *":$new_path:"*)
      return 0
      ;;
  esac

  if [ -n "$current_value" ]; then
    printf -v "$var_name" '%s:%s' "$current_value" "$new_path"
  else
    printf -v "$var_name" '%s' "$new_path"
  fi
}

dedupe_colon_var() {
  local var_name="$1"
  local current_value="${!var_name:-}"
  local deduped=""
  local entry
  local old_ifs="$IFS"

  IFS=':' read -r -a _entries <<< "$current_value"
  IFS="$old_ifs"

  for entry in "${_entries[@]}"; do
    [ -n "$entry" ] || continue
    case ":$deduped:" in
      *":$entry:"*) ;;
      *) deduped="${deduped:+$deduped:}$entry" ;;
    esac
  done

  printf -v "$var_name" '%s' "$deduped"
}

_restore_nounset=0
if [[ $- == *u* ]]; then
  set +u
  _restore_nounset=1
fi

source /opt/ros/noetic/setup.bash
source "$WS_PATH/devel/setup.bash"

if [ -f "$GAZEBO_CLASSIC_DIR/setup_gazebo.bash" ]; then
  source "$GAZEBO_CLASSIC_DIR/setup_gazebo.bash" "$PX4_PATH" "$PX4_BUILD_DIR"
  append_unique_path ROS_PACKAGE_PATH "$PX4_PATH"
  append_unique_path ROS_PACKAGE_PATH "$GAZEBO_CLASSIC_PKG_DIR"
else
  source "$PX4_PATH/Tools/setup_gazebo.bash" "$PX4_PATH" "$PX4_BUILD_DIR"
  append_unique_path ROS_PACKAGE_PATH "$PX4_PATH"
  append_unique_path ROS_PACKAGE_PATH "$LEGACY_GAZEBO_PKG_DIR"
fi

dedupe_colon_var ROS_PACKAGE_PATH
dedupe_colon_var GAZEBO_MODEL_PATH
append_unique_path GAZEBO_PLUGIN_PATH "$ROS_GAZEBO_PLUGIN_DIR"
dedupe_colon_var GAZEBO_PLUGIN_PATH
append_unique_path LD_LIBRARY_PATH "$GAZEBO_SYSTEM_PLUGIN_DIR"
dedupe_colon_var LD_LIBRARY_PATH

if [[ $_restore_nounset -eq 1 ]]; then
  set -u
fi

export ROS_PACKAGE_PATH
export GAZEBO_MODEL_PATH
export GAZEBO_PLUGIN_PATH
export LD_LIBRARY_PATH
export WS_PATH
export PX4_PATH
export PX4_DIR
export PX4_BUILD_DIR
export GAZEBO_CLASSIC_DIR
export GAZEBO_CLASSIC_PKG_DIR
export GAZEBO_SYSTEM_PLUGIN_DIR
export ROS_GAZEBO_PLUGIN_DIR
