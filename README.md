# PX4 `v1.16.0` 公开 README 补丁说明

这份文档是给“从旧 GitHub 环境继续复现到当前可运行环境”的人看的中文说明。
如果🚫不需要深入了解，只想快速升级仿真环境的话，请直接看- `QuickRead.md`

它不是通用 PX4 升级教程，而是基于原始项目仓库：

- `cjx5d666/PX4-Gazebo-Egoplanner`

在当前这套环境里实际做过的迁移、换参、启动链修补、深度相机保留和 Gazebo 外壳重构记录。

目标是回答下面这些最实际的问题：

1. 旧环境到底以什么为基线
2. 为什么要单独上 `PX4 v1.16.0`
3. 从旧环境迁到 `v1.16.0` 具体要改哪些文件
4. 机体模型、深度相机、控制分配参数分别落在哪些文件
5. 哪些文件可以直接复制，复制到哪里
6. 怎么验证现在这套主链是真的跑通了

## 一、先讲清楚当前环境形态

这不是一个“单仓库、单命令”的普通项目。

当前实际运行环境分成三块：

### 1. PX4 主树

旧树保留在：

```bash
/home/adminpc/PX4-Autopilot
```

当前主运行树在：

```bash
/home/adminpc/PX4-Autopilot-v1.16.0
```

### 2. catkin 工作区

```bash
/home/adminpc/catkin_ws
```

里面放的是：

- `start_sim.sh`
- `start_sim_agent.sh`
- `stop_sim.sh`
- `agent_env.sh`
- `check_env.sh`
- `px4_bridge.py`
- `fix_cloud.py`
- `mission_manager.py`
- `obstacle_manager.py`
- 跟踪实验脚本

### 3. Ego-Planner 工程

```bash
/home/adminpc/catkin_ws/src/ego-planner
```

所以整个系统真正跑起来时，实际是：

- PX4 SITL
- Gazebo Classic
- MAVROS
- 深度相机模型
- 点云修正链
- PX4 bridge
- Ego-Planner
- mission manager

一起构成的一条链。

## 二、旧 GitHub 环境到底是什么基线

当前复现的原始参考不是官方 PX4 README，而是：

- `https://github.com/cjx5d666/PX4-Gazebo-Egoplanner`

应该把它理解成：

- 这是原始人类配置好的旧环境参考
- 当前这套能跑的系统，是在它的基础上继续做了本地迁移和修补

也就是说，公开 README 里如果要写“起点”，应该先承认：

1. 原始环境是 PX4 老版本路径组织
2. 原始 Gazebo 模型路径还是 `Tools/sitl_gazebo`
3. 当前公开补丁不是重新发明一套新系统
4. 而是把那套旧环境迁到了 `PX4 v1.16.0`

## 三、这次迁移为什么不是直接覆盖旧树

不要在：

```bash
/home/adminpc/PX4-Autopilot
```

上原地升级。

这次实际采用的是“双树并存”策略：

- 旧树继续保留：
  - `/home/adminpc/PX4-Autopilot`
- 新树单独新建：
  - `/home/adminpc/PX4-Autopilot-v1.16.0`

这么做的原因很简单：

1. 一旦迁移失败，可以立刻回看旧树差异
2. 不会把原来还能跑的基线直接毁掉
3. 可以把“迁移问题”和“旧项目本身问题”分开排查

这一步是整个迁移里最重要的策略选择之一。

## 四、从旧 PX4 到 `v1.16.0`，目录上哪些地方变了

### 1. PX4 树路径变了

旧：

```bash
/home/adminpc/PX4-Autopilot
```

新：

```bash
/home/adminpc/PX4-Autopilot-v1.16.0
```

### 2. Gazebo Classic 路径变了

旧：

```bash
/home/adminpc/PX4-Autopilot/Tools/sitl_gazebo
/home/adminpc/PX4-Autopilot/Tools/setup_gazebo.bash
```

新：

```bash
/home/adminpc/PX4-Autopilot-v1.16.0/Tools/simulation/gazebo-classic/sitl_gazebo-classic
/home/adminpc/PX4-Autopilot-v1.16.0/Tools/simulation/gazebo-classic/setup_gazebo.bash
```

### 3. Airframe 入口语义变了

旧环境经常直接碰的是：

```bash
ROMFS/px4fmu_common/init.d-posix/airframes/10016_iris
```

