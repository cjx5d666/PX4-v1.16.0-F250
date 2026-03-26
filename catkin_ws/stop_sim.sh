#!/bin/bash

WS_PATH="${WS_PATH:-$HOME/catkin_ws}"
AGENT_ENV="$WS_PATH/agent_env.sh"

if [ -f "$AGENT_ENV" ]; then
  source "$AGENT_ENV" 2>/dev/null || true
else
  source /opt/ros/noetic/setup.bash 2>/dev/null || true
  source "$WS_PATH/devel/setup.bash" 2>/dev/null || true
fi

TERM_PID_DIR="$HOME/.cache/px4_sim_terminals"
AUTO_STATE_DIR="$HOME/.cache/px4_auto"
AUTO_PID_FILE="$AUTO_STATE_DIR/auto_takeoff.pid"

echo "正在清理仿真环境..."

rosnode kill -a > /dev/null 2>&1
killall -9 rosmaster > /dev/null 2>&1
killall -9 roscore > /dev/null 2>&1

killall -9 _px4_ > /dev/null 2>&1
killall -9 gzserver > /dev/null 2>&1
killall -9 gzclient > /dev/null 2>&1

pkill -f px4_bridge.py
pkill -f fix_cloud.py
pkill -f mission_manager.py
pkill -f obstacle_manager.py
pkill -f ego_planner_node
pkill -f traj_server
pkill -f 'roslaunch ego_planner'
pkill -f 'roslaunch px4'
pkill -f rviz
pkill -f codex_auto_takeoff_hold
pkill -f tracking_test_runner.py
pkill -f tracking_analysis.py

if [ -f "$AUTO_PID_FILE" ]; then
  pid="$(cat "$AUTO_PID_FILE" 2>/dev/null)"
  [ -n "$pid" ] && kill "$pid" > /dev/null 2>&1 || true
  [ -n "$pid" ] && kill -9 "$pid" > /dev/null 2>&1 || true
fi
rm -rf "$AUTO_STATE_DIR"

if [ -d "$TERM_PID_DIR" ]; then
  for pidfile in "$TERM_PID_DIR"/*.pid; do
    [ -f "$pidfile" ] || continue
    pid="$(cat "$pidfile" 2>/dev/null)"
    if [ -n "$pid" ]; then
      kill "$pid" > /dev/null 2>&1 || true
      sleep 0.2
      kill -9 "$pid" > /dev/null 2>&1 || true
    fi
    rm -f "$pidfile"
  done
fi

echo "清理完毕。干净利落！"
