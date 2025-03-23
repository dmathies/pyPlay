import os
from threading import Thread
from typing import Any
from yaml import safe_load
from artnet import OpCode
from ArtNet.client import  ArtNetClient
from ArtNet.helper import serialize_device_info, deserialize_device_info


DEVICE_INFO = []

def poll_reply(op_code: OpCode, ip: str, port: int, reply: dict[str, Any]) -> None:
    print(f"Received {op_code.name} from {ip}:{port}")

def other_artnet(op_code: OpCode, ip: str, port: int, reply: dict[str, Any]) -> None:
    print(f"Received {op_code.name} from {ip}:{port}")

    for k, v in reply.items():
        print(f"\t{k} = {v}")

CONFIG:dict = {}

def main():

    global DEVICE_INFO, CONFIG

    client : ArtNetClient = ArtNetClient(ip="192.168.0.208")

    with open("device_config.json", "r") as f:
        json_output = f.read()

    DEVICE_INFO = deserialize_device_info(json_output)

    print(f"DEVICE_INFO configuration updated: {json_output}")

    # Load configuration from file or use defaults
    config_file = "artnet_config.yml"
    if os.path.exists(config_file):
        with open(config_file, "r") as f:
            CONFIG = safe_load(f)
    else:
        CONFIG = {"net": 0, "sub": 0, "universe": 0, "port_name": "", "long_name": ""}

    client.set_config(CONFIG, DEVICE_INFO)
    client.register_rdm_config_callback(rdm_callback)


    #artnet.subscribe(OpCode.ArtPollReply, poll_reply)
    #artnet.subscribe_other(other_artnet)

    x = Thread(target=client.artnet.listen, kwargs=dict(timeout=30.0))
    x.start()

    client.artnet.send_poll()

    x.join()

def rdm_callback(device_id:int, parameter_id: int):
    print(device_id, parameter_id)
    json_output = serialize_device_info(DEVICE_INFO)
    with open("device_config.json", "w") as f:
        f.write(json_output)


import yaml

def config_changed_callback():
    with open("artnet_config.yml", "w") as f:
        yaml.dump(CONFIG, f)
    print("")

if __name__ == "__main__":
    main()
