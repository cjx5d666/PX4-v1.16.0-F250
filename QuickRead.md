# PX4 v1.16.0 Migration Patch Bundle

## Overview

这个目录是从当前 Codex PX4 工作区里整理出来的一份临时 GitHub 上传包。

它的定位不是完整发布整个 PX4 仓库，而是给“基于旧 GitHub 环境继续复现”的人提供一组最关键的补丁文件。

旧环境基线默认是：

- `cjx5d666/PX4-Gazebo-Egoplanner`

这份目录主要覆盖三类内容：

1. `PX4 v1.16.0` 迁移时必须替换的 PX4 文件
2. `catkin_ws` 里必须同步更新的启动/环境脚本
3. 后续做原生跟踪实验时用到的 tracking 脚本

## Files

### `px4_patch/`

放的是 PX4 `v1.16.0` 树里需要替换的文件：

- `launch/mavros_posix_sitl.launch`
- `ROMFS/px4fmu_common/init.d-posix/airframes/10015_gazebo-classic_iris`
- `Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris/iris.sdf.jinja`
- `Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris_depth_camera/iris_depth_camera.sdf`
- `Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris_depth_camera/model.config`

### `catkin_ws/`

放的是工作区脚本：

- `agent_env.sh`
- `start_sim.sh`
- `start_sim_agent.sh`
- `stop_sim.sh`
- `check_env.sh`
- `src/ego-planner/src/planner/plan_manage/launch/px4_single.launch`

### `tracking/`

放的是非 planner 原生跟踪实验脚本：

- `start_tracking_stack.sh`
- `run_tracking_suite.sh`
- `tracking_test_runner.py`
- `tracking_analysis.py`

## Steps

1. 先保留旧 PX4 树，不要原地覆盖：
   - `/home/adminpc/PX4-Autopilot`
2. 新建独立的：
   - `/home/adminpc/PX4-Autopilot-v1.16.0`
3. 把 `px4_patch/` 里的文件按相对路径覆盖到新树
4. 把 `catkin_ws/` 里的文件按相对路径覆盖到：
   - `/home/adminpc/catkin_ws`
5. 如果需要原生跟踪实验，再把 `tracking/` 里的脚本复制到：
   - `/home/adminpc/catkin_ws`
6. 所有从 Windows 写入 Linux 的脚本和 launch 文件都转成 `LF`
7. 构建：

```bash
cd /home/adminpc/PX4-Autopilot-v1.16.0
DONT_RUN=1 make px4_sitl gazebo-classic_iris_depth_camera -j"$(nproc)"
```

## Validation

推荐按三层验证：

1. 最小无 planner 验证
   - 先只确认 PX4 + Gazebo + MAVROS 能稳定起飞/悬停
2. agent 主链验证

```bash
cd /home/adminpc/catkin_ws
./stop_sim.sh
./start_sim_agent.sh
./start_sim_agent.sh --only-arm
```

3. GUI 主链验证

```bash
cd /home/adminpc/catkin_ws
./stop_sim.sh
./start_sim.sh
```

## Pitfalls

1. 不要把旧 `Tools/sitl_gazebo` 路径继续写死，`v1.16.0` 已经迁到：
   - `Tools/simulation/gazebo-classic/sitl_gazebo-classic`
2. 不要把 `iris.sdf` 这种生成物当长期手工编辑文件，长期维护的是：
   - `iris.sdf.jinja`
3. `CA_ROTOR*_PY` 不能直接照抄 Gazebo rotor pose，要按 PX4 control allocation 语义处理
4. `catkin_ws/iris.sdf.jinja` 只是项目侧检查点，不是 Gazebo 运行时唯一来源
5. Gazebo 外壳这次是 `visual-only` 修改，不影响物理碰撞体和动力学参数