现在 `v1.16.0` Gazebo Classic 这一侧，核心目标变成：

```bash
/home/adminpc/PX4-Autopilot-v1.16.0/ROMFS/px4fmu_common/init.d-posix/airframes/10015_gazebo-classic_iris
/home/adminpc/PX4-Autopilot-v1.16.0/ROMFS/px4fmu_common/init.d-posix/airframes/1015_gazebo-classic_iris_depth_camera
```

不能再机械沿用旧文件名。

## 五、这次迁移实际改了哪些文件

### 1. PX4 树内必须改的文件

```bash
/home/adminpc/PX4-Autopilot-v1.16.0/launch/mavros_posix_sitl.launch
/home/adminpc/PX4-Autopilot-v1.16.0/ROMFS/px4fmu_common/init.d-posix/airframes/10015_gazebo-classic_iris
/home/adminpc/PX4-Autopilot-v1.16.0/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris/iris.sdf.jinja
/home/adminpc/PX4-Autopilot-v1.16.0/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris/iris.sdf
/home/adminpc/PX4-Autopilot-v1.16.0/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris_depth_camera/iris_depth_camera.sdf
/home/adminpc/PX4-Autopilot-v1.16.0/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris_depth_camera/model.config
```

### 2. catkin 工作区里必须跟着改的文件

```bash
/home/adminpc/catkin_ws/agent_env.sh
/home/adminpc/catkin_ws/start_sim_agent.sh
/home/adminpc/catkin_ws/start_sim.sh
/home/adminpc/catkin_ws/stop_sim.sh
/home/adminpc/catkin_ws/check_env.sh
/home/adminpc/catkin_ws/src/ego-planner/src/planner/plan_manage/launch/px4_single.launch
```

### 3. shell 默认环境文件

```bash
/home/adminpc/.bashrc
```

## 六、推荐的实际迁移步骤

下面这套顺序是按“真的做过、也踩过坑”的顺序整理的。

### Step 1. 新建 `v1.16.0` 独立工作树

```bash
cd /home/adminpc
git clone --recursive --branch v1.16.0 --depth 1 --shallow-submodules \
  https://github.com/PX4/PX4-Autopilot.git PX4-Autopilot-v1.16.0

cd /home/adminpc/PX4-Autopilot-v1.16.0
git switch -c codex/px4-v1.16-migration
```

### Step 2. 先补齐 shallow clone 缺失的 tag/history

这是这次迁移里的第一个构建坑。

如果直接构建，可能会在 `px_update_git_header.py` 上炸掉，原因是 NuttX 子模块历史太浅。

执行：

```bash
cd /home/adminpc/PX4-Autopilot-v1.16.0
git fetch --tags --unshallow || git fetch --tags

cd /home/adminpc/PX4-Autopilot-v1.16.0/platforms/nuttx/NuttX/nuttx
git fetch --tags --unshallow || git fetch --tags

cd /home/adminpc/PX4-Autopilot-v1.16.0/platforms/nuttx/NuttX/apps
git fetch --tags --unshallow || git fetch --tags
```

### Step 3. 先把旧树里的模型和相机文件迁过来

如果你已经在旧环境里有一套可用的魔改模型，最省事的办法不是重写，而是直接复制。

```bash
cp /home/adminpc/PX4-Autopilot/Tools/sitl_gazebo/models/iris/iris.sdf.jinja \
  /home/adminpc/PX4-Autopilot-v1.16.0/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris/iris.sdf.jinja

cp /home/adminpc/PX4-Autopilot/Tools/sitl_gazebo/models/iris_depth_camera/iris_depth_camera.sdf \
  /home/adminpc/PX4-Autopilot-v1.16.0/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris_depth_camera/iris_depth_camera.sdf

cp /home/adminpc/PX4-Autopilot/Tools/sitl_gazebo/models/iris_depth_camera/model.config \
  /home/adminpc/PX4-Autopilot-v1.16.0/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris_depth_camera/model.config
```

### Step 4. 再改 `mavros_posix_sitl.launch`

目标文件：

```bash
/home/adminpc/PX4-Autopilot-v1.16.0/launch/mavros_posix_sitl.launch
```

要把之前用过的 MAVROS local TF 参数补回去，至少应确保：

