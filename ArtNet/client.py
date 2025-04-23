import struct
from typing import Callable, Any, Optional

from ArtNet import ArtNet
from ArtNet.rdm import parse_rdm, RdmCommandClass, pack_rdm
from .helper import (
    OpCode,
    unpack_data,
    pack_data,
)
from .rdm import RdmParameterID

type DeviceInfo = list[dict[str, Any]]

ART_NET_PORT = 6454


class ArtNetClient:
    def __init__(self, ip: str = "<broadcast>", port: int = ART_NET_PORT) -> None:

        self.config_update_callback: Optional[Callable] = None
        self.rdm_update_callback: Optional[Callable[[int, int, DeviceInfo], None]] = (
            None
        )
        self.DEVICE_INFO: DeviceInfo = []
        self.config: dict[str, Any] = {}

        self.RDM_PARAMETER_GETTERS = {
            RdmParameterID.RdmParamDeviceInfo: self.RdmGetDeviceInfo,
            RdmParameterID.RdmParamSupportedParameters: self.RdmParamSupportedParameters,
            RdmParameterID.RdmParamParameterDescription: self.RdmParamParameterDescription,
            RdmParameterID.RdmParamDmxPersonality: self.RdmParamPersonality,
            RdmParameterID.RdmParamDmxPersonalityDescription: self.RdmParamPersonalityDescription,
            RdmParameterID.RdmParamSlotInfo: self.RdmParamSlotInfo,
            RdmParameterID.RdmParamSlotDescription: self.RdmParamSlotDescription,
            RdmParameterID.RdmParamDefaultSlotValue: self.RdmParamDefaultSlotValue,
        }

        self.RDM_PARAMETER_TYPES = {
            RdmParameterID.RdmParamManufacturerLabel: "32s",
            RdmParameterID.RdmParamDeviceLabel: "32s",
            RdmParameterID.RdmParamDeviceModelDescription: "32s",
            # RdmParameterID.RdmParamDmxPersonalityDescription: {"get": "B,>H,32s", "getIdx": "B"},
            RdmParameterID.RdmParamDmxPersonality: "B",
            RdmParameterID.RdmParamDeviceHours: ">I",
            RdmParameterID.RdmParamLampStrikes: ">I",
            RdmParameterID.RdmParamLampState: "B",
            RdmParameterID.RdmParamLampHours: ">I",
            RdmParameterID.RdmParamCurve: ">H",
            RdmParameterID.RdmParamModulationFrequency: "B,B",
            RdmParameterID.RdmParamDmxStartAddress: ">H",
            RdmParameterID.RdmParamLanguageCapabilities: "[2s]",
            RdmParameterID.RdmParamLanguage: "2s",
            RdmParameterID.RdmParamSoftwareVersionLabel: "32s",
            RdmParameterID.RdmParamBootSoftwareVersionId: ">H",
            RdmParameterID.RdmParamBootSoftwareVersionLabel: "32s",
        }

        self.RDM_PARAMETER_DATATYPES = ["", "B", "s", "B", "B", ">H", ">H", ">I", ">I"]

        self.RDM_PARAMETER_SETTERS: dict[RdmParameterID, Callable] = {}

        self.artnet: ArtNet = ArtNet(ip)

        # Register ArtAddress handler so that configuration can be updated via ArtAddress packets.
        self.artnet.subscribe(OpCode.ArtAddress, self.handle_art_address)
        self.artnet.subscribe(OpCode.ArtPoll, self.handle_poll_request)

    def __del__(self) -> None:
        self.artnet.__del__()

    def set_config(self, config: dict[str, Any], rdm_devices=None) -> None:
        self.config = config
        if rdm_devices is not None:
            self.DEVICE_INFO = rdm_devices
            self.artnet.subscribe(OpCode.ArtRdm, self.handle_rdm_request)
            self.artnet.subscribe(OpCode.ArtTodRequest, self.handle_tod_request)

    def register_rdm_config_callback(
        self, callback: Callable[[int, int, DeviceInfo], None]
    ) -> None:
        self.rdm_update_callback = callback

    def register_config_callback(self, callback: Callable) -> None:
        self.config_update_callback = callback

    def handle_poll_request(
        self, op_code: OpCode, ip: str, port: int, reply: dict[str, Any]
    ) -> None:
        self.artnet.send_poll_reply(ip, port, self.config)

    def handle_tod_request(
        self, op_code: OpCode, ip: str, port: int, reply: dict[str, Any]
    ) -> None:
        print(f"Received {op_code.name} from {ip}:{port}")
        uids: list[int] = []
        for dev in self.DEVICE_INFO:
            device_id = dev.get("id", -1)
            # Pack it as a 48-bit big-endian value
            uids.append(device_id)

        self.artnet.send_tod_data(ip, port, self.config, uids)

    def get_device_by_id(self, device_id):
        for device in self.DEVICE_INFO:
            if device["id"] == device_id:
                return device
        return None  # Return None if no matching device is found

    def RdmGetDeviceInfo(self, uid, data: bytes = b"") -> bytes:
        device = self.get_device_by_id(uid)
        if device is None:
            return b""

        current_personality_id = device["parameters"][
            RdmParameterID.RdmParamDmxPersonality
        ]
        current_personality = device.get("dmx_personalities", [])[
            current_personality_id - 1
        ]

        packet = (
            struct.pack(">H", 0x01)
            + struct.pack(">H", device["model"])
            + struct.pack(">H", device["category"])
            + struct.pack(">I", device["sw_version"])  # SW Version
            + struct.pack(">H", current_personality.get("slots", 0))  # DMX Footprint
            + struct.pack("B", current_personality_id)  # DMX Personality
            + struct.pack(
                "B", len(device.get("dmx_personalities", []))
            )  # DMX Personality count
            + struct.pack(
                ">H", device["parameters"][RdmParameterID.RdmParamDmxStartAddress]
            )
            + struct.pack(">H", device["DMX Sub Device Count"])  # DMX Sub Device Count
            + struct.pack("B", device["sensor_count"])  # Sensor Count
        )
        return packet

    def RdmGetDeviceParam(self, uid, param_id, data: bytes = b"") -> bytes:
        device = self.get_device_by_id(uid)
        custom_parameter = self.get_param_by_id(uid, param_id)

        if device is not None and custom_parameter is not None:
            data_type = self.RDM_PARAMETER_DATATYPES[custom_parameter.get("data_type")]

            data_size = custom_parameter.get("size")
            item_size = struct.calcsize(data_type)

            if data_type == "s":
                data_type = "" + data_size + data_type
            elif data_size > item_size:  # it's an array
                data_type = "[" + data_type + "]"
            parameter = custom_parameter.get("value")

            return pack_data(data_type, parameter)

        else:
            data_type = self.RDM_PARAMETER_TYPES.get(param_id)

            try:
                if data_type is not None:
                    parameter = device["parameters"][param_id]
                    if isinstance(data_type, dict):
                        index = data_type.get("getIdx")
                        if index is not None:
                            index_val = unpack_data(index, data)[0]
                            parameter = device["parameters"][param_id][index_val]

                        data_type = data_type.get("get")

                    return pack_data(data_type, parameter)
            except:
                pass

            return b""

    def RdmSetDeviceParam(self, uid, param_id, data: bytes = b"") -> bytes:
        device = self.get_device_by_id(uid)
        custom_parameter = self.get_param_by_id(uid, param_id)

        if custom_parameter is not None:
            data_type = self.RDM_PARAMETER_DATATYPES[custom_parameter.get("data_type")]
            data_size = custom_parameter.get("size")
            item_size = struct.calcsize(data_type)

            if data_type == "s":
                data_type = "" + data_size + data_type
            elif data_size > item_size:  # it's an array
                data_type = "[" + data_type + "]"

            custom_parameter["value"] = unpack_data(data_type, data)

        else:
            data_type = self.RDM_PARAMETER_TYPES.get(param_id)
            index = None
            index_val = 0

            if data_type is not None:
                parameter = device["parameters"][param_id]
                if isinstance(data_type, dict):
                    index = data_type.get("setSlot")
                    if index is not None:
                        index_val = index
                    data_type = data_type.get("set")

            if data_type is not None:
                argument = unpack_data(data_type, data)

                try:
                    if index is not None:
                        if isinstance(
                            device["parameters"][param_id][index_val], (list, tuple)
                        ):
                            device["parameters"][param_id][index_val] = argument
                        else:
                            device["parameters"][param_id][index_val] = argument[0]
                    else:
                        if isinstance(device["parameters"][param_id], (list, tuple)):
                            device["parameters"][param_id] = argument
                        else:
                            device["parameters"][param_id] = argument[0]

                except KeyError:
                    pass

        if self.rdm_update_callback:
            self.rdm_update_callback(uid, param_id, self.DEVICE_INFO)

        return b""

        # RdmParameterID.RdmParamDmxPersonalityDescription: self.RdmParamPersonalityDescription,

    def RdmParamPersonality(self, uid, data: bytes = b"") -> bytes:
        device = self.get_device_by_id(uid)
        packet = []
        personality_count = len(device.get("dmx_personalities", []))
        packet.append(
            struct.pack(
                "B", device["parameters"][RdmParameterID.RdmParamDmxPersonality]
            )
        )
        packet.append(struct.pack("B", personality_count))

        return b"".join(packet)

    def RdmParamPersonalityDescription(self, uid, data: bytes = b"") -> bytes:
        device = self.get_device_by_id(uid)

        packet = []
        try:
            personality_id = struct.unpack("B", data[0:1])[0]
            personality = device.get("dmx_personalities", [])[personality_id - 1]

            packet.append(struct.pack("B", personality_id))
            packet.append(struct.pack(">H", personality.get("slots")))
            packet.append(
                struct.pack("32s", bytes(personality.get("name", ""), "ascii"))
            )
        except (KeyError, IndexError):
            pass

        return b"".join(packet)

    def RdmParamSlotInfo(self, uid, data: bytes = b"") -> bytes:
        device = self.get_device_by_id(uid)
        current_personality_id = device["parameters"][
            RdmParameterID.RdmParamDmxPersonality
        ]
        current_personality = device.get("dmx_personalities", [])[
            current_personality_id - 1
        ]

        packet = []

        for dev in current_personality.get("slot_descriptions", []):
            packet.append(struct.pack(">H", dev.get("offset")))
            packet.append(struct.pack("B", dev.get("type")))
            packet.append(struct.pack(">H", dev.get("label_id")))

        return b"".join(packet)

    def RdmParamDefaultSlotValue(self, uid, data: bytes = b"") -> bytes:
        device = self.get_device_by_id(uid)
        current_personality_id = device["parameters"][
            RdmParameterID.RdmParamDmxPersonality
        ]
        current_personality = device.get("dmx_personalities", [])[
            current_personality_id - 1
        ]

        packet = []

        for dev in current_personality.get("slot_descriptions", []):
            packet.append(struct.pack(">H", dev.get("offset")))
            packet.append(struct.pack("B", dev.get("default_value", 0)))

        return b"".join(packet)

    def RdmParamSlotDescription(self, uid, data: bytes = b"") -> bytes:
        device = self.get_device_by_id(uid)
        current_personality_id = device["parameters"][
            RdmParameterID.RdmParamDmxPersonality
        ]
        current_personality = device.get("dmx_personalities", [])[
            current_personality_id - 1
        ]

        slot = struct.unpack(">H", data[0:2])[0]

        packet = []

        for dev in current_personality.get("slot_descriptions", []):
            if slot == dev.get("offset"):
                packet.append(struct.pack(">H", dev.get("offset")))
                packet.append(struct.pack("32s", bytes(dev.get("label", ""), "ascii")))

        return b"".join(packet)

    def RdmParamSupportedParameters(self, uid, data: bytes = b"") -> bytes:
        device = self.get_device_by_id(uid)
        packet = []

        for dev in device.get("custom_parameters", []):
            packet.append(struct.pack(">H", dev.get("id")))

        return b"".join(packet)

    def get_param_by_id(self, uid, param_id):

        device = self.get_device_by_id(uid)
        if device is None:
            return None

        for param in device.get("custom_parameters", []):
            if param["id"] == param_id:
                return param
        return None  # Return None if no matching device is found

    def RdmParamParameterDescription(self, uid, data: bytes = b"") -> bytes:
        param = struct.unpack(">H", data[0:2])[0]
        parameter = self.get_param_by_id(uid, param)

        return (
            struct.pack(">H", param)
            + struct.pack("B", parameter.get("size", 0))
            + struct.pack("B", parameter.get("data_type", 0))
            + struct.pack("B", parameter.get("command_classes", 0))
            + struct.pack("B", parameter.get("type", 0))
            + struct.pack("B", parameter.get("unit", 0))
            + struct.pack("B", parameter.get("prefix", 0))
            + struct.pack(">I", parameter.get("min_value", 0))  # Min Value
            + struct.pack(">I", parameter.get("max_value", 0))  # Max Value
            + struct.pack(">I", parameter.get("default_value", 0))  # Default Value
            + struct.pack("32s", bytes(parameter.get("name", 0), "ascii"))
        )

    def handle_rdm_request(
        self, op_code: OpCode, ip: str, port: int, packet: bytes
    ) -> None:
        # print(f"Received {op_code.name} (request) from {ip}:{port}")

        request = parse_rdm(bytes(packet))

        if request is None:
            return

        # for k, v in request.items():
        #   print(f"\t{k} = {v}")

        command = request["RdmCommand"]
        parameter_id: RdmParameterID = request["RdmParameterId"]

        # print(f"\tRdmCommand= {request.get('RdmCommand').name}")
        # print(f"\tRdmParameterID= {request.get('RdmParameterId').name}")

        reply = None

        if command == RdmCommandClass.RdmGetCommand:
            getter = self.RDM_PARAMETER_GETTERS.get(parameter_id)
            if getter is not None:
                reply = getter(request["RdmDestUID"], request["RdmParameterData"])
            else:
                reply = self.RdmGetDeviceParam(
                    request["RdmDestUID"],
                    request["RdmParameterId"],
                    request["RdmParameterData"],
                )

        if command == RdmCommandClass.RdmSetCommand:
            setter = self.RDM_PARAMETER_SETTERS.get(parameter_id)
            if setter is not None:
                reply = setter(
                    request["RdmDestUID"],
                    request["RdmParameterId"],
                    request["RdmParameterData"],
                )
            else:
                reply = self.RdmSetDeviceParam(
                    request["RdmDestUID"],
                    request["RdmParameterId"],
                    request["RdmParameterData"],
                )

        if reply is not None:
            response = request

            RdmSourceUID = response["RdmDestUID"]
            response["RdmDestUID"] = response["RdmSourceUID"]
            response["RdmSourceUID"] = RdmSourceUID

            response["RdmTransactioNumber"] = (
                response["RdmTransactioNumber"] + 1
            ) & 0xFF
            if command == RdmCommandClass.RdmGetCommand:
                response["RdmCommand"] = RdmCommandClass.RdmGetCommandResponse
            else:
                response["RdmCommand"] = RdmCommandClass.RdmSetCommandResponse

            response["RdmParameterDataLength"] = len(reply)
            response["RdmParameterData"] = reply

            self.artnet.send_rdm(ip, port, self.config, pack_rdm(response))

    def handle_art_address(
        self, op_code: OpCode, ip: str, port: int, reply: dict[str, Any]
    ) -> None:
        """
        Handle an ArtAddress packet to update node configuration.
        Expects data to contain:
          - net (1 byte)
          - sub (1 byte)
          - universe (1 byte)
          - port_name (18 bytes, null-terminated)
          - long_name (64 bytes, null-terminated)
        The new configuration is then saved to a local YAML file.
        """
        try:
            print(f" art_address Received {op_code.name} (request) from {ip}:{port}")

            cfg = self.config
            net = (
                cfg.get("net", 0)
                if reply["NetSwitch"] & 0x80 == 0
                else reply["NetSwitch"] & 0x7F
            )
            sub = (
                cfg.get("sub", 0)
                if reply["SubSwitch"] & 0x80 == 0
                else reply["SubSwitch"] & 0x7F
            )
            universe = (
                cfg.get("universe", 0)
                if reply["SwOut"][0] & 0x80 == 0
                else reply["SwOut"][0] & 0xF
            )
            port_name = (
                cfg.get("port_name", "")
                if len(reply["ShortName"]) == 0
                else reply["ShortName"]
            )
            long_name = (
                cfg.get("long_name", "")
                if len(reply["LongName"]) == 0
                else reply["LongName"]
            )

            # Update configuration in memory.
            self.config["net"] = net
            self.config["sub"] = sub
            self.config["universe"] = universe
            self.config["port_name"] = port_name
            self.config["long_name"] = long_name

            if self.config_update_callback:
                self.config_update_callback(self.config)

            print(f"ArtAddress configuration updated: {self.config}")

        except Exception as e:
            print(f"Error handling ArtAddress packet: {e}")
