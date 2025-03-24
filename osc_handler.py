import socket
import pygame
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer

OSC_MESSAGE = pygame.USEREVENT + 2


class OSCHandler:
    def __init__(self, ip="127.0.0.1", port=9000):

        if ip == "auto":
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]

        self.ip = ip
        self.port = port
        self.dispatcher = Dispatcher()
        self.dispatcher.set_default_handler(self.default_handler)
        self.server = BlockingOSCUDPServer((ip, port), self.dispatcher)

    def default_handler(self, address, *args):
        print(f"OSC Message: {address} {args}")
        pygame.event.post(pygame.event.Event(OSC_MESSAGE, data={"go": True}))

    def start_server(self):
        self.server.serve_forever()
