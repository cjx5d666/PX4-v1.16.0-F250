#!/usr/bin/env python3

import argparse
import csv
import json
import math
import os
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

import rospy
from geometry_msgs.msg import PoseStamped, TwistStamped
from mavros_msgs.msg import ParamValue, State
from mavros_msgs.srv import CommandBool, ParamGet, ParamPull, ParamSet, SetMode


KEY_PARAMS = [
    "MPC_XY_P",
    "MPC_Z_P",
    "MPC_XY_VEL_P_ACC",
    "MPC_XY_VEL_I_ACC",
    "MPC_XY_VEL_D_ACC",
    "MPC_Z_VEL_P_ACC",
    "MPC_Z_VEL_I_ACC",
    "MPC_Z_VEL_D_ACC",
    "MPC_ACC_HOR",
    "MPC_ACC_UP_MAX",
    "MPC_ACC_DOWN_MAX",
    "MPC_XY_VEL_MAX",
    "MPC_Z_VEL_MAX_UP",
    "MPC_Z_VEL_MAX_DN",
    "MPC_THR_HOVER",
]


LEVEL_CONFIGS: Dict[str, Dict[str, float]] = {
    "l1": {
        "z_step_amp": 0.35,
        "circle_radius": 0.60,
        "circle_freq_hz": 0.08,
        "figure8_amp_x": 0.80,
        "figure8_amp_y": 0.50,
        "figure8_freq_hz": 0.07,
        "z_sine_amp": 0.20,
        "z_sine_freq_hz": 0.035,
        "diag_xy_step_amp": 0.50,
        "diag_xy_ramp_amp": 0.80,
    }
}


def smoothstep(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3.0 - 2.0 * x)


@dataclass
class ProfileDefinition:
    name: str
    duration: float
    reference: Callable[[float, float], Tuple[float, float, float]]
    metadata: Dict[str, object]


