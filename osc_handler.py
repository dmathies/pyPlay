import socket
import threading
import time

import pygame
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer
from pythonosc import udp_client

from cue_engine import ActiveCue
from qplayer_config import LoopMode

OSC_MESSAGE = pygame.USEREVENT + 2


class OSCHandler:
    def __init__(self, ip="127.0.0.1", rx_port=9000, tx_port = 8000, name="osc_handler"):

        if ip == "auto":
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]

        self.ip = ip
        self.name = name
        self.port = rx_port
        self.dispatcher = Dispatcher()
        self.dispatcher.map("/qplayer/remote/*", self.qplayer_handler)

        self.server = BlockingOSCUDPServer((ip, rx_port), self.dispatcher)
        self.client = udp_client.SimpleUDPClient("192.168.0.255", tx_port)
        self.last_update_time = time.time()
        self.received_showfile_chunks = {}

    def qplayer_handler(self, address:str, *args):
        print(f"OSC Message: {address} {args}")
        if len(args) > 0:
            if args[0] == self.name:
                # For me
                address_parts = address.split("/")
                if len(address_parts) >=3:
                    command = address_parts[3]
                    if command in ("go", "pause", "unpause", "stop", "preload"):
                        args = args[1:]
                        pygame.event.post(pygame.event.Event(OSC_MESSAGE, data={"command": command, "args": args}))
                    elif command == "ping":
                        self.client.send_message("/qplayer/remote/pong", self.name)
                    elif command == "update-show":
                        if len(args) == 4:
                            self.handle_showfile(int(args[1]), int(args[2]), args[3])

    def handle_showfile(self, block_number: int, total_blocks: int, blob: bytes):

        self.received_showfile_chunks[block_number] = blob
        print(f"Received chunk {block_number+1}/{total_blocks}")

        if len(self.received_showfile_chunks) == total_blocks:
            blob = b''.join(self.received_showfile_chunks[i] for i in range(total_blocks))
            pygame.event.post(pygame.event.Event(OSC_MESSAGE, data={"command": "update-show", "args": blob}))

        self.client.send_message("/qplayer/remote/update-show-ack", [self.name, block_number])

    def start_client_discovery(self):
        threading.Thread(target=self.client_beacon ,daemon=True).start()

    def client_beacon(self):
        while True:
            self.client.send_message("/qplayer/remote/discovery", self.name)
            print(f"Beacon: {self.name}")
            time.sleep(1)

    def start_server(self):
        self.start_client_discovery()
        self.server.serve_forever()

    def osc_tick(self, cues:[ActiveCue]):

        periodic_report = False

        if time.time() - self.last_update_time > 0.1:
            self.last_update_time = time.time()
            periodic_report = True

        for active_cue in cues:
            current_time =  active_cue.position()
            cue_state = 2
            if active_cue.cue.loopMode != LoopMode.OneShot: cue_state = 3
            if active_cue.paused: cue_state = 4
            if active_cue.complete: cue_state = 0

            if cue_state != active_cue.state_reported or (periodic_report and not (cue_state == 4 or active_cue.video_data.still)):
                self.client.send_message("/qplayer/remote/fb/cue-status", [self.name, active_cue.cue.qid, cue_state, current_time] )
                print(f"Active Cue: {active_cue.cue.name}, state:{cue_state}, time: {current_time:.2f}")
                active_cue.state_reported = cue_state