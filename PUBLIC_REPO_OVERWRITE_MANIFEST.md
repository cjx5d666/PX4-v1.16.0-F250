# Public Repo Overwrite Manifest

This file lists the current intended public-package baseline for:

- `cjx5d666/PX4-v1.16.0-F250`

Use this when you want to fully refresh the public repo from the current clean
local staging state instead of patching it piecemeal.

## Overwrite Rule

Treat the current `github_upload_staging/` tree as the source of truth.

Recommended public-repo action:

1. replace the public `README.md` with this staging `README.md`
2. replace the public `px4_patch/` tree with this staging `px4_patch/`
3. replace the public `catkin_ws/` tree with this staging `catkin_ws/`
4. replace the public `tracking/` tree with this staging `tracking/`
5. do not upload local-only continuity files such as:
   - `memory/`
   - `handoffs/`
   - `reports/`
   - `__remote_staging/`

## Current Intended Public Tree

### Top level

- `PUBLIC_REPO_OVERWRITE_MANIFEST.md`
- `README.md`
- `px4_patch/`
- `catkin_ws/`
- `tracking/`

### `px4_patch/`

- `px4_patch/launch/mavros_posix_sitl.launch`
- `px4_patch/ROMFS/px4fmu_common/init.d-posix/airframes/10015_gazebo-classic_iris`
- `px4_patch/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris/iris.sdf.jinja`
- `px4_patch/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris_depth_camera/iris_depth_camera.sdf`
- `px4_patch/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris_depth_camera/model.config`

### `catkin_ws/`

- `catkin_ws/agent_env.sh`
- `catkin_ws/check_env.sh`
- `catkin_ws/fix_cloud.py`
- `catkin_ws/guest_gnome_windowctl.py`
- `catkin_ws/mission_manager.py`
- `catkin_ws/obstacle_manager.py`
- `catkin_ws/planner_trace_runner.py`
- `catkin_ws/px4_bridge.py`
- `catkin_ws/run_planner_trace.sh`
- `catkin_ws/start_sim_agent.sh`
- `catkin_ws/start_sim.sh`
- `catkin_ws/stop_sim.sh`
- `catkin_ws/src/ego-planner/src/planner/plan_manage/launch/advanced_param_px4.xml`
- `catkin_ws/src/ego-planner/src/planner/plan_manage/launch/default.rviz`
- `catkin_ws/src/ego-planner/src/planner/plan_manage/launch/px4_single.launch`

### `tracking/`

- `tracking/run_tracking_suite.sh`
- `tracking/start_tracking_stack.sh`
- `tracking/tracking_analysis.py`
- `tracking/tracking_test_runner.py`

## Notes

- `run_planner_trace.sh` and `planner_trace_runner.py` are now part of the
  public baseline and should no longer be omitted.
- `advanced_param_px4.xml` is part of the public baseline and should no longer
  remain implicit.
- The public README should describe both:
  - the `Ego-Planner` task line
  - the fixed-trajectory tracking line
- Do not upload `__pycache__`, `.pyc`, local logs, or local experiment result
  folders as part of the public refresh.
- Keeping this manifest file in the public repo is acceptable; it is a
  maintainer-side refresh checklist and does not affect runtime behavior.
