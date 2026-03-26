# PX4 `v1.16.0` 迁移实操教程

这份 README 不是概念说明，而是一份按顺序执行的实际教程。

默认前提只有一个：

- 你已经按旧 GitHub 基线把原项目环境搭起来了
- 旧基线参考仓库是：
  - `cjx5d666/PX4-Gazebo-Egoplanner`

这份补丁包的作用不是替代旧仓库，而是告诉你：

1. 先保留旧环境
2. 再单独下载 `PX4 v1.16.0`
3. 然后把这个补丁包里的文件复制到正确位置
4. 最后构建和验证

如果你只是想“不要动脑子，直接照着做”，就从下面的 Step 0 开始。

## Overview

迁移后的目标状态是：

- 旧 PX4 树保留：
  - `/home/adminpc/PX4-Autopilot`
- 新 PX4 树新建：
  - `/home/adminpc/PX4-Autopilot-v1.16.0`
- catkin 工作区仍然是：
  - `/home/adminpc/catkin_ws`

这个补丁包里已经放好了三类文件：

1. `px4_patch/`
   - 要复制到 `PX4-Autopilot-v1.16.0` 里的文件
2. `catkin_ws/`
   - 要复制到 `/home/adminpc/catkin_ws` 里的主链和环境文件
3. `tracking/`
   - 后续做原生跟踪实验时要复制到 `/home/adminpc/catkin_ws` 里的文件

当前这份补丁包里包含的 `iris.sdf.jinja` 和 `iris_depth_camera.sdf` 已经是最新主线版本：

- 已带当前定版动力学参数
- 已带当前 Gazebo 外壳视觉重构
- 外壳改动是 `visual-only`
- 不改物理碰撞体和动力学

## Files

### 这份补丁包里实际包含的文件

#### `px4_patch/`

- `launch/mavros_posix_sitl.launch`
- `ROMFS/px4fmu_common/init.d-posix/airframes/10015_gazebo-classic_iris`
- `Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris/iris.sdf.jinja`
- `Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris_depth_camera/iris_depth_camera.sdf`
- `Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris_depth_camera/model.config`

#### `catkin_ws/`

- `agent_env.sh`
- `start_sim.sh`
- `start_sim_agent.sh`
- `stop_sim.sh`
- `check_env.sh`
- `guest_gnome_windowctl.py`
- `px4_bridge.py`
- `fix_cloud.py`
- `mission_manager.py`
- `obstacle_manager.py`
- `src/ego-planner/src/planner/plan_manage/launch/px4_single.launch`
- `src/ego-planner/src/planner/plan_manage/launch/default.rviz`

#### `tracking/`

- `start_tracking_stack.sh`
- `run_tracking_suite.sh`
- `tracking_test_runner.py`
- `tracking_analysis.py`

### 这份补丁包默认不重复提供的旧基线内容

下面这些内容默认还是来自旧 GitHub 基线环境本身，不在这个补丁包里重复放：

- Ego-Planner 主体源码

所以本教程默认你已经有一套旧基线工作区，并且这些文件已经存在于：

- `/home/adminpc/catkin_ws`

## Steps

## Step 0. 先确认你手里已经有旧基线

先确认这几个路径存在：

```bash
ls /home/adminpc/PX4-Autopilot
ls /home/adminpc/catkin_ws
ls /home/adminpc/catkin_ws/src/ego-planner
```

如果这些都存在，说明你已经有旧 GitHub 环境，可以继续。

如果这些都不存在，不要直接跳过，你应该先按旧仓库 README 把旧基线搭起来，再回来做这份补丁。

## Step 1. 把这个补丁包仓库放到本机

假设你把这个补丁包仓库克隆到：

```bash
/home/adminpc/px4-v1.16-patch-bundle
```

后面所有命令都按这个路径写。

先定义几个变量，后面直接复制命令时不容易出错：

```bash
PATCH_ROOT=/home/adminpc/px4-v1.16-patch-bundle
OLD_PX4=/home/adminpc/PX4-Autopilot
NEW_PX4=/home/adminpc/PX4-Autopilot-v1.16.0
WS=/home/adminpc/catkin_ws
```

