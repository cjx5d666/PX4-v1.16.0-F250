#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
[PX4 Bridge - Final Version]
功能：Ego-Planner 与 PX4 之间的安全中间件
职责：轨迹平滑、安全限幅、异常接管、悬停锁存
"""

import rospy
import math
from enum import Enum, auto
from quadrotor_msgs.msg import PositionCommand
from geometry_msgs.msg import PoseStamped
from mavros_msgs.msg import PositionTarget, State
from std_msgs.msg import Bool, Header

# ======================= 参数配置 =======================
class Config:
    # --- 安全参数 ---
    MIN_HEIGHT = 0.5            # [安全] 最低飞行高度 (m)
    MAX_SPEED_LIMIT = 1.5       # [安全] 物理最大速度 (m/s)
    PLANNER_TIMEOUT = 0.5       # [监控] Planner 数据超时时间
    MISSION_TIMEOUT = 1.0       # [监控] Mission 心跳超时时间 (关键安全特性)
    
    # --- 平滑参数 ---
    ENABLE_SMOOTHING = True     # 是否开启速度平滑
    SMOOTH_ALPHA = 0.6          # 滤波系数: 0.1(柔) ~ 1.0(刚)
    
    # --- 调试 ---
    # 如果想脱离 Mission 脚本单独用 Rviz 点目标，设为 False
    REQUIRE_MISSION_HEARTBEAT = True 
# =======================================================

class FlightState(Enum):
    WAITING_FOR_CONNECTION = auto()
    WAITING_FOR_OFFBOARD = auto()
    HOVERING = auto()           # 稳态悬停 (位置锁存)
    TRACKING = auto()           # 轨迹追踪

class PX4Bridge:
    def __init__(self):
        rospy.init_node('px4_bridge_machine')
        
        # --- 状态量 ---
        self.state = FlightState.WAITING_FOR_CONNECTION
        self.last_state = None
        self.force_stop_active = False
        
        # --- 悬停锚点 (解决 Offboard 悬停晃动) ---
        self.hover_pose = None 
        
        # --- 数据缓存 ---
        self.current_state = State()
        self.local_pose = PoseStamped()
        self.planner_cmd = None
        self.last_vel_smooth = None
        
        # --- 计时器 ---
        self.got_planner_cmd = False
        self.last_planner_time = rospy.Time(0)
        self.last_mission_heartbeat = rospy.Time(0)

        # --- 订阅 ---
        rospy.Subscriber("/mavros/state", State, self.state_cb)
        rospy.Subscriber("/mavros/local_position/pose", PoseStamped, self.pose_cb)
        rospy.Subscriber("/planning/pos_cmd", PositionCommand, self.planner_cb)
        rospy.Subscriber("/bridge/force_stop", Bool, self.force_stop_cb)
        rospy.Subscriber("/mission/heartbeat", Header, self.heartbeat_cb) # 监听上层存活状态

        # --- 发布 ---
        self.raw_pub = rospy.Publisher("/mavros/setpoint_raw/local", PositionTarget, queue_size=1)

        self.rate = rospy.Rate(30.0)
        rospy.loginfo(f">>> PX4 Bridge Ready | Heartbeat Check: {Config.REQUIRE_MISSION_HEARTBEAT} <<<")

    # ================= 回调函数 =================
    def state_cb(self, msg): self.current_state = msg
    def pose_cb(self, msg): self.local_pose = msg
    
    def planner_cb(self, msg):
        self.planner_cmd = msg
        self.got_planner_cmd = True
        self.last_planner_time = rospy.Time.now()
        
    def heartbeat_cb(self, msg):
        self.last_mission_heartbeat = rospy.Time.now()

    def force_stop_cb(self, msg):
        if msg.data: rospy.logwarn(">>> EMERGENCY STOP ACTIVATED <<<")
        self.force_stop_active = msg.data

    # ================= 辅助逻辑 =================
    def smooth_velocity(self, raw_vel):
        if not Config.ENABLE_SMOOTHING or self.last_vel_smooth is None:
            self.last_vel_smooth = raw_vel
            return raw_vel
        alpha = Config.SMOOTH_ALPHA
        self.last_vel_smooth.x = alpha * raw_vel.x + (1 - alpha) * self.last_vel_smooth.x
        self.last_vel_smooth.y = alpha * raw_vel.y + (1 - alpha) * self.last_vel_smooth.y
        self.last_vel_smooth.z = alpha * raw_vel.z + (1 - alpha) * self.last_vel_smooth.z
        return self.last_vel_smooth

    def get_current_yaw(self):
        q = self.local_pose.pose.orientation
        return math.atan2(2.0*(q.w*q.z + q.x*q.y), 1.0 - 2.0*(q.y*q.y + q.z*q.z))

    # ================= 指令构建 =================
    def construct_hover_target(self):
        """构建悬停指令 (使用锁存锚点，防止漂移)"""
        target = PositionTarget()
        target.header.stamp = rospy.Time.now()
        target.coordinate_frame = PositionTarget.FRAME_LOCAL_NED
        target.type_mask = 0b100111111000 # 仅控制位置 + Yaw
        
        if self.hover_pose is None:
            target.position = self.local_pose.pose.position
        else:
            target.position = self.hover_pose
            
        target.yaw = self.get_current_yaw()
        return target

    def construct_tracking_target(self):
        """构建追踪指令 (前馈控制)"""
        target = PositionTarget()
        target.header.stamp = rospy.Time.now()
        target.coordinate_frame = PositionTarget.FRAME_LOCAL_NED
        target.type_mask = PositionTarget.IGNORE_YAW_RATE
        
        # 1. 位置 (最低高度保护)
        target.position.x = self.planner_cmd.position.x
        target.position.y = self.planner_cmd.position.y
        target.position.z = max(self.planner_cmd.position.z, Config.MIN_HEIGHT)
        
        # 2. 速度 (限幅 + 平滑)
        raw_vel = self.planner_cmd.velocity
        vel_mag = math.sqrt(raw_vel.x**2 + raw_vel.y**2 + raw_vel.z**2)
        if vel_mag > Config.MAX_SPEED_LIMIT:
            scale = Config.MAX_SPEED_LIMIT / vel_mag
            raw_vel.x *= scale; raw_vel.y *= scale; raw_vel.z *= scale
            
        target.velocity = self.smooth_velocity(raw_vel)
        
        # 3. 加速度 (前馈)
        target.acceleration_or_force = self.planner_cmd.acceleration
        
        # 4. 偏航
        target.yaw = self.planner_cmd.yaw
        return target

    # ================= 主循环 =================
    def update_state_machine(self):
        # 1. 基础连接检查
        if not self.current_state.connected:
            self.state = FlightState.WAITING_FOR_CONNECTION
            return self.construct_hover_target()
        
        if self.current_state.mode != "OFFBOARD":
            self.state = FlightState.WAITING_FOR_OFFBOARD
            self.hover_pose = None # 切出 Offboard 清除锚点
            return self.construct_hover_target()

        # 2. 状态判定
        if self.force_stop_active:
            self.state = FlightState.HOVERING
        else:
            # 存活检查
            planner_alive = (rospy.Time.now() - self.last_planner_time).to_sec() < Config.PLANNER_TIMEOUT
            mission_alive = True
            if Config.REQUIRE_MISSION_HEARTBEAT:
                mission_alive = (rospy.Time.now() - self.last_mission_heartbeat).to_sec() < Config.MISSION_TIMEOUT
            
            # 只有 Planner 和 Mission 都存活才追踪
            if self.got_planner_cmd and planner_alive and mission_alive:
                self.state = FlightState.TRACKING
            else:
                if not mission_alive and self.state == FlightState.TRACKING:
                    rospy.logwarn_throttle(1, "[Bridge] Mission Heartbeat Lost! Emergency Hover.")
                self.state = FlightState.HOVERING

        # 3. 悬停锁存逻辑 (关键防抖)
        if self.state == FlightState.HOVERING:
            if self.last_state != FlightState.HOVERING or self.hover_pose is None:
                # 刚切入悬停 -> 显式记录当前位置，防止引用污染
                curr_p = self.local_pose.pose.position
                from geometry_msgs.msg import Point # 确保导入了Point
                self.hover_pose = Point(x=curr_p.x, y=curr_p.y, z=curr_p.z)
                
                # 自动修正悬停高度：如果当前太低，强制锁在安全高度
                self.hover_pose.z = max(self.hover_pose.z, Config.MIN_HEIGHT)
                
                self.last_vel_smooth = None
                rospy.loginfo(f"[Bridge] Position Locked at: x={self.hover_pose.x:.2f}, y={self.hover_pose.y:.2f}")
        else:
            self.hover_pose = None

        # 4. 输出
        if self.state == FlightState.TRACKING:
            return self.construct_tracking_target()
        else:
            return self.construct_hover_target()

    def run(self):
        while not rospy.is_shutdown():
            try:
                cmd = self.update_state_machine()
                self.raw_pub.publish(cmd)
                if self.state != self.last_state:
                    self.last_state = self.state
            except Exception as e:
                rospy.logerr(f"Bridge Error: {e}")
            self.rate.sleep()

if __name__ == "__main__":
    try:
        PX4Bridge().run()
    except rospy.ROSInterruptException:
        pass

