#!/usr/bin/env python3

import argparse
import csv
import json
import math
import os
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, List, Optional, Tuple

import rospy
from geometry_msgs.msg import PoseStamped
from quadrotor_msgs.msg import PositionCommand
from sensor_msgs.msg import PointCloud2


@dataclass
class CommandSample:
    stamp_s: float
    position: Tuple[float, float, float]
    velocity: Tuple[float, float, float]
    speed_norm: float


class PlannerTraceRunner:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.output_dir = os.path.abspath(args.output_dir)
        os.makedirs(self.output_dir, exist_ok=True)

        self.latest_pose: Optional[PoseStamped] = None
        self.latest_cmd: Optional[PositionCommand] = None
        self.latest_cloud: Optional[PointCloud2] = None
        self.command_history: Deque[CommandSample] = deque()
        self.sample_rows: List[Dict[str, float]] = []
        self.cloud_rows: List[Dict[str, float]] = []

        rospy.init_node("planner_trace_runner", anonymous=True)
        rospy.Subscriber("/mavros/local_position/pose", PoseStamped, self._pose_cb, queue_size=20)
        rospy.Subscriber("/planning/pos_cmd", PositionCommand, self._cmd_cb, queue_size=200)
        rospy.Subscriber("/cloud_corrected", PointCloud2, self._cloud_cb, queue_size=5)

        self.rate = rospy.Rate(args.rate_hz)

    def _pose_cb(self, msg: PoseStamped) -> None:
        self.latest_pose = msg

    def _cmd_cb(self, msg: PositionCommand) -> None:
        velocity = (msg.velocity.x, msg.velocity.y, msg.velocity.z)
        self.latest_cmd = msg
        self.command_history.append(
            CommandSample(
                stamp_s=self._stamp_to_sec(msg.header.stamp),
                position=(msg.position.x, msg.position.y, msg.position.z),
                velocity=velocity,
                speed_norm=self._norm(velocity),
            )
        )
        self._trim_history()

    def _cloud_cb(self, msg: PointCloud2) -> None:
        stamp_s = self._stamp_to_sec(msg.header.stamp)
        self.latest_cloud = msg
        self.cloud_rows.append(
            {
                "cloud_stamp_s": stamp_s,
                "point_count": float(msg.width * msg.height),
            }
        )

    @staticmethod
    def _stamp_to_sec(stamp: rospy.Time) -> float:
        return float(stamp.secs) + float(stamp.nsecs) * 1e-9

    @staticmethod
    def _norm(values: Tuple[float, float, float]) -> float:
        return math.sqrt(sum(v * v for v in values))

    @staticmethod
    def _distance(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> float:
        return math.sqrt(sum((x - y) * (x - y) for x, y in zip(a, b)))

    def _trim_history(self) -> None:
        if self.latest_pose is None:
            return
        cutoff_s = self._stamp_to_sec(self.latest_pose.header.stamp) - self.args.match_history_s
        while self.command_history and self.command_history[0].stamp_s < cutoff_s:
            self.command_history.popleft()

    def _wait_for_inputs(self) -> None:
        deadline = time.monotonic() + self.args.input_timeout_s
        while time.monotonic() < deadline and not rospy.is_shutdown():
            if self.latest_pose is not None and self.latest_cmd is not None and self.latest_cloud is not None:
                return
            time.sleep(0.1)
        raise RuntimeError("Timed out waiting for /mavros/local_position/pose, /planning/pos_cmd, and /cloud_corrected")

    def _record_trace(self) -> None:
        self._wait_for_inputs()
        start_wall = time.monotonic()
        origin = (
            self.latest_pose.pose.position.x,
            self.latest_pose.pose.position.y,
            self.latest_pose.pose.position.z,
        )
        prev_pose_xyz: Optional[Tuple[float, float, float]] = None
        prev_pose_stamp_s: Optional[float] = None

        while time.monotonic() - start_wall < self.args.duration_s and not rospy.is_shutdown():
            pose = self.latest_pose
            cmd = self.latest_cmd
            cloud = self.latest_cloud
            if pose is None or cmd is None or cloud is None:
                self.rate.sleep()
                continue

            pose_stamp_s = self._stamp_to_sec(pose.header.stamp)
            cmd_stamp_s = self._stamp_to_sec(cmd.header.stamp)
            cloud_stamp_s = self._stamp_to_sec(cloud.header.stamp)

            pose_xyz = (
                pose.pose.position.x,
                pose.pose.position.y,
                pose.pose.position.z,
            )
            cmd_xyz = (
                cmd.position.x,
                cmd.position.y,
                cmd.position.z,
            )
            cmd_vel = (
                cmd.velocity.x,
                cmd.velocity.y,
                cmd.velocity.z,
            )
            cmd_speed = self._norm(cmd_vel)

            actual_vel = (0.0, 0.0, 0.0)
            actual_speed = 0.0
            if prev_pose_xyz is not None and prev_pose_stamp_s is not None:
                dt = pose_stamp_s - prev_pose_stamp_s
                if dt > 1e-4:
                    actual_vel = tuple((cur - prev) / dt for cur, prev in zip(pose_xyz, prev_pose_xyz))
                    actual_speed = self._norm(actual_vel)

            latest_error = self._distance(pose_xyz, cmd_xyz)
            latest_speed_error = self._distance(actual_vel, cmd_vel)
            origin_offset = self._distance(cmd_xyz, origin)
            active = cmd_speed >= self.args.active_speed_threshold or origin_offset >= self.args.active_distance_threshold

            matched_lag_s = math.nan
            matched_error = math.nan
            match = self._best_match(pose_stamp_s, pose_xyz)
            if match is not None:
                matched_lag_s, matched_error = match

            self.sample_rows.append(
                {
                    "pose_stamp_s": pose_stamp_s,
                    "cmd_stamp_s": cmd_stamp_s,
                    "cloud_stamp_s": cloud_stamp_s,
                    "cmd_age_s": max(0.0, pose_stamp_s - cmd_stamp_s),
                    "cloud_age_s": max(0.0, pose_stamp_s - cloud_stamp_s),
                    "pose_x": pose_xyz[0],
                    "pose_y": pose_xyz[1],
                    "pose_z": pose_xyz[2],
                    "cmd_x": cmd_xyz[0],
                    "cmd_y": cmd_xyz[1],
                    "cmd_z": cmd_xyz[2],
                    "cmd_vx": cmd_vel[0],
                    "cmd_vy": cmd_vel[1],
                    "cmd_vz": cmd_vel[2],
                    "actual_vx": actual_vel[0],
                    "actual_vy": actual_vel[1],
                    "actual_vz": actual_vel[2],
                    "cmd_speed_norm": cmd_speed,
                    "actual_speed_norm": actual_speed,
                    "latest_position_error_norm": latest_error,
                    "latest_speed_error_norm": latest_speed_error,
                    "matched_lag_s": matched_lag_s,
                    "matched_position_error_norm": matched_error,
                    "command_origin_offset_m": origin_offset,
                    "cloud_point_count": float(cloud.width * cloud.height),
                    "active": 1.0 if active else 0.0,
                }
            )

            prev_pose_xyz = pose_xyz
            prev_pose_stamp_s = pose_stamp_s
            self.rate.sleep()

    def _best_match(self, pose_stamp_s: float, pose_xyz: Tuple[float, float, float]) -> Optional[Tuple[float, float]]:
        candidates = [
            sample
            for sample in self.command_history
            if sample.stamp_s <= pose_stamp_s + self.args.future_match_tolerance_s
        ]
        if not candidates:
            return None

        best_sample = None
        best_error = None
        for sample in candidates:
            error = self._distance(pose_xyz, sample.position)
            if best_error is None or error < best_error:
                best_error = error
                best_sample = sample

        if best_sample is None or best_error is None:
            return None
        if best_error > self.args.max_match_error_m:
            return None

        return (pose_stamp_s - best_sample.stamp_s, best_error)

    def _stats(self, values: List[float]) -> Dict[str, float]:
        if not values:
            return {"count": 0}
        ordered = sorted(values)
        return {
            "count": len(values),
            "mean": sum(values) / len(values),
            "min": ordered[0],
            "p50": ordered[len(ordered) // 2],
            "p95": ordered[min(len(ordered) - 1, int(round((len(ordered) - 1) * 0.95)))],
            "max": ordered[-1],
        }

    def _write_csv(self) -> None:
        trace_path = os.path.join(self.output_dir, "trace_samples.csv")
        with open(trace_path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(self.sample_rows[0].keys()))
            writer.writeheader()
            writer.writerows(self.sample_rows)

        cloud_path = os.path.join(self.output_dir, "cloud_samples.csv")
        with open(cloud_path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["cloud_stamp_s", "point_count"])
            writer.writeheader()
            writer.writerows(self.cloud_rows)

    def _build_summary(self) -> Dict[str, object]:
        active_rows = [row for row in self.sample_rows if row["active"] >= 0.5]
        matched_rows = [row for row in active_rows if not math.isnan(row["matched_lag_s"])]
        cloud_intervals = [
            self.cloud_rows[i]["cloud_stamp_s"] - self.cloud_rows[i - 1]["cloud_stamp_s"]
            for i in range(1, len(self.cloud_rows))
            if self.cloud_rows[i]["cloud_stamp_s"] > self.cloud_rows[i - 1]["cloud_stamp_s"]
        ]

        summary = {
            "duration_s": self.args.duration_s,
            "rate_hz": self.args.rate_hz,
            "sample_count": len(self.sample_rows),
            "active_sample_count": len(active_rows),
            "latest_position_error_norm_m": self._stats(
                [row["latest_position_error_norm"] for row in active_rows]
            ),
            "latest_speed_error_norm_mps": self._stats(
                [row["latest_speed_error_norm"] for row in active_rows]
            ),
            "matched_command_lag_s": self._stats(
                [row["matched_lag_s"] for row in matched_rows]
            ),
            "matched_position_error_norm_m": self._stats(
                [row["matched_position_error_norm"] for row in matched_rows]
            ),
            "cmd_age_s": self._stats([row["cmd_age_s"] for row in self.sample_rows]),
            "cloud_age_s": self._stats([row["cloud_age_s"] for row in self.sample_rows]),
            "cmd_speed_norm_mps": self._stats([row["cmd_speed_norm"] for row in active_rows]),
            "actual_speed_norm_mps": self._stats([row["actual_speed_norm"] for row in active_rows]),
            "cloud_point_count": self._stats([row["point_count"] for row in self.cloud_rows]),
            "cloud_interval_s": self._stats(cloud_intervals),
            "cloud_rate_hz": 0.0,
            "active_thresholds": {
                "speed_mps": self.args.active_speed_threshold,
                "distance_m": self.args.active_distance_threshold,
            },
            "match_thresholds": {
                "history_s": self.args.match_history_s,
                "future_tolerance_s": self.args.future_match_tolerance_s,
                "max_error_m": self.args.max_match_error_m,
            },
        }
        if cloud_intervals:
            summary["cloud_rate_hz"] = len(cloud_intervals) / sum(cloud_intervals)
        return summary

    def run(self) -> None:
        self._record_trace()
        if not self.sample_rows:
            raise RuntimeError("No trace samples were captured")
        self._write_csv()
        summary = self._build_summary()
        with open(os.path.join(self.output_dir, "summary.json"), "w", encoding="utf-8") as handle:
            json.dump(summary, handle, indent=2, sort_keys=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture a reproducible planner trace from the live PX4 + Ego-Planner stack")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--duration-s", type=float, default=25.0)
    parser.add_argument("--rate-hz", type=float, default=30.0)
    parser.add_argument("--input-timeout-s", type=float, default=30.0)
    parser.add_argument("--active-speed-threshold", type=float, default=0.3)
    parser.add_argument("--active-distance-threshold", type=float, default=1.0)
    parser.add_argument("--match-history-s", type=float, default=8.0)
    parser.add_argument("--future-match-tolerance-s", type=float, default=0.25)
    parser.add_argument("--max-match-error-m", type=float, default=2.0)
    return parser.parse_args()


def main() -> None:
    runner = PlannerTraceRunner(parse_args())
    runner.run()


if __name__ == "__main__":
    main()
