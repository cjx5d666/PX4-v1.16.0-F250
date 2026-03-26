#!/usr/bin/env python3
import rospy
import random
import math
from gazebo_msgs.srv import SpawnModel, DeleteModel
from geometry_msgs.msg import Pose, Point, Quaternion

def create_cylinder_sdf(name, radius, height):
    """生成简单的圆柱体 SDF 字符串"""
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

def spawn_random_obstacles(count=15, range_x=[-10, 10], range_y=[-10, 10], safe_zone=2.0):
    rospy.init_node('obstacle_generator')
    
    # 等待 Gazebo 服务
    rospy.wait_for_service('/gazebo/spawn_sdf_model')
    spawn_model = rospy.ServiceProxy('/gazebo/spawn_sdf_model', SpawnModel)
    
    print(f"--- 正在生成 {count} 个随机障碍物 ---")
    
    for i in range(count):
        obs_name = f"random_obs_{i}"
        
        # 随机位置，但避开无人机起始点 (0,0) 的安全区
        while True:
            x = random.uniform(range_x[0], range_x[1])
            y = random.uniform(range_y[0], range_y[1])
            if math.sqrt(x**2 + y**2) > safe_zone:
                break
        
        # 随机半径和高度
        radius = random.uniform(0.6, 0.8)
        height = random.uniform(3.2, 4.0)
        
        # 设置姿态 (地面中心点)
        pose = Pose()
        pose.position.x = x
        pose.position.y = y
        pose.position.z = height / 2.0  # 使底部对齐地面
        
        sdf = create_cylinder_sdf(obs_name, radius, height)
        
        try:
            spawn_model(obs_name, sdf, "", pose, "world")
        except rospy.ServiceException as e:
            print(f"Spawn service failed: {e}")

if __name__ == "__main__":
    # 配置：生成 n 个障碍物，范围在 nxn 米内，起始点 n 米内不生成
    spawn_random_obstacles(count=10, range_x=[-9, 9], range_y=[-9, 9], safe_zone=3.0)
    print("--- 生成完毕，开始你的避障表演 ---")
