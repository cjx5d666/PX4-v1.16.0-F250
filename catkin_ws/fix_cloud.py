#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import numpy as np
import rospy
import sensor_msgs.point_cloud2 as pc2
import tf2_ros
from sensor_msgs.msg import PointCloud2
from std_msgs.msg import Header
from tf.transformations import concatenate_matrices, quaternion_matrix, translation_matrix


class CloudFixer:
    def __init__(self):
        rospy.init_node("cloud_fixer_node")

        configured_input = rospy.get_param("~input_topic", "")
        candidate_topics = [
            configured_input,
            "/iris_depth_camera/camera/depth/points",
            "/iris_depth_camera/depth_camera/points",
            "/depth_camera/points",
        ]
        self.input_topics = []
        for topic in candidate_topics:
            if topic and topic not in self.input_topics:
                self.input_topics.append(topic)
        self.target_frame = rospy.get_param("~target_frame", "map")
        self.tf_timeout = rospy.Duration(rospy.get_param("~tf_timeout_s", 0.15))
        self.point_stride = max(1, int(rospy.get_param("~point_stride", 1)))
        self.max_publish_hz = max(0.0, float(rospy.get_param("~max_publish_hz", 0.0)))
        self.last_publish_time = rospy.Time(0)

        self.subscribers = [
            rospy.Subscriber(
                topic,
                PointCloud2,
                self.callback,
                callback_args=topic,
                queue_size=1,
                buff_size=2**24,
            )
            for topic in self.input_topics
        ]
        self.pub = rospy.Publisher("/cloud_corrected", PointCloud2, queue_size=1)

        self.tf_buffer = tf2_ros.Buffer()
        self.listener = tf2_ros.TransformListener(self.tf_buffer)

        rospy.loginfo(
            ">>> CloudFixer ready | inputs=%s frame=%s stride=%d max_publish_hz=%.2f <<<",
            ",".join(self.input_topics),
            self.target_frame,
            self.point_stride,
            self.max_publish_hz,
        )

    def _should_drop_for_rate_limit(self, stamp: rospy.Time) -> bool:
        if self.max_publish_hz <= 0.0:
            return False

        min_period = rospy.Duration.from_sec(1.0 / self.max_publish_hz)
        if self.last_publish_time != rospy.Time(0) and stamp - self.last_publish_time < min_period:
            return True

        self.last_publish_time = stamp
        return False

    def _lookup_transform(self, cloud_msg: PointCloud2):
        lookup_stamp = cloud_msg.header.stamp
        if lookup_stamp == rospy.Time(0):
            transform = self.tf_buffer.lookup_transform(
                self.target_frame,
                cloud_msg.header.frame_id,
                rospy.Time(0),
                self.tf_timeout,
            )
            publish_stamp = transform.header.stamp if transform.header.stamp != rospy.Time(0) else rospy.Time.now()
            return transform, publish_stamp

        transform = self.tf_buffer.lookup_transform(
            self.target_frame,
            cloud_msg.header.frame_id,
            lookup_stamp,
            self.tf_timeout,
        )
        return transform, lookup_stamp

    def callback(self, cloud_msg: PointCloud2, source_topic: str):
        try:
            transform, publish_stamp = self._lookup_transform(cloud_msg)
            if self._should_drop_for_rate_limit(publish_stamp):
                return

            translation = [
                transform.transform.translation.x,
                transform.transform.translation.y,
                transform.transform.translation.z,
            ]
            rotation = [
                transform.transform.rotation.x,
                transform.transform.rotation.y,
                transform.transform.rotation.z,
                transform.transform.rotation.w,
            ]

            transform_matrix = concatenate_matrices(
                translation_matrix(translation),
                quaternion_matrix(rotation),
            )

            point_dtype = np.dtype([("x", np.float32), ("y", np.float32), ("z", np.float32)])
            points_iter = pc2.read_points(cloud_msg, field_names=("x", "y", "z"), skip_nans=True)
            points = np.fromiter(points_iter, dtype=point_dtype)

            if points.size == 0:
                return

            if self.point_stride > 1:
                points = points[:: self.point_stride]

            xyz = np.column_stack((points["x"], points["y"], points["z"])).astype(np.float32, copy=False)
            ones = np.ones((xyz.shape[0], 1), dtype=np.float32)
            points_hom = np.hstack((xyz, ones))
            transformed = np.dot(points_hom, transform_matrix.T)[:, :3].astype(np.float32, copy=False)

            header = Header(stamp=publish_stamp, frame_id=self.target_frame)
            self.pub.publish(pc2.create_cloud_xyz32(header, transformed))

        except (tf2_ros.LookupException, tf2_ros.ConnectivityException, tf2_ros.ExtrapolationException) as exc:
            rospy.logwarn_throttle(
                2.0,
                "CloudFixer TF lookup failed | input=%s source_frame=%s stamp=%.6f err=%s",
                source_topic,
                cloud_msg.header.frame_id,
                cloud_msg.header.stamp.to_sec(),
                exc,
            )
        except Exception as exc:
            rospy.logerr_throttle(2.0, f"CloudFixer unexpected error: {exc}")


if __name__ == "__main__":
    try:
        CloudFixer()
        rospy.spin()
    except rospy.ROSInterruptException:
        pass
