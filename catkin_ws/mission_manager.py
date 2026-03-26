#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
[Mission Manager - Final Version]
功能：自主导航任务调度器
职责：发布航点、判断到达、发送存活心跳
"""

import rospy
import math
from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import Path
from mavros_msgs.msg import State
from std_msgs.msg import Header

# ================= 任务配置 =================
# 航点列表 [x, y, z] (World Frame)
WAYPOINTS = [
    [  12.0,   0.0,  1.0],
    [   0.0,  12.0,  1.0],
    [ -12.0,   0.0,  1.0],
    [   0.0, -12.0,  1.0],
    [  12.0,   0.0,  1.0],
    [ -12.0,   0.0,  1.0],    
    [   0.0,   0.0,  1.0]
]
ARRIVAL_THRESHOLD = 0.4   # 到达判定半径 (m)
WAYPOINT_TIMEOUT = 30.0   # 单点超时时间 (s)
# ===========================================

class MissionManager:
    def __init__(self):
        rospy.init_node('mission_manager', anonymous=True)
        
        # --- 发布 ---
        # 1. 给 Ego-Planner 发目标
        self.traj_pub = rospy.Publisher("/waypoint_generator/waypoints", Path, queue_size=10)
        # 2. 给 Bridge 发心跳
        self.heartbeat_pub = rospy.Publisher("/mission/heartbeat", Header, queue_size=1)
        
        # --- 订阅 ---
        self.current_state = State()
        rospy.Subscriber("/mavros/state", State, self.state_cb)
        
        self.local_pose = None
        rospy.Subscriber("/mavros/local_position/pose", PoseStamped, self.pose_cb)
        
        rospy.loginfo(">>> Mission Manager Initialized <<<")

    def state_cb(self, msg): self.current_state = msg
    def pose_cb(self, msg): self.local_pose = msg

    def check_arrival(self, target_point):
        """计算当前位置与目标的欧氏距离"""
        if self.local_pose is None: return False, 999.9
        
        dx = self.local_pose.pose.position.x - target_point[0]
        dy = self.local_pose.pose.position.y - target_point[1]
        dz = self.local_pose.pose.position.z - target_point[2]
        
        dist = math.sqrt(dx**2 + dy**2 + dz**2)
        return dist < ARRIVAL_THRESHOLD, dist

    def send_goal(self, point):
        """封装并发送目标点"""
        path_msg = Path()
        path_msg.header.frame_id = "map" # 确保与 Launch 文件一致
        path_msg.header.stamp = rospy.Time.now()
        
        pose = PoseStamped()
        pose.header = path_msg.header
        pose.pose.position.x = point[0]
        pose.pose.position.y = point[1]
        pose.pose.position.z = point[2]
        pose.pose.orientation.w = 1.0 # 默认姿态
        
        path_msg.poses.append(pose)
        self.traj_pub.publish(path_msg)

    def run(self):
        # 1. 启动等待
        rospy.loginfo("Waiting for OFFBOARD & ARMED...")
        while not rospy.is_shutdown():
            # 持续发送心跳
            self.heartbeat_pub.publish(Header(stamp=rospy.Time.now()))
            
            if self.current_state.mode == "OFFBOARD" and self.current_state.armed:
                rospy.loginfo(">>> Drone Ready! Starting Mission in 3s... <<<")
                rospy.sleep(3.0)
                break
            rospy.sleep(0.1)

        # 2. 执行任务
        for i, wp in enumerate(WAYPOINTS):
            if rospy.is_shutdown(): break
            
            rospy.loginfo(f"[Mission] Go to WP{i+1}: {wp}")
            self.send_goal(wp)
            
            start_time = rospy.Time.now()
            rate = rospy.Rate(10) # 10Hz 检测循环
            
            while not rospy.is_shutdown():
                # [关键] 每一帧都广播心跳
                self.heartbeat_pub.publish(Header(stamp=rospy.Time.now()))
                
                # 检查到达
                arrived, dist = self.check_arrival(wp)
                if arrived:
                    rospy.loginfo(f"[Mission] Arrived WP{i+1} (Err: {dist:.2f}m)")
                    break
                
                # 超时保护
                if (rospy.Time.now() - start_time).to_sec() > WAYPOINT_TIMEOUT:
                    rospy.logwarn(f"[Mission] Timeout WP{i+1} - Skipping")
                    break
                
                # 补发指令 (防止丢包)
                if (rospy.Time.now() - start_time).to_sec() % 2.0 < 0.1:
                     self.send_goal(wp)
                
                rate.sleep()
            
            # 悬停观察 2秒
            for _ in range(20): 
                self.heartbeat_pub.publish(Header(stamp=rospy.Time.now()))
                rospy.sleep(0.1)

        rospy.loginfo(">>> MISSION FINISHED <<<")
        # 脚本退出后心跳停止 -> Bridge 将在 1秒后自动悬停

if __name__ == '__main__':
    try:
        MissionManager().run()
    except rospy.ROSInterruptException:
        pass