```xml
<group ns="mavros">
  <param name="local_position/tf/send" value="true"/>
  <param name="local_position/tf/frame_id" value="map"/>
  <param name="local_position/tf/child_frame_id" value="base_link"/>
  <param name="global_position/tf/send" value="false"/>
</group>
```

### Step 5. 最关键的是 airframe / control allocation

目标文件：

```bash
/home/adminpc/PX4-Autopilot-v1.16.0/ROMFS/px4fmu_common/init.d-posix/airframes/10015_gazebo-classic_iris
```

这一步不能简单照抄 Gazebo 模型里的 rotor pose。

这次最终稳定可用的一组 control allocation 参数是：

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

这一段非常重要，因为第一次迁移失败的核心坑就在这里：

- Gazebo 模型里的 `y`
- 不能直接原封不动抄进 PX4 `v1.16.0` 的 control allocation

PX4 这一侧按自己的坐标语义解释参数，尤其 `PY` 要按 PX4 这边的约定来。

## 七、当前机体模型和参数文件到底怎么分工

这是最容易让后面接手的人搞混的地方。

### 1. 当前动力学参数主文件

项目侧主记录文件是：

```bash
/home/adminpc/catkin_ws/iris.sdf.jinja
```

这里保存的是当前定版的机体参数检查点。

### 2. 当前 Gazebo 运行时实际加载的文件

真正运行时生效的不是上面这份 catkin 文件，而是 PX4 `v1.16.0` 树里的：

```bash
/home/adminpc/PX4-Autopilot-v1.16.0/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris/iris.sdf.jinja
/home/adminpc/PX4-Autopilot-v1.16.0/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris/iris.sdf
/home/adminpc/PX4-Autopilot-v1.16.0/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris_depth_camera/iris_depth_camera.sdf
```

换句话说：

- `catkin_ws/iris.sdf.jinja` 更像项目侧记录和主检查点
- PX4 `v1.16.0` 树里的模型文件才是 Gazebo 运行时真正吃到的版本

如果 README 不把这点写清楚，后面最容易出现的误判就是：

- “我明明改了文件，为什么 Gazebo 没变”

## 八、这次定版的关键参数值

### 1. 机体惯量和质量

当前关键值：

```xml
<mass>0.70</mass>
<ixx>0.003164</ixx>
<iyy>0.003164</iyy>
<izz>0.006044</izz>
```

### 2. 旋翼几何

当前关键值：

```text
rotor arm radius = 0.0884
rotor collision radius = 0.0635
```

### 3. 电机模型

当前关键值：

```xml
<timeConstantUp>0.0081</timeConstantUp>
<timeConstantDown>0.0081</timeConstantDown>
<maxRotVelocity>2237.54</maxRotVelocity>
<motorConstant>1.815e-06</motorConstant>
<momentConstant>0.015652892561983472</momentConstant>
```

### 4. 控制通道映射

当前关键值：

```xml
<input_scaling>1913.76</input_scaling>
<zero_position_armed>323.78</zero_position_armed>
```

## 九、深度相机这一侧到底保留了什么

当前 depth camera 的真实挂点没有动，仍然在：

```bash
/home/adminpc/PX4-Autopilot-v1.16.0/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris_depth_camera/iris_depth_camera.sdf
```

关键 pose 仍然是：

```xml
<pose>0.1 0 0 0 0 0</pose>
```

这一点必须写进 README，因为这是和规划、点云、相机前向视场强相关的固定约束。

## 十、启动脚本和环境脚本必须怎么改

这一部分建议写成“如果你已经有一套旧 catkin 工作区，直接把当前写好的脚本替换过去”。

### 1. 直接复制这些脚本到 catkin 工作区

```bash
/home/adminpc/catkin_ws/agent_env.sh
/home/adminpc/catkin_ws/start_sim_agent.sh
/home/adminpc/catkin_ws/start_sim.sh
/home/adminpc/catkin_ws/stop_sim.sh
/home/adminpc/catkin_ws/check_env.sh
```

这些脚本里已经处理好了：

1. 优先使用 `/home/adminpc/PX4-Autopilot-v1.16.0`
2. 新 Gazebo Classic 路径
3. GUI 可见四阶段启动
4. 远端 agent 启动
5. `--only-arm` / `--arm-offboard`
6. 清理逻辑

### 2. planner launch 也要一起替换

```bash
/home/adminpc/catkin_ws/src/ego-planner/src/planner/plan_manage/launch/px4_single.launch
```

当前版本支持：

