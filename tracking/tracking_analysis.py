#!/usr/bin/env python3

import argparse
import csv
import json
import math
import os
from typing import Dict, List, Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401


AXES = ["x", "y", "z"]
NUMERIC_FIELDS = {
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
}


def load_json(path: str) -> Dict[str, object]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def stable_timebase(time_values: np.ndarray) -> np.ndarray:
    adjusted = np.asarray(time_values, dtype=float).copy()
    if len(adjusted) == 0:
        return adjusted
    for idx in range(1, len(adjusted)):
        if adjusted[idx] <= adjusted[idx - 1]:
            adjusted[idx] = adjusted[idx - 1] + 1e-6
    return adjusted


def load_telemetry(path: str) -> Dict[str, object]:
    columns: Dict[str, List[object]] = {}
    with open(path, "r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for field in reader.fieldnames or []:
            columns[field] = []
        for row in reader:
            for field, value in row.items():
                if field in NUMERIC_FIELDS:
                    columns[field].append(float(value))
                else:
                    columns[field].append(value)

    result: Dict[str, object] = {}
    for field, values in columns.items():
        if field in NUMERIC_FIELDS:
            result[field] = np.asarray(values, dtype=float)
        else:
            result[field] = list(values)
    return result


def subset_numeric(data: Dict[str, object], mask: np.ndarray) -> Dict[str, np.ndarray]:
    subset: Dict[str, np.ndarray] = {}
    for field in NUMERIC_FIELDS:
        subset[field] = np.asarray(data[field])[mask]
    return subset


def estimate_lag_seconds(ref: np.ndarray, actual: np.ndarray, dt: float, max_lag_s: float = 3.0) -> Optional[float]:
    if len(ref) < 4 or dt <= 0:
        return None
    if np.std(ref) < 1e-4 or np.std(actual) < 1e-4:
        return None

    max_shift = min(int(max_lag_s / dt), len(ref) // 3)
    if max_shift <= 0:
        return None

    best_shift = 0
    best_score = -1e18
    for shift in range(-max_shift, max_shift + 1):
        if shift < 0:
            ref_slice = ref[-shift:]
            act_slice = actual[: len(ref_slice)]
        elif shift > 0:
            ref_slice = ref[:-shift]
            act_slice = actual[shift:]
        else:
            ref_slice = ref
            act_slice = actual
        if len(ref_slice) < 4:
            continue
        ref_centered = ref_slice - ref_slice.mean()
        act_centered = act_slice - act_slice.mean()
        denom = np.linalg.norm(ref_centered) * np.linalg.norm(act_centered)
        if denom <= 0:
            continue
        score = float(np.dot(ref_centered, act_centered) / denom)
        if score > best_score:
            best_score = score
            best_shift = shift
    return float(best_shift * dt)


def compute_settling_time(t: np.ndarray, actual: np.ndarray, final_ref: float, band: float, start_idx: int) -> Optional[float]:
    if start_idx >= len(t):
        return None
    abs_err = np.abs(actual[start_idx:] - final_ref)
    if len(abs_err) == 0:
        return None
    future_max = np.maximum.accumulate(abs_err[::-1])[::-1]
    settled_indices = np.where(future_max <= band)[0]
    if len(settled_indices) == 0:
        return None
    idx = start_idx + int(settled_indices[0])
    return float(t[idx] - t[start_idx])


def compute_planar_decomposition(data: Dict[str, object]) -> Optional[Dict[str, np.ndarray]]:
    time_values = stable_timebase(np.asarray(data["profile_time_s"], dtype=float))
    ref_x = np.asarray(data["ref_x"], dtype=float)
    ref_y = np.asarray(data["ref_y"], dtype=float)
    actual_x = np.asarray(data["actual_x"], dtype=float)
    actual_y = np.asarray(data["actual_y"], dtype=float)
    if len(time_values) < 4:
        return None

    dref_x = np.gradient(ref_x, time_values)
    dref_y = np.gradient(ref_y, time_values)
    ref_speed_xy = np.sqrt(dref_x * dref_x + dref_y * dref_y)
    moving_mask = ref_speed_xy > 0.03
    if not np.any(moving_mask):
        return None

    tangent_x = np.zeros_like(ref_speed_xy)
    tangent_y = np.zeros_like(ref_speed_xy)
    tangent_x[moving_mask] = dref_x[moving_mask] / ref_speed_xy[moving_mask]
    tangent_y[moving_mask] = dref_y[moving_mask] / ref_speed_xy[moving_mask]

    normal_x = -tangent_y
    normal_y = tangent_x

    err_x = actual_x - ref_x
    err_y = actual_y - ref_y

    along_track_error = err_x * tangent_x + err_y * tangent_y
    cross_track_error = err_x * normal_x + err_y * normal_y

    lag_proxy_samples = np.full_like(ref_speed_xy, np.nan, dtype=float)
    lag_proxy_samples[moving_mask] = -along_track_error[moving_mask] / ref_speed_xy[moving_mask]

    return {
        "time_s": time_values,
        "ref_speed_xy_mps": ref_speed_xy,
        "moving_mask": moving_mask.astype(bool),
        "along_track_error_m": along_track_error,
        "cross_track_error_m": cross_track_error,
        "lag_proxy_samples_s": lag_proxy_samples,
    }


def compute_metrics(data: Dict[str, object], metadata: Dict[str, object]) -> Dict[str, object]:
    time_values = stable_timebase(np.asarray(data["profile_time_s"], dtype=float))
    eval_start = float(metadata.get("analysis_start_s", 0.0))
    mask = time_values >= eval_start
    if not np.any(mask):
        mask = np.ones_like(time_values, dtype=bool)
    eval_data = subset_numeric(data, mask)

    metrics: Dict[str, object] = {
        "profile_type": metadata.get("profile_type"),
        "family": metadata.get("family"),
        "level": metadata.get("level"),
        "analysis_mode": metadata.get("analysis_mode"),
        "sample_count": int(np.count_nonzero(mask)),
        "analysis_start_s": eval_start,
    }

    dt = float(np.median(np.diff(eval_data["profile_time_s"]))) if len(eval_data["profile_time_s"]) > 2 else 0.0
    metrics["dt_s"] = dt
    metrics["rmse_xyz_m"] = float(np.sqrt(np.mean(np.square(eval_data["err_norm"]))))
    metrics["peak_err_xyz_m"] = float(np.max(np.abs(eval_data["err_norm"])))
    metrics["mean_speed_norm_mps"] = float(np.mean(eval_data["speed_norm"]))

    axis_metrics: Dict[str, Dict[str, Optional[float]]] = {}
    for axis in AXES:
        err = eval_data[f"err_{axis}"]
        ref = eval_data[f"ref_{axis}"]
        actual = eval_data[f"actual_{axis}"]
        ref_std = float(np.std(ref))
        actual_std = float(np.std(actual))
        axis_metrics[axis] = {
            "rmse_m": float(np.sqrt(np.mean(np.square(err)))),
            "peak_abs_err_m": float(np.max(np.abs(err))),
            "mean_abs_err_m": float(np.mean(np.abs(err))),
            "steady_state_bias_m": float(np.mean(err[-max(5, len(err) // 5) :])),
            "phase_lag_s": estimate_lag_seconds(ref, actual, dt) if len(ref) > 10 else None,
            "amplitude_ratio": float(actual_std / ref_std) if ref_std > 1e-4 else None,
        }
    metrics["axes"] = axis_metrics
    metrics["rmse_xy_m"] = float(np.sqrt(np.mean(np.square(eval_data["err_x"]) + np.square(eval_data["err_y"]))))
    metrics["rmse_z_m"] = axis_metrics["z"]["rmse_m"]

    planar_full = compute_planar_decomposition(data)
    if planar_full is not None:
        planar_eval = {
            key: value[mask] if isinstance(value, np.ndarray) else value
            for key, value in planar_full.items()
        }
        moving_mask = planar_eval["moving_mask"]
        if np.any(moving_mask):
            along = planar_eval["along_track_error_m"][moving_mask]
            cross = planar_eval["cross_track_error_m"][moving_mask]
            lag_proxy_samples = planar_eval["lag_proxy_samples_s"][moving_mask]
            metrics["planar_tracking"] = {
                "along_track_mean_m": float(np.mean(along)),
                "along_track_rmse_m": float(np.sqrt(np.mean(np.square(along)))),
                "cross_track_mean_m": float(np.mean(cross)),
                "cross_track_rmse_m": float(np.sqrt(np.mean(np.square(cross)))),
                "lag_proxy_s": float(np.mean(lag_proxy_samples)),
                "moving_sample_count": int(np.count_nonzero(moving_mask)),
            }

    if metadata.get("profile_type") == "circle" and "circle_center_xy" in metadata:
        center_x, center_y = metadata["circle_center_xy"]
        radius = float(metadata["radius_m"])
        actual_radius = np.sqrt(
            np.square(eval_data["actual_x"] - center_x) +
            np.square(eval_data["actual_y"] - center_y)
        )
        radial_error = actual_radius - radius
        metrics["circle_shape"] = {
            "radial_bias_m": float(np.mean(radial_error)),
            "radial_rmse_m": float(np.sqrt(np.mean(np.square(radial_error)))),
            "radial_peak_abs_m": float(np.max(np.abs(radial_error))),
        }

    step_axis = metadata.get("step_axis")
    if step_axis is not None:
        axis = str(step_axis)
        step_time = float(metadata["step_time_s"])
        full_ref = np.asarray(data[f"ref_{axis}"], dtype=float)
        full_actual = np.asarray(data[f"actual_{axis}"], dtype=float)
        full_time = stable_timebase(np.asarray(data["profile_time_s"], dtype=float))
        step_idx = int(np.searchsorted(full_time, step_time))
        initial_ref = float(np.mean(full_ref[max(0, step_idx - 10): step_idx + 1]))
        final_ref = float(np.mean(full_ref[-max(10, len(full_ref) // 5):]))
        amplitude = final_ref - initial_ref
        band = max(0.03, abs(amplitude) * 0.05)
        if abs(amplitude) > 1e-4:
            post_actual = full_actual[step_idx:]
            if amplitude > 0:
                peak = float(np.max(post_actual))
                overshoot_abs = max(0.0, peak - final_ref)
            else:
                peak = float(np.min(post_actual))
                overshoot_abs = max(0.0, final_ref - peak)
            metrics["step_response"] = {
                "axis": axis,
                "amplitude_m": amplitude,
                "overshoot_m": overshoot_abs,
                "overshoot_pct": float((overshoot_abs / abs(amplitude)) * 100.0),
                "settling_band_m": band,
                "settling_time_s": compute_settling_time(full_time, full_actual, final_ref, band, step_idx),
            }

    return metrics


def save_metrics(path: str, metrics: Dict[str, object]) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(metrics, handle, indent=2, sort_keys=True)


def plot_timeseries(data: Dict[str, object], profile_name: str, output_path: str) -> None:
    fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True)
    time_values = stable_timebase(np.asarray(data["profile_time_s"], dtype=float))
    for idx, axis_name in enumerate(AXES):
        axes[idx].plot(time_values, np.asarray(data[f"ref_{axis_name}"], dtype=float), label=f"{axis_name} ref", linewidth=2.0)
        axes[idx].plot(time_values, np.asarray(data[f"actual_{axis_name}"], dtype=float), label=f"{axis_name} actual", linewidth=1.6)
        axes[idx].set_ylabel(f"{axis_name} [m]")
        axes[idx].grid(True, alpha=0.25)
        axes[idx].legend(loc="upper right")
    axes[-1].set_xlabel("time [s]")
    fig.suptitle(f"{profile_name}: reference vs actual")
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def plot_errors(data: Dict[str, object], profile_name: str, output_path: str) -> None:
    fig, axes = plt.subplots(4, 1, figsize=(12, 10), sharex=True)
    time_values = stable_timebase(np.asarray(data["profile_time_s"], dtype=float))
    for idx, axis_name in enumerate(AXES):
        axes[idx].plot(time_values, np.asarray(data[f"err_{axis_name}"], dtype=float), linewidth=1.6)
        axes[idx].set_ylabel(f"e_{axis_name} [m]")
        axes[idx].grid(True, alpha=0.25)
    axes[-1].plot(time_values, np.asarray(data["err_norm"], dtype=float), color="black", linewidth=1.8)
    axes[-1].set_ylabel("|e| [m]")
    axes[-1].set_xlabel("time [s]")
    axes[-1].grid(True, alpha=0.25)
    fig.suptitle(f"{profile_name}: tracking error")
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def plot_xy(data: Dict[str, object], profile_name: str, output_path: str) -> None:
    fig, ax = plt.subplots(figsize=(8, 8))
    ax.plot(np.asarray(data["ref_x"], dtype=float), np.asarray(data["ref_y"], dtype=float), label="reference", linewidth=2.0)
    ax.plot(np.asarray(data["actual_x"], dtype=float), np.asarray(data["actual_y"], dtype=float), label="actual", linewidth=1.6)
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
    ax.set_title(f"{profile_name}: XY top view")
    ax.grid(True, alpha=0.25)
    ax.axis("equal")
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def plot_3d(data: Dict[str, object], profile_name: str, output_path: str) -> None:
    fig = plt.figure(figsize=(10, 8))
    ax = fig.add_subplot(111, projection="3d")
    ax.plot(np.asarray(data["ref_x"], dtype=float), np.asarray(data["ref_y"], dtype=float), np.asarray(data["ref_z"], dtype=float), label="reference", linewidth=2.0)
    ax.plot(np.asarray(data["actual_x"], dtype=float), np.asarray(data["actual_y"], dtype=float), np.asarray(data["actual_z"], dtype=float), label="actual", linewidth=1.6)
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
    ax.set_zlabel("z [m]")
    ax.set_title(f"{profile_name}: 3D trajectory")
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def plot_shape_tracking(data: Dict[str, object], profile_name: str, output_path: str) -> None:
    planar = compute_planar_decomposition(data)
    if planar is None:
        return
    time_values = planar["time_s"]
    fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True)
    axes[0].plot(time_values, planar["along_track_error_m"], linewidth=1.5, color="#8b2f1c")
    axes[0].set_ylabel("along [m]")
    axes[0].grid(True, alpha=0.25)

    axes[1].plot(time_values, planar["cross_track_error_m"], linewidth=1.5, color="#245f73")
    axes[1].set_ylabel("cross [m]")
    axes[1].grid(True, alpha=0.25)

    axes[2].plot(time_values, planar["lag_proxy_samples_s"], linewidth=1.2, color="#0b6e4f")
    axes[2].set_ylabel("lag proxy [s]")
    axes[2].set_xlabel("time [s]")
    axes[2].grid(True, alpha=0.25)

    fig.suptitle(f"{profile_name}: shape tracking decomposition")
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def profile_dirs(run_dir: str) -> List[str]:
    items = []
    for name in sorted(os.listdir(run_dir)):
        full_path = os.path.join(run_dir, name)
        if os.path.isdir(full_path) and os.path.isfile(os.path.join(full_path, "telemetry.csv")):
            items.append(full_path)
    return items


def build_summary_rows(rows: List[Dict[str, object]]) -> List[Dict[str, object]]:
    normalized = []
    for row in rows:
        axes = row.get("axes", {})
        planar = row.get("planar_tracking", {})
        step_response = row.get("step_response", {})
        circle_shape = row.get("circle_shape", {})
        normalized.append(
            {
                "profile": row["profile"],
                "family": row.get("family"),
                "level": row.get("level"),
                "type": row["profile_type"],
                "rmse_xyz_m": row["rmse_xyz_m"],
                "rmse_xy_m": row["rmse_xy_m"],
                "rmse_z_m": row["rmse_z_m"],
                "peak_err_xyz_m": row["peak_err_xyz_m"],
                "along_track_rmse_m": planar.get("along_track_rmse_m"),
                "cross_track_rmse_m": planar.get("cross_track_rmse_m"),
                "xy_lag_proxy_s": planar.get("lag_proxy_s"),
                "circle_radial_rmse_m": circle_shape.get("radial_rmse_m"),
                "x_lag_s": axes.get("x", {}).get("phase_lag_s"),
                "y_lag_s": axes.get("y", {}).get("phase_lag_s"),
                "z_lag_s": axes.get("z", {}).get("phase_lag_s"),
                "z_overshoot_pct": step_response.get("overshoot_pct") if step_response.get("axis") == "z" else None,
                "z_settling_time_s": step_response.get("settling_time_s") if step_response.get("axis") == "z" else None,
            }
        )
    return normalized


def write_summary_csv(summary_rows: List[Dict[str, object]], output_path: str) -> None:
    fieldnames = [
        "profile",
        "family",
        "level",
        "type",
        "rmse_xyz_m",
        "rmse_xy_m",
        "rmse_z_m",
        "peak_err_xyz_m",
        "along_track_rmse_m",
        "cross_track_rmse_m",
        "xy_lag_proxy_s",
        "circle_radial_rmse_m",
        "x_lag_s",
        "y_lag_s",
        "z_lag_s",
        "z_overshoot_pct",
        "z_settling_time_s",
    ]
    with open(output_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in summary_rows:
            writer.writerow(row)


def write_summary_markdown(summary_rows: List[Dict[str, object]], output_path: str) -> None:
    def fmt(value: object) -> str:
        if value is None:
            return "-"
        if isinstance(value, (int, float)):
            if math.isnan(value):
                return "-"
            return f"{value:.3f}"
        return str(value)

    lines = [
        "# Tracking Summary",
        "",
        "| profile | family | rmse_xy_m | along_track_rmse_m | cross_track_rmse_m | xy_lag_proxy_s | rmse_z_m | z_overshoot_pct | z_settling_time_s |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in summary_rows:
        lines.append(
            "| {profile} | {family} | {rmse_xy_m} | {along_track_rmse_m} | {cross_track_rmse_m} | {xy_lag_proxy_s} | {rmse_z_m} | {z_overshoot_pct} | {z_settling_time_s} |".format(
                profile=row["profile"],
                family=row["family"],
                rmse_xy_m=fmt(row["rmse_xy_m"]),
                along_track_rmse_m=fmt(row["along_track_rmse_m"]),
                cross_track_rmse_m=fmt(row["cross_track_rmse_m"]),
                xy_lag_proxy_s=fmt(row["xy_lag_proxy_s"]),
                rmse_z_m=fmt(row["rmse_z_m"]),
                z_overshoot_pct=fmt(row["z_overshoot_pct"]),
                z_settling_time_s=fmt(row["z_settling_time_s"]),
            )
        )
    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def analyze_run(run_dir: str) -> None:
    rows = []
    for profile_dir in profile_dirs(run_dir):
        profile_name = os.path.basename(profile_dir)
        telemetry_path = os.path.join(profile_dir, "telemetry.csv")
        metadata_path = os.path.join(profile_dir, "profile_metadata.json")

        data = load_telemetry(telemetry_path)
        metadata = load_json(metadata_path)
        metrics = compute_metrics(data, metadata)
        metrics["profile"] = profile_name

        save_metrics(os.path.join(profile_dir, "metrics.json"), metrics)
        plot_timeseries(data, profile_name, os.path.join(profile_dir, "timeseries_xyz.png"))
        plot_errors(data, profile_name, os.path.join(profile_dir, "error_xyz.png"))
        plot_xy(data, profile_name, os.path.join(profile_dir, "trajectory_xy.png"))
        plot_3d(data, profile_name, os.path.join(profile_dir, "trajectory_3d.png"))
        plot_shape_tracking(data, profile_name, os.path.join(profile_dir, "shape_tracking_xy.png"))
        rows.append(metrics)

    summary_rows = build_summary_rows(rows)
    write_summary_csv(summary_rows, os.path.join(run_dir, "summary.csv"))
    write_summary_markdown(summary_rows, os.path.join(run_dir, "summary.md"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze PX4 tracking run outputs")
    parser.add_argument("--run-dir", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    analyze_run(os.path.abspath(args.run_dir))


if __name__ == "__main__":
    main()
