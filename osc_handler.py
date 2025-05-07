import socket
import threading
import time

import pygame
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer
from pythonosc import udp_client

import utils
from cue_engine import ActiveCue, CueStatus
from qplayer_config import LoopMode
from utils import get_ip

OSC_MESSAGE = pygame.USEREVENT + 2


class OSCHandler:
    def __init__(self, ip="auto", rx_port=9000, tx_port=8000, name="osc_handler"):

        ip = get_ip(ip)

        self.ip = ip
        self.name = name
        self.rx_port = rx_port
        self.tx_port = tx_port
        self.dispatcher = Dispatcher()
        self.dispatcher.map(
            "/qplayer/remote/*", handler=self.qplayer_handler, needs_reply_address=True
        )

        self.dispatcher.set_default_handler(self.default_handler)
        self.server = BlockingOSCUDPServer(("0.0.0.0", rx_port), self.dispatcher)

        broadcast_addr = utils.get_broadcast(ip=self.ip)
        self.client = udp_client.SimpleUDPClient(
            address=broadcast_addr, port=tx_port, allow_broadcast=True
        )
        # self.client._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        print(f"Connected to OSC on {ip} (tx:{tx_port}) (rx:{rx_port})")

        self.last_update_time = time.time()
        self.received_showfile_chunks = {}

    def default_handler(self, address: str, *args):
        print(f"OSC Message Received: {address}, {args}")

    def qplayer_handler(self, client_address: list, address: str, *args):
        print(f"OSC Message: {address} {args}")
        if len(args) > 0:
            if args[0] == self.name:
                # For me
                address_parts = address.split("/")
                if len(address_parts) >= 3:
                    command = address_parts[3]
                    if command in ("go", "pause", "unpause", "stop", "preload"):
                        args = args[1:]
                        pygame.event.post(
                            pygame.event.Event(
                                OSC_MESSAGE, data={"command": command, "args": args}
                            )
                        )
                    elif command == "ping":
                        # Don't broadcast the pong
                        reply = udp_client.SimpleUDPClient(
                            client_address[0], self.tx_port
                        )
                        reply.send_message("/qplayer/remote/pong", self.name)
                    elif command == "update-show":
                        if len(args) == 4:
                            self.handle_showfile(
                                client_address, int(args[1]), int(args[2]), args[3]
                            )

    def handle_showfile(
        self,
        client_address: list,
        block_number: int,
        total_blocks: int,
        blob: bytes,
    ):

        self.received_showfile_chunks[block_number] = blob

        if len(self.received_showfile_chunks) == block_number + 1:
            # time.sleep(0.01)
            # Don't broadcast the ack
            reply = udp_client.SimpleUDPClient(client_address[0], self.tx_port)
            reply.send_message(
                "/qplayer/remote/update-show-ack", [self.name, block_number]
            )
        else:
            # Out of order receive
            self.received_showfile_chunks = {}
            reply = udp_client.SimpleUDPClient(client_address[0], self.tx_port)
            reply.send_message(
                "/qplayer/remote/update-show-nack", [self.name, block_number]
            )

        if len(self.received_showfile_chunks) == total_blocks:
            print(
                f"Received chunk {block_number+1}/{total_blocks} from {client_address[0]}:{self.tx_port}"
            )
            blob = b"".join(
                self.received_showfile_chunks[i] for i in range(total_blocks)
            )
            pygame.event.post(
                pygame.event.Event(
                    OSC_MESSAGE, data={"command": "update-show", "args": blob}
                )
            )
            self.received_showfile_chunks = {}

    def start_client_discovery(self):
        threading.Thread(target=self.client_beacon, daemon=True).start()

    def client_beacon(self):
        while True:
            # self.client.send_message("/qplayer/remote/discovery", self.name)
            # print(f"Beacon: {self.name}")
            time.sleep(1)

    def start_server(self):
        self.start_client_discovery()
        self.server.serve_forever()

    def osc_tick(self, cues: list[ActiveCue]):

        periodic_report = False

        if time.time() - self.last_update_time > 0.1:
            self.last_update_time = time.time()
            periodic_report = True

        for active_cue in cues:
            current_time = active_cue.position()
            cue_state = CueStatus.RUNNING
            if active_cue.cue.loopMode != LoopMode.OneShot:
                cue_state = CueStatus.LOOPING
            if active_cue.paused:
                cue_state = CueStatus.PAUSED
            if active_cue.complete:
                cue_state = CueStatus.COMPLETE
                current_time = 0

            if cue_state != active_cue.state_reported or (
                periodic_report and not (cue_state == 4 or active_cue.video_data.still)
            ):
                self.client.send_message(
                    "/qplayer/remote/fb/cue-status",
                    [self.name, active_cue.cue.qid, cue_state, current_time],
                )
                print(
                    f"Active Cue: {active_cue.cue.name}, state:{cue_state}, time: {current_time:.2f}"
                )
                active_cue.state_reported = cue_state