## Step 2. 下载官方 `PX4 v1.16.0`

不要覆盖旧树，直接新建一棵：

```bash
cd /home/adminpc
git clone --recursive --branch v1.16.0 --depth 1 --shallow-submodules \
  https://github.com/PX4/PX4-Autopilot.git PX4-Autopilot-v1.16.0
```

然后进入新树：

```bash
cd /home/adminpc/PX4-Autopilot-v1.16.0
git switch -c codex/px4-v1.16-migration
```

## Step 3. 先补齐 shallow clone 缺失的 tag/history

这一步不要省。

如果不做，后面构建很可能会在 `px_update_git_header.py` 或 NuttX 版本头生成上报错。

照着执行：

```bash
cd $NEW_PX4
git fetch --tags --unshallow || git fetch --tags

cd $NEW_PX4/platforms/nuttx/NuttX/nuttx
git fetch --tags --unshallow || git fetch --tags

cd $NEW_PX4/platforms/nuttx/NuttX/apps
git fetch --tags --unshallow || git fetch --tags
```

## Step 4. 把补丁包里的 PX4 文件复制到 `v1.16.0` 新树

先确保目标目录存在：

```bash
mkdir -p $NEW_PX4/launch
mkdir -p $NEW_PX4/ROMFS/px4fmu_common/init.d-posix/airframes
mkdir -p $NEW_PX4/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris
mkdir -p $NEW_PX4/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris_depth_camera
```

然后直接复制：

```bash
cp $PATCH_ROOT/px4_patch/launch/mavros_posix_sitl.launch \
  $NEW_PX4/launch/mavros_posix_sitl.launch

cp $PATCH_ROOT/px4_patch/ROMFS/px4fmu_common/init.d-posix/airframes/10015_gazebo-classic_iris \
  $NEW_PX4/ROMFS/px4fmu_common/init.d-posix/airframes/10015_gazebo-classic_iris

cp $PATCH_ROOT/px4_patch/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris/iris.sdf.jinja \
  $NEW_PX4/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris/iris.sdf.jinja

cp $PATCH_ROOT/px4_patch/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris_depth_camera/iris_depth_camera.sdf \
  $NEW_PX4/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris_depth_camera/iris_depth_camera.sdf

cp $PATCH_ROOT/px4_patch/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris_depth_camera/model.config \
  $NEW_PX4/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris_depth_camera/model.config
```

到这里为止，`v1.16.0` 侧和模型相关的关键文件就已经替换好了。

## Step 5. 把补丁包里的 catkin 工作区脚本复制到工作区

先确保 planner launch 的目标目录存在：

```bash
mkdir -p $WS/src/ego-planner/src/planner/plan_manage/launch
```

然后直接复制：

```bash
cp $PATCH_ROOT/catkin_ws/agent_env.sh $WS/agent_env.sh
cp $PATCH_ROOT/catkin_ws/start_sim.sh $WS/start_sim.sh
cp $PATCH_ROOT/catkin_ws/start_sim_agent.sh $WS/start_sim_agent.sh
cp $PATCH_ROOT/catkin_ws/stop_sim.sh $WS/stop_sim.sh
cp $PATCH_ROOT/catkin_ws/check_env.sh $WS/check_env.sh
cp $PATCH_ROOT/catkin_ws/guest_gnome_windowctl.py $WS/guest_gnome_windowctl.py
cp $PATCH_ROOT/catkin_ws/px4_bridge.py $WS/px4_bridge.py
cp $PATCH_ROOT/catkin_ws/fix_cloud.py $WS/fix_cloud.py
cp $PATCH_ROOT/catkin_ws/mission_manager.py $WS/mission_manager.py
cp $PATCH_ROOT/catkin_ws/obstacle_manager.py $WS/obstacle_manager.py

cp $PATCH_ROOT/catkin_ws/src/ego-planner/src/planner/plan_manage/launch/px4_single.launch \
  $WS/src/ego-planner/src/planner/plan_manage/launch/px4_single.launch

cp $PATCH_ROOT/catkin_ws/src/ego-planner/src/planner/plan_manage/launch/default.rviz \
  $WS/src/ego-planner/src/planner/plan_manage/launch/default.rviz
```