```xml
<arg name="enable_rviz" default="true"/>
```

这样远端启动时可以：

```bash
roslaunch ego_planner px4_single.launch enable_rviz:=false
```

### 3. `.bashrc` 也要顺手更新

目标是：

1. 如果新树存在，默认指向 `PX4-Autopilot-v1.16.0`
2. 如果新树不存在，再回退到旧树
3. 新树时使用：
   - `Tools/simulation/gazebo-classic/setup_gazebo.bash`

## 十一、如果不想手工一行一行改，哪些文件可以直接复制

这是 README 里最有用的一节。

### PX4 树内可直接复制覆盖的文件

如果你已经拿到了当前可运行环境中的文件，可以直接复制：

```bash
cp <当前可运行环境>/launch/mavros_posix_sitl.launch \
  /home/adminpc/PX4-Autopilot-v1.16.0/launch/mavros_posix_sitl.launch

cp <当前可运行环境>/ROMFS/px4fmu_common/init.d-posix/airframes/10015_gazebo-classic_iris \
  /home/adminpc/PX4-Autopilot-v1.16.0/ROMFS/px4fmu_common/init.d-posix/airframes/10015_gazebo-classic_iris

cp <当前可运行环境>/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris/iris.sdf.jinja \
  /home/adminpc/PX4-Autopilot-v1.16.0/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris/iris.sdf.jinja

cp <当前可运行环境>/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris_depth_camera/iris_depth_camera.sdf \
  /home/adminpc/PX4-Autopilot-v1.16.0/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris_depth_camera/iris_depth_camera.sdf

cp <当前可运行环境>/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris_depth_camera/model.config \
  /home/adminpc/PX4-Autopilot-v1.16.0/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris_depth_camera/model.config
```

### catkin 工作区可直接复制覆盖的文件

```bash
cp <当前可运行环境>/catkin_ws/agent_env.sh /home/adminpc/catkin_ws/agent_env.sh
cp <当前可运行环境>/catkin_ws/start_sim_agent.sh /home/adminpc/catkin_ws/start_sim_agent.sh
cp <当前可运行环境>/catkin_ws/start_sim.sh /home/adminpc/catkin_ws/start_sim.sh
cp <当前可运行环境>/catkin_ws/stop_sim.sh /home/adminpc/catkin_ws/stop_sim.sh
cp <当前可运行环境>/catkin_ws/check_env.sh /home/adminpc/catkin_ws/check_env.sh
cp <当前可运行环境>/catkin_ws/src/ego-planner/src/planner/plan_manage/launch/px4_single.launch \
  /home/adminpc/catkin_ws/src/ego-planner/src/planner/plan_manage/launch/px4_single.launch
```

复制完成后记得：

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
  /home/adminpc/catkin_ws/stop_sim.sh \
  /home/adminpc/catkin_ws/check_env.sh

chmod +x \
  /home/adminpc/catkin_ws/agent_env.sh \
  /home/adminpc/catkin_ws/start_sim_agent.sh \
  /home/adminpc/catkin_ws/start_sim.sh \
  /home/adminpc/catkin_ws/stop_sim.sh \
  /home/adminpc/catkin_ws/check_env.sh