class TrackingTestRunner:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.state = State()
        self.pose: Optional[PoseStamped] = None
        self.velocity: Optional[TwistStamped] = None
        self.pose_pub = None
        self.arm_srv = None
        self.mode_srv = None
        self.param_get_srv = None
        self.param_set_srv = None
        self.param_pull_srv = None
        self.hover_target = (0.0, 0.0, args.hover_z)

        self.output_dir = os.path.abspath(args.output_dir)
        os.makedirs(self.output_dir, exist_ok=True)

        rospy.init_node("tracking_test_runner", anonymous=False)
        rospy.Subscriber("/mavros/state", State, self._state_cb)
        rospy.Subscriber("/mavros/local_position/pose", PoseStamped, self._pose_cb)
        rospy.Subscriber("/mavros/local_position/velocity_local", TwistStamped, self._velocity_cb)
        self.pose_pub = rospy.Publisher("/mavros/setpoint_position/local", PoseStamped, queue_size=20)

        rospy.wait_for_service("/mavros/cmd/arming", timeout=30)
        rospy.wait_for_service("/mavros/set_mode", timeout=30)
        rospy.wait_for_service("/mavros/param/pull", timeout=30)
        rospy.wait_for_service("/mavros/param/get", timeout=30)
        rospy.wait_for_service("/mavros/param/set", timeout=30)

        self.arm_srv = rospy.ServiceProxy("/mavros/cmd/arming", CommandBool)
        self.mode_srv = rospy.ServiceProxy("/mavros/set_mode", SetMode)
        self.param_pull_srv = rospy.ServiceProxy("/mavros/param/pull", ParamPull)
        self.param_get_srv = rospy.ServiceProxy("/mavros/param/get", ParamGet)
        self.param_set_srv = rospy.ServiceProxy("/mavros/param/set", ParamSet)

        self.rate = rospy.Rate(args.rate_hz)
        self._wait_for_connection()
        self._wait_for_pose()

    def _state_cb(self, msg: State) -> None:
        self.state = msg

    def _pose_cb(self, msg: PoseStamped) -> None:
        self.pose = msg

    def _velocity_cb(self, msg: TwistStamped) -> None:
        self.velocity = msg

    def _wait_for_connection(self) -> None:
        deadline = time.monotonic() + 60.0
        while time.monotonic() < deadline and not rospy.is_shutdown():
            if self.state.connected:
                return
            time.sleep(0.1)
        raise RuntimeError("Timed out waiting for MAVROS connection")

    def _wait_for_pose(self) -> None:
        deadline = time.monotonic() + 60.0
        while time.monotonic() < deadline and not rospy.is_shutdown():
            if self.pose is not None:
                return
            time.sleep(0.1)
        raise RuntimeError("Timed out waiting for local pose")

    def _publish_position(self, xyz: Tuple[float, float, float]) -> None:
        msg = PoseStamped()
        msg.header.stamp = rospy.Time.now()
        msg.header.frame_id = "map"
        msg.pose.orientation.w = 1.0
        msg.pose.position.x = xyz[0]
        msg.pose.position.y = xyz[1]
        msg.pose.position.z = xyz[2]
        self.pose_pub.publish(msg)

    def _current_position(self) -> Tuple[float, float, float]:
        assert self.pose is not None
        p = self.pose.pose.position
        return (p.x, p.y, p.z)

    def _current_velocity(self) -> Tuple[float, float, float]:
        if self.velocity is None:
            return (0.0, 0.0, 0.0)
        v = self.velocity.twist.linear
        return (v.x, v.y, v.z)

    def _distance(self, a: Tuple[float, float, float], b: Tuple[float, float, float]) -> float:
        return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))

    def _speed(self) -> float:
        vx, vy, vz = self._current_velocity()
        return math.sqrt(vx * vx + vy * vy + vz * vz)

    def _prime_and_arm(self) -> None:
        prime_deadline = time.monotonic() + 3.0
        while time.monotonic() < prime_deadline and not rospy.is_shutdown():
            self._publish_position(self.hover_target)
            self.rate.sleep()

        deadline = time.monotonic() + self.args.arm_timeout
        last_mode_attempt = 0.0
        last_arm_attempt = 0.0
        while time.monotonic() < deadline and not rospy.is_shutdown():
            now = time.monotonic()
            self._publish_position(self.hover_target)
            if self.state.mode != "OFFBOARD" and now - last_mode_attempt >= 1.0:
                try:
                    self.mode_srv(0, "OFFBOARD")
                except rospy.ServiceException:
                    pass
                last_mode_attempt = now
            if not self.state.armed and now - last_arm_attempt >= 1.0:
                try:
                    self.arm_srv(True)
                except rospy.ServiceException:
                    pass
                last_arm_attempt = now
            if self.state.armed and self.state.mode == "OFFBOARD":
                return
            self.rate.sleep()
        raise RuntimeError("Failed to enter OFFBOARD and arm within timeout")

    def _hold_until_settled(self, target: Tuple[float, float, float], label: str, timeout_s: float) -> Dict[str, float]:
        start_wall = time.monotonic()
        settled_for = 0.0
        samples = 0
        while time.monotonic() - start_wall < timeout_s and not rospy.is_shutdown():
            self._publish_position(target)
            pos = self._current_position()
            err = self._distance(pos, target)
            speed = self._speed()
            if err <= self.args.settle_pos_tol and speed <= self.args.settle_vel_tol:
                settled_for += 1.0 / self.args.rate_hz
                if settled_for >= self.args.settle_hold_s:
                    return {
                        "settle_error_norm": err,
                        "settle_speed_norm": speed,
                        "settle_elapsed_wall_s": time.monotonic() - start_wall,
                        "samples": samples,
                        "label": label,
                    }
            else:
                settled_for = 0.0
            samples += 1
            self.rate.sleep()
        raise RuntimeError(f"Failed to settle at {label} target {target}")

    def _pull_params(self) -> None:
        response = self.param_pull_srv(True)
        if not response.success:
            raise RuntimeError("Failed to pull PX4 parameters via MAVROS")

    def _get_param(self, name: str) -> float:
        response = self.param_get_srv(name)
        if not response.success:
            raise RuntimeError(f"Failed to read PX4 parameter {name}")
        return float(response.value.real if abs(response.value.real) > 0.0 else response.value.integer)

    def _set_param(self, name: str, value: float) -> float:
        request = ParamValue()
        request.real = float(value)
        response = self.param_set_srv(name, request)
        if not response.success:
            raise RuntimeError(f"Failed to set PX4 parameter {name}={value}")
        return float(response.value.real if abs(response.value.real) > 0.0 else response.value.integer)

    def snapshot_params(self, target_path: str) -> Dict[str, float]:
        self._pull_params()
        values = {name: self._get_param(name) for name in KEY_PARAMS}
        with open(target_path, "w", encoding="utf-8") as handle:
            json.dump(values, handle, indent=2, sort_keys=True)
        return values

    def apply_param_updates(self, updates: Dict[str, float], target_path: str) -> Dict[str, Dict[str, float]]:
        results = {}
        for name, value in updates.items():
            before = self._get_param(name)
            after = self._set_param(name, value)
            results[name] = {"before": before, "requested": value, "after": after}
        with open(target_path, "w", encoding="utf-8") as handle:
            json.dump(results, handle, indent=2, sort_keys=True)
        return results

    def write_run_manifest(self, suite_name: str, level_name: str, profiles: List[ProfileDefinition], param_updates: Dict[str, float]) -> None:
        manifest = {
            "suite": suite_name,
            "level": level_name,
            "hover_target": {
                "x": self.hover_target[0],
                "y": self.hover_target[1],
                "z": self.hover_target[2],
            },
            "profiles": [p.name for p in profiles],
            "rate_hz": self.args.rate_hz,
            "settle_pos_tol": self.args.settle_pos_tol,
            "settle_vel_tol": self.args.settle_vel_tol,
            "settle_hold_s": self.args.settle_hold_s,
            "param_updates": param_updates,
            "started_wall_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        }
        with open(os.path.join(self.output_dir, "run_manifest.json"), "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2, sort_keys=True)

    def run_profile(self, profile: ProfileDefinition) -> Dict[str, object]:
        profile_dir = os.path.join(self.output_dir, profile.name)
        os.makedirs(profile_dir, exist_ok=True)
        metadata = dict(profile.metadata)
        metadata["duration"] = profile.duration
        metadata["hover_target"] = {
            "x": self.hover_target[0],
            "y": self.hover_target[1],
            "z": self.hover_target[2],
        }
        metadata["rate_hz"] = self.args.rate_hz

        metadata_path = os.path.join(profile_dir, "profile_metadata.json")
        with open(metadata_path, "w", encoding="utf-8") as handle:
            json.dump(metadata, handle, indent=2, sort_keys=True)

        csv_path = os.path.join(profile_dir, "telemetry.csv")
        fieldnames = [
            "profile",
            "phase",
            "sim_time_s",
            "wall_time_s",
            "profile_time_s",
            "ref_x",
            "ref_y",
            "ref_z",
            "actual_x",
            "actual_y",
            "actual_z",
            "vel_x",
            "vel_y",
            "vel_z",
            "err_x",
            "err_y",
            "err_z",
            "err_norm",
            "speed_norm",
            "connected",
            "armed",
            "mode",
        ]

        with open(csv_path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()

            pre_hold_deadline = time.monotonic() + self.args.pre_profile_hold_s
            while time.monotonic() < pre_hold_deadline and not rospy.is_shutdown():
                self._log_sample(writer, profile.name, "pre_hold", 0.0, self.hover_target)
                self._publish_position(self.hover_target)
                self.rate.sleep()

            start_wall = time.monotonic()
            while time.monotonic() - start_wall <= profile.duration and not rospy.is_shutdown():
                elapsed = time.monotonic() - start_wall
                target = profile.reference(elapsed, self.args.hover_z)
                self._log_sample(writer, profile.name, "trajectory", elapsed, target)
                self._publish_position(target)
                self.rate.sleep()

            final_target = profile.reference(profile.duration, self.args.hover_z)
            post_hold_deadline = time.monotonic() + self.args.post_profile_hold_s
            while time.monotonic() < post_hold_deadline and not rospy.is_shutdown():
                elapsed = profile.duration + (time.monotonic() - post_hold_deadline + self.args.post_profile_hold_s)
                self._log_sample(writer, profile.name, "post_hold", elapsed, final_target)
                self._publish_position(final_target)
                self.rate.sleep()

        return {
            "name": profile.name,
            "profile_dir": profile_dir,
            "metadata_path": metadata_path,
            "csv_path": csv_path,
        }

    def _log_sample(self, writer: csv.DictWriter, profile_name: str, phase: str, profile_time_s: float, target: Tuple[float, float, float]) -> None:
        actual = self._current_position()
        velocity = self._current_velocity()
        err = tuple(a - b for a, b in zip(actual, target))
        err_norm = math.sqrt(sum(v * v for v in err))
        speed_norm = math.sqrt(sum(v * v for v in velocity))
        writer.writerow(
            {
                "profile": profile_name,
                "phase": phase,
                "sim_time_s": rospy.Time.now().to_sec(),
                "wall_time_s": time.time(),
                "profile_time_s": round(profile_time_s, 6),
                "ref_x": round(target[0], 6),
                "ref_y": round(target[1], 6),
                "ref_z": round(target[2], 6),
                "actual_x": round(actual[0], 6),
                "actual_y": round(actual[1], 6),
                "actual_z": round(actual[2], 6),
                "vel_x": round(velocity[0], 6),
                "vel_y": round(velocity[1], 6),
                "vel_z": round(velocity[2], 6),
                "err_x": round(err[0], 6),
                "err_y": round(err[1], 6),
                "err_z": round(err[2], 6),
                "err_norm": round(err_norm, 6),
                "speed_norm": round(speed_norm, 6),
                "connected": int(self.state.connected),
                "armed": int(self.state.armed),
                "mode": self.state.mode,
            }
        )

    def run_suite(self, suite_name: str, level_name: str, profiles: List[ProfileDefinition], param_updates: Dict[str, float]) -> None:
        self.write_run_manifest(suite_name, level_name, profiles, param_updates)
        self.snapshot_params(os.path.join(self.output_dir, "params_before.json"))
        if param_updates:
            self.apply_param_updates(param_updates, os.path.join(self.output_dir, "params_applied.json"))
        self.snapshot_params(os.path.join(self.output_dir, "params_effective.json"))

        self._prime_and_arm()
        settle_info = self._hold_until_settled(self.hover_target, "hover_target", self.args.initial_settle_timeout)
        with open(os.path.join(self.output_dir, "hover_settle.json"), "w", encoding="utf-8") as handle:
            json.dump(settle_info, handle, indent=2, sort_keys=True)

        run_results = []
        for profile in profiles:
            result = self.run_profile(profile)
            run_results.append(result)
            self._hold_until_settled(self.hover_target, f"post_{profile.name}", self.args.inter_profile_settle_timeout)

        summary = {
            "suite": suite_name,
            "level": level_name,
            "profiles_completed": [result["name"] for result in run_results],
            "finished_wall_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        }
        with open(os.path.join(self.output_dir, "runner_summary.json"), "w", encoding="utf-8") as handle:
            json.dump(summary, handle, indent=2, sort_keys=True)

        final_hold_deadline = time.monotonic() + self.args.final_hold_s
        while time.monotonic() < final_hold_deadline and not rospy.is_shutdown():
            self._publish_position(self.hover_target)
            self.rate.sleep()


def parse_param_updates(raw_items: List[str]) -> Dict[str, float]:
    updates: Dict[str, float] = {}
    for item in raw_items:
        name, value = item.split("=", 1)
        updates[name.strip()] = float(value)
    return updates


def merge_param_updates(cli_updates: Dict[str, float], file_path: Optional[str]) -> Dict[str, float]:
    merged: Dict[str, float] = {}
    if file_path:
        with open(file_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        for key, value in payload.items():
            merged[str(key)] = float(value)
    merged.update(cli_updates)
    return merged


def _step_profile(name: str, axis: str, amplitude: float, hold_s: float, total_s: float, family: str, level: str, analysis_mode: str) -> ProfileDefinition:
    axis_idx = {"x": 0, "y": 1, "z": 2}[axis]

    def reference(t: float, hover_z: float) -> Tuple[float, float, float]:
        values = [0.0, 0.0, hover_z]
        if t >= hold_s:
            values[axis_idx] += amplitude
        return tuple(values)

    return ProfileDefinition(
        name=name,
        duration=total_s,
        reference=reference,
        metadata={
            "profile_type": "step",
            "family": family,
            "level": level,
            "analysis_mode": analysis_mode,
            "axis": axis,
            "step_axis": axis,
            "step_time_s": hold_s,
            "amplitude_m": amplitude,
            "analysis_start_s": hold_s,
        },
    )


def _ramp_x_profile(name: str, amplitude: float, hold_s: float, ramp_duration: float, total_s: float, level: str) -> ProfileDefinition:
    def reference(t: float, hover_z: float) -> Tuple[float, float, float]:
        if t < hold_s:
            x = 0.0
        elif t < hold_s + ramp_duration:
            x = amplitude * (t - hold_s) / ramp_duration
        else:
            x = amplitude
        return (x, 0.0, hover_z)

    return ProfileDefinition(
        name=name,
        duration=total_s,
        reference=reference,
        metadata={
            "profile_type": "ramp",
            "family": "diag_xy_ramp",
            "level": level,
            "analysis_mode": "xy_shape",
            "analysis_start_s": hold_s,
            "ramp_start_s": hold_s,
            "ramp_end_s": hold_s + ramp_duration,
            "amplitude_m": amplitude,
        },
    )


def build_profiles(suite_name: str, level_name: str) -> List[ProfileDefinition]:
    if level_name not in LEVEL_CONFIGS:
        raise ValueError(f"Unknown level: {level_name}")

    config = LEVEL_CONFIGS[level_name]

    def z_step_hold_xy_profile() -> ProfileDefinition:
        amplitude = config["z_step_amp"]
        return _step_profile(
            name=f"z_step_hold_xy_{level_name}",
            axis="z",
            amplitude=amplitude,
            hold_s=2.0,
            total_s=12.0,
            family="z_step_hold_xy",
            level=level_name,
            analysis_mode="z_only",
        )

    def circle_profile(with_z_sine: bool) -> ProfileDefinition:
        radius = config["circle_radius"]
        frequency_hz = config["circle_freq_hz"]
        z_amp = config["z_sine_amp"]
        z_frequency_hz = config["z_sine_freq_hz"]
        ramp_s = 4.0
        duration = 28.0 if with_z_sine else 26.0
        family = "circle_xy_with_z_sine" if with_z_sine else "circle_xy_const_z"

        def reference(t: float, hover_z: float) -> Tuple[float, float, float]:
            env = smoothstep(t / ramp_s)
            angle = 2.0 * math.pi * frequency_hz * t
            x = env * radius * (math.cos(angle) - 1.0)
            y = env * radius * math.sin(angle)
            z = hover_z
            if with_z_sine:
                z += env * z_amp * math.sin(2.0 * math.pi * z_frequency_hz * t + math.pi / 6.0)
            return (x, y, z)

        return ProfileDefinition(
            name=f"{family}_{level_name}",
            duration=duration,
            reference=reference,
            metadata={
                "profile_type": "circle",
                "family": family,
                "level": level_name,
                "analysis_mode": "xy_shape_with_z" if with_z_sine else "xy_shape",
                "radius_m": radius,
                "circle_center_xy": [-radius, 0.0],
                "frequency_hz": frequency_hz,
                "z_sine_amp_m": z_amp if with_z_sine else 0.0,
                "z_sine_frequency_hz": z_frequency_hz if with_z_sine else 0.0,
                "analysis_start_s": ramp_s + 2.0,
                "active_axes": ["x", "y", "z"] if with_z_sine else ["x", "y"],
            },
        )

    def figure8_profile(with_z_sine: bool) -> ProfileDefinition:
        amp_x = config["figure8_amp_x"]
        amp_y = config["figure8_amp_y"]
        frequency_hz = config["figure8_freq_hz"]
        z_amp = config["z_sine_amp"]
        z_frequency_hz = config["z_sine_freq_hz"]
        ramp_s = 4.0
        duration = 30.0 if with_z_sine else 28.0
        family = "figure8_xy_with_z_sine" if with_z_sine else "figure8_xy_const_z"

        def reference(t: float, hover_z: float) -> Tuple[float, float, float]:
            env = smoothstep(t / ramp_s)
            angle = 2.0 * math.pi * frequency_hz * t
            x = env * amp_x * math.sin(angle)
            y = env * amp_y * math.sin(2.0 * angle)
            z = hover_z
            if with_z_sine:
                z += env * z_amp * math.sin(2.0 * math.pi * z_frequency_hz * t + math.pi / 4.0)
            return (x, y, z)

        return ProfileDefinition(
            name=f"{family}_{level_name}",
            duration=duration,
            reference=reference,
            metadata={
                "profile_type": "figure8",
                "family": family,
                "level": level_name,
                "analysis_mode": "xy_shape_with_z" if with_z_sine else "xy_shape",
                "frequency_hz": frequency_hz,
                "amplitude_x_m": amp_x,
                "amplitude_y_m": amp_y,
                "z_sine_amp_m": z_amp if with_z_sine else 0.0,
                "z_sine_frequency_hz": z_frequency_hz if with_z_sine else 0.0,
                "analysis_start_s": ramp_s + 2.0,
                "active_axes": ["x", "y", "z"] if with_z_sine else ["x", "y"],
            },
        )

    def diag_step_x_profile() -> ProfileDefinition:
        return _step_profile(
            name=f"diag_step_x_{level_name}",
            axis="x",
            amplitude=config["diag_xy_step_amp"],
            hold_s=2.0,
            total_s=10.0,
            family="diag_xy_step",
            level=level_name,
            analysis_mode="xy_shape",
        )

    def diag_step_y_profile() -> ProfileDefinition:
        return _step_profile(
            name=f"diag_step_y_{level_name}",
            axis="y",
            amplitude=config["diag_xy_step_amp"],
            hold_s=2.0,
            total_s=10.0,
            family="diag_xy_step",
            level=level_name,
            analysis_mode="xy_shape",
        )

    def diag_ramp_x_profile() -> ProfileDefinition:
        return _ramp_x_profile(
            name=f"diag_ramp_x_{level_name}",
            amplitude=config["diag_xy_ramp_amp"],
            hold_s=2.0,
            ramp_duration=5.0,
            total_s=12.0,
            level=level_name,
        )

    profile_map = {
        f"z_step_hold_xy_{level_name}": z_step_hold_xy_profile(),
        f"circle_xy_const_z_{level_name}": circle_profile(with_z_sine=False),
        f"figure8_xy_const_z_{level_name}": figure8_profile(with_z_sine=False),
        f"circle_xy_with_z_sine_{level_name}": circle_profile(with_z_sine=True),
        f"figure8_xy_with_z_sine_{level_name}": figure8_profile(with_z_sine=True),
        f"diag_step_x_{level_name}": diag_step_x_profile(),
        f"diag_step_y_{level_name}": diag_step_y_profile(),
        f"diag_ramp_x_{level_name}": diag_ramp_x_profile(),
    }

    suites = {
        "default": [
            f"z_step_hold_xy_{level_name}",
            f"circle_xy_const_z_{level_name}",
            f"figure8_xy_const_z_{level_name}",
            f"circle_xy_with_z_sine_{level_name}",
            f"figure8_xy_with_z_sine_{level_name}",
        ],
        "smoke": [
            f"circle_xy_const_z_{level_name}",
            f"figure8_xy_const_z_{level_name}",
            f"circle_xy_with_z_sine_{level_name}",
        ],
        "z_only": [f"z_step_hold_xy_{level_name}"],
        "diag_xy": [
            f"diag_step_x_{level_name}",
            f"diag_step_y_{level_name}",
            f"diag_ramp_x_{level_name}",
        ],
    }

    if suite_name not in suites:
        raise ValueError(f"Unknown suite: {suite_name}")
    return [profile_map[name] for name in suites[suite_name]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run non-planner PX4 tracking tests")
    parser.add_argument("--suite", default="default", choices=["default", "smoke", "z_only", "diag_xy"])
    parser.add_argument("--level", default="l1", choices=sorted(LEVEL_CONFIGS.keys()))
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--hover-z", type=float, default=2.5)
    parser.add_argument("--rate-hz", type=float, default=30.0)
    parser.add_argument("--arm-timeout", type=float, default=90.0)
    parser.add_argument("--settle-pos-tol", type=float, default=0.18)
    parser.add_argument("--settle-vel-tol", type=float, default=0.25)
    parser.add_argument("--settle-hold-s", type=float, default=3.0)
    parser.add_argument("--initial-settle-timeout", type=float, default=45.0)
    parser.add_argument("--inter-profile-settle-timeout", type=float, default=35.0)
    parser.add_argument("--pre-profile-hold-s", type=float, default=2.0)
    parser.add_argument("--post-profile-hold-s", type=float, default=4.0)
    parser.add_argument("--final-hold-s", type=float, default=4.0)
    parser.add_argument("--param", action="append", default=[], help="Override PX4 param, e.g. MPC_XY_P=1.2")
    parser.add_argument("--param-file", default=None, help="JSON file containing PX4 params to apply")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cli_updates = parse_param_updates(args.param)
    param_updates = merge_param_updates(cli_updates, args.param_file)
    profiles = build_profiles(args.suite, args.level)
    runner = TrackingTestRunner(args)
    runner.run_suite(args.suite, args.level, profiles, param_updates)


if __name__ == "__main__":
    main()
