#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
[Mission Manager]
功能：自主导航任务调度器
职责：发布航点、判断到达、发送存活心跳
"""

import math

import rospy
from geometry_msgs.msg import PoseStamped
from mavros_msgs.msg import State
from nav_msgs.msg import Path
from std_msgs.msg import Header


DEFAULT_WAYPOINTS = [
    [12.0, 0.0, 1.0],
    [0.0, 12.0, 1.0],
    [-12.0, 0.0, 1.0],
    [0.0, -12.0, 1.0],
    [12.0, 0.0, 1.0],
    [-12.0, 0.0, 1.0],
    [0.0, 0.0, 1.0],
]


class MissionManager:
    def __init__(self):
        rospy.init_node("mission_manager", anonymous=True)

        self.waypoints = self.load_waypoints()
        self.arrival_threshold = float(rospy.get_param("~arrival_threshold", 0.4))
        self.waypoint_timeout = float(rospy.get_param("~waypoint_timeout", 30.0))
        self.post_waypoint_hover_s = float(rospy.get_param("~post_waypoint_hover_s", 2.0))
        self.goal_resend_period = float(rospy.get_param("~goal_resend_period", 2.0))
        self.start_delay = float(rospy.get_param("~start_delay", 3.0))

        self.traj_pub = rospy.Publisher("/waypoint_generator/waypoints", Path, queue_size=10)
        self.heartbeat_pub = rospy.Publisher("/mission/heartbeat", Header, queue_size=1)

        self.current_state = State()
        self.local_pose = None
        rospy.Subscriber("/mavros/state", State, self.state_cb)
        rospy.Subscriber("/mavros/local_position/pose", PoseStamped, self.pose_cb)

        rospy.loginfo(">>> Mission Manager Initialized | waypoints=%d <<<", len(self.waypoints))

    def state_cb(self, msg):
        self.current_state = msg

    def pose_cb(self, msg):
        self.local_pose = msg

    def load_waypoints(self):
        raw_waypoints = rospy.get_param("~waypoints", DEFAULT_WAYPOINTS)
        parsed = []
        for idx, waypoint in enumerate(raw_waypoints):
            if len(waypoint) != 3:
                raise ValueError(f"Waypoint {idx} must contain exactly 3 values")
            parsed.append([float(waypoint[0]), float(waypoint[1]), float(waypoint[2])])
        return parsed

    def check_arrival(self, target_point):
        if self.local_pose is None:
            return False, 999.9

        dx = self.local_pose.pose.position.x - target_point[0]
        dy = self.local_pose.pose.position.y - target_point[1]
        dz = self.local_pose.pose.position.z - target_point[2]

        dist = math.sqrt(dx**2 + dy**2 + dz**2)
        return dist < self.arrival_threshold, dist

    def send_goal(self, point):
        path_msg = Path()
        path_msg.header.frame_id = "map"
        path_msg.header.stamp = rospy.Time.now()

        pose = PoseStamped()
        pose.header = path_msg.header
        pose.pose.position.x = point[0]
        pose.pose.position.y = point[1]
        pose.pose.position.z = point[2]
        pose.pose.orientation.w = 1.0

        path_msg.poses.append(pose)
        self.traj_pub.publish(path_msg)

    def publish_heartbeat(self):
        self.heartbeat_pub.publish(Header(stamp=rospy.Time.now()))

    def run(self):
        rospy.loginfo("Waiting for OFFBOARD & ARMED...")
        while not rospy.is_shutdown():
            self.publish_heartbeat()

            if self.current_state.mode == "OFFBOARD" and self.current_state.armed:
                rospy.loginfo(">>> Drone Ready! Starting Mission in %.1fs... <<<", self.start_delay)
                rospy.sleep(self.start_delay)
                break
            rospy.sleep(0.1)

        for idx, waypoint in enumerate(self.waypoints):
            if rospy.is_shutdown():
                break

            rospy.loginfo("[Mission] Go to WP%d: %s", idx + 1, waypoint)
            self.send_goal(waypoint)

            start_time = rospy.Time.now()
            last_goal_sent = rospy.Time(0)
            rate = rospy.Rate(10)

            while not rospy.is_shutdown():
                self.publish_heartbeat()

                arrived, dist = self.check_arrival(waypoint)
                if arrived:
                    rospy.loginfo("[Mission] Arrived WP%d (Err: %.2fm)", idx + 1, dist)
                    break

                if (rospy.Time.now() - start_time).to_sec() > self.waypoint_timeout:
                    rospy.logwarn("[Mission] Timeout WP%d - Skipping", idx + 1)
                    break

                if (
                    last_goal_sent == rospy.Time(0)
                    or (rospy.Time.now() - last_goal_sent).to_sec() >= self.goal_resend_period
                ):
                    self.send_goal(waypoint)
                    last_goal_sent = rospy.Time.now()

                rate.sleep()

            hover_iterations = max(0, int(round(self.post_waypoint_hover_s / 0.1)))
            for _ in range(hover_iterations):
                self.publish_heartbeat()
                rospy.sleep(0.1)

        rospy.loginfo(">>> MISSION FINISHED <<<")


if __name__ == "__main__":
    try:
        MissionManager().run()
    except rospy.ROSInterruptException:
        pass
