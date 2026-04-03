from collections import deque
import os
import platform
import shutil
import sys
import threading
import json, time, glob
from dataclasses import asdict

import pygame

from config_manager import ConfigManager
from cue_engine import CUE_EVENT
from cue_engine import CueEngine
from dmx_handler import DMXHandler, DMX_EVENT
from http_handler import start_http_handler
from osc_handler import OSCHandler, OSC_MESSAGE
# from renderer import Renderer
from qplayer_config import load_qproj, load_qproj_from_bytes, Point, FramingShutter
from utils import call_method_by_name
from video_handler import VideoHandler, VideoData
from websocket_handler import WS_EVENT, WebSocketHandler
from ndi_output import NDIConfig, NDIOutput

USAGE_TEXT = """\
Usage:
  python main.py [options] [cue_file]

Options:
  --single-screen        Render to a single debug window.
  --no-post              Disable bloom/tonemap postprocessing.
  --profile              Print periodic render timing breakdowns.
  --show-fps             Show on-screen FPS overlay.
  --warp-mesh NxM        Set output warp mesh resolution, e.g. 16x16 or 8.
  --scene-scale S        Internal scene scale from 0.1 to 1.0, e.g. 0.8.
  --ndi                  Enable NDI output.
  --ndi-only             Hidden-window NDI-only mode. Implies --ndi and --single-screen.
  --ndi-name NAME        Set the NDI stream name.
  --ndi-size WxH         Downscale NDI output before sending, e.g. 320x180.
  --ndi-fps N            Limit NDI send rate, e.g. 10.
  --help                 Show this help text.

Profile environment variables:
  PYPLAY_BLOOM_PASSES    Bloom blur passes. Default: 6.
  PYPLAY_SHOW_FPS        Enable on-screen FPS overlay. Default: 0.
  PYPLAY_PROFILE_INTERVAL
                         Seconds between profile prints. Default: 1.0.
  PYPLAY_PROFILE_CUES    Include slowest per-cue timings. Default: 0.
  PYPLAY_PROFILE_GPU     Insert glFinish around measured stages. Default: 0.
  PYPLAY_NDI_DEBUG       Print NDI capture/send debug logs. Default: 0.
"""

args = sys.argv[1:]
if "--help" in args:
    print(USAGE_TEXT)
    raise SystemExit(0)

single_screen = False
if "--single-screen" in args:
    single_screen = True
    args = [a for a in args if a != "--single-screen"]

hidden_window = False
ndi_only = False
if "--ndi-only" in args:
    ndi_only = True
    hidden_window = True
    single_screen = True
    args = [a for a in args if a != "--ndi-only"]

disable_postprocess = False
if "--no-post" in args:
    disable_postprocess = True
    args = [a for a in args if a != "--no-post"]

profile_render = False
if "--profile" in args:
    profile_render = True
    args = [a for a in args if a != "--profile"]

show_fps_overlay = False
if "--show-fps" in args:
    show_fps_overlay = True
    args = [a for a in args if a != "--show-fps"]

warp_mesh = (16, 16)
if "--warp-mesh" in args:
    idx = args.index("--warp-mesh")
    if idx + 1 < len(args):
        mesh_value = args[idx + 1].lower()
        args = args[:idx] + args[idx + 2 :]
        try:
            if "x" in mesh_value:
                cols_text, rows_text = mesh_value.split("x", 1)
                warp_mesh = (max(1, int(cols_text)), max(1, int(rows_text)))
            else:
                size = max(1, int(mesh_value))
                warp_mesh = (size, size)
        except ValueError:
            warp_mesh = (16, 16)
    else:
        args = args[:idx]

scene_scale = 1.0
if "--scene-scale" in args:
    idx = args.index("--scene-scale")
    if idx + 1 < len(args):
        try:
            scene_scale = float(args[idx + 1])
        except ValueError:
            scene_scale = 1.0
        scene_scale = max(0.1, min(1.0, scene_scale))
        args = args[:idx] + args[idx + 2 :]
    else:
        args = args[:idx]

