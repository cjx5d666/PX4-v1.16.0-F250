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

_restore_nounset=0
if [[ $- == *u* ]]; then
  set +u
  _restore_nounset=1
fi

source /opt/ros/noetic/setup.bash
source "$WS_PATH/devel/setup.bash"

if [ -f "$GAZEBO_CLASSIC_DIR/setup_gazebo.bash" ]; then
  source "$GAZEBO_CLASSIC_DIR/setup_gazebo.bash" "$PX4_PATH" "$PX4_BUILD_DIR"
  export ROS_PACKAGE_PATH="$ROS_PACKAGE_PATH:$PX4_PATH:$GAZEBO_CLASSIC_PKG_DIR"
else
  source "$PX4_PATH/Tools/setup_gazebo.bash" "$PX4_PATH" "$PX4_BUILD_DIR"
  export ROS_PACKAGE_PATH="$ROS_PACKAGE_PATH:$PX4_PATH:$LEGACY_GAZEBO_PKG_DIR"
fi

if [[ $_restore_nounset -eq 1 ]]; then
  set -u
fi

export WS_PATH
export PX4_PATH
export PX4_DIR
export PX4_BUILD_DIR
export GAZEBO_CLASSIC_DIR
export GAZEBO_CLASSIC_PKG_DIR