```

## 十二、构建时的两个真实坑

### 坑 1：shallow clone 历史不够

现象：

- `px_update_git_header.py`
- 或 NuttX 相关版本头生成报错

处理：

- 回去执行 `git fetch --tags --unshallow || git fetch --tags`

### 坑 2：手工生成过 `iris.sdf`

现象：

- 构建时报 `generation would overwrite changes to iris.sdf`

原因：

- 你把生成物 `iris.sdf` 当成长期编辑文件了

处理：

```bash
rm -f /home/adminpc/PX4-Autopilot-v1.16.0/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris/iris.sdf
```

然后重新构建。

## 十三、构建命令

```bash
cd /home/adminpc/PX4-Autopilot-v1.16.0
DONT_RUN=1 make px4_sitl gazebo-classic_iris_depth_camera -j"$(nproc)"
```

## 十四、验证应该怎么分层做

不要一上来就跑完整 planner 主链。

推荐按三层验证：

### 第一层：最小无 planner 验证

目标：

- 只看 PX4 + Gazebo + MAVROS 能不能稳定飞起来

这样可以先确认：

- 问题是不是 planner 引入的

### 第二层：agent 主链验证

```bash
cd /home/adminpc/catkin_ws
./stop_sim.sh
./start_sim_agent.sh
./start_sim_agent.sh --only-arm
```

检查：

- `/mavros/state`
- `/cloud_corrected`
- `/planning/pos_cmd`
- `/waypoint_generator/waypoints`
- `/depth_camera/points`

### 第三层：GUI 主链验证

```bash
cd /home/adminpc/catkin_ws
./stop_sim.sh
./start_sim.sh
```

预期会看到四阶段反馈：

```text
正在启动魔改自主导航仿真系统...
阶段 1/4: 启动 PX4 + Gazebo + MAVROS
阶段 2/4: 自动起飞并保持到 2.5m
阶段 3/4: 高度稳定，启动障碍物/桥接/点云/规划器
阶段 4/4: 规划链路已就绪，启动任务管理器并交接控制
自动起飞保持器已释放，现由 bridge/planner 接管。
```

## 十五、Gazebo 外壳这块后来又改了什么

这部分属于迁移完成后的“视觉重构补丁”，也应该顺手写到 README 里。

当前外壳视觉已经不是 stock Iris 外壳。

实际改动位置是：

```bash
/home/adminpc/PX4-Autopilot-v1.16.0/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris/iris.sdf.jinja
/home/adminpc/PX4-Autopilot-v1.16.0/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris/iris.sdf
/home/adminpc/PX4-Autopilot-v1.16.0/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris_depth_camera/iris_depth_camera.sdf
/home/adminpc/catkin_ws/iris.sdf.jinja
```

这次外壳重构只改了 `visual`，没有改这些东西：

- `collision`
- `inertial`
- `mass`
- `inertia`
- rotor `pose`
- joint
- depth camera 真实挂点 pose

也就是说：

- 它只影响“看起来像什么”
- 不直接改变物理碰撞体
- 不直接改变动力学

视觉上做的事情主要包括：

- 放大中心机身和上层堆叠
- 加粗加长机臂
- 加大 motor pod
- 让机头更前伸
- 补出前部相机安装桥和护架
- 把深度相机外观做得更像相机模组

这一段如果 README 不写，后面别人会误以为“换壳”会改变物理碰撞。

## 十六、当前最容易踩的坑

### 1. 旧 `Tools/sitl_gazebo` 路径不能继续写死

到了 `v1.16.0`，Gazebo Classic 已经在：

```bash
Tools/simulation/gazebo-classic/sitl_gazebo-classic
```

### 2. `catkin_ws/iris.sdf.jinja` 不是运行时唯一来源

它是项目侧检查点，不是 Gazebo 唯一运行时入口。

真正生效的，是 PX4 `v1.16.0` 树里的模型文件。

### 3. GUI tab 必须继续用 `bash -ic`

如果退回 `bash -c`，很容易重新遇到：

- ROS 环境没加载
- `rospy` 导入失败

### 4. 从 Windows 写入的脚本一定要转 LF

否则会出现：

- `ROS_PACKAGE_PATH` 污染
- `rospack` 查包异常
- shell 脚本行为奇怪

### 5. 不要把 `iris.sdf` 当长期手工编辑文件

长期应该维护：

```bash
iris.sdf.jinja
```

不是生成物：

```bash
iris.sdf
```

## 十七、当前日常使用入口

### GUI 可见桌面流程

```bash
cd /home/adminpc/catkin_ws
./stop_sim.sh
./start_sim.sh
```

### 远端 / agent 流程

```bash
cd /home/adminpc/catkin_ws
./stop_sim.sh
./start_sim_agent.sh
./start_sim_agent.sh --only-arm
```

### 环境检查

```bash
cd /home/adminpc/catkin_ws
./check_env.sh
```

## 十八、一句话结论

这次公开 README 最应该表达清楚的不是“版本号从旧版换成了 `1.16.0`”，而是：

1. 旧 GitHub 环境是起点
2. 当前采用“双 PX4 树并存”的迁移方式
3. 关键是把机体模型、深度相机、control allocation、MAVROS launch 和 catkin 启动链一起迁到 `v1.16.0`
4. 运行时真正生效的 Gazebo 模型在 PX4 `v1.16.0` 树里
5. Gazebo 外壳后续做过一轮 `visual-only` 重构，但没有改动力学和碰撞
6. 迁移成功要靠分层验证，而不是直接赌完整 planner 主链
