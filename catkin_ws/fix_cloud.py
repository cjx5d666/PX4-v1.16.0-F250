#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import rospy
import tf2_ros
import numpy as np
from sensor_msgs.msg import PointCloud2
import sensor_msgs.point_cloud2 as pc2
from tf.transformations import quaternion_matrix, translation_matrix, concatenate_matrices

class CloudFixer:
    def __init__(self):
        rospy.init_node('cloud_fixer_node')
        
        # --- 配置 ---
        self.target_frame = "map"  # 目标参考系
        
        # 1. 订阅原始深度相机点云
        # 设置 buff_size 防止大数据量导致的点云丢包或延迟
        self.sub = rospy.Subscriber(
            "/depth_camera/points", 
            PointCloud2, 
            self.callback, 
            queue_size=1, 
            buff_size=2**24
        )
        
        # 2. 发布转换后的点云
        self.pub = rospy.Publisher("/cloud_corrected", PointCloud2, queue_size=1)
        
        # 3. TF 监听
        self.tf_buffer = tf2_ros.Buffer()
        self.listener = tf2_ros.TransformListener(self.tf_buffer)
        
        rospy.loginfo(">>> CloudFixer: 全量坐标转换模式已启动 <<<")

    def callback(self, cloud_msg):
        try:
            # --- 1. 获取最新变换 (Map -> Camera) ---
            # 使用 rospy.Time(0) 获取最新可用变换，解决 TF 等待警告
            trans = self.tf_buffer.lookup_transform(
                self.target_frame, 
                cloud_msg.header.frame_id, 
                rospy.Time(0) 
            )
            
            # 提取平移和旋转
            t = [trans.transform.translation.x, 
                 trans.transform.translation.y, 
                 trans.transform.translation.z]
            q = [trans.transform.rotation.x, 
                 trans.transform.rotation.y, 
                 trans.transform.rotation.z, 
                 trans.transform.rotation.w]
            
            # 构造 4x4 变换矩阵
            mat_t = translation_matrix(t)
            mat_r = quaternion_matrix(q)
            mat_total = concatenate_matrices(mat_t, mat_r)

            # --- 2. 读取原始点云 (全量读取) ---
            # read_points 会自动处理 NaN 点
            points_gen = pc2.read_points(cloud_msg, field_names=("x", "y", "z"), skip_nans=True)
            P_cam = np.array(list(points_gen), dtype=np.float32)
            
            if P_cam.shape[0] == 0:
                return

            # --- 3. 坐标转换 ---
            # 转换为齐次坐标 (N, 4)
            ones = np.ones((P_cam.shape[0], 1))
            points_hom = np.hstack((P_cam, ones))
            
            # 矩阵运算: P_map = T * P_cam
            # 这里使用点积，注意转置关系
            P_map = np.dot(points_hom, mat_total.T)[:, :3]

            # --- 4. 发布结果 ---
            header = cloud_msg.header
            header.frame_id = self.target_frame
            # 保持原始时间戳，方便其他节点进行时间对齐
            new_cloud = pc2.create_cloud_xyz32(header, P_map)
            self.pub.publish(new_cloud)
            
        except (tf2_ros.LookupException, tf2_ros.ConnectivityException, tf2_ros.ExtrapolationException):
            # 偶尔的 TF 缺失直接跳过，不打印 warn 保持终端整洁
            pass
        except Exception as e:
            rospy.logerr_throttle(2, f"CloudFixer unexpected error: {e}")

if __name__ == '__main__':
    try:
        CloudFixer()
        rospy.spin()
    except rospy.ROSInterruptException:
        pass
