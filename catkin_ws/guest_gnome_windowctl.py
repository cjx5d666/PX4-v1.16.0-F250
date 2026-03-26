#!/usr/bin/env python3

import argparse
import ast
import json
import subprocess
import sys
import time


DBUS_ADDR = "unix:path=/run/user/1000/bus"


def parse_eval_output(raw: str):
    if not (raw.startswith("(") and raw.endswith(")")):
        raise RuntimeError(f"Unexpected gdbus output: {raw}")
    inner = raw[1:-1]
    try:
        ok_token, value_token = inner.split(", ", 1)
    except ValueError as exc:
        raise RuntimeError(f"Unexpected gdbus output: {raw}") from exc
    ok = ok_token.strip().lower() == "true"
    try:
        value = ast.literal_eval(value_token.strip())
    except Exception as exc:
        raise RuntimeError(f"Unexpected gdbus output: {raw}") from exc
    if isinstance(value, str) and len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        try:
            value = ast.literal_eval(value)
        except Exception:
            pass
    if not ok:
        raise RuntimeError(f"GNOME Shell Eval failed: {value}")
    return value


def shell_eval(js: str):
    cmd = [
        "gdbus",
        "call",
        "--session",
        "--dest",
        "org.gnome.Shell",
        "--object-path",
        "/org/gnome/Shell",
        "--method",
        "org.gnome.Shell.Eval",
        js,
    ]
    env = dict(subprocess.os.environ)
    env["DBUS_SESSION_BUS_ADDRESS"] = DBUS_ADDR
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return parse_eval_output(result.stdout.strip())


def find_window_expr(query: str) -> str:
    q = json.dumps(query)
    return f"""
global.get_window_actors()
  .map(actor => actor.meta_window)
  .find(w => {{
    const title = w.get_title() || "";
    const klass = w.get_wm_class() || "";
    return title.includes({q}) || klass.includes({q});
  }})
""".strip()


def list_windows():
    js = """
JSON.stringify(
  global.get_window_actors().map(actor => {
    const w = actor.meta_window;
    const r = w.get_frame_rect();
    return {
      title: w.get_title(),
      wmclass: w.get_wm_class(),
      x: r.x,
      y: r.y,
      width: r.width,
      height: r.height,
      maximized_h: w.maximized_horizontally,
      maximized_v: w.maximized_vertically
    };
  })
)
""".strip()
    print(json.dumps(json.loads(shell_eval(js)), ensure_ascii=False, indent=2))


def tile_window(query: str, half: str):
    side = "left" if half == "left" else "right"
    js = f"""
const Meta = imports.gi.Meta;
const Main = imports.ui.main;
const win = {find_window_expr(query)};
if (!win) {{
  "NOT_FOUND";
}} else {{
  const monitor = win.get_monitor();
  const area = Main.layoutManager.getWorkAreaForMonitor(monitor);
  win.unmaximize(Meta.MaximizeFlags.BOTH);
  const targetX = { 'area.x' if side == 'left' else 'area.x + Math.floor(area.width / 2)' };
  const targetW = Math.floor(area.width / 2);
  win.move_resize_frame(true, targetX, area.y, targetW, area.height);
  win.activate(global.get_current_time());
  "OK";
}}
""".strip()
    print(shell_eval(js))


def wait_for_window(query: str, timeout: float):
    deadline = time.time() + timeout
    js = f"""
const win = {find_window_expr(query)};
win ? "FOUND" : "MISSING";
""".strip()
    while time.time() < deadline:
        raw = shell_eval(js)
        if raw == "FOUND":
            print(raw)
            return
        time.sleep(1.0)
    raise SystemExit(1)


def activate_window(query: str):
    js = f"""
const win = {find_window_expr(query)};
if (!win) {{
  "NOT_FOUND";
}} else {{
  win.activate(global.get_current_time());
  "OK";
}}
""".strip()
    print(shell_eval(js))


def close_window(query: str):
    js = f"""
const win = {find_window_expr(query)};
if (!win) {{
  "NOT_FOUND";
}} else {{
  win.delete(global.get_current_time());
  "OK";
}}
""".strip()
    print(shell_eval(js))


def main():
    parser = argparse.ArgumentParser(description="GNOME Shell window helper for PX4 GUI recording flows")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list")

    p_wait = sub.add_parser("wait")
    p_wait.add_argument("query")
    p_wait.add_argument("--timeout", type=float, default=60.0)

    p_tile = sub.add_parser("tile")
    p_tile.add_argument("query")
    p_tile.add_argument("--half", choices=["left", "right"], required=True)

    p_activate = sub.add_parser("activate")
    p_activate.add_argument("query")

    p_close = sub.add_parser("close")
    p_close.add_argument("query")

    args = parser.parse_args()

    if args.cmd == "list":
        list_windows()
    elif args.cmd == "wait":
        wait_for_window(args.query, args.timeout)
    elif args.cmd == "tile":
        tile_window(args.query, args.half)
    elif args.cmd == "activate":
        activate_window(args.query)
    elif args.cmd == "close":
        close_window(args.query)


if __name__ == "__main__":
    main()