ndi_enabled = False
if "--ndi" in args:
    ndi_enabled = True
    args = [a for a in args if a != "--ndi"]
if ndi_only:
    ndi_enabled = True

ndi_name = "pyPlay NDI"
if "--ndi-name" in args:
    idx = args.index("--ndi-name")
    if idx + 1 < len(args):
        ndi_name = args[idx + 1]
        args = args[:idx] + args[idx + 2 :]
    else:
        args = args[:idx]

ndi_size = (0, 0)
if "--ndi-size" in args:
    idx = args.index("--ndi-size")
    if idx + 1 < len(args):
        size_value = args[idx + 1].lower()
        args = args[:idx] + args[idx + 2 :]
        try:
            width_text, height_text = size_value.split("x", 1)
            ndi_size = (max(1, int(width_text)), max(1, int(height_text)))
        except ValueError:
            ndi_size = (0, 0)
    else:
        args = args[:idx]

ndi_fps = 25
if "--ndi-fps" in args:
    idx = args.index("--ndi-fps")
    if idx + 1 < len(args):
        try:
            ndi_fps = max(1, int(args[idx + 1]))
        except ValueError:
            ndi_fps = 25
        args = args[:idx] + args[idx + 2 :]
    else:
        args = args[:idx]

if len(args) > 0:
    cue_file = args[0]
else:
    cue_file = "Cues.qproj"

base_path = os.path.dirname(cue_file)

if platform.system() == "Linux":
    # Force SDL2 to use EGL instead of GLX on X11.
    print("Linux EGL setup")
    os.environ["SDL_VIDEO_X11_FORCE_EGL"] = "1"
    os.environ["PYOPENGL_PLATFORM"] = "egl"
    os.environ["MESA_D3D12_DEFAULT_ADAPTER_NAME"] = "nvidia"
    os.environ["DISPLAY"] = ":0.0"

from pygame.locals import KEYDOWN, K_F11, K_SPACE

from renderer import Renderer

from video_handler import load_video

# --- Versioned mesh save/load utilities --------------------------------------
SAVE_DIR = "mesh_versions"
os.makedirs(SAVE_DIR, exist_ok=True)

def _serialize_grid(grid):
    # renderer.left_grid is [[(x,y), ...], ...]
    return [[[x, y] for (x, y) in row] for row in grid]


def _serialize_corners(corners):
    # corners is list[Point]
    return [{"x": c.x, "y": c.y} for c in corners]


def _next_version():
    versions = sorted(glob.glob(os.path.join(SAVE_DIR, "mesh_v*.json")))
    if not versions:
        return 1
    last = versions[-1]
    try:
        n = int(os.path.basename(last)[6:9])
    except Exception:
        n = len(versions) + 1
    return n + 1


def save_mesh_version(renderer):
    """Save current mesh + corner positions (not homography) to disk."""
    ver = _next_version()
    payload = {
        "version": ver,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "left_grid": _serialize_grid(renderer.left_grid),
        "right_grid": _serialize_grid(renderer.right_grid),
        "left_corners": _serialize_corners(renderer.left_corners),
        "right_corners": _serialize_corners(renderer.right_corners),
    }
    path = os.path.join(SAVE_DIR, f"mesh_v{ver:03d}.json")
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)
    # also write "latest"
    with open(os.path.join(SAVE_DIR, "mesh_latest.json"), "w") as f:
        json.dump(payload, f, indent=2)
    print(f"[mesh] saved {path}")
    return ver


