import os
import shutil

import numpy as np
import pygame
import threading

from pygame.locals import KEYDOWN, K_F11, K_SPACE

from config_manager import ConfigManager
from cue_engine import CueEngine
from utils import call_method_by_name
from video_handler import VideoHandler
from dmx_handler import DMXHandler, DMX_EVENT
from osc_handler import OSCHandler, OSC_MESSAGE
from cue_engine import ActiveCue, CUE_EVENT
from renderer import Renderer
from qplayer_config import load_qproj

cue_file = "Cues.qproj"

def main():
    config = ConfigManager()
    qplayer_config = load_qproj(cue_file)
    video_handler = VideoHandler()
    renderer = Renderer()

    cue_engine = CueEngine(qplayer_config.cues, renderer, video_handler)

    dmx_handler = DMXHandler(config.get_dmx_config(), config.get_ip_address())
    osc_handler = OSCHandler(ip=config.get_ip_address(), rx_port=config.get_osc_rx_port(), tx_port=config.get_osc_tx_port(), name=config.get_osc_name())

    # threading.Thread(target=dmx_handler.start_listening, daemon=True).start()
    threading.Thread(target=osc_handler.start_server, daemon=True).start()

    running = True
    cue_engine.register_callback(osc_handler.osc_tick, args=osc_handler)

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
                            print(f"Successfully wrote {len(cue_data)} bytes to {cue_file}")

                        qplayer_config = load_qproj(cue_file)
                        cue_engine.set_cues(qplayer_config.cues)

                    except Exception as e:
                        print(f"Error during processing cue_file {e}")
                else:
                    call_method_by_name(cue_engine, event.data["command"],*event.data["args"])

        renderer.render_frame(cue_engine.active_cues)
        cue_engine.tick()

    pygame.quit()

if __name__ == "__main__":
    main()