这一步完成后，新的环境脚本和启动脚本就进入工作区了。

## Step 6. 如果要做原生跟踪实验，再复制 tracking 脚本

如果你暂时只想跑主链，这一步可以先跳过。

如果你后面还想做原生跟踪实验，把下面几个文件也复制进去：

```bash
cp $PATCH_ROOT/tracking/start_tracking_stack.sh $WS/start_tracking_stack.sh
cp $PATCH_ROOT/tracking/run_tracking_suite.sh $WS/run_tracking_suite.sh
cp $PATCH_ROOT/tracking/tracking_test_runner.py $WS/tracking_test_runner.py
cp $PATCH_ROOT/tracking/tracking_analysis.py $WS/tracking_analysis.py
```

## Step 7. 把从 Windows/GitHub 下来的脚本统一转成 LF

这一步非常重要，不要省。

如果这些文件带 `CRLF`，可能会出现：

- `ROS_PACKAGE_PATH` 污染
- `rospack` 找包失败
- shell 脚本行为异常

直接执行：

```bash
perl -0pi -e 's/\r\n/\n/g' \
  $NEW_PX4/launch/mavros_posix_sitl.launch \
  $NEW_PX4/ROMFS/px4fmu_common/init.d-posix/airframes/10015_gazebo-classic_iris \
  $NEW_PX4/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris/iris.sdf.jinja \
  $NEW_PX4/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris_depth_camera/iris_depth_camera.sdf \
  $NEW_PX4/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris_depth_camera/model.config \
  $WS/agent_env.sh \
  $WS/start_sim.sh \
  $WS/start_sim_agent.sh \
  $WS/stop_sim.sh \
  $WS/check_env.sh \
  $WS/guest_gnome_windowctl.py \
  $WS/px4_bridge.py \
  $WS/fix_cloud.py \
  $WS/mission_manager.py \
  $WS/obstacle_manager.py \
  $WS/src/ego-planner/src/planner/plan_manage/launch/px4_single.launch \
  $WS/src/ego-planner/src/planner/plan_manage/launch/default.rviz
```

如果你复制了 tracking 脚本，也一并转掉：

```bash
perl -0pi -e 's/\r\n/\n/g' \
  $WS/start_tracking_stack.sh \
  $WS/run_tracking_suite.sh \
  $WS/tracking_test_runner.py \
  $WS/tracking_analysis.py
```

## Step 8. 给工作区脚本加执行权限

```bash
chmod +x \
  $WS/agent_env.sh \
  $WS/start_sim.sh \
  $WS/start_sim_agent.sh \
  $WS/stop_sim.sh \
  $WS/check_env.sh \
  $WS/guest_gnome_windowctl.py
```

如果你复制了 tracking 脚本，再执行：

```bash
chmod +x \
  $WS/start_tracking_stack.sh \
  $WS/run_tracking_suite.sh
```

## Step 9. 构建 `PX4 v1.16.0`

```bash
cd $NEW_PX4
DONT_RUN=1 make px4_sitl gazebo-classic_iris_depth_camera -j"$(nproc)"
```

如果构建通过，说明 `v1.16.0` 新树至少在编译层面是通的。

## Step 10. 如果你想让默认 shell 也优先走 `v1.16.0`

这一步不是必须的，因为 `agent_env.sh` 已经会优先使用新树。

但如果你希望登录 shell 也默认走 `v1.16.0`，可以在 `~/.bashrc` 里按下面逻辑配置：

```bash
if [ -d "$HOME/PX4-Autopilot-v1.16.0" ]; then
  export PX4_DIR="$HOME/PX4-Autopilot-v1.16.0"
else
  export PX4_DIR="$HOME/PX4-Autopilot"
fi
```

然后如果是 `v1.16.0`，要确保走的是：

```bash
$PX4_DIR/Tools/simulation/gazebo-classic/setup_gazebo.bash
```

## Validation

不要一上来就跑完整 planner 主链。

最稳的办法是按下面三层验证。

## 第一层验证：最小无 planner 验证

