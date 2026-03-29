#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
[PX4 Bridge]
功能：Ego-Planner 与 PX4 之间的安全中间件
职责：轨迹平滑、安全限幅、异常接管、悬停锁存
"""

import math
from enum import Enum, auto

import rospy
from geometry_msgs.msg import Point, PoseStamped, Vector3
from mavros_msgs.msg import PositionTarget, State
from quadrotor_msgs.msg import PositionCommand
from std_msgs.msg import Bool, Header


class Config:
    MIN_HEIGHT = 0.5
    MAX_SPEED_LIMIT = 1.5
    PLANNER_TIMEOUT = 0.5
    MISSION_TIMEOUT = 1.0
    ENABLE_SMOOTHING = True
    SMOOTH_ALPHA = 0.6
    REQUIRE_MISSION_HEARTBEAT = True
    ZERO_ACCEL_WHEN_SHAPING = False

    @classmethod
    def load_from_ros(cls):
        cls.MIN_HEIGHT = float(rospy.get_param("~min_height", cls.MIN_HEIGHT))
        cls.MAX_SPEED_LIMIT = float(rospy.get_param("~max_speed_limit", cls.MAX_SPEED_LIMIT))
        cls.PLANNER_TIMEOUT = float(rospy.get_param("~planner_timeout", cls.PLANNER_TIMEOUT))
        cls.MISSION_TIMEOUT = float(rospy.get_param("~mission_timeout", cls.MISSION_TIMEOUT))
        cls.ENABLE_SMOOTHING = bool(rospy.get_param("~enable_smoothing", cls.ENABLE_SMOOTHING))
        cls.SMOOTH_ALPHA = float(rospy.get_param("~smooth_alpha", cls.SMOOTH_ALPHA))
        cls.REQUIRE_MISSION_HEARTBEAT = bool(
            rospy.get_param("~require_mission_heartbeat", cls.REQUIRE_MISSION_HEARTBEAT)
        )
        cls.ZERO_ACCEL_WHEN_SHAPING = bool(
            rospy.get_param("~zero_accel_when_shaping", cls.ZERO_ACCEL_WHEN_SHAPING)
        )


class FlightState(Enum):
    WAITING_FOR_CONNECTION = auto()
    WAITING_FOR_OFFBOARD = auto()
    HOVERING = auto()
    TRACKING = auto()


def copy_vector3(vec) -> Vector3:
    return Vector3(x=vec.x, y=vec.y, z=vec.z)


def zero_vector3() -> Vector3:
    return Vector3(x=0.0, y=0.0, z=0.0)


class PX4Bridge:
    def __init__(self):
        rospy.init_node("px4_bridge_machine")
        Config.load_from_ros()

        self.state = FlightState.WAITING_FOR_CONNECTION
        self.last_state = None
        self.force_stop_active = False
        self.hover_pose = None

        self.current_state = State()
        self.local_pose = PoseStamped()
        self.planner_cmd = None
        self.last_vel_smooth = None

        self.got_planner_cmd = False
        self.last_planner_time = rospy.Time(0)
        self.last_mission_heartbeat = rospy.Time(0)

        rospy.Subscriber("/mavros/state", State, self.state_cb)
        rospy.Subscriber("/mavros/local_position/pose", PoseStamped, self.pose_cb)
        rospy.Subscriber("/planning/pos_cmd", PositionCommand, self.planner_cb)
        rospy.Subscriber("/bridge/force_stop", Bool, self.force_stop_cb)
        rospy.Subscriber("/mission/heartbeat", Header, self.heartbeat_cb)

        self.raw_pub = rospy.Publisher("/mavros/setpoint_raw/local", PositionTarget, queue_size=1)
        self.rate = rospy.Rate(30.0)

        rospy.loginfo(
            ">>> PX4 Bridge Ready | heartbeat=%s smooth=%s alpha=%.2f speed_limit=%.2f zero_accel=%s <<<",
            Config.REQUIRE_MISSION_HEARTBEAT,
            Config.ENABLE_SMOOTHING,
            Config.SMOOTH_ALPHA,
            Config.MAX_SPEED_LIMIT,
            Config.ZERO_ACCEL_WHEN_SHAPING,
        )

    def state_cb(self, msg):
        self.current_state = msg

    def pose_cb(self, msg):
        self.local_pose = msg

    def planner_cb(self, msg):
        self.planner_cmd = msg
        self.got_planner_cmd = True
        self.last_planner_time = rospy.Time.now()

    def heartbeat_cb(self, _msg):
        self.last_mission_heartbeat = rospy.Time.now()

    def force_stop_cb(self, msg):
        if msg.data:
            rospy.logwarn(">>> EMERGENCY STOP ACTIVATED <<<")
        self.force_stop_active = msg.data

    def smooth_velocity(self, raw_vel: Vector3) -> Vector3:
        current = copy_vector3(raw_vel)
        if not Config.ENABLE_SMOOTHING:
            self.last_vel_smooth = current
            return current

        if self.last_vel_smooth is None:
            self.last_vel_smooth = current
            return current

        alpha = Config.SMOOTH_ALPHA
        smoothed = Vector3(
            x=alpha * current.x + (1.0 - alpha) * self.last_vel_smooth.x,
            y=alpha * current.y + (1.0 - alpha) * self.last_vel_smooth.y,
            z=alpha * current.z + (1.0 - alpha) * self.last_vel_smooth.z,
        )
        self.last_vel_smooth = smoothed
        return smoothed

    def apply_speed_limit(self, raw_vel: Vector3):
        limited = copy_vector3(raw_vel)
        vel_mag = math.sqrt(limited.x**2 + limited.y**2 + limited.z**2)
        clipped = False
        scale = 1.0

        if vel_mag > Config.MAX_SPEED_LIMIT > 0.0:
            scale = Config.MAX_SPEED_LIMIT / vel_mag
            limited.x *= scale
            limited.y *= scale
            limited.z *= scale
            clipped = True

        return limited, clipped, scale

    def get_current_yaw(self):
        q = self.local_pose.pose.orientation
        return math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))

    def construct_hover_target(self):
        target = PositionTarget()
        target.header.stamp = rospy.Time.now()
        target.coordinate_frame = PositionTarget.FRAME_LOCAL_NED
        target.type_mask = 0b100111111000

        if self.hover_pose is None:
            target.position = self.local_pose.pose.position
        else:
            target.position = self.hover_pose

        target.yaw = self.get_current_yaw()
        return target

    def construct_tracking_target(self):
        target = PositionTarget()
        target.header.stamp = rospy.Time.now()
        target.coordinate_frame = PositionTarget.FRAME_LOCAL_NED
        target.type_mask = PositionTarget.IGNORE_YAW_RATE

        target.position.x = self.planner_cmd.position.x
        target.position.y = self.planner_cmd.position.y
        target.position.z = max(self.planner_cmd.position.z, Config.MIN_HEIGHT)

        requested_velocity = copy_vector3(self.planner_cmd.velocity)
        limited_velocity, clipped, accel_scale = self.apply_speed_limit(requested_velocity)
        shaped_velocity = self.smooth_velocity(limited_velocity)
        target.velocity = shaped_velocity

        velocity_modified = clipped or any(
            abs(getattr(shaped_velocity, axis) - getattr(requested_velocity, axis)) > 1e-3
            for axis in ("x", "y", "z")
        )

        if velocity_modified and Config.ZERO_ACCEL_WHEN_SHAPING:
            target.acceleration_or_force = zero_vector3()
        else:
            accel = copy_vector3(self.planner_cmd.acceleration)
            if clipped and accel_scale < 1.0:
                accel.x *= accel_scale
                accel.y *= accel_scale
                accel.z *= accel_scale
            target.acceleration_or_force = accel

        target.yaw = self.planner_cmd.yaw
        return target

    def update_state_machine(self):
        if not self.current_state.connected:
            self.state = FlightState.WAITING_FOR_CONNECTION
            return self.construct_hover_target()

        if self.current_state.mode != "OFFBOARD":
            self.state = FlightState.WAITING_FOR_OFFBOARD
            self.hover_pose = None
            self.last_vel_smooth = None
            return self.construct_hover_target()

        if self.force_stop_active:
            self.state = FlightState.HOVERING
        else:
            planner_alive = (rospy.Time.now() - self.last_planner_time).to_sec() < Config.PLANNER_TIMEOUT
            mission_alive = True
            if Config.REQUIRE_MISSION_HEARTBEAT:
                mission_alive = (rospy.Time.now() - self.last_mission_heartbeat).to_sec() < Config.MISSION_TIMEOUT

            if self.got_planner_cmd and planner_alive and mission_alive:
                self.state = FlightState.TRACKING
            else:
                if not mission_alive and self.state == FlightState.TRACKING:
                    rospy.logwarn_throttle(1.0, "[Bridge] Mission Heartbeat Lost! Emergency Hover.")
                self.state = FlightState.HOVERING

        if self.state == FlightState.HOVERING:
            if self.last_state != FlightState.HOVERING or self.hover_pose is None:
                curr_p = self.local_pose.pose.position
                self.hover_pose = Point(x=curr_p.x, y=curr_p.y, z=max(curr_p.z, Config.MIN_HEIGHT))
                self.last_vel_smooth = None
                rospy.loginfo(
                    "[Bridge] Position Locked at: x=%.2f, y=%.2f, z=%.2f",
                    self.hover_pose.x,
                    self.hover_pose.y,
                    self.hover_pose.z,
                )
        else:
            self.hover_pose = None

        if self.state == FlightState.TRACKING:
            return self.construct_tracking_target()
        return self.construct_hover_target()

    def run(self):
        while not rospy.is_shutdown():
            try:
                cmd = self.update_state_machine()
                self.raw_pub.publish(cmd)
                if self.state != self.last_state:
                    self.last_state = self.state
            except Exception as exc:
                rospy.logerr(f"Bridge Error: {exc}")
            self.rate.sleep()


if __name__ == "__main__":
    try:
        PX4Bridge().run()
    except rospy.ROSInterruptException:
        pass
