# PX4 `v1.16.0` Port for Custom Iris + Depth Camera + Ego-Planner

This document describes the changes required to port the original project workflow from a trusted PX4 `v1.13.x` baseline to PX4 `v1.16.0`, while preserving:

- the custom Iris model parameters
- the forward depth camera model
- MAVROS + Gazebo Classic SITL
- the `px4_bridge.py` / `fix_cloud.py` / Ego-Planner chain
- the GUI-visible one-click startup flow

## Important Note

You do **not** need to delete the original PX4 tree.

The migration can be done safely by:

1. keeping the original tree, for example:
   - `/home/adminpc/PX4-Autopilot`
2. adding a separate PX4 `v1.16.0` tree:
   - `/home/adminpc/PX4-Autopilot-v1.16.0`
3. updating launcher scripts and environment setup to prefer the new tree

This makes rollback much easier.

## Upstream Baseline

This project originally followed the environment shape documented in:

- [cjx5d666/PX4-Gazebo-Egoplanner](https://github.com/cjx5d666/PX4-Gazebo-Egoplanner)

The port described here is an additional layer on top of that baseline.

## What Changed Compared with the Old PX4 `v1.13.x` Layout

### 1. PX4 tree path

Old:

```bash
/home/adminpc/PX4-Autopilot
```

New:

```bash
/home/adminpc/PX4-Autopilot-v1.16.0
```

### 2. Gazebo Classic path

Old:

```bash
/home/adminpc/PX4-Autopilot/Tools/sitl_gazebo
/home/adminpc/PX4-Autopilot/Tools/setup_gazebo.bash
```

New:

```bash
/home/adminpc/PX4-Autopilot-v1.16.0/Tools/simulation/gazebo-classic/sitl_gazebo-classic
/home/adminpc/PX4-Autopilot-v1.16.0/Tools/simulation/gazebo-classic/setup_gazebo.bash
```

### 3. Airframe file target

The old custom workflow often touched:

```bash
ROMFS/px4fmu_common/init.d-posix/airframes/10016_iris
```

For PX4 `v1.16.0`, the relevant Gazebo Classic Iris files are:

```bash
ROMFS/px4fmu_common/init.d-posix/airframes/10015_gazebo-classic_iris
ROMFS/px4fmu_common/init.d-posix/airframes/1015_gazebo-classic_iris_depth_camera
```

## Files That Must Be Ported

### PX4 side

```bash
/home/adminpc/PX4-Autopilot-v1.16.0/launch/mavros_posix_sitl.launch
/home/adminpc/PX4-Autopilot-v1.16.0/ROMFS/px4fmu_common/init.d-posix/airframes/10015_gazebo-classic_iris
/home/adminpc/PX4-Autopilot-v1.16.0/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris/iris.sdf.jinja
/home/adminpc/PX4-Autopilot-v1.16.0/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris_depth_camera/iris_depth_camera.sdf
/home/adminpc/PX4-Autopilot-v1.16.0/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris_depth_camera/model.config
```

### Catkin / planner side

```bash
/home/adminpc/catkin_ws/agent_env.sh
/home/adminpc/catkin_ws/start_sim_agent.sh
/home/adminpc/catkin_ws/start_sim.sh
/home/adminpc/catkin_ws/stop_sim.sh
/home/adminpc/catkin_ws/check_env.sh
/home/adminpc/catkin_ws/src/ego-planner/src/planner/plan_manage/launch/px4_single.launch
```

### Shell default

```bash
/home/adminpc/.bashrc
```

## Step-by-Step Port Procedure

### Step 1. Clone PX4 `v1.16.0` into a new directory

```bash
cd /home/adminpc
git clone --recursive --branch v1.16.0 --depth 1 --shallow-submodules \
  https://github.com/PX4/PX4-Autopilot.git PX4-Autopilot-v1.16.0

cd /home/adminpc/PX4-Autopilot-v1.16.0
git switch -c px4-v1.16-custom-port
```

### Step 2. Fetch tag history for a clean build

This is required because a shallow clone may fail during version header generation.

```bash
cd /home/adminpc/PX4-Autopilot-v1.16.0
git fetch --tags --unshallow || git fetch --tags

cd /home/adminpc/PX4-Autopilot-v1.16.0/platforms/nuttx/NuttX/nuttx
git fetch --tags --unshallow || git fetch --tags

cd /home/adminpc/PX4-Autopilot-v1.16.0/platforms/nuttx/NuttX/apps
git fetch --tags --unshallow || git fetch --tags
```

### Step 3. Port the custom Gazebo Classic model files

Copy your custom model files from the old PX4 tree into the new Gazebo Classic location.

```bash
cp /home/adminpc/PX4-Autopilot/Tools/sitl_gazebo/models/iris/iris.sdf.jinja \
   /home/adminpc/PX4-Autopilot-v1.16.0/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris/iris.sdf.jinja

cp /home/adminpc/PX4-Autopilot/Tools/sitl_gazebo/models/iris_depth_camera/iris_depth_camera.sdf \
   /home/adminpc/PX4-Autopilot-v1.16.0/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris_depth_camera/iris_depth_camera.sdf

cp /home/adminpc/PX4-Autopilot/Tools/sitl_gazebo/models/iris_depth_camera/model.config \
   /home/adminpc/PX4-Autopilot-v1.16.0/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris_depth_camera/model.config
```

### Step 4. Re-apply MAVROS local TF settings

In:

```bash
/home/adminpc/PX4-Autopilot-v1.16.0/launch/mavros_posix_sitl.launch
```

add:

```xml
<group ns="mavros">
  <param name="local_position/tf/send" value="true"/>
  <param name="local_position/tf/frame_id" value="map"/>
  <param name="local_position/tf/child_frame_id" value="base_link"/>
  <param name="global_position/tf/send" value="false"/>
</group>
```

### Step 5. Update the PX4 `v1.16.0` Iris airframe control-allocation values

Edit:

```bash
/home/adminpc/PX4-Autopilot-v1.16.0/ROMFS/px4fmu_common/init.d-posix/airframes/10015_gazebo-classic_iris
```

Use:

```sh
param set-default CA_ROTOR_COUNT 4
param set-default CA_ROTOR0_PX 0.0884
param set-default CA_ROTOR0_PY 0.0884
param set-default CA_ROTOR0_KM 0.015652892561983472
param set-default CA_ROTOR1_PX -0.0884
param set-default CA_ROTOR1_PY -0.0884
param set-default CA_ROTOR1_KM 0.015652892561983472
param set-default CA_ROTOR2_PX 0.0884
param set-default CA_ROTOR2_PY -0.0884
param set-default CA_ROTOR2_KM -0.015652892561983472
param set-default CA_ROTOR3_PX -0.0884
param set-default CA_ROTOR3_PY 0.0884
param set-default CA_ROTOR3_KM -0.015652892561983472
```

## Custom Model Parameters Used in This Port

The custom Iris model template in:

```bash
/home/adminpc/PX4-Autopilot-v1.16.0/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris/iris.sdf.jinja
```

was ported with the following key values:

### Body / inertia

```xml
<mass>0.70</mass>
<ixx>0.003164</ixx>
<iyy>0.003164</iyy>
<izz>0.006044</izz>
```

### Rotor geometry

```xml
rotor pose radius arm: 0.0884
rotor collision radius: 0.0635
```

### Motor model

```xml
<timeConstantUp>0.0081</timeConstantUp>
<timeConstantDown>0.0081</timeConstantDown>
<maxRotVelocity>2237.54</maxRotVelocity>
<motorConstant>1.815e-06</motorConstant>
<momentConstant>0.015652892561983472</momentConstant>
```

### Control channel mapping

```xml
<input_scaling>1913.76</input_scaling>
<zero_position_armed>323.78</zero_position_armed>
```

## Step 6. Update environment bootstrap and launcher scripts

The safest approach is:

- keep the old PX4 tree on disk
- update scripts so they prefer `PX4-Autopilot-v1.16.0` if it exists
- fall back to the old tree only if the new one is missing

### `agent_env.sh`

Make sure it:

1. prefers `/home/adminpc/PX4-Autopilot-v1.16.0`
2. uses:

```bash
/home/adminpc/PX4-Autopilot-v1.16.0/Tools/simulation/gazebo-classic/setup_gazebo.bash
```

3. exports:

```bash
ROS_PACKAGE_PATH+=:/home/adminpc/PX4-Autopilot-v1.16.0
ROS_PACKAGE_PATH+=:/home/adminpc/PX4-Autopilot-v1.16.0/Tools/simulation/gazebo-classic/sitl_gazebo-classic
```

### `start_sim.sh`

Keep the GUI-visible staged workflow:

1. start PX4 + Gazebo + MAVROS
2. auto takeoff / hold to `~2.5m`
3. start obstacles + bridge + cloud fix + planner
4. wait for planning topics
5. start mission manager
6. release handover to bridge/planner

### `start_sim_agent.sh`

Keep support for:

```bash
./start_sim_agent.sh
./start_sim_agent.sh --only-arm
./start_sim_agent.sh --arm-offboard
```

### `px4_single.launch`

Add support for:

```xml
<arg name="enable_rviz" default="true"/>
```

and gate RViz with `if="$(arg enable_rviz)"`.

## Step 7. Convert files to LF and make scripts executable

If any files are copied from Windows, convert them to LF:

```bash
perl -0pi -e 's/\r\n/\n/g' \
  /home/adminpc/PX4-Autopilot-v1.16.0/launch/mavros_posix_sitl.launch \
  /home/adminpc/PX4-Autopilot-v1.16.0/ROMFS/px4fmu_common/init.d-posix/airframes/10015_gazebo-classic_iris \
  /home/adminpc/PX4-Autopilot-v1.16.0/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris/iris.sdf.jinja \
  /home/adminpc/PX4-Autopilot-v1.16.0/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris_depth_camera/iris_depth_camera.sdf \
  /home/adminpc/PX4-Autopilot-v1.16.0/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris_depth_camera/model.config \
  /home/adminpc/catkin_ws/agent_env.sh \
  /home/adminpc/catkin_ws/start_sim_agent.sh \
  /home/adminpc/catkin_ws/start_sim.sh \
  /home/adminpc/catkin_ws/stop_sim.sh

chmod +x \
  /home/adminpc/catkin_ws/agent_env.sh \
  /home/adminpc/catkin_ws/start_sim_agent.sh \
  /home/adminpc/catkin_ws/start_sim.sh \
  /home/adminpc/catkin_ws/stop_sim.sh
```

## Step 8. Build PX4 `v1.16.0`

```bash
cd /home/adminpc/PX4-Autopilot-v1.16.0
DONT_RUN=1 make px4_sitl gazebo-classic_iris_depth_camera -j"$(nproc)"
```

## Validation Workflow

### 1. Minimal hover check

First validate:

- PX4
- Gazebo
- MAVROS
- no planner

The goal is to confirm that the ported model is flyable before debugging planner behavior.

### 2. Full agent workflow

```bash
cd /home/adminpc/catkin_ws
./stop_sim.sh
./start_sim_agent.sh
./start_sim_agent.sh --only-arm
```

Check:

- `/mavros/state`
- `/cloud_corrected`
- `/planning/pos_cmd`
- `/waypoint_generator/waypoints`
- `/depth_camera/points`

### 3. Full GUI workflow

```bash
cd /home/adminpc/catkin_ws
./stop_sim.sh
./start_sim.sh
```

Expected staged feedback:

```text
正在启动魔改自主导航仿真系统...
阶段 1/4: 启动 PX4 + Gazebo + MAVROS
阶段 2/4: 自动起飞并保持到 2.5m
阶段 3/4: 高度稳定，启动障碍物/桥接/点云/规划器
阶段 4/4: 规划链路已就绪，启动任务管理器并交接控制
自动起飞保持器已释放，现由 bridge/planner 接管。
```

## Pitfalls That Matter

### Pitfall 1. Do not overwrite the original PX4 tree in place

Keep the original tree and add a separate `v1.16.0` tree.

### Pitfall 2. Do not keep using the old `Tools/sitl_gazebo` path

PX4 `v1.16.0` Gazebo Classic lives under:

```bash
Tools/simulation/gazebo-classic/sitl_gazebo-classic
```

### Pitfall 3. Do not manually maintain generated `iris.sdf`

Edit:

```bash
iris.sdf.jinja
```

not:

```bash
iris.sdf
```

Otherwise the build may fail with overwrite protection.

### Pitfall 4. The first airframe port can fail if `CA_ROTOR*_PY` is copied directly from Gazebo rotor poses

This was a real migration bug.

PX4 control allocation in `v1.16.0` expects rotor coordinates with PX4 frame semantics, not a blind copy of Gazebo SDF values.

Symptoms include:

- the vehicle falls or flips
- local pose goes below ground
- arming becomes unstable
- planner falsely reports that the drone is inside an obstacle

### Pitfall 5. Files copied from Windows must use LF

CRLF can break:

- ROS package discovery
- shell scripts
- environment exports

### Pitfall 6. Keep GUI terminal tabs on `bash -ic`

Using `bash -c` can silently drop the ROS/PX4 environment.

## Daily Usage After the Port

### GUI workflow

```bash
cd /home/adminpc/catkin_ws
./stop_sim.sh
./start_sim.sh
```

### Agent workflow

```bash
cd /home/adminpc/catkin_ws
./stop_sim.sh
./start_sim_agent.sh
./start_sim_agent.sh --only-arm
```

### Environment check

```bash
cd /home/adminpc/catkin_ws
./check_env.sh
```

## Summary

This port does **not** require deleting the old PX4 tree.

The safer approach is:

1. keep the original `v1.13.x` tree
2. add a new `v1.16.0` tree
3. port the custom Gazebo Classic model files
4. port the control allocation values
5. update scripts and environment to prefer the new tree
6. validate minimal hover first, then the full planner chain