目的：

- 只验证 PX4 + Gazebo + MAVROS 是不是能稳定起来
- 先把 planner 排除掉

如果你已经复制了 tracking 脚本，可以这样跑：

```bash
cd $WS
./stop_sim.sh
./start_tracking_stack.sh --gui
```

这一层通过，说明最基础的飞行模型和启动链已经没问题。

## 第二层验证：agent 主链验证

```bash
cd $WS
./stop_sim.sh
./start_sim_agent.sh
./start_sim_agent.sh --only-arm
```

然后检查：

```bash
rostopic list | grep -E '/mavros/state|/cloud_corrected|/planning/pos_cmd|/waypoint_generator/waypoints|/depth_camera/points'
```

## 第三层验证：GUI 主链验证

```bash
cd $WS
./stop_sim.sh
./start_sim.sh
```

正常情况下应该能看到四阶段反馈：

```text
正在启动魔改自主导航仿真系统...
阶段 1/4: 启动 PX4 + Gazebo + MAVROS
阶段 2/4: 自动起飞并保持到 2.5m
阶段 3/4: 高度稳定，启动障碍物/桥接/点云/规划器
阶段 4/4: 规划链路已就绪，启动任务管理器并交接控制
自动起飞保持器已释放，现由 bridge/planner 接管。
```

当前 `start_sim.sh` 还有两个已经并入的 GUI 展示修补：

1. 自动起飞阶段的状态目录会被再次创建
   - 否则 `~/.cache/px4_auto/auto_takeoff.pid` 可能报目录不存在
   - 进而导致 `hover_ready.flag` 等不到
2. 当 `Gazebo` 和 `RViz` 都起来后，会自动：
   - 关闭 RViz 的 `ROS 1 End-of-Life` 弹窗
   - 把 `Gazebo` 摆到左半屏
   - 把 `RViz` 摆到右半屏

另外，当前补丁包也把 `default.rviz` 一起带上了：

- `RViz` 默认视角会和当前主线一致
- 当前配置是：
  - `ThirdPersonFollower`
  - `Target Frame: base_link`

如果这一层也通过，说明：

- `PX4 v1.16.0` 迁移成功
- 当前机体参数可用
- 深度相机链可用
- 主启动链可用

## Pitfalls

### 1. 不要原地覆盖旧 PX4 树

旧树必须保留：

```bash
/home/adminpc/PX4-Autopilot
```

新树单独新建：

```bash
/home/adminpc/PX4-Autopilot-v1.16.0
```

### 2. 不要继续使用旧 `Tools/sitl_gazebo` 路径

`v1.16.0` 里 Gazebo Classic 已经迁到：

```bash
Tools/simulation/gazebo-classic/sitl_gazebo-classic
```

### 3. 不要把 `iris.sdf` 当长期编辑文件

长期维护的是：

```bash
iris.sdf.jinja
```

不是生成物：

```bash
iris.sdf
```

### 4. `CA_ROTOR*_PY` 不能直接照抄 Gazebo rotor pose

这是这次迁移里最关键的坑之一。

PX4 `v1.16.0` 这边的 control allocation 参数有自己的坐标语义，不能直接把 Gazebo rotor `y` 原样搬过去。

### 5. `catkin_ws/iris.sdf.jinja` 不是 Gazebo 运行时唯一来源

项目侧主记录文件是：

```bash
/home/adminpc/catkin_ws/iris.sdf.jinja
```

但 Gazebo 运行时实际生效的，仍然是 PX4 `v1.16.0` 树里的：

```bash
/home/adminpc/PX4-Autopilot-v1.16.0/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris/iris.sdf.jinja
/home/adminpc/PX4-Autopilot-v1.16.0/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris_depth_camera/iris_depth_camera.sdf
```

### 6. 当前外壳改动是 `visual-only`

这次补丁包里的外壳重构只改了可视化外观，没有改：

- `collision`
- `mass`
- `inertia`
- rotor `pose`
- depth camera 真实挂点

所以：

- 它会改变 Gazebo 里“看起来像什么”
- 不会直接改变物理碰撞体
- 不会直接重改动力学参数