def load_latest_mesh():
    path = os.path.join(SAVE_DIR, "mesh_latest.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None


def load_previous_mesh():
    versions = sorted(glob.glob(os.path.join(SAVE_DIR, "mesh_v*.json")))
    if len(versions) >= 2:
        prev_path = versions[-2]
        with open(prev_path) as f:
            return json.load(f)
    return None
# --------------------------------------------------


def main():
    print(f"PyPlay starting up in: {os.getcwd()}")

    config = ConfigManager()
    qplayer_config = load_qproj(cue_file)

    renderer = Renderer(
        single_screen=single_screen,
        hidden_window=hidden_window,
        enable_postprocess=not disable_postprocess,
        profile_render=profile_render,
        show_fps_overlay=show_fps_overlay,
        warp_mesh=warp_mesh,
        scene_scale=scene_scale,
        hidden_window_size=ndi_size if ndi_size != (0, 0) else (1280, 720),
    )
    video_handler = VideoHandler()
    ndi_output = NDIOutput(
        NDIConfig(
            enabled=ndi_enabled,
            name=ndi_name,
            width=ndi_size[0],
            height=ndi_size[1],
            fps=ndi_fps,
        )
    )

    cue_engine = CueEngine(
        qplayer_config.cues,
        renderer,
        video_handler,
        base_path,
        profile_enabled=profile_render,
    )

    mask_data = VideoData()
    load_video(cue_engine.resolve_path("Mask.jpg"), mask_data)
    mask_data.get_next_frame()
    black_video_data = VideoData()
    load_video(cue_engine.resolve_path("Black.jpg"), black_video_data)
    black_video_data.get_next_frame()

    renderer.set_background(black_video_data)
    # renderer.set_mask(mask_data)

    dmx_handler = DMXHandler(config.get_dmx_config(), config.get_ip_address())
    osc_handler = OSCHandler(
        ip=config.get_ip_address(),
        rx_port=config.get_osc_rx_port(),
        tx_port=config.get_osc_tx_port(),
        name=config.get_osc_name(),
    )

    # Start WebSocket server to receive UI updates
    ws_handler = WebSocketHandler()
    ws_handler.start()

    #
    # # Start HTTP server to serve PWA frontend (optional)
    start_http_handler("ui", port=8080)

    threading.Thread(target=dmx_handler.start_listening, daemon=True).start()
    threading.Thread(target=osc_handler.start_server, daemon=True).start()

    running = True
    cue_engine.register_callback(osc_handler.osc_tick, args=osc_handler)

    loaded_mesh = load_latest_mesh()
    if loaded_mesh:
        print(f"[mesh] reverting to v{loaded_mesh['version']}")
        # restore grids
        left_saved_rows = len(loaded_mesh["left_grid"])
        left_saved_cols = len(loaded_mesh["left_grid"][0]) if left_saved_rows else 0
        left_current_rows = len(renderer.left_grid)
        left_current_cols = len(renderer.left_grid[0]) if left_current_rows else 0
        if (left_saved_rows, left_saved_cols) != (left_current_rows, left_current_cols):
            print(
                f"[mesh] left grid size mismatch: saved={left_saved_cols}x{left_saved_rows} "
                f"current={left_current_cols}x{left_current_rows}; restoring overlap only"
            )
        for i, row in enumerate(loaded_mesh["left_grid"][:left_current_rows]):
            for j, (x, y) in enumerate(row[:left_current_cols]):
                renderer.update_vbo_vertex("left", i, j, x, y)

        right_saved_rows = len(loaded_mesh["right_grid"])
        right_saved_cols = len(loaded_mesh["right_grid"][0]) if right_saved_rows else 0
        right_current_rows = len(renderer.right_grid)
        right_current_cols = len(renderer.right_grid[0]) if right_current_rows else 0
        if (right_saved_rows, right_saved_cols) != (right_current_rows, right_current_cols):
            print(
                f"[mesh] right grid size mismatch: saved={right_saved_cols}x{right_saved_rows} "
                f"current={right_current_cols}x{right_current_rows}; restoring overlap only"
            )
        for i, row in enumerate(loaded_mesh["right_grid"][:right_current_rows]):
            for j, (x, y) in enumerate(row[:right_current_cols]):
                renderer.update_vbo_vertex("right", i, j, x, y)
        # restore corners (this recomputes homography)
        left_corners = [Point(c["x"], c["y"]) for c in loaded_mesh["left_corners"]]
        right_corners = [Point(c["x"], c["y"]) for c in loaded_mesh["right_corners"]]
        renderer.set_corners(left_corners, "left")
        renderer.set_corners(right_corners, "right")

        # # push back to all UIs
        # ws_handler.send_to_clients({
        #     "type": "mesh_data",
        #     "screen": "left",
        #     "points": loaded_mesh["left_grid"],
        #     "version": loaded_mesh["version"],
        # })
        # ws_handler.send_to_clients({
        #     "type": "mesh_data",
        #     "screen": "right",
        #     "points": loaded_mesh["right_grid"],
        #     "version": loaded_mesh["version"],
        # })
        # # also push corners so the perspective page can update
        # ws_handler.send_to_clients({
        #     "type": "perspective",
        #     "leftCorners": loaded_mesh["left_corners"],
        #     "rightCorners": loaded_mesh["right_corners"],
        # })

    # --- FPS tracking ---
    frame_times = deque(maxlen=120)  # keep last 120 frames (~2 seconds)
    last_fps_time = time.time()
    fps_print_interval = 2.0  # seconds between console prints

    print("pyPlay Started...")
    while running:
        try:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == KEYDOWN:
                    if event.key == pygame.K_ESCAPE or event.key == pygame.K_q:
                        running = False
                    elif event.key == K_F11:
                        pygame.display.toggle_fullscreen()
                    elif event.key == K_SPACE:
                        cue_engine.go("next")

                elif event.type == CUE_EVENT:  # New video
                    cue_engine.active_cues.append(event.data)
                    cue_engine.active_cues.sort(
                        key=lambda obj: (obj.z_index, getattr(obj, "cue_order", 0))
                    )

                elif event.type == DMX_EVENT:
                    universe = event.data.get("universe")
                    data = event.data.get("data")
                    if universe is not None and data is not None:
                        cue_engine.update_dmx_levels(int(universe), data)

                elif event.type == OSC_MESSAGE:
                    if event.data["command"] == "update-show":
                        try:
                            cue_data = event.data["args"]
                            if isinstance(cue_data, str):
                                cue_data = cue_data.encode("utf-8")

                            qplayer_config = load_qproj_from_bytes(cue_data)
                            applied_from_memory_only = False

                            if os.path.exists(cue_file):
                                backup_path = cue_file + ".bak"
                                try:
                                    shutil.copy2(cue_file, backup_path)
                                    print(f"Backup created at {backup_path}")
                                except Exception as e:
                                    applied_from_memory_only = True
                                    print(f"Error creating backup for cue file {e}")

                            try:
                                with open(cue_file, "wb") as f:
                                    f.write(cue_data)
                                    print(
                                        f"Successfully wrote {len(cue_data)} bytes to {cue_file}"
                                    )
                            except Exception as e:
                                applied_from_memory_only = True
                                print(f"Error writing to cue file {e}")

                            cue_engine.set_cues(qplayer_config.cues)
                            if applied_from_memory_only:
                                print("Applied update-show from in-memory payload only; disk file was not updated.")
                            else:
                                print("Applied update-show from disk and in-memory payload.")

                        except Exception as e:
                            print(f"Error during processing cue_file {e}")
                    else:
                        call_method_by_name(
                            cue_engine, event.data["command"], *event.data["args"]
                        )
                elif event.type == WS_EVENT:
                    data = event.data
                    print("Received from WebSocket:", data)
                    if data.get("corners"):
                        corners: list[Point] = [Point(x, y) for x, y in data["corners"]]
                        corners[2], corners[3] = corners[3], corners[2]
                        screen = data.get("screen", "left")
                        renderer.set_corners(corners=corners, screen=screen)
                    elif data.get("shutters"):
                        shutters: list[FramingShutter] = ws_handler.shutters_to_framing_list(data)
                        renderer.set_framing(shutters, 1.0)

                    elif data.get("type")=='mesh_request':
                        screen = data.get("screen")
                        grid = renderer.left_grid if screen == "left" else renderer.right_grid
                        # grid is 17x17 of (x,y)
                        points = [[[x, y] for (x, y) in row] for row in grid]
                        ws_handler.send_to_clients({
                            "type": "mesh_data",
                            "screen": screen,
                            "points": points,
                        })
                    elif data.get("type")=='mesh_update':
                        renderer.update_vbo_vertex(
                            data["screen"],
                            data["i"],
                            data["j"],
                            data["x"],
                            data["y"],
                        )
                    elif data.get("type")=='mesh_save':
                        ver = save_mesh_version(renderer)
                        ws_handler.send_to_clients({
                            "type": "mesh_saved",
                            "version": ver,
                        })

                    elif data.get("type") == "mesh_revert":
                        loaded_mesh = load_previous_mesh()
                        if not loaded_mesh:
                            ws_handler.send_to_clients({
                                "type": "mesh_error",
                                "error": "No previous version to revert to."
                            })
                        else:
                            print(f"[mesh] reverting to v{loaded_mesh['version']}")
                            # restore grids
                            for i, row in enumerate(loaded_mesh["left_grid"]):
                                for j, (x, y) in enumerate(row):
                                    renderer.update_vbo_vertex("left", i, j, x, y)
                            for i, row in enumerate(loaded_mesh["right_grid"]):
                                for j, (x, y) in enumerate(row):
                                    renderer.update_vbo_vertex("right", i, j, x, y)
                            # restore corners (this recomputes homography)
                            left_corners = [Point(c["x"], c["y"]) for c in loaded_mesh["left_corners"]]
                            right_corners = [Point(c["x"], c["y"]) for c in loaded_mesh["right_corners"]]
                            renderer.set_corners(left_corners, "left")
                            renderer.set_corners(right_corners, "right")

                            # push back to all UIs
                            ws_handler.send_to_clients({
                                "type": "mesh_data",
                                "screen": "left",
                                "points": loaded_mesh["left_grid"],
                                "version": loaded_mesh["version"],
                            })
                            ws_handler.send_to_clients({
                                "type": "mesh_data",
                                "screen": "right",
                                "points": loaded_mesh["right_grid"],
                                "version": loaded_mesh["version"],
                            })
                            # also push corners so the perspective page can update
                            ws_handler.send_to_clients({
                                "type": "perspective",
                                "leftCorners": loaded_mesh["left_corners"],
                                "rightCorners": loaded_mesh["right_corners"],
                            })

                    elif data.get("status"):
                        page = data.get("status")

                        if page == "update":
                            ws_handler.send_to_clients(cue_engine.get_status())
                        elif page == "perspective":
                            ws_handler.send_to_clients({
                                "type": "perspective",
                                "leftCorners":  [asdict(p) for p in renderer.left_corners],
                                "rightCorners": [asdict(p) for p in renderer.right_corners],
                            })
                        elif page == "framing":
                            ws_handler.send_to_clients({"framing": [asdict(p) for p in renderer.framing]})

            frame_for_ndi = renderer.render_frame(
                cue_engine.active_cues, capture_frame=ndi_output.enabled
            )
            if ndi_output.enabled:
                ndi_output.send_rgb_frame(frame_for_ndi)
            
            # --- FPS calculation ---
            now = time.time()
            frame_times.append(now)

            if len(frame_times) > 1:
                fps = len(frame_times) / (frame_times[-1] - frame_times[0])
                if now - last_fps_time >= fps_print_interval:
                    # print(f"[Renderer] FPS: {fps:5.1f}")
                    last_fps_time = now

            cue_engine.tick()

        except Exception as e:
            # Log and keep going instead of quitting the app
            print(f"[MAIN LOOP] Unhandled error: {e}")
            # Optional: you could also mark all active cues as "complete"
            # or trigger some "safe mode" here.

    ndi_output.close()
    pygame.quit()


if __name__ == "__main__":
    main()
