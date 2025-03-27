import pygame
import ArtNet
import socket
import os
import numpy as np
from ArtNet.client import ArtNetClient
from ArtNet.helper import serialize_device_info, deserialize_device_info
from yaml import dump as yaml_dump
from yaml import safe_load

DMX_EVENT = pygame.USEREVENT + 1


class DMXHandler:
    def __init__(self, config, local_ip="auto"):
        self.dmx_state = {}

        if local_ip == "auto":
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]

        self.client = ArtNetClient(ip=local_ip)

        with open("device_config.json", "r") as f:
            json_output = f.read()

        self.DEVICE_INFO = deserialize_device_info(json_output)

        # Load configuration from file or use defaults
        config_file = "artnet_config.yml"
        if os.path.exists(config_file):
            with open(config_file, "r") as f:
                CONFIG = safe_load(f)
        else:
            CONFIG = {
                "net": 0,
                "sub": 0,
                "universe": 0,
                "port_name": "",
                "long_name": "",
            }

        self.client.set_config(CONFIG, self.DEVICE_INFO)
        self.config = CONFIG

    def dmx_receive(self, op_code, ip, port, reply):
        base_addr = (
            self.DEVICE_INFO[0]
            .get("parameters")
            .get(ArtNet.rdm.RdmParameterID.RdmParamDmxStartAddress)
        )
        uni = self.config.get("universe")
        net = self.config.get("net")
        sub = self.config.get("sub")

        universe = ArtNet.ArtNet.to_universe15bit(None, uni, net, sub)

        if reply.get("Universe") == universe:
            # DMX Message
            fade_time = reply.get("Data")[base_addr + 2] / 10.0
            if fade_time == 0:
                fade_time = 0.1

            event_data = {
                "dimmer": reply.get("Data")[base_addr - 1] / 255.0,
                "video_index": reply.get("Data")[base_addr],
                "video_mode": reply.get("Data")[base_addr + 1],
                "fade_time": fade_time,
                "scale": [
                    reply.get("Data")[base_addr + 3] / 128.0,
                    reply.get("Data")[base_addr + 4] / 128.0,
                ],
                "rotation": reply.get("Data")[base_addr + 5] / 255.0 * np.pi * 2,
                "offset": [
                    (reply.get("Data")[base_addr + 6] - 128.0) / 128.0,
                    (reply.get("Data")[base_addr + 7] - 128) / 128.0,
                ],
                "brightness": (reply.get("Data")[base_addr + 8]) / 256.0,
                "contrast": 1 - reply.get("Data")[base_addr + 9] / 256.0,
                "gamma": 1 + reply.get("Data")[base_addr + 10] / 64.0,
                "fr0_rotation": reply.get("Data")[base_addr + 11] / 256.0 * np.pi * 2,
                "fr0_maskStart": 1.5 - reply.get("Data")[base_addr + 12] / 200.0,
                "fr0_softness": reply.get("Data")[base_addr + 13] / 512.0,
                "fr1_rotation": reply.get("Data")[base_addr + 14] / 256.0 * np.pi * 2,
                "fr1_maskStart": 1.5 - reply.get("Data")[base_addr + 15] / 200.0,
                "fr1_softness": reply.get("Data")[base_addr + 16] / 512.0,
                "fr2_rotation": reply.get("Data")[base_addr + 17] / 256.0 * np.pi * 2,
                "fr2_maskStart": 1.5 - reply.get("Data")[base_addr + 18] / 200.0,
                "fr2_softness": reply.get("Data")[base_addr + 19] / 512.0,
                "fr3_rotation": reply.get("Data")[base_addr + 20] / 256.0 * np.pi * 2,
                "fr3_maskStart": 1.5 - reply.get("Data")[base_addr + 21] / 200.0,
                "fr3_softness": reply.get("Data")[base_addr + 22] / 512.0,
            }

            if self.dmx_state != event_data:
                self.dmx_state = event_data
                pygame.event.post(pygame.event.Event(DMX_EVENT, data=event_data))

    def rdm_callback(self, device_id: int, parameter_id: int, device_info: dict):
        print(device_id, parameter_id)
        json_output = serialize_device_info(device_info)
        with open("device_config.json", "w") as f:
            f.write(json_output)

    def config_changed_callback(self, config: dict):
        with open("artnet_config.yml", "w") as f:
            yaml_dump(config, f)

    def start_listening(self):
        self.client.artnet.subscribe(ArtNet.OpCode.ArtDmx, self.dmx_receive)
        self.client.register_rdm_config_callback(self.rdm_callback)
        self.client.register_config_callback(self.config_changed_callback)
        self.client.artnet.listen(timeout=30.0)
