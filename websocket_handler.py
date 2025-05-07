import pygame
import threading
import asyncio
import json
import websockets
from websockets.legacy.server import WebSocketServerProtocol

from qplayer_config import FramingShutter

# Custom Pygame event
WS_EVENT = pygame.USEREVENT + 4


class WebSocketHandler:
    def __init__(self, host="0.0.0.0", port=8765):
        self.host = host
        self.port = port
        self.clients = set()
        self.loop = None  # Will hold event loop reference

    def start(self):
        """Start the websocket server in its own thread."""
        def thread_entry():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_until_complete(self.run_server())

        threading.Thread(target=thread_entry, daemon=True).start()

    async def handler(self, websocket: WebSocketServerProtocol):
        self.clients.add(websocket)
        try:
            async for message in websocket:
                data = json.loads(message)
                event = pygame.event.Event(WS_EVENT, {"data": data})
                pygame.event.post(event)
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self.clients.remove(websocket)

    async def run_server(self):
        async with websockets.serve(self.handler, self.host, self.port):  # type: ignore
            await asyncio.Future()  # run forever

    def send_to_clients(self, message: dict):
        """Call this from any thread (e.g. main.py) to send a message."""
        if self.loop is not None:
            asyncio.run_coroutine_threadsafe(self._broadcast(message), self.loop)

    async def _broadcast(self, message: dict):
        msg = json.dumps(message)
        # print(f"[WS] Clients: {self.clients}")
        print(f"Broadcasting to {len(self.clients)} clients:", msg)
        for i, ws in enumerate(self.clients):
            try:
                await ws.send(msg)
                # print(f"[WS] Sent to client {i}")
            except Exception as e:
                print(f"[WS] Failed to send to client {i}: {e}")

        # await asyncio.gather(*(ws.send(msg) for ws in self.clients if ws.open))

    @staticmethod
    def shutters_to_framing_list(data: dict) -> list[FramingShutter]:
        shutters = data["shutters"]
        order = ["right", "top", "left", "bottom"]
        return [
            FramingShutter(
                rotation=-shutters[side]["angle"],
                maskStart=shutters[side]["in"] / 100.0,
                softness=shutters[side]["softness"]
            )
            for side in order
        ]
