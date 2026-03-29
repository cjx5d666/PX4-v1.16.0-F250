#!/usr/bin/env python3

import math
import random

import rospy
from gazebo_msgs.srv import DeleteModel, SpawnModel
from geometry_msgs.msg import Pose


def create_cylinder_sdf(name, radius, height):
    return f"""
    <sdf version="1.6">
      <model name="{name}">
        <static>true</static>
        <link name="link">
          <collision name="collision">
            <geometry><cylinder><radius>{radius}</radius><length>{height}</length></cylinder></geometry>
          </collision>
          <visual name="visual">
            <geometry><cylinder><radius>{radius}</radius><length>{height}</length></cylinder></geometry>
            <material><ambient>0.1 0.1 0.1 1</ambient><diffuse>0.1 0.1 0.2 1</diffuse></material>
          </visual>
        </link>
      </model>
    </sdf>
    """


def distance_xy(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def delete_existing_obstacles(delete_model, prefix, max_candidates):
    for idx in range(max_candidates):
        model_name = f"{prefix}{idx}"
        try:
            delete_model(model_name)
        except rospy.ServiceException:
            pass


def sample_position(rng, range_x, range_y, safe_zone, min_spacing, placed_xy):
    for _ in range(500):
        x = rng.uniform(range_x[0], range_x[1])
        y = rng.uniform(range_y[0], range_y[1])
        if math.hypot(x, y) <= safe_zone:
            continue
        if any(distance_xy((x, y), existing) < min_spacing for existing in placed_xy):
            continue
        return x, y
    raise RuntimeError("Failed to sample a non-overlapping obstacle field")


def spawn_random_obstacles():
    rospy.init_node("obstacle_generator")

    count = int(rospy.get_param("~count", 10))
    range_x = list(rospy.get_param("~range_x", [-9.0, 9.0]))
    range_y = list(rospy.get_param("~range_y", [-9.0, 9.0]))
    safe_zone = float(rospy.get_param("~safe_zone", 3.0))
    min_spacing = float(rospy.get_param("~min_spacing", 1.8))
    name_prefix = rospy.get_param("~name_prefix", "random_obs_")
    max_candidates = int(rospy.get_param("~max_cleanup_candidates", max(50, count * 3)))
    seed = int(rospy.get_param("~seed", 250))

    rng = random.Random(seed)

    rospy.wait_for_service("/gazebo/spawn_sdf_model")
    rospy.wait_for_service("/gazebo/delete_model")
    spawn_model = rospy.ServiceProxy("/gazebo/spawn_sdf_model", SpawnModel)
    delete_model = rospy.ServiceProxy("/gazebo/delete_model", DeleteModel)

    delete_existing_obstacles(delete_model, name_prefix, max_candidates)

    rospy.loginfo(
        "Spawning %d deterministic obstacles | seed=%d safe_zone=%.2f min_spacing=%.2f",
        count,
        seed,
        safe_zone,
        min_spacing,
    )

    placed_xy = []
    for idx in range(count):
        obs_name = f"{name_prefix}{idx}"
        x, y = sample_position(rng, range_x, range_y, safe_zone, min_spacing, placed_xy)
        radius = rng.uniform(0.6, 0.8)
        height = rng.uniform(3.2, 4.0)

        pose = Pose()
        pose.position.x = x
        pose.position.y = y
        pose.position.z = height / 2.0

        sdf = create_cylinder_sdf(obs_name, radius, height)
        spawn_model(obs_name, sdf, "", pose, "world")
        placed_xy.append((x, y))

    rospy.loginfo("Obstacle field ready")


if __name__ == "__main__":
    try:
        spawn_random_obstacles()
    except rospy.ROSInterruptException:
        pass
