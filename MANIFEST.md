# GitHub Upload Manifest

这个目录已经收进去的内容，适合作为 GitHub 首次整理时的核心补丁文件。

## 已收进去的内容

### PX4 v1.16.0 迁移核心文件

- `px4_patch/launch/mavros_posix_sitl.launch`
- `px4_patch/ROMFS/px4fmu_common/init.d-posix/airframes/10015_gazebo-classic_iris`
- `px4_patch/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris/iris.sdf.jinja`
- `px4_patch/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris_depth_camera/iris_depth_camera.sdf`
- `px4_patch/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris_depth_camera/model.config`

### catkin 启动与环境脚本

- `catkin_ws/agent_env.sh`
- `catkin_ws/start_sim.sh`
- `catkin_ws/start_sim_agent.sh`
- `catkin_ws/stop_sim.sh`
- `catkin_ws/check_env.sh`
- `catkin_ws/guest_gnome_windowctl.py`
- `catkin_ws/px4_bridge.py`
- `catkin_ws/fix_cloud.py`
- `catkin_ws/mission_manager.py`
- `catkin_ws/obstacle_manager.py`
- `catkin_ws/src/ego-planner/src/planner/plan_manage/launch/px4_single.launch`
- `catkin_ws/src/ego-planner/src/planner/plan_manage/launch/default.rviz`

### 原生跟踪实验脚本

- `tracking/start_tracking_stack.sh`
- `tracking/run_tracking_suite.sh`
- `tracking/tracking_test_runner.py`
- `tracking/tracking_analysis.py`

## 当前没有单独收进去的内容

下面这些内容目前没有在这个临时目录里重复放一份：

- Ego-Planner 主体源码

原因不是它们不重要，而是这次临时 GitHub 收集目录主要针对：

1. `v1.16.0` 迁移补丁
2. 当前主线运行脚本
3. tracking 实验脚本

如果你后面还想把仓库再做完整，可以继续补：

- Ego-Planner 主体源码说明
- 依赖安装说明
- 环境初始化脚本

## 关于当前外壳版本

这个目录里的：

- `px4_patch/.../models/iris/iris.sdf.jinja`
- `px4_patch/.../models/iris_depth_camera/iris_depth_camera.sdf`

已经按当前主线的 Gazebo 外壳视觉重构版本更新过，重点包括：

- 更大的中心机身
- 更清晰的前伸机头
- 更明显的相机安装位
- 更像真实机体比例的机臂和电机位

而且这些改动是 `visual-only`，不会改变物理碰撞体和动力学参数。

## 这次应一并同步的 GUI 主链修补

如果要让 GitHub 仓库和当前稳定主线一致，下面这些修补也应该体现在
上传内容和对外说明里：

- `catkin_ws/start_sim.sh`
  已修复自动起飞阶段的目录问题
  - `stop_sim.sh` 清理后，`~/.cache/px4_auto` 需要在 stage 2 再次创建
  - 否则 `auto_takeoff.pid` / `hover_ready.flag` 可能直接失败
- `catkin_ws/start_sim.sh`
  已加入展示版窗口整理逻辑
  - 自动关闭 RViz 的 `ROS 1 End-of-Life` 弹窗
  - 自动把 `Gazebo` 摆左半屏
  - 自动把 `RViz` 摆右半屏
- 这个窗口整理依赖：
  - `catkin_ws/guest_gnome_windowctl.py`
- `catkin_ws/src/ego-planner/src/planner/plan_manage/launch/default.rviz`
  也应保持当前新版
  - 默认使用 `ThirdPersonFollower`
  - `Target Frame` 为 `base_link`
- `catkin_ws/stop_sim.sh`
  也应保持当前新版
  - 继续覆盖 `rviz / roslaunch ego_planner / tracking_* / auto_takeoff`
    等残留清理
