import queue
import re
import socket
import threading
from time import sleep

import pythonosc
from pythonosc.osc_message_builder import OscMessageBuilder
from pythonosc.udp_client import SimpleUDPClient
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer

from utils import get_ip, get_broadcast


class OSCTester:

    def __init__(self, ip="127.0.0.1", rx_port=8000, tx_port=9000, name="Video1"):
        self.ack_queue = queue.Queue()

        self.max_retries = 5
        self.timeout = 1.0
        self.chunk_size = 1024

        ip = get_ip()
        print(f"OSC Tester: ip{ip}, rx:{rx_port}, tx:{tx_port}")
        self.ip = ip
        self.broadcast_addr = get_broadcast(ip)
        self.name = name
        self.rx_port = rx_port
        self.tx_port = tx_port
        self.dispatcher = Dispatcher()
        self.dispatcher.set_default_handler(self.default_handler)
        BlockingOSCUDPServer.allow_reuse_ports = True
        BlockingOSCUDPServer.allow_reuse_address = True
        SimpleUDPClient.allow_reuse_address = True

        self.server = BlockingOSCUDPServer(("0.0.0.0", self.rx_port), self.dispatcher)

        self.client = SimpleUDPClient(
            address=get_broadcast(ip), port=self.tx_port, allow_broadcast=True
        )

    def main(self):
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        while True:
            print("Command> ", end="")
            input1 = re.split(r"[ ,|;]\s*", input())
            command = input1[0].strip()
            if command == "exit":
                break
            args = [item.strip() for item in input1[1:]]
            if command == "update-show":
                self.send_file()
            else:
                self.client.send_message(
                    f"/qplayer/remote/{command}", [self.name] + args
                )

    def _send_chunk(self, index, total_chunks, chunk_data):
        msg = OscMessageBuilder(address="/qplayer/remote/update-show")
        msg.add_arg(self.name)
        msg.add_arg(index)
        msg.add_arg(total_chunks)
        msg.add_arg(chunk_data, arg_type="b")
        self.client.send(msg.build())
        # sleep(1)

    def send_file(self):
        self.dispatcher.map("/qplayer/remote/update-show-ack", self.ack_handler)
        with open("Cues.qproj", "rb") as f:
            data = f.read()

        total_chunks = (len(data) + self.chunk_size - 1) // self.chunk_size

        for i in range(total_chunks):
            chunk = data[i * self.chunk_size : (i + 1) * self.chunk_size]
            retries = 0

            while retries < self.max_retries:
                self._send_chunk(i, total_chunks, chunk)
                # print(f"Sent chunk {i+1}/{total_chunks}, waiting for ACK...")

                try:
                    while self.ack_queue.get(timeout=self.timeout) != i:
                        pass
                    # print(f"ACK received for chunk {i}")
                except queue.Empty:
                    retries += 1
                    print(f"Retrying chunk {i}, attempt {retries}")
                break

            if retries == self.max_retries:
                print(f"Failed to send chunk {i} after {self.max_retries} retries.")

                self.dispatcher.unmap(
                    "/qplayer/remote/update-show-ack", self.ack_handler
                )
                return False

        print("File sent successfully.")
        self.dispatcher.unmap("/qplayer/remote/update-show-ack", self.ack_handler)

        return True

    def ack_handler(self, address: str, *args):
        # print (f"OSC ACK Message Received: {address}, {args}")
        if len(args) == 2 and args[0] == self.name:
            self.ack_queue.put(int(args[1]))

    def default_handler(self, address: str, *args):
        print(f"OSC Message Received: {address}, {args}")


if __name__ == "__main__":
    OSCTester(ip="auto").main()
