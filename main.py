import os
import platform
import shutil
import sys
import threading
from dataclasses import asdict

import pygame

from config_manager import ConfigManager
from cue_engine import CUE_EVENT
from cue_engine import CueEngine
from dmx_handler import DMXHandler
from http_handler import start_http_handler
from osc_handler import OSCHandler, OSC_MESSAGE
# from renderer import Renderer
from qplayer_config import load_qproj, Point, FramingShutter
from utils import call_method_by_name
from video_handler import VideoHandler, VideoData
from websocket_handler import WS_EVENT, WebSocketHandler

if len(sys.argv) > 1:
    cue_file = sys.argv[1]
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


def main():
    config = ConfigManager()
    qplayer_config = load_qproj(cue_file)

    renderer = Renderer()
    video_handler = VideoHandler()

    cue_engine = CueEngine(qplayer_config.cues, renderer, video_handler, base_path)

    mask_data = VideoData()
    load_video(cue_engine.resolve_path("Mask.jpg"), mask_data)
    mask_data.get_next_frame()
    black_video_data = VideoData()
    load_video(cue_engine.resolve_path("Black.jpg"), black_video_data)
    black_video_data.get_next_frame()

    renderer.set_background(black_video_data)
    renderer.set_mask(mask_data)

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
    start_http_handler("ui", port=8000)

    # threading.Thread(target=dmx_handler.start_listening, daemon=True).start()
    threading.Thread(target=osc_handler.start_server, daemon=True).start()

    running = True
    cue_engine.register_callback(osc_handler.osc_tick, args=osc_handler)

    print("pyPlay Started...")
    while running:
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
                cue_engine.active_cues.sort(key=lambda obj: obj.z_index)

            # elif event.type == DMX_EVENT:
            #   renderer.set_parameters(event.data)
            #   next_video = event.data.get("video_index")
            #
            #   if next_video>= len(video_playlist):
            #     next_video=len(video_playlist)-1
            #
            #   if current_video != next_video:
            #     .goto_cue(next_video)
            #     current_video=next_video
            #
            elif event.type == OSC_MESSAGE:
                if event.data["command"] == "update-show":
                    try:
                        cue_data = event.data["args"]
                        if os.path.exists(cue_file):
                            backup_path = cue_file + ".bak"
                            shutil.copy2(cue_file, backup_path)
                            print(f"Backup created at {backup_path}")

                        with open(cue_file, "wb") as f:
                            f.write(cue_data)
                            print(
                                f"Successfully wrote {len(cue_data)} bytes to {cue_file}"
                            )

                        qplayer_config = load_qproj(cue_file)
                        cue_engine.set_cues(qplayer_config.cues)

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

                    renderer.set_corners(corners=corners, alpha=1.0)
                elif data.get("shutters"):
                    shutters: list[FramingShutter] = ws_handler.shutters_to_framing_list(data)
                    renderer.set_framing(shutters, 1.0)
                elif data.get("status"):
                    page = data.get("status")

                    if page == "update":
                        ws_handler.send_to_clients(cue_engine.get_status())
                    elif page == "perspective":
                        ws_handler.send_to_clients({"corners": [asdict(p) for p in renderer.corners]})
                    elif page == "framing":
                        ws_handler.send_to_clients({"framing": [asdict(p) for p in renderer.framing]})

        renderer.render_frame(cue_engine.active_cues)
        cue_engine.tick()

    pygame.quit()


if __name__ == "__main__":
    main()
